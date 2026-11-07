"""Exact tests for the mutation survivors of 5d36e9b (2026-11-08): _routeros_peer's placement edges, the gate passing
the session's VRF to it, and the node named in the readiness error."""
from __future__ import annotations

import ipaddress
from types import SimpleNamespace

import pytest

from netdryrun import mgmt, runner
from netdryrun.lab import LabError, Node

from test_eor_routeros_peer import ROS, Owns
from test_mgmt import RouteLab
from test_verdict_runner import leak, make


def _drv(*addrs):
    return SimpleNamespace(local_addresses=lambda vrf="default": [ipaddress.ip_interface(a) for a in addrs])


def _lab(nodes, links, addresses):
    lab = SimpleNamespace(nodes={n: Node(n, f"clab-t-{n}", *k) for n, k in nodes.items()}, links=links)
    lab.interface_addresses = lambda node, iface: [ipaddress.ip_interface(a) for a in addresses.get((node, iface), [])]
    lab.peers_of = lambda node, iface: runner.Lab.peers_of(lab, node, iface)
    return lab


LINUX = ("linux", "quay.io/frrouting/frr:10.4.1")
MT = ("mikrotik_ros", "x")


def test_a_lab_without_nodes_or_links_places_nothing():
    assert runner._routeros_peer(object(), "r1", "10.0.12.2", lambda n: _drv("10.0.12.2/30")) is None
    lab = SimpleNamespace(nodes={"r2": Node("r2", "c", *MT)})          # no links attribute at all
    assert runner._routeros_peer(lab, "r1", "10.0.12.2", lambda n: _drv("10.0.12.2/30")) is None


def test_a_zoned_address_is_never_placed_even_when_global():
    lab = _lab({"r1": LINUX, "r2": MT}, [(("r1", "eth1"), ("r2", "eth1"))], {("r1", "eth1"): ["10.0.12.1/30"]})
    own = lambda n: _drv("10.0.12.2/30")   # noqa: E731
    assert runner._routeros_peer(lab, "r1", "10.0.12.2", own) == "r2"
    assert runner._routeros_peer(lab, "r1", "10.0.12.2%eth1", own) is None


def test_the_node_may_be_either_end_and_its_own_interface_is_read():
    """r1 second on the link, its interface named differently from the RouterOS side's."""
    lab = _lab({"r1": LINUX, "r2": MT}, [(("r2", "eth5"), ("r1", "eth1"))], {("r1", "eth1"): ["10.0.12.1/30"]})
    assert runner._routeros_peer(lab, "r1", "10.0.12.2", lambda n: _drv("10.0.12.2/30")) == "r2"


def test_a_link_without_the_subnet_doesnt_stop_the_search():
    lab = _lab({"r1": LINUX, "r2": MT, "r3": LINUX},
               [(("r1", "eth2"), ("r3", "eth1")), (("r1", "eth1"), ("r2", "eth1"))],
               {("r1", "eth2"): ["10.0.13.1/30"], ("r1", "eth1"): ["10.0.12.1/30"]})
    assert runner._routeros_peer(lab, "r1", "10.0.12.2", lambda n: _drv("10.0.12.2/30")) == "r2"


def test_a_single_peer_of_another_kind_that_owns_the_address_is_not_routeros():
    lab = _lab({"r1": LINUX, "r2": MT, "r3": LINUX}, [(("r1", "eth1"), ("r3", "eth1"))], {("r1", "eth1"): ["10.0.13.1/30"]})
    assert runner._routeros_peer(lab, "r1", "10.0.13.3", lambda n: _drv("10.0.13.3/30")) is None


def test_a_peer_that_isnt_a_lab_node_places_nothing():
    lab = _lab({"r1": LINUX, "r2": MT}, [(("r1", "eth1"), ("ghost", "eth1"))], {("r1", "eth1"): ["10.0.12.1/30"]})
    assert runner._routeros_peer(lab, "r1", "10.0.12.2", lambda n: _drv("10.0.12.2/30")) is None


def test_two_routeros_nodes_over_two_links_place_nothing():
    lab = _lab({"r1": LINUX, "r2": MT, "r3": MT},
               [(("r1", "eth1"), ("r2", "eth1")), (("r1", "eth2"), ("r3", "eth1"))],
               {("r1", "eth1"): ["10.0.12.1/24"], ("r1", "eth2"): ["10.0.12.5/24"]})
    assert runner._routeros_peer(lab, "r1", "10.0.12.2", lambda n: _drv("10.0.12.2/24")) is None


def test_the_default_table_is_read_when_the_sessions_vrf_doesnt_hold_it():
    lab = _lab({"r1": LINUX, "r2": MT}, [(("r1", "eth1"), ("r2", "eth1"))], {("r1", "eth1"): ["10.0.12.1/30"]})
    seen = []

    def own(vrf="default"):
        seen.append(vrf)
        return [ipaddress.ip_interface("10.0.12.2/30")] if vrf == "default" else []
    assert runner._routeros_peer(lab, "r1", "10.0.12.2", lambda n: SimpleNamespace(local_addresses=own), "RED") == "r2"
    assert seen == ["RED", "default"]


def test_a_vrf_read_that_fails_still_reads_the_default_table():
    lab = _lab({"r1": LINUX, "r2": MT}, [(("r1", "eth1"), ("r2", "eth1"))], {("r1", "eth1"): ["10.0.12.1/30"]})

    def own(vrf="default"):
        if vrf == "RED":
            raise LabError("no table RED")
        return [ipaddress.ip_interface("10.0.12.2/30")]
    assert runner._routeros_peer(lab, "r1", "10.0.12.2", lambda n: SimpleNamespace(local_addresses=own), "RED") == "r2"


def test_a_row_without_an_address_is_skipped_not_fatal():
    lab = _lab({"r1": LINUX, "r2": MT}, [(("r1", "eth1"), ("r2", "eth1"))], {("r1", "eth1"): ["10.0.12.1/30"]})
    drv = SimpleNamespace(local_addresses=lambda vrf="default": [object(), ipaddress.ip_interface("10.0.12.2/30")])
    assert runner._routeros_peer(lab, "r1", "10.0.12.2", lambda n: drv) == "r2"


def test_the_gate_passes_the_sessions_vrf(monkeypatch):
    """The session in VRF RED: the RouterOS node owns the address there only."""
    e = make(monkeypatch, kinds=ROS, r1={"neighbors": {"RED": {"10.0.12.2": "established"}}})
    from test_eor_041 import EorDrv
    e.drivers["r1"] = EorDrv(e.drivers["r1"], lambda t: {"10.0.12.2": {"ipv4-unicast": "pending"}})

    def own(vrf="default"):
        return [ipaddress.ip_interface("10.0.12.2/30")] if vrf == "RED" else []
    e.drivers["r2"] = Owns(e.drivers["r2"])
    e.drivers["r2"].local_addresses = own
    neg = leak("n", timeout=30, vrf="RED")
    w: dict = {}
    assert runner._bgp_convergence_gate([neg], [neg], e.drivers, log=e.logs.append, warnings=w, lab=e.lab,
                                        extras={}, eor_reported=set()) == {}
    assert [x["code"] for x in w[id(neg)]] == ["eor-untracked"]


@pytest.mark.parametrize("kind,patch", [(("ceos", "c"), "_eos_config"), (("juniper_cjunosevolved", "cj"), "_junos_answers")])
def test_the_readiness_error_names_the_node(monkeypatch, kind, patch):
    def never(*a, **k):
        raise LabError("cli down")
    monkeypatch.setattr(mgmt, patch, never)
    with pytest.raises(LabError) as e:
        mgmt.prepare(RouteLab(nodes=["x7"], kinds={"x7": kind}), [], sleep=lambda s: None)
    assert "so x7's route out over the management network" in str(e.value)


def test_a_self_link_on_the_node_is_read_on_both_ends():
    """A link from r1 to itself (eth3-eth4): eth4 holds the subnet with no peer beyond, so the session can't be placed
    (the eth3 end without the subnet must not end the search of that link)."""
    lab = _lab({"r1": LINUX, "r2": MT}, [(("r1", "eth3"), ("r1", "eth4")), (("r1", "eth1"), ("r2", "eth1"))],
               {("r1", "eth4"): ["10.0.12.9/24"], ("r1", "eth1"): ["10.0.12.1/24"]})
    assert runner._routeros_peer(lab, "r1", "10.0.12.2", lambda n: _drv("10.0.12.2/24")) is None
