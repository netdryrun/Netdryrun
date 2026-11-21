"""Guards for oracle FP-043-EOSAGG: they pass before and after its fix (on main and on ndr/fix-eos-nonbgp today).

The fast-fix gate runs tests/oracles/FP-043-EOSAGG/ and needs every test there to fail on the fix's parent, so the
guards live here, in the unit suite. This file is in the oracle's `evidence:`, so the fix can't change it. The labs,
phases and captured data come from the oracle's own module; every answer is a live capture (cEOS 4.36.3M and FRR
10.4.1, lab ndr-eosagg, 2026-11-21), nothing derived.

What must not change when EOS names its own aggregate `bgp`:
- with no aggregate (healthy, healthystatic) a bgp or aggregate check sees nothing, on EOS as on FRR;
- a BGP path learned for the aggregate's exact prefix still counts as bgp (present, not selected);
- a selected aggregate still fails `present: false` (any protocol, and `aggregate` where EOS accepts it);
- an aggregate that loses to a static never passes a `present: true` bgp check, and the static stays the active route;
- FRR's verdicts (which the oracle compares against) are the ones FRR gave live, and FRR refuses `protocol: aggregate`.
"""
import importlib.util
import json
from pathlib import Path

import pytest

_PATH = Path(__file__).resolve().parent / "oracles" / "FP-043-EOSAGG" / "test_oracle_fp_043_eosagg.py"
_SPEC = importlib.util.spec_from_file_location("oracle_fp_043_eosagg", _PATH)
o = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(o)

HEALTHY = [(ph, k) for ph in ("healthy", "healthystatic") for k in o.PREFIXES]
LEARNED_EXACT = [("exact", "v4"), ("exact", "v6"), ("exactstatic", "v4"), ("exactstatic", "v6")]


@pytest.mark.parametrize("dut", sorted(o.DUTS))
@pytest.mark.parametrize("phase", o.PHASES)
def test_every_captured_file_is_there_and_the_device_answered_it(dut, phase):
    lab = o.CapturedLab(dut, phase)
    for suffix in set(lab.table.values()):
        text = o.fx(dut, phase, suffix)
        assert text.strip(), (dut, phase, suffix)
        assert "% Invalid input" not in text and '"errors"' not in text and "% Unknown" not in text, (dut, phase, suffix)


def test_every_capture_ran_with_rc_0():
    log = (o.FX / "ceos4363m_eosagg_LOG.txt").read_text(encoding="utf-8")
    caps = [line for line in log.splitlines() if " rc=" in line]
    assert len(caps) == len(o.PHASES) * (15 + 13) and all(" rc=0 " in line for line in caps)


@pytest.mark.parametrize("phase", o.PHASES)
@pytest.mark.parametrize("key", sorted(o.PREFIXES))
def test_the_device_holds_its_own_aggregate_exactly_in_the_aggregate_phases(phase, key):
    """The premise, from the device's own answers: EOS's BGP table lists the node's own aggregate (localAgg) and its
    RIB a bgp entry for the prefix in every aggregate phase, and neither in the healthy ones; FRR's BGP table lists
    its own aggregated path the same way."""
    assert o.own_aggregate_in_eos_rib(phase, key) is (phase in o.AGG_PHASES)
    vrf, prefix, _, _ = o.PREFIXES[key]
    frr = json.loads(o.fx("frr", phase, f"{key}_bgp.json"))
    own = [p for p in frr.get("paths", []) if p.get("aggregated") and p.get("local")]
    assert bool(own) is (phase in o.AGG_PHASES), (phase, key)


@pytest.mark.parametrize("phase,key", o.BEHIND_STATIC)
def test_show_ip_route_lists_only_the_static_behind_which_the_aggregate_waits(phase, key):
    """Why shape b exists: `show ip route` lists only the static; the RIB lists the aggregate as bgp, not best."""
    vrf, prefix, _, _ = o.PREFIXES[key]
    routes = json.loads(o.fx("eos", phase, f"{key}_ip_route.json"))["vrfs"][vrf]["routes"]
    assert {r["routeType"] for r in routes.values()} == {"dropRoute"}
    rib = json.loads(o.fx("eos", phase, f"{key}_rib_route.json"))["vrfs"][vrf]["ribRoutesByProtocol"]
    assert rib["bgp"]["ribRoutes"][prefix]["bestRoute"] is False
    assert rib["staticConfig"]["ribRoutes"][prefix]["bestRoute"] is True


@pytest.mark.parametrize("phase,key", HEALTHY)
def test_no_aggregate_no_bgp_route_on_eos_as_on_frr(phase, key):
    """No aggregate configured (healthystatic: a static only; healthy: nothing): bgp and aggregate are absent."""
    assert o.verdict("eos", phase, key, "bgp-absent")[0] == "PASS"
    assert o.verdict("frr", phase, key, "bgp-absent")[0] == "PASS"
    assert o.verdict("eos", phase, key, "agg-absent")[0] in ("PASS", "REFUSED")
    assert all(eos == frr for eos, frr in o.table(phase, key).values()), o.table(phase, key)


@pytest.mark.parametrize("key", sorted(o.PREFIXES))
def test_healthystatic_static_is_the_route(key):
    assert o.verdict("eos", "healthystatic", key, "static-active")[0] == "PASS"
    assert o.verdict("eos", "healthystatic", key, "any-absent")[0] == "FAIL"
    assert o.verdict("eos", "healthy", key, "any-absent")[0] == "PASS"


@pytest.mark.parametrize("phase,key", LEARNED_EXACT)
def test_a_learned_exact_path_still_counts_as_bgp(phase, key):
    """up1 sends the exact prefix: that BGP-learned path is present (not selected) whatever the aggregate is named."""
    vrf, prefix, _, _ = o.PREFIXES[key]
    bgp = json.loads(o.fx("eos", phase, f"{key}_ip_bgp.json"))["vrfs"][vrf]["bgpRouteEntries"][prefix]
    assert any(p.get("peerEntry", {}).get("peerAddr") not in (None, "", "0.0.0.0", "::") and
               not p["routeType"].get("localAgg") for p in bgp["bgpRoutePaths"])
    for dut in ("eos", "frr"):
        assert o.verdict(dut, phase, key, "bgp-absent")[0] == "FAIL", (dut, phase, key)
        assert o.verdict(dut, phase, key, "bgp-candidate")[0] == "PASS", (dut, phase, key)


@pytest.mark.parametrize("phase,key", o.SELECTED)
def test_a_selected_aggregate_still_fails_present_false(phase, key):
    assert o.verdict("eos", phase, key, "any-absent")[0] == "FAIL"
    assert o.verdict("eos", phase, key, "agg-absent")[0] in ("FAIL", "REFUSED")
    assert o.verdict("frr", phase, key, "any-absent")[0] == "FAIL"


@pytest.mark.parametrize("phase,key", o.BEHIND_STATIC)
def test_an_aggregate_behind_a_static_never_passes_present_true(phase, key):
    """The aggregate isn't selected: `protocol: bgp` (active) fails and the static is the active route, on both."""
    for dut in ("eos", "frr"):
        assert o.verdict(dut, phase, key, "bgp-active")[0] == "FAIL", (dut, phase, key)
        assert o.verdict(dut, phase, key, "static-active")[0] == "PASS", (dut, phase, key)
        assert o.verdict(dut, phase, key, "any-absent")[0] == "FAIL", (dut, phase, key)
    assert o.verdict("eos", phase, key, "agg-active")[0] in ("FAIL", "REFUSED")


def _live(path: Path) -> dict:
    out = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        parts = line.split()
        if len(parts) >= 6 and parts[5].startswith(("passed=", "REFUSED")):
            out[parts[4]] = "REFUSED" if parts[5] == "REFUSED" else ("PASS" if parts[5] == "passed=True" else "FAIL")
    return out


@pytest.mark.parametrize("phase", o.PHASES)
def test_frr_verdicts_from_the_captures_are_the_live_ones(phase):
    """The yardstick: the FRR verdicts the oracle reads from captures equal what the FRR driver judged live on frr2."""
    live = _live(o.FX / f"frr1041_eosagg_{phase}_verdicts.txt")
    assert len(live) == len(o.PREFIXES) * len(o.CHECKS)
    for name, v in live.items():
        key, check = name.split("-", 1)
        assert o.verdict("frr", phase, key, check)[0] == v, (phase, name)


@pytest.mark.parametrize("phase", o.PHASES)
def test_eos_main_verdicts_live_are_the_bug_as_captured(phase):
    """The live EOS runs on main (a5244a0) and on ndr/fix-eos-nonbgp (49dc098): shape a and shape b as the oracle
    says, the healthy phases clean."""
    main = _live(o.FX / f"ceos4363m_eosagg_{phase}_verdicts_main.txt")
    fix = _live(o.FX / f"ceos4363m_eosagg_{phase}_verdicts_fix.txt")
    assert len(main) == len(fix) == len(o.PREFIXES) * len(o.CHECKS)
    if phase in ("sel", "selms"):
        assert all(main[f"{k}-bgp-absent"] == fix[f"{k}-bgp-absent"] == "PASS" for k in o.PREFIXES)
    if phase in ("static", "exactstatic"):
        assert all(main[f"{k}-agg-absent"] == fix[f"{k}-agg-absent"] == "PASS" for k in o.PREFIXES)
    if phase == "static":
        assert all(main[f"{k}-bgp-absent"] == "PASS" and fix[f"{k}-bgp-absent"] == "FAIL" for k in o.PREFIXES)
    if phase in ("healthy", "healthystatic"):
        assert all(main[f"{k}-{c}"] == fix[f"{k}-{c}"] == "PASS" for k in o.PREFIXES for c in ("bgp-absent", "agg-absent"))


def test_frr_refuses_protocol_aggregate_before_the_run():
    """FRR names its own aggregate bgp and refuses `protocol: aggregate` (exit 2, live) rather than read it absent."""
    text = (o.FX / "frr1041_eosagg_aggrefused_check.txt").read_text(encoding="utf-8")
    assert "protocol aggregate is never reported by frr" in text
    for key in o.PREFIXES:
        assert o.verdict("frr", "sel", key, "agg-absent")[0] == "REFUSED"
