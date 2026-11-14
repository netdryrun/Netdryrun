"""Guards for oracle FP-042-NXOSHIST: they pass before and after its fix.

The fast-fix gate needs every test in tests/oracles/FP-042-NXOSHIST/ to fail on the fix's parent, so the guards live
here. This file is in the oracle's `evidence:`, so the fix can't change it. The NX-API lab, the derivation and the check
helper come from the oracle's own module.

On the unmodified captures (tests/fixtures/nxos_route_default.txt and nxos_bgp_default.txt, NX-OS 10.4(8), live) the
default from 10.0.1.2 is a valid, best BGP path that loses the URIB to n1's static Null0 default: received and not
selected. Its verdicts stay as they are: `protocol bgp active: false` passes, `protocol bgp present: false` fails (the
leak is received), `protocol static` passes. On the derived withdrawn state the static default is still there.
"""
import importlib.util
from pathlib import Path

import pytest

_PATH = Path(__file__).resolve().parent / "oracles" / "FP-042-NXOSHIST" / "test_oracle_fp_042_nxoshist.py"
_SPEC = importlib.util.spec_from_file_location("oracle_fp_042_nxoshist", _PATH)
o = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(o)


@pytest.mark.parametrize("raw, passes", [
    ({"protocol": "bgp", "active": False}, True),
    ({"protocol": "bgp", "present": False}, False),
    ({"protocol": "static"}, True),
], ids=["bgp-not-selected-passes", "bgp-present-false-fails", "static-passes"])
def test_the_captured_received_default_keeps_its_verdicts(raw, passes):
    r = o.route_check(o.captured(), **raw)
    assert r.passed is passes, r.detail


@pytest.mark.parametrize("flag", ["pathhistory", "pathdeleted"])
def test_the_static_default_still_passes_after_the_withdrawal(flag):
    r = o.route_check(o.derived(flag), protocol="static")
    assert r.passed, r.detail
