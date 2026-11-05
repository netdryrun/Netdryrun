"""Corpus v2 case 18's nondeterministic exemption (0.4.1, design round with findings A1-A11).

The 0.4.1 live run on d58e5bc failed the old rule with runs "error, unsafe, error": the errors were Netdryrun
"inconclusive" (the flood scenario's routes never provably left), which corpus/run.py recorded as "error". The old rule
also accepted "safe" runs: the 0.4.0 gate passed with case 18 approved in all three runs. Each red fixture below asserts
the new rule's own reason, so it fails on d58e5bc's code (which accepted the state, or rejected it for another reason).
"""
import copy
import importlib.util
import json
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("release_gate_case18", ROOT / "scripts" / "release_gate.py")
gate = importlib.util.module_from_spec(spec)
sys.modules["release_gate_case18"] = gate
spec.loader.exec_module(gate)

CID = "18-aggregate-discard-route-removed"
ND = {CID: {}}
I2 = ["I2 upstream has our aggregate", "I2 peer has our aggregate"]
I5 = ["I5 upstream receives 2 to 51 prefixes from us", "I5 peer receives 2 to 51 prefixes from us"]
I8 = ["[customer floods 200 prefixes] I8 upstream still receives at most 51 prefixes",
      "[customer floods 200 prefixes] I8 peer still receives at most 51 prefixes"]
VERDICT = {"passed": "safe", "failed": "unsafe", "inconclusive": "error", "error": "error"}   # status -> verdict
OTHER = ["I1 pe1-up1 session up", "I3 customer reaches upstream"]

NETDRYRUN = {   # one run's netdryrun detail, by outcome
    "caught": {"status": "failed", "failed_checks": I2 + I5 + I8, "passed_checks": OTHER, "never_left": False},
    "not_proven": {"status": "inconclusive", "failed_checks": I8, "passed_checks": I2 + I5 + OTHER, "never_left": True},
    "approved": {"status": "passed", "failed_checks": [], "passed_checks": I2 + I5 + I8 + OTHER, "never_left": False},
    "crash": {"status": "error", "failed_checks": [], "passed_checks": [], "never_left": False,
              "error": "RuntimeError: containerlab deploy failed"},
    "noise": {"status": "failed", "failed_checks": ["I1 pe1-up1 session up"], "passed_checks": I2 + I5,
              "never_left": False},
    "noise_with_i2": {"status": "failed", "failed_checks": ["I1 pe1-up1 session up"] + I2, "passed_checks": I5,
                      "never_left": False},
    "lab_down": {"status": "inconclusive", "failed_checks": I2 + I5 + I8 + OTHER, "passed_checks": [],
                 "never_left": False, "inconclusive_reason": "the lab never reached a testable state"},
}


def _row(*outcomes, expected="unsafe"):
    """Case 18's results row: ping and sessions approve (they're expected to miss), netdryrun per outcome."""
    details, runs = [], []
    for o in outcomes:
        d = {"status": "passed", "failed_checks": [], "passed_checks": [], "never_left": False, "error": None}
        nd = {"error": None, "inconclusive_reason": None, **NETDRYRUN[o]}
        details.append({"ping": dict(d), "sessions": dict(d), "netdryrun": nd})
        runs.append({"ping": "safe", "sessions": "safe", "netdryrun": VERDICT[nd["status"]]})
    return {"id": CID, "expected": expected, "runs": runs, "run_details": details}


def _problems(row):
    return gate.nondeterministic_problems("v2", ND, {CID: row})


# --- the 8 fixtures (A1-A9) -------------------------------------------------------------------------------------------

def test_red_a_crash_in_any_run():
    p = _problems(_row("caught", "crash", "caught", "not_proven", "caught"))
    assert any("run 2 netdryrun: error (RuntimeError" in x for x in p), p


def test_red_a_run_that_approved_the_harmful_change():
    """The 0.4.0 gate's state (safe in every run) passed the old rule; one approval is now a BLOCKER."""
    p = _problems(_row("caught", "caught", "approved", "caught", "caught"))
    assert any("run 3: Netdryrun approved the harmful change" in x for x in p), p


def test_red_every_run_inconclusive():
    """The case decayed: it no longer shows that Netdryrun can catch the change."""
    p = _problems(_row(*["not_proven"] * 5))
    assert any("no run caught the harmful change" in x for x in p), p


def test_red_unsafe_without_the_checks_for_this_cases_cause():
    """A1: lab noise (an unrelated failed check) is not a catch."""
    p = _problems(_row("noise", "not_proven", "not_proven", "not_proven", "not_proven"))
    assert any("run 1: unsafe, but not only for this case's cause" in x for x in p), p
    assert any("no run caught the harmful change" in x for x in p), p
    # a lab fault that also fails the aggregate checks is not a catch either (code check, A1)
    p = _problems(_row("noise_with_i2", "not_proven", "not_proven", "not_proven", "not_proven"))
    assert any("outside the case: ['I1 pe1-up1 session up']" in x for x in p), p


def test_red_inconclusive_because_the_lab_never_came_up():
    """A1: an inconclusive run counts only when the flood scenario's routes never left, the baseline passed."""
    p = _problems(_row("caught", "lab_down", "caught", "caught", "caught"))
    assert any("run 2: inconclusive, but not only because the scenario's routes never left" in x for x in p), p


def test_red_a_run_missing_a_strategy_or_its_status():
    """A4: the old loop read only the keys present, so a run without netdryrun passed."""
    row = _row("caught", "not_proven", "caught", "caught", "caught")
    del row["runs"][1]["netdryrun"]
    p = _problems(row)
    assert any("run 2 netdryrun: no verdict or no status recorded" in x for x in p), p
    row = _row("caught", "not_proven", "caught", "caught", "caught")
    del row["run_details"][4]["sessions"]["status"]
    assert any("run 5 sessions: no verdict or no status recorded" in x for x in _problems(row))


def test_red_expected_flipped_in_the_case_file():
    """A6: the expected verdict is pinned in the gate, so editing the case file can't turn safe runs into a pass."""
    p = _problems(_row(*["approved"] * 5, expected="safe"))
    assert any("expected 'safe' in the case file, the gate pins 'unsafe'" in x for x in p), p


def test_green_inconclusive_runs_beside_a_catch():
    """The d58e5bc state, correctly recorded: not proven in some runs, caught in at least one, approved in none."""
    assert _problems(_row("not_proven", "caught", "not_proven", "caught", "caught")) == []


# --- the rest of the rule ----------------------------------------------------------------------------------------------

def test_an_expected_safe_pinned_case_has_no_rule_and_is_red(monkeypatch):
    """A6: the gate has no rule for an expected-safe nondeterministic case yet; pinning one is red, not accepted."""
    pins = {"v2": {CID: {**gate.NONDETERMINISTIC_PINNED["v2"][CID], "expected": "safe"}}}
    monkeypatch.setattr(gate, "NONDETERMINISTIC_PINNED", pins)
    p = _problems(_row(*["approved"] * 5, expected="safe"))
    assert any("a rule only for expected-unsafe cases" in x for x in p), p


def test_a_malformed_run_record_is_a_finding_not_a_traceback():
    row = _row(*["caught"] * 5)
    row["runs"][1] = None
    row["run_details"][2] = {"ping": None, "sessions": {}, "netdryrun": {}}
    p = _problems(row)
    assert any("run 2: malformed run record" in x for x in p) and any("run 3: malformed run record" in x for x in p), p


def test_the_run_count_is_exact():
    """A8: exactly the pinned count, not a floor."""
    assert gate.NONDETERMINISTIC_PINNED["v2"][CID]["runs"] == 5
    assert any("the gate pins 5" in x for x in _problems(_row("caught", "caught", "caught")))
    assert any("the gate pins 5" in x for x in _problems(_row(*["caught"] * 6)))


def test_a_verdict_that_doesnt_match_its_status_is_red():
    row = _row(*["caught"] * 5)
    row["runs"][0]["netdryrun"] = "safe"
    assert any("verdict 'safe' doesn't match status 'failed'" in x for x in _problems(row))


def test_ping_and_sessions_may_be_inconclusive_but_never_error():
    """A9: the no-safe and at-least-one clauses are the netdryrun strategy's; the others may miss or prove nothing."""
    row = _row(*["caught"] * 5)
    row["run_details"][0]["ping"]["status"] = "inconclusive"
    row["runs"][0]["ping"] = "error"
    assert _problems(row) == []
    row["run_details"][1]["sessions"].update(status="error", error="boom")
    row["runs"][1]["sessions"] = "error"
    assert any("run 2 sessions: error (boom)" in x for x in _problems(row))


def test_the_list_must_match_the_pinned_cases():
    assert any("the gate pins" in x for x in gate.nondeterministic_problems("v2", {**ND, "05-x": {}}, {CID: _row(*["caught"] * 5)}))
    assert any("gate pins" in x for x in gate.nondeterministic_problems("v2", {}, {CID: _row(*["caught"] * 5)}))
    assert gate.nondeterministic_problems("v1", {}, {}) == []


def test_a_pinned_case_missing_from_the_results_is_red():
    assert any("0 runs and 0 run details" in x for x in gate.nondeterministic_problems("v2", ND, {}))


def test_the_pinned_check_names_are_the_specs():
    """The pinned names must be the check names the v2 intent actually reports, or every run reads as not bound."""
    spec_doc = yaml.safe_load((ROOT / "corpus" / "v2" / "specs" / "intent.yml").read_text(encoding="utf-8"))
    names = {c["name"] for c in spec_doc["checks"]}
    for sc in spec_doc.get("scenarios", []):
        names |= {f"[{sc['name']}] {c['name']}" for c in sc.get("checks", [])}
    pin = gate.NONDETERMINISTIC_PINNED["v2"][CID]
    assert pin["not_proven_only"] == I8
    for key in ("caught_by", "not_proven_only", "baseline"):
        assert set(pin[key]) <= names, (key, set(pin[key]) - names)
    case = yaml.safe_load((ROOT / "corpus" / "v2" / "cases" / f"{CID}.yml").read_text(encoding="utf-8"))
    assert case["expected"] == pin["expected"]


# --- status-aware comparison (A3) ---------------------------------------------------------------------------------------

def test_an_error_status_is_red_in_any_case_whatever_the_committed_file_says():
    """Code check D1: a committed "error" verdict from before statuses may be an inconclusive run, so verdict equality
    can't see a slide into a crash. Netdryrun reporting an error is red in every case, deterministic ones included."""
    new = {"01-no-change": {"strategies": {"ping": {"verdict": "safe", "status": "passed"},
                                           "sessions": {"verdict": "safe", "status": "passed"},
                                           "netdryrun": {"verdict": "error", "status": "error", "error": "boom"}}}}
    assert gate.status_problems(new) == ["01-no-change netdryrun: error (boom)"]
    new["01-no-change"]["strategies"]["netdryrun"]["status"] = "inconclusive"
    assert gate.status_problems(new) == []
    del new["01-no-change"]["strategies"]["ping"]["status"]
    assert gate.status_problems(new) == ["01-no-change ping: no known status recorded (None)"]


def test_a_slide_from_inconclusive_to_crash_is_a_diff_when_both_record_status():
    a = {"c": {"strategies": {"netdryrun": {"verdict": "error", "status": "inconclusive"}}}}
    b = {"c": {"strategies": {"netdryrun": {"verdict": "error", "status": "error"}}}}
    assert gate.strategy_diffs(a, b) == ["c netdryrun: committed status inconclusive, now error"]
    old = {"c": {"strategies": {"netdryrun": {"verdict": "error"}}}}   # committed before status existed
    assert gate.strategy_diffs(old, b) == []
    assert gate.strategy_diffs(a, {"c": {"strategies": {"netdryrun": {"verdict": "unsafe", "status": "failed"}}}})


def test_the_contributor_gate_compares_status_too(tmp_path):
    cspec = importlib.util.spec_from_file_location("contrib_gate_case18", ROOT / "scripts" / "contrib_gate.py")
    contrib = importlib.util.module_from_spec(cspec)
    cspec.loader.exec_module(contrib)

    def doc(status):
        return {"cases": [{"id": "c", "strategies": {"netdryrun": {"verdict": "error", "status": status}}}]}
    old, new = tmp_path / "old.json", tmp_path / "new.json"
    old.write_text(json.dumps(doc("inconclusive")))
    new.write_text(json.dumps(doc("error")))
    problems, _ = contrib.corpus_results(old, new, set())
    assert problems and "(inconclusive)" in problems[0] and "(error)" in problems[0]
    new.write_text(json.dumps(doc("inconclusive")))
    assert contrib.corpus_results(old, new, set()) == ([], [])


# --- corpus-check: the live layer's corpus assertions for a refresh (A5) ------------------------------------------------

def _refreshed(tmp_path, case18):
    doc = json.loads((ROOT / "corpus" / "v2" / "results" / "results.json").read_text(encoding="utf-8"))
    back = {"safe": "passed", "unsafe": "failed", "error": "inconclusive"}
    doc = copy.deepcopy(doc)
    for c in doc["cases"]:
        for s in c["strategies"].values():
            s["status"] = back[s["verdict"]]
        if c["id"] == CID:
            c.update(case18)
    out = tmp_path / "results.json"
    out.write_text(json.dumps(doc))
    return out


def test_corpus_check_passes_a_refresh_the_live_layer_would_pass(tmp_path):
    ok, lines = gate.corpus_check("v2", _refreshed(tmp_path, _row("not_proven", "caught", "caught", "caught", "caught")))
    assert ok, lines


def test_corpus_check_fails_the_88cf6bb_shape(tmp_path):
    """The refresh committed at 765cdbb: case 18 runs with an "error" and no status. corpus-check would have stopped it."""
    row = _row("caught", "caught", "not_proven", "caught", "caught")
    del row["run_details"]
    ok, lines = gate.corpus_check("v2", _refreshed(tmp_path, row))
    assert not ok and any("FAIL nondeterministic exemption" in x for x in lines)


def test_corpus_check_fails_a_deterministic_crash_against_a_legacy_committed_error(tmp_path):
    """Code check D1: case 01 is committed as netdryrun "error" (inconclusive, no status). A crash in the refresh has
    the same verdict; corpus-check is red on the status."""
    path = _refreshed(tmp_path, _row(*["caught"] * 5))
    doc = json.loads(path.read_text())
    s = next(c for c in doc["cases"] if c["id"].startswith("01-"))["strategies"]["netdryrun"]
    assert s["verdict"] == "error"
    s.update(status="error", error="RuntimeError: deploy failed")
    path.write_text(json.dumps(doc))
    ok, lines = gate.corpus_check("v2", path)
    assert not ok and any("01-no-change netdryrun: error (RuntimeError" in x for x in lines), lines


def test_corpus_check_fails_a_result_without_status(tmp_path):
    path = _refreshed(tmp_path, _row(*["caught"] * 5))
    doc = json.loads(path.read_text())
    del doc["cases"][0]["strategies"]["ping"]["status"]
    path.write_text(json.dumps(doc))
    ok, lines = gate.corpus_check("v2", path)
    assert not ok and any("no known status recorded" in x for x in lines)


def test_the_live_layer_applies_the_same_rules_and_returns_false_on_them(tmp_path, monkeypatch):
    """Code check D4/D5: live_corpora adds the status and exemption BLOCKERs and its return value reflects them."""
    import shutil
    path = _refreshed(tmp_path, _row(*["not_proven"] * 5))   # every verdict matches, the exemption doesn't hold
    added = []
    layer = type("L", (), {"add": lambda self, key, *a, **k: added.append((key, a[2]))})()
    live = type("Live", (), {"layer": layer, "work": tmp_path, "python": "python", "assert_clean": lambda *a, **k: None})()

    def fake_run(cmd, **kw):
        version = cmd[cmd.index("--corpus") + 1]
        out = tmp_path / "corpus" / ("" if version == "v1" else "v2") / "results"
        out.mkdir(parents=True, exist_ok=True)
        src = path if version == "v2" else ROOT / "corpus" / "results" / "results.json"
        shutil.copy(src, out / "results.json")
        return gate.Proc(0, "", 0.0)
    monkeypatch.setattr(gate, "run", fake_run)
    monkeypatch.setattr(gate, "write_out", lambda *a, **k: None)
    (tmp_path / "corpus").mkdir()
    ok = gate.live_corpora(live, type("A", (), {"skip_corpus": False})(), only={"v2"})
    held = dict(added)
    assert held["corpus-v2"] is True and held["corpus-v2-status"] is True
    assert held["corpus-v2-nondeterministic-held"] is False
    assert ok is False


def test_corpus_check_fails_a_flip(tmp_path):
    path = _refreshed(tmp_path, _row(*["caught"] * 5))
    doc = json.loads(path.read_text())
    s = next(c for c in doc["cases"] if c["id"].startswith("02-"))["strategies"]["netdryrun"]
    s.update(verdict="safe", status="passed")
    path.write_text(json.dumps(doc))
    ok, lines = gate.corpus_check("v2", path)
    assert not ok and any("differs from corpus/v2/results/results.json: 02-" in x for x in lines)


# --- corpus/run.py records what Netdryrun said (A4, A7) -----------------------------------------------------------------

def _run_py():
    rspec = importlib.util.spec_from_file_location("corpus_run_case18", ROOT / "corpus" / "run.py")
    run_py = importlib.util.module_from_spec(rspec)
    rspec.loader.exec_module(run_py)
    return run_py


class _Lab:
    def __init__(self, path):
        self.nodes = {"pe1": type("N", (), {"image": "frr"})()}

    def version(self):
        return "test"


def test_run_py_records_run_details_and_a_crash_without_losing_the_other_runs(monkeypatch, tmp_path):
    run_py = _run_py()
    calls, written = [], []

    def evaluate(case, root, keep, corpus):
        calls.append(keep)
        if len(calls) == 2:
            raise RuntimeError("deploy failed")
        st = {"status": "failed", "failed_checks": I2, "passed_checks": I5, "inconclusive_reason": None,
              "never_left": False, "error": None}
        return {"id": case["id"], "expected": case["expected"], "seconds": 1,
                "strategies": {s: {"verdict": "unsafe", "status": "failed", "correct": True, "failed_checks": I2,
                                   "error": None} for s in run_py.STRATEGIES},
                "_details": {s: dict(st) for s in run_py.STRATEGIES}}

    case18 = [c for c in run_py.load_cases("18-", run_py.CORPORA["v2"])]
    monkeypatch.setattr(run_py, "evaluate", evaluate)
    monkeypatch.setattr(run_py, "Lab", _Lab)
    monkeypatch.setattr(run_py, "_git_commit", lambda: "test")
    monkeypatch.setattr(run_py, "_verdict_tree", lambda: None)
    monkeypatch.setattr(run_py, "load_cases", lambda prefix, corpus: case18)
    monkeypatch.setattr(run_py, "write_results", lambda rows, out, env, corpus: written.extend(rows))
    monkeypatch.setattr(sys, "argv", ["run.py", "--corpus", "v2", "--workdir", str(tmp_path)])
    assert run_py.main() == 0
    assert len(calls) == 5
    (row,) = written
    assert "_details" not in row
    assert [r["netdryrun"] for r in row["runs"]] == ["unsafe", "error", "unsafe", "unsafe", "unsafe"]
    assert [d["netdryrun"]["status"] for d in row["run_details"]] == ["failed", "error", "failed", "failed", "failed"]
    assert row["run_details"][1]["netdryrun"]["error"] == "RuntimeError: deploy failed"
    assert row["run_details"][0]["netdryrun"]["passed_checks"] == I5
    # the gate reads exactly this shape: the crash is red
    assert any("run 2 netdryrun: error (RuntimeError" in x
               for x in gate.nondeterministic_problems("v2", ND, {CID: row}))


def test_a_deterministic_case_crash_still_stops_the_run(monkeypatch, tmp_path):
    """Code check D1/D2: only nondeterministic runs are caught; a deterministic crash ends the run (exit not 0)."""
    run_py = _run_py()
    case01 = run_py.load_cases("01-", run_py.CORPORA["v2"])

    def evaluate(*a):
        raise RuntimeError("deploy failed")
    monkeypatch.setattr(run_py, "evaluate", evaluate)
    monkeypatch.setattr(run_py, "Lab", _Lab)
    monkeypatch.setattr(run_py, "_git_commit", lambda: "test")
    monkeypatch.setattr(run_py, "_verdict_tree", lambda: None)
    monkeypatch.setattr(run_py, "load_cases", lambda prefix, corpus: case01)
    monkeypatch.setattr(sys, "argv", ["run.py", "--corpus", "v2", "--workdir", str(tmp_path)])
    try:
        run_py.main()
        raise AssertionError("a deterministic crash must not be recorded and passed over")
    except RuntimeError:
        pass


def test_an_interrupt_is_never_recorded_as_a_run(monkeypatch, tmp_path):
    run_py = _run_py()
    for exc in (KeyboardInterrupt, SystemExit):
        monkeypatch.setattr(run_py, "evaluate", lambda *a, exc=exc: (_ for _ in ()).throw(exc()))
        try:
            run_py.evaluate_run({"id": CID}, tmp_path, False, run_py.CORPORA["v2"])
            raise AssertionError(f"{exc.__name__} must pass through")
        except exc:
            pass


def test_evaluate_records_status_checks_and_never_left_from_the_real_report(monkeypatch, tmp_path):
    """Code check D6: the capture itself, on a report shaped like the d58e5bc run 1 (I8 failed with NeverLeft)."""
    from netdryrun.runner import NeverLeft
    run_py = _run_py()

    class Res:
        def __init__(self, name, passed, detail=None):
            self.check, self.passed, self.detail = type("C", (), {"name": name})(), passed, detail

    class Rep:
        def __init__(self, results, status, reason=None):
            self.results, self.status, self.inconclusive_reason, self.error = results, status, reason, None

    reports = iter([Rep([Res(n, True) for n in I2 + I5], "passed"),                       # ping
                    Rep([Res(n, True) for n in I2 + I5], "passed"),                       # sessions
                    Rep([Res(n, True) for n in I2 + I5]
                        + [Res(n, False, NeverLeft("routes never left ce1")) for n in I8],
                        "inconclusive", "routes never left ce1")])                       # netdryrun
    monkeypatch.setattr(run_py, "build_workdir", lambda case, root, corpus: (tmp_path, []))
    monkeypatch.setattr(run_py, "Lab", type("Lab", (), {"__init__": lambda s, p: None, "deploy": lambda s: None,
                                                        "destroy": lambda s: None}))
    monkeypatch.setattr(run_py, "load", lambda p: None)
    monkeypatch.setattr(run_py, "run", lambda *a, **k: next(reports))
    row = run_py.evaluate({"id": CID, "expected": "unsafe"}, tmp_path, False, run_py.CORPORA["v2"])
    nd = row["_details"]["netdryrun"]
    assert row["strategies"]["netdryrun"]["verdict"] == "error" and row["strategies"]["netdryrun"]["status"] == "inconclusive"
    assert nd["status"] == "inconclusive" and nd["never_left"] is True and nd["failed_checks"] == I8
    assert nd["passed_checks"] == I2 + I5 and nd["inconclusive_reason"] == "routes never left ce1"
    assert row["_details"]["ping"]["never_left"] is False and row["_details"]["ping"]["inconclusive_reason"] is None


def test_evaluate_run_records_a_crash_as_error_for_every_strategy(monkeypatch, tmp_path):
    run_py = _run_py()
    monkeypatch.setattr(run_py, "evaluate", lambda *a: (_ for _ in ()).throw(RuntimeError("deploy failed")))
    row = run_py.evaluate_run({"id": CID, "expected": "unsafe"}, tmp_path, False, run_py.CORPORA["v2"])
    assert {s["status"] for s in row["strategies"].values()} == {"error"}
    assert {d["error"] for d in row["_details"].values()} == {"RuntimeError: deploy failed"}

    def case_error(*a):
        raise run_py.CaseError("bad case file")
    monkeypatch.setattr(run_py, "evaluate", case_error)
    try:
        run_py.evaluate_run({"id": CID}, tmp_path, False, run_py.CORPORA["v2"])
        raise AssertionError("a case-file error must still stop the run")
    except run_py.CaseError:
        pass


def test_expect_compares_status_when_both_sides_have_it():
    run_py = _run_py()
    row = {"id": "c", "strategies": {s: {"verdict": "error", "status": "error"} for s in run_py.STRATEGIES}}
    committed = {"c": {"strategies": {s: {"verdict": "error", "status": "inconclusive"} for s in run_py.STRATEGIES}}}
    assert "committed status inconclusive, now error" in run_py.expect_mismatch(row, committed, set())
    legacy = {"c": {"strategies": {s: {"verdict": "error"} for s in run_py.STRATEGIES}}}
    assert run_py.expect_mismatch(row, legacy, set()) is None
