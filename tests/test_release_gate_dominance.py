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
TAG_JUDGE = 'TAG add_parser("plants" "--dominance"'
HEAD_JUDGE = "HEAD (committed) fastfix_gate.py"


def args(tmp_path, **kw):
    a = dict(strict=True, version="1.1.0", candidate=True, fastfix_base="v1.0.0", out=str(tmp_path), published_tag=None)
    a.update(kw)
    return SimpleNamespace(**a)


def answers(**over):
    a = {"merge-base": "b" * 40, "rev-parse": HEAD, "describe": "v1.0.0", "show-base": "BASE", "show-tag": TAG_JUDGE,
         "show-head": HEAD_JUDGE, "ls-remote": f"{TAG_SHA}\trefs/tags/v1.0.0"}
    a.update(over)

    def git_(*cmd):
        if cmd[0] == "merge-base" and cmd[1] == "--is-ancestor":
            return a.get("is-ancestor", "")
        if cmd[0] == "rev-parse" and cmd[1] == "--verify":
            return a.get("tag-sha", TAG_SHA)
        if cmd[0] == "show":
            if cmd[1] == "HEAD:CHANGELOG.md":
                return a.get("changelog", CHANGELOG)
            if cmd[1].startswith("HEAD:"):
                return a["show-head"]
            return a["show-tag"] if cmd[1].startswith("v") else a["show-base"]
        return a[cmd[0]]
    return git_


def fake_runner(record: dict, codes: dict | None = None, plants: dict | None = None):
    seen, judges = [], {}

    def runner(cmd, timeout):
        cmd = [str(c) for c in cmd]
        seen.append(cmd)
        name = "dominance" if "--dominance" in cmd else cmd[2]
        judges[name] = Path(cmd[1]).read_text(encoding="utf-8")       # the temporary copy is gone afterwards
        if "--json" in cmd:
            data = record if name == "dominance" else plants or {"caught": 1, "applied": 1, "total": 1,
                                                                   "not_applicable": [], "pending_since_base": []}
            Path(cmd[cmd.index("--json") + 1]).write_text(json.dumps(data), encoding="utf-8")
        return gate.Proc((codes or {}).get(name, 0), "out", 0.1)
    runner.seen, runner.judges = seen, judges
    return runner


CLEAN = {"candidate": HEAD, "flips": [], "skipped_at_base": []}
ALL_IDS = ["loosening", "reproduce-first", "dominance", "dominance-skips", "plants", "plants-pending", "published-judge"]


def by_id(layer):
    return {c.id: c for c in layer.checks}


def static(tmp_path, git_, runner, **kw):
    layer = gate.Layer("static", args(tmp_path, **kw))
    gate.fastfix_checks(layer, layer.args, git_=git_, runner=runner)
    return by_id(layer)


# ---- naming the published release

@pytest.mark.parametrize("over,why", [
    ({"describe": None}, "no published v* tag is reachable"),
    ({"is-ancestor": None}, "is not an ancestor of HEAD"),
    ({"changelog": "## 1.1.0\n\n## 0.9.0\n"}, "is not the newest release in CHANGELOG.md"),
    ({"describe": "v0.9.0"}, "is not the newest release in CHANGELOG.md"),
    ({"tag-sha": None}, "is not a tag or commit here"),
    # what was published: origin's tag, not whatever the local tag says
    ({"ls-remote": None}, "can't confirm v1.0.0 against origin"),
    ({"ls-remote": ""}, "can't confirm v1.0.0 against origin"),
    ({"ls-remote": f"{'m' * 40}\trefs/tags/v1.0.0"}, "doesn't match what was published"),
    ({"ls-remote": f"{'o' * 40}\trefs/tags/v1.0.0\n{'m' * 40}\trefs/tags/v1.0.0^{{}}"}, "doesn't match"),
])
def test_a_published_release_that_cant_be_named_blocks_dominance_and_plants(tmp_path, over, why):
    runner = fake_runner(CLEAN)
    checks = static(tmp_path, answers(**over), runner)
    for id_ in ("dominance", "plants"):
        c = checks[id_]
        assert c.status == gate.FAIL and c.severity == gate.BLOCKER and "can't name the published release" in c.summary
        assert why in c.summary, c.summary
    assert not any("--dominance" in cmd or cmd[2] == "plants" for cmd in runner.seen)


def test_an_annotated_tag_is_compared_by_the_commit_it_peels_to(tmp_path):
    checks = static(tmp_path, answers(**{"ls-remote": f"{'o' * 40}\trefs/tags/v1.0.0\n{TAG_SHA}\trefs/tags/v1.0.0^{{}}"}),
                    fake_runner(CLEAN))
    assert checks["dominance"].status == gate.PASS, checks["dominance"].summary


# ---- who judges: the published release's copy, whatever --fastfix-base says

def test_the_published_release_judges_even_when_the_fastfix_base_is_old(tmp_path):
    """--fastfix-base v0.4.2 (a base whose copy predates the commands) used to make the candidate judge itself."""
    runner = fake_runner(CLEAN)
    checks = static(tmp_path, answers(), runner, fastfix_base="v0.4.2")
    assert list(checks) == ALL_IDS
    assert all(c.status == gate.PASS for c in checks.values()), [(c.id, c.summary) for c in checks.values()]
    assert runner.judges["loosening"].startswith("BASE")              # the change's own base judges the change
    assert runner.judges["dominance"].startswith("TAG") and runner.judges["plants"].startswith("TAG")
    dom = next(cmd for cmd in runner.seen if "--dominance" in cmd)
    assert dom[dom.index("--base") + 1] == "v1.0.0" and dom[dom.index("--candidate") + 1] == HEAD
    plants = next(cmd for cmd in runner.seen if cmd[2] == "plants")
    assert plants[plants.index("--base") + 1] == "v1.0.0"
    assert "published release's fastfix_gate.py (v1.0.0)" in checks["dominance"].summary


def test_an_empty_fastfix_range_still_runs_dominance_and_plants(tmp_path):
    runner = fake_runner(CLEAN)
    checks = static(tmp_path, answers(**{"merge-base": HEAD}), runner)
    assert checks["loosening"].status != gate.PASS and "nothing to compare" in checks["loosening"].summary
    assert checks["dominance"].status == gate.PASS and checks["plants"].status == gate.PASS


def test_a_published_release_without_the_commands_fails_unless_it_is_the_bootstrap_tag(tmp_path):
    runner = fake_runner(CLEAN)
    checks = static(tmp_path, answers(**{"show-tag": "OLD JUDGE"}), runner)
    for id_ in ("dominance", "plants"):
        assert checks[id_].status == gate.FAIL and "only the release after v0.4.2" in checks[id_].summary
    assert not any("--dominance" in cmd or cmd[2] == "plants" for cmd in runner.seen)


def test_the_bootstrap_release_uses_its_committed_copy_and_says_so_with_a_major(tmp_path, monkeypatch):
    monkeypatch.setattr(gate, "BOOTSTRAP_TAG", "v1.0.0")
    runner = fake_runner(CLEAN)
    checks = static(tmp_path, answers(**{"show-tag": "OLD JUDGE"}), runner)
    # HEAD's committed blob, never the working tree's file
    assert runner.judges["dominance"].startswith(HEAD_JUDGE) and runner.judges["plants"].startswith(HEAD_JUDGE)
    assert "BOOTSTRAP" in checks["dominance"].summary
    pj = checks["published-judge"]
    assert (pj.status, pj.severity) == (gate.FAIL, gate.MAJOR) and "BOOTSTRAP" in pj.summary


@pytest.mark.parametrize("code", [1, 2])
def test_a_blocked_or_broken_dominance_run_fails(tmp_path, code):
    checks = static(tmp_path, answers(), fake_runner(CLEAN, {"dominance": code}))
    assert checks["dominance"].status == gate.FAIL


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
    checks = static(tmp_path, answers(), fake_runner({**CLEAN, "skipped_at_base": skipped}))
    c = checks["dominance-skips"]
    assert (c.status, c.severity) == (status, gate.MAJOR), c.summary


@pytest.mark.parametrize("record,status", [
    ({"caught": 1, "applied": 1, "total": 1, "not_applicable": [], "pending_since_base": []}, gate.PASS),
    ({"caught": 1, "applied": 1, "total": 1, "not_applicable": [], "pending_since_base": ["FP-9"]}, gate.FAIL),
    ({"caught": 1, "applied": 1, "total": 1, "not_applicable": []}, gate.FAIL),       # an older record: no proof
])
def test_an_oracle_waiting_for_its_fix_since_the_release_is_a_major(tmp_path, record, status):
    checks = static(tmp_path, answers(), fake_runner(CLEAN, plants=record))
    assert (checks["plants-pending"].status, checks["plants-pending"].severity) == (status, gate.MAJOR)


def test_no_dominance_without_candidate(tmp_path):
    runner = fake_runner(CLEAN)
    layer = gate.Layer("static", args(tmp_path, candidate=False))
    gate.fastfix_checks(layer, layer.args, git_=answers(), runner=runner)
    assert [c.id for c in layer.checks] == ["loosening", "reproduce-first"]


# ---- real repositories: the candidate's own judge doesn't run, and a moved local tag is caught

def _git(repo: Path, *a: str) -> str:
    return subprocess.run(["git", "-C", str(repo), *a], check=True, capture_output=True, text=True).stdout.strip()


@pytest.fixture
def published(tmp_path, monkeypatch):
    """A repository at 1.0.0 (tagged, pushed to its origin with the real fastfix_gate.py), then a candidate that
    flips corpus case c1 and edits its own fastfix_gate.py to pass everything."""
    repo, origin = tmp_path / "r", tmp_path / "origin.git"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    for k, v in (("user.email", "t@example.invalid"), ("user.name", "t"), ("commit.gpgsign", "false"),
                 ("tag.gpgsign", "false")):
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
    _git(repo, "tag", "-a", "v1.0.0", "-m", "1.0.0")
    subprocess.run(["git", "init", "-q", "--bare", str(origin)], check=True, capture_output=True)
    _git(repo, "remote", "add", "origin", str(origin))
    _git(repo, "push", "-q", "origin", "main", "v1.0.0")
    write("scripts/fastfix_gate.py", "import sys\nsys.exit(0)\n")
    write("corpus/results/results.json", cases("safe"))
    write("CHANGELOG.md", "## 1.1.0\n\n## 1.0.0\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "c1 passes; the judge passes everything")
    monkeypatch.setattr(gate, "ROOT", repo)

    def git_(*a):
        p = subprocess.run(["git", "-C", str(repo), *a], capture_output=True, text=True)
        return p.stdout.strip() if p.returncode == 0 else None

    return repo, git_


@needs_git
def test_a_candidate_that_edits_its_own_judge_to_pass_is_still_blocked(published, tmp_path):
    repo, git_ = published
    # even with a --fastfix-base whose copy predates the commands: the published tag picks the judge
    checks = static(tmp_path / "out", git_, lambda cmd, timeout: gate.run(cmd, cwd=repo, timeout=timeout),
                    fastfix_base="HEAD")
    assert checks["dominance"].status == gate.FAIL, checks["dominance"].output
    assert "c1: FAIL -> PASS" in checks["dominance"].output
    assert "scripts/fastfix_gate.py@" in checks["dominance"].output
    assert checks["published-judge"].status == gate.PASS
    data = json.loads((tmp_path / "out" / "gate" / "dominance.json").read_text(encoding="utf-8"))
    assert {f["case"].split("@")[0] for f in data["flips"]} == {"c1", "scripts/fastfix_gate.py"}


@needs_git
def test_a_local_tag_moved_off_the_published_commit_blocks(published, tmp_path):
    repo, git_ = published
    _git(repo, "tag", "-f", "-a", "v1.0.0", "-m", "moved", "HEAD")
    checks = static(tmp_path / "out", git_, lambda cmd, timeout: gate.run(cmd, cwd=repo, timeout=timeout),
                    fastfix_base="HEAD")
    assert checks["dominance"].status == gate.FAIL and "doesn't match what was published" in checks["dominance"].summary


# ---- report: a new device read needs live on every example of that network OS, on this very commit

def record(name, sha, checks):
    return {"title": name, "git": {"sha": sha, "branch": "b", "dirty": False},
            "checks": [{"id": i, "title": i, "severity": "BLOCKER", "status": st} for i, st in checks]}


def dominance_json(tmp_path, flips, cand="a", **extra):
    (tmp_path / "gate").mkdir(exist_ok=True)
    data = {"candidate": cand, "flips": flips, "command_log_at_base": True, "changed_drivers": [],
            "new_read_entries": []}
    data.update(extra)
    (tmp_path / "gate" / "dominance.json").write_text(json.dumps(data))


READ_FRR = {"source": "fixtures", "case": "tests.test_verdict_drivers::test_x[FrrDriver]", "from": "FAIL", "to": "PASS",
            "kind": "new-read", "drivers": ["frr"], "allowed_by": "fastfix/allow/x.yml"}
READ_SRL = {**READ_FRR, "drivers": ["srlinux"]}
STATIC = record("static", "a", [("dominance", "PASS")])
LIVE_ALL = [(f"example-{ex}", "PASS") for exs in gate.LIVE_BY_NOS.values() for ex in exs]


@pytest.mark.parametrize("live,flips,extra,expect", [
    (None, [READ_FRR], {}, "new device read on frr"),                                       # no live at all
    (record("live", "b", LIVE_ALL), [READ_FRR], {}, "a carried result doesn't count"),    # live on another commit
    (record("live", "a", [("example-sonic-frr", "PASS")]), [READ_FRR], {}, "example-frr-bgp not in the live record"),
    (record("live", "a", [("example-frr-bgp", "FAIL")]), [READ_FRR], {}, "example-frr-bgp FAIL"),
    (record("live", "a", [("example-frr-bgp", "PASS")]), [{**READ_FRR, "drivers": ["*"]}], {}, "new device read on eos"),
    (record("live", "a", [("example-frr-bgp", "PASS")]), [{**READ_FRR, "drivers": ["vyos"]}], {}, "new device read on"),
    # every example of the OS, not any one: srlinux has two
    (record("live", "a", [("example-srl-frr", "PASS")]), [READ_SRL], {}, "example-srl-hidden-leak not in the live"),
    # no driver named at all: every OS
    (record("live", "a", [("example-frr-bgp", "PASS")]), [{**READ_FRR, "drivers": []}], {}, "new device read on eos"),
    # a reviewed new-read entry since the release counts even when this run saw no flip for it
    (record("live", "a", [("example-frr-bgp", "PASS")]), [],
     {"new_read_entries": [{"case": "tests.test_nxos::test_hist", "file": "fastfix/allow/n.yml", "drivers": ["nxos"]}]},
     "new device read on nxos"),
    # the published release kept no command log: every OS whose driver changed needs live too
    (record("live", "a", [("example-frr-bgp", "PASS")]), [], {"command_log_at_base": False, "changed_drivers": ["junos"]},
     "the junos driver changed"),
    (record("live", "a", [("example-frr-bgp", "PASS")]), [], {"command_log_at_base": False, "changed_drivers": ["*"]},
     "new device read on eos"),
    (record("live", "a", [("example-frr-bgp", "PASS")]), [], {"command_log_at_base": False, "changed_drivers": None},
     "can't be read"),
])
def test_a_new_read_without_live_on_this_commit_blocks(tmp_path, live, flips, extra, expect):
    dominance_json(tmp_path, flips, **extra)
    records = {"static": STATIC, **({"live": live} if live else {})}
    blockers, gaps, info = gate.new_read_problems(records, tmp_path)
    assert any(expect in b for b in blockers), blockers


@pytest.mark.parametrize("flips,live,extra", [
    ([READ_FRR], [("example-frr-bgp", "PASS")], {}),
    ([READ_SRL], [("example-srl-frr", "PASS"), ("example-srl-hidden-leak", "PASS")], {}),
    ([{**READ_FRR, "drivers": ["*"]}], LIVE_ALL, {}),
    ([{**READ_FRR, "kind": "verdict"}], [], {}),          # not a read: no live needed here (other layers still run)
    ([], [("example-junos-frr", "PASS")], {"command_log_at_base": False, "changed_drivers": ["junos"]}),
])
def test_a_new_read_with_live_on_this_commit_is_clear(tmp_path, flips, live, extra):
    dominance_json(tmp_path, flips, **extra)
    blockers, gaps, _ = gate.new_read_problems({"static": STATIC, "live": record("live", "a", live)}, tmp_path)
    assert blockers == [] and gaps == []


def test_a_release_without_the_command_log_says_so_in_the_report(tmp_path):
    dominance_json(tmp_path, [], command_log_at_base=False, changed_drivers=[])
    _, _, info = gate.new_read_problems({"static": STATIC, "live": record("live", "a", [])}, tmp_path)
    assert info and "keep no fake-lab command log" in info[0]


@pytest.mark.parametrize("write,expect", [
    (None, "can't be read"),
    ("{not json", "can't be read"),
    (json.dumps({"candidate": "zzz", "flips": []}), "not static's commit"),
])
def test_an_unreadable_or_foreign_dominance_record_blocks(tmp_path, write, expect):
    if write is not None:
        (tmp_path / "gate").mkdir()
        (tmp_path / "gate" / "dominance.json").write_text(write)
    blockers, _, _ = gate.new_read_problems({"static": STATIC}, tmp_path)
    assert blockers and expect in blockers[0], blockers


def test_static_without_dominance_is_a_gap(tmp_path):
    blockers, gaps, _ = gate.new_read_problems({"static": record("static", "a", [("x", "PASS")])}, tmp_path)
    assert blockers == [] and gaps and "without --candidate" in gaps[0]
