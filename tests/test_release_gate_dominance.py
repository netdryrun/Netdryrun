"""Red fixtures for the release gate's dominance check (the candidate against the published release), its new-read
routing to live, and the living-plants line (scripts/release_gate.py static --candidate, report).

Each check only blocks: no input here can turn a FAIL into a PASS."""
from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "fastfix_gate.py"
_spec = importlib.util.spec_from_file_location("release_gate_dominance", ROOT / "scripts" / "release_gate.py")
gate = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = gate
_spec.loader.exec_module(gate)

needs_git = pytest.mark.skipif(shutil.which("git") is None, reason="no git here (slim container)")
TAG_SHA, HEAD = "t" * 40, "h" * 40
CHANGELOG = "# Changelog\n\n## 1.1.0 (unreleased)\n\n## 1.0.0 (2026-01-01)\n\n## 0.9.0\n"


def args(tmp_path, **kw):
    return SimpleNamespace(strict=True, version="1.1.0", candidate=True, fastfix_base="v1.0.0", out=str(tmp_path),
                           published_tag=None, **kw)


def answers(**over):
    a = {"merge-base": "b" * 40, "rev-parse": HEAD, "show": "BASE", "describe": "v1.0.0"}
    a.update(over)

    def git_(*cmd):
        if cmd[0] == "merge-base" and cmd[1] == "--is-ancestor":
            return a.get("is-ancestor", "")
        if cmd[0] == "rev-parse" and cmd[1] == "--verify":
            return a.get("tag-sha", TAG_SHA)
        if cmd[0] == "show" and cmd[1] == "HEAD:CHANGELOG.md":
            return a.get("changelog", CHANGELOG)
        return a[cmd[0]]
    return git_


def fake_runner(record: dict, codes: dict | None = None):
    seen, judges = [], {}

    def runner(cmd, timeout):
        cmd = [str(c) for c in cmd]
        seen.append(cmd)
        name = "dominance" if "--dominance" in cmd else cmd[2]
        judges[name] = Path(cmd[1]).read_text(encoding="utf-8")       # the temporary copy is gone afterwards
        if "--json" in cmd:
            data = record if cmd[2] == "loosening" else {"caught": 1, "applied": 1, "total": 1, "not_applicable": []}
            Path(cmd[cmd.index("--json") + 1]).write_text(json.dumps(data), encoding="utf-8")
        return gate.Proc((codes or {}).get(name, 0), "out", 0.1)
    runner.seen, runner.judges = seen, judges
    return runner


CLEAN = {"candidate": HEAD, "flips": [], "skipped_at_base": []}


def by_id(layer):
    return {c.id: c for c in layer.checks}


@pytest.mark.parametrize("over,why", [
    ({"describe": None}, "no published v* tag is reachable"),
    ({"is-ancestor": None}, "is not an ancestor of HEAD"),
    ({"changelog": "## 1.1.0\n\n## 0.9.0\n"}, "is not the newest release in CHANGELOG.md"),
    ({"describe": "v0.9.0"}, "is not the newest release in CHANGELOG.md"),
    ({"tag-sha": None}, "is not a tag or commit here"),
])
def test_a_published_release_that_cant_be_named_blocks(tmp_path, over, why):
    layer = gate.Layer("static", args(tmp_path))
    runner = fake_runner(CLEAN)
    gate.fastfix_checks(layer, layer.args, git_=answers(**over), runner=runner)
    c = by_id(layer)["dominance"]
    assert c.status == gate.FAIL and c.severity == gate.BLOCKER and "can't name the published release" in c.summary
    assert why in c.summary
    assert not any("--dominance" in cmd for cmd in runner.seen)


def test_dominance_runs_against_the_tag_with_the_bases_judge(tmp_path):
    layer = gate.Layer("static", args(tmp_path))
    runner = fake_runner(CLEAN)
    gate.fastfix_checks(layer, layer.args, git_=answers(show='BASE add_parser("plants" "--dominance"'), runner=runner)
    checks = by_id(layer)
    assert list(checks) == ["loosening", "reproduce-first", "dominance", "dominance-skips", "plants"]
    assert all(c.status == gate.PASS for c in layer.checks), [(c.id, c.summary) for c in layer.checks]
    dom = next(cmd for cmd in runner.seen if "--dominance" in cmd)
    assert dom[dom.index("--base") + 1] == "v1.0.0" and dom[dom.index("--candidate") + 1] == HEAD
    assert runner.judges["dominance"].startswith("BASE") and runner.judges["plants"].startswith("BASE")
    plants = next(cmd for cmd in runner.seen if cmd[2] == "plants")
    assert plants[plants.index("--base") + 1] == "b" * 40
    assert "by the base's fastfix_gate.py" in checks["dominance"].summary


def test_a_base_whose_judge_predates_dominance_uses_this_checkouts_copy_and_says_so(tmp_path):
    layer = gate.Layer("static", args(tmp_path))
    runner = fake_runner(CLEAN)
    gate.fastfix_checks(layer, layer.args, git_=answers(show="BASE (0.4.2)"), runner=runner)
    assert runner.judges["dominance"] == SCRIPT.read_text(encoding="utf-8") == runner.judges["plants"]
    assert runner.judges["loosening"].startswith("BASE")
    assert "predates the command" in by_id(layer)["dominance"].summary


@pytest.mark.parametrize("code", [1, 2])
def test_a_blocked_or_broken_dominance_run_fails(tmp_path, code):
    layer = gate.Layer("static", args(tmp_path))
    gate.fastfix_checks(layer, layer.args, git_=answers(), runner=fake_runner(CLEAN, {"dominance": code}))
    assert by_id(layer)["dominance"].status == gate.FAIL


@pytest.mark.parametrize("skipped,status", [
    ([], gate.PASS),
    ([{"case": "tests.test_redteam::test_x", "target": "tests/test_redteam.py", "origin": "redteam", "reason": "no tool"}],
     gate.FAIL),
    ([{"case": "tests.oracles.FP-1.test_oracle_fp_1::t", "target": "tests/oracles/FP-1", "origin": "oracles",
       "reason": "r"}], gate.FAIL),
    ([{"case": "k", "target": "?", "origin": "unknown", "reason": "r"}], gate.FAIL),
    ([{"case": "k", "target": "t", "origin": "known_false_passes", "reason": "r", "same_at_candidate": True}],
     gate.FAIL),                                     # skipped on both sides is still not compared
    ("not a list", gate.FAIL),
])
def test_a_must_not_pass_fixture_skipped_at_the_tag_is_a_major(tmp_path, skipped, status):
    layer = gate.Layer("static", args(tmp_path))
    gate.fastfix_checks(layer, layer.args, git_=answers(),
                        runner=fake_runner({**CLEAN, "skipped_at_base": skipped}))
    c = by_id(layer)["dominance-skips"]
    assert (c.status, c.severity) == (status, gate.MAJOR), c.summary


def test_no_dominance_without_candidate(tmp_path):
    a = args(tmp_path)
    a.candidate = False
    layer = gate.Layer("static", a)
    gate.fastfix_checks(layer, a, git_=answers(), runner=fake_runner(CLEAN))
    assert [c.id for c in layer.checks] == ["loosening", "reproduce-first"]


# ---- the candidate's own judge, edited to pass everything, is not the one that runs (real repositories)

def _git(repo: Path, *a: str) -> str:
    return subprocess.run(["git", "-C", str(repo), *a], check=True, capture_output=True, text=True).stdout.strip()


@needs_git
def test_a_candidate_that_edits_its_own_judge_to_pass_is_still_blocked(tmp_path, monkeypatch):
    repo = tmp_path / "r"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    for k, v in (("user.email", "t@example.invalid"), ("user.name", "t"), ("commit.gpgsign", "false")):
        _git(repo, "config", k, v)

    def write(rel, text):
        (repo / rel).parent.mkdir(parents=True, exist_ok=True)
        (repo / rel).write_text(text, encoding="utf-8")

    cases = lambda c1: json.dumps({"cases": [{"id": "c1", "strategies": {"netdryrun": {"verdict": c1}}}]})  # noqa: E731
    write("src/toy/__init__.py", "def judge(x):\n    return x > 0\n")
    write("tests/test_redteam.py", "from toy import judge\n\n\ndef test_refuses_negative():\n    assert not judge(-1)\n")
    write("tests/redteam/README.md", "")
    write("corpus/results/results.json", cases("unsafe"))
    write("CHANGELOG.md", "## 1.0.0\n")
    write("scripts/fastfix_gate.py", SCRIPT.read_text(encoding="utf-8"))
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "1.0.0")
    _git(repo, "tag", "v1.0.0")
    write("scripts/fastfix_gate.py", "import sys\nsys.exit(0)\n")
    write("corpus/results/results.json", cases("safe"))
    write("CHANGELOG.md", "## 1.1.0\n\n## 1.0.0\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "c1 passes; the judge passes everything")

    monkeypatch.setattr(gate, "ROOT", repo)

    def git_(*a):
        p = subprocess.run(["git", "-C", str(repo), *a], capture_output=True, text=True)
        return p.stdout.strip() if p.returncode == 0 else None

    layer = gate.Layer("static", args(tmp_path / "out"))
    gate.fastfix_checks(layer, layer.args, git_=git_, runner=lambda cmd, timeout: gate.run(cmd, cwd=repo, timeout=timeout))
    checks = by_id(layer)
    assert checks["dominance"].status == gate.FAIL, checks["dominance"].output
    assert "c1: FAIL -> PASS" in checks["dominance"].output
    assert "scripts/fastfix_gate.py: FAIL -> PASS" in checks["dominance"].output
    data = json.loads((tmp_path / "out" / "gate" / "dominance.json").read_text(encoding="utf-8"))
    assert {f["case"] for f in data["flips"]} == {"c1", "scripts/fastfix_gate.py"}


# ---- report: a new device read needs live on that network OS, on this very commit

def record(name, sha, checks):
    return {"title": name, "git": {"sha": sha, "branch": "b", "dirty": False},
            "checks": [{"id": i, "title": i, "severity": "BLOCKER", "status": st} for i, st in checks]}


def dominance_json(tmp_path, flips, cand="a"):
    (tmp_path / "gate").mkdir(exist_ok=True)
    (tmp_path / "gate" / "dominance.json").write_text(json.dumps({"candidate": cand, "flips": flips}))


READ_FRR = {"source": "fixtures", "case": "tests.test_verdict_drivers::test_x[FrrDriver]", "from": "FAIL", "to": "PASS",
            "kind": "new-read", "drivers": ["frr"], "allowed_by": "fastfix/allow/x.yml"}
STATIC = record("static", "a", [("dominance", "PASS")])
LIVE_ALL = [(f"example-{ex}", "PASS") for exs in gate.LIVE_BY_NOS.values() for ex in exs]


@pytest.mark.parametrize("live,flips,expect", [
    (None, [READ_FRR], "new device read on frr"),                                            # no live at all
    (record("live", "b", LIVE_ALL), [READ_FRR], "a carried result doesn't count"),         # live on another commit
    (record("live", "a", [("example-sonic-frr", "PASS")]), [READ_FRR], "no example for it"),
    (record("live", "a", [("example-frr-bgp", "FAIL")]), [READ_FRR], "example-frr-bgp FAIL"),
    (record("live", "a", [("example-frr-bgp", "PASS")]), [{**READ_FRR, "drivers": ["*"]}], "new device read on eos"),
    (record("live", "a", [("example-frr-bgp", "PASS")]), [{**READ_FRR, "drivers": ["vyos"]}], "new device read on"),
])
def test_a_new_read_without_live_on_this_commit_blocks(tmp_path, live, flips, expect):
    dominance_json(tmp_path, flips)
    records = {"static": STATIC, **({"live": live} if live else {})}
    blockers, gaps = gate.new_read_problems(records, tmp_path)
    assert any(expect in b for b in blockers), blockers


@pytest.mark.parametrize("flips,live", [
    ([READ_FRR], [("example-frr-bgp", "PASS")]),
    ([{**READ_FRR, "drivers": ["*"]}], LIVE_ALL),
    ([{**READ_FRR, "kind": "verdict"}], []),          # not a read: no live needed here (other layers still run)
])
def test_a_new_read_with_live_on_this_commit_is_clear(tmp_path, flips, live):
    dominance_json(tmp_path, flips)
    blockers, gaps = gate.new_read_problems({"static": STATIC, "live": record("live", "a", live)}, tmp_path)
    assert blockers == [] and gaps == []


@pytest.mark.parametrize("write,expect", [
    (None, "can't be read"),
    ("{not json", "can't be read"),
    (json.dumps({"candidate": "zzz", "flips": []}), "not static's commit"),
])
def test_an_unreadable_or_foreign_dominance_record_blocks(tmp_path, write, expect):
    if write is not None:
        (tmp_path / "gate").mkdir()
        (tmp_path / "gate" / "dominance.json").write_text(write)
    blockers, _ = gate.new_read_problems({"static": STATIC}, tmp_path)
    assert blockers and expect in blockers[0], blockers


def test_static_without_dominance_is_a_gap(tmp_path):
    blockers, gaps = gate.new_read_problems({"static": record("static", "a", [("x", "PASS")])}, tmp_path)
    assert blockers == [] and gaps and "without --candidate" in gaps[0]
