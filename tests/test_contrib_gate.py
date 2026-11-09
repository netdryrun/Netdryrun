"""The contributor CI gates (scripts/contrib_gate.py): each one must fail on the thing it guards against."""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import contrib_gate as gate  # noqa: E402

needs_git = pytest.mark.skipif(shutil.which("git") is None or shutil.which("tar") is None, reason="needs git and tar")


def sh(cwd, *cmd, **kw):
    return subprocess.run(cmd, cwd=cwd, check=True, capture_output=True, text=True, **kw).stdout


@pytest.fixture
def repo(tmp_path, monkeypatch):
    r = tmp_path / "repo"
    r.mkdir()
    sh(r, "git", "init", "-q", "-b", "main")
    sh(r, "git", "config", "user.name", "Ada Contributor")
    sh(r, "git", "config", "user.email", "ada@example.org")
    sh(r, "git", "config", "commit.gpgsign", "false")
    monkeypatch.setattr(gate, "ROOT", r)
    return r


def commit(repo, files: dict[str, str], msg: str):
    for rel, text in files.items():
        p = repo / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
    sh(repo, "git", "add", "-A")
    sh(repo, "git", "commit", "-q", "-m", msg)
    return sh(repo, "git", "rev-parse", "HEAD").strip()


# ---- DCO --------------------------------------------------------------------------------------------------------
@needs_git
def test_dco_wants_a_sign_off_by_the_author(repo):
    base = commit(repo, {"a.txt": "1"}, "base")
    commit(repo, {"a.txt": "2"}, "no sign-off")
    assert gate.dco(base) and "no Signed-off-by" in gate.dco(base)[0]
    sh(repo, "git", "commit", "-q", "--amend", "-m", "signed\n\nSigned-off-by: Someone Else <else@example.org>")
    assert gate.dco(base), "a sign-off by someone else is not the author's"
    sh(repo, "git", "commit", "-q", "--amend", "-s", "-m", "signed")
    assert gate.dco(base) == []


# ---- disclosure -------------------------------------------------------------------------------------------------
TEMPLATE = (ROOT / ".github" / "pull_request_template.md").read_text(encoding="utf-8")


def test_the_pr_template_has_the_disclosure_boxes_unticked():
    assert gate.disclosure(TEMPLATE)          # as it comes: nothing ticked, so the gate fails
    assert len(gate.DISCLOSURE.findall(TEMPLATE)) == 2


@pytest.mark.parametrize("which", ["No AI tools", "AI tools"])
def test_one_ticked_box_passes_either_way(which):
    body = TEMPLATE.replace(f"- [ ] {which}", f"- [x] {which}", 1)
    assert gate.disclosure(body) == []


def test_both_ticked_or_none_or_no_body_fails():
    both = TEMPLATE.replace("- [ ] No AI tools", "- [x] No AI tools").replace("- [ ] AI tools", "- [x] AI tools")
    assert gate.disclosure(both) and gate.disclosure("") and gate.disclosure(None)


# ---- fails on revert ----------------------------------------------------------------------------------------------
PKG = {"src/netdryrun/__init__.py": "", "src/netdryrun/drivers/__init__.py": "",
       "src/netdryrun/drivers/x.py": "def established(state):\n    return state == 'Established'\n"}


@needs_git
def test_a_verdict_change_with_no_test_fails(repo):
    base = commit(repo, PKG, "base")
    commit(repo, {"src/netdryrun/drivers/x.py": "def established(state):\n    return state.lower() == 'established'\n"},
           "fix")
    assert "no test added or changed" in gate.fails_on_revert(base)[0]


@needs_git
def test_a_test_that_passes_on_the_old_code_too_fails(repo):
    base = commit(repo, PKG, "base")
    commit(repo, {"src/netdryrun/drivers/x.py": "def established(state):\n    return state.lower() == 'established'\n",
                  "tests/test_x.py": "from netdryrun.drivers.x import established\n\n"
                                     "def test_it():\n    assert established('Established')\n"}, "fix")
    assert "also pass on the base branch's code" in gate.fails_on_revert(base)[0]


@needs_git
def test_a_test_that_fails_on_the_old_code_passes_the_gate(repo):
    base = commit(repo, PKG, "base")
    commit(repo, {"src/netdryrun/drivers/x.py": "def established(state):\n    return state.lower() == 'established'\n",
                  "tests/test_x.py": "from netdryrun.drivers.x import established\n\n"
                                     "def test_it():\n    assert established('established')\n"}, "fix")
    assert gate.fails_on_revert(base) == []


@needs_git
def test_docs_only_changes_need_no_test(repo):
    base = commit(repo, PKG, "base")
    commit(repo, {"README.md": "hello"}, "docs")
    assert gate.fails_on_revert(base) == []


# ---- known false passes: the base branch's tests against this code ------------------------------------------------
@needs_git
def test_a_known_false_pass_that_comes_back_fails_even_if_the_pr_weakens_its_test(repo):
    base = commit(repo, {**PKG, "tests/known_false_passes.yml": "- id: x\n  tests: [tests/test_x.py]\n",
                         "tests/test_x.py": "from netdryrun.drivers.x import established\n\n"
                                            "def test_idle_is_not_up():\n    assert not established('Idle')\n"}, "base")
    assert gate.known_false_passes(base) == []
    # the PR brings the false pass back and "fixes" the test that guards it
    commit(repo, {"src/netdryrun/drivers/x.py": "def established(state):\n    return True\n",
                  "tests/test_x.py": "def test_idle_is_not_up():\n    pass\n"}, "weaken")
    found = gate.known_false_passes(base)
    assert found and "known false pass is back" in found[0]


@needs_git
def test_a_base_test_that_reads_src_by_path_reads_the_code_under_test(repo):
    """Dependabot PRs #4 and #5: a base test that scans src/ by path (test_verdict_keys_041.py) crashed with
    FileNotFoundError, because the base tree had its src/ removed. The tree now carries this checkout's src/, so the
    scan reads the code under test, and a false pass brought back in it still fails the gate."""
    scan = ("from pathlib import Path\n\n"
            "def test_scan():\n"
            "    src = Path(__file__).parent.parent / 'src' / 'netdryrun' / 'drivers' / 'x.py'\n"
            "    assert 'return True' not in src.read_text()\n")
    base = commit(repo, {**PKG, "tests/known_false_passes.yml": "- id: x\n  tests: [tests/test_scan.py]\n",
                         "tests/test_scan.py": scan}, "base")
    assert gate.known_false_passes(base) == []
    commit(repo, {"README.md": "a dependency bump"}, "bump")
    assert gate.known_false_passes(base) == []
    commit(repo, {"src/netdryrun/drivers/x.py": "def established(state):\n    return True\n"}, "bring it back")
    found = gate.known_false_passes(base)
    assert found and "known false pass is back" in found[0]


def _event(login, type_="Bot", head="netdryrun/Netdryrun", base="netdryrun/Netdryrun", body=""):
    return {"pull_request": {"user": {"login": login, "type": type_}, "body": body,
                             "head": {"repo": {"full_name": head}}, "base": {"repo": {"full_name": base}}}}


def test_dependabot_is_exempt_from_the_disclosure_and_nobody_else_is():
    assert gate.disclosure_exempt(_event("dependabot[bot]"))
    assert not gate.disclosure_exempt(_event("dependabot[bot]", type_="User"))       # type is GitHub's, not the name
    assert not gate.disclosure_exempt(_event("dependabot"))                           # a human named like the bot
    assert not gate.disclosure_exempt(_event("renovate[bot]"))                        # only the listed bot
    assert not gate.disclosure_exempt(_event("dependabot[bot]", head="someone/fork"))  # never from a fork
    assert not gate.disclosure_exempt(_event("dependabot[bot]", head=None))
    assert not gate.disclosure_exempt({})                                             # fail closed on a bare event


def test_the_disclosure_command_passes_dependabot_and_still_fails_a_human(tmp_path):
    ev = tmp_path / "event.json"
    ev.write_text(json.dumps(_event("dependabot[bot]")), encoding="utf-8")
    assert gate.main(["disclosure", str(ev)]) == 0
    ev.write_text(json.dumps(_event("ada", type_="User")), encoding="utf-8")
    assert gate.main(["disclosure", str(ev)]) == 1


# ---- corpus -----------------------------------------------------------------------------------------------------
def _tree(root: Path, cases: dict[str, str], amend: str = "") -> Path:
    (root / "corpus" / "cases").mkdir(parents=True)
    (root / "corpus" / "v2" / "cases").mkdir(parents=True)
    for rel, text in cases.items():
        (root / "corpus" / rel).write_text(text, encoding="utf-8")
    (root / "corpus" / "AMENDMENTS.md").write_text("# Amendments\n" + amend, encoding="utf-8")
    return root


CASE = "id: 10-leak\nexpected: unsafe\nedits: []\n"


def test_a_changed_expected_verdict_needs_an_amendment(tmp_path):
    base = _tree(tmp_path / "a", {"cases/10-leak.yml": CASE})
    head = _tree(tmp_path / "b", {"cases/10-leak.yml": CASE.replace("unsafe", "safe")})
    assert "expected verdict unsafe -> safe" in gate.corpus_guard(base, head)[0]
    amended = _tree(tmp_path / "c", {"cases/10-leak.yml": CASE.replace("unsafe", "safe")}, "\n## 10-leak\nwhy\n")
    assert gate.corpus_guard(base, amended) == []


def test_a_deleted_case_or_a_rewritten_amendment_fails(tmp_path):
    base = _tree(tmp_path / "a", {"cases/10-leak.yml": CASE}, "old entry\n")
    head = _tree(tmp_path / "b", {}, "rewritten\n")
    found = gate.corpus_guard(base, head)
    assert any("deleted" in p for p in found) and any("append-only" in p for p in found)


def test_a_new_case_is_welcome(tmp_path):
    base = _tree(tmp_path / "a", {"cases/10-leak.yml": CASE})
    head = _tree(tmp_path / "b", {"cases/10-leak.yml": CASE, "v2/cases/31-new.yml": CASE})
    assert gate.corpus_guard(base, head) == []


def test_committed_results_or_the_nondeterministic_list_need_an_amendment_to_change(tmp_path):
    def tree(name, verdict, nondet="{}", amend=""):
        t = _tree(tmp_path / name, {"v2/cases/10-leak.yml": CASE})
        (t / "corpus" / "v2" / "results").mkdir()
        (t / "corpus" / "v2" / "results" / "results.json").write_text(json.dumps(
            {"cases": [{"id": "10-leak", "strategies": {"netdryrun": {"verdict": verdict}}}]}))
        (t / "corpus" / "v2" / "NONDETERMINISTIC.yml").write_text(nondet)
        (t / "corpus" / "v2" / "AMENDMENTS.md").write_text("# v2\n" + amend)
        return t
    base = tree("a", "unsafe")
    assert any("results.json: 10-leak" in p for p in gate.corpus_guard(base, tree("b", "safe")))
    assert any("NONDETERMINISTIC.yml: 10-leak added" in p
               for p in gate.corpus_guard(base, tree("c", "unsafe", "10-leak: {why: race}\n")))
    assert gate.corpus_guard(base, tree("d", "safe", amend="\n## 10-leak\nrerun on 0.4.1\n")) == []


def test_the_committed_corpus_is_unchanged_against_itself():
    assert gate.corpus_guard(ROOT, ROOT) == []


def test_corpus_results_fail_on_any_changed_netdryrun_verdict():
    committed = ROOT / "corpus" / "v2" / "results" / "results.json"
    data = json.loads(committed.read_text(encoding="utf-8"))
    assert gate.corpus_results(committed, committed) == ([], [])
    flipped = json.loads(json.dumps(data))
    for c in flipped["cases"]:
        v = c["strategies"]["netdryrun"]["verdict"]
        # an inconclusive run (verdict "error", 8 v2 cases since 0.4.1) turning safe is a change too
        c["strategies"]["netdryrun"]["verdict"] = {"unsafe": "safe", "safe": "unsafe", "error": "safe"}.get(v, v)
    new = committed.parent / "flipped.json"
    try:
        new.write_text(json.dumps(flipped), encoding="utf-8")
        problems, notes = gate.corpus_results(committed, new)
    finally:
        new.unlink()
    assert len(problems) == len(data["cases"]) - 1          # every case but the nondeterministic one
    assert len(notes) == 1 and "18-aggregate-discard-route-removed" in notes[0]


# ---- provenance -------------------------------------------------------------------------------------------------
def test_every_committed_fixture_has_a_recorded_source():
    assert gate.provenance() == []


def test_a_fixture_without_a_source_fails(tmp_path):
    fx = tmp_path / "tests" / "fixtures"
    fx.mkdir(parents=True)
    (fx / "a.txt").write_text("{}")
    (fx / "new_capture.txt").write_text("{}")
    (fx / "SOURCES.yml").write_text(yaml.safe_dump([{"files": ["a.txt", "gone.txt"], "kind": "live-capture",
                                                     "source": "lab x", "added": "abc"}]))
    found = gate.provenance(tmp_path)
    assert "tests/fixtures/new_capture.txt: no recorded source" in found[-1]
    assert any("gone.txt matches no file" in p for p in found)


def test_a_source_entry_must_say_what_kind_and_where(tmp_path):
    fx = tmp_path / "tests" / "fixtures"
    fx.mkdir(parents=True)
    (fx / "a.txt").write_text("{}")
    (fx / "SOURCES.yml").write_text(yaml.safe_dump([{"files": ["a.txt"], "kind": "made-up", "source": "me",
                                                     "added": "abc"}]))
    assert "kind must be one of" in gate.provenance(tmp_path)[0]


def test_no_fixture_is_hand_written_any_more():
    assert gate.HAND_WRITTEN == frozenset()


def test_a_new_hand_written_fixture_fails_and_the_frozen_ones_need_a_reason(tmp_path, monkeypatch):
    monkeypatch.setattr(gate, "HAND_WRITTEN", frozenset({"routeros_ping.txt"}))
    fx = tmp_path / "tests" / "fixtures"
    fx.mkdir(parents=True)
    (fx / "my_parser.txt").write_text("{}")
    (fx / "routeros_ping.txt").write_text("[]")
    entry = {"files": ["my_parser.txt", "routeros_ping.txt"], "kind": "hand-written", "source": "typed in",
             "added": "abc"}
    (fx / "SOURCES.yml").write_text(yaml.safe_dump([entry]))
    found = gate.provenance(tmp_path)
    assert any("my_parser.txt: hand-written" in p for p in found)
    assert not any("routeros_ping.txt: hand-written" in p for p in found)
    assert any("must say why" in p for p in found)


def test_a_stray_file_in_captures_fails(tmp_path):
    fx = tmp_path / "tests" / "fixtures"
    fx.mkdir(parents=True)
    (fx / "SOURCES.yml").write_text("[]")
    (tmp_path / "captures" / "iosxe").mkdir(parents=True)
    (tmp_path / "captures" / "iosxe" / "show-bgp.txt").write_text("raw output, no manifest")
    assert any("outside a bundle" in p for p in gate.provenance(tmp_path))


# ---- lab templates ----------------------------------------------------------------------------------------------
def _template(root: Path, **meta_over) -> Path:
    t = root / "community" / "labs" / "frr-pair"
    shutil.copytree(ROOT / "examples" / "frr-bgp", t)
    (t / "bad").mkdir()
    (t / "bad" / "configs").mkdir()
    shutil.copy(ROOT / "examples" / "frr-bgp-broken" / "r2-bad.conf", t / "bad" / "configs" / "r2.conf")
    meta = {"name": "frr-pair", "description": "x", "nos": ["frr"], "images": ["quay.io/frrouting/frr:10.4.1"],
            "licence": "free", "expected": {"good": "passed", "bad": "failed"}, "bad_change": "r2 leaks a default",
            "author": "ada", "source": "written for this template"} | meta_over
    (t / "template.yml").write_text(yaml.safe_dump(meta))
    return t


def test_a_complete_template_passes_the_static_checks(tmp_path):
    _template(tmp_path)
    assert gate.labs(tmp_path) == []


@pytest.mark.parametrize("over,why", [
    ({"expected": {"good": "passed", "bad": "passed"}}, "expected must be"),
    ({"images": ["quay.io/frrouting/frr:latest"]}, "not pinned"),
    ({"images": ["frrouting/frr"]}, "not pinned"),
    ({"nos": ["iosxe"]}, "has no driver"),
    ({"licence": "ask me"}, "licence must be"),
    ({"licence": "bring-your-own-image"}, "needs reports/good.json"),
    ({"author": ""}, "missing author"),
])
def test_template_problems(tmp_path, over, why):
    _template(tmp_path, **over)
    assert any(why in p for p in gate.labs(tmp_path)), gate.labs(tmp_path)


def test_a_template_without_a_bad_change_fails(tmp_path):
    t = _template(tmp_path)
    shutil.rmtree(t / "bad")
    assert any("no bad/ change" in p for p in gate.labs(tmp_path))


def test_a_bad_change_must_edit_the_lab(tmp_path):
    t = _template(tmp_path)
    (t / "bad" / "configs" / "r9.conf").write_text("hostname r9\n")
    assert any("replaces no file" in p for p in gate.labs(tmp_path))
