"""Nokia SR Linux driver: sr_cli JSON state, ping from the network-instance namespace.

sr_cli answers `{}` for a state path with no entries. Before an empty answer is trusted for a
network-instance other than default, the driver confirms the instance exists (its oper-state): a
typo in a VRF name must never read as "no routes". Output with a structure the parsers don't know
raises; it is never read as empty.
"""
from __future__ import annotations

import ipaddress

from .base import (BgpNeighbor, BgpPath, Driver, DriverError, NoSuchInstance, Observation, Route, as_int, canon_communities,
                   check_vrf_name, load_json, network, parser, render_as_path, unexpected)
from .frr import _canon_addr, _keep_down, parse_ping

# SR Linux route-type names -> the shared vocabulary used in netdryrun.yml (FRR's names)
PROTOCOLS = {"local": "connected", "host": "local", "ospfv2": "ospf", "ospfv3": "ospf6"}


def _protocol(rtype: str) -> str:
    """Every BGP route type (bgp, bgp-evpn, bgp-vpn, bgp-label, ...) was learned via BGP, so `protocol: bgp`
    (and its guards) match it."""
    return "bgp" if rtype.startswith("bgp") else PROTOCOLS.get(rtype, rtype)

NEIGHBORS_CMD = "info from state /network-instance <vrf> protocols bgp neighbor *"
ROUTE_CMD = "info from state /network-instance <vrf> route-table <afi> route <prefix>"
RIB_CMD = "info from state /network-instance <vrf> bgp-rib ... local-rib route <prefix>"
ATTR_CMD = "info from state /network-instance <vrf> bgp-rib attr-sets attr-set <id>"
INSTANCE_CMD = "info from state /network-instance <vrf> oper-state"


def _json(text: str, command: str = "sr_cli") -> dict:
    data = load_json(command, text)
    if not isinstance(data, dict):
        raise unexpected(command, text)
    return data


def _list(command: str, data: dict, key: str) -> list[dict]:
    """The one list a state answer holds: `{}` (no entries) or `{key: [entry, ...]}`."""
    if not data:
        return []
    rows = data.get(key)
    if not isinstance(rows, list):
        raise unexpected(command, data)
    for r in rows:
        if not isinstance(r, dict):
            raise unexpected(command, f"{key}: {str(r)[:150]}")
    return rows


SRL_DEFAULT_ADV_INTERVAL = 5   # seconds (SR Linux's default minimum-advertisement-interval)


@parser(NEIGHBORS_CMD)
def parse_bgp_neighbors(text: str) -> dict[str, BgpNeighbor]:
    out = {}
    for n in _list(NEIGHBORS_CMD, _json(text, NEIGHBORS_CMD), "neighbor"):
        addr, state = n.get("peer-address"), n.get("session-state")
        if not isinstance(addr, str) or not addr or not isinstance(state, str) or not state:
            raise unexpected(NEIGHBORS_CMD, str(n)[:150])
        families = n.get("afi-safi", None if state.lower() == "established" else [])
        if not isinstance(families, list):  # an established session always lists its families
            raise unexpected(NEIGHBORS_CMD, f"{addr}: no afi-safi list")
        prefixes = {}
        for af in families:
            if "received-routes" in af:  # families without counters (evpn) are skipped; see unsupported_afis
                # accepted = received minus rejected by import policy (matches FRR's acceptedPrefixCounter)
                prefixes[str(af["afi-safi-name"])] = (as_int(NEIGHBORS_CMD, af["received-routes"])
                                                      - as_int(NEIGHBORS_CMD, af.get("rejected-routes", 0)))
        # SR Linux's minimum-advertisement-interval, 5 s by default where the state doesn't list it
        timers = n.get("timers") if isinstance(n.get("timers"), dict) else {}
        adv = float(as_int(NEIGHBORS_CMD, timers.get("minimum-advertisement-interval", SRL_DEFAULT_ADV_INTERVAL)))
        _keep_down(out, _canon_addr(addr), BgpNeighbor(addr, state.lower(), prefixes, adv_interval=adv))
    return out


def _bgp_learned(row: dict) -> bool:
    """SR Linux lists the router's own static and interface routes in its BGP local-RIB as locally
    originated paths (neighbor 0.0.0.0, origin-protocol static, ...), whether or not an export policy
    advertises them. Only paths with origin-protocol bgp were learned over BGP."""
    return str(row.get("origin-protocol", "bgp")).lower() == "bgp"


def _received(row: dict) -> bool:
    """False for a path SR Linux keeps in its local RIB after import policy rejected it (`invalid-reason:
    {rejected-route: true}`): FRR, EOS and Junos keep no such path and it can never be used, so it was not
    received (interop IOP-6). Any other invalid reason is one this driver hasn't seen: an error, never a guess."""
    why = row.get("invalid-reason")
    if why is None:
        return True
    if not isinstance(why, dict) or not all(isinstance(v, bool) for v in why.values()):
        raise unexpected(RIB_CMD, f"invalid-reason {str(why)[:100]}")
    reasons = sorted(k for k, v in why.items() if v)
    if any(k != "rejected-route" for k in reasons):
        raise DriverError(f"{row.get('prefix')}: the path from {row.get('neighbor')} is invalid for "
                          f"{', '.join(reasons)}, a reason the srlinux driver doesn't read yet")
    return not reasons


def _rib_rows(text: str, prefix: str) -> list[dict]:
    """Local-RIB paths for exactly `prefix`, leaving out those import policy rejected (see _received)."""
    want = ipaddress.ip_network(prefix)
    rows = _list(RIB_CMD, _json(text, RIB_CMD), "route")
    for r in rows:
        if "prefix" not in r:
            raise unexpected(RIB_CMD, str(r)[:150])
    return [r for r in rows if network(RIB_CMD, r["prefix"]) == want and _received(r)]


@parser(ROUTE_CMD)
def parse_routes(text: str, prefix: str, bgp_rib_text: str | None = None) -> list[Route]:
    """Route-table entries for `prefix`, plus BGP-RIB paths that aren't installed.

    SR Linux's route table only holds installed routes. A BGP path that lost to a static or local
    route (a leak that's received but not selected) only shows in the BGP RIB, and must still count
    as present for `present: false`, valid or not (an unresolved next hop), as on EOS and FRR. The
    static itself also shows there, as a locally originated path: that one is not a BGP route.
    """
    want = ipaddress.ip_network(prefix)
    key = "ipv6-prefix" if want.version == 6 else "ipv4-prefix"
    out = []
    for r in _list(ROUTE_CMD, _json(text, ROUTE_CMD), "route"):
        if key not in r:
            raise unexpected(ROUTE_CMD, str(r)[:150])
        if network(ROUTE_CMD, r[key]) != want:
            continue
        rtype = str(r.get("route-type", "")).lower()
        out.append(Route(prefix, _protocol(rtype), bool(r.get("active"))))
    if bgp_rib_text is not None and not any(r.protocol == "bgp" and r.active for r in out):
        if any(_bgp_learned(r) for r in _rib_rows(bgp_rib_text, prefix)):
            out.append(Route(prefix, "bgp", False))
    return out


@parser(RIB_CMD)
def parse_rib_paths(text: str, prefix: str) -> list[dict]:
    """Local-RIB entries for exactly `prefix`, best path first: neighbor, best-route, attr-id."""
    return sorted(_rib_rows(text, prefix), key=lambda r: not r.get("best-route"))


@parser(ATTR_CMD)
def parse_attr_set(text: str, row: dict, default_local_pref: int | None = None) -> BgpPath:
    """A local-RIB entry plus its attr-set. The attr-set has no local-pref when the path carries none
    (eBGP-learned or local); SR Linux then applies the neighbor's configured local-preference."""
    a = _json(text, ATTR_CMD)
    if not a:
        raise DriverError(f"attr-set {row.get('attr-id')} for {row.get('prefix')} not found")
    segs = [(s.get("type", ""), s.get("member") or []) for s in (a.get("as-path") or {}).get("segment") or []]
    comms = a.get("communities") or {}
    nh = a.get("next-hop")
    return BgpPath(
        best=bool(row.get("best-route")),
        as_path=render_as_path(segs),
        next_hop=_canon_addr(str(nh)) if nh else None,
        local_pref=as_int(ATTR_CMD, a["local-pref"]) if "local-pref" in a else default_local_pref,
        med=as_int(ATTR_CMD, a["med"]) if "med" in a else None,   # no MED attribute: unknown, not 0
        communities=canon_communities(comms.get("community")),
        large_communities=canon_communities(comms.get("large-community")),
        neighbor=row.get("neighbor"),
        local_candidate=not _bgp_learned(row),
    )


def _find(data, key: str):
    """The first value of `key` anywhere in a JSON answer."""
    if isinstance(data, dict):
        if key in data:
            return data[key]
        data = list(data.values())
    if isinstance(data, list):
        for v in data:
            found = _find(v, key)
            if found is not None:
                return found
    return None


def parse_instance_state(text: str) -> str | None:
    """`info from state /network-instance X oper-state`: the oper-state, None when the instance is absent."""
    state = _find(_json(text, INSTANCE_CMD), "oper-state")
    return state if isinstance(state, str) and state else None


def _ip_or_none(addr) -> str | None:
    try:
        return str(ipaddress.ip_address(str(addr)))
    except ValueError:
        return None


def unread_path(row: dict) -> BgpPath:
    """A path whose attributes were not read (only the first path's are: the best one if any)."""
    return BgpPath(best=bool(row.get("best-route")), as_path=None, next_hop=None, local_pref=None, med=None,
                   neighbor=row.get("neighbor"), local_candidate=not _bgp_learned(row))


class SrlDriver(Driver):
    name = "srlinux"
    # bgp_neighbors reads received-routes counters, which SR Linux has for IPv4 and IPv6 unicast but not for
    # evpn (skipped): an EVPN count would always read 0, which passes max and exact: 0
    unsupported_afis = frozenset({"evpn"})

    def _cli(self, command: str, evidence: list[dict]) -> str:
        return self._exec(["sr_cli", "--output-format", "json", command], evidence)

    def _confirm_vrf(self, vrf: str, evidence: list[dict]) -> None:
        """Before an empty answer is trusted: a path under a network-instance that doesn't exist
        answers like one with no entries, so read the instance's oper-state."""
        if vrf == "default":
            return
        if parse_instance_state(self._cli(f"info from state /network-instance {vrf} oper-state", evidence)) is None:
            raise NoSuchInstance(f"network-instance {vrf!r} does not exist on {self.node} (no oper-state)")

    def bgp_neighbors(self, vrf: str = "default") -> Observation:
        vrf = check_vrf_name(vrf)
        ev: list[dict] = []
        neighbors = parse_bgp_neighbors(self._cli(f"info from state /network-instance {vrf} protocols bgp neighbor *", ev))
        if not neighbors:
            self._confirm_vrf(vrf, ev)
        return Observation(neighbors, ev)

    def routes(self, prefix: str, vrf: str = "default") -> Observation:
        vrf = check_vrf_name(vrf)
        ev: list[dict] = []
        table = "ipv6-unicast" if ipaddress.ip_network(prefix).version == 6 else "ipv4-unicast"
        text = self._cli(
            f"info from state /network-instance {vrf} route-table {table} route {prefix} "
            "id * route-type * route-owner * origin-network-instance *",
            ev,
        )
        rib = self._cli(
            f"info from state /network-instance {vrf} bgp-rib afi-safi {table} {table} local-rib route {prefix} "
            "neighbor * origin-protocol * path-id *",
            ev,
        )
        routes = parse_routes(text, prefix, rib)
        if not routes:
            self._confirm_vrf(vrf, ev)
        return Observation(routes, ev)

    def bgp_paths(self, prefix: str, vrf: str = "default") -> Observation:
        vrf = check_vrf_name(vrf)
        ev: list[dict] = []
        table = "ipv6-unicast" if ipaddress.ip_network(prefix).version == 6 else "ipv4-unicast"
        rows = parse_rib_paths(self._cli(
            f"info from state /network-instance {vrf} bgp-rib afi-safi {table} {table} local-rib route {prefix} "
            "neighbor * origin-protocol * path-id *", ev), prefix)
        if not rows:
            self._confirm_vrf(vrf, ev)
            return Observation([], ev)
        # Best path first: one attr-set read per sample, not one per path. When the best is the router's own
        # route (a local candidate), also read the first path learned over BGP: that's the one a
        # `present: false` failure describes.
        learned = next((r for r in rows if _bgp_learned(r)), None)
        read = {0} | ({rows.index(learned)} if learned is not None and not _bgp_learned(rows[0]) else set())
        return Observation([self._read_path(r, vrf, ev) if n in read else unread_path(r) for n, r in enumerate(rows)], ev)

    def _read_path(self, row: dict, vrf: str, ev: list[dict]) -> BgpPath:
        # attr-id and neighbor come from device output and go back into a CLI string: only a number and an IP
        attr_id = str(row.get("attr-id"))
        if not attr_id.isdigit():
            raise DriverError(f"unexpected attr-id {attr_id[:40]!r} for {row.get('prefix')}")
        attrs = self._cli(f"info from state /network-instance {vrf} bgp-rib attr-sets attr-set {attr_id}", ev)
        default_lp = None
        neighbor = _ip_or_none(row.get("neighbor"))
        # The router's own routes (neighbor 0.0.0.0) have no neighbor to ask. For a learned path, a failing
        # lookup is an error, never a silently unknown local-pref.
        if "local-pref" not in _json(attrs, ATTR_CMD) and neighbor and _bgp_learned(row) \
                and not ipaddress.ip_address(neighbor).is_unspecified:
            state = _json(self._cli(f"info from state /network-instance {vrf} protocols bgp neighbor "
                                    f"{neighbor} local-preference", ev), NEIGHBORS_CMD)
            lp = state.get("local-preference")
            default_lp = as_int(NEIGHBORS_CMD, lp) if lp is not None else None
        return parse_attr_set(attrs, row, default_lp)

    def all_routes(self, vrf: str = "default", family: int = 4) -> Observation:
        vrf = check_vrf_name(vrf)
        ev: list[dict] = []
        table, key = ("ipv6-unicast", "ipv6-prefix") if family == 6 else ("ipv4-unicast", "ipv4-prefix")
        text = self._cli(f"info from state /network-instance {vrf} route-table {table} route * "
                         "id * route-type * route-owner * origin-network-instance *", ev)
        routes = parse_all_routes(text, key)
        if not routes:
            self._confirm_vrf(vrf, ev)
        return Observation(routes, ev)

    def _netns(self, vrf: str) -> str:
        """Linux namespace of a network-instance: srbase-<name>; some releases name default plain 'srbase'."""
        r = self.lab.exec(self.node, ["ip", "netns", "list"], timeout=15)
        names = {line.split()[0] for line in r.stdout.splitlines() if line.strip()}
        wanted = f"srbase-{vrf}"
        if wanted in names or vrf != "default":
            return wanted
        return "srbase" if "srbase" in names else wanted

    def ping(self, target: str, source: str | None, count: int, vrf: str = "default") -> Observation:
        vrf = check_vrf_name(vrf)
        ev: list[dict] = []
        ping = "ping6" if ipaddress.ip_address(target).version == 6 else "ping"
        cmd = ["ip", "netns", "exec", self._netns(vrf), ping, "-c", str(count), "-W", "1"]
        if source:
            cmd += ["-I", source]
        cmd.append(target)
        r = self.lab.exec(self.node, cmd, timeout=count * 2 + 10)
        ev.append({"node": self.node, "cmd": " ".join(cmd), "rc": r.rc, "output": r.stdout[-5000:], "stderr": r.stderr[-1000:]})
        return Observation(parse_ping(r.stdout), ev)


@parser("info from state /network-instance <vrf> route-table <afi> route *")
def parse_all_routes(text: str, key: str = "ipv4-prefix") -> list[Route]:
    cmd = "info from state /network-instance <vrf> route-table <afi> route *"
    out = []
    for r in _list(cmd, _json(text, cmd), "route"):
        if key not in r:
            raise unexpected(cmd, str(r)[:150])
        rtype = str(r.get("route-type", "")).lower()
        out.append(Route(str(network(cmd, r[key])), _protocol(rtype), bool(r.get("active"))))
    return out
