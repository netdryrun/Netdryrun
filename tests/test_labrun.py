"""scripts/labrun.py (0.4.2 step 1): a long gate run can't die, stall or start with SIGINT ignored unnoticed, a pause
never counts against a timeout, and `stop` takes the whole run down. Each test is a failure 0.4.1 actually had."""
from __future__ import annotations

import importlib.util
import json
import os
import signal
import subprocess
import sys
import textwrap
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
posix = pytest.mark.skipif(os.name != "posix", reason="process groups and signals: POSIX only")


def load(name):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


labrun = load("labrun")


def child(tmp_path: Path, body: str) -> list[str]:
    """A tiny run that uses labrun's run-side helpers the way release_gate.py does."""
    p = tmp_path / "child.py"
    p.write_text(f"import sys, time, signal, json, os\nsys.path.insert(0, {str(SCRIPTS)!r})\nimport labrun\n"
                 + textwrap.dedent(body), encoding="utf-8")
    return [sys.executable, str(p)]


def start(tmp_path, cmd, *extra, preexec=None) -> tuple[int, dict]:
    state = tmp_path / "state"
    env = {**os.environ, "LABRUN_TICK": "0.2"}
    r = subprocess.run([sys.executable, str(SCRIPTS / "labrun.py"), "--state", str(state), "start", "--id", "t",
                        "--receipt-timeout", "3", "--stale", "2", "--gap", "60", *extra, "--", *cmd],
                       capture_output=True, text=True, env=env, timeout=60, preexec_fn=preexec)
    return r.returncode, {"dir": state / "t", "out": r.stdout + r.stderr, "state": state}


def result(d: Path, timeout=30) -> dict:
    t0 = time.time()
    while time.time() - t0 < timeout:
        res = labrun.read_json(d / "result.json")
        if res:
            return res
        time.sleep(0.2)
    raise AssertionError(f"no result.json in {d}")


@posix
def test_a_run_that_writes_its_receipt_and_finishes_is_ok(tmp_path):
    rc, s = start(tmp_path, child(tmp_path, """
        labrun.receipt(layer="live")
        labrun.done(0, "fine")
    """))
    assert rc == 0, s["out"]
    res = result(s["dir"])
    assert res["state"] == "ok" and res["done"]["summary"] == "fine"


@posix
def test_a_run_that_dies_before_its_receipt_is_reported_by_start_itself(tmp_path):
    """26380cb's first try failed at 0.0 s and today's SR Linux launch never ran: `start` must say so, at once."""
    rc, s = start(tmp_path, child(tmp_path, "sys.exit(3)\n"))
    assert rc == 1 and "launch-failed" in s["out"]
    assert result(s["dir"])["state"] == "launch-failed"


@posix
def test_no_receipt_within_the_timeout_is_a_failed_launch_and_the_run_is_killed(tmp_path):
    rc, s = start(tmp_path, child(tmp_path, "time.sleep(600)\n"))
    assert rc == 1
    res = result(s["dir"])
    assert res["state"] == "launch-failed" and "no receipt" in res["why"]
    pgid = labrun.read_json(s["dir"] / "run.json")["pgid"]
    assert not labrun.group_alive(pgid)


@posix
def test_an_exit_after_the_receipt_without_done_is_never_ok(tmp_path):
    rc, s = start(tmp_path, child(tmp_path, """
        labrun.receipt()
        time.sleep(0.5)
        sys.exit(0)
    """))
    assert rc == 0
    res = result(s["dir"])
    assert res["state"] == "exited-without-result" and res["rc"] == 0


@posix
def test_a_run_whose_heartbeat_stops_is_stalled_and_killed(tmp_path):
    rc, s = start(tmp_path, child(tmp_path, """
        labrun.receipt()
        time.sleep(600)
    """))
    assert rc == 0
    res = result(s["dir"])
    assert res["state"] == "stalled"
    assert not labrun.group_alive(labrun.read_json(s["dir"] / "run.json")["pgid"])


@posix
def test_the_run_gets_sigint_at_its_default_even_from_a_launcher_that_ignores_it(tmp_path):
    """G2, 7532310 and 26380cb: a launcher's `&` left SIGINT ignored for the whole tree."""
    def ignore():
        signal.signal(signal.SIGINT, signal.SIG_IGN)
        signal.signal(signal.SIGQUIT, signal.SIG_IGN)
    rc, s = start(tmp_path, child(tmp_path, """
        # Python installs its own SIGINT handler at start unless SIGINT is ignored, so "not ignored" is the test
        ok = signal.getsignal(signal.SIGINT) is not signal.SIG_IGN and signal.getsignal(signal.SIGQUIT) is signal.SIG_DFL
        labrun.receipt(sigint_default=ok)
        labrun.done(0)
    """), preexec=ignore)
    assert rc == 0, s["out"]
    assert labrun.read_json(s["dir"] / "receipt.json")["sigint_default"] is True


@posix
def test_stop_takes_the_whole_process_group_down(tmp_path):
    rc, s = start(tmp_path, child(tmp_path, """
        import subprocess
        subprocess.Popen([sys.executable, "-c", "import time; time.sleep(600)"])   # a grandchild, like a lab tool
        labrun.HEART = labrun.Heartbeat(every=0.3).start()
        labrun.receipt()
        time.sleep(600)
    """))
    assert rc == 0
    pgid = labrun.read_json(s["dir"] / "run.json")["pgid"]
    r = subprocess.run([sys.executable, str(SCRIPTS / "labrun.py"), "--state", str(s["state"]), "stop", "t"],
                       capture_output=True, text=True, timeout=60)
    assert r.returncode == 0 and "is gone" in r.stdout
    assert not labrun.group_alive(pgid)
    assert result(s["dir"])["state"] == "stopped"


@posix
def test_a_paused_run_holds_at_a_case_boundary_and_keeps_beating(tmp_path):
    """The old pause SIGSTOPped the tree and its timeouts kept counting; now the run holds between cases, alive."""
    rc, s = start(tmp_path, child(tmp_path, """
        labrun.HEART = labrun.Heartbeat(every=0.3).start()
        labrun.receipt()
        open(os.path.join(os.environ["LABRUN_DIR"], "pause"), "w").close()
        held = labrun.hold_if_paused(poll=0.2)
        labrun.done(0, f"held {held:.1f}")
    """))
    assert rc == 0
    d = s["dir"]
    time.sleep(3)                                    # longer than --stale: a held run must not be called stalled
    assert labrun.read_json(d / "heartbeat.json")["held"] is True
    assert not (d / "result.json").exists()
    (d / "pause").unlink()
    res = result(d)
    assert res["state"] == "ok" and float(res["done"]["summary"].split()[1]) >= 2


# ---- the watcher's clock rules, with a fake clock -----------------------------------------------------------------
class FakeProc:
    def __init__(self, polls):
        self.polls, self.pid, self.returncode = list(polls), 4242, None

    def poll(self):
        v = self.polls.pop(0) if self.polls else 0
        if v is not None:
            self.returncode = v
        return v

    def wait(self):
        return self.returncode


def test_a_gap_in_the_watchers_own_clock_is_a_taint_not_a_stall(tmp_path, monkeypatch):
    """Host sleep or a frozen WSL VM: the watcher sees its own wall clock jump. That interval is recorded as a taint
    (cases in it are no verdict) and the run gets a full --stale to beat again, instead of being killed as stalled."""
    d = tmp_path / "r"
    d.mkdir()
    times = iter([1000.0, 1002.0, 1004.0, 1300.0, 1302.0, 1304.0, 1306.0, 1307.0])   # 296 s jump between 1004 and 1300
    clock = lambda: next(times)                                                # noqa: E731

    def popen(*a, **k):
        labrun.write_json(d / "receipt.json", {"wall": 1000.0})
        labrun.write_json(d / "heartbeat.json", {"wall": 1004.0})
        return FakeProc([None, None, None, None, None, 0])

    def on_exit():
        labrun.write_json(d / "done.json", {"code": 0})
    monkeypatch.setattr(labrun, "kill_group", lambda *a, **k: True)
    sleeps = []
    res = labrun.watch(d, ["x"], receipt_timeout=90, stale=90, gap=60, clock=clock,
                       sleep=lambda s: (sleeps.append(s), len(sleeps) == 5 and on_exit()), popen=popen)
    assert res["state"] == "ok", res
    assert res["taints"] == [{"from": 1004.0, "to": 1300.0, "seconds": 296.0}]


def test_release_gate_gives_no_receipt_when_g2_fails(tmp_path, monkeypatch):
    monkeypatch.setenv("LABRUN_DIR", str(tmp_path))
    gate = load("release_gate")
    monkeypatch.setattr(gate, "harness_problem", lambda: "SIGINT is ignored")
    args = type("A", (), {"layer": "live", "version": "0.4.2"})()
    assert gate.labrun_begin(args) == 2
    assert not (tmp_path / "receipt.json").exists()
    assert json.loads((tmp_path / "done.json").read_text())["code"] == 2


def test_release_gate_writes_receipt_heartbeat_and_done(tmp_path, monkeypatch):
    monkeypatch.setenv("LABRUN_DIR", str(tmp_path))
    gate = load("release_gate")
    monkeypatch.setattr(gate, "harness_problem", lambda: None)
    args = type("A", (), {"layer": "live", "version": "0.4.2"})()
    assert gate.labrun_begin(args) is None
    assert (tmp_path / "receipt.json").exists() and (tmp_path / "heartbeat.json").exists()
    gate.lab_boundary("example frr-bgp")
    assert json.loads((tmp_path / "heartbeat.json").read_text())["phase"] == "example frr-bgp"
    gate.labrun_end(0, "gate: no BLOCKER failed")
    assert json.loads((tmp_path / "done.json").read_text())["code"] == 0


def test_outside_labrun_the_gate_hooks_do_nothing(tmp_path, monkeypatch):
    monkeypatch.delenv("LABRUN_DIR", raising=False)
    gate = load("release_gate")
    assert gate.labrun_begin(type("A", (), {"layer": "static", "version": "x"})()) is None
    gate.lab_boundary("x")
    gate.labrun_end(0, "x")
    assert not list(tmp_path.iterdir())
