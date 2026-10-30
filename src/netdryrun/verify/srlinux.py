"""SR Linux read side of the verify snapshot: strict parsers for the state we have captured, and the refusal for the rest.

What exists here are native readers (SR Linux's own names and shapes) for four captured outputs:
  info from state network-instance <ni> protocols bgp neighbor * | as json     -> parse_neighbors
  info from state network-instance <ni> route-table ipv4-unicast route * | as json -> parse_route_table
  info from state network-instance <ni> bgp-rib afi-safi ipv4-unicast ... route * | as json   -> parse_rib_paths
  info from state network-instance <ni> bgp-rib attr-sets attr-set <id> | as json -> parse_attr_set

Every JSON object has an allowlist of keys; a key it doesn't know is an error, because it may be an attribute the diff would
otherwise never compare. A required field that is missing, a value of the wrong type, a stale or pending-delete path, an enabled
address family or add-path mode verify does not snapshot, a link-local next hop (its interface is not captured), a route from
another network instance: all errors. Never a smaller snapshot, never a default.

`SrlCollector.collect()` does NOT build a Snapshot yet. Parts of the snapshot (next-hop group members, the Adj-RIB-In and Adj-RIB-Out
listings, the normalised running configuration, next-hop resolution) have no capture, and a snapshot built without them would
approve changes it cannot see. It refuses, naming every missing source (MISSING_SOURCES); `verify.run.classify_nodes` keeps
refusing SR Linux nodes. The captures to take, and the field-to-source table, are in docs/SRL-SNAPSHOT.md.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Callable

from .snapshot import (AsPath, SnapshotError, canon_community, canon_ip, canon_large_community, canon_prefix, canon_set,
                       prefix_afi)

_UINT32 = 0xFFFFFFFF

SESSION_STATES = ("idle", "connect", "active", "opensent", "openconfirm", "established")
SNAPSHOT_AFIS = ("ipv4-unicast",)
ROUTE_TYPES = ("local", "host", "static", "bgp", "aggregate", "isis", "ospf", "linux", "dhcp", "gribi", "arp-nd", "icmp",
               "ndk1", "ndk2", "bgp-evpn")
ORIGINS = ("igp", "egp", "incomplete")

# What has no capture yet. Each entry: the source, and why a snapshot cannot be built without it.
MISSING_SOURCES = {
    "next-hop-group members": "the route table names a next-hop-group id; its next-hop addresses, interfaces and weights are in "
                              "another listing that is not captured, so a RIB entry's next hops cannot be built",
    "adj-rib-in / adj-rib-out listings": "routes a peer sent and routes this node advertised are separate listings (and depend on "
                                         "soft-reconfiguration and add-path); without them 'peer sent P' and 'node advertised P' "
                                         "cannot be told from 'P is in the local RIB'",
    "next-hop resolution": "whether a BGP path's next hop is reachable and its IGP metric are not in the RIB path listing",
    "running configuration": "the normalised running config compared between before and after is not captured in a stable form",
    "other network instances and IPv6": "only the default network instance and IPv4 unicast are captured; a VRF or IPv6 session "
                                        "must not be silently left out of the snapshot",
    "locally originated AS path": "an empty AS path (a route this node originates) has not been captured, so its printed form is unknown",
}


# ---------------------------------------------------------------------------------------------------------
# Small strict readers
# ---------------------------------------------------------------------------------------------------------
def _load(text: object, what: str):
    if not isinstance(text, str) or not text.strip():
        raise SnapshotError(f"{what}: empty answer")
    try:
        return json.loads(text)
    except ValueError:
        raise SnapshotError(f"{what}: not JSON: {text[:60]!r}") from None


def _obj(value, what: str, allowed: set[str] | frozenset[str], required: tuple[str, ...] = ()) -> dict:
    if not isinstance(value, dict):
        raise SnapshotError(f"{what}: expected an object, got {type(value).__name__}")
    extra = sorted(set(value) - set(allowed))
    if extra:
        raise SnapshotError(f"{what}: unknown field {extra[0]!r} (it may be an attribute the diff would not compare)")
    for key in required:
        if key not in value:
            raise SnapshotError(f"{what}: missing {key!r}")
    return value


def _list_of(root: dict, key: str, what: str) -> list:
    """The row list of an answer: `{}` is the real empty answer; anything else must hold a list of objects."""
    if key not in root:
        if root:
            raise SnapshotError(f"{what}: unknown field {sorted(root)[0]!r}")
        return []
    rows = root[key]
    if not isinstance(rows, list) or not rows:
        raise SnapshotError(f"{what}: {key!r} is not a non-empty list")
    return rows


def _bool(value, what: str) -> bool:
    if not isinstance(value, bool):
        raise SnapshotError(f"{what}: not a boolean: {str(value)[:40]!r}")
    return value


def _int(value, what: str, top: int = _UINT32) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= top:
        raise SnapshotError(f"{what}: not an unsigned integer: {str(value)[:40]!r}")
    return value


def _str(value, what: str) -> str:
    if not isinstance(value, str) or not value:
        raise SnapshotError(f"{what}: not a non-empty string: {str(value)[:40]!r}")
    return value


def _asn(value, what: str) -> int:
    return _int(value, what)


def _prefix4(value, what: str) -> str:
    if not isinstance(value, str) or "/" not in value:
        raise SnapshotError(f"{what}: not a prefix with a mask: {str(value)[:40]!r}")
    p = canon_prefix(value, what)
    if prefix_afi(p) != "ipv4":
        raise SnapshotError(f"{what}: {p} is not IPv4 (IPv6 is not captured)")
    return p


# ---------------------------------------------------------------------------------------------------------
# BGP neighbors
# ---------------------------------------------------------------------------------------------------------
@dataclass(frozen=True)
class SrlSession:
    vrf: str
    peer: str
    state: str
    established: bool
    remote_as: int
    local_as: int
    local_address: str | None
    afis: tuple[str, ...]
    counters: dict[str, tuple[tuple[str, int], ...]] = field(hash=False)   # per AFI: (name, value) pairs; none is "accepted"


_NEIGHBOR_KEYS = frozenset({
    "peer-address", "admin-state", "under-maintenance", "maintenance-group", "peer-type", "local-preference", "next-hop-self",
    "peer-as", "peer-group", "route-flap-damping", "peer-router-id", "session-state", "last-state", "last-event",
    "last-established", "established-transitions", "export-policy", "import-policy", "advertised-capabilities",
    "received-capabilities", "received-afi-safi", "received-end-of-rib", "as-path-options", "authentication",
    "failure-detection", "graceful-restart", "multihop", "afi-safi", "local-as", "route-reflector", "send-default-route",
    "timers", "transport", "sent-messages", "received-messages", "description", "evpn", "ipv4-unicast", "ipv6-unicast",
})
_AFI_ENTRY_KEYS = frozenset({
    "afi-safi-name", "admin-state", "oper-state", "received-routes", "sent-routes", "active-routes", "rejected-routes",
    "suppressed-routes", "received-routes-withdrawn-due-to-error", "send-community-type", "add-paths", "graceful-restart",
    "ipv4-unicast", "ipv6-unicast",
})
_COUNTERS = ("received-routes", "sent-routes", "active-routes", "rejected-routes", "suppressed-routes")


def _afi_entries(neighbor: dict, where: str):
    entries = neighbor["afi-safi"]
    if not isinstance(entries, list) or not entries:
        raise SnapshotError(f"{where}: afi-safi is not a non-empty list")
    names: list[str] = []
    enabled: list[str] = []
    counters: dict[str, tuple[tuple[str, int], ...]] = {}
    for e in entries:
        _obj(e, f"{where} afi-safi", _AFI_ENTRY_KEYS, ("afi-safi-name", "admin-state"))
        name = _str(e["afi-safi-name"], f"{where} afi-safi name")
        if name in names:
            raise SnapshotError(f"{where}: address family {name} listed twice")
        names.append(name)
        admin = e["admin-state"]
        if admin not in ("enable", "disable"):
            raise SnapshotError(f"{where} {name}: admin-state {str(admin)[:30]!r} is neither enable nor disable")
        if admin == "disable":
            continue
        if name not in SNAPSHOT_AFIS:
            raise SnapshotError(f"{where}: address family {name} is enabled and verify does not snapshot it "
                                f"(only {', '.join(SNAPSHOT_AFIS)})")
        enabled.append(name)
        addp = e.get("add-paths")
        if addp is not None:
            _obj(addp, f"{where} {name} add-paths", {"receive", "send"}, ("receive", "send"))
            if _bool(addp["receive"], f"{where} add-paths receive") or _bool(addp["send"], f"{where} add-paths send"):
                raise SnapshotError(f"{where} {name}: add-path is enabled; the Adj-RIB listings it needs are not captured")
        if e.get("oper-state") == "up":
            counters[name] = tuple((k, _int(e.get(k), f"{where} {name} {k}")) for k in sorted(_COUNTERS))
        elif e.get("oper-state") not in ("down", "up"):
            raise SnapshotError(f"{where} {name}: oper-state {str(e.get('oper-state'))[:30]!r} is neither up nor down")
    return tuple(enabled), counters


def parse_neighbors(text: str, vrf: str) -> dict[str, SrlSession]:
    """BGP sessions of one network instance by peer address."""
    root = _obj(_load(text, "bgp neighbors"), "bgp neighbors", {"neighbor"})
    out: dict[str, SrlSession] = {}
    for n in _list_of(root, "neighbor", "bgp neighbors"):
        _obj(n, "bgp neighbor", _NEIGHBOR_KEYS, ("peer-address", "session-state", "afi-safi", "admin-state"))
        peer = canon_ip(n["peer-address"], "bgp neighbor peer-address")
        where = f"bgp neighbor {peer}"
        if peer in out:
            raise SnapshotError(f"{where}: listed twice")
        state = n["session-state"]
        if not isinstance(state, str) or state not in SESSION_STATES:
            raise SnapshotError(f"{where}: unknown session state {str(state)[:30]!r}")
        established = state == "established"
        if "peer-as" not in n:
            raise SnapshotError(f"{where}: missing 'peer-as'")
        local_as = n.get("local-as")
        if local_as is None:
            raise SnapshotError(f"{where}: missing 'local-as'")
        _obj(local_as, f"{where} local-as", {"as-number", "prepend-global-as", "prepend-local-as"}, ("as-number",))
        transport = n.get("transport")
        local_address = None
        if transport is not None:
            _obj(transport, f"{where} transport", {"mtu-discovery", "tcp-mss", "passive-mode", "local-address", "local-port",
                                                   "remote-port"})
            if "local-address" in transport:
                local_address = canon_ip(transport["local-address"], f"{where} local address")
        if established and local_address is None:
            raise SnapshotError(f"{where}: established without a local address")
        afis, counters = _afi_entries(n, where)
        out[peer] = SrlSession(vrf=vrf, peer=peer, state=state, established=established,
                               remote_as=_asn(n["peer-as"], f"{where} peer-as"),
                               local_as=_asn(local_as["as-number"], f"{where} local-as"),
                               local_address=local_address, afis=afis, counters=counters)
    return out


# ---------------------------------------------------------------------------------------------------------
# Route table
# ---------------------------------------------------------------------------------------------------------
@dataclass(frozen=True)
class SrlRoute:
    prefix: str
    route_type: str
    owner: str
    active: bool
    preference: int
    metric: int
    next_hop_group: str | None
    fib_programmed: bool


@dataclass(frozen=True)
class SrlRouteGroup:
    """All rows for one prefix and route type. Their facts are read only when there is one row; with more the answer is
    ambiguous and asking for it is an error."""
    entries: tuple[SrlRoute, ...]

    def _one(self) -> SrlRoute:
        if len(self.entries) != 1:
            raise SnapshotError(f"{self.entries[0].prefix}: {len(self.entries)} {self.entries[0].route_type} routes; ambiguous")
        return self.entries[0]

    owner = property(lambda self: self._one().owner)
    active = property(lambda self: self._one().active)
    preference = property(lambda self: self._one().preference)
    metric = property(lambda self: self._one().metric)
    next_hop_group = property(lambda self: self._one().next_hop_group)
    fib_programmed = property(lambda self: self._one().fib_programmed)


_ROUTE_KEYS = frozenset({
    "ipv4-prefix", "id", "route-type", "route-owner", "origin-network-instance", "leakable", "leaked", "metric", "preference",
    "active", "route-limit-exceeded", "last-app-update", "next-hop-group", "next-hop-group-network-instance",
    "resilient-hash", "dynamic-load-balancing", "fib-programming",
})
_FIB_KEYS = frozenset({"suppressed", "last-successful-operation-type", "last-successful-operation-timestamp",
                       "pending-operation-type", "last-failed-operation-type"})


def parse_route_table(text: str, vrf: str) -> dict[tuple[str, str], SrlRouteGroup]:
    root = _obj(_load(text, "route table"), "route table", {"route"})
    groups: dict[tuple[str, str], list[SrlRoute]] = {}
    for r in _list_of(root, "route", "route table"):
        _obj(r, "route", _ROUTE_KEYS, ("ipv4-prefix", "route-type", "route-owner", "active", "preference", "metric"))
        prefix = _prefix4(r["ipv4-prefix"], "route prefix")
        where = f"route {prefix}"
        ni = r.get("origin-network-instance", vrf)
        if ni != vrf:
            raise SnapshotError(f"{where}: from network instance {str(ni)[:30]!r}, not {vrf!r} (other network instances are not captured)")
        for flag in ("leaked", "leakable"):
            if flag in r:
                _bool(r[flag], f"{where} {flag}")
        if r.get("leaked"):
            raise SnapshotError(f"{where}: a leaked route; its origin network instance is not captured")
        rtype = r["route-type"]
        if not isinstance(rtype, str) or rtype not in ROUTE_TYPES:
            raise SnapshotError(f"{where}: unknown route type {str(rtype)[:30]!r}")
        active = _bool(r["active"], f"{where} active")
        fib = r.get("fib-programming")
        programmed = False
        if fib is not None:
            _obj(fib, f"{where} fib-programming", _FIB_KEYS)
            programmed = (active and fib.get("suppressed") is False and fib.get("pending-operation-type") == "none"
                          and fib.get("last-failed-operation-type") == "none" and "last-successful-operation-type" in fib)
        nhg = r.get("next-hop-group")
        route = SrlRoute(prefix=prefix, route_type=rtype, owner=_str(r["route-owner"], f"{where} owner"), active=active,
                         preference=_int(r["preference"], f"{where} preference"), metric=_int(r["metric"], f"{where} metric"),
                         next_hop_group=None if nhg is None else _str(nhg, f"{where} next-hop-group"),
                         fib_programmed=programmed)
        groups.setdefault((prefix, rtype), []).append(route)
    return {k: SrlRouteGroup(tuple(v)) for k, v in groups.items()}


# ---------------------------------------------------------------------------------------------------------
# BGP RIB paths
# ---------------------------------------------------------------------------------------------------------
@dataclass(frozen=True)
class SrlPath:
    prefix: str
    source: str                 # the peer address, or "local" for a path this node originated
    protocol: str
    received: bool
    path_id: int
    used: bool
    valid: bool
    best: bool
    backup: bool
    attr_id: str


_RIB_KEYS = frozenset({
    "prefix", "neighbor", "origin-protocol", "path-id", "last-modified", "used-route", "unused-weight-only", "valid-route",
    "best-route", "backup-route", "stale-route", "fib-disabled", "pending-delete", "neighbor-as", "group-best",
    "tie-break-reason", "attr-id",
})
_RIB_REQUIRED = ("prefix", "neighbor", "origin-protocol", "path-id", "used-route", "valid-route", "best-route", "backup-route",
                 "stale-route", "pending-delete", "attr-id")


def parse_rib_paths(text: str, vrf: str, afi: str) -> dict[tuple, SrlPath]:
    """Local-RIB paths keyed (vrf, afi, source, path id, prefix)."""
    if afi != "ipv4":
        raise SnapshotError(f"bgp rib: address family {afi!r} is not captured")
    root = _obj(_load(text, "bgp rib"), "bgp rib", {"route"})
    out: dict[tuple, SrlPath] = {}
    for r in _list_of(root, "route", "bgp rib"):
        _obj(r, "bgp rib path", _RIB_KEYS, _RIB_REQUIRED)
        prefix = _prefix4(r["prefix"], "bgp rib prefix")
        where = f"bgp rib {prefix}"
        if _bool(r["stale-route"], f"{where} stale-route"):
            raise SnapshotError(f"{where}: a stale path (graceful restart): not settled, it proves neither presence nor absence")
        if _bool(r["pending-delete"], f"{where} pending-delete"):
            raise SnapshotError(f"{where}: a path pending delete: not settled")
        proto = _str(r["origin-protocol"], f"{where} origin-protocol")
        neighbor = canon_ip(r["neighbor"], f"{where} neighbor")
        if neighbor in ("0.0.0.0", "::"):
            source, received = "local", False
        elif proto == "bgp":
            source, received = neighbor, True
        else:
            raise SnapshotError(f"{where}: protocol {proto!r} with a peer address {neighbor}")
        path = SrlPath(prefix=prefix, source=source, protocol=proto, received=received,
                       path_id=_int(r["path-id"], f"{where} path-id"), used=_bool(r["used-route"], f"{where} used-route"),
                       valid=_bool(r["valid-route"], f"{where} valid-route"), best=_bool(r["best-route"], f"{where} best-route"),
                       backup=_bool(r["backup-route"], f"{where} backup-route"), attr_id=_str(r["attr-id"], f"{where} attr-id"))
        key = (vrf, afi, source, path.path_id, prefix)
        if key in out:
            raise SnapshotError(f"{where}: path {source} id {path.path_id} listed twice")
        out[key] = path
    return out


# ---------------------------------------------------------------------------------------------------------
# Attribute sets
# ---------------------------------------------------------------------------------------------------------
@dataclass(frozen=True)
class SrlAttrs:
    index: str
    origin: str
    next_hop: str
    med: int | None             # an omitted attribute is unknown (None), never 0 or a default
    local_pref: int | None
    atomic_aggregate: bool
    as_path: AsPath
    communities: tuple[str, ...]
    large_communities: tuple[str, ...]


_ATTR_KEYS = frozenset({"index", "origin", "atomic-aggregate", "next-hop", "med", "local-pref", "as-path", "communities"})


def parse_attr_set(text: str) -> SrlAttrs:
    a = _obj(_load(text, "attribute set"), "attribute set", _ATTR_KEYS, ("index", "origin", "next-hop", "as-path"))
    where = f"attribute set {str(a['index'])[:20]}"
    origin = a["origin"]
    if not isinstance(origin, str) or origin not in ORIGINS:
        raise SnapshotError(f"{where}: unknown origin {str(origin)[:20]!r}")
    nh = canon_ip(a["next-hop"], f"{where} next-hop")
    if nh.lower().startswith("fe80:"):
        raise SnapshotError(f"{where}: link-local next hop {nh}: its interface is not captured")
    asp = _obj(a["as-path"], f"{where} as-path", {"segment"})
    segs = asp.get("segment")
    if not isinstance(segs, list) or not segs:
        raise SnapshotError(f"{where}: an AS path with no segments (a locally originated route) is not captured")
    parsed = []
    for seg in segs:
        _obj(seg, f"{where} as-path segment", {"as-path-index", "type", "member"}, ("type", "member"))
        members = seg["member"]
        if not isinstance(members, list) or not members:
            raise SnapshotError(f"{where}: empty AS path segment")
        parsed.append((seg["type"], [_asn(m, f"{where} AS path member") for m in members]))
    try:
        path = AsPath.build(parsed)
    except SnapshotError:
        raise
    comm = a.get("communities", {})
    _obj(comm, f"{where} communities", {"community", "large-community"})

    def tokens(key: str) -> list:
        v = comm.get(key, [])
        if not isinstance(v, list):
            raise SnapshotError(f"{where}: {key} is not a list")
        return v
    return SrlAttrs(
        index=_str(a["index"], f"{where} index"), origin=origin, next_hop=nh,
        med=None if "med" not in a else _int(a["med"], f"{where} med"),
        local_pref=None if "local-pref" not in a else _int(a["local-pref"], f"{where} local-pref"),
        atomic_aggregate=_bool(a.get("atomic-aggregate", False), f"{where} atomic-aggregate"), as_path=path,
        communities=canon_set([canon_community(c) for c in tokens("community")]),
        large_communities=canon_set([canon_large_community(c) for c in tokens("large-community")]))


# ---------------------------------------------------------------------------------------------------------
# Collector: refuses until every source is captured
# ---------------------------------------------------------------------------------------------------------
class SrlCollector:
    def __init__(self, node: str, run: Callable[[str, list[str]], tuple[int, str, str]]):
        self.node = node
        self.run = run

    def collect(self):
        """No Snapshot yet: refuse, and run nothing, so a node is never passed on a partial read."""
        missing = "; ".join(f"{k} ({v})" for k, v in MISSING_SOURCES.items())
        raise SnapshotError(f"{self.node}: SR Linux cannot be snapshotted yet; not captured: {missing}")
