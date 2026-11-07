"""A "pending" End-of-RIB toward a RouterOS peer in the lab is untracked, not waited for (coordinator, 2026-11-08).

RouterOS 7.x never sends End-of-RIB: local.eor is "" on every session in every RouterOS capture (it does receive one:
remote.eor "ip"), and FRR's read of its RouterOS peer stayed endOfRibRecv False for the whole live run (the watch log
of the isolated mikrotik rerun, kept as a fixture). Waiting for it only ever ran out the cap (600 s on the example)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import ipaddress

from netdryrun import runner
from netdryrun.lab import LabError

from test_eor_041 import EorDrv
from test_verdict_runner import leak, make

FX = Path(__file__).parent / "fixtures"
ROS = {"r2": ("mikrotik_ros", "vrnetlab/mikrotik_routeros:7.23.8")}


# ------------------------------------------------------------------------------------------- the premise, from captures

@pytest.mark.parametrize("name", ["routeros_eor_pending.txt", "routeros_eor_received.txt", "routeros_bgp_session.txt"])
def test_routeros_never_sends_end_of_rib_in_any_capture(name):
    text = (FX / name).read_text(encoding="utf-8")
    rows = json.loads(text[text.index("["):])
    assert rows and all(r["local.eor"] == "" for r in rows)
    assert any(r["remote.eor"] == "ip" for r in rows)       # it receives one: the field is real, not empty everywhere


def test_frr_never_saw_end_of_rib_from_routeros_over_a_whole_run():
    lines = (FX / "frr_eor_toward_routeros_watch.txt").read_text(encoding="utf-8").splitlines()
    up = [x for x in lines if " frr1: Established " in x]
    assert len(up) >= 25 and all("'endOfRibRecv': False" in x for x in up)


# ------------------------------------------------------------------------------------------- the gate

def _gate(e, negatives, warnings, lab=True):
    return runner._bgp_convergence_gate(negatives, negatives, e.drivers, log=e.logs.append, warnings=warnings,
                                        lab=e.lab if lab else None, extras={}, eor_reported=set())


class Owns:
    """A driver whose own addresses are `addrs` (as RouterOS's local_addresses reads them)."""

    def __init__(self, inner, *addrs):
        self.inner, self.addrs = inner, [ipaddress.ip_interface(a) for a in addrs]

    def __getattr__(self, k):
        return getattr(self.inner, k)

    def local_addresses(self, vrf="default"):
        return list(self.addrs)


def _pending(monkeypatch, state="pending", owns=("10.0.12.2/30",), **kw):
    e = make(monkeypatch, r1={"neighbors": {"default": {"10.0.12.2": "established"}}}, **kw)
    e.drivers["r1"] = EorDrv(e.drivers["r1"], lambda t: {"10.0.12.2": {"ipv4-unicast": state}})
    e.drivers["r2"] = Owns(e.drivers["r2"], *owns)
    return e


def _owner(e):
    return lambda n: e.drivers.get(n)


def test_pending_toward_a_routeros_peer_is_untracked_with_its_own_warning(monkeypatch):
    e = _pending(monkeypatch, kinds=ROS)
    neg = leak("n", timeout=30)
    w: dict = {}
    assert _gate(e, [neg], w) == {}
    assert e.clock.now < 30
    assert [(x["code"], x["session"], x["text"]) for x in w[id(neg)]] == [(
        "eor-untracked", "10.0.12.2",
        "convergence: r1's session to 10.0.12.2 is to r2, a RouterOS node (RouterOS 7.x doesn't send End-of-RIB), so "
        "its End-of-RIB can't be tracked; the gate judged it by stable prefix counts only (a route can still arrive "
        "later)")]


def test_pending_toward_any_other_kind_is_still_waited_for(monkeypatch):
    e = _pending(monkeypatch)
    neg = leak("n", timeout=30)
    assert id(neg) in _gate(e, [neg], {})


def test_unknown_toward_a_routeros_peer_is_still_waited_for(monkeypatch):
    """Only a read that says "pending" is excused: a read that failed ("unknown") is no read of RouterOS at all."""
    e = _pending(monkeypatch, state="unknown", kinds=ROS)
    neg = leak("n", timeout=30)
    assert id(neg) in _gate(e, [neg], {})


def test_without_the_lab_nothing_is_excused(monkeypatch):
    e = _pending(monkeypatch, kinds=ROS)
    neg = leak("n", timeout=30)
    assert id(neg) in _gate(e, [neg], {}, lab=False)


def test_unreadable_addresses_excuse_nothing(monkeypatch):
    e = _pending(monkeypatch, kinds=ROS)

    def no(node, iface):
        raise LabError("could not read")
    e.lab.interface_addresses = no
    neg = leak("n", timeout=30)
    assert id(neg) in _gate(e, [neg], {})


def test_a_shared_segment_with_another_kind_excuses_nothing(monkeypatch):
    kinds = {**ROS, "br": ("bridge", "")}
    links = [(("r1", "eth1"), ("br", "p1")), (("br", "p2"), ("r2", "eth1")), (("br", "p3"), ("r3", "eth1"))]
    e = _pending(monkeypatch, nodes=("r1", "r2", "r3", "br"), kinds=kinds)
    e.lab.links = links
    neg = leak("n", timeout=30)
    assert id(neg) in _gate(e, [neg], {})


def test_a_session_the_topology_cant_place_excuses_nothing(monkeypatch):
    """iBGP between loopbacks: no link subnet holds the address, so the RouterOS node isn't known to be the peer."""
    e = _pending(monkeypatch, kinds=ROS, owns=("10.0.12.2/30", "10.255.0.2/32", "fe80::2/64"))
    own = _owner(e)
    assert runner._routeros_peer(e.lab, "r1", "10.255.0.2", own) is None
    assert runner._routeros_peer(e.lab, "r1", "10.0.12.2", own) == "r2"
    assert runner._routeros_peer(e.lab, "r1", "10.0.12.2") is None            # no driver to read its addresses
    assert runner._routeros_peer(e.lab, "r1", "eth1", own) is None             # unnumbered: not placed here
    assert runner._routeros_peer(e.lab, "r1", "10.0.12.1", own) is None        # its own address, not a peer's


def test_a_link_local_neighbor_is_never_placed(monkeypatch):
    """Every Linux link holds an fe80::/64, so a link-local neighbor would match every link (adversary, finding 4)."""
    e = _pending(monkeypatch, kinds=ROS, owns=("fe80::2/64",))
    e.lab.addresses[("r1", "eth1")].append("fe80::1/64")
    assert runner._routeros_peer(e.lab, "r1", "fe80::2%eth1", _owner(e)) is None
    assert runner._routeros_peer(e.lab, "r1", "fe80::2", _owner(e)) is None


def test_an_address_the_routeros_node_doesnt_own_excuses_nothing(monkeypatch):
    """A router bridged through the RouterOS node, or behind it in a wide subnet, isn't the RouterOS node (adversary
    on the RouterOS diff, finding 1)."""
    e = _pending(monkeypatch, kinds=ROS, owns=("10.0.12.5/24",))
    e.lab.addresses[("r1", "eth1")] = ["10.0.12.1/24"]
    neg = leak("n", timeout=30)
    assert runner._routeros_peer(e.lab, "r1", "10.0.12.2", _owner(e)) is None
    assert id(neg) in _gate(e, [neg], {})


def test_a_routeros_node_whose_driver_isnt_chosen_excuses_nothing(monkeypatch):
    e = _pending(monkeypatch, kinds=ROS)
    assert runner._routeros_peer(e.lab, "r1", "10.0.12.2", lambda n: "beta driver not chosen") is None
    e.drivers["r2"].local_addresses = lambda vrf="default": (_ for _ in ()).throw(LabError("REST down"))
    assert runner._routeros_peer(e.lab, "r1", "10.0.12.2", _owner(e)) is None


def test_a_placement_that_failed_is_tried_again_on_the_next_sample(monkeypatch):
    """Verifier: RouterOS REST not up on the first sample must not pin the session to "waited for" for the run."""
    e = _pending(monkeypatch, kinds=ROS)
    up = {"n": 0}
    real = e.drivers["r2"].local_addresses

    def flaky(vrf="default"):
        up["n"] += 1
        if up["n"] <= 2:
            raise LabError("REST not up")
        return real(vrf)
    e.drivers["r2"].local_addresses = flaky
    neg = leak("n", timeout=60)
    w: dict = {}
    assert _gate(e, [neg], w) == {}
    assert e.clock.now < 60 and [x["code"] for x in w[id(neg)]] == ["eor-untracked"]


def test_the_routeros_address_is_read_in_the_sessions_vrf_too(monkeypatch):
    e = _pending(monkeypatch, kinds=ROS)
    seen = []
    e.drivers["r2"].local_addresses = lambda vrf="default": seen.append(vrf) or (
        [ipaddress.ip_interface("10.0.12.2/30")] if vrf == "RED" else [])
    assert runner._routeros_peer(e.lab, "r1", "10.0.12.2", _owner(e), "RED") == "r2"
    assert seen == ["RED"]                        # found there: default not read


def test_pending_toward_a_routeros_peer_of_another_node_is_untracked_too(monkeypatch):
    """The extra-node path: r1's check, r3 a routing node whose RouterOS peer r2 never sends End-of-RIB."""
    kinds = {"r2": ROS["r2"]}
    e = make(monkeypatch, kinds=kinds, r1={"neighbors": {"default": {"10.0.12.2": "established"}}},
             r3={"neighbors": {"default": {"10.0.23.2": "established"}}})
    e.lab.links = [(("r1", "eth1"), ("r2", "eth1")), (("r3", "eth1"), ("r2", "eth2"))]
    e.lab.addresses[("r3", "eth1")] = ["10.0.23.3/30"]
    e.drivers["r1"] = EorDrv(e.drivers["r1"], lambda t: {"10.0.12.2": {"ipv4-unicast": "received"}})
    e.drivers["r3"] = EorDrv(e.drivers["r3"], lambda t: {"10.0.23.2": {"ipv4-unicast": "pending"}})
    e.drivers["r2"] = Owns(e.drivers["r2"], "10.0.12.2/30", "10.0.23.2/30")
    neg = leak("n", timeout=30)
    w: dict = {}
    assert runner._bgp_convergence_gate([neg], [neg], {"r1": e.drivers["r1"]}, log=e.logs.append, warnings=w,
                                        lab=e.lab, extras={"r2": e.drivers["r2"], "r3": e.drivers["r3"]},
                                        eor_reported=set()) == {}
    assert ("eor-untracked", "r3", "10.0.23.2") in [(x["code"], x["node"], x["session"]) for x in w[id(neg)]]
    assert not any(x["code"] == "gate-eor-pending" for x in w[id(neg)])


def test_no_routeros_node_reads_no_addresses(monkeypatch):
    e = make(monkeypatch)
    e.lab.interface_addresses = lambda *a: pytest.fail("no RouterOS node: nothing to place")
    assert runner._routeros_peer(e.lab, "r1", "10.0.12.2") is None


def test_two_routeros_peers_in_the_subnet_excuse_nothing(monkeypatch):
    kinds = {**ROS, "r3": ("mikrotik_ros", "x"), "br": ("bridge", "")}
    e = make(monkeypatch, nodes=("r1", "r2", "r3", "br"), kinds=kinds)
    e.lab.links = [(("r1", "eth1"), ("br", "p1")), (("br", "p2"), ("r2", "eth1")), (("br", "p3"), ("r3", "eth1"))]
    assert runner._routeros_peer(e.lab, "r1", "10.0.12.2") is None
