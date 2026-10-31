"""FRR collection of the verify snapshot, from vtysh JSON.

Commands (per node):
  show vrf
  show bgp vrf all neighbors json
  show ip route vrf all json                       show ipv6 route vrf all json
  show bgp vrf all ipv4 unicast detail json        show bgp vrf all ipv6 unicast detail json
  show bgp [vrf V] <afi> unicast neighbors N advertised-routes detail json   (every established session)
  show bgp [vrf V] <afi> unicast neighbors N received-routes json            (sessions with soft-reconfiguration inbound)

Received routes come from the plain listing: FRR 10.4.1's `received-routes detail json` prints the path in the BGP
table, after inbound policy, for every prefix the table has (found on the first live capture), so it is not what
the neighbor sent. The plain listing is, but it carries no communities: a received route's communities before
inbound policy are not in the snapshot, and a `with:` pin on them never matches a received-only route.

Validation is strict, and stricter than the check drivers: each JSON object the parser reads has an
allowlist of keys. A key it doesn't know is an error, because it may be an attribute the diff would
otherwise never compare (a change in it would pass unseen). Keys known to be noise (uptimes, versions,
internal flags, interface indexes) are listed and dropped. Required fields that are missing, VRFs that are
in one output and not another, an address family or protocol verify doesn't snapshot, and unnumbered
(interface) BGP neighbors are all errors too: never a smaller snapshot.

The neighbor objects are the one exception: they carry about a hundred timers, counters and capability
flags, so only their required fields and their address-family map are validated.
"""
from __future__ import annotations

import ipaddress
import json
import re
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import replace

from ..drivers.base import DriverError, check_vrf_name, load_json
from ..drivers.frr import parse_vrfs
from .snapshot import (PATH_FLAGS, AsPath, BgpAttrs, BgpPath, ItemKey, NextHop, NodeSnapshot, PathNextHop,
                       RibEntry, Session, SnapshotError, canon_community, canon_ext_communities, canon_ip,
                       canon_large_community, canon_prefix, canon_set, parse_asn, prefix_afi)

VRF_CMD = "show vrf"
NEIGHBORS_CMD = "show bgp vrf all neighbors json"
ROUTE_CMDS = {"ipv4": "show ip route vrf all json", "ipv6": "show ipv6 route vrf all json"}
BGP_CMDS = {"ipv4": "show bgp vrf all ipv4 unicast detail json", "ipv6": "show bgp vrf all ipv6 unicast detail json"}
CONFIG_CMD = "show running-config"

# FRR's address-family keys: the ones verify snapshots, and the ones it knows but refuses (a session that
# carries one of them would have routes verify can't see)
AF_KEYS = {"ipv4Unicast": "ipv4-unicast", "ipv6Unicast": "ipv6-unicast"}
AF_UNSUPPORTED = {"ipv4Multicast", "ipv6Multicast", "ipv4LabeledUnicast", "ipv6LabeledUnicast", "ipv4Vpn", "ipv6Vpn",
                  "ipv4Encap", "ipv6Encap", "ipv4Flowspec", "ipv6Flowspec", "l2VpnEvpn", "ipv4Mvpn", "ipv6Mvpn",
                  "linkstate"}

# zebra protocol names (route_types.txt, ZEBRA_ROUTE_*), as `show ip route json` prints them
PROTOCOLS = frozenset({"system", "kernel", "connected", "local", "static", "rip", "ripng", "ospf", "ospf6", "isis",
                       "bgp", "pim", "eigrp", "nhrp", "hsls", "olsr", "table", "ldp", "vnc", "vnc-direct",
                       "vnc-rn", "bgp-direct", "bgp-direct-to-nve-groups", "babel", "sharp", "pbr", "bfd",
                       "openfabric", "vrrp", "nhg", "srte", "table-direct", "frr"})

# --- key allowlists --------------------------------------------------------------------------------------
ROUTE_KEYS = {"prefix", "prefixLen", "protocol", "instance", "vrfId", "vrfName", "selected", "destSelected",
              "distance", "metric", "installed", "tag", "table", "failed", "queued", "offloaded", "offloadFailed",
              "trapped", "internalStatus", "internalFlags", "internalNextHopNum", "internalNextHopActiveNum",
              "nexthopGroupId", "installedNexthopGroupId", "receivedNexthopGroupId", "uptime"}
ROUTE_REQUIRED = {"prefix", "protocol", "distance", "metric", "nexthops"}
NEXTHOP_KEYS = {"flags", "fib", "ip", "afi", "interfaceIndex", "interfaceName", "active", "weight", "directlyConnected",
                "onLink", "duplicate", "recursive", "resolver", "unreachable", "reject", "admin-prohibited",
                "blackhole", "vrf", "labels", "src", "rmapSource"}
BGP_VRF_KEYS = {"vrfId", "vrfName", "tableVersion", "routerId", "defaultLocPrf", "localAS", "routes", "totalRoutes",
                "totalPaths"}
DEST_KEYS = {"prefix", "version", "advertisedTo", "pathCount", "multiPathCount", "paths"}
PATH_KEYS = {"aspath", "origin", "metric", "locPrf", "weight", "valid", "version", "bestpath", "multipath",
             "community", "extendedCommunity", "largeCommunity", "lastUpdate", "nexthops", "peer", "sourced", "local",
             "atomicAggregate", "aggregatorAs", "aggregatorId", "originatorId", "clusterList", "addpathRxId",
             "addpathTxId", "otc", "aigpMetric", "remoteLabel", "remoteSid", "rpkiValidationState", *PATH_FLAGS,
             "processScheduled"}   # transient: the destination is queued for best-path selection (not compared)
PATH_EXTRA = ("aigpMetric", "otc", "remoteLabel", "remoteSid", "rpkiValidationState")
PATH_NEXTHOP_KEYS = {"ip", "hostname", "afi", "scope", "linkLocalOnly", "length", "metric", "accessible", "used",
                     "interface",
                     "importCheckEnabled"}   # how bgpd tracks the next hop; its outcome is `accessible` (compared)
PEER_KEYS = {"peerId", "routerId", "hostname", "domainname", "type", "interface"}
BESTPATH_KEYS = {"overall", "bestpathFromAs", "selectionReason"}
ADJ_KEYS = {"bgpTableVersion", "bgpLocalRouterId", "defaultLocPrf", "localAS", "advertisedRoutes", "receivedRoutes",
            "totalPrefixCounter", "filteredPrefixCounter", "bgpOriginatingDefaultNetwork"}
# A default route sent by `neighbor X default-originate`: FRR names it beside the advertised routes
# (bgpOriginatingDefaultNetwork), without its attributes, so it is one adj_out item with these fixed values: its
# appearance and disappearance are differences, a change made by its route-map is not seen.
DEFAULT_ORIGINATE = BgpAttrs(origin="igp", as_path=AsPath(()), next_hops=(), local_pref=None, med=None, weight=None,
                             communities=(), ext_communities=(), large_communities=(), cluster_list=(),
                             originator_id=None, atomic_aggregate=False, aggregator=None,
                             extra=(("default-originate", "true"),))
# one route of the plain received-routes listing (FRR's route_vty_out_tmp); IPv6 prints its next hop as nextHopGlobal
RECEIVED_KEYS = {"addrPrefix", "prefixLen", "network", "nextHop", "nextHopGlobal", "metric", "locPrf", "weight", "path",
                 "origin", "valid", "best"}
ORIGIN_NAMES = {"igp": "igp", "i": "igp", "egp": "egp", "e": "egp", "incomplete": "incomplete", "?": "incomplete"}
PEER_TYPES = {"external", "internal", "confed-external", "confed-internal"}


# Facts of the boot, not of the configs (two boots of one lab with the same configs differed in both, live):
# - Docker gives each node its management address on eth0 per boot, so the `local` (host) routes of eth0 in the
#   default VRF are not part of the snapshot; the management subnet and kernel routes still are.
# - containerlab gives interfaces random MAC addresses, so an IPv6 link-local next hop is named by the lab node and
#   interface that own it (`fe80::%peer1:eth1`, the same on every boot); one no lab node owns, or two nodes share,
#   keeps its address (gauntlet 0.4, R1: a link-local next hop set in config is configuration, and a typo in it
#   must show). Without the lab's addresses (parsing a fixture) it is `fe80::`. The raw output keeps the address.
# - Every interface has a connected fe80::/64, and which one zebra marks selected follows interface creation order:
#   those entries are compared by interface and FIB state, not by the selected flag.
MGMT_INTERFACE = "eth0"
LINK_LOCAL = "fe80::"
LINK_LOCAL_SUBNET = "fe80::/64"


_LL_OWNERS: ContextVar[tuple[dict[str, str], frozenset] | None] = ContextVar("link_local_owners", default=None)
_LL_TOKEN = re.compile(r"(?<![0-9A-Fa-f:])[Ff][Ee]80:[0-9A-Fa-f:]*")
_LL_IFACE = re.compile(r"^\d+:\s+([^:@\s]+)(?:@\S+)?:", re.M)


def parse_link_local(text: str, node: str) -> dict[str, str]:
    """`ip -6 addr show scope link` in a node: link-local address -> "node:interface"."""
    out: dict[str, str] = {}
    iface = None
    for line in text.splitlines():
        m = _LL_IFACE.match(line)
        if m:
            iface = m.group(1)
            continue
        parts = line.split()
        if iface and len(parts) >= 2 and parts[0] == "inet6":
            addr = parts[1].split("/")[0]
            try:
                if ipaddress.ip_address(addr).is_link_local:
                    a = str(ipaddress.ip_address(addr))
                    # one address on two interfaces of the node: which one is meant depends on the link
                    out[a] = "" if a in out and out[a] != f"{node}:{iface}" else f"{node}:{iface}"
            except ValueError:
                continue
    return out


def link_local_names(per_node: dict[str, dict[str, str]]) -> dict[str, str]:
    """Each link-local address exactly one lab interface owns -> its name; an address two interfaces share is
    left out (which one a next hop means depends on the link), so it is kept as written."""
    seen: dict[str, list[str]] = {}
    for owners in per_node.values():
        for addr, owner in owners.items():
            seen.setdefault(addr, []).append(owner)
    return {addr: f"{LINK_LOCAL}%{o[0]}" for addr, o in seen.items() if len(o) == 1 and o[0]}


def configured_link_locals(lines: tuple[str, ...]) -> frozenset:
    """The link-local addresses a node's running config names (a route-map's next hop, a static route)."""
    out = set()
    for ln in lines:
        for tok in _LL_TOKEN.findall(ln):
            try:
                out.add(str(ipaddress.ip_address(tok.rstrip(":"))))
            except ValueError:
                continue
    return frozenset(out)


@contextmanager
def link_local_owners(names: dict[str, str] | None, configured: frozenset | set = frozenset()):
    token = _LL_OWNERS.set(None if names is None else (names, frozenset(configured)))
    try:
        yield
    finally:
        _LL_OWNERS.reset(token)


def _boot_free(ip: str) -> str:
    a = ipaddress.ip_address(ip.split("%")[0])
    if a.version != 6 or not a.is_link_local:
        return ip
    ctx = _LL_OWNERS.get()
    if ctx is None:
        return LINK_LOCAL
    names, configured = ctx
    if str(a) in names:
        return names[str(a)]
    # one the config names (a typo shows); any other is a neighbour's random per-boot address whose interface
    # verify couldn't read (an SR Linux namespace): compared as fe80:: as before (cold review 6)
    return str(a) if str(a) in configured else LINK_LOCAL


def _mgmt_address(vrf: str, entry: RibEntry) -> bool:
    return (vrf == "default" and entry.protocol == "local" and bool(entry.nexthops)
            and all(h.interface == MGMT_INTERFACE and h.ip is None for h in entry.nexthops))


class CommandFailed(SnapshotError):
    """A vtysh command that failed to run (bgpd still starting, a daemon not up): the convergence loop
    retries these until its timeout; every other SnapshotError stops at once."""


class CommandTimedOut(CommandFailed):
    """A vtysh command that hit its time limit (exit code 124 from the exec): its output was cut. Retried like
    any failed command; if it never finishes, the snapshot is incomplete and the verdict is INCONCLUSIVE naming
    the command (no route ceiling: a snapshot is complete or it approves nothing)."""


TIMED_OUT = 124


def _bad(command: str, what: str) -> SnapshotError:
    return SnapshotError(f"unexpected output from `{command}`: {' '.join(str(what).split())[:240]}")


def _obj(command: str, value, where: str, keys: set, required: set = frozenset()) -> dict:
    if not isinstance(value, dict):
        raise _bad(command, f"{where}: expected an object, got {str(value)[:80]}")
    unknown = sorted(set(value) - keys - required)
    if unknown:
        raise _bad(command, f"{where}: unknown field(s) {unknown}; verify reads only fields it knows, so a new "
                            "field is an error until it is classified")
    missing = sorted(required - set(value))
    if missing:
        raise _bad(command, f"{where}: missing field(s) {missing}")
    return value


def _int(command: str, value, where: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise _bad(command, f"{where}: not an integer: {str(value)[:60]!r}")
    return value


def _opt_int(command: str, obj: dict, key: str, where: str) -> int | None:
    return _int(command, obj[key], f"{where}.{key}") if key in obj else None


def _flag(command: str, obj: dict, key: str, where: str) -> bool:
    """FRR prints boolean flags only when true; when present the value must be a boolean."""
    if key not in obj:
        return False
    if not isinstance(obj[key], bool):
        raise _bad(command, f"{where}.{key}: not a boolean: {str(obj[key])[:40]!r}")
    return obj[key]


def _str(command: str, value, where: str) -> str:
    if not isinstance(value, str) or not value:
        raise _bad(command, f"{where}: not a non-empty string: {str(value)[:60]!r}")
    return value


def _vrf(command: str, name, where: str = "VRF") -> str:
    try:
        return check_vrf_name(name)
    except DriverError:
        raise _bad(command, f"{where}: not a VRF name: {str(name)[:60]!r}") from None


def _json(command: str, text: str):
    try:
        data = load_json(command, text)
    except DriverError as e:
        raise SnapshotError(str(e)) from None
    if isinstance(data, dict) and "warning" in data:
        raise _bad(command, f"vtysh warning: {data['warning']}")
    return data


# ---------------------------------------------------------------------------------------------------------
# show bgp vrf all neighbors json
# ---------------------------------------------------------------------------------------------------------

def parse_neighbors(text: str) -> dict[str, dict[str, Session]]:
    """{vrf: {neighbor: Session}}. `{}` is a router without BGP. Every BGP instance is listed, with
    `vrfId`/`vrfName` next to its neighbors."""
    cmd = NEIGHBORS_CMD
    data = _json(cmd, text)
    if not isinstance(data, dict):
        raise _bad(cmd, text)
    out: dict[str, dict[str, Session]] = {}
    for vrf, inst in data.items():
        vrf = _vrf(cmd, vrf)
        if not isinstance(inst, dict):
            raise _bad(cmd, f"{vrf}: expected an object")
        if "vrfName" in inst and inst["vrfName"] != vrf:
            raise _bad(cmd, f"{vrf}: vrfName is {inst['vrfName']!r}")
        sessions = {}
        for key, nb in inst.items():
            if key in ("vrfId", "vrfName"):
                continue
            where = f"{vrf} neighbor {key}"
            try:
                addr = canon_ip(key)
            except SnapshotError:
                raise _bad(cmd, f"{where}: verify 0.4 compares sessions by neighbor IP address; unnumbered (interface) "
                                "and peer-group keys are not supported yet") from None
            if not isinstance(nb, dict):
                raise _bad(cmd, f"{where}: expected an object")
            for req in ("bgpState", "remoteAs", "localAs"):
                if req not in nb:
                    raise _bad(cmd, f"{where}: missing field {req!r}")
            state = _str(cmd, nb["bgpState"], f"{where}.bgpState").split()[0].lower()
            remote_as = parse_asn(nb["remoteAs"], f"{where}.remoteAs")
            local_as = parse_asn(nb["localAs"], f"{where}.localAs")
            fams = nb.get("addressFamilyInfo", {} if state != "established" else None)
            if not isinstance(fams, dict):
                raise _bad(cmd, f"{where}: an established session lists its address families (addressFamilyInfo)")
            afis, counts, soft = [], [], []
            for af, info in fams.items():
                if af in AF_UNSUPPORTED:
                    raise _bad(cmd, f"{where}: address family {af} is not snapshotted by verify 0.4 (IPv4 and IPv6 "
                                    "unicast only); its routes would go unseen")
                if af not in AF_KEYS:
                    raise _bad(cmd, f"{where}: unknown address family {af!r}")
                if not isinstance(info, dict) or "acceptedPrefixCounter" not in info:
                    raise _bad(cmd, f"{where} {af}: no acceptedPrefixCounter")
                name = AF_KEYS[af]
                afis.append(name)
                counts.append((name, _int(cmd, info["acceptedPrefixCounter"], f"{where} {af}.acceptedPrefixCounter")))
                if _flag(cmd, info, "inboundSoftConfigPermit", f"{where} {af}"):
                    soft.append(name)
                    if _add_path_rx(nb, af):
                        raise _bad(cmd, f"{where} {af}: the neighbor may send several paths per prefix (add-path), and "
                                        "verify 0.4 reads received routes from a listing with one path per prefix")
            local = None
            if state == "established":
                if "hostLocal" not in nb:
                    raise _bad(cmd, f"{where}: an established session names its local address (hostLocal)")
                local = canon_ip(nb["hostLocal"], f"{where}.hostLocal")
            sessions[addr] = Session(state, remote_as, local_as, tuple(sorted(afis)), local,
                                     tuple(sorted(counts)), tuple(sorted(soft)))
        out[vrf] = sessions
    return out


def sent_counters(text: str) -> dict[tuple[str, str, str], int]:
    """(vrf, neighbor, afi-safi) -> sentPrefixCounter, where the neighbor output gives one (an empty advertised
    listing is checked against it)."""
    out = {}
    for vrf, inst in _json(NEIGHBORS_CMD, text).items():
        for key, nb in inst.items() if isinstance(inst, dict) else ():
            fams = nb.get("addressFamilyInfo") if isinstance(nb, dict) else None
            for af, info in (fams or {}).items():
                n = info.get("sentPrefixCounter") if isinstance(info, dict) else None
                if af in AF_KEYS and isinstance(n, int) and not isinstance(n, bool):
                    out[(vrf, canon_ip(key), AF_KEYS[af])] = n
    return out


def adv_intervals(text: str) -> dict[tuple[str, str], float]:
    """(vrf, neighbor) -> the advertisement interval bgpd applies to it (minBtwnAdvertisementRunsTimerMsecs), in
    seconds. A timer for the stability loop, never part of the snapshot's items."""
    out = {}
    for vrf, inst in _json(NEIGHBORS_CMD, text).items():
        for key, nb in inst.items() if isinstance(inst, dict) else ():
            ms = nb.get("minBtwnAdvertisementRunsTimerMsecs") if isinstance(nb, dict) else None
            if isinstance(ms, int) and not isinstance(ms, bool):
                out[(vrf, key)] = ms / 1000
    return out


def _add_path_rx(nb: dict, af: str) -> bool:
    """The neighbor said it may send this node several paths per prefix (its add-path TX capability)."""
    caps = nb.get("neighborCapabilities", {})
    ap = caps.get("addPath", {}) if isinstance(caps, dict) else {}
    info = ap.get(af, {}) if isinstance(ap, dict) else {}
    return isinstance(info, dict) and any(info.get(k) for k in ("txReceived", "txAdvertisedAndReceived"))


# ---------------------------------------------------------------------------------------------------------
# show ip[v6] route vrf all json
# ---------------------------------------------------------------------------------------------------------

def _nexthop(cmd: str, nh, where: str, resolvers: tuple = ()) -> NextHop:
    _obj(cmd, nh, where, NEXTHOP_KEYS)
    if "blackhole" in nh or "reject" in nh or "admin-prohibited" in nh or "unreachable" in nh:
        kind = ("blackhole" if _flag(cmd, nh, "blackhole", where) else
                "reject" if _flag(cmd, nh, "reject", where) or _flag(cmd, nh, "admin-prohibited", where) else
                "unreachable" if _flag(cmd, nh, "unreachable", where) else None)
        if kind is None:
            raise _bad(cmd, f"{where}: unreadable next-hop type")
    elif "ip" in nh:
        kind = "gateway"
    elif "interfaceName" in nh:
        kind = "interface"
    else:
        raise _bad(cmd, f"{where}: a next hop with neither an address nor an interface")
    labels = nh.get("labels", [])
    if not isinstance(labels, list):
        raise _bad(cmd, f"{where}.labels: not a list")
    src = nh.get("src", nh.get("rmapSource"))
    return NextHop(
        ip=_boot_free(canon_ip(nh["ip"], f"{where}.ip")) if "ip" in nh else None,
        interface=_str(cmd, nh["interfaceName"], f"{where}.interfaceName") if "interfaceName" in nh else None,
        vrf=_str(cmd, nh["vrf"], f"{where}.vrf") if "vrf" in nh else None,
        active=_flag(cmd, nh, "active", where), fib=_flag(cmd, nh, "fib", where),
        directly_connected=_flag(cmd, nh, "directlyConnected", where), on_link=_flag(cmd, nh, "onLink", where),
        recursive=_flag(cmd, nh, "recursive", where), duplicate=_flag(cmd, nh, "duplicate", where), kind=kind,
        weight=_opt_int(cmd, nh, "weight", where),
        labels=tuple(_int(cmd, x, f"{where}.labels") for x in labels),
        src=canon_ip(src, f"{where}.src") if src is not None else None,
        resolved_via=canon_set(resolvers))


def _nexthops(cmd: str, hops, where: str) -> tuple[NextHop, ...]:
    """zebra lists a recursive next hop followed by the next hops that resolve it ("resolver": true);
    each resolver stays attached to its recursive next hop."""
    if not isinstance(hops, list):
        raise _bad(cmd, f"{where}.nexthops: not a list")
    groups: list[tuple[dict, list[dict]]] = []
    for i, nh in enumerate(hops):
        if not isinstance(nh, dict):
            raise _bad(cmd, f"{where}.nexthops[{i}]: not an object")
        if _flag(cmd, nh, "resolver", f"{where}.nexthops[{i}]"):
            if not groups or not _flag(cmd, groups[-1][0], "recursive", where):
                raise _bad(cmd, f"{where}.nexthops[{i}]: a resolver without a recursive next hop before it")
            groups[-1][1].append({k: v for k, v in nh.items() if k != "resolver"})
        else:
            groups.append((nh, []))
    out = []
    for j, (nh, res) in enumerate(groups):
        resolvers = tuple(_nexthop(cmd, r, f"{where}.nexthops[{j}] resolver") for r in res)
        out.append(_nexthop(cmd, nh, f"{where}.nexthops[{j}]", resolvers))
    return canon_set(out)


def parse_routes(text: str, afi: str) -> dict[str, dict[tuple[str, str], tuple[RibEntry, ...]]]:
    """{vrf: {(prefix, protocol): entries}}."""
    cmd = ROUTE_CMDS[afi]
    data = _json(cmd, text)
    if not isinstance(data, dict):
        raise _bad(cmd, text)
    out: dict[str, dict[tuple[str, str], tuple[RibEntry, ...]]] = {}
    for vrf, table in data.items():
        vrf = _vrf(cmd, vrf)
        if not isinstance(table, dict):
            raise _bad(cmd, f"{vrf}: expected an object of prefixes")
        grouped: dict[tuple[str, str], list[RibEntry]] = {}
        for key, entries in table.items():
            prefix = canon_prefix(key, f"{cmd}: {vrf}")
            if prefix_afi(prefix) != afi:
                raise _bad(cmd, f"{vrf}: {prefix} in the {afi} table")
            if not isinstance(entries, list) or not entries:
                raise _bad(cmd, f"{vrf} {prefix}: expected a non-empty list of entries")
            for i, e in enumerate(entries):
                where = f"{vrf} {prefix}[{i}]"
                _obj(cmd, e, where, ROUTE_KEYS | {"nexthops"}, ROUTE_REQUIRED)
                if canon_prefix(e["prefix"], where) != prefix:
                    raise _bad(cmd, f"{where}: entry for {e['prefix']}")
                if "vrfName" in e and e["vrfName"] != vrf:
                    raise _bad(cmd, f"{where}: vrfName is {e['vrfName']!r}")
                proto = _str(cmd, e["protocol"], f"{where}.protocol").lower()
                if proto not in PROTOCOLS:
                    raise _bad(cmd, f"{where}: unknown protocol {proto!r}")
                entry = RibEntry(protocol=proto, instance=_opt_int(cmd, e, "instance", where),
                                 selected=_flag(cmd, e, "selected", where), fib=_flag(cmd, e, "installed", where),
                                 distance=_int(cmd, e["distance"], f"{where}.distance"),
                                 metric=_int(cmd, e["metric"], f"{where}.metric"),
                                 tag=_opt_int(cmd, e, "tag", where), table=_opt_int(cmd, e, "table", where),
                                 failed=_flag(cmd, e, "failed", where), nexthops=_nexthops(cmd, e["nexthops"], where))
                if _mgmt_address(vrf, entry):
                    continue
                if prefix == LINK_LOCAL_SUBNET and proto == "connected":
                    entry = replace(entry, selected=False)
                grouped.setdefault((prefix, proto), []).append(entry)
        out[vrf] = {k: canon_set(v) for k, v in grouped.items()}
    return out


# ---------------------------------------------------------------------------------------------------------
# BGP paths: show bgp vrf all <afi> unicast detail json, and the adj-RIB commands (same path objects)
# ---------------------------------------------------------------------------------------------------------

def _communities(cmd: str, p: dict, key: str, where: str) -> str:
    if key not in p:
        return ""
    obj = p[key]
    if not isinstance(obj, dict) or not isinstance(obj.get("string"), str) or set(obj) - {"string", "list"}:
        raise _bad(cmd, f"{where}.{key}: expected an object with a string")
    return obj["string"]


def parse_attrs(cmd: str, p, where: str) -> tuple[str, int, BgpAttrs, dict]:
    """(source, add-path rx ID, attributes, the raw path object) from one FRR path object."""
    _obj(cmd, p, where, PATH_KEYS, {"aspath", "origin", "nexthops", "peer"})
    asp = p["aspath"]
    if not isinstance(asp, dict) or not isinstance(asp.get("segments"), list) or set(asp) - {"string", "segments", "length"}:
        raise _bad(cmd, f"{where}.aspath: expected an object with segments")
    segs = []
    for s in asp["segments"]:
        if not isinstance(s, dict) or set(s) != {"type", "list"} or not isinstance(s["list"], list):
            raise _bad(cmd, f"{where}.aspath: bad segment {str(s)[:80]}")
        segs.append((s["type"], s["list"]))
    origin = ORIGIN_NAMES.get(str(p["origin"]).strip().lower()) if isinstance(p["origin"], str) else None
    if origin is None:
        raise _bad(cmd, f"{where}.origin: unknown origin {str(p['origin'])[:30]!r}")
    if not isinstance(p["nexthops"], list) or not p["nexthops"]:
        raise _bad(cmd, f"{where}.nexthops: expected a non-empty list")
    hops = []
    for i, nh in enumerate(p["nexthops"]):
        w = f"{where}.nexthops[{i}]"
        _obj(cmd, nh, w, PATH_NEXTHOP_KEYS, {"ip"})
        scope = nh.get("scope", "global")
        if scope not in ("global", "link-local"):
            raise _bad(cmd, f"{w}.scope: unknown scope {scope!r}")
        hops.append(PathNextHop(ip=_boot_free(canon_ip(nh["ip"], f"{w}.ip")), scope=scope,
                                accessible=_flag(cmd, nh, "accessible", w), used=_flag(cmd, nh, "used", w),
                                igp_metric=_opt_int(cmd, nh, "metric", w),
                                interface=_str(cmd, nh["interface"], f"{w}.interface") if "interface" in nh else None))
    peer = _obj(cmd, p["peer"], f"{where}.peer", PEER_KEYS, {"peerId"})
    try:
        comms = tuple(sorted({canon_community(t) for t in _communities(cmd, p, "community", where).split()}))
        large = tuple(sorted({canon_large_community(t) for t in _communities(cmd, p, "largeCommunity", where).split()}))
        ext = canon_ext_communities(_communities(cmd, p, "extendedCommunity", where))
    except SnapshotError as e:
        raise _bad(cmd, f"{where}: {e}") from None
    cluster = ()
    if "clusterList" in p:
        cl = p["clusterList"]
        if not isinstance(cl, dict) or set(cl) != {"list"} or not isinstance(cl["list"], list):
            raise _bad(cmd, f"{where}.clusterList: expected an object with a list")
        cluster = tuple(canon_ip(x, f"{where}.clusterList") for x in cl["list"])
    aggregator = None
    if "aggregatorAs" in p or "aggregatorId" in p:
        if "aggregatorAs" not in p or "aggregatorId" not in p:
            raise _bad(cmd, f"{where}: aggregatorAs and aggregatorId come together")
        aggregator = f"{parse_asn(p['aggregatorAs'], where)}:{canon_ip(p['aggregatorId'], where)}"
    extra = tuple(sorted((k, json.dumps(p[k], sort_keys=True)) for k in PATH_EXTRA if k in p))
    attrs = BgpAttrs(origin=origin, as_path=AsPath.build(segs), next_hops=canon_set(hops),
                     local_pref=_opt_int(cmd, p, "locPrf", where), med=_opt_int(cmd, p, "metric", where),
                     weight=_opt_int(cmd, p, "weight", where), communities=comms, ext_communities=ext,
                     large_communities=large, cluster_list=cluster,
                     originator_id=canon_ip(p["originatorId"], where) if "originatorId" in p else None,
                     atomic_aggregate=_flag(cmd, p, "atomicAggregate", where), aggregator=aggregator, extra=extra)
    peer_id = _str(cmd, peer["peerId"], f"{where}.peer.peerId")
    local = _flag(cmd, p, "sourced", where) or _flag(cmd, p, "local", where) or peer_id in ("0.0.0.0", "::")
    if local:
        source = "local"
    else:
        try:
            source = canon_ip(peer_id)
        except SnapshotError:
            raise _bad(cmd, f"{where}: path from {peer_id!r}; verify 0.4 needs the neighbor's IP address "
                            "(unnumbered BGP is not supported yet)") from None
    path_id = _opt_int(cmd, p, "addpathRxId", where) or 0
    return source, path_id, attrs, p


def parse_path(cmd: str, p, where: str) -> tuple[str, int, BgpPath]:
    source, path_id, attrs, raw = parse_attrs(cmd, p, where)
    best = False
    if "bestpath" in raw:
        bp = _obj(cmd, raw["bestpath"], f"{where}.bestpath", BESTPATH_KEYS)
        best = _flag(cmd, bp, "overall", f"{where}.bestpath")
    peer = raw["peer"]
    if source == "local":
        ptype = "local"
    else:
        ptype = peer.get("type")
        if ptype not in PEER_TYPES:
            raise _bad(cmd, f"{where}.peer.type: unknown peer type {str(ptype)[:30]!r}")
    flags = tuple(sorted(f for f in PATH_FLAGS if _flag(cmd, raw, f, where)))
    return source, path_id, BgpPath(attrs=attrs, best=best, multipath=_flag(cmd, raw, "multipath", where),
                                    valid=_flag(cmd, raw, "valid", where), peer_type=ptype,
                                    peer_router_id=canon_ip(peer["routerId"], where) if "routerId" in peer else None,
                                    flags=flags)


def _dest_paths(cmd: str, prefix: str, dest, where: str) -> list:
    """A destination is either the detail header object ({"prefix", "paths": [...]}) or a list of path
    objects; both forms are read in full."""
    if isinstance(dest, list):
        return dest
    _obj(cmd, dest, where, DEST_KEYS, {"paths"})
    if "prefix" in dest and canon_prefix(dest["prefix"], where) != prefix:
        raise _bad(cmd, f"{where}: object for {dest['prefix']}")
    if not isinstance(dest["paths"], list):
        raise _bad(cmd, f"{where}.paths: not a list")
    if "pathCount" in dest and _int(cmd, dest["pathCount"], f"{where}.pathCount") != len(dest["paths"]):
        raise _bad(cmd, f"{where}: pathCount {dest['pathCount']} but {len(dest['paths'])} paths listed")
    return dest["paths"]


def parse_bgp_table(text: str, afi: str) -> dict[str, dict[tuple[str, str, int], BgpPath]]:
    """{vrf: {(prefix, source, path id): BgpPath}} from `show bgp vrf all <afi> unicast detail json`."""
    cmd = BGP_CMDS[afi]
    data = _json(cmd, text)
    if not isinstance(data, dict):
        raise _bad(cmd, text)
    out: dict[str, dict[tuple[str, str, int], BgpPath]] = {}
    for vrf, inst in data.items():
        vrf = _vrf(cmd, vrf)
        _obj(cmd, inst, vrf, BGP_VRF_KEYS, {"routes"})
        if "vrfName" in inst and inst["vrfName"] != vrf:
            raise _bad(cmd, f"{vrf}: vrfName is {inst['vrfName']!r}")
        if not isinstance(inst["routes"], dict):
            raise _bad(cmd, f"{vrf}.routes: not an object")
        paths: dict[tuple[str, str, int], BgpPath] = {}
        for key, dest in inst["routes"].items():
            prefix = canon_prefix(key, f"{cmd}: {vrf}")
            if prefix_afi(prefix) != afi:
                raise _bad(cmd, f"{vrf}: {prefix} in the {afi} table")
            plist = _dest_paths(cmd, prefix, dest, f"{vrf} {prefix}")
            if not plist:
                raise _bad(cmd, f"{vrf} {prefix}: a destination without paths")
            for i, p in enumerate(plist):
                source, pid, path = parse_path(cmd, p, f"{vrf} {prefix} path {i}")
                if (prefix, source, pid) in paths:
                    raise _bad(cmd, f"{vrf} {prefix}: two paths from {source} (path id {pid}); verify can't tell them apart")
                paths[(prefix, source, pid)] = path
        if "totalPaths" in inst and _int(cmd, inst["totalPaths"], f"{vrf}.totalPaths") != len(paths):
            raise _bad(cmd, f"{vrf}: totalPaths {inst['totalPaths']} but {len(paths)} paths read")
        out[vrf] = paths
    return out


# The running config as FRR prints it, minus only what FRR adds around it: the "Building configuration..." and
# "Current configuration:" header, the "!" separators, blank lines, the final "end" and trailing spaces. Every
# command line is kept, in FRR's own order (gauntlet 0.4, R4: config that changes nothing observable in the lab
# is still a change).
_CONFIG_NOISE = ("Building configuration...", "Current configuration:")


def parse_running_config(text: str) -> tuple[str, ...]:
    out = []
    for raw in text.split("\n"):
        line = raw.rstrip()
        if not line.strip() or line.strip() == "!" or line in _CONFIG_NOISE or line == "end":
            continue
        out.append(line)
    return tuple(out)


def qualified(lines: tuple[str, ...]) -> list[str]:
    """Each config line with the section headers above it ("router bgp 65000 > address-family ipv4 unicast >
    neighbor ..."), for listing what changed: FRR indents a section's body one space per level."""
    out, stack = [], []
    for line in lines:
        depth = len(line) - len(line.lstrip(" "))
        stack = stack[:depth]
        out.append(" > ".join([*stack, line.strip()]))
        if len(stack) == depth:
            stack.append(line.strip())
    return out


DEFAULT_COND_ADV_TIMER = 60.0   # FRR's `bgp conditional-advertisement timer` default (seconds)


def cond_adv_timer(lines: tuple[str, ...]) -> float:
    """How often conditional advertisement is re-evaluated when an advertise-map is configured, else 0."""
    if not any(" advertise-map " in f" {ln.strip()} " for ln in lines):
        return 0.0
    timers = [float(ln.split()[-1]) for ln in lines if ln.strip().startswith("bgp conditional-advertisement timer ")
              and ln.split()[-1].isdigit()]
    return max(timers, default=DEFAULT_COND_ADV_TIMER)


def adj_command(vrf: str, afi: str, neighbor: str, direction: str) -> str:
    in_vrf = "" if vrf == "default" else f" vrf {check_vrf_name(vrf)}"
    which = "advertised-routes detail" if direction == "out" else "received-routes"
    return f"show bgp{in_vrf} {afi} unicast neighbors {canon_ip(neighbor)} {which} json"


def parse_adj(text: str, cmd: str, afi: str, direction: str) -> dict[tuple[str, int], BgpAttrs]:
    """{(prefix, path id): attributes} from an advertised-routes / received-routes detail listing. `{}` is
    a session with nothing in that direction."""
    data = _json(cmd, text)
    if not isinstance(data, dict):
        raise _bad(cmd, text)
    if not data:
        return {}
    if direction == "in":
        return _parse_received(data, cmd, afi)
    key = "advertisedRoutes"
    _obj(cmd, data, "listing", ADJ_KEYS, {key})
    if ("receivedRoutes" if direction == "out" else "advertisedRoutes") in data:
        raise _bad(cmd, "listing of the other direction")
    routes = data[key]
    if not isinstance(routes, dict):
        raise _bad(cmd, f"{key}: not an object")
    out: dict[tuple[str, int], BgpAttrs] = {}
    for k, dest in routes.items():
        prefix = canon_prefix(k, cmd)
        if prefix_afi(prefix) != afi:
            raise _bad(cmd, f"{prefix} in an {afi} listing")
        plist = _dest_paths(cmd, prefix, dest, prefix)
        if not plist:
            raise _bad(cmd, f"{prefix}: no path")
        id_key = "addpathTxId"
        for i, p in enumerate(plist):
            _src, _rx, attrs, raw = parse_attrs(cmd, p, f"{prefix} path {i}")
            if len(plist) > 1 and id_key not in raw:
                raise _bad(cmd, f"{prefix}: several paths without {id_key}; verify can't tell them apart")
            pid = _opt_int(cmd, raw, id_key, f"{prefix} path {i}") if len(plist) > 1 else 0
            if (prefix, pid) in out:
                raise _bad(cmd, f"{prefix}: two paths with {id_key} {pid}")
            out[(prefix, pid)] = attrs
    listed = len(routes)
    if "bgpOriginatingDefaultNetwork" in data:
        default = "0.0.0.0/0" if afi == "ipv4" else "::/0"
        if data["bgpOriginatingDefaultNetwork"] != default or (default, 0) in out:
            raise _bad(cmd, f"bgpOriginatingDefaultNetwork: {str(data['bgpOriginatingDefaultNetwork'])[:60]!r}")
        out[(default, 0)] = DEFAULT_ORIGINATE
        listed += 1
    _check_total(cmd, data, listed)
    return out


def _check_total(cmd: str, data: dict, listed: int) -> None:
    if "totalPrefixCounter" in data and _int(cmd, data["totalPrefixCounter"], "totalPrefixCounter") != listed:
        raise _bad(cmd, f"totalPrefixCounter {data['totalPrefixCounter']} but {listed} prefixes listed")


def _parse_received(data: dict, cmd: str, afi: str) -> dict[tuple[str, int], BgpAttrs]:
    """The plain received-routes listing: per prefix, what the neighbor sent (one path; add-path sessions are
    refused when the neighbors are read). Communities aren't listed, so they stay empty here."""
    _obj(cmd, data, "listing", ADJ_KEYS - {"advertisedRoutes", "bgpOriginatingDefaultNetwork"}, {"receivedRoutes"})
    routes = data["receivedRoutes"]
    if not isinstance(routes, dict):
        raise _bad(cmd, "receivedRoutes: not an object")
    out: dict[tuple[str, int], BgpAttrs] = {}
    for k, r in routes.items():
        prefix = canon_prefix(k, cmd)
        if prefix_afi(prefix) != afi:
            raise _bad(cmd, f"{prefix} in an {afi} listing")
        _obj(cmd, r, prefix, RECEIVED_KEYS, {"network", "path", "origin"})
        if canon_prefix(r["network"], prefix) != prefix:
            raise _bad(cmd, f"{prefix}: entry for {r['network']}")
        hops = [r[h] for h in ("nextHop", "nextHopGlobal") if h in r]
        if len(hops) != 1:
            raise _bad(cmd, f"{prefix}: expected one next hop, got {len(hops)}")
        ip = canon_ip(hops[0], f"{prefix} next hop")
        scope = "link-local" if ipaddress.ip_address(ip).is_link_local else "global"
        origin = ORIGIN_NAMES.get(str(r["origin"]).strip().lower()) if isinstance(r["origin"], str) else None
        if origin is None:
            raise _bad(cmd, f"{prefix}.origin: unknown origin {str(r['origin'])[:30]!r}")
        if not isinstance(r["path"], str):
            raise _bad(cmd, f"{prefix}.path: not a string")
        try:
            as_path = AsPath.parse(r["path"])
        except SnapshotError as e:
            raise _bad(cmd, f"{prefix}: {e}") from None
        out[(prefix, 0)] = BgpAttrs(origin=origin, as_path=as_path,
                                    next_hops=(PathNextHop(_boot_free(ip), scope, False, False, None, None),),
                                    local_pref=_opt_int(cmd, r, "locPrf", prefix), med=_opt_int(cmd, r, "metric", prefix),
                                    weight=_opt_int(cmd, r, "weight", prefix), communities=(), ext_communities=(),
                                    large_communities=(), cluster_list=(), originator_id=None, atomic_aggregate=False,
                                    aggregator=None)
    _check_total(cmd, data, len(routes))
    return out


# ---------------------------------------------------------------------------------------------------------
# One node
# ---------------------------------------------------------------------------------------------------------

class FrrCollector:
    """Collects one FRR node's snapshot. `exec_fn(node, argv) -> (rc, stdout, stderr)` runs a command in
    the node (Lab.exec in a real run, a fake in tests)."""

    driver = "frr"

    def __init__(self, node: str, exec_fn, ll_owners: dict[str, str] | None = None):
        self.node = node
        self.exec_fn = exec_fn
        self.ll_owners = ll_owners   # link_local_names() of the lab; None: link-locals compare as fe80::

    def _vtysh(self, command: str, raw: list[dict]) -> str:
        rc, out, err = self.exec_fn(self.node, ["vtysh", "-c", command])
        raw.append({"node": self.node, "cmd": f"vtysh -c '{command}'", "rc": rc, "output": out, "stderr": err[-2000:]})
        if rc == TIMED_OUT:
            raise CommandTimedOut(f"`vtysh -c '{command}'` on {self.node} did not finish in time; its output was cut")
        if rc != 0:
            msg = (err or out).strip().splitlines()
            raise CommandFailed(f"`vtysh -c '{command}'` failed on {self.node} (rc={rc}): {msg[-1] if msg else 'no output'}")
        return out

    def collect(self) -> NodeSnapshot:
        raw: list[dict] = []
        try:
            return self._collect(raw)
        except CommandFailed:
            raise
        except SnapshotError as e:
            raise SnapshotError(f"{self.node}: {e}") from None

    def _collect(self, raw: list[dict]) -> NodeSnapshot:
        config = parse_running_config(self._vtysh(CONFIG_CMD, raw))
        if self.ll_owners is None:
            return self._collect_items(raw, config)
        with link_local_owners(self.ll_owners, configured_link_locals(config)):
            return self._collect_items(raw, config)

    def _collect_items(self, raw: list[dict], config: tuple[str, ...]) -> NodeSnapshot:
        node = self.node
        vrfs_conf = parse_vrfs(self._vtysh(VRF_CMD, raw))
        for v in vrfs_conf:
            _vrf(VRF_CMD, v)
        active = {"default"} | {v for v, up in vrfs_conf.items() if up}
        known = {"default"} | set(vrfs_conf)
        neighbors_text = self._vtysh(NEIGHBORS_CMD, raw)
        sessions = parse_neighbors(neighbors_text)
        sent = sent_counters(neighbors_text)
        adv_interval = max(adv_intervals(neighbors_text).values(), default=0.0)
        ribs = {afi: parse_routes(self._vtysh(ROUTE_CMDS[afi], raw), afi) for afi in ("ipv4", "ipv6")}
        tables = {afi: parse_bgp_table(self._vtysh(BGP_CMDS[afi], raw), afi) for afi in ("ipv4", "ipv6")}

        # Completeness: every VRF in every output, or the snapshot is incomplete (an error, never smaller)
        for afi, rib in ribs.items():
            missing = sorted(active - set(rib))
            extra = sorted(set(rib) - known)
            if missing or extra:
                raise SnapshotError(f"`{ROUTE_CMDS[afi]}` lists VRFs {sorted(rib)}; `show vrf` says {sorted(active)} "
                                    f"(missing {missing}, unknown {extra})")
        bgp_vrfs = set(sessions)
        for afi, table in tables.items():
            if set(table) != bgp_vrfs:
                raise SnapshotError(f"`{BGP_CMDS[afi]}` lists BGP instances {sorted(table)}; `{NEIGHBORS_CMD}` lists "
                                    f"{sorted(bgp_vrfs)}")
        if bgp_vrfs - known:
            raise SnapshotError(f"BGP instances in VRFs {sorted(bgp_vrfs - known)} that `show vrf` doesn't list")

        items: dict[ItemKey, object] = {}
        for vrf, nbrs in sessions.items():
            for nbr, s in nbrs.items():
                items[ItemKey("session", node, vrf, neighbor=nbr)] = s
        for afi, rib in ribs.items():
            for vrf, entries in rib.items():
                for (prefix, proto), es in entries.items():
                    items[ItemKey("rib", node, vrf, afi, "unicast", prefix, protocol=proto)] = es
        for afi, table in tables.items():
            for vrf, paths in table.items():
                for (prefix, source, pid), path in paths.items():
                    items[ItemKey("path", node, vrf, afi, "unicast", prefix, neighbor=source, path_id=pid)] = path
        for vrf, nbrs in sorted(sessions.items()):
            for nbr, s in sorted(nbrs.items()):
                if not s.established:
                    continue   # nothing is exchanged; the session's own state is the diff
                for fam in s.afis:
                    afi = fam.split("-")[0]
                    directions = ["out"] + (["in"] if fam in s.soft_reconfig_in else [])
                    for d in directions:
                        cmd = adj_command(vrf, afi, nbr, d)
                        listing = parse_adj(self._vtysh(cmd, raw), cmd, afi, d)
                        if d == "out" and not listing and sent.get((vrf, nbr, fam), 0) > 0:
                            raise CommandFailed(f"`vtysh -c '{cmd}'` on {node} listed nothing, but the neighbor output "
                                                f"says {sent[(vrf, nbr, fam)]} prefixes were sent: not read as "
                                                "'advertises nothing'")
                        for (prefix, pid), attrs in listing.items():
                            kind = "adj_out" if d == "out" else "adj_in"
                            items[ItemKey(kind, node, vrf, afi, "unicast", prefix, neighbor=nbr, path_id=pid)] = attrs
        vrfs = tuple(sorted(active | bgp_vrfs))
        return NodeSnapshot(node, self.driver, vrfs, items, raw, adv_interval=adv_interval, config=config,
                            cond_adv_timer=cond_adv_timer(config))


def show_command(key: ItemKey) -> str:
    """One read-only vtysh command that shows an item on its node."""
    in_vrf = "" if key.vrf == "default" else f" vrf {key.vrf}"
    if key.kind == "config":
        return CONFIG_CMD
    if key.kind == "vrf":
        return "show vrf"
    if key.kind == "session":
        return f"show bgp{in_vrf} neighbors {key.neighbor}"
    if key.kind == "rib":
        fam = "ipv6" if key.afi == "ipv6" else "ip"
        return f"show {fam} route{in_vrf} {key.prefix}"
    if key.kind == "path":
        return f"show bgp{in_vrf} {key.afi} unicast {key.prefix}"
    which = "advertised-routes" if key.kind == "adj_out" else "received-routes"
    return f"show bgp{in_vrf} {key.afi} unicast neighbors {key.neighbor} {which}"


__all__ = ["CommandFailed", "CommandTimedOut", "FrrCollector", "parse_adj", "parse_bgp_table", "parse_neighbors", "parse_routes",
           "show_command"]
