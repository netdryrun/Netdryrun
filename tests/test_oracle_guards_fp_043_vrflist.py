"""Guards for oracle FP-043-VRFLIST: they pass before and after its fix.

The fast-fix gate runs tests/oracles/FP-043-VRFLIST/ and needs every test there to fail on the fix's parent, so the
guards live here, in the unit suite. This file is in the oracle's `evidence:`, so the fix can't change it. Helpers come
from the oracle's own module (tests/oracles/FP-043-VRFLIST/).
"""
import importlib.util
from pathlib import Path

from netdryrun import record as rec
from netdryrun.lab import ExecResult

_PATH = Path(__file__).resolve().parent / "oracles" / "FP-043-VRFLIST" / "test_oracle_fp_043_vrflist.py"
_SPEC = importlib.util.spec_from_file_location("oracle_fp_043_vrflist", _PATH)
o = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(o)

NO_VRFS = ExecResult([], 0, "", "")   # zebra lists no VRF besides default (default isn't listed): read fine, none


def sessions(data, node):
    return sorted(c["neighbor"] for c in data["checks"]
                  if c.get("type") == "bgp_session" and c.get("node") == node and "vrf" not in c)


def test_a_node_with_no_vrfs_read_fine_stays_clean(monkeypatch):
    data, warnings = o.record(monkeypatch, o.OneNodeLab(NO_VRFS))
    assert rec.baseline_gaps(warnings) == [], warnings
    assert sessions(data, "r1"), data["checks"]


def test_the_default_vrf_is_still_recorded_when_the_vrf_list_fails(monkeypatch):
    clean, _ = o.record(monkeypatch, o.OneNodeLab(NO_VRFS))
    data, _ = o.record(monkeypatch, o.OneNodeLab(o.VRF_FAILS))
    assert sessions(data, "r1") == sessions(clean, "r1") != [], data["checks"]
