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
@pytest.mark.parametrize("plant", ["src/json/__init__.py", "src/tempfile/__init__.py", "src/toy_extra/__init__.py"])
def test_the_gate_runs_no_package_but_the_products_from_the_code_under_test(repo, plant):
    """A package beside the product's (src/json, src/tempfile) would shadow the standard library inside the judged
    run, the fake labs' log writer included: the code under test would judge itself."""
    repo.write("src/toy/__init__.py", JUDGE.replace("LIMIT = 0", "LIMIT = -10"))
    repo.write(plant, "def dumps(*a, **k):\n    return ''\n")
    repo.commit("loosen and plant a package")
    code, out = repo.loosening(repo.base)
    assert code == ffg.ERROR and f"{plant.split('/')[1]} is not one of the packages under judgement" in out, out


@pytest.mark.parametrize("plant", ["json.py", "tempfile", "pytest.py"])
def test_a_tree_whose_src_shadows_the_standard_library_is_refused(tmp_path, plant):
    (tmp_path / "src" / "toy").mkdir(parents=True)
    (tmp_path / "src" / "toy" / "__init__.py").write_text("", encoding="utf-8")
    (tmp_path / "src" / plant).mkdir() if "." not in plant else (tmp_path / "src" / plant).write_text("")
    with pytest.raises(ffg.GateError, match=f"src/{plant.split('.')[0]} would shadow"):
        ffg.preflight(tmp_path, sys.executable)


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


def _run(**outcomes: str) -> "ffg.PytestRun":
    return ffg.PytestRun(1 if any(o in ("failed", "error") for o in outcomes.values()) else 0, outcomes,
                         {k: f"{o} here" for k, o in outcomes.items() if o != "passed"}, "")


@pytest.mark.parametrize("at_candidate", ["failed", "error"])
def test_a_guard_skipped_at_the_base_that_fails_at_the_candidate_is_a_problem(at_candidate):
    """Layer 6 (f220469): the base could not show the guard holds, and the candidate's code makes it fail. That is
    a block with no allowlist path, so a guard must never skip to mean "known and accepted" (WRONG_REASON did, and
    every fix of its cases became unmergeable)."""
    report = ffg.Report()
    ffg.fixture_compare(_run(**{"t::guard": "skipped", "t::other": "passed"}),
                        _run(**{"t::guard": at_candidate, "t::other": "passed"}), report)
    assert any(p.startswith(f"fixtures :: t::guard: skipped at the base, {at_candidate} at the candidate")
               for p in report.problems), report.problems
    assert not report.flips, report.flips


@pytest.mark.parametrize("at_candidate", ["failed", "error", "skipped"])
def test_a_guard_that_passed_at_the_base_and_not_at_the_candidate_is_a_loosening_flip(at_candidate):
    """The shape a known-wrong-reason guard has now: it passes at the base, and a fix that changes the case's ending
    makes it fail at the candidate. That is a FAIL -> PASS flip (blocked until a reviewed allowlist entry clears it),
    never accepted silently and never the skipped-at-base problem."""
    report = ffg.Report()
    ffg.fixture_compare(_run(**{"t::guard": "passed", "t::other": "passed"}),
                        _run(**{"t::guard": at_candidate, "t::other": "passed"}), report)
    assert [(f.source, f.case, f.before, f.after) for f in report.flips] == [("fixtures", "t::guard", "FAIL", "PASS")]
    assert not report.problems, report.problems


KNOWN_REASON_SRC = 'def reason(x):\n    return "error: no pathCount"\n'
KNOWN_REASON_TEST = textwrap.dedent("""


    def test_known_wrong_reason():
        import pytest

        from toy.why import reason
        if reason(1).startswith("error:") and "no pathCount" in reason(1):
            {accept}
        pytest.fail("no longer ends in its known wrong-reason error: move it to REFUSALS")
    """)


@needs_git
@pytest.mark.parametrize("accept,expect", [
    ("return", "test_known_wrong_reason: FAIL -> PASS"),
    ("pytest.skip('known wrong reason')", "test_known_wrong_reason: skipped at the base, failed at the candidate"),
])
def test_a_fix_of_a_known_wrong_reason_case_is_a_flip_only_when_the_guard_passes_at_the_base(repo, accept, expect):
    """The WRONG_REASON mechanism through the gate's base-vs-candidate comparison: a fix that makes the case end in
    its real refusal is an ordinary flip when the base's guard passed, and a block with no allowlist path when it
    skipped (EOS b230514)."""
    repo.write("src/toy/why.py", KNOWN_REASON_SRC)
    repo.write("tests/test_redteam.py", REDTEAM + KNOWN_REASON_TEST.format(accept=accept))
    base = repo.commit("a known wrong reason")
    repo.write("src/toy/why.py", KNOWN_REASON_SRC.replace("no pathCount", "the community refusal"))
    repo.write("tests/test_redteam.py", REDTEAM)
    repo.commit("the case ends in its refusal", Session="fixer", No_Oracle="the case now ends in its refusal")
    code, out = repo.loosening(base)
    assert code == 1 and expect in out, out
    if accept != "return":
        return
    repo.write("fastfix/allow/known.yml", textwrap.dedent("""\
        flips:
          - source: fixtures
            case: "tests.test_redteam::test_known_wrong_reason"
            from: FAIL
            to: PASS
            evidence: [tests/test_redteam.py]
            why: The case now ends in its real refusal; the updated red-team test takes it out of the known list.
            reviewed_by: coordinator
        """))
    repo.commit("allow", Session="reviewer")
    code, out = repo.loosening(base)
    assert code == 0, out


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


# the command log is compared run against run. tests/fakes.py (log format 2) names the temporary paths a test made
# itself; an older base's fakes logged them as they were, and for those rows only the product's own scratch directory
# names are read as run names. What only differs by run (those names, the trees' own paths, key order) is no new read;
# a new call is one, temp path or not, and so is any other path under /tmp

def _log(path: Path, rows: list[tuple[str, object]], fmt: int | None = None) -> Path:
    path.write_text("".join(json.dumps({"test": t, "command": c if isinstance(c, str) else json.dumps(c),
                                        **({"log": fmt} if fmt is not None else {})}) + "\n"
                            for t, c in rows), encoding="utf-8")
    return path


CASE = "tests.test_x::test_deploy"
TEST = "tests/test_x.py::test_deploy"
ROOTS = ("/tmp/ndr-fastfix-k2j3h4l5/base", "/tmp/ndr-fastfix-k2j3h4l5/mixed")


def _deploy(topology: str, env_order: list[tuple[str, str]], root: str) -> dict:
    return {"call": "<lambda>", "args": {"cmd": ["containerlab", "deploy", "-t", topology],
                                         "kw": {"env": dict(env_order), "cwd": f"{root}/tests"}}}


def _new_reads(tmp_path, base_rows, cand_rows, roots=ROOTS, fmt=None):
    report = ffg.Report()
    base = ffg.read_commands(_log(tmp_path / "b.jsonl", base_rows, fmt), roots)
    cand = ffg.read_commands(_log(tmp_path / "c.jsonl", cand_rows, fmt), roots)
    ffg.new_reads(report, 0, ffg.PytestRun(0, {}, {}, ""), {CASE: "FAIL"}, base, cand)
    return report.flips


ENV = [("HOME", "/home/u"), ("PATH", "/usr/bin"), ("_", "/usr/bin/env")]


def test_an_older_logs_scratch_directory_the_trees_paths_and_key_order_are_no_new_read(tmp_path):
    base = [(TEST, _deploy("/tmp/netdryrun-verify-61i7icgq/after/t.clab.yml", ENV, ROOTS[0])),
            (TEST, "cat /tmp/pytest-of-ndr/<tmp>/test_deploy0/t.yml")]
    cand = [(TEST, _deploy("/tmp/netdryrun-verify-f0bwtp86/after/t.clab.yml", ENV[::-1], ROOTS[1])),
            (TEST, "cat /tmp/pytest-of-ndr/<tmp>/test_deploy0/t.yml")]
    assert _new_reads(tmp_path, base, cand) == []


@pytest.mark.parametrize("extra", [
    # a new call whose argument is a scratch directory of the product's
    {"call": "exec", "args": {"cmd": ["cat", "/tmp/netdryrun-verify-zzzzzzzz/secret"]}},
    # the same scratch directory, another file in it
    {"call": "exec", "args": {"cmd": ["cat", "/tmp/netdryrun-verify-f0bwtp86/secret"]}},
    "cat /tmp/pytest-of-ndr/<tmp>/test_deploy0/other.yml",
    # the same call with another file under the temporary directory
    _deploy("/tmp/netdryrun-verify-f0bwtp86/before/t.clab.yml", ENV, ROOTS[1]),
    # the same call with another environment value
    _deploy("/tmp/netdryrun-verify-f0bwtp86/after/t.clab.yml", ENV[:2] + [("_", "/bin/sh")], ROOTS[1]),
    # fixed device files and paths that only contain tmp (the reviewer's shapes)
    "vtysh -f /tmp/frr.conf", "cat /tmp/ndr-secret.cfg", "cat /var/tmp/shadow", "cat /home/u/tmp/id_rsa",
    "copy scp://h/tmp/evil.cfg running-config", "show vrf tmp_customer_b", "show interface tmpbr000002",
    # a scratch directory's name not followed by a path in it, or not under the temp directory
    "rm -rf /tmp/netdryrun-verify-zzzzzzzz", "cat /var/tmp/netdryrun-verify-zzzzzzzz/x",
])
@pytest.mark.parametrize("fmt", [None, ffg.LOG_FORMAT])
def test_a_new_command_next_to_a_temp_path_is_still_a_new_read(tmp_path, extra, fmt):
    base = [(TEST, _deploy("/tmp/netdryrun-verify-61i7icgq/after/t.clab.yml", ENV, ROOTS[0])),
            (TEST, "vtysh -f /tmp/netdryrun-inject.conf"), (TEST, "show interface tmpbr000001")]
    cand = [(TEST, _deploy("/tmp/netdryrun-verify-61i7icgq/after/t.clab.yml" if fmt else
                           "/tmp/netdryrun-verify-f0bwtp86/after/t.clab.yml", ENV, ROOTS[1])),
            (TEST, "vtysh -f /tmp/netdryrun-inject.conf"), (TEST, "show interface tmpbr000001"), (TEST, extra)]
    flips = _new_reads(tmp_path, base, cand, fmt=fmt)
    assert [(f.case, f.kind) for f in flips] == [(CASE, ffg.NEW_READ)], flips


def test_two_scratch_directories_never_read_as_one(tmp_path):
    """An older log: the base uses one scratch directory twice, the candidate two of the same shape."""
    base = [(TEST, "clab deploy -t /tmp/netdryrun-verify-61i7icgq/t.yml"),
            (TEST, "clab destroy -t /tmp/netdryrun-verify-61i7icgq/t.yml")]
    cand = [(TEST, "clab deploy -t /tmp/netdryrun-verify-f0bwtp86/t.yml"),
            (TEST, "clab destroy -t /tmp/netdryrun-verify-zzzzzzzz/t.yml")]
    assert [f.kind for f in _new_reads(tmp_path, base, cand)] == [ffg.NEW_READ]
    same = [(TEST, "clab deploy -t /tmp/netdryrun-verify-f0bwtp86/t.yml"),
            (TEST, "clab destroy -t /tmp/netdryrun-verify-f0bwtp86/t.yml")]
    assert _new_reads(tmp_path, base, same) == []


def test_a_new_log_is_read_without_guessing_run_names(tmp_path):
    """tests/fakes.py from log format 2 already named the temporary paths the test made: a path it left as it is was
    not one of them, so another name there is a new read."""
    base = [(TEST, "clab deploy -t /tmp/netdryrun-verify-61i7icgq/t.yml"), (TEST, "cat <tmp1>/t.yml")]
    cand = [(TEST, "clab deploy -t /tmp/netdryrun-verify-f0bwtp86/t.yml"), (TEST, "cat <tmp1>/t.yml")]
    assert [f.kind for f in _new_reads(tmp_path, base, cand, fmt=ffg.LOG_FORMAT)] == [ffg.NEW_READ]
    assert _new_reads(tmp_path, base[1:], cand[1:], fmt=ffg.LOG_FORMAT) == []


def test_stable_command_keeps_what_isnt_a_run_name():
    sc = ffg.stable_command
    assert sc("show bgp summary") == "show bgp summary"
    assert sc("7") == "7" and sc("null") == "null"
    assert sc('{"b": 1, "a": "/tmp/tmpab12cd34/x"}') == '{"a": "/tmp/tmpab12cd34/x", "b": 1}'
    assert sc('{"b": 1, "a": "/tmp/netdryrun-verify-61i7icgq/x"}', legacy=True) == \
        '{"a": "/tmp/netdryrun-verify-<1>/x", "b": 1}'
    assert sc('"/tmp/netdryrun-verify-61i7icgq/x"', legacy=True) == '"/tmp/netdryrun-verify-<1>/x"'
    # each kind numbered from 1, so a directory of another kind ahead of it renumbers nothing
    assert sc("cat /tmp/netdryrun-cfg-aaaaaaaa/x /tmp/netdryrun-verify-61i7icgq/x", legacy=True) == \
        "cat /tmp/netdryrun-cfg-<1>/x /tmp/netdryrun-verify-<1>/x"
    assert sc("/tmp/netdryrun-verify-61i7icgq/x") == "/tmp/netdryrun-verify-61i7icgq/x"      # format 2: as it is
    # the trees' paths as whole path names only
    assert sc("/w/base/tests/x", ("/w/base",)) == "<root>/tests/x"
    assert sc('"/w/base/tests/x"', ("/w/base",)) == '"<root>/tests/x"'
    assert sc("/w/base2/x /x/w/base", ("/w/base",)) == "/w/base2/x /x/w/base"
    assert sc("/w/mixed/x /w/y", ("/w", "/w/mixed")) == "<root>/x <root>/y"          # the longer root first
    # dict keys are never changed, so two keys can't merge into one
    assert sc('{"/w/base/x": 1, "/tmp/netdryrun-verify-61i7icgq/y": 2}', ("/w/base",), legacy=True) == \
        '{"/tmp/netdryrun-verify-61i7icgq/y": 2, "/w/base/x": 1}'
    for kept in ("/tmp/frr.conf", "/var/tmp/netdryrun-verify-61i7icgq/x", "/tmp/netdryrun-verify-61i7icgq",
                 "x/tmp/netdryrun-verify-61i7icgq/y", "/tmp/netdryrun-verify-61i7icgqz/y", "/tmp/tmpab12cd34/x",
                 "tmp_customer_b", "/tmp/pytest-of-ndr/pytest-12/x"):
        assert sc(kept, legacy=True) == kept, kept


def test_a_legacy_scratch_directory_is_numbered_per_test(tmp_path):
    log = _log(tmp_path / "l.jsonl", [("tests/test_x.py::test_a", "cat /tmp/netdryrun-verify-61i7icgq/x"),
                                      ("tests/test_x.py::test_b", "cat /tmp/netdryrun-verify-f0bwtp86/x"),
                                      ("tests/test_x.py::test_a", "cat /tmp/netdryrun-verify-zzzzzzzz/x")])
    assert ffg.read_commands(log) == {
        "tests.test_x::test_a": {"cat /tmp/netdryrun-verify-<1>/x", "cat /tmp/netdryrun-verify-<2>/x"},
        "tests.test_x::test_b": {"cat /tmp/netdryrun-verify-<1>/x"}}


@pytest.mark.parametrize("base_rows,cand_rows", [
    # one scratch directory replaced by one of another kind (the release judge's base is an older tag)
    (["cat /tmp/netdryrun-cfg-aaaaaaaa/startup"], ["cat /tmp/netdryrun-sec-zzzzzzzz/startup"]),
    # two directories of two kinds, each now read for the other's file
    (["cat /tmp/netdryrun-a-aaaaaaaa/x", "cat /tmp/netdryrun-b-bbbbbbbb/y"],
     ["cat /tmp/netdryrun-b-cccccccc/x", "cat /tmp/netdryrun-a-dddddddd/y"]),
])
def test_an_older_logs_scratch_directory_keeps_its_kind(tmp_path, base_rows, cand_rows):
    flips = _new_reads(tmp_path, [(TEST, r) for r in base_rows], [(TEST, r) for r in cand_rows])
    assert [f.kind for f in flips] == [ffg.NEW_READ], flips


@pytest.mark.parametrize("fmt", [1, 3, "2", None])
def test_a_log_in_a_format_the_gate_doesnt_know_is_refused(tmp_path, fmt):
    """Rows with no "log" key are an older base's; any other value is neither that nor format 2."""
    path = tmp_path / "l.jsonl"
    path.write_text(json.dumps({"test": TEST, "command": "x", "log": fmt}) + "\n", encoding="utf-8")
    with pytest.raises(ffg.GateError, match="format this gate doesn't know at line 1"):
        ffg.read_commands(path)


# the reviewer's probes against the real profiler and environment record, in one gate run: a toy product package
# named netdryrun (so tests/fakes.py's profiler watches it), the suite's own autouse fixture, one red-team test per
# probe. Each probe's driver method changes from its base body to its candidate body; a probe flips as a new read
# exactly when `want` says so.
# Not here, known limits of the log itself rather than of its scrubbing: env=os.environ passed uncopied (logged by
# type), a command sent twice or in another order (each test's commands are a set), names drawn at random by the code
# (uuid, pid, set order: those flip a comment-only change, which only ever asks for more review), and code that
# rewrites the log file.
PROBES = {
    "control_new_exec": ('return self.lab.exec("r1", ["show", "version"])',
                         'self.lab.exec("r1", ["show", "bgp"])\nreturn self.lab.exec("r1", ["show", "version"])', True),
    "comment_only": ('return self.lab.exec("r1", ["show", "version"])',
                     '# comment\nreturn self.lab.exec("r1", ["show", "version"])', False),
    "env_copy_comment_only": ('return self.lab.run(["clab", "deploy"], env=dict(os.environ))',
                              '# comment\nreturn self.lab.run(["clab", "deploy"], env=dict(os.environ))', False),
    "env_global_mutation": ('return self.lab.run(["clab", "deploy"], env=dict(os.environ))',
                            'os.environ["NETDRYRUN_SKIP_LIVE"] = "1"\n'
                            'try:\n    return self.lab.run(["clab", "deploy"], env=dict(os.environ))\n'
                            'finally:\n    os.environ.pop("NETDRYRUN_SKIP_LIVE")', True),
    "env_global_pop": ('return self.lab.run(["clab", "deploy"], env=dict(os.environ))',
                       'v = os.environ.pop("NDR_PROBE_CRED")\n'
                       'try:\n    return self.lab.run(["clab", "deploy"], env=dict(os.environ))\n'
                       'finally:\n    os.environ["NDR_PROBE_CRED"] = v', True),
    "env_credential_leak": ('return self.lab.run(["clab", "deploy"], env={k: v for k, v in os.environ.items() '
                            'if k != "NDR_PROBE_CRED"})',
                            'return self.lab.run(["clab", "deploy"], env=dict(os.environ))', True),
    "env_set_inherited_value": ('return self.lab.run(["clab", "deploy"], env={**os.environ})',
                                'return self.lab.run(["clab", "deploy"], env={**os.environ, '
                                '"NDR_PROBE_CRED": os.environ["NDR_PROBE_CRED"]})', False),
    "tmp_fixed_file": ('return self.lab.exec("r1", ["cat", "/tmp/ndr-a.cfg"])',
                       'self.lab.exec("r1", ["cat", "/tmp/ndr-secret.cfg"])\n'
                       'return self.lab.exec("r1", ["cat", "/tmp/ndr-a.cfg"])', True),
    "tmp_fixed_file_str": ('return self.lab.exec("r1", "cat /tmp/startup.cfg")',
                           'self.lab.exec("r1", "rm /tmp/startup.cfg")\n'
                           'return self.lab.exec("r1", "cat /tmp/startup.cfg")', True),
    "tmp_device_path_swap": ('return self.lab.exec("r1", "bash cat /tmp/running.cfg")',
                             'self.lab.exec("r1", "bash cat /tmp/candidate.cfg")\n'
                             'return self.lab.exec("r1", "bash cat /tmp/running.cfg")', True),
    "frr_inject_new_device_file": ('return self.lab.exec("r1", ["vtysh", "-f", "/tmp/netdryrun-inject.conf"])',
                                   'self.lab.exec("r1", ["vtysh", "-f", "/tmp/frr.conf"])\n'
                                   'return self.lab.exec("r1", ["vtysh", "-f", "/tmp/netdryrun-inject.conf"])', True),
    "var_tmp": ('return self.lab.exec("r1", ["cat", "/var/tmp/a.log"])',
                'self.lab.exec("r1", ["cat", "/var/tmp/shadow"])\nreturn self.lab.exec("r1", ["cat", "/var/tmp/a.log"])',
                True),
    "home_tmp": ('return self.lab.exec("r1", ["cat", "/home/u/tmp/a.cfg"])',
                 'self.lab.exec("r1", ["cat", "/home/u/tmp/id_rsa"])\n'
                 'return self.lab.exec("r1", ["cat", "/home/u/tmp/a.cfg"])', True),
    "url_tmp": ('return self.lab.exec("r1", ["copy", "scp://h/tmp/a.cfg", "running-config"])',
                'self.lab.exec("r1", ["copy", "scp://h/tmp/evil.cfg", "running-config"])\n'
                'return self.lab.exec("r1", ["copy", "scp://h/tmp/a.cfg", "running-config"])', True),
    "vrf_name": ('return self.lab.exec("r1", ["show", "vrf", "tmp_customer_a"])',
                 'self.lab.exec("r1", ["show", "vrf", "tmp_customer_b"])\n'
                 'return self.lab.exec("r1", ["show", "vrf", "tmp_customer_a"])', True),
    "iface_name": ('return self.lab.exec("r1", ["show", "interface", "tmpbr000001"])',
                   'self.lab.exec("r1", ["shutdown", "interface", "tmpbr000002"])\n'
                   'return self.lab.exec("r1", ["show", "interface", "tmpbr000001"])', True),
    "iface_same_verb": ('return self.lab.exec("r1", ["show", "interface", "tmpbr000001"])',
                        'self.lab.exec("r1", ["show", "interface", "tmpbr000002"])\n'
                        'return self.lab.exec("r1", ["show", "interface", "tmpbr000001"])', True),
    "dict_key_collision": ('return self.lab.exec("r1", {"/tmp/a.cfg": "read"})',
                           'return self.lab.exec("r1", {"/tmp/a.cfg": "read", "/tmp/shadow": "read"})', True),
    "mkdtemp_comment_only": ('d = tempfile.mkdtemp(prefix="netdryrun-verify-")\n'
                             'return self.lab.run(["clab", "deploy", "-t", d + "/after/t.yml"], env=dict(os.environ))',
                             '# comment\nd = tempfile.mkdtemp(prefix="netdryrun-verify-")\n'
                             'return self.lab.run(["clab", "deploy", "-t", d + "/after/t.yml"], env=dict(os.environ))',
                             False),
    "mkdtemp_new_file": ('d = tempfile.mkdtemp(prefix="netdryrun-verify-")\n'
                         'return self.lab.run(["clab", "deploy", "-t", d + "/t.yml"])',
                         'd = tempfile.mkdtemp(prefix="netdryrun-verify-")\n'
                         'self.lab.run(["cat", d + "/secret"])\n'
                         'return self.lab.run(["clab", "deploy", "-t", d + "/t.yml"])', True),
    "second_mkdtemp_same_shape": ('d = tempfile.mkdtemp(prefix="v-")\n'
                                  'return self.lab.run(["clab", "deploy", "-t", d + "/t.yml"])',
                                  'd = tempfile.mkdtemp(prefix="v-")\ne = tempfile.mkdtemp(prefix="w-")\n'
                                  'self.lab.run(["clab", "destroy", "-t", e + "/t.yml"])\n'
                                  'return self.lab.run(["clab", "deploy", "-t", d + "/t.yml"])', True),
    "tempdir_comment_only": ('with tempfile.TemporaryDirectory() as d:\n'
                             '    return self.lab.run(["clab", "deploy", "-t", d + "/t.yml"])',
                             '# comment\nwith tempfile.TemporaryDirectory() as d:\n'
                             '    return self.lab.run(["clab", "deploy", "-t", d + "/t.yml"])', False),
    "tmp_path_comment_only": ('return self.lab.run(["clab", "deploy", "-t", str(tmp / "t.yml")])',
                              '# comment\nreturn self.lab.run(["clab", "deploy", "-t", str(tmp / "t.yml")])', False),
    "tmp_path_new_file": ('return self.lab.run(["clab", "deploy", "-t", str(tmp / "t.yml")])',
                          'self.lab.run(["cat", str(tmp / "secret")])\n'
                          'return self.lab.run(["clab", "deploy", "-t", str(tmp / "t.yml")])', True),
    # an environment copy cut down to a few keys is logged whole, the log's own path with it: one path for both runs
    "env_filtered_ndr_comment": ('return self.lab.run(["clab", "deploy"], env={k: v for k, v in os.environ.items() '
                                 'if k.startswith("NDR_")})',
                                 '# comment\nreturn self.lab.run(["clab", "deploy"], env={k: v for k, v in '
                                 'os.environ.items() if k.startswith("NDR_")})', False),
    # a file from the source tree while the test runs elsewhere: the gate names the trees, not the working directory
    "tree_path_cwd_elsewhere_comment": ('return self.lab.exec("r1", ["load", str(Path(__file__).resolve().parent / '
                                        '"t.j2")])',
                                        '# comment\nreturn self.lab.exec("r1", ["load", str(Path(__file__).resolve()'
                                        '.parent / "t.j2")])', False,
                                        "def test_{n}(monkeypatch, tmp_path):\n    monkeypatch.chdir(tmp_path)\n"
                                        "    assert Driver(Lab()).p_{n}(tmp_path) == \"ok\"\n"),
    # product and test temp directories are numbered apart: one more product directory made before the test's own
    # renumbers nothing, and the product's directory never reads as the test's
    "renumber_noise_extra_mkdtemp": ('u = tmp()\nreturn self.lab.exec("r1", ["vtysh", "-f", u + "/frr.conf"])',
                                     'tempfile.mkdtemp()\nu = tmp()\n'
                                     'return self.lab.exec("r1", ["vtysh", "-f", u + "/frr.conf"])', False,
                                     "def test_{n}():\n    assert Driver(Lab()).p_{n}(lambda: tempfile.mkdtemp()) "
                                     "== \"ok\"\n"),
    "renumber_hides_swap": ('u = tmp()\nreturn self.lab.exec("r1", ["vtysh", "-f", u + "/frr.conf"])',
                            's = tempfile.mkdtemp()\nu = tmp()\n'
                            'return self.lab.exec("r1", ["vtysh", "-f", s + "/frr.conf"])', True,
                            "def test_{n}():\n    assert Driver(Lab()).p_{n}(lambda: tempfile.mkdtemp()) == \"ok\"\n"),
    # makers the session wraps in the tempfile module before the product imports it
    "from_import_mkdtemp_comment": ('return self.lab.exec("r1", ["cat", mkdtemp() + "/a"])',
                                    '# comment\nreturn self.lab.exec("r1", ["cat", mkdtemp() + "/a"])', False),
    "mktemp_comment": ('return self.lab.exec("r1", ["cat", tempfile.mktemp()])',
                       '# comment\nreturn self.lab.exec("r1", ["cat", tempfile.mktemp()])', False),
    # a directory a module-scoped fixture made outside any test
    "module_fixture_mkdtemp_comment": ('return self.lab.exec("r1", ["cat", tmp + "/a.cfg"])',
                                       '# comment\nreturn self.lab.exec("r1", ["cat", tmp + "/a.cfg"])', False,
                                       "@pytest.fixture(scope=\"module\")\ndef mod_dir_{n}():\n"
                                       "    return tempfile.mkdtemp()\n\n\ndef test_{n}(mod_dir_{n}):\n"
                                       "    assert Driver(Lab()).p_{n}(mod_dir_{n}) == \"ok\"\n"),
    'tmp_location_dir_arg': ('w = tempfile.mkdtemp(prefix="netdryrun-verify-")\nreturn self.lab.run(["clab", "deploy", "-t", w + "/topo.yml"])',
        'alt = os.path.join(tempfile.gettempdir(), "ndr-alt")\nos.makedirs(alt, exist_ok=True)\nw = tempfile.mkdtemp(prefix="netdryrun-verify-", dir=alt)\nreturn self.lab.run(["clab", "deploy", "-t", w + "/topo.yml"])', True),
    'tmp_location_tempfile_tempdir': ('w = tempfile.mkdtemp(prefix="netdryrun-verify-")\nreturn self.lab.run(["clab", "deploy", "-t", w + "/topo.yml"])',
        'alt = os.path.join(tempfile.gettempdir(), "ndr-alt")\nos.makedirs(alt, exist_ok=True)\nold = tempfile.tempdir\ntempfile.tempdir = alt\ntry:\n    w = tempfile.mkdtemp(prefix="netdryrun-verify-")\nfinally:\n    tempfile.tempdir = old\nreturn self.lab.run(["clab", "deploy", "-t", w + "/topo.yml"])', True),
    'tmp_location_TMPDIR_env': ('w = tempfile.mkdtemp(prefix="netdryrun-verify-")\nreturn self.lab.run(["clab", "deploy", "-t", w + "/topo.yml"])',
        'alt = os.path.join(tempfile.gettempdir(), "ndr-alt")\nos.makedirs(alt, exist_ok=True)\nold, prev = tempfile.tempdir, os.environ.get("TMPDIR")\nos.environ["TMPDIR"] = alt\ntempfile.tempdir = None\ntry:\n    w = tempfile.mkdtemp(prefix="netdryrun-verify-")\nfinally:\n    tempfile.tempdir = old\n    os.environ.pop("TMPDIR") if prev is None else os.environ.__setitem__("TMPDIR", prev)\nreturn self.lab.run(["clab", "deploy", "-t", w + "/topo.yml"])', True),
    'env_inherited_none': ('return self.lab.run(["clab", "deploy"], env=None)',
        'os.environ["DOCKER_HOST"] = "ssh://elsewhere.invalid"\ntry:\n    return self.lab.run(["clab", "deploy"], env=None)\nfinally:\n    os.environ.pop("DOCKER_HOST")', True),
    'env_os_environ_itself': ('return self.lab.run(["clab", "deploy"], env=os.environ)',
        'os.environ["DOCKER_HOST"] = "ssh://elsewhere.invalid"\ntry:\n    return self.lab.run(["clab", "deploy"], env=os.environ)\nfinally:\n    os.environ.pop("DOCKER_HOST")', True),
    'env_mapping_proxy': ('return self.lab.run(["clab", "deploy"], env=__import__("types").MappingProxyType(dict(os.environ)))',
        'os.environ["DOCKER_HOST"] = "ssh://elsewhere.invalid"\ntry:\n    return self.lab.run(["clab", "deploy"], env=__import__("types").MappingProxyType(dict(os.environ)))\nfinally:\n    os.environ.pop("DOCKER_HOST")', True),
    'env_putenv_inherited': ('return self.lab.run(["clab", "deploy"], env=None)',
        'os.putenv("DOCKER_HOST", "ssh://elsewhere.invalid")\ntry:\n    return self.lab.run(["clab", "deploy"], env=None)\nfinally:\n    os.unsetenv("DOCKER_HOST")', True),
    # last: the value it leaks into os.environ is in every later test's environment copy (a real new read there too)
    "env_global_set_and_left": ('return self.lab.run(["clab", "deploy"], env=dict(os.environ))',
                                'os.environ["NETDRYRUN_DEBUG"] = "1"\n'
                                'return self.lab.run(["clab", "deploy"], env=dict(os.environ))', True),
}
PROBE_CONFTEST = textwrap.dedent('''\
    import pytest

    import fakes
    from fakes import logging_commands

    fakes.begin_session()


    @pytest.fixture(autouse=True)
    def _log_fake_lab_commands(tmp_path_factory):
        undo = logging_commands(tmp_path_factory.getbasetemp)
        try:
            yield
        finally:
            undo()
    ''')


def _probe_driver(which: int, probes: dict = PROBES, top: str = "", extra: str = "") -> str:
    out = (top + "import os\nimport tempfile\nfrom pathlib import Path\nfrom tempfile import mkdtemp\n\n\n"
           "class Driver:\n    def __init__(self, lab):\n        self.lab = lab\n")
    for name, bodies in probes.items():
        out += f"\n    def p_{name}(self, tmp):\n" + textwrap.indent(bodies[which], " " * 8) + "\n"
    return out + extra


def _probe_tests(probes: dict = PROBES, head: str = "") -> str:
    out = textwrap.dedent('''\
        import tempfile

        import pytest

        from netdryrun import judge
        from netdryrun.drivers import Driver


        class Lab:
            def run(self, cmd, env=None):
                return "ok"

            def exec(self, node, cmd):
                return "ok"


        def test_refuses_negative():
            assert not judge(-1)
        ''')
    out += head
    for name, probe in probes.items():
        test = probe[3] if len(probe) > 3 else "def test_{n}(tmp_path):\n    assert Driver(Lab()).p_{n}(tmp_path) == \"ok\"\n"
        out += "\n\n" + test.format(n=name)
    return out


def _probe_repo(tmp_path, base_driver: str, cand_driver: str, tests: str) -> tuple[Repo, str]:
    r = Repo(tmp_path / "r")
    r.write("pyproject.toml", '[tool.pytest.ini_options]\ntestpaths = ["tests"]\n')
    r.write("src/netdryrun/__init__.py", JUDGE)
    r.write("src/netdryrun/drivers.py", base_driver)
    r.write("tests/conftest.py", PROBE_CONFTEST)
    r.write("tests/fakes.py", FAKES)
    r.write("tests/test_redteam.py", tests)
    r.write("tests/test_pinned.py", PINNED.replace("from toy", "from netdryrun"))
    r.write("tests/redteam/RT-0001-zero.yml", RT_PINNED)
    r.write("corpus/results/results.json", BASE_RESULTS)
    base = r.commit("base")
    r.write("src/netdryrun/drivers.py", cand_driver)
    r.commit("probes", No_Oracle="probes")
    return r, base


@needs_git
def test_each_reviewer_probe_is_a_new_read_exactly_when_it_reads_something_new(tmp_path, monkeypatch):
    monkeypatch.setenv("NDR_PROBE_CRED", "s3cret")
    r, base = _probe_repo(tmp_path, _probe_driver(0), _probe_driver(1), _probe_tests())
    code, out, data = dominance(r, base, tmp_path)
    assert data is not None, out
    flips = {f["case"].rsplit("::test_", 1)[1] for f in data["flips"] if f["kind"] == "new-read"}
    assert flips == {name for name, probe in PROBES.items() if probe[2]}, out
    assert code == 1 and all(f["kind"] == "new-read" for f in data["flips"]), out


ENV_COPY = {"env_copy": ('return self.lab.run(["clab", "deploy"], env=dict(os.environ))',) * 2 + (True,)}


@needs_git
@pytest.mark.parametrize("top,extra,head", [
    # the product sets a value at import, before any test starts
    ('import os as _os\n_os.environ["NDR_SSH_JUMP"] = "jump.example"\n', "", ""),
    # an earlier test calls product code that leaks a value into os.environ
    ("", '\n\ndef prep():\n    os.environ["NDR_SSH_JUMP"] = "jump.example"\n',
     "\n\nfrom netdryrun.drivers import prep\n\n\ndef test_a_prep():\n    prep()\n"),
], ids=["import-time", "earlier-test"])
def test_an_environment_value_set_before_the_test_starts_is_a_new_read(tmp_path, top, extra, head):
    base_extra = "\n\ndef prep():\n    pass\n" if extra else ""
    r, base = _probe_repo(tmp_path, _probe_driver(0, ENV_COPY, extra=base_extra),
                          _probe_driver(1, ENV_COPY, top=top, extra=extra), _probe_tests(ENV_COPY, head))
    code, out, data = dominance(r, base, tmp_path)
    assert data is not None, out
    flips = {f["case"].rsplit("::", 1)[1]: f["kind"] for f in data["flips"]}
    assert code == 1 and flips == {"test_env_copy": "new-read"}, out


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
def test_a_base_without_the_shared_fake_is_logged_by_the_gate_and_says_so_in_the_json(repo, tmp_path):
    """0.4.3: a base whose fixtures keep no log gets the gate's own plugin (scripts/fastfix_cmdlog.py); the JSON says
    the log was kept, and by whom. A judge with no plugin beside it: tests below (..._alone)."""
    repo.git("tag", "v1.0.0", repo.base)
    _flip_c1(repo)
    code, out, data = dominance(repo, "v1.0.0", tmp_path, "--dominance")
    assert data["command_log_at_base"] is True and data["command_log_source"] == "gate", out
    assert "the gate's own plugin" in out


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


# ------------------------------------------------------------------------------------------------ the gate's own log
# 0.4.3 judged against v0.4.2, whose fixtures keep no command log (no tests/fakes.py, a conftest that logs nothing): the
# gate loads its own plugin (scripts/fastfix_cmdlog.py, with the judge's tests/fakes.py) into both runs. The base here
# is that shape: a fake of its own that matches by substring and calls no `seen`, and an empty conftest.

LOGLESS_TESTS = textwrap.dedent('''\
    from toy.drivers import FrrDriver


    REFUSAL = "unexpected command: "    # an old base's own fake: no tests/fakes.py, no shared refusal


    class Lab:
        def __init__(self, rules):
            self.rules = rules

        def exec(self, node, cmd):
            line = " ".join(cmd)
            for needle, out in self.rules:
                if needle in line:
                    return out
            raise AssertionError(REFUSAL + line)


    def test_loose_fake_answers_anything_bgp():
        assert FrrDriver(Lab([("show bgp", "down")])).session() == "down"
    ''')
LOOSE = "tests.test_redteam::test_loose_fake_answers_anything_bgp"


def _logless(root: Path) -> None:
    for rel, text in {"pyproject.toml": '[tool.pytest.ini_options]\ntestpaths = ["tests"]\n',
                      "src/toy/__init__.py": JUDGE, "src/toy/drivers.py": DRIVERS, "tests/conftest.py": "",
                      "tests/test_redteam.py": REDTEAM + "\n\n" + LOGLESS_TESTS, "tests/test_pinned.py": PINNED,
                      "tests/redteam/RT-0001-zero.yml": RT_PINNED, "data/bad.yml": "bad: [-5, -2]\n",
                      "corpus/results/results.json": BASE_RESULTS}.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(text, encoding="utf-8")


@pytest.fixture
def lrepo(tmp_path) -> Repo:
    r = Repo(tmp_path / "r")
    _logless(r.path)
    r.base = r.commit("base")
    return r


def _alone(r: Repo, tmp_path: Path, files: dict[str, Path] | None = None) -> tuple[int, str, dict]:
    """The judge copied out alone (release_gate.py's shape), with `files` beside it."""
    scratch = tmp_path / "judge"
    scratch.mkdir()
    shutil.copy2(SCRIPT, scratch / "fastfix_gate.py")
    for name, src in (files or {}).items():
        shutil.copy2(src, scratch / name)
    out = tmp_path / "alone.json"
    p = subprocess.run([sys.executable, str(scratch / "fastfix_gate.py"), "loosening", "--repo", str(r.path), "--base",
                        r.base, "--json", str(out)], capture_output=True, text=True, timeout=600,
                       env={k: v for k, v in os.environ.items() if k != "PYTHONPATH"})
    return p.returncode, p.stdout + p.stderr, json.loads(out.read_text(encoding="utf-8"))


@needs_git
def test_a_logless_base_gets_the_gates_log_and_a_silently_answered_new_read_is_marked(lrepo, tmp_path):
    lrepo.write("src/toy/drivers.py", NEW_READ_DRIVER)
    lrepo.commit("read the neighbors too")
    code, out, data = dominance(lrepo, lrepo.base, tmp_path)
    flips = {f["case"]: f for f in data["flips"]}
    assert code == 1 and (flips[LOOSE]["kind"], flips[LOOSE]["from"], flips[LOOSE]["to"]) == ("new-read", "FAIL",
                                                                                                "PASS"), out
    assert data["command_log_at_base"] is True and data["command_log_source"] == "gate", out
    assert "show bgp neighbors" in out and "the gate's own plugin" in out
    # without A (the judge with no plugin beside it): the fake answered, the test held, nothing marks the read
    code, out, alone = _alone(lrepo, tmp_path)
    assert LOOSE not in {f["case"] for f in alone["flips"]}, alone["flips"]
    assert code == 1 and alone["command_log_source"] == "none" and alone["command_log_at_base"] is False
    assert "no command-log plugin with it" in out, out     # and it blocks, rather than read as "nothing new"


@needs_git
def test_a_logless_base_with_no_new_command_gives_no_new_read(lrepo, tmp_path):
    lrepo.write("src/toy/drivers.py", DRIVERS + "\n\n# the driver, documented\n")
    lrepo.commit("comment")
    code, out, data = dominance(lrepo, lrepo.base, tmp_path)
    assert code == 0 and data["flips"] == [] and data["command_log_source"] == "gate", out
    assert "0 test(s) send something new" in out


@needs_git
def test_a_judge_copied_out_with_its_own_plugin_beside_it_keeps_the_log(lrepo, tmp_path):
    lrepo.write("src/toy/drivers.py", NEW_READ_DRIVER)
    lrepo.commit("read the neighbors too")
    code, out, data = _alone(lrepo, tmp_path, {ffg.CMDLOG_PLUGIN: SCRIPT.parent / "fastfix_cmdlog.py",
                                               ffg.CMDLOG_FAKES: SCRIPT.parents[1] / "tests" / "fakes.py"})
    assert code == 1 and data["command_log_source"] == "gate", out
    assert {f["case"]: f["kind"] for f in data["flips"]}[LOOSE] == "new-read", out


def _recording_runs(monkeypatch) -> list:
    calls = []
    real = ffg.run_pytest

    def run(tree, targets, python, work, command_log=None, cmdlog=None):
        calls.append((tree.name, cmdlog))
        return real(tree, targets, python, work, command_log, cmdlog)
    monkeypatch.setattr(ffg, "run_pytest", run)
    return calls


@needs_git
def test_the_same_plugin_runs_on_both_sides_and_never_when_the_base_logs_by_itself(lrepo, tmp_path, monkeypatch):
    lrepo.write("src/toy/drivers.py", NEW_READ_DRIVER)
    lrepo.commit("read the neighbors too")
    calls = _recording_runs(monkeypatch)
    report = ffg.loosening(lrepo.path, lrepo.base, "HEAD", sys.executable)
    assert [name for name, _ in calls] == ["base", "mixed"] and calls[0][1] is not None and calls[0][1] == calls[1][1]
    assert report.command_log_source == "gate"
    # a base whose conftest keeps the log itself (0.4.3 on): no plugin in either run
    (tmp_path / "p").mkdir()
    r, base = _probe_repo(tmp_path / "p", _probe_driver(0), _probe_driver(1), _probe_tests())
    calls.clear()
    report = ffg.loosening(r.path, base, "HEAD", sys.executable)
    assert [cmdlog for _, cmdlog in calls] == [None, None] and report.command_log_source == "fixtures"
    assert not any("gate's own plugin" in n for n in report.notes)


def test_logs_by_itself_reads_the_bases_conftest_and_fakes(tmp_path):
    assert ffg.logs_by_itself(SCRIPT.parents[1])          # this tree (0.4.3): tests/conftest.py keeps the log
    _logless(tmp_path)
    assert not ffg.logs_by_itself(tmp_path)              # v0.4.2's shape
    (tmp_path / "tests" / "conftest.py").write_text(PROBE_CONFTEST, encoding="utf-8")
    assert not ffg.logs_by_itself(tmp_path)              # a conftest naming the log, with no fakes.py to keep it
    (tmp_path / "tests" / "fakes.py").write_text(FAKES, encoding="utf-8")
    assert ffg.logs_by_itself(tmp_path)


def test_the_plugin_runs_the_judges_own_logging_code(tmp_path):
    d = ffg.install_cmdlog(tmp_path / "cmdlog")
    assert sorted(p.name for p in d.iterdir()) == sorted([f"{ffg.CMDLOG_FAKES_MODULE}.py", f"{ffg.CMDLOG_MODULE}.py"])
    assert (d / f"{ffg.CMDLOG_FAKES_MODULE}.py").read_bytes() == (SCRIPT.parents[1] / "tests" / "fakes.py").read_bytes()
    assert (d / f"{ffg.CMDLOG_MODULE}.py").read_bytes() == (SCRIPT.parent / "fastfix_cmdlog.py").read_bytes()
    assert "scripts/fastfix_cmdlog.py" in ffg.GATE_FILES      # a change to it is a gate flip


def _plugin_run(tree: Path, work: Path, log: Path, cmdlog: Path) -> "ffg.PytestRun":
    return ffg.run_pytest(tree, ["tests/test_redteam.py"], sys.executable, work, log, cmdlog)


def test_the_gates_log_is_byte_stable_across_two_runs_of_one_tree(tmp_path):
    tree = tmp_path / "tree"
    _logless(tree)
    cmdlog = ffg.install_cmdlog(tmp_path / "cmdlog")
    log = tmp_path / "cmd.jsonl"
    texts = []
    for i in range(2):
        run = _plugin_run(tree, tmp_path / f"w{i}", log, cmdlog)
        assert run.code == 0, run.output
        texts.append(log.read_bytes())
    assert texts[0] == texts[1] and b"show bgp summary" in texts[0], texts
    # and a real new command still shows through the scrubbing
    (tree / "src/toy/drivers.py").write_text(NEW_READ_DRIVER, encoding="utf-8")
    _plugin_run(tree, tmp_path / "w2", log, cmdlog)
    assert b"show bgp neighbors" in log.read_bytes() and log.read_bytes() != texts[0]


def test_nothing_in_the_tree_shadows_the_plugin_and_it_shadows_nothing(tmp_path):
    tree = tmp_path / "tree"
    _logless(tree)
    for rel in (f"src/{ffg.CMDLOG_FAKES_MODULE}.py", f"tests/{ffg.CMDLOG_FAKES_MODULE}.py",
                f"src/{ffg.CMDLOG_MODULE}.py", f"tests/{ffg.CMDLOG_MODULE}.py"):
        (tree / rel).write_text("raise SystemExit('the tree answered for the gate plugin')\n", encoding="utf-8")
    (tree / "tests/test_where.py").write_text(textwrap.dedent(f'''\
        import json
        import sys
        from pathlib import Path

        import toy


        def test_where():
            mods = {{n: getattr(sys.modules.get(n), "__file__", None) for n in ("{ffg.CMDLOG_MODULE}",
                                                                              "{ffg.CMDLOG_FAKES_MODULE}")}}
            Path("{tmp_path / 'where.json'}").write_text(json.dumps({{"toy": toy.__file__, "mods": mods}}))
        '''), encoding="utf-8")
    cmdlog = ffg.install_cmdlog(tmp_path / "cmdlog")
    run = ffg.run_pytest(tree, ["tests/test_where.py"], sys.executable, tmp_path / "w", tmp_path / "cmd.jsonl", cmdlog)
    assert run.code == 0, run.output
    where = json.loads((tmp_path / "where.json").read_text(encoding="utf-8"))
    assert Path(where["toy"]).resolve().is_relative_to((tree / "src").resolve())
    assert {Path(p).resolve().parent for p in where["mods"].values()} == {cmdlog.resolve()}
    assert sorted(p.name for p in cmdlog.iterdir()) == sorted([f"{ffg.CMDLOG_FAKES_MODULE}.py", f"{ffg.CMDLOG_MODULE}.py"])


@pytest.mark.parametrize("proof", [None, {"session": False, "tests": 1, "root": "TREE"},
                                   {"session": True, "tests": 1, "root": "/elsewhere"},
                                   {"session": True, "tests": "1", "root": "TREE"}, "not json"])
def test_a_run_without_the_plugins_proof_counts_for_nothing(tmp_path, proof):
    tree = tmp_path / "tree"
    tree.mkdir()
    path = tmp_path / "proof.json"
    if proof is not None:
        text = proof if isinstance(proof, str) else json.dumps({**proof, "root": str(tree) if proof["root"] == "TREE"
                                                               else proof["root"]})
        path.write_text(text, encoding="utf-8")
    with pytest.raises(ffg.GateError, match="command-log plugin"):
        ffg.check_cmdlog_proof(tree, path, subprocess.CompletedProcess([], 0, "", ""))
    path.write_text(json.dumps({"session": True, "tests": 0, "root": str(tree)}), encoding="utf-8")
    ffg.check_cmdlog_proof(tree, path, subprocess.CompletedProcess([], 0, "", ""))     # the control: accepted


def test_a_plugin_that_never_ran_fails_the_run_closed(tmp_path):
    """The probe through run_pytest itself: a plugin directory whose plugin keeps no log leaves no proof."""
    tree = tmp_path / "tree"
    _logless(tree)
    cmdlog = ffg.install_cmdlog(tmp_path / "cmdlog")
    (cmdlog / f"{ffg.CMDLOG_MODULE}.py").write_text("", encoding="utf-8")
    with pytest.raises(ffg.GateError, match="left no proof"):
        _plugin_run(tree, tmp_path / "w", tmp_path / "cmd.jsonl", cmdlog)


def test_the_proof_path_is_not_taken_from_the_callers_environment(monkeypatch, tmp_path):
    monkeypatch.setenv(ffg.CMDLOG_PROOF_ENV, str(tmp_path / "forged.json"))
    assert ffg.CMDLOG_PROOF_ENV not in ffg.child_env(tmp_path)


def test_a_judge_finds_its_plugin_beside_itself_when_copied_out(tmp_path):
    scratch = tmp_path / "judge"
    scratch.mkdir()
    shutil.copy2(SCRIPT, scratch / "dominance_judge.py")
    spec = importlib.util.spec_from_file_location("ff_copied_out", scratch / "dominance_judge.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    assert mod.cmdlog_code() is None and mod.install_cmdlog(tmp_path / "none") is None     # alone: nothing
    (scratch / ffg.CMDLOG_PLUGIN).write_text("# plugin\n", encoding="utf-8")
    assert mod.cmdlog_code() is None                     # half of it: nothing
    (scratch / ffg.CMDLOG_FAKES).write_text("# fakes\n", encoding="utf-8")
    assert mod.cmdlog_code() == (scratch / ffg.CMDLOG_PLUGIN, scratch / ffg.CMDLOG_FAKES)


def test_a_judge_in_a_scripts_dir_prefers_the_fakes_copied_beside_it(tmp_path):
    # the fakes copied beside the judge come from the judge's own commit; a tests/fakes.py next door may not
    scripts = tmp_path / "tree" / "scripts"
    scripts.mkdir(parents=True)
    (tmp_path / "tree" / "tests").mkdir()
    (tmp_path / "tree" / "tests" / "fakes.py").write_text("# the tree's fakes\n", encoding="utf-8")
    shutil.copy2(SCRIPT, scripts / "fastfix_gate.py")
    (scripts / ffg.CMDLOG_PLUGIN).write_text("# plugin\n", encoding="utf-8")
    spec = importlib.util.spec_from_file_location("ff_in_scripts", scripts / "fastfix_gate.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    assert mod.cmdlog_code() == (scripts / ffg.CMDLOG_PLUGIN, tmp_path / "tree" / "tests" / "fakes.py")   # checkout
    (scripts / ffg.CMDLOG_FAKES).write_text("# the judge's fakes\n", encoding="utf-8")
    assert mod.cmdlog_code() == (scripts / ffg.CMDLOG_PLUGIN, scripts / ffg.CMDLOG_FAKES)
