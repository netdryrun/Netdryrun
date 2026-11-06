"""Every branch the 0.4.1 red-team batch added, exercised on purpose (release gate coverage floors: runner 98%, drivers
99%). Router output comes from the live captures in tests/fixtures; edits to it are named in each test."""
from __future__ import annotations

import ipaddress
import json
from pathlib import Path

import pytest

from netdryrun import runner
from netdryrun.drivers import addresses, eos, frr, nxos, routeros_state, srlinux
from netdryrun.drivers.base import BgpNeighbor, DriverError, NoSuchInstance
from netdryrun.drivers.eos import EosDriver
from netdryrun.drivers.nxos import NxosDriver
from netdryrun.drivers.frr import FrrDriver
from netdryrun.config import ConfigError

from test_verdict_drivers import Lab
from test_verdict_runner import Clock, FakeLab, leak, make

FX = Path(__file__).parent / "fixtures"


def fx(name):
    return (FX / name).read_text(encoding="utf-8")


def est(*addrs, pfx=None):
    return {a: BgpNeighbor(a, "established", dict(pfx or {"ipv4-unicast": 1})) for a in addrs}


# ------------------------------------------------------------------------------------------- driver base

def test_the_base_driver_cant_read_own_addresses_and_reads_eor_from_the_neighbors():
    d = FrrDriver.__mro__[1](Lab([]), "r1")   # Driver itself
    with pytest.raises(DriverError, match="own addresses"):
        d.local_addresses()
    nb = {"a": BgpNeighbor("a", "established", eor={"*": "pending"}), "b": BgpNeighbor("b", "idle")}
    assert d.end_of_rib("default", nb) == {"a": {"*": "pending"}}


# ------------------------------------------------------------------------------------------- addresses

def test_an_unparseable_address_is_unexpected():
    with pytest.raises(DriverError, match="not an address"):
        addresses.parse_ip_j_addr(json.dumps([{"ifname": "eth1", "addr_info": [{"local": "nope", "prefixlen": 24}]}]),
                                  True)


def test_eos_addresses_of_another_vrf_are_left_out():
    v4 = json.loads(fx("eos_local_ipv4.json"))
    v4["interfaces"]["Ethernet1"]["vrf"] = "RED"            # edit: Ethernet1 moved to VRF RED
    got = addresses.parse_eos_interfaces(json.dumps(v4), "default", "x")
    assert ipaddress.ip_interface("10.0.200.1/30") not in got
    assert [str(a) for a in addresses.parse_eos_interfaces(json.dumps(v4), "RED", "x")] == ["10.0.200.1/30"]


def test_junos_ifa_local_that_isnt_text_is_unexpected():
    bad = {"interface-information": [{"physical-interface": [{"ifa-local": [{"data": 5}]}]}]}
    with pytest.raises(DriverError, match="ifa-local"):
        addresses.parse_junos_terse(json.dumps(bad))


def test_a_shape_the_parser_doesnt_know_is_unexpected_not_a_traceback():
    with pytest.raises(DriverError):
        addresses.parse_nxos_ip_brief(json.dumps({"result": {"body": {"TABLE_intf": []}}}), "default")
    with pytest.raises(DriverError):
        addresses.parse_srl_addresses(json.dumps({"interface": [{"subinterface": [{"ipv4": {"address": [5]}}]}]}), "x")


def test_eos_and_nxos_drivers_read_their_own_addresses():
    d = EosDriver(Lab([("show ip interface", fx("eos_local_ipv4.json")),
                       ("show ipv6 interface", fx("eos_local_ipv6.json"))]), "r1")
    assert ipaddress.ip_interface("10.0.200.1/30") in d.local_addresses()
    n = NxosDriver(Lab([("show ip interface brief vrf all", fx("nxos_local_ip_brief.json"))]), "n1")
    assert [str(a) for a in n.local_addresses("RED")] == ["10.0.2.1/32"]


# ------------------------------------------------------------------------------------------- End-of-RIB readers

def test_frr_unexpected_gr_modes_and_shapes_are_unknown():
    info = json.loads(fx("frr_eor_pending.json"))["10.0.12.2"]
    g = info["gracefulRestartInfo"]
    assert frr.frr_eor({**info, "gracefulRestartInfo": {**g, "localGrMode": "Odd*"}}) == {"*": "unknown"}
    assert frr.frr_eor({**info, "gracefulRestartInfo": {**g, "endOfRibRecv": []}}) == {"*": "unknown"}
    no_blocks = {k: v for k, v in g.items() if k != "ipv4Unicast"}
    assert frr.frr_eor({**info, "gracefulRestartInfo": no_blocks}) == {"*": "unknown"}


def test_srlinux_family_without_gr_is_untracked_and_junk_is_unknown():
    n = json.loads(fx("srl_eor_gr_baseline.txt"))
    n.pop("received-end-of-rib")
    n["graceful-restart"]["neighbor-capability"]["afi-safi"] = [{"name": "ipv6-unicast"}]   # edit: GR for v6 only
    assert srlinux.srl_eor(n) == {"ipv4-unicast": "untracked"}
    assert srlinux.srl_eor({**n, "afi-safi": 5}) == {"*": "unknown"}
    assert srlinux.srl_eor({**n, "advertised-capabilities": "GRACEFUL_RESTART"}) == {"*": "unknown"}


def test_routeros_unknown_family_names_are_unknown():
    row = {r["remote.address"]: r for r in json.loads(fx("routeros_eor_pending.txt")[4:])}["192.0.2.2"]
    assert routeros_state.ros_eor({**row, "remote.afi": "vpnv4"}) == {"*": "unknown"}
    assert routeros_state.ros_eor({**row, "remote.capabilities": None}) == {"*": "unknown"}


def test_eos_without_end_of_rib_data_reads_untracked_or_unknown():
    p = json.loads(fx("eos_eor_gr_default.json"))["vrfs"]["default"]["peerList"][0]
    bare = {k: v for k, v in p.items() if k != "endOfRibs"}
    caps = dict(bare.get("neighborCapabilities", {}))
    caps.pop("grCaps", None)
    assert eos.eos_eor({**bare, "neighborCapabilities": caps}) == {"*": "untracked"}
    assert eos.eos_eor(bare) == {"*": "unknown"}                      # the peer sent the GR capability
    assert eos.parse_eos_eor("not json", "default") == {}
    assert eos._eor_key("Ethernet1") == "Ethernet1" and eos._eor_key("2001:DB8::1") == "2001:db8::1"


def test_eos_end_of_rib_reads_both_families_and_unread_is_unknown():
    v4 = fx("eos_eor_pending.txt")
    d = EosDriver(Lab([("show ip bgp neighbors vrf default", v4),
                       ("show ipv6 bgp neighbors vrf default", '{"vrfs": {"default": {"peerList": []}}}')]), "r1")
    got = d.end_of_rib("default", est("10.0.200.2", "2001:db8::9"))
    assert got == {"10.0.200.2": {"ipv4-unicast": "pending"}, "2001:db8::9": {"*": "unknown"}}
    assert d.end_of_rib("default", {"x": BgpNeighbor("x", "idle")}) == {}
    broken = EosDriver(Lab([("show ip bgp neighbors", (1, "", "boom"))]), "r1")
    assert broken.end_of_rib("default", est("10.0.200.2")) == {"10.0.200.2": {"*": "unknown"}}


def test_nxos_end_of_rib_per_neighbor_and_family():
    d = NxosDriver(Lab([("neighbors 10.0.1.2 vrf default", fx("nxos_eor_pending.txt")),
                        ("neighbors 10.9.9.9", (1, "", "unreachable"))]), "n1")
    nb = {**est("10.0.1.2"), **est("10.9.9.9"), "Eth1/1": BgpNeighbor("Eth1/1", "established"),
          "10.7.7.7": BgpNeighbor("10.7.7.7", "idle")}
    got = d.end_of_rib("default", nb)
    assert got == {"10.0.1.2": {"ipv4-unicast": "pending"}, "10.9.9.9": {"ipv4-unicast": "unknown"},
                   "Eth1/1": {"ipv4-unicast": "unknown"}}   # never a device string in a command


def test_nxos_ascii_reply_forms():
    assert nxos._ascii_msg("not json") is None
    assert nxos._ascii_msg(json.dumps({"result": [{"msg": "x"}]})) == "x"
    assert nxos._ascii_msg(json.dumps({"result": [{"msg": 5}]})) is None


# ------------------------------------------------------------------------------------------- runner: far ends

def _lab(addresses_, links, nodes=("r1", "r2", "r3")):
    return FakeLab(Clock(), nodes=nodes, addresses=addresses_, links=links)


def test_unnumbered_far_end_only_with_one_peer():
    lab = _lab({}, [(("r1", "eth1"), ("r2", "eth1"))])
    assert runner._far_ends(lab, {("r1", "default", "eth1")}) == {("r2", "default", "eth1")}
    bridged = FakeLab(Clock(), nodes=("r1", "r2", "r3", "ix"), kinds={"ix": ("bridge", "")}, addresses={},
                      links=[(("r1", "eth1"), ("ix", "p1")), (("r2", "eth1"), ("ix", "p2")), (("r3", "eth1"), ("ix", "p3"))])
    assert runner._far_ends(bridged, {("r1", "default", "eth1")}) == set()


def test_far_end_not_placed_is_not_excluded():
    lab = _lab({("r1", "eth1"): ["10.0.12.1/30"], ("r2", "eth1"): ["10.0.12.2/30"]}, [(("r1", "eth1"), ("r2", "eth1"))])
    assert runner._far_ends(lab, {("r1", "default", None)}) == set()
    assert runner._far_ends(lab, {("r1", "default", "swp9")}) == set()           # a name, not this link's
    assert runner._far_ends(lab, {("r1", "default", "192.0.2.9")}) == set()      # not in the link's subnet

    class Unreadable(FakeLab):
        def __init__(self, broken):
            super().__init__(Clock(), addresses={("r1", "eth1"): ["10.0.12.1/30"], ("r2", "eth1"): ["10.0.12.2/30"]})
            self.broken = broken

        def interface_addresses(self, node, iface):
            if node == self.broken:
                raise RuntimeError("unreadable")
            return super().interface_addresses(node, iface)
    for broken in ("r1", "r2"):
        assert runner._far_ends(Unreadable(broken), {("r1", "default", "10.0.12.2")}) == set()


# ------------------------------------------------------------------------------------------- runner: the gate

class EorDrv:
    def __init__(self, inner, eor):
        self.inner, self.eor = inner, eor

    def __getattr__(self, k):
        return getattr(self.inner, k)

    def end_of_rib(self, vrf, neighbors):
        return self.eor(self.inner.clock.now)


def gate(e, negatives, extras=None, warnings=None, reported=None, all_checks=None):
    return runner._bgp_convergence_gate(negatives, all_checks or negatives, e.drivers, log=e.logs.append,
                                        warnings=warnings, extras=extras or {}, eor_reported=reported)


def test_a_driver_whose_end_of_rib_raises_reads_unknown(monkeypatch):
    e = make(monkeypatch, r1={"neighbors": {"default": {"10.0.12.2": "established"}}})

    def boom(t):
        raise RuntimeError("bug")
    e.drivers["r1"] = EorDrv(e.drivers["r1"], boom)
    neg = leak("n", timeout=30)
    assert id(neg) in gate(e, [neg], warnings={})


def test_an_end_of_rib_answer_that_isnt_a_map_is_skipped(monkeypatch):
    e = make(monkeypatch, r1={"neighbors": {"default": {"10.0.12.2": "established"}}})
    e.drivers["r1"] = EorDrv(e.drivers["r1"], lambda t: {"10.0.12.2": "received"})
    assert gate(e, [leak("n", timeout=30)], warnings={}) == {}


def test_an_extra_node_that_turns_unreadable_or_keeps_counting_warns_at_the_cap(monkeypatch):
    e = make(monkeypatch, r1={"neighbors": {"default": {"10.0.12.2": "established"}}},
             r2={"neighbors": {"default": {"10.0.23.3": "established"}},
                 "neighbors_error": lambda t: DriverError("cli gone") if t > 0 else None},
             r3={"neighbors": {"default": lambda t: {"10.0.23.2": ("established", {"ipv4-unicast": int(t)})}}})
    neg = leak("n", timeout=30)
    w: dict = {}
    assert gate(e, [neg], extras={"r2": e.drivers["r2"], "r3": e.drivers["r3"]}, warnings=w) == {}
    assert sorted(x["code"] for x in w[id(neg)]) == ["gate-counts-moving", "gate-unreadable"]


def test_untracked_without_a_run_set_warns_each_time(monkeypatch):
    e = make(monkeypatch, r1={"neighbors": {"default": {"10.0.12.2": "established"}}})
    e.drivers["r1"] = EorDrv(e.drivers["r1"], lambda t: {"10.0.12.2": {"*": "untracked"}})
    a = leak("a", timeout=30)
    for _ in range(2):
        w: dict = {}
        gate(e, [a], warnings=w, reported=None)
        assert [x["code"] for x in w[id(a)]] == ["eor-untracked"]


def test_untracked_on_a_blocked_node_has_nowhere_to_go(monkeypatch):
    e = make(monkeypatch, r1={"neighbors": {"default": {"10.0.12.2": "established", "10.0.13.3": "active"}}})
    e.drivers["r1"] = EorDrv(e.drivers["r1"], lambda t: {"10.0.12.2": {"*": "untracked"}})
    a = leak("a", timeout=30)
    w: dict = {}
    assert id(a) in gate(e, [a], warnings=w, reported=set())
    assert w == {}


# ------------------------------------------------------------------------------------------- runner: declared peers

class Flaky:
    def __init__(self, answers):
        self.answers = list(answers)

    def bgp_neighbors(self, vrf="default"):
        a = self.answers.pop(0)
        if isinstance(a, Exception):
            raise a
        return type("O", (), {"value": a})()


def test_declared_peer_read_is_retried_then_checked(monkeypatch):
    monkeypatch.setattr(runner, "_sleep", lambda s: None)
    d = Flaky([DriverError("blip"), {"10.0.12.2": None}])
    runner._check_declared_peers({("r1", "default", "10.0.12.2")}, lambda n: d)
    d = Flaky([DriverError("a"), DriverError("b"), DriverError("c")])
    with pytest.raises(DriverError):
        runner._check_declared_peers({("r1", "default", "10.0.12.2")}, lambda n: d)


def test_declared_peer_in_a_vrf_the_node_doesnt_have_is_a_config_error(monkeypatch):
    d = Flaky([NoSuchInstance("no vrf RED")])
    with pytest.raises(ConfigError, match="in vrf RED"):
        runner._check_declared_peers({("r1", "RED", "10.0.12.2")}, lambda n: d)


def test_canon_ip_keeps_a_name():
    assert runner._canon_ip("Eth1/1") == "Eth1/1" and runner._canon_ip("fe80::1%eth1") == "fe80::1"
