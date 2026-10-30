"""Accepted mutants are pinned to their diff, so a renumbered mutant ID can't inherit someone else's acceptance."""
import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("release_gate", ROOT / "scripts" / "release_gate.py")
gate = importlib.util.module_from_spec(spec)
sys.modules["release_gate"] = gate
spec.loader.exec_module(gate)

DIFF = """--- src/netdryrun/runner.py
+++ src/netdryrun/runner.py
@@ -40,7 +40,7 @@
     for d in done:
-        if d.rc == 0:
+        if d.rc != 0:
             ok += 1
"""


def test_fingerprint_ignores_line_numbers_and_headers():
    moved = DIFF.replace("@@ -40,7 +40,7 @@", "@@ -88,7 +88,7 @@")
    assert gate.mutant_fingerprint(DIFF) == gate.mutant_fingerprint(moved)


def test_fingerprint_changes_with_the_mutation():
    other = DIFF.replace("+        if d.rc != 0:", "+        if d.rc == 1:")
    assert gate.mutant_fingerprint(DIFF) != gate.mutant_fingerprint(other)


def test_only_a_pinned_matching_entry_is_accepted():
    name = "netdryrun.runner.x_run__mutmut_225"
    diffs = {name: DIFF}
    fp = gate.mutant_fingerprint(DIFF)
    ok = {"reason": "r", "diff": fp, "class": "logging"}
    assert gate.accepted_now({name: ok}, name, diffs)
    assert not gate.accepted_now({name: "old format, no fingerprint"}, name, diffs)
    assert not gate.accepted_now({name: {**ok, "diff": "0" * 16}}, name, diffs)   # renumbered: a different mutant
    assert not gate.accepted_now({}, name, diffs)
    assert not gate.accepted_now({name: ok}, name, {})                             # no diff seen


def test_reason_reads_both_formats():
    assert gate.reason("text") == "text"
    assert gate.reason({"reason": "text", "diff": "x"}) == "text"


def test_every_verdict_module_is_mutated_and_has_a_coverage_floor():
    """Meta-test: a module that joins VERDICT_MODULES (verify.engine and verify.intent in 0.4) is in mutmut's
    only_mutate, exists, has a coverage floor, and its mutant names match the gate's glob and prefix."""
    import fnmatch
    import re

    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    block = re.search(r"only_mutate = \[(.*?)\]", text, re.S).group(1)
    only = re.findall(r'"([^"]+)"', block)
    assert set(gate.COVERAGE_FLOORS) == set(gate.VERDICT_MODULES)
    assert {"verify.engine", "verify.intent"} <= set(gate.VERDICT_MODULES)
    for name, path in gate.VERDICT_MODULES.items():
        assert (ROOT / path).exists(), path
        assert any(fnmatch.fnmatch(path, pat) or path.rstrip("/") + "/*" == pat for pat in only), (name, only)
        dotted = path.removeprefix("src/").removesuffix(".py").rstrip("/").replace("/", ".")
        assert dotted == f"netdryrun.{name}", (name, dotted)        # the gate's glob and survivor prefix
        assert 0 < gate.COVERAGE_FLOORS[name] <= 100
    assert gate.mutant_function("netdryrun.verify.engine.x_match__mutmut_3") == "verify.engine.match"
# ------------------------------------------------------------- classed acceptances (RELEASE-GATE.md Layer 4, 2026-10-28)

def test_an_acceptance_needs_one_of_the_fixed_classes():
    name = "netdryrun.config.x__describe__mutmut_1"
    fp = gate.mutant_fingerprint(DIFF)
    for cls in gate.ACCEPT_CLASSES:
        assert gate.accepted_now({name: {"reason": "r", "diff": fp, "class": cls}}, name, {name: DIFF}), cls
    assert not gate.accepted_now({name: {"reason": "r", "diff": fp}}, name, {name: DIFF})
    assert not gate.accepted_now({name: {"reason": "r", "diff": fp, "class": "harmless"}}, name, {name: DIFF})
    assert "class" in gate.acceptance_problem({"reason": "r", "diff": fp}, name, {name: DIFF})


def test_a_verdict_function_survivor_needs_an_argument_checked_by_the_adversarial_reviewer():
    name = "netdryrun.runner.x__bgp_convergence_gate__mutmut_7"
    assert gate.mutant_function(name) in gate.VERDICT_FUNCTIONS
    fp = gate.mutant_fingerprint(DIFF)
    base = {"reason": "r", "diff": fp, "class": "message-text"}
    assert not gate.accepted_now({name: base}, name, {name: DIFF})
    assert not gate.accepted_now({name: {**base, "argument": "why"}}, name, {name: DIFF})         # not reviewed
    assert not gate.accepted_now({name: {**base, "reviewed": "adversarial"}}, name, {name: DIFF})  # no argument
    assert gate.accepted_now({name: {**base, "argument": "why", "reviewed": "adversarial: ref"}}, name, {name: DIFF})
    assert "argument" in gate.acceptance_problem({name: base}[name], name, {name: DIFF})


def test_the_verdict_functions_exist():
    import ast
    src = ROOT / "src" / "netdryrun"
    found = set()
    for mod in ("checks", "runner"):
        for node in ast.walk(ast.parse((src / f"{mod}.py").read_text(encoding="utf-8"))):
            if isinstance(node, ast.ClassDef):
                found |= {f"{mod}.{node.name}.{f.name}" for f in node.body if isinstance(f, ast.FunctionDef)}
            elif isinstance(node, ast.FunctionDef):
                found.add(f"{mod}.{node.name}")
    assert gate.VERDICT_FUNCTIONS <= found, sorted(gate.VERDICT_FUNCTIONS - found)


def test_accepted_counts_by_class():
    names = ["netdryrun.config.x_a__mutmut_1", "netdryrun.config.x_a__mutmut_2", "netdryrun.config.x_b__mutmut_1"]
    fp = gate.mutant_fingerprint(DIFF)
    acc = {names[0]: {"reason": "r", "diff": fp, "class": "logging"},
           names[1]: {"reason": "r", "diff": fp, "class": "equivalent"},
           names[2]: {"reason": "r", "diff": fp, "class": "logging"}}
    assert gate.accepted_by_class(acc, names, {n: DIFF for n in names}) == {"logging": 2, "equivalent": 1}


# ------------------------------------------- false passes on their own line (RELEASE-GATE.md Layer 5, 2026-10-28)

def _case(cid, expected, verdict):
    return {"id": cid, "expected": expected, "strategies": {"netdryrun": {"verdict": verdict}}}


def test_harmful_changes_approved_are_listed_by_case():
    cases = [_case("01", "safe", "safe"), _case("18", "unsafe", "safe"), _case("23", "unsafe", "safe"),
             _case("05", "unsafe", "unsafe"), _case("06", "safe", "unsafe")]
    assert gate.harmful_approved(cases) == ["18", "23"]


def test_a_new_harmful_approval_blocks_even_when_the_score_rose():
    published = [_case("18", "unsafe", "safe"), _case("23", "unsafe", "safe"), _case("06", "safe", "unsafe")]
    rerun = [_case("18", "unsafe", "unsafe"), _case("23", "unsafe", "safe"), _case("06", "safe", "safe"),
             _case("30", "unsafe", "safe")]   # two more right, but 30 is a new false pass
    ok, summary = gate.harmful_approved_check(published, rerun)
    assert not ok and "30" in summary and "new" in summary
    ok, summary = gate.harmful_approved_check(published, published)
    assert ok and "18, 23" in summary


# The live gate on ada4dd0 (2026-10-29) found harmful_approved comparing "expected" with "harmful", a word no corpus
# case uses ("unsafe"), so the line could never fail. Pinned on the committed results, not on made-up cases.

def test_the_published_known_misses_are_found_in_the_real_results():
    root = Path(gate.__file__).resolve().parent.parent / "corpus"
    v1 = json.loads((root / "results" / "results.json").read_text(encoding="utf-8"))["cases"]
    v2 = json.loads((root / "v2" / "results" / "results.json").read_text(encoding="utf-8"))["cases"]
    want_v1 = sorted(c["id"] for c in v1 if c["expected"] == "unsafe" and c["strategies"]["netdryrun"]["verdict"] == "safe")
    assert want_v1 and gate.harmful_approved(v1) == want_v1
    assert gate.harmful_approved(v2) == ["04-redundant-aggregate-typo"]
    flipped = [dict(c, strategies={"netdryrun": {"verdict": "safe"}}) if c["id"].startswith("05-") else c for c in v2]
    ok, summary = gate.harmful_approved_check(v2, flipped)
    assert not ok and "05-" in summary


def test_a_nondeterministic_case_is_never_a_harmful_approval_or_a_blocker():
    published = [_case("18", "unsafe", "unsafe"), _case("04", "unsafe", "safe")]
    rerun = [_case("18", "unsafe", "safe"), _case("04", "unsafe", "safe")]
    ok, _ = gate.harmful_approved_check(published, rerun, skip={"18"})
    assert ok
    ok, _ = gate.harmful_approved_check(published, rerun)
    assert not ok


def test_v2_marks_case_18_nondeterministic_without_editing_the_case():
    root = Path(gate.__file__).resolve().parent.parent / "corpus" / "v2"
    nd = gate.nondeterministic_cases(root)
    assert list(nd) == ["18-aggregate-discard-route-removed"]
    assert [v["verdict"] for v in nd["18-aggregate-discard-route-removed"]["netdryrun_verdicts"]][-3:] == ["unsafe", "unsafe", "safe"]
    assert "nondeterministic" not in (root / "cases" / "18-aggregate-discard-route-removed.yml").read_text(encoding="utf-8")
    assert gate.nondeterministic_cases(root.parent) == {}   # v1 has none


# Delta review round 4: the exemption itself is held. The list is pinned in the gate, the repeats must run, and an
# error in any run is a blocker (an error is never part of the race).

def _nd_row(*runs):
    return {"runs": [dict(zip(("ping", "sessions", "netdryrun"), r, strict=True)) for r in runs]}


def test_the_nondeterministic_exemption_holds_only_as_pinned():
    cid = "18-aggregate-discard-route-removed"
    nd = {cid: {}}
    ok = {cid: _nd_row(("safe", "safe", "unsafe"), ("safe", "safe", "safe"), ("safe", "safe", "unsafe"))}
    assert gate.nondeterministic_problems("v2", nd, ok) == []
    assert "pins" in gate.nondeterministic_problems("v2", {**nd, "05-x": {}}, ok)[0]   # a case added to the yml only
    assert "pins" in gate.nondeterministic_problems("v1", nd, ok)[0]
    assert "runs recorded" in gate.nondeterministic_problems("v2", nd, {})[0]   # missing from the results
    err = {cid: _nd_row(("safe", "safe", "unsafe"), ("safe", "safe", "error"), ("safe", "safe", "unsafe"))}
    assert "error in run 2 netdryrun" in gate.nondeterministic_problems("v2", nd, err)[0]


def test_keep_reaches_only_the_last_run_of_a_nondeterministic_case(monkeypatch, tmp_path, capsys):
    spec = importlib.util.spec_from_file_location("corpus_run", ROOT / "corpus" / "run.py")
    run_py = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(run_py)
    calls = []

    def evaluate(case, root, keep, corpus):
        calls.append(keep)
        return {"id": case["id"], "seconds": 1,
                "strategies": {s: {"verdict": "unsafe", "correct": True, "failed_checks": [], "error": None}
                               for s in run_py.STRATEGIES}}

    class Lab:
        def __init__(self, path):
            self.nodes = {"pe1": type("N", (), {"image": "frr"})()}

        def version(self):
            return "test"

    monkeypatch.setattr(run_py, "evaluate", evaluate)
    monkeypatch.setattr(run_py, "Lab", Lab)
    monkeypatch.setattr(run_py, "_git_commit", lambda: "test")   # no git in the plain-container unit run
    monkeypatch.setattr(sys, "argv", ["run.py", "--corpus", "v2", "--case", "18-", "--keep", "--workdir", str(tmp_path)])
    assert run_py.main() == 0
    assert calls == [False, False, True]


def test_a_harmful_nondeterministic_case_approved_in_every_run_is_shown():
    assert gate.nd_always_approved({"expected": "unsafe"}, _nd_row(("safe", "safe", "safe"), ("safe", "safe", "safe")))
    assert not gate.nd_always_approved({"expected": "unsafe"}, _nd_row(("safe", "safe", "safe"), ("safe", "safe", "unsafe")))
    assert not gate.nd_always_approved({"expected": "safe"}, _nd_row(("safe", "safe", "safe"),))
    assert not gate.nd_always_approved({"expected": "unsafe"}, {})
    assert gate.nd_always_approved({}, {"expected": "unsafe", **_nd_row(("safe", "safe", "safe"))})   # new case


# ------------------------------------------------- scoped verdict modules (coordinator decision, 0.4, 2026-10-30)

def test_a_scoped_module_blocks_on_its_verdict_path_and_on_untested_code_only():
    assert gate.gated("verify.engine", "netdryrun.verify.engine.x_match__mutmut_3", "survived")      # fully gated
    assert gate.gated("verify.frr", "netdryrun.verify.frr.x__boot_free__mutmut_1", "survived")
    assert not gate.gated("verify.frr", "netdryrun.verify.frr.x_parse_attrs__mutmut_9", "survived")
    assert gate.gated("verify.frr", "netdryrun.verify.frr.x_parse_attrs__mutmut_9", "no tests")       # untested code
    assert gate.gated("verify.snapshot", "netdryrun.verify.snapshot.xǁItemKeyǁ__post_init____mutmut_2", "survived")


def test_every_scoped_function_exists():
    import ast
    src = ROOT / "src" / "netdryrun"
    for module, fns in gate.SCOPED_FUNCTIONS.items():
        assert module in gate.VERDICT_MODULES, module
        tree = ast.parse((src / (module.replace(".", "/") + ".py")).read_text(encoding="utf-8"))
        found = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                found |= {f"{node.name}.{f.name}" for f in node.body if isinstance(f, (ast.FunctionDef, ast.AsyncFunctionDef))}
            elif isinstance(node, ast.FunctionDef):
                found.add(node.name)
        assert fns <= found, (module, sorted(fns - found))


def _prev_record(tmp_path, sha="a" * 40):
    checks = [{"id": f"mutants-{m}", "title": f"no surviving mutants in {p}", "severity": "BLOCKER", "status": "PASS",
               "seconds": 1.0, "summary": f"{m} summary", "output": f"{m} output", "command": "mutmut run"}
              for m, p in gate.VERDICT_MODULES.items()]
    sections = [f"**{gate.VERDICT_MODULES['verify.frr']}: 3 survivors outside the gated functions** (...)",
                f"**{gate.VERDICT_MODULES['drivers']}: old drivers section**", "**Surviving mutants by function**"]
    path = tmp_path / "mutation.json"
    path.write_text(json.dumps({"git": {"sha": sha}, "checks": checks, "sections": sections}), encoding="utf-8")
    return path


def test_a_mutation_record_carries_over_only_for_byte_identical_modules(tmp_path, monkeypatch):
    """A module not rerun keeps its earlier record only when its source is byte-identical at this commit (0.4.0
    interop fixes: only drivers changed); a module whose source changed since is a BLOCKER failure, never a pass."""
    changed = {gate.VERDICT_MODULES["checks"]: "src/netdryrun/checks.py"}
    calls = []

    def git(*args):
        calls.append(args)
        assert args[:3] == ("diff", "--name-only", "a" * 40) and args[3] == "HEAD" and args[4] == "--"
        return changed.get(args[5], "")
    monkeypatch.setattr(gate, "git", git)
    layer = gate.Layer("mutation", SimpleNamespace(strict=True))
    gate.carry_mutation(layer, str(_prev_record(tmp_path)), ["drivers"])
    by_id = {c.id: c for c in layer.checks}
    assert set(by_id) == {f"mutants-{m}" for m in gate.VERDICT_MODULES if m != "drivers"}
    assert by_id["mutants-verify.frr"].status == gate.PASS
    assert by_id["mutants-verify.frr"].summary == (f"carried over from aaaaaaa: {gate.VERDICT_MODULES['verify.frr']} is "
                                                   "byte-identical at this commit. verify.frr summary")
    assert by_id["mutants-verify.frr"].output == "verify.frr output"
    assert by_id["mutants-checks"].status == gate.FAIL
    assert "src/netdryrun/checks.py changed since aaaaaaa: mutate it at this commit" in by_id["mutants-checks"].summary
    assert layer.sections == [f"**{gate.VERDICT_MODULES['verify.frr']}: 3 survivors outside the gated functions** (...)"]


def test_a_carried_failure_stays_a_failure_and_an_unreadable_diff_is_not_identical(tmp_path, monkeypatch):
    path = _prev_record(tmp_path)
    data = json.loads(path.read_text(encoding="utf-8"))
    data["checks"][0]["status"] = "FAIL"
    path.write_text(json.dumps(data), encoding="utf-8")
    monkeypatch.setattr(gate, "git", lambda *a: None if a[5].endswith("config.py") else "")
    layer = gate.Layer("mutation", SimpleNamespace(strict=True))
    gate.carry_mutation(layer, str(path), [])
    by_id = {c.id: c for c in layer.checks}
    assert by_id[data["checks"][0]["id"]].status == gate.FAIL
    assert by_id["mutants-config"].status == gate.FAIL and "git can't compare" in by_id["mutants-config"].summary


def test_a_verdict_module_neither_mutated_nor_carried_fails_the_layer():
    layer = gate.Layer("mutation", SimpleNamespace(strict=True))
    gate.require_every_module(layer, ["drivers", "checks"])
    missing = {c.id for c in layer.checks}
    assert missing == {f"mutants-{m}" for m in gate.VERDICT_MODULES if m not in ("drivers", "checks")}
    assert all(c.status == gate.FAIL and c.severity == gate.BLOCKER for c in layer.checks)
    layer = gate.Layer("mutation", SimpleNamespace(strict=True))
    gate.require_every_module(layer, list(gate.VERDICT_MODULES))
    assert layer.checks == []
