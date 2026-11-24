"""FRR import check: a `network` whose import-check registration never reached zebra (oracle FP-043-FRRIMPORTCHK,
RT-0084).

FRR bgpd (10.4.1; the same code in 8.5.4, 10.2.1 and master) marks a `network` applied before its zebra connection
is up as valid (bgp_isvalid_nexthop() answers valid with no zebra connection), its registration with zebra fails, and
bgp_nht_register_nexthops() never sends it again: it walks the nexthop cache, not the import-check table. The prefix
then stays announced whatever zebra's RIB holds, for the life of the lab, while a router changed in production (import
check registered) withdraws it. A lab boot hits this often (pe1 of corpus v2 case 18: 7 boots of 11). The same race
can also withhold a backed network for good (a VRF instance not yet known to zebra), so "the route exists" proves
nothing either way.

bgpd prints the state itself, per BGP instance: `show bgp [vrf NAME] import-check-table detail [json]`. A stuck
entry is invalid next to a valid path that depends on it (FRR contradicting itself: the primary signal, whatever the
registration flag is called), or says it is not registered ("Is not Registered", JSON `"isRegistered": false`).

guard() reads every FRR router in the lab (not only the ones the checks read), every non-view BGP instance by name
(`vrf all` is not an instance: the text answers "% No such BGP instance exist" and the JSON `{}`), and requires an
entry for every `network` line in bgpd's running config, on two consecutive identical samples: a read before bgpd
applied its config, a read that fails, or an answer of a shape this module doesn't know is never "nothing stuck". It
waits within a time limit, then ends the run as an error.

Healthy states that hold no usable entry are accepted only on positive evidence (review of 58eb8e0): a `backdoor`
network is never announced (left out); a network its route-map denies has no path and no entry (FRR only: after the
boot log shows bgpd's config loaded, bgpd's BGP table answering that it holds no path of its own for exactly that
prefix, past the route-map delay); a VRF instance zebra doesn't know (bgpd's vrfId -1) can't register, which counts
when it and its paths are all invalid (nothing announced); a router whose bgpd doesn't run (vtysh can't reach it,
`bgpd=no` in /etc/frr/daemons, no bgpd process) has nothing to check.

A stuck instance is remedied only on a lab this run deployed: import check toggled off and on in one vtysh call per
router (bgpd frees the entry and registers a fresh one now that zebra is connected; the running config doesn't
change). Then everything is read again and must be clean, bgpd's running config byte-identical, and no BGP session in
the lab dropped or reset (the toggle re-runs every `network` of the instance: a peer at its maximum-prefix limit could
see a transient prefix). Anything else is an error, never a verdict. On a lab it didn't deploy (`check`, the standing
guards in verify) it only detects: a stuck entry there is an error.
"""
from __future__ import annotations

import ipaddress
import json
import re
from dataclasses import dataclass, field
from typing import Callable

from ..lab import LabError
from .base import DriverError

BGPD_CONFIG = ["vtysh", "-d", "bgpd", "-c", "show running-config"]
NEIGHBORS = ["vtysh", "-c", "show bgp vrf all neighbors json"]
STARTUP_FILES = ("/etc/frr/frr.conf", "/etc/frr/bgpd.conf")
DAEMONS = ["cat", "/etc/frr/daemons"]
VRFS = ["vtysh", "-c", "show bgp vrfs json"]
VRF_UNKNOWN = -1   # bgpd's vrfId for a VRF instance whose VRF zebra doesn't know (no VRF device)
PROCESSES = ["sh", "-c", "cat /proc/[0-9]*/comm"]   # every process's name, one per line
NO_DAEMON = "failed to connect to any daemons"   # vtysh -d bgpd when it can't reach bgpd (FRR 10.4.1, live)
# `docker exec` of a program the image doesn't have (Docker 29.9.2, live): rc 127 and this line
NO_VTYSH = 'exec: "vtysh": executable file not found in $PATH'
ROUTE_MAP_KEYS = frozenset({"invoked", "disabledOptimization", "processedChange", "rules", "cpuTimeMS"})
BGPD_DOWN = "bgpd is not running (vtysh can't reach it, /etc/frr/daemons says bgpd=no, no bgpd process)"
BUDGET = 120.0       # seconds to wait for a complete, stable read (at boot, and again after a remedy)
SAMPLE_GAP = 2.0     # seconds between the two samples that must agree
RETRY_GAP = 2.0      # seconds before reading again after an unreadable sample, or two that disagreed
# networks FRR never registers by design (bgp_nht.c: is_default_host_route): never "stuck"
NEVER_REGISTERED = frozenset({"0.0.0.0/32", "::/128"})
# address families whose `network` statements go through the import check (bgp_route.c:
# bgp_nexthop_reachability_check: SAFI_UNICAST and SAFI_LABELED_UNICAST), and those that never do
CHECKED_FAMILIES = frozenset({("ipv4", "unicast"), ("ipv6", "unicast"), ("ipv4", "labeled-unicast"),
                              ("ipv6", "labeled-unicast")})
UNCHECKED_FAMILIES = frozenset({("ipv4", "multicast"), ("ipv6", "multicast"), ("ipv4", "vpn"), ("ipv6", "vpn"),
                                ("ipv4", "flowspec"), ("ipv6", "flowspec"), ("l2vpn", "evpn")})
# the keys bgp_show_nexthop() and bgp_show_nexthop_paths() print (FRR 10.2.1, 10.4.1, master): any other key is an
# answer this module wasn't built for (a renamed flag would otherwise read as "registered")
ENTRY_KEYS = frozenset({"valid", "complete", "igpMetric", "pathCount", "peer", "isEvpnGatewayIp", "resolvedPrefix",
                        "nexthops", "isConnected", "isRegistered", "lastUpdate", "lastUpdateStr", "srteColor",
                        "paths"})
PATH_KEYS = frozenset({"afi", "safi", "prefix", "rd", "vrf", "flags"})
AFI_JSON = {"IPv4": "ipv4", "IPv6": "ipv6"}
AFI_TEXT = {"1": "ipv4", "2": "ipv6"}
SAFI_TEXT = {"1": "unicast", "2": "multicast", "4": "labeled-unicast", "128": "vpn", "70": "evpn", "133": "flowspec"}
PATH_VALID = 0x10    # BGP_PATH_VALID (bgpd/bgp_route.h)
_NAME = re.compile(r"^[A-Za-z0-9_.:-]{1,64}$")   # a VRF name or ASN that may reach a vtysh command line
_ROUTER = re.compile(r"^router bgp (\S+)(?: (vrf|view) (\S+))?(?: as-notation (?:dot|plain|asplain))?$")
_FAMILY = re.compile(r"^ address-family (\S+)(?: (\S+))?$")
_NETWORK = re.compile(r"^ +network (\S+)(?: .*)?$")
_RMAP_DELAY = re.compile(r"^bgp route-map delay-timer (\d+)$", re.M)
RMAP_DELAY_DEFAULT = 5   # bgpd's route-map update delay when the config sets none (bgpd.h: RMAP_DEFAULT_UPDATE_TIMER)
_BGPD_LOADING = re.compile(r"^\[(\d+)\|bgpd\] sending configuration$", re.M)
_TEXT_HEADER = "Current BGP import check cache:"
_TEXT_ENTRY = re.compile(r"^ (?:SR-TE color \d+ - )?(\S+) (valid \[IGP metric \d+\]|invalid), #paths (\d+)"
                         r"(?:, peer \S+)?(?: EVPN Gateway IP)?$")
_TEXT_DETAIL = re.compile(r"^  (?:Must be Connected|Resolved prefix \S+|gate \S+.*|if \S+(?:, ifindex \d+)?|blackhole"
                          r"|Last update: .*|Paths:)$")
_TEXT_PATH = re.compile(r"^    (\d+)/(\d+) (\S+)(?: RD \S+)? (?:VRF|View) (\S+) flags 0x([0-9a-fA-F]+)$")
NOT_REGISTERED = "  Is not Registered"


class ImportCheckError(LabError):
    """The lab can't be judged: a router's import check is stuck (and wasn't, or couldn't be, remedied), or its state
    is unknown."""


class Unknown(DriverError):
    """One read this sample can't use (failed, unrecognized, before bgpd loaded its config): retried until the
    time limit, then an error. A DriverError, so the parsers meet the shared fuzz contract (test_driver_fuzz.py)."""


@dataclass(frozen=True)
class Network:
    prefix: str          # canonical, e.g. 192.0.2.0/24
    family: tuple        # ("ipv4", "unicast")
    route_map: str = field(default="", compare=False)       # `route-map NAME`: a deny leaves no path, no entry
    backdoor: bool = field(default=False, compare=False)    # `backdoor`: never announced, no path, no entry


@dataclass
class Instance:
    header: str          # the `router bgp` line exactly as bgpd prints it (the remedy enters it)
    kind: str            # "" (default or VRF instance by name below) or "view"
    vrf: str             # "default" or the VRF name
    import_check: bool = True
    networks: list = field(default_factory=list)

    @property
    def checked(self) -> list:
        """The networks whose import-check entry must exist and be registered."""
        if self.kind == "view" or not self.import_check:
            return []
        # bgp_static_set(): a backdoor network never reaches bgp_static_update(), so it has neither path nor entry
        return [n for n in self.networks
                if n.family in CHECKED_FAMILIES and n.prefix not in NEVER_REGISTERED and not n.backdoor]


@dataclass(frozen=True)
class Entry:
    address: str
    valid: bool
    registered: bool
    paths: tuple         # ((prefix, vrf, family, valid), ...), sorted

    def stuck(self) -> str | None:
        """Why this entry can't be what a router in production holds, or None."""
        if not self.registered:
            return "is not registered with zebra"
        if any(p[3] != self.valid for p in self.paths):
            return (f"is {'valid' if self.valid else 'invalid'} while a path that depends on it is "
                    f"{'invalid' if self.valid else 'valid'}")
        return None


@dataclass
class NodeRead:
    node: str
    skipped: str = ""                                # why the node has nothing to check ("" = it has)
    config: str = ""                                 # bgpd's running config, as read
    stuck: list = field(default_factory=list)        # [(Instance, prefix, why)]
    entries: dict = field(default_factory=dict)      # vrf -> sorted entries (the sample's signature)
    exempt: list = field(default_factory=list)       # [(vrf, prefix, why)]: needs no entry, on positive evidence
    hold: float = 0.0                                # seconds the sample must stay the same before it counts

    def signature(self) -> tuple:
        return (self.skipped, self.config, tuple(sorted(self.entries.items())), tuple(sorted(self.exempt)))


# ------------------------------------------------------------------------------------------------- parsers

def parse_bgpd_config(text: str) -> list[Instance]:
    """bgpd's `show running-config` -> its BGP instances with their `network` lines. Anything this parser can't
    account for (a truncated answer, a `router bgp` line or address family it doesn't know holding a network) is
    Unknown, never "no networks"."""
    lines = [ln.rstrip() for ln in text.split("\n")]
    filled = [ln for ln in lines if ln.strip()]
    if (not filled or filled[0] != "Building configuration..." or "Current configuration:" not in filled
            or filled[-1] != "end"):
        raise Unknown(f"bgpd's running config is not a complete answer ({_cut(text)})")
    out: list[Instance] = []
    cur: Instance | None = None
    fam: tuple | None = None
    for ln in lines:
        if cur is None:
            if ln.startswith("router bgp"):
                m = _ROUTER.match(ln)
                if not m or not _NAME.match(m.group(1)) or (m.group(3) and not _NAME.match(m.group(3))):
                    raise Unknown(f"bgpd's running config has a `router bgp` line this check doesn't know: {ln!r}")
                cur = Instance(header=ln, kind="view" if m.group(2) == "view" else "",
                               vrf=m.group(3) if m.group(2) == "vrf" else "default")
                if m.group(2) == "view":
                    cur.vrf = m.group(3)
            elif _NETWORK.match(ln):
                raise Unknown(f"bgpd's running config has a `network` line outside any `router bgp`: {ln!r}")
            continue
        if ln == "exit":
            if fam is not None:
                raise Unknown(f"bgpd's running config leaves an address family open in {cur.header!r}")
            out.append(cur)
            cur, fam = None, None
            continue
        if ln and not ln.startswith(" "):
            raise Unknown(f"bgpd's running config has {ln!r} inside {cur.header!r} (no `exit` before it)")
        m = _FAMILY.match(ln)
        if m:
            if fam is not None:
                raise Unknown(f"bgpd's running config opens {ln.strip()!r} inside another address family")
            fam = (m.group(1), m.group(2) or "")
            continue
        if ln == " exit-address-family":
            fam = None
            continue
        if ln == " no bgp network import-check":
            cur.import_check = False
            continue
        if ln == " bgp network import-check":
            cur.import_check = True
            continue
        m = _NETWORK.match(ln)
        if m:
            where = fam or ("ipv4", "unicast")   # a network at the router level is IPv4 unicast
            if where not in CHECKED_FAMILIES and where not in UNCHECKED_FAMILIES:
                raise Unknown(f"bgpd's running config has a network in address family {' '.join(where)!r}, "
                              "which this check doesn't know")
            try:
                net = ipaddress.ip_network(m.group(1), strict=True)
            except ValueError:
                raise Unknown(f"bgpd's running config has a network this check can't read: {ln.strip()!r}") from None
            if where in CHECKED_FAMILIES and f"ipv{net.version}" != where[0]:
                raise Unknown(f"bgpd's running config has {ln.strip()!r} in address family {' '.join(where)}")
            words = ln.split()[2:]
            rmap = ""
            if "route-map" in words:
                i = words.index("route-map")
                rmap = words[i + 1] if i + 1 < len(words) else ""
                if not _NAME.match(rmap):
                    raise Unknown(f"bgpd's running config has a route-map name this check can't read: {ln.strip()!r}")
            cur.networks.append(Network(str(net), where, route_map=rmap, backdoor="backdoor" in words))
    if cur is not None:
        raise Unknown(f"bgpd's running config ends inside {cur.header!r} (no `exit`)")
    return out


def _pairs(pairs: list) -> list:
    return _Obj(pairs)


class _Obj(list):
    """A JSON object as its (key, value) pairs, in order, repeats kept: bgpd prints one key per entry address, and
    two networks of one address (10.0.0.0/8 and 10.0.0.0/16) print the same key."""

    def single(self, where: str) -> dict:
        out: dict = {}
        for k, v in self:
            if k in out:
                raise Unknown(f"{where}: repeated key {k!r} in one object")
            out[k] = v
        return out


def _prefix(value, where: str) -> str:
    try:
        return str(ipaddress.ip_network(value, strict=True))
    except (TypeError, ValueError):
        raise Unknown(f"{where}: {value!r} is not a prefix") from None


def parse_table_json(text: str, where: str) -> list[Entry]:
    """`show bgp [vrf NAME] import-check-table detail json` -> its entries. `{}` (an instance bgpd doesn't have, as
    `vrf all` gets), a missing family, a key this parser doesn't know, a path count that doesn't match the paths
    listed: Unknown."""
    try:
        top = json.loads(text, object_pairs_hook=_pairs)
    except (json.JSONDecodeError, RecursionError, TypeError):
        raise Unknown(f"{where}: not JSON ({_cut(text)})") from None
    if not isinstance(top, _Obj):
        raise Unknown(f"{where}: not a JSON object ({_cut(text)})")
    top = top.single(where)
    if set(top) != {"ipv4", "ipv6"}:
        raise Unknown(f"{where}: expected the ipv4 and ipv6 tables, got keys {sorted(top)} ({_cut(text)})")
    out = []
    for afi in ("ipv4", "ipv6"):
        table = top[afi]
        if not isinstance(table, _Obj):
            raise Unknown(f"{where}: {afi} is not an object")
        for addr, raw in table:
            try:
                a = ipaddress.ip_address(addr)
            except ValueError:
                raise Unknown(f"{where}: entry {addr!r} is not an address") from None
            if f"ipv{a.version}" != afi or not isinstance(raw, _Obj):
                raise Unknown(f"{where}: entry {addr!r} is not an {afi} entry object")
            e = raw.single(f"{where} {addr}")
            extra = set(e) - ENTRY_KEYS
            if extra:
                raise Unknown(f"{where}: entry {addr} has key(s) this check doesn't know: {sorted(extra)}")
            valid, count, paths, reg = e.get("valid"), e.get("pathCount"), e.get("paths"), e.get("isRegistered", True)
            if (not isinstance(valid, bool) or not isinstance(count, int) or isinstance(count, bool)
                    or not isinstance(paths, list) or reg not in (True, False) or count != len(paths)):
                raise Unknown(f"{where}: entry {addr} lacks a readable valid flag, path count or path list, or its "
                              f"registration flag isn't false: {_cut(json.dumps(e))}")
            if reg is True and "isRegistered" in e:
                raise Unknown(f"{where}: entry {addr} prints isRegistered true, which FRR never prints")
            out.append(Entry(str(a), valid, reg, tuple(sorted(_json_path(p, f"{where} {addr}") for p in paths))))
    return out


def _json_path(raw, where: str) -> tuple:
    if not isinstance(raw, _Obj):
        raise Unknown(f"{where}: a path is not an object")
    p = raw.single(where)
    extra = set(p) - PATH_KEYS
    flags = p.get("flags")
    if extra or not isinstance(flags, _Obj):
        raise Unknown(f"{where}: a path has key(s) this check doesn't know ({sorted(extra)}) or no flags")
    flags = flags.single(f"{where} flags")
    afi, safi, vrf, valid = AFI_JSON.get(p.get("afi")), p.get("safi"), p.get("vrf"), flags.get("valid")
    if afi is None or not isinstance(safi, str) or not isinstance(vrf, str) or not isinstance(valid, bool):
        raise Unknown(f"{where}: a path lacks a readable afi, safi, vrf or valid flag: {_cut(json.dumps(p))}")
    return (_prefix(p.get("prefix"), where), vrf, (afi, safi), valid)


def parse_table_text(text: str, where: str) -> list[Entry]:
    """`show bgp [vrf NAME] import-check-table detail` -> its entries. Every line must be one bgpd prints there
    (bgp_nexthop.c: bgp_show_nexthop, bgp_show_nexthops_detail, bgp_show_nexthop_paths); any other line, such as
    "% No such BGP instance exist", is Unknown. The text has no end marker, so it must at least end its last line:
    an answer cut inside a line (`flags 0x1` of `flags 0x18`) would read a valid path as invalid."""
    if not text.endswith("\n"):
        raise Unknown(f"{where}: the answer stops inside a line ({_cut(text)})")
    lines = text.split("\n")
    while lines and not lines[-1].strip():
        lines.pop()
    if not lines or lines[0].rstrip() != _TEXT_HEADER:
        raise Unknown(f"{where}: not an import-check table ({_cut(text)})")
    out: list[Entry] = []
    cur = None   # [address, valid, registered, paths, count]

    def close():
        if cur is not None:
            if cur[4] != len(cur[3]):
                raise Unknown(f"{where}: entry {cur[0]} says {cur[4]} path(s) and lists {len(cur[3])}")
            out.append(Entry(cur[0], cur[1], cur[2], tuple(sorted(cur[3]))))
    for ln in lines[1:]:
        ln = ln.rstrip()
        m = _TEXT_ENTRY.match(ln)
        if m:
            close()
            try:
                addr = str(ipaddress.ip_address(m.group(1)))
            except ValueError:
                raise Unknown(f"{where}: entry {m.group(1)!r} is not an address") from None
            cur = [addr, m.group(2) != "invalid", True, [], int(m.group(3))]
            continue
        if cur is None:
            raise Unknown(f"{where}: line {ln!r} before any entry")
        if ln == NOT_REGISTERED:
            if cur[1]:
                raise Unknown(f"{where}: a valid entry says it is not registered")
            cur[2] = False
            continue
        m = _TEXT_PATH.match(ln)
        if m:
            afi, safi = AFI_TEXT.get(m.group(1)), SAFI_TEXT.get(m.group(2), m.group(2))
            if afi is None:
                raise Unknown(f"{where}: path line with an unknown address family: {ln!r}")
            cur[3].append((_prefix(m.group(3), where), m.group(4), (afi, safi),
                           bool(int(m.group(5), 16) & PATH_VALID)))
            continue
        if not _TEXT_DETAIL.match(ln):
            raise Unknown(f"{where}: a line this check doesn't know: {ln!r}")
    close()
    return out


def parse_bgp_vrfs(text: str) -> dict[str, int]:
    """`show bgp vrfs json` -> VRF name -> bgpd's VRF id (-1: a VRF zebra doesn't know, no device). Every VRF bgpd
    has an instance for, as many as it counts; anything else is Unknown."""
    try:
        top = json.loads(text, object_pairs_hook=_pairs)
    except (json.JSONDecodeError, RecursionError, TypeError):
        raise Unknown(f"`{VRFS[-1]}`: not JSON ({_cut(text)})") from None
    if not isinstance(top, _Obj):
        raise Unknown(f"`{VRFS[-1]}`: not a JSON object ({_cut(text)})")
    top = top.single(VRFS[-1])
    vrfs, total = top.get("vrfs"), top.get("totalVrfs")
    if set(top) != {"vrfs", "totalVrfs"} or not isinstance(vrfs, _Obj) or not isinstance(total, int) \
            or isinstance(total, bool):
        raise Unknown(f"`{VRFS[-1]}`: not the VRF list this check knows ({_cut(text)})")
    vrfs = vrfs.single(VRFS[-1])
    if len(vrfs) != total:
        raise Unknown(f"`{VRFS[-1]}` counts {total} VRF(s) and lists {len(vrfs)}")
    out = {}
    for name, v in vrfs.items():
        vid = v.single(f"{VRFS[-1]} {name}").get("vrfId") if isinstance(v, _Obj) else None
        if not isinstance(vid, int) or isinstance(vid, bool) or vid < -1:
            raise Unknown(f"`{VRFS[-1]}`: VRF {name!r} has no readable vrfId")
        out[name] = vid
    return out


def route_map_command(name: str) -> list[str]:
    """bgpd's own view of one route-map (`-d bgpd`: zebra keeps its own invoke counts)."""
    return ["vtysh", "-d", "bgpd", "-c", f"show route-map {name} json"]


def parse_route_map(text: str, name: str) -> tuple[int, bool] | None:
    """`vtysh -d bgpd -c 'show route-map NAME json'` -> None when bgpd has no such route-map, else (how many times
    bgpd applied it, whether a change to it is still waiting to be applied: `processedChange`). FRR 10.4.1, live:
    tests/fixtures/frr_fp043ic_followup/rmcap_*. Anything else is Unknown."""
    where = f"`show route-map {name} json`"
    try:
        top = json.loads(text, object_pairs_hook=_pairs)
    except (json.JSONDecodeError, RecursionError, TypeError):
        raise Unknown(f"{where}: not JSON ({_cut(text)})") from None
    if not isinstance(top, _Obj):
        raise Unknown(f"{where}: not a JSON object ({_cut(text)})")
    top = top.single(where)
    daemon = top.get("bgpd")
    if set(top) != {"bgpd"} or not isinstance(daemon, _Obj):
        raise Unknown(f"{where}: not bgpd's answer alone ({_cut(text)})")
    maps = daemon.single(where)
    if not maps:
        return None
    m = maps.get(name)
    if set(maps) != {name} or not isinstance(m, _Obj):
        raise Unknown(f"{where}: answers about another route-map ({_cut(text)})")
    m = m.single(where)
    invoked, pending = m.get("invoked"), m.get("processedChange")
    if not set(m) <= ROUTE_MAP_KEYS or not isinstance(invoked, int) or isinstance(invoked, bool) or invoked < 0 \
            or not isinstance(pending, bool):
        raise Unknown(f"{where}: not the route-map state this check knows ({_cut(text)})")
    return invoked, pending


def _cut(text: str, n: int = 160) -> str:
    t = " ".join(str(text).split())
    return (t[:n] + "...") if len(t) > n else (t or "no output")


# ------------------------------------------------------------------------------------------------- reading

def table_commands(vrf: str) -> tuple[list[str], list[str]]:
    """The text and JSON reads of one instance's import-check table, by name (never `vrf all`)."""
    if vrf != "default" and (not _NAME.match(vrf) or vrf.lower() == "all"):
        raise Unknown(f"VRF name {vrf!r} can't be put on a command line (`vrf all` is not one instance)")
    sel = "" if vrf == "default" else f" vrf {vrf}"
    cmd = f"show bgp{sel} import-check-table detail"
    return ["vtysh", "-c", cmd], ["vtysh", "-c", f"{cmd} json"]


def _startup_has_bgp(lab, node: str) -> bool | None:
    """Whether the node's FRR startup files configure BGP: True, False, or None when none could be read."""
    seen = False
    for path in STARTUP_FILES:
        r = lab.exec(node, ["cat", path])
        if r.rc == 0:
            seen = True
            if re.search(r"(?m)^\s*router bgp(\s|$)", r.stdout):
                return True
    return False if seen else None


def _bgpd_down(lab, node: str, r) -> bool:
    """Positive evidence that bgpd isn't running and won't be started (FRR with `bgpd=no`, agent eval T10): vtysh
    says it can't reach bgpd, FRR's daemons file turns bgpd off (watchfrr starts only the daemons it names), and no
    bgpd process runs in the container. A bgpd that is starting or died (watchfrr restarts it), a daemons file that
    can't be read or says anything else, a process list that can't be read: not evidence, so the read is retried,
    then an error. (`pgrep -x bgpd` answered rc 1 with bgpd running on FRR 10.4.1: not used.)"""
    if NO_DAEMON not in f"{r.stdout}\n{r.stderr}":
        return False
    d = lab.exec(node, DAEMONS)
    if d.rc != 0 or [_shell_value(v) for v in re.findall(r"(?m)^[ \t]*bgpd[ \t]*=(.*)$", d.stdout)] != ["no"]:
        return False
    p = lab.exec(node, PROCESSES)
    names = [ln.strip() for ln in p.stdout.split("\n") if ln.strip()]
    return p.rc == 0 and not p.stderr.strip() and bool(names) and "bgpd" not in names


def _shell_value(v: str) -> str:
    """A daemons-file value as the shell that sources it reads it: a trailing ` # comment` dropped, one pair of
    quotes taken off (`bgpd="no"`, `bgpd=no  # off`). Anything fancier stays as written, so it isn't "no"."""
    v = re.sub(r"[ \t]+#.*$", "", v).strip()
    if len(v) >= 2 and v[0] == v[-1] and v[0] in "'\"":
        v = v[1:-1]
    return v


def route_map_delay(config: str) -> int:
    """bgpd's route-map update delay (`bgp route-map delay-timer N`, printed only when not the default): a route-map
    defined or changed during the config load is re-applied to `network` statements that many seconds later."""
    found = _RMAP_DELAY.findall(config)
    if len(found) > 1:
        raise Unknown("bgpd's running config sets the route-map delay timer more than once")
    return int(found[0]) if found else RMAP_DELAY_DEFAULT


def _denied(lab, node: str, driver: str, inst: Instance, net: Network, loaded: bool, config: str) -> str:
    """Why a `network` with a route-map and no import-check entry needs none, on positive evidence only, or Unknown.
    bgp_static_update() applies the route-map first: on a deny it withdraws the prefix and registers nothing, so
    bgpd holds no path of its own and no entry. Absence alone is never the evidence: a network bgpd hasn't applied
    yet looks the same, so bgpd must have finished loading its config (its boot log says so), and its BGP table must
    answer, for exactly this prefix, that it holds no path of its own. Then bgpd must show the route-map decided:
    either the route-map is not defined at all (bgpd denies a network whose map doesn't exist, and so would a router
    in production running this config), or bgpd applied it (invoked) and has no change to it still waiting
    (processedChange false). A map defined after the `network` is applied only by bgpd's route-map update, which
    `bgp route-map delay-timer 0` turns off: the map then never ran on the network (review of 5a36902, MAJOR-A: a
    permitting map read as a deny). The samples must then stay the same past the route-map delay (NodeRead.hold)."""
    what = f"{net.prefix} in {inst.header!r} has route-map {net.route_map} and no import-check entry"
    if driver != "frr":
        raise Unknown(f"{what}: on a {driver} router a route-map deny can't be told from a network bgpd hasn't "
                      "applied yet (its log doesn't show when bgpd finished loading its config)")
    if not loaded:
        raise Unknown(f"{what}, and its boot log doesn't show bgpd finished loading its config")
    if net.family[1] != "unicast":
        raise Unknown(f"{what} in address family {' '.join(net.family)}, whose BGP table this check doesn't read")
    from . import frr
    sel = "" if inst.vrf == "default" else f" vrf {inst.vrf}"
    cmd = f"show bgp{sel} {net.family[0]} unicast {net.prefix} json"
    x = lab.exec(node, ["vtysh", "-c", cmd])
    if x.rc != 0:
        raise Unknown(f"{what}, and `{cmd}` failed ({_cut(x.stderr or x.stdout)})")
    try:
        own = [p for p in frr._bgp_paths_raw(frr.BGP_PATHS_CMD, x.stdout, net.prefix) if not frr._learned(p)]
    except DriverError as e:
        raise Unknown(f"{what}, and `{cmd}` gave no answer this check can use ({e})") from None
    if own:
        raise Unknown(f"{what} but a path of its own in the BGP table")
    rm = lab.exec(node, route_map_command(net.route_map))
    if rm.rc != 0:
        raise Unknown(f"{what}, and bgpd's route-map {net.route_map} could not be read "
                      f"({_cut(rm.stderr or rm.stdout)})")
    state = parse_route_map(rm.stdout, net.route_map)
    in_config = re.search(rf"(?m)^route-map {re.escape(net.route_map)} (?:permit|deny) \d+$", config) is not None
    if state is None:
        if in_config:
            raise Unknown(f"{what}: bgpd's running config defines route-map {net.route_map} but bgpd says it has "
                          "none")
        return (f"its route-map {net.route_map} is not defined, so bgpd denies it (as production running this "
                "config would): no path of its own, no entry")
    if not in_config:
        raise Unknown(f"{what}: bgpd has route-map {net.route_map} but its running config doesn't define it")
    invoked, pending = state
    if pending and route_map_delay(config) == 0:
        raise ImportCheckError(
            f"{node}: {what}, and bgpd never applied the route-map's last change (`processedChange`): with "
            "`bgp route-map delay-timer 0` bgpd never applies a route-map change, wherever the route-map is "
            "defined, so whether this network is denied by the route-map or only by the boot order can't be told, "
            "and the lab may withhold a prefix production announces. Remove `bgp route-map delay-timer 0` from the "
            "lab's config. No verdict.")
    if pending:
        raise Unknown(f"{what}, and bgpd hasn't applied the last change to route-map {net.route_map} yet")
    if invoked == 0:
        raise Unknown(f"{what}, and bgpd never applied route-map {net.route_map}")
    return (f"denied by its route-map {net.route_map}: bgpd applied it with no change waiting, no path of its "
            "own, no entry")


def read_node(lab, node: str, driver: str) -> NodeRead:
    """One sample of one router. Raises Unknown for anything that isn't a complete, understood answer."""
    r = lab.exec(node, BGPD_CONFIG)
    if r.rc != 0:
        if _startup_has_bgp(lab, node) is False:
            return NodeRead(node, skipped="bgpd doesn't answer and its startup config has no `router bgp`")
        if _bgpd_down(lab, node, r):
            # nothing announces, so nothing is stuck now; a bgpd that starts later is read by the recheck before the
            # verdict (runner) or after the snapshot (verify)
            return NodeRead(node, skipped=BGPD_DOWN)
        raise Unknown(f"bgpd's running config could not be read ({_cut(r.stderr or r.stdout)})")
    instances = parse_bgpd_config(r.stdout)
    if not instances:
        if driver == "frr" and _startup_has_bgp(lab, node) is not False:
            raise Unknown("bgpd's running config has no `router bgp` yet (its startup config has one, or can't be "
                          "read): bgpd hasn't loaded its config")
        return NodeRead(node, skipped="no `router bgp` in bgpd's running config", config=r.stdout)
    loaded = False   # the boot log shows bgpd's config load ended
    # a router with no `network` to check has no table to wait for, so its boot log is the config load check's alone
    if driver == "frr" and any(inst.checked for inst in instances):
        log = lab.boot_log(node)
        if log.rc != 0:
            raise Unknown(f"its boot log could not be read ({_cut(log.stderr or log.stdout)}), so whether bgpd is "
                          "still applying its config is unknown")
        starts = list(_BGPD_LOADING.finditer(log.stdout))
        for m in starts:
            # vtysh -b ends bgpd's part with "done", or, when bgpd rejected a line, with "Configuration
            # file[...] processing failure: N" (tests/fixtures/frr_boot_log_rejected.txt): the config load check
            # reports that one
            if not re.search(rf"(?m)^\[{m.group(1)}\|bgpd\] (?:done|Configuration file\[.*\] processing "
                             rf"failure: \d+)$", log.stdout):
                raise Unknown("its boot log shows bgpd still applying its config")
        loaded = bool(starts)
    read = NodeRead(node, config=r.stdout)
    vrf_ids = None   # bgpd's VRF ids, read once per sample when a VRF instance has networks to check
    denied = False
    for inst in instances:
        nets = inst.checked
        if not nets:
            continue
        inactive = False
        if inst.vrf != "default":
            if vrf_ids is None:
                v = lab.exec(node, VRFS)
                if v.rc != 0:
                    raise Unknown(f"`{VRFS[-1]}` failed ({_cut(v.stderr or v.stdout)})")
                vrf_ids = parse_bgp_vrfs(v.stdout)
            if inst.vrf not in vrf_ids:
                raise Unknown(f"`{VRFS[-1]}` doesn't list the instance {inst.header!r}")
            inactive = vrf_ids[inst.vrf] == VRF_UNKNOWN
        text_cmd, json_cmd = table_commands(inst.vrf)
        where = f"`{' '.join(json_cmd[2:])}`"
        rj = lab.exec(node, json_cmd)
        rt = lab.exec(node, text_cmd)
        if rj.rc != 0 or rt.rc != 0:
            bad = rj if rj.rc != 0 else rt
            raise Unknown(f"`{bad.cmd[-1] if bad.cmd else ''}` failed ({_cut(bad.stderr or bad.stdout)})")
        from_json = parse_table_json(rj.stdout, where)
        if inactive:
            # bgpd names the VRF of a path in an instance zebra doesn't know "Unknown" in JSON, by name in text
            # (live: tests/fixtures/frr_fp043ic_followup)
            from_json = [Entry(e.address, e.valid, e.registered,
                               tuple(sorted((p[0], inst.vrf if p[1] == "Unknown" else p[1], p[2], p[3])
                                            for p in e.paths)))
                         for e in from_json]
        from_text = parse_table_text(rt.stdout, f"`{text_cmd[2]}`")
        if sorted(from_json, key=repr) != sorted(from_text, key=repr):
            raise Unknown(f"the import-check table's text and JSON answers disagree in {inst.header!r}")
        missing = [n for n in nets if not any(p[0] == n.prefix and p[1] == inst.vrf and p[2] == n.family
                                              for e in from_json for p in e.paths)]
        plain = [n for n in missing if not n.route_map]
        if plain:
            raise Unknown(f"{inst.header!r} has no import-check entry for network(s) "
                          f"{', '.join(n.prefix for n in plain)} (bgpd hasn't applied them yet, or the table is "
                          "not what it holds)")
        for n in missing:
            read.exempt.append((inst.vrf, n.prefix, _denied(lab, node, driver, inst, n, loaded, r.stdout)))
            denied = True
        read.entries[inst.vrf] = tuple(sorted(from_json, key=repr))
        for e in from_json:
            why = e.stuck()
            if why and inactive and not e.valid and e.paths and not any(p[3] for p in e.paths):
                # the VRF has no device in zebra (bgpd: vrfId -1): the entry can't register, and bgpd announces
                # nothing from the instance (every path that depends on it invalid), as production without the
                # VRF. A VRF created later is read by the recheck before the verdict
                read.exempt.append((inst.vrf, e.address, "its VRF is not active in zebra (bgpd vrfId -1): the entry "
                                    "can't register, and every path that depends on it is invalid"))
                continue
            if why:
                read.stuck.append((inst, ", ".join(p[0] for p in e.paths) or e.address, why))
    if denied:
        # a route-map defined or changed while bgpd loaded its config is re-applied to the networks this many seconds
        # later: a deny read before then could still turn into a path (and an entry, stuck or not)
        read.hold = route_map_delay(r.stdout) + SAMPLE_GAP + 1.0
    return read


def _settled(lab, nodes: dict[str, str], *, clock, sleep, budget: float, log, label: str) -> dict[str, NodeRead]:
    """Every router read completely, on two consecutive samples that agree, within the budget; else an error. A
    sample that holds an exemption (NodeRead.hold) counts only once the same answer has held that long."""
    deadline = clock() + budget
    last: dict[str, tuple] | None = None
    since = 0.0   # when `last` was first seen
    while True:
        reads: dict[str, NodeRead] = {}
        problems: dict[str, str] = {}
        for node, driver in sorted(nodes.items()):
            try:
                reads[node] = read_node(lab, node, driver)
            except Unknown as e:
                problems[node] = str(e)
        now = {n: r.signature() for n, r in reads.items()}
        t = clock()
        if not problems and last == now:
            hold = max((r.hold for r in reads.values()), default=0.0)
            left = hold - (t - since)
            if left <= 0:
                return reads
            if since + hold > deadline:
                raise ImportCheckError(
                    f"{label}a route-map deny counts only once it has held past bgpd's route-map delay ({hold:g}s "
                    f"with the sampling, from `bgp route-map delay-timer`), which ends after this check's "
                    f"{budget:g}s limit: whether the lab announces only what its routes back is unknown. Lower "
                    "`bgp route-map delay-timer`. No verdict.")
            if t >= deadline:
                raise ImportCheckError(f"{label}could not hold every FRR router's BGP import check for {hold:g}s "
                                       f"within {budget:g}s (a route-map deny counts only past bgpd's route-map "
                                       "delay), so whether the lab announces only what its routes back is unknown. "
                                       "No verdict.")
            sleep(min(left, SAMPLE_GAP) if SAMPLE_GAP > 0 else left)
            continue
        if t >= deadline:
            why = "; ".join(f"{n}: {p}" for n, p in sorted(problems.items())) or (
                "the import-check tables kept changing between samples")
            raise ImportCheckError(f"{label}could not read every FRR router's BGP import check within {budget:g}s, "
                                   f"so whether the lab announces only what its routes back is unknown: {why}. "
                                   "No verdict.")
        retry = bool(problems) or last is not None   # unreadable, or two samples that disagree
        last, since = (None, t) if problems else (now, t)
        sleep(RETRY_GAP if retry else SAMPLE_GAP)


def _sessions(lab, node: str) -> dict:
    """(vrf, neighbor) -> (state, established count, dropped count) from bgpd; unreadable: an error."""
    r = lab.exec(node, NEIGHBORS)
    try:
        if r.rc != 0:
            raise ValueError
        top = json.loads(r.stdout)
        out = {}
        for vrf, peers in top.items():
            if not isinstance(peers, dict):
                raise ValueError
            for name, p in peers.items():
                if name in ("vrfId", "vrfName"):
                    continue
                if not isinstance(p, dict):
                    raise ValueError
                st, up, down = p.get("bgpState"), p.get("connectionsEstablished"), p.get("connectionsDropped")
                if not isinstance(st, str) or not isinstance(up, int) or not isinstance(down, int):
                    raise ValueError
                out[(vrf, name)] = (st, up, down)
        return out
    except (ValueError, AttributeError, json.JSONDecodeError):
        raise ImportCheckError(f"{node}: its BGP sessions could not be read around the import-check remedy "
                               f"({_cut(r.stderr or r.stdout)}), so whether the remedy reset one is unknown. "
                               "No verdict.") from None


def gap_warnings(found: dict[str, str]) -> list[str]:
    """The guard's "not checked" nodes as baseline gap lines: first in the file, and `record` exits 1 (RT-0066)."""
    return [f"INCOMPLETE BASELINE: {n}: its FRR import check is {what}; a route bgpd announces without zebra backing "
            "it may be recorded" for n, what in sorted(found.items()) if what.startswith("not checked")]


def remedy_command(instances: list[Instance]) -> list[str]:
    """One vtysh call: import check off and on in each stuck instance, under its exact `router bgp` line."""
    argv = ["vtysh", "-c", "configure terminal"]
    for inst in instances:
        argv += ["-c", inst.header, "-c", "no bgp network import-check", "-c", "bgp network import-check",
                 "-c", "exit"]
    return argv[:-2] + ["-c", "end"]


def _describe(stuck: list) -> str:
    return "; ".join(f"{p} in {inst.header!r} {why}" for inst, p, why in stuck)


def guard(lab, nodes: dict[str, str], *, remedy: bool, clock: Callable[[], float], sleep: Callable[[float], None],
          log: Callable[[str], None] = lambda _: None, label: str = "", budget: float = BUDGET) -> dict[str, str]:
    """Check (and on a lab this run deployed, remedy) every FRR router's import check. `nodes`: router -> driver
    ("frr" or "sonic"). Returns router -> what was found or done, for the report; raises ImportCheckError when the
    lab can't be judged."""
    label = f"[{label}] " if label else ""
    gaps = getattr(nodes, "gaps", {})
    for name, how in sorted(getattr(nodes, "found", {}).items()):
        log(f"{label}{name}: no driver claims it, but {how}: its import check is guarded as FRR's")
    for name in sorted(getattr(nodes, "not_frr", [])):
        log(f"{label}{name}: no driver claims it and its image has no vtysh: not an FRR router, no import check")
    for name, why in sorted(gaps.items()):
        log(f"{label}WARNING {name}: {why}")
    if not nodes:   # no FRR router: nothing to sample (review MINOR-5)
        return {n: f"not checked: {why}" for n, why in gaps.items()}
    reads = _settled(lab, nodes, clock=clock, sleep=sleep, budget=budget, log=log, label=label)
    stuck = {n: r for n, r in reads.items() if r.stuck}
    found = {n: (r.skipped or "registered" + "".join(f"; {p} (vrf {v}) needs no entry: {why}"
                                                     for v, p, why in sorted(r.exempt)))
             for n, r in reads.items()}
    found.update({n: f"not checked: {why}" for n, why in gaps.items()})

    def said(found: dict[str, str]) -> dict[str, str]:   # a router found by probing says so in the report
        for n, how in getattr(nodes, "found", {}).items():
            if n in found:
                found[n] = f"{found[n]} (no driver claims it; {how})"
        return found
    if not stuck:
        return said(found)
    listing = " | ".join(f"{n}: {_describe(r.stuck)}" for n, r in sorted(stuck.items()))
    if not remedy:
        where = ("once the evidence was taken (nothing is remedied then)" if label
                 else "on a lab this run didn't deploy")
        raise ImportCheckError(
            f"{label}FRR's import check is stuck {where}: {listing}. bgpd applied these "
            "`network` statements before its zebra connection was up and never registered them, so it announces "
            "them whatever its routes say (production would not). Redeploy the lab, or on each router run "
            "`vtysh -c 'configure terminal' -c 'router bgp <asn>' -c 'no bgp network import-check' "
            "-c 'bgp network import-check' -c 'end'`. No verdict.")
    routers = [n for n, r in reads.items() if not r.skipped]
    before = {n: _sessions(lab, n) for n in routers}
    for node, r in sorted(stuck.items()):
        instances = []
        for inst, _p, _w in r.stuck:
            if inst not in instances:
                instances.append(inst)
        log(f"{label}{node}: import check stuck ({_describe(r.stuck)}); toggling it off and on to register it")
        x = lab.exec(node, remedy_command(instances))
        if x.rc != 0 or x.stdout.strip() or x.stderr.strip():
            raise ImportCheckError(f"{label}{node}: the import-check remedy failed (rc {x.rc}: "
                                   f"{_cut(x.stderr or x.stdout)}) while {_describe(r.stuck)}. No verdict.")
    after = _settled(lab, nodes, clock=clock, sleep=sleep, budget=budget, log=log, label=label)
    still = {n: r for n, r in after.items() if r.stuck}
    if still:
        raise ImportCheckError(
            f"{label}FRR's import check is still stuck after the remedy: "
            f"{' | '.join(f'{n}: {_describe(r.stuck)}' for n, r in sorted(still.items()))}. The lab would announce "
            "prefixes production withdraws. No verdict.")
    for node in stuck:
        if after[node].config != reads[node].config:
            raise ImportCheckError(f"{label}{node}: bgpd's running config changed across the import-check remedy, "
                                   "so the lab no longer runs the config under test. No verdict.")
    for node in routers:
        now = _sessions(lab, node)
        for key, (state, up, down) in before[node].items():
            s2 = now.get(key)
            if s2 is None or s2[2] != down or (state == "Established" and (s2[0] != state or s2[1] != up)):
                raise ImportCheckError(
                    f"{label}{node}: BGP session {key[1]} (vrf {key[0]}) changed across the import-check remedy "
                    f"({state}, {up} established, {down} dropped -> "
                    f"{'gone' if s2 is None else f'{s2[0]}, {s2[1]} established, {s2[2]} dropped'}): the toggle may "
                    "have announced a transient prefix (a maximum-prefix limit, dampening). No verdict.")
    for node, r in stuck.items():
        found[node] = f"remedied: {_describe(r.stuck)}; registered after the remedy"
    return said(found)


class Candidates(dict):
    """router -> driver, plus `found` (router -> how a node with no known driver was found to run FRR) and `gaps`
    (node -> why the guard could not tell whether it runs FRR): never dropped in silence (RT-0066)."""

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.found: dict[str, str] = {}
        self.gaps: dict[str, str] = {}
        self.not_frr: list[str] = []   # probed: the image has no vtysh


def probe(lab, name: str) -> str | None:
    """Whether a node no driver claims runs FRR's bgpd (review of 5a36902, MAJOR-B: a retagged FRR image, no driver
    override, was never guarded). vtysh answering bgpd's running config, or saying it can't reach bgpd, is FRR; Docker
    saying the image has no vtysh is not. Anything else raises Unknown: the caller reports it as a gap."""
    r = lab.exec(name, BGPD_CONFIG)
    said = f"{r.stdout}\n{r.stderr}"
    if r.rc == 0 and said.lstrip().startswith("Building configuration..."):
        return "vtysh answers with bgpd's running config"
    if r.rc != 0 and NO_DAEMON in said:
        return "vtysh is there but can't reach bgpd"
    if r.rc == 127 and NO_VTYSH in said:
        return None
    raise Unknown(f"`{' '.join(BGPD_CONFIG)}` answered rc {r.rc} ({_cut(r.stderr or r.stdout)})")


def candidates(lab, driver_of: Callable[[str, object], str | None]) -> Candidates:
    """Every node of the lab that runs FRR's bgpd (FRR, SONiC): router -> driver. A node no driver claims (an image
    whose name names no NOS) is probed: FRR found that way is guarded as FRR, and one that can't be told is a gap."""
    out = Candidates()
    for name, node in lab.nodes.items():
        if node.kind in ("bridge", "ovs-bridge"):
            continue
        try:
            d = driver_of(name, node)
        except (DriverError, LabError):   # no driver: not a router this check can read (as mgmt.prepare skips it)
            d = None
        if d in ("frr", "sonic"):
            out[name] = d
        elif d is None:
            try:
                how = probe(lab, name)
            except (Unknown, LabError) as e:
                out.gaps[name] = (f"no driver claims it and whether it runs FRR could not be told ({e}): its import "
                                  "check is not checked")
                continue
            if how:
                out[name], out.found[name] = "frr", how
            else:
                out.not_frr.append(name)
    return out
