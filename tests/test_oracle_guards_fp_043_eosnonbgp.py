"""Guards for oracle FP-043-EOSNONBGP: they pass before and after its fix.

The fast-fix gate runs tests/oracles/FP-043-EOSNONBGP/ and needs every test there to fail on the fix's parent, so the
guards live here, in the unit suite. This file is in the oracle's `evidence:`, so the fix can't change it. The lab,
the phases and the captured data come from the oracle's own module; every answer is a live capture (cEOS 4.36.3M,
lab ndr-fp043, 2026-11-21), nothing derived.

What must not change when EOS reads every candidate route:
- a protocol with no candidate for the prefix still passes `present: false` (healthy phases, live verdicts PASS);
- the selected route still fails `present: false`, and a candidate that isn't selected never makes `present: true`
  pass where it didn't before;
- EOS answers `show ip route <prefix>` and `show rib route ip <prefix>` by longest match (9.9.9.0/24 answers with the
  0.0.0.0/0 routes): a covering route is never the asked prefix.
"""
import importlib.util
import json
from pathlib import Path

import pytest

_PATH = Path(__file__).resolve().parent / "oracles" / "FP-043-EOSNONBGP" / "test_oracle_fp_043_eosnonbgp.py"
_SPEC = importlib.util.spec_from_file_location("oracle_fp_043_eosnonbgp", _PATH)
o = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(o)


@pytest.mark.parametrize("phase", sorted(o.PHASES))
def test_every_captured_file_is_there_and_eos_answered_it(phase):
    for suffix in o.PHASES[phase].values():
        text = o.fx(phase, suffix)
        assert text.strip(), (phase, suffix)
        assert "% Invalid input" not in text and '"errors"' not in text, (phase, suffix)


def test_the_live_runs_judged_as_the_oracle_says():
    """The premise, from netdryrun 0.4.2's own reports on the live lab: the two false passes, and the healthy runs."""
    def verdicts(phase):
        rep = json.loads(o.fx(phase, "report.json"))
        return {c["name"]: c["passed"] for c in rep["checks"]}
    assert verdicts("rt0056")["static-default-absent"] is True          # the false pass (RT-0056)
    assert verdicts("rt0063")["ospf-default-absent"] is True            # the false pass (RT-0063)
    assert verdicts("healthyA")["static-default-absent"] is True        # no static candidate: a true pass
    assert verdicts("healthyB")["ospf-default-absent"] is True          # no OSPF candidate: a true pass
    assert verdicts("rt0056")["bgp-default-absent"] is False
    assert verdicts("rt0063")["static-default-absent"] is False


def test_the_candidates_were_valid_routes():
    """The not-selected candidates are real routes: each is the selected one once the winner goes (rt0056sel,
    ospfsel), so a fix can't argue them away as unusable."""
    assert o.rib_says("rt0056sel") == {"staticConfig": True}
    assert o.rib_says("ospfsel") == {"ospf": True}
    assert json.loads(o.fx("rt0056sel", "ip_route.json"))["vrfs"]["default"]["routes"][o.DEFAULT]["routeType"] == "static"
    assert json.loads(o.fx("ospfsel", "ip_route.json"))["vrfs"]["default"]["routes"][o.DEFAULT]["routeType"] == \
        "ospfExternalType2"


def test_show_ip_route_hides_the_candidates():
    """Why the bug exists: neither `show ip route ... detail` nor `show ip route static` / `ospf` prints them."""
    assert " S " not in o.fx("rt0056", "ip_route_detail.txt").split("Gateway of last resort:")[1]
    assert "0.0.0.0/0" not in o.fx("rt0056", "ip_route_static.txt")
    assert "0.0.0.0/0" not in o.fx("rt0063", "ip_route_ospf.txt")
    assert " O" not in o.fx("rt0063", "ip_route_detail.txt").split("Gateway of last resort:")[1]


@pytest.mark.parametrize("phase,protocol", [("healthyA", "static"), ("healthyA", "ospf"),
                                            ("healthyB", "ospf"), ("healthyB", "bgp"),
                                            ("rt0056", "ospf"), ("rt0063", "bgp")])
def test_no_candidate_of_the_protocol_still_passes_present_false(phase, protocol):
    r, lab = o.route_check(phase, protocol=protocol, present=False)
    assert r.passed, f"{phase}: protocol {protocol} has no candidate for {o.DEFAULT}: {r.detail} (asked: {lab.asked})"


@pytest.mark.parametrize("phase,protocol", [("rt0056", "bgp"), ("healthyA", "bgp"), ("rt0063", "static"),
                                            ("healthyB", "static")])
def test_the_selected_route_still_fails_present_false(phase, protocol):
    r, _ = o.route_check(phase, protocol=protocol, present=False)
    assert not r.passed and r.samples_unready == 0, (phase, protocol, r.detail)
    assert "unexpectedly present" in r.detail, (phase, protocol, r.detail)


@pytest.mark.parametrize("phase,protocol", [("rt0056", "static"), ("rt0063", "ospf")])
def test_a_candidate_that_is_not_selected_never_passes_present_true(phase, protocol):
    """`present: true` (active by default) asks for the selected route: the losing candidate must not pass it."""
    r, lab = o.route_check(phase, protocol=protocol)
    assert not r.passed, f"{phase}: the not-selected {protocol} candidate passed present: true: {r.detail}"


@pytest.mark.parametrize("phase,protocol", [("rt0056", "bgp"), ("rt0063", "static"), ("healthyA", "bgp"),
                                            ("healthyB", "static")])
def test_the_selected_route_still_passes_present_true(phase, protocol):
    r, lab = o.route_check(phase, protocol=protocol)
    assert r.passed, f"{phase}: the selected {protocol} route: {r.detail} (asked: {lab.asked})"


def test_a_covering_default_is_not_the_asked_prefix():
    """EOS answers 9.9.9.0/24 with the 0.0.0.0/0 routes (longest match, captured): no 9.9.9.0/24 route exists."""
    assert o.DEFAULT in json.loads(o.fx("rt0056", "ip_route_9.json"))["vrfs"]["default"]["routes"]
    rib = json.loads(o.fx("rt0056", "rib_route_9.json"))["vrfs"]["default"]["ribRoutesByProtocol"]
    assert {p for v in rib.values() for p in v["ribRoutes"]} == {o.DEFAULT}
    for protocol in ("static", "bgp"):
        r, lab = o.route_check("rt0056", prefix="9.9.9.0/24", protocol=protocol)
        assert not r.passed, f"9.9.9.0/24 {protocol} present: {r.detail} (asked: {lab.asked})"
        r, lab = o.route_check("rt0056", prefix="9.9.9.0/24", protocol=protocol, present=False)
        assert r.passed, f"9.9.9.0/24 {protocol} present: false: {r.detail} (asked: {lab.asked})"
