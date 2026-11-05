"""The 0.4.1 red-team fixes R1, R5, R6, R7 and R8 (design round 3).

R1 (B-9001): `link_down` on an interface that isn't a topology link (management eth0) took nothing down and every scenario
check passed. R5 (A-0049/A-0050): a VRF that doesn't route (EOS routingDisabled, SR Linux instance down) answered "no
routes", so `present: false` passed. R6 (B-9006): a ping to the node's own address never leaves it. R7 (B-9004): an `only`
entry with host bits silently widened the allow-list. R8 (B-9007): an `as_path_regex` matching every path asserted nothing.

Each test is red on 1de8d70 (accepted, passed or read as empty there).
"""
from __future__ import annotations

import ipaddress
import json
from pathlib import Path

import pytest

from netdryrun.config import ConfigError, _validate_check
from netdryrun.drivers import addresses, eos
from netdryrun.drivers.base import DriverError, NoSuchInstance

from test_verdict_runner import Clock, FakeLab, Fault, Scenario, chk, make, route

FX = Path(__file__).parent / "fixtures"


def fx(name):
    return (FX / name).read_text(encoding="utf-8")


def check(**raw):
    return _validate_check(0, raw, 30)


# ------------------------------------------------------------------------------------------- R1 link faults

def test_link_down_on_an_interface_that_is_no_topology_link_is_refused(monkeypatch):
    e = make(monkeypatch)
    sc = Scenario("mgmt", [Fault("link_down", "r1", "eth0")], [route("[mgmt] x", node="r2")])
    rep = e.run([route("a")], [sc])
    assert rep.status == "error" and "eth0" in rep.error and "eth1" in rep.error   # names the link interfaces
    assert e.lab.link_events() == []                                              # nothing was taken down


def test_a_fault_that_leaves_the_interface_admin_up_is_an_error(monkeypatch):
    e = make(monkeypatch)
    e.lab.stuck_up = True
    sc = Scenario("s", [Fault("link_down", "r1", "eth1")], [route("[s] x", node="r2")])
    rep = e.run([route("a")], [sc])
    assert rep.status == "error" and "still administratively up" in rep.error


@pytest.mark.parametrize("kind", ["cisco_xrv9k", "nokia_sros", "arista_veos", "vr-anything"])
def test_every_vm_kind_is_refused_for_link_faults(kind):
    lab = FakeLab(Clock(), kinds={"r1": (kind, "some/image:1")})
    from netdryrun.lab import Lab, LabError
    with pytest.raises(LabError, match="VM"):
        Lab._require_linux_links(lab, "r1")


def test_admin_flag_is_an_exact_token():
    from netdryrun.lab import ExecResult, Lab

    class L:
        def __init__(self, out):
            self.out = out

        def exec(self, node, cmd, timeout=15):
            return ExecResult(cmd, 0, self.out, "")
    down = "5: eth1@if6: <BROADCAST,MULTICAST,LOWER_UP> mtu 9500 qdisc noqueue state DOWN"
    up_lowerdown = "5: eth1@if6: <NO-CARRIER,BROADCAST,MULTICAST,UP> mtu 9500 state LOWERLAYERDOWN"
    assert Lab.admin_up(L(down), "r1", "eth1") is False          # LOWER_UP is not UP
    assert Lab.admin_up(L(up_lowerdown), "r1", "eth1") is True   # the flag, not the state column


# ------------------------------------------------------------------------------------------- R5 VRFs that don't route

@pytest.mark.parametrize("name,vrf", [("eos_route_default_routing_disabled.json", "default"),
                                      ("eos_route_red_routing_disabled.json", "RED"),
                                      ("eos_route_red_v6_routing_disabled.json", "RED")])
def test_eos_vrf_with_routing_disabled_is_not_no_routes(name, vrf):
    with pytest.raises(NoSuchInstance, match="routing disabled"):
        eos.parse_all_routes(fx(name), vrf)
    with pytest.raises(NoSuchInstance, match="routing disabled"):
        eos.parse_routes(fx(name), json.dumps({"vrfs": {vrf: {"bgpRouteEntries": {}}}}), "10.0.0.0/8", vrf)


def test_eos_route_answer_without_the_flag_is_unexpected():
    with pytest.raises(DriverError, match="routingDisabled"):
        eos.parse_all_routes(json.dumps({"vrfs": {"default": {"routes": {}}}}))


def test_srlinux_disabled_instance_is_not_settled_and_no_links_is_fine():
    from netdryrun.drivers.srlinux import SrlDriver
    from netdryrun.lab import ExecResult

    class L:
        def __init__(self, out):
            self.out = out

        def exec(self, node, cmd, timeout=60):
            return ExecResult(cmd, 0, self.out, "")
    d = SrlDriver.__new__(SrlDriver)
    d.node = "srl1"
    d.lab = L(fx("srl_instance_disabled.json"))
    with pytest.raises(DriverError, match="not settled") as e:
        d._confirm_vrf("RED", [])
    assert not isinstance(e.value, NoSuchInstance)                 # retried, never "no routes"
    d.lab = L(fx("srl_instance_no_links.json"))
    d._confirm_vrf("BLUE", [])                                     # an ip-vrf with no links reads up


# ------------------------------------------------------------------------------------------- R6 ping targets

@pytest.mark.parametrize("target", ["0.0.0.0", "::", "127.0.0.1", "::1", "224.0.0.5", "ff02::1", "255.255.255.255"])
def test_ping_to_a_target_that_never_leaves_the_node_is_refused(target):
    with pytest.raises(ConfigError, match="never leaves the node"):
        check(type="ping", node="r1", target=target)


def test_ping_to_its_own_source_is_refused():
    with pytest.raises(ConfigError, match="source"):
        check(type="ping", node="r1", target="10.0.0.1", source="10.0.0.1")


@pytest.mark.parametrize("parse,target", [
    (lambda: addresses.parse_ip_j_addr(fx("frr_local_ip_addr.json"), True), "10.0.12.1"),
    (lambda: addresses.parse_ip_j_addr(fx("frr_local_ip_addr.json"), True), "10.0.12.3"),        # its subnet's broadcast
    (lambda: addresses.parse_eos_interfaces(fx("eos_local_ipv4.json"), "default", "x"), "192.168.30.1"),
    (lambda: addresses.parse_nxos_ip_brief(fx("nxos_local_ip_brief.json"), "RED"), "10.0.2.1"),
    (lambda: addresses.parse_routeros_addresses(json.loads(fx("routeros_local_ipv4.json")), "default", "x"), "192.0.2.1"),
    (lambda: addresses.parse_srl_addresses(fx("srl_local_ipv4.json"), "x"), "10.0.100.1"),
    (lambda: addresses.parse_junos_terse(fx("junos_local_interfaces_terse.json")), "2001:db8:100::1"),
])
def test_ping_to_an_own_address_is_refused_on_every_driver(parse, target):
    with pytest.raises(DriverError, match="never leaves|broadcast"):
        addresses.refuse_own_target("r1", target, parse())


def test_a_peer_address_is_not_own():
    addresses.refuse_own_target("r1", "10.0.12.2", addresses.parse_ip_j_addr(fx("frr_local_ip_addr.json"), True))


def test_vrf_addresses_stay_in_their_vrf():
    assert ipaddress.ip_interface("10.0.2.1/32") not in addresses.parse_nxos_ip_brief(fx("nxos_local_ip_brief.json"),
                                                                                     "default")


@pytest.mark.parametrize("text", ["", "{", '{"interfaces": ', "[1, 2"])
def test_truncated_or_unreadable_address_output_is_an_error(text):
    for parse in (lambda t: addresses.parse_ip_j_addr(t, True), lambda t: addresses.parse_eos_interfaces(t, "default", "x"),
                  lambda t: addresses.parse_nxos_ip_brief(t, "default"), lambda t: addresses.parse_srl_addresses(t, "x"),
                  addresses.parse_junos_terse):
        with pytest.raises(DriverError):
            parse(text)


def test_a_whole_run_fails_a_ping_to_the_nodes_own_address(monkeypatch):
    e = make(monkeypatch)
    e.drivers["r1"].local_addresses = lambda vrf="default": [ipaddress.ip_interface("10.0.12.1/30")]
    e.drivers["r1"].ping_ = lambda t: (3, 3)
    rep = e.run([chk("ping", "self", target="10.0.12.1")])
    assert rep.results[0].passed is False and "itself" in rep.results[0].detail


# ------------------------------------------------------------------------------------------- R7 and R8

def test_only_entry_with_host_bits_is_refused():
    with pytest.raises(ConfigError, match="host bits"):
        check(type="bgp_prefixes", node="r1", neighbor="10.0.0.2", only=["10.1.1.77/24"])


@pytest.mark.parametrize("rx", ["65001|", ".*", "|65001", "^.*$", "(65001)?", "x*"])
def test_as_path_regex_matching_every_path_is_refused(rx):
    with pytest.raises(ConfigError, match="matches every AS path"):
        check(type="bgp_route", node="r1", prefix="10.0.0.0/8", as_path_regex=rx)


@pytest.mark.parametrize("rx", ["^$", "^65001", "65001$", "_?64496_?"])
def test_narrow_as_path_regex_stays_valid(rx):
    check(type="bgp_route", node="r1", prefix="10.0.0.0/8", as_path_regex=rx)
