"""The edges of the RT-0070 fix beyond its oracle (tests/oracles/FP-042-FRRDAMP).

With `bgp dampening`, bgpd keeps a withdrawn route listed as a dampening history entry. The FRR (and SONiC) driver
read it as a received, not-selected BGP route. A history entry (`dampeningHistoryEntry` in a prefix's detail,
`history` in a listing) and a path being removed (`removed`) are no path now; a damped (suppressed) path is still a
received route the peer announces: present, never active."""
import json

import pytest

from netdryrun.drivers.base import DriverError
from netdryrun.drivers.frr import FrrDriver, _withdrawn, count_neighbor_prefixes, parse_bgp_paths, parse_routes
from netdryrun.drivers.sonic import SonicDriver
from test_verdict_drivers import Lab

PFX = "0.0.0.0/0"
NO_ROUTE = json.dumps({PFX: []})


def path(**flags):
    p = {"aspath": {"string": "65002", "segments": [{"type": "as-sequence", "list": [65002]}], "length": 1},
         "origin": "IGP", "nexthops": [{"ip": "10.0.12.2", "afi": "ipv4", "used": True}],
         "peer": {"peerId": "10.0.12.2", "type": "external"}}
    p.update(flags)
    return p


def bgp(*paths):
    return json.dumps({"prefix": PFX, "pathCount": len(paths), "paths": list(paths)})


@pytest.mark.parametrize("flag", ["dampeningHistoryEntry", "history", "removed"])
def test_a_withdrawn_path_is_no_bgp_route(flag):
    assert parse_routes(NO_ROUTE, PFX, bgp(path(**{flag: True}))) == []
    assert parse_bgp_paths(bgp(path(**{flag: True})), PFX) == []


@pytest.mark.parametrize("flag", ["dampeningHistoryEntry", "history", "removed"])
def test_a_flag_set_false_keeps_the_path(flag):
    routes = parse_routes(NO_ROUTE, PFX, bgp(path(**{flag: False})))
    assert [(r.protocol, r.active) for r in routes] == [("bgp", False)]
    assert len(parse_bgp_paths(bgp(path(**{flag: False})), PFX)) == 1


def test_a_damped_path_is_still_received_never_active():
    """Decision: a damped (suppressed) path is one the peer still announces, so the route is present via bgp and not
    selected, as for a path with an unusable next hop."""
    for flags in ({"dampeningSuppressed": True}, {"damped": True}):
        routes = parse_routes(NO_ROUTE, PFX, bgp(path(**flags)))
        assert [(r.protocol, r.active) for r in routes] == [("bgp", False)]


def test_a_history_entry_beside_a_received_path_leaves_the_received_one():
    routes = parse_routes(NO_ROUTE, PFX, bgp(path(dampeningHistoryEntry=True), path(valid=True)))
    assert [(r.protocol, r.active) for r in routes] == [("bgp", False)]
    got = parse_bgp_paths(bgp(path(history=True), path(valid=True, peer={"peerId": "10.0.13.2"})), PFX)
    assert [p.neighbor for p in got] == ["10.0.13.2"]


def test_the_path_count_still_counts_the_listed_history_entry():
    """pathCount counts the history entry: dropping it before the count check would make every such answer an error,
    and a count that disagrees with the listing is still one."""
    with pytest.raises(DriverError):
        parse_routes(NO_ROUTE, PFX, json.dumps({"prefix": PFX, "pathCount": 2, "paths": [path(history=True)]}))


@pytest.mark.parametrize("value", ["true", 1, None, {}])
def test_a_flag_that_is_not_a_boolean_is_unexpected(value):
    with pytest.raises(DriverError):
        _withdrawn("cmd", path(dampeningHistoryEntry=value))
    with pytest.raises(DriverError):
        parse_routes(NO_ROUTE, PFX, bgp(path(history=value)))


def test_withdrawn_is_any_of_the_flags():
    assert _withdrawn("cmd", path()) is False
    assert _withdrawn("cmd", path(history=False, removed=True)) is True
    assert _withdrawn("cmd", path(dampeningHistoryEntry=True, removed=False)) is True
    assert _withdrawn("cmd", path(damped=True, dampeningSuppressed=True)) is False


def test_the_neighbor_listing_leaves_out_both_history_keys():
    routes = {"10.20.0.0/24": [{"valid": True}, {"dampeningHistoryEntry": True}],
              "10.21.0.0/24": [{"history": True}]}
    assert count_neighbor_prefixes(json.dumps({"routes": routes}), "cmd", 1) == 1
    with pytest.raises(DriverError):
        count_neighbor_prefixes(json.dumps({"routes": {"10.20.0.0/24": [{"history": "yes"}]}}), "cmd", 0)


def withdrawn_lab(flag, prefix=PFX, route_answer=NO_ROUTE):
    p = path(**{flag: True})
    return Lab([(f"show ip route {prefix} json", route_answer),
                (f"show bgp ipv4 unicast {prefix} json",
                 json.dumps({"prefix": prefix, "pathCount": 1, "paths": [p]}))])


@pytest.mark.parametrize("flag", ["dampeningHistoryEntry", "history", "removed"])
@pytest.mark.parametrize("cls", [FrrDriver, SonicDriver])
def test_the_driver_reports_no_route_for_a_withdrawn_entry(cls, flag):
    """SONiC runs the FRR driver's route read (RT-0070 holds there too)."""
    assert cls(withdrawn_lab(flag), "r1").routes(PFX).value == []
    # any other prefix: zebra answers `{}` without it (FRR 10.4.1), the case 0.3.1 to 0.4.1 also passed on
    assert cls(withdrawn_lab(flag, "10.40.0.0/24", "{}"), "r1").routes("10.40.0.0/24").value == []


def _route_check(cls, lab, prefix, **raw):
    from netdryrun.checks import run_check
    from netdryrun.config import _validate_check
    t = [0.0]
    check = _validate_check(0, {"node": "r1", "type": "route", "prefix": prefix, **raw}, 20)
    return run_check(check, cls(lab, "r1"), clock=lambda: t[0], sleep=lambda s: t.__setitem__(0, t[0] + max(s, 0.5)))


@pytest.mark.parametrize("flag", ["dampeningHistoryEntry", "removed"])
@pytest.mark.parametrize("cls", [FrrDriver, SonicDriver])
def test_checks_on_a_withdrawn_entry(cls, flag):
    """The false pass is gone (`active: false` fails) and so is the false alarm: a `present: false` guard on a route
    the peer withdrew passes instead of reading it as unexpectedly present."""
    assert _route_check(cls, withdrawn_lab(flag), PFX, protocol="bgp", active=False).passed is False
    assert _route_check(cls, withdrawn_lab(flag), PFX, protocol="bgp", present=False).passed is True
    assert _route_check(cls, withdrawn_lab(flag), PFX, present=False).passed is True
    r = _route_check(cls, withdrawn_lab(flag, "10.40.0.0/24", "{}"), "10.40.0.0/24", present=False)
    assert r.passed is True, r.detail


def test_a_damped_route_still_fails_present_false():
    lab = Lab([(f"show ip route {PFX} json", NO_ROUTE),
               (f"show bgp ipv4 unicast {PFX} json", bgp(path(dampeningSuppressed=True)))])
    assert _route_check(FrrDriver, lab, PFX, present=False).passed is False
