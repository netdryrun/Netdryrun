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
_BGPD_LOADING = re.compile(r"^\[(\d+)\|bgpd\] sending configuration$", re.M)
_TEXT_HEADER = "Current BGP import check cache:"
_TEXT_ENTRY = re.compile(r"^ (?:SR-TE color \d+ - )?(\S+) (valid \[IGP metric \d+\]|invalid), #paths (\d+)"
                         r"(?:, peer \S+)?(?: EVPN Gateway IP)?$")
_TEXT_DETAIL = re.compile(r"^  (?:Must be Connected|Resolved prefix \S+|gate \S+.*|if \S+, ifindex \d+|blackhole"
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
        return [n for n in self.networks if n.family in CHECKED_FAMILIES and n.prefix not in NEVER_REGISTERED]


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

    def signature(self) -> tuple:
        return (self.skipped, self.config, tuple(sorted(self.entries.items())))


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
            cur.networks.append(Network(str(net), where))
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


def read_node(lab, node: str, driver: str) -> NodeRead:
    """One sample of one router. Raises Unknown for anything that isn't a complete, understood answer."""
    r = lab.exec(node, BGPD_CONFIG)
    if r.rc != 0:
        if _startup_has_bgp(lab, node) is False:
            return NodeRead(node, skipped="bgpd doesn't answer and its startup config has no `router bgp`")
        raise Unknown(f"bgpd's running config could not be read ({_cut(r.stderr or r.stdout)})")
    instances = parse_bgpd_config(r.stdout)
    if not instances:
        if driver == "frr" and _startup_has_bgp(lab, node) is not False:
            raise Unknown("bgpd's running config has no `router bgp` yet (its startup config has one, or can't be "
                          "read): bgpd hasn't loaded its config")
        return NodeRead(node, skipped="no `router bgp` in bgpd's running config", config=r.stdout)
    if driver == "frr":
        log = lab.boot_log(node)
        if log.rc == 0:
            for m in _BGPD_LOADING.finditer(log.stdout):
                # vtysh -b ends bgpd's part with "done", or, when bgpd rejected a line, with "Configuration
                # file[...] processing failure: N" (tests/fixtures/frr_boot_log_rejected.txt): the config load check
                # reports that one
                if not re.search(rf"(?m)^\[{m.group(1)}\|bgpd\] (?:done|Configuration file\[.*\] processing "
                                 rf"failure: \d+)$", log.stdout):
                    raise Unknown("its boot log shows bgpd still applying its config")
    read = NodeRead(node, config=r.stdout)
    for inst in instances:
        nets = inst.checked
        if not nets:
            continue
        text_cmd, json_cmd = table_commands(inst.vrf)
        where = f"`{' '.join(json_cmd[2:])}`"
        rj = lab.exec(node, json_cmd)
        rt = lab.exec(node, text_cmd)
        if rj.rc != 0 or rt.rc != 0:
            bad = rj if rj.rc != 0 else rt
            raise Unknown(f"`{bad.cmd[-1] if bad.cmd else ''}` failed ({_cut(bad.stderr or bad.stdout)})")
        from_json = parse_table_json(rj.stdout, where)
        from_text = parse_table_text(rt.stdout, f"`{text_cmd[2]}`")
        if sorted(from_json, key=repr) != sorted(from_text, key=repr):
            raise Unknown(f"the import-check table's text and JSON answers disagree in {inst.header!r}")
        missing = [n for n in nets if not any(p[0] == n.prefix and p[1] == inst.vrf and p[2] == n.family
                                              for e in from_json for p in e.paths)]
        if missing:
            raise Unknown(f"{inst.header!r} has no import-check entry for network(s) "
                          f"{', '.join(n.prefix for n in missing)} (bgpd hasn't applied them yet, or the table is "
                          "not what it holds)")
        read.entries[inst.vrf] = tuple(sorted(from_json, key=repr))
        for e in from_json:
            why = e.stuck()
            if why:
                read.stuck.append((inst, ", ".join(p[0] for p in e.paths) or e.address, why))
    return read


def _settled(lab, nodes: dict[str, str], *, clock, sleep, budget: float, log, label: str) -> dict[str, NodeRead]:
    """Every router read completely, on two consecutive samples that agree, within the budget; else an error."""
    deadline = clock() + budget
    last: dict[str, tuple] | None = None
    while True:
        reads: dict[str, NodeRead] = {}
        problems: dict[str, str] = {}
        for node, driver in sorted(nodes.items()):
            try:
                reads[node] = read_node(lab, node, driver)
            except Unknown as e:
                problems[node] = str(e)
        now = {n: r.signature() for n, r in reads.items()}
        if not problems and last == now:
            return reads
        if clock() >= deadline:
            why = "; ".join(f"{n}: {p}" for n, p in sorted(problems.items())) or (
                "the import-check tables kept changing between samples")
            raise ImportCheckError(f"{label}could not read every FRR router's BGP import check within {budget:g}s, "
                                   f"so whether the lab announces only what its routes back is unknown: {why}. "
                                   "No verdict.")
        retry = bool(problems) or last is not None   # unreadable, or two samples that disagree
        last = None if problems else now
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
    reads = _settled(lab, nodes, clock=clock, sleep=sleep, budget=budget, log=log, label=label)
    stuck = {n: r for n, r in reads.items() if r.stuck}
    found = {n: (r.skipped or "registered") for n, r in reads.items()}
    if not stuck:
        return found
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
    return found


def candidates(lab, driver_of: Callable[[str, object], str | None]) -> dict[str, str]:
    """Every node of the lab that runs FRR's bgpd (FRR, SONiC): router -> driver."""
    out = {}
    for name, node in lab.nodes.items():
        if node.kind in ("bridge", "ovs-bridge"):
            continue
        try:
            d = driver_of(name, node)
        except (DriverError, LabError):   # no driver: not a router this check can read (as mgmt.prepare skips it)
            d = None
        if d in ("frr", "sonic"):
            out[name] = d
    return out
