"""Mutation survivors in the runner's helpers and run(): exact messages, exact returned sets, exact retries."""
from __future__ import annotations

import re
from pathlib import Path
from types import SimpleNamespace

import pytest

from netdryrun import runner
from netdryrun.config import Config, ConfigError, Fault, Scenario
from netdryrun.drivers.base import DriverError, NoSuchInstance
from netdryrun.lab import LabError, Node

from test_verdict_runner import Clock, FakeLab, leak, make, chk


# ------------------------------------------------------------------------------------------- _container_iface

@pytest.mark.parametrize("name,want", [
    ("Ethernet1", "eth1"), ("Ethernet12", "eth12"),
    ("ethernet-1/1", "e1-1"), ("ethernet-3/14", "e3-14"),
    ("eth0", "eth0"), ("lo", "lo"), ("ETHERNET-1/2", "ETHERNET-1/2"), ("ethernet-1", "ethernet-1"),
    ("Ethernet1x", "Ethernet1x"), ("xethernet-1/2", "xethernet-1/2"),
])
def test_container_iface(name, want):
    assert runner._container_iface(name) == want


# ------------------------------------------------------------------------------------------- _routing_nodes

def test_routing_nodes_of_a_lab_without_nodes_is_empty():
    assert runner._routing_nodes(SimpleNamespace(), lambda n: 1 / 0) == {}


def test_routing_nodes_keeps_the_driver_error_text():
    lab = FakeLab(Clock(), nodes=("r1", "r2"))

    def driver_for(node):
        if node == "r2":
            raise DriverError("beta driver: not chosen")
        return "drv-" + node

    assert runner._routing_nodes(lab, driver_for) == {"r1": "drv-r1", "r2": "beta driver: not chosen"}


# ------------------------------------------------------------------------------------------- _far_ends

def _lab(addresses, links, nodes=("r1", "r2", "r3", "ix"), cls=FakeLab):
    return cls(Clock(), nodes=nodes, kinds={"ix": ("bridge", "")}, addresses=addresses, links=links)


def test_far_ends_of_a_lab_without_links_is_empty():
    assert runner._far_ends(SimpleNamespace(), [("r1", "default", "10.0.12.2")]) == set()


def test_far_ends_skips_an_empty_key_and_goes_on_with_the_next_declaration():
    lab = _lab({("r1", "eth1"): ["10.0.12.1/30"], ("r2", "eth7"): ["10.0.12.2/30"]},
               [(("r1", "eth1"), ("r2", "eth7"))])
    assert runner._far_ends(lab, [("r1", "default", ""), ("r1", "default", None), ("r1", "default", "10.0.12.2")]) \
        == {("r2", "default", "10.0.12.1")}


@pytest.mark.parametrize("link", [(("r1", "eth1"), ("r2", "eth7")), (("r2", "eth7"), ("r1", "eth1"))])
def test_far_ends_finds_the_node_on_either_end_of_a_link(link):
    lab = _lab({("r1", "eth1"): ["10.0.12.1/30"], ("r2", "eth7"): ["10.0.12.2/30"]}, [link])
    assert runner._far_ends(lab, [("r1", "default", "10.0.12.2")]) == {("r2", "default", "10.0.12.1")}
    assert runner._far_ends(lab, [("r2", "default", "10.0.12.1")]) == {("r1", "default", "10.0.12.2")}


def test_far_ends_unnumbered_names_the_peer_interface():
    lab = _lab({}, [(("r2", "eth7"), ("r1", "eth1")), (("r1", "eth2"), ("r3", "eth9"))])
    assert runner._far_ends(lab, [("r1", "red", "eth1")]) == {("r2", "red", "eth7")}


def test_far_ends_counts_only_addresses_in_the_declared_subnet():
    # a second address of the same family on another subnet must not hide the one in the subnet
    lab = _lab({("r1", "eth1"): ["10.0.12.1/30", "10.9.9.1/30"], ("r2", "eth7"): ["10.0.12.2/30"]},
               [(("r1", "eth1"), ("r2", "eth7"))])
    assert runner._far_ends(lab, [("r1", "default", "10.0.12.2")]) == {("r2", "default", "10.0.12.1")}


class _Unreadable(FakeLab):
    bad: set = set()

    def interface_addresses(self, node, iface):
        if (node, iface) in self.bad:
            raise LabError("cannot read")
        return super().interface_addresses(node, iface)


@pytest.mark.parametrize("bad_peer,good_peer", [("r2", "r3"), ("r3", "r2")])
def test_far_ends_an_unreadable_peer_does_not_hide_the_peer_that_owns_the_address(bad_peer, good_peer):
    lab = _lab({("r1", "eth1"): ["10.0.0.1/24"], ("r2", "eth1"): ["10.0.0.2/24"], ("r3", "eth1"): ["10.0.0.3/24"]},
               [(("r1", "eth1"), ("ix", "p1")), (("r2", "eth1"), ("ix", "p2")), (("r3", "eth1"), ("ix", "p3"))],
               cls=_Unreadable)
    lab.bad = {(bad_peer, "eth1")}
    owner = {"r2": "10.0.0.2", "r3": "10.0.0.3"}[good_peer]
    assert runner._far_ends(lab, [("r1", "default", owner)]) == {(good_peer, "default", "10.0.0.1")}


# ------------------------------------------------------------------------------------------- _check_declared_peers

class Flaky:
    def __init__(self, answers):
        self.answers, self.vrfs = list(answers), []

    def bgp_neighbors(self, vrf="default"):
        self.vrfs.append(vrf)
        a = self.answers.pop(0)
        if isinstance(a, Exception):
            raise a
        return SimpleNamespace(value=a)


def _peers_error(declared, answers, monkeypatch):
    monkeypatch.setattr(runner, "_sleep", lambda s: None)
    d = Flaky(answers)
    with pytest.raises(ConfigError) as ei:
        runner._check_declared_peers(declared, lambda n: d)
    return str(ei.value), d


def test_declared_peer_read_retries_with_the_poll_sleep_and_the_vrf(monkeypatch):
    sleeps = []
    monkeypatch.setattr(runner, "_sleep", sleeps.append)
    d = Flaky([DriverError("a"), DriverError("b"), {"10.0.12.2": None}])
    runner._check_declared_peers({("r1", "RED", "10.0.12.2")}, lambda n: d)
    assert sleeps == [runner.POLL, runner.POLL] and d.vrfs == ["RED", "RED", "RED"]


def test_declared_peer_read_fails_after_three_reads_with_the_last_error(monkeypatch):
    sleeps = []
    monkeypatch.setattr(runner, "_sleep", sleeps.append)
    d = Flaky([DriverError("a"), DriverError("b"), DriverError("c"), DriverError("d")])
    with pytest.raises(DriverError, match=r"^c$"):
        runner._check_declared_peers({("r1", "default", "10.0.12.2")}, lambda n: d)
    assert len(d.vrfs) == 3 and sleeps == [runner.POLL, runner.POLL]


def test_declared_peer_missing_in_the_default_vrf_message(monkeypatch):
    msg, d = _peers_error({("r1", "default", "10.0.12.9")}, [{"10.0.12.3": None, "10.0.12.2": None}], monkeypatch)
    assert d.vrfs == ["default"]
    assert msg == ("nodes.r1.peers.10.0.12.9: r1 has no BGP session to 10.0.12.9 "
                   "(its sessions: 10.0.12.2, 10.0.12.3); eor: not_sent must name one of them")


def test_declared_peer_missing_in_a_vrf_with_no_sessions_message(monkeypatch):
    msg, _ = _peers_error({("r1", "RED", "10.0.12.9")}, [{}], monkeypatch)
    assert msg == ("nodes.r1.peers.RED/10.0.12.9: r1 has no BGP session to 10.0.12.9 in vrf RED "
                   "(its sessions: none); eor: not_sent must name one of them")


def test_declared_peer_in_a_vrf_the_node_lacks_names_no_sessions(monkeypatch):
    msg, _ = _peers_error({("r2", "BLUE", "10.1.1.1")}, [NoSuchInstance("no vrf")], monkeypatch)
    assert msg == ("nodes.r2.peers.BLUE/10.1.1.1: r2 has no BGP session to 10.1.1.1 in vrf BLUE "
                   "(its sessions: none); eor: not_sent must name one of them")


# ------------------------------------------------------------------------------------------- preflight

def _cfg(scenarios, **kw):
    return Config(path=Path("netdryrun.yml"), lab=Path("t.clab.yml"), timeout=30, checks=[], scenarios=scenarios, **kw)


def test_preflight_link_down_on_a_lab_without_links_names_none():
    lab = SimpleNamespace(nodes={"r1": Node("r1", "clab-t-r1", "linux", "frr")})
    sc = Scenario("s", [Fault("link_down", "r1", "eth1")], [])
    with pytest.raises(LabError, match=r"^" + re.escape(
            "scenario 's': link_down r1 eth1: not an interface of a link in the topology (links on r1: none); "
            "a fault on any other interface takes no lab link down") + r"$"):
        runner.preflight(_cfg([sc]), lab)


def test_preflight_link_down_on_an_unknown_interface_lists_the_links_of_the_node():
    lab = FakeLab(Clock(), nodes=("r1", "r2"),
                  links=[(("r1", "eth2"), ("r2", "eth1")), (("r1", "eth1"), ("r2", "eth2"))])
    sc = Scenario("sc", [Fault("link_down", "r1", "eth0")], [])
    with pytest.raises(LabError, match=r"^" + re.escape(
            "scenario 'sc': link_down r1 eth0: not an interface of a link in the topology "
            "(links on r1: eth1, eth2); a fault on any other interface takes no lab link down") + r"$"):
        runner.preflight(_cfg([sc]), lab)


# ------------------------------------------------------------------------------------------- run()

@pytest.mark.parametrize("kw,name", [({"settle": -1}, "--settle"), ({"hold": -1}, "--hold")])
def test_run_refuses_a_negative_duration_naming_the_option(monkeypatch, kw, name):
    e = make(monkeypatch)
    rep = e.run([leak("n")], **kw)
    assert rep.error == f"{name} must be a number of seconds >= 0, got -1"


def test_run_names_the_containers_not_running(monkeypatch):
    e = make(monkeypatch)
    e.lab.running = {"clab-t-r1"}
    rep = e.run([leak("n")])
    assert rep.error == "lab containers not running: clab-t-r2, clab-t-r3"


def test_run_logs_the_setup_it_runs(monkeypatch):
    e = make(monkeypatch)
    e.run([chk("route", "x", prefix="10.9.9.0/24")], deploy=True, setup={"r1": ["ip a"]})
    assert "Running setup on r1..." in e.logs


def test_run_puts_the_unwatched_sleep_back(monkeypatch):
    e = make(monkeypatch)
    e.run([chk("route", "x", prefix="10.9.9.0/24")])
    assert runner._sleep == e.clock.sleep


class _Eor:
    """A fake driver with one End-of-RIB answer for every neighbor it reports."""

    def __init__(self, inner, state):
        self.inner, self.state = inner, state

    def __getattr__(self, k):
        return getattr(self.inner, k)

    def end_of_rib(self, vrf, neighbors):
        return {a: {"*": self.state} for a in neighbors}


def _inject(prefix="10.66.0.0/16"):
    return Fault("inject_routes", "r2", prefixes=[prefix])


def test_an_untracked_end_of_rib_is_warned_once_per_run_across_the_gate_and_the_scenarios(monkeypatch):
    e = make(monkeypatch, r1={"neighbors": {"default": {"10.0.12.2": "established"}},
                              "routes": {"default": lambda t, p: False}})
    e.drivers["r1"] = _Eor(e.drivers["r1"], "untracked")
    sc = Scenario("s", [_inject()], [leak("[s] n2", prefix="10.77.0.0/16")])
    rep = e.run([leak("n")], [sc], settle=1, hold=3)
    assert rep.error == "" and rep.status == "passed" and len(rep.results) == 2
    got = [(r.check.name, w["code"], w["session"]) for r in rep.results for w in r.warnings]
    assert got == [("n", "eor-untracked", "10.0.12.2")]


def test_a_declared_not_sent_peer_is_not_waited_for_in_the_run_gate_or_in_a_scenario(monkeypatch):
    e = make(monkeypatch, r1={"neighbors": {"default": {"10.0.12.2": "established"}},
                              "routes": {"default": lambda t, p: False}})
    e.drivers["r1"] = _Eor(e.drivers["r1"], "unknown")
    sc = Scenario("s", [_inject()], [leak("[s] n2", prefix="10.77.0.0/16")])
    cfg = Config(path=Path("netdryrun.yml"), lab=Path("t.clab.yml"), timeout=30, checks=[leak("n")],
                 scenarios=[sc], eor_not_sent=frozenset({("r1", "default", "10.0.12.2")}))
    rep = runner.run(cfg, deploy=False, log=e.logs.append, settle=1, hold=3)
    assert rep.error == "" and rep.status == "passed" and [r.passed for r in rep.results] == [True, True]


def test_the_run_gate_does_not_wait_for_the_far_end_of_a_session_declared_down(monkeypatch):
    e = make(monkeypatch,
             r1={"neighbors": {"default": {"10.0.12.2": "idle", "10.0.13.3": "established"}},
                 "routes": {"default": lambda t, p: False}},
             r2={"neighbors": {"default": {"10.0.12.1": "idle"}}, "routes": {"default": lambda t, p: False}})
    down = chk("bgp_session", "r1-r2 down", node="r1", neighbor="10.0.12.2", state="down")
    rep = e.run([down, leak("n")], settle=1, hold=3)
    assert rep.error == "" and rep.status == "passed"
    assert [w for r in rep.results for w in r.warnings] == []
