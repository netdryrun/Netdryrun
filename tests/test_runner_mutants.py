"""Runner behaviour pinned by the 0.4 mutation run: the startup-config load of cEOS, SR Linux and SONiC, the report's
config_load record, the advertisement-interval stretch of settle and hold, and what run() does around its phases
(the driver overrides scenarios get, the recovery stop, interrupts, crashes and the lab's cleanup)."""
from __future__ import annotations

import os
import signal
from pathlib import Path

import pytest

from netdryrun import runner
from netdryrun.config import Config, Fault, Scenario
from netdryrun.drivers.base import BgpNeighbor, DriverError, Observation
from netdryrun.lab import ExecResult, Node

from test_runner_robustness import ALWAYS, FakeDriver, FakeLab, World, _redundancy_scenario, cfg, chk, install

S = runner.SRL_LOAD_FAILED
SRL_GREP = ["grep", "-h", S, "/var/log/messages"]


class ExecLab:
    """A lab whose exec answers each node with one fixed result, recording each command."""

    def __init__(self, nodes: dict, results: dict | None = None, topology=None):
        self.nodes = {n: Node(n, f"clab-t-{n}", kind, image) for n, (kind, image) in nodes.items()}
        self.results = results or {}
        self.topology = topology
        self.ran = []

    def exec(self, node, cmd, timeout=60, input=None):
        self.ran.append((node, cmd))
        rc, out, err = self.results[node]
        return ExecResult(cmd, rc, out, err)


SRL = ("nokia_srlinux", "ghcr.io/nokia/srlinux:26.7.2")
SONIC = ("sonic-vs", "docker-sonic-vs:master.1258173-c10162df4")


def _config(**kw):
    return Config(path=Path("t.yml"), lab=Path("t.clab.yml"), timeout=60, checks=[], **kw)


# ------------------------------------------------------------------------------------------ _startup_load

def test_eos_errors_that_can_not_be_read_name_the_tail_of_stderr():
    """The reason quotes the last 200 characters of what the command printed, then says the load is unknown."""
    err = "E" * 50 + "x" * 200
    lab = ExecLab({"ceos1": ("arista_ceos", "ceos:4.36.3M")}, {"ceos1": (1, "", err)})
    assert runner._startup_load(lab, "ceos1", "eos", lambda n: []) == [
        f"its startup-config errors could not be read ({'x' * 200}), so whether its config loaded is unknown"]


def test_sr_linux_is_read_on_a_deployed_lab_by_default():
    """The default is a lab this run deployed: SR Linux's load log is read, a clean one is [] (not None)."""
    lab = ExecLab({"srl1": SRL}, {"srl1": (1, "", "")})
    assert runner._startup_load(lab, "srl1", "srlinux", lambda n: []) == []
    assert lab.ran == [("srl1", SRL_GREP)]


def test_sr_linux_log_that_can_not_be_read_quotes_its_tail():
    err = "E" * 50 + "y" * 200
    lab = ExecLab({"srl1": SRL}, {"srl1": (2, "", err)})
    assert runner._startup_load(lab, "srl1", "srlinux", lambda n: [], True) == [
        f"its startup-config load log could not be read ({'y' * 200}), so whether its config loaded is unknown"]


def test_sr_linux_log_that_can_not_be_read_without_output_gives_the_rc():
    lab = ExecLab({"srl1": SRL}, {"srl1": (2, "", "")})
    assert runner._startup_load(lab, "srl1", "srlinux", lambda n: [], True) == [
        "its startup-config load log could not be read (rc 2), so whether its config loaded is unknown"]


def test_sr_linux_log_that_can_not_be_read_quotes_stdout_when_stderr_is_empty():
    lab = ExecLab({"srl1": SRL}, {"srl1": (2, "grep: busy\n", "")})
    assert runner._startup_load(lab, "srl1", "srlinux", lambda n: [], True) == [
        "its startup-config load log could not be read (grep: busy), so whether its config loaded is unknown"]


def test_sr_linux_failed_load_quotes_the_first_failure_up_to_300_characters():
    out = f"Oct 30 srl mgmt: {S}: first {'z' * 400}\nOct 30 srl mgmt: {S}: second\n"
    lab = ExecLab({"srl1": SRL}, {"srl1": (0, out, "")})
    assert runner._startup_load(lab, "srl1", "srlinux", lambda n: [], True) == [
        "it failed to load its startup config: " + f"{S}: first {'z' * 400}"[:300]]


def test_sonic_bound_config_names_the_first_three_binds_and_the_setup_way():
    binds = [f"c/{i}:/etc/x{i}" for i in range(1, 5)]
    found = runner._startup_load(ExecLab({"sonic1": SONIC}), "sonic1", "sonic", lambda n: binds, True)
    assert len(found) == 1
    assert found[0].startswith("a config bound into a SONiC node is not checked (c/1:/etc/x1, c/2:/etc/x2, "
                               "c/3:/etc/x3): configure SONiC with setup commands (nodes.<name>.setup)")


def test_a_sonic_node_whose_topology_can_not_be_read_is_an_error(tmp_path):
    """The binds of an unreadable topology are unknown: a SONiC node there is never clean."""
    lab = ExecLab({"sonic1": SONIC}, topology=tmp_path / "missing.clab.yml")
    assert runner._bound_files(lab, "sonic1") == ["(the topology's binds could not be read)"]
    found = runner.config_load_by_node(lab, runner._driver_of(_config()))
    assert found["sonic1"] and "not checked" in found["sonic1"][0]


# ------------------------------------------------------------------------------------------ _sonic_config_bind

@pytest.mark.parametrize("bind, flagged", [
    ("(the topology's binds could not be read)", True),
    ("cfg/s1.cfg:startup-config", True),
    ("/etc/x", True),
    ("./v:/var", True),
    ("s:/etc/x:a:b", True),
    ("s:/etcX", False),
    ("s:/opt/x", False),
])
def test_which_sonic_binds_can_change_its_config(bind, flagged):
    """Unknown binds and startup-configs count; a destination is read as the field after the first colon, and
    one into, or above, a config place counts."""
    assert runner._sonic_config_bind(bind) is flagged


# ------------------------------------------------------------------------------------------ _config_load

class _Drv:
    name = "frr"

    def nos_version(self):
        return "10.4.1"


def test_config_load_skips_bridges_and_goes_on_after_a_node_without_a_driver():
    rep = runner.RunReport(config=_config())
    lab = ExecLab({"a1": ("linux", "alpine:3"), "br": ("bridge", ""), "ob": ("ovs-bridge", ""),
                   "r1": ("linux", "quay.io/frrouting/frr:10.4.1")})
    lab.image_digest = lambda image: "sha256:1"

    def driver_for(n):
        if n != "r1":
            raise DriverError("no driver")
        return _Drv()
    runner._config_load(lab, driver_for, rep, {"r1": []})
    nodes = rep.environment["nodes"]
    assert "br" not in nodes and "ob" not in nodes
    assert nodes["a1"] == {"config_load": "not verified (no routing driver)"}
    assert nodes["r1"] == {"nos_version": "10.4.1", "image_digest": "sha256:1", "config_load": "clean"}


# ------------------------------------------------------------------------- _stretch_for_advertisement_intervals

class _BgpDrv:
    """bgp_neighbors(vrf) from {vrf: {address: adv_interval}}; a vrf missing from the map raises DriverError."""

    def __init__(self, by_vrf):
        self.by_vrf = by_vrf

    def bgp_neighbors(self, vrf="default"):
        if vrf not in self.by_vrf:
            raise DriverError(f"no vrf {vrf}")
        return Observation({a: BgpNeighbor(a, "established", {}, adv_interval=i)
                            for a, i in self.by_vrf[vrf].items()}, [])


def _stretch(drivers, settle=10.0, hold=10.0, checks=(), scenarios=()):
    logs = []

    def driver_for(n):
        if drivers[n] is None:
            raise DriverError("host")
        return drivers[n]
    config = Config(path=Path("t.yml"), lab=Path("t.clab.yml"), timeout=60, checks=list(checks),
                    scenarios=list(scenarios))
    out = runner._stretch_for_advertisement_intervals(type("L", (), {"nodes": dict(drivers)})(), driver_for, config,
                                                      settle, hold, logs.append)
    return out, logs


BLUE = chk("route", "r1 has x in blue", node="r1", prefix="10.9.9.0/24", vrf="blue")


def test_stretch_reads_the_vrfs_of_the_main_checks():
    out, logs = _stretch({"r1": _BgpDrv({"default": {}, "blue": {"10.0.0.2": 30.0}})}, checks=[BLUE])
    assert out == (32.0, 32.0)
    assert logs == ["r1 (to 10.0.0.2, vrf blue) has an advertisement interval of 30s, so a route can arrive that "
                    "late: settle and hold extended to at least 32s"]


def test_stretch_reads_the_vrfs_of_the_scenario_checks():
    sc = Scenario(name="s", faults=[Fault("link_down", "r1", "eth1")], checks=[BLUE])
    out, _ = _stretch({"r1": _BgpDrv({"default": {}, "blue": {"10.0.0.2": 30.0}})}, scenarios=[sc])
    assert out == (32.0, 32.0)


def test_stretch_in_the_default_vrf_names_no_vrf():
    out, logs = _stretch({"r1": _BgpDrv({"default": {"10.0.0.2": 30.0}})})
    assert out == (32.0, 32.0)
    assert logs[0].startswith("r1 (to 10.0.0.2) has an advertisement interval of 30s")


@pytest.mark.parametrize("interval", [None, 0.0])
def test_no_known_interval_stretches_nothing(interval):
    out, logs = _stretch({"r1": _BgpDrv({"default": {"10.0.0.2": interval}})}, settle=0.5, hold=0.5)
    assert out == (0.5, 0.5) and logs == []


def test_a_sub_second_interval_still_stretches():
    out, _ = _stretch({"r1": _BgpDrv({"default": {"10.0.0.2": 0.5}})}, settle=1.0, hold=1.0)
    assert out == (2.5, 2.5)


def test_windows_already_as_long_as_needed_are_left_without_a_log():
    out, logs = _stretch({"r1": _BgpDrv({"default": {"10.0.0.2": 8.0}})}, settle=10.0, hold=12.0)
    assert out == (10.0, 12.0) and logs == []


def test_a_host_before_a_router_does_not_end_the_search():
    out, _ = _stretch({"a1": None, "r1": _BgpDrv({"default": {"10.0.0.2": 30.0}})})
    assert out == (32.0, 32.0)


def test_a_vrf_without_bgp_does_not_end_the_search_on_its_node():
    out, _ = _stretch({"r1": _BgpDrv({"default": {"10.0.0.2": 30.0}})}, checks=[BLUE])
    assert out == (32.0, 32.0)


def test_the_first_node_with_the_longest_interval_is_named():
    _, logs = _stretch({"r1": _BgpDrv({"default": {"10.0.0.2": 30.0}}),
                        "r2": _BgpDrv({"default": {"10.0.0.1": 30.0}})})
    assert logs[0].startswith("r1 (to 10.0.0.2)")


# ------------------------------------------------------------------------------------------ run

class SrlLab(FakeLab):
    """FakeLab plus an SR Linux node whose load log says its startup config failed."""

    def __init__(self, world):
        super().__init__(world, nodes=("r1",))
        self.nodes["srl1"] = Node("srl1", "clab-t-srl1", *SRL)

    def exec(self, node, cmd, timeout=60, input=None):
        return ExecResult(cmd, 0, f"Oct 30 srl mgmt: {S}: bad json\n", "")


def test_run_reads_the_sr_linux_load_on_a_lab_it_deployed(tmp_path, monkeypatch):
    """A rejected SR Linux startup config makes a deployed run an error, never a pass."""
    w = World()
    srl = FakeDriver(w)
    srl.name = "srlinux"
    install(monkeypatch, w, SrlLab(w), {"r1": FakeDriver(w), "srl1": srl})
    rep = runner.run(cfg(tmp_path, [chk("route", "r1 has x", node="r1", prefix="10.9.9.0/24")]), deploy=True)
    assert rep.status == "error"
    assert "srl1: it failed to load its startup config" in rep.error


def test_run_hands_its_driver_overrides_to_the_scenarios(tmp_path, monkeypatch):
    """A node first reached inside a scenario (a fault's node) gets the driver the config names for it."""
    w = World()
    drivers = {n: FakeDriver(w) for n in ("r1", "r2", "r3")}
    install(monkeypatch, w, FakeLab(w), drivers)
    calls = []

    def for_node(lab_, node, override=None):
        calls.append((node, override))
        if calls.count((node, override)) == 1 and node == "r1":
            raise DriverError("not up yet")
        return drivers[node]
    monkeypatch.setattr(runner, "for_node", for_node)
    config = cfg(tmp_path, [ALWAYS], [_redundancy_scenario()])
    config.drivers = {"r1": "frr"}
    runner.run(config, deploy=False)
    assert calls.count(("r1", "frr")) >= 2 and ("r1", None) not in calls


def _not_recovering(tmp_path, monkeypatch, scenarios):
    w = World()
    drivers = {n: FakeDriver(w, routes=lambda world, p: p != "10.9.9.0/24" or not world.links)
               for n in ("r1", "r2", "r3")}
    install(monkeypatch, w, FakeLab(w), drivers)
    logs = []
    rep = runner.run(cfg(tmp_path, [ALWAYS], scenarios), deploy=False, log=logs.append)
    assert rep.status == "failed"
    return logs


def test_a_scenario_that_does_not_recover_says_later_ones_are_skipped(tmp_path, monkeypatch):
    second = Scenario(name="r2-r3 fails", faults=[Fault("link_down", "r2", "eth2")],
                      checks=[chk("route", "[r2-r3 fails] r3 keeps 10.1.0.0/24", node="r3", prefix="10.1.0.0/24")])
    logs = _not_recovering(tmp_path, monkeypatch, [_redundancy_scenario(), second])
    assert "The network did not recover after scenario 'r1-r2 fails'; later scenarios skipped" in logs


def test_the_last_scenario_not_recovering_skips_nothing(tmp_path, monkeypatch):
    logs = _not_recovering(tmp_path, monkeypatch, [_redundancy_scenario()])
    assert not any("later scenarios skipped" in m for m in logs)


def test_an_interrupt_names_its_signal(tmp_path, monkeypatch):
    w = World()
    install(monkeypatch, w, FakeLab(w, deploy_error=runner.Interrupted(signal.SIGTERM)), {"r3": FakeDriver(w)})
    with pytest.raises(KeyboardInterrupt) as ei:
        runner.run(cfg(tmp_path, [ALWAYS]), deploy=True)
    assert ei.value.report.error == "interrupted by SIGTERM: no verdict"


def test_a_plain_ctrl_c_is_named_sigint(tmp_path, monkeypatch):
    w = World()
    install(monkeypatch, w, FakeLab(w, deploy_error=KeyboardInterrupt()), {"r3": FakeDriver(w)})
    with pytest.raises(KeyboardInterrupt) as ei:
        runner.run(cfg(tmp_path, [ALWAYS]), deploy=True)
    assert ei.value.report.error == "interrupted by SIGINT: no verdict"


def test_a_signal_during_cleanup_is_honoured_and_named(tmp_path, monkeypatch):
    class Lab(FakeLab):
        def destroy(self):
            os.kill(os.getpid(), signal.SIGTERM)
            return super().destroy()
    w = World()
    lab = Lab(w)
    install(monkeypatch, w, lab, {"r3": FakeDriver(w)})
    with pytest.raises(runner.Interrupted) as ei:
        runner.run(cfg(tmp_path, [ALWAYS]), deploy=True)
    assert lab.destroyed == 1
    assert ei.value.report.error == "interrupted by SIGTERM: no verdict"


def test_a_crash_is_an_internal_error_with_the_debug_hint(tmp_path, monkeypatch):
    class Lab(FakeLab):
        def check_tools(self):
            raise RuntimeError("boom")
    monkeypatch.delenv("NETDRYRUN_DEBUG", raising=False)
    w = World()
    install(monkeypatch, w, Lab(w), {})
    rep = runner.run(cfg(tmp_path, [ALWAYS]), deploy=True)
    assert rep.error == ("internal error: RuntimeError: boom. This is a Netdryrun bug, not a verdict on the change; "
                         "rerun with --debug (or NETDRYRUN_DEBUG=1) for the traceback, and please report it")


def _deployed_run(tmp_path, monkeypatch, lab_cls=FakeLab, **kw):
    w = World()
    lab = lab_cls(w)
    install(monkeypatch, w, lab, {"r3": FakeDriver(w)})
    logs = []
    rep = runner.run(cfg(tmp_path, [ALWAYS]), deploy=True, log=logs.append, **kw)
    assert rep.status == "passed"
    return lab, logs


def test_a_clean_cleanup_says_it_destroys_and_warns_of_nothing(tmp_path, monkeypatch):
    lab, logs = _deployed_run(tmp_path, monkeypatch)
    assert lab.destroyed == 1 and "Destroying lab..." in logs
    assert not any("warning" in m for m in logs)


@pytest.mark.parametrize("rc, out, err, said", [
    (1, "out", "err", "err"),
    (2, "out", "", "out"),
    (1, "", "x" * 50 + "y" * 300, "y" * 300),
])
def test_a_failed_cleanup_is_warned_with_its_output(tmp_path, monkeypatch, rc, out, err, said):
    class Lab(FakeLab):
        def destroy(self):
            return ExecResult([], rc, out, err)
    _, logs = _deployed_run(tmp_path, monkeypatch, Lab)
    assert f"warning: lab cleanup failed: {said}" in logs


def test_a_cleanup_that_raises_is_warned(tmp_path, monkeypatch):
    class Lab(FakeLab):
        def destroy(self):
            raise RuntimeError("gone")
    _, logs = _deployed_run(tmp_path, monkeypatch, Lab)
    assert "warning: lab cleanup failed: gone" in logs


def test_a_kept_lab_says_how_to_destroy_it(tmp_path, monkeypatch):
    lab, logs = _deployed_run(tmp_path, monkeypatch, keep=True)
    assert lab.destroyed == 0
    assert "Lab t left running for debugging; destroy with: containerlab destroy -t t.clab.yml --cleanup" in logs
