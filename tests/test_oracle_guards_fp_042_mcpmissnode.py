"""Guards for oracle FP-042-MCPMISSNODE: they pass before and after its fix.

The fast-fix gate needs every test in tests/oracles/FP-042-MCPMISSNODE/ to fail on the fix's parent, so the guards live
here. This file is in the oracle's `evidence:`, so the fix can't change it. The fake lab, driver and helpers come from
the oracle's own module.

What must keep working: a session that is down makes the YAML start with a gap line the description names (today
"# INCOMPLETE BASELINE"); a missing node still makes the YAML start with a gap line and the CLI exit 1 (a fix may
rename the marker, never drop it); a complete baseline starts with the header and no gap.
"""
import importlib.util
from pathlib import Path

from netdryrun import record as rec

_PATH = Path(__file__).resolve().parent / "oracles" / "FP-042-MCPMISSNODE" / "test_oracle_fp_042_mcpmissnode.py"
_SPEC = importlib.util.spec_from_file_location("oracle_fp_042_mcpmissnode", _PATH)
o = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(o)


def test_a_down_session_starts_with_the_signal_the_description_names(monkeypatch):
    text, warnings = o.record(monkeypatch, {"r1": o.Drv("established"), "r2": o.Drv("idle")})
    assert rec.baseline_gaps(warnings)
    marker = o.gap_marker(text)
    assert marker and marker in o.description()


def test_a_missing_node_still_starts_with_a_gap_line(monkeypatch):
    text, warnings = o.record(monkeypatch, {"r1": o.Drv(None), "r2": o.Drv("established")})
    assert rec.baseline_gaps(warnings) and o.gap_marker(text)
    assert "r1" in text.splitlines()[0]


def test_a_complete_baseline_starts_with_the_header(monkeypatch):
    text, warnings = o.record(monkeypatch, {"r1": o.Drv("established"), "r2": o.Drv("established")})
    assert not rec.baseline_gaps(warnings) and o.gap_marker(text) is None
