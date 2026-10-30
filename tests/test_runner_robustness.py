"""Runner robustness and timing, on fake labs, fake drivers and a fake clock (no containers).

Each test here reproduces a finding of the pre-launch code audit (C-code.md): scenario checks passing on the
state from before the fault (B5), post-convergence checks starting before every BGP session is up (M3),
SIGTERM leaving the lab running (M1), crashes exiting 1 with no report (M2), a negative ping failing when the
destination has no route (M5), and two runs of the same lab colliding.
"""
from __future__ import annotations

import ipaddress
import json
import os
import signal
import subprocess
import sys
import textwrap
from pathlib import Path
from types import SimpleNamespace

import pytest

import netdryrun
from netdryrun import checks as checks_mod
from netdryrun import runner
from netdryrun.checks import _ping
from netdryrun.cli import main
from netdryrun.config import Check, Config, Fault, Scenario
from netdryrun.drivers.base import BgpNeighbor, DriverError, Observation, Route
from netdryrun.lab import ExecResult, Lab, LabError, Node

PKG_ROOT = str(Path(netdryrun.__file__).resolve().parent.parent)


# ----------------------------------------------------------------------------------------------- fakes

class World:
    """The fake clock, and when the fault went in (so the fake network can react to it with a delay)."""

    def __init__(self):
        self.t = 0.0
        self.fault_at = None
        self.links = []   # (t, node, iface, up)

    def __call__(self):
        return self.t

    def sleep(self, s):
        self.t += max(0.0, s)

    def since_fault(self):
        return None if self.fault_at is None else self.t - self.fault_at

    def faulted_for(self, seconds):
        s = self.since_fault()
        return s is not None and s >= seconds


class FakeLab:
    def __init__(self, world, nodes=("r1", "r2", "r3"), existing=(), deploy_error=None):
        self.world, self.name, self.topology = world, "t", Path("t.clab.yml")
        self.nodes = {n: Node(n, f"clab-t-{n}", "linux", "quay.io/frrouting/frr:10.4.1") for n in nodes}
        self.links = [(("r1", "eth1"), ("r2", "eth1")), (("r2", "eth2"), ("r3", "eth1"))]
        self.existing, self.deploy_error = set(existing), deploy_error
        self.deployed = self.destroyed = 0
        self.locked = False

    def check_tools(self):
        pass

    def version(self):
        return "test"

    def acquire_lock(self):
        self.locked = True

    def release_lock(self):
        self.locked = False

    def existing_containers(self):
        return self.existing

    def deploy(self):
        self.deployed += 1
        if self.deploy_error:
            raise self.deploy_error
        return ExecResult([], 0, "", "")

    def destroy(self):
        self.destroyed += 1
        return ExecResult([], 0, "", "")

    def running_containers(self):
        return {n.container for n in self.nodes.values()}

    def boot_log(self, node):   # a clean FRR boot: every config line loaded
        return ExecResult([], 0, "[45|bgpd] done", "")

    def run_setup(self, *a, **k):
        pass

    def _require_linux_links(self, node):
        pass

    def data_interfaces(self, node):
        return ["eth1"]

    def set_link(self, node, iface, up):
        self.world.links.append((self.world.t, node, iface, up))
        if not up and self.world.fault_at is None:
            self.world.fault_at = self.world.t
        if up:
            self.world.fault_at = None
        return ExecResult([], 0, "", "")

    def interface_addresses(self, node, iface):
        return [ipaddress.ip_interface("10.0.12.1/30")] if (node, iface) == ("r1", "eth1") else []

    def peers_of(self, node, iface):
        return Lab.peers_of(self, node, iface)


class FakeDriver:
    """State as functions of the world: neighbors(world) -> {addr: state}, routes(world, prefix) -> bool."""

    def __init__(self, world, neighbors=lambda w: {}, routes=lambda w, prefix: True, neighbors_error=None,
                 ping=None):
        self.world, self._neighbors, self._routes = world, neighbors, routes
        self.neighbors_error, self._ping = neighbors_error, ping

    def bgp_neighbors(self, vrf="default"):
        if self.neighbors_error:
            raise self.neighbors_error
        return Observation({a: BgpNeighbor(a, s, {"ipv4-unicast": 3}) for a, s in self._neighbors(self.world).items()}, [])

    def routes(self, prefix, vrf="default"):
        return Observation([Route(prefix, "bgp", True)] if self._routes(self.world, prefix) else [], [])

    def ping(self, target, source, count, vrf="default"):
        return self._ping(self.world)


def install(monkeypatch, world, lab, drivers):
    """Drive the runner on the fake clock. Works with any runner that waits through checks.* and time.sleep."""
    monkeypatch.setattr(runner, "_clock", world, raising=False)
    monkeypatch.setattr(runner, "_sleep", world.sleep, raising=False)
    monkeypatch.setattr(runner, "time", SimpleNamespace(sleep=world.sleep, monotonic=world))
    for name in ("run_round_robin", "hold_together"):
        orig = getattr(checks_mod, name)
        monkeypatch.setattr(runner, name,
                            lambda *a, _o=orig, **k: _o(*a, **{**k, "clock": world, "sleep": world.sleep}))
    monkeypatch.setattr(runner, "Lab", lambda path: lab)
    monkeypatch.setattr(runner, "for_node", lambda lab_, node, override=None: drivers[node])


def chk(ctype, name, timeout=120, **params):
    return Check(type=ctype, params=params, name=name, timeout=timeout)


def cfg(tmp_path, checks, scenarios=()):
    return Config(path=tmp_path / "netdryrun.yml", lab=tmp_path / "t.clab.yml", timeout=120, checks=list(checks),
                  scenarios=list(scenarios))


def by_name(rep):
    return {r.check.name: r for r in rep.results}


ALWAYS = chk("route", "baseline: r3 has 10.9.9.0/24", node="r3", prefix="10.9.9.0/24")


# ------------------------------------------------------------ B5: scenario checks vs pre-fault state

def _redundancy_scenario(timeout=30):
    return Scenario(name="r1-r2 fails", faults=[Fault("link_down", "r1", "eth1")],
                    checks=[chk("route", "[r1-r2 fails] r3 keeps 10.1.0.0/24", timeout=timeout,
                                node="r3", prefix="10.1.0.0/24")])


@pytest.mark.parametrize("settle", [10.0, 0.0])
def test_scenario_positive_cannot_pass_on_pre_fault_state(tmp_path, monkeypatch, settle):
    # The audit's probe: the route is still there at t=0 and t=3 after the link goes down, and disappears at
    # t=5 for good (no backup path; the failure is detected late). It used to pass after 3 s.
    w = World()

    def routes(world, prefix):
        return prefix == "10.9.9.0/24" or not world.faulted_for(5)

    drivers = {n: FakeDriver(w, routes=routes) for n in ("r1", "r2", "r3")}
    install(monkeypatch, w, FakeLab(w), drivers)
    rep = runner.run(cfg(tmp_path, [ALWAYS], [_redundancy_scenario()]), deploy=False, settle=settle, hold=10)
    r = by_name(rep)["[r1-r2 fails] r3 keeps 10.1.0.0/24"]
    assert not r.passed, r.detail
    assert rep.status == "failed"


def test_scenario_waits_for_the_fault_to_show_in_bgp(tmp_path, monkeypatch):
    # Behind a bridge, BGP notices the failure only when the hold timer expires (here 40 s after the link
    # goes down) and the route disappears 2 s later. Settle and hold windows alone (10 s each) would pass it.
    w = World()
    down = lambda world: "idle" if world.faulted_for(40) else "established"  # noqa: E731
    neighbors = {"r1": lambda world: {"10.0.12.2": down(world)}, "r2": lambda world: {"10.0.12.1": down(world)},
                 "r3": lambda world: {}}

    def routes(world, prefix):
        return prefix == "10.9.9.0/24" or not world.faulted_for(42)

    drivers = {n: FakeDriver(w, neighbors=neighbors[n], routes=routes) for n in ("r1", "r2", "r3")}
    logs = []
    install(monkeypatch, w, FakeLab(w), drivers)
    rep = runner.run(cfg(tmp_path, [ALWAYS], [_redundancy_scenario(timeout=120)]), deploy=False, settle=10, hold=10,
                     log=logs.append)
    assert not by_name(rep)["[r1-r2 fails] r3 keeps 10.1.0.0/24"].passed
    assert rep.status == "failed"
    assert any("took effect" in m for m in logs)


def test_scenario_errors_when_the_fault_never_shows(tmp_path, monkeypatch):
    w = World()
    neighbors = {"r1": lambda world: {"10.0.12.2": "established"}, "r2": lambda world: {"10.0.12.1": "established"},
                 "r3": lambda world: {}}
    drivers = {n: FakeDriver(w, neighbors=neighbors[n]) for n in ("r1", "r2", "r3")}
    install(monkeypatch, w, FakeLab(w), drivers)
    rep = runner.run(cfg(tmp_path, [ALWAYS], [_redundancy_scenario(timeout=30)]), deploy=False)
    assert rep.status == "error" and rep.exit_code == 2
    assert "did not take effect within 30s" in rep.error and "r2 -> 10.0.12.1" in rep.error
    assert w.links[-1][3] is True   # the link was restored


def test_real_redundancy_still_passes(tmp_path, monkeypatch):
    w = World()
    down = lambda world: "idle" if world.faulted_for(2) else "established"  # noqa: E731
    neighbors = {"r1": lambda world: {"10.0.12.2": down(world)}, "r2": lambda world: {"10.0.12.1": down(world)},
                 "r3": lambda world: {}}
    drivers = {n: FakeDriver(w, neighbors=neighbors[n]) for n in ("r1", "r2", "r3")}
    install(monkeypatch, w, FakeLab(w), drivers)
    rep = runner.run(cfg(tmp_path, [ALWAYS], [_redundancy_scenario()]), deploy=False, settle=10, hold=10)
    assert rep.status == "passed", [(r.check.name, r.detail) for r in rep.results]
    r = by_name(rep)["[r1-r2 fails] r3 keeps 10.1.0.0/24"]
    assert "held" in r.detail and r.history[0]["t"] >= 0


def test_peers_of_follows_links_through_bridges(tmp_path):
    topo = tmp_path / "t.clab.yml"
    topo.write_text(textwrap.dedent("""\
        name: t
        topology:
          nodes:
            r1: {kind: linux}
            r2: {kind: linux}
            r3: {kind: linux}
            br: {kind: bridge}
          links:
            - endpoints: ["r1:eth1", "br:p1"]
            - endpoints: ["r2:eth1", "br:p2"]
            - endpoints: [{node: r3, interface: eth1}, {node: br, interface: p3}]
            - endpoints: ["r1:eth2", "r3:eth2"]
        """))
    lab = Lab(topo)
    assert sorted(lab.peers_of("r1", "eth1")) == [("r2", "eth1"), ("r3", "eth1")]
    assert lab.peers_of("r1", "eth2") == [("r3", "eth2")]


# ------------------------------------------------- M3: post-convergence checks wait for every session

def test_negative_check_waits_for_every_bgp_session_on_its_node(tmp_path, monkeypatch):
    # The audit's probe: the checked r1-r2 session is up at t=5; r3's session to r2, which carries the leak,
    # only comes up at t=50. The negative check used to finish at t=29 and pass.
    w = World()
    neighbors = {"r1": lambda world: {"10.0.12.2": "established" if world.t >= 5 else "active"},
                 "r3": lambda world: {"10.0.23.2": "established" if world.t >= 50 else "active"}}

    def routes(world, prefix):
        return world.t >= 50   # the leak arrives with the r2-r3 session

    drivers = {n: FakeDriver(w, neighbors=neighbors[n], routes=routes) for n in ("r1", "r3")}
    install(monkeypatch, w, FakeLab(w, nodes=("r1", "r2", "r3")), drivers)
    checks = [chk("bgp_session", "r1-r2 up", node="r1", neighbor="10.0.12.2", state="established"),
              chk("route", "r3 never gets the leak", node="r3", prefix="10.66.0.0/16", present=False)]
    rep = runner.run(cfg(tmp_path, checks), deploy=False, settle=10, hold=10)
    leak = by_name(rep)["r3 never gets the leak"]
    assert not leak.passed and "unexpectedly present" in leak.detail
    assert rep.status == "failed"


def test_negative_check_not_evaluated_if_its_node_never_converges(tmp_path, monkeypatch):
    w = World()
    neighbors = {"r1": lambda world: {"10.0.12.2": "established"}, "r3": lambda world: {"10.0.23.2": "active"}}
    drivers = {n: FakeDriver(w, neighbors=neighbors[n], routes=lambda world, p: False) for n in ("r1", "r3")}
    install(monkeypatch, w, FakeLab(w), drivers)
    checks = [chk("bgp_session", "r1-r2 up", node="r1", neighbor="10.0.12.2", state="established"),
              chk("route", "r3 never gets the leak", timeout=60, node="r3", prefix="10.66.0.0/16", present=False)]
    rep = runner.run(cfg(tmp_path, checks), deploy=False)
    leak = by_name(rep)["r3 never gets the leak"]
    assert not leak.passed and leak.detail.startswith("not evaluated") and "10.0.23.2 (active)" in leak.detail
    assert rep.status == "failed"


def test_sessions_expected_down_and_non_bgp_nodes_dont_block_the_gate(tmp_path, monkeypatch):
    w = World()
    neighbors = {"r1": lambda world: {"10.0.12.2": "established"},
                 "r3": lambda world: {"10.0.23.2": "established", "10.0.99.9": "idle"}}
    drivers = {n: FakeDriver(w, neighbors=neighbors[n], routes=lambda world, p: False) for n in ("r1", "r3")}
    drivers["h1"] = FakeDriver(w, neighbors_error=DriverError("bgpd is not running"),
                               ping=lambda world: Observation((3, 0), []))
    install(monkeypatch, w, FakeLab(w, nodes=("r1", "r3", "h1")), drivers)
    checks = [chk("bgp_session", "r1-r2 up", node="r1", neighbor="10.0.12.2", state="established"),
              chk("bgp_session", "r3 old peer gone", node="r3", neighbor="10.0.99.9", state="down"),
              chk("route", "r3 never gets the leak", node="r3", prefix="10.66.0.0/16", present=False),
              chk("ping", "h1 cannot reach", node="h1", target="10.9.9.9", expect="failure")]
    rep = runner.run(cfg(tmp_path, checks), deploy=False, settle=10, hold=10)
    assert rep.status == "passed", [(r.check.name, r.detail) for r in rep.results]
    assert w.t < 60   # the ping-only host did not make the run wait for its timeout


# --------------------------------------------------------------------------- M1: signals clean up

SIGNAL_SCRIPT = textwrap.dedent("""\
    import os, signal, sys
    from pathlib import Path
    import netdryrun.runner as runner
    from netdryrun.cli import main
    from netdryrun.drivers.base import BgpNeighbor, Observation
    from netdryrun.lab import ExecResult, Node

    folder, sig = Path(sys.argv[1]), getattr(signal, sys.argv[2])

    class Lab:
        def __init__(self, path):
            self.name, self.topology = "t", path
            self.nodes = {"r1": Node("r1", "clab-t-r1", "linux", "frr")}
        def check_tools(self): pass
        def version(self): return "test"
        def acquire_lock(self): pass
        def release_lock(self): pass
        def existing_containers(self): return set()
        def deploy(self): return ExecResult([], 0, "", "")
        def destroy(self):
            (folder / "destroyed").write_text("yes")
            return ExecResult([], 0, "", "")
        def running_containers(self): return {"clab-t-r1"}

    class Driver:
        def bgp_neighbors(self, vrf="default"):
            os.kill(os.getpid(), sig)   # the signal arrives while the checks run
            return Observation({"10.0.0.2": BgpNeighbor("10.0.0.2", "established")}, [])

    runner.Lab = Lab
    runner.for_node = lambda lab, node, override=None: Driver()
    sys.exit(main(["run", str(folder), "--json", str(folder / "report.json"), "--no-step-summary"]))
    """)


def _lab_folder(tmp_path):
    (tmp_path / "t.clab.yml").write_text("name: t\ntopology:\n  nodes:\n    r1: {kind: linux, image: frr}\n")
    (tmp_path / "netdryrun.yml").write_text(
        "lab: t.clab.yml\nchecks:\n  - {type: bgp_session, node: r1, neighbor: 10.0.0.2}\n")
    return tmp_path


@pytest.mark.skipif(os.name != "posix", reason="POSIX signals")
@pytest.mark.parametrize("sig,code", [("SIGTERM", 143), ("SIGHUP", 129), ("SIGINT", 130)])
def test_signals_destroy_the_lab_and_exit_with_a_defined_code(tmp_path, sig, code):
    folder = _lab_folder(tmp_path)
    script = tmp_path / "drive.py"
    script.write_text(SIGNAL_SCRIPT)
    env = {**os.environ, "PYTHONPATH": PKG_ROOT + os.pathsep + os.environ.get("PYTHONPATH", ""), "CI": "1"}
    env.pop("GITHUB_STEP_SUMMARY", None)
    p = subprocess.run([sys.executable, str(script), str(folder), sig], capture_output=True, text=True, env=env,
                       timeout=60)
    assert p.returncode == code, p.stderr
    assert (folder / "destroyed").exists(), "the lab was left running"
    assert "Interrupted: no verdict" in p.stderr and "Traceback" not in p.stderr
    data = json.loads((folder / "report.json").read_text())
    assert data["status"] == "error" and sig in data["error"]


def test_mcp_server_destroys_running_labs_on_sigterm(monkeypatch):
    from netdryrun import mcp_server

    destroyed, exits = [], []
    lab = FakeLab(World())
    lab.destroy = lambda: destroyed.append(1)
    monkeypatch.setattr(runner, "_ACTIVE", {lab})
    monkeypatch.setattr(mcp_server.os, "_exit", exits.append)
    mcp_server._on_terminate(signal.SIGTERM, None)
    assert destroyed == [1] and exits == [143] and not runner._ACTIVE


# ----------------------------------------------- M2: bad input and crashes are errors (exit 2), not "failed"

@pytest.mark.parametrize("text,message", [
    ("lab: t.clab.yml\nchecks: [\n", "not valid YAML"),
    ("lab: t.clab.yml\ntimeout: 2m\nchecks:\n  - {type: bgp_session, node: r1, neighbor: 10.0.0.2}\n",
     "timeout must be a positive number of seconds"),
    ("lab: t.clab.yml\nnodes: [r1]\nchecks:\n  - {type: bgp_session, node: r1, neighbor: 10.0.0.2}\n",
     "nodes must be a mapping"),
])
@pytest.mark.parametrize("cmd", ["run", "validate"])
def test_bad_config_exits_2_with_a_clear_message(tmp_path, capsys, text, message, cmd):
    folder = _lab_folder(tmp_path)
    (folder / "netdryrun.yml").write_text(text)
    args = [cmd, str(folder)] + (["--json", str(folder / "r.json"), "--no-step-summary"] if cmd == "run" else [])
    assert main(args) == 2
    err = capsys.readouterr().err
    assert message in err and "Traceback" not in err and len(err.strip().splitlines()) == 1
    if cmd == "run":
        assert json.loads((folder / "r.json").read_text())["status"] == "error"


def test_negative_settle_is_refused(tmp_path, capsys, monkeypatch):
    import netdryrun.cli as cli

    def must_not_run(*a, **k):   # never reach a real containerlab, even if the option slipped through
        raise AssertionError("a negative --settle reached run()")

    monkeypatch.setattr(cli, "run", must_not_run)
    with pytest.raises(SystemExit) as e:
        main(["run", str(_lab_folder(tmp_path)), "--settle", "-1"])
    assert e.value.code == 2 and "--settle: must be a number of seconds >= 0" in capsys.readouterr().err


def test_negative_settle_in_the_api_is_an_error_before_deploying(tmp_path, monkeypatch):
    w = World()
    lab = FakeLab(w)
    install(monkeypatch, w, lab, {n: FakeDriver(w) for n in ("r1", "r2", "r3")})
    rep = runner.run(cfg(tmp_path, [ALWAYS]), settle=-1)
    assert rep.status == "error" and "--settle" in rep.error and lab.deployed == 0


@pytest.mark.parametrize("topology,message", [
    ("name: t\ntopology:\n  nodes: [r1, r2]\n", "topology.nodes must be a mapping"),
    ("name: t\ntopology: {nodes: {r1: {kind: linux}\n", "topology is not valid YAML"),
    # duplicate keys are refused in the topology too (PyYAML alone keeps the second one silently)
    ("name: t\ntopology: {nodes: {r1: {kind: linux}}}\nname: u\n", "duplicate key 'name' (first defined on line 1)"),
])
def test_bad_topology_exits_2_and_writes_the_report(tmp_path, capsys, topology, message):
    folder = _lab_folder(tmp_path)
    (folder / "t.clab.yml").write_text(topology)
    assert main(["run", str(folder), "--json", str(folder / "r.json"), "--no-step-summary"]) == 2
    data = json.loads((folder / "r.json").read_text())
    assert data["status"] == "error" and message in data["error"]
    assert "Traceback" not in capsys.readouterr().err
    assert main(["record", str(folder / "t.clab.yml"), "--out", str(folder / "rec.yml")]) == 2


def test_unexpected_exception_is_an_error_with_a_report_and_the_lab_destroyed(tmp_path, monkeypatch):
    w = World()
    lab = FakeLab(w, deploy_error=RuntimeError("boom"))
    install(monkeypatch, w, lab, {n: FakeDriver(w) for n in ("r1", "r2", "r3")})
    rep = runner.run(cfg(tmp_path, [ALWAYS]))
    assert rep.status == "error" and rep.exit_code == 2
    assert rep.error.startswith("internal error: RuntimeError: boom") and "--debug" in rep.error
    assert lab.destroyed == 1


def test_internal_error_in_the_cli_exits_2_and_debug_shows_the_traceback(tmp_path, monkeypatch, capsys):
    import netdryrun.cli as cli

    def crash(*a, **k):
        raise RuntimeError("boom")

    monkeypatch.setattr(cli, "run", crash)
    # setenv records the variable's old state, so the "1" that --debug writes below is undone after the test
    # (delenv on an unset variable records nothing, and the "1" would leak into every later test)
    monkeypatch.setenv("NETDRYRUN_DEBUG", "")
    folder = _lab_folder(tmp_path)
    assert main(["run", str(folder), "--no-step-summary"]) == 2
    err = capsys.readouterr().err
    assert "internal error: RuntimeError: boom" in err and "Traceback" not in err
    assert main(["run", str(folder), "--no-step-summary", "--debug"]) == 2
    assert "Traceback" in capsys.readouterr().err


@pytest.mark.parametrize("passed", [True, False])
def test_a_report_that_cannot_be_written_exits_2_after_the_verdict(tmp_path, monkeypatch, capsys, passed):
    """The verdict is in, but evidence the user asked for is missing: exit 2 (not 0 or 1), never an internal
    error, and every other report is still written."""
    import netdryrun.cli as cli
    from netdryrun.checks import Result

    folder = _lab_folder(tmp_path)

    def fake_run(config, **kw):
        r = Result(config.checks[0], passed, "x", 2, 3.0, "2026-01-01T00:00:00+00:00")
        return runner.RunReport(config=config, lab_name="t", started="s", finished="f", results=[r])

    monkeypatch.setattr(cli, "run", fake_run)
    summary = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
    missing = tmp_path / "no-such-dir"
    args = ["run", str(folder), "--json", str(missing / "r.json"), "--markdown", str(tmp_path / "r.md"),
            "--junit", str(missing / "r.xml")]
    assert main(args) == 2
    err = capsys.readouterr().err
    assert "internal error" not in err and len([x for x in err.splitlines() if x.strip()]) == 2
    assert (tmp_path / "r.md").exists() and summary.exists()
    # and when every write works, the verdict's own exit code
    assert main(["run", str(folder), "--markdown", str(tmp_path / "r2.md"), "--no-step-summary"]) == (0 if passed else 1)
    # a step summary that can't be written is the same
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(missing / "summary.md"))
    assert main(["run", str(folder)]) == 2


# ------------------------------------------------------------------ two runs of the same lab at once

def test_a_lab_already_running_is_refused_and_left_alone(tmp_path, monkeypatch):
    w = World()
    lab = FakeLab(w, existing={"clab-t-r1"})
    install(monkeypatch, w, lab, {n: FakeDriver(w) for n in ("r1", "r2", "r3")})
    rep = runner.run(cfg(tmp_path, [ALWAYS]))
    assert rep.status == "error" and "already running" in rep.error
    assert lab.deployed == 0 and lab.destroyed == 0 and not lab.locked


def test_a_run_that_never_deployed_never_destroys(tmp_path, monkeypatch):
    # an error before deploy (here an unknown node) must not tear down a lab of the same name
    w = World()
    lab = FakeLab(w)
    install(monkeypatch, w, lab, {})
    rep = runner.run(cfg(tmp_path, [chk("route", "r9 route", node="r9", prefix="10.0.0.0/24")]))
    assert rep.status == "error" and "r9" in rep.error
    assert lab.deployed == 0 and lab.destroyed == 0


@pytest.mark.skipif(os.name != "posix", reason="flock")
def test_two_runs_of_the_same_lab_on_one_host_are_refused(tmp_path):
    topo = tmp_path / "t.clab.yml"
    topo.write_text(f"name: ndr-lock-test-{os.getpid()}\ntopology:\n  nodes:\n    r1: {{}}\n")
    first, second = Lab(topo), Lab(topo)
    first.acquire_lock()
    try:
        with pytest.raises(LabError, match="already using lab"):
            second.acquire_lock()
    finally:
        first.release_lock()
    second.acquire_lock()   # free again once the first run is done
    second.release_lock()


# ----------------------------------------------------------- M5: ping expect: failure with no route

def _ping_driver(stdout, stderr, rc):
    from netdryrun.drivers.frr import parse_ping
    ev = [{"node": "r1", "cmd": "ping", "rc": rc, "output": stdout, "stderr": stderr}]
    return SimpleNamespace(ping=lambda *a: Observation(parse_ping(stdout), ev))


@pytest.mark.parametrize("stdout,stderr", [
    ("", "ping: connect: Network is unreachable\n"),
    ("PING 10.9.9.9 (10.9.9.9): 56 data bytes\n", "ping: sendto: Network unreachable\n"),
    ("", "ping: connect: No route to host\n"),
])
def test_ping_expect_failure_passes_when_the_destination_has_no_route(stdout, stderr):
    d = _ping_driver(stdout, stderr, 2)
    ok, detail, _ = _ping(d, {"target": "10.9.9.9", "expect": "failure"})
    assert ok and "destination unreachable" in detail
    ok, detail, _ = _ping(d, {"target": "10.9.9.9"})
    assert not ok and "did not run" not in detail


def test_ping_that_did_not_run_is_still_an_error():
    d = _ping_driver("", "ping: bind: Cannot assign requested address\n", 2)
    ok, detail, _ = _ping(d, {"target": "10.9.9.9", "source": "192.0.2.1", "expect": "failure"})
    assert not ok and detail.startswith("error: ping did not run")


# ----------------------------------------------- validate reads the topology and makes run's pre-deploy checks

@pytest.mark.parametrize("topology,checks,message", [
    ("nodes:\n    r1: {kind: linux, image: frr}", "- {type: bgp_session, node: r9, neighbor: 10.0.0.2}",
     "unknown node(s) r9"),
    ("nodes:\n    r1: {kind: linux, image: alpine}", "- {type: bgp_session, node: r1, neighbor: 10.0.0.2}",
     "cannot detect driver for node r1"),
    ("nodes:\n    r1: {kind: arista_ceos, image: 'ceos:4.36.3M'}",
     "- {type: bgp_prefixes, node: r1, neighbor: 10.0.0.2, max: 0, afi: evpn}", "afi evpn is not supported on eos"),
    ("nodes: {r1: {kind: linux, image: frr}\n", "- {type: bgp_session, node: r1, neighbor: 10.0.0.2}",
     "topology is not valid YAML"),
])
def test_validate_makes_the_pre_deploy_checks_of_run(tmp_path, capsys, topology, checks, message):
    (tmp_path / "t.clab.yml").write_text(f"name: t\ntopology:\n  {topology}\n")
    (tmp_path / "netdryrun.yml").write_text(f"lab: t.clab.yml\nchecks:\n  {checks}\n")
    assert main(["validate", str(tmp_path)]) == 2
    err = capsys.readouterr().err
    assert message in err and "Traceback" not in err and len(err.strip().splitlines()) == 1


def test_validate_refuses_a_link_fault_on_sr_linux(tmp_path, capsys):
    (tmp_path / "t.clab.yml").write_text("name: t\ntopology:\n  nodes:\n    srl1: {kind: nokia_srlinux}\n"
                                         "    frr1: {kind: linux, image: frr}\n")
    (tmp_path / "netdryrun.yml").write_text(
        "lab: t.clab.yml\nchecks:\n  - {type: bgp_session, node: frr1, neighbor: 10.0.0.1}\n"
        "scenarios:\n  - link_down: {node: srl1, interface: e1-1}\n"
        "    checks:\n      - {type: bgp_session, node: frr1, neighbor: 10.0.0.1, state: down}\n")
    assert main(["validate", str(tmp_path)]) == 2
    assert "failure scenarios on SR Linux nodes (srl1) are not supported yet" in capsys.readouterr().err


def test_validate_passes_a_good_config_without_docker(tmp_path, capsys, monkeypatch):
    monkeypatch.setenv("PATH", str(tmp_path))   # no containerlab, no docker: validate must not need them
    assert main(["validate", str(_lab_folder(tmp_path))]) == 0
    assert "OK:" in capsys.readouterr().out


def test_mcp_validate_reports_an_unknown_node(tmp_path):
    pytest.importorskip("mcp")
    from netdryrun import mcp_server

    folder = _lab_folder(tmp_path)
    (folder / "netdryrun.yml").write_text("lab: t.clab.yml\nchecks:\n  - {type: bgp_session, node: r9, neighbor: 10.0.0.2}\n")
    data = json.loads(mcp_server.validate(str(folder)))
    assert data["valid"] is False and "unknown node(s) r9" in data["error"]
