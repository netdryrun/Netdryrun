"""Every key a check accepts must change the verdict. A key that validates but is never compared is a check
that doesn't test what it says.

That was the shape of 0.3.0 false passes 3 and 4 (`afi` and `protocol` were accepted and never compared
with anything) and of the B-series in the pre-launch audit. Strict validation stops *unknown* keys; this
stops *known but ignored* ones, including the next key someone adds to `CHECK_TYPES`.

For each check type and each key it accepts, FLIPS holds a lab state and two values of that key: with the
first the check passes, with the second it fails, on the same state. The check goes through the real
validator and the runner's own schedulers (`run_round_robin` for positive checks, `hold_together` for
post-convergence ones), with a driver per node, VRF-aware, on a fake clock.

A key that by design doesn't decide a verdict goes in NOT_A_VERDICT_KEY with the reason. The meta-test
fails for any key in neither table.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import pytest
from test_checks import FakeClock

from netdryrun.checks import hold_together, is_post_convergence, run_round_robin
from netdryrun.config import CHECK_TYPES, COMMON_KEYS, _validate_check
from netdryrun.drivers.base import BgpNeighbor, BgpPath, Observation, Route


@dataclass
class State:
    neighbors: dict[str, BgpNeighbor] = field(default_factory=dict)
    routes: dict[str, list[Route]] = field(default_factory=dict)
    paths: dict[str, list[BgpPath]] = field(default_factory=dict)
    pings: dict = field(default_factory=dict)   # target or (target, source) -> (sent, received)


class TimedDriver:
    """One node: {vrf: State} as a function of time, given as [(from_t, {vrf: State}), ...]."""

    def __init__(self, timeline, clock):
        self.timeline, self.clock = timeline, clock

    def _state(self, vrf) -> State:
        now = [s for t, s in self.timeline if t <= self.clock()][-1]
        return now.get(vrf, State())

    def bgp_neighbors(self, vrf="default"):
        return Observation(dict(self._state(vrf).neighbors), [])

    def routes(self, prefix, vrf="default"):
        return Observation(list(self._state(vrf).routes.get(prefix, [])), [])

    def bgp_paths(self, prefix, vrf="default"):
        return Observation(list(self._state(vrf).paths.get(prefix, [])), [])

    def ping(self, target, source, count, vrf="default"):
        pings = self._state(vrf).pings
        sent, received = pings.get((target, source), pings.get(target, (count, 0)))
        return Observation((min(sent, count), min(received, count)), [{"stderr": ""}])


def verdict(raw: dict, nodes: dict) -> bool:
    """nodes: {node: State | [(from_t, {vrf: State})]}; a bare State is the default VRF from t=0."""
    clock = FakeClock()
    timelines = {n: (s if isinstance(s, list) else [(0, {"default": s})]) for n, s in nodes.items()}
    drivers = {n: TimedDriver(t, clock) for n, t in timelines.items()}
    check = _validate_check(0, dict(raw), 30)
    if is_post_convergence(check):
        [r] = hold_together([check], drivers, hold=10, interval=3, clock=clock, sleep=clock.sleep)
    else:
        [r] = run_round_robin([check], drivers, interval=3, clock=clock, sleep=clock.sleep)
    return r.passed


N, N2 = "10.0.0.2", "10.0.0.3"
P, P2 = "10.66.0.0/16", "10.77.0.0/16"
T, T2 = "10.9.9.9", "10.9.9.10"


def up(count=5, **families):
    return {N: BgpNeighbor(N, "established", {"ipv4-unicast": count, **families})}


def best(**kw):
    attrs = dict(best=True, as_path="65002", next_hop="10.0.0.2", local_pref=100, med=0, communities=["65000:1"])
    return [BgpPath(**{**attrs, **kw})]


S = {"type": "bgp_session", "node": "r1", "neighbor": N}
PX = {"type": "bgp_prefixes", "node": "r1", "neighbor": N}
R = {"type": "route", "node": "r1", "prefix": P}
BR = {"type": "bgp_route", "node": "r1", "prefix": P}
PING = {"type": "ping", "node": "r1", "target": T}

EMPTY = State()
SESSION = State(neighbors=up())
ROUTE = State(routes={P: [Route(P, "bgp", True)]})
PATH = State(paths={P: best()})
PINGS = State(pings={T: (3, 3), T2: (3, 0)})
IN_RED = [(0, {"default": EMPTY, "red": State(neighbors=up(), routes=ROUTE.routes, paths=PATH.paths,
                                                  pings=PINGS.pings)})]
# for the timing keys: a route that appears at t=15, and a leak that appears at t=12
ROUTE_LATE = [(0, {"default": EMPTY}), (15, {"default": ROUTE})]
LEAK_LATE = [(0, {"default": EMPTY}), (12, {"default": ROUTE})]

# (type, key): (passing check, the change that must make it fail, the nodes' state)
FLIPS = {
    ("bgp_session", "node"): (S, {"node": "r2"}, {"r1": SESSION, "r2": EMPTY}),
    ("bgp_session", "neighbor"): (S, {"neighbor": N2}, {"r1": SESSION}),
    ("bgp_session", "state"): (S, {"state": "idle"}, {"r1": SESSION}),
    ("bgp_session", "vrf"): ({**S, "vrf": "red"}, {"vrf": "default"}, {"r1": IN_RED}),
    ("bgp_prefixes", "node"): ({**PX, "min": 1}, {"node": "r2"}, {"r1": SESSION, "r2": EMPTY}),
    ("bgp_prefixes", "neighbor"): ({**PX, "min": 1}, {"neighbor": N2}, {"r1": SESSION}),
    ("bgp_prefixes", "min"): ({**PX, "min": 5}, {"min": 6}, {"r1": SESSION}),
    ("bgp_prefixes", "max"): ({**PX, "max": 5}, {"max": 4}, {"r1": SESSION}),
    ("bgp_prefixes", "exact"): ({**PX, "exact": 5}, {"exact": 4}, {"r1": SESSION}),
    ("bgp_prefixes", "afi"): ({**PX, "max": 5, "afi": "ipv4-unicast"}, {"afi": "ipv6-unicast"},
                              {"r1": State(neighbors=up(5, **{"ipv6-unicast": 9}))}),
    ("bgp_prefixes", "vrf"): ({**PX, "min": 1, "vrf": "red"}, {"vrf": "default"}, {"r1": IN_RED}),
    ("route", "node"): (R, {"node": "r2"}, {"r1": ROUTE, "r2": EMPTY}),
    ("route", "prefix"): (R, {"prefix": P2}, {"r1": ROUTE}),
    ("route", "present"): (R, {"present": False}, {"r1": ROUTE}),
    ("route", "protocol"): ({**R, "protocol": "bgp"}, {"protocol": "static"}, {"r1": ROUTE}),
    ("route", "active"): ({**R, "active": False}, {"active": True}, {"r1": State(routes={P: [Route(P, "bgp", False)]})}),
    ("route", "vrf"): ({**R, "vrf": "red"}, {"vrf": "default"}, {"r1": IN_RED}),
    ("bgp_route", "node"): (BR, {"node": "r2"}, {"r1": PATH, "r2": EMPTY}),
    ("bgp_route", "prefix"): (BR, {"prefix": P2}, {"r1": PATH}),
    ("bgp_route", "present"): (BR, {"present": False}, {"r1": PATH}),
    ("bgp_route", "vrf"): ({**BR, "vrf": "red"}, {"vrf": "default"}, {"r1": IN_RED}),
    ("bgp_route", "communities"): ({**BR, "communities": ["65000:1"]}, {"communities": ["65000:2"]}, {"r1": PATH}),
    ("bgp_route", "without_communities"): ({**BR, "without_communities": ["65000:2"]},
                                           {"without_communities": ["65000:1"]}, {"r1": PATH}),
    ("bgp_route", "as_path"): ({**BR, "as_path": "65002"}, {"as_path": "65003"}, {"r1": PATH}),
    ("bgp_route", "as_path_regex"): ({**BR, "as_path_regex": "^65002$"}, {"as_path_regex": "^65003$"}, {"r1": PATH}),
    ("bgp_route", "local_pref"): ({**BR, "local_pref": 100}, {"local_pref": 200}, {"r1": PATH}),
    ("bgp_route", "med"): ({**BR, "med": 0}, {"med": 5}, {"r1": PATH}),
    ("bgp_route", "next_hop"): ({**BR, "next_hop": "10.0.0.2"}, {"next_hop": "10.0.0.9"}, {"r1": PATH}),
    ("ping", "node"): (PING, {"node": "r2"}, {"r1": PINGS, "r2": EMPTY}),
    ("ping", "target"): (PING, {"target": T2}, {"r1": PINGS}),
    ("ping", "source"): ({**PING, "source": "10.0.0.1"}, {"source": "10.0.0.99"},
                         {"r1": State(pings={(T, "10.0.0.1"): (3, 3), (T, "10.0.0.99"): (3, 0)})}),
    ("ping", "expect"): (PING, {"expect": "failure"}, {"r1": PINGS}),
    ("ping", "vrf"): ({**PING, "vrf": "red"}, {"vrf": "default"}, {"r1": IN_RED}),
    ("ping", "count"): ({**PING, "count": 3}, {"count": 10}, {"r1": State(pings={T: (10, 3)})}),
    ("ping", "min_replies"): ({**PING, "count": 5, "min_replies": 3}, {"min_replies": 4}, {"r1": State(pings={T: (5, 3)})}),
    # the common keys that decide a verdict: how long a check may wait, how long a negative one must hold
    ("*", "timeout"): ({**R, "timeout": 30}, {"timeout": 5}, {"r1": ROUTE_LATE}),
    ("*", "hold"): ({**R, "present": False, "hold": 5}, {"hold": 30}, {"r1": LEAK_LATE}),
}

NOT_A_VERDICT_KEY = {
    "type": "selects the evaluator: a different type is a different check, attacked type by type here",
    "name": "a label for reports only, by design",
}


def _all_keys():
    for ctype, spec in sorted(CHECK_TYPES.items()):
        for key in sorted(set(spec["required"]) | set(spec["optional"]) | set(COMMON_KEYS)):
            yield ctype, key


@pytest.mark.parametrize("ctype,key", [pytest.param(t, k, id=f"{t}.{k}") for t, k in FLIPS if t != "*"])
def test_the_key_decides_the_verdict(ctype, key):
    base, change, nodes = FLIPS[(ctype, key)]
    assert base["type"] == ctype
    assert verdict(base, nodes) is True, "the base check must pass, or the flip proves nothing"
    assert verdict({**base, **change}, nodes) is False, f"{ctype}.{key} changed and the verdict didn't"


@pytest.mark.parametrize("key", [k for t, k in FLIPS if t == "*"])
def test_the_common_key_decides_the_verdict(key):
    base, change, nodes = FLIPS[("*", key)]
    assert verdict(base, nodes) is True
    assert verdict({**base, **change}, nodes) is False, f"{key} changed and the verdict didn't"


@pytest.mark.parametrize("ctype,key", [pytest.param(t, k, id=f"{t}.{k}") for t, k in _all_keys()])
def test_meta_every_accepted_key_is_load_bearing(ctype, key):
    """A key in CHECK_TYPES (or COMMON_KEYS) needs a FLIPS entry proving it can turn a pass into a fail,
    or a written reason in NOT_A_VERDICT_KEY. Adding a key without either turns CI red here."""
    assert (ctype, key) in FLIPS or ("*", key) in FLIPS or key in NOT_A_VERDICT_KEY, (
        f"{ctype}.{key} is accepted by the validator but nothing shows it can change a verdict: add a FLIPS "
        "entry in tests/test_load_bearing_keys.py (or, if it truly can't, a reason in NOT_A_VERDICT_KEY)")


def test_meta_no_stale_entries():
    keys = set(_all_keys())
    stale = [k for k in FLIPS if k[0] != "*" and k not in keys]
    assert not stale, f"FLIPS entries for keys that no longer exist: {stale}"
