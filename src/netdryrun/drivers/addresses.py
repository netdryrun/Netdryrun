"""A node's own IP addresses, for the ping check's own-address refusal (0.4.1 red team B-9006, design round 3 R6).

Every parser reads a live capture's shape (tests/fixtures/*_local_*). JSON that doesn't parse, or a shape these parsers
don't know, raises: the ping check then reads the sample as unready and retries, and still unreadable at its timeout it
fails, never "not an own address". Truncated output is JSON that doesn't parse, so it raises too.
"""
from __future__ import annotations

import ipaddress
import json
import re

from .base import DriverError, unexpected


def _strict(fn):
    """Any shape the parser doesn't know (a list where a map was, a number where a list was) is unexpected output: a
    DriverError, never another exception and never "no addresses"."""
    import functools

    @functools.wraps(fn)
    def run(*args, **kw):
        try:
            return fn(*args, **kw)
        except DriverError:
            raise
        except Exception as e:
            raise unexpected(fn.__name__, f"{type(e).__name__}: {e}") from None
    return run


def _load(command: str, text: str):
    # the whole answer is the JSON document, with only whitespace around it: text before it (a CLI error line, a
    # banner) is unexpected output, never skipped (FP-042-ADDRLOAD: skipping it read malformed output as no addresses)
    try:
        return json.loads(text.strip())
    except (ValueError, TypeError, AttributeError, RecursionError) as e:
        raise unexpected(command, f"not JSON ({e}): {str(text)[:120]!r}") from None


def _iface(command: str, text: str, prefixlen: object = None) -> ipaddress._BaseAddress:
    try:
        addr = str(text).split("%")[0]
        return ipaddress.ip_interface(addr if prefixlen is None or "/" in addr else f"{addr}/{prefixlen}")
    except ValueError:
        raise unexpected(command, f"not an address: {str(text)[:60]!r}") from None


@_strict
def parse_ip_j_addr(text: str, skip_enslaved: bool, command: str = "ip -j addr") -> list:
    """`ip -j addr [show vrf X]` (iproute2, FRR and SONiC containers). For the default VRF, interfaces with a master
    (enslaved to a VRF device) are left out; `show vrf X` lists only that VRF's interfaces."""
    data = _load(command, text)
    if not isinstance(data, list):
        raise unexpected(command, str(data)[:150])
    out = []
    for link in data:
        # every live link prints addr_info ([] without addresses): one without it is unexpected, never "no addresses"
        if not isinstance(link, dict) or not isinstance(link.get("addr_info"), list):
            raise unexpected(command, str(link)[:150])
        if skip_enslaved and link.get("master"):
            continue
        for a in link["addr_info"]:
            if not isinstance(a, dict) or "local" not in a:
                raise unexpected(command, str(a)[:150])
            addr = _iface(command, a["local"], a.get("prefixlen"))
            # Linux answers for every address of a prefix on lo (10.9.0.1/24 dev lo makes 10.9.0.5 local): the whole
            # prefix is the node's own, marked by LOCAL_PREFIX
            out.append(LocalPrefix(addr) if link.get("ifname") == "lo" and addr.network.prefixlen < addr.max_prefixlen
                       else addr)
    return out


@_strict
def parse_vrf_device_addr(text: str, vrf: str, command: str) -> list:
    """`ip -j addr show dev <vrf>`: the VRF device's own addresses. `show vrf X` lists only the interfaces enslaved to
    X, never X itself, yet the kernel answers a ping in X to an address on X locally (FP-043-VRFDEV, RT-0053). The
    answer must be exactly that one device; anything else is unexpected output, never "no addresses"."""
    data = _load(command, text)
    if not isinstance(data, list) or len(data) != 1 or not isinstance(data[0], dict) or data[0].get("ifname") != vrf:
        raise unexpected(command, str(data)[:150])
    # a plain device, not lo: only its addresses are the node's own, not the rest of their subnets
    return parse_ip_j_addr(text, skip_enslaved=False, command=command)


@_strict
def parse_eos_interfaces(text: str, vrf: str, command: str) -> list:
    """`show ip interface | json` and `show ipv6 interface | json` (cEOS): each interface names its `vrf`."""
    data = _load(command, text)
    ifs = data.get("interfaces") if isinstance(data, dict) else None
    if not isinstance(ifs, dict):
        raise unexpected(command, str(data)[:150])
    out = []
    for name, i in ifs.items():
        if not isinstance(i, dict) or not isinstance(i.get("vrf"), str):
            raise unexpected(command, f"{name}: no vrf")
        if i["vrf"] != vrf:
            continue
        ia = i.get("interfaceAddress")
        if ia is not None:   # IPv4
            if not isinstance(ia, dict):
                raise unexpected(command, f"{name}: interfaceAddress {str(ia)[:80]}")
            # an `ip address virtual` (anycast gateway) is the node's own as much as its primary (red team round 4,
            # RT-0046); "0.0.0.0" is how cEOS prints an unset one (eos_local_ipv4.json)
            singles = [ia.get("primaryIp"), ia.get("virtualIp")]
            lists = [ia.get("secondaryIpsOrderedList"), ia.get("virtualSecondaryIpsOrderedList")]
            if any(x is not None and not isinstance(x, list) for x in lists):
                raise unexpected(command, f"{name}: an address list that isn't a list")
            for a in singles + [x for lst in lists if lst for x in lst]:
                if a is None:
                    continue
                if not isinstance(a, dict) or "address" not in a:
                    raise unexpected(command, f"{name}: address entry {str(a)[:80]}")
                if a["address"] != "0.0.0.0":
                    out.append(_iface(command, a["address"], a.get("maskLen")))
        addrs6 = i.get("addresses")
        if addrs6 is not None and not isinstance(addrs6, list):
            raise unexpected(command, f"{name}: addresses {str(addrs6)[:80]}")
        for a in addrs6 or []:   # IPv6
            if not isinstance(a, dict) or not a.get("address"):
                raise unexpected(command, f"{name}: IPv6 address entry {str(a)[:80]}")
            out.append(_iface(command, a["address"], str(a.get("subnet", "/128")).split("/")[-1]))
        ll = i.get("linkLocal")
        if ll is not None:
            if not isinstance(ll, dict):
                raise unexpected(command, f"{name}: linkLocal {str(ll)[:80]}")
            if ll.get("address"):
                out.append(_iface(command, ll["address"], 64))
    return out


def _nxos_rows(command: str, text: str) -> list:
    data = _load(command, text)
    if isinstance(data, dict) and "result" in data and data["result"] is None:
        return []   # NX-API's "printed nothing" (no address of this family anywhere; nxos_*_emptyvrf_null.txt)
    try:
        body = data["result"]["body"]
    except (KeyError, TypeError):
        raise unexpected(command, str(data)[:150]) from None
    rows = (body.get("TABLE_intf") or {}).get("ROW_intf") if isinstance(body, dict) else None
    if isinstance(rows, dict):
        rows = [rows]
    if not isinstance(rows, list):
        raise unexpected(command, str(body)[:150])
    for r in rows:
        if not isinstance(r, dict) or not isinstance(r.get("vrf-name-out"), str):
            raise unexpected(command, f"row {str(r)[:80]}")
    return rows


def _rows_of(command: str, table, key: str) -> list:
    rows = (table or {}).get(key) if isinstance(table, (dict, type(None))) else None
    if table is not None and rows is None:
        raise unexpected(command, f"{key}: {str(table)[:80]}")
    if isinstance(rows, dict):
        rows = [rows]
    if rows is not None and not isinstance(rows, list):
        raise unexpected(command, f"{key}: {str(rows)[:80]}")
    return rows or []


@_strict
def parse_nxos_ip_detail(text: str, vrf: str, command: str = "show ip interface vrf all") -> list:
    """NX-API `show ip interface vrf all` (n9kv 10.x, captured 2026-11-06): each interface's primary `prefix`/`masklen`
    and its secondaries (TABLE_secondary_address rows with prefixN/masklenN), which the brief form leaves out (red team
    round 4, RT-0045). The masks make subnet broadcasts refusable too."""
    out = []
    for r in _nxos_rows(command, text):
        if r["vrf-name-out"] != vrf:
            continue
        if not r.get("prefix") or "masklen" not in r:
            raise unexpected(command, f"{r.get('intf-name')}: no prefix or masklen")
        out.append(_iface(command, r["prefix"], r["masklen"]))
        for sec in _rows_of(command, r.get("TABLE_secondary_address"), "ROW_secondary_address"):
            if not isinstance(sec, dict):
                raise unexpected(command, f"{r.get('intf-name')}: secondary {str(sec)[:80]}")
            pairs = [(k, "masklen" + k[len("prefix"):]) for k in sec if re.fullmatch(r"prefix\d+", k)]
            if not pairs or any(m not in sec for _, m in pairs):
                raise unexpected(command, f"{r.get('intf-name')}: secondary {str(sec)[:80]}")
            out += [_iface(command, sec[k], sec[m]) for k, m in pairs]
    return out


@_strict
def parse_nxos_ipv6_detail(text: str, vrf: str, command: str = "show ipv6 interface vrf all") -> list:
    """NX-API `show ipv6 interface vrf all` (captured 2026-11-06): every address of TABLE_addr (`addr` with its prefix
    length) and the interface's link-local address."""
    out = []
    for r in _nxos_rows(command, text):
        if r["vrf-name-out"] != vrf:
            continue
        addrs = _rows_of(command, r.get("TABLE_addr"), "ROW_addr")
        if not addrs and not r.get("linklocal-addr"):   # link-local only (`use-link-local-only`) has no TABLE_addr
            raise unexpected(command, f"{r.get('intf-name')}: no TABLE_addr")
        for a in addrs:
            if not isinstance(a, dict) or not isinstance(a.get("addr"), str):
                raise unexpected(command, f"{r.get('intf-name')}: address {str(a)[:80]}")
            out.append(_iface(command, a["addr"]))
        if r.get("linklocal-addr"):
            out.append(_iface(command, r["linklocal-addr"], 64))
    return out


@_strict
def parse_nxos_ip_brief(text: str, vrf: str, command: str = "show ip interface brief vrf all") -> list:
    """NX-API `show ip interface brief vrf all`: ROW_intf rows with vrf-name-out and prefix (the address, no mask)."""
    data = _load(command, text)
    try:
        body = data["result"]["body"]
    except (KeyError, TypeError):
        raise unexpected(command, str(data)[:150]) from None
    rows = (body.get("TABLE_intf") or {}).get("ROW_intf") if isinstance(body, dict) else None
    if isinstance(rows, dict):
        rows = [rows]
    if not isinstance(rows, list):
        raise unexpected(command, str(body)[:150])
    out = []
    for r in rows:
        if not isinstance(r, dict) or not isinstance(r.get("vrf-name-out"), str):
            raise unexpected(command, f"row {str(r)[:80]}")
        if r["vrf-name-out"] != vrf:
            continue
        if not r.get("prefix"):
            raise unexpected(command, f"{r.get('intf-name')}: no prefix")
        out.append(_iface(command, r["prefix"], 32))
    return out


@_strict
def parse_routeros_addresses(rows: list, vrf: str, command: str) -> list:
    """REST /ip/address and /ipv6/address rows: `vrf` ("main" is the default VRF), disabled and invalid rows left out."""
    if not isinstance(rows, list):   # a map (even {}) is no row list: never "no addresses" (found by the fuzzer)
        raise unexpected(command, str(rows)[:150])
    want = "main" if vrf == "default" else vrf
    out = []
    for r in rows:
        if not isinstance(r, dict) or "address" not in r or "vrf" not in r:
            raise unexpected(command, str(r)[:150])
        if r["vrf"] == want and str(r.get("disabled")) != "true" and str(r.get("invalid")) != "true":
            out.append(_iface(command, r["address"]))
    return out


@_strict
def parse_srl_addresses(text: str, command: str) -> list:
    """`info from state /interface * subinterface * ipv4|ipv6 address *` (SR Linux): every subinterface's addresses,
    whatever network-instance it is in (the capture doesn't map them; see local_addresses)."""
    data = _load(command, text)
    ifs = data.get("interface") if isinstance(data, dict) else None
    if not isinstance(ifs, list):
        raise unexpected(command, str(data)[:150])
    out = []
    for i in ifs:
        if not isinstance(i, dict) or not isinstance(i.get("subinterface", []), list):
            raise unexpected(command, f"interface {str(i)[:80]}")
        for sub in i.get("subinterface", []):
            if not isinstance(sub, dict):
                raise unexpected(command, f"subinterface {str(sub)[:80]}")
            for fam in ("ipv4", "ipv6"):
                block = sub.get(fam, {})
                if not isinstance(block, dict) or not isinstance(block.get("address", []), list):
                    raise unexpected(command, f"{fam} block {str(block)[:80]}")
                for a in block.get("address", []):
                    if not isinstance(a, dict) or "ip-prefix" not in a:
                        raise unexpected(command, str(a)[:150])
                    out.append(_iface(command, a["ip-prefix"]))
    return out


@_strict
def parse_junos_terse(text: str, command: str = "show interfaces terse") -> list:
    """`show interfaces terse | display json` (cJunosEvolved): every ifa-local of every logical interface, whatever
    routing-instance it is in (the capture doesn't map them; see local_addresses)."""
    data = _load(command, text)
    out = []

    def walk(x):
        if isinstance(x, dict):
            for k, v in x.items():
                if k == "ifa-local":
                    for leaf in v if isinstance(v, list) else [v]:
                        val = leaf.get("data") if isinstance(leaf, dict) else None
                        if not isinstance(val, str):
                            raise unexpected(command, f"ifa-local {str(leaf)[:80]}")
                        out.append(_iface(command, val))
                else:
                    walk(v)
        elif isinstance(x, list):
            for v in x:
                walk(v)
    if not isinstance(data, dict) or "interface-information" not in data:
        raise unexpected(command, str(data)[:150])
    walk(data)
    return out


class LocalPrefix:
    """An address on Linux's lo whose whole prefix is local to the node."""

    def __init__(self, iface):
        self.iface = iface
        self.ip, self.network, self.version = iface.ip, iface.network, iface.version

    def __str__(self):
        return f"{self.iface} (lo: the whole prefix is local)"


def refuse_own_target(node: str, target: str, addrs: list) -> None:
    """The ping target must not be one of the node's own addresses, or the broadcast address of one of its IPv4
    subnets: such a ping never leaves the node (red team B-9006). A runtime error read as unready: never a pass."""
    ip = ipaddress.ip_address(str(target).split("%")[0])
    for a in addrs:
        if isinstance(a, LocalPrefix) and ip in a.network:
            raise DriverError(f"ping target {target} is inside {a.network}, which is on {node}'s lo: the node answers "
                              "it itself, so the ping never leaves the node")
        if a.ip == ip:
            raise DriverError(f"ping target {target} is an address of {node} itself ({a}): the ping never leaves the "
                              "node, so it says nothing about the network")
        if a.version == 6 and a.network.prefixlen < 127 and a.network.network_address == ip:
            raise DriverError(f"ping target {target} is the subnet-router anycast address of {node}'s prefix {a.network}: "
                              "the node answers it itself, so the ping never leaves the node")
        if a.version == 4 and a.network.prefixlen < 31 and a.network.broadcast_address == ip:
            raise DriverError(f"ping target {target} is the broadcast address of {node}'s subnet {a.network}")
