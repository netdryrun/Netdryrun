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

from .base import (BgpNeighbor, BgpPath, Driver, DriverError, NoSuchInstance, Observation, Route, canon_communities,
                   check_vrf_name, unexpected)
from .routeros_rest import HELPER, Reply, classify_reply
from .routeros_state import (
    RoutingRoute,
    accepted_prefixes,
    parse_connections,
    parse_import_log,
    parse_ping,
    parse_routing_routes,
    parse_sessions,
    parse_tables,
    parse_version,
)

# containerlab's mikrotik_ros kind sets admin:admin (kind docs); the lab is throwaway and never reachable from outside
_CRED = "admin:admin"
_ROUTE_KINDS = ("bgp", "static", "connected")


def _table(vrf: str) -> str:
    return "main" if vrf == "default" else vrf


class RouterosDriver(Driver):
    name = "routeros"
    route_protocols = frozenset({"bgp", "connected", "static"})
    unsupported_afis = frozenset({"ipv6-unicast", "evpn"})
    # RouterOS lists `bgp.med: "0"` for a path received with no MED (FRR's network statements, live CHR 7.23.8), and none
    # for its own: 0 can't be told from no MED, so it is unknown and a `med: 0` check is refused before deploying
    ambiguous_bgp_values = {"med": {0: "RouterOS output cannot tell MED 0 from no MED (check a non-zero MED, or check "
                                       "this route on another platform)"}}
    # RouterOS leaves bgp.communities out of a path that carries none (live CHR 7.23.8), so a missing key can't be told
    # from one it didn't print: `without_communities` could pass on what it never saw (Layer 6 on b03cb7a). A
    # `communities` check can't pass on a missing key (the communities it requires are missing too)
    unsupported_bgp_attributes = frozenset({"without_communities"})

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
        paths = parse_routing_routes(self._rows(f"/routing/route?{query}", evidence))
        # the query filters on both: a row for another prefix or table is an answer this driver doesn't know, never
        # "that prefix isn't there" (dropped, it made `present: false` pass). Pseudo rows (an interface, a scoped
        # link-local) carry no prefix and name no other one.
        for p in paths if prefix is not None else []:
            if p.table != table or (p.prefix is not None and p.prefix != prefix):
                raise unexpected("/routing/route", f"a row for {p.prefix} in table {p.table} in the answer for {prefix} "
                                                   f"in table {table}")
        return paths

    @staticmethod
    def _v4_prefix(prefix: str) -> str:
        net = ipaddress.ip_network(prefix, strict=False)
        if net.version != 4:
            raise DriverError(f"{prefix}: IPv6 routes are not supported on routeros yet")
        return str(net)

    own_address_families = frozenset({4, 6})   # what local_addresses reads (round 4, RT-0044)

    def local_addresses(self, vrf: str = "default") -> list:
        from .addresses import parse_routeros_addresses
        vrf = check_vrf_name(vrf)
        out = []
        for path in ("/ip/address", "/ipv6/address"):
            out += parse_routeros_addresses(self._rows(path, []), vrf, f"GET {path}")
        return out

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
            n = BgpNeighbor(s.remote_address, "established" if s.established else "active", eor=dict(s.eor))
            if s.established:
                # prefix-count is what the session received: accepted plus filtered paths, every one listed in the
                # table (live CHR 7.23.8). A table that lists another number was cut or misread (Layer 6 on b03cb7a)
                listed = {p.prefix for p in paths if p.kind == "bgp" and p.session == s.name and p.prefix}
                if s.received_count is not None and len(listed) != s.received_count:
                    raise DriverError(f"BGP session {s.name} ({s.remote_address}) received {s.received_count} prefixes "
                                      f"(prefix-count) but the table lists {len(listed)} of its paths")
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
        rows = self._paths(table, ev, prefix)
        received = [p for p in rows if p.kind == "bgp" and p.prefix == prefix and not p.filtered]
        # RouterOS lists the node's own advertised prefix only as bgp-output-<peer> rows, one per peer it goes to
        # (routeros_routes_main.txt, live 7.23.8): an own path in the BGP table, which `present: false` must see
        # (angle-5 design review on d87aa3e, RT-0051); never a received path
        own = sorted({p.out_peer for p in rows if p.kind == "bgp-output" and p.prefix == prefix and p.out_peer})
        addresses = {}
        if received:
            addresses = {s.name: s.remote_address for s in parse_sessions(self._rows("/routing/bgp/session", ev))}
        out = []
        for p in received:
            out.append(BgpPath(
                best=p.contribution in ("active", "best-candidate"),
                as_path=None if p.as_path is None else " ".join(str(a) for a in p.as_path),
                # a VRF's gateway reads "203.0.113.2@RED" (live CHR 7.23.8); only the path's own table is dropped
                next_hop=p.gateway.removesuffix(f"@{table}") if p.gateway else p.gateway,
                local_pref=p.local_pref,          # None when the path carries none: the default is not read, so a check fails
                med=p.med or None,     # 0 is unknown: see ambiguous_bgp_values
                communities=canon_communities(p.communities),
                large_communities=canon_communities(p.large_communities),
                neighbor=addresses.get(p.session or ""),
            ))
        for peer in own:
            out.append(BgpPath(best=False, as_path=None, next_hop=None, local_pref=None, med=None,
                               neighbor=peer, local_candidate=True, local_origin="advertised by the node to " + peer))
        return Observation(out, ev)

    def nos_version(self) -> str | None:
        try:
            reply = self._rest("GET", "/system/resource", [])
        except DriverError:
            return None
        return parse_version(reply.obj) if reply.kind == "object" else None

    def startup_errors(self) -> list[str]:
        """The startup config's load on this router ([]: every line ran), from RouterOS's own log (see parse_import_log)."""
        return parse_import_log(self._rows("/log", []))

    def vrfs(self) -> Observation:
        """The node's VRFs other than default: every valid routing table but `main` (used by `netdryrun record`)."""
        ev: list[dict] = []
        tables = parse_tables(self._rows("/routing/table", ev))
        return Observation(sorted(t for t, valid in tables.items() if valid and t != "main"), ev)

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
