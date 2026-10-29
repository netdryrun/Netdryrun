"""Verdict logic of checks.py, pinned down so that mutation testing finds no surviving mutant.

Every evaluator, the polling loops, the confirmation streak, the hold windows and the timeouts are driven
here by a VRF-aware fake driver on a fake clock. Each test asserts a verdict, a status or a sample count,
never a message text. A false pass is the worst possible bug, so most tests set up the state where a
broken comparison would pass a check that must fail.
"""
from __future__ import annotations

import pytest

from netdryrun import checks as C
from netdryrun.checks import (Result, Unready, _bgp_prefixes, _bgp_route, _bgp_session, _evaluate, _ping, _route,
                              converge_then_hold, hold_check, hold_together, inconclusive_reason,
                              is_post_convergence, run_check, run_round_robin)
from netdryrun.config import Check
from netdryrun.drivers.base import BgpNeighbor, BgpPath, DriverError, Observation, Route

NB = "10.0.0.2"


# ----------------------------------------------------------------------------------------------- fakes

class Clock:
    """A fake monotonic clock. It starts far from zero, so `clock() + t0` and `clock() - t0` differ."""

    def __init__(self, start=1000.0):
        self.start = self.t = start
        self.sleeps: list[float] = []

    def __call__(self):
        return self.t

    def sleep(self, s):
        assert s >= 0, f"negative sleep {s}"
        self.sleeps.append(s)
        assert len(self.sleeps) < 2000, "polling loop that never ends"
        self.t += s

    @property
    def now(self):
        """Seconds since the clock started."""
        return self.t - self.start


def _at(value, clock):
    """value is a constant, or a function of the fake clock's elapsed time."""
    return value(clock.now) if callable(value) else value


class Fake:
    """A driver whose state lives in one VRF at a time. Asking for any other VRF is an error, as on a device
    (no such VRF), so an evaluator that drops or mangles the vrf argument fails its check.

    neighbors / routes / paths / ping map a VRF name to a value or to a function of elapsed time."""

    def __init__(self, clock=None, neighbors=None, routes=None, paths=None, ping=None, evidence=None):
        self.clock = clock or Clock()
        self._neighbors, self._routes, self._paths, self._ping = neighbors or {}, routes or {}, paths or {}, ping or {}
        self.evidence = evidence if evidence is not None else [{"cmd": "show"}]
        self.calls: list[tuple] = []

    def _vrf(self, table, vrf):
        if vrf not in table:
            raise DriverError(f"no VRF {vrf!r}")
        return _at(table[vrf], self.clock)

    def bgp_neighbors(self, vrf="default"):
        self.calls.append(("bgp_neighbors", vrf))
        return Observation(self._vrf(self._neighbors, vrf), list(self.evidence))

    def routes(self, prefix, vrf="default"):
        self.calls.append(("routes", prefix, vrf))
        return Observation(self._vrf(self._routes, vrf), list(self.evidence))

    def bgp_paths(self, prefix, vrf="default"):
        self.calls.append(("bgp_paths", prefix, vrf))
        return Observation(self._vrf(self._paths, vrf), list(self.evidence))

    def ping(self, target, source, count, vrf="default"):
        self.calls.append(("ping", target, source, count, vrf))
        sent, received, evidence = self._vrf(self._ping, vrf)
        return Observation((sent, received), evidence)


def nbr(state="established", **prefixes):
    pfx = {k.replace("_", "-"): v for k, v in prefixes.items()}
    return {NB: BgpNeighbor(NB, state, pfx)}


def chk(ctype, timeout=30.0, hold=None, node="r1", **params):
    return Check(type=ctype, params={"node": node, **params}, name=f"{node} {ctype}", timeout=timeout, hold=hold)


def session(state="established", **kw):
    return chk("bgp_session", neighbor=NB, state=state, **kw)


def prefixes(**kw):
    return chk("bgp_prefixes", neighbor=NB, **kw)


def ok(fn, driver, params):
    return fn(driver, params)[0]


# ----------------------------------------------------------------------------------------------- bgp_session

@pytest.mark.parametrize("state,expected", [("established", True), ("idle", False), ("active", False)])
def test_session_established(state, expected):
    assert ok(_bgp_session, Fake(neighbors={"default": nbr(state)}), {"neighbor": NB, "state": "established"}) is expected


@pytest.mark.parametrize("state,expected", [("established", False), ("idle", True), ("active", True), ("connect", True)])
def test_session_down_means_any_state_but_established(state, expected):
    assert ok(_bgp_session, Fake(neighbors={"default": nbr(state)}), {"neighbor": NB, "state": "down"}) is expected


@pytest.mark.parametrize("state,expected", [("idle", True), ("active", False), ("established", False)])
def test_session_exact_state(state, expected):
    assert ok(_bgp_session, Fake(neighbors={"default": nbr(state)}), {"neighbor": NB, "state": "idle"}) is expected


@pytest.mark.parametrize("want", ["established", "down", "idle"])
def test_session_unknown_neighbor_never_passes(want):
    """A neighbor that isn't configured is not 'down': a typo in the address must not pass state: down."""
    d = Fake(neighbors={"default": {"10.9.9.9": BgpNeighbor("10.9.9.9", "idle", {})}})
    assert ok(_bgp_session, d, {"neighbor": NB, "state": want}) is False
    assert ok(_bgp_session, Fake(neighbors={"default": {}}), {"neighbor": NB, "state": want}) is False


def test_unknown_neighbor_is_unready_only_when_the_node_has_no_neighbors():
    _, detail, _ = _bgp_session(Fake(neighbors={"default": {}}), {"neighbor": NB, "state": "established"})
    assert isinstance(detail, Unready)
    d = Fake(neighbors={"default": {"10.9.9.9": BgpNeighbor("10.9.9.9", "idle", {})}})
    _, detail, _ = _bgp_session(d, {"neighbor": NB, "state": "established"})
    assert not isinstance(detail, Unready)
    _, detail, _ = _bgp_prefixes(Fake(neighbors={"default": {}}), {"neighbor": NB, "min": 1})
    assert isinstance(detail, Unready)
    _, detail, _ = _bgp_prefixes(d, {"neighbor": NB, "min": 1})
    assert not isinstance(detail, Unready)


def test_session_reads_the_checks_vrf():
    d = Fake(neighbors={"default": nbr("idle"), "blue": nbr("established")})
    assert ok(_bgp_session, d, {"neighbor": NB, "state": "established", "vrf": "blue"}) is True
    assert ok(_bgp_session, d, {"neighbor": NB, "state": "established"}) is False
    assert ok(_bgp_session, d, {"neighbor": NB, "state": "down"}) is True
    assert ok(_bgp_session, d, {"neighbor": NB, "state": "down", "vrf": "blue"}) is False
    assert d.calls == [("bgp_neighbors", "blue"), ("bgp_neighbors", "default"),
                       ("bgp_neighbors", "default"), ("bgp_neighbors", "blue")]


def test_evidence_is_the_drivers():
    d = Fake(neighbors={"default": nbr("established", ipv4_unicast=1)}, evidence=[{"cmd": "x", "output": "y"}])
    assert _bgp_session(d, {"neighbor": NB, "state": "established"})[2] == [{"cmd": "x", "output": "y"}]
    assert _bgp_session(d, {"neighbor": "10.9.9.9", "state": "established"})[2] == [{"cmd": "x", "output": "y"}]
    assert _bgp_prefixes(d, {"neighbor": NB, "min": 1})[2] == [{"cmd": "x", "output": "y"}]
    assert _bgp_prefixes(d, {"neighbor": "10.9.9.9", "min": 1})[2] == [{"cmd": "x", "output": "y"}]
    d2 = Fake(neighbors={"default": nbr("idle")}, evidence=[{"cmd": "z"}])
    assert _bgp_prefixes(d2, {"neighbor": NB, "max": 1})[2] == [{"cmd": "z"}]


# ----------------------------------------------------------------------------------------------- bgp_prefixes

@pytest.mark.parametrize("bounds", [{"max": 10}, {"exact": 0}, {"min": 0, "max": 5}, {"max": 0}])
def test_prefixes_unknown_neighbor_never_passes(bounds):
    """0 prefixes from a neighbor that isn't there would satisfy max and exact: 0."""
    d = Fake(neighbors={"default": {"10.9.9.9": BgpNeighbor("10.9.9.9", "established", {})}})
    assert ok(_bgp_prefixes, d, {"neighbor": NB, **bounds}) is False
    assert ok(_bgp_prefixes, Fake(neighbors={"default": {}}), {"neighbor": NB, **bounds}) is False


@pytest.mark.parametrize("state", ["idle", "active", "connect", "opensent"])
@pytest.mark.parametrize("bounds", [{"max": 10}, {"exact": 0}, {"max": 0}, {"min": 1}])
def test_prefixes_need_an_established_session(state, bounds):
    """Counters reset to 0 when a session drops, which would satisfy max by accident."""
    d = Fake(neighbors={"default": nbr(state, ipv4_unicast=0)})
    assert ok(_bgp_prefixes, d, {"neighbor": NB, **bounds}) is False
    d = Fake(neighbors={"default": nbr(state, ipv4_unicast=3)})
    assert ok(_bgp_prefixes, d, {"neighbor": NB, "min": 1, "max": 5}) is False


@pytest.mark.parametrize("count,expected", [(4, True), (5, True), (6, False), (0, True)])
def test_prefixes_max_is_inclusive(count, expected):
    d = Fake(neighbors={"default": nbr(ipv4_unicast=count)})
    assert ok(_bgp_prefixes, d, {"neighbor": NB, "max": 5}) is expected


@pytest.mark.parametrize("count,expected", [(2, False), (3, True), (4, True)])
def test_prefixes_min_is_inclusive(count, expected):
    d = Fake(neighbors={"default": nbr(ipv4_unicast=count)})
    assert ok(_bgp_prefixes, d, {"neighbor": NB, "min": 3}) is expected


@pytest.mark.parametrize("count,expected", [(1, False), (2, True), (3, True), (4, False)])
def test_prefixes_range(count, expected):
    d = Fake(neighbors={"default": nbr(ipv4_unicast=count)})
    assert ok(_bgp_prefixes, d, {"neighbor": NB, "min": 2, "max": 3}) is expected


@pytest.mark.parametrize("count,expected", [(2, False), (3, True), (4, False)])
def test_prefixes_exact(count, expected):
    d = Fake(neighbors={"default": nbr(ipv4_unicast=count)})
    assert ok(_bgp_prefixes, d, {"neighbor": NB, "exact": 3}) is expected


def test_prefixes_exact_ignores_min_and_max():
    d = Fake(neighbors={"default": nbr(ipv4_unicast=3)})
    assert ok(_bgp_prefixes, d, {"neighbor": NB, "exact": 3, "min": 5}) is True
    assert ok(_bgp_prefixes, d, {"neighbor": NB, "exact": 3, "max": 1}) is True
    assert ok(_bgp_prefixes, d, {"neighbor": NB, "exact": 2, "min": 0, "max": 9}) is False


def test_prefixes_family_without_a_counter_counts_zero():
    """Established, but the family reports nothing: 0 prefixes, never 1."""
    d = Fake(neighbors={"default": nbr(ipv6_unicast=7)})
    assert ok(_bgp_prefixes, d, {"neighbor": NB, "min": 1}) is False
    assert ok(_bgp_prefixes, d, {"neighbor": NB, "exact": 0}) is True
    assert ok(_bgp_prefixes, d, {"neighbor": NB, "max": 0}) is True
    assert ok(_bgp_prefixes, d, {"neighbor": NB, "exact": 1}) is False


def test_prefixes_afi_selects_the_family_and_defaults_to_ipv4():
    d = Fake(neighbors={"default": nbr(ipv4_unicast=2, ipv6_unicast=9, evpn=0)})
    assert ok(_bgp_prefixes, d, {"neighbor": NB, "exact": 2}) is True
    assert ok(_bgp_prefixes, d, {"neighbor": NB, "exact": 9, "afi": "ipv6-unicast"}) is True
    assert ok(_bgp_prefixes, d, {"neighbor": NB, "exact": 0, "afi": "evpn"}) is True
    assert ok(_bgp_prefixes, d, {"neighbor": NB, "exact": 2, "afi": "ipv6-unicast"}) is False


def test_prefixes_without_bounds_need_none():
    """No min given means min 0 (config validation refuses a check without any bound)."""
    d = Fake(neighbors={"default": nbr(ipv4_unicast=0)})
    assert ok(_bgp_prefixes, d, {"neighbor": NB, "max": 3}) is True


def test_prefixes_read_the_checks_vrf():
    d = Fake(neighbors={"default": nbr(ipv4_unicast=50), "blue": nbr(ipv4_unicast=2)})
    assert ok(_bgp_prefixes, d, {"neighbor": NB, "max": 5, "vrf": "blue"}) is True
    assert ok(_bgp_prefixes, d, {"neighbor": NB, "max": 5}) is False
    assert [c[1] for c in d.calls] == ["blue", "default"]
    only_blue = Fake(neighbors={"blue": nbr(ipv4_unicast=2)})
    assert ok(_bgp_prefixes, only_blue, {"neighbor": NB, "max": 5, "vrf": "blue"}) is True


# ----------------------------------------------------------------------------------------------- route

def R(proto="bgp", active=True, prefix="10.1.0.0/16"):
    return Route(prefix, proto, active)


def route_ok(routes, vrf="default", **params):
    return ok(_route, Fake(routes={vrf: routes}), {"prefix": "10.1.0.0/16", **params})


def test_route_present_needs_an_active_route():
    assert route_ok([R()]) is True
    assert route_ok([R(active=False)]) is False
    assert route_ok([]) is False
    assert route_ok([R(active=False), R("static")]) is True


def test_route_protocol_filter():
    assert route_ok([R("static")], protocol="bgp") is False
    assert route_ok([R("static"), R("bgp", active=False)], protocol="bgp") is False
    assert route_ok([R("static", active=False), R("bgp")], protocol="bgp") is True
    assert route_ok([R("static")]) is True                 # no protocol: any protocol
    assert route_ok([R("bgp")], protocol="BGP") is True    # compared lower-case


def test_route_active_false_accepts_a_route_that_is_not_selected():
    assert route_ok([R(active=False)], active=False) is True
    assert route_ok([R(active=False)], active=True) is False
    assert route_ok([R("static", active=False)], active=False, protocol="bgp") is False
    assert route_ok([], active=False) is False
    assert route_ok([R()], active=False) is True


def test_route_absent():
    assert route_ok([], present=False) is True
    assert route_ok([R()], present=False) is False
    assert route_ok([R(active=False)], present=False) is False   # received but not selected is still a leak
    assert route_ok([R("static")], present=False, protocol="bgp") is True
    assert route_ok([R("static"), R("bgp", active=False)], present=False, protocol="bgp") is False


def test_route_present_only_false_is_absent():
    """`is not False`: anything but a real False means present (config insists on a boolean anyway)."""
    assert route_ok([], present=None) is False
    assert route_ok([], present=0) is False
    assert route_ok([R()], present=0) is True


def test_route_reads_the_checks_vrf():
    d = Fake(routes={"default": [], "blue": [R()]})
    assert ok(_route, d, {"prefix": "10.1.0.0/16", "vrf": "blue"}) is True
    assert ok(_route, d, {"prefix": "10.1.0.0/16"}) is False
    assert ok(_route, d, {"prefix": "10.1.0.0/16", "present": False}) is True
    assert ok(_route, d, {"prefix": "10.1.0.0/16", "present": False, "vrf": "blue"}) is False
    assert d.calls[0] == ("routes", "10.1.0.0/16", "blue")
    assert d.calls[1] == ("routes", "10.1.0.0/16", "default")
    ev = Fake(routes={"default": [R()]}, evidence=[{"cmd": "r"}])
    for params in ({}, {"present": False}, {"active": False}):
        assert _route(ev, {"prefix": "10.1.0.0/16", **params})[2] == [{"cmd": "r"}]
    ev = Fake(routes={"default": [R(active=False)]}, evidence=[{"cmd": "r"}])
    for params in ({}, {"active": False}, {"present": False}):
        assert _route(ev, {"prefix": "10.1.0.0/16", **params})[2] == [{"cmd": "r"}]
    assert _route(Fake(routes={"default": []}, evidence=[{"cmd": "r"}]), {"prefix": "10.1.0.0/16", "present": False})[2] \
        == [{"cmd": "r"}]


# ----------------------------------------------------------------------------------------------- bgp_route

def P(**kw):
    base = dict(best=True, as_path="65020", next_hop="10.1.1.2", local_pref=100, med=0)
    base.update(kw)
    return BgpPath(**base)


def test_bgp_route_reads_the_checks_vrf():
    d = Fake(paths={"default": [], "blue": [P()]})
    assert ok(_bgp_route, d, {"prefix": "10.1.0.0/16", "vrf": "blue"}) is True
    assert ok(_bgp_route, d, {"prefix": "10.1.0.0/16"}) is False
    assert ok(_bgp_route, d, {"prefix": "10.1.0.0/16", "present": False}) is True
    assert ok(_bgp_route, d, {"prefix": "10.1.0.0/16", "present": False, "vrf": "blue"}) is False
    assert d.calls[0] == ("bgp_paths", "10.1.0.0/16", "blue")


def test_bgp_route_absent_ignores_only_local_candidates():
    assert ok(_bgp_route, Fake(paths={"default": [P(local_candidate=True)]}), {"prefix": "p", "present": False}) is True
    assert ok(_bgp_route, Fake(paths={"default": [P(best=False)]}), {"prefix": "p", "present": False}) is False
    assert ok(_bgp_route, Fake(paths={"default": [P(local_candidate=True), P(best=False)]}),
              {"prefix": "p", "present": False}) is False
    assert ok(_bgp_route, Fake(paths={"default": [P(local_candidate=True)]}), {"prefix": "p"}) is True


def test_bgp_route_needs_a_best_path():
    assert ok(_bgp_route, Fake(paths={"default": []}), {"prefix": "p"}) is False
    assert ok(_bgp_route, Fake(paths={"default": [P(best=False)]}), {"prefix": "p"}) is False
    assert ok(_bgp_route, Fake(paths={"default": [P(best=False), P(as_path="1")]}), {"prefix": "p", "as_path": "1"}) is True
    assert ok(_bgp_route, Fake(paths={"default": [P(best=False, as_path="1"), P()]}), {"prefix": "p", "as_path": "1"}) is False


@pytest.mark.parametrize("params,expected", [
    ({"communities": ["1:1"]}, True),
    ({"communities": ["1:1", "1:2"]}, False),
    ({"communities": ["9:9:9"]}, True),
    ({"without_communities": ["1:2"]}, True),
    ({"without_communities": ["1:1"]}, False),
    ({"without_communities": ["9:9:9"]}, False),
    ({"as_path": "65020"}, True),
    ({"as_path": "65020 65030"}, False),
    ({"as_path_regex": "^650"}, True),
    ({"as_path_regex": "^651"}, False),
    ({"local_pref": 100}, True),
    ({"local_pref": 200}, False),
    ({"med": 0}, True),
    ({"med": 5}, False),
    ({"next_hop": "10.1.1.2"}, True),
    ({"next_hop": "10.1.1.3"}, False),
    ({"communities": ["1:1"], "med": 5}, False),
    ({"local_pref": 100, "med": 0, "next_hop": "10.1.1.2", "as_path": "65020"}, True),
])
def test_bgp_route_attributes(params, expected):
    d = Fake(paths={"default": [P(communities=["1:1"], large_communities=["9:9:9"])]})
    assert ok(_bgp_route, d, {"prefix": "p", **params}) is expected


def test_bgp_route_regex_on_an_unreadable_as_path():
    d = Fake(paths={"default": [P(as_path=None)]})
    assert ok(_bgp_route, d, {"prefix": "p", "as_path_regex": "^$"}) is True
    assert ok(_bgp_route, d, {"prefix": "p", "as_path_regex": "1"}) is False
    assert ok(_bgp_route, d, {"prefix": "p", "as_path": ""}) is False


def test_bgp_route_evidence():
    for paths, params in (([], {}), ([P()], {}), ([P(best=False)], {}), ([P()], {"med": 9}), ([P()], {"present": False}),
                          ([], {"present": False})):
        assert _bgp_route(Fake(paths={"default": paths}, evidence=[{"cmd": "b"}]), {"prefix": "p", **params})[2] \
            == [{"cmd": "b"}]


# ----------------------------------------------------------------------------------------------- ping

def ping_ev(output="", stderr=""):
    return [{"cmd": "ping", "output": output, "stderr": stderr}]


def ping(result, vrf="default", **params):
    d = Fake(ping={vrf: result})
    out = _ping(d, {"target": "10.9.9.9", **params})
    return out, d


@pytest.mark.parametrize("sent,received,expected", [(3, 3, True), (3, 2, True), (3, 1, False), (3, 0, False),
                                                    (1, 1, True), (1, 0, False), (2, 1, True), (5, 3, False),
                                                    (5, 4, True)])
def test_ping_success_tolerates_one_lost_packet(sent, received, expected):
    (passed, _, _), _ = ping((sent, received, ping_ev()))
    assert passed is expected


@pytest.mark.parametrize("sent,received,expected", [(3, 0, True), (3, 1, False), (3, 3, False), (1, 0, True)])
def test_ping_failure_needs_zero_replies(sent, received, expected):
    (passed, _, _), _ = ping((sent, received, ping_ev()), expect="failure")
    assert passed is expected


@pytest.mark.parametrize("received,need,expected", [(2, 2, True), (1, 2, False), (3, 3, True), (2, 3, False),
                                                    (1, 1, True), (0, 1, False)])
def test_ping_min_replies(received, need, expected):
    (passed, _, _), _ = ping((3, received, ping_ev()), min_replies=need)
    assert passed is expected


def test_ping_count_source_and_vrf_reach_the_driver():
    (passed, _, _), d = ping((3, 3, ping_ev()))
    assert passed and d.calls == [("ping", "10.9.9.9", None, 3, "default")]
    d = Fake(ping={"blue": (5, 5, ping_ev())})
    with pytest.raises(DriverError):   # the check names no VRF, so it pings in default, which this fake lacks
        _ping(d, {"target": "10.9.9.9", "count": 5})
    d = Fake(ping={"blue": (5, 5, ping_ev())})
    passed, _, _ = _ping(d, {"target": "10.9.9.9", "count": 5, "source": "10.0.0.1", "vrf": "blue"})
    assert passed and d.calls == [("ping", "10.9.9.9", "10.0.0.1", 5, "blue")]


@pytest.mark.parametrize("output,stderr", [
    ("connect: Network is unreachable\n", ""),
    ("", "sendto: Network unreachable\n"),
    ("From 10.0.0.1 icmp_seq=1 Destination Host Unreachable\n", ""),
    ("", "ping: No route to host"),
    ("Destination Net Unreachable", ""),
    ("destination unreachable", ""),
])
def test_ping_to_an_unreachable_destination_is_a_result(output, stderr):
    """No statistics at all, but the destination is unreachable: expect failure passes, success fails."""
    (passed, _, _), _ = ping((0, 0, ping_ev(output, stderr)), expect="failure")
    assert passed is True
    (passed, _, _), _ = ping((0, 0, ping_ev(output, stderr)))
    assert passed is False
    (passed, _, _), _ = ping((0, 0, ping_ev(output, stderr)), expect="success")
    assert passed is False


def test_ping_unreachable_text_in_any_evidence_entry():
    ev = [{"cmd": "a", "output": "x", "stderr": ""}, {"cmd": "b", "output": "", "stderr": "Network is unreachable"}]
    (passed, _, _), _ = ping((0, 0, ev), expect="failure")
    assert passed is True
    ev = [{"cmd": "a", "output": "connect: Network is unreachable"}, {"cmd": "b"}]
    (passed, _, _), _ = ping((0, 0, ev), expect="failure")
    assert passed is True


@pytest.mark.parametrize("evidence", [
    ping_ev("", "ping: bind: Cannot assign requested address\n"),
    ping_ev("garbage", ""),
    [],
    [{"cmd": "ping"}],
])
def test_ping_that_did_not_run_never_passes(evidence):
    """A ping that never ran (bad source, missing VRF) sent nothing: that is not 'no replies'."""
    for params in ({"expect": "failure"}, {}, {"expect": "success"}):
        (passed, _, _), _ = ping((0, 0, evidence), **params)
        assert passed is False


def test_ping_unreachable_after_sending_is_judged_on_the_counts():
    (passed, _, _), _ = ping((3, 0, ping_ev("Destination Host Unreachable")), expect="failure")
    assert passed is True
    (passed, _, _), _ = ping((3, 2, ping_ev("Destination Host Unreachable")), expect="failure")
    assert passed is False
    (passed, _, _), _ = ping((3, 3, ping_ev("Destination Host Unreachable")))
    assert passed is True


def test_ping_evidence_is_returned():
    for result, params in (((3, 3, ping_ev("a")), {}), ((3, 0, ping_ev("a")), {"expect": "failure"}),
                           ((0, 0, ping_ev("Network is unreachable")), {"expect": "failure"}),
                           ((0, 0, ping_ev("Network is unreachable")), {}),
                           ((0, 0, ping_ev("x", "bad")), {})):
        (_, _, evidence), _ = ping(result, **params)
        assert evidence == result[2]


# ----------------------------------------------------------------------------------------------- is_post_convergence

@pytest.mark.parametrize("c,expected", [
    (chk("route", prefix="p"), False),
    (chk("route", prefix="p", present=True), False),
    (chk("route", prefix="p", present=False), True),
    (chk("route", prefix="p", present=None), False),
    (chk("bgp_route", prefix="p"), False),
    (chk("bgp_route", prefix="p", present=False), True),
    (chk("bgp_route", prefix="p", communities=["1:1"]), True),
    (chk("bgp_route", prefix="p", next_hop="10.0.0.1"), True),
    (chk("bgp_route", prefix="p", as_path="65002"), True),
    (chk("bgp_route", prefix="p", as_path_regex="^65002"), True),
    (chk("bgp_route", prefix="p", local_pref=200), True),
    (chk("bgp_route", prefix="p", med=0), True),
    (chk("bgp_route", prefix="p", present=True), False),
    (chk("route", prefix="p", next_hop="10.0.0.1"), False),
    (chk("bgp_route", prefix="p", without_communities=["1:1"]), True),
    (chk("route", prefix="p", without_communities=["1:1"]), False),
    (chk("ping", target="t"), False),
    (chk("ping", target="t", expect="success"), False),
    (chk("ping", target="t", expect="failure"), True),
    (chk("route", prefix="p", expect="failure"), False),
    (chk("bgp_session", neighbor=NB), False),
    (chk("bgp_session", neighbor=NB, state="established"), False),
    (chk("bgp_session", neighbor=NB, state="down"), True),
    (chk("bgp_session", neighbor=NB, state="active"), True),
    (chk("ping", target="t", state="down"), False),
    (chk("bgp_prefixes", neighbor=NB, min=1), False),
    (chk("bgp_prefixes", neighbor=NB, max=1), True),
    (chk("bgp_prefixes", neighbor=NB, exact=1), True),
    (chk("bgp_prefixes", neighbor=NB, min=1, max=4), True),
    (chk("bgp_session", neighbor=NB, max=1), False),
    (chk("ping", target="t", present=False), False),
])
def test_is_post_convergence(c, expected):
    assert is_post_convergence(c) is expected


# ----------------------------------------------------------------------------------------------- _evaluate

def test_crashed_evaluator_is_a_failed_unready_sample():
    class Boom:
        def bgp_neighbors(self, vrf="default"):
            raise DriverError("bgpd is not running")

    passed, detail, evidence = _evaluate(session(), Boom())
    assert passed is False and isinstance(detail, Unready) and evidence == []
    c = Clock()
    r = run_check(session(timeout=6), Boom(), interval=3, clock=c, sleep=c.sleep)
    assert not r.passed and r.samples_unready == r.attempts and r.samples_passed == 0
    assert r.history and all(h["unready"] for h in r.history)


def test_unready_only_marks_failing_samples():
    c = Clock()
    d = Fake(c, neighbors={"default": lambda t: {} if t < 3 else nbr("idle")})
    r = run_check(session(timeout=6), d, interval=3, clock=c, sleep=c.sleep)
    assert not r.passed and r.samples_unready == 1 and r.attempts == 3
    assert [bool(h.get("unready")) for h in r.history] == [True, False, False]
    assert all(isinstance(h["detail"], str) for h in r.history)


# ----------------------------------------------------------------------------------------------- run_check

def run(c, d, clock, **kw):
    return run_check(c, d, clock=clock, sleep=clock.sleep, **kw)


def test_run_check_needs_two_passes_in_a_row():
    c = Clock()
    d = Fake(c, neighbors={"default": lambda t: nbr("established" if t >= 6 else "idle")})
    r = run(session(), d, c, interval=3)
    assert r.passed and r.attempts == 4 and r.samples_passed == 2 and r.duration == 9.0
    assert [h["passed"] for h in r.history] == [False, False, True, True]
    assert [h["t"] for h in r.history] == [0.0, 3.0, 6.0, 9.0]


def test_run_check_one_pass_is_not_enough_by_default():
    c = Clock()
    # passes once, at t=0 only: two passes in a row never happen
    d = Fake(c, neighbors={"default": lambda t: nbr("established" if t < 1 else "idle")})
    r = run(session(timeout=9), d, c, interval=3)
    assert not r.passed and r.samples_passed == 1


@pytest.mark.parametrize("confirm,attempts", [(1, 1), (2, 2), (3, 3)])
def test_run_check_confirm(confirm, attempts):
    c = Clock()
    r = run(session(), Fake(c, neighbors={"default": nbr()}), c, interval=3, confirm=confirm)
    assert r.passed and r.attempts == attempts


def test_run_check_streak_resets_on_a_failing_sample():
    c = Clock()
    seq = {0: "established", 3: "idle", 6: "established", 9: "established"}
    d = Fake(c, neighbors={"default": lambda t: nbr(seq.get(round(t), "idle"))})
    r = run(session(timeout=30), d, c, interval=3, confirm=2)
    assert r.passed and r.attempts == 4


def test_run_check_flapping_never_passes():
    c = Clock()
    d = Fake(c, neighbors={"default": lambda t: nbr("established" if round(t / 3) % 2 == 0 else "idle")})
    r = run(session(timeout=15), d, c, interval=3)
    assert not r.passed and r.samples_passed == 3 and r.attempts == 6


def test_run_check_times_out_at_the_deadline():
    c = Clock()
    r = run(session(timeout=10), Fake(c, neighbors={"default": nbr("idle")}), c, interval=3)
    assert not r.passed
    assert r.attempts == 5 and r.duration == 10.0 and c.now == 10.0   # samples at 0, 3, 6, 9, 10
    assert c.sleeps == [3, 3, 3, 1]


def test_run_check_last_sample_lands_on_the_deadline():
    """The final sleep is cut short to the deadline: a check that passes twice by then passes."""
    c = Clock()
    d = Fake(c, neighbors={"default": lambda t: nbr("established" if 9 <= t < 11 else "idle")})
    assert run(session(timeout=10), d, c, interval=3).passed


def test_run_check_zero_timeout_samples_once():
    c = Clock()
    r = run(session(timeout=0), Fake(c, neighbors={"default": nbr()}), c, interval=3)
    assert not r.passed and r.attempts == 1   # a single pass is not confirmed
    c = Clock()
    r = run(session(timeout=0), Fake(c, neighbors={"default": nbr()}), c, interval=3, confirm=1)
    assert r.passed and r.attempts == 1


def test_run_check_passing_at_the_deadline_is_not_stable():
    c = Clock()
    d = Fake(c, neighbors={"default": lambda t: nbr("established" if t >= 9 else "idle")})
    r = run(session(timeout=9), d, c, interval=3)
    assert not r.passed and r.samples_passed == 1 and r.attempts == 4


def test_run_check_keeps_the_last_50_samples_and_counts_all():
    c = Clock()
    r = run(session(timeout=300), Fake(c, neighbors={"default": nbr("idle")}), c, interval=3)
    assert r.attempts == 101 and len(r.history) == 50 and r.history[-1]["t"] == 300.0


def test_run_check_evidence_is_from_the_last_sample():
    c = Clock()
    d = Fake(c, neighbors={"default": nbr()}, evidence=[{"cmd": "last"}])
    assert run(session(), d, c).evidence == [{"cmd": "last"}]


# ----------------------------------------------------------------------------------------------- hold_check

def absent_route(prefix="0.0.0.0/0"):
    return chk("route", prefix=prefix, present=False)


def leak_after(t0, until=None):
    return lambda t: [R(prefix="0.0.0.0/0")] if t >= t0 and (until is None or t < until) else []


def test_hold_check_holds_for_the_whole_window():
    c = Clock()
    r = hold_check(absent_route(), Fake(c, routes={"default": []}), hold=10, interval=3, clock=c, sleep=c.sleep)
    assert r.passed and r.attempts == 5 and r.duration == 10.0 and r.samples_passed == 5
    assert c.sleeps == [3, 3, 3, 1]


@pytest.mark.parametrize("at", [0, 3, 9, 10])
def test_hold_check_fails_at_the_first_violation(at):
    c = Clock()
    r = hold_check(absent_route(), Fake(c, routes={"default": leak_after(at)}), hold=10, interval=3, clock=c, sleep=c.sleep)
    assert not r.passed and r.duration == at


def test_hold_check_violation_that_goes_away_still_fails():
    c = Clock()
    r = hold_check(absent_route(), Fake(c, routes={"default": leak_after(3, 4)}), hold=10, interval=3,
                   clock=c, sleep=c.sleep)
    assert not r.passed and r.attempts == 2


def test_hold_check_ends_after_the_window():
    """A violation after the window is not this check's business."""
    c = Clock()
    r = hold_check(absent_route(), Fake(c, routes={"default": leak_after(11)}), hold=10, interval=3,
                   clock=c, sleep=c.sleep)
    assert r.passed


# ----------------------------------------------------------------------------------------------- converge_then_hold

def test_converge_then_hold_fails_fast_on_a_leak_that_goes_away():
    """A leak seen after convergence is a real failure, even if it disappears later."""
    c = Clock()
    r = converge_then_hold(absent_route(), Fake(c, routes={"default": leak_after(0, 3)}), hold=10, interval=3,
                           clock=c, sleep=c.sleep)
    assert not r.passed and r.attempts == 1


def test_converge_then_hold_lets_prefix_counts_ramp_up():
    c = Clock()
    d = Fake(c, neighbors={"default": lambda t: nbr(ipv4_unicast=0 if t < 6 else 3)})
    r = converge_then_hold(prefixes(min=2, max=5), d, hold=10, interval=3, clock=c, sleep=c.sleep)
    assert r.passed
    assert r.attempts == 3 + 5 and r.samples_passed == 1 + 5 and r.duration == 16.0
    assert len(r.history) == 8 and r.history[0]["passed"] is False


def test_converge_then_hold_prefix_count_that_never_ramps_up_fails():
    c = Clock()
    d = Fake(c, neighbors={"default": nbr(ipv4_unicast=0)})
    r = converge_then_hold(prefixes(min=2, timeout=9), d, hold=10, interval=3, clock=c, sleep=c.sleep)
    assert not r.passed and r.attempts == 4 and c.now == 9


def test_converge_then_hold_prefix_count_that_drops_in_the_hold_fails():
    c = Clock()
    d = Fake(c, neighbors={"default": lambda t: nbr(ipv4_unicast=3 if t < 6 else 9)})
    r = converge_then_hold(prefixes(min=2, max=5), d, hold=10, interval=3, clock=c, sleep=c.sleep)
    assert not r.passed and r.attempts == 1 + 3


def test_converge_then_hold_counts_unready_samples_of_both_phases():
    c = Clock()
    d = Fake(c, neighbors={"default": lambda t: {} if t < 3 else nbr(ipv4_unicast=3)})
    r = converge_then_hold(prefixes(min=2), d, hold=3, interval=3, clock=c, sleep=c.sleep)
    assert r.passed and r.samples_unready == 1 and r.attempts == 2 + 2


@pytest.mark.parametrize("ctype", ["route", "bgp_prefixes"])
def test_converge_then_hold_uses_the_checks_own_hold(ctype):
    c = Clock()
    if ctype == "route":
        check, d = Check("route", {"node": "r1", "prefix": "0.0.0.0/0", "present": False}, "x", 30, hold=20), \
            Fake(c, routes={"default": leak_after(15)})
    else:
        check, d = Check("bgp_prefixes", {"node": "r1", "neighbor": NB, "max": 5}, "x", 30, hold=20), \
            Fake(c, neighbors={"default": lambda t: nbr(ipv4_unicast=1 if t < 15 else 9)})
    assert not converge_then_hold(check, d, hold=10, interval=3, clock=c, sleep=c.sleep).passed
    c = Clock()
    check.hold = None
    d.clock = c
    assert converge_then_hold(check, d, hold=10, interval=3, clock=c, sleep=c.sleep).passed


def test_converge_then_hold_keeps_the_start_of_the_reach_phase():
    c = Clock()
    d = Fake(c, neighbors={"default": lambda t: nbr(ipv4_unicast=0 if t < 3 else 3)})
    r = converge_then_hold(prefixes(min=2), d, hold=3, interval=3, clock=c, sleep=c.sleep)
    assert r.passed and r.duration == 6.0 and [h["t"] for h in r.history] == [0.0, 3.0, 0.0, 3.0]


# ----------------------------------------------------------------------------------------------- run_round_robin

def rr(checks, drivers, clock, **kw):
    return run_round_robin(checks, drivers, clock=clock, sleep=clock.sleep, **kw)


def test_round_robin_confirmation():
    c = Clock()
    a = session(node="a")
    d = Fake(c, neighbors={"default": lambda t: nbr("established" if t >= 6 else "idle")})
    [r] = rr([a], {"a": d}, c, interval=3)
    assert r.passed and r.attempts == 4 and r.samples_passed == 2 and r.duration == 9.0


@pytest.mark.parametrize("confirm", [1, 2, 3])
def test_round_robin_confirm_count(confirm):
    c = Clock()
    [r] = rr([session(node="a")], {"a": Fake(c, neighbors={"default": nbr()})}, c, interval=3, confirm=confirm)
    assert r.passed and r.attempts == confirm


def test_round_robin_single_pass_is_not_confirmed():
    c = Clock()
    d = Fake(c, neighbors={"default": lambda t: nbr("established" if t < 1 else "idle")})
    [r] = rr([session(node="a", timeout=9)], {"a": d}, c, interval=3)
    assert not r.passed and r.samples_passed == 1


def test_round_robin_streak_resets():
    c = Clock()
    seq = {0: "established", 3: "idle", 6: "established", 9: "idle", 12: "established", 15: "established"}
    d = Fake(c, neighbors={"default": lambda t: nbr(seq.get(round(t), "idle"))})
    [r] = rr([session(node="a")], {"a": d}, c, interval=3)
    assert r.passed and r.attempts == 6 and r.samples_passed == 4


def test_round_robin_flapping_fails():
    c = Clock()
    d = Fake(c, neighbors={"default": lambda t: nbr("established" if round(t / 3) % 2 == 0 else "idle")})
    [r] = rr([session(node="a", timeout=15)], {"a": d}, c, interval=3)
    assert not r.passed and r.samples_passed == 3


def test_round_robin_timeout_ends_a_check_only_on_a_failing_sample():
    """A check passing at its deadline still gets its confirming sample (and passes)."""
    c = Clock()
    d = Fake(c, neighbors={"default": lambda t: nbr("established" if t >= 9 else "idle")})
    [r] = rr([session(node="a", timeout=9)], {"a": d}, c, interval=3)
    assert r.passed and r.attempts == 5 and r.duration == 12.0


def test_round_robin_passing_then_failing_after_the_deadline_fails():
    c = Clock()
    d = Fake(c, neighbors={"default": lambda t: nbr("established" if 9 <= t < 10 else "idle")})
    [r] = rr([session(node="a", timeout=9)], {"a": d}, c, interval=3)
    assert not r.passed and r.attempts == 5 and r.samples_passed == 1


def test_round_robin_times_out_exactly_at_the_deadline():
    c = Clock()
    [r] = rr([session(node="a", timeout=10)], {"a": Fake(c, neighbors={"default": nbr("idle")})}, c, interval=3)
    assert not r.passed and r.attempts == 5 and r.duration == 10.0 and c.now == 10.0
    assert c.sleeps == [3, 3, 3, 1]


def test_round_robin_zero_timeout():
    c = Clock()
    [r] = rr([session(node="a", timeout=0)], {"a": Fake(c, neighbors={"default": nbr("idle")})}, c, interval=3)
    assert not r.passed and r.attempts == 1 and c.sleeps == []


def test_round_robin_wakes_for_the_nearest_failing_deadline():
    c = Clock()
    slow = session(node="a", timeout=4)
    fast = session(node="b", timeout=30)
    drivers = {"a": Fake(c, neighbors={"default": nbr("idle")}),
               "b": Fake(c, neighbors={"default": lambda t: nbr("established" if t >= 3 else "idle")})}
    ra, rb = rr([slow, fast], drivers, c, interval=3)
    assert not ra.passed and ra.duration == 4.0 and ra.attempts == 3
    assert rb.passed
    assert c.sleeps[:2] == [3, 1]


def test_round_robin_sleeps_the_interval_while_every_open_check_is_passing():
    c = Clock()
    a = session(node="a", timeout=1)
    d = Fake(c, neighbors={"default": nbr()})
    [r] = rr([a], {"a": d}, c, interval=3, confirm=3)
    assert r.passed and c.sleeps == [3, 3]


def test_round_robin_past_deadline_sleeps_the_interval():
    """Every still-failing check is past its deadline only between rounds that ended it; never a busy loop."""
    c = Clock()
    a = session(node="a", timeout=2)
    b = session(node="b", timeout=30)
    drivers = {"a": Fake(c, neighbors={"default": nbr("idle")}),
               "b": Fake(c, neighbors={"default": lambda t: nbr("established" if t >= 6 else "idle")})}
    ra, rb = rr([a, b], drivers, c, interval=3)
    assert not ra.passed and rb.passed
    assert all(s > 0 for s in c.sleeps)


def test_round_robin_records_every_check_of_every_round():
    """One check that's still converging must not stop the others' samples from counting."""
    c = Clock()
    first = session(node="a")
    second = session(node="b")
    drivers = {"a": Fake(c, neighbors={"default": lambda t: nbr("established" if t >= 6 else "idle")}),
               "b": Fake(c, neighbors={"default": lambda t: nbr("established" if t < 5 else "idle")})}
    ra, rb = rr([first, second], drivers, c, interval=3)
    assert ra.passed and rb.passed and rb.attempts == 2 and rb.duration == 3.0


def test_round_robin_results_in_input_order_and_on_result():
    c = Clock()
    a, b = session(node="a", timeout=0), session(node="b")
    seen = []
    drivers = {"a": Fake(c, neighbors={"default": nbr("idle")}), "b": Fake(c, neighbors={"default": nbr()})}
    out = rr([b, a], drivers, c, interval=3, on_result=seen.append)
    assert [r.check for r in out] == [b, a]
    assert [r.check for r in seen] == [a, b]   # in the order they finished
    assert [r.passed for r in out] == [True, False]


def test_round_robin_empty():
    c = Clock()
    assert rr([], {}, c) == [] and c.sleeps == []


def test_round_robin_reads_each_checks_vrf():
    c = Clock()
    blue = session(node="a", vrf="blue")
    plain = session(node="a")
    d = Fake(c, neighbors={"blue": nbr(), "default": nbr("idle")})
    rb, rp = rr([blue, plain.__class__(**{**plain.__dict__, "timeout": 3})], {"a": d}, c, interval=3)
    assert rb.passed and not rp.passed


def test_round_robin_refuses_a_short_result_list(monkeypatch):
    """A result list shorter than the checks must never silently drop a check (zip strict)."""
    c = Clock()
    a, b = session(node="a"), session(node="b")
    monkeypatch.setattr(C, "_evaluate_all", lambda checks, drivers: [(True, "ok", [])])
    with pytest.raises(ValueError):
        rr([a, b], {}, c, interval=3)
    monkeypatch.setattr(C, "_evaluate_all", lambda checks, drivers: [(True, "ok", [])] * 3)
    with pytest.raises(ValueError):
        rr([a, b], {}, c, interval=3)


def test_hold_together_refuses_a_short_result_list(monkeypatch):
    c = Clock()
    a, b = absent_route(), chk("route", node="r2", prefix="p", present=False)
    monkeypatch.setattr(C, "_evaluate_all", lambda checks, drivers: [(True, "ok", [])])
    with pytest.raises(ValueError):
        hold_together([a, b], {}, hold=10, interval=3, clock=c, sleep=c.sleep)


def test_hold_together_refuses_a_short_reach_result(monkeypatch):
    c = Clock()
    a, b = prefixes(min=1), prefixes(node="r2", min=1)
    monkeypatch.setattr(C, "run_round_robin", lambda *a, **k: [])
    with pytest.raises(ValueError):
        hold_together([a, b], {}, hold=10, interval=3, clock=c, sleep=c.sleep)


def test_evaluate_all_keeps_input_order_and_uses_each_checks_node():
    c = Clock()
    checks = [session(node=n) for n in ("a", "b", "c")]
    drivers = {"a": Fake(c, neighbors={"default": nbr()}), "b": Fake(c, neighbors={"default": nbr("idle")}),
               "c": Fake(c, neighbors={"default": nbr()})}
    assert [x[0] for x in C._evaluate_all(checks, drivers)] == [True, False, True]
    assert [x[0] for x in C._evaluate_all(checks[1:2], drivers)] == [False]
    assert C._evaluate_all([], drivers) == []
    assert [x[0] for x in C._evaluate_all(checks, drivers, workers=1)] == [True, False, True]


# ----------------------------------------------------------------------------------------------- hold_together

def ht(checks, drivers, clock, **kw):
    return hold_together(checks, drivers, clock=clock, sleep=clock.sleep, **kw)


def test_hold_together_passes_after_each_window():
    c = Clock()
    a = absent_route()
    b = Check("route", {"node": "r2", "prefix": "0.0.0.0/0", "present": False}, "b", 30, hold=20)
    drivers = {"r1": Fake(c, routes={"default": []}), "r2": Fake(c, routes={"default": []})}
    ra, rb = ht([a, b], drivers, c, hold=10, interval=3)
    assert ra.passed and rb.passed
    assert ra.duration == 10.0 and rb.duration == 20.0
    assert ra.attempts == 5 and ra.samples_passed == 5


def test_hold_together_own_window_catches_a_late_violation():
    c = Clock()
    b = Check("route", {"node": "r2", "prefix": "0.0.0.0/0", "present": False}, "b", 30, hold=20)
    [rb] = ht([b], {"r2": Fake(c, routes={"default": leak_after(15)})}, c, hold=10, interval=3)
    assert not rb.passed and rb.duration == 15.0


@pytest.mark.parametrize("at", [0, 3, 9, 10])
def test_hold_together_fails_at_the_first_violation(at):
    c = Clock()
    a, b = absent_route(), chk("route", node="r2", prefix="0.0.0.0/0", present=False)
    drivers = {"r1": Fake(c, routes={"default": leak_after(at)}), "r2": Fake(c, routes={"default": []})}
    ra, rb = ht([a, b], drivers, c, hold=10, interval=3)
    assert not ra.passed and ra.duration == at and rb.passed


def test_hold_together_violation_after_the_window_is_ignored():
    c = Clock()
    [r] = ht([absent_route()], {"r1": Fake(c, routes={"default": leak_after(11)})}, c, hold=10, interval=3)
    assert r.passed and c.sleeps == [3, 3, 3, 1]


def test_hold_together_reach_phase_then_hold():
    c = Clock()
    p = prefixes(min=2, max=5)
    d = Fake(c, neighbors={"default": lambda t: nbr(ipv4_unicast=0 if t < 6 else 3)})
    [r] = ht([p], {"r1": d}, c, hold=10, interval=3)
    assert r.passed and r.check is p


def test_hold_together_reach_that_fails_keeps_the_original_check():
    c = Clock()
    p = prefixes(min=2, max=5, timeout=9)
    [r] = ht([p], {"r1": Fake(c, neighbors={"default": nbr(ipv4_unicast=0)})}, c, hold=10, interval=3)
    assert not r.passed and r.check is p and c.now == 9


def test_hold_together_reach_window_is_bounded():
    """Convergence is already proven: counts get REACH_WINDOW seconds to ramp up, not the full timeout."""
    c = Clock()
    p = prefixes(min=2, timeout=120)
    [r] = ht([p], {"r1": Fake(c, neighbors={"default": nbr(ipv4_unicast=0)})}, c, hold=10, interval=3)
    assert not r.passed and c.now == C.REACH_WINDOW


def test_hold_together_exact_uses_exact_as_the_lower_bound():
    c = Clock()
    p = prefixes(exact=3)
    d = Fake(c, neighbors={"default": lambda t: nbr(ipv4_unicast=0 if t < 6 else 3)})
    [r] = ht([p], {"r1": d}, c, hold=10, interval=3)
    assert r.passed
    c = Clock()
    d = Fake(c, neighbors={"default": lambda t: nbr(ipv4_unicast=0 if t < 6 else 4)})
    [r] = ht([prefixes(exact=3)], {"r1": d}, c, hold=10, interval=3)
    assert not r.passed


def test_hold_together_max_only_goes_straight_into_the_hold():
    c = Clock()
    d = Fake(c, neighbors={"default": lambda t: nbr(ipv4_unicast=9 if t < 3 else 1)})
    [r] = ht([prefixes(max=5)], {"r1": d}, c, hold=10, interval=3)
    assert not r.passed and r.attempts == 1


def test_hold_together_exact_zero_has_no_reach_phase():
    c = Clock()
    d = Fake(c, neighbors={"default": lambda t: nbr(ipv4_unicast=2 if t < 3 else 0)})
    [r] = ht([prefixes(exact=0)], {"r1": d}, c, hold=10, interval=3)
    assert not r.passed and r.attempts == 1


def test_hold_together_mixed_order_and_on_result():
    c = Clock()
    a = absent_route()
    p = prefixes(node="r2", min=1, max=5)
    seen = []
    drivers = {"r1": Fake(c, routes={"default": leak_after(3)}), "r2": Fake(c, neighbors={"default": nbr(ipv4_unicast=2)})}
    out = ht([p, a], drivers, c, hold=10, interval=3, on_result=seen.append)
    assert [r.check for r in out] == [p, a] and [r.check for r in seen] == [p, a]
    assert [r.passed for r in out] == [True, False]


def test_hold_together_empty():
    c = Clock()
    assert ht([], {}, c) == [] and c.sleeps == []


def test_hold_together_unready_counts():
    c = Clock()

    class Boom:
        def routes(self, prefix, vrf="default"):
            raise DriverError("down")

    [r] = ht([absent_route()], {"r1": Boom()}, c, hold=10, interval=3)
    assert not r.passed and r.samples_unready == 1 and r.attempts == 1


# ----------------------------------------------------------------------------------------------- inconclusive_reason

def res(c, passed=False, attempts=10, samples_passed=0, unready=0):
    return Result(c, passed, "x", attempts, 30.0, "t", samples_passed=samples_passed, samples_unready=unready)


def test_inconclusive_needs_a_failure():
    assert inconclusive_reason([]) is None
    assert inconclusive_reason([res(session(), passed=True, samples_passed=2)]) is None


def test_inconclusive_when_every_failed_node_never_answered():
    rs = [res(session(), unready=10), res(chk("route", prefix="p"))]
    assert inconclusive_reason(rs)


def test_inconclusive_not_when_one_session_sample_was_readable():
    assert inconclusive_reason([res(session(), unready=9)]) is None


def test_inconclusive_not_with_zero_attempts():
    assert inconclusive_reason([res(session(), attempts=0, unready=0)]) is None


def test_inconclusive_positive_sample_anywhere_decides():
    rs = [res(session(), unready=10), res(session(node="r2"), samples_passed=1)]
    assert inconclusive_reason(rs) is None
    # a trivially true post-convergence check passing proves nothing
    rs = [res(session(), unready=10), res(absent_route(), passed=True, attempts=3, samples_passed=3)]
    assert inconclusive_reason(rs)


def test_inconclusive_post_convergence_failure_with_state_decides():
    rs = [res(session(), unready=10), res(absent_route(), attempts=3, unready=2)]
    assert inconclusive_reason(rs) is None
    rs = [res(session(), unready=10), res(absent_route(), attempts=3, unready=3)]
    assert inconclusive_reason(rs)


def test_inconclusive_node_without_session_checks_uses_its_routing_table_then_every_check():
    rs = [res(chk("route", prefix="p"), unready=10), res(chk("ping", target="t"), unready=10)]
    assert inconclusive_reason(rs)
    # 0.3.2 (agent eval T10): a ping that read cleanly doesn't show the node gave control-plane state
    rs = [res(chk("route", prefix="p"), unready=10), res(chk("ping", target="t"), unready=9)]
    assert inconclusive_reason(rs)
    rs = [res(chk("route", prefix="p"), unready=9), res(chk("ping", target="t"), unready=10)]
    assert inconclusive_reason(rs) is None
    rs = [res(chk("bgp_route", prefix="p"), unready=10), res(chk("route", prefix="q"), unready=9)]
    assert inconclusive_reason(rs) is None
    rs = [res(chk("bgp_route", prefix="p"), unready=10), res(chk("ping", target="t"), unready=9)]   # bgp_route alone
    assert inconclusive_reason(rs)
    rs = [res(chk("ping", target="t"), unready=10), res(chk("ping", target="u"), unready=9)]   # ping-only node
    assert inconclusive_reason(rs) is None


def test_inconclusive_state_checks_decide_for_their_node():
    """Routes and pings on a node whose BGP never answered don't need to be unready themselves."""
    rs = [res(prefixes(min=1), unready=10), res(chk("route", prefix="p"), unready=0)]
    assert inconclusive_reason(rs)
    rs = [res(session(), unready=10), res(prefixes(min=1), unready=3)]
    assert inconclusive_reason(rs) is None


def test_inconclusive_every_failed_node_must_be_dead():
    rs = [res(session(), unready=10), res(chk("route", node="r2", prefix="p"))]
    assert inconclusive_reason(rs) is None
    rs = [res(session(), unready=10), res(chk("route", node="r2", prefix="p"), unready=10)]
    assert inconclusive_reason(rs)
    # a passing node elsewhere with no positive sample (only post-convergence) doesn't matter
    rs = [res(session(), unready=10), res(absent_route().__class__("route", {"node": "r3", "prefix": "p",
                                                                          "present": False}, "x", 30),
                                          passed=True, attempts=3, samples_passed=3)]
    assert inconclusive_reason(rs)


# ----------------------------------------------------------------------------------------------- result fields
#
# What the report shows for each check: when it started (an aware UTC timestamp), how long it took (rounded to
# 0.1 s), its last 50 samples, the evidence of the final attempt, and its detail. A passing check reports its
# last sample's detail unchanged; a failing check is annotated only when some sample passed.

def _iso_utc(s):
    from datetime import datetime
    assert isinstance(s, str)
    return datetime.fromisoformat(s).utcoffset().total_seconds() == 0


def _same_detail(r):
    return r.detail == r.history[-1]["detail"]


def test_fields_run_check():
    c = Clock()
    d = Fake(c, neighbors={"default": lambda t: nbr("established" if t >= 2.5 else "idle")}, evidence=[{"cmd": "e"}])
    check = session()
    r = run_check(check, d, interval=1.25, clock=c, sleep=c.sleep)
    assert r.check is check and r.passed and _iso_utc(r.started) and r.evidence == [{"cmd": "e"}]
    assert r.duration == 3.8 and r.history[-1]["t"] == 3.8 and [h["t"] for h in r.history] == [0.0, 1.2, 2.5, 3.8]
    assert _same_detail(r) and isinstance(r.detail, str) and r.detail


def test_fields_run_check_failures():
    c = Clock()
    r = run_check(session(timeout=10), Fake(c, neighbors={"default": nbr("idle")}), interval=3, clock=c, sleep=c.sleep)
    assert not r.passed and _same_detail(r)            # never passed: the last sample's detail
    c = Clock()
    d = Fake(c, neighbors={"default": lambda t: nbr("established" if t >= 9 else "idle")})
    r = run_check(session(timeout=9), d, interval=3, clock=c, sleep=c.sleep)
    assert not r.passed and isinstance(r.detail, str) and not _same_detail(r)   # passing at the deadline: annotated
    c = Clock()
    d = Fake(c, neighbors={"default": lambda t: nbr("established" if round(t / 3) % 2 == 0 else "idle")})
    r = run_check(session(timeout=15), d, interval=3, clock=c, sleep=c.sleep)
    assert not r.passed and isinstance(r.detail, str) and not _same_detail(r)   # flapping: annotated


def test_run_check_default_interval():
    c = Clock()
    r = run_check(session(timeout=10), Fake(c, neighbors={"default": nbr("idle")}), clock=c, sleep=c.sleep)
    assert c.sleeps == [3, 3, 3, 1] and r.attempts == 5


def test_run_check_last_sleep_is_cut_to_the_deadline():
    c = Clock()
    run_check(session(timeout=9.5), Fake(c, neighbors={"default": nbr("idle")}), interval=3, clock=c, sleep=c.sleep)
    assert c.sleeps == [3, 3, 3, 0.5]


def test_fields_hold_check():
    c = Clock()
    check = absent_route()
    r = hold_check(check, Fake(c, routes={"default": []}, evidence=[{"cmd": "e"}]), hold=3.75, interval=1.25,
                   clock=c, sleep=c.sleep)
    assert r.check is check and r.passed and _iso_utc(r.started) and r.evidence == [{"cmd": "e"}]
    assert r.duration == 3.8 and isinstance(r.detail, str)
    c = Clock()
    r = hold_check(check, Fake(c, routes={"default": leak_after(3.75)}), hold=10, interval=1.25, clock=c, sleep=c.sleep)
    assert not r.passed and r.duration == 3.8 and _same_detail(r)


def test_hold_check_defaults_and_last_sleep():
    c = Clock()
    hold_check(absent_route(), Fake(c, routes={"default": []}), clock=c, sleep=c.sleep)
    assert c.sleeps == [3, 3, 3, 1]
    c = Clock()
    hold_check(absent_route(), Fake(c, routes={"default": []}), hold=9.5, interval=3, clock=c, sleep=c.sleep)
    assert c.sleeps == [3, 3, 3, 0.5]


def test_hold_check_keeps_50_samples():
    c = Clock()
    r = hold_check(absent_route(), Fake(c, routes={"default": []}), hold=300, interval=3, clock=c, sleep=c.sleep)
    assert r.attempts == 101 and len(r.history) == 50 and r.history[0]["t"] == 153.0


def test_converge_then_hold_defaults_and_interval():
    c = Clock()
    converge_then_hold(absent_route(), Fake(c, routes={"default": []}), clock=c, sleep=c.sleep)
    assert c.sleeps == [3, 3, 3, 1]
    c = Clock()
    converge_then_hold(absent_route(), Fake(c, routes={"default": []}), hold=10, interval=2, clock=c, sleep=c.sleep)
    assert c.sleeps == [2] * 5
    c = Clock()
    d = Fake(c, neighbors={"default": lambda t: nbr(ipv4_unicast=0 if t < 4 else 3)})
    r = converge_then_hold(prefixes(min=2), d, hold=4, interval=2, clock=c, sleep=c.sleep)
    assert r.passed and c.sleeps == [2, 2, 2, 2] and r.attempts == 3 + 3


def test_fields_converge_then_hold():
    c = Clock()
    d = Fake(c, neighbors={"default": lambda t: nbr(ipv4_unicast=0 if t < 2.5 else 3)})
    r = converge_then_hold(prefixes(min=2), d, hold=1.25, interval=1.25, clock=c, sleep=c.sleep)
    assert r.passed and _iso_utc(r.started) and r.duration == 3.7   # 2.5 to reach + 1.2 held (each rounded)


def test_converge_then_hold_keeps_50_samples():
    c = Clock()
    d = Fake(c, neighbors={"default": lambda t: nbr(ipv4_unicast=0 if t < 90 else 3)})
    r = converge_then_hold(prefixes(min=2, timeout=200), d, hold=90, interval=3, clock=c, sleep=c.sleep)
    assert r.passed and len(r.history) == 50 and r.attempts == 31 + 31


def test_converge_then_hold_adds_unready_samples_of_the_hold():
    c = Clock()
    d = Fake(c, neighbors={"default": lambda t: nbr(ipv4_unicast=3) if t < 3 else {}})
    r = converge_then_hold(prefixes(min=2, max=5), d, hold=10, interval=3, clock=c, sleep=c.sleep)
    assert not r.passed and r.samples_unready == 1 and r.samples_passed == 2


def test_fields_round_robin():
    c = Clock()
    d = Fake(c, neighbors={"default": lambda t: nbr("established" if t >= 2.5 else "idle")}, evidence=[{"cmd": "e"}])
    a = session(node="a")
    [r] = rr([a], {"a": d}, c, interval=1.25)
    assert r.check is a and r.passed and _iso_utc(r.started) and r.evidence == [{"cmd": "e"}]
    assert r.duration == 3.8 and _same_detail(r)


def test_round_robin_details():
    c = Clock()
    [r] = rr([session(node="a", timeout=10)], {"a": Fake(c, neighbors={"default": nbr("idle")})}, c, interval=3)
    assert not r.passed and _same_detail(r)
    c = Clock()
    d = Fake(c, neighbors={"default": lambda t: nbr("established" if round(t / 3) % 2 == 0 else "idle")})
    [r] = rr([session(node="a", timeout=15)], {"a": d}, c, interval=3)
    assert not r.passed and isinstance(r.detail, str) and not _same_detail(r)
    c = Clock()
    seq = {0: "established", 3: "idle", 6: "established", 9: "established"}
    d = Fake(c, neighbors={"default": lambda t: nbr(seq.get(round(t), "idle"))})
    [r] = rr([session(node="a")], {"a": d}, c, interval=3)
    assert r.passed and _same_detail(r)                 # passed after an earlier pass: not annotated


def test_round_robin_default_interval_and_50_samples():
    c = Clock()
    [r] = rr([session(node="a", timeout=10)], {"a": Fake(c, neighbors={"default": nbr("idle")})}, c)
    assert c.sleeps == [3, 3, 3, 1]
    c = Clock()
    [r] = rr([session(node="a", timeout=300)], {"a": Fake(c, neighbors={"default": nbr("idle")})}, c, interval=3)
    assert r.attempts == 101 and len(r.history) == 50 and r.history[0]["t"] == 153.0


def test_round_robin_last_sleep_is_cut_to_the_deadline():
    c = Clock()
    rr([session(node="a", timeout=9.5)], {"a": Fake(c, neighbors={"default": nbr("idle")})}, c, interval=3)
    assert c.sleeps == [3, 3, 3, 0.5]


def test_round_robin_finished_checks_dont_set_the_wake_up():
    c = Clock()
    a, b = session(node="a", timeout=2), session(node="b", timeout=4)
    drivers = {"a": Fake(c, neighbors={"default": nbr("idle")}), "b": Fake(c, neighbors={"default": nbr("idle")})}
    ra, rb = rr([a, b], drivers, c, interval=3)
    assert ra.duration == 2.0 and rb.duration == 4.0 and c.sleeps == [2, 2]


@pytest.mark.parametrize("cost", [1.0, 2.0])
def test_round_robin_deadline_passed_during_the_round_sleeps_the_interval(cost):
    """The round itself took a failing check past its deadline (or exactly to it; here a slow on_result):
    wait the interval, never 0 s."""
    c = Clock()
    failing, passing = session(node="b", timeout=1), session(node="a")
    drivers = {"a": Fake(c, neighbors={"default": nbr()}), "b": Fake(c, neighbors={"default": nbr("idle")})}

    def slow(_r):
        c.t += cost

    rb, ra = rr([failing, passing], drivers, c, interval=3, confirm=1, on_result=slow)
    assert ra.passed and not rb.passed and c.sleeps[0] == 3


def test_fields_hold_together():
    c = Clock()
    a, b = absent_route(), chk("route", node="r2", prefix="0.0.0.0/0", present=False)
    drivers = {"r1": Fake(c, routes={"default": []}, evidence=[{"cmd": "a"}]),
               "r2": Fake(c, routes={"default": leak_after(2.5)}, evidence=[{"cmd": "b"}])}
    ra, rb = ht([a, b], drivers, c, hold=3.75, interval=1.25)
    assert ra.check is a and rb.check is b and ra.passed and not rb.passed
    assert _iso_utc(ra.started) and _iso_utc(rb.started)
    assert ra.evidence == [{"cmd": "a"}] and rb.evidence == [{"cmd": "b"}]
    assert ra.duration == 3.8 and rb.duration == 2.5 and ra.attempts == 4 and rb.attempts == 3
    assert ra.history and rb.history and _same_detail(rb) and isinstance(ra.detail, str)
    c = Clock()
    [r] = ht([a], {"r1": Fake(c, routes={"default": leak_after(3.75)})}, c, hold=10, interval=1.25)
    assert r.duration == 3.8


def test_hold_together_keeps_50_samples():
    c = Clock()
    a, b = absent_route(), chk("route", node="r2", prefix="0.0.0.0/0", present=False)
    drivers = {"r1": Fake(c, routes={"default": []}), "r2": Fake(c, routes={"default": leak_after(300)})}
    ra, rb = ht([a, b], drivers, c, hold=300, interval=3)
    assert ra.passed and len(ra.history) == 50 and ra.attempts == 101 and ra.history[0]["t"] == 153.0
    assert not rb.passed and len(rb.history) == 50 and rb.history[0]["t"] == 153.0


def test_hold_together_defaults_and_last_sleep():
    c = Clock()
    hold_together([absent_route()], {"r1": Fake(c, routes={"default": []})}, clock=c, sleep=c.sleep)
    assert c.sleeps == [3, 3, 3, 1]
    c = Clock()
    ht([absent_route()], {"r1": Fake(c, routes={"default": []})}, c, hold=9.5, interval=3)
    assert c.sleeps == [3, 3, 3, 0.5]


def test_hold_together_reach_phase_timing():
    """One passing sample ends the reach phase, polled at the caller's interval."""
    c = Clock()
    d = Fake(c, neighbors={"default": lambda t: nbr(ipv4_unicast=0 if t < 4 else 3)})
    [r] = ht([prefixes(min=2)], {"r1": d}, c, hold=4, interval=2)
    assert r.passed and c.sleeps == [2, 2, 2, 2] and r.attempts == 3


def test_hold_together_failed_reach_is_the_result():
    c = Clock()
    p = prefixes(min=2, timeout=9)
    [r] = ht([p], {"r1": Fake(c, neighbors={"default": nbr(ipv4_unicast=0)})}, c, hold=10, interval=3)
    assert not r.passed and r.attempts == 4 and r.duration == 9.0


@pytest.mark.parametrize("bounds", [{"min": 2, "max": 5}, {"exact": 3}])
def test_hold_together_reach_phase_checks_only_the_lower_bound(bounds):
    """Too many prefixes from the start: the reach phase (lower bound only) passes at once and the hold fails
    on its first sample, without waiting out the reach window."""
    c = Clock()
    [r] = ht([prefixes(**bounds)], {"r1": Fake(c, neighbors={"default": nbr(ipv4_unicast=9)})}, c, hold=10, interval=3)
    assert not r.passed and c.now == 0 and r.attempts == 1
