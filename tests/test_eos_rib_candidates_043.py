"""EOS reads every candidate route from `show rib route ip|ipv6 vrf <vrf> <prefix> | json` (FP-043-EOSNONBGP, red team
RT-0056 and RT-0063): `show ip route <prefix>` lists only the selected route, so a static or OSPF route that lost route
selection was never seen and `present: false` on its protocol passed.

The captured answers are cEOS 4.36.3M's (tests/fixtures/SOURCES.yml): the oracle's (ceos4363m_fp043_*) and the fix's
live proof (ceos4363m_fix043_*: a prefix with no route, a connected route, a VRF, IPv6, a VRF that doesn't exist).
Answers built here are marked DERIVED: each is a captured answer with one thing changed (a key renamed or dropped, a
family or VRF swapped), to pin what the parser does with output it doesn't know: it raises, never "no candidate".
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from netdryrun.checks import run_check
from netdryrun.config import _validate_check
from netdryrun.drivers.base import DriverError
from netdryrun.drivers.eos import EosDriver, parse_rib_candidates, parse_routes

from test_verdict_drivers import Lab

FX = Path(__file__).parent / "fixtures"
DEFAULT = "0.0.0.0/0"


def fx(name: str) -> str:
    return (FX / name).read_text(encoding="utf-8")


RT0056_ROUTE = fx("ceos4363m_fp043_rt0056_ip_route.json")      # eBGP default selected
RT0056_RIB = fx("ceos4363m_fp043_rt0056_rib_route.json")        # static 250 not selected, bgp selected
RT0056_BGP = fx("ceos4363m_fp043_rt0056_ip_bgp.json")
RT0056_RIB_9 = fx("ceos4363m_fp043_rt0056_rib_route_9.json")    # longest match: 9.9.9.0/24 answers with 0.0.0.0/0
RT0063_ROUTE = fx("ceos4363m_fp043_rt0063_ip_route.json")       # static Null0 selected
RT0063_RIB = fx("ceos4363m_fp043_rt0063_rib_route.json")        # static best (notInFec), ospf not selected
HEALTHY_B_RIB = fx("ceos4363m_fp043_healthyB_rib_route.json")   # static Null0 only


def _derived(text: str, edit) -> str:
    data = json.loads(text)
    edit(data)
    return json.dumps(data)


def _rib(data, vrf="default"):
    return data["vrfs"][vrf]["ribRoutesByProtocol"]


# ------------------------------------------------------------------------------------------------- the parser

def test_every_candidate_of_the_exact_prefix_with_best_route():
    assert sorted(parse_rib_candidates(RT0056_RIB, DEFAULT)) == [("bgp", True, "bgp"),
                                                                 ("static", False, "staticConfig")]
    assert sorted(parse_rib_candidates(RT0063_RIB, DEFAULT)) == [("ospf", False, "ospf"),
                                                                 ("static", True, "staticConfig")]


def test_a_covering_route_is_not_the_asked_prefix():
    """EOS answers `show rib route ip vrf default 9.9.9.0/24` with the 0.0.0.0/0 routes (captured): none is 9.9.9.0/24."""
    assert parse_rib_candidates(RT0056_RIB_9, "9.9.9.0/24") == []
    routes = parse_routes(fx("ceos4363m_fp043_rt0056_ip_route_9.json"), fx("ceos4363m_fp043_rt0056_ip_bgp_9.json"),
                          "9.9.9.0/24", "default", RT0056_RIB_9)
    assert routes == []


def test_not_in_fec_is_not_absent():
    """`notInFec: true` is on the selected Null0 static and on the losing OSPF route alike (captured): both count."""
    rib = json.loads(RT0063_RIB)
    assert all(h["notInFec"] for p in _rib(rib).values() for r in p["ribRoutes"].values()
               for h in r["resolvedNextHops"])
    assert {p for p, _, _ in parse_rib_candidates(RT0063_RIB, DEFAULT)} == {"static", "ospf"}
    assert parse_rib_candidates(HEALTHY_B_RIB, DEFAULT) == [("static", True, "staticConfig")]


@pytest.mark.parametrize("why,edit", [
    ("no vrfs map", lambda d: d.pop("vrfs")),
    ("no ribRoutesByProtocol", lambda d: d["vrfs"]["default"].pop("ribRoutesByProtocol")),
    ("no ribRoutes", lambda d: _rib(d)["ospf"].pop("ribRoutes")),
    ("no bestRoute", lambda d: _rib(d)["ospf"]["ribRoutes"][DEFAULT].pop("bestRoute")),
    ("bestRoute not a boolean", lambda d: _rib(d)["ospf"]["ribRoutes"][DEFAULT].update(bestRoute="false")),
    ("a protocol key it can't map", lambda d: _rib(d).update(gribi=_rib(d).pop("ospf"))),
    ("a protocol that isn't a map", lambda d: _rib(d).update(ospf=[])),
    ("a prefix key that isn't a prefix", lambda d: _rib(d)["ospf"]["ribRoutes"].update(junk={"bestRoute": False})),
    ("the VRF missing", lambda d: d["vrfs"].update(other=d["vrfs"].pop("default"))),
])
def test_output_it_does_not_know_raises(why, edit):
    """DERIVED from the rt0063 capture, one change each."""
    with pytest.raises(DriverError):
        parse_rib_candidates(_derived(RT0063_RIB, edit), DEFAULT)


def test_an_eos_error_answer_raises():
    with pytest.raises(DriverError):
        parse_rib_candidates('{"errors": ["% Invalid input"]}', DEFAULT)
    with pytest.raises(DriverError):
        parse_rib_candidates("", DEFAULT)


def test_a_key_it_cannot_map_on_a_covering_route_is_still_skipped():
    """Only the asked prefix is read: a covering route's protocol doesn't decide anything (DERIVED from rt0056_9)."""
    text = _derived(RT0056_RIB_9, lambda d: _rib(d).update(gribi=_rib(d).pop("staticConfig")))
    assert parse_rib_candidates(text, "9.9.9.0/24") == []


def test_ipv6_ospf3_is_ospf6():
    """DERIVED: the rt0063 shape for ::/0 in an IPv6 RIB, OSPFv3 keyed ospf3 (as routeType names it)."""
    def v6(d):
        rib = _rib(d)
        rib["ospf3"] = rib.pop("ospf")
        for p in rib.values():
            p["ribRoutes"] = {"::/0": p["ribRoutes"].pop(DEFAULT)}
    assert sorted(parse_rib_candidates(_derived(RT0063_RIB, v6), "::/0")) == [("ospf6", False, "ospf3"),
                                                                              ("static", True, "staticConfig")]


# ------------------------------------------------------------------------------------------------- the driver

def _lab(rib=(0, RT0056_RIB), route=RT0056_ROUTE, bgp=RT0056_BGP):
    return Lab([("show ip route", route), ("show ipv6 route", route), ("show rib route", rib),
                ("show ip bgp", bgp), ("show ipv6 bgp", bgp)])


def _check(lab, **attrs):
    check = _validate_check(0, {"type": "route", "node": "e1", "prefix": DEFAULT, **attrs}, 20)
    t = [0.0]
    return run_check(check, EosDriver(lab, "e1"), clock=lambda: t[0], sleep=lambda s: t.__setitem__(0, t[0] + max(s, .5)))


def test_the_driver_asks_the_rib_in_the_vrf_and_family():
    lab = _lab()
    EosDriver(lab, "e1").routes(DEFAULT, "default")
    assert "Cli -p 15 -c show rib route ip vrf default 0.0.0.0/0 | json" in lab.lines()
    lab = _lab(rib=(0, RT0056_RIB.replace('"default"', '"blue"')), route=RT0056_ROUTE.replace('"default"', '"blue"'),
               bgp=RT0056_BGP.replace('"default"', '"blue"'))
    routes = EosDriver(lab, "e1").routes(DEFAULT, "blue").value
    assert "Cli -p 15 -c show rib route ip vrf blue 0.0.0.0/0 | json" in lab.lines()
    assert ("static", False) in [(r.protocol, r.active) for r in routes]


def test_ipv6_asks_show_rib_route_ipv6():
    lab = Lab([("show ipv6 route", (1, "% Invalid input")), ("show rib route ipv6", (1, "% Invalid input"))])
    with pytest.raises(DriverError):
        EosDriver(lab, "e1").routes("::/0", "default")
    lab = _lab()
    try:
        EosDriver(lab, "e1").routes("2001:db8::/32", "default")
    except DriverError:
        pass   # the captured IPv4 answers aren't this prefix's; only the command asked matters here
    assert any(line.endswith("show rib route ipv6 vrf default 2001:db8::/32 | json") for line in lab.lines())


def test_the_losing_candidate_fails_present_false_and_not_present_true():
    assert not _check(_lab(), protocol="static", present=False).passed
    assert not _check(_lab(), protocol="static").passed
    assert _check(_lab(), protocol="static", active=False).passed
    assert _check(_lab(), protocol="bgp").passed
    assert _check(_lab(), protocol="ospf", present=False).passed


@pytest.mark.parametrize("answer", [
    (1, "\n> show rib route ip vrf default 0.0.0.0/0 | json\n% Invalid input at line 1\n"),   # an EOS without it
    (0, ""),
    (0, '{"errors": ["% Internal error"]}'),
    (0, "not json"),
    (1, RT0056_RIB),
])
def test_an_unread_rib_is_an_error_never_absent(answer):
    """An EOS that refuses `show rib route` (older releases), or any answer that isn't a RIB: the read fails and the
    check is no pass, whatever the routing table says."""
    with pytest.raises(DriverError):
        EosDriver(_lab(rib=answer), "e1").routes(DEFAULT)
    r = _check(_lab(rib=answer), protocol="static", present=False)
    assert not r.passed


def test_a_best_candidate_the_routing_table_lists_under_another_protocol_is_present_not_active():
    """The two reads raced (DERIVED: rt0056's RIB with bgp not best and static best, against the eBGP routing table):
    the RIB's best static is present for `present: false`, never active for `present: true`."""
    def flip(d):
        rib = _rib(d)
        rib["staticConfig"]["ribRoutes"][DEFAULT]["bestRoute"] = True
        rib["bgp"]["ribRoutes"][DEFAULT]["bestRoute"] = False
    lab = _lab(rib=(0, _derived(RT0056_RIB, flip)))
    routes = EosDriver(lab, "e1").routes(DEFAULT).value
    assert sorted((r.protocol, r.active) for r in routes) == [("bgp", True), ("static", False)]
    assert not _check(_lab(rib=(0, _derived(RT0056_RIB, flip))), protocol="static", present=False).passed
    assert not _check(_lab(rib=(0, _derived(RT0056_RIB, flip))), protocol="static").passed


# ------------------------------------------------------------------------------------------------- live proof shapes

def test_a_prefix_with_no_route_is_an_empty_protocol_map():
    """Live: no candidate at all is `ribRoutesByProtocol: {}` (IPv4, IPv6, a VRF); only that shape reads as none."""
    assert parse_rib_candidates(fx("ceos4363m_fix043_absent_rib_route_9.json"), "9.9.9.0/24") == []
    assert parse_rib_candidates(fx("ceos4363m_fix043_v6_absent_rib_route.json"), "2001:db8:99::/64") == []
    assert parse_rib_candidates(fx("ceos4363m_fix043_vrf_absent_rib_route_9.json"), "9.9.9.0/24", "blue") == []
    lab = Lab([("show ip route", fx("ceos4363m_fix043_absent_ip_route_9.json")),
               ("show rib route", fx("ceos4363m_fix043_absent_rib_route_9.json")),
               ("show ip bgp", fx("ceos4363m_fp043_rt0056_ip_bgp_9.json"))])
    assert EosDriver(lab, "e1").routes("9.9.9.0/24").value == []


def test_connected_is_connected():
    assert parse_rib_candidates(fx("ceos4363m_fix043_connected_rib_route.json"), "10.0.200.0/30") == [
        ("connected", True, "connected")]


def test_a_vrf_candidate_behind_a_connected_route():
    """Live, VRF blue: 10.88.0.0/24 connected (selected) and `ip route vrf blue 10.88.0.0/24 Null0 250` (not)."""
    rib = fx("ceos4363m_fix043_vrf_rib_route.json")
    assert sorted(parse_rib_candidates(rib, "10.88.0.0/24", "blue")) == [("connected", True, "connected"),
                                                                       ("static", False, "staticConfig")]
    with pytest.raises(DriverError, match="not in the output"):
        parse_rib_candidates(rib, "10.88.0.0/24", "default")   # another VRF's answer is never this one's
    lab = Lab([("show ip route", fx("ceos4363m_fix043_vrf_ip_route.json")), ("show rib route", rib),
               ("show ip bgp", fx("ceos4363m_fix043_vrf_ip_bgp.json"))])
    routes = EosDriver(lab, "e1").routes("10.88.0.0/24", "blue").value
    assert sorted((r.protocol, r.active) for r in routes) == [("connected", True), ("static", False)]
    assert "Cli -p 15 -c show rib route ip vrf blue 10.88.0.0/24 | json" in lab.lines()


def test_ipv6_candidate_behind_a_connected_route():
    """Live, IPv6: 2001:db8:5::/64 connected (selected) and `ipv6 route 2001:db8:5::/64 Null0 250` (not); the static
    key is staticConfig in IPv6 too."""
    rib = fx("ceos4363m_fix043_v6_rib_route.json")
    assert sorted(parse_rib_candidates(rib, "2001:db8:5::/64")) == [("connected", True, "connected"),
                                                                  ("static", False, "staticConfig")]
    lab = Lab([("show ipv6 route", fx("ceos4363m_fix043_v6_ip_route.json")), ("show rib route ipv6", rib),
               ("show ipv6 bgp", fx("ceos4363m_fix043_v6_ip_bgp.json"))])
    routes = EosDriver(lab, "e1").routes("2001:db8:5::/64").value
    assert sorted((r.protocol, r.active) for r in routes) == [("connected", True), ("static", False)]
    assert "Cli -p 15 -c show rib route ipv6 vrf default 2001:db8:5::/64 | json" in lab.lines()


def test_a_vrf_that_does_not_exist_is_an_error():
    """Live: rc 1 and `{"errors": ["VRF nosuch does not exist"]}`."""
    text = fx("ceos4363m_fix043_nosuchvrf_rib_route.json")
    with pytest.raises(DriverError):
        parse_rib_candidates(text, "9.9.9.0/24", "nosuch")
    lab = Lab([("show ip route", fx("ceos4363m_fix043_absent_ip_route_9.json").replace('"default"', '"nosuch"')),
               ("show rib route", (1, text))])
    with pytest.raises(DriverError):
        EosDriver(lab, "e1").routes("9.9.9.0/24", "nosuch")


def test_a_vrf_without_routing_has_an_empty_rib_so_the_routing_table_decides():
    """Live: VRF red (no `ip routing vrf red`) answers an empty protocol map, like a VRF with no route. The routing
    table's `routingDisabled: true` is read first and makes the check an error (A-0049), so the RIB never reads it as
    absent (DERIVED routing-table answer: the captured empty one with the flag set)."""
    assert parse_rib_candidates(fx("ceos4363m_fix043_norouting_rib_route.json"), "9.9.9.0/24", "red") == []
    route = _derived(fx("ceos4363m_fix043_absent_ip_route_9.json"),
                     lambda d: d["vrfs"].update(red={**d["vrfs"].pop("default"), "routingDisabled": True}))
    lab = Lab([("show ip route", route), ("show rib route", fx("ceos4363m_fix043_norouting_rib_route.json")),
               ("show ip bgp", fx("ceos4363m_fix043_vrf_ip_bgp.json"))])
    with pytest.raises(DriverError, match="routing disabled"):
        EosDriver(lab, "e1").routes("9.9.9.0/24", "red")

