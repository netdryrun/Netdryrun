"""Arista EOS (cEOS-lab) driver: `Cli ... | json` state, ping from the EOS CLI.

Routes are read from both the routing table (active routes) and the BGP table, because a
received-but-not-selected BGP path only appears in the BGP table and must still count as present
for `present: false` checks.

EOS keys every answer by VRF (`{"vrfs": {name: ...}}`). A VRF missing from that map is never read as
"no routes": the VRF doesn't exist, or the output isn't what this driver knows. Both raise.
"""
from __future__ import annotations

import re

import ipaddress

from .base import (BgpNeighbor, BgpPath, Driver, DriverError, NoSuchInstance, Observation, Route, as_int, canon_communities,
                   check_vrf_name, load_json, network, parser, unexpected)
from .frr import _canon_addr, parse_ping

PROTOCOLS = {"ebgp": "bgp", "ibgp": "bgp", "bgp": "bgp", "connected": "connected", "static": "static",
             "ospf": "ospf", "ospfintraarea": "ospf", "ospfinterarea": "ospf", "ospfexternaltype1": "ospf",
             "ospfexternaltype2": "ospf", "isis": "isis", "isislevel1": "isis", "isislevel2": "isis",
             "aggregate": "aggregate", "droproute": "static", "dropped": "static"}  # static discard (Null0)

SUMMARY_CMD = {"ipv4-unicast": "show ip bgp summary | json", "ipv6-unicast": "show ipv6 bgp summary | json"}
ROUTE_CMD = "show ip route <prefix> | json"
ALL_ROUTES_CMD = "show ip route | json"
BGP_CMD = "show ip bgp <prefix> | json"


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
        n = out.get(key) or BgpNeighbor(str(addr), state)
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
    peer = p.get("peerEntry")
    if not isinstance(peer, dict) or not isinstance(peer.get("peerAddr"), str):  # "" for its own paths
        raise unexpected(BGP_CMD, f"path without peerEntry: {str(p)[:150]}")
    return bool(peer["peerAddr"])


def _bgp_entries(command: str, text: str, vrf: str) -> dict:
    entry = _vrf(command, _json(command, text), vrf)
    entries = _table(command, entry, "bgpRouteEntries")
    for key, e in entries.items():
        if not isinstance(e, dict) or not isinstance(e.get("bgpRoutePaths"), list):
            raise unexpected(command, f"{key}: {str(e)[:150]}")
        for p in e["bgpRoutePaths"]:
            if not isinstance(p, dict):
                raise unexpected(command, f"{key} path: {str(p)[:150]}")
    return entries


@parser(ROUTE_CMD)
def parse_routes(route_text: str, bgp_text: str, prefix: str, vrf: str = "default") -> list[Route]:
    want = ipaddress.ip_network(prefix)
    out = []
    for key, r in _table(ROUTE_CMD, _vrf(ROUTE_CMD, _json(ROUTE_CMD, route_text), vrf), "routes").items():
        if not isinstance(r, dict):
            raise unexpected(ROUTE_CMD, f"{key}: {str(r)[:150]}")
        if network(ROUTE_CMD, key) == want:
            rtype = str(r.get("routeType", "")).lower().replace(" ", "")
            out.append(Route(prefix, PROTOCOLS.get(rtype, rtype), True))
    # A BGP path can be "best" inside BGP and still not be installed (a static or connected route with
    # a better preference wins the routing table). Unless BGP is the installed route, every BGP path
    # learned from a neighbor, valid or not, is "present but not selected": a leak that must still fail
    # `present: false`.
    has_installed_bgp = any(r.protocol == "bgp" for r in out)
    for key, e in _bgp_entries(BGP_CMD, bgp_text, vrf).items():
        if network(BGP_CMD, key) != want:
            continue
        if not has_installed_bgp and any(_learned(p) for p in e["bgpRoutePaths"]):
            out.append(Route(prefix, "bgp", False))
            break
    return out


@parser(ALL_ROUTES_CMD)
def parse_all_routes(text: str, vrf: str = "default") -> list[Route]:
    out = []
    for key, r in _table(ALL_ROUTES_CMD, _vrf(ALL_ROUTES_CMD, _json(ALL_ROUTES_CMD, text), vrf), "routes").items():
        if not isinstance(r, dict):
            raise unexpected(ALL_ROUTES_CMD, f"{key}: {str(r)[:150]}")
        rtype = str(r.get("routeType", "")).lower().replace(" ", "")
        out.append(Route(str(network(ALL_ROUTES_CMD, key)), PROTOCOLS.get(rtype, rtype), True))
    return out


@parser(BGP_CMD)
def parse_bgp_paths(text: str, prefix: str, vrf: str = "default") -> list[BgpPath]:
    """`show ip bgp <prefix> vrf <vrf> | json`: the best path is the one EOS marks active.
    A locally originated path has no localPreference or med field; it carries neither attribute.
    Every path is listed, valid or not, active or not."""
    want = ipaddress.ip_network(prefix)
    out = []
    for key, e in _bgp_entries(BGP_CMD, text, vrf).items():
        if network(BGP_CMD, key) != want:
            continue
        for p in e["bgpRoutePaths"]:
            detail = p.get("routeDetail") or {}
            nh = p.get("nextHop") or ""
            out.append(BgpPath(
                best=bool((p.get("routeType") or {}).get("active")),
                as_path=" ".join(str((p.get("asPathEntry") or {}).get("asPath", "")).split()),
                next_hop=_canon_addr(str(nh)) if nh else None,
                local_pref=as_int(BGP_CMD, p["localPreference"]) if "localPreference" in p else None,
                med=as_int(BGP_CMD, p["med"]) if "med" in p else None,   # no MED attribute: unknown, not 0
                communities=canon_communities(detail.get("communityList")),
                large_communities=canon_communities(detail.get("largeCommunityList")),
                neighbor=(p.get("peerEntry") or {}).get("peerAddr") or None,
            ))
    return out


class EosDriver(Driver):
    name = "eos"
    # bgp_neighbors reads the IPv4 and IPv6 unicast summaries only: an EVPN count would always read 0
    unsupported_afis = frozenset({"evpn"})

    def _cli(self, command: str, evidence: list[dict]) -> str:
        return self._exec(["Cli", "-p", "15", "-c", command], evidence)

    def bgp_neighbors(self, vrf: str = "default") -> Observation:
        vrf = check_vrf_name(vrf)
        ev: list[dict] = []
        out: dict[str, BgpNeighbor] = {}
        parse_bgp_summary(self._cli(f"show ip bgp summary vrf {vrf} | json", ev), vrf, "ipv4-unicast", out)
        # A failing IPv6 summary (error, timeout, unreadable output) raises: swallowing it made every
        # IPv6 prefix count read 0, which passes `max` and `exact: 0`.
        parse_bgp_summary(self._cli(f"show ipv6 bgp summary vrf {vrf} | json", ev), vrf, "ipv6-unicast", out)
        return Observation(out, ev)

    def routes(self, prefix: str, vrf: str = "default") -> Observation:
        vrf = check_vrf_name(vrf)
        ev: list[dict] = []
        fam = "ipv6" if ipaddress.ip_network(prefix).version == 6 else "ip"
        rt = self._cli(f"show {fam} route vrf {vrf} {prefix} | json", ev)
        bgp = self._cli(f"show {fam} bgp {prefix} vrf {vrf} | json", ev)
        return Observation(parse_routes(rt, bgp, prefix, vrf), ev)

    def bgp_paths(self, prefix: str, vrf: str = "default") -> Observation:
        vrf = check_vrf_name(vrf)
        ev: list[dict] = []
        fam = "ipv6" if ipaddress.ip_network(prefix).version == 6 else "ip"
        return Observation(parse_bgp_paths(self._cli(f"show {fam} bgp {prefix} vrf {vrf} | json", ev), prefix, vrf), ev)

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
        r = self.lab.exec(self.node, ["Cli", "-p", "15", "-c", cmd], timeout=count * 2 + 15)
        ev.append({"node": self.node, "cmd": f"Cli -c {cmd}", "rc": r.rc, "output": r.stdout[-5000:], "stderr": r.stderr[-1000:]})
        return Observation(parse_ping(r.stdout), ev)
