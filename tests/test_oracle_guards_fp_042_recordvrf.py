"""Guards for oracle FP-042-RECORDVRF: they pass before and after its fix.

The fast-fix gate needs every test in tests/oracles/FP-042-RECORDVRF/ to fail on the fix's parent, so the guards live
here. This file is in the oracle's `evidence:`, so the fix can't change it. The fake PE lab and driver come from the
oracle's own module.

What must keep working: the default VRF's guards (no 0.0.0.0/0 and no upstream link subnet via BGP, without `vrf:`);
VRF cust's session, prefix count and routes, each with `vrf: cust`; no guard in any VRF for a prefix the node learns
there today; and on the leaked state, the default VRF's own guard still passes (the leak is in cust only).
"""
import importlib.util
from pathlib import Path

_PATH = Path(__file__).resolve().parent / "oracles" / "FP-042-RECORDVRF" / "test_oracle_fp_042_recordvrf.py"
_SPEC = importlib.util.spec_from_file_location("oracle_fp_042_recordvrf", _PATH)
o = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(o)


def test_the_default_vrf_keeps_its_guards(monkeypatch):
    data, _ = o.record(monkeypatch)
    checks = data["checks"]
    assert len(o.default_guard(checks, "default")) == 1
    assert {"type": "route", "node": "pe1", "prefix": "10.0.12.0/24", "protocol": "bgp", "present": False} in checks


def test_the_vrf_is_recorded_with_its_vrf(monkeypatch):
    data, _ = o.record(monkeypatch)
    cust = [c for c in data["checks"] if c.get("vrf") == "cust"]
    assert {"type": "bgp_session", "node": "pe1", "neighbor": "10.1.0.2", "vrf": "cust"} in cust
    assert any(c["type"] == "bgp_prefixes" and c["neighbor"] == "10.1.0.2" for c in cust)
    for p in ("10.10.0.0/24", "10.10.1.0/24"):
        assert {"type": "route", "node": "pe1", "prefix": p, "protocol": "bgp", "vrf": "cust"} in cust


def test_no_guard_against_what_a_vrf_learns_today(monkeypatch):
    data, _ = o.record(monkeypatch)
    for c in data["checks"]:
        if c.get("present") is False:
            learned = {r.prefix for r in o.PeDrv()._table(c.get("vrf", "default"))}
            assert c["prefix"] not in learned, c


def test_every_recorded_check_passes_on_the_recording_state(monkeypatch):
    data, _ = o.record(monkeypatch)
    for i, raw in enumerate(data["checks"]):
        r = o.judge(i, raw, o.PeDrv())
        assert r.passed, (raw, r.detail)
