"""The 0.4.1 red-team round-4 fixes (design/redteam-041-fixes-round4.md), items a-d and f-j.

a (RT-0044): a driver that read IPv4 own addresses only let a ping to its IPv6 own address pass; each driver now declares
the families its read covers, and the ping check reads a target of another family unready. b (RT-0045): the NX-OS brief
form leaves secondary addresses out and has no masks. c (RT-0046): an EOS `ip address virtual` is the node's own. d
(RT-0047): the IPv6 subnet-router anycast address of an own prefix is answered by the node itself. f (B2): a ping-only
node whose BGP read fails says so. g (B1): a node the file says runs BGP that is never readable is not evaluated. h: a
session carrying a family its End-of-RIB read doesn't list is untracked. i: the address parsers refuse shapes they don't
know. j: JUnit carries the convergence warnings.

Each fix test is red on add4b2f (missing there, or accepted/passed there): 33 of 37. The four that pass there are
controls that keep the fixes from over-refusing (a declared family, an unset EOS virtual address, a /127 and another
prefix, a family without routes or the "*" read). A NameError in the new ping refusal (DriverError not imported in
checks.py) survived the whole suite until test_a_target_of_a_family_the_driver_cant_read_is_unready.
"""
from __future__ import annotations

import ipaddress
import json
from pathlib import Path

import pytest

from netdryrun import checks, report, runner
from netdryrun.checks import Result
from netdryrun.config import Check, Config
from netdryrun.drivers import addresses
from netdryrun.drivers.base import BgpNeighbor, Driver, DriverError
from netdryrun.drivers.eos import EosDriver
from netdryrun.drivers.frr import FrrDriver
from netdryrun.drivers.junos import JunosDriver
from netdryrun.drivers.nxos import NxosDriver
from netdryrun.drivers.routeros import RouterosDriver
from netdryrun.drivers.sonic import SonicDriver
from netdryrun.drivers.srlinux import SrlDriver
from netdryrun.runner import RunReport

from test_verdict_drivers import Lab
from test_verdict_runner import chk, leak, make

FX = Path(__file__).parent / "fixtures"


def fx(name):
    return (FX / name).read_text(encoding="utf-8")


def nxos_own(vrf="default"):
    lab = Lab([("show ip interface vrf all", fx("nxos_local_ip_detail.json")),
               ("show ipv6 interface vrf all", fx("nxos_local_ipv6_detail.json"))])
    return NxosDriver(lab, "n1").local_addresses(vrf)


def eos_with(**ia):
    d = json.loads(fx("eos_local_ipv4.json"))
    name = next(iter(d["interfaces"]))
    d["interfaces"][name]["interfaceAddress"].update(ia)
    return addresses.parse_eos_interfaces(json.dumps(d), "default", "show ip interface")


# ------------------------------------------------------------------------------------------- a: families

ALL_DRIVERS = [FrrDriver, SonicDriver, EosDriver, NxosDriver, RouterosDriver, SrlDriver, JunosDriver]


@pytest.mark.parametrize("cls", ALL_DRIVERS, ids=lambda c: c.__name__)
def test_every_driver_declares_both_families_its_own_address_read_covers(cls):
    assert cls.own_address_families == frozenset({4, 6})


def test_the_base_driver_declares_no_family():
    assert Driver.own_address_families == frozenset()


class _V4Only:
    name = "v4only"
    own_address_families = frozenset({4})

    def local_addresses(self, vrf="default"):
        return [ipaddress.ip_interface("10.0.0.1/30")]

    def ping(self, *a):
        raise AssertionError("the ping must not run")


def test_a_target_of_a_family_the_driver_cant_read_is_unready():
    with pytest.raises(DriverError, match="own IPv6 addresses can't be read on the v4only driver"):
        checks._ping(_V4Only(), {"node": "r1", "target": "2001:db8::1"})


def test_a_driver_that_inherits_no_declaration_is_unready_for_every_family():
    class Bare(Driver):
        name = "bare"

        def local_addresses(self, vrf="default"):
            return []
    for target in ("10.0.0.9", "2001:db8::9"):
        with pytest.raises(DriverError, match="can't be read on the bare driver"):
            checks._ping(Bare(Lab([]), "r1"), {"node": "r1", "target": target})


def test_a_declared_family_is_checked_against_the_own_addresses():
    class Plain(_V4Only):
        own_address_families = frozenset({4, 6})

        def local_addresses(self, vrf="default"):
            return [ipaddress.ip_interface("2001:db8::1/64")]
    with pytest.raises(DriverError, match="never leaves"):
        checks._ping(Plain(), {"node": "r1", "target": "2001:db8::1"})


# ------------------------------------------------------------------------------------------- a, b: NX-OS

@pytest.mark.parametrize("target", ["2001:db8:1::1",     # RT-0044: the IPv6 own address
                                    "10.0.33.1",         # RT-0045: the secondary
                                    "10.0.1.3",          # a /30's broadcast (the brief form had no mask)
                                    "192.168.10.1"])
def test_nxos_refuses_every_own_address_in_the_default_vrf(target):
    with pytest.raises(DriverError, match="never leaves|broadcast"):
        addresses.refuse_own_target("n1", target, nxos_own())


def test_nxos_own_addresses_exactly():
    assert sorted(map(str, nxos_own())) == sorted([
        "192.168.10.1/32", "10.0.1.1/30", "10.0.3.1/30", "10.0.33.1/30", "2001:db8:1::1/64"]
        + [str(a) for a in nxos_own() if a.version == 6 and a.is_link_local])
    assert sorted(map(str, nxos_own("RED")))[:2] == ["10.0.2.1/30", "2001:db8:2::1/64"]


def test_nxos_a_peer_and_another_vrf_are_not_own():
    addresses.refuse_own_target("n1", "10.0.1.2", nxos_own())
    addresses.refuse_own_target("n1", "10.0.2.1", nxos_own())       # RED's, not default's


# ------------------------------------------------------------------------------------------- c: EOS virtual

def test_eos_virtual_ip_and_its_secondaries_are_own():
    own = eos_with(virtualIp={"address": "10.1.1.1", "maskLen": 24},
                   virtualSecondaryIpsOrderedList=[{"address": "10.2.2.1", "maskLen": 24}])
    for target in ("10.1.1.1", "10.2.2.1", "10.1.1.255"):
        with pytest.raises(DriverError, match="never leaves|broadcast"):
            addresses.refuse_own_target("e1", target, own)


def test_eos_unset_virtual_ip_is_skipped():
    assert "0.0.0.0/0" not in map(str, eos_with())
    addresses.refuse_own_target("e1", "10.9.9.9", eos_with())


# ------------------------------------------------------------------------------------------- d: anycast

def test_ipv6_subnet_router_anycast_is_refused():
    with pytest.raises(DriverError, match="subnet-router anycast"):
        addresses.refuse_own_target("r1", "2001:db8:1::", [ipaddress.ip_interface("2001:db8:1::1/64")])


def test_a_127_has_no_subnet_router_anycast_and_another_prefix_is_not_own():
    addresses.refuse_own_target("r1", "2001:db8:1::", [ipaddress.ip_interface("2001:db8:1::1/127")])
    addresses.refuse_own_target("r1", "2001:db8:2::", [ipaddress.ip_interface("2001:db8:1::1/64")])


# ------------------------------------------------------------------------------------------- f, g: gate

def test_b2_a_ping_only_node_whose_read_fails_is_waited_for_then_warned(monkeypatch):
    e = make(monkeypatch)
    e.drivers["r1"].neighbors_error = lambda t: DriverError("vtysh: bgpd is not running") if t < 6 else None
    e.drivers["r1"].neighbors = {"default": {"10.0.12.2": "established"}}
    p = chk("ping", "p", target="10.9.9.9", expect="failure", timeout=60)
    w: dict = {}
    # a bgpd still starting: the gate keeps reading and releases the ping once the node shows it converged
    assert runner._bgp_convergence_gate([p], [p], e.drivers, log=e.logs.append, warnings=w) == {}
    assert 6 <= e.clock.now < 60 and id(p) not in w


def test_b2_never_readable_ping_only_node_is_warned_at_the_cap(monkeypatch):
    e = make(monkeypatch)
    e.drivers["r1"].neighbors_error = DriverError("vtysh: bgpd is not running")
    p = chk("ping", "p", target="10.9.9.9", expect="failure", timeout=60)
    w: dict = {}
    assert runner._bgp_convergence_gate([p], [p], e.drivers, log=e.logs.append, warnings=w) == {}
    text = "convergence: r1's BGP state could not be read by the cap (60s); the check was evaluated without the BGP gate"
    assert [(x["code"], x["node"], x["text"]) for x in w[id(p)]] == [("gate-unreadable", "r1", text)]
    assert "warning: " + text in e.logs


def test_b1_a_bgp_node_never_readable_is_not_evaluated(monkeypatch):
    e = make(monkeypatch)
    e.drivers["r1"].neighbors_error = DriverError("cli timeout")
    neg = leak("n", timeout=6)
    sess = chk("bgp_session", "s", neighbor="10.0.12.2", state="established", timeout=6)
    blocked = runner._bgp_convergence_gate([neg], [neg, sess], e.drivers, log=e.logs.append, warnings={})
    r = blocked[id(neg)]
    assert not r.passed and r.samples_passed == 0 and r.samples_unready == r.attempts > 0
    assert str(r.detail).startswith("not evaluated: r1's BGP state could not be read by the cap (6s): cli timeout")


def test_g_a_node_without_bgp_checks_never_readable_is_warned(monkeypatch):
    e = make(monkeypatch)
    e.drivers["r1"].neighbors_error = DriverError("cli timeout")
    neg = leak("n", timeout=6)
    w: dict = {}
    assert runner._bgp_convergence_gate([neg], [neg], e.drivers, log=e.logs.append, warnings=w) == {}
    assert [x["text"] for x in w[id(neg)]] == [
        "convergence: r1's BGP state could not be read by the cap (6s); the check was evaluated without the BGP gate"]


# ------------------------------------------------------------------------------------------- h: untracked family

class _Eor:
    def __init__(self, inner, eor):
        self.inner, self.eor = inner, eor

    def __getattr__(self, k):
        return getattr(self.inner, k)

    def end_of_rib(self, vrf, neighbors):
        return self.eor


def test_h_a_carried_family_missing_from_the_end_of_rib_read_is_untracked(monkeypatch):
    e = make(monkeypatch, r1={"neighbors": {"default": {"10.0.12.2": BgpNeighbor(
        "10.0.12.2", "established", {"ipv4-unicast": 3, "ipv6-unicast": 2})}}})
    e.drivers["r1"] = _Eor(e.drivers["r1"], {"10.0.12.2": {"ipv4-unicast": "received"}})
    neg = leak("n", timeout=9)
    w: dict = {}
    runner._bgp_convergence_gate([neg], [neg], e.drivers, log=e.logs.append, warnings=w, eor_reported=set())
    assert [(x["code"], x["session"]) for x in w[id(neg)]] == [("eor-untracked", "10.0.12.2")]


def test_h_an_empty_family_or_the_star_is_not_untracked(monkeypatch):
    for fams, v6 in (({"ipv4-unicast": "received"}, 0), ({"*": "received"}, 2)):
        e = make(monkeypatch, r1={"neighbors": {"default": {"10.0.12.2": BgpNeighbor(
            "10.0.12.2", "established", {"ipv4-unicast": 3, "ipv6-unicast": v6})}}})
        e.drivers["r1"] = _Eor(e.drivers["r1"], {"10.0.12.2": fams})
        neg = leak("n", timeout=9)
        w: dict = {}
        runner._bgp_convergence_gate([neg], [neg], e.drivers, log=e.logs.append, warnings=w, eor_reported=set())
        assert id(neg) not in w


# ------------------------------------------------------------------------------------------- i: strict parsers

@pytest.mark.parametrize("call", [
    lambda: addresses.parse_ip_j_addr(json.dumps([{"ifname": "eth1"}]), True),                     # no addr_info
    lambda: addresses.parse_eos_interfaces(json.dumps({"interfaces": {"Ethernet1": {
        "name": "Ethernet1", "vrf": "default", "interfaceAddress": "10.0.0.1"}}}), "default", "x"),
    lambda: addresses.parse_eos_interfaces(json.dumps({"interfaces": {"Ethernet1": {
        "name": "Ethernet1", "vrf": "default", "interfaceAddress": {"primaryIp": {"maskLen": 30}}}}}), "default", "x"),
    lambda: addresses.parse_eos_interfaces(json.dumps({"interfaces": {"Ethernet1": {
        "name": "Ethernet1", "vrf": "default", "addresses": [{"subnet": "x/64"}]}}}), "default", "x"),
    lambda: addresses.parse_srl_addresses(json.dumps({"interface": [{"name": "e1", "subinterface": {}}]}), "x"),
    lambda: addresses.parse_srl_addresses(json.dumps({"interface": [{"name": "e1", "subinterface": [
        {"index": 0, "ipv4": {"address": {}}}]}]}), "x"),
    lambda: addresses.parse_nxos_ip_brief(json.dumps({"result": {"body": {"TABLE_intf": {"ROW_intf": [
        {"intf-name": "Eth1/1", "vrf-name-out": "default"}]}}}}), "default"),
    lambda: addresses.parse_nxos_ip_detail(json.dumps({"result": {"body": {"TABLE_intf": {"ROW_intf": [
        {"intf-name": "Eth1/1", "vrf-name-out": "default", "prefix": "10.0.0.1"}]}}}}), "default"),
    lambda: addresses.parse_nxos_ip_detail(json.dumps({"result": {"body": {"TABLE_intf": {"ROW_intf": [
        {"intf-name": "Eth1/1", "vrf-name-out": "default", "prefix": "10.0.0.1", "masklen": 30,
         "TABLE_secondary_address": {"ROW_secondary_address": {"prefix1": "10.0.9.1"}}}]}}}}), "default"),
    lambda: addresses.parse_nxos_ipv6_detail(json.dumps({"result": {"body": {"TABLE_intf": {"ROW_intf": [
        {"intf-name": "Eth1/1", "vrf-name-out": "default"}]}}}}), "default"),
], ids=["ip-j-no-addr_info", "eos-ia-not-map", "eos-entry-no-address", "eos-v6-no-address", "srl-sub-not-list",
        "srl-address-not-list", "nxos-brief-no-prefix", "nxos-detail-no-masklen", "nxos-secondary-no-masklen",
        "nxos-v6-no-table"])
def test_an_unknown_address_shape_is_unexpected_never_no_addresses(call):
    with pytest.raises(DriverError):
        call()


# ------------------------------------------------------------------------------------------- j: JUnit

def test_junit_carries_the_warnings_and_keeps_the_status():
    c = Check(type="route", params={"node": "r1", "prefix": "10.66.0.0/16", "present": False}, name="n", timeout=30)
    r = Result(c, True, "absent", 3, 3.0, "t", samples_passed=3,
               warnings=[{"code": "gate-unreadable", "node": "r1", "session": "", "text": "convergence: <x> & y"}])
    cfg = Config(path=Path("netdryrun.yml"), lab=Path("topo.clab.yml"), timeout=30, checks=[c])
    junit = report.to_junit(RunReport(config=cfg, lab_name="t", results=[r]))
    assert "<system-out>warning: convergence: &lt;x&gt; &amp; y</system-out>" in junit
    assert 'failures="0" errors="0"' in junit and "<failure" not in junit


# ------------------------------------------------------------------------------------------- code adversary (round 4)

def test_b1_doesnt_block_a_vrf_the_file_doesnt_say_runs_bgp(monkeypatch):
    # r1 runs BGP in the default VRF only; RED has no BGP instance at all
    e = make(monkeypatch, r1={"neighbors": {"default": {"10.0.12.2": "established"}}})
    sess = chk("bgp_session", "s", neighbor="10.0.12.2", state="established", timeout=6)
    p = chk("ping", "p", target="10.9.9.9", expect="failure", timeout=6, vrf="red")
    neg = leak("n", timeout=6, vrf="red")
    w: dict = {}
    assert runner._bgp_convergence_gate([p], [sess, p], e.drivers, log=e.logs.append, warnings=w) == {}
    assert e.clock.now == 0 and id(p) not in w                        # no BGP in RED: nothing to wait for
    blocked = runner._bgp_convergence_gate([neg], [sess, neg], e.drivers, log=e.logs.append, warnings=w)
    assert blocked == {} and [x["code"] for x in w[id(neg)]] == ["gate-unreadable"]


def test_b1_still_blocks_the_vrf_the_file_says_runs_bgp(monkeypatch):
    e = make(monkeypatch, r1={"neighbors": {"default": {"10.0.12.2": "established"}}})
    sess = chk("bgp_session", "s", neighbor="10.0.12.6", state="established", timeout=6, vrf="red")
    neg = leak("n", timeout=6, vrf="red")
    blocked = runner._bgp_convergence_gate([neg], [sess, neg], e.drivers, log=e.logs.append, warnings={})
    assert str(blocked[id(neg)].detail).startswith("not evaluated: r1's BGP state (vrf red) could not be read by the cap")


def _nx(rows):
    return json.dumps({"jsonrpc": "2.0", "result": {"body": {"TABLE_intf": {"ROW_intf": rows}}}, "id": 1})


def test_nxos_without_any_ipv6_reads_no_ipv6_addresses():
    null = json.dumps({"jsonrpc": "2.0", "result": None, "id": 1})
    assert addresses.parse_nxos_ipv6_detail(null, "default") == []
    lab = Lab([("show ip interface vrf all", fx("nxos_local_ip_detail.json")), ("show ipv6 interface vrf all", null)])
    with pytest.raises(DriverError, match="never leaves"):
        addresses.refuse_own_target("n1", "10.0.1.1", NxosDriver(lab, "n1").local_addresses())


def test_nxos_link_local_only_interface_is_read():
    row = {"intf-name": "Ethernet1/1", "vrf-name-out": "default", "linklocal-addr": "fe80::1"}
    assert list(map(str, addresses.parse_nxos_ipv6_detail(_nx([row]), "default"))) == ["fe80::1/64"]


def test_nxos_secondary_keys_other_than_prefix_n_are_ignored():
    row = {"intf-name": "Ethernet1/3", "vrf-name-out": "default", "prefix": "10.0.3.1", "masklen": 30,
           "TABLE_secondary_address": {"ROW_secondary_address": {"prefix1": "10.0.33.1", "masklen1": 30,
                                                                 "prefix-tag1": "0"}}}
    assert list(map(str, addresses.parse_nxos_ip_detail(_nx([row]), "default"))) == ["10.0.3.1/30", "10.0.33.1/30"]


def test_an_ipv4_mapped_ping_target_is_refused():
    from netdryrun.config import ConfigError, _validate_check
    with pytest.raises(ConfigError, match="IPv4-mapped"):
        _validate_check(0, {"type": "ping", "node": "r1", "target": "::ffff:10.0.1.1"}, 30)
