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


def git_quoted(name):
    """A path as git prints it without -z (core.quotePath): C-quoted when it has a quote, a backslash, a control
    character or a non-ASCII byte."""
    raw = name.encode("utf-8")
    if not any(b in b'"\\' or b < 0x20 or b >= 0x7f for b in raw):
        return name
    return '"' + "".join(chr(b) if 0x20 <= b < 0x7f and b not in b'"\\' else
                         {0x22: '\\"', 0x5c: "\\\\", 0x09: "\\t", 0x0a: "\\n"}.get(b, f"\\{b:03o}")
                         for b in raw) + '"'


def answers(**over):
    a = {"merge-base": "b" * 40, "rev-parse": HEAD, "describe": "v1.0.0", "show-base": "BASE", "show-tag": TAG_JUDGE,
         "show-head": HEAD_JUDGE, "ls-remote": f"{TAG_SHA}\trefs/tags/v1.0.0\n{'a' * 40}\trefs/tags/v0.9.0"}
    a.update(over)

    def git_(*cmd):
        if cmd[0] == "merge-base" and cmd[1] == "--is-ancestor":
            return a.get("is-ancestor", "")
        if cmd[0] == "rev-parse" and cmd[1] == "--verify":
            if cmd[-1] == "HEAD^{commit}":
                return a.get("rev-parse", HEAD)
            if cmd[-1].startswith("HEAD:"):                         # a gate file's blob at the candidate
                return a.get("blobs", {}).get(cmd[-1][len("HEAD:"):])
            assert cmd[-1].startswith("refs/tags/"), cmd           # never a short name another ref could shadow
            return a.get("tag-sha", TAG_SHA) if cmd[-1].endswith("^{commit}") else a.get("tag-object", "o" * 40)
        if cmd[0] == "show":
            if cmd[1] == "HEAD:CHANGELOG.md":
                return a.get("changelog", CHANGELOG)
            if cmd[1][len("HEAD:"):] in a.get("allow", {}):
                return a["allow"][cmd[1][len("HEAD:"):]]
            if cmd[1].startswith(f"HEAD:{gate.HISTORIC_DIR}/"):
                return a.get("historic", {}).get(cmd[1][len("HEAD:"):])
            if cmd[1].startswith("HEAD:"):
                return a["show-head"]
            return a["show-tag"] if cmd[1].startswith(TAG_SHA) else a["show-base"]
        if cmd[0] == "ls-tree":
            return "\n".join(a.get("historic", {}))
        if cmd[0] == "rev-list":
            return a.get("rev-list", "")
        if cmd[0] == "diff":
            names = a.get("diff", "")
            if isinstance(names, str):
                return names
            # as git prints them: NUL-terminated with -z, else one per line with unusual names C-quoted
            return "".join(n + "\0" for n in names) if "-z" in cmd else "".join(git_quoted(n) + "\n" for n in names)
        assert cmd[0] != "ls-remote", "origin is asked by URL (canonical_tags), never through the local git"
        return a[cmd[0]]
    git_.ls_remote = lambda: a["ls-remote"]                        # the published repository, asked by URL
    git_.patch_id = lambda sha: a.get("patch-ids", {}).get(sha)
    return git_


def fake_runner(record: dict, codes: dict | None = None, plants: dict | None = None, outs: dict | None = None):
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
        return gate.Proc((codes or {}).get(name, 0), (outs or {}).get(name, "out"), 0.1)
    runner.seen, runner.judges = seen, judges
    return runner


CLEAN = {"candidate": HEAD, "flips": [], "skipped_at_base": []}
ALL_IDS = ["loosening", "reproduce-first", "dominance", "dominance-skips", "plants", "plants-pending", "published-judge"]


def by_id(layer):
    return {c.id: c for c in layer.checks}


def static(tmp_path, git_, runner, **kw):
    layer = gate.Layer("static", args(tmp_path, **kw))
    gate.fastfix_checks(layer, layer.args, git_=git_, runner=runner, ls_remote=getattr(git_, "ls_remote", None),
                        patch_id=getattr(git_, "patch_id", None))
    return by_id(layer)


# ---- naming the published release

@pytest.mark.parametrize("over,why", [
    ({"describe": None}, "no published v* tag is reachable"),
    ({"is-ancestor": None}, "is not an ancestor of HEAD"),
    ({"changelog": "## 1.1.0\n\n## 0.9.0\n"}, "is not the newest release in CHANGELOG.md"),
    ({"describe": "v0.9.0"}, "is not the newest release in CHANGELOG.md"),
    ({"tag-sha": None}, "refs/tags/v1.0.0 is not a tag here"),
    ({"describe": "v1.0"}, "is not a release tag"),
    # what was published: origin's tag, not whatever the local tag says
    ({"ls-remote": None}, "can't confirm v1.0.0 against origin"),
    ({"ls-remote": ""}, "can't confirm v1.0.0 against origin"),
    ({"ls-remote": f"{'m' * 40}\trefs/tags/v1.0.0"}, "doesn't match what was published"),
    ({"ls-remote": f"{'o' * 40}\trefs/tags/v1.0.0\n{'m' * 40}\trefs/tags/v1.0.0^{{}}"}, "doesn't match"),
    ({"ls-remote": f"{TAG_SHA}\trefs/tags/v1.0.1"}, "can't confirm v1.0.0 against origin"),
    # a release published after this one: the candidate is judged against the newest
    ({"ls-remote": f"{TAG_SHA}\trefs/tags/v1.0.0\n{'n' * 40}\trefs/tags/v1.0.1"}, "origin has v1.0.1, newer than"),
    ({"ls-remote": f"{TAG_SHA}\trefs/tags/v1.0.0\n{'n' * 40}\trefs/tags/v1.0.10\n{'n' * 40}\trefs/tags/v1.0.9"},
     "origin has v1.0.10, newer than"),
])
def test_a_published_release_that_cant_be_named_blocks_dominance_and_plants(tmp_path, over, why):
    runner = fake_runner(CLEAN)
    checks = static(tmp_path, answers(**over), runner)
    for id_ in ("dominance", "plants"):
        c = checks[id_]
        assert c.status == gate.FAIL and c.severity == gate.BLOCKER and "can't name the published release" in c.summary
        assert why in c.summary, c.summary
    assert not any("--dominance" in cmd or cmd[2] == "plants" for cmd in runner.seen)


@pytest.mark.parametrize("listed", [
    f"{'o' * 40}\trefs/tags/v1.0.0",               # no peeled line (a bundle): the same tag object as here
    f"{TAG_SHA}\trefs/tags/v1.0.0",                # a lightweight tag: the commit itself
])
def test_a_remote_that_lists_no_peeled_ref_is_compared_by_tag_object(tmp_path, listed):
    checks = static(tmp_path, answers(**{"ls-remote": listed}), fake_runner(CLEAN))
    assert checks["dominance"].status == gate.PASS, checks["dominance"].summary


def test_the_candidates_own_tag_at_origin_is_not_a_newer_release(tmp_path):
    listed = f"{TAG_SHA}\trefs/tags/v1.0.0\n{HEAD}\trefs/tags/v1.1.0\n{'x' * 40}\trefs/tags/v2-beta"
    checks = static(tmp_path, answers(**{"ls-remote": listed}), fake_runner(CLEAN))
    assert checks["dominance"].status == gate.PASS, checks["dominance"].summary


@pytest.mark.parametrize("listed", [
    f"{TAG_SHA}\trefs/tags/v1.0.0\n{'z' * 40}\trefs/tags/v1.1.0",                               # lightweight
    f"{TAG_SHA}\trefs/tags/v1.0.0\n{'q' * 40}\trefs/tags/v1.1.0\n{'z' * 40}\trefs/tags/v1.1.0^{{}}",   # annotated
])
def test_a_version_origin_already_released_from_another_commit_blocks(tmp_path, listed):
    """1.1.0 is out at origin but not fetched here: a later commit claiming 1.1.0 is not that release."""
    runner = fake_runner(CLEAN)
    checks = static(tmp_path, answers(**{"ls-remote": listed}), runner)
    for id_ in ("dominance", "plants"):
        assert checks[id_].status == gate.FAIL and "origin already has v1.1.0 at zzzzzzzzzz" in checks[id_].summary
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
    # the verified commit, never the tag's name (which another ref could shadow)
    assert dom[dom.index("--base") + 1] == TAG_SHA and dom[dom.index("--candidate") + 1] == HEAD
    plants = next(cmd for cmd in runner.seen if cmd[2] == "plants")
    assert plants[plants.index("--base") + 1] == TAG_SHA
    assert "published release's fastfix_gate.py (v1.0.0, tttttttttt)" in checks["dominance"].summary


def test_an_empty_fastfix_range_still_runs_dominance_and_plants(tmp_path):
    runner = fake_runner(CLEAN)
    checks = static(tmp_path, answers(**{"merge-base": HEAD}), runner)
    assert checks["loosening"].status != gate.PASS and "nothing to compare" in checks["loosening"].summary
    assert checks["dominance"].status == gate.PASS and checks["plants"].status == gate.PASS


def test_a_published_release_without_the_commands_fails_unless_it_is_the_bootstrap_tag(tmp_path):
    runner = fake_runner(CLEAN)
    checks = static(tmp_path, answers(**{"show-tag": "OLD JUDGE"}), runner)
    for id_ in ("dominance", "plants"):
        assert checks[id_].status == gate.FAIL and "only release 0.4.3 against v0.4.2" in checks[id_].summary
    assert not any("--dominance" in cmd or cmd[2] == "plants" for cmd in runner.seen)


def test_the_bootstrap_release_uses_its_committed_copy_and_says_so_with_a_major(tmp_path, monkeypatch):
    monkeypatch.setattr(gate, "BOOTSTRAP_TAG", "v1.0.0")
    monkeypatch.setattr(gate, "BOOTSTRAP_NEXT", "1.1.0")
    runner = fake_runner(CLEAN)
    checks = static(tmp_path, answers(**{"show-tag": "OLD JUDGE"}), runner)
    # HEAD's committed blob, never the working tree's file
    assert runner.judges["dominance"].startswith(HEAD_JUDGE) and runner.judges["plants"].startswith(HEAD_JUDGE)
    assert "BOOTSTRAP" in checks["dominance"].summary
    pj = checks["published-judge"]
    assert (pj.status, pj.severity) == (gate.FAIL, gate.MAJOR) and "BOOTSTRAP" in pj.summary


@pytest.mark.parametrize("listed,why", [
    # 1.1.0 is out: 1.0.0 is not the published release any more, whatever CHANGELOG.md's headings say
    (f"{TAG_SHA}\trefs/tags/v1.0.0\n{'n' * 40}\trefs/tags/v1.1.0", "origin has v1.1.0, newer than v1.0.0"),
    # even when origin lists nothing newer: only the release right after the bootstrap tag may judge itself
    (f"{TAG_SHA}\trefs/tags/v1.0.0", "only release 1.1.0 against v1.0.0 may be judged by its own copy"),
])
def test_a_later_release_cant_reach_the_bootstrap(tmp_path, monkeypatch, listed, why):
    """A 1.2.0 candidate names the bootstrap tag and hides 1.1.0 from the CHANGELOG heading pattern."""
    monkeypatch.setattr(gate, "BOOTSTRAP_TAG", "v1.0.0")
    monkeypatch.setattr(gate, "BOOTSTRAP_NEXT", "1.1.0")
    runner = fake_runner(CLEAN)
    git_ = answers(**{"show-tag": "OLD JUDGE", "ls-remote": listed,
                      "changelog": "## 1.2.0\n\n## [1.1.0] (see above)\n\n## 1.0.0\n"})
    checks = static(tmp_path, git_, runner, version="1.2.0", published_tag="v1.0.0")
    for id_ in ("dominance", "plants"):
        assert checks[id_].status == gate.FAIL and why in checks[id_].summary, checks[id_].summary
    assert not any("--dominance" in cmd or cmd[2] == "plants" for cmd in runner.seen)


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
    monkeypatch.setattr(gate, "CANONICAL_ORIGIN", str(origin))      # what the published repository's URL answers
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
@pytest.mark.parametrize("decoy", ["refs/v1.0.0", "v1.0.0"])     # refs/<tag>, and $GIT_DIR/<tag>: both outrank tags
def test_a_ref_that_shadows_a_lightweight_published_tag_cant_supply_the_judge(published, tmp_path, decoy):
    """origin lists no peeled line for a lightweight tag (gh release create makes those), and git's short-name lookup
    tries refs/<name> and $GIT_DIR/<name> before refs/tags/<name>: a forged commit there, merged with -s ours so it is
    an ancestor, carried a judge that passes everything."""
    repo, git_ = published
    real = _git(repo, "rev-parse", "v1.0.0^{commit}")
    _git(repo, "tag", "-d", "v1.0.0")
    _git(repo, "push", "-q", "origin", ":refs/tags/v1.0.0")
    _git(repo, "tag", "v1.0.0", real)                                  # lightweight, as published
    _git(repo, "push", "-q", "origin", "v1.0.0")
    _git(repo, "checkout", "-q", "-b", "forge", real)
    (repo / "scripts" / "fastfix_gate.py").write_text('# FORGED add_parser("plants" "--dominance"\n', encoding="utf-8")
    _git(repo, "commit", "-q", "-am", "forged judge")
    forged = _git(repo, "rev-parse", "HEAD")
    _git(repo, "checkout", "-q", "main")
    _git(repo, "merge", "-q", "-s", "ours", "-m", "keep ours", "forge")
    if decoy.startswith("refs/"):
        _git(repo, "update-ref", decoy, forged)
    else:
        (repo / ".git" / decoy).write_text(forged + "\n", encoding="utf-8")
    assert _git(repo, "rev-parse", "v1.0.0^{commit}") == forged          # the short name now means the forgery
    runner = fake_runner({**CLEAN, "candidate": _git(repo, "rev-parse", "HEAD")})
    checks = static(tmp_path / "out", git_, runner, fastfix_base="HEAD")
    assert checks["dominance"].status == gate.PASS, checks["dominance"].summary
    assert "FORGED" not in runner.judges["dominance"] and "FORGED" not in runner.judges["plants"]
    assert runner.judges["dominance"].rstrip("\n") == SCRIPT.read_text(encoding="utf-8").rstrip("\n")
    dom = next(cmd for cmd in runner.seen if "--dominance" in cmd)
    assert dom[dom.index("--base") + 1] == real


@needs_git
@pytest.mark.parametrize("route", ["origin-folder", "insteadof"])
def test_a_local_stand_in_for_origin_cant_vouch_for_a_moved_tag(published, tmp_path, route):
    """Asked as `git ls-remote origin`, a repository with no remote named origin read a committed folder named origin/,
    and a url.*.insteadOf rule could send the published URL anywhere: either one agreed with a tag moved to a forged
    judge. The published repository is asked by its URL, outside the repository, with git's config set aside."""
    repo, git_ = published
    real = _git(repo, "rev-parse", "v1.0.0^{commit}")
    _git(repo, "checkout", "-q", "-b", "forge", real)
    (repo / "scripts" / "fastfix_gate.py").write_text('# FORGED add_parser("plants" "--dominance"\n', encoding="utf-8")
    _git(repo, "commit", "-q", "-am", "forged judge")
    forged = _git(repo, "rev-parse", "HEAD")
    _git(repo, "checkout", "-q", "main")
    _git(repo, "merge", "-q", "-s", "ours", "-m", "keep ours", "forge")
    _git(repo, "tag", "-f", "v1.0.0", forged)
    stand_in = repo / "origin"
    subprocess.run(["git", "clone", "-q", "--bare", str(repo), str(stand_in)], check=True, capture_output=True)
    if route == "origin-folder":
        _git(repo, "remote", "remove", "origin")
    else:
        _git(repo, "config", f"url.{stand_in}.insteadOf", gate.CANONICAL_ORIGIN)
    assert gate.CANONICAL_ORIGIN != str(stand_in)
    runner = fake_runner({**CLEAN, "candidate": _git(repo, "rev-parse", "HEAD")})
    checks = static(tmp_path / "out", git_, runner, fastfix_base="HEAD")
    assert checks["dominance"].status == gate.FAIL, checks["dominance"].summary
    assert "doesn't match what was published" in checks["dominance"].summary
    assert "dominance" not in runner.judges and "plants" not in runner.judges


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


# ---- the historic record: exact lines about named commits, for one release against one base, never a PASS

S1, S2, S3 = "1" * 40, "2" * 40, "3" * 40
L1 = f"BLOCKED {S1[:10]}: Fixes-Oracle: 'a review MINOR-1' is not a bug ID like RT-0036"
L2 = f"BLOCKED {S1[:10]} changes shipped code (src/, action.yml, templates/) without 'Fixes-Oracle: <ID>'"
L3 = f"BLOCKED {S2[:10]} has no Session: trailer, so the allowlist's independence can't be shown"
OUTS = {"reproduce": f"{L1}\n{L2}\nreproduce: BLOCKED (0 unexplained flip(s), 2 problem(s))",
        "loosening": f"{L3}\nloosening: BLOCKED (0 unexplained flip(s), 1 problem(s))",
        "dominance": f"{L3}\nloosening: BLOCKED (0 unexplained flip(s), 1 problem(s))"}
CODES = {"reproduce": 1, "loosening": 1, "dominance": 1}


TWIN = S1[:10] + "9" * 30


def waiver(sha, lines, **kw):
    return {"sha": sha, "patch_id": "p" + sha[:39], "lines": lines,
            "why": "landed on main before the rule it breaks could be followed; reviewed line by line",
            "reviewed_by": "historic-review", "owner_decision": "owner: accept for 0.4.3 only", **kw}


def historic(tmp_path, monkeypatch, waivers=None, outs=None, version="1.1.0", record_version="1.1.0",
             base=TAG_SHA, bases=None, extra_files=(), **over):
    monkeypatch.setattr(gate, "HISTORIC_BASES", bases if bases is not None else {"1.1.0": TAG_SHA})
    record = {"release": record_version, "base": base,
              "waivers": waivers if waivers is not None else [waiver(S1, [L1, L2]), waiver(S2, [L3])]}
    files = {f"{gate.HISTORIC_DIR}/{version}.json": json.dumps(record), **{f: "{}" for f in extra_files}}
    git_ = answers(**{"merge-base": TAG_SHA, "historic": files, "rev-list": f"{S1}\n{S2}\n{S3}\n{HEAD}",
                      "patch-ids": {s: "p" + s[:39] for s in (S1, S2, S3)}, **over})
    return static(tmp_path, git_, fake_runner(CLEAN, dict(CODES), outs=outs or OUTS), version=version)


def test_a_run_blocked_only_by_waived_lines_is_a_major_never_a_pass(tmp_path, monkeypatch):
    checks = historic(tmp_path, monkeypatch)
    for id_ in ("reproduce-first", "loosening", "dominance"):
        c = checks[id_]
        assert (c.status, c.severity) == (gate.FAIL, gate.MAJOR) and "accept in accepted.json" in c.summary, c.summary
    assert checks["historic-record"].status == gate.PASS, checks["historic-record"].summary


def test_without_a_record_the_same_lines_block(tmp_path, monkeypatch):
    checks = static(tmp_path, answers(**{"merge-base": TAG_SHA}), fake_runner(CLEAN, dict(CODES), outs=OUTS))
    for id_ in ("reproduce-first", "loosening", "dominance"):
        assert (checks[id_].status, checks[id_].severity) == (gate.FAIL, gate.BLOCKER)
    assert "historic-record" not in checks


@pytest.mark.parametrize("name,kw,blocked,why", [
    # a second bad commit: its line is not waived, so the run still blocks
    ("second-commit", {"outs": {**OUTS, "reproduce": f"{L1}\n{L2}\nBLOCKED {S3[:10]} changes shipped code x\n"}},
     ["reproduce-first"], None),
    # the judge's text changed: the line no longer matches, and the record's line is unused
    ("changed-text", {"outs": {**OUTS, "reproduce": f"{L1.replace('RT-0036', 'RT-0099')}\n{L2}\n"}},
     ["reproduce-first"], "waives a line no judge printed"),
    # a sha outside base..HEAD
    ("stale-sha", {"rev-list": f"{S2}\n{HEAD}"}, ["reproduce-first", "loosening", "dominance"],
     "is not a commit between the base and HEAD"),
    # another change under the same sha's name (a rewritten commit)
    ("patch-id", {"patch-ids": {S1: "x" * 40, S2: "p" + S2[:39]}}, ["reproduce-first", "loosening", "dominance"],
     "is not 1111111111's change"),
    # the record is for another release, or the release has no historic base, or the run's base is another commit
    ("wrong-version", {"record_version": "1.0.9"}, ["reproduce-first", "loosening", "dominance"],
     "only release(s) 1.1.0"),
    ("expired", {"bases": {"1.0.9": TAG_SHA}}, ["reproduce-first", "loosening", "dominance"], "only release(s) 1.0.9"),
    ("other-base", {"base": "b" * 40}, ["reproduce-first", "loosening", "dominance"], "must both be against"),
    ("run-base", {"merge-base": "c" * 40}, ["reproduce-first", "loosening"], "must both be against"),
    # the change's base is the record's, but the published release the dominance run is judged against is not
    ("published-elsewhere", {"merge-base": "b" * 40, "base": "b" * 40, "bases": {"1.1.0": "b" * 40}}, ["dominance"],
     "the published release is tttttttttt"),
    ("stray-file", {"extra_files": [f"{gate.HISTORIC_DIR}/1.1.1.json"]}, ["reproduce-first", "loosening", "dominance"],
     "not the historic record of this release"),
    # a flip, an oracle failure or a plant line, even about the named commit
    ("flip", {"waivers": [waiver(S1, [L1, L2, "BLOCKED loosening flip with no reviewed allowlist entry: gate :: "
                                             "scripts/x.py@abc: FAIL -> PASS"]), waiver(S2, [L3])]},
     ["reproduce-first", "loosening", "dominance"], "is not one BLOCKED line about 1111111111"),
    ("oracle", {"waivers": [waiver(S1, [L1, L2, f"BLOCKED {S1[:10]} Fixes-Oracle: FP-1: every oracle test must fail "
                                                "on the parent x"]), waiver(S2, [L3])]},
     ["reproduce-first", "loosening", "dominance"], "never waivable"),
    ("unused", {"waivers": [waiver(S1, [L1, L2]), waiver(S2, [L3]), waiver(S3, [f"BLOCKED {S3[:10]} never printed"])]},
     [], "waives a line no judge printed"),
    ("no-owner", {"waivers": [waiver(S1, [L1, L2], owner_decision=""), waiver(S2, [L3])]},
     ["reproduce-first", "loosening", "dominance"], "owner_decision must say it"),
    ("short-sha", {"waivers": [waiver(S1[:10], [L1, L2]), waiver(S2, [L3])]},
     ["reproduce-first", "loosening", "dominance"], "full 40-digit"),
    # another commit in the range shares the waived commit's 10 digits, so the judge's lines can't tell them apart
    ("twin-prefix", {"rev-list": f"{S1}\n{TWIN}\n{S2}\n{S3}\n{HEAD}"}, ["reproduce-first", "loosening", "dominance"],
     "share 1111111111"),
    # the judge printed a waived line more often than the record lists it: none of its copies is waived
    ("printed-twice", {"outs": {**OUTS, "reproduce": f"{L1}\n{L2}\n{L2}\nreproduce: BLOCKED (0 unexplained flip(s), "
                                                    "3 problem(s))"}}, ["reproduce-first"], "2 time(s), the record lists it 1"),
])
def test_a_historic_record_waives_nothing_it_shouldnt(tmp_path, monkeypatch, name, kw, blocked, why):
    over = {k: kw.pop(k) for k in ("rev-list", "patch-ids", "merge-base") if k in kw}
    checks = historic(tmp_path, monkeypatch, **kw, **over)
    for id_ in blocked:
        c = checks[id_]
        assert (c.status, c.severity) == (gate.FAIL, gate.BLOCKER), (id_, c.severity, c.summary)
    if why:
        h = checks["historic-record"]
        assert (h.status, h.severity) == (gate.FAIL, gate.BLOCKER) and why in h.output, h.output


def test_a_broken_judge_run_is_never_waived(tmp_path, monkeypatch):
    monkeypatch.setattr(gate, "HISTORIC_BASES", {"1.1.0": TAG_SHA})
    record = {"release": "1.1.0", "base": TAG_SHA, "waivers": [waiver(S1, [L1, L2]), waiver(S2, [L3])]}
    git_ = answers(**{"merge-base": TAG_SHA, "historic": {f"{gate.HISTORIC_DIR}/1.1.0.json": json.dumps(record)},
                      "rev-list": f"{S1}\n{S2}", "patch-ids": {S1: "p" + S1[:39], S2: "p" + S2[:39]}})
    checks = static(tmp_path, git_, fake_runner(CLEAN, {**CODES, "reproduce": 2}, outs=OUTS))
    assert (checks["reproduce-first"].status, checks["reproduce-first"].severity) == (gate.FAIL, gate.BLOCKER)


# ---- the gate-naming bridge: the published v0.4.2 judge names a gate flip by bare path, the next judge by
# <path>@<blob>; for one release against one base, the frozen judge's two gate-naming lines are dropped only for a
# gate file whose exact entry the dominance run allowed, each one named, and the run is a MAJOR, never a PASS

ALLOW = "fastfix/allow/0.4.3-gate.yml"
B1, B2 = "a" * 12, "b" * 12
GATES = {"scripts/fastfix_gate.py": B1, "scripts/release_gate.py": B2}


def bare(path):
    return f"BLOCKED loosening flip with no reviewed allowlist entry: gate :: {path}: FAIL -> PASS"


def stale(path, blob, file=ALLOW):
    return (f"BLOCKED {file}: allows gate :: {path}@{blob} FAIL -> PASS, which is not a flip in this change (stale or "
            "pre-loaded entries block)")


def gate_entry(path, blob):
    return {"source": "gate", "case": f"{path}@{blob}", "from": "FAIL", "to": "PASS", "evidence": ["r.txt"],
            "why": "x" * 40, "reviewed_by": "r"}


BRIDGE_LINES = [bare(p) for p in GATES] + [stale(p, b) for p, b in GATES.items()]   # flips first, as finish()


def judge_out(lines, name="loosening"):
    """What the frozen judge's finish() prints: flip lines, then problem lines, then a summary that counts them."""
    flips = [ln for ln in lines if ln.startswith(gate.JUDGE_FLIP)]
    rest = [ln for ln in lines if ln not in flips]
    return "\n".join(flips + rest + [f"{name}: BLOCKED ({len(flips)} unexplained flip(s), {len(rest)} problem(s))"])


def dominance_record(allowed_by=ALLOW, candidate=HEAD, flips=None):
    return {"candidate": candidate, "skipped_at_base": [], "flips": flips if flips is not None else [
        {"source": "gate", "case": f"{p}@{b}", "from": "FAIL", "to": "PASS", "kind": "gate", "allowed_by": allowed_by}
        for p, b in GATES.items()]}


def bridge_git(entries=None, blobs=None, changed=ALLOW, allow_file=ALLOW, **over):
    allow = {"flips": entries if entries is not None else [gate_entry(p, b) for p, b in GATES.items()]}
    return answers(**{"merge-base": TAG_SHA, "diff": changed, "allow": {allow_file: json.dumps(allow)},
                      "blobs": {p: b + "0" * 28 for p, b in (blobs or GATES).items()}, **over})


def bridged(tmp_path, monkeypatch, lines=None, flips=None, entries=None, blobs=None, changed=ALLOW,
            bridge_bases=None, version="1.1.0", dominance_code=0, record_candidate=HEAD, loosening_code=1,
            out=None, allowed_by=ALLOW, allow_file=ALLOW, **over):
    monkeypatch.setattr(gate, "NAMING_BRIDGE", bridge_bases if bridge_bases is not None else {"1.1.0": TAG_SHA})
    out = out if out is not None else judge_out(BRIDGE_LINES if lines is None else lines)
    record = dominance_record(allowed_by=allowed_by, candidate=record_candidate, flips=flips)
    runner = fake_runner(record, {"loosening": loosening_code, "dominance": dominance_code}, outs={"loosening": out})
    return static(tmp_path, bridge_git(entries, blobs, changed, allow_file, **over), runner, version=version)


def test_the_frozen_judges_gate_naming_lines_are_dropped_by_name_and_the_run_is_a_major(tmp_path, monkeypatch):
    c = bridged(tmp_path, monkeypatch)["loosening"]
    assert (c.status, c.severity) == (gate.FAIL, gate.MAJOR), (c.severity, c.summary)
    assert "gate-naming bridge" in c.summary and "accept in accepted.json" in c.summary, c.summary
    for ln in BRIDGE_LINES:
        assert f"dropped by the gate-naming bridge: {ln}" in c.output


def test_the_gate_lists_of_both_gates_agree():
    spec = importlib.util.spec_from_file_location("ff_for_bridge", SCRIPT)
    ff = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = ff
    spec.loader.exec_module(ff)
    assert gate.GATE_FILES == ff.GATE_FILES and gate.ALLOW_DIR == ff.ALLOW_DIR


VERDICT = "BLOCKED loosening flip with no reviewed allowlist entry: fixtures :: tests.t::test_x: FAIL -> PASS"
SURF = "scripts/surfaces_agree.py"
NO_SESSION = f"BLOCKED {S2[:10]} has no Session: trailer, so the allowlist's independence can't be shown"
STALE_VERDICT = (f"BLOCKED {ALLOW}: allows fixtures :: tests.t::test_x FAIL -> PASS, which is not a flip in this "
                 "change (stale or pre-loaded entries block)")


@pytest.mark.parametrize("name,kw", [
    # a bare gate flip with no <path>@<blob> entry that dominance allowed (surfaces_agree, not in the allowlist)
    ("bare-no-entry", {"lines": BRIDGE_LINES + [bare(SURF)]}),
    # an entry whose blob is not the candidate's file
    ("blob-differs", {"blobs": {"scripts/fastfix_gate.py": "c" * 12, "scripts/release_gate.py": B2}}),
    # the stale line names a blob dominance didn't allow
    ("stale-other-blob", {"lines": BRIDGE_LINES + [stale("scripts/fastfix_gate.py", "d" * 12)]}),
    # dominance didn't allow the flip (still unexplained there), or saw it under another name
    ("not-allowed", {"flips": dominance_record(allowed_by=None)["flips"]}),
    ("bare-at-dominance", {"flips": [{"source": "gate", "case": p, "from": "FAIL", "to": "PASS", "allowed_by": ALLOW}
                                     for p in GATES]}),
    # the allowlist at HEAD lacks the exact entry, wasn't changed in this change, or the stale line names another file
    ("entry-missing", {"entries": [gate_entry("scripts/release_gate.py", B2)]}),
    ("allowlist-unchanged", {"changed": ""}),
    ("other-file", {"lines": BRIDGE_LINES + [stale("scripts/fastfix_gate.py", B1, "fastfix/allow/other.yml")]}),
    # a non-gate (verdict) flip, and any other frozen-judge line
    ("verdict-flip", {"lines": BRIDGE_LINES + [VERDICT]}),
    ("other-line", {"lines": BRIDGE_LINES + [NO_SESSION]}),
    ("stale-verdict-entry", {"lines": BRIDGE_LINES + [STALE_VERDICT]}),
    # another base, another published release, another version
    ("other-base", {"merge-base": "c" * 40}),
    ("published-elsewhere", {"merge-base": "b" * 40, "bridge_bases": {"1.1.0": "b" * 40}}),
    ("other-version", {"bridge_bases": {"1.0.9": TAG_SHA}}),
    # a dominance run that broke, or a record from another candidate
    ("dominance-broken", {"dominance_code": 2}),
    ("foreign-record", {"record_candidate": "f" * 40}),
    # the frozen judge itself broke: nothing it printed is dropped
    ("loosening-broken", {"loosening_code": 2}),
    # a file name with a space must not split into a root file the old judge never reads (git diff -z)
    ("split-name", {"changed": "fastfix/allow/x y.yml", "allowed_by": "y.yml", "allow_file": "y.yml",
                    "lines": [bare(p) for p in GATES]}),
    ("root-file", {"changed": f"{ALLOW}\0y.yml", "allowed_by": "y.yml", "allow_file": "y.yml"}),
    ("split-into-allow-path", {"changed": "fastfix/allow/a fastfix/allow/b.yml", "allowed_by": "fastfix/allow/b.yml",
                               "allow_file": "fastfix/allow/b.yml",
                               "lines": [bare(p) for p in GATES] + [stale(p, b, "fastfix/allow/b.yml")
                                                                    for p, b in GATES.items()]}),
    ("not-yaml", {"changed": "fastfix/allow/g.json", "allowed_by": "fastfix/allow/g.json",
                  "allow_file": "fastfix/allow/g.json"}),
    # a bare flip is dropped only beside the stale line that shows the old judge read that entry
    ("bare-without-stale", {"lines": [bare(p) for p in GATES]}),
    ("bare-with-other-stale", {"lines": [bare(p) for p in GATES] + [stale("scripts/release_gate.py", B2)]}),
    # the entry must be exactly the gate flip: not another source or another from/to
    ("entry-other-source", {"entries": [{**gate_entry(p, b), "source": "fixtures"} for p, b in GATES.items()]}),
    ("entry-other-from", {"entries": [{**gate_entry(p, b), "from": "UNKNOWN"} for p, b in GATES.items()]}),
    # the dominance flip must be a gate flip, allowed by a file name
    ("dominance-flip-not-gate", {"flips": [{**f, "source": "fixtures"} for f in dominance_record()["flips"]]}),
    ("allowed-by-not-a-string", {"allowed_by": [ALLOW]}),
    # the judge's output must be its own shape: no text past a newline, and counts that add up
    ("continuation-line", {"out": judge_out(BRIDGE_LINES[:-1] + [BRIDGE_LINES[-1] + "\nanything after a newline"])}),
    ("indented-continuation", {"out": judge_out(BRIDGE_LINES[:-1] + [BRIDGE_LINES[-1] + "\n  anything"])}),
    ("count-mismatch", {"out": "\n".join(BRIDGE_LINES + ["loosening: BLOCKED (2 unexplained flip(s), 3 problem(s))"])}),
    ("no-summary", {"out": "\n".join(BRIDGE_LINES)}),
    ("fixtures-note-after-problem", {"out": "\n".join(BRIDGE_LINES + [gate.JUDGE_FIXTURES_NOTE + " hidden text",
                                                                       "loosening: BLOCKED (2 unexplained flip(s), "
                                                                       "2 problem(s))"])}),
    ("flip-after-problem", {"out": "\n".join([bare("scripts/fastfix_gate.py")] + BRIDGE_LINES[2:] + BRIDGE_LINES[1:2]
                                             + ["loosening: BLOCKED (2 unexplained flip(s), 2 problem(s))"])}),
])
def test_the_gate_naming_bridge_drops_nothing_it_shouldnt(tmp_path, monkeypatch, name, kw):
    c = bridged(tmp_path, monkeypatch, **kw)["loosening"]
    assert (c.status, c.severity) == (gate.FAIL, gate.BLOCKER), (name, c.severity, c.summary)


def test_the_bridge_never_touches_reproduce_or_dominance(tmp_path, monkeypatch):
    monkeypatch.setattr(gate, "NAMING_BRIDGE", {"1.1.0": TAG_SHA})
    outs = {"reproduce": judge_out(BRIDGE_LINES, "reproduce"), "dominance": judge_out(BRIDGE_LINES)}
    checks = static(tmp_path, bridge_git(), fake_runner(dominance_record(), {"reproduce": 1, "dominance": 1},
                                                        outs=outs))
    for id_ in ("reproduce-first", "dominance"):
        assert (checks[id_].status, checks[id_].severity) == (gate.FAIL, gate.BLOCKER), id_


def test_the_bridge_and_a_historic_record_together_are_still_a_major(tmp_path, monkeypatch):
    monkeypatch.setattr(gate, "HISTORIC_BASES", {"1.1.0": TAG_SHA})
    record = {"release": "1.1.0", "base": TAG_SHA, "waivers": [waiver(S2, [NO_SESSION])]}
    c = bridged(tmp_path, monkeypatch, lines=BRIDGE_LINES + [NO_SESSION], **{
        "historic": {f"{gate.HISTORIC_DIR}/1.1.0.json": json.dumps(record)}, "rev-list": f"{S2}\n{HEAD}",
        "patch-ids": {S2: "p" + S2[:39]}})
    lo = c["loosening"]
    assert (lo.status, lo.severity) == (gate.FAIL, gate.MAJOR) and "historic record" in lo.summary \
        and "gate-naming bridge" in lo.summary, lo.summary
    assert f"waived: {NO_SESSION}" in lo.output and c["historic-record"].status == gate.PASS


# ---- fingerprints: an acceptance names the content it accepted

def test_a_waived_or_bridged_major_carries_a_fingerprint_of_its_lines(tmp_path, monkeypatch):
    first = historic(tmp_path / "a", monkeypatch)["reproduce-first"]
    again = historic(tmp_path / "b", monkeypatch)["reproduce-first"]
    other_l1 = L1.replace("MINOR-1", "MINOR-2")
    other = historic(tmp_path / "c", monkeypatch, waivers=[waiver(S1, [other_l1, L2]), waiver(S2, [L3])],
                     outs={**OUTS, "reproduce": f"{other_l1}\n{L2}\nreproduce: BLOCKED (0 unexplained flip(s), "
                                                "2 problem(s))"})["reproduce-first"]
    assert first.severity == other.severity == gate.MAJOR, (first.summary, other.summary)
    assert first.fingerprint and f"[fingerprint {first.fingerprint}]" in first.summary
    assert first.fingerprint == again.fingerprint != other.fingerprint
    c = bridged(tmp_path / "d", monkeypatch)["loosening"]
    assert c.fingerprint and f"[fingerprint {c.fingerprint}]" in c.summary


def test_the_other_fast_fix_majors_carry_a_fingerprint_of_their_content(tmp_path):
    skipped = {**CLEAN, "skipped_at_base": [{"case": "t::a", "origin": "oracles", "reason": "r"}]}
    a = static(tmp_path / "a", answers(), fake_runner(skipped))["dominance-skips"]
    skipped2 = {**CLEAN, "skipped_at_base": [{"case": "t::b", "origin": "oracles", "reason": "r"}]}
    b = static(tmp_path / "b", answers(), fake_runner(skipped2))["dominance-skips"]
    assert a.severity == gate.MAJOR and a.fingerprint and b.fingerprint and a.fingerprint != b.fingerprint
    assert static(tmp_path / "c", answers(), fake_runner(CLEAN))["dominance-skips"].fingerprint == ""   # a PASS


@pytest.mark.parametrize("changed,by", [
    (["fastfix/allow/x y.yml", ALLOW], ALLOW),              # another allowlist with a space, changed beside it
    (["fastfix/allow/x y.yml"], "fastfix/allow/x y.yml"),   # the name with a space is the allowlist
    (["fastfix/allow/x\u00e9.yml"], "fastfix/allow/x\u00e9.yml"),   # a name git quotes without -z
])
def test_the_bridge_reads_the_changed_allowlists_nul_separated(changed, by):
    git_ = bridge_git(changed=changed, allow_file=by)
    assert set(gate.bridge_from_dominance(git_, TAG_SHA, dominance_record(allowed_by=by)["flips"]).allowed) \
        == set(GATES)


def test_the_fake_git_prints_changed_names_as_git_does():
    git_ = answers(diff=["fastfix/allow/x y.yml", "fastfix/allow/x\u00e9.yml"])
    assert git_("diff", "--name-only", "-z") == "fastfix/allow/x y.yml\0fastfix/allow/x\u00e9.yml\0"
    assert git_("diff", "--name-only") == 'fastfix/allow/x y.yml\n"fastfix/allow/x\\303\\251.yml"\n'


def test_the_judge_shape_takes_the_fixtures_note_only_after_flip_lines():
    summary = "loosening: BLOCKED (1 unexplained flip(s), 1 problem(s))"
    note = gate.JUDGE_FIXTURES_NOTE + " rest of the note"
    assert gate.judge_shape_problem("\n".join([bare(SURF), note, NO_SESSION, summary])) is None
    assert gate.judge_shape_problem("\n".join([bare(SURF), NO_SESSION, note, summary]))     # after a problem


def _unit_layer():
    from types import SimpleNamespace
    return gate.Layer("unit", SimpleNamespace(strict=False, version="1.1.0"))


def _coverage(tmp_path, covered):
    cov = tmp_path / "coverage.json"
    files = {f"src/{path}" + ("x.py" if path.endswith("/") else ""): {"summary": {
        "num_statements": 10, "covered_lines": covered.get(name, 10), "num_branches": 0, "covered_branches": 0}}
        for name, path in gate.VERDICT_MODULES.items()}
    cov.write_text(json.dumps({"files": files}))
    layer = _unit_layer()
    gate.coverage_checks(layer, cov)
    return layer.checks[-1]


def test_the_coverage_major_carries_a_fingerprint_of_what_is_below(tmp_path):
    layer = _unit_layer()
    gate.coverage_checks(layer, None)
    assert layer.checks[-1].severity == gate.MAJOR and layer.checks[-1].fingerprint
    name = next(iter(gate.VERDICT_MODULES))
    a, b = _coverage(tmp_path, {name: 1}), _coverage(tmp_path, {name: 2})
    assert a.status == gate.FAIL and a.fingerprint and b.fingerprint and a.fingerprint != b.fingerprint
    assert _coverage(tmp_path, {}).fingerprint == ""            # a PASS


def test_the_corpus_freshness_major_carries_a_fingerprint_of_what_is_stale():
    from types import SimpleNamespace
    fps = []
    for stale in ({"v3": "ran on verdict code aaa"}, {"v3": "ran on verdict code bbb"}, {}):
        layer = gate.Layer("static", SimpleNamespace(strict=False, version="1.1.0"))
        gate.corpus_fresh_check(layer, stale)
        fps.append(layer.checks[-1].fingerprint)
    assert fps[0] and fps[1] and fps[0] != fps[1] and fps[2] == ""


@pytest.mark.parametrize("changed,by", [
    ("fastfix/allow/x y.yml", "y.yml"),                     # split on the space: a root file
    (f"{ALLOW}\0y.yml", "y.yml"),                           # a root file, even listed as changed
    ("fastfix/allow/a fastfix/allow/b.yml", "fastfix/allow/b.yml"),   # split on the space: an unchanged allowlist
    ("fastfix/allow/g.json", "fastfix/allow/g.json"),       # not YAML: no judge reads it
])
def test_the_bridge_reads_only_changed_yaml_allowlists_by_their_whole_name(changed, by):
    git_ = bridge_git(changed=changed, allow_file=by)
    assert gate.bridge_from_dominance(git_, TAG_SHA, dominance_record(allowed_by=by)["flips"]).allowed == {}
    ok = bridge_git()
    assert set(gate.bridge_from_dominance(ok, TAG_SHA, dominance_record()["flips"]).allowed) == set(GATES)


# ---- the kind bridge: the published v0.4.2 judge rejects every allowlist entry that says kind: new-read (its keys
# must be exactly the seven), so the flip such an entry allows stays unexplained to it. For one release against one
# base, its "keys must be exactly" line and that entry's flip line are dropped only for an entry whose keys are exactly
# the seven plus kind, which the dominance run (HEAD's judge, logging at the base) allowed as a new read from the same
# file, with no problem naming it; the run is a MAJOR, never a PASS

KALLOW = "fastfix/allow/0.4.3-new-read.yml"
KC1 = "tests.test_redteam::test_eos_route_is_refused[EosDriver]"     # a verdict flip at the old judge too
KC2 = "tests.test_redteam::test_srl_reads_neighbors"                # only the command log shows it (no old flip)
SEVEN = "['case', 'evidence', 'from', 'reviewed_by', 'source', 'to', 'why']"     # v0.4.2's sorted(ALLOW_KEYS)


def keys_line(n, file=KALLOW):
    return f"BLOCKED {file} flip #{n}: keys must be exactly {SEVEN}"


def vflip(case, before="FAIL", after="PASS"):
    return f"BLOCKED loosening flip with no reviewed allowlist entry: fixtures :: {case}: {before} -> {after}"


def kind_entry(case, **over):
    e = {"source": "fixtures", "case": case, "from": "FAIL", "to": "PASS", "evidence": ["tests/test_redteam.py"],
         "why": "x" * 40, "reviewed_by": "reviewer-2: the updated test asserts the same refusal", "kind": "new-read"}
    e.update(over)
    return {k: v for k, v in e.items() if v is not None}


def kind_record(flips=None, problems=None, candidate=HEAD, allowed_by=KALLOW):
    return {"candidate": candidate, "skipped_at_base": [], "problems": [] if problems is None else problems,
            "flips": flips if flips is not None else [
                {"source": "fixtures", "case": c, "from": "FAIL", "to": "PASS", "kind": "new-read", "drivers": ["*"],
                 "allowed_by": allowed_by} for c in (KC1, KC2)]}


KIND_LINES = [vflip(KC1), keys_line(1), keys_line(2)]


def kind_git(entries=None, changed=(KALLOW,), extra_allow=None, **over):
    allow = {KALLOW: json.dumps({"flips": entries if entries is not None else [kind_entry(KC1), kind_entry(KC2)]}),
             **(extra_allow or {})}
    return answers(**{"merge-base": TAG_SHA, "diff": list(changed), "allow": allow, **over})


def kinded(tmp_path, monkeypatch, lines=None, entries=None, record=None, version="1.1.0", kind_bases=None,
           changed=(KALLOW,), dominance_code=0, loosening_code=1, out=None, extra_allow=None, **over):
    monkeypatch.setattr(gate, "KIND_BRIDGE", kind_bases if kind_bases is not None else {"1.1.0": TAG_SHA})
    monkeypatch.setattr(gate, "NAMING_BRIDGE", {})
    out = out if out is not None else judge_out(KIND_LINES if lines is None else lines)
    runner = fake_runner(record if record is not None else kind_record(),
                         {"loosening": loosening_code, "dominance": dominance_code}, outs={"loosening": out})
    return static(tmp_path, kind_git(entries, changed, extra_allow, **over), runner, version=version)


def test_the_frozen_judges_kind_lines_are_dropped_by_name_and_the_run_is_a_major(tmp_path, monkeypatch):
    c = kinded(tmp_path, monkeypatch)["loosening"]
    assert (c.status, c.severity) == (gate.FAIL, gate.MAJOR), (c.severity, c.summary)
    assert "3 line(s) the kind bridge drops" in c.summary and "accept in accepted.json" in c.summary, c.summary
    for ln in KIND_LINES:
        assert f"dropped by the kind bridge: {ln}" in c.output
    assert c.fingerprint and f"[fingerprint {c.fingerprint}]" in c.summary
    other = kinded(tmp_path / "b", monkeypatch, lines=[keys_line(1), keys_line(2)])["loosening"]
    assert other.severity == gate.MAJOR and other.fingerprint != c.fingerprint      # keyed on the exact lines


def _with(case, **change):
    return [{**f, **change} if f["case"] == case else f for f in kind_record()["flips"]]


@pytest.mark.parametrize("name,kw", [
    # an entry with a second extra key, or another kind, or not a fixture entry: its keys line stays
    ("second-extra-key", {"entries": [kind_entry(KC1, note="a second extra key"), kind_entry(KC2)]}),
    ("no-kind", {"entries": [kind_entry(KC1, kind=None, note="x"), kind_entry(KC2)]}),
    ("kind-verdict", {"entries": [kind_entry(KC1, kind="verdict"), kind_entry(KC2)]}),
    ("gate-source", {"entries": [kind_entry(KC1, source="gate"), kind_entry(KC2)]}),
    # dominance didn't match that entry: not allowed, allowed as something else, by another file, under another from
    ("not-allowed", {"record": kind_record(flips=_with(KC1, allowed_by=None))}),
    ("allowed-as-verdict", {"record": kind_record(flips=_with(KC1, kind="verdict"))}),
    ("allowed-by-another-file", {"record": kind_record(allowed_by="fastfix/allow/other.yml")}),
    ("other-from-at-dominance", {"record": kind_record(flips=_with(KC1, **{"from": "UNKNOWN"}))}),
    ("missing-at-dominance", {"record": kind_record(flips=[f for f in kind_record()["flips"] if f["case"] != KC1])}),
    # dominance reported a problem naming the entry or its case; or its record has no problem list
    ("problem-names-entry", {"record": kind_record(problems=[f"{KALLOW} flip #1: evidence must be ..."])}),
    ("problem-names-case", {"record": kind_record(problems=[f"fixtures :: {KC1}: judged at the base, not at ..."])}),
    ("no-problem-list", {"record": {k: v for k, v in kind_record().items() if k != "problems"}}),
    # two entries name the same flip: neither can be shown to be the one dominance matched
    ("duplicate-entry", {"entries": [kind_entry(KC1), kind_entry(KC2), kind_entry(KC1)],
                         "lines": KIND_LINES + [keys_line(3)]}),
    ("duplicate-in-another-file", {"changed": (KALLOW, "fastfix/allow/b.yml"),
                                   "extra_allow": {"fastfix/allow/b.yml": json.dumps({"flips": [kind_entry(KC1)]})}}),
    ("unreadable-other-allowlist", {"changed": (KALLOW, "fastfix/allow/b.yml"),
                                    "extra_allow": {"fastfix/allow/b.yml": "flips: [unclosed"}}),
    ("allowlist-unchanged", {"changed": ()}),
    # the flip line goes only beside its own entry's keys line, with that entry's from and to
    ("flip-without-keys-line", {"lines": [vflip(KC1), keys_line(2)]}),
    ("flip-other-from", {"lines": [vflip(KC1, "UNKNOWN"), keys_line(1), keys_line(2)]}),
    ("flip-of-another-case", {"lines": KIND_LINES + [vflip("tests.test_redteam::test_other")]}),
    ("keys-line-printed-twice", {"lines": KIND_LINES + [keys_line(1)]}),
    ("log-only-keys-line-printed-twice", {"lines": KIND_LINES + [keys_line(2)]}),
    ("keys-line-other-number", {"lines": KIND_LINES + [keys_line(3)]}),
    ("keys-line-other-wording", {"lines": [vflip(KC1), keys_line(1).replace("must be exactly", "must be"),
                                           keys_line(2)]}),
    # any other frozen-judge line, or a judge that broke
    ("other-line", {"lines": KIND_LINES + [NO_SESSION]}),
    ("loosening-broken", {"loosening_code": 2}),
    ("dominance-broken", {"dominance_code": 2}),
    ("foreign-record", {"record": kind_record(candidate="f" * 40)}),
    # another version, another base, another published release
    ("other-version", {"kind_bases": {"1.0.9": TAG_SHA}}),
    ("other-base", {"merge-base": "c" * 40}),
    ("published-elsewhere", {"merge-base": "b" * 40, "kind_bases": {"1.1.0": "b" * 40}}),
])
def test_the_kind_bridge_drops_nothing_it_shouldnt(tmp_path, monkeypatch, name, kw):
    c = kinded(tmp_path, monkeypatch, **kw)["loosening"]
    assert (c.status, c.severity) == (gate.FAIL, gate.BLOCKER), (name, c.severity, c.summary)


def test_the_kind_bridge_never_touches_reproduce_or_dominance(tmp_path, monkeypatch):
    monkeypatch.setattr(gate, "KIND_BRIDGE", {"1.1.0": TAG_SHA})
    outs = {"reproduce": judge_out(KIND_LINES, "reproduce"), "dominance": judge_out(KIND_LINES)}
    checks = static(tmp_path, kind_git(), fake_runner(kind_record(), {"reproduce": 1, "dominance": 1}, outs=outs))
    for id_ in ("reproduce-first", "dominance"):
        assert (checks[id_].status, checks[id_].severity) == (gate.FAIL, gate.BLOCKER), id_


def test_both_bridges_together_name_each_dropped_line_by_its_bridge(tmp_path, monkeypatch):
    monkeypatch.setattr(gate, "KIND_BRIDGE", {"1.1.0": TAG_SHA})
    monkeypatch.setattr(gate, "NAMING_BRIDGE", {"1.1.0": TAG_SHA})
    allow = {ALLOW: json.dumps({"flips": [gate_entry(p, b) for p, b in GATES.items()]}),
             KALLOW: json.dumps({"flips": [kind_entry(KC1), kind_entry(KC2)]})}
    git_ = answers(**{"merge-base": TAG_SHA, "diff": [ALLOW, KALLOW], "allow": allow,
                      "blobs": {p: b + "0" * 28 for p, b in GATES.items()}})
    record = {**kind_record(), "flips": kind_record()["flips"] + dominance_record()["flips"]}
    lines = BRIDGE_LINES + KIND_LINES
    c = static(tmp_path, git_, fake_runner(record, {"loosening": 1}, outs={"loosening": judge_out(lines)}))["loosening"]
    assert (c.status, c.severity) == (gate.FAIL, gate.MAJOR), c.summary
    assert "gate-naming bridge" in c.summary and "kind bridge" in c.summary, c.summary
    assert f"dropped by the kind bridge: {vflip(KC1)}" in c.output
    assert f"dropped by the gate-naming bridge: {bare('scripts/fastfix_gate.py')}" in c.output


def test_the_kind_bridge_is_keyed_to_v042_for_043_only():
    assert gate.KIND_BRIDGE == {"0.4.3": "61cd95de8b5446d6adf24deda43f9bfb6957ee20"} == gate.NAMING_BRIDGE
    spec = importlib.util.spec_from_file_location("ff_for_kind", SCRIPT)
    ff = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = ff
    spec.loader.exec_module(ff)
    assert gate.ALLOW_KEYS == ff.ALLOW_KEYS


def _v042_judge():
    p = subprocess.run(["git", "-C", str(ROOT), "show", "v0.4.2:scripts/fastfix_gate.py"], capture_output=True,
                       text=True)
    if p.returncode != 0 or "def allow_entries" not in p.stdout:
        pytest.skip("no v0.4.2 tag in this checkout (a shallow clone, the slim container, mutmut's copy)")
    spec = importlib.util.spec_from_loader("fastfix_gate_v042", loader=None)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    exec(compile(p.stdout, "v0.4.2:scripts/fastfix_gate.py", "exec"), mod.__dict__)
    return mod


@needs_git
def test_the_kind_bridge_reads_the_published_judges_own_lines_for_the_same_record(tmp_path):
    """The published v0.4.2 judge's allow_entries and Flip print the lines the bridge drops, and HEAD's judge writes
    the dominance record the bridge reads, for the same allowlist entry (FX-0.4.3-gate-flip-naming-split's lesson)."""
    old = _v042_judge()
    import yaml
    (tmp_path / "fastfix/allow").mkdir(parents=True)
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests/test_redteam.py").write_text("", encoding="utf-8")
    (tmp_path / KALLOW).write_text(yaml.safe_dump({"flips": [kind_entry(KC1)]}), encoding="utf-8")
    report = old.Report()
    assert old.allow_entries(KALLOW, tmp_path, {KALLOW, "tests/test_redteam.py"}, report, set()) == []
    printed = [f"BLOCKED {p}" for p in report.problems]
    printed.append(f"{gate.JUDGE_FLIP}{old.Flip('fixtures', KC1, 'FAIL', 'PASS')}")
    # HEAD's judge: the record of the same entry allowing the same flip as a new read
    spec = importlib.util.spec_from_file_location("ff_for_kind_record", SCRIPT)
    ff = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = ff
    spec.loader.exec_module(ff)
    rep = ff.Report()
    rep.allowed[ff.Flip("fixtures", KC1, "FAIL", "PASS", ff.NEW_READ, ("eos",))] = KALLOW
    record = {**rep.as_json(), "candidate": HEAD}
    git_ = answers(**{"diff": [KALLOW], "allow": {KALLOW: json.dumps({"flips": [kind_entry(KC1)]})}})
    bridge = gate.kind_bridge_from_dominance(git_, TAG_SHA, record)
    assert bridge.entries == {(KALLOW, 1): (KC1, "FAIL", "PASS")}
    assert printed == [keys_line(1), vflip(KC1)] and all(bridge.covers(ln, printed) for ln in printed), printed


def _listing_runner(record):
    seen = {}

    def runner(cmd, timeout):
        cmd = [str(c) for c in cmd]
        name = "dominance" if "--dominance" in cmd else cmd[2]
        seen[name] = {p.name: p.read_text(encoding="utf-8") for p in Path(cmd[1]).parent.iterdir()}
        if "--json" in cmd:
            data = record if name == "dominance" else {"caught": 1, "applied": 1, "total": 1, "not_applicable": [],
                                                       "pending_since_base": []}
            Path(cmd[cmd.index("--json") + 1]).write_text(json.dumps(data), encoding="utf-8")
        return gate.Proc(0, "out", 0.1)
    runner.seen = seen
    return runner


def test_a_judge_is_copied_out_with_its_own_commits_command_log_plugin(tmp_path):
    """The plugin and the logging code beside each judge come from the judge's own commit: the published release's
    when it judges, the base's for the base judge."""
    r = _listing_runner(CLEAN)
    static(tmp_path, answers(), r)
    assert r.seen["dominance"]["fastfix_cmdlog.py"] == TAG_JUDGE + "\n"           # the tag's commit, as its judge
    assert r.seen["dominance"]["fastfix_cmdlog_fakes.py"] == TAG_JUDGE + "\n"
    assert r.seen["loosening"]["fastfix_cmdlog.py"] == "BASE\n"                  # the base judge: the base's own


def test_the_bootstrap_judge_gets_heads_plugin(tmp_path, monkeypatch):
    monkeypatch.setattr(gate, "BOOTSTRAP_TAG", "v1.0.0")
    monkeypatch.setattr(gate, "BOOTSTRAP_NEXT", "1.1.0")
    r = _listing_runner(CLEAN)
    static(tmp_path, answers(**{"show-tag": "no commands here"}), r)
    assert r.seen["dominance"]["dominance_judge.py"] == HEAD_JUDGE + "\n"
    assert r.seen["dominance"]["fastfix_cmdlog.py"] == HEAD_JUDGE + "\n"         # HEAD's, as the judge


def test_no_plugin_is_written_beside_a_judge_whose_commit_has_none(tmp_path):
    judge = tmp_path / "judge.py"
    gate.cmdlog_beside(lambda *c: None if c[1].endswith("tests/fakes.py") else "plugin text", "abc", judge)
    assert list(tmp_path.iterdir()) == []                                        # both or neither
    gate.cmdlog_beside(lambda *c: "text", "abc", judge)
    assert sorted(p.name for p in tmp_path.iterdir()) == ["fastfix_cmdlog.py", "fastfix_cmdlog_fakes.py"]
