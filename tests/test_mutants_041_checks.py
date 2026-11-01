"""0.4.1 mutation gate: the verdicts and the exact detail texts of _bgp_prefixes, _bgp_route, _ping and _route.

These are verdict functions, so a mutant that only changes a message is killed here by asserting the text, not
accepted. The fake driver keeps its state in one VRF (any other VRF is an error, as on a device) and records
every call, so an evaluator that drops or mangles the afi or vrf argument fails.
"""
from __future__ import annotations

import pytest

from netdryrun.checks import Unready, _bgp_prefixes, _bgp_route, _ping, _route
from netdryrun.drivers.base import BgpNeighbor, BgpPath, DriverError, Observation, Route

NB = "10.0.0.2"


class Fake:
    """One VRF of state: neighbors, received prefixes, routes, BGP paths, a ping result."""

    def __init__(self, vrf="default", neighbor=None, received=None, routes=None, paths=None, ping=None,
                 evidence=None):
        self.vrf = vrf
        self.neighbor, self.received = neighbor, received
        self._routes, self._paths, self._ping = routes or [], paths or [], ping
        self.evidence = evidence if evidence is not None else [{"cmd": "show"}]
        self.calls: list[tuple] = []

    def _in(self, vrf):
        if vrf != self.vrf:
            raise DriverError(f"no VRF {vrf!r}")

    def bgp_neighbors(self, vrf="default"):
        self.calls.append(("bgp_neighbors", vrf))
        self._in(vrf)
        return Observation({NB: self.neighbor} if self.neighbor else {}, [{"cmd": "neighbors"}])

    def bgp_received(self, neighbor, afi="ipv4-unicast", vrf="default"):
        self.calls.append(("bgp_received", neighbor, afi, vrf))
        self._in(vrf)
        return Observation(set(self.received or ()), [{"cmd": "received"}])

    def routes(self, prefix, vrf="default"):
        self.calls.append(("routes", prefix, vrf))
        self._in(vrf)
        return Observation(list(self._routes), list(self.evidence))

    def bgp_paths(self, prefix, vrf="default"):
        self.calls.append(("bgp_paths", prefix, vrf))
        self._in(vrf)
        return Observation(list(self._paths), list(self.evidence))

    def ping(self, target, source, count, vrf="default"):
        self.calls.append(("ping", target, source, count, vrf))
        self._in(vrf)
        sent, received, evidence = self._ping
        return Observation((sent, received), evidence)


def established(afi="ipv4-unicast", count=3):
    return BgpNeighbor(NB, "established", {afi: count})


# ----------------------------------------------------------------------------------------------- bgp_prefixes

def _pfx(n):
    return [f"10.{10 + i}.0.0/16" for i in range(n)]   # fixed width, so sorted() keeps this order


def test_only_reads_received_prefixes_in_the_checks_afi_and_vrf():
    d = Fake(vrf="red", neighbor=established("ipv6-unicast", 2), received=["2001:db8::/48", "2001:db8:1::/48"])
    ok, detail, ev = _bgp_prefixes(d, {"neighbor": NB, "afi": "ipv6-unicast", "vrf": "red",
                                       "only": ["2001:db8::/48", "2001:db8:1::/48"]})
    assert ok is True
    assert detail == "2 ipv6-unicast prefixes accepted; all within the allowed set"
    assert ev == [{"cmd": "neighbors"}, {"cmd": "received"}]
    assert d.calls == [("bgp_neighbors", "red"), ("bgp_received", NB, "ipv6-unicast", "red")]


def test_only_still_fails_a_count_over_max():
    """Every prefix is allowed, but there are more than max: the count bound still fails the check."""
    d = Fake(neighbor=established(count=5), received=_pfx(5))
    ok, detail, ev = _bgp_prefixes(d, {"neighbor": NB, "max": 3, "only": _pfx(5)})
    assert ok is False
    assert detail == "5 ipv4-unicast prefixes accepted; all within the allowed set"
    assert ev == [{"cmd": "neighbors"}, {"cmd": "received"}]


def test_only_counted_but_none_listed_is_unready_with_its_reason():
    d = Fake(neighbor=established(count=3), received=[])
    ok, detail, ev = _bgp_prefixes(d, {"neighbor": NB, "only": ["10.1.0.0/16"]})
    assert ok is False
    assert isinstance(detail, Unready)
    assert detail == f"error: 3 ipv4-unicast prefixes counted from {NB} but none listed"
    assert ev == [{"cmd": "neighbors"}, {"cmd": "received"}]


@pytest.mark.parametrize("n,shown", [
    (1, "10.10.0.0/16"),
    (2, "10.10.0.0/16, 10.11.0.0/16"),
    (10, ", ".join(_pfx(10))),
    (11, ", ".join(_pfx(10)) + " and 1 more"),
    (12, ", ".join(_pfx(10)) + " and 2 more"),
])
def test_only_lists_at_most_ten_prefixes_outside_the_allowed_set(n, shown):
    d = Fake(neighbor=established(count=n), received=_pfx(n))
    ok, detail, ev = _bgp_prefixes(d, {"neighbor": NB, "only": ["192.0.2.0/24"]})
    assert ok is False
    assert detail == f"{n} ipv4-unicast prefixes accepted; not in the allowed set: {shown}"
    assert ev == [{"cmd": "neighbors"}, {"cmd": "received"}]


# ----------------------------------------------------------------------------------------------- route

def test_route_not_active_lists_every_route_seen_and_the_protocol_wanted():
    d = Fake(routes=[Route("0.0.0.0/0", "static", True), Route("0.0.0.0/0", "ospf", False)])
    assert _route(d, {"prefix": "0.0.0.0/0", "protocol": "bgp"}) == (
        False, "not active via bgp; seen: static, ospf (inactive)", [{"cmd": "show"}])


def test_route_not_active_without_a_protocol():
    d = Fake(routes=[Route("0.0.0.0/0", "bgp", False)])
    assert _route(d, {"prefix": "0.0.0.0/0"}) == (False, "not active; seen: bgp (inactive)", [{"cmd": "show"}])


def test_route_not_active_with_nothing_seen():
    assert _route(Fake(), {"prefix": "0.0.0.0/0"}) == (False, "not active; seen: nothing", [{"cmd": "show"}])


@pytest.mark.parametrize("active,detail", [(True, "unexpectedly present via bgp"),
                                           (False, "unexpectedly present via bgp (not selected)")])
def test_route_absent_fails_on_a_selected_or_unselected_route(active, detail):
    d = Fake(routes=[Route("0.0.0.0/0", "bgp", active)])
    assert _route(d, {"prefix": "0.0.0.0/0", "present": False}) == (False, detail, [{"cmd": "show"}])


def test_route_absent_passes_with_its_text():
    assert _route(Fake(), {"prefix": "0.0.0.0/0", "present": False}) == (True, "absent", [{"cmd": "show"}])


# ----------------------------------------------------------------------------------------------- ping

@pytest.mark.parametrize("evidence,detail", [
    ([{"output": "", "stderr": "  ping: bind: Cannot assign requested address \n"}],
     "error: ping did not run: ping: bind: Cannot assign requested address"),
    ([{"output": "", "stderr": "first"}, {"output": "", "stderr": "last"}], "error: ping did not run: last"),
    ([{"output": ""}], "error: ping did not run"),
    ([{"output": "", "stderr": "   "}], "error: ping did not run"),
    ([], "error: ping did not run"),
])
def test_ping_that_did_not_run_reports_the_last_stderr(evidence, detail):
    d = Fake(ping=(0, 0, evidence))
    assert _ping(d, {"target": "10.9.9.9"}) == (False, detail, evidence)
    d = Fake(ping=(0, 0, evidence))
    assert _ping(d, {"target": "10.9.9.9", "expect": "failure"}) == (False, detail, evidence)


# ----------------------------------------------------------------------------------------------- bgp_route

def path(best=True, next_hop="10.0.0.1", communities=(), local=False, **kw):
    attrs = {"as_path": "65001", "local_pref": 100, "med": 0, **kw}
    return BgpPath(best=best, next_hop=next_hop, communities=list(communities), local_candidate=local, **attrs)


DESC = "as-path '65001', next hop 10.0.0.1, local-pref 100, MED 0, communities none"


def test_bgp_route_absent_passes_with_its_text():
    d = Fake(paths=[path(local=True)])
    assert _bgp_route(d, {"prefix": "10.1.0.0/16", "present": False}) == (True, "no BGP path", [{"cmd": "show"}])


def test_bgp_route_only_a_local_route_fails_with_its_reason():
    d = Fake(paths=[path(local=True)])
    assert _bgp_route(d, {"prefix": "10.1.0.0/16"}) == (
        False, "no BGP path: only the router's own route, which the NOS lists in the BGP table whether it is "
               "advertised or not (check the route on a neighbor instead)", [{"cmd": "show"}])


def test_bgp_route_no_path_at_all():
    assert _bgp_route(Fake(), {"prefix": "10.1.0.0/16"}) == (False, "no BGP path", [{"cmd": "show"}])


@pytest.mark.parametrize("local_best,why", [(True, "the router's own route is best"),
                                            (False, "next hop unreachable?")])
def test_bgp_route_no_best_path_says_why(local_best, why):
    d = Fake(paths=[path(best=False), path(best=local_best, local=True)])
    assert _bgp_route(d, {"prefix": "10.1.0.0/16"}) == (
        False, f"1 BGP path(s) but none is best ({why})", [{"cmd": "show"}])


def test_bgp_route_lists_every_missing_community():
    d = Fake(paths=[path()])
    ok, detail, _ = _bgp_route(d, {"prefix": "10.1.0.0/16", "communities": ["65000:1", "65000:2"]})
    assert ok is False
    assert detail == f"missing communities 65000:1 65000:2 (best path: {DESC})"


def test_bgp_route_lists_every_forbidden_community_carried():
    d = Fake(paths=[path(communities=["65000:1", "65000:2"])])
    ok, detail, _ = _bgp_route(d, {"prefix": "10.1.0.0/16", "without_communities": ["65000:1", "65000:2"]})
    assert ok is False
    assert detail == ("carries communities 65000:1 65000:2 "
                      "(best path: as-path '65001', next hop 10.0.0.1, local-pref 100, MED 0, "
                      "communities 65000:1 65000:2)")


def test_bgp_route_unreadable_communities_with_a_without_list():
    d = Fake(paths=[path(communities=["zz-alias", "aa-alias"])])
    ok, detail, _ = _bgp_route(d, {"prefix": "10.1.0.0/16", "without_communities": ["65000:9"]})
    assert ok is False
    assert detail == ("carries communities Netdryrun can't read as numbers (aa-alias zz-alias), so it can't tell "
                      "whether they are ones the path must not carry (best path: as-path '65001', next hop "
                      "10.0.0.1, local-pref 100, MED 0, communities zz-alias aa-alias)")


def test_bgp_route_unknown_next_hop_and_several_wrongs_joined():
    d = Fake(paths=[path(next_hop=None)])
    ok, detail, _ = _bgp_route(d, {"prefix": "10.1.0.0/16", "next_hop": "10.0.0.9", "med": 5})
    assert ok is False
    assert detail == ("MED is 0, expected 5; next hop is ?, expected 10.0.0.9 "
                      "(best path: as-path '65001', next hop ?, local-pref 100, MED 0, communities none)")
