"""Red fixtures for scripts/fastfix_gate.py: the loosening gate and the reproduce-first check (0.4.2 fast fix).

Each test builds a throwaway git repository holding a toy verifier (`src/toy`: judge(x) is True when x "passes"),
its red-team and pinned fixtures, fixture data outside tests/, and corpus results, then attacks one rule. Every
attack must block (exit 1), every unreadable input must fail (exit 2), and only the honest changes are clean.

Where this runs (LESSONS 13): the repo; mutmut's runner (the script is found by __file__, never the cwd, and git
always gets -C <the temp repo>, because a bare git inside mutants/ would find the outer checkout); the slim container
(no git there: the git tests skip and test_git_mode_fails_closed_without_git proves the commands refuse to run); and
the live layer's scratch copy (test_loosening_files_runs_alone_in_a_scratch_copy).
"""
from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "fastfix_gate.py"
_spec = importlib.util.spec_from_file_location("fastfix_gate_under_test", SCRIPT)
ffg = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = ffg        # dataclasses look the module up while the class is built
_spec.loader.exec_module(ffg)

needs_git = pytest.mark.skipif(shutil.which("git") is None, reason="no git here (slim container): "
                               "test_git_mode_fails_closed_without_git covers this shape")

JUDGE = "LIMIT = 0\n\n\ndef judge(x):\n    return x > LIMIT\n"
REDTEAM = textwrap.dedent('''\
    from pathlib import Path

    import yaml

    from toy import judge

    DATA = Path(__file__).resolve().parents[1] / "data" / "bad.yml"


    def test_refuses_negative():
        assert not judge(-1)


    def test_refuses_data_cases():
        for v in yaml.safe_load(DATA.read_text())["bad"]:
            assert not judge(v)
    ''')
PINNED = "from toy import judge\n\n\ndef test_zero_refused():\n    assert not judge(0)\n"
RT_PINNED = "id: RT-0001\ntitle: zero passed\nkind: pinned\ntests:\n  - tests/test_pinned.py::test_zero_refused\n"


def results(**cases) -> str:
    rows = []
    for cid, v in cases.items():
        row = {"id": cid, "strategies": {"netdryrun": {"verdict": v[0] if isinstance(v, list) else v}}}
        if isinstance(v, list):
            row["runs"] = [{"netdryrun": x} for x in v]
        rows.append(row)
    return json.dumps({"schema": "netdryrun.corpus/v1", "cases": rows}, indent=1)


BASE_RESULTS = results(c1="unsafe", c2="safe", c3="error", c4=["unsafe", "safe", "unsafe"])


class Repo:
    def __init__(self, path: Path):
        self.path = path
        path.mkdir()
        self.git("init", "-q", "-b", "main")
        self.git("config", "user.email", "t@example.invalid")
        self.git("config", "user.name", "t")
        self.git("config", "commit.gpgsign", "false")

    def git(self, *args: str) -> str:
        return subprocess.run(["git", "-C", str(self.path), *args], check=True, capture_output=True,
                              text=True).stdout.strip()

    def write(self, rel: str, text: str) -> None:
        p = self.path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")

    def remove(self, rel: str) -> None:
        self.git("rm", "-q", "-r", rel)

    def commit(self, subject: str, **trailers: str) -> str:
        self.git("add", "-A")
        lines = "\n".join(f"{k.replace('_', '-')}: {v}" for k, v in trailers.items())
        self.git("commit", "-q", "--allow-empty", "-m", subject, *(["-m", lines] if lines else []))
        return self.git("rev-parse", "HEAD")

    def loosening(self, base: str, cand: str = "HEAD") -> tuple[int, str]:
        return run_main(["loosening", "--repo", str(self.path), "--base", base, "--candidate", cand])

    def reproduce(self, base: str, cand: str = "HEAD") -> tuple[int, str]:
        return run_main(["reproduce", "--repo", str(self.path), "--range", f"{base}..{cand}"])


def run_main(argv: list[str]) -> tuple[int, str]:
    p = subprocess.run([sys.executable, str(SCRIPT), *argv], capture_output=True, text=True,
                       env={k: v for k, v in os.environ.items() if k != "PYTHONPATH"}, timeout=600)
    return p.returncode, p.stdout + p.stderr


@pytest.fixture
def repo(tmp_path) -> Repo:
    r = Repo(tmp_path / "r")
    r.write("pyproject.toml", '[tool.pytest.ini_options]\ntestpaths = ["tests"]\n')
    r.write("src/toy/__init__.py", JUDGE)
    r.write("tests/conftest.py", "")
    r.write("tests/test_redteam.py", REDTEAM)
    r.write("tests/test_pinned.py", PINNED)
    r.write("tests/redteam/RT-0001-zero.yml", RT_PINNED)
    r.write("data/bad.yml", "bad: [-5, -2]\n")
    r.write("corpus/results/results.json", BASE_RESULTS)
    r.base = r.commit("base")
    return r


# ------------------------------------------------------------------------------------------------ loosening

@needs_git
def test_tightening_change_is_clean(repo):
    repo.write("src/toy/__init__.py", JUDGE.replace("x > LIMIT", "x > LIMIT and x != 99"))
    repo.write("corpus/results/results.json", results(c1="unsafe", c2="unsafe", c3="error",
                                                      c4=["unsafe", "safe", "unsafe"]))
    repo.commit("tighten")
    code, out = repo.loosening(repo.base)
    assert code == 0, out
    assert "loosening: clean" in out


@needs_git
@pytest.mark.parametrize("case,new", [("c1", "safe"), ("c3", "safe"), ("c4", ["safe", "safe", "safe"]),
                                      ("c1", ["unsafe", "safe", "unsafe"])])
def test_corpus_flip_blocks(repo, case, new):
    cases = {"c1": "unsafe", "c2": "safe", "c3": "error", "c4": ["unsafe", "safe", "unsafe"], case: new}
    repo.write("corpus/results/results.json", results(**cases))
    repo.commit("refresh")
    code, out = repo.loosening(repo.base)
    assert code == 1, out
    assert f"corpus/results/results.json :: {case}:" in out


@needs_git
def test_flip_hidden_by_offsetting_tightening_blocks(repo):
    # c1 loosens while c2 tightens: the PASS count is unchanged, the per-case comparison still sees it
    repo.write("corpus/results/results.json", results(c1="safe", c2="unsafe", c3="error",
                                                      c4=["unsafe", "safe", "unsafe"]))
    repo.commit("swap")
    code, out = repo.loosening(repo.base)
    assert code == 1 and ":: c1: FAIL -> PASS" in out, out


@needs_git
def test_case_removed_blocks(repo):
    repo.write("corpus/results/results.json", results(c2="safe", c3="error", c4=["unsafe", "safe", "unsafe"]))
    repo.commit("drop c1")
    code, out = repo.loosening(repo.base)
    assert code == 1 and "c1: judged at the base, not at the candidate" in out, out


@needs_git
def test_results_file_removed_blocks(repo):
    repo.remove("corpus/results/results.json")
    repo.commit("drop results")
    code, out = repo.loosening(repo.base)
    assert code == 1 and "missing at the candidate" in out, out


@needs_git
@pytest.mark.parametrize("text", [
    results(c1="unsafe", c2="safe", c3="maybe", c4="unsafe"),                          # unknown verdict word
    '{"cases": [{"id": "c1", "strategies": {"netdryrun": {"verdict": "unsafe", "verdict": "safe"}}}]}',  # dup key
    results(c1="unsafe", c2="safe", c3="error", c4="unsafe").replace('"c2"', '"c1"'),  # duplicate case id
    "{not json",
])
def test_unreadable_results_fail(repo, text):
    repo.write("corpus/results/results.json", text)
    repo.commit("bad results")
    code, out = repo.loosening(repo.base)
    assert code == 2, out


@needs_git
def test_src_loosening_caught_by_redteam_blocks(repo):
    repo.write("src/toy/__init__.py", JUDGE.replace("LIMIT = 0", "LIMIT = -10"))
    repo.commit("loosen")
    code, out = repo.loosening(repo.base)
    assert code == 1 and "test_refuses_negative: FAIL -> PASS" in out, out


@needs_git
def test_edited_redteam_fixture_is_still_judged_by_the_base(repo):
    repo.write("src/toy/__init__.py", JUDGE.replace("LIMIT = 0", "LIMIT = -10"))
    repo.write("tests/test_redteam.py", "def test_refuses_negative():\n    pass\n\n\ndef test_refuses_data_cases():\n    pass\n")
    repo.commit("loosen and edit the fixture")
    code, out = repo.loosening(repo.base)
    assert code == 1 and "test_refuses_negative: FAIL -> PASS" in out, out


@needs_git
def test_edited_fixture_data_outside_tests_is_still_the_bases(repo):
    repo.write("src/toy/__init__.py", JUDGE.replace("x > LIMIT", "x > LIMIT or x == -5"))
    repo.write("data/bad.yml", "bad: [-2]\n")
    repo.commit("loosen -5 and drop it from the data")
    code, out = repo.loosening(repo.base)
    assert code == 1 and "test_refuses_data_cases: FAIL -> PASS" in out, out


@needs_git
def test_pinned_redteam_test_is_run(repo):
    repo.write("src/toy/__init__.py", JUDGE.replace("x > LIMIT", "x > LIMIT or x == 0"))
    repo.commit("loosen zero")
    code, out = repo.loosening(repo.base)
    assert code == 1 and "test_zero_refused: FAIL -> PASS" in out, out


@needs_git
@pytest.mark.parametrize("plant,text", [
    ("conftest.py", "import pytest\n\n@pytest.hookimpl(hookwrapper=True)\ndef pytest_runtest_makereport(item, call):\n"
                    "    rep = (yield).get_result()\n    rep.outcome = 'passed'\n"),
    ("src/sitecustomize.py", "import toy\ntoy.LIMIT = 0\n"),
    ("src/pytest.py", "raise SystemExit(0)\n"),
    ("pytest.ini", "[pytest]\naddopts = --deselect tests/test_redteam.py::test_refuses_negative\n"),
])
def test_candidate_cannot_take_over_the_harness(repo, plant, text):
    repo.write("src/toy/__init__.py", JUDGE.replace("LIMIT = 0", "LIMIT = -10"))
    repo.write(plant, text)
    repo.commit("loosen and plant")
    code, out = repo.loosening(repo.base)
    assert code == 1 and "test_refuses_negative: FAIL -> PASS" in out, out


@needs_git
def test_skipped_fixture_counts_as_pass(repo):
    repo.write("src/toy/__init__.py", JUDGE + "\nimport pytest\npytest.skip('nope', allow_module_level=True)\n")
    repo.commit("skip everything")
    code, out = repo.loosening(repo.base)
    assert code == 1, out


@needs_git
def test_dirty_working_tree_is_ignored(repo):
    repo.write("src/toy/__init__.py", JUDGE.replace("LIMIT = 0", "LIMIT = -10"))
    loose = repo.commit("loosen")
    repo.write("src/toy/__init__.py", JUDGE)        # uncommitted repair: must not hide the committed loosening
    code, out = repo.loosening(repo.base, loose)
    assert code == 1, out


@needs_git
def test_red_baseline_blocks(tmp_path):
    r = Repo(tmp_path / "r")
    r.write("src/toy/__init__.py", JUDGE.replace("LIMIT = 0", "LIMIT = -10"))
    r.write("tests/test_redteam.py", REDTEAM)
    r.write("data/bad.yml", "bad: [-5]\n")
    r.write("tests/redteam/README.md", "")
    r.write("corpus/results/results.json", BASE_RESULTS)
    base = r.commit("red base")
    r.write("README.md", "x")
    r.commit("docs")
    code, out = r.loosening(base)
    assert code == 1 and "the baseline is red" in out, out


ALLOW = textwrap.dedent("""\
    flips:
      - source: corpus/results/results.json
        case: c1
        from: FAIL
        to: PASS
        evidence: [captures/c1-rerun.txt]
        why: The c1 lab topology was rebuilt with the corrected export filter, see the capture.
        reviewed_by: coordinator
    """)


def _flip_c1(repo, session="fixer"):
    repo.write("captures/c1-rerun.txt", "router output\n")
    repo.write("src/toy/__init__.py", JUDGE + "# c1 handled\n")
    repo.write("corpus/results/results.json", results(c1="safe", c2="safe", c3="error",
                                                      c4=["unsafe", "safe", "unsafe"]))
    repo.commit("c1 is safe now", Session=session, No_Oracle="false alarm on c1, see captures/c1-rerun.txt")


@needs_git
def test_reviewed_allowlist_from_another_session_is_clean(repo):
    _flip_c1(repo)
    repo.write("fastfix/allow/c1.yml", ALLOW)
    repo.commit("allow c1", Session="reviewer")
    code, out = repo.loosening(repo.base)
    assert code == 0, out
    assert "allowed by fastfix/allow/c1.yml" in out


@needs_git
@pytest.mark.parametrize("mutate,expect", [
    (lambda a: a, "also changed shipped code"),                                                     # same session
    (lambda a: a.replace("captures/c1-rerun.txt", "src/toy/__init__.py"), "evidence must be"),
    (lambda a: a.replace("captures/c1-rerun.txt", "data/bad.yml"), "evidence must be"),      # didn't change
    (lambda a: a.replace("case: c1", "case: c2"), "not a flip in this change"),            # stale entry
    (lambda a: a.replace("case: c1", "case: c*"), "no wildcards"),
    (lambda a: a.replace("see the capture.", "x").replace("The c1 lab topology was rebuilt with", "x"), "'why'"),
    (lambda a: a.replace("    reviewed_by: coordinator\n", ""), "keys must be exactly"),
])
def test_bad_allowlist_blocks(repo, mutate, expect):
    assert expect == "also changed shipped code" or mutate(ALLOW) != ALLOW, "the mutation must change the allowlist"
    _flip_c1(repo)
    repo.write("fastfix/allow/c1.yml", mutate(ALLOW))
    same = expect == "also changed shipped code"
    repo.commit("allow c1", Session="fixer" if same else "reviewer")
    code, out = repo.loosening(repo.base)
    assert code == 1 and expect in out, out


@needs_git
def test_allowlist_in_the_fix_commit_blocks(repo):
    repo.write("fastfix/allow/c1.yml", ALLOW)
    _flip_c1(repo)
    code, out = repo.loosening(repo.base)
    assert code == 1 and "an allowlist commit holds nothing else" in out, out


@needs_git
def test_allowlist_that_predates_the_change_does_not_apply(repo):
    repo.write("captures/c1-rerun.txt", "router output\n")
    repo.write("fastfix/allow/c1.yml", ALLOW)
    old = repo.commit("old allow", Session="reviewer")
    repo.write("src/toy/__init__.py", JUDGE + "# c1\n")
    repo.write("corpus/results/results.json", results(c1="safe", c2="safe", c3="error",
                                                      c4=["unsafe", "safe", "unsafe"]))
    repo.commit("flip", Session="fixer", No_Oracle="false alarm on c1, see the capture")
    code, out = repo.loosening(old)
    assert code == 1 and "c1: FAIL -> PASS" in out, out


@needs_git
@pytest.mark.parametrize("evidence,code", [("tests/test_pinned.py", 0), ("src/toy/__init__.py", 1),
                                           ("tests/oracles/FP-9/test_oracle_fp_9.py", 1)])
def test_fixture_guard_change_allowed_only_by_its_updated_test(repo, evidence, code):
    # zero is now reported differently (an exception, not a pass): the base's exact-value guard breaks
    repo.write("src/toy/__init__.py", JUDGE.replace("    return x > LIMIT", "    if x == 0:\n        raise ValueError(x)\n"
                                                    "    return x > LIMIT"))
    repo.write("tests/test_pinned.py", PINNED.replace("    assert not judge(0)", "    with pytest.raises(ValueError):\n"
                                                      "        judge(0)").replace("from toy", "import pytest\n\nfrom toy"))
    repo.write("tests/oracles/FP-9/test_oracle_fp_9.py", "def test_x():\n    pass\n")
    repo.commit("zero raises", Session="fixer", No_Oracle="zero is an input error now, see the test")
    repo.write("fastfix/allow/zero.yml", textwrap.dedent(f"""\
        flips:
          - source: fixtures
            case: "tests.test_pinned::test_zero_refused"
            from: FAIL
            to: PASS
            evidence: [{evidence}]
            why: Zero now raises an input error instead of returning a verdict; the updated test pins that.
            reviewed_by: coordinator
        """))
    repo.commit("allow", Session="reviewer")
    out = repo.loosening(repo.base)
    assert out[0] == code, out[1]


@needs_git
@pytest.mark.parametrize("base", ["no-such-ref", "--output=x"])
def test_unresolvable_base_fails(repo, base):
    code, out = repo.loosening(base)
    assert code == 2, out


@needs_git
def test_same_commit_is_not_a_pass(repo):
    code, out = repo.loosening("HEAD")
    assert code == 2 and "nothing to compare" in out, out


def test_git_mode_fails_closed_without_git(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(ffg.shutil, "which", lambda name: None)
    assert ffg.main(["loosening", "--repo", str(tmp_path), "--base", "main"]) == 2
    assert ffg.main(["reproduce", "--repo", str(tmp_path), "--range", "main..HEAD"]) == 2
    assert "git is not available" in capsys.readouterr().out


def test_loosening_files_runs_alone_in_a_scratch_copy(tmp_path):
    """The live layer's scratch copy holds corpus/ and no scripts/, src/ or .git: the script must work alone."""
    scratch = tmp_path / "scratch"
    (scratch / "old").mkdir(parents=True)
    (scratch / "new").mkdir()
    shutil.copy2(SCRIPT, scratch / "fastfix_gate.py")
    (scratch / "old" / "results.json").write_text(BASE_RESULTS, encoding="utf-8")
    env = {k: v for k, v in os.environ.items() if k not in ("PYTHONPATH", "GIT_DIR")}
    env["GIT_CEILING_DIRECTORIES"] = str(tmp_path)

    def check(new: str) -> tuple[int, str]:
        (scratch / "new" / "results.json").write_text(new, encoding="utf-8")
        p = subprocess.run([sys.executable, "fastfix_gate.py", "loosening-files", "--base", "old/results.json",
                            "--candidate", "new/results.json"], cwd=scratch, env=env, capture_output=True, text=True)
        return p.returncode, p.stdout + p.stderr

    assert check(BASE_RESULTS)[0] == 0
    code, out = check(results(c1="safe", c2="safe", c3="error", c4=["unsafe", "safe", "unsafe"]))
    assert code == 1 and "c1: FAIL -> PASS" in out, out
    code, out = check(results(c1="unsafe", c2="safe", c3="error", c4=["safe", "safe", "safe"]))
    assert code == 1 and "c4: MIXED -> PASS" in out, out
    code, out = check(results(c2="safe", c3="error", c4=["unsafe", "safe", "unsafe"]))
    assert code == 1 and "c1: judged at the base" in out, out
    code, out = check("[]")
    assert code == 2, out


def test_corpus_verdicts_reads_every_run():
    v = ffg.corpus_verdicts(json.loads(BASE_RESULTS), "x")
    assert v == {"c1": "FAIL", "c2": "PASS", "c3": "UNKNOWN", "c4": "MIXED"}
    for bad in ({"cases": []}, {"cases": [{"id": "a"}]}, {"cases": [{"id": "a", "strategies": {"netdryrun": {"verdict": "safe"}},
                                                                     "runs": []}]}, []):
        with pytest.raises(ffg.GateError):
            ffg.corpus_verdicts(bad, "x")


# ------------------------------------------------------------------------------------------------ reproduce-first

ORACLE_YML = "id: FP-1\nbug: judge passes the captured value 7, which must be refused\nevidence:\n  - tests/fixtures/fp1.txt\n"
ORACLE_TEST = textwrap.dedent('''\
    from pathlib import Path

    from toy import judge

    CAPTURE = Path(__file__).resolve().parents[2] / "fixtures" / "fp1.txt"


    def test_captured_value_is_refused():
        assert not judge(int(CAPTURE.read_text()))
    ''')
FIXED = JUDGE.replace("x > LIMIT", "x > LIMIT and x != 7")


def _oracle(repo, session="oracle-writer", test=ORACLE_TEST, **extra):
    repo.write("tests/fixtures/fp1.txt", "7\n")
    repo.write("tests/oracles/FP-1/ORACLE.yml", ORACLE_YML)
    repo.write("tests/oracles/FP-1/test_oracle_fp_1.py", test)
    for rel, text in extra.items():
        repo.write(rel, text)
    return repo.commit("oracle FP-1", Oracle="FP-1", Session=session)


@needs_git
def test_reproduce_first_honest_flow_is_clean(repo):
    _oracle(repo)
    repo.write("src/toy/__init__.py", FIXED)
    repo.commit("fix FP-1", Fixes_Oracle="FP-1", Session="fixer")
    code, out = repo.reproduce(repo.base)
    assert code == 0, out
    assert "fails on" in out and "1 oracles held at the candidate" in out


@needs_git
def test_src_change_without_trailer_blocks_and_no_oracle_reason_clears(repo):
    repo.write("src/toy/__init__.py", JUDGE + "# refactor\n")
    repo.commit("refactor")
    code, out = repo.reproduce(repo.base)
    assert code == 1 and "without 'Fixes-Oracle: <ID>' or 'No-Oracle" in out, out
    repo.git("commit", "-q", "--amend", "-m", "refactor", "-m", "No-Oracle: comment only, no verdict path touched")
    assert repo.reproduce(repo.base)[0] == 0


@needs_git
def test_oracle_added_in_the_fix_commit_blocks(repo):
    repo.write("tests/fixtures/fp1.txt", "7\n")
    repo.write("tests/oracles/FP-1/ORACLE.yml", ORACLE_YML)
    repo.write("tests/oracles/FP-1/test_oracle_fp_1.py", ORACLE_TEST)
    repo.write("src/toy/__init__.py", FIXED)
    repo.commit("fix with its own test", Fixes_Oracle="FP-1", Oracle="FP-1", Session="fixer")
    code, out = repo.reproduce(repo.base)
    assert code == 1 and "was not committed before the fix" in out, out


@needs_git
def test_oracle_from_the_fixing_session_blocks(repo):
    _oracle(repo, session="fixer")
    repo.write("src/toy/__init__.py", FIXED)
    repo.commit("fix", Fixes_Oracle="FP-1", Session="fixer")
    code, out = repo.reproduce(repo.base)
    assert code == 1 and "from the fixing session" in out, out


@needs_git
def test_fix_that_edits_its_oracle_blocks(repo):
    _oracle(repo)
    repo.write("src/toy/__init__.py", FIXED)
    repo.write("tests/oracles/FP-1/test_oracle_fp_1.py", ORACLE_TEST.replace("assert not", "assert"))
    repo.commit("fix and bend the oracle", Fixes_Oracle="FP-1", Session="fixer")
    code, out = repo.reproduce(repo.base)
    assert code == 1 and "the fix changes files under tests/oracles/" in out, out


@needs_git
def test_fix_that_edits_the_evidence_blocks(repo):
    _oracle(repo)
    repo.write("src/toy/__init__.py", FIXED)
    repo.write("tests/fixtures/fp1.txt", "-7\n")
    repo.commit("fix and change the capture", Fixes_Oracle="FP-1", Session="fixer")
    code, out = repo.reproduce(repo.base)
    assert code == 1 and "edits its oracle's evidence" in out, out


@needs_git
def test_fix_that_bends_the_shared_harness_blocks(repo):
    # no src change that fixes anything: the fix rewires tests/conftest.py so judge(7) looks refused
    _oracle(repo)
    repo.write("tests/conftest.py", "import toy\n_real = toy.judge\ntoy.judge = lambda x: False if x == 7 else _real(x)\n")
    repo.write("src/toy/__init__.py", JUDGE + "# fixed, honest\n")
    repo.commit("fix", Fixes_Oracle="FP-1", Session="fixer")
    code, out = repo.reproduce(repo.base)
    assert code == 1 and "the oracle must pass on the fix" in out, out


@needs_git
def test_oracle_that_already_passes_on_the_parent_blocks(repo):
    _oracle(repo, test=ORACLE_TEST.replace("assert not judge", "assert judge"))
    repo.write("src/toy/__init__.py", JUDGE + "# nothing\n")
    repo.commit("fix", Fixes_Oracle="FP-1", Session="fixer")
    code, out = repo.reproduce(repo.base)
    assert code == 1 and "must fail on the parent" in out, out


@needs_git
def test_oracle_failing_on_the_parent_without_an_assertion_blocks(repo):
    _oracle(repo, test="from toy import judge, new_api\n\n\ndef test_it():\n    assert not new_api(7)\n")
    repo.write("src/toy/__init__.py", FIXED + "\n\ndef new_api(x):\n    return judge(x)\n")
    repo.commit("fix", Fixes_Oracle="FP-1", Session="fixer")
    code, out = repo.reproduce(repo.base)
    assert code == 1 and "must fail on the parent" in out, out


@needs_git
def test_bug_brought_back_later_blocks(repo):
    _oracle(repo)
    repo.write("src/toy/__init__.py", FIXED)
    repo.commit("fix", Fixes_Oracle="FP-1", Session="fixer")
    repo.write("src/toy/__init__.py", JUDGE)
    repo.commit("revert by accident", No_Oracle="cleanup of an unrelated helper, honest")
    code, out = repo.reproduce(repo.base)
    assert code == 1 and "oracle FP-1 fails on the candidate" in out, out


@needs_git
def test_oracle_commit_that_touches_src_blocks(repo):
    _oracle(repo, **{"src/toy/__init__.py": FIXED})
    code, out = repo.reproduce(repo.base)
    assert code == 1 and "changes files outside tests/" in out, out


@needs_git
@pytest.mark.parametrize("what", ["no-meta", "bad-name", "no-trailer"])
def test_malformed_oracle_blocks(repo, what):
    repo.write("tests/fixtures/fp1.txt", "7\n")
    if what != "no-meta":
        repo.write("tests/oracles/FP-1/ORACLE.yml", ORACLE_YML)
    repo.write(f"tests/oracles/FP-1/{'test_other.py' if what == 'bad-name' else 'test_oracle_fp_1.py'}", ORACLE_TEST)
    repo.commit("oracle", Session="oracle-writer", **({} if what == "no-trailer" else {"Oracle": "FP-1"}))
    repo.write("src/toy/__init__.py", FIXED)
    repo.commit("fix", Fixes_Oracle="FP-1", Session="fixer")
    code, out = repo.reproduce(repo.base)
    assert code == 1, out


@needs_git
def test_src_change_hidden_in_a_merge_resolution_blocks(repo):
    repo.git("checkout", "-q", "-b", "side")
    repo.write("README.md", "side\n")
    repo.commit("side work")
    repo.git("checkout", "-q", "main")
    repo.write("NOTES.md", "main\n")
    repo.commit("main work")
    repo.git("merge", "-q", "--no-ff", "--no-commit", "side")
    repo.write("src/toy/__init__.py", JUDGE.replace("LIMIT = 0", "LIMIT = -10"))
    repo.git("add", "-A")
    repo.git("commit", "-q", "-m", "Merge side")
    code, out = repo.reproduce(repo.base)
    assert code == 1 and "in a merge resolution" in out, out


@needs_git
def test_two_session_trailers_fail(repo):
    repo.write("src/toy/__init__.py", JUDGE + "# x\n")
    repo.git("add", "-A")
    repo.git("commit", "-q", "-m", "x", "-m", "Session: a1a\nSession: b2b\nNo-Oracle: a comment only, nothing else here")
    code, out = repo.reproduce(repo.base)
    assert code == 2 and "exactly one is allowed" in out, out


@needs_git
@pytest.mark.parametrize("rng", ["main", "a...b", "HEAD..HEAD"])
def test_bad_range_fails(repo, rng):
    code, out = run_main(["reproduce", "--repo", str(repo.path), "--range", rng])
    assert code == 2, out


# ------------------------------------------------------------------------------------------------ release gate wiring

def _release_gate():
    spec = importlib.util.spec_from_file_location("release_gate_for_fastfix", SCRIPT.parent / "release_gate.py")
    gate = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = gate
    spec.loader.exec_module(gate)
    return gate


@pytest.mark.parametrize("answers,code,expect", [
    ({"merge-base": None, "rev-parse": "h" * 40, "show": None}, 0, ["FAIL", "FAIL"]),      # shallow clone, unknown ref
    ({"merge-base": "h" * 40, "rev-parse": "h" * 40, "show": None}, 0, ["FAIL", "FAIL"]),  # empty range: strict FAIL
    ({"merge-base": "b" * 40, "rev-parse": "h" * 40, "show": "BASE"}, 1, ["FAIL", "FAIL"]),  # the script blocks
    ({"merge-base": "b" * 40, "rev-parse": "h" * 40, "show": "BASE"}, 2, ["FAIL", "FAIL"]),  # the script can't run
    ({"merge-base": "b" * 40, "rev-parse": "h" * 40, "show": "BASE"}, 0, ["PASS", "PASS"]),
    ({"merge-base": "b" * 40, "rev-parse": "h" * 40, "show": None}, 0, ["PASS", "PASS"]),    # bootstrap: own copy
])
def test_release_gate_static_wiring(answers, code, expect):
    from types import SimpleNamespace
    gate = _release_gate()
    layer = gate.Layer("static", SimpleNamespace(strict=True, version="0.0.0"))
    seen = []

    def runner(cmd, timeout):
        seen.append([str(c) for c in cmd])
        text = Path(cmd[1]).read_text(encoding="utf-8")
        # the base's copy judges the change; only a base without one falls back to this checkout's
        assert text.startswith("BASE") if answers["show"] else text == SCRIPT.read_text(encoding="utf-8")
        return gate.Proc(code, "out", 0.1)

    gate.fastfix_checks(layer, SimpleNamespace(fastfix_base="origin/main"),
                        git_=lambda *a: answers[a[0]], runner=runner)
    assert [c.id for c in layer.checks] == ["loosening", "reproduce-first"]
    assert [c.status for c in layer.checks] == expect
    assert all(c.severity == gate.BLOCKER for c in layer.checks)
    if seen:
        assert seen[0][2:] == ["loosening", "--repo", str(gate.ROOT), "--base", "b" * 40]
        assert seen[1][-2:] == ["--range", "b" * 40 + "..HEAD"]


# ------------------------------------------------------------------------------------------------ code review round

@needs_git
def test_change_to_the_gate_itself_is_a_flip_once_the_base_has_it(repo):
    repo.write("scripts/fastfix_gate.py", "# the judge\n")
    base = repo.commit("gate lands")
    repo.write("scripts/fastfix_gate.py", "# the judge, made lenient\n")
    repo.commit("tweak the judge")
    code, out = repo.loosening(base)
    assert code == 1 and "gate :: scripts/fastfix_gate.py: FAIL -> PASS" in out, out


@needs_git
def test_loosened_action_yml_is_judged_and_needs_a_trailer(repo):
    repo.write("action.yml", "runs:\n  fail_on: unsafe\n")
    repo.write("tests/test_redteam.py", REDTEAM + textwrap.dedent('''

        def test_action_fails_on_unsafe():
            assert "fail_on: unsafe" in (Path(__file__).resolve().parents[1] / "action.yml").read_text()
        '''))
    base = repo.commit("action")
    repo.write("action.yml", "runs:\n  fail_on: never\n")
    repo.commit("relax the action")
    code, out = repo.loosening(base)
    assert code == 1 and "test_action_fails_on_unsafe: FAIL -> PASS" in out, out
    code, out = repo.reproduce(base)
    assert code == 1 and "changes shipped code" in out, out


@needs_git
@pytest.mark.parametrize("evidence,expect", [("captures/c1-rerun.txt", "also changed shipped code"),
                                             ("corpus/results/results.json", "evidence must be")])
def test_records_only_flip_cannot_be_laundered_by_one_session(repo, evidence, expect):
    repo.write("captures/c1-rerun.txt", "router output\n")
    repo.write("corpus/results/results.json", results(c1="safe", c2="safe", c3="error",
                                                      c4=["unsafe", "safe", "unsafe"]))
    repo.commit("edit the records", Session="same-one")
    repo.write("fastfix/allow/c1.yml", ALLOW.replace("captures/c1-rerun.txt", evidence))
    repo.commit("allow it", Session="same-one" if evidence.startswith("captures") else "other-one")
    code, out = repo.loosening(repo.base)
    assert code == 1 and expect in out, out


@needs_git
def test_pytest_raises_oracle_is_accepted(repo):
    _oracle(repo, test="import pytest\n\nfrom toy import judge\n\n\ndef test_seven_is_refused():\n"
                       "    with pytest.raises(ValueError):\n        judge(7)\n")
    repo.write("src/toy/__init__.py", JUDGE.replace("    return x > LIMIT", "    if x == 7:\n        raise ValueError(x)\n"
                                                    "    return x > LIMIT"))
    repo.commit("fix", Fixes_Oracle="FP-1", Session="fixer")
    code, out = repo.reproduce(repo.base)
    assert code == 0, out


@needs_git
def test_harness_planted_before_the_oracle_cannot_bend_it(repo):
    # a fixer-session commit, before the oracle exists, plants a conftest keyed on a marker the "fix" adds
    repo.write("tests/conftest.py", "import toy\nif hasattr(toy, 'FIXED'):\n    toy.judge = lambda x: False\n")
    repo.commit("tidy tests", Session="fixer")
    _oracle(repo)
    repo.write("src/toy/__init__.py", JUDGE + "\nFIXED = True\n")
    repo.commit("fix", Fixes_Oracle="FP-1", Session="fixer")
    code, out = repo.reproduce(repo.base)
    assert code == 1 and "the oracle must pass on the fix" in out, out


def _git_version() -> tuple[int, ...]:
    out = subprocess.run(["git", "--version"], capture_output=True, text=True).stdout if shutil.which("git") else ""
    return tuple(int(x) for x in (out.split()[-1:] or ["0"])[0].split(".")[:2] if x.isdigit())


@needs_git
@pytest.mark.skipif(_git_version() < (2, 36), reason="needs git 2.36+ (--remerge-diff); older git blocks clean "
                    "merges that touch the same file, which is conservative")
def test_clean_merge_needs_no_trailer(repo):
    repo.git("checkout", "-q", "-b", "side")
    repo.write("src/toy/__init__.py", JUDGE + "# side\n")
    repo.commit("side", No_Oracle="comment only, nothing on a verdict path")
    repo.git("checkout", "-q", "main")
    repo.write("src/toy/__init__.py", "# main\n" + JUDGE)
    repo.commit("main", No_Oracle="comment only, nothing on a verdict path")
    repo.git("merge", "-q", "--no-ff", "-m", "Merge side", "side")
    code, out = repo.reproduce(repo.base)
    assert code == 0, out
