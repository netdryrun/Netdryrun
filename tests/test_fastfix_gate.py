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
import re
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
def test_a_fixture_the_base_skips_is_not_a_red_baseline_and_a_skipped_guard_still_blocks(tmp_path):
    """PR #6: 65 docs-snippet fixture tests skip on GitHub's runner (a tool it lacks). A skip at the base proves
    nothing there, so it isn't compared and isn't a red baseline; a guard that passed at the base and is skipped at
    the candidate is still a FAIL -> PASS flip."""
    r = Repo(tmp_path / "r")
    r.write("src/toy/__init__.py", JUDGE)
    r.write("tests/test_redteam.py", REDTEAM + "\n\ndef test_needs_a_tool():\n    import pytest\n"
                                              "    pytest.skip('this machine lacks the tool')\n")
    r.write("data/bad.yml", "bad: [-5]\n")
    r.write("tests/redteam/README.md", "")
    r.write("corpus/results/results.json", BASE_RESULTS)
    base = r.commit("base with an environment skip")
    r.write("README.md", "x")
    r.commit("docs")
    code, out = r.loosening(base)
    assert code == 0 and "skipped at the base" in out, out
    r.write("src/toy/__init__.py", JUDGE + "\nimport pytest\npytest.skip('nope', allow_module_level=True)\n")
    r.commit("skip everything")
    code, out = r.loosening(base)
    # a module-level skip leaves the guards uncollected: each is "judged at the base, not at the candidate", which
    # blocks as surely as a FAIL -> PASS flip
    assert code == 1 and ("FAIL -> PASS" in out or "a missing verdict is not a pass" in out), out


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
def test_an_allowlist_from_the_coding_session_under_a_reordered_name_blocks(repo):
    _flip_c1(repo, session="c1-fix")
    repo.write("fastfix/allow/c1.yml", ALLOW)
    repo.commit("allow c1", Session="Fix_C1")
    code, out = repo.loosening(repo.base)
    assert code == 1 and "also changed shipped code" in out, out


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


@pytest.mark.parametrize("source,case,ok", [
    ("fixtures", "tests.test_verdict_drivers::test_frr_bgp_neighbors[FrrDriver]", True),
    ("fixtures", "tests.test_verdict_drivers::test_frr_bgp_neighbors", True),
    ("fixtures", "tests.test_x::test_y[a-b_1.2]", True),
    ("fixtures", "tests.test_x::test_y[Frr]Driver]", False),        # a ']' inside the id
    ("fixtures", "tests.test_x::test_[y][FrrDriver]", False),       # '[' in the middle
    ("fixtures", "tests.test_x::test_[y]z", False),
    ("fixtures", "tests.test_x::test_y[[FrrDriver]]", False),       # nested
    ("fixtures", "tests.test_x::test_y[]", False),                  # empty
    ("fixtures", "[FrrDriver]", False),                             # nothing but the id
    ("fixtures", "tests.test_x::test_y[Frr*]", False),
    ("fixtures", "tests.test_x::test_y[Frr?]", False),
    ("fixtures", "tests.test_x::test_*[FrrDriver]", False),
    ("fixtures", "tests.test_x::test_?", False),
    ("fixtures", "tests.test_x::test_y]", False),
    ("fixtures", "tests.test_x::test_y[FrrDriver", False),
    ("corpus/results/[ab].json", "c1", False),                      # brackets in source
    ("corpus/results/r.json[x]", "c1", False),
    ("corpus/results/*.json", "c1", False),
    ("corpus/results/r?.json", "c1", False),
])
def test_allowlist_key_is_literal(source, case, ok):
    assert ffg.literal_key(source, case) is ok


def test_parametrised_case_allows_only_its_own_flip(tmp_path, monkeypatch):
    """`test_x[FrrDriver]` is compared by equality: it allows that flip and leaves [SonicDriver] and the bare name."""
    case = "tests.test_verdict_drivers::test_frr_bgp_neighbors"
    allow = "fastfix/allow/p.yml"
    (tmp_path / "fastfix/allow").mkdir(parents=True)
    (tmp_path / "captures").mkdir()
    (tmp_path / "captures/rerun.txt").write_text("router output\n")
    (tmp_path / allow).write_text(textwrap.dedent(f"""\
        flips:
          - source: fixtures
            case: "{case}[FrrDriver]"
            from: FAIL
            to: PASS
            evidence: [captures/rerun.txt]
            why: The FRR driver now reads the neighbor table the fixed way; see the rerun capture.
            reviewed_by: coordinator
        """))
    monkeypatch.setattr(ffg, "changed_files", lambda *a: {allow, "captures/rerun.txt"})
    monkeypatch.setattr(ffg, "separation_problems", lambda *a: None)
    report = ffg.Report(flips=[ffg.Flip("fixtures", f"{case}{p}", "FAIL", "PASS")
                               for p in ("[FrrDriver]", "[SonicDriver]", "")])
    ffg.apply_allowlist(tmp_path, "b", "c", tmp_path, report)
    assert not report.problems, report.problems
    assert sorted(f.case for f in report.flips) == [case, f"{case}[SonicDriver]"]
    assert any("[FrrDriver]" in n for n in report.notes)


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
@pytest.mark.parametrize("oracle_session,fix_session", [
    ("fixer", "fixer"),
    ("fix-unnsess", "unnsess-fix"),           # the same words in another order, case or separator: one session
    ("Unnsess_Fix", "unnsess-fix"),
])
def test_oracle_from_the_fixing_session_blocks(repo, oracle_session, fix_session):
    _oracle(repo, session=oracle_session)
    repo.write("src/toy/__init__.py", FIXED)
    repo.commit("fix", Fixes_Oracle="FP-1", Session=fix_session)
    code, out = repo.reproduce(repo.base)
    assert code == 1 and "from the fixing session" in out, out


@needs_git
def test_the_fixing_side_editing_its_oracle_after_the_fix_blocks_under_a_reordered_name(repo):
    """0306e3c: the fixer's follow-up, under a reordered session name, edited the oracle its fix had to pass."""
    _oracle(repo, session="unnsess-oracle")
    repo.write("src/toy/__init__.py", FIXED)
    repo.commit("fix", Fixes_Oracle="FP-1", Session="unnsess-fix")
    repo.write("tests/oracles/FP-1/test_oracle_fp_1.py", ORACLE_TEST + "\n# loosened\n")
    repo.commit("oracle touch-up", Oracle="FP-1", Session="fix-unnsess")
    code, out = repo.reproduce(repo.base)
    assert code == 1 and "the fixing session (fix-unnsess)" in out, out


@needs_git
def test_an_oracle_session_whose_words_differ_from_the_fixers_is_another_session(repo):
    _oracle(repo, session="unnsess-oracle")
    repo.write("src/toy/__init__.py", FIXED)
    repo.commit("fix", Fixes_Oracle="FP-1", Session="unnsess-fix")
    code, out = repo.reproduce(repo.base)
    assert code == 0, out


def test_same_session_compares_words_not_spelling():
    g = _gate_module()
    assert g.same_session("fix-unnsess", "unnsess-fix") and g.same_session("A.b", "b_a")
    assert not g.same_session("unnsess-fix", "unnsess-oracle") and not g.same_session("ndr-fix-042-n6b", "ndr-fix-042")
    assert not g.same_session(None, "x") and not g.same_session("", "")


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

    gate.fastfix_checks(layer, SimpleNamespace(fastfix_base="origin/main", version="0.0.0"),
                        git_=lambda *a: answers.get(a[0]), runner=runner)
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
    assert code == 1 and re.search(r"gate :: scripts/fastfix_gate.py@[0-9a-f]{12}: FAIL -> PASS", out), out


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


# ---- check-message: trailers where git reads them (PR #6: 897f1e2 and ca9d984 put Fixes-Oracle in its own paragraph)
def _gate_module():
    import importlib.util
    spec = importlib.util.spec_from_file_location("fastfix_gate_msg", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["fastfix_gate_msg"] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.mark.parametrize("msg,ok", [
    ("Fix X\n\nWhy.\n\nFixes-Oracle: FP-042-FRR102\nSession: ndr-a\n", True),
    ("Fix X\n\nFixes-Oracle: FP-042-FRR102\nSession: ndr-a\n", True),
    ("Docs only\n", True),
    ("Docs\n\nJust prose, no trailers.\n", True),
    # the PR #6 shape: `git commit -m subject -m "Fixes-Oracle: X" -m "Session: Y"`
    ("Fix X\n\nFixes-Oracle: FP-042-FRR102\n\nSession: ndr-a\n", False),
    ("Fix X\n\nOracle: RT-S01 is in the body\nand more prose\n\nSession: ndr-a\n", False),
    ("Fix X\n\nWhy.\n\nNo-Oracle: a reason long enough here\nnot a trailer line\n", False),
    ("Fix X\n# a git comment line\n\nFixes-Oracle: FP-1\nSession: s\n", True),
    # a value that names no bug ID (0306e3c), or more than one on a line
    ("Fix X\n\nWhy.\n\nFixes-Oracle: unnsess-adversary MINOR-1,2,3,6\nSession: fix-unnsess\n", False),
    ("Fix X\n\nFixes-Oracle: FP-1, FP-2\nSession: ndr-a\n", False),
    ("Oracle\n\nOracle: fp-1\nSession: ndr-a\n", False),
    ("Oracle\n\nOracle: FP-1\nOracle: RT-0036\nSession: ndr-a\n", True),
])
def test_check_message_finds_trailers_git_wont_read(msg, ok):
    assert (_gate_module().message_problems(msg) == []) is ok


def test_check_message_command_exit_codes(tmp_path):
    good, bad = tmp_path / "good", tmp_path / "bad"
    good.write_text("Fix\n\nFixes-Oracle: FP-1\nSession: s\n", encoding="utf-8")
    bad.write_text("Fix\n\nFixes-Oracle: FP-1\n\nSession: s\n", encoding="utf-8")
    assert run_main(["check-message", str(good)])[0] == 0
    code, out = run_main(["check-message", str(bad)])
    assert code == 1 and "not the trailer block" in out
    assert run_main(["check-message", str(tmp_path / "missing")])[0] == 2


@needs_git
def test_reproduce_says_when_the_trailer_is_in_the_body(repo):
    repo.write("src/toy/__init__.py", JUDGE.replace("LIMIT = 0", "LIMIT = 1"))
    sha = repo.commit("tighten\n\nFixes-Oracle: FP-1\n\nSession: ndr-fix")
    code, out = repo.reproduce(repo.base, sha)
    assert code == 1 and "in its trailer block" in out and "not the trailer block" in out, out


# ---- Layer 6 on f220469 (GPT and Grok on the gate brief) ---------------------------------------------------------
@needs_git
def test_an_oracle_deleted_after_its_fix_blocks(repo):
    """Grok: an oracle commit from another session deletes the oracle, then a No-Oracle revert brings the bug back;
    nothing ran it at the candidate."""
    _oracle(repo)
    repo.write("src/toy/__init__.py", FIXED)
    repo.commit("fix", Fixes_Oracle="FP-1", Session="fixer")
    repo.remove("tests/oracles/FP-1")
    repo.commit("retire FP-1", Oracle="FP-1", Session="someone-else")
    repo.write("src/toy/__init__.py", JUDGE)
    repo.commit("restore the old judge", No_Oracle="restore previous driver behaviour, reviewed")
    code, out = repo.reproduce(repo.base)
    assert code == 1 and "FP-1" in out and "not at the candidate" in out, out


@needs_git
def test_a_symlink_in_an_oracle_folder_blocks(repo):
    """Grok: a conftest.py symlinked into src/ lets the fix change the oracle without touching tests/oracles/."""
    _oracle(repo)
    link = repo.path / "tests" / "oracles" / "FP-1" / "conftest.py"
    try:
        os.symlink(os.path.join("..", "..", "..", "src", "toy", "__init__.py"), link)
    except (OSError, NotImplementedError):
        pytest.skip("this machine can't make a symlink")
    repo.commit("oracle helper", Oracle="FP-1", Session="oracle-writer")
    repo.write("src/toy/__init__.py", FIXED)
    repo.commit("fix", Fixes_Oracle="FP-1", Session="fixer")
    code, out = repo.reproduce(repo.base)
    assert code == 1 and "symlink" in out, out


@needs_git
@pytest.mark.parametrize("gate_file", ["scripts/gate_records.py", "scripts/labrun.py", "scripts/surfaces_agree.py"])
def test_every_gate_script_is_a_flip_once_the_base_has_the_gate(repo, gate_file):
    """GPT: GATE_FILES left out the records, labrun and surfaces scripts, so a change there needed no review."""
    repo.write("scripts/fastfix_gate.py", "# the judge\n")
    repo.write(gate_file, "# part of the gate\n")
    base = repo.commit("gate lands")
    repo.write(gate_file, "# part of the gate, made lenient\n")
    repo.commit("tweak")
    code, out = repo.loosening(base)
    assert code == 1 and re.search(rf"gate :: {re.escape(gate_file)}@([0-9a-f]{{12}}|deleted): FAIL -> PASS", out), out


@needs_git
def test_a_guard_the_base_skips_but_the_candidate_fails_blocks(tmp_path):
    """Grok: a must-not-pass fixture skipped at the base and failing at the candidate was dropped from the compare.
    A failing guard at the candidate is the tool accepting the input, whatever the base could run."""
    r = Repo(tmp_path / "r")
    r.write("src/toy/__init__.py", JUDGE)
    r.write("tests/test_redteam.py", REDTEAM + textwrap.dedent('''

        def test_refuses_the_new_input():
            import pytest
            import toy
            if not hasattr(toy, "accepts_new"):
                pytest.skip("this machine's toy has no new input yet")
            assert not toy.accepts_new()
        '''))
    r.write("data/bad.yml", "bad: [-5]\n")
    r.write("tests/redteam/README.md", "")
    r.write("corpus/results/results.json", BASE_RESULTS)
    base = r.commit("base")
    r.write("src/toy/__init__.py", JUDGE + "\n\ndef accepts_new():\n    return True\n")
    r.commit("new input, accepted")
    code, out = r.loosening(base)
    assert code == 1 and "test_refuses_the_new_input" in out, out


# ------------------------------------------------------------------------------------------------ dominance, new reads

FAKES = (Path(__file__).resolve().parent / "fakes.py").read_text(encoding="utf-8")
DRIVERS = textwrap.dedent('''\
    class FrrDriver:
        def __init__(self, lab):
            self.lab = lab

        def session(self):
            return self.lab.exec("r1", ["vtysh", "-c", "show bgp summary"])
    ''')
DRIVER_TESTS = textwrap.dedent('''\
    import pytest

    from fakes import UnexpectedCommand, seen
    from toy.drivers import FrrDriver


    class Lab:
        def __init__(self, rules):
            self.rules = rules

        def exec(self, node, cmd):
            line = " ".join(cmd)
            seen(line)
            for needle, out in self.rules:
                if needle in line:
                    return out
            raise UnexpectedCommand(line)


    @pytest.mark.parametrize("driver", [FrrDriver], ids=["FrrDriver"])
    def test_down_session_is_refused(driver):
        assert driver(Lab([("show bgp summary", "down")])).session() == "down"


    def test_session_read_is_refused():
        assert FrrDriver(Lab([("show bgp summary", "down")])).session() == "down"


    def test_loose_fake_answers_anything_bgp():
        assert FrrDriver(Lab([("show bgp", "down")])).session() == "down"
    ''')
NEW_READ_DRIVER = DRIVERS.replace('        return self.lab.exec("r1", ["vtysh", "-c", "show bgp summary"])',
                                  '        self.lab.exec("r1", ["vtysh", "-c", "show bgp neighbors"])\n'
                                  '        return self.lab.exec("r1", ["vtysh", "-c", "show bgp summary"])')


@pytest.fixture
def drepo(tmp_path) -> Repo:
    """The toy verifier with a driver, a shared fake lab (tests/fakes.py, as the product has it) and driver tests in
    the red team."""
    r = Repo(tmp_path / "r")
    r.write("pyproject.toml", '[tool.pytest.ini_options]\ntestpaths = ["tests"]\n')
    r.write("src/toy/__init__.py", JUDGE)
    r.write("src/toy/drivers.py", DRIVERS)
    r.write("tests/conftest.py", "")
    r.write("tests/fakes.py", FAKES)
    r.write("tests/test_redteam.py", REDTEAM + "\n\n" + DRIVER_TESTS)
    r.write("tests/test_pinned.py", PINNED)
    r.write("tests/redteam/RT-0001-zero.yml", RT_PINNED)
    r.write("data/bad.yml", "bad: [-5, -2]\n")
    r.write("corpus/results/results.json", BASE_RESULTS)
    r.base = r.commit("base")
    return r


def dominance(r: Repo, base: str, tmp: Path, *extra: str) -> tuple[int, str, dict | None]:
    out = tmp / "dominance.json"
    out.unlink(missing_ok=True)
    code, text = run_main(["loosening", "--repo", str(r.path), "--base", base, "--json", str(out), *extra])
    return code, text, json.loads(out.read_text(encoding="utf-8")) if out.is_file() else None


@needs_git
def test_dominance_corpus_flip_since_the_tag_blocks_and_is_in_the_json(repo, tmp_path):
    repo.git("tag", "v1.0.0", repo.base)
    repo.write("README.md", "docs\n")
    repo.commit("docs")
    repo.write("corpus/results/results.json", results(c1="safe", c2="safe", c3="error", c4=["unsafe", "safe", "unsafe"]))
    repo.commit("c1 passes now")
    code, out, data = dominance(repo, "v1.0.0", tmp_path, "--dominance")
    assert code == 1 and ":: c1: FAIL -> PASS" in out, out
    assert data["base"] == repo.base and data["candidate"] == repo.git("rev-parse", "HEAD")
    assert data["compared"] == {"corpus": 4, "fixtures": 3}
    assert [(f["case"], f["kind"], f["allowed_by"]) for f in data["flips"]] == [("c1", "verdict", None)]


@needs_git
def test_new_read_refused_by_a_fake_names_its_driver_or_every_driver(drepo, tmp_path):
    drepo.write("src/toy/drivers.py", NEW_READ_DRIVER)
    drepo.commit("read the neighbors too")
    code, out, data = dominance(drepo, drepo.base, tmp_path)
    assert code == 1, out
    kinds = {f["case"]: (f["kind"], f["drivers"]) for f in data["flips"]}
    assert kinds["tests.test_redteam::test_down_session_is_refused[FrrDriver]"] == ("new-read", ["frr"])
    # a node id that names no driver: every driver's live run
    assert kinds["tests.test_redteam::test_session_read_is_refused"] == ("new-read", ["*"])
    assert "new-read on frr" in out


@needs_git
def test_a_new_read_a_loose_fake_answers_is_found_by_the_command_log(drepo, tmp_path):
    """A fake that matches by substring answers the new command and the test still holds: only the command log
    shows the read is new."""
    drepo.write("src/toy/drivers.py", NEW_READ_DRIVER)
    drepo.commit("read the neighbors too")
    code, out, data = dominance(drepo, drepo.base, tmp_path)
    flips = {f["case"]: f for f in data["flips"]}
    loose = flips["tests.test_redteam::test_loose_fake_answers_anything_bgp"]
    assert code == 1 and (loose["kind"], loose["from"], loose["to"]) == ("new-read", "FAIL", "PASS"), out
    assert "show bgp neighbors" in out


@needs_git
def test_code_that_turns_the_command_log_off_blocks(drepo, tmp_path):
    drepo.write("src/toy/__init__.py", JUDGE + "\nimport os\nos.environ.pop('NDR_FAKE_COMMAND_LOG', None)\n")
    drepo.commit("tidy the environment", No_Oracle="environment tidy, nothing on a verdict path")
    code, out, _ = dominance(drepo, drepo.base, tmp_path)
    assert code == 1 and "turned the log off" in out, out


def _allow_new_read(r: Repo, kind: str | None = "new-read", reviewer: str = "reviewer-2", session: str = "allower",
                    review: str | None = "record"):
    r.write("src/toy/drivers.py", NEW_READ_DRIVER)
    r.write("tests/test_redteam.py", REDTEAM + "\n\n" + DRIVER_TESTS.replace(
        '[("show bgp summary", "down")]', '[("show bgp neighbors", "x"), ("show bgp summary", "down")]'))
    r.commit("read the neighbors too, and answer them in the fakes", Session="fixer",
             No_Oracle="new read, verdict unchanged, see the updated fixtures")
    cases = ["tests.test_redteam::test_down_session_is_refused[FrrDriver]",
             "tests.test_redteam::test_session_read_is_refused", "tests.test_redteam::test_loose_fake_answers_anything_bgp"]
    entries = "".join(textwrap.dedent(f"""\
          - source: fixtures
            case: "{c}"
            from: FAIL
            to: PASS
            evidence: [tests/test_redteam.py]
            why: The driver now also reads the neighbor table; the fake answers it in the updated test.
            reviewed_by: "{reviewer}: the updated test asserts the same refusal of the down session"
        """) + (f"  kind: {kind}\n" if kind else "") for c in cases)
    r.write("fastfix/allow/new-read.yml", "flips:\n" + entries)
    r.commit("allow the new read", Session=session)
    if review:      # the reviewer's own commit: its record, and (red) more than its record
        r.write("fastfix/reviews/new-read.md", "the neighbor read is answered and the refusal still holds\n")
        if review == "and-code":
            r.write("tests/test_pinned.py", PINNED + "\n")
        r.commit("review the new read", Session=reviewer)


@needs_git
def test_a_reviewed_new_read_is_allowed_and_stays_in_the_json(drepo, tmp_path):
    _allow_new_read(drepo)
    code, out, data = dominance(drepo, drepo.base, tmp_path)
    assert code == 0, out
    reads = [f for f in data["flips"] if f["kind"] == "new-read"]
    assert len(reads) == 3 and all(f["allowed_by"] == "fastfix/allow/new-read.yml" for f in reads), data["flips"]
    # every reviewed new-read entry goes to the release gate, which routes it to live, flip seen here or not
    assert sorted(e["case"] for e in data["new_read_entries"]) == sorted(f["case"] for f in reads)
    assert data["command_log_at_base"] is True and data["changed_drivers"] == []     # no product driver file


def test_changed_drivers_maps_files_to_network_oses():
    assert ffg.changed_drivers(["src/netdryrun/drivers/eos.py", "src/netdryrun/drivers/routeros_rest.py",
                                "README.md"]) == ["eos", "routeros"]
    assert ffg.changed_drivers(["src/netdryrun/drivers/base.py"]) == ["*"]
    assert ffg.changed_drivers(["docs/x.md"]) == []


@needs_git
def test_a_base_without_the_shared_fake_says_so_in_the_json(repo, tmp_path):
    repo.git("tag", "v1.0.0", repo.base)
    _flip_c1(repo)
    code, out, data = dominance(repo, "v1.0.0", tmp_path, "--dominance")
    assert data["command_log_at_base"] is False, out


@needs_git
@pytest.mark.parametrize("kind,reviewer,review,expect", [
    (None, "reviewer-2", "record", "is a new device read: its entry must say kind: new-read"),
    ("new-read", "fixer", None, "not a fresh session"),
    ("new-read", "x", None, "reviewed_by is '<session>"),
    # a reviewer is a session with a commit of its own in the change, holding only its review record
    ("new-read", "reviewer-2", None, "no commit in this change carries Session: reviewer-2"),
    ("new-read", "made-up-name", None, "no commit in this change carries Session: made-up-name"),
    ("new-read", "reviewer-2", "and-code", "reviewer reviewer-2's commits in this change hold more than review"),
    ("new-read", "allower", "record", "reviewer allower also wrote the allowlist"),
])
def test_a_new_read_needs_its_own_reviewed_entry(drepo, tmp_path, kind, reviewer, review, expect):
    _allow_new_read(drepo, kind=kind, reviewer=reviewer, review=review)
    code, out, _ = dominance(drepo, drepo.base, tmp_path)
    assert code == 1 and expect in out, out


@needs_git
def test_dominance_notes_an_entry_that_matches_no_flip_since_the_tag(repo, tmp_path):
    repo.git("tag", "v1.0.0", repo.base)
    _flip_c1(repo)
    repo.write("fastfix/allow/c1.yml", ALLOW)
    repo.commit("allow c1", Session="reviewer")
    repo.write("corpus/results/results.json", BASE_RESULTS)     # c1 back to unsafe: the entry allows nothing now
    repo.commit("c1 unsafe again", Session="fixer")
    code, out, _ = dominance(repo, "v1.0.0", tmp_path, "--dominance")
    assert code == 0 and "(no effect here)" in out, out
    code, out, _ = dominance(repo, "v1.0.0", tmp_path)
    assert code == 1 and "stale or pre-loaded" in out, out


@needs_git
def test_a_fixture_skipped_at_the_base_is_listed_with_its_origin(tmp_path):
    r = Repo(tmp_path / "r")
    r.write("src/toy/__init__.py", JUDGE)
    r.write("tests/test_redteam.py", REDTEAM + "\n\ndef test_needs_a_tool():\n    import pytest\n"
                                              "    pytest.skip('this machine lacks the tool')\n")
    r.write("data/bad.yml", "bad: [-5]\n")
    r.write("tests/redteam/README.md", "")
    r.write("corpus/results/results.json", BASE_RESULTS)
    base = r.commit("base with an environment skip")
    r.write("README.md", "x")
    r.commit("docs")
    code, out, data = dominance(r, base, tmp_path)
    assert code == 0, out
    assert data["skipped_at_base"] == [{"case": "tests.test_redteam::test_needs_a_tool", "target": "tests/test_redteam.py",
                                        "origin": "redteam", "reason": "this machine lacks the tool",
                                        "same_at_candidate": True}]


@pytest.mark.parametrize("key,drivers", [
    ("tests.test_verdict_drivers::test_x[SrlDriver]", ("srlinux",)),
    ("tests.test_verdict_drivers::test_x[RouterosDriver]", ("routeros",)),
    ("tests.test_frr_drivers_mutants_042b::test_count", ("frr",)),
    ("tests.test_nxos::test_hist", ("nxos",)),
    ("tests.test_eos_addpath_042::test_paths[SonicDriver]", ("eos", "sonic")),     # every driver it names
    ("tests.test_verdict_drivers::test_x[a::b-SrlDriver]", ("srlinux",)),
    ("tests.test_redteam::test_rt_0042", ("*",)),
    ("tests.test_verify_snapshot::test_adj", ("*",)),
])
def test_drivers_of_a_node_id(key, drivers):
    assert ffg.drivers_of(key) == drivers


@pytest.mark.parametrize("nodeid,key", [
    ("tests/test_x.py::test_y", "tests.test_x::test_y"),
    ("tests/test_x.py::TestC::test_y[p]", "tests.test_x.TestC::test_y[p]"),
    ("tests/test_x.py::test_y[a::b]", "tests.test_x::test_y[a::b]"),            # "::" inside a parameter id
    ("tests/test_x.py::TestC::test_y[a::b-c[d]]", "tests.test_x.TestC::test_y[a::b-c[d]]"),
    ("tests/oracles/FP-1/test_oracle_fp_1.py::t", "tests.oracles.FP-1.test_oracle_fp_1::t"),
])
def test_junit_key_matches_junit_names(nodeid, key):
    assert ffg.junit_key(nodeid) == key


@pytest.mark.parametrize("msg,hit", [
    ("fakes.UnexpectedCommand: unexpected command: show bgp", True),
    ("AssertionError: unexpected command: show bgp", True),
    ("unexpected command: show bgp", True),
    ("unexpected command 'show bgp'", True),
    ("RuntimeError: unexpected command 'show bgp'", True),
    ("unexpected commander", False),
    ("assert 'up' == 'down'", False),
    ("KeyError: 'unexpected command: x'", False),     # not the shared refusal (the driver-exception rule covers it)
])
def test_unexpected_command_message(msg, hit):
    assert bool(ffg.UNEXPECTED.match(msg)) is hit


# ------------------------------------------------------------------------------------------------ living plants

JUDGE_P = "LIMIT = 0\n\n\ndef judge(x):\n    return x > LIMIT\n\n\ndef helper():\n    return None\n"
FIXED_P = JUDGE_P.replace("x > LIMIT", "x > LIMIT and x != 7")
ORACLE_PLANT = ORACLE_YML + "plant: plant.diff\n"


def _fixed(r: Repo, judge: str = FIXED_P) -> str:
    """The toy with room after judge(), its FP-1 oracle, and the fix. Returns the fix's sha."""
    r.write("src/toy/__init__.py", JUDGE_P)
    r.commit("room to grow", No_Oracle="layout only, judge() is unchanged")
    _oracle(r)
    r.write("src/toy/__init__.py", judge)
    return r.commit("fix FP-1", Fixes_Oracle="FP-1", Session="fixer")


def _reverse(r: Repo, fix: str) -> str:
    return r.git("diff", fix, f"{fix}^", "--", "src", "action.yml", "templates") + "\n"


def _plant(r: Repo, text: str, meta: str = ORACLE_PLANT, session: str = "planter") -> str:
    r.write("tests/oracles/FP-1/ORACLE.yml", meta)
    r.write("tests/oracles/FP-1/plant.diff", text)
    return r.commit("plant FP-1", Oracle="FP-1", Session=session)


def plants(r: Repo, tmp: Path, base: str | None = None) -> tuple[int, str, dict | None]:
    out = tmp / "plants.json"
    out.unlink(missing_ok=True)
    code, text = run_main(["plants", "--repo", str(r.path), "--candidate", "HEAD", "--json", str(out),
                           *(["--base", base] if base else [])])
    return code, text, json.loads(out.read_text(encoding="utf-8")) if out.is_file() else None


@needs_git
def test_a_living_plant_is_caught(repo, tmp_path):
    fix = _fixed(repo)
    _plant(repo, _reverse(repo, fix))
    code, out, data = plants(repo, tmp_path, repo.base)
    assert code == 0, out
    assert (data["caught"], data["applied"], data["total"], data["not_applicable"]) == (1, 1, 1, [])
    code, out = repo.reproduce(repo.base)
    assert code == 0 and "the plant is the fix's exact reverse" in out, out


@needs_git
def test_a_plant_that_no_longer_applies_blocks(repo, tmp_path):
    fix = _fixed(repo)
    _plant(repo, _reverse(repo, fix))
    repo.write("src/toy/__init__.py", FIXED_P.replace("x > LIMIT and x != 7", "x > LIMIT and x not in (7,)"))
    repo.commit("rewrite the refusal", No_Oracle="same refusal, written as a set")
    code, out, _ = plants(repo, tmp_path)
    assert code == 1 and "plant FP-1 no longer applies; re-port it" in out, out


@needs_git
def test_an_oracle_that_passes_with_its_plant_blocks(repo, tmp_path):
    """Vacuous: a later change refuses 7 a second way, so putting the bug back changes nothing the oracle sees."""
    fix = _fixed(repo)
    _plant(repo, _reverse(repo, fix))
    repo.write("src/toy/__init__.py", FIXED_P + "\n\n_plain = judge\n\n\ndef judge(x):\n    return _plain(x) and x != 7\n")
    repo.commit("belt and braces", No_Oracle="a second refusal of the captured value")
    code, out, data = plants(repo, tmp_path)
    assert code == 1 and "oracle FP-1 no longer catches its bug" in out, out
    assert data["caught"] == 0 and data["oracles"] == {"FP-1": "not caught"}


@needs_git
def test_a_plant_that_breaks_an_import_blocks(repo, tmp_path):
    fix = _fixed(repo, JUDGE_P.replace("def judge(x):\n    return x > LIMIT",
                                       "def refuses(x):\n    return x == 7\n\n\ndef judge(x):\n"
                                       "    return x > LIMIT and not refuses(x)"))
    _plant(repo, _reverse(repo, fix))
    text = (repo.path / "src/toy/__init__.py").read_text(encoding="utf-8")
    repo.write("src/toy/__init__.py", text + "\n\nSEVEN = refuses(7)\n")
    repo.commit("use refuses() at import", No_Oracle="a constant, nothing on a verdict path")
    code, out, _ = plants(repo, tmp_path)
    assert code == 1 and "plant FP-1 breaks the build, not the verdict" in out, out


@needs_git
@pytest.mark.parametrize("how,expect", [
    ("weaker", "plant is not the fix's exact reverse"),
    ("ported-but-exact-applies", "exact reverse still applies"),
    ("outside-shipped", "doesn't ship"),
])
def test_a_plant_that_is_not_the_fixs_reverse_blocks(repo, tmp_path, how, expect):
    fix = _fixed(repo)
    exact = _reverse(repo, fix)
    if how == "outside-shipped":
        text = exact.replace("src/toy/__init__.py", "tests/conftest.py")
    else:   # a plant that puts back less than the fix took out: 7 stays refused through a back door
        text = exact.replace("+    return x > LIMIT", "+    return x > LIMIT and x != 8")
    _plant(repo, text, ORACLE_PLANT + (f"ported_from: {fix}\n" if how == "ported-but-exact-applies" else ""))
    code, out, _ = plants(repo, tmp_path)
    assert code == 1 and expect in out, out
    if how == "weaker":
        code, out = repo.reproduce(repo.base)
        assert code == 1 and "plant is not the fix's exact reverse" in out, out


@needs_git
def test_a_ported_plant_is_accepted_once_the_exact_reverse_stops_applying(repo, tmp_path):
    fix = _fixed(repo)
    repo.write("src/toy/__init__.py", FIXED_P.replace("x > LIMIT and x != 7", "x > LIMIT and x not in (7,)"))
    repo.commit("rewrite the refusal", No_Oracle="same refusal, written as a set")
    repo.write("src/toy/__init__.py", JUDGE_P)
    ported = repo.git("diff", "--", "src") + "\n"
    repo.git("checkout", "--", "src")
    _plant(repo, ported, ORACLE_PLANT + f"ported_from: {fix}\n")
    code, out, data = plants(repo, tmp_path)
    assert code == 0 and data["caught"] == 1, out


@needs_git
@pytest.mark.parametrize("how,expect", [
    # the plant may only bring the bug back; a line that fails on purpose would make any oracle "catch" it
    ("adds-a-raise", "is a port that adds an assert or raise its fix's reverse doesn't have"),
    ("other-file", "is a port that changes files its fix didn't (src/toy/other.py)"),
])
def test_a_port_that_does_more_than_the_reverse_blocks(repo, tmp_path, how, expect):
    fix = _fixed(repo)
    repo.write("src/toy/__init__.py", FIXED_P.replace("x > LIMIT and x != 7", "x > LIMIT and x not in (7,)"))
    repo.commit("rewrite the refusal", No_Oracle="same refusal, written as a set")
    repo.write("src/toy/__init__.py", JUDGE_P)
    if how == "other-file":
        repo.write("src/toy/other.py", "X = 1\n")
        repo.git("add", "-N", "src/toy/other.py")
    ported = repo.git("diff", "--", "src") + "\n"
    if how == "other-file":
        repo.git("rm", "-q", "--cached", "src/toy/other.py")
        (repo.path / "src/toy/other.py").unlink()
    repo.git("checkout", "--", "src")
    if how == "adds-a-raise":
        ported = ported.replace("+    return x > LIMIT\n",
                                "+    return x > LIMIT if x != 7 else (_ for _ in ()).throw(AssertionError)\n")
    _plant(repo, ported, ORACLE_PLANT + f"ported_from: {fix}\n")
    code, out, _ = plants(repo, tmp_path)
    assert code == 1 and expect in out, out
    # the fix is in this change too: the reproduce check holds its port to the same rules
    code, out = repo.reproduce(repo.base)
    assert code == 1 and f"Fixes-Oracle: FP-1: plant.diff {expect}" in out, out


@needs_git
def test_a_plant_caught_outside_the_oracles_own_folder_blocks(repo, tmp_path):
    """The assertion that fails sits in shipped code (or a shared helper), not in tests/oracles/FP-1/: the oracle
    itself would not see the bug."""
    with_check = JUDGE_P + "\n\ndef refused(x):\n    assert not judge(x)\n"
    repo.write("src/toy/__init__.py", with_check)
    repo.commit("room to grow", No_Oracle="layout only, judge() is unchanged")
    _oracle(repo, test=ORACLE_TEST.replace("from toy import judge", "from toy import refused")
            .replace("assert not judge(int(CAPTURE.read_text()))", "refused(int(CAPTURE.read_text()))"))
    repo.write("src/toy/__init__.py", with_check.replace("x > LIMIT", "x > LIMIT and x != 7"))
    fix = repo.commit("fix FP-1", Fixes_Oracle="FP-1", Session="fixer")
    _plant(repo, _reverse(repo, fix))
    code, out, data = plants(repo, tmp_path)
    assert code == 1 and "not by an assertion raised in tests/oracles/FP-1/" in out, out
    assert data["caught"] == 0 and data["oracles"] == {"FP-1": "caught elsewhere"}


ORACLE_FAKE_TEST = textwrap.dedent('''\
    from toy import probe


    class Lab:
        def exec(self, cmd):
            if cmd != "show ok":
                raise AssertionError("unexpected " f"command {cmd!r}")   # as a frozen oracle's fake words it
            return "7"


    def test_probe_reads_the_right_table():
        assert probe(Lab()) == "7"
    ''')


@needs_git
def test_a_plant_caught_only_by_a_fakes_refusal_in_the_oracles_folder_blocks(repo, tmp_path):
    """The plant changes only the command sent. The oracle folder's own fake refuses it, raising inside
    tests/oracles/FP-1/, so only the refusal wording tells it apart from the oracle's assertion."""
    probe = JUDGE_P + '\n\ndef probe(lab):\n    return lab.exec("show bad")\n'
    repo.write("src/toy/__init__.py", probe)
    repo.commit("room to grow", No_Oracle="layout only, judge() is unchanged")
    _oracle(repo, test=ORACLE_FAKE_TEST)
    repo.write("src/toy/__init__.py", probe.replace("show bad", "show ok"))
    fix = repo.commit("fix FP-1", Fixes_Oracle="FP-1", Session="fixer")
    _plant(repo, _reverse(repo, fix))
    code, out, data = plants(repo, tmp_path)
    assert code == 1 and "not by an assertion raised in tests/oracles/FP-1/" in out, out
    assert data["caught"] == 0 and data["oracles"] == {"FP-1": "caught elsewhere"}


@needs_git
@pytest.mark.parametrize("evidence", ["../outside.txt", "/etc/hostname", "C:/x.txt"])
def test_a_plant_whose_evidence_leaves_the_repository_fails_closed(repo, tmp_path, evidence):
    fix = _fixed(repo)
    base = repo.git("rev-parse", "HEAD")
    _plant(repo, _reverse(repo, fix), ORACLE_PLANT.replace("tests/fixtures/fp1.txt", evidence))
    code, out, _ = plants(repo, tmp_path, base)
    assert code == 2 and "is not a path inside the repository" in out, out


@needs_git
def test_a_plant_swapped_while_the_old_one_still_applies_blocks(repo, tmp_path):
    fix = _fixed(repo)
    _plant(repo, _reverse(repo, fix))
    base = repo.git("rev-parse", "HEAD")
    # an easier plant: it also deletes helper(), which the oracle never looks at
    easier = _reverse(repo, fix).rstrip("\n") + "\n"
    _plant(repo, easier.replace("-    return x > LIMIT and x != 7", "-    return x > LIMIT and x != 7 "),
           session="planter-2")
    code, out, _ = plants(repo, tmp_path, base)
    assert code == 1 and "plant FP-1 swapped while the old one still applies" in out, out


@needs_git
def test_a_re_port_from_the_session_that_broke_the_plant_blocks(repo, tmp_path):
    fix = _fixed(repo)
    _plant(repo, _reverse(repo, fix))
    base = repo.git("rev-parse", "HEAD")
    repo.write("src/toy/__init__.py", FIXED_P.replace("x > LIMIT and x != 7", "x > LIMIT and x not in (7,)"))
    repo.commit("rewrite the refusal", No_Oracle="same refusal, written as a set", Session="refactorer")
    repo.write("src/toy/__init__.py", JUDGE_P)
    ported = repo.git("diff", "--", "src") + "\n"
    repo.git("checkout", "--", "src")
    _plant(repo, ported, ORACLE_PLANT + f"ported_from: {fix}\n", session="refactorer")
    code, out, _ = plants(repo, tmp_path, base)
    assert code == 1 and "re-ports it from a session that changed shipped code" in out, out


@needs_git
def test_plant_none_is_only_for_fixes_older_than_the_rule(repo, tmp_path):
    none = ORACLE_YML + "plant: none\nplant_why: fixed before plants existed; its fix was refactored away since then\n"
    _fixed(repo)
    repo.write("tests/oracles/FP-1/ORACLE.yml", none)
    repo.commit("FP-1 predates plants", Oracle="FP-1", Session="planter")     # this commit brings the rule
    code, out, data = plants(repo, tmp_path)
    assert code == 0 and data["not_applicable"] == ["FP-1"] and data["owed_ports"] == 1, out
    # a new oracle fixed after the rule can't say none
    repo.write("tests/fixtures/fp2.txt", "8\n")
    repo.write("tests/oracles/FP-2/ORACLE.yml", none.replace("FP-1", "FP-2").replace("fp1", "fp2"))
    repo.write("tests/oracles/FP-2/test_oracle_fp_2.py", ORACLE_TEST.replace("fp1", "fp2"))
    repo.commit("oracle FP-2", Oracle="FP-2", Session="oracle-writer")
    code, out, _ = plants(repo, tmp_path)
    assert code == 1 and "oracle FP-2: plant: none on an oracle with no fix yet" in out, out
    repo.write("src/toy/__init__.py", FIXED_P.replace("x != 7", "x not in (7, 8)"))
    repo.commit("fix FP-2", Fixes_Oracle="FP-2", Session="fixer-2")
    code, out, _ = plants(repo, tmp_path)
    assert code == 1 and "oracle FP-2: plant: none is only for oracles fixed before plants were required" in out, out


@needs_git
def test_a_new_oracle_without_a_fix_needs_no_plant_yet(repo, tmp_path):
    fix = _fixed(repo)
    _plant(repo, _reverse(repo, fix))
    repo.write("tests/fixtures/fp2.txt", "8\n")
    repo.write("tests/oracles/FP-2/ORACLE.yml", ORACLE_YML.replace("FP-1", "FP-2").replace("fp1", "fp2"))
    repo.write("tests/oracles/FP-2/test_oracle_fp_2.py", ORACLE_TEST.replace("fp1", "fp2"))
    repo.commit("oracle FP-2", Oracle="FP-2", Session="oracle-writer")
    before = repo.git("rev-parse", "HEAD~1")
    code, out, data = plants(repo, tmp_path, before)
    assert code == 0 and data["pending"] == ["FP-2"] and data["pending_since_base"] == [], out
    # still waiting for its fix at the next release: the release gate counts it (a MAJOR there)
    repo.write("README.md", "later\n")
    repo.commit("docs")
    code, out, data = plants(repo, tmp_path, repo.git("rev-parse", "HEAD~1"))
    assert code == 0 and data["pending_since_base"] == ["FP-2"], out
    # once fixed, it needs its plant
    repo.write("src/toy/__init__.py", FIXED_P.replace("x != 7", "x not in (7, 8)"))
    repo.commit("fix FP-2", Fixes_Oracle="FP-2", Session="fixer-2")
    code, out, _ = plants(repo, tmp_path)
    assert code == 1 and "oracle FP-2 is fixed" in out and "names no plant" in out, out


@needs_git
def test_a_symlinked_plant_blocks(repo, tmp_path):
    fix = _fixed(repo)
    repo.write("plants/fp1.diff", _reverse(repo, fix))
    repo.write("tests/oracles/FP-1/ORACLE.yml", ORACLE_PLANT)
    try:
        os.symlink(os.path.join("..", "..", "..", "plants", "fp1.diff"), repo.path / "tests/oracles/FP-1/plant.diff")
    except (OSError, NotImplementedError):
        pytest.skip("this machine can't make a symlink")
    repo.commit("plant FP-1 by link", Oracle="FP-1", Session="planter")
    code, out, _ = plants(repo, tmp_path)
    assert code == 1 and "symlink" in out, out


def test_plants_without_git_fail_closed(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(ffg.shutil, "which", lambda name: None)
    assert ffg.main(["plants", "--repo", str(tmp_path)]) == 2
    assert "git is not available" in capsys.readouterr().out


def test_normalise_diff_ignores_index_lines_and_line_ends():
    a = "diff --git a/src/x.py b/src/x.py\nindex 1234567..89abcde 100644\n--- a/src/x.py\n+++ b/src/x.py\n"
    b = a.replace("index 1234567..89abcde", "index 1234567890ab..89abcdef0123").replace("\n", "\r\n")
    assert ffg.normalise_diff(a) == ffg.normalise_diff(b)
