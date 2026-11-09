"""scripts/gate_records.py and its release_gate.py wiring (0.4.2 step 2): one-command reruns of a single case, where a
rerun can never wash out a red, a host gap is never a verdict, and a flaky case can't be rerun until it passes."""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


gr = load("gate_records")
SHA = "a" * 40


def rec(checks, layer="live", sha=SHA):
    return {"layer": layer, "git": {"sha": sha, "dirty": False}, "checks": checks, "sections": []}


def chk(id_, status, ended=1000.0, seconds=10.0, severity="BLOCKER"):
    return {"id": id_, "title": id_, "severity": severity, "status": status, "seconds": seconds, "summary": "s",
            "output": "", "command": "", "ended": ended}


def put(out, checks, run_id="r1", sha=SHA, cases=None):
    return gr.append(out, rec(checks, sha=sha), commit=sha, key="k", run_id=run_id, cases=cases)


def test_an_attempt_is_never_overwritten(tmp_path):
    a = put(tmp_path, [chk("example-x", "PASS")])
    b = put(tmp_path, [chk("example-x", "PASS")])
    assert a != b and a.exists() and b.exists()
    assert len(gr.attempts(tmp_path, "live")) == 2


def test_a_fail_stays_fail_whatever_later_attempts_say(tmp_path):
    put(tmp_path, [chk("example-x", "FAIL")])
    put(tmp_path, [chk("example-x", "PASS")])
    v = gr.verdict(gr.attempts(tmp_path, "live"), SHA, taints_of=lambda _: [])
    assert v["checks"]["example-x"]["status"] == "FAIL"


def test_attempts_on_another_commit_count_for_nothing(tmp_path):
    put(tmp_path, [chk("example-x", "PASS")], sha="b" * 40)
    v = gr.verdict(gr.attempts(tmp_path, "live"), SHA, taints_of=lambda _: [])
    assert v["checks"] == {}


def test_a_pass_inside_a_host_gap_is_no_verdict_and_a_fail_there_still_fails(tmp_path):
    taint = [{"from": 995.0, "to": 1100.0, "seconds": 105.0}]
    put(tmp_path, [chk("example-x", "PASS", ended=1000.0), chk("example-y", "FAIL", ended=1000.0),
                   chk("example-z", "PASS", ended=2000.0)])
    v = gr.verdict(gr.attempts(tmp_path, "live"), SHA, taints_of=lambda _: taint)["checks"]
    assert v["example-x"]["status"] is None and v["example-x"]["tainted"] == 1
    assert v["example-y"]["status"] == "FAIL"           # a FAIL inside a gap still fails (Layer 6 on f220469)
    assert v["example-z"]["status"] == "PASS"


def test_a_case_gets_at_most_two_reruns_per_commit(tmp_path):
    for _ in range(3):
        put(tmp_path, [chk("example-x", "FAIL"), chk("example-x-clean", "PASS")])
    recs = gr.attempts(tmp_path, "live")
    assert gr.rerun_refused(recs, SHA, ["example-x", "example-y"]) == ["example-x"]
    assert gr.rerun_refused(recs, "b" * 40, ["example-x"]) == []          # a new commit (a fix) starts again


def test_resume_skips_only_what_this_run_finished_on_this_commit(tmp_path):
    put(tmp_path, [chk("example-x", "FAIL"), chk("corpus-v1", "PASS"), chk("corpus-v1-status", "PASS")], run_id="r1")
    put(tmp_path, [chk("example-y", "PASS")], run_id="other")
    put(tmp_path, [chk("example-z", "PASS")], run_id="r1", sha="b" * 40)
    done = gr.done_cases(gr.attempts(tmp_path, "live"), SHA, "r1")
    assert done == {"example-x", "corpus-v1"}


def test_case_of_keeps_a_corpus_whole():
    assert gr.case_of("corpus-v2-nondeterministic-held") == "corpus-v2"
    assert gr.case_of("example-frr-bgp-clean") == "example-frr-bgp"


def test_no_git_means_no_key_and_plan_calls_it_stale(tmp_path):
    assert gr.input_key(tmp_path) == "unknown"
    put(tmp_path, [chk("example-x", "PASS")])
    rows = dict((r[0], r[1]) for r in gr.plan_rows(tmp_path, ["live", "unit"], SHA, "unknown"))
    assert rows == {"live": "stale", "unit": "owed"}


def test_plan_shows_a_red_attempt_as_fail(tmp_path):
    put(tmp_path, [chk("example-x", "FAIL")])
    put(tmp_path, [chk("example-x", "PASS")])
    [(layer, state, detail)] = gr.plan_rows(tmp_path, ["live"], SHA, "k")
    assert state == "FAIL" and "example-x" in detail


# ---- release_gate.py wiring ---------------------------------------------------------------------------------------
@pytest.fixture
def gate(monkeypatch):
    g = load("release_gate")
    monkeypatch.setattr(g, "example_dirs", lambda: ["frr-bgp", "junos-frr"])
    monkeypatch.setattr(g, "git", lambda *a: SHA + "\n" if a[:1] == ("rev-parse",) else None)
    return g


def args_for(tmp_path, **kw):
    base = dict(layer="live", out=str(tmp_path), version="0.4.2", case=[], resume=False, run_id="", examples=[],
                strict=True, stranger_status=None)
    return argparse.Namespace(**{**base, **kw})


def test_case_selects_one_example_or_one_corpus(gate, tmp_path):
    a = args_for(tmp_path, case=["example:junos-frr", "corpus:v2"])
    assert gate.select_cases(a) is None
    assert a.selection == {"examples": {"junos-frr"}, "corpora": {"v2"}} and a.examples == ["junos-frr"]
    assert "unknown case" in gate.select_cases(args_for(tmp_path, case=["example:nope"]))
    assert "live layer only" in gate.select_cases(args_for(tmp_path, layer="unit", case=["corpus:v1"]))


def test_a_fourth_attempt_of_a_case_is_refused(gate, tmp_path):
    for _ in range(3):
        put(tmp_path, [chk("example-junos-frr", "FAIL")])
    assert "already ran 3 times" in gate.select_cases(args_for(tmp_path, case=["example:junos-frr"]))


def test_resume_needs_a_run_id_and_runs_only_the_rest(gate, tmp_path):
    assert "needs --run-id" in gate.select_cases(args_for(tmp_path, resume=True))
    put(tmp_path, [chk("example-frr-bgp", "PASS"), chk("corpus-v1", "FAIL")], run_id="night1")
    a = args_for(tmp_path, resume=True, run_id="night1")
    assert gate.select_cases(a) is None
    assert a.selection == {"examples": {"junos-frr"}, "corpora": {"v2"}}


def test_gate_md_keeps_an_earlier_fail_on_the_same_commit(gate, tmp_path):
    put(tmp_path, [chk("example-frr-bgp", "FAIL")])
    (tmp_path / "gate").mkdir(exist_ok=True)
    (tmp_path / "gate" / "live.json").write_text(json.dumps(
        {**rec([chk("example-frr-bgp", "PASS")]), "title": "Layer 5", "version": "0.4.2", "started": "x",
         "seconds": 1, "host": "h", "python": "3", "strict": True, "tools": {}}), encoding="utf-8")
    text, cleared = gate.render(args_for(tmp_path))
    assert not cleared and "failed in an earlier attempt on this commit" in text


def test_a_partial_run_updates_its_own_checks_and_keeps_the_others(gate, tmp_path, monkeypatch):
    monkeypatch.setattr(gate, "git_state", lambda: {"sha": SHA, "dirty": False})
    full = gate.Layer("live", args_for(tmp_path))
    full.add("example-frr-bgp", "example frr-bgp", "BLOCKER", True)
    full.add("example-junos-frr", "example junos-frr", "BLOCKER", False, "boot timed out")
    gate.save(full)
    a = args_for(tmp_path, case=["example:junos-frr"])
    assert gate.select_cases(a) is None
    part = gate.Layer("live", a)
    part.add("example-junos-frr", "example junos-frr", "BLOCKER", True)
    gate.save(part)
    saved = json.loads((tmp_path / "gate" / "live.json").read_text(encoding="utf-8"))
    assert {c["id"]: c["status"] for c in saved["checks"]} == {"example-frr-bgp": "PASS", "example-junos-frr": "PASS"}
    assert len(gr.attempts(tmp_path, "live")) == 2
    text, cleared = gate.render(args_for(tmp_path))     # the rerun passed, but the first attempt's FAIL stays
    assert not cleared and "failed in an earlier attempt on this commit" in text


# ---- Layer 6 on f220469 (cold review): a rerun, a taint, a lost record or a partial layer never washes out a red ----
def put_tree(out, checks, sha, tree, run_id="r1"):
    return gr.append(out, rec(checks, sha=sha), commit=sha, key="k", run_id=run_id, tree=tree)


def test_a_new_commit_with_the_same_tree_keeps_the_fail_and_the_attempts(tmp_path):
    """An empty commit (same tree) was a fresh start: the FAIL forgotten, 3 new attempts."""
    put_tree(tmp_path, [chk("example-x", "FAIL")], SHA, "t1")
    put_tree(tmp_path, [chk("example-x", "PASS")], "b" * 40, "t1")
    recs = gr.attempts(tmp_path, "live")
    assert gr.verdict(recs, "b" * 40, taints_of=lambda _: [], tree="t1")["checks"]["example-x"]["status"] == "FAIL"
    put_tree(tmp_path, [chk("example-x", "PASS")], "c" * 40, "t1")
    assert gr.rerun_refused(gr.attempts(tmp_path, "live"), "c" * 40, ["example-x"], tree="t1") == ["example-x"]
    assert gr.verdict(recs, "d" * 40, taints_of=lambda _: [], tree="t2")["checks"] == {}   # a real fix starts again


def test_a_tainted_fail_still_fails_and_every_taint_counts_as_an_attempt(tmp_path):
    """labrun --gap 0 made every check tainted: a FAIL was dropped and not counted, so it could be rerun into a PASS."""
    put(tmp_path, [chk("example-x", "FAIL", ended=1000.0)], run_id="g0")
    put(tmp_path, [chk("example-x", "PASS", ended=5000.0)], run_id="g0b")
    put(tmp_path, [chk("example-x", "PASS", ended=9000.0)], run_id="clean")
    taints = {"g0": [{"from": 0, "to": 2000}], "g0b": [{"from": 4000, "to": 6000}]}
    v = gr.verdict(gr.attempts(tmp_path, "live"), SHA, taints_of=lambda rid: taints.get(rid, []))
    assert v["checks"]["example-x"]["status"] == "FAIL" and v["attempts_per_case"]["example-x"] == 3


def test_an_unreadable_attempt_record_blocks(tmp_path):
    p = put(tmp_path, [chk("example-x", "FAIL")])
    p.write_bytes(p.read_bytes()[:-5])                      # truncated: it held a FAIL
    put(tmp_path, [chk("example-x", "PASS")])
    v = gr.verdict(gr.attempts(tmp_path, "live"), SHA, taints_of=lambda _: [])
    assert v["unreadable"] == [str(p)]
    [(layer, state, detail)] = gr.plan_rows(tmp_path, ["live"], SHA, "k")
    assert state == "FAIL" and "can't be read" in detail


def test_a_partial_live_layer_never_clears(gate, tmp_path, monkeypatch):
    """--case on a commit with no full live record saved a live.json of one check, and GATE.md showed no gap."""
    monkeypatch.setattr(gate, "git_state", lambda: {"sha": SHA, "dirty": False})
    a = args_for(tmp_path, case=["example:frr-bgp"])
    assert gate.select_cases(a) is None
    part = gate.Layer("live", a)
    part.add("example-frr-bgp", "example frr-bgp", "BLOCKER", True)
    gate.save(part)
    saved = json.loads((tmp_path / "gate" / "live.json").read_text(encoding="utf-8"))
    assert saved["partial"] is True
    text, cleared = gate.render(args_for(tmp_path))
    assert not cleared and "live/live-partial" in text
    full = gate.Layer("live", args_for(tmp_path))          # a full run clears the mark
    full.add("example-frr-bgp", "example frr-bgp", "BLOCKER", True)
    gate.save(full)
    assert "partial" not in json.loads((tmp_path / "gate" / "live.json").read_text(encoding="utf-8"))


def test_an_unreadable_record_blocks_gate_md(gate, tmp_path):
    p = put(tmp_path, [chk("example-frr-bgp", "FAIL")])
    p.write_bytes(p.read_bytes()[:-5])
    (tmp_path / "gate").mkdir(exist_ok=True)
    (tmp_path / "gate" / "live.json").write_text(json.dumps(
        {**rec([chk("example-frr-bgp", "PASS")]), "title": "Layer 5", "version": "0.4.2", "started": "x",
         "seconds": 1, "host": "h", "python": "3", "strict": True, "tools": {}}), encoding="utf-8")
    text, cleared = gate.render(args_for(tmp_path))
    assert not cleared and "attempt record can't be read" in text
