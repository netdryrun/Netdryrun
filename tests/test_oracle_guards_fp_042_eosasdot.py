"""Guards for oracle FP-042-EOSASDOT: they pass before and after its fix.

The fast-fix gate runs tests/oracles/FP-042-EOSASDOT/ and needs every test there to fail on the fix's parent, so the
guards live here, in the unit suite. This file is in the oracle's `evidence:`, so the fix can't change it.

What a fix must keep, on the live cEOS 4.36.3M captures:
- plain AS paths parse unchanged: eos_bgp_paths.txt gives "65020" (best) and "65020 65020 65020";
- AS sets parse unchanged: eos_bgp_paths_as_set.txt gives "65005 {65004,65006}";
- the private 4-byte ASN guard still passes on the live capture, and `as_path: '65020'` still passes;
- the guard still fails on the same path printed in asplain (4200000001 65020), and an exact `as_path` of it passes.
"""
import importlib.util
from pathlib import Path

_PATH = Path(__file__).resolve().parent / "oracles" / "FP-042-EOSASDOT" / "test_oracle_fp_042_eosasdot.py"
_SPEC = importlib.util.spec_from_file_location("oracle_fp_042_eosasdot", _PATH)
o = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(o)


def test_plain_as_paths_parse_unchanged():
    paths = o.eos.parse_bgp_paths(o.fx("eos_bgp_paths.txt"), o.PREFIX)
    assert [(p.best, p.as_path) for p in paths] == [(True, "65020"), (False, "65020 65020 65020")]


def test_as_set_parses_unchanged():
    paths = o.eos.parse_bgp_paths(o.fx("eos_bgp_paths_as_set.txt"), "172.16.0.0/16")
    assert {p.as_path for p in paths} == {"65005 {65004,65006}"}


def test_guard_passes_on_the_live_capture():
    r = o.bgp_route(o.fx("eos_bgp_paths.txt"), as_path_regex=o.GUARD)
    assert r.passed, r.detail


def test_exact_as_path_passes_on_the_live_capture():
    r = o.bgp_route(o.fx("eos_bgp_paths.txt"), as_path="65020")
    assert r.passed, r.detail


def test_guard_fails_on_the_asplain_path():
    r = o.bgp_route(o.derived(f"{o.ASPLAIN} 65020"), as_path_regex=o.GUARD)
    assert not r.passed, r.detail


def test_exact_asplain_as_path_passes_on_the_asplain_path():
    r = o.bgp_route(o.derived(f"{o.ASPLAIN} 65020"), as_path=f"{o.ASPLAIN} 65020")
    assert r.passed, r.detail
