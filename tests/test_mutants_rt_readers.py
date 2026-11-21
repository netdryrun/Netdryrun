"""The End-of-RIB readers, the Junos stale read and the own-address reads, input by input (mutation triage of 22e1f95).

Each reader decides whether the gate waits (End-of-RIB), whether a route is settled (stale) or whether a ping may run
(own addresses), so every shape it distinguishes is pinned here, with the exact command it sends where it sends one.
"""
from __future__ import annotations

import copy
import ipaddress
import json
from pathlib import Path

import pytest

from netdryrun.drivers import addresses, eos, frr, junos, nxos, routeros_state, srlinux
from netdryrun.drivers.base import BgpNeighbor, DriverError
from netdryrun.drivers.eos import EosDriver
from netdryrun.drivers.frr import FrrDriver
from netdryrun.drivers.junos import JunosDriver
from netdryrun.drivers.nxos import NxosDriver
from netdryrun.drivers.routeros import RouterosDriver
from netdryrun.drivers.srlinux import SrlDriver

from test_verdict_drivers import Lab

FX = Path(__file__).parent / "fixtures"


def fx(name):
    return (FX / name).read_text(encoding="utf-8")


def j(name):
    t = fx(name)
    return json.loads(t[min(i for i in (t.find("{"), t.find("[")) if i >= 0):])


# ------------------------------------------------------------------------------------------- FRR

def frr_info(local, remote, **g_over):
    info = j("frr_eor_received.json")["10.0.12.2"]
    g = info["gracefulRestartInfo"]
    g.update(localGrMode=local, remoteGrMode=remote, **g_over)
    return info


@pytest.mark.parametrize("local,remote,want", [
    ("Disable*", "Helper", {"*": "untracked"}), ("Helper*", "NotApplicable", {"*": "untracked"}),
    ("Disable", "NotApplicable", {"*": "untracked"}),
    ("Restart*", "Helper", {"ipv4-unicast": "received"}), ("Helper*", "Restart*", {"ipv4-unicast": "received"}),
    ("Helper", "Helper*", {"ipv4-unicast": "received"}), ("Restart", "Restart", {"ipv4-unicast": "received"}),
    ("disable", "Helper", {"*": "unknown"}), ("Helper", "notapplicable", {"*": "unknown"}),
    ("*Helper", "Helper", {"*": "unknown"}), ("Helper", "*Restart", {"*": "unknown"}),
    ("Helper", "Odd", {"*": "unknown"}), ("Odd", "Restart", {"*": "unknown"}),
])
def test_frr_gr_modes(local, remote, want):
    assert frr.frr_eor(frr_info(local, remote)) == want


def test_frr_unknown_family_keeps_its_name_and_odd_status_is_unknown():
    info = frr_info("Helper*", "Restart")
    g = info["gracefulRestartInfo"]
    g["ipv4Multicast"] = {"endOfRibStatus": {"endOfRibRecv": False}}
    g["ipv6Unicast"] = {"endOfRibStatus": ["not", "a", "map"]}
    assert frr.frr_eor(info) == {"ipv4-unicast": "received", "ipv4Multicast": "pending", "ipv6-unicast": "unknown"}


# ------------------------------------------------------------------------------------------- RouterOS

def ros_row(**over):
    row = {r["remote.address"]: r for r in json.loads(fx("routeros_eor_pending.txt")[4:])}["192.0.2.2"]
    row = dict(row, **over)
    return {k: v for k, v in row.items() if v is not None}


def test_routeros_missing_eor_with_gr_is_pending():
    row = ros_row()
    row.pop("remote.eor")
    assert routeros_state.ros_eor(row) == {"ipv4-unicast": "pending"}


def test_routeros_two_families():
    assert routeros_state.ros_eor(ros_row(**{"remote.afi": "ip,ipv6", "remote.eor": "ip,ipv6"})) == \
        {"ipv4-unicast": "received", "ipv6-unicast": "received"}
    assert routeros_state.ros_eor(ros_row(**{"remote.afi": "ip,ipv6", "remote.eor": "ipv6"})) == \
        {"ipv4-unicast": "pending", "ipv6-unicast": "received"}


def test_routeros_missing_or_empty_afi_means_ip():
    row = ros_row(**{"remote.eor": "ip"})
    row.pop("remote.afi", None)
    assert routeros_state.ros_eor(row) == {"ipv4-unicast": "received"}
    assert routeros_state.ros_eor(ros_row(**{"remote.afi": "", "remote.eor": ""})) == {"ipv4-unicast": "pending"}
    assert routeros_state.ros_eor(ros_row(**{"remote.afi": "IP"})) == {"*": "unknown"}


# ------------------------------------------------------------------------------------------- SR Linux

def srl():
    return copy.deepcopy(j("srl_eor_gr_baseline.txt"))


def test_srlinux_capabilities_must_both_be_lists():
    n = srl()
    n["received-capabilities"] = "GRACEFUL_RESTART"
    assert srlinux.srl_eor(n) == {"*": "unknown"}


@pytest.mark.parametrize("gr", [[], {"neighbor-capability": {}, "local-capability": {"afi-safi": []}},
                                {"local-capability": {"afi-safi": [{"name": "ipv4-unicast"}]}}])
def test_srlinux_unreadable_gr_families_still_read_received(gr):
    n = srl()
    n["graceful-restart"] = gr
    assert srlinux.srl_eor(n) == {"ipv4-unicast": "received"}
    n.pop("received-end-of-rib")
    assert srlinux.srl_eor(n) == {"ipv4-unicast": "unknown"}


def test_srlinux_no_family_up_is_unknown_exactly():
    n = srl()
    for af in n["afi-safi"]:
        af["oper-state"] = "down"
    assert srlinux.srl_eor(n) == {"*": "unknown"}


# ------------------------------------------------------------------------------------------- Junos

def junos_peer():
    return copy.deepcopy(j("junos_eor_received.txt")["bgp-information"][0]["bgp-peer"][0])


@pytest.mark.parametrize("key", ["nlri-type-session", "peer-restart-nlri-negotiated", "peer-end-of-rib-received"])
@pytest.mark.parametrize("bad", [5, [], ["x"], [{"data": 5}], "text"])
def test_junos_bad_leaf_shapes_are_unknown(key, bad):
    p = junos_peer()
    p[key] = bad
    assert junos.junos_eor(p) == {"*": "unknown"}


def test_junos_unknown_family_keeps_its_name():
    p = junos_peer()
    p["nlri-type-session"] = [{"data": "inet-unicast inet-vpn-unicast"}]
    assert junos.junos_eor(p) == {"ipv4-unicast": "received", "inet-vpn-unicast": "untracked"}


# ------------------------------------------------------------------------------------------- EOS

def eos_peer():
    return copy.deepcopy(j("eos_eor_gr_default.json")["vrfs"]["default"]["peerList"][0])


@pytest.mark.parametrize("incoming,want", [
    ({}, {"*": "unknown"}), (["x"], {"*": "unknown"}),
    ({"ipv4Unicast": "received"}, {"ipv4-unicast": "unknown"}),
    ({"l2VpnEvpn": {"status": "pending"}}, {"l2VpnEvpn": "pending"}),
])
def test_eos_incoming_shapes(incoming, want):
    p = eos_peer()
    p["endOfRibs"]["incoming"] = incoming
    assert eos.eos_eor(p) == want


def test_eos_end_of_rib_commands_exactly():
    lab = Lab([("show ip bgp neighbors vrf red | json", fx("eos_eor_pending.txt").replace('"default"', '"red"')),
               ("show ipv6 bgp neighbors vrf red | json", '{"vrfs": {"red": {"peerList": []}}}')])
    d = EosDriver(lab, "r1")
    nb = {"10.0.200.2": BgpNeighbor("10.0.200.2", "established")}
    assert d.end_of_rib("red", nb) == {"10.0.200.2": {"ipv4-unicast": "pending"}}
    assert lab.lines() == ["Cli -p 15 -c show ip bgp neighbors vrf red | json"]     # all found: no IPv6 read
    nb["2001:db8::9"] = BgpNeighbor("2001:db8::9", "established")
    v6 = '{"vrfs": {"red": {"peerList": [{"peerAddress": "2001:DB8::9", "endOfRibs": {"incoming": ' \
         '{"ipv6Unicast": {"status": "received"}}}}]}}}'
    lab = Lab([("show ip bgp neighbors vrf red | json", fx("eos_eor_pending.txt").replace('"default"', '"red"')),
               ("show ipv6 bgp neighbors vrf red | json", v6)])
    d = EosDriver(lab, "r1")
    assert d.end_of_rib("red", nb) == {"10.0.200.2": {"ipv4-unicast": "pending"},
                                       "2001:db8::9": {"ipv6-unicast": "received"}}
    assert lab.lines() == ["Cli -p 15 -c show ip bgp neighbors vrf red | json",
                           "Cli -p 15 -c show ipv6 bgp neighbors vrf red | json"]


# ------------------------------------------------------------------------------------------- NX-OS

def nx_msg(name="nxos_eor_pending.txt"):
    return nxos._ascii_msg(fx(name))


def test_nxos_untracked_and_pending_exactly():
    msg = nx_msg()
    assert nxos.nxos_eor_text(msg, "ipv4-unicast") == "pending"
    no_gr = msg.replace("Graceful Restart capability: advertised received", "Graceful Restart capability: advertised")
    assert nxos.nxos_eor_text(no_gr, "ipv4-unicast") == "untracked"
    no_list = msg.replace("Address families received from peer:", "Families seen:")
    assert nxos.nxos_eor_text(no_list, "ipv4-unicast") == "untracked"
    other = msg.replace("Address families received from peer:\n    IPv4 Unicast", "Address families received from peer:\n"
                                                                                 "    IPv6 Unicast")
    assert other != msg and nxos.nxos_eor_text(other, "ipv4-unicast") == "untracked"


def test_nxos_end_of_rib_commands_exactly():
    lab = Lab([("cli_ascii", fx("nxos_eor_pending.txt"))])
    d = NxosDriver(lab, "n1")
    nb = {"10.0.1.2": BgpNeighbor("10.0.1.2", "established", {"ipv4-unicast": 3, "ipv6-unicast": 1}),
          "10.0.9.9": BgpNeighbor("10.0.9.9", "idle"),
          "10.0.1.6": BgpNeighbor("10.0.1.6", "established", {})}
    got = d.end_of_rib("red", nb)
    assert got == {"10.0.1.2": {"ipv4-unicast": "pending", "ipv6-unicast": "unknown"},
                   "10.0.1.6": {"ipv4-unicast": "pending"}}
    cmds = [ln.split(" cli_ascii ", 1)[1].rsplit(" ", 1)[0] for ln in lab.lines()]
    assert cmds == ["show bgp ipv4 unicast neighbors 10.0.1.2 vrf red", "show bgp ipv6 unicast neighbors 10.0.1.2 vrf red",
                    "show bgp ipv4 unicast neighbors 10.0.1.6 vrf red"]


# ------------------------------------------------------------------------------------------- Junos stale

from test_junos_mutants import RC, answer, entry, routes, rt  # noqa: E402


def test_junos_stale_errors_exactly():
    e = entry()
    del e["bgp-rt-flag"]
    with pytest.raises(DriverError) as x:
        routes(answer(rt(e)))
    assert str(x.value) == RC + "10.20.0.0/24: a BGP route without bgp-rt-flag (a stale mark couldn't be read)"
    for bad in ([5], [{"data": 5}], "Stale", {"data": "Stale"}):
        with pytest.raises(DriverError) as x:
            routes(answer(rt(entry(**{"bgp-rt-flag": bad}))))
        assert str(x.value) == RC + f"10.20.0.0/24: bgp-rt-flag {str(bad)[:80]}"
    long = [{"data": "Accepted"}] * 20 + [{"data": 5}]
    with pytest.raises(DriverError) as x:
        routes(answer(rt(entry(**{"bgp-rt-flag": long}))))
    assert str(x.value) == RC + f"10.20.0.0/24: bgp-rt-flag {str(long)[:80]}"


def test_junos_unknown_protocol_without_a_flag_names_the_command():
    e = entry(**{"protocol-name": [{"data": "Mystery"}]})
    del e["bgp-rt-flag"]
    with pytest.raises(DriverError) as x:
        routes(answer(rt(e)))
    assert str(x.value).startswith(RC)


# ------------------------------------------------------------------------------------------- own addresses

def test_own_target_with_a_scope_and_exact_messages():
    addrs = [ipaddress.ip_interface("fe80::1/64"), ipaddress.ip_interface("10.0.0.1/30"),
             ipaddress.ip_interface("10.0.1.1/31"), ipaddress.ip_interface("10.0.2.1/24")]
    with pytest.raises(DriverError) as x:
        addresses.refuse_own_target("r1", "fe80::1%eth1", addrs)
    assert str(x.value) == ("ping target fe80::1%eth1 is an address of r1 itself (fe80::1/64): the ping never leaves the "
                            "node, so it says nothing about the network")
    with pytest.raises(DriverError) as x:
        addresses.refuse_own_target("r1", "10.0.0.3", addrs)
    assert str(x.value) == "ping target 10.0.0.3 is the broadcast address of r1's subnet 10.0.0.0/30"
    addresses.refuse_own_target("r1", "10.0.1.0", addrs)           # a /31 has no broadcast address
    with pytest.raises(DriverError) as x:
        addresses.refuse_own_target("r1", "10.0.9.9", [addresses.LocalPrefix(ipaddress.ip_interface("10.0.9.1/24"))])
    assert str(x.value) == ("ping target 10.0.9.9 is inside 10.0.9.0/24, which is on r1's lo: the node answers it itself, "
                            "so the ping never leaves the node")


def test_frr_own_address_commands_exactly():
    lab = Lab([("ip -j addr", fx("frr_local_ip_addr.json"))])
    d = FrrDriver(lab, "r1")
    got = d.local_addresses()
    assert lab.lines() == ["ip -j addr"]
    assert ipaddress.ip_interface("172.20.20.2/24") in got
    d.local_addresses("red")
    # a named VRF: its enslaved interfaces, then the VRF device itself (an address on it is the node's own, RT-0053)
    assert lab.lines()[-2:] == ["ip -j addr show vrf red", "ip -j addr show dev red"]


def test_frr_named_vrf_keeps_enslaved_interfaces_and_errors_name_the_command():
    vrf_answer = json.dumps([{"ifname": "eth2", "master": "red", "addr_info": [{"local": "10.1.0.1", "prefixlen": 30}]}])
    dev_answer = json.dumps([{"ifname": "red", "addr_info": []}])
    d = FrrDriver(Lab([("ip -j addr show vrf red", vrf_answer), ("ip -j addr show dev red", dev_answer),
                       ("ip -j addr", "[{\"addr_info\": [5]}]")]), "r1")
    assert [str(a) for a in d.local_addresses("red")] == ["10.1.0.1/30"]
    with pytest.raises(DriverError) as x:
        d.local_addresses()
    assert str(x.value) == "unexpected output from `ip -j addr`: 5"


def test_eos_own_address_commands_exactly():
    lab = Lab([("show ip interface | json", fx("eos_local_ipv4.json")),
               ("show ipv6 interface | json", fx("eos_local_ipv6.json"))])
    EosDriver(lab, "r1").local_addresses()
    assert lab.lines() == ["Cli -p 15 -c show ip interface | json", "Cli -p 15 -c show ipv6 interface | json"]
    bad = Lab([("show ip interface | json", '{"interfaces": {"Et1": {}}}'), ("show ipv6", "{}")])
    with pytest.raises(DriverError) as x:
        EosDriver(bad, "r1").local_addresses()
    assert str(x.value) == "unexpected output from `show ip interface | json`: Et1: no vrf"


def test_junos_and_nxos_own_address_commands_exactly():
    lab = Lab([("show interfaces terse", fx("junos_local_interfaces_terse.json"))])
    JunosDriver(lab, "j1").local_addresses()
    assert lab.lines()[0].endswith("cli -c 'show interfaces terse | display json | no-more'")
    lab = Lab([("show ip interface vrf all", fx("nxos_local_ip_detail.json")), ("show ipv6 interface vrf all", fx("nxos_local_ipv6_detail.json"))])
    NxosDriver(lab, "n1").local_addresses()
    assert " cli show ip interface vrf all " in lab.lines()[0] + " " and " cli show ipv6 interface vrf all " in lab.lines()[1] + " "


def test_routeros_own_address_paths_and_vrf_exactly():
    v4 = json.loads(fx("routeros_local_ipv4.json"))
    v4.append({"address": "10.9.0.1/24", "vrf": "RED", "disabled": "false", "invalid": "false"})
    v6 = json.loads(fx("routeros_local_ipv6.json"))
    lab = Lab([("GET /ip/address", f"200\n{json.dumps(v4)}"), ("GET /ipv6/address", f"200\n{json.dumps(v6)}")])
    d = RouterosDriver(lab, "r1")
    red = [str(a) for a in d.local_addresses("RED")]
    assert red == ["203.0.113.1/30", "10.9.0.1/24"]
    default = [str(a) for a in d.local_addresses()]
    assert "192.0.2.1/30" in default and "fe80::a8c1:abff:feac:6ae9/64" in default and "10.9.0.1/24" not in default
    paths = [ln.split(" GET ", 1)[1].split(" ", 1)[0] for ln in lab.lines()]
    assert paths == ["/ip/address", "/ipv6/address", "/ip/address", "/ipv6/address"]
    bad = Lab([("GET /ip/address", "200\n[{\"address\": \"10.0.0.1/24\"}]"), ("GET /ipv6/address", "200\n[]")])
    with pytest.raises(DriverError) as x:
        RouterosDriver(bad, "r1").local_addresses()
    assert str(x.value) == "unexpected output from `GET /ip/address`: {'address': '10.0.0.1/24'}"


def test_srlinux_own_address_reads_both_families_exactly():
    lab = Lab([("ipv4 address *", fx("srl_local_ipv4.json")), ("ipv6 address *", fx("srl_local_ipv6.json"))])
    got = [str(a) for a in SrlDriver(lab, "s1").local_addresses()]
    assert "10.0.100.1/30" in got and "3fff:172:20:20::3/64" in got
    assert [ln.split("json ", 1)[1] for ln in lab.lines()] == [
        "info from state /interface * subinterface * ipv4 address *",
        "info from state /interface * subinterface * ipv6 address *"]
    bad = Lab([("ipv4 address *", '{"interface": [{"subinterface": [{"ipv4": {"address": [5]}}]}]}'),
               ("ipv6 address *", '{"interface": []}')])
    with pytest.raises(DriverError) as x:
        SrlDriver(bad, "s1").local_addresses()
    assert str(x.value) == "unexpected output from `info from state /interface * subinterface * ipv4 address *`: 5"


def test_a_slash_31_peer_is_not_a_broadcast_address():
    addresses.refuse_own_target("r1", "10.0.1.1", [ipaddress.ip_interface("10.0.1.0/31")])


def test_frr_default_vrf_drops_enslaved_interfaces_and_named_vrf_errors_name_the_command():
    answer = json.dumps([{"ifname": "eth1", "addr_info": [{"local": "10.0.12.1", "prefixlen": 30}]},
                         {"ifname": "eth2", "master": "red", "addr_info": [{"local": "10.1.0.1", "prefixlen": 30}]}])
    d = FrrDriver(Lab([("ip -j addr show vrf red", "[5]"), ("ip -j addr", answer)]), "r1")
    assert [str(a) for a in d.local_addresses()] == ["10.0.12.1/30"]
    with pytest.raises(DriverError) as x:
        d.local_addresses("red")
    assert str(x.value) == "unexpected output from `ip -j addr show vrf red`: 5"
