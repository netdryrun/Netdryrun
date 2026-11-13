"""The edges of the RT-0071 fix beyond its oracle (tests/oracles/FP-042-FRRRECVHIST).

With `bgp dampening`, a prefix the neighbor withdrew stays in `show bgp ... neighbors N routes json` as a history path
(and in its totalRoutes). parse_received, which feeds bgp_received, `bgp_prefixes only:` and record's closed-world
`only` list, listed it as a prefix the neighbor sends. A prefix whose paths are all withdrawn (`history`,
`dampeningHistoryEntry`, `removed`) is no received prefix now; one live path keeps it, and a damped (suppressed) path
is still announced. totalRoutes is still checked against every prefix key listed, so a cut listing still raises."""
import json

import pytest

from netdryrun.checks import run_check
from netdryrun.config import _validate_check
from netdryrun.drivers.base import DriverError
from netdryrun.drivers.frr import FrrDriver, parse_received
from netdryrun.drivers.sonic import SonicDriver
from netdryrun.record import _session_checks
from test_verdict_drivers import Lab

NEIGHBOR = "10.0.12.2"
LIVE = "10.20.0.0/24"
GONE = "0.0.0.0/0"
FLAGS = ["history", "dampeningHistoryEntry", "removed"]


def path(net: str, **flags) -> dict:
    p = {"pathFrom": "external", "network": net, "peerId": NEIGHBOR, "path": "65002", "origin": "IGP",
         "nexthops": [{"ip": NEIGHBOR, "afi": "ipv4", "used": True}]}
    p.update(flags)
    return p


def listing(routes: dict, total: int | None = None) -> str:
    return json.dumps({"vrfId": 0, "vrfName": "default", "routerId": "1.1.1.1", "localAS": 65001, "routes": routes,
                       "totalRoutes": len(routes) if total is None else total,
                       "totalPaths": sum(len(ps) for ps in routes.values())})


def with_history(flag: str = "history") -> dict:
    return {GONE: [path(GONE, **{flag: True})], LIVE: [path(LIVE, valid=True, bestpath=True)]}


@pytest.mark.parametrize("flag", FLAGS)
def test_a_prefix_listed_only_by_withdrawn_paths_is_not_received(flag):
    assert parse_received(listing(with_history(flag)), 4) == {LIVE}


def test_several_withdrawn_paths_still_leave_the_prefix_out():
    routes = {GONE: [path(GONE, history=True), path(GONE, removed=True, peerId="10.0.13.2")], LIVE: [path(LIVE)]}
    assert parse_received(listing(routes), 4) == {LIVE}


@pytest.mark.parametrize("flag", FLAGS)
def test_one_live_path_keeps_the_prefix(flag):
    """Only a prefix whose every path is withdrawn goes: filtering on any withdrawn path would drop a live prefix,
    and `only` would never see it."""
    for paths in ([path(GONE, **{flag: True}), path(GONE, valid=True)], [path(GONE, valid=True), path(GONE, **{flag: True})]):
        assert parse_received(listing({GONE: paths, LIVE: [path(LIVE)]}), 4) == {GONE, LIVE}


@pytest.mark.parametrize("flags", [{"dampeningSuppressed": True}, {"damped": True}, {"history": False},
                                   {"removed": False, "dampeningHistoryEntry": False}])
def test_a_damped_path_or_a_flag_set_false_keeps_the_prefix(flags):
    """Decision (as RT-0070): a damped (suppressed) path is one the neighbor still announces."""
    assert parse_received(listing({GONE: [path(GONE, **flags)], LIVE: [path(LIVE)]}), 4) == {GONE, LIVE}


def test_totalroutes_is_checked_on_every_key_listed():
    """totalRoutes counts the history-only prefix: the listing above (2 keys, totalRoutes 2) is whole and reads."""
    assert parse_received(listing(with_history(), total=2), 4) == {LIVE}
    # compared with the prefixes kept (1), a whole listing would be an error, and a cut one would read
    with pytest.raises(DriverError):
        parse_received(listing(with_history(), total=1), 4)
    with pytest.raises(DriverError):
        parse_received(listing(with_history(), total=3), 4)   # one prefix missing from the listing


def test_a_listing_of_history_entries_only_is_empty_but_whole():
    assert parse_received(listing({GONE: [path(GONE, history=True)]}), 4) == set()
    with pytest.raises(DriverError):
        parse_received(listing({GONE: [path(GONE, history=True)]}, total=2), 4)


@pytest.mark.parametrize("value", ["true", 1, None, {}])
def test_a_flag_that_is_not_a_boolean_is_unexpected_even_beside_a_live_path(value):
    with pytest.raises(DriverError):
        parse_received(listing({GONE: [path(GONE, valid=True), path(GONE, history=value)]}), 4)


def test_a_path_naming_another_prefix_is_still_unexpected_when_withdrawn():
    with pytest.raises(DriverError):
        parse_received(listing({GONE: [path(LIVE, history=True)]}), 4)


def neighbors(accepted: int) -> str:
    """One established eBGP session with add-path receive on (FRR 10.4.1's default), as the RT-0066 capture."""
    return json.dumps({NEIGHBOR: {
        "remoteAs": 65002, "localAs": 65001, "nbrExternalLink": True, "bgpState": "Established",
        "neighborCapabilities": {"addPath": {"ipv4Unicast": {"rxAdvertisedAndReceived": True}}},
        "addressFamilyInfo": {"ipv4Unicast": {"acceptedPrefixCounter": accepted}}}})


def lab(routes: dict) -> Lab:
    live = sum(1 for ps in routes.values() for p in ps if not any(p.get(k) for k in FLAGS))
    return Lab([(f"neighbors {NEIGHBOR} routes json", listing(routes)), ("show bgp neighbors json", neighbors(live))])


def prefixes_check(cls, routes: dict, **raw):
    t = [0.0]
    check = _validate_check(0, {"node": "r1", "type": "bgp_prefixes", "neighbor": NEIGHBOR, **raw}, 20)
    return run_check(check, cls(lab(routes), "r1"), clock=lambda: t[0],
                     sleep=lambda s: t.__setitem__(0, t[0] + max(s, 0.5)))


@pytest.mark.parametrize("cls", [FrrDriver, SonicDriver])
def test_the_driver_lists_no_withdrawn_prefix(cls):
    """SONiC runs the FRR driver's received read (RT-0071 holds there too)."""
    assert cls(lab(with_history()), "r1").bgp_received(NEIGHBOR).value == {LIVE}


@pytest.mark.parametrize("cls", [FrrDriver, SonicDriver])
def test_only_passes_while_a_history_entry_is_listed_and_fails_when_the_prefix_returns(cls):
    r = prefixes_check(cls, with_history(), min=1, max=3, only=[LIVE])
    assert r.passed, r.detail
    back = {GONE: [path(GONE, valid=True)], LIVE: [path(LIVE, valid=True)]}
    r = prefixes_check(cls, back, min=1, max=3, only=[LIVE])
    assert not r.passed and GONE in r.detail, r.detail


@pytest.mark.parametrize("cls", [FrrDriver, SonicDriver])
def test_record_leaves_the_withdrawn_prefix_out_of_only(cls):
    drv = cls(lab(with_history()), "r1")
    warnings: list[str] = []
    checks = _session_checks("r1", drv.bgp_neighbors().value, "range", warnings, "default", drv)
    [c] = [c for c in checks if c["type"] == "bgp_prefixes" and c["afi"] == "ipv4-unicast"]
    assert c["only"] == [LIVE], (c, warnings)
