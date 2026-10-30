"""The live must-fail gate for NX-OS (scripts/nxos_live_mustfail.py): its check file is valid and covers every
check type both ways, and its verifier rejects every way a live run could fall short."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import nxos_live_mustfail as gate  # noqa: E402

from netdryrun.config import CHECK_TYPES, load  # noqa: E402

MUSTFAIL = ROOT / "scripts" / "labs" / "nxos-cap" / "mustfail.yml"


def test_the_check_file_loads_and_covers_every_type_both_ways():
    cfg = load(MUSTFAIL)
    assert set(gate.CHECK_TYPES) == set(CHECK_TYPES)
    for t in CHECK_TYPES:
        names = [c.name for c in cfg.checks if c.type == t]
        assert any(n.startswith("MUST FAIL") for n in names) and any(n.startswith("MUST PASS") for n in names), t
    assert all(c.name.startswith(("MUST FAIL", "MUST PASS")) for c in cfg.checks)


def _check(name, ctype="route", passed=False, unready=False, detail="d"):
    return {"name": name, "type": ctype, "passed": passed, "detail": detail,
            "history": [{"t": 1, "passed": passed, "detail": detail, **({"unready": True} if unready else {})}]}


def _report(checks, status="failed"):
    full = [_check(f"MUST {k} x", t, passed=(k == "PASS")) for t in CHECK_TYPES for k in ("FAIL", "PASS")]
    return {"status": status, "checks": full + checks}


def test_a_good_run_meets_the_gate():
    assert gate.verify(_report([])) == []


@pytest.mark.parametrize("extra,why", [
    ([_check("MUST FAIL: leak", passed=True)], "PASSED"),
    ([_check("MUST FAIL: leak", unready=True)], "without usable state"),
    ([_check("MUST PASS: control", passed=False)], "failed"),
    ([_check("some check", passed=True)], "not named"),
])
def test_every_shortfall_is_reported(extra, why):
    problems = gate.verify(_report(extra))
    assert len(problems) == 1 and why in problems[0]


def test_a_missing_type_or_a_run_without_verdict_fails_the_gate():
    report = {"status": "failed", "checks": [c for c in _report([])["checks"] if c["type"] != "ping"]}
    assert any("ping: no MUST FAIL and no MUST PASS" in p for p in gate.verify(report))
    assert any("no verdict" in p for p in gate.verify({**_report([]), "status": "inconclusive"}))
