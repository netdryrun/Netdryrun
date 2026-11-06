"""The management-path wiring in runner.py, exactly (mutation triage of bd76896, 2026-11-06): preflight's management-VRF
and VM-kind refusals, and run()'s prepare, driver cover, report field and every phase's re-check."""
from __future__ import annotations

from pathlib import Path

import pytest

from netdryrun import mgmt, runner
from netdryrun.config import Config, Fault, Scenario
from netdryrun.lab import LabError

from test_verdict_runner import leak, make, route


def cfg(checks, scenarios=(), drivers=None):
    return Config(path=Path("netdryrun.yml"), lab=Path("t.clab.yml"), timeout=120, checks=list(checks),
                  drivers=drivers or {}, scenarios=list(scenarios))


# ------------------------------------------------------------------------------------------- preflight

@pytest.mark.parametrize("kind,vrf", [("cisco_n9kv", "management"), ("vr-n9kv", "management"),
                                      ("nokia_srlinux", "mgmt"), ("srl", "mgmt")])
def test_a_check_in_the_management_vrf_is_refused_exact(monkeypatch, kind, vrf):
    e = make(monkeypatch, kinds={"r1": (kind, "img")})
    monkeypatch.setattr(runner, "resolve", lambda node, override=None: "srlinux")
    with pytest.raises(LabError) as err:
        runner.preflight(cfg([route("leak", vrf=vrf)]), e.lab)
    assert str(err.value) == (f"check 'leak' reads vrf {vrf} on r1: that is its management network (Docker's), not a "
                              "lab VRF")


@pytest.mark.parametrize("kind,vrf", [("cisco_n9kv", "mgmt"), ("nokia_srlinux", "management"), ("linux", "management"),
                                      ("linux", "mgmt"), ("cisco_n9kv", "RED")])
def test_the_same_vrf_names_elsewhere_are_lab_vrfs(monkeypatch, kind, vrf):
    e = make(monkeypatch, kinds={"r1": (kind, "img")})
    monkeypatch.setattr(runner, "resolve", lambda node, override=None: "srlinux")
    runner.preflight(cfg([route("x", vrf=vrf)]), e.lab)


@pytest.mark.parametrize("kind", ["sonic-vm", "vr-sonic", "cisco_n9kv", "vr-anything"])
@pytest.mark.parametrize("driver", ["frr", "sonic"])
def test_frr_and_sonic_drivers_are_refused_on_vm_kinds_exact(monkeypatch, kind, driver):
    e = make(monkeypatch, kinds={"r1": (kind, "img")})
    seen = []
    monkeypatch.setattr(runner, "resolve", lambda node, override=None: seen.append((node.name, override)) or driver)
    with pytest.raises(LabError) as err:
        runner.preflight(cfg([route("x")], drivers={"r1": "frr"}), e.lab)
    assert str(err.value) == (f"node r1 is a VM kind ({kind}): the {driver} driver would read and ping from the "
                              "container that launches the VM, not from the router")
    assert ("r1", "frr") in seen


@pytest.mark.parametrize("kind,driver", [("sonic-vm", "nxos"), ("linux", "frr"), ("vr-x", "junos")])
def test_other_drivers_or_container_kinds_pass(monkeypatch, kind, driver):
    e = make(monkeypatch, kinds={"r1": (kind, "img")})
    monkeypatch.setattr(runner, "resolve", lambda node, override=None: driver)
    runner.preflight(cfg([route("x")]), e.lab)


def test_a_vm_kind_whose_driver_cant_be_resolved_is_left_to_for_node(monkeypatch):
    e = make(monkeypatch, kinds={"r1": ("sonic-vm", "img")})

    def boom(node, override=None):
        raise LabError("undetectable")
    monkeypatch.setattr(runner, "resolve", boom)
    runner.preflight(cfg([route("x")]), e.lab)


# ------------------------------------------------------------------------------------------- run()

class Spy:
    def __init__(self, monkeypatch, e):
        self.e, self.calls = e, []
        self.state = {"r1": mgmt.Mgmt("r1", "clab", kind="linux", removed=["default via gw dev eth0"])}

        def prepare(lab, checks, log=None, sleep=None):
            self.calls.append(("prepare", lab is e.lab, [c.name for c in checks], log is not None, sleep))
            lab.management = self.state
            return self.state
        monkeypatch.setattr(runner.mgmt, "prepare", prepare)
        monkeypatch.setattr(runner.mgmt, "recheck", lambda lab, when: self.calls.append(("recheck", lab is e.lab, when)))
        monkeypatch.setattr(runner.mgmt, "require_covered",
                            lambda lab, state, node, drv: self.calls.append(("cover", node, drv)))
        monkeypatch.setattr(runner, "resolve",
                            lambda node, override=None: self.calls.append(("resolve", node.name, override)) or "frr")

    def of(self, kind):
        return [c[1:] for c in self.calls if c[0] == kind]


def test_run_prepares_with_every_check_log_and_the_watched_sleep(monkeypatch):
    e = make(monkeypatch)
    spy = Spy(monkeypatch, e)
    sc = Scenario("s", [Fault("link_down", "r1", "eth1")], [route("[s] x", node="r3")])
    e.run([route("a"), leak("n", node="r2")], [sc], drivers_cfg={"r2": "frr"})
    (lab_ok, names, has_log, sleep), = spy.of("prepare")
    assert lab_ok and names == ["a", "n", "[s] x"] and has_log and isinstance(sleep, runner._NodeWatch)
    after = spy.calls[[c[0] for c in spy.calls].index("prepare"):]     # preflight resolves too, before deploying
    assert [c[1:] for c in after if c[0] == "resolve"][:3] == [("r1", None), ("r2", "frr"), ("r3", None)]
    assert spy.of("cover") == [("r1", "frr"), ("r2", "frr"), ("r3", "frr")]


def test_run_skips_a_node_whose_driver_cant_be_resolved_and_covers_the_rest(monkeypatch):
    e = make(monkeypatch)
    spy = Spy(monkeypatch, e)

    def resolve(node, override=None):
        if node.name == "r1":
            raise LabError("no driver")
        return "frr"
    monkeypatch.setattr(runner, "resolve", resolve)
    e.run([route("a"), route("b", node="r2")])
    assert spy.of("cover") == [("r2", "frr")]


def test_run_reports_each_nodes_management_default(monkeypatch):
    e = make(monkeypatch)
    Spy(monkeypatch, e)
    rep = e.run([route("a")])
    assert rep.environment["nodes"]["r1"]["management_default"] == "removed: default via gw dev eth0"


def test_run_rechecks_at_every_phase_exact(monkeypatch):
    e = make(monkeypatch)
    spy = Spy(monkeypatch, e)
    sc = Scenario("s1", [Fault("link_down", "r1", "eth1")], [route("[s1] x", node="r3")])
    e.run([route("a"), leak("n")], [sc])
    assert spy.of("recheck") == [(True, "after the positive checks"), (True, "before the post-convergence checks"),
                                 (True, "after the post-convergence checks"), (True, "before scenario 's1'"),
                                 (True, "after scenario 's1'")]


def test_run_keeps_the_positive_results(monkeypatch):
    e = make(monkeypatch)
    Spy(monkeypatch, e)
    rep = e.run([route("a"), route("b"), leak("n")])
    assert [r.check.name for r in rep.results] == ["a", "b", "n"]
