"""The node's own BGP path that routeType.localAgg doesn't mark (adversary review of FP-043-EOSAGG, F4).

`aggregate-address P advertise-only` puts the aggregate in neither the routing table nor the RIB (live, cEOS 4.36.3M,
ceos4363m_advagg_advonly_*): the BGP table's own path is the only read that shows it, and the node sends it to its
peers. 0.4.3's fix named that path bgp by its localAgg flag, read with a default of false, so on an EOS that doesn't
print the flag `protocol: bgp present: false` would pass while the aggregate is advertised. A `network` statement or
redistribution needs a route in the RIB to originate from; an own path with nothing in the routing table or the RIB
has no source but BGP itself, so it is a bgp route whatever the flag says (FP-042-FRR102: a missing key needs another
source, never a guess). Answers built here are marked DERIVED: a captured answer with one thing changed.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from netdryrun.checks import run_check
from netdryrun.config import _validate_check
from netdryrun.drivers.base import DriverError
from netdryrun.drivers.eos import EosDriver, parse_routes

from test_verdict_drivers import Lab

FX = Path(__file__).parent / "fixtures"
ADV = "10.70.0.0/16"


def fx(name: str) -> str:
    return (FX / name).read_text(encoding="utf-8")


ROUTE = fx("ceos4363m_advagg_advonly_ip_route.json")        # no route
RIB = fx("ceos4363m_advagg_advonly_rib_route.json")          # no candidate
BGP = fx("ceos4363m_advagg_advonly_ip_bgp.json")             # the node's own path, localAgg true


def _flag_false() -> str:
    """DERIVED: the live answer with localAgg false instead of true."""
    data = json.loads(BGP)
    data["vrfs"]["default"]["bgpRouteEntries"][ADV]["bgpRoutePaths"][0]["routeType"]["localAgg"] = False
    return json.dumps(data)


def _flag_missing() -> str:
    """DERIVED: the live answer with the localAgg key removed, nothing else changed (an EOS that doesn't print it)."""
    data = json.loads(BGP)
    route_type = data["vrfs"]["default"]["bgpRouteEntries"][ADV]["bgpRoutePaths"][0]["routeType"]
    del route_type["localAgg"]
    return json.dumps(data)


BGP_NOFLAG = _flag_missing()


def _verdicts(bgp: str) -> dict[str, bool]:
    lab = Lab([("show ip route", ROUTE), ("show rib route", RIB), ("show ip bgp", bgp)])
    out = {}
    for name, attrs in {"bgp-absent": {"protocol": "bgp", "present": False}, "any-absent": {"present": False},
                        "bgp-candidate": {"protocol": "bgp", "active": False}, "bgp-active": {"protocol": "bgp"}}.items():
        check = _validate_check(0, {"type": "route", "node": "e1", "prefix": ADV, **attrs}, 20)
        t = [0.0]
        out[name] = run_check(check, EosDriver(lab, "e1"), clock=lambda t=t: t[0],
                              sleep=lambda s, t=t: t.__setitem__(0, t[0] + max(s, .5))).passed
    return out


# FRR 10.4.1 names an advertise-only aggregate the same way: in the BGP table, not installed (adversary review)
EXPECTED = {"bgp-absent": False, "any-absent": False, "bgp-candidate": True, "bgp-active": False}


@pytest.mark.parametrize("bgp", [pytest.param(BGP, id="live-localAgg-true"),
                                 pytest.param(BGP_NOFLAG, id="DERIVED-localAgg-missing"),
                                 pytest.param(_flag_false(), id="DERIVED-localAgg-false")])
def test_an_advertise_only_aggregate_is_a_bgp_route_whatever_the_flag_says(bgp):
    assert [(r.protocol, r.active) for r in parse_routes(ROUTE, bgp, ADV, "default", RIB)] == [("bgp", False)]
    assert _verdicts(bgp) == EXPECTED


def test_the_derived_answer_differs_from_the_live_one_only_by_the_flag():
    assert "localAgg" in BGP and "localAgg" not in BGP_NOFLAG
    live = json.loads(BGP)
    del live["vrfs"]["default"]["bgpRouteEntries"][ADV]["bgpRoutePaths"][0]["routeType"]["localAgg"]
    assert live == json.loads(BGP_NOFLAG)


def test_without_a_rib_read_an_empty_routing_table_proves_nothing_so_no_route_is_added():
    """No RIB answer (bgp_paths' VRF check, or an older caller): an empty routing table doesn't show that no other
    protocol holds the prefix, so the rule needs the RIB (routes() always reads it). A network statement's own path
    stays out of the route check, as test_router_own_bgp_route_is_not_a_received_route_anywhere requires."""
    assert parse_routes(ROUTE, BGP_NOFLAG, ADV) == []


def test_a_rib_with_another_protocols_candidate_is_the_source_so_no_bgp_route_is_added():
    """DERIVED: the advertise-only answers with a static candidate in the RIB (not selected): the own path then has
    a source to originate from, and the static is the only route read."""
    rib = json.loads(RIB)
    rib["vrfs"]["default"]["ribRoutesByProtocol"] = json.loads(fx("ceos4363m_rcheos_aggstatic_rib_route.json"))[
        "vrfs"]["default"]["ribRoutesByProtocol"]
    rib["vrfs"]["default"]["ribRoutesByProtocol"].pop("bgp")
    rib = json.dumps(rib).replace("10.66.0.0/16", ADV)
    assert [r.protocol for r in parse_routes(ROUTE, BGP_NOFLAG, ADV, "default", rib)] == ["static"]


def test_an_unflagged_own_path_beside_a_rib_bgp_entry_is_an_error():
    """DERIVED: the live aggregate behind a static (aggstatic) with localAgg removed. The RIB's bgp entry is then
    neither the own aggregate nor a learned path by any read: an error, never a guess."""
    bgp = json.loads(fx("ceos4363m_rcheos_aggstatic_ip_bgp.json"))
    for e in bgp["vrfs"]["default"]["bgpRouteEntries"].values():
        for p in e["bgpRoutePaths"]:
            p["routeType"].pop("localAgg", None)
    with pytest.raises(DriverError, match="localAgg"):
        parse_routes(fx("ceos4363m_rcheos_aggstatic_ip_route.json"), json.dumps(bgp), "10.66.0.0/16", "default",
                     fx("ceos4363m_rcheos_aggstatic_rib_route.json"))


def test_an_unflagged_own_path_beside_a_route_of_another_protocol_is_not_read_as_bgp():
    """DERIVED: the aggregate-behind-a-static answers with the RIB's bgp entry gone and localAgg removed: what a
    `network` statement of a static prefix looks like (the static is in both reads, the own path in the BGP table).
    The static is the route it originates from, so no bgp route is added. This is the documented limit of the rule:
    an EOS that prints no localAgg and holds an advertise-only aggregate beside a static for the same prefix reads
    the same way (live 4.36.3M prints the flag on the aggregate, and the first test reads it)."""
    rib = json.loads(fx("ceos4363m_rcheos_aggstatic_rib_route.json"))
    rib["vrfs"]["default"]["ribRoutesByProtocol"].pop("bgp")
    bgp = json.loads(fx("ceos4363m_rcheos_aggstatic_ip_bgp.json"))
    for e in bgp["vrfs"]["default"]["bgpRouteEntries"].values():
        for p in e["bgpRoutePaths"]:
            p["routeType"].pop("localAgg", None)
    out = parse_routes(fx("ceos4363m_rcheos_aggstatic_ip_route.json"), json.dumps(bgp), "10.66.0.0/16", "default",
                       json.dumps(rib))
    assert [(r.protocol, r.active) for r in out] == [("static", True)]
