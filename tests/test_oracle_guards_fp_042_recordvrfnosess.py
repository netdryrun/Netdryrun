"""Guards for oracle FP-042-RECORDVRFNOSESS: they pass before and after its fix.

The fast-fix gate needs every test in tests/oracles/FP-042-RECORDVRFNOSESS/ to fail on the fix's parent, so the guards
live here. This file is in the oracle's `evidence:`, so the fix can't change it. The fake PE lab and driver come from
the oracle's own module.

What must keep working: a VRF with BGP sessions keeps its 0.0.0.0/0 guard with its `vrf:`; the sessionless VRF's BGP
routes stay recorded with its `vrf:`; a VRF without a BGP instance (mgmt) gets no check and no line; no guard in any
VRF for a prefix the node learns there today; every recorded check passes on the recording state; and on the leaked
state, the VRF with sessions keeps passing its own guard (the leak is in the sessionless VRF only).
"""
import importlib.util
from pathlib import Path

import pytest

_PATH = (Path(__file__).resolve().parent / "oracles" / "FP-042-RECORDVRFNOSESS"
         / "test_oracle_fp_042_recordvrfnosess.py")
_SPEC = importlib.util.spec_from_file_location("oracle_fp_042_recordvrfnosess", _PATH)
o = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(o)

WITH_SESSIONS = {"vrf": "default", "default": "cust"}


@pytest.mark.parametrize("shape", o.SHAPES)
def test_a_vrf_with_sessions_keeps_its_guards(monkeypatch, shape):
    data, _ = o.record(monkeypatch, shape)
    vrf = WITH_SESSIONS[shape]
    assert len(o.default_guard(data["checks"], vrf)) == 1
    at = {} if vrf == "default" else {"vrf": vrf}
    assert {"type": "route", "node": "pe1", "prefix": "10.0.12.0/24", "protocol": "bgp", "present": False,
            **at} in data["checks"]


@pytest.mark.parametrize("shape", o.SHAPES)
def test_the_sessionless_vrf_keeps_its_routes(monkeypatch, shape):
    data, _ = o.record(monkeypatch, shape)
    vrf = o.SESSIONLESS[shape]
    at = {} if vrf == "default" else {"vrf": vrf}
    assert {"type": "route", "node": "pe1", "prefix": "10.10.0.0/24", "protocol": "bgp", **at} in data["checks"]
    assert not [c for c in o.in_vrf(data["checks"], vrf) if c["type"] in ("bgp_session", "bgp_prefixes")]


@pytest.mark.parametrize("shape", o.SHAPES)
def test_a_vrf_without_a_bgp_instance_gets_nothing_new(monkeypatch, shape):
    data, warnings = o.record(monkeypatch, shape)
    assert not o.in_vrf(data["checks"], "mgmt")
    assert not [w for w in warnings if "mgmt" in w], warnings


@pytest.mark.parametrize("shape", o.SHAPES)
def test_no_guard_against_what_a_vrf_learns_today(monkeypatch, shape):
    data, _ = o.record(monkeypatch, shape)
    for c in data["checks"]:
        if c.get("present") is False:
            learned = {r.prefix for r in o.PeDrv(shape)._table(c.get("vrf", "default"))}
            assert c["prefix"] not in learned, c


@pytest.mark.parametrize("shape", o.SHAPES)
def test_every_recorded_check_passes_on_the_recording_state(monkeypatch, shape):
    data, _ = o.record(monkeypatch, shape)
    for i, raw in enumerate(data["checks"]):
        r = o.judge(i, raw, o.PeDrv(shape))
        assert r.passed, (raw, r.detail)


@pytest.mark.parametrize("shape", o.SHAPES)
def test_the_vrf_with_sessions_still_passes_its_guard_after_the_leak(monkeypatch, shape):
    data, _ = o.record(monkeypatch, shape)
    after = o.PeDrv(shape, leaked=True)
    for i, raw in enumerate(o.default_guard(data["checks"], WITH_SESSIONS[shape])):
        assert o.judge(i, raw, after).passed, raw
