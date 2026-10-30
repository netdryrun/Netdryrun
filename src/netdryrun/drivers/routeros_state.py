"""RouterOS 7 state read strictly from REST rows (after `routeros_rest.classify_reply` said the answer was readable).

Facts from the first live capture (CHR 7.23.8, 2026-10-30) that shape this module:

- `prefix-count` on a BGP session is the RECEIVED count: it includes prefixes an input filter rejected. Accepted prefixes
  come from the routing route table: BGP paths of that session whose `contribution` is not `filtered`.
- `/routing/route` marks every path with a `contribution`: active (installed), candidate (valid, not best), best-candidate
  (BGP's best, outranked by another protocol: received but not selected) or filtered (rejected by policy, still listed).
- A connection that cannot start (`inactive`) has no session row at all: no row is neither "established" nor "unknown peer".
- `/routing/route` also lists pseudo rows (interfaces, link-locals) whose dst-address is not a prefix; they are recognised by
  `belongs-to`, never guessed.
- An unknown routing table answers 200 with an empty list, so a table must be confirmed from `/routing/table` first.
Unknown keys or values on route rows raise: a new RouterOS flag may change what a row means, so it is never skipped.
"""
from __future__ import annotations

import ipaddress
import re
from dataclasses import dataclass, field

from .base import parser, unexpected
from .routeros_rest import as_bool, as_int


@dataclass(frozen=True)
class Session:
    name: str
    remote_address: str
    remote_as: int
    vrf: str
    established: bool
    received_count: int | None      # prefix-count: RECEIVED, not accepted
    afi: str = "ip"                  # remote.afi: ip | ipv6 | ...


@dataclass(frozen=True)
class Connection:
    name: str
    remote_address: str
    vrf: str
    inactive: bool
    about: str | None


@dataclass(frozen=True)
class RoutingRoute:
    kind: str                       # bgp | bgp-output | static | connected | interface
    table: str
    prefix: str | None              # None for pseudo rows (interfaces, link-locals)
    contribution: str
    active: bool
    filtered: bool
    distance: int | None
    gateway: str | None
    session: str | None
    as_path: list[int] | None
    local_pref: int | None
    med: int | None
    communities: list[str] = field(default_factory=list)
    large_communities: list[str] = field(default_factory=list)
    link_local: bool = False


def _vrf(table: str | None) -> str:
    return "default" if table in (None, "", "main") else table


def _addr(request: str, value: object) -> tuple[str, str]:
    """(address, vrf) from a RouterOS address that may carry `@VRF`."""
    text = str(value)
    host, _, vrf = text.partition("@")
    try:
        ipaddress.ip_address(host)
    except ValueError:
        raise unexpected(request, f"not an address: {text[:60]!r}") from None
    return host, (vrf or "default")


def _need(request: str, row: dict, *keys: str) -> None:
    for k in keys:
        if k not in row:
            raise unexpected(request, f"row without {k!r}")


@parser("/routing/bgp/session")
def parse_sessions(rows) -> list[Session]:
    req = "/routing/bgp/session"
    out = []
    for r in rows:
        _need(req, r, "name", "remote.address", "remote.as", "established", "remote.afi")
        host, vrf = _addr(req, r["remote.address"])
        established = as_bool(req, r["established"])
        if "prefix-count" in r:
            count = as_int(req, r["prefix-count"])
        elif established:
            raise unexpected(req, f"established session {r['name']!r} without a prefix-count")
        else:
            count = None
        out.append(Session(str(r["name"]), host, as_int(req, r["remote.as"]), vrf, established, count, str(r["remote.afi"])))
    return out


@parser("/routing/bgp/connection")
def parse_connections(rows) -> list[Connection]:
    req = "/routing/bgp/connection"
    out = []
    for r in rows:
        _need(req, r, "name", "remote.address", "inactive")
        host, _ = _addr(req, r["remote.address"])
        out.append(Connection(str(r["name"]), host, _vrf(r.get("vrf")), as_bool(req, r["inactive"]), r.get(".about")))
    return out


@parser("/routing/table")
def parse_tables(rows) -> dict[str, bool]:
    """Routing table name to whether it is usable. A table missing from this list does not exist."""
    req = "/routing/table"
    out = {}
    for r in rows:
        _need(req, r, "name", "invalid")
        out[str(r["name"])] = not as_bool(req, r["invalid"])
    return out


_ROUTE_KEYS = {
    ".id", "active", "afi", "belongs-to", "bgp", "bgp-net", "connect", "local-address", "bgp.as-path", "bgp.communities", "bgp.large-communities", "bgp.local-pref",
    "bgp.med", "bgp.origin", "bgp.session", "blackhole", "comment", "contribution", "distance", "dst-address", "filtered",
    "gateway", "immediate-gw", "nexthop-id", "routing-table", "scope", "static", "target-scope",
}
_CONTRIBUTIONS = {"active", "candidate", "best-candidate", "filtered"}
_BGP_IN = re.compile(r"^bgp-IP-\S+$")
_BGP_OUT = re.compile(r"^bgp-output-\S+$")


@parser("/routing/route")
def parse_routing_routes(rows) -> list[RoutingRoute]:
    req = "/routing/route"
    out = []
    for r in rows:
        bad = [k for k in r if k not in _ROUTE_KEYS and not k.startswith("debug.")]
        if bad:
            raise unexpected(req, f"unknown key(s) {sorted(bad)[:4]} in a route row")
        _need(req, r, "belongs-to", "contribution", "dst-address", "routing-table")
        contribution = r["contribution"]
        if contribution not in _CONTRIBUTIONS:
            raise unexpected(req, f"unknown contribution {str(contribution)[:40]!r}")
        belongs = r["belongs-to"]
        if belongs in ("connected", "interface", "static"):
            kind = belongs
        elif _BGP_IN.match(belongs):
            kind = "bgp"
        elif _BGP_OUT.match(belongs):
            kind = "bgp-output"
        else:
            raise unexpected(req, f"unknown belongs-to {str(belongs)[:40]!r}")
        dst = str(r["dst-address"])
        prefix, link_local = None, False
        if kind != "interface":
            if "%" in dst:
                link_local = True          # fe80::%ether3/64: a scoped link-local, not a routable prefix (checked first:
                                           # newer Pythons accept the scope id and would return it as a prefix)
            else:
                try:
                    prefix = str(ipaddress.ip_network(dst, strict=False))
                except ValueError:
                    raise unexpected(req, f"not a prefix: {dst[:60]!r}") from None
        session = None
        if kind == "bgp":
            _need(req, r, "bgp.session")
            session = str(r["bgp.session"])
        as_path = None
        if "bgp.as-path" in r:
            as_path = [as_int(req, a) for a in str(r["bgp.as-path"]).split(",")] if r["bgp.as-path"] else []
        out.append(RoutingRoute(
            kind=kind, table=str(r["routing-table"]), prefix=prefix, contribution=contribution,
            active=as_bool(req, r["active"]) if "active" in r else False,
            filtered=as_bool(req, r["filtered"]) if "filtered" in r else False,
            distance=as_int(req, r["distance"]) if "distance" in r else None,
            gateway=r.get("gateway"), session=session, as_path=as_path,
            local_pref=as_int(req, r["bgp.local-pref"]) if "bgp.local-pref" in r else None,
            med=as_int(req, r["bgp.med"]) if "bgp.med" in r else None,
            communities=[c for c in str(r.get("bgp.communities", "")).split(",") if c],
            large_communities=[c for c in str(r.get("bgp.large-communities", "")).split(",") if c],
            link_local=link_local,
        ))
    return out


def accepted_prefixes(paths: list[RoutingRoute], session: str) -> set[str]:
    """Prefixes a BGP session delivered that passed the input filter (the count `prefix-count` does not give)."""
    return {p.prefix for p in paths if p.kind == "bgp" and p.session == session and not p.filtered and p.prefix}


def best_paths(paths: list[RoutingRoute], prefix: str, table: str) -> list[RoutingRoute]:
    """BGP paths that BGP itself selected for exactly `prefix` in `table`: installed (`active`) or outranked by another
    protocol (`best-candidate`). A covering or longer prefix is not an exact match."""
    want = str(ipaddress.ip_network(prefix, strict=False))
    return [p for p in paths if p.kind == "bgp" and p.prefix == want and p.table == table
            and p.contribution in ("active", "best-candidate")]


@parser("/ping")
def parse_ping(rows) -> tuple[int, int]:
    """(sent, received) from the last cumulative row of a REST ping answer."""
    req = "/ping"
    if not rows:
        raise unexpected(req, "no rows")
    last = rows[-1]
    _need(req, last, "sent", "received")
    sent, received = as_int(req, last["sent"]), as_int(req, last["received"])
    if received > sent:
        raise unexpected(req, f"received {received} > sent {sent}")
    return sent, received
