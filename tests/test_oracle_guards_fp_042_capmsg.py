"""Guards for oracle FP-042-CAPMSG: they pass before and after its fix.

The fast-fix gate runs tests/oracles/FP-042-CAPMSG/ and needs every test there to fail on the fix's parent, so the
guards live here, in the unit suite. This file is in the oracle's `evidence:`, so the fix can't change it. Helpers come
from the oracle's own module (tests/oracles/FP-042-CAPMSG/).

The two size caps are format limits, said in the file, not gaps: each is produced here by the real code (more BGP
routes than MAX_ROUTES_PER_NODE, more link subnets than MAX_LINK_GUARDS_PER_NODE) and must stay out of baseline_gaps.
"""
import importlib.util
from pathlib import Path

from netdryrun import record as rec
from netdryrun.drivers.base import Route
from netdryrun.lab import ExecResult

_PATH = Path(__file__).resolve().parent / "oracles" / "FP-042-CAPMSG" / "test_oracle_fp_042_capmsg.py"
_SPEC = importlib.util.spec_from_file_location("oracle_fp_042_capmsg", _PATH)
o = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(o)

NEIGHBORS = (o.FX / "frr_bgp_neighbors.txt").read_text(encoding="utf-8")   # live, IP-keyed (FRR example lab)


def caps(warnings):
    return [w for w in warnings if w.startswith("INCOMPLETE BASELINE") and "only the first" in w]


def test_the_routes_cap_is_not_a_gap(monkeypatch):
    lab = o.OneNodeLab({"vtysh -c show bgp neighbors json": ExecResult([], 0, NEIGHBORS, "")})
    many = [Route(f"10.{i}.0.0/24", "bgp", True) for i in range(rec.MAX_ROUTES_PER_NODE + 1)]
    _, warnings = o.record(monkeypatch, lab, routes=many)
    assert caps(warnings), warnings
    assert not set(caps(warnings)) & set(rec.baseline_gaps(warnings)), rec.baseline_gaps(warnings)


def test_the_link_guards_cap_is_not_a_gap(monkeypatch):
    lab = o.OneNodeLab({"vtysh -c show bgp neighbors json": ExecResult([], 0, NEIGHBORS, "")},
                       links=rec.MAX_LINK_GUARDS_PER_NODE + 1)
    _, warnings = o.record(monkeypatch, lab, guards=True)
    assert caps(warnings), warnings
    assert not set(caps(warnings)) & set(rec.baseline_gaps(warnings)), rec.baseline_gaps(warnings)


def test_a_failed_read_without_those_words_is_still_a_gap(monkeypatch):
    lab = o.OneNodeLab({"vtysh -c show bgp neighbors json": ExecResult([], 1, "% Unknown command\n", "")})
    _, warnings = o.record(monkeypatch, lab)
    failed = [w for w in warnings if w.startswith("INCOMPLETE BASELINE") and "Unknown command" in w]
    assert failed and all(w in rec.baseline_gaps(warnings) for w in failed), warnings
