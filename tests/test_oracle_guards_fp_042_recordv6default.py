"""Guards for oracle FP-042-RECORDV6DEFAULT: they pass before and after its fix.

The fast-fix gate needs every test in tests/oracles/FP-042-RECORDV6DEFAULT/ to fail on the fix's parent, so the guards
live here. This file is in the oracle's `evidence:`, so the fix can't change it. The fake PE lab and driver come from
the oracle's own module.

What must keep working: where the driver can't read IPv6 routes (all_routes(family=6) says not supported, as on
RouterOS), no VRF gets a ::/0 guard and no gap line is added beyond today's: with routes recorded, the one "could not
read IPv6 routes" line per VRF with a BGP instance; with --no-routes, none. A VRF with an eBGP session keeps its ::/0
guard; every VRF keeps its 0.0.0.0/0 guard; no guard against what a VRF learns today; every recorded check passes on
the recording state; and after the leak, the VRFs it didn't reach keep passing their ::/0 guards.
"""
import importlib.util
from pathlib import Path

import pytest

_PATH = (Path(__file__).resolve().parent / "oracles" / "FP-042-RECORDV6DEFAULT"
         / "test_oracle_fp_042_recordv6default.py")
_SPEC = importlib.util.spec_from_file_location("oracle_fp_042_recordv6default", _PATH)
o = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(o)

# shape -> the VRF with an established eBGP session
WITH_EBGP = {"svc": "default", "default": "cust", "ibgp": "default"}


def where(vrf):
    return o.PE if vrf == "default" else f"{o.PE} (vrf {vrf})"


@pytest.mark.parametrize("shape", o.SHAPES)
def test_no_v6_default_guard_where_ipv6_routes_cannot_be_read(monkeypatch, shape):
    data, _ = o.record(monkeypatch, shape, v6=False)
    assert not [c for c in data["checks"] if ":" in str(c.get("prefix", ""))], data["checks"]


@pytest.mark.parametrize("shape", o.SHAPES)
def test_no_new_gap_line_where_ipv6_routes_cannot_be_read(monkeypatch, shape):
    data, warnings = o.record(monkeypatch, shape, v6=False)
    gaps = o.rec.baseline_gaps(warnings)
    vrfs = ("default", o.PeDrv(shape).other)
    assert sorted(gaps) == sorted(
        f"INCOMPLETE BASELINE: {where(v)}: could not read IPv6 routes ({o.V6_UNSUPPORTED}), so none is recorded as a "
        "check: fix the read and record again, or add checks by hand" for v in vrfs), gaps
    assert len(o.gap_lines(data, warnings)) == len(vrfs)


@pytest.mark.parametrize("shape", o.SHAPES)
def test_no_gap_line_at_all_with_no_routes_where_ipv6_routes_cannot_be_read(monkeypatch, shape):
    data, warnings = o.record(monkeypatch, shape, v6=False, include_routes=False)
    assert not o.rec.baseline_gaps(warnings), warnings
    assert not o.gap_lines(data, warnings)
    assert not [c for c in data["checks"] if ":" in str(c.get("prefix", ""))], data["checks"]


@pytest.mark.parametrize("shape", o.SHAPES)
@pytest.mark.parametrize("v6", [True, False])
def test_every_vrf_keeps_its_ipv4_default_guard(monkeypatch, shape, v6):
    data, _ = o.record(monkeypatch, shape, v6=v6)
    for vrf in ("default", o.PeDrv(shape).other):
        at = {} if vrf == "default" else {"vrf": vrf}
        assert {"type": "route", "node": o.PE, "prefix": "0.0.0.0/0", "protocol": "bgp", "present": False,
                **at} in data["checks"], (vrf, data["checks"])


@pytest.mark.parametrize("shape", o.SHAPES)
def test_a_vrf_with_an_ebgp_session_keeps_its_v6_default_guard(monkeypatch, shape):
    data, _ = o.record(monkeypatch, shape)
    assert len(o.v6_default_guard(data["checks"], WITH_EBGP[shape])) == 1, data["checks"]


@pytest.mark.parametrize("shape", o.SHAPES)
def test_no_guard_against_what_a_vrf_learns_today(monkeypatch, shape):
    data, _ = o.record(monkeypatch, shape)
    drv = o.PeDrv(shape)
    for c in data["checks"]:
        if c.get("present") is False:
            fam = 6 if ":" in c["prefix"] else 4
            assert c["prefix"] not in {r.prefix for r in drv._table(c.get("vrf", "default"), fam)}, c


@pytest.mark.parametrize("shape", o.SHAPES)
@pytest.mark.parametrize("v6", [True, False])
def test_every_recorded_check_passes_on_the_recording_state(monkeypatch, shape, v6):
    data, _ = o.record(monkeypatch, shape, v6=v6)
    for i, raw in enumerate(data["checks"]):
        r = o.judge(i, raw, o.PeDrv(shape))
        assert r.passed, (raw, r.detail)


@pytest.mark.parametrize("shape", o.SHAPES)
def test_the_vrf_the_leak_missed_still_passes_its_v6_guard(monkeypatch, shape):
    data, _ = o.record(monkeypatch, shape)
    after = o.PeDrv(shape, leaked=True)
    for i, raw in enumerate(o.v6_default_guard(data["checks"], WITH_EBGP[shape])):
        assert o.judge(i, raw, after).passed, raw
