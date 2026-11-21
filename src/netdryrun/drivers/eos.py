"""Arista EOS (cEOS-lab) driver: `Cli ... | json` state, ping from the EOS CLI.

Routes are read from the routing table (the route EOS selected), the RIB (every candidate of every protocol, selected
or not) and the BGP table, because a candidate that lost route selection (a floating static behind a BGP default, an
OSPF default behind a static drop route) or a received-but-not-selected BGP path must still count as present for
`present: false` checks. `show ip route <prefix>` lists only the selected route (FP-043-EOSNONBGP). The node's own
BGP aggregate is `bgp` in all three reads, selected or not, as on FRR (FP-043-EOSAGG).

EOS keys every answer by VRF (`{"vrfs": {name: ...}}`). A VRF missing from that map is never read as
"no routes": the VRF doesn't exist, or the output isn't what this driver knows. Both raise.
"""
from __future__ import annotations

import json
import re

import ipaddress

from .base import (BgpNeighbor, BgpPath, Driver, DriverError, NoSuchInstance, Observation, Route, RoutingDisabled,
                   add_path_range_why, as_int, canon_communities, check_vrf_name, load_json, must, must_bool, network,
                   parser, render_as_path, unexpected)
from .frr import _canon_addr, parse_ping
from .stale import refuse_if_stale

PROTOCOLS = {"ebgp": "bgp", "ibgp": "bgp", "bgp": "bgp", "connected": "connected", "static": "static",
             "ospf": "ospf", "ospfintraarea": "ospf", "ospfinterarea": "ospf", "ospfexternaltype1": "ospf",
             "ospfexternaltype2": "ospf", "isis": "isis", "isislevel1": "isis", "isislevel2": "isis",
             # the node's own BGP aggregate (`aggregate-address`) is bgp, as on FRR and NX-OS (FP-043-EOSAGG, RT-0087)
             "bgpaggregate": "bgp", "droproute": "static", "dropped": "static"}  # static discard (Null0)


def _protocol(rtype: str, prefix: str, command: str = "show ip route <prefix> | json") -> str:
    """An EOS routeType as a netdryrun protocol name. Every OSPF route type (intra, inter, external, NSSA, and
    any later one) is ospf, and in an IPv6 table it is OSPFv3, ospf6: the map once had no name that gave ospf6, so
    `protocol: ospf6 present: false` never matched an EOS route (red team RT-0025). The node's own BGP aggregate
    (routeType bgpAggregate) is bgp: 0.4.2 read it as `aggregate`, so `protocol: bgp present: false` passed on it
    while FRR fails the same check (RT-0085, FP-043-EOSAGG). Any other route type this driver doesn't map (a
    nexthop-group static, a leaked route, an aggregate that isn't BGP's, one a later EOS adds) is an error: 0.4.0
    passed the raw name through, which no `protocol` matched, so `present: false` on it passed (acceptance 0.4.1)."""
    raw, rtype = rtype, rtype.lower().replace(" ", "")
    if rtype.startswith("ospf"):
        return "ospf6" if ":" in prefix else "ospf"   # by family: OSPFv3 carrying IPv4 is ospf (Route normalises it too)
    if rtype.startswith("isis"):
        return "isis"
    if rtype not in PROTOCOLS:
        raise unexpected(command, f"routeType {raw!r} (read as {rtype!r}) is not one this driver maps to a protocol")
    return PROTOCOLS[rtype]


def _programmed(command: str, route: dict) -> bool:
    """Whether a routing-table entry forwards: EOS flags one it could not put in the kernel or the hardware
    (kernelProgrammed / hardwareProgrammed false, e.g. a full TCAM), and such a route is not active, never
    a pass of `present` (red team plausible case, 2026-11-01). cEOS 4.36.3M prints both flags on every route, so
    one missing is unknown: the read fails, never "not forwarding", which would pass `present: false` (Layer 6
    round 2 on eaa323c)."""
    return must_bool(command, route, "kernelProgrammed") and must_bool(command, route, "hardwareProgrammed")


SUMMARY_CMD = {"ipv4-unicast": "show ip bgp summary | json", "ipv6-unicast": "show ipv6 bgp summary | json"}
ROUTE_CMD = "show ip route <prefix> | json"
ALL_ROUTES_CMD = "show ip route | json"
BGP_CMD = "show ip bgp <prefix> | json"
RIB_CMD = "show rib route ip <prefix> | json"


def _json(command: str, text: str) -> dict:
    data = load_json(command, text)
    if isinstance(data, dict) and "errors" in data:
        raise DriverError(f"EOS error from `{command}`: {data['errors']}")
    if not isinstance(data, dict):
        raise unexpected(command, text)
    return data


def _vrf(command: str, data: dict, vrf: str) -> dict:
    """The answer for `vrf`. Without the `vrfs` map the output is unexpected; without the VRF in it,
    the VRF doesn't exist or the command has nothing configured in it (BGP without that VRF). That
    can't be told apart from output this driver doesn't know, so it raises: never "no routes"."""
    vrfs = data.get("vrfs")
    if not isinstance(vrfs, dict):
        raise unexpected(command, data)
    if vrf not in vrfs:
        raise NoSuchInstance(f"VRF {vrf!r} is not in the output of `{command}` (VRFs listed: "
                          f"{', '.join(sorted(map(str, vrfs))) or 'none'}): it does not exist, or this "
                          "command has nothing configured in it")
    entry = vrfs[vrf]
    if not isinstance(entry, dict):
        raise unexpected(command, f"vrf {vrf}: {str(entry)[:150]}")
    return entry


def _routing_vrf(command: str, data: dict, vrf: str) -> dict:
    """A route answer's VRF entry, which must route: `routingDisabled: true` (a VRF without `ip routing`, or the default
    VRF after `no ip routing`, captured live 2026-11-06 for IPv4 and IPv6) has no routes because nothing routes there,
    never because a route is absent (red team A-0049). Every live route answer prints the flag: missing is unexpected."""
    entry = _vrf(command, data, vrf)
    disabled = entry.get("routingDisabled")
    if disabled is not True and disabled is not False:
        raise unexpected(command, f"vrf {vrf}: routingDisabled is {disabled!r}, not a boolean")
    if disabled:
        raise RoutingDisabled(f"VRF {vrf!r} has routing disabled (`{command}`): nothing routes there, so no route "
                              "check means anything in it")
    return entry


def _table(command: str, entry: dict, key: str) -> dict:
    """A required map inside a VRF's answer (routes, peers, bgpRouteEntries); `{}` is a real empty one."""
    table = entry.get(key)
    if not isinstance(table, dict):
        raise unexpected(command, f"no {key!r} map: {str(entry)[:150]}")
    return table


def _summary(text: str, vrf: str, afi: str, into: dict[str, BgpNeighbor] | None):
    command = SUMMARY_CMD.get(afi, f"show bgp {afi} summary | json")
    out = into if into is not None else {}
    entry = _vrf(command, _json(command, text), vrf)
    for addr, p in _table(command, entry, "peers").items():
        if not isinstance(p, dict) or not isinstance(p.get("peerState"), str) or not p["peerState"].strip():
            raise unexpected(command, f"{addr}: {str(p)[:150]}")
        key = _canon_addr(str(addr))
        # "Idle(Admin)" (EOS prints no space) -> "idle": the first word is the FSM state
        state = re.split(r"[\s(]", p["peerState"].strip(), maxsplit=1)[0].lower()
        # EOS sends updates without delay unless `neighbor ... out-delay` is set, which the summary doesn't show:
        # its platform default (0) is used
        n = out.get(key) or BgpNeighbor(str(addr), state, adv_interval=0.0)
        if "asn" in p and "asn" in entry:   # eBGP when the peer's AS isn't the VRF's own (record's closed-world guard)
            n.external = str(p["asn"]) != str(entry["asn"])
        if n.address != str(addr):
            # scoped link-locals sharing a key (one peer is also listed once per address family): ambiguous, and a
            # down session is never hidden by an up one
            if str(addr) not in n.ambiguous:
                n.ambiguous = (n.ambiguous or [n.address]) + [str(addr)]
            if n.state == "established" and state != "established":
                n.state = state
        if "prefixAccepted" in p:
            n.prefixes[afi] = as_int(command, p["prefixAccepted"])
        elif n.state == "established":  # a missing count would read as 0 prefixes, passing `max`
            raise unexpected(command, f"{addr}: established without prefixAccepted")
        out[key] = n
    return out


@parser("show ip bgp summary | json")
def parse_bgp_summary(text: str, vrf: str = "default", afi: str = "ipv4-unicast",
                      into: dict[str, BgpNeighbor] | None = None) -> dict[str, BgpNeighbor]:
    return _summary(text, vrf, afi, into)


def _learned(p: dict) -> bool:
    """A path received from a BGP neighbor (EOS leaves peerAddr empty for the router's own paths:
    network statements, redistribution). Valid or not, active or not, it was received."""
    return bool(_peer(p))


def _own_aggregate(p: dict) -> bool:
    """The node's own BGP aggregate (`aggregate-address`): routeType.localAgg true and no peer (cEOS 4.36.3M prints
    localAgg only on such a path, live, ceos4363m_eosagg_*). Not a boolean, or on a path from a neighbor, is output
    this driver doesn't know."""
    flag = must(BGP_CMD, p, "routeType").get("localAgg", False) if isinstance(p.get("routeType"), dict) else None
    if flag is not True and flag is not False:
        raise unexpected(BGP_CMD, f"routeType.localAgg is {flag!r}, not a boolean: {str(p)[:150]}")
    if flag and _peer(p):
        raise unexpected(BGP_CMD, f"a path from neighbor {_peer(p)} marked localAgg: {str(p)[:150]}")
    return flag


def _peer(p: dict) -> str:
    """The neighbor a path came from: peerEntry.peerAddr, "" for the router's own paths. Missing is an error."""
    peer = must(BGP_CMD, p, "peerEntry") if isinstance(p, dict) else None
    addr = must(BGP_CMD, peer, "peerAddr") if isinstance(peer, dict) else None
    if not isinstance(addr, str):
        raise unexpected(BGP_CMD, f"path without peerEntry: {str(p)[:150]}")
    return addr


def _path_count(command: str, key: str, e: dict) -> None:
    """`totalPaths` must equal the paths listed: a path dropped from under its count must never read as one path
    less, or as no path (0.4.1, the shape of the Junos fuzz finding of 2026-11-01)."""
    if "totalPaths" not in e:
        raise unexpected(command, f"{key}: no totalPaths: {str({k: v for k, v in e.items() if k != 'bgpRoutePaths'})[:150]}")
    count = as_int(command, e["totalPaths"])
    if count != len(e["bgpRoutePaths"]):
        raise unexpected(command, f"{key}: totalPaths {count}, but {len(e['bgpRoutePaths'])} paths listed")


def _bgp_entries(command: str, text: str, vrf: str) -> dict:
    entry = _vrf(command, _json(command, text), vrf)
    entries = _table(command, entry, "bgpRouteEntries")
    for key, e in entries.items():
        if not isinstance(e, dict) or not isinstance(e.get("bgpRoutePaths"), list):
            raise unexpected(command, f"{key}: {str(e)[:150]}")
        _path_count(command, key, e)
        for p in e["bgpRoutePaths"]:
            if not isinstance(p, dict):
                raise unexpected(command, f"{key} path: {str(p)[:150]}")
            # graceful restart: neither present nor gone yet. cEOS prints routeType.stale on every path: missing is
            # unknown, never "not stale" (Layer 6 round 2 on eaa323c)
            stale = must_bool(command, must(command, p, "routeType"), "stale")
            refuse_if_stale(key, _peer(p), stale)
    return entries


def _exact_entry(key: str, want) -> None:
    """`show ip bgp <prefix>` lists exactly that prefix, nothing without it (cEOS 4.36.3M): an entry for another one
    is output this parser doesn't know, never "no path". (`show ip route <prefix>` is different: it answers with the
    longest match, so parse_routes skips a covering route there.)"""
    if network(BGP_CMD, key) != want:
        raise unexpected(BGP_CMD, f"an entry for {key} in the answer for {want}")


BGP_INACTIVE = {"errors": ["BGP inactive"]}   # cEOS with no BGP configured, rc 1 (eos_bgp_inactive.txt, live)


# `show rib route ip|ipv6` keys its candidates by the source protocol; the static key is the config agent's name
RIB_PROTOCOLS = {"staticConfig": "static"}


def _rib_protocol(key: str, prefix: str) -> str:
    """A `ribRoutesByProtocol` key as a netdryrun protocol name. Keys other than staticConfig name the protocol as
    routeType does (bgp, ospf, ospf3, isis, connected) and go through the same map; a key it doesn't know is an error,
    never a name no `protocol` matches (which would pass `present: false` on it). That includes `routeInput` ("Route
    Input": a plain cEOS lists 0.0.0.0/8 and 127.0.0.0/8 under it, live), vrfLeak, gribi and dynamicPolicy: nothing in
    the answer says which configuration made such an entry, so a check on its exact prefix is an error."""
    return RIB_PROTOCOLS.get(key) or _protocol(key, prefix, RIB_CMD)


@parser(RIB_CMD)
def parse_rib_candidates(text: str, prefix: str, vrf: str = "default") -> list[tuple[str, bool, str]]:
    """Every candidate EOS's RIB holds for exactly `prefix` in `vrf`, selected or not, from `show rib route ip|ipv6 vrf
    <vrf> <prefix> | json` (cEOS 4.36.3M, live, FP-043-EOSNONBGP): [(protocol, bestRoute, raw key)].

    The answer is keyed vrfs -> ribRoutesByProtocol -> <protocol> -> ribRoutes -> <prefix>, one entry per protocol with
    `bestRoute`. Like `show ip route <prefix>`, EOS answers with the longest match (9.9.9.0/24 answers with the
    0.0.0.0/0 routes): an entry for another prefix is skipped, never the asked one. `notInFec` is on a not-selected
    route and on a selected Null0 route alike, so it says nothing about presence and isn't read. Anything this parser
    doesn't know (no vrfs map, the VRF missing, a protocol key it can't map, an entry without bestRoute) raises:
    an unreadable RIB is never "no candidate"."""
    want = ipaddress.ip_network(prefix)
    entry = _vrf(RIB_CMD, _json(RIB_CMD, text), vrf)
    out = []
    for key, proto in _table(RIB_CMD, entry, "ribRoutesByProtocol").items():
        if not isinstance(proto, dict):
            raise unexpected(RIB_CMD, f"{key}: {str(proto)[:150]}")
        for pkey, r in _table(RIB_CMD, proto, "ribRoutes").items():
            if not isinstance(r, dict):
                raise unexpected(RIB_CMD, f"{key} {pkey}: {str(r)[:150]}")
            if network(RIB_CMD, pkey) != want:
                continue   # the longest match for the asked prefix: another prefix, never this one
            out.append((_rib_protocol(str(key), prefix), must_bool(RIB_CMD, r, "bestRoute"), str(key)))
    return out


@parser(ROUTE_CMD)
def parse_routes(route_text: str, bgp_text: str | None, prefix: str, vrf: str = "default",
                 rib_text: str | None = None) -> list[Route]:
    """The routes for exactly `prefix`: the routing table's selected route, every other RIB candidate (not selected),
    and the BGP table's paths for the prefix that aren't the installed route (not selected).

    The node's own BGP aggregate is `bgp` in every read, selected or not, as FRR and NX-OS name it (FP-043-EOSAGG,
    RT-0087): routeType bgpAggregate in the routing table, the RIB's `bgp` entry, the BGP table's path with
    routeType.localAgg. 0.4.2 named it `aggregate` while selected (RT-0085) and nothing while a static won (RT-0086);
    the first fix named it `bgp` only while it lost, so its name hung on selection."""
    want = ipaddress.ip_network(prefix)
    out = []
    for key, r in _table(ROUTE_CMD, _routing_vrf(ROUTE_CMD, _json(ROUTE_CMD, route_text), vrf), "routes").items():
        if not isinstance(r, dict):
            raise unexpected(ROUTE_CMD, f"{key}: {str(r)[:150]}")
        if network(ROUTE_CMD, key) == want:
            out.append(Route(prefix, _protocol(str(must(ROUTE_CMD, r, "routeType")), prefix), _programmed(ROUTE_CMD, r),
                             raw_protocol=str(r["routeType"])))
    # the routing table's route is a BGP-learned path (eBGP, iBGP), not the node's own aggregate, programmed or not
    installed_learned = any(r.protocol == "bgp" and r.raw_protocol.lower() != "bgpaggregate" for r in out)
    rib_bgp = None   # a bgp entry only the RIB lists: what it is comes from the BGP table below
    if rib_text is not None:
        # Every RIB candidate of a protocol the routing table doesn't list is present but not selected (a floating
        # static behind a BGP default, an OSPF default behind a static drop route: RT-0056, RT-0063; the node's own
        # aggregate behind a static: RT-0086). The RIB keys one entry per protocol, so a protocol the routing table
        # lists is that route: a selected aggregate (bgpAggregate, bgp) is the RIB's `bgp` entry, never a second bgp
        # candidate (adversary review of FP-043-EOSNONBGP). Any other candidate the RIB marks best while the routing
        # table selects another protocol (a change between the two reads) is added the same way, inactive: present
        # for `present: false`, never active for `present: true`.
        seen = {r.protocol for r in out}
        for proto, _best, raw in parse_rib_candidates(rib_text, prefix, vrf):   # bestRoute: read, must be a boolean
            if proto not in seen:
                seen.add(proto)
                out.append(Route(prefix, proto, False, raw_protocol=raw))
                if proto == "bgp":
                    rib_bgp = raw
    if bgp_text is None:   # the node runs no BGP (EosDriver._bgp_cli)
        if rib_bgp is not None:
            raise unexpected(RIB_CMD, f"a {rib_bgp!r} entry for {prefix} in vrf {vrf} on a node that runs no BGP: "
                                      "neither the node's own aggregate nor a learned path")
        return out
    own_agg = learned = False
    for key, e in _bgp_entries(BGP_CMD, bgp_text, vrf).items():
        _exact_entry(key, want)
        for p in e["bgpRoutePaths"]:
            own_agg = _own_aggregate(p) or own_agg
            learned = _learned(p) or learned
    if rib_bgp is not None and not (own_agg or learned):
        # Never a bgp route nothing classifies: the RIB says bgp, the BGP table has neither the node's own aggregate
        # nor a path from a neighbor for the prefix (a change between the reads, or output this driver doesn't know)
        raise unexpected(RIB_CMD, f"a {rib_bgp!r} entry for {prefix} in vrf {vrf} that the BGP table (`{BGP_CMD}`) "
                                  "doesn't list as the node's own aggregate (localAgg) or as a path from a neighbor")
    # A BGP path can be "best" inside BGP and still not be installed (a static or connected route with a better
    # preference, or the node's own aggregate, wins the routing table). Unless a learned path is the installed route,
    # every BGP path learned from a neighbor, valid or not, is "present but not selected": a leak that must still fail
    # `present: false`, and that `protocol: bgp active: false` sees whatever else holds the prefix.
    if learned and not installed_learned:
        out.append(Route(prefix, "bgp", False))
    # The node's own aggregate in the BGP table (it is sent to peers) is a bgp route the node holds, whatever the
    # RIB said; the routing table or the RIB lists it already when either has a bgp entry.
    if own_agg and not any(r.protocol == "bgp" for r in out):
        out.append(Route(prefix, "bgp", False, raw_protocol="localAgg"))
    return out


@parser(ALL_ROUTES_CMD)
def parse_all_routes(text: str, vrf: str = "default") -> list[Route]:
    out = []
    for key, r in _table(ALL_ROUTES_CMD, _routing_vrf(ALL_ROUTES_CMD, _json(ALL_ROUTES_CMD, text), vrf), "routes").items():
        if not isinstance(r, dict):
            raise unexpected(ALL_ROUTES_CMD, f"{key}: {str(r)[:150]}")
        net = str(network(ALL_ROUTES_CMD, key))
        out.append(Route(net, _protocol(str(must(ALL_ROUTES_CMD, r, "routeType")), net, ALL_ROUTES_CMD),
                         _programmed(ALL_ROUTES_CMD, r), raw_protocol=str(r["routeType"])))
    return out


_parse_routes_three_reads = parse_routes


@parser(ROUTE_CMD)
def parse_routes(route_text: str, bgp_text: str | None, prefix: str, vrf: str = "default",
                 rib_text: str | None = None) -> list[Route]:
    """parse_routes of the three reads, plus the node's own path that nothing else originates (adversary review of
    FP-043-EOSAGG, F4). `aggregate-address P advertise-only` puts the aggregate in neither the routing table nor the
    RIB (live, cEOS 4.36.3M, ceos4363m_advagg_advonly_*): the BGP table's own path is the only read that shows it,
    and the node sends it to its peers. A `network` statement or redistribution needs a route in the RIB to
    originate from, so an own path (no peer) with nothing in the routing table and nothing in the RIB has no source
    but BGP itself: a bgp route, not selected, whatever routeType.localAgg says or whether EOS prints it
    (FP-042-FRR102: a missing key is never a guess). Only with a RIB answer read: without one an empty routing table
    doesn't show that no other protocol holds the prefix.

    Limit: a static route whose next hop doesn't resolve is in none of the three reads on EOS (live, cEOS 4.36.3M),
    so `protocol: static present: false` passes while it is configured (compatibility page, EOS limits)."""
    out = _parse_routes_three_reads(route_text, bgp_text, prefix, vrf, rib_text)
    if out or bgp_text is None or rib_text is None:
        return out
    for e in _bgp_entries(BGP_CMD, bgp_text, vrf).values():   # every entry is the prefix's: checked above
        if any(not _peer(p) for p in e["bgpRoutePaths"]):
            return [Route(prefix, "bgp", False, raw_protocol="own path")]
    return out


_AS_TOKEN = re.compile(r"\{([^}]*)\}|\[([^\]]*)\]|\(([^)]*)\)|(\S+)")
_ASN = re.compile(r"[0-9]+")
MAX_ASN = 4294967295   # 4-byte ASNs: a larger number is no ASN


def _as_path(printed: object) -> str:
    """EOS's AS path in the netdryrun.yml form: sets {a,b} and confederation sets [a,b] comma-separated (EOS
    prints `{65004 65006}`, interop IOP-3), sequences and confederation sequences (a b) space-separated.
    Every ASN must be asplain: a dotted (asdot) token such as 64086.59905, which EOS prints under `bgp asn notation
    asdot`, or any other token is unexpected output, as on NX-OS. Kept as text, a "must not contain" as_path_regex
    written in asplain (the only form netdryrun.yml takes) would never see the ASN and pass (FP-042-EOSASDOT)."""
    if not isinstance(printed, str):
        raise unexpected(BGP_CMD, f"asPath: {str(printed)[:80]!r}")
    segs: list[tuple[str, list]] = []
    for m in _AS_TOKEN.finditer(printed):
        aset, cset, cseq, asn = m.groups()
        members = next(g for g in (aset, cset, cseq, asn) if g is not None).replace(",", " ").split()
        if not members or not all(_ASN.fullmatch(x) and int(x) <= MAX_ASN for x in members):
            raise unexpected(BGP_CMD, f"asPath: {printed[:80]!r}")
        segs.append(("as-set" if aset is not None else "confed-set" if cset is not None
                     else "confed-sequence" if cseq is not None else "as-sequence", members))
    return render_as_path(segs)


def _med(value: int) -> int | None:
    return value or None


@parser(BGP_CMD)
def parse_bgp_paths(text: str, prefix: str, vrf: str = "default") -> list[BgpPath]:
    """`show ip bgp <prefix> vrf <vrf> | json`: the best path is the one EOS marks active.
    A locally originated path has no localPreference or med field; it carries neither attribute.
    Every path is listed, valid or not, active or not."""
    want = ipaddress.ip_network(prefix)
    out = []
    for key, e in _bgp_entries(BGP_CMD, text, vrf).items():
        _exact_entry(key, want)
        for p in e["bgpRoutePaths"]:
            # cEOS 4.36.3M prints the AS path, the active flag and both community lists ([] when none) on every
            # path: one missing is unknown, never "no communities" or an empty AS path (Layer 6 round 2 on eaa323c)
            detail = must(BGP_CMD, p, "routeDetail")
            nh = p.get("nextHop") or ""
            out.append(BgpPath(
                best=must_bool(BGP_CMD, must(BGP_CMD, p, "routeType"), "active"),
                as_path=_as_path(must(BGP_CMD, must(BGP_CMD, p, "asPathEntry"), "asPath")),
                next_hop=_canon_addr(str(nh)) if nh else None,
                local_pref=as_int(BGP_CMD, p["localPreference"]) if "localPreference" in p else None,
                # no MED attribute: unknown, not 0. cEOS 4.36.3M also prints "med": 0 for a path received with
                # no MED (interop IOP-2), so 0 is unknown too, and a `med: 0` check is refused (ambiguous_bgp_values)
                med=_med(as_int(BGP_CMD, p["med"])) if "med" in p else None,
                communities=canon_communities(must(BGP_CMD, detail, "communityList")),
                large_communities=canon_communities(must(BGP_CMD, detail, "largeCommunityList")),
                neighbor=_peer(p) or None,
            ))
    return out


STARTUP_ERRORS_CMD = "show startup-config errors"
_NO_STARTUP_ERRORS = "No errors were found in startup-config."
_STARTUP_TOTAL = re.compile(r"^Total (\d+) errors found in startup-config\.$")
_STARTUP_COUNT = re.compile(r"^errors in startup-config: (\d+)$")
_STARTUP_REASON = re.compile(r"^% (.+?) at line (\d+)$")


def parse_startup_config_errors(text: str) -> list[str]:
    """`show startup-config errors` (cEOS 4.36.3M, live): [] when every startup-config line loaded, else each line
    EOS rejected at boot ("line N: <line> (<reason>)"), in order. EOS skips such a line and loads the rest. Output
    it can't account for (the count disagrees with the lines found, or a line it doesn't know) raises: never clean."""
    lines = [ln.rstrip() for ln in text.splitlines() if ln.strip()]
    if lines == [_NO_STARTUP_ERRORS]:
        return []
    if not lines or not _STARTUP_TOTAL.match(lines[0]) or not _STARTUP_COUNT.match(lines[-1]):
        raise DriverError(f"{STARTUP_ERRORS_CMD}: unexpected output: {' '.join(text.split())[:200]!r}")
    total, count = int(_STARTUP_TOTAL.match(lines[0]).group(1)), int(_STARTUP_COUNT.match(lines[-1]).group(1))
    out, body = [], lines[1:-1]
    if len(body) % 2:
        raise DriverError(f"{STARTUP_ERRORS_CMD}: unexpected output: {' '.join(text.split())[:200]!r}")
    for cmd, why in zip(body[::2], body[1::2], strict=True):
        m = _STARTUP_REASON.match(why)
        if not cmd.startswith(">") or not m:
            raise DriverError(f"{STARTUP_ERRORS_CMD}: unexpected output: {cmd[:80]!r} {why[:80]!r}")
        out.append(f"line {m.group(2)}: {cmd[1:].strip()} ({m.group(1)})")
    if not total == count == len(out):
        raise DriverError(f"{STARTUP_ERRORS_CMD}: says {total} and {count} errors, lists {len(out)}")
    return out


def _eor_key(addr: str) -> str:
    try:
        return str(ipaddress.ip_address(str(addr).split("%")[0]))
    except ValueError:
        return str(addr)


EOS_FAMILIES = {"ipv4Unicast": "ipv4-unicast", "ipv6Unicast": "ipv6-unicast"}


def parse_eos_eor(text: str, vrf: str) -> dict[str, dict[str, str]]:
    """{neighbor address: End-of-RIB per family} from `show ip bgp neighbors vrf <vrf> | json`. Fail-safe: output that
    isn't the neighbor list gives {}, and end_of_rib then reads every session unknown (never received)."""
    import json
    try:
        peers = json.loads(text)["vrfs"][vrf]["peerList"]
        return {_eor_key(p["peerAddress"]): eos_eor(p) for p in peers if isinstance(p.get("peerAddress"), str)}
    except Exception:
        return {}


def eos_eor(p: dict) -> dict[str, str]:
    """End-of-RIB per family from one EOS peer (cEOS 4.3x, captured live 2026-11-06): `endOfRibs.incoming.<afi>.status`
    read "received", then "pending" during a graceful restart, then "received". No `endOfRibs` and no graceful-restart
    capability received from the peer: untracked. Anything else: unknown. Never raises."""
    eors = p.get("endOfRibs")
    inc = eors.get("incoming") if isinstance(eors, dict) else None
    if isinstance(inc, dict) and inc:
        out = {}
        for afi, v in inc.items():
            status = v.get("status") if isinstance(v, dict) else None
            out[EOS_FAMILIES.get(afi, afi)] = status if status in ("received", "pending") else "unknown"
        return out
    caps = p.get("neighborCapabilities")
    gr = caps.get("grCaps") if isinstance(caps, dict) else None
    if eors is None and (not isinstance(gr, dict) or not gr.get("received")):
        return {"*": "untracked"}
    return {"*": "unknown"}


def parse_eos_add_path_off(text: str, vrf: str, address: str) -> set[str]:
    """The families of one EOS peer (`show ip|ipv6 bgp neighbors <peer> vrf <vrf> | json`) in which it can't send this
    node several paths per prefix: `neighborCapabilities.addPathsCaps.<afi>.receivingAddPaths.enabled` is exactly
    false (cEOS 4.36.3M advertises add-path receive by default, so it is on whenever the peer sends add-path, red team
    RT-0069). Fail-safe: output this function doesn't recognise, another peer, or a family without the entry gives no
    family, and the driver then reads prefixAccepted as a count of paths. Never raises."""
    try:
        data = json.loads(text)
    except (ValueError, RecursionError):
        return set()
    vrfs = data.get("vrfs") if isinstance(data, dict) else None
    entry = vrfs.get(vrf) if isinstance(vrfs, dict) else None
    peers = entry.get("peerList") if isinstance(entry, dict) else None
    if not isinstance(peers, list):
        return set()
    mine = [p for p in peers if isinstance(p, dict) and isinstance(p.get("peerAddress"), str)
            and _canon_addr(p.get("peerAddress")) == _canon_addr(address)]
    if len(mine) != 1:
        return set()
    caps = mine[0].get("neighborCapabilities")
    ap = caps.get("addPathsCaps") if isinstance(caps, dict) else None
    out: set[str] = set()
    for afi, name in EOS_FAMILIES.items():
        fam = ap.get(afi) if isinstance(ap, dict) else None
        rx = fam.get("receivingAddPaths") if isinstance(fam, dict) else None
        if isinstance(rx, dict) and rx.get("enabled") is False:
            out.add(name)
    return out


class EosDriver(Driver):
    name = "eos"
    # No `aggregate`: the node's own BGP aggregate is bgp, as on FRR, which refuses `protocol: aggregate` too; EOS has no
    # other aggregate route this driver maps, so the name would match nothing and pass `present: false` (RT-0086,
    # FP-043-EOSAGG). Refused before the run, never read as absent.
    route_protocols = frozenset({"bgp", "connected", "static", "ospf", "ospf6", "isis"})
    # bgp_neighbors reads the IPv4 and IPv6 unicast summaries only: an EVPN count would always read 0
    unsupported_afis = frozenset({"evpn"})
    # cEOS 4.36.3M prints "med": 0 for a path received with no MED (interop IOP-2): no output field tells them apart
    ambiguous_bgp_values = {"med": {0: "EOS output cannot tell MED 0 from no MED (check a non-zero MED, or check "
                                       "this route on another platform)"}}

    def _cli(self, command: str, evidence: list[dict]) -> str:
        return self._exec(["Cli", "-p", "15", "-c", command], evidence)

    def _bgp_cli(self, command: str, evidence: list[dict]) -> str:
        """A BGP read. On a node with no BGP configured, cEOS answers every one of them with exactly
        `{"errors": ["BGP inactive"]}` and rc 1 (cEOS 4.36.3M, eos_bgp_inactive.txt, live 2026-11-08): that, and only
        that, is NoSuchInstance (no BGP here); any other failure stays an error. A `route` check on such a node was an
        error on every sample (live, angle-5 lab A)."""
        argv = ["Cli", "-p", "15", "-c", command]
        r = self.lab.exec(self.node, argv, timeout=60)
        if r.rc == 1:
            try:
                answer = json.loads(r.stdout)
            except ValueError:
                answer = None
            if answer == BGP_INACTIVE:
                evidence.append({"node": self.node, "cmd": " ".join(argv), "rc": r.rc, "output": r.stdout[-2000:],
                                 "stderr": r.stderr[-2000:]})
                raise NoSuchInstance(f"BGP is not configured on {self.node} (`{command}`: BGP inactive)")
        evidence.append({"node": self.node, "cmd": " ".join(argv), "rc": r.rc, "output": r.stdout[-20000:],
                         "stderr": r.stderr[-2000:]})
        if r.rc != 0:
            msg = (r.stderr or r.stdout).strip().splitlines()
            raise DriverError(f"`{' '.join(argv)}` failed on {self.node} (rc={r.rc}): {msg[-1] if msg else 'no output'}")
        return r.stdout

    own_address_families = frozenset({4, 6})   # what local_addresses reads (round 4, RT-0044)

    def local_addresses(self, vrf: str = "default") -> list:
        from .addresses import parse_eos_interfaces
        vrf = check_vrf_name(vrf)
        out = []
        for cmd in ("show ip interface | json", "show ipv6 interface | json"):
            out += parse_eos_interfaces(self._cli(cmd, []), vrf, cmd)
        return out

    def end_of_rib(self, vrf: str, neighbors: dict) -> dict[str, dict[str, str]]:
        """From `show ip|ipv6 bgp neighbors vrf <vrf> | json` (the summary has no End-of-RIB); see eos_eor."""
        est = [a for a, n in neighbors.items() if n.state == "established"]
        if not est:
            return {}
        got: dict[str, dict[str, str]] = {}
        try:
            vrf = check_vrf_name(vrf)
            got.update(parse_eos_eor(self._cli(f"show ip bgp neighbors vrf {vrf} | json", []), vrf))
            if any(_eor_key(a) not in got for a in est):
                got.update(parse_eos_eor(self._cli(f"show ipv6 bgp neighbors vrf {vrf} | json", []), vrf))
        except Exception:
            pass   # unread: every session below reads unknown
        return {a: got.get(_eor_key(a)) or {"*": "unknown"} for a in est}

    def bgp_neighbors(self, vrf: str = "default") -> Observation:
        vrf = check_vrf_name(vrf)
        ev: list[dict] = []
        out: dict[str, BgpNeighbor] = {}
        parse_bgp_summary(self._bgp_cli(f"show ip bgp summary vrf {vrf} | json", ev), vrf, "ipv4-unicast", out)
        # A failing IPv6 summary (error, timeout, unreadable output) raises: swallowing it made every
        # IPv6 prefix count read 0, which passes `max` and `exact: 0`.
        parse_bgp_summary(self._bgp_cli(f"show ipv6 bgp summary vrf {vrf} | json", ev), vrf, "ipv6-unicast", out)
        self._add_path_ranges(vrf, out, ev)
        return Observation(out, ev)

    def _add_path_ranges(self, vrf: str, neighbors: dict[str, BgpNeighbor], ev: list[dict]) -> None:
        """With add-path from the peer, the summary's prefixAccepted counts paths (red team RT-0069, cEOS 4.36.3M: 2
        prefixes with 2 paths each read as 4, so `min: 4` passed). For each established peer with more than one path
        accepted in a family, read its add-path receive state; where it isn't clearly off, the P paths are 1 to P
        prefixes, judged only where the whole range agrees, otherwise no verdict (no per-neighbor listing of EOS's is
        captured to count them from). A read that fails is not clearly off."""
        for n in neighbors.values():
            fams = [afi for afi in EOS_FAMILIES.values() if n.prefixes.get(afi, 0) > 1]
            if n.state != "established" or not fams:
                continue
            try:
                ver = ipaddress.ip_address(n.address.split("%")[0]).version
            except ValueError:
                ver = 4
            cmd = f"show {'ipv6' if ver == 6 else 'ip'} bgp neighbors {n.address} vrf {vrf} | json"
            try:
                off, why = parse_eos_add_path_off(self._bgp_cli(cmd, ev), vrf, n.address), "it may send add-path"
            except DriverError as e:
                off, why = set(), f"its add-path state couldn't be read ({e})"
            for afi in fams:
                if afi in off:
                    continue
                paths = n.prefixes[afi]
                n.prefixes[afi] = 1
                n.prefixes_upto[afi] = paths
                n.prefixes_upto_why[afi] = add_path_range_why(paths)
                n.prefixes_unread[afi] = (f"{why} in {afi} (`{cmd}`), so EOS's prefixAccepted ({paths}) counts paths, "
                                          "not prefixes")

    def routes(self, prefix: str, vrf: str = "default") -> Observation:
        vrf = check_vrf_name(vrf)
        ev: list[dict] = []
        fam = "ipv6" if ipaddress.ip_network(prefix).version == 6 else "ip"
        rt = self._cli(f"show {fam} route vrf {vrf} {prefix} | json", ev)
        # every candidate, selected or not (FP-043-EOSNONBGP). A refusal (an EOS without `show rib route`) or any
        # other failure raises: an unread RIB is never "no candidate"
        rib = self._cli(f"show rib route {fam} vrf {vrf} {prefix} | json", ev)
        try:
            bgp = self._bgp_cli(f"show {fam} bgp {prefix} vrf {vrf} | json", ev)
        except NoSuchInstance:
            bgp = None   # no BGP on the node: no BGP path (the routing table answer above confirmed the VRF)
        return Observation(parse_routes(rt, bgp, prefix, vrf, rib), ev)

    def bgp_paths(self, prefix: str, vrf: str = "default") -> Observation:
        vrf = check_vrf_name(vrf)
        ev: list[dict] = []
        fam = "ipv6" if ipaddress.ip_network(prefix).version == 6 else "ip"
        try:
            text = self._bgp_cli(f"show {fam} bgp {prefix} vrf {vrf} | json", ev)
        except NoSuchInstance:
            # no BGP on the node: no BGP path, once the VRF itself is shown to exist (its routing table answers)
            parse_routes(self._cli(f"show {fam} route vrf {vrf} {prefix} | json", ev), None, prefix, vrf)
            return Observation([], ev)
        return Observation(parse_bgp_paths(text, prefix, vrf), ev)

    def all_routes(self, vrf: str = "default", family: int = 4) -> Observation:
        vrf = check_vrf_name(vrf)
        ev: list[dict] = []
        fam = "ipv6" if family == 6 else "ip"
        return Observation(parse_all_routes(self._cli(f"show {fam} route vrf {vrf} | json", ev), vrf), ev)

    def ping(self, target: str, source: str | None, count: int, vrf: str = "default") -> Observation:
        vrf = check_vrf_name(vrf)
        ev: list[dict] = []
        fam = "ipv6 " if ipaddress.ip_address(target).version == 6 else ""
        cmd = f"ping {fam}vrf {vrf} {target} repeat {count}" + (f" source {source}" if source else "")
        from ..mgmt import check_node   # no route out over Management0, before and after (B3, R5)
        check_node(self.lab, self.node, f"before the ping to {target}")
        r = self.lab.exec(self.node, ["Cli", "-p", "15", "-c", cmd], timeout=count * 2 + 15)
        ev.append({"node": self.node, "cmd": f"Cli -c {cmd}", "rc": r.rc, "output": r.stdout[-5000:], "stderr": r.stderr[-1000:]})
        check_node(self.lab, self.node, f"after the ping to {target}")
        return Observation(parse_ping(r.stdout), ev)
