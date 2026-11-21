"""The node's own BGP paths that routeType.localAgg doesn't mark (adversary review of FP-043-EOSAGG, F4 and its
re-check).

`aggregate-address P advertise-only` puts the aggregate in neither the routing table nor the RIB (live, cEOS 4.36.3M,
ceos4363m_advagg_advonly_*): the BGP table's own path is the only read that shows it, and the node sends it to its
peers. 0.4.3's fix named that path bgp by its localAgg flag, read with a default of false, so on an EOS that doesn't
print the flag `protocol: bgp present: false` would have passed while the aggregate is advertised. A `network`
statement's own path names the route it comes from in routeDetail.redistributionProtocol (live,
ceos4363m_advagg_network_*); the aggregate's has no such field, behind a static too (ceos4363m_advagg_aostatic_*).
An own path with neither field is refused (FP-042-FRR102: a missing key needs another source, never a guess).
Answers built here are marked DERIVED: a captured answer with one thing changed.
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


def test_a_live_advertise_only_aggregate_is_a_bgp_route_not_selected():
    assert [(r.protocol, r.active) for r in parse_routes(ROUTE, BGP, ADV, "default", RIB)] == [("bgp", False)]
    assert _verdicts(BGP) == EXPECTED


@pytest.mark.parametrize("bgp", [pytest.param(BGP_NOFLAG, id="DERIVED-localAgg-missing"),
                                 pytest.param(_flag_false(), id="DERIVED-localAgg-false")])
def test_an_advertise_only_aggregate_without_the_flag_is_refused(bgp):
    """No flag and no redistributionProtocol: neither the aggregate nor a `network` statement by any read."""
    with pytest.raises(DriverError, match="neither routeType.localAgg .* nor routeDetail.redistributionProtocol"):
        parse_routes(ROUTE, bgp, ADV, "default", RIB)
    with pytest.raises(DriverError, match="redistributionProtocol"):
        parse_routes(ROUTE, bgp, ADV)   # without the RIB read too
    assert set(_verdicts(bgp).values()) == {False}   # an error is never a pass, `present: false` included


def test_the_derived_answer_differs_from_the_live_one_only_by_the_flag():
    assert "localAgg" in BGP and "localAgg" not in BGP_NOFLAG
    live = json.loads(BGP)
    del live["vrfs"]["default"]["bgpRouteEntries"][ADV]["bgpRoutePaths"][0]["routeType"]["localAgg"]
    assert live == json.loads(BGP_NOFLAG)


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


# live, cap3 of the re-check: 10.80.0.0/16 advertise-only beside `ip route 10.80.0.0/16 Null0`, and the `network
# 10.79.1.0/24` route of `ip route 10.79.1.0/24 Null0`
AO, NET = "10.80.0.0/16", "10.79.1.0/24"
AO_READS = [fx(f"ceos4363m_advagg_aostatic_{n}.json") for n in ("ip_route", "ip_bgp", "rib_route")]
NET_READS = [fx(f"ceos4363m_advagg_network_{n}.json") for n in ("ip_route", "ip_bgp", "rib_route")]


def _own_path(bgp: str, prefix: str, edit) -> str:
    data = json.loads(bgp)
    [path] = data["vrfs"]["default"]["bgpRouteEntries"][prefix]["bgpRoutePaths"]
    edit(path)
    return json.dumps(data)


def _routes(reads, prefix):
    route, bgp, rib = reads
    return [(r.protocol, r.active) for r in parse_routes(route, bgp, prefix, "default", rib)]


def test_a_live_advertise_only_aggregate_behind_a_static_is_the_static_and_a_bgp_route():
    assert "redistributionProtocol" not in AO_READS[1] and '"localAgg": true' in AO_READS[1]
    assert _routes(AO_READS, AO) == [("static", True), ("bgp", False)]


def test_a_live_network_statement_is_its_static_route_only():
    """The own path names its source (redistributionProtocol "Static"); the RIB answer's bgp entry is the covering
    10.79.0.0/16 aggregate, not the prefix's."""
    assert '"redistributionProtocol": "Static"' in NET_READS[1] and "localAgg" not in NET_READS[1]
    assert _routes(NET_READS, NET) == [("static", True)]


def test_an_advertise_only_aggregate_behind_a_static_without_the_flag_is_refused_not_read_as_a_network_route():
    """DERIVED: the live 10.80.0.0/16 answers with localAgg removed. They read exactly like a `network` statement
    of the static except for redistributionProtocol, so the missing field is refused, never read as the static
    alone (which would pass `protocol: bgp present: false` while the aggregate is advertised)."""
    bgp = _own_path(AO_READS[1], AO, lambda p: p["routeType"].pop("localAgg"))
    with pytest.raises(DriverError, match="redistributionProtocol"):
        parse_routes(AO_READS[0], bgp, AO, "default", AO_READS[2])


@pytest.mark.parametrize("edit", [pytest.param(lambda p: p["routeDetail"].pop("redistributionProtocol"), id="missing"),
                                  pytest.param(lambda p: p["routeDetail"].update(redistributionProtocol=""), id="empty"),
                                  pytest.param(lambda p: p["routeDetail"].update(redistributionProtocol=None), id="null"),
                                  pytest.param(lambda p: p.pop("routeDetail"), id="no-routeDetail")])
def test_a_network_statement_without_its_source_is_refused(edit):
    """DERIVED: the live 10.79.1.0/24 answers with the source field taken away."""
    with pytest.raises(DriverError, match="redistributionProtocol"):
        parse_routes(NET_READS[0], _own_path(NET_READS[1], NET, edit), NET, "default", NET_READS[2])


def test_a_redistributed_own_path_whose_route_is_gone_is_still_a_bgp_route():
    """DERIVED: the live 10.79.1.0/24 BGP answer with the static gone from the routing table and the RIB (a change
    between the reads, or a route withdrawn while BGP still holds the path): the path is in the BGP table and sent,
    so it is a bgp route, not selected. Without a RIB read an empty routing table proves nothing, and nothing is
    added (test_router_own_bgp_route_is_not_a_received_route_anywhere)."""
    route = json.loads(NET_READS[0])
    route["vrfs"]["default"]["routes"] = {}
    rib = json.loads(NET_READS[2])
    rib["vrfs"]["default"]["ribRoutesByProtocol"].pop("staticConfig")
    assert [(r.protocol, r.active) for r in parse_routes(json.dumps(route), NET_READS[1], NET, "default",
                                                         json.dumps(rib))] == [("bgp", False)]
    assert parse_routes(json.dumps(route), NET_READS[1], NET) == []
