"""FRRouting driver: vtysh JSON output plus ping from the container.

Every parser checks the structure it reads. Output it doesn't recognize (a renamed key, a warning
object, output keyed by VRF) raises a DriverError: it is never read as "no routes", which would make
a `present: false` check pass.
"""
from __future__ import annotations

import ipaddress
import json
import re
from collections import Counter
from dataclasses import replace

from .base import (BgpNeighbor, BgpPath, Driver, DriverError, NoSuchInstance, Observation, Route, add_path_range_why,
                   as_int, canon_communities, check_vrf_name, load_json, network, parser, render_as_path, unexpected)

AFI_NAMES = {"ipv4Unicast": "ipv4-unicast", "ipv6Unicast": "ipv6-unicast", "l2VpnEvpn": "evpn"}

NEIGHBORS_CMD = "show bgp neighbors json"
ROUTE_CMD = "show ip route <prefix> json"
ALL_ROUTES_CMD = "show ip route json"
BGP_PATHS_CMD = "show bgp <afi> unicast <prefix> json"
BGP_TABLE_CMD = "show bgp ipv4 unicast <prefix> longer-prefixes json"
VRF_CMD = "show vrf"
RECEIVED_CMD = "show bgp <afi> unicast neighbors <neighbor> routes json"

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


def parse_version(text: str) -> str | None:
    """`show version`: "FRRouting 10.4.1_git (r1) on Linux(...)" -> "FRRouting 10.4.1_git"."""
    m = re.search(r"^(FRRouting \S+)", text, re.M)
    return m.group(1) if m else None


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
        # the advertisement interval bgpd applies to this neighbor (configured, or FRR's default)
        mrai = info.get("minBtwnAdvertisementRunsTimerMsecs")
        adv = as_int(NEIGHBORS_CMD, mrai) / 1000 if mrai is not None else None
        external = True if info.get("nbrExternalLink") is True else False if info.get("nbrInternalLink") is True else None
        # "Idle (Admin)" -> "idle": the first word is the FSM state
        _keep_down(out, _canon_addr(addr), BgpNeighbor(addr, state, prefixes, adv_interval=adv, external=external,
                                                       eor=frr_eor(info) if state == "established" else {}))
    return out


def add_path_rx(text: str) -> set[tuple[str, str, str]]:
    """(neighbor key, neighbor as FRR names it, afi) for every established session whose peer may send this node
    several paths per prefix: its add-path TX capability (`neighborCapabilities.addPath.<afi>.txReceived` or
    `txAdvertisedAndReceived`) is anything but a clear false, or isn't listed. FRR's acceptedPrefixCounter then counts
    paths, not prefixes (RT-0066: 2 prefixes with 2 paths each read as 4, so `min: 4` passed)."""
    data = _bgp_json(NEIGHBORS_CMD, text)
    out = set()
    for addr, info in data.items():
        if not isinstance(info, dict) or [w.lower() for w in str(info.get("bgpState", "")).split()[:1]] != ["established"]:
            continue
        caps = info.get("neighborCapabilities")
        ap = caps.get("addPath") if isinstance(caps, dict) else None
        for afi in (info.get("addressFamilyInfo") or {}):
            entry = ap.get(afi) if isinstance(ap, dict) else None
            known_off = isinstance(entry, dict) and all(entry.get(k, False) is False
                                                        for k in ("txReceived", "txAdvertisedAndReceived"))
            if not known_off:
                out.add((_canon_addr(addr), addr, AFI_NAMES.get(afi, afi)))
    return out


def count_neighbor_prefixes(text: str, cmd: str, accepted: int) -> int:
    """Distinct prefixes in `show bgp ... neighbors N routes json`, the routes this node accepted from N, one key per
    prefix and its paths listed under it. The listing's paths must add up to FRR's acceptedPrefixCounter for the same
    neighbor and family, or the two answers disagree and the count is an error, never a guess."""
    data = load_json(cmd, text)
    if not isinstance(data, dict):
        raise unexpected(cmd, text)
    routes = data.get("routes", {} if not data else None)
    if not isinstance(routes, dict) or not all(isinstance(p, list) for p in routes.values()):
        raise unexpected(cmd, str(data)[:300])
    # FRR's counter leaves out history (dampened) and removed paths; the listing may show them (Layer 6 review)
    live = {pfx: [p for p in ps if not (isinstance(p, dict) and _withdrawn(cmd, p))] for pfx, ps in routes.items()}
    routes = {pfx: ps for pfx, ps in live.items() if ps}
    paths = sum(len(p) for p in routes.values())
    if paths != accepted:
        raise DriverError(f"`{cmd}`: lists {paths} paths over {len(routes)} prefixes, but the neighbor's "
                          f"acceptedPrefixCounter is {accepted}: the prefix count can't be read")
    return len(routes)


def frr_eor(info: dict) -> dict[str, str]:
    """End-of-RIB per family from one neighbor of `show bgp neighbors json` (FRR 10.4.1, captured live 2026-11-05).

    With graceful restart negotiated, each family has `gracefulRestartInfo.<afi>.endOfRibStatus.endOfRibRecv`: false
    while the table is in flight, true once End-of-RIB arrived; the top-level `gracefulRestartInfo.endOfRibRecv` map
    lists the families already received and is a cross-check (the two disagreeing reads unknown). Graceful restart off
    (local mode `Disable`, remote `NotApplicable`): no per-family block, untracked. Anything else: unknown."""
    g = info.get("gracefulRestartInfo")
    if not isinstance(g, dict):
        return {"*": "unknown"}
    local = str(g.get("localGrMode", "")).rstrip("*")
    remote = str(g.get("remoteGrMode", "")).rstrip("*")
    if local == "Disable" or remote == "NotApplicable":
        return {"*": "untracked"}
    if local not in ("Helper", "Restart") or remote not in ("Helper", "Restart"):
        return {"*": "unknown"}
    recv_map = g.get("endOfRibRecv")
    if not isinstance(recv_map, dict):
        return {"*": "unknown"}
    out = {}
    for afi, block in g.items():
        if not isinstance(block, dict) or "endOfRibStatus" not in block:
            continue
        status = block["endOfRibStatus"]
        recv = status.get("endOfRibRecv") if isinstance(status, dict) else None
        listed = recv_map.get(afi)
        name = AFI_NAMES.get(afi, afi)
        if recv is True and listed is True:
            out[name] = "received"
        elif recv is False and listed is None:
            out[name] = "pending"
        else:
            out[name] = "unknown"
    return out or {"*": "unknown"}


def _route_table(command: str, text: str) -> dict[ipaddress._BaseNetwork, list[dict]]:
    """zebra's `show ip route ... json`: {prefix: [entry, ...]}. `{}` is a real empty answer; any key
    that isn't a prefix (a warning, output keyed by VRF name) is unexpected. The default prefix with an empty list is
    zebra's answer when no default route exists at all (FRR 10.4.1, live capture frr_route_default_absent.json): no
    route, as `{}`. Once Docker's management default is removed (0.4.1, B3) a lab node can have none."""
    data = load_json(command, text)
    if not isinstance(data, dict):
        raise unexpected(command, text)
    table = {}
    for key, entries in data.items():
        net = network(command, key)
        if entries == [] and net.prefixlen == 0:
            continue
        if not isinstance(entries, list) or not entries:
            raise unexpected(command, f"{key}: {str(entries)[:150]}")
        for e in entries:
            if not isinstance(e, dict) or not isinstance(e.get("protocol"), str):
                raise unexpected(command, f"{key}: {str(e)[:150]}")
        table[net] = entries
    return table


# zebra's route types (lib/route_types.txt): any other name is an error, never passed through raw (it matched no
# `protocol`, so `present: false` on it passed; Layer 6 on b03cb7a, the EOS acceptance finding on every driver)
ZEBRA_TYPES = frozenset({"system", "kernel", "connected", "local", "static", "rip", "ripng", "ospf", "ospf6", "isis",
                         "bgp", "pim", "eigrp", "nhrp", "hsls", "olsr", "table", "ldp", "vnc", "vnc-direct", "vnc-rn",
                         "bgp-direct", "bgp-direct-to-nve", "babel", "sharp", "pbr", "bfd", "openfabric", "vrrp",
                         "nhg", "srte", "table-direct"})


# zebra's flags that say an installed route doesn't forward (yet): a FIB install that failed, a dataplane (ASIC)
# offload that failed, an install still queued, and a route trapped to the CPU. zebra prints each only when true.
# `trapped` is normal for the router's own addresses on an ASIC dataplane, so it counts for BGP and static routes
# only (angle-5 red team on d87aa3e, RT-0046; design redteam-041-angle5-fixes, C5 revision 2)
ZEBRA_FAILURE_FLAGS = ("failed", "offloadFailed", "queued", "trapped")
_TRAPPED_COUNTS = frozenset({"bgp", "static"})   # trapped is normal for the router's own and IGP-internal routes


def zebra_forwards(command: str, e: dict, selected: bool = True) -> bool:
    """Does this zebra route entry forward: selected and installed, with no failure flag set? One test for every
    reader of zebra's route JSON (the drivers and verify, which keeps selection apart: `selected=False` leaves it
    out). A flag that is set to anything but a boolean is an error."""
    for key in ("selected", "installed", *ZEBRA_FAILURE_FLAGS):
        if key in e and not isinstance(e[key], bool):
            raise unexpected(command, f"{key}: not a boolean: {str(e[key])[:40]!r}")
    if (selected and e.get("selected") is not True) or e.get("installed") is not True:
        return False
    proto = str(e["protocol"]).lower()
    # each flag by name, so the defaulted-key scan (tests/test_verdict_keys_041.py) sees every read
    failing = (e.get("failed") is True or e.get("offloadFailed") is True or e.get("queued") is True
               or (e.get("trapped") is True and proto in _TRAPPED_COUNTS))
    return not failing


# On SONiC the ASIC programs BGP and static routes after zebra installs them, and the shipped sonic-vs build prints
# `offloaded: true` once it has (sonic_route.txt, live): without it the route isn't forwarding in the switch, for
# example while orchagent is stopped (angle-5 red team on d87aa3e, RT-0047; design C5, M4)
OFFLOADED_TYPES = frozenset({"bgp", "static"})


RUNNING_CONFIG_CMD = "show running-config bgpd"
_ALIAS = re.compile(r"^\s*bgp community alias\s+(\S+)\s+(\S+)\s*$", re.M)


@parser(RUNNING_CONFIG_CMD)
def parse_community_aliases(text: str) -> set[str]:
    """The alias names of `bgp community alias <community> <alias>` lines in bgpd's running config. An answer that
    isn't a whole configuration ("Current configuration:" ... "end") is an error, never "no aliases"."""
    lines = [ln.rstrip() for ln in text.strip().splitlines()]
    if "Current configuration:" not in lines or not lines or lines[-1] != "end":
        raise unexpected(RUNNING_CONFIG_CMD, text.strip()[:150] or "no output")
    return {m.group(2) for m in _ALIAS.finditer(text)}


def _route(prefix: str, e: dict, command: str = ROUTE_CMD, offload: bool = False) -> Route:
    # zebra prints `installed: true` on every route in the FIB and leaves the key out otherwise (a FIB install
    # that failed prints `failed: true` instead): no key is not installed (red team RT-0021)
    if e["protocol"].lower() not in ZEBRA_TYPES:
        raise unexpected(command, f"protocol {e['protocol']!r} is not one this driver maps to a protocol")
    proto = e["protocol"].lower()
    if "offloaded" in e and not isinstance(e["offloaded"], bool):
        raise unexpected(command, f"offloaded: not a boolean: {str(e['offloaded'])[:40]!r}")
    active = zebra_forwards(command, e) and not (offload and proto in OFFLOADED_TYPES and e.get("offloaded") is not True)
    return Route(prefix, proto, active)


@parser(RECEIVED_CMD)
def parse_received(text: str, family: int) -> set[str]:
    """`show bgp [vrf X] <afi> unicast neighbors <addr> routes json`: the prefixes accepted from the neighbor
    (after import policy), keyed by prefix under `routes`. No routes at all prints `{}`."""
    data = _bgp_json(RECEIVED_CMD, text)
    if not data:
        return set()
    routes = data.get("routes")
    if not isinstance(routes, dict):
        raise unexpected(RECEIVED_CMD, text)
    out = set()
    for key, paths in routes.items():
        net = network(RECEIVED_CMD, key)
        if net.version != family or not isinstance(paths, list) or not paths:
            raise unexpected(RECEIVED_CMD, f"{key}: {str(paths)[:150]}")
        # each path names its prefix (`network`, FRR 10.4.1): an element that doesn't is output this parser doesn't
        # know, never a received prefix that `only` then judges (Layer 6 round 2 on eaa323c)
        for p in paths:
            if not isinstance(p, dict) or not isinstance(p.get("network"), str)                     or network(RECEIVED_CMD, p["network"]) != net:
                raise unexpected(RECEIVED_CMD, f"{key} path: {str(p)[:150]}")
        # a prefix listed only by paths the neighbor withdrew (a dampening history entry, a path being removed) is no
        # prefix it sends: listed, `record` wrote it into `only` and the prefix coming back passed (red team RT-0071,
        # oracle FP-042-FRRRECVHIST). One live path keeps it; a damped (suppressed) path is still announced
        if all([_withdrawn(RECEIVED_CMD, p) for p in paths]):   # every flag read: one that isn't a boolean raises
            continue
        out.add(str(net))
    # bgpd closes the listing with its own route total (FRR 10.4.1; its totalPaths counts every path of those
    # prefixes, from any neighbor): a listing that disagrees was cut or misread, and a prefix missing from it would
    # never fail `only`. The total counts the withdrawn prefixes too, so the check is on every key listed
    if data.get("totalRoutes") != len(routes):
        raise unexpected(RECEIVED_CMD, f"{len(routes)} routes listed, totalRoutes {data.get('totalRoutes')!r}")
    return out


PATHS_TEXT_CMD = "show bgp <afi> unicast <prefix>"
_PATHS_AVAILABLE = re.compile(r"^\s*Paths: \((\d+) available\b", re.M)


def needs_text_count(text: str) -> bool:
    """A `show bgp ... <prefix> json` answer that lists paths without pathCount (FRR 10.2.1, captured: oracle
    FP-042-FRR102): the path count must then come from the text answer before the paths are believed."""
    try:
        data = json.loads(text)
    except ValueError:
        return False
    return isinstance(data, dict) and isinstance(data.get("paths"), list) and "pathCount" not in data


def parse_paths_available(text: str, prefix: str) -> int:
    """`show bgp <afi> unicast <prefix>` (text): the count in "Paths: (N available, best #k ...)", which FRR 10.2.1
    prints where its JSON leaves pathCount out (tests/fixtures/frr1021_*_prefix_text.txt). Exactly one such line for
    exactly this prefix, or no count: never a guess."""
    # FRR prints "BGP routing table entry for 192.168.21.0/24, version 5": the prefix ends at the comma
    head = re.search(r"BGP routing table entry for ([^\s,]+)", text)
    found = _PATHS_AVAILABLE.findall(text)
    try:
        same = bool(head) and ipaddress.ip_network(head.group(1), strict=False) == ipaddress.ip_network(prefix)
    except ValueError:   # an entry line naming no prefix this parser can read
        same = False
    if not same or len(found) != 1:
        raise DriverError(f"bgpd listed the BGP paths for {prefix} without pathCount, and its text answer "
                          f"(`{PATHS_TEXT_CMD}`) gives no single path count for {prefix} to check them against: "
                          "the paths can't be trusted, so no verdict on them")
    return int(found[0])


def _path_count(command: str, data: dict, text_count: int | None = None, prefix: str = "") -> None:
    """`pathCount` must equal the paths listed: a path dropped from under its count must never read as one path
    less, or as no path (0.4.1, the shape of the Junos fuzz finding of 2026-11-01). Where bgpd prints no pathCount
    (FRR 10.2.1), the text answer's "N available" is the count instead (text_count); without it there is no verdict
    on the paths, named, never a guess (oracle FP-042-FRR102)."""
    if "pathCount" not in data:
        if text_count is None:
            raise DriverError(f"bgpd listed the BGP paths for {prefix or data.get('prefix')} without pathCount: the "
                              f"count comes from the text answer (`{PATHS_TEXT_CMD}`), which wasn't read, so no "
                              "verdict on them")
        if text_count != len(data["paths"]):
            raise unexpected(command, f"{text_count} paths available (text answer), but {len(data['paths'])} listed")
        return
    count = as_int(command, data["pathCount"])
    if count != len(data["paths"]):
        raise unexpected(command, f"pathCount {count}, but {len(data['paths'])} paths listed")


def _segments(p: dict) -> list:
    """A path's AS-path segments. bgpd prints `aspath.segments` on every path (an empty list for the router's own);
    without it the AS path was not printed, which must never read as empty, a locally originated route
    (acceptance A-6)."""
    if (not isinstance(p, dict) or "aspath" not in p or not isinstance(p["aspath"], dict)
            or not isinstance(p["aspath"].get("segments"), list)):
        raise unexpected(BGP_PATHS_CMD, f"path without aspath segments: {str(p)[:150]}")
    aspath = p["aspath"]
    # each segment names its type and its list, and aspath.length (printed on every path, each capture) is the hop
    # count of those segments: a segment without its list read as no ASNs, so `as_path: ""` passed on a path that
    # had some (Layer 6 round 4 on bf29e89)
    segs = []
    for s in aspath["segments"]:
        if not isinstance(s, dict) or not isinstance(s.get("type"), str) or not isinstance(s.get("list"), list):
            raise unexpected(BGP_PATHS_CMD, f"aspath segment without its type or list: {str(s)[:150]}")
        segs.append((s["type"], s["list"]))
    hops = sum(len(asns) if kind == "as-sequence" else 1 if kind == "as-set" else 0 for kind, asns in segs)
    if "length" not in aspath or as_int(BGP_PATHS_CMD, aspath["length"]) != hops:
        raise unexpected(BGP_PATHS_CMD, f"aspath length {aspath.get('length')!r}, but its segments count {hops} hops")
    return segs


def _communities(p: dict, key: str) -> list[str]:
    """bgpd adds `community` / `largeCommunity` to a path only when it carries the attribute (frr_bgp_paths captures
    with and without), so absence is none. Present, it must carry its string, as verify reads it: an object without
    one read as no communities, so `without_communities` passed (Layer 6 round 4 on bf29e89)."""
    if key not in p:
        return []
    obj = p[key]
    if not isinstance(obj, dict) or not isinstance(obj.get("string"), str):
        raise unexpected(BGP_PATHS_CMD, f"{key} without its string: {str(obj)[:150]}")
    return obj["string"].split()


def _bgp_paths_raw(command: str, text: str, prefix: str, text_count: int | None = None) -> list[dict]:
    """Path objects for exactly `prefix` from `show bgp ... <prefix> json`. `{}` means no path. text_count: the text
    answer's path count, for a bgpd that prints no pathCount (see _path_count)."""
    data = _bgp_json(command, text)
    if not data:
        return []
    if not isinstance(data.get("paths"), list) or "prefix" not in data:
        raise unexpected(command, text)
    _path_count(command, data, text_count, prefix)
    if network(command, data["prefix"]) != ipaddress.ip_network(prefix):
        # bgpd answers for exactly the prefix asked, `{}` without it (FRR 10.4.1): an answer for another one is output
        # this parser doesn't know, never "no path" (read as no path, it made `present: false` pass)
        raise unexpected(command, f"paths for {data['prefix']} in the answer for {prefix}")
    for p in data["paths"]:
        if not isinstance(p, dict):
            raise unexpected(command, f"path: {str(p)[:150]}")
        stale = p["stale"] if "stale" in p else False   # bgpd prints the flag only when set
        if not isinstance(stale, bool):
            raise unexpected(command, f"stale: {str(stale)[:40]!r}")
        if stale:
            # graceful restart: bgpd keeps the restarting peer's paths, marked stale, until it re-sends them or
            # the stale timer ends. Such a path is neither present nor gone yet, so no check can pass on it
            raise DriverError(f"{prefix}: BGP path from {(p.get('peer') or {}).get('peerId', '?')} is stale "
                              "(graceful restart in progress): not settled")
    return [p for p in data["paths"] if not _withdrawn(command, p)]


# flags bgpd prints (only when set) on a path the peer withdrew but bgpd still lists: a dampening history entry
# (`dampeningHistoryEntry` in a prefix's detail, `history` in a table or neighbor listing) and a path being removed
WITHDRAWN_FLAGS = ("dampeningHistoryEntry", "history", "removed")


def _withdrawn(command: str, p: dict) -> bool:
    """A path bgpd keeps after the peer withdrew it. With `bgp dampening`, a withdrawn route stays listed as a history
    entry (no `valid`, no best path, "(history entry)" in the text answer) until its penalty decays; read as a path,
    a withdrawn default passed `route ... protocol bgp active: false` as "present via bgp (not selected)" (red team
    RT-0070, oracle FP-042-FRRDAMP). Such a path is no path. A damped (suppressed) path is kept: the peer still
    announces it, so the route is received, present and never active (`dampeningSuppressed` / `damped`). A flag that
    isn't a boolean is output this parser doesn't know."""
    out = False
    for k in WITHDRAWN_FLAGS:
        if k in p:
            if not isinstance(p[k], bool):
                raise unexpected(command, f"{k}: {str(p[k])[:40]!r}")
            out = out or p[k]
    return out


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
def parse_routes(text: str, prefix: str, bgp_text: str | None = None, offload: bool = False,
                 bgp_count: int | None = None) -> list[Route]:
    """Routing-table entries for `prefix`, plus a not-installed BGP route when the BGP table has a path
    learned from a neighbor that zebra doesn't hold (invalid next hop, not selected): it was received,
    so it counts as present, as on EOS and SR Linux. zebra answers for exactly the prefix asked, `{}` without it
    (FRR 10.4.1): a route for another prefix is output this parser doesn't know, never "not there"."""
    want = ipaddress.ip_network(prefix)
    table = _route_table(ROUTE_CMD, text)
    for net in table:
        if net != want:
            raise unexpected(ROUTE_CMD, f"a route for {net} in the answer for {want}")
    out = [_route(prefix, e, offload=offload) for entries in table.values() for e in entries]
    if bgp_text is not None:
        paths = _bgp_paths_for_route_check(bgp_text, prefix, bgp_count)   # read even when zebra has it: a stale path is an error
        if not any(r.protocol == "bgp" for r in out) and any(_learned(p) for p in paths):
            out.append(Route(prefix, "bgp", False))
    return out


def _bgp_paths_for_route_check(text: str, prefix: str, text_count: int | None = None) -> list[dict]:
    """The BGP side of a route check. No BGP instance in the VRF means no BGP paths (the VRF itself is
    confirmed separately); any other warning or shape is an error."""
    data = load_json(BGP_PATHS_CMD, text)
    if isinstance(data, dict) and data.get("bgpNoSuchInstance"):
        return []
    if isinstance(data, dict) and isinstance(data.get("warning"), str) and _NO_INSTANCE.search(data["warning"]):
        return []
    return _bgp_paths_raw(BGP_PATHS_CMD, text, prefix, text_count)


@parser(ALL_ROUTES_CMD)
def parse_all_routes(text: str, offload: bool = False) -> list[Route]:
    return [_route(str(net), e, ALL_ROUTES_CMD, offload) for net, entries in _route_table(ALL_ROUTES_CMD, text).items()
            for e in entries]


def _next_hop(hops: list) -> str | None:
    """The global next hop (an IPv6 path may also list a link-local one); link-local only if nothing else."""
    hops = [h for h in hops if isinstance(h, dict) and h.get("ip")]
    best = next((h for h in hops if h.get("scope", "global") == "global"), hops[0] if hops else None)
    return _canon_addr(str(best["ip"])) if best else None


@parser(BGP_PATHS_CMD)
def parse_bgp_paths(text: str, prefix: str, default_local_pref: int | None = 100,
                    text_count: int | None = None) -> list[BgpPath]:
    """`show bgp <afi> unicast <prefix> json`. A path without locPrf carries no LOCAL_PREF attribute
    (eBGP-learned or local), and FRR applies the instance's default local preference to it. Every path
    is listed, valid or not, best or not."""
    out = []
    for p in _bgp_paths_raw(BGP_PATHS_CMD, text, prefix, text_count):
        segs = _segments(p)
        out.append(BgpPath(
            best=bool((p.get("bestpath") or {}).get("overall")),
            as_path=render_as_path(segs),  # not aspath.string: FRR prints "Local" for an empty path
            next_hop=_next_hop(p.get("nexthops") or []),
            local_pref=as_int(BGP_PATHS_CMD, p["locPrf"]) if "locPrf" in p else default_local_pref,
            med=as_int(BGP_PATHS_CMD, p["metric"]) if "metric" in p else None,   # no MED attribute: unknown, not 0
            communities=canon_communities(_communities(p, "community")),
            large_communities=canon_communities(_communities(p, "largeCommunity")),
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
    offload = False   # plain FRR has no ASIC: offload isn't part of reading a route (SonicDriver sets it)
    # zebra's route types; EVPN and VPN routes are bgp there, and a BGP aggregate is bgp too
    route_protocols = frozenset({"bgp", "connected", "local", "static", "kernel", "ospf", "ospf6", "isis", "rip",
                                 "ripng", "eigrp", "babel", "nhrp", "table", "sharp", "pbr", "openfabric"})

    def _vtysh(self, command: str, evidence: list[dict]) -> str:
        return self._exec(["vtysh", "-c", command], evidence)

    def _text_count(self, json_text: str, vrf_part: str, afi: str, prefix: str, evidence: list[dict]) -> int | None:
        """Where bgpd lists a prefix's paths without pathCount (FRR 10.2.1), read the count from the text answer of
        the same command, so a dropped path is still caught (oracle FP-042-FRR102). None when pathCount is printed."""
        if not needs_text_count(json_text):
            return None
        return parse_paths_available(self._vtysh(f"show bgp{vrf_part} {afi} unicast {prefix}", evidence), prefix)

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

    def nos_version(self) -> str | None:
        try:
            return parse_version(self._vtysh("show version", []))
        except DriverError:
            return None

    def bgp_neighbors(self, vrf: str = "default") -> Observation:
        vrf = check_vrf_name(vrf)
        ev: list[dict] = []
        cmd = "show bgp neighbors json" if vrf == "default" else f"show bgp vrf {vrf} neighbors json"
        text = self._vtysh(cmd, ev)
        neighbors = parse_bgp_neighbors(text)
        if not neighbors:
            self._confirm_vrf(vrf, ev)
        # with add-path from the peer, acceptedPrefixCounter counts paths: count the prefixes it lists (RT-0066)
        vrf_part = "" if vrf == "default" else f" vrf {vrf}"
        for key, name, afi in sorted(add_path_rx(text)):
            n = neighbors.get(key)
            if n is None or afi not in n.prefixes:
                continue
            if afi not in ("ipv4-unicast", "ipv6-unicast"):
                # no per-neighbor listing read for this family (EVPN, ...): the counter's P paths are 1 to P
                # prefixes, judged only where the whole range agrees, otherwise no verdict (never the path count)
                paths = n.prefixes[afi]
                neighbors[key] = n = replace(
                    n, prefixes={**n.prefixes, afi: min(paths, 1)}, prefixes_upto={**n.prefixes_upto, afi: paths},
                    prefixes_upto_why={**n.prefixes_upto_why, afi: add_path_range_why(paths)},
                    prefixes_unread={**n.prefixes_unread, afi: f"the peer may send add-path in {afi}, so FRR's "
                                     f"acceptedPrefixCounter ({paths}) counts paths, not prefixes"})
                continue
            rcmd = f"show bgp{vrf_part} {afi.split('-')[0]} unicast neighbors {name} routes json"
            count = count_neighbor_prefixes(self._vtysh(rcmd, ev), rcmd, n.prefixes[afi])
            neighbors[key] = replace(n, prefixes={**n.prefixes, afi: count})
        return Observation(neighbors, ev)

    def routes(self, prefix: str, vrf: str = "default") -> Observation:
        vrf = check_vrf_name(vrf)
        ev: list[dict] = []
        version = ipaddress.ip_network(prefix).version
        fam, afi = ("ipv6", "ipv6") if version == 6 else ("ip", "ipv4")
        vrf_part = "" if vrf == "default" else f" vrf {vrf}"
        text = self._vtysh(f"show {fam} route{vrf_part} {prefix} json", ev)
        bgp = self._vtysh(f"show bgp{vrf_part} {afi} unicast {prefix} json", ev)
        routes = parse_routes(text, prefix, bgp, offload=self.offload, bgp_count=self._text_count(bgp, vrf_part, afi,
                                                                                                    prefix, ev))
        if not routes:
            self._confirm_vrf(vrf, ev)
        return Observation(routes, ev)

    def vrfs(self) -> Observation:
        """Active VRFs from zebra's `show vrf` (an inactive one has no kernel device, so no state to record)."""
        ev: list[dict] = []
        found = parse_vrfs(self._vtysh(VRF_CMD, ev))
        return Observation(sorted(v for v, active in found.items() if active and v != "default"), ev)

    def all_routes(self, vrf: str = "default", family: int = 4) -> Observation:
        vrf = check_vrf_name(vrf)
        ev: list[dict] = []
        fam = "ipv6" if family == 6 else "ip"
        vrf_part = "" if vrf == "default" else f" vrf {vrf}"
        routes = parse_all_routes(self._vtysh(f"show {fam} route{vrf_part} json", ev), offload=self.offload)
        if not routes:
            self._confirm_vrf(vrf, ev)
        return Observation(routes, ev)

    reads_received = True

    def bgp_received(self, neighbor: str, afi: str = "ipv4-unicast", vrf: str = "default") -> Observation:
        vrf = check_vrf_name(vrf)
        if afi not in ("ipv4-unicast", "ipv6-unicast"):
            raise DriverError(f"the prefixes received in {afi} can't be listed")
        if "%" in neighbor:   # a scoped link-local can be several sessions (see BgpNeighbor.ambiguous)
            raise DriverError(f"the prefixes received from {neighbor} can't be listed: use a global address")
        try:
            addr = ipaddress.ip_address(neighbor)
        except ValueError:
            raise DriverError(f"the prefixes received from {neighbor!r} can't be listed: not an address") from None
        ev: list[dict] = []
        vrf_part = "" if vrf == "default" else f" vrf {vrf}"
        fam = afi.split("-")[0]
        text = self._vtysh(f"show bgp{vrf_part} {fam} unicast neighbors {addr} routes json", ev)
        return Observation(parse_received(text, 6 if fam == "ipv6" else 4), ev)

    def bgp_paths(self, prefix: str, vrf: str = "default") -> Observation:
        vrf = check_vrf_name(vrf)
        ev: list[dict] = []
        afi = "ipv6" if ipaddress.ip_network(prefix).version == 6 else "ipv4"
        vrf_part = "" if vrf == "default" else f" vrf {vrf}"
        text = self._vtysh(f"show bgp{vrf_part} {afi} unicast {prefix} json", ev)
        count = self._text_count(text, vrf_part, afi, prefix, ev)
        paths = parse_bgp_paths(text, prefix, default_local_pref=None, text_count=count)
        if not paths:
            self._confirm_vrf(vrf, ev)
        if any(p.local_pref is None for p in paths):
            # Some path has no LOCAL_PREF attribute: read the default it gets (an empty table listing)
            default = parse_default_local_pref(
                self._vtysh(f"show bgp{vrf_part} ipv4 unicast 255.255.255.255/32 longer-prefixes json", ev))
            paths = parse_bgp_paths(text, prefix, default_local_pref=default, text_count=count)
        return Observation(paths, ev)

    def community_aliases(self) -> Observation:
        """The alias names of the node's `bgp community alias` lines (bgpd's running config, FRR 10.4.1). bgpd prints
        an alias in place of the community, so a community check reads them as unreadable (checks._bgp_route)."""
        ev: list[dict] = []
        return Observation(parse_community_aliases(self._vtysh(RUNNING_CONFIG_CMD, ev)), ev)

    own_address_families = frozenset({4, 6})   # what local_addresses reads (round 4, RT-0044)

    def local_addresses(self, vrf: str = "default") -> list:
        from .addresses import parse_ip_j_addr
        vrf = check_vrf_name(vrf)
        cmd = ["ip", "-j", "addr"] + ([] if vrf == "default" else ["show", "vrf", vrf])
        out = parse_ip_j_addr(self._exec(cmd, []), skip_enslaved=vrf == "default", command=" ".join(cmd))
        if vrf != "default":
            # `show vrf X` lists the interfaces enslaved to X, not the VRF device itself; an address on it (the usual
            # VRF loopback, `ip addr add A dev X`) is answered by the node too (RT-0053)
            dev = ["ip", "-j", "addr", "show", "dev", vrf]
            out += parse_ip_j_addr(self._exec(dev, []), skip_enslaved=False, command=" ".join(dev))
        return out

    def ping(self, target: str, source: str | None, count: int, vrf: str = "default") -> Observation:
        vrf = check_vrf_name(vrf)
        ev: list[dict] = []
        cmd = ["ping", "-c", str(count), "-W", "1"]
        if source:
            cmd += ["-I", source]
        cmd.append(target)
        if vrf != "default":
            cmd = ["ip", "vrf", "exec", vrf, *cmd]
        from ..mgmt import check_node   # no route out over the management network, before and after (B3, R5)
        check_node(self.lab, self.node, f"before the ping to {target}")
        r = self.lab.exec(self.node, cmd, timeout=count * 2 + 10)
        ev.append({"node": self.node, "cmd": " ".join(cmd), "rc": r.rc, "output": r.stdout[-5000:], "stderr": r.stderr[-1000:]})
        check_node(self.lab, self.node, f"after the ping to {target}")
        return Observation(parse_ping(r.stdout), ev)
