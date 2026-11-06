"""A scenario's BGP gate gets the same inputs as the top-level one (mutation triage of 22e1f95, runner.run_scenario):
the lab (for far ends of declared-down sessions), every other routing node, the eor: not_sent declarations and the
run's set of untracked End-of-RIB warnings already given. Whole runs on the fake lab and clock.
"""
from __future__ import annotations

from pathlib import Path

from netdryrun import runner
from netdryrun.config import Config, Fault, Scenario

from test_mutants_rt_gate import EorDrv
from test_verdict_runner import chk, leak, make, route


def run(e, checks, scenarios, **cfg):
    config = Config(path=Path("netdryrun.yml"), lab=Path("t.clab.yml"), timeout=30, checks=list(checks),
                    scenarios=list(scenarios), **cfg)
    return runner.run(config, deploy=False, on_result=e.results.append, log=e.logs.append, settle=1, hold=3)


def by_name(rep):
    return {r.check.name: r for r in rep.results}


def test_a_fault_that_leaves_the_link_up_errors_exactly(monkeypatch):
    e = make(monkeypatch)
    e.lab.stuck_up = True
    rep = e.run([route("a")], [Scenario("s", [Fault("link_down", "r1", "eth1")], [route("[s] x", node="r2")])])
    assert rep.error == ("scenario 's': r1 eth1 is still administratively up after `ip link set down`: the fault did "
                         "not take effect")


def test_the_scenario_gate_excludes_the_far_end_of_a_declared_down_session(monkeypatch):
    # r1's session to r2 (10.0.12.2) is declared down; r2's session back to r1 (10.0.12.1) is down too. The scenario
    # takes r2 eth2 down (no BGP over it), and its leak guard on r2 must not be blocked by the far end.
    e = make(monkeypatch, r1={"neighbors": {"default": {"10.0.12.2": "idle"}}, "routes": {"default": lambda t, p: False}},
             r2={"neighbors": {"default": {"10.0.12.1": "idle", "10.0.23.3": "established"}},
                 "routes": {"default": lambda t, p: False}})
    down = chk("bgp_session", "r1-r2 down", node="r1", neighbor="10.0.12.2", state="down")
    sc = Scenario("s", [Fault("link_down", "r2", "eth2")], [leak("[s] r2 no leak", node="r2", timeout=6)])
    rep = run(e, [down], [sc])
    assert by_name(rep)["[s] r2 no leak"].passed, by_name(rep)["[s] r2 no leak"].detail


def test_the_scenario_gate_watches_the_other_routing_nodes(monkeypatch):
    e = make(monkeypatch, r1={"neighbors": {"default": {"10.0.13.3": "established"}},
                              "routes": {"default": lambda t, p: False}},
             r3={"neighbors": {"default": {"10.0.31.9": "active"}}, "routes": {"default": lambda t, p: False}})
    sc = Scenario("s", [Fault("link_down", "r1", "eth1")], [leak("[s] no leak", timeout=6)])
    rep = run(e, [route("a", node="r2")], [sc])
    r = by_name(rep)["[s] no leak"]
    assert [w["code"] for w in r.warnings] == ["gate-session-down"] and r.warnings[0]["node"] == "r3"


def test_the_scenario_gate_honours_eor_not_sent(monkeypatch):
    e = make(monkeypatch, r1={"neighbors": {"default": {"10.0.13.3": "established"}},
                              "routes": {"default": lambda t, p: False}})
    e.drivers["r1"] = EorDrv(e.drivers["r1"], lambda t, v: {"10.0.13.3": {"*": "unknown"}})
    sc = Scenario("s", [Fault("link_down", "r1", "eth1")], [leak("[s] no leak", timeout=6)])
    rep = run(e, [route("a", node="r2")], [sc], eor_not_sent=frozenset({("r1", "default", "10.0.13.3")}))
    assert rep.status == "passed", (rep.error, [(r.check.name, r.detail) for r in rep.results])


def test_an_untracked_session_is_reported_once_per_run_across_scenarios(monkeypatch):
    e = make(monkeypatch, r1={"neighbors": {"default": {"10.0.13.3": "established"}},
                              "routes": {"default": lambda t, p: False}})
    e.drivers["r1"] = EorDrv(e.drivers["r1"], lambda t, v: {"10.0.13.3": {"*": "untracked"}})
    sc = Scenario("s", [Fault("link_down", "r1", "eth1")], [leak("[s] no leak", timeout=6)])
    rep = run(e, [leak("top", timeout=6)], [sc])
    codes = [(r.check.name, w["code"]) for r in rep.results for w in r.warnings]
    assert codes == [("top", "eor-untracked")]
