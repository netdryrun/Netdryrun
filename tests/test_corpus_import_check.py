"""corpus/run.py remedies FRR's import check on the lab it deploys, before any strategy runs.

Every strategy runs with deploy=False on the lab the harness deployed, and on a lab a run didn't deploy the runner only
detects a stuck import check (bgpd applied its `network` statements before zebra was up) and gives no verdict. The
harness is the deployer, so it applies the product's own remedy right after its deploy, as `netdryrun run` does on a lab
it deploys, and records what it found. Lab answers are the live FRR 10.4.1 captures of tests/test_frr_import_check.py
(corpus v2 case 18, pe1 on a stuck boot and after the remedy).
"""
from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

import netdryrun
from netdryrun.drivers import frr_import_check as ic
from netdryrun.lab import ExecResult, LabError, Node
from netdryrun.runner import driver_resolver

from test_frr_import_check import EMPTY_JSON, EMPTY_TEXT, REMEDIED_JSON, REMEDIED_TEXT
from test_frr_import_check import Lab as AnswerLab
from test_frr_import_check import live, node_answers

ROOT = Path(__file__).resolve().parent.parent
CASE = "18-aggregate-discard-route-removed"
FRR = "quay.io/frrouting/frr:10.4.1"
PE2 = {"config": live("c18_stuck_boot2", "pe2", ic.BGPD_CONFIG), "j": EMPTY_JSON, "t": EMPTY_TEXT,
       "sessions": live("c18_stuck_boot2", "pe2", ic.NEIGHBORS)}   # the same boot: pe2 has no `network` line


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


class FakeLab(AnswerLab):
    """One running lab for every strategy: pe1 and pe2 run FRR (pe2 has no import-check entries), h1 is a host whose
    image has no vtysh. `stuck`: pe1's import check is stuck at boot; `after`: what pe1 answers after the remedy."""

    def __init__(self, stuck=True, remedied=True, nodes=("pe1", "pe2", "h1")):
        answers = node_answers() if stuck else node_answers(j=REMEDIED_JSON, t=REMEDIED_TEXT)
        answers.update(node_answers(node="pe2", **PE2))
        after = node_answers(j=REMEDIED_JSON, t=REMEDIED_TEXT) if remedied else node_answers()
        after.update(node_answers(node="pe2", **PE2))
        super().__init__(answers, after=after)
        every = {"pe1": Node("pe1", "clab-t-pe1", "linux", FRR), "pe2": Node("pe2", "clab-t-pe2", "linux", FRR),
                 "h1": Node("h1", "clab-t-h1", "linux", "alpine:3")}
        self.nodes = {n: every[n] for n in nodes}
        self.events = []

    def exec(self, node, argv, timeout=60, input=None):
        if node == "h1":
            return ExecResult(argv, 127, "", ic.NO_VTYSH)
        return super().exec(node, argv, timeout, input)

    def deploy(self):
        self.events.append("deploy")

    def destroy(self):
        self.events.append("destroy")

    def version(self):
        return "0.0.0-fake"


def fake_run(lab, seen):
    """The runner on a lab it didn't deploy, as far as the import check goes: candidates() and guard(remedy=False)
    on the shared lab (runner.run), and a stuck import check is a run error, no verdict."""
    def run(config, *, deploy, settle, hold):
        assert deploy is False
        seen.append(config)
        try:
            ic.guard(lab, ic.candidates(lab, driver_resolver(config.drivers)), remedy=False, clock=lambda: 0.0,
                     sleep=lambda s: None)
        except ic.ImportCheckError as e:
            return SimpleNamespace(status="error", results=[], error=str(e), inconclusive_reason="")
        return SimpleNamespace(status="passed", results=[], error="", inconclusive_reason="")
    return run


def _evaluate(monkeypatch, tmp_path, lab, corpus_dir=ROOT / "corpus", module="corpus_run_ic"):
    mod = _load(corpus_dir / "run.py", module)
    seen = []
    monkeypatch.setattr(mod, "Lab", lambda topology: lab)
    monkeypatch.setattr(mod, "run", fake_run(lab, seen))
    (case,) = mod.load_cases(CASE[:2], corpus_dir / "v2")
    row = mod.evaluate(case, tmp_path / "work", keep=False, corpus=corpus_dir / "v2")
    return mod, row, seen


def test_a_stuck_boot_is_remedied_once_and_every_strategy_gets_a_verdict(monkeypatch, tmp_path, capsys):
    lab = FakeLab()
    mod, row, seen = _evaluate(monkeypatch, tmp_path, lab)
    assert len(lab.remedied) == 1 and lab.remedied[0][0] == "pe1"
    assert lab.events == ["deploy", "destroy"] and len(seen) == 3
    routers = row["import_check"]["routers"]
    assert row["import_check"]["error"] is None
    assert routers["pe1"].startswith("remedied: 192.0.2.0/24 in 'router bgp 65000' is not registered with zebra")
    assert routers["pe2"] == "registered" and "h1" not in routers
    assert row["_details"]["import_check"] == row["import_check"]
    for s in mod.STRATEGIES:
        assert row["strategies"][s]["status"] == "passed" and row["strategies"][s]["error"] is None
    assert "toggling it off and on" in capsys.readouterr().out


def test_without_the_harness_remedy_every_strategy_is_the_reported_error(monkeypatch, tmp_path):
    """The failure this fixes (red without the fix): the runner's own guard on a lab it didn't deploy."""
    lab = FakeLab()
    mod = _load(ROOT / "corpus" / "run.py", "corpus_run_ic_red")
    monkeypatch.setattr(mod, "remedy_import_check", lambda lab, configs: ({}, None))
    monkeypatch.setattr(mod, "Lab", lambda topology: lab)
    monkeypatch.setattr(mod, "run", fake_run(lab, []))
    (case,) = mod.load_cases(CASE[:2], ROOT / "corpus" / "v2")
    row = mod.evaluate(case, tmp_path / "work", keep=False, corpus=ROOT / "corpus" / "v2")
    for s in mod.STRATEGIES:
        assert row["strategies"][s]["verdict"] == "error"
        assert "stuck on a lab this run didn't deploy: pe1: 192.0.2.0/24" in row["strategies"][s]["error"]


def test_still_stuck_after_the_remedy_makes_every_strategy_an_error(monkeypatch, tmp_path):
    lab = FakeLab(remedied=False)
    mod, row, seen = _evaluate(monkeypatch, tmp_path, lab)
    assert seen == [] and lab.events == ["deploy", "destroy"]
    err = row["import_check"]["error"]
    assert "still stuck after the remedy" in err and "pe1: 192.0.2.0/24" in err
    for s in mod.STRATEGIES:
        assert row["strategies"][s] == {"verdict": "error", "status": "error", "correct": False,
                                        "failed_checks": [], "error": err}
        assert row["_details"][s]["status"] == "error"


def test_a_router_that_cannot_be_checked_makes_every_strategy_an_error(monkeypatch, tmp_path):
    """A node no driver claims that can't be told apart from FRR is "not checked": never a verdict here."""
    lab = FakeLab(stuck=False)
    lab.nodes["x1"] = Node("x1", "clab-t-x1", "linux", "example.com/router:1")
    mod, row, seen = _evaluate(monkeypatch, tmp_path, lab)
    assert seen == [] and lab.remedied == []
    assert row["import_check"]["routers"]["x1"].startswith("not checked")
    assert "could not be confirmed on every router" in row["import_check"]["error"]
    assert {row["strategies"][s]["verdict"] for s in mod.STRATEGIES} == {"error"}


def test_no_frr_router_is_a_no_op(monkeypatch, tmp_path):
    lab = FakeLab(nodes=("h1",))
    mod, row, seen = _evaluate(monkeypatch, tmp_path, lab)
    assert row["import_check"] == {"routers": {}, "error": None}
    assert lab.remedied == [] and [a for a in lab.asked if a[0] != "h1"] == []
    assert len(seen) == 3 and {row["strategies"][s]["status"] for s in mod.STRATEGIES} == {"passed"}


def test_a_healthy_boot_is_not_touched(monkeypatch, tmp_path):
    lab = FakeLab(stuck=False)
    mod, row, seen = _evaluate(monkeypatch, tmp_path, lab)
    assert lab.remedied == [] and row["import_check"]["routers"] == {"pe1": "registered", "pe2": "registered"}
    assert len(seen) == 3


def test_a_nondeterministic_run_keeps_its_own_import_check_record(monkeypatch, tmp_path):
    """Each run of a nondeterministic case deploys its own lab: its record goes into that run's details."""
    labs = [FakeLab(), FakeLab(stuck=False)]
    mod = _load(ROOT / "corpus" / "run.py", "corpus_run_ic_nd")
    monkeypatch.setattr(mod, "Lab", lambda topology: labs[0] if labs[0].events == [] else labs[1])
    monkeypatch.setattr(mod, "run", lambda config, **kw: SimpleNamespace(status="passed", results=[], error="",
                                                                       inconclusive_reason=""))
    (case,) = mod.load_cases(CASE[:2], ROOT / "corpus" / "v2")
    rows = [mod.evaluate_run(case, tmp_path / "work", False, ROOT / "corpus" / "v2") for _ in labs]
    details = [r.pop("_details") for r in rows]
    assert details[0]["import_check"]["routers"]["pe1"].startswith("remedied")
    assert details[1]["import_check"]["routers"]["pe1"] == "registered"


def test_strategies_with_different_drivers_are_a_case_error():
    mod = _load(ROOT / "corpus" / "run.py", "corpus_run_ic_drv")
    configs = {"a": SimpleNamespace(drivers={}), "b": SimpleNamespace(drivers={"pe1": "frr"})}
    with pytest.raises(mod.CaseError, match="different node drivers"):
        mod.remedy_import_check(FakeLab(), configs)


DRIVER = """
import importlib.util, json, sys
from types import SimpleNamespace
sys.path.insert(0, sys.argv[2])
import test_corpus_import_check as t
from netdryrun.drivers import frr_import_check as ic
ic.SAMPLE_GAP = 0.0
spec = importlib.util.spec_from_file_location("corpus_run", sys.argv[1])
mod = importlib.util.module_from_spec(spec)
sys.modules["corpus_run"] = mod
spec.loader.exec_module(mod)
lab = t.FakeLab()
seen = []
mod.Lab = lambda topology: lab
mod.run = t.fake_run(lab, seen)
sys.argv = ["run.py", "--case", "01", "--workdir", sys.argv[3]]
rc = mod.main()
print("RESULT " + json.dumps({"rc": rc, "remedied": [n for n, _ in lab.remedied], "strategies": len(seen),
                              "here": str(mod.HERE)}))
"""


def test_run_py_from_a_scratch_copy_remedies_as_the_release_gate_runs_it(tmp_path):
    """The release gate's live layer copies corpus/ alone (no src/ or scripts/ beside it) and runs run.py with the
    tested wheel's python (scripts/release_gate.py live_corpora): the same shape here, in a subprocess."""
    copy = tmp_path / "gate" / "corpus"
    shutil.copytree(ROOT / "corpus", copy)
    driver = tmp_path / "driver.py"
    driver.write_text(DRIVER, encoding="utf-8")
    env = dict(os.environ, NDR_VERDICT_TREE="0" * 64,
               PYTHONPATH=str(Path(netdryrun.__file__).resolve().parent.parent))
    r = subprocess.run([sys.executable, str(driver), str(copy / "run.py"), str(ROOT / "tests"), str(tmp_path / "w")],
                       capture_output=True, text=True, cwd=tmp_path, env=env, timeout=120)
    assert r.returncode == 0, r.stderr
    result = json.loads(r.stdout.rsplit("RESULT ", 1)[1])
    assert result == {"rc": 0, "remedied": ["pe1"], "strategies": 3, "here": str(copy)}
    out = r.stdout.split("RESULT ")[0]
    assert "   ping=safe  sessions=safe  netdryrun=safe" in out
    assert '"import_check"' in out and "remedied: 192.0.2.0/24" in out


class CrashLab(FakeLab):
    """`exec` on pe1 fails the way a dead container does (docker exec fails), so the remedy itself crashes."""

    def exec(self, node, argv, timeout=60, input=None):
        if node == "pe1":
            raise LabError("docker exec failed")
        return super().exec(node, argv, timeout, input)


def _evaluate_run(monkeypatch, tmp_path, lab, run=None, module="corpus_run_ic_crash"):
    mod = _load(ROOT / "corpus" / "run.py", module)
    monkeypatch.setattr(mod, "Lab", lambda topology: lab)
    monkeypatch.setattr(mod, "run", run or fake_run(lab, []))
    (case,) = mod.load_cases(CASE[:2], ROOT / "corpus" / "v2")
    return mod, mod.evaluate_run(case, tmp_path / "work", False, ROOT / "corpus" / "v2")


def _crash_record(mod, row):
    for s in mod.STRATEGIES:
        assert row["strategies"][s]["status"] == "error"
        assert row["_details"][s]["status"] == "error"
    assert row["_details"]["import_check"] == row["import_check"]
    return row["import_check"]


def test_a_remedy_that_crashes_still_records_the_import_check(monkeypatch, tmp_path):
    """A crash inside the remedy (a LabError from lab.exec) is the run that most needs its evidence: the row and that
    run's details both record the import check with the crash, never no record at all."""
    lab = CrashLab()
    mod, row = _evaluate_run(monkeypatch, tmp_path, lab)
    rec = _crash_record(mod, row)
    assert rec["routers"] == {}
    assert "crashed" in rec["error"] and "LabError: docker exec failed" in rec["error"]
    assert lab.events == ["deploy", "destroy"]


def test_a_crash_before_the_remedy_records_that_the_import_check_was_not_reached(monkeypatch, tmp_path):
    lab = FakeLab()

    def deploy():
        raise LabError("containerlab deploy failed")
    lab.deploy = deploy
    mod, row = _evaluate_run(monkeypatch, tmp_path, lab, module="corpus_run_ic_crash2")
    rec = _crash_record(mod, row)
    assert rec["routers"] == {} and "not reached" in rec["error"] and "containerlab deploy failed" in rec["error"]


def test_a_crash_after_the_remedy_keeps_what_the_remedy_found(monkeypatch, tmp_path):
    lab = FakeLab()

    def run(config, **kw):
        raise LabError("docker exec failed")
    mod, row = _evaluate_run(monkeypatch, tmp_path, lab, run=run, module="corpus_run_ic_crash3")
    rec = _crash_record(mod, row)
    assert rec["routers"]["pe1"].startswith("remedied") and rec["routers"]["pe2"] == "registered"
    assert rec["error"] is None   # the import check itself was fine; the crash is in every strategy's error
    assert "LabError: docker exec failed" in row["strategies"]["netdryrun"]["error"]
