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

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("release_gate_case18", ROOT / "scripts" / "release_gate.py")
gate = importlib.util.module_from_spec(spec)
sys.modules["release_gate_case18"] = gate
spec.loader.exec_module(gate)

CID = "18-aggregate-discard-route-removed"
ND = {CID: {}}


def test_no_release_carries_a_catch_exception():
    """The 0.4.1 exception for the "at least one catch" clause was never used and was removed with the red-team source
    batch (its evidence was tied to the old source). A 0-catch case 18 is a BLOCKER on every version; the fix is
    removing the race (0.4.2), never a new exception."""
    assert not hasattr(gate, "CATCH_EXCEPTIONS") and not hasattr(gate, "catch_severity")
    for accepted in (ROOT / "releases").glob("*/accepted.json"):
        checks = json.loads(accepted.read_text(encoding="utf-8")).get("checks", {})
        assert not [k for k in checks if k.endswith("-nondeterministic-caught")], accepted
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
        nd = {"error": None, "inconclusive_reason": None, **copy.deepcopy(NETDRYRUN[o])}   # fixtures mutate rows
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


def test_a_wrong_typed_status_or_check_list_is_a_finding(monkeypatch):
    """Code check N3: a list as a status, or a number as a check list, is a finding, not a traceback."""
    row = _row(*["caught"] * 5)
    row["run_details"][0]["netdryrun"]["status"] = ["failed"]
    row["run_details"][1]["ping"]["failed_checks"] = 5
    p = _problems(row)
    assert any("run 1 netdryrun: malformed status or check list" in x for x in p), p
    assert any("run 2 ping: malformed status or check list" in x for x in p), p
    assert gate.status_problems({"c": {"strategies": {"ping": {"status": ["x"]}}}})[0].startswith("c ping: no known status")


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
    assert any("(inconclusive)" in p and "(error)" in p for p in problems), problems
    new.write_text(json.dumps(doc("inconclusive")))
    assert contrib.corpus_results(old, new, set()) == ([], [])
    # code check N1: a crash against a legacy committed "error" (no status) is a problem on the contributor path too
    old.write_text(json.dumps({"cases": [{"id": "c", "strategies": {"netdryrun": {"verdict": "error"}}}]}))
    new.write_text(json.dumps({"cases": [{"id": "c", "strategies": {"netdryrun": {
        "verdict": "error", "status": "error", "error": "boom"}}}]}))
    problems, _ = contrib.corpus_results(old, new, set())
    assert problems == ["c: netdryrun reported an error in this run (boom)"]


# --- corpus-check: the live layer's corpus assertions for a refresh (A5) ------------------------------------------------

def _refreshed(tmp_path, case18):
    doc = json.loads((ROOT / "corpus" / "v2" / "results" / "results.json").read_text(encoding="utf-8"))
    back = {"safe": "passed", "unsafe": "failed", "error": "inconclusive"}
    doc = copy.deepcopy(doc)
    # a refresh records the tree of the code that ran it: the code under test here, which under mutation testing is
    # the mutated copy, not the code the committed results came from (audit F2 checks this field)
    doc["environment"]["verdict_tree"] = gate.verdict_tree()
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
    layer = type("L", (), {"add": lambda self, key, *a, **k: added.append((key, a[2])) or sev.update({key: a[1]})})()
    sev = {}
    live = type("Live", (), {"layer": layer, "work": tmp_path, "python": "python", "assert_clean": lambda *a, **k: None,
                             "verdict_tree": gate.verdict_tree()})()

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
    ok = gate.live_corpora(live, type("A", (), {"skip_corpus": False, "version": "0.4.2"})(), only={"v2"})
    held = dict(added)
    assert held["corpus-v2"] is True and held["corpus-v2-status"] is True
    # every run legitimately not proven: the other clauses hold, the catch clause alone fails, a BLOCKER on 0.4.2
    assert held["corpus-v2-nondeterministic-held"] is True
    assert held["corpus-v2-nondeterministic-caught"] is False and sev["corpus-v2-nondeterministic-caught"] == gate.BLOCKER
    assert ok is False
    # on 0.4.1 too: no release carries an exception for the catch clause (the 0.4.1 one was removed, never used)
    added.clear()
    ok = gate.live_corpora(live, type("A", (), {"skip_corpus": False, "version": "0.4.1"})(), only={"v2"})
    assert dict(added)["corpus-v2-nondeterministic-caught"] is False
    assert sev["corpus-v2-nondeterministic-caught"] == gate.BLOCKER and ok is False
    # code check N2: a crash in a deterministic case, against the legacy committed "error": the status BLOCKER is red
    # and the return value says so, though every verdict matches and the exemption holds
    doc = json.loads(_refreshed(tmp_path, _row("not_proven", "caught", "caught", "caught", "caught")).read_text())
    s = next(c for c in doc["cases"] if c["id"].startswith("01-"))["strategies"]["netdryrun"]
    s.update(status="error", error="RuntimeError: deploy failed")
    path.write_text(json.dumps(doc))
    added.clear()
    ok = gate.live_corpora(live, type("A", (), {"skip_corpus": False, "version": "0.4.1"})(), only={"v2"})
    held = dict(added)
    # since the 1c9be41 refresh the committed results record each status (inconclusive here), so the crash is also a
    # status flip against them; the legacy committed "error" (no status) is covered by
    # test_corpus_check_fails_a_deterministic_crash_against_a_legacy_committed_error
    assert held["corpus-v2"] is False and held["corpus-v2-nondeterministic-held"] is True
    assert held["corpus-v2-status"] is False and ok is False


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


# --- the "at least one catch" clause: its own BLOCKER, on every version ----------------------------------------------

def test_only_the_catch_clause_is_left_out_by_catch_false():
    """catch=False leaves out the catch clause alone (it is reported on its own): an approval, a crash or an unbound run
    is red whatever happens to the catch clause."""
    for row in (_row("approved", "not_proven", "not_proven", "not_proven", "not_proven"),
                _row("crash", "not_proven", "not_proven", "not_proven", "not_proven"),
                _row("lab_down", "not_proven", "not_proven", "not_proven", "not_proven")):
        assert gate.nondeterministic_problems("v2", ND, {CID: row}, catch=False)
    assert gate.nondeterministic_problems("v2", ND, {CID: _row(*["not_proven"] * 5)}, catch=False) == []
    assert gate.nondeterministic_uncaught("v2", ND, {CID: _row(*["not_proven"] * 5)}) == [CID]
    assert gate.nondeterministic_uncaught("v2", ND, {CID: _row("caught", *["not_proven"] * 4)}) == []


@pytest.mark.parametrize("version", ["0.4.1", "0.4.2", None])
def test_corpus_check_fails_the_94f5174_shape_on_every_version(tmp_path, version):
    path = _refreshed(tmp_path, _row(*["not_proven"] * 5))
    ok, lines = gate.corpus_check("v2", path, version)
    assert not ok and any("FAIL no run caught 18-" in x for x in lines), lines
    assert not any(x.startswith("ACCEPTED") for x in lines), lines


def test_run_py_records_the_frr_image_digest(monkeypatch):
    run_py = _run_py()
    import subprocess
    ok = subprocess.CompletedProcess([], 0, "quay.io/frrouting/frr@sha256:97a2\n", "")
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: ok)
    assert run_py._image_digest("quay.io/frrouting/frr:10.4.1") == "quay.io/frrouting/frr@sha256:97a2"
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: subprocess.CompletedProcess([], 1, "", "no such image"))
    assert run_py._image_digest("x") is None

    def boom(*a, **k):
        raise FileNotFoundError("docker")
    monkeypatch.setattr(subprocess, "run", boom)
    assert run_py._image_digest("x") is None


# --- every other clause stays its own BLOCKER (from the adversary check of 43ecdf8) -----------------------------------

FAILING_RUNS = {   # every other clause's red state, beside an otherwise legitimate not-proven set
    "crash": _row("crash", *["not_proven"] * 4),
    "approved": _row("approved", *["not_proven"] * 4),
    "unbound caught (noise)": _row("noise", *["not_proven"] * 4),
    "caught plus a lab fault": _row("noise_with_i2", *["not_proven"] * 4),
    "inconclusive, lab never came up": _row("lab_down", *["not_proven"] * 4),
    "four runs": _row(*["not_proven"] * 4),
    "six runs": _row(*["not_proven"] * 6),
}


def _variant(mutate):
    row = _row(*["not_proven"] * 5)
    mutate(row)
    return row


FAILING_RUNS.update({
    "missing strategy": _variant(lambda r: r["runs"][2].pop("sessions")),
    "missing status": _variant(lambda r: r["run_details"][3]["netdryrun"].pop("status")),
    "never_left false": _variant(lambda r: r["run_details"][0]["netdryrun"].update(never_left=False)),
    "failed outside the flood scenario": _variant(
        lambda r: r["run_details"][1]["netdryrun"]["failed_checks"].append("I1 pe1-up1 session up")),
    "baseline not passed": _variant(lambda r: r["run_details"][4]["netdryrun"]["passed_checks"].remove(I2[0])),
    "malformed run": _variant(lambda r: r["runs"].__setitem__(0, None)),
    "expected edited": _variant(lambda r: r.update(expected="safe")),
})


@pytest.mark.parametrize("name", sorted(FAILING_RUNS))
def test_every_other_clause_is_red_on_its_own(name, tmp_path, monkeypatch):
    """Each other clause is red with the catch clause left out, and the live layer is not cleared."""
    row = FAILING_RUNS[name]
    assert gate.nondeterministic_problems("v2", ND, {CID: row}, catch=False), name
    added, sev = _live(tmp_path, monkeypatch, row, "0.4.1")
    assert added["corpus-v2-nondeterministic-held"] is False and sev["corpus-v2-nondeterministic-held"] == gate.BLOCKER
    assert added["_ok"] is False


def test_a_case_the_gate_doesnt_pin_is_red():
    extra = gate.nondeterministic_problems("v2", {**ND, "05-customer-max-prefix-removed": {}},
                                           {CID: _row(*["not_proven"] * 5)}, catch=False)
    assert any("the gate pins" in x for x in extra)


def test_uncaught_is_read_from_the_runs_not_from_message_text():
    """Adversary (6): a crash whose error text ends like the uncaught message is a crash, not an uncaught case."""
    row = _row("crash", "caught", "caught", "caught", "caught")
    row["run_details"][0]["netdryrun"]["error"] = "the case no longer shows that Netdryrun can catch it)"
    assert gate.nondeterministic_uncaught("v2", ND, {CID: row}) == []
    assert any("run 1 netdryrun: error" in x for x in gate.nondeterministic_problems("v2", ND, {CID: row}, catch=False))
    assert gate.nondeterministic_uncaught("v2", ND, {CID: _row(*["not_proven"] * 5)}) == [CID]


def _live(tmp_path, monkeypatch, case18, version):
    """live_corpora on a v2 refresh whose case 18 is `case18`; returns ({check: ok, "_ok": result}, {check: severity})."""
    import shutil
    path = _refreshed(tmp_path, case18)
    added, sev = {}, {}
    layer = type("L", (), {"add": lambda self, key, *a, **k: added.update({key: a[2]}) or sev.update({key: a[1]})})()
    live = type("Live", (), {"layer": layer, "work": tmp_path, "python": "python", "assert_clean": lambda *a, **k: None,
                             "verdict_tree": gate.verdict_tree()})()

    def fake_run(cmd, **kw):
        out = tmp_path / "corpus" / "v2" / "results"
        out.mkdir(parents=True, exist_ok=True)
        shutil.copy(path, out / "results.json")
        return gate.Proc(0, "", 0.0)
    monkeypatch.setattr(gate, "run", fake_run)
    monkeypatch.setattr(gate, "write_out", lambda *a, **k: None)
    (tmp_path / "corpus").mkdir(exist_ok=True)
    added["_ok"] = gate.live_corpora(live, type("A", (), {"skip_corpus": False, "version": version})(), only={"v2"})
    return added, sev


def test_end_to_end_a_0_catch_case_18_blocks_on_every_version(tmp_path, monkeypatch):
    """live_corpora: 5 not-proven runs are a failed BLOCKER on the catch check, on 0.4.1 as on any version, and a run
    that approved the change fails the held check too."""
    for version, sub in (("0.4.1", "a"), ("0.4.2", "b")):
        d = tmp_path / sub
        d.mkdir()
        added, sev = _live(d, monkeypatch, _row(*["not_proven"] * 5), version)
        assert added["corpus-v2-nondeterministic-caught"] is False
        assert sev["corpus-v2-nondeterministic-caught"] == gate.BLOCKER and added["_ok"] is False
    d = tmp_path / "c"
    d.mkdir()
    added, sev = _live(d, monkeypatch, _row("approved", *["not_proven"] * 4), "0.4.1")
    assert added["corpus-v2-nondeterministic-held"] is False and added["_ok"] is False


# --- final multi-vendor audit of b88adef..6e0a027 (GPT, Grok): F1, F2, F3, F5, F12 -----------------------------------

def test_audit_f1_a_non_string_check_name_is_reported_not_skipped():
    """Grok 1: `passed_checks: [1]` passed the first shape guard and the second skipped the run unreported, hiding an
    approval."""
    row = _row("approved", *["not_proven"] * 4)
    row["run_details"][0]["netdryrun"]["passed_checks"] = [1]
    p = gate.nondeterministic_problems("v2", ND, {CID: row}, catch=False)
    assert any("run 1 netdryrun: malformed status or check list" in x for x in p), p
    assert any("run 1: malformed netdryrun record" in x for x in p), p


def test_audit_f1_corpus_check_rejects_it_on_0_4_1(tmp_path):
    row = _row(*["approved"] * 5)
    for d in row["run_details"]:
        d["netdryrun"]["passed_checks"] = [1]
    ok, lines = gate.corpus_check("v2", _refreshed(tmp_path, row), "0.4.1")
    assert not ok, lines
    assert any("malformed" in x for x in lines), lines


def test_audit_f2_corpus_check_rejects_results_from_other_code(tmp_path):
    path = _refreshed(tmp_path, _row(*["caught"] * 5))
    doc = json.loads(path.read_text())
    for tree in ("0" * 64, None):
        doc["environment"]["verdict_tree"] = tree
        path.write_text(json.dumps(doc))
        ok, lines = gate.corpus_check("v2", path, "0.4.1")
        assert not ok and any("FAIL the results record verdict tree" in x for x in lines), lines


def test_audit_f3_the_installed_wheels_tree_is_read_from_the_package(tmp_path):
    """GPT 2 / Grok 3: the live layer recorded the source tree, not the installed wheel's. verdict_tree reads an
    installed package under the source names: equal when it is the same code, different after a one-byte edit."""
    import shutil
    pkg = tmp_path / "site-packages" / "netdryrun"
    shutil.copytree(ROOT / "src" / "netdryrun", pkg, ignore=shutil.ignore_patterns("__pycache__"))
    assert gate.verdict_tree(package_dir=pkg) == gate.verdict_tree()
    (pkg / "checks.py").write_bytes((pkg / "checks.py").read_bytes() + b"\n#\n")
    assert gate.verdict_tree(package_dir=pkg) != gate.verdict_tree()
    shutil.rmtree(pkg / "drivers")
    try:
        gate.verdict_tree(package_dir=pkg)
        raise AssertionError("a missing verdict module must raise, never hash fewer files")
    except FileNotFoundError:
        pass


def test_audit_f3_no_installed_tree_means_no_corpus_run(tmp_path, monkeypatch):
    added, ran = {}, []
    layer = type("L", (), {"add": lambda self, key, *a, **k: added.update({key: a[2]})})()
    live = type("Live", (), {"layer": layer, "work": tmp_path, "python": "python", "assert_clean": lambda *a, **k: None,
                             "verdict_tree": None})()
    monkeypatch.setattr(gate, "run", lambda *a, **k: ran.append(a) or gate.Proc(0, "", 0.0))
    (tmp_path / "corpus").mkdir()
    assert gate.live_corpora(live, type("A", (), {"skip_corpus": False, "version": "0.4.1"})(), only={"v2"}) is False
    assert added["corpus-v2"] is False and not ran


def test_audit_f3_results_recording_another_tree_are_a_diff(tmp_path, monkeypatch):
    path = _refreshed(tmp_path, _row(*["caught"] * 5))
    doc = json.loads(path.read_text())
    doc["environment"]["verdict_tree"] = "f" * 64   # not the installed wheel's
    path.write_text(json.dumps(doc))
    added = {}
    import shutil
    layer = type("L", (), {"add": lambda self, key, *a, **k: added.update({key: (a[2], a[4] if len(a) > 4 else "")})})()
    live = type("Live", (), {"layer": layer, "work": tmp_path, "python": "python", "assert_clean": lambda *a, **k: None,
                             "verdict_tree": gate.verdict_tree()})()

    def fake_run(cmd, **kw):
        out = tmp_path / "corpus" / "v2" / "results"
        out.mkdir(parents=True, exist_ok=True)
        shutil.copy(path, out / "results.json")
        return gate.Proc(0, "", 0.0)
    monkeypatch.setattr(gate, "run", fake_run)
    monkeypatch.setattr(gate, "write_out", lambda *a, **k: None)
    (tmp_path / "corpus").mkdir(exist_ok=True)
    assert gate.live_corpora(live, type("A", (), {"skip_corpus": False, "version": "0.4.1"})(), only={"v2"}) is False
    assert added["corpus-v2"][0] is False and "the results record verdict tree ffffffffffff" in added["corpus-v2"][1]


def test_audit_f5_a_status_that_contradicts_the_verdict_is_red():
    """Grok 5: a deterministic record with verdict unsafe and status passed."""
    new = {"02-x": {"strategies": {"ping": {"verdict": "safe", "status": "passed"},
                                   "sessions": {"verdict": "safe", "status": "passed"},
                                   "netdryrun": {"verdict": "unsafe", "status": "passed"}}}}
    assert gate.status_problems(new) == ["02-x netdryrun: verdict 'unsafe' doesn't match status 'passed'"]


def test_audit_f12_a_results_change_between_layers_is_code(monkeypatch):
    """Grok 7: corpus/*/results/ was treated as a record, so a results edit after the live layer moved its baseline."""
    calls = {"merge-base": "", "diff": "corpus/v2/results/results.json\nreleases/0.4.1/GATE.md"}
    monkeypatch.setattr(gate, "git", lambda *a: calls.get(a[0]))
    msg = gate.code_differs({"static": "b" * 40, "live": "a" * 40})
    assert msg and "corpus/v2/results/results.json" in msg
    calls["diff"] = "releases/0.4.1/GATE.md\ncorpus/v2/AMENDMENTS.md"
    # 2026-11-13: Markdown is prose-only only when no script or test names it (a gate script reads AMENDMENTS.md)
    from types import SimpleNamespace
    named = {"value": True}
    monkeypatch.setattr(gate, "run", lambda cmd, timeout=60: SimpleNamespace(code=0 if named["value"] else 1, out=""))
    assert "corpus/v2/AMENDMENTS.md" in gate.code_differs({"static": "b" * 40, "live": "a" * 40})
    named["value"] = False
    assert gate.code_differs({"static": "b" * 40, "live": "a" * 40}) is None


def test_audit_check_the_installed_package_path_is_read_strictly(tmp_path):
    """Code check of the audit fixes (#2): the package folder is the one absolute __init__.py line, whatever else is
    printed; none or two is unknown (and the corpus doesn't run)."""
    init = tmp_path / "venv" / "netdryrun" / "__init__.py"
    assert gate.installed_package_dir(f"some warning\n{init}\n") == init.parent
    assert gate.installed_package_dir(f"{init}\nDeprecationWarning: x\n") == init.parent
    assert gate.installed_package_dir("None\n") is None
    assert gate.installed_package_dir("netdryrun/__init__.py\n") is None   # relative: not a path we can trust
    assert gate.installed_package_dir(f"{init}\n{init}\n") is None


def test_audit_check_results_changes_are_code_only_for_the_layers_that_read_them(monkeypatch):
    """Code check of the audit fixes (#3): mutation and static never read corpus/*/results/, so a refresh there doesn't
    rerun them; live and unit do."""
    monkeypatch.setattr(gate, "git", lambda *a: {"merge-base": "", "diff": "corpus/v2/results/results.json"}.get(a[0]))
    assert gate.code_differs({"static": "b" * 40, "mutation": "a" * 40}) is None
    assert gate.code_differs({"static": "b" * 40, "unit": "a" * 40})
    assert gate.code_differs({"static": "b" * 40, "live": "a" * 40})
