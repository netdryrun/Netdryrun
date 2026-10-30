"""Cisco NX-OS (Nexus 9000v, containerlab kind cisco_n9kv) driver. Beta.

NX-OS runs in a VM inside the vrnetlab container, so `docker exec` reaches the container, not the
switch. The driver asks NX-API (enabled by vrnetlab's bootstrap config) from inside the container:
a small Python helper POSTs one JSON-RPC request to https://127.0.0.1/ins, which qemu forwards to the
VM, and prints the reply. A transport failure (the VM still booting, NX-API not up) exits non-zero: an
error, never "no state".

NX-API quirks this driver reads around:
- `"result": null` is NX-OS's answer for a command that printed nothing. It means "nothing" only once
  the VRF is confirmed to exist (`show vrf <name>`), as on FRR and SR Linux.
- A table with one row is an object, with several rows a list (`TABLE_x.ROW_x`); both are read, any
  other type is unexpected.
- Numbers and booleans may be strings ("65001", "true").
"""
from __future__ import annotations

import ipaddress
import re

from .base import (BgpNeighbor, BgpPath, Driver, DriverError, NoSuchInstance, Observation, Route, as_int,
                   canon_communities, check_vrf_name, load_json, network, parser, render_as_path, unexpected)
from .frr import _canon_addr, parse_ping
from .stale import refuse_if_stale

# Runs inside the vrnetlab container (python3 is there for launch.py). argv: method, command, timeout.
# The credentials are the ones containerlab passed to launch.py (default admin/admin).
HELPER = r"""
import base64, json, os, ssl, sys, urllib.error, urllib.request
def creds():
    for pid in os.listdir("/proc"):
        try:
            a = open("/proc/%s/cmdline" % pid, "rb").read().decode().split("\0")
        except (OSError, ValueError):
            continue
        if any(x.endswith("launch.py") for x in a):
            get = lambda k, d: a[a.index(k) + 1] if k in a[:-1] else d
            return get("--username", "admin"), get("--password", "admin")
    return "admin", "admin"
method, cmd, timeout = sys.argv[1], sys.argv[2], float(sys.argv[3])
u, p = creds()
body = json.dumps({"jsonrpc": "2.0", "method": method, "params": {"cmd": cmd, "version": 1}, "id": 1}).encode()
auth = base64.b64encode(("%s:%s" % (u, p)).encode()).decode()
req = urllib.request.Request("https://127.0.0.1/ins", body,
                             {"Content-Type": "application/json-rpc", "Authorization": "Basic " + auth})
try:
    r = urllib.request.urlopen(req, timeout=timeout, context=ssl._create_unverified_context())
    out = r.read()
except urllib.error.HTTPError as e:
    out = e.read()   # a CLI error is HTTP 400 or 500 with a JSON-RPC error body: the parser reads it
    if e.code not in (400, 500) or not out.strip().startswith((b"{", b"[")):
        sys.stderr.write("NX-API answered HTTP %d\n" % e.code)
        sys.exit(3)
except Exception as e:
    sys.stderr.write("NX-API not reachable (is NX-OS still booting?): %s: %s\n" % (type(e).__name__, e))
    sys.exit(3)
sys.stdout.write(out.decode("utf-8", "replace"))
"""

# NX-OS client names (show ip route `clientname`) -> the shared vocabulary (FRR's names)
PROTOCOLS = {"bgp": "bgp", "direct": "connected", "local": "local", "static": "static", "ospf": "ospf",
             "ospfv3": "ospf6", "isis": "isis", "rip": "rip", "eigrp": "eigrp", "hsrp": "hsrp", "am": "local",
             "discard": "static", "broadcast": "local"}

SUMMARY_CMD = "show bgp <afi> unicast summary vrf <vrf>"
ROUTE_CMD = "show ip route <prefix> vrf <vrf>"
ALL_ROUTES_CMD = "show ip route vrf <vrf>"
BGP_CMD = "show bgp <afi> unicast <prefix> vrf <vrf>"
VRF_CMD = "show vrf <vrf>"
BGP_VRFS_CMD = "show bgp vrf all ipv4 unicast summary"
PING_CMD = "ping <target> vrf <vrf>"

# An NX-OS error that says the VRF itself is missing (checked against live output, see the fixtures)
_NO_VRF = re.compile(r"vrf\S*\s+\S+\s+(?:does not exist|not found|is not configured)|no such vrf|invalid vrf"
                     r"|vrf\s+not\s+found", re.I)


class CliError(DriverError):
    """NX-OS answered the command with an error (not a transport failure, not unreadable output)."""


def _reply(command: str, text: str):
    """The body of an NX-API JSON-RPC reply, or None for `"result": null` (the command printed nothing).
    An error reply raises: NoSuchInstance when it says the VRF doesn't exist, DriverError otherwise."""
    data = load_json(command, text)
    if isinstance(data, list) and len(data) == 1:
        data = data[0]
    if not isinstance(data, dict):
        raise unexpected(command, text)
    if "error" in data:
        err = data["error"]
        msg = err.get("data", {}).get("msg") if isinstance(err, dict) and isinstance(err.get("data"), dict) else None
        msg = " ".join(str(msg or (err.get("message") if isinstance(err, dict) else err) or "").split())
        if _NO_VRF.search(msg):
            raise NoSuchInstance(f"NX-OS: {msg}")
        raise CliError(f"NX-OS error from `{command}`: {msg[:200] or 'no message'}")
    if "result" not in data:
        raise unexpected(command, text)
    res = data["result"]
    if res is None:
        return None
    if not isinstance(res, dict) or res.get("body") is None:   # "nothing" is `"result": null`, never a null body
        raise unexpected(command, text)
    return res["body"]


def _body(command: str, text: str) -> dict | None:
    """A structured (`cli`) body: a JSON object, or None for no output."""
    body = _reply(command, text)
    if body is None:
        return None
    if not isinstance(body, dict):
        raise unexpected(command, f"body is not an object: {str(body)[:150]}")
    return body


def _rows(command: str, obj: dict, name: str, required: bool = True) -> list[dict]:
    """obj["TABLE_<name>"]["ROW_<name>"] as a list (NX-OS gives one row as an object, several as a list).
    A missing table is [] only where the caller says NX-OS leaves it out for "none" (required=False)."""
    table = obj.get(f"TABLE_{name}")
    if table is None and not required:
        return []
    if not isinstance(table, dict) or f"ROW_{name}" not in table:
        raise unexpected(command, f"no TABLE_{name}.ROW_{name}: {str(obj)[:150]}")
    rows = table[f"ROW_{name}"]
    rows = [rows] if isinstance(rows, dict) else rows
    if not isinstance(rows, list) or not rows or not all(isinstance(r, dict) for r in rows):
        raise unexpected(command, f"ROW_{name}: {str(rows)[:150]}")
    return rows


def _flag(command: str, value: object) -> bool:
    if value is True or value is False:
        return value
    if isinstance(value, str) and value.lower() in ("true", "false"):
        return value.lower() == "true"
    raise unexpected(command, f"not a boolean: {str(value)[:80]!r}")


def _vrf_rows(command: str, body: dict, vrf: str) -> list[dict]:
    """The rows for `vrf` (NX-OS may list a VRF more than once, once without its tables). A body
    without the VRF answers for something else: unexpected, never "nothing in this VRF"."""
    rows = _rows(command, body, "vrf")
    for r in rows:
        if not isinstance(r.get("vrf-name-out"), str):
            raise unexpected(command, f"vrf row without vrf-name-out: {str(r)[:150]}")
    mine = [r for r in rows if r["vrf-name-out"] == vrf]
    if not mine:
        raise unexpected(command, f"no answer for vrf {vrf} (vrfs: {', '.join(r['vrf-name-out'] for r in rows)})")
    return mine


# ------------------------------------------------------------------------------------------- parsers

@parser(SUMMARY_CMD)
def parse_bgp_summary(text: str, vrf: str = "default", afi: str = "ipv4-unicast",
                      into: dict[str, BgpNeighbor] | None = None) -> dict[str, BgpNeighbor] | None:
    """`show bgp ipv4|ipv6 unicast summary vrf X`. None when NX-OS printed nothing (no BGP in that VRF;
    the driver confirms the VRF). Prefix counts are `prefixreceived`, the State/PfxRcd column."""
    body = _body(SUMMARY_CMD, text)
    if body is None:
        return None
    out = into if into is not None else {}
    for v in _vrf_rows(SUMMARY_CMD, body, vrf):
        for af in _rows(SUMMARY_CMD, v, "af", required=False):        # a VRF row without tables: none
            for saf in _rows(SUMMARY_CMD, af, "saf"):
                # NX-OS leaves TABLE_neighbor out for a family without peers, and then lists no peer counts
                peers = saf.get("configuredpeers", 0)
                for n in _rows(SUMMARY_CMD, saf, "neighbor", required=as_int(SUMMARY_CMD, peers) > 0):
                    addr, state = n.get("neighborid"), n.get("state")
                    if not isinstance(addr, str) or not addr or not isinstance(state, str) or not state.strip():
                        raise unexpected(SUMMARY_CMD, str(n)[:150])
                    key = _canon_addr(addr)
                    nb = out.get(key) or BgpNeighbor(addr, state.split()[0].lower())
                    if "prefixreceived" in n:
                        nb.prefixes[afi] = as_int(SUMMARY_CMD, n["prefixreceived"])
                    elif nb.state == "established":  # a missing count would read as 0 prefixes, passing `max`
                        raise unexpected(SUMMARY_CMD, f"{addr}: established without prefixreceived")
                    out[key] = nb
    return out


def _prefix_rows(command: str, body: dict | None, vrf: str) -> list[tuple[ipaddress._BaseNetwork, dict]]:
    """(prefix, row) for every TABLE_prefix row of `show ip|ipv6 route ... vrf X`."""
    if body is None:
        return []
    out = []
    for v in _vrf_rows(command, body, vrf):
        for af in _rows(command, v, "addrf", required=False):
            for p in _rows(command, af, "prefix", required=False):
                if "ipprefix" not in p:
                    raise unexpected(command, f"prefix row without ipprefix: {str(p)[:150]}")
                out.append((network(command, p["ipprefix"]), p))
    return out


def _rib_routes(command: str, prefix: str, row: dict) -> list[Route]:
    out = []
    for path in _rows(command, row, "path"):
        client = path.get("clientname")
        if not isinstance(client, str) or not client:
            raise unexpected(command, f"path without clientname: {str(path)[:150]}")
        proto = client.split("-")[0].lower()           # "bgp-65001", "ospf-1", "static", "direct"
        out.append(Route(prefix, PROTOCOLS.get(proto, proto), _flag(command, path.get("ubest", False))))
    return out


def _bgp_prefix_rows(command: str, body: dict | None, vrf: str) -> list[tuple[ipaddress._BaseNetwork, dict]]:
    """(prefix, row) for every prefix in `show bgp <afi> unicast [<prefix>] vrf X`."""
    if body is None:
        return []
    out = []
    for v in _vrf_rows(command, body, vrf):
        for afi in _rows(command, v, "afi", required=False):
            for safi in _rows(command, afi, "safi"):
                for rd in _rows(command, safi, "rd", required=False):
                    for p in _rows(command, rd, "prefix", required=False):
                        key = p.get("ipprefix", p.get("ipv6prefix"))
                        if key is None:
                            raise unexpected(command, f"prefix row without ipprefix: {str(p)[:150]}")
                        out.append((network(command, key), p))
    return out


def _bgp_paths_raw(text: str, prefix: str, vrf: str) -> list[dict]:
    want = ipaddress.ip_network(prefix)
    paths = []
    for net, row in _bgp_prefix_rows(BGP_CMD, _body(BGP_CMD, text), vrf):
        if net == want:
            paths += _rows(BGP_CMD, row, "path")
    for p in paths:
        if "pathstaled" in p:   # graceful restart: a stale path is neither present nor gone yet
            refuse_if_stale(prefix, p.get("ipv6neighbor", p.get("neighbor")), _flag(BGP_CMD, p["pathstaled"]))
    return paths


def _peer(p: dict) -> str:
    """The address the path came from: `neighbor` (IPv4) or `ipv6neighbor`; 0.0.0.0 for the router's own.
    (`neighborid` is the peer's router ID, and the router's own ID for a local path: not an address.)"""
    peer = p.get("ipv6neighbor", p.get("neighbor"))
    if not isinstance(peer, str) or not peer:
        raise unexpected(BGP_CMD, f"path without neighbor: {str(p)[:150]}")
    return peer


def _learned(p: dict) -> bool:
    """A path received from a BGP neighbor (pathtype external, internal, confederation...), not the
    router's own (pathtype local, aggregate, redist; neighbor 0.0.0.0). Valid or not, best or not, it
    was received."""
    kind = p.get("pathtype")
    if not isinstance(kind, str) or not kind:
        raise unexpected(BGP_CMD, f"path without pathtype: {str(p)[:150]}")
    return kind.lower() not in ("local", "aggregate", "redist", "redistributed") and _peer(p) not in ("0.0.0.0", "::")


@parser(ROUTE_CMD)
def parse_routes(route_text: str, bgp_text: str, prefix: str, vrf: str = "default") -> list[Route] | None:
    """Routing-table entries for exactly `prefix`, plus a not-installed BGP route when the BGP table holds
    a path learned from a neighbor that the routing table doesn't use (a static with a better distance
    wins, the next hop is unreachable): received, so present for `present: false`. None when both
    commands printed nothing: an absence the driver trusts only once the VRF is confirmed."""
    want = ipaddress.ip_network(prefix)
    rib = _body(ROUTE_CMD, route_text)
    bgp = _body(BGP_CMD, bgp_text)
    out = [r for net, row in _prefix_rows(ROUTE_CMD, rib, vrf) if net == want
           for r in _rib_routes(ROUTE_CMD, prefix, row)]
    paths = _bgp_paths_raw(bgp_text, prefix, vrf)   # read even when installed: a stale path is an error
    if not any(r.protocol == "bgp" for r in out) and any(_learned(p) for p in paths):
        out.append(Route(prefix, "bgp", False))
    if not out and rib is None and bgp is None:
        return None
    return out


@parser(ALL_ROUTES_CMD)
def parse_all_routes(text: str, vrf: str = "default") -> list[Route] | None:
    body = _body(ALL_ROUTES_CMD, text)
    if body is None:
        return None
    return [r for net, row in _prefix_rows(ALL_ROUTES_CMD, body, vrf) for r in _rib_routes(ALL_ROUTES_CMD, str(net), row)]


_AS_TOKEN = re.compile(r"\{([^}]*)\}|\[([^\]]*)\]|\(([^)]*)\)|(\S+)")


def _as_path(text: object) -> str:
    """NX-OS's AS path string ("65002 65003", sets "{65004 65005}", confederations "(65010 65011)") in
    the netdryrun.yml form. Any other token is unexpected."""
    if not isinstance(text, str):
        raise unexpected(BGP_CMD, f"aspath: {str(text)[:80]!r}")
    segs: list[tuple[str, list]] = []
    for m in _AS_TOKEN.finditer(text):
        aset, cset, cseq, asn = m.groups()
        members = next(g for g in (aset, cset, cseq, asn) if g is not None).replace(",", " ").split()
        if not members or not all(x.isdigit() for x in members):
            raise unexpected(BGP_CMD, f"aspath: {text[:80]!r}")
        kind = ("as-set" if aset is not None else "confed-set" if cset is not None
                else "confed-sequence" if cseq is not None else "as-sequence")
        segs.append((kind, members))
    return render_as_path(segs)


def _communities(p: dict, key: str) -> list[str]:
    """Communities under TABLE_<key>.ROW_<key> (one `<key>` per row) or as a plain string or list."""
    if f"TABLE_{key}" in p:
        rows = _rows(BGP_CMD, p, key)
        if not all(isinstance(r.get(key), str) for r in rows):
            raise unexpected(BGP_CMD, f"{key}: {str(rows)[:150]}")
        return canon_communities([r[key] for r in rows])
    v = p.get(key)
    if v is None:
        return []
    if isinstance(v, str):
        return canon_communities(v.split())
    if isinstance(v, list) and all(isinstance(x, str) for x in v):
        return canon_communities(v)
    raise unexpected(BGP_CMD, f"{key}: {str(v)[:80]!r}")


@parser(BGP_CMD)
def parse_bgp_paths(text: str, prefix: str, vrf: str = "default") -> list[BgpPath] | None:
    """Every path for exactly `prefix` in the BGP table, valid or not, best one flagged (`pathbest`).
    None when NX-OS printed nothing."""
    if _body(BGP_CMD, text) is None:
        return None
    out = []
    for p in _bgp_paths_raw(text, prefix, vrf):
        nh = p.get("ipv6nexthop", p.get("ipnexthop"))
        out.append(BgpPath(
            best=_flag(BGP_CMD, p.get("pathbest")),
            as_path=_as_path(p.get("aspath", "")),
            next_hop=_canon_addr(nh) if isinstance(nh, str) and nh else None,
            local_pref=as_int(BGP_CMD, p["localpref"]) if "localpref" in p else None,
            med=as_int(BGP_CMD, p.get("metric", 0)),
            communities=_communities(p, "community"),
            large_communities=_communities(p, "largecommunity"),
            neighbor=_canon_addr(_peer(p)) if _learned(p) else None,
        ))
    return out


@parser(BGP_VRFS_CMD)
def parse_bgp_vrfs(text: str) -> list[str]:
    """The VRFs BGP runs in (`show bgp vrf all ipv4 unicast summary`). Any error raises: an empty set
    would turn a failing summary into "no BGP instance"."""
    body = _body(BGP_VRFS_CMD, text)
    if body is None:
        raise unexpected(BGP_VRFS_CMD, "no output")
    rows = _rows(BGP_VRFS_CMD, body, "vrf")
    if not all(isinstance(r.get("vrf-name-out"), str) for r in rows):
        raise unexpected(BGP_VRFS_CMD, str(rows)[:150])
    return sorted({r["vrf-name-out"] for r in rows})


def parse_vrf_state(text: str, vrf: str) -> str | None:
    """`show vrf <name>`: the VRF's state ("Up"), or None when NX-OS doesn't list it. Fail-safe: None
    makes the driver raise "VRF ... does not exist"."""
    try:
        body = _body(VRF_CMD, text)
    except NoSuchInstance:
        return None
    if body is None:
        return None
    for row in _rows(VRF_CMD, body, "vrf"):
        if row.get("vrf_name") == vrf:
            state = row.get("vrf_state")
            if not isinstance(state, str):
                raise unexpected(VRF_CMD, str(row)[:150])
            return state
    return None


def parse_ping_reply(text: str) -> tuple[int, int]:
    """(sent, received) from a `cli_ascii` ping reply. Fail-safe: (0, 0) when ping did not run (an error
    reply, unreadable output), which the ping check reports and never passes on."""
    try:
        data = load_json(PING_CMD, text)
    except DriverError:
        return (0, 0)
    res = data.get("result") if isinstance(data, dict) else None
    msg = res.get("msg") if isinstance(res, dict) else None
    return parse_ping(msg) if isinstance(msg, str) else (0, 0)


# -------------------------------------------------------------------------------------------- driver

class NxosDriver(Driver):
    name = "nxos"
    # bgp_neighbors reads the IPv4 and IPv6 unicast summaries only: an EVPN count would always read 0
    unsupported_afis = frozenset({"evpn"})

    def _nxapi(self, command: str, evidence: list[dict], method: str = "cli", timeout: float = 60) -> str:
        """One NX-API request from inside the container. Not reaching NX-API is an error."""
        r = self.lab.exec(self.node, ["python3", "-c", HELPER, method, command, str(timeout)], timeout=timeout + 15)
        evidence.append({"node": self.node, "cmd": f"nxapi {method}: {command}", "rc": r.rc,
                         "output": r.stdout[-20000:], "stderr": r.stderr[-2000:]})
        if r.rc != 0:
            msg = (r.stderr or r.stdout).strip().splitlines()
            raise DriverError(f"`{command}` failed on {self.node} (rc={r.rc}): {msg[-1] if msg else 'no output'}")
        return r.stdout

    def _confirm_vrf(self, vrf: str, evidence: list[dict]) -> None:
        """Before an empty answer is trusted: NX-OS prints nothing for a VRF without the route and, for
        some commands, for a VRF that doesn't exist."""
        if vrf == "default":
            return
        state = parse_vrf_state(self._nxapi(f"show vrf {vrf}", evidence), vrf)
        if state is None:
            raise NoSuchInstance(f"VRF {vrf!r} does not exist on {self.node} (`show vrf {vrf}` doesn't list it)")
        if state.lower() != "up":
            raise NoSuchInstance(f"VRF {vrf!r} is {state} on {self.node}")

    def bgp_neighbors(self, vrf: str = "default") -> Observation:
        vrf = check_vrf_name(vrf)
        ev: list[dict] = []
        out: dict[str, BgpNeighbor] = {}
        try:
            parse_bgp_summary(self._nxapi(f"show bgp ipv4 unicast summary vrf {vrf}", ev), vrf, "ipv4-unicast", out)
            # A failing IPv6 summary raises: swallowing it would read every IPv6 prefix count as 0
            parse_bgp_summary(self._nxapi(f"show bgp ipv6 unicast summary vrf {vrf}", ev), vrf, "ipv6-unicast", out)
        except CliError:
            # NX-OS answers a bare "Invalid params" both for a VRF without BGP and a VRF that doesn't
            # exist. Only when BGP answers for its VRFs and this one isn't among them is it "no instance".
            vrfs = parse_bgp_vrfs(self._nxapi(BGP_VRFS_CMD, ev))
            if vrf in vrfs:
                raise
            self._confirm_vrf(vrf, ev)
            raise NoSuchInstance(f"no BGP instance in VRF {vrf!r} on {self.node} (BGP runs in: "
                                 f"{', '.join(sorted(vrfs))})") from None   # never empty: parse_bgp_vrfs raises
        if not out:
            self._confirm_vrf(vrf, ev)
        return Observation(out, ev)

    def routes(self, prefix: str, vrf: str = "default") -> Observation:
        vrf = check_vrf_name(vrf)
        ev: list[dict] = []
        fam, afi = ("ipv6", "ipv6") if ipaddress.ip_network(prefix).version == 6 else ("ip", "ipv4")
        rt = self._nxapi(f"show {fam} route {prefix} vrf {vrf}", ev)
        bgp = self._nxapi(f"show bgp {afi} unicast {prefix} vrf {vrf}", ev)
        routes = parse_routes(rt, bgp, prefix, vrf)
        if not routes:
            self._confirm_vrf(vrf, ev)
        return Observation(routes or [], ev)

    def bgp_paths(self, prefix: str, vrf: str = "default") -> Observation:
        vrf = check_vrf_name(vrf)
        ev: list[dict] = []
        afi = "ipv6" if ipaddress.ip_network(prefix).version == 6 else "ipv4"
        paths = parse_bgp_paths(self._nxapi(f"show bgp {afi} unicast {prefix} vrf {vrf}", ev), prefix, vrf)
        if not paths:
            self._confirm_vrf(vrf, ev)
        return Observation(paths or [], ev)

    def all_routes(self, vrf: str = "default", family: int = 4) -> Observation:
        vrf = check_vrf_name(vrf)
        ev: list[dict] = []
        fam = "ipv6" if family == 6 else "ip"
        routes = parse_all_routes(self._nxapi(f"show {fam} route vrf {vrf}", ev), vrf)
        if not routes:
            self._confirm_vrf(vrf, ev)
        return Observation(routes or [], ev)

    def ping(self, target: str, source: str | None, count: int, vrf: str = "default") -> Observation:
        vrf = check_vrf_name(vrf)
        ev: list[dict] = []
        fam = "ping6" if ipaddress.ip_address(target).version == 6 else "ping"
        cmd = f"{fam} {target} count {count}" + (f" source {source}" if source else "") + f" vrf {vrf}"
        r = self.lab.exec(self.node, ["python3", "-c", HELPER, "cli_ascii", cmd, str(count * 2 + 15)],
                          timeout=count * 2 + 30)
        ev.append({"node": self.node, "cmd": f"nxapi cli_ascii: {cmd}", "rc": r.rc, "output": r.stdout[-5000:],
                   "stderr": r.stderr[-1000:]})
        return Observation(parse_ping_reply(r.stdout) if r.rc == 0 else (0, 0), ev)
