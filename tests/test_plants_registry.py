"""This repository's own oracle registry: every fixed oracle names a plant (the fix's reverse, a port of it, or
plant: none with a reason when it was fixed before plants were required), and a new oracle without a fix waits.
Running the plants themselves is the release gate's job (fastfix_gate.py plants); this is the quick registry read."""
from __future__ import annotations

import importlib.util
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("fastfix_gate_registry", ROOT / "scripts" / "fastfix_gate.py")
ffg = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = ffg
_spec.loader.exec_module(ffg)


def _full_history() -> bool:
    if shutil.which("git") is None:
        return False
    p = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "--is-shallow-repository"], capture_output=True, text=True)
    return p.returncode == 0 and p.stdout.strip() == "false"


@pytest.mark.skipif(not _full_history(), reason="needs git and the full history (not a shallow clone)")
def test_every_oracle_here_has_a_valid_plant_entry():
    head = ffg.resolve(ROOT, "HEAD")
    fixes = ffg.fixes_by_oracle(ROOT, head)
    rule = ffg.plant_rule_commit(ROOT, head)
    report, summary = ffg.Report(), {"not_applicable": [], "pending": []}
    ids = sorted(d.name for d in (ROOT / ffg.ORACLES).iterdir() if d.is_dir() and ffg.ID_RE.match(d.name))
    assert ids and rule is not None
    with tempfile.TemporaryDirectory(prefix="ndr-registry-") as tmp:
        planted = [oid for oid in ids
                   if ffg.plant_registry(ROOT, head, ROOT, oid, fixes, rule, Path(tmp), report, summary) is not None]
    assert report.problems == [], "\n".join(report.problems)
    assert planted, "no oracle has a living plant"
    assert set(summary["pending"]) <= {oid for oid in ids if not fixes.get(oid)}
