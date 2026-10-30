"""FRRouting driver: vtysh JSON output plus ping from the container.

Every parser checks the structure it reads. Output it doesn't recognize (a renamed key, a warning
object, output keyed by VRF) raises a DriverError: it is never read as "no routes", which would make
a `present: false` check pass.
"""
from __future__ import annotations

import ipaddress
import re
from collections import Counter

from .base import (BgpNeighbor, BgpPath, Driver, DriverError, NoSuchInstance, Observation, Route, as_int, canon_communities,
                   check_vrf_name, load_json, network, parser, render_as_path, unexpected)

AFI_NAMES = {"ipv4Unicast": "ipv4-unicast", "ipv6Unicast": "ipv6-unicast", "l2VpnEvpn": "evpn"}

NEIGHBORS_CMD = "show bgp neighbors json"
ROUTE_CMD = "show ip route <prefix> json"
ALL_ROUTES_CMD = "show ip route json"
BGP_PATHS_CMD = "show bgp <afi> unicast <prefix> json"
BGP_TABLE_CMD = "show bgp ipv4 unicast <prefix> longer-prefixes json"
VRF_CMD = "show vrf"

# bgpd's answers when the BGP instance itself is missing (no `router bgp` in that VRF)
_NO_INSTANCE = re.compile(r"unknown|not found", re.I)


def _canon_addr(addr: str) -> str:
    """Canonical address key so 2001:db8:0::1 and 2001:db8::1 match; non-IP keys (interfaces) kept."""
    try:
        return str(ipaddress.ip_address(addr.split("%")[0]))
    except ValueError:
        return addr


def _keep_down(out: dict, key: str, n: BgpNeighbor) -> None:
    """Add a neighbor under its canonical key. Scoped link-locals (fe80::1%eth1, fe80::1%eth2) differ only by
    zone and share a key: the key is then ambiguous (every session listed, so no check is evaluated on it), and
    the one that isn't established is kept, so the convergence gate never reads a down session as up."""
    old = out.get(key)
    if old is None:
        out[key] = n
        return
    keep = n if old.state == "established" else old
    keep.ambiguous = (old.ambiguous or [old.address]) + [n.address]
    out[key] = keep


# vtysh -b, which loads frr.conf at boot, prints one of these for every line it couldn't apply, then goes on: the
# router runs without the line (vtysh/vtysh.c, vtysh_config_from_file; FRR 10.4.1 boot logs in tests/fixtures)
_LOAD_ERROR = re.compile(r"^line (\d+): (?:% (Unknown command|Ambiguous command|Command incomplete)(?:\[\d+\])?: "
                         r"|(Warning)(?:\[\d+\])?\.\.\.: |Failure to communicate\[\d+\] to (\S+), line: )(.*)$")
_LOAD_FAILURE = re.compile(r"^\[\d+\|(\S+)\] Configuration file\[.*\] processing failure: (\d+)$")
# a daemon reading its own file (bgpd.conf, no integrated frr.conf) logs "<reason> on config line N: <line>"
_DAEMON_LINE = re.compile(r"^\S+ \S+ (\w+): (?:\[[^\]]*\])*\s*(.*?) on config line (\d+): (.*)$")
# vtysh -b's own output at boot: there was a config load to report on
LOAD_RAN = re.compile(r"^\[\d+\|\S+\] (?:sending configuration|done$|Configuration file\[)|on config line \d+: ",
                      re.M)


def _lines(text: str) -> list[str]:
    """Lines as vtysh numbers them (it reads with fgets: only \\n ends a line). str.splitlines() also splits on \\f,
    \\x0b, U+2028 and more, which would shift every later line number onto another line."""
    parts = text.split("\n")
    if parts[-1] == "":   # the newline that ends the last line starts no line
        parts.pop()
    return [ln.removesuffix("\r") for ln in parts]


def _closes(line: str) -> bool:
    return line.startswith("!") or line in ("exit", "end") or line.startswith("exit-")


def config_sections(text: str) -> list[tuple[tuple[str, ...], str]]:
    """Each line of an FRR config as (every header above it, the line), all stripped: `router bgp 65000` >
    `address-family l2vpn evpn` > `vni 10` > `route-target import 65000:99`. The headers come from indentation, at
    every depth (two `vni` blocks are two sections); a comment or `exit` line is never a header. vtysh itself places
    a line by the commands before it, not by indentation, so `parse_config_load_errors` doesn't rely on this alone."""
    out, stack = [], []   # stack: (indent, line) of the headers open above the current line
    for raw in _lines(text):
        line = raw.strip()
        if not line:
            out.append((tuple(h for _, h in stack), line))
            continue
        indent = len(raw.expandtabs(8)) - len(raw.expandtabs(8).lstrip())
        while stack and stack[-1][0] >= indent:
            stack.pop()
        out.append((tuple(h for _, h in stack), line))
        if not _closes(line):
            stack.append((indent, line))
    return out


def _significant(lines) -> list[str]:
    return [ln.strip() for ln in lines if ln.strip() and not ln.strip().startswith("!")]


def _blocks(text: str) -> list[list[str]]:
    """A config cut at every line that starts at the left margin: each block is that line and the lines under it."""
    out: list[list[str]] = []
    for raw in _lines(text):
        if raw.strip() and raw[:1] not in (" ", "\t"):
            out.append([])
        if out:
            out[-1].append(raw)
    return out


def _within(small: list[str], big: list[str]) -> bool:
    """Every line of `small`, in order, among the lines of `big`."""
    rest = iter(big)
    return all(any(x == y for y in rest) for x in small)


def _block_applied(config: str, i: int, running: str) -> bool:
    """Line i's whole left-margin block in the file is, line by line in order, inside a block of the daemon's running
    config that has the same first line. Any line FRR rewrote, dropped or moved in that block (`route-target both`
    printed as import and export, a line placed in another block) breaks it."""
    raw = _lines(config)
    start = i
    while start > 0 and not (raw[start].strip() and raw[start][:1] not in (" ", "\t")):
        start -= 1
    end = i + 1
    while end < len(raw) and not (raw[end].strip() and raw[end][:1] not in (" ", "\t")):
        end += 1
    mine = _significant(raw[start:end])
    return bool(mine) and any(_significant(b)[:1] == mine[:1] and _within(mine, _significant(b))
                              for b in _blocks(running))


def _is_header(config: str, i: int) -> bool:
    """The file has deeper-indented lines right under line i: a block's first line. A header the daemon refused can
    still show in the running config (the block exists) while the lines under it went elsewhere."""
    raw = _lines(config)
    depth = lambda ln: len(ln.expandtabs(8)) - len(ln.expandtabs(8).lstrip())   # noqa: E731
    nxt = next((ln for ln in raw[i + 1:] if ln.strip() and not ln.strip().startswith("!")), None)
    return nxt is not None and depth(nxt) > depth(raw[i])


def communicate_daemons(text: str) -> list[str]:
    """The daemons a boot log says answered a config line with "Failure to communicate" (mgmtd left out): the only
    lines `parse_config_load_errors` can clear, each against that daemon's own running config."""
    return sorted({m.group(4) for raw in text.splitlines() if (m := _LOAD_ERROR.match(raw.strip())) and m.group(4)
                   and m.group(4) != "mgmtd"})


def parse_config_load_errors(text: str, running: dict[str, str] | None = None, config: str | None = None) -> list[str]:
    """The config lines FRR rejected at boot, from the container's log, each once, in line order. A daemon that
    reports a processing failure without any such line still counts.

    A daemon can answer a line with "Failure to communicate[13]" (CMD_WARNING_CONFIG_FAILED) and still apply it
    (`bgp graceful-restart`, FRR 10.4.1, Verdict Corpus case 29). With `running` (each such daemon's own
    `show running-config`, `vtysh -d <daemon>`: the merged view shows a route-map line zebra took and bgpd refused)
    and `config` (the frr.conf vtysh -b loaded), such a line doesn't count when line N of the file is that line and
    that daemon's running config has it in the same section (the same `router bgp ... vrf`, the same address
    family) at least as many times as the file does (two `vni` blocks share a section). Every other kind is never
    applied (a line vtysh couldn't parse never reaches a daemon) or can't be told apart, and always counts; so do
    lines for mgmtd, whose stored config can show a line a daemon then failed to apply, and lines for a daemon whose
    running config wasn't read. A line under other lines in the file (a header) always counts, and the line's whole
    left-margin block must be in that daemon's running config as written: vtysh places a line by the commands
    before it, not by its indentation, so the section check alone could match a misindented line elsewhere."""
    applied = {d: Counter(config_sections(t)) for d, t in (running or {}).items()}
    # vtysh reads a line into a 4096-byte buffer: a longer one counts as several lines, shifting every later N
    file = (config_sections(config) if config is not None
            and all(len(ln.encode()) < 4095 for ln in _lines(config)) else [])
    in_file = Counter(file)
    lines: dict[tuple[int, str], tuple[bool, str, str]] = {}   # (line, source) -> (applied, daemon, message)
    failures: list[tuple[str, str]] = []
    for raw in text.splitlines():
        m = _LOAD_ERROR.match(raw.strip())
        if m:
            n, kind, warning, daemon, cmd = m.groups()
            why = kind or (f"rejected by {daemon}" if daemon else "warning")
            i = int(n) - 1
            done = (daemon in applied and daemon != "mgmtd" and 0 <= i < len(file) and file[i][1] == cmd.strip()
                    and applied[daemon][file[i]] >= in_file[file[i]] and not _is_header(config, i)
                    and _block_applied(config, i, running[daemon]))
            lines.setdefault((int(n), ""), (done, daemon or "", f"line {n}: {cmd.strip()} ({why})"))
            continue
        d = _DAEMON_LINE.match(raw.strip())
        if d:   # the daemon's own file, numbered on its own: kept apart from frr.conf's line N
            daemon, why, n, cmd = d.groups()
            lines.setdefault((int(n), daemon.lower()),
                             (False, "", f"line {n}: {cmd.strip()} ({why.strip()}, {daemon.lower()})"))
            continue
        f = _LOAD_FAILURE.match(raw.strip())
        if f:
            failures.append((f.group(1), f"{f.group(1)} reported a configuration file processing failure ({f.group(2)})"))
    kept = [msg for _, (done, _, msg) in sorted(lines.items()) if not done]
    if kept:
        return kept
    # every reported line was applied: a processing failure only its daemons' lines explain
    explained = {daemon for done, daemon, _ in lines.values()}
    return list(dict.fromkeys(msg for daemon, msg in failures if daemon not in explained))


def _bgp_json(command: str, text: str) -> dict:
    data = load_json(command, text)
    if not isinstance(data, dict):
        raise unexpected(command, text)
    if "warning" in data:  # e.g. {"warning": "View/Vrf is unknown"}
        if isinstance(data["warning"], str) and _NO_INSTANCE.search(data["warning"]):
            raise NoSuchInstance(f"vtysh: {data['warning']}")
        raise DriverError(f"vtysh: {data['warning']}")
    if data.get("bgpNoSuchInstance"):
        raise NoSuchInstance("vtysh: no BGP instance in this VRF")
    return data


@parser(NEIGHBORS_CMD)
def parse_bgp_neighbors(text: str) -> dict[str, BgpNeighbor]:
    """`show bgp [vrf X] neighbors json`: one object per neighbor, keyed by address (or interface)."""
    data = _bgp_json(NEIGHBORS_CMD, text)
    out = {}
    for addr, info in data.items():
        if not isinstance(info, dict) or not isinstance(info.get("bgpState"), str) or not info["bgpState"].strip():
            raise unexpected(NEIGHBORS_CMD, f"{addr}: {str(info)[:150]}")
        state = info["bgpState"].split()[0].lower()
        families = info.get("addressFamilyInfo", None if state == "established" else {})
        if not isinstance(families, dict):  # an established session always lists its families
            raise unexpected(NEIGHBORS_CMD, f"{addr} addressFamilyInfo: {str(families)[:150]}")
        prefixes = {}
        for afi, af in families.items():
            # a family without its counter would read as 0 prefixes, which satisfies `max` and `exact: 0`
            if not isinstance(af, dict) or "acceptedPrefixCounter" not in af:
                raise unexpected(NEIGHBORS_CMD, f"{addr} {afi}: no acceptedPrefixCounter")
            prefixes[AFI_NAMES.get(afi, afi)] = as_int(NEIGHBORS_CMD, af["acceptedPrefixCounter"])
        # "Idle (Admin)" -> "idle": the first word is the FSM state
        _keep_down(out, _canon_addr(addr), BgpNeighbor(addr, state, prefixes))
    return out


def _route_table(command: str, text: str) -> dict[ipaddress._BaseNetwork, list[dict]]:
    """zebra's `show ip route ... json`: {prefix: [entry, ...]}. `{}` is a real empty answer; any key
    that isn't a prefix (a warning, output keyed by VRF name) is unexpected."""
    data = load_json(command, text)
    if not isinstance(data, dict):
        raise unexpected(command, text)
    table = {}
    for key, entries in data.items():
        net = network(command, key)
        if not isinstance(entries, list) or not entries:
            raise unexpected(command, f"{key}: {str(entries)[:150]}")
        for e in entries:
            if not isinstance(e, dict) or not isinstance(e.get("protocol"), str):
                raise unexpected(command, f"{key}: {str(e)[:150]}")
        table[net] = entries
    return table


def _route(prefix: str, e: dict) -> Route:
    return Route(prefix, e["protocol"].lower(), bool(e.get("selected")) and bool(e.get("installed", True)))


def _bgp_paths_raw(command: str, text: str, prefix: str) -> list[dict]:
    """Path objects for exactly `prefix` from `show bgp ... <prefix> json`. `{}` means no path."""
    data = _bgp_json(command, text)
    if not data:
        return []
    if not isinstance(data.get("paths"), list) or "prefix" not in data:
        raise unexpected(command, text)
    if network(command, data["prefix"]) != ipaddress.ip_network(prefix):
        return []  # bgpd answered for another (covering) prefix: nothing for this one
    for p in data["paths"]:
        if not isinstance(p, dict):
            raise unexpected(command, f"path: {str(p)[:150]}")
        if p.get("stale"):
            # graceful restart: bgpd keeps the restarting peer's paths, marked stale, until it re-sends them or
            # the stale timer ends. Such a path is neither present nor gone yet, so no check can pass on it
            raise DriverError(f"{prefix}: BGP path from {(p.get('peer') or {}).get('peerId', '?')} is stale "
                              "(graceful restart in progress): not settled")
    return data["paths"]


def _learned(p: dict) -> bool:
    """A path received from a BGP neighbor, not the router's own (network statement, redistribution,
    aggregate). Validity and best-path selection don't matter: received but not selected is present."""
    peer = p.get("peer")
    if not isinstance(peer, dict) or not isinstance(peer.get("peerId"), str):  # every path names its peer
        raise unexpected(BGP_PATHS_CMD, f"path without peer: {str(p)[:150]}")
    if p.get("local") or p.get("sourced"):
        return False
    return peer["peerId"] not in ("", "0.0.0.0", "::")


@parser(ROUTE_CMD)
def parse_routes(text: str, prefix: str, bgp_text: str | None = None) -> list[Route]:
    """Routing-table entries for `prefix`, plus a not-installed BGP route when the BGP table has a path
    learned from a neighbor that zebra doesn't hold (invalid next hop, not selected): it was received,
    so it counts as present, as on EOS and SR Linux. zebra may answer with a covering prefix."""
    want = ipaddress.ip_network(prefix)
    out = [_route(prefix, e) for net, entries in _route_table(ROUTE_CMD, text).items() if net == want
           for e in entries]
    if bgp_text is not None:
        paths = _bgp_paths_for_route_check(bgp_text, prefix)   # read even when zebra has it: a stale path is an error
        if not any(r.protocol == "bgp" for r in out) and any(_learned(p) for p in paths):
            out.append(Route(prefix, "bgp", False))
    return out


def _bgp_paths_for_route_check(text: str, prefix: str) -> list[dict]:
    """The BGP side of a route check. No BGP instance in the VRF means no BGP paths (the VRF itself is
    confirmed separately); any other warning or shape is an error."""
    data = load_json(BGP_PATHS_CMD, text)
    if isinstance(data, dict) and data.get("bgpNoSuchInstance"):
        return []
    if isinstance(data, dict) and isinstance(data.get("warning"), str) and _NO_INSTANCE.search(data["warning"]):
        return []
    return _bgp_paths_raw(BGP_PATHS_CMD, text, prefix)


@parser(ALL_ROUTES_CMD)
def parse_all_routes(text: str) -> list[Route]:
    return [_route(str(net), e) for net, entries in _route_table(ALL_ROUTES_CMD, text).items() for e in entries]


def _next_hop(hops: list) -> str | None:
    """The global next hop (an IPv6 path may also list a link-local one); link-local only if nothing else."""
    hops = [h for h in hops if isinstance(h, dict) and h.get("ip")]
    best = next((h for h in hops if h.get("scope", "global") == "global"), hops[0] if hops else None)
    return _canon_addr(str(best["ip"])) if best else None


@parser(BGP_PATHS_CMD)
def parse_bgp_paths(text: str, prefix: str, default_local_pref: int | None = 100) -> list[BgpPath]:
    """`show bgp <afi> unicast <prefix> json`. A path without locPrf carries no LOCAL_PREF attribute
    (eBGP-learned or local), and FRR applies the instance's default local preference to it. Every path
    is listed, valid or not, best or not."""
    out = []
    for p in _bgp_paths_raw(BGP_PATHS_CMD, text, prefix):
        segs = [(s.get("type", ""), s.get("list") or []) for s in (p.get("aspath") or {}).get("segments") or []]
        out.append(BgpPath(
            best=bool((p.get("bestpath") or {}).get("overall")),
            as_path=render_as_path(segs),  # not aspath.string: FRR prints "Local" for an empty path
            next_hop=_next_hop(p.get("nexthops") or []),
            local_pref=as_int(BGP_PATHS_CMD, p["locPrf"]) if "locPrf" in p else default_local_pref,
            med=as_int(BGP_PATHS_CMD, p["metric"]) if "metric" in p else None,   # no MED attribute: unknown, not 0
            communities=canon_communities(((p.get("community") or {}).get("string") or "").split()),
            large_communities=canon_communities(((p.get("largeCommunity") or {}).get("string") or "").split()),
            neighbor=(p.get("peer") or {}).get("peerId"),
        ))
    return out


@parser(BGP_TABLE_CMD)
def parse_default_local_pref(text: str) -> int | None:
    """defaultLocPrf from the header of a BGP table listing (`bgp default local-preference`)."""
    data = _bgp_json(BGP_TABLE_CMD, text)
    if "routes" not in data:
        raise unexpected(BGP_TABLE_CMD, text)
    v = data.get("defaultLocPrf")
    return as_int(BGP_TABLE_CMD, v) if v is not None else None


def parse_vrfs(text: str) -> dict[str, bool]:
    """zebra's `show vrf`: "vrf NAME id N table T" (active) or "vrf NAME inactive"; default not listed."""
    out = {}
    for line in text.splitlines():
        m = re.match(r"\s*vrf\s+(\S+)\s*(.*)$", line)
        if m:
            out[m.group(1)] = not m.group(2).startswith("inactive")
    return out


def parse_ping(text: str) -> tuple[int, int]:
    """(sent, received). (0, 0) means ping did not run; the check reports that as an error."""
    m = re.search(r"(\d+) packets transmitted, (\d+) (?:packets )?received", text)
    return (int(m.group(1)), int(m.group(2))) if m else (0, 0)


class FrrDriver(Driver):
    name = "frr"

    def _vtysh(self, command: str, evidence: list[dict]) -> str:
        return self._exec(["vtysh", "-c", command], evidence)

    def _confirm_vrf(self, vrf: str, evidence: list[dict]) -> None:
        """Before an empty answer is trusted: zebra answers `{}` for a VRF that doesn't exist, exactly as
        for an existing VRF without the route, so check the VRF list."""
        if vrf == "default":
            return
        vrfs = parse_vrfs(self._vtysh(VRF_CMD, evidence))
        if vrf not in vrfs:
            raise NoSuchInstance(f"VRF {vrf!r} does not exist on {self.node} "
                              f"(`show vrf` lists: {', '.join(sorted(vrfs)) or 'none'})")
        if not vrfs[vrf]:
            raise NoSuchInstance(f"VRF {vrf!r} is configured on {self.node} but inactive (no kernel VRF device)")

    def bgp_neighbors(self, vrf: str = "default") -> Observation:
        vrf = check_vrf_name(vrf)
        ev: list[dict] = []
        cmd = "show bgp neighbors json" if vrf == "default" else f"show bgp vrf {vrf} neighbors json"
        neighbors = parse_bgp_neighbors(self._vtysh(cmd, ev))
        if not neighbors:
            self._confirm_vrf(vrf, ev)
        return Observation(neighbors, ev)

    def routes(self, prefix: str, vrf: str = "default") -> Observation:
        vrf = check_vrf_name(vrf)
        ev: list[dict] = []
        version = ipaddress.ip_network(prefix).version
        fam, afi = ("ipv6", "ipv6") if version == 6 else ("ip", "ipv4")
        vrf_part = "" if vrf == "default" else f" vrf {vrf}"
        text = self._vtysh(f"show {fam} route{vrf_part} {prefix} json", ev)
        bgp = self._vtysh(f"show bgp{vrf_part} {afi} unicast {prefix} json", ev)
        routes = parse_routes(text, prefix, bgp)
        if not routes:
            self._confirm_vrf(vrf, ev)
        return Observation(routes, ev)

    def all_routes(self, vrf: str = "default", family: int = 4) -> Observation:
        vrf = check_vrf_name(vrf)
        ev: list[dict] = []
        fam = "ipv6" if family == 6 else "ip"
        vrf_part = "" if vrf == "default" else f" vrf {vrf}"
        routes = parse_all_routes(self._vtysh(f"show {fam} route{vrf_part} json", ev))
        if not routes:
            self._confirm_vrf(vrf, ev)
        return Observation(routes, ev)

    def bgp_paths(self, prefix: str, vrf: str = "default") -> Observation:
        vrf = check_vrf_name(vrf)
        ev: list[dict] = []
        afi = "ipv6" if ipaddress.ip_network(prefix).version == 6 else "ipv4"
        vrf_part = "" if vrf == "default" else f" vrf {vrf}"
        text = self._vtysh(f"show bgp{vrf_part} {afi} unicast {prefix} json", ev)
        paths = parse_bgp_paths(text, prefix, default_local_pref=None)
        if not paths:
            self._confirm_vrf(vrf, ev)
        if any(p.local_pref is None for p in paths):
            # Some path has no LOCAL_PREF attribute: read the default it gets (an empty table listing)
            default = parse_default_local_pref(
                self._vtysh(f"show bgp{vrf_part} ipv4 unicast 255.255.255.255/32 longer-prefixes json", ev))
            paths = parse_bgp_paths(text, prefix, default_local_pref=default)
        return Observation(paths, ev)

    def ping(self, target: str, source: str | None, count: int, vrf: str = "default") -> Observation:
        vrf = check_vrf_name(vrf)
        ev: list[dict] = []
        cmd = ["ping", "-c", str(count), "-W", "1"]
        if source:
            cmd += ["-I", source]
        cmd.append(target)
        if vrf != "default":
            cmd = ["ip", "vrf", "exec", vrf, *cmd]
        r = self.lab.exec(self.node, cmd, timeout=count * 2 + 10)
        ev.append({"node": self.node, "cmd": " ".join(cmd), "rc": r.rc, "output": r.stdout[-5000:], "stderr": r.stderr[-1000:]})
        return Observation(parse_ping(r.stdout), ev)
