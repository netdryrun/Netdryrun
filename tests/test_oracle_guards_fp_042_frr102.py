"""Guards for oracle FP-042-FRR102: they pass before and after its fix.

The fast-fix gate runs tests/oracles/FP-042-FRR102/ and needs every test there to fail on the fix's parent, so the
guards live here, in the unit suite. This file is in the oracle's `evidence:`, so the fix can't change it.
Helpers and the captured data come from the oracle's own module (tests/oracles/FP-042-FRR102/).
"""
import importlib.util
import json
from pathlib import Path

import pytest

from netdryrun.drivers.base import DriverError
from netdryrun.drivers.frr import parse_bgp_paths

_PATH = Path(__file__).resolve().parent / "oracles" / "FP-042-FRR102" / "test_oracle_fp_042_frr102.py"
_SPEC = importlib.util.spec_from_file_location("oracle_fp_042_frr102", _PATH)
o = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(o)


def test_own_prefix_bgp_route_absent_never_passes():
    """leaf01 advertises 192.168.11.0/24 (advertisedTo eth1, eth2): `bgp_route present: false` must not pass."""
    r = o.negative(o.CapturedLab(), type="bgp_route", prefix=o.OWN, present=False)
    assert not r.passed, r.detail


@pytest.mark.parametrize("kind", ["route", "bgp_route"])
def test_answer_without_paths_never_reads_absent(kind):
    """The shape the spec feared, not captured: the own prefix's answer with its paths list taken out. It names the
    prefix and who it is advertised to, so a BGP route exists: no `present: false` may pass on it."""
    data = json.loads(o.fx("frr1021_own_prefix_json.txt"))
    del data["paths"]
    lab = o.CapturedLab({f"show bgp ipv4 unicast {o.OWN} json": json.dumps(data)})
    raw = {"type": kind, "prefix": o.OWN, "present": False, **({"protocol": "bgp"} if kind == "route" else {})}
    # for `route`, zebra's captured answer (connected) stays; without the paths a learned BGP path can't be ruled out
    r = o.negative(lab, **raw)
    assert not r.passed, r.detail


@pytest.mark.parametrize("count", [1, 3])
def test_printed_path_count_is_still_checked(count):
    """Where pathCount IS printed (FRR 10.4.1 prints it: tests/fixtures/frr_bgp_paths_local.txt), a count that
    doesn't match the paths listed is still an error, never one path less or none."""
    data = json.loads(o.fx("frr1021_learned_prefix_json.txt"))
    data["pathCount"] = count
    with pytest.raises(DriverError):
        parse_bgp_paths(json.dumps(data), o.LEARNED, default_local_pref=100)
