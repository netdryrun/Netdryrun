"""The behavior snapshot that `netdryrun verify` compares: typed, normalised and strictly validated.

A snapshot holds, per node, one value per *item*. An item is identified by an ItemKey (kind, node, VRF,
AFI, SAFI, prefix, neighbor, protocol, add-path ID) and its value is one of the dataclasses below:

- ``session``: (node, VRF, neighbor) -> Session (state, ASNs, address families, local address)
- ``rib``:     (node, VRF, AFI, SAFI, prefix, protocol) -> tuple[RibEntry] (selected, FIB-installed,
  distance, metric, next hops with their resolution), every protocol zebra reports
- ``path``:    (node, VRF, AFI, SAFI, prefix, source, path ID) -> BgpPath, every BGP path per prefix
- ``adj_out``: (node, VRF, AFI, SAFI, neighbor, prefix, path ID) -> BgpAttrs, what the node advertises
- ``adj_in``:  (node, VRF, AFI, SAFI, neighbor, prefix, path ID) -> BgpAttrs, what it received before
  inbound policy (only where `soft-reconfiguration inbound` keeps it)

Normalisation is done once, when a value is built, and checked again by every constructor: AS_SEQUENCE
order is kept and AS_SET is a sorted set; communities are canonical (well-known names as their 65535:x
value); ECMP next-hop sets are sorted, so their order on the device never matters; absent attributes stay
None (never coerced to a default). Uptimes, timers, counters and table versions are never part of a value.

Anything that doesn't fit the schema raises SnapshotError (a DriverError): verify reports it as an error
(exit 2), never as "nothing changed".
"""
from __future__ import annotations

import ipaddress
import json
import re
import types
import typing
from dataclasses import dataclass, field, fields, is_dataclass

from ..drivers.base import DriverError

SNAPSHOT_SCHEMA = "netdryrun.snapshot/v1"
KINDS = ("session", "rib", "path", "adj_out", "adj_in")
DIFF_KINDS = KINDS + ("vrf", "config")    # "vrf": a VRF a node has (NodeSnapshot.vrfs); "config": its running
                                         # config (NodeSnapshot.config). Diff items, never stored items
AFIS = ("ipv4", "ipv6")
SAFIS = ("unicast",)
AFI_SAFIS = ("ipv4-unicast", "ipv6-unicast")      # the session address families verify 0.4 snapshots
ORIGINS = ("igp", "egp", "incomplete")
SEGMENT_TYPES = ("seq", "set", "confed-seq", "confed-set")
PATH_FLAGS = ("aggregated", "damped", "fibInstalled", "history", "removed", "rxedFromRrClient", "stale", "suppressed")


class SnapshotError(DriverError):
    """Driver output, or a stored snapshot, that does not match the snapshot schema."""


# ---------------------------------------------------------------------------------------------------------
# Canonical scalar forms
# ---------------------------------------------------------------------------------------------------------

def canon_ip(value: object, where: str = "address") -> str:
    """An IP address in canonical text form. IPv6 link-local addresses keep their %interface scope."""
    if not isinstance(value, str):
        raise SnapshotError(f"{where}: not an IP address: {str(value)[:80]!r}")
    try:
        return str(ipaddress.ip_address(value))
    except ValueError:
        raise SnapshotError(f"{where}: not an IP address: {value[:80]!r}") from None


def canon_prefix(value: object, where: str = "prefix") -> str:
    """A prefix in canonical text form; host bits set are an error (devices never print them)."""
    if not isinstance(value, str):
        raise SnapshotError(f"{where}: not a prefix: {str(value)[:80]!r}")
    try:
        return str(ipaddress.ip_network(value, strict=True))
    except ValueError:
        raise SnapshotError(f"{where}: not a prefix: {value[:80]!r}") from None


def prefix_afi(prefix: str) -> str:
    return "ipv6" if ipaddress.ip_network(prefix).version == 6 else "ipv4"


# Well-known communities by every name FRR and netdryrun.yml use, as their numeric value
_WELL_KNOWN = {
    "internet": "0:0", "graceful-shutdown": "65535:0", "accept-own": "65535:1",
    "route-filter-translated-v4": "65535:2", "route-filter-v4": "65535:3", "route-filter-translated-v6": "65535:4",
    "route-filter-v6": "65535:5", "llgr-stale": "65535:6", "no-llgr": "65535:7", "accept-own-nexthop": "65535:8",
    "blackhole": "65535:666", "no-export": "65535:65281", "no-advertise": "65535:65282",
    "no-export-subconfed": "65535:65283", "local-as": "65535:65283", "no-peer": "65535:65284",
}
_UINT16 = 0xFFFF
_UINT32 = 0xFFFFFFFF


def canon_community(token: object) -> str:
    """A standard community: `65000:100`, or a well-known name, as its numeric `a:b` form."""
    t = str(token).strip().lower().replace("_", "-")
    if t in _WELL_KNOWN:
        return _WELL_KNOWN[t]
    m = re.fullmatch(r"(\d+):(\d+)", t)
    if m and int(m.group(1)) <= _UINT16 and int(m.group(2)) <= _UINT16:
        return f"{int(m.group(1))}:{int(m.group(2))}"
    if re.fullmatch(r"\d+", t) and int(t) <= _UINT32:     # the 32-bit integer form
        n = int(t)
        return f"{n >> 16}:{n & _UINT16}"
    raise SnapshotError(f"not a standard community: {str(token)[:60]!r}")


def canon_large_community(token: object) -> str:
    m = re.fullmatch(r"(\d+):(\d+):(\d+)", str(token).strip())
    if not m or any(int(x) > _UINT32 for x in m.groups()):
        raise SnapshotError(f"not a large community: {str(token)[:60]!r}")
    return ":".join(str(int(x)) for x in m.groups())


_EXT_TYPES = {"rt": "rt", "soo": "soo", "lb": "lb", "et": "et", "rmac": "rmac", "mm": "mm", "esi-label": "esi-label",
              "es-import-rt": "es-import-rt", "df-pref": "df-pref", "nd": "nd", "encap": "encap", "fs": "fs",
              "redirect": "redirect", "ipv6-rt": "ipv6-rt", "color": "color", "ot": "ot"}


def canon_ext_communities(text: object) -> tuple[str, ...]:
    """FRR's extended community string (`RT:65000:100 SoO:65000:1 LB:65000:125000 (1.000 Mbps)`) as a
    sorted tuple of `type:value` tokens (type lower-case). Text the parser doesn't recognise is an error."""
    if not isinstance(text, str):
        raise SnapshotError(f"extended communities: not a string: {str(text)[:80]!r}")
    out = []
    pos = 0
    pattern = re.compile(r"\s*([A-Za-z][A-Za-z0-9-]*):(\S+?)(?:\s+\([^)]*\))?(?=\s|$)")
    while pos < len(text.rstrip()):
        m = pattern.match(text, pos)
        if not m or m.group(1).lower() not in _EXT_TYPES:
            raise SnapshotError(f"extended communities: cannot read {text[pos:pos + 60]!r}")
        out.append(f"{_EXT_TYPES[m.group(1).lower()]}:{m.group(2).lower()}")
        pos = m.end()
    return tuple(sorted(set(out)))


def canon_ext_community(token: object) -> str:
    """One extended community as written in an intent file (`rt:65000:100`)."""
    got = canon_ext_communities(str(token))
    if len(got) != 1:
        raise SnapshotError(f"not one extended community: {str(token)[:60]!r}")
    return got[0]


def parse_asn(value: object, where: str = "ASN") -> int:
    """An ASN in asplain; asdot (`1.10`) is converted. Anything else is an error."""
    if isinstance(value, bool):
        raise SnapshotError(f"{where}: not an ASN: {value!r}")
    if isinstance(value, int):
        n = value
    elif isinstance(value, str) and re.fullmatch(r"\d+", value.strip()):
        n = int(value)
    elif isinstance(value, str) and re.fullmatch(r"\d+\.\d+", value.strip()):
        hi, lo = (int(x) for x in value.strip().split("."))
        if hi > _UINT16 or lo > _UINT16:
            raise SnapshotError(f"{where}: not an ASN: {value!r}")
        n = (hi << 16) | lo
    else:
        raise SnapshotError(f"{where}: not an ASN: {str(value)[:40]!r}")
    if not 0 <= n <= _UINT32:
        raise SnapshotError(f"{where}: ASN out of range: {n}")
    return n


# ---------------------------------------------------------------------------------------------------------
# Typed values
# ---------------------------------------------------------------------------------------------------------

def _plain(obj):
    if is_dataclass(obj):
        return {f.name: _plain(getattr(obj, f.name)) for f in fields(obj)}
    if isinstance(obj, tuple):
        return [_plain(x) for x in obj]
    return obj


def sort_key(obj) -> str:
    """A total order for any snapshot value (None-safe), used to store sets as sorted tuples."""
    return json.dumps(_plain(obj), sort_keys=True)


def canon_set(values) -> tuple:
    """A set of snapshot values as a canonical sorted tuple, duplicates removed."""
    uniq = {sort_key(v): v for v in values}
    return tuple(uniq[k] for k in sorted(uniq))


def _require(cond: bool, what: str) -> None:
    if not cond:
        raise SnapshotError(what)


@dataclass(frozen=True)
class AsPath:
    """AS path segments in order. AS_SEQUENCE order is kept; adjacent sequences are merged; AS_SET (and
    confederation sets) are sorted sets."""
    segments: tuple[tuple[str, tuple[int, ...]], ...] = ()

    def __post_init__(self):
        prev = None
        for seg in self.segments:
            _require(isinstance(seg, tuple) and len(seg) == 2, f"AS path: bad segment {seg!r}")
            kind, asns = seg
            _require(kind in SEGMENT_TYPES, f"AS path: unknown segment type {kind!r}")
            _require(bool(asns) and all(isinstance(a, int) and not isinstance(a, bool) and 0 <= a <= _UINT32
                                        for a in asns), f"AS path: bad ASNs {asns!r}")
            if kind.endswith("set"):
                _require(list(asns) == sorted(set(asns)), f"AS path: {kind} not a sorted set: {asns!r}")
            _require(not (kind == prev == "seq"), "AS path: adjacent sequences not merged")
            prev = kind

    @classmethod
    def build(cls, segments) -> "AsPath":
        """From (type, ASNs) pairs in any of the spellings devices use, normalised."""
        out: list[tuple[str, tuple[int, ...]]] = []
        for kind, asns in segments:
            k = str(kind).lower().replace("_", "-").replace("as-", "", 1).replace("sequence", "seq")
            k = {"seq": "seq", "set": "set", "confed-seq": "confed-seq", "confed-set": "confed-set",
                 "confederation-seq": "confed-seq", "confederation-set": "confed-set"}.get(k)
            if k is None:
                raise SnapshotError(f"AS path: unknown segment type {str(kind)[:40]!r}")
            nums = [parse_asn(a, "AS path") for a in asns]
            if not nums:
                raise SnapshotError("AS path: empty segment")
            if k.endswith("set"):
                out.append((k, tuple(sorted(set(nums)))))
            elif out and out[-1][0] == k == "seq":
                out[-1] = (k, out[-1][1] + tuple(nums))
            else:
                out.append((k, tuple(nums)))
        return cls(tuple(out))

    @classmethod
    def parse(cls, text: object) -> "AsPath":
        """From the text form used in intent files and reports: `65001 65002 {65003,65004} (65010) [65011]`.
        An empty string is the empty path (a locally originated route)."""
        if isinstance(text, bool) or not isinstance(text, (str, int)):
            raise SnapshotError(f"as_path must be a string such as '65001 65002', got {text!r}")
        s = re.sub(r"\s*,\s*", ",", str(text).strip())
        segs: list[tuple[str, list]] = []
        pos = 0
        token = re.compile(r"\s*(?:(\d+(?:\.\d+)?)|\{([\d.,]+)\}|\(([\d. ]+)\)|\[([\d.,]+)\])")
        while pos < len(s):
            m = token.match(s, pos)
            if not m or m.end() == pos:
                raise SnapshotError(f"bad as_path {str(text)[:80]!r}: use ASNs separated by spaces, sets as {{a,b}}")
            if m.group(1):
                segs.append(("seq", [m.group(1)]))
            elif m.group(2):
                segs.append(("set", m.group(2).split(",")))
            elif m.group(3):
                segs.append(("confed-seq", m.group(3).split()))
            else:
                segs.append(("confed-set", m.group(4).split(",")))
            pos = m.end()
        return cls.build(segs)

    def render(self) -> str:
        parts = []
        for kind, asns in self.segments:
            if kind == "seq":
                parts += [str(a) for a in asns]
            elif kind == "set":
                parts.append("{" + ",".join(str(a) for a in asns) + "}")
            elif kind == "confed-seq":
                parts.append("(" + " ".join(str(a) for a in asns) + ")")
            else:
                parts.append("[" + ",".join(str(a) for a in asns) + "]")
        return " ".join(parts)


@dataclass(frozen=True)
class NextHop:
    """One zebra next hop, with the next hops that resolve it (recursive routes)."""
    ip: str | None
    interface: str | None
    vrf: str | None
    active: bool
    fib: bool
    directly_connected: bool
    on_link: bool
    recursive: bool
    duplicate: bool
    kind: str                       # "gateway", "interface", "blackhole", "unreachable", "reject"
    weight: int | None
    labels: tuple[int, ...]
    src: str | None
    resolved_via: tuple[NextHop, ...] = ()

    def __post_init__(self):
        _require(self.kind in ("gateway", "interface", "blackhole", "unreachable", "reject"),
                 f"next hop: unknown kind {self.kind!r}")
        _require(self.resolved_via == canon_set(self.resolved_via), "next hop: resolvers not canonical")


@dataclass(frozen=True)
class RibEntry:
    """One zebra RIB entry for a prefix (one protocol may have several, e.g. statics with two distances)."""
    protocol: str
    instance: int | None
    selected: bool
    fib: bool
    distance: int
    metric: int
    tag: int | None
    table: int | None
    failed: bool
    nexthops: tuple[NextHop, ...]

    def __post_init__(self):
        _require(self.nexthops == canon_set(self.nexthops), "RIB entry: next hops not canonical (ECMP is a set)")


@dataclass(frozen=True)
class PathNextHop:
    """A BGP path's next hop and its resolution (accessible, IGP metric)."""
    ip: str
    scope: str                      # "global" or "link-local"
    accessible: bool
    used: bool
    igp_metric: int | None
    interface: str | None

    def __post_init__(self):
        _require(self.scope in ("global", "link-local"), f"BGP next hop: unknown scope {self.scope!r}")


@dataclass(frozen=True)
class BgpAttrs:
    origin: str
    as_path: AsPath
    next_hops: tuple[PathNextHop, ...]
    local_pref: int | None          # None: the path carries no LOCAL_PREF (compared as parsed)
    med: int | None                 # None: no MULTI_EXIT_DISC
    weight: int | None
    communities: tuple[str, ...]
    ext_communities: tuple[str, ...]
    large_communities: tuple[str, ...]
    cluster_list: tuple[str, ...]   # order kept
    originator_id: str | None
    atomic_aggregate: bool
    aggregator: str | None          # "ASN:router-id"
    extra: tuple[tuple[str, str], ...] = ()   # other attributes the driver reads (OTC, AIGP, labels), JSON text

    def __post_init__(self):
        _require(self.origin in ORIGINS, f"BGP origin: unknown value {self.origin!r}")
        _require(isinstance(self.as_path, AsPath), "BGP attributes: as_path is not an AsPath")
        _require(self.next_hops == canon_set(self.next_hops), "BGP attributes: next hops not canonical")
        _require(list(self.communities) == sorted(set(self.communities))
                 and all(canon_community(c) == c for c in self.communities), "BGP attributes: communities not canonical")
        _require(list(self.large_communities) == sorted(set(self.large_communities))
                 and all(canon_large_community(c) == c for c in self.large_communities),
                 "BGP attributes: large communities not canonical")
        _require(list(self.ext_communities) == sorted(set(self.ext_communities)),
                 "BGP attributes: extended communities not canonical")
        _require(list(self.extra) == sorted(set(self.extra)), "BGP attributes: extra attributes not canonical")


@dataclass(frozen=True)
class BgpPath:
    """One path in a node's BGP table (Loc-RIB), best or not, valid or not."""
    attrs: BgpAttrs
    best: bool
    multipath: bool
    valid: bool
    peer_type: str                  # "external", "internal", "confed-external", "confed-internal", "local"
    peer_router_id: str | None
    flags: tuple[str, ...] = ()     # aggregated, damped, fibInstalled, history, removed, rxedFromRrClient, stale,
                                    # suppressed

    def __post_init__(self):
        _require(isinstance(self.attrs, BgpAttrs), "BGP path: attrs is not BgpAttrs")
        _require(all(f in PATH_FLAGS for f in self.flags) and list(self.flags) == sorted(set(self.flags)),
                 f"BGP path: bad flags {self.flags!r}")


@dataclass(frozen=True)
class Session:
    # The raw FSM state ("established", "active", "idle", ...) is evidence only (compare=False): sessions are
    # compared as established or not (`established`, derived from it), so "active" vs "connect" is no change.
    state: str = field(compare=False)
    remote_as: int | None
    local_as: int | None
    afis: tuple[str, ...]           # address families configured on the session, e.g. ("ipv4-unicast",)
    local_address: str | None       # the session's local address while established
    # A derived fact: never part of the diff (compare=False), but part of stability.
    prefix_counts: tuple[tuple[str, int], ...] = field(default=(), compare=False)
    soft_reconfig_in: tuple[str, ...] = ()     # address families with soft-reconfiguration inbound (compared)
    established: bool = field(init=False)

    def __post_init__(self):
        _require(isinstance(self.state, str) and bool(self.state) and self.state == self.state.lower(),
                 f"session: bad state {self.state!r}")
        _require(all(a in AFI_SAFIS for a in self.afis) and list(self.afis) == sorted(set(self.afis)),
                 f"session: bad address families {self.afis!r}")
        object.__setattr__(self, "established", self.state == "established")


VALUE_TYPES = {"session": Session, "rib": tuple[RibEntry, ...], "path": BgpPath, "adj_out": BgpAttrs, "adj_in": BgpAttrs}


@dataclass(frozen=True, order=True)
class ItemKey:
    kind: str
    node: str
    vrf: str
    afi: str = ""
    safi: str = ""
    prefix: str = ""
    neighbor: str = ""      # session: the neighbor; path: the source ("local" or the peer); adj_*: the session
    protocol: str = ""      # rib only
    path_id: int = 0        # path and adj_*: the add-path ID (0 without add-path)

    def __post_init__(self):
        _require(self.kind in DIFF_KINDS, f"item key: unknown kind {self.kind!r}")
        _require(bool(self.node) and bool(self.vrf), "item key: node and vrf are required")
        if self.kind in ("vrf", "config"):
            _require(not (self.afi or self.safi or self.prefix or self.neighbor or self.protocol or self.path_id),
                     f"item key: bad {self.kind} key {self!r}")
        elif self.kind == "session":
            _require(bool(self.neighbor) and not (self.afi or self.prefix or self.protocol),
                     f"item key: bad session key {self!r}")
        else:
            _require(self.afi in AFIS and self.safi in SAFIS and bool(self.prefix), f"item key: bad key {self!r}")
            _require(prefix_afi(self.prefix) == self.afi, f"item key: {self.prefix} is not {self.afi}")
            _require((self.kind == "rib") == bool(self.protocol), f"item key: protocol only on rib items {self!r}")
            _require(self.kind == "rib" or bool(self.neighbor), f"item key: {self.kind} needs a neighbor")

    def where(self) -> str:
        bits = [self.node]
        if self.kind == "vrf":
            return f"{self.node} vrf {self.vrf}"
        if self.kind == "config":
            return f"{self.node} running config"
        if self.vrf != "default":
            bits.append(f"vrf {self.vrf}")
        if self.kind == "session":
            return f"{' '.join(bits)} session {self.neighbor}"
        bits.append(self.prefix)
        if self.kind == "rib":
            bits.append(f"[{self.protocol}]")
        elif self.kind == "path":
            bits.append(f"path from {self.neighbor}" + (f" (path id {self.path_id})" if self.path_id else ""))
        elif self.kind == "adj_out":
            bits.append(f"advertised to {self.neighbor}")
        else:
            bits.append(f"received from {self.neighbor} (before inbound policy)")
        return " ".join(bits)


def value_matches_kind(kind: str, value) -> bool:
    if kind not in VALUE_TYPES:
        return False
    if kind == "rib":
        return isinstance(value, tuple) and bool(value) and all(isinstance(e, RibEntry) for e in value) \
            and value == canon_set(value)
    return isinstance(value, VALUE_TYPES[kind])


@dataclass
class NodeSnapshot:
    node: str
    driver: str
    vrfs: tuple[str, ...]
    items: dict[ItemKey, object]
    raw: list[dict] = field(default_factory=list, compare=False)   # the commands and their output (evidence)
    # the longest advertisement interval (MRAI, seconds) the node's sessions report: when a route can still arrive
    # after the lab looks settled. A timer, not behavior: never compared, never stored (the raw output has it).
    adv_interval: float = field(default=0.0, compare=False)
    # the node's running config, normalised (frr.parse_running_config): compared, so a config change with no
    # observable effect is still a difference (0.4 gauntlet, R4). () where it isn't read (an older stored snapshot)
    config: tuple[str, ...] = ()
    # the conditional-advertisement scan interval (s) when an advertise-map is configured, else 0: like
    # adv_interval, how late an update can come after the lab looks settled. Never compared.
    cond_adv_timer: float = field(default=0.0, compare=False)

    def __post_init__(self):
        for k, v in self.items.items():
            _require(isinstance(k, ItemKey) and k.node == self.node, f"{self.node}: item {k!r} of another node")
            _require(k.vrf in self.vrfs, f"{self.node}: item in unknown VRF {k.vrf!r}")
            _require(value_matches_kind(k.kind, v), f"{self.node}: bad value for {k.where()}")


@dataclass
class Snapshot:
    nodes: dict[str, NodeSnapshot]
    unobserved: dict[str, str] = field(default_factory=dict)    # node -> why it has no snapshot

    def items(self) -> dict[ItemKey, object]:
        out: dict[ItemKey, object] = {}
        for ns in self.nodes.values():
            out.update(ns.items)
        return out

    def stability_view(self) -> dict:
        """What must be identical on two consecutive samples: every item, plus the derived facts (prefix
        counts) that the diff itself ignores."""
        view = {}
        for k, v in self.items().items():
            view[k] = (v, v.prefix_counts) if isinstance(v, Session) else v
        for n, ns in self.nodes.items():
            view[ItemKey("vrf", n, "default")] = ns.vrfs
            view[ItemKey("config", n, "default")] = ns.config
        return view

    def sessions(self) -> dict[ItemKey, Session]:
        return {k: v for k, v in self.items().items() if k.kind == "session"}

    def to_json(self, raw: bool = True) -> dict:
        return {"schema": SNAPSHOT_SCHEMA,
                "nodes": {n: {"driver": ns.driver, "vrfs": list(ns.vrfs),
                              "items": [{"key": _plain(k), "value": _plain(v)} for k, v in sorted(ns.items.items())],
                              "config": list(ns.config),
                              **({"raw": ns.raw} if raw else {})}
                          for n, ns in sorted(self.nodes.items())},
                "unobserved": dict(sorted(self.unobserved.items()))}

    @classmethod
    def from_json(cls, data: object) -> "Snapshot":
        """A stored snapshot, validated as strictly as driver output: an unknown or missing field is an error."""
        if not isinstance(data, dict) or set(data) != {"schema", "nodes", "unobserved"}:
            raise SnapshotError(f"snapshot: expected keys schema, nodes, unobserved; got {sorted(data) if isinstance(data, dict) else type(data).__name__}")
        if data["schema"] != SNAPSHOT_SCHEMA:
            raise SnapshotError(f"snapshot: schema must be {SNAPSHOT_SCHEMA!r}, got {data['schema']!r}")
        if not isinstance(data["nodes"], dict) or not isinstance(data["unobserved"], dict):
            raise SnapshotError("snapshot: nodes and unobserved must be mappings")
        nodes = {}
        for name, nd in data["nodes"].items():
            if not isinstance(nd, dict) or not {"driver", "vrfs", "items"} <= set(nd) <= {"driver", "vrfs", "items", "raw",
                                                                                         "config"}:
                raise SnapshotError(f"snapshot: node {name!r}: expected keys driver, vrfs, items (and raw, config)")
            items = {}
            if not isinstance(nd["items"], list):
                raise SnapshotError(f"snapshot: node {name!r}: items must be a list")
            for it in nd["items"]:
                if not isinstance(it, dict) or set(it) != {"key", "value"}:
                    raise SnapshotError(f"snapshot: node {name!r}: each item has exactly key and value")
                key = decode(ItemKey, it["key"], "item key")
                if key.kind not in VALUE_TYPES:
                    raise SnapshotError(f"snapshot: node {name!r}: a stored item can't be of kind {key.kind!r}")
                if key in items:
                    raise SnapshotError(f"snapshot: duplicate item {key.where()}")
                items[key] = decode(VALUE_TYPES[key.kind], it["value"], key.where())
            raw = nd.get("raw", [])
            if not isinstance(raw, list):
                raise SnapshotError(f"snapshot: node {name!r}: raw must be a list")
            nodes[name] = NodeSnapshot(str(name), _typed(str, nd["driver"], "driver"),
                                       decode(tuple[str, ...], nd["vrfs"], "vrfs"), items, raw,
                                       config=decode(tuple[str, ...], nd.get("config", []), "config"))
        unobserved = {str(k): _typed(str, v, f"unobserved {k}") for k, v in data["unobserved"].items()}
        return cls(nodes, unobserved)


# ---------------------------------------------------------------------------------------------------------
# Strict decoding of stored values
# ---------------------------------------------------------------------------------------------------------

def _typed(tp, value, where):
    if tp is bool:
        ok = isinstance(value, bool)
    elif tp is int:
        ok = isinstance(value, int) and not isinstance(value, bool)
    else:
        ok = isinstance(value, tp)
    if not ok:
        raise SnapshotError(f"{where}: expected {tp.__name__}, got {str(value)[:60]!r}")
    return value


def decode(tp, data, where: str):
    """A value of type `tp` from its JSON form. Every dataclass needs exactly its own field names."""
    if tp is type(None):
        if data is not None:
            raise SnapshotError(f"{where}: expected null, got {str(data)[:60]!r}")
        return None
    if tp in (str, int, bool):
        return _typed(tp, data, where)
    origin = typing.get_origin(tp)
    args = typing.get_args(tp)
    if origin in (typing.Union, types.UnionType):
        for a in args:
            try:
                return decode(a, data, where)
            except SnapshotError:
                continue
        raise SnapshotError(f"{where}: unexpected value {str(data)[:60]!r}")
    if origin is tuple:
        if not isinstance(data, list):
            raise SnapshotError(f"{where}: expected a list, got {str(data)[:60]!r}")
        if len(args) == 2 and args[1] is Ellipsis:
            return tuple(decode(args[0], x, where) for x in data)
        if len(data) != len(args):
            raise SnapshotError(f"{where}: expected {len(args)} values, got {len(data)}")
        return tuple(decode(a, x, where) for a, x in zip(args, data, strict=True))
    if is_dataclass(tp):
        if not isinstance(data, dict):
            raise SnapshotError(f"{where}: expected an object, got {str(data)[:60]!r}")
        names = [f.name for f in fields(tp) if f.init]
        derived = [f.name for f in fields(tp) if not f.init]     # computed by the class; checked when stored
        unknown = sorted(set(data) - set(names) - set(derived))
        missing = [n for n in names if n not in data]
        if unknown or missing:
            raise SnapshotError(f"{where}: {tp.__name__} has unknown field(s) {unknown} / missing field(s) {missing}")
        hints = typing.get_type_hints(tp)
        try:
            value = tp(**{n: decode(hints[n], data[n], f"{where}.{n}") for n in names})
        except TypeError as e:
            raise SnapshotError(f"{where}: {e}") from None
        for n in derived:
            if n in data and data[n] != getattr(value, n):
                raise SnapshotError(f"{where}: {n} is {data[n]!r}, but the other fields make it {getattr(value, n)!r}")
        return value
    raise SnapshotError(f"{where}: cannot decode type {tp!r}")   # pragma: no cover - a programming error
