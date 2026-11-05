"""A node's own IP addresses, for the ping check's own-address refusal (0.4.1 red team B-9006, design round 3 R6).

Every parser reads a live capture's shape (tests/fixtures/*_local_*). JSON that doesn't parse, or a shape these parsers
don't know, raises: the ping check then reads the sample as unready and retries, and still unreadable at its timeout it
fails, never "not an own address". Truncated output is JSON that doesn't parse, so it raises too.
"""
from __future__ import annotations

import ipaddress
import json

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
    try:
        i = min(x for x in (text.find("{"), text.find("[")) if x >= 0)
        return json.loads(text[i:])
    except (ValueError, TypeError) as e:
        raise unexpected(command, f"not JSON ({e}): {text[:120]!r}") from None


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
        if not isinstance(link, dict) or not isinstance(link.get("addr_info", []), list):
            raise unexpected(command, str(link)[:150])
        if skip_enslaved and link.get("master"):
            continue
        for a in link.get("addr_info", []):
            if not isinstance(a, dict) or "local" not in a:
                raise unexpected(command, str(a)[:150])
            addr = _iface(command, a["local"], a.get("prefixlen"))
            # Linux answers for every address of a prefix on lo (10.9.0.1/24 dev lo makes 10.9.0.5 local): the whole
            # prefix is the node's own, marked by LOCAL_PREFIX
            out.append(LocalPrefix(addr) if link.get("ifname") == "lo" and addr.network.prefixlen < addr.max_prefixlen
                       else addr)
    return out


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
        if isinstance(ia, dict):   # IPv4
            for a in [ia.get("primaryIp"), *(ia.get("secondaryIpsOrderedList") or [])]:
                if isinstance(a, dict) and a.get("address") not in (None, "0.0.0.0"):
                    out.append(_iface(command, a["address"], a.get("maskLen")))
        for a in i.get("addresses") or []:   # IPv6
            if isinstance(a, dict) and a.get("address"):
                out.append(_iface(command, a["address"], str(a.get("subnet", "/128")).split("/")[-1]))
        ll = i.get("linkLocal")
        if isinstance(ll, dict) and ll.get("address"):
            out.append(_iface(command, ll["address"], 64))
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
    return [_iface(command, r["prefix"], 32) for r in rows
            if isinstance(r, dict) and r.get("vrf-name-out") == vrf and r.get("prefix")]


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
        for sub in (i.get("subinterface") or []) if isinstance(i, dict) else []:
            for fam in ("ipv4", "ipv6"):
                for a in ((sub.get(fam) or {}).get("address") or []) if isinstance(sub, dict) else []:
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
        if a.version == 4 and a.network.prefixlen < 31 and a.network.broadcast_address == ip:
            raise DriverError(f"ping target {target} is the broadcast address of {node}'s subnet {a.network}")
