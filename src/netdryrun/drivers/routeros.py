"""MikroTik RouterOS 7 (CHR in containerlab, kind mikrotik_ros) driver, read through the REST API.

Beta, bring your own image. The router is a VM inside the container, and the host cannot reach its management address, so
every request runs inside the container (a small Python helper, `routeros_rest.HELPER`). What the first live capture
taught is in `routeros_rest.py` and `routeros_state.py`; the rules this driver adds:

- A routing table (VRF) is confirmed from `/routing/table` before anything is read from it: an unknown table answers 200
  with an empty list, exactly like an empty one.
- Session state comes from `/routing/bgp/session` and `/routing/bgp/connection`. A connection that cannot start has no
  session row; it is reported as not established, never as absent. The `prefix-count` counter is the RECEIVED count, so the
  accepted count is derived from the routing route table (paths of that session that policy did not filter).
- A route is present when BGP received it and policy accepted it, installed or not (`best-candidate`: received but not
  selected, the leaked-default shape), as on the other drivers; a policy-filtered path is not a route.
- Not supported, and refused with a clear message rather than answered: IPv6 sessions and routes, ping inside a VRF, and
  any route row, key or value the parsers do not know (graceful-restart stale marks included).
"""
from __future__ import annotations

import ipaddress

from .base import BgpNeighbor, BgpPath, Driver, DriverError, NoSuchInstance, Observation, Route, canon_communities, check_vrf_name
from .routeros_rest import HELPER, Reply, classify_reply
from .routeros_state import (
    RoutingRoute,
    accepted_prefixes,
    parse_connections,
    parse_ping,
    parse_routing_routes,
    parse_sessions,
    parse_tables,
)

# containerlab's mikrotik_ros kind sets admin:admin (kind docs); the lab is throwaway and never reachable from outside
_CRED = "admin:admin"
_ROUTE_KINDS = ("bgp", "static", "connected")


def _table(vrf: str) -> str:
    return "main" if vrf == "default" else vrf


class RouterosDriver(Driver):
    name = "routeros"
    unsupported_afis = frozenset({"ipv6-unicast", "evpn"})

    def _rest(self, method: str, path: str, evidence: list[dict], body: str = "", timeout: float = 90) -> Reply:
        """One REST request inside the container. Evidence never carries the credentials."""
        shown = f"REST {method} {path}" + (f" {body}" if body else "")
        r = self.lab.exec(self.node, ["python3", "-c", HELPER, method, path, _CRED, body], timeout=timeout)
        head, _, payload = r.stdout.partition("\n")
        status = int(head) if head.strip().isdigit() and len(head.strip()) == 3 else 0
        evidence.append({"node": self.node, "cmd": shown, "rc": r.rc, "output": payload[-20000:], "stderr": r.stderr[-2000:]})
        if r.rc != 0:
            msg = (r.stderr or r.stdout).strip().splitlines()
            raise DriverError(f"`{shown}` failed on {self.node} (rc={r.rc}): {msg[-1] if msg else 'no output'}")
        return classify_reply(shown, status, payload).require_ok()

    def _rows(self, path: str, evidence: list[dict]) -> list[dict]:
        reply = self._rest("GET", path, evidence)
        if reply.kind == "empty_list":
            return []
        if reply.kind != "rows":
            raise DriverError(f"`GET {path}` on {self.node}: expected a list of rows, got {reply.kind}")
        return list(reply.rows)

    def _confirm_table(self, vrf: str, evidence: list[dict]) -> str:
        """The routing table behind a VRF name, confirmed to exist. `main` always exists."""
        table = _table(vrf)
        if vrf == "default":
            return table
        tables = parse_tables(self._rows("/routing/table", evidence))
        if table not in tables:
            raise NoSuchInstance(f"VRF {vrf!r} does not exist on {self.node} "
                                 f"(`/routing/table` lists: {', '.join(sorted(tables)) or 'none'})")
        if not tables[table]:
            raise NoSuchInstance(f"VRF {vrf!r} is configured on {self.node} but its routing table is invalid")
        return table

    def _paths(self, table: str, evidence: list[dict], prefix: str | None = None) -> list[RoutingRoute]:
        query = f"routing-table={table}" if prefix is None else f"dst-address={prefix}&routing-table={table}"
        return parse_routing_routes(self._rows(f"/routing/route?{query}", evidence))

    @staticmethod
    def _v4_prefix(prefix: str) -> str:
        net = ipaddress.ip_network(prefix, strict=False)
        if net.version != 4:
            raise DriverError(f"{prefix}: IPv6 routes are not supported on routeros yet")
        return str(net)

    def bgp_neighbors(self, vrf: str = "default") -> Observation:
        vrf = check_vrf_name(vrf)
        ev: list[dict] = []
        table = self._confirm_table(vrf, ev)
        sessions = [s for s in parse_sessions(self._rows("/routing/bgp/session", ev)) if s.vrf == vrf]
        connections = [c for c in parse_connections(self._rows("/routing/bgp/connection", ev)) if c.vrf == vrf]
        for s in sessions:
            if s.afi != "ip":
                raise DriverError(f"BGP session {s.name} ({s.remote_address}) is {s.afi}: IPv6 sessions are not supported on routeros yet")
        paths = self._paths(table, ev) if any(s.established for s in sessions) else []
        out: dict[str, BgpNeighbor] = {}
        for s in sessions:
            n = BgpNeighbor(s.remote_address, "established" if s.established else "active")
            if s.established:
                n.prefixes["ipv4-unicast"] = len(accepted_prefixes(paths, s.name))
            out[s.remote_address] = n
        for c in connections:
            # configured but with no session row: a connection that cannot start is idle (its reason stays in the
            # evidence), one that is merely waiting is active. Neither is established
            out.setdefault(c.remote_address, BgpNeighbor(c.remote_address, "idle" if c.inactive else "active"))
        return Observation(out, ev)

    def routes(self, prefix: str, vrf: str = "default") -> Observation:
        vrf = check_vrf_name(vrf)
        prefix = self._v4_prefix(prefix)
        ev: list[dict] = []
        table = self._confirm_table(vrf, ev)
        found = [Route(prefix, p.kind, p.active) for p in self._paths(table, ev, prefix)
                 if p.kind in _ROUTE_KINDS and p.prefix == prefix and not p.filtered]
        return Observation(found, ev)

    def all_routes(self, vrf: str = "default", family: int = 4) -> Observation:
        vrf = check_vrf_name(vrf)
        if family == 6:
            raise DriverError("IPv6 routes are not supported on routeros yet")
        ev: list[dict] = []
        table = self._confirm_table(vrf, ev)
        found = [Route(p.prefix, p.kind, p.active) for p in self._paths(table, ev)
                 if p.kind in _ROUTE_KINDS and p.prefix and not p.link_local and not p.filtered and ":" not in p.prefix]
        return Observation(found, ev)

    def bgp_paths(self, prefix: str, vrf: str = "default") -> Observation:
        vrf = check_vrf_name(vrf)
        prefix = self._v4_prefix(prefix)
        ev: list[dict] = []
        table = self._confirm_table(vrf, ev)
        received = [p for p in self._paths(table, ev, prefix) if p.kind == "bgp" and p.prefix == prefix and not p.filtered]
        addresses = {}
        if received:
            addresses = {s.name: s.remote_address for s in parse_sessions(self._rows("/routing/bgp/session", ev))}
        out = []
        for p in received:
            out.append(BgpPath(
                best=p.contribution in ("active", "best-candidate"),
                as_path=None if p.as_path is None else " ".join(str(a) for a in p.as_path),
                next_hop=p.gateway,
                local_pref=p.local_pref,          # None when the path carries none: the default is not read, so a check fails
                med=p.med,
                communities=canon_communities(p.communities),
                large_communities=canon_communities(p.large_communities),
                neighbor=addresses.get(p.session or ""),
            ))
        return Observation(out, ev)

    def ping(self, target: str, source: str | None, count: int, vrf: str = "default") -> Observation:
        vrf = check_vrf_name(vrf)
        if vrf != "default":
            raise DriverError("ping inside a VRF is not supported on routeros yet")
        ev: list[dict] = []
        request = {"address": target, "count": str(count)}
        if source:
            request["src-address"] = source
        import json
        reply = self._rest("POST", "/ping", ev, body=json.dumps(request, separators=(",", ":")), timeout=count * 3 + 30)
        if reply.kind != "rows":
            raise DriverError(f"`POST /ping` on {self.node}: expected probe rows, got {reply.kind}")
        return Observation(parse_ping(list(reply.rows)), ev)
