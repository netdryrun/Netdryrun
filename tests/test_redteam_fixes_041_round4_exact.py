"""Round-4 fixes, exactly (mutation triage of bd76896, 2026-11-06): the NX-OS address parsers' errors, the anycast
refusal, the ping check's family and source rules, and the EOS ping's management re-check."""
from __future__ import annotations

import ipaddress
import json

import pytest

from netdryrun import checks, mgmt
from netdryrun.drivers import addresses
from netdryrun.drivers.base import DriverError
from netdryrun.drivers.eos import EosDriver
from netdryrun.lab import ExecResult

from test_mgmt import EosLab, m_of

IP_CMD, V6_CMD = "show ip interface vrf all", "show ipv6 interface vrf all"


def _nx(body):
    return json.dumps({"jsonrpc": "2.0", "result": {"body": body}, "id": 1})


def err(fn, *a):
    with pytest.raises(DriverError) as e:
        fn(*a)
    return str(e.value)


# ------------------------------------------------------------------------------------------- NX-OS rows

def test_nxos_no_result_or_body_exact():
    data = {"jsonrpc": "2.0", "pad": "p" * 200}
    assert err(addresses.parse_nxos_ip_detail, json.dumps(data), "default") == \
        f"unexpected output from `{IP_CMD}`: " + str(data)[:150]
    assert err(addresses.parse_nxos_ipv6_detail, json.dumps({"result": {"x": 1}}), "default") == \
        f"unexpected output from `{V6_CMD}`: " + str({"result": {"x": 1}})


def test_nxos_body_without_rows_exact():
    body = {"TABLE_other": {"pad": "q" * 200}}
    assert err(addresses.parse_nxos_ip_detail, _nx(body), "default") == \
        f"unexpected output from `{IP_CMD}`: " + str(body)[:150]
    assert err(addresses.parse_nxos_ip_detail, _nx("text body"), "default") == \
        f"unexpected output from `{IP_CMD}`: text body"
    assert err(addresses.parse_nxos_ip_detail, _nx({"TABLE_intf": {"ROW_intf": "x"}}), "default") == \
        f"unexpected output from `{IP_CMD}`: " + str({"TABLE_intf": {"ROW_intf": "x"}})


def test_nxos_a_single_row_mapping_is_a_list_of_one():
    row = {"intf-name": "lo0", "vrf-name-out": "default", "prefix": "192.168.10.1", "masklen": 32}
    assert [str(a) for a in addresses.parse_nxos_ip_detail(_nx({"TABLE_intf": {"ROW_intf": row}}), "default")] == \
        ["192.168.10.1/32"]


@pytest.mark.parametrize("row", [["not", "a", "map"], {"intf-name": "e1", "vrf-name-out": 5},
                                 {"intf-name": "e1"}])
def test_nxos_a_row_without_its_vrf_exact(row):
    assert err(addresses.parse_nxos_ip_detail, _nx({"TABLE_intf": {"ROW_intf": [row]}}), "default") == \
        f"unexpected output from `{IP_CMD}`: row {str(row)[:80]}"


def test_nxos_rows_of_exact():
    cmd = "c"
    assert addresses._rows_of(cmd, None, "ROW_x") == []
    assert addresses._rows_of(cmd, {"ROW_x": {"a": 1}}, "ROW_x") == [{"a": 1}]
    assert addresses._rows_of(cmd, {"ROW_x": [{"a": 1}]}, "ROW_x") == [{"a": 1}]
    with pytest.raises(DriverError) as e:
        addresses._rows_of(cmd, {"OTHER": "z" * 100}, "ROW_x")
    assert str(e.value) == "unexpected output from `c`: ROW_x: " + str({"OTHER": "z" * 100})[:80]
    with pytest.raises(DriverError) as e:
        addresses._rows_of(cmd, "a string table", "ROW_x")
    assert str(e.value) == "unexpected output from `c`: ROW_x: a string table"
    with pytest.raises(DriverError) as e:
        addresses._rows_of(cmd, {"ROW_x": "y" * 100}, "ROW_x")
    assert str(e.value) == "unexpected output from `c`: ROW_x: " + ("y" * 100)[:80]


# ------------------------------------------------------------------------------------------- anycast

def test_subnet_router_anycast_message_exact():
    with pytest.raises(DriverError) as e:
        addresses.refuse_own_target("r1", "2001:db8:1::", [ipaddress.ip_interface("2001:db8:1::1/64")])
    assert str(e.value) == ("ping target 2001:db8:1:: is the subnet-router anycast address of r1's prefix 2001:db8:1::/64: "
                            "the node answers it itself, so the ping never leaves the node")


# ------------------------------------------------------------------------------------------- the ping check

class D:
    name = "fake"
    own_address_families = frozenset({4, 6})

    def __init__(self, addrs=(), families=None):
        self.addrs = list(addrs)
        if families is not None:
            self.own_address_families = families
        self.vrfs: list = []

    def local_addresses(self, vrf="default"):
        self.vrfs.append(vrf)
        return self.addrs

    def ping(self, target, source, count, vrf="default"):
        from netdryrun.drivers.base import Observation
        return Observation((count, count), [{"output": "", "stderr": ""}])


def test_a_scoped_target_is_judged_by_its_address_family():
    with pytest.raises(DriverError) as e:
        checks._ping(D(families=frozenset({4})), {"node": "r1", "target": "fe80::1%eth1"})
    assert str(e.value) == ("r1's own IPv6 addresses can't be read on the fake driver, so a ping to fe80::1%eth1 can't "
                            "be shown to leave the node")
    checks._ping(D(families=frozenset({6})), {"node": "r1", "target": "fe80::1%eth1"})


def test_a_driver_without_the_declaration_reads_both_families_and_without_a_name_says_so():
    class Plain:
        def local_addresses(self, vrf="default"):
            return []

        def ping(self, *a):
            from netdryrun.drivers.base import Observation
            return Observation((3, 3), [])
    checks._ping(Plain(), {"node": "r1", "target": "2001:db8::9"})
    checks._ping(Plain(), {"node": "r1", "target": "10.0.0.9"})

    class NoName(Plain):
        own_address_families = frozenset()
    with pytest.raises(DriverError) as e:
        checks._ping(NoName(), {"node": "r1", "target": "10.0.0.9"})
    assert str(e.value) == ("r1's own IPv4 addresses can't be read on the ? driver, so a ping to 10.0.0.9 can't be "
                            "shown to leave the node")


def test_the_source_must_be_an_own_address_exact():
    d = D([ipaddress.ip_interface("10.0.12.1/30")])
    with pytest.raises(DriverError) as e:
        checks._ping(d, {"node": "r1", "target": "10.0.0.9", "source": "10.0.12.9", "vrf": "RED"})
    assert str(e.value) == "ping source 10.0.12.9 is not an address of r1 in vrf RED"
    assert d.vrfs == ["RED"]
    with pytest.raises(DriverError) as e:
        checks._ping(d, {"node": "r1", "target": "10.0.0.9", "source": "10.0.12.9"})
    assert str(e.value) == "ping source 10.0.12.9 is not an address of r1 in vrf default"


@pytest.mark.parametrize("addr,source", [
    (ipaddress.ip_interface("10.0.12.1/30"), "10.0.12.1"),
    (addresses.LocalPrefix(ipaddress.ip_interface("10.9.9.1/24")), "10.9.9.1"),
    (ipaddress.ip_interface("fe80::1/64"), "fe80::1%eth1"),
])
def test_an_own_source_is_accepted_whatever_the_address_kind(addr, source):
    ok, why, _ = checks._ping(D([addr]), {"node": "r1", "target": "10.0.0.9" if "." in source else "fe80::9",
                                          "source": source})
    assert ok and why == "3/3 replies (need 2)"


def test_a_check_without_a_source_skips_the_source_rule():
    ok, _, _ = checks._ping(D([]), {"node": "r1", "target": "10.0.0.9"})
    assert ok


def test_the_source_rule_compares_every_address():
    d = D([ipaddress.ip_interface("10.0.0.1/30"), addresses.LocalPrefix(ipaddress.ip_interface("10.9.9.1/24")),
           ipaddress.ip_interface("10.0.12.1/30")])
    assert checks._ping(d, {"node": "r1", "target": "10.0.0.9", "source": "10.0.12.1"})[0]
    with pytest.raises(DriverError):
        checks._ping(D([addresses.LocalPrefix(ipaddress.ip_interface("10.9.9.1/24"))]),
                     {"node": "r1", "target": "10.0.0.9", "source": "10.9.9.2"})


# ------------------------------------------------------------------------------------------- EOS ping

def test_eos_ping_rechecks_its_own_node_after_the_ping_exact():
    lab = EosLab()
    mgmt.prepare(lab, [])
    real = lab.exec

    def exec_(node, cmd, timeout=60, input=None):
        if cmd[-1].startswith("ping "):
            lab.running = lab.startup                  # the route comes back during the ping
            return ExecResult(cmd, 0, "3 packets transmitted, 3 received, 0% packet loss", "")
        return real(node, cmd, timeout, input)
    lab.exec = exec_
    with pytest.raises(mgmt.ManagementPathError) as e:
        EosDriver(lab, "r1").ping("10.0.0.9", None, 3)
    assert str(e.value).startswith("r1 has a route out over the management network (after the ping to 10.0.0.9): ")
    assert m_of().node == "r1"


# ------------------------------------------------------------------------------------------- gate (B1, h)

def test_b1_detail_exact(monkeypatch):
    from netdryrun import runner
    from test_verdict_runner import chk, leak, make
    e = make(monkeypatch)
    e.drivers["r1"].neighbors_error = DriverError("cli   timeout\n now")
    neg = leak("n", timeout=6)
    sess = chk("bgp_session", "s", neighbor="10.0.12.2", state="established", timeout=6)
    blocked = runner._bgp_convergence_gate([neg], [neg, sess], e.drivers, log=e.logs.append, warnings={})
    assert str(blocked[id(neg)].detail) == (
        "not evaluated: r1's BGP state could not be read by the cap (6s): cli timeout now. A post-convergence check "
        "means nothing before the node's BGP state shows it converged")


def test_h_an_end_of_rib_session_missing_from_the_neighbors_is_read_not_a_crash(monkeypatch):
    from netdryrun import runner
    from netdryrun.drivers.base import BgpNeighbor
    from test_redteam_fixes_041_round4 import _Eor
    from test_verdict_runner import leak, make
    e = make(monkeypatch, r1={"neighbors": {"default": {"10.0.12.2": BgpNeighbor("10.0.12.2", "established",
                                                                                 {"ipv4-unicast": 3})}}})
    # the End-of-RIB read names a session the neighbor read doesn't list (it went away between the two reads)
    e.drivers["r1"] = _Eor(e.drivers["r1"], {"10.0.12.2": {"ipv4-unicast": "received"},
                                             "10.0.12.9": {"ipv4-unicast": "received"}})
    neg = leak("n", timeout=9)
    w: dict = {}
    assert runner._bgp_convergence_gate([neg], [neg], e.drivers, log=e.logs.append, warnings=w,
                                        eor_reported=set()) == {}
    assert id(neg) not in w
