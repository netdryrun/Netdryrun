"""Guards for oracle FP-042-RECORDVRFLISTFAIL: they pass before and after its fix.

The fast-fix gate needs every test in tests/oracles/FP-042-RECORDVRFLISTFAIL/ to fail on the fix's parent, so the
guards live here. This file is in the oracle's `evidence:`, so the fix can't change it. The fake PE lab and drivers come
from the oracle's own module.

What must keep working: a driver that doesn't implement vrfs() (the base Driver's "not supported" answer, as on EOS and
SR Linux) still gets only the plain warning that the default VRF alone is recorded, and no gap line, so record exits 0
there as documented; its default VRF is recorded as before. A driver whose VRF read works records every VRF it lists,
with no gap line about VRFs. Every recorded check passes on the recording state.
"""
import importlib.util
from pathlib import Path

_PATH = (Path(__file__).resolve().parent / "oracles" / "FP-042-RECORDVRFLISTFAIL"
         / "test_oracle_fp_042_recordvrflistfail.py")
_SPEC = importlib.util.spec_from_file_location("oracle_fp_042_recordvrflistfail", _PATH)
o = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(o)


def test_a_driver_that_cannot_list_vrfs_keeps_the_plain_warning_and_no_gap_line(monkeypatch):
    data, warnings = o.record(monkeypatch, o.PeState())
    plain = [w for w in warnings if w.startswith(f"{o.PE}: ") and "only the default VRF" in w]
    assert plain, warnings
    assert "not supported" in plain[0], plain
    assert not rec_gaps(warnings), warnings
    assert not o.gap_lines(data, warnings)


def test_a_driver_that_cannot_list_vrfs_still_records_its_default_vrf(monkeypatch):
    data, _ = o.record(monkeypatch, o.PeState())
    checks = data["checks"]
    assert checks and all("vrf" not in c for c in checks), checks
    assert {"type": "route", "node": o.PE, "prefix": "0.0.0.0/0", "protocol": "bgp", "present": False} in checks
    assert {"type": "route", "node": o.PE, "prefix": "198.51.100.0/24", "protocol": "bgp"} in checks


def test_a_vrf_list_that_reads_records_every_vrf_and_no_vrf_gap(monkeypatch):
    data, warnings = o.record(monkeypatch, o.FrrPe(fail=False))
    assert {c.get("vrf", "default") for c in data["checks"]} == {"default", "cust"}
    assert {"type": "route", "node": o.PE, "prefix": "0.0.0.0/0", "protocol": "bgp", "present": False,
            "vrf": "cust"} in data["checks"]
    assert not [w for w in warnings if "only the default VRF" in w], warnings
    assert not rec_gaps(warnings), warnings


def test_every_recorded_check_passes_on_the_recording_state(monkeypatch):
    for drv in (o.PeState(), o.FrrPe(), o.FrrPe(fail=False)):
        data, _ = o.record(monkeypatch, drv)
        for i, raw in enumerate(data["checks"]):
            r = o.judge(i, raw, o.FrrPe(fail=False))
            assert r.passed, (drv.name, raw, r.detail)


def rec_gaps(warnings):
    return o.rec.baseline_gaps(warnings)
