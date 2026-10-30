"""Static layer: a public string the project retired must not come back (0.3.2 renamed the pass verdict).

The old text stays only where history is recorded: the CHANGELOG, advisories, release records, recorded
agent runs, and lines that say they are history ("0.3.1 said ...")."""
import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("release_gate", ROOT / "scripts" / "release_gate.py")
gate = importlib.util.module_from_spec(spec)
sys.modules["release_gate"] = gate
spec.loader.exec_module(gate)

OLD = "SAFE" + " TO PROCEED"   # split, so this file never trips the check it tests


def test_a_retired_string_in_a_doc_is_reported_with_its_line():
    problems = gate.retired_string_problems([("website/docs/faq.md", f"a\nThe verdict is `{OLD}`.\n")])
    assert len(problems) == 1 and problems[0].startswith("website/docs/faq.md:2:") and OLD in problems[0]


def test_history_keeps_the_old_text():
    for path in ("CHANGELOG.md", "advisories/0.3.0-false-pass/README.md", "releases/0.3.2/review.md",
                 "examples/agent-eval/results/haiku1/T09/transcript.jsonl", "examples/agent-eval/RESULTS.md",
                 "examples/agent-demo/AGENT-RUN.md"):
        assert gate.retired_string_problems([(path, f"verdict `{OLD}`\n")]) == [], path
    for line in (f"0.3.1 said `{OLD}` for a pass", f"Netdryrun 0.3.1 returned `{OLD}` for `passed`",
                 f"verdict `{OLD}` (the pass verdict before 0.3.2, now ...)", f"`{OLD}` was renamed in 0.3.2"):
        assert gate.retired_string_problems([("README.md", line)]) == [], line


def test_case_matters_only_for_the_verdict_text():
    # the verdict is the exact upper-case string; ordinary prose about safety is not a verdict
    assert gate.retired_string_problems([("website/docs/x.md", "is it safe to proceed? no")]) == []


def test_the_repository_has_no_retired_string_outside_history():
    try:
        p = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True)
    except FileNotFoundError:   # no git at all (the gate's plain python:3.12-slim container); static runs the check
        pytest.skip("git is not installed here")
    if p.returncode != 0:   # Linux git can't read a Windows worktree; CI and the gate's Linux clone can
        pytest.skip(f"git can't list the files here: {p.stderr.strip()[:100]}")
    files = p.stdout.split()
    texts = []
    for f in files:
        try:
            texts.append((f, (ROOT / f).read_text(encoding="utf-8")))
        except (UnicodeDecodeError, OSError):
            pass
    assert gate.retired_string_problems(texts) == []
