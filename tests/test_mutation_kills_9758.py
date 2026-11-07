"""Exact tests for the mutation survivors of 9758c87 (2026-11-07): each pins what a surviving mutant changed."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from netdryrun import mgmt, runner
from netdryrun.config import Fault, Scenario
from netdryrun.drivers import addresses
from netdryrun.drivers.base import DriverError
from netdryrun.drivers.frr import ROUTE_CMD, _route_table
from netdryrun.lab import ExecResult, LabError
from netdryrun.mgmt import ManagementPathError

from test_mgmt import CLAB_EOS, FRR_V4, GW4, EosLab, RouteLab, m_of
from test_verdict_runner import make, route


class NodeEosLab(EosLab):
    """EosLab that refuses any command addressed to another node."""

    def exec(self, node, cmd, timeout=60, input=None):
        assert node == "r1", f"command sent to {node!r}"
        return super().exec(node, cmd, timeout, input)


# ------------------------------------------------------------------------------------------- mgmt

def test_every_eos_command_names_its_node():
    lab = NodeEosLab()
    mgmt.prepare(lab, [])
    lab.running = CLAB_EOS
    mgmt.recheck(lab, "W")                                 # check_eos: config read, table scans, the delete again


def test_check_dispatches_junos_with_the_lab(monkeypatch):
    lab = RouteLab()
    seen = []
    monkeypatch.setattr(mgmt, "check_junos", lambda lab_, m, when: seen.append(lab_ is lab))
    mgmt._check(lab, mgmt.Mgmt("j", "clab", kind="junos"), "W")
    assert seen == [True]


def test_devices_found_by_route_never_read_addresses():
    lab = RouteLab()
    lab.addrs["r1"] = "2: eth9: <UP>\n    inet 172.31.99.9/24 scope global eth9\n"
    m = m_of(devices=())
    mgmt._linux_devices(lab, m)
    assert m.devices == {"eth0"} and not any(c[1:3] == ("addr", "show") for _, c in lab.calls)


def test_unreadable_addresses_message_keeps_the_last_200_characters():
    long = "A" * 300 + "END"
    lab = RouteLab(v4="", v6="")
    real = lab.exec_root
    lab.exec_root = lambda node, cmd, timeout=60: (ExecResult(cmd, 1, "", long) if cmd[1:3] == ["addr", "show"]
                                                   else real(node, cmd, timeout))
    with pytest.raises(LabError) as e:
        mgmt.prepare(lab, [])
    assert str(e.value) == f"r1: its addresses can't be read (`ip addr show` rc=1: {long[-200:]})"


@pytest.mark.parametrize("tokens,expected", [
    (["dev", "eth0", "encap", "mpls", "1", "via", "10.0.0.1"], {"dev": "eth0", "via": "10.0.0.1"}),
    (["encap", "mpls", "via", "10.0.0.1"], {"via": "10.0.0.1"}),
    (["via"], {"via": ""}),
    (["dev", "e", "via"], {"dev": "e", "via": ""}),
])
def test_pairs_more_edges(tokens, expected):
    assert mgmt._pairs(tokens) == expected


def test_readded_routes_accumulate_and_are_joined_with_semicolons():
    lab = RouteLab()
    m = mgmt.prepare(lab, [])["r1"]
    lab.tables["r1"][4] = FRR_V4
    mgmt.check_node(lab, "r1", "A")
    lab.tables["r1"][4] = FRR_V4
    mgmt.check_node(lab, "r1", "B")
    assert m.readded == ["default via 172.31.99.1 dev eth0 (A)", "default via 172.31.99.1 dev eth0 (B)"]
    assert mgmt.describe(m, "linux").endswith(
        "; back and removed again: default via 172.31.99.1 dev eth0 (A); default via 172.31.99.1 dev eth0 (B)")


def test_eos_readded_lines_accumulate():
    lab = EosLab()
    m = mgmt.prepare(lab, [])["r1"]
    lab.running = CLAB_EOS
    mgmt.recheck(lab, "A")
    lab.running = "hostname e1\nip route 0.0.0.0/0 172.31.99.1\n"
    mgmt.recheck(lab, "B")
    assert m.readded == ["ip route 0.0.0.0/0 172.31.99.1 (A)", "ipv6 route ::0/0 3fff:172:31:99::1 (A)",
                         "ip route 0.0.0.0/0 172.31.99.1 (B)"]


def test_eos_a_line_that_stays_after_the_second_delete_says_so_once():
    class Stuck(EosLab):
        def exec(self, node, cmd, timeout=60, input=None):
            if cmd[-1].startswith("configure"):
                self.sent.append(cmd[-1])
                return ExecResult(cmd, 0, "", "")
            return super().exec(node, cmd, timeout, input)
    lab = Stuck()
    lab.running = "hostname e1\n"
    lab.startup = "hostname e1\n"
    mgmt.prepare(lab, [])
    lab.running = "hostname e1\nip route 0.0.0.0/0 172.31.99.1\n"
    with pytest.raises(ManagementPathError) as e:
        mgmt.recheck(lab, "W")
    assert "(W, after deleting it again): ip route 0.0.0.0/0 172.31.99.1" in str(e.value) and len(lab.sent) == 1


def test_eos_other_text_joins_several_management_vias():
    text = json.dumps({"vrfs": {"default": {"routes": {"9.0.0.0/8": {"routeType": "static", "vias": [
        {"nexthopAddr": GW4, "interface": "Management0"}, {"nexthopAddr": "172.31.99.7", "interface": "Management1"}]}}}}})
    assert mgmt.classify_eos(text, 4, m_of())[1] == [
        "9.0.0.0/8 (vrf default, static) via 172.31.99.1 Management0, 172.31.99.7 Management1"]


def test_classify_linux_a_leg_without_a_device_and_routes_after_skipped_ones():
    rs = mgmt.parse_ip_route("default proto static\n\tnexthop via 10.9.0.2 weight 1\n"
                             "multicast ff00::/8 dev eth0 table local proto kernel\n"
                             "10.8.0.0/16 nhid 3 proto zebra\n10.7.0.0/16 via 172.31.99.1 dev eth0", 4)
    docker, other = mgmt.classify_linux(rs, m_of())
    # the leg without a device is refused too (adversary on the multipath fix), then the later routes still read
    assert docker == [] and [r.line for r in other] == ["nexthop via 10.9.0.2 weight 1", "10.8.0.0/16 nhid 3 proto zebra",
                                                        "10.7.0.0/16 via 172.31.99.1 dev eth0"]


def test_a_multipath_leg_on_the_management_device_without_a_gateway_is_other():
    rs = mgmt.parse_ip_route("default proto static\n\tnexthop dev eth0 weight 1", 4)
    assert [r.line for r in mgmt.classify_linux(rs, m_of())[1]] == ["nexthop dev eth0 weight 1"]


def test_parse_ip_addr_ignores_a_line_before_any_device_and_cuts_long_lines():
    assert mgmt.parse_ip_addr("    inet 10.0.0.1/24 scope global\n2: eth0: <UP>\n") == {"eth0": []}
    long = "2: eth0: <UP>\n    inet " + "x" * 200
    with pytest.raises(LabError) as e:
        mgmt.parse_ip_addr(long)
    assert str(e.value) == f"`ip addr show` printed an address it doesn't explain: {('inet ' + 'x' * 200)[:120]!r}"


def test_parse_ip_route_cuts_a_long_line_without_destination_at_120():
    raw = "unicast" + " " * 200
    with pytest.raises(LabError) as e:
        mgmt.parse_ip_route(raw, 4)
    assert str(e.value) == f"`ip route` printed a route without a destination: {raw[:120]!r}"


# ------------------------------------------------------------------------------------------- FRR route table

def test_frr_route_table_errors_name_the_command_exactly():
    def err(text):
        with pytest.raises(DriverError) as e:
            _route_table(ROUTE_CMD, text)
        return str(e.value)
    assert err("not json").startswith(f"unexpected output from `{ROUTE_CMD}`: ")
    assert err("[1, 2]") == f"unexpected output from `{ROUTE_CMD}`: [1, 2]"
    assert err('{"zz": []}') == f"unexpected output from `{ROUTE_CMD}`: not a prefix: 'zz'"
    long = ["y" * 200]
    assert err(json.dumps({"10.0.0.0/8": long[0]})) == \
        f"unexpected output from `{ROUTE_CMD}`: 10.0.0.0/8: " + ("y" * 200)[:150]
    entry = {"no": "protocol", "pad": "p" * 200}
    assert err(json.dumps({"10.0.0.0/8": [entry]})) == \
        f"unexpected output from `{ROUTE_CMD}`: 10.0.0.0/8: " + " ".join(str(entry)[:150].split())


def test_frr_an_empty_default_doesnt_stop_the_other_keys_being_read():
    with pytest.raises(DriverError, match="10.0.0.0/8: bad"):
        _route_table(ROUTE_CMD, '{"0.0.0.0/0": [], "10.0.0.0/8": "bad"}')


# ------------------------------------------------------------------------------------------- NX-OS rows

def test_nxos_rows_bad_json_and_a_long_row_exact():
    with pytest.raises(DriverError) as e:
        addresses.parse_nxos_ip_detail("not json", "default")
    assert str(e.value).startswith("unexpected output from `show ip interface vrf all`: ")
    row = {"pad": "r" * 200}
    body = json.dumps({"jsonrpc": "2.0", "result": {"body": {"TABLE_intf": {"ROW_intf": [row]}}}, "id": 1})
    with pytest.raises(DriverError) as e:
        addresses.parse_nxos_ip_detail(body, "default")
    assert str(e.value) == "unexpected output from `show ip interface vrf all`: row " + str(row)[:80]


# ------------------------------------------------------------------------------------------- runner

def test_preflight_resolves_a_vm_nodes_driver_with_its_override(monkeypatch):
    e = make(monkeypatch, kinds={"r1": ("sonic-vm", "img")})
    seen = []
    monkeypatch.setattr(runner, "resolve", lambda node, override=None: seen.append((node.name, override)) or "frr")
    cfg = runner.Config(path=Path("netdryrun.yml"), lab=Path("t.clab.yml"), timeout=60, checks=[route("a")],
                        drivers={"r1": "frr"})
    with pytest.raises(LabError):
        runner.preflight(cfg, e.lab)
    assert seen == [("r1", "frr"), ("r1", "frr")]          # the override loop, then the VM-kind check


def test_preflight_maps_a_sonic_endpoint_alias_by_kind(monkeypatch):
    e = make(monkeypatch, kinds={"r1": ("sonic-vs", "docker-sonic-vs")})
    e.lab.links = [(("r1", "Ethernet0"), ("r2", "eth1"))]
    cfg = runner.Config(path=Path("netdryrun.yml"), lab=Path("t.clab.yml"), timeout=60, checks=[route("a")],
                        scenarios=[Scenario("s", [Fault("link_down", "r1", "eth1")], [route("[s] x")])])
    runner.preflight(cfg, e.lab)


def test_the_sonic_port_check_runs_only_on_sonic_nodes(monkeypatch):
    e = make(monkeypatch)                                  # FRR nodes
    e.lab.sonic_port_device = lambda node, port: pytest.fail("asked a non-SONiC node for its SONiC port map")
    e.run([route("a")], [Scenario("s", [Fault("link_down", "r1", "eth1")], [route("[s] x", node="r3")])])


def test_run_reports_not_applicable_with_the_nodes_kind(monkeypatch):
    from test_mgmt import _route_lab
    e = make(monkeypatch, kinds={"r2": ("nokia_srlinux", "srl")})
    _route_lab(e)
    rep = e.run([route("a")])
    assert rep.environment["nodes"]["r2"]["management_default"] == "not applicable (nokia_srlinux)"


def test_run_logs_every_route_deleted_again(monkeypatch):
    e = make(monkeypatch)
    state = {"r1": mgmt.Mgmt("r1", "clab", kind="linux", readded=["a (A)", "b (B)"])}

    def prepare(lab, checks, log=None, sleep=None):
        lab.management = state
        return state
    monkeypatch.setattr(runner.mgmt, "prepare", prepare)
    monkeypatch.setattr(runner.mgmt, "recheck", lambda lab, when: None)
    e.run([route("a")])
    assert "r1: management default route was back and removed again: a (A); b (B)" in e.logs


def test_red_a_nexthop_object_default_beside_a_multipath_default_is_refused():
    """Two defaults in one table at different metrics, a multipath one and an nhid-only one without a device: the
    second was taken for the first's head and escaped the no-device refusal (9758c87 triage, coordinator: fix)."""
    rs = mgmt.parse_ip_route("default proto static metric 20\n\tnexthop via 10.9.0.2 dev d0 weight 1\n"
                             "default nhid 12 proto zebra metric 30", 4)
    assert [(r.line, r.multipath) for r in rs] == [("default proto static metric 20", True),
                                                   ("nexthop via 10.9.0.2 dev d0 weight 1", True),
                                                   ("default nhid 12 proto zebra metric 30", False)]
    assert [r.line for r in mgmt.classify_linux(rs, m_of())[1]] == ["default nhid 12 proto zebra metric 30"]


def test_a_single_default_beside_a_multipath_one_is_still_dockers_when_it_is():
    rs = mgmt.parse_ip_route("default proto static metric 20\n\tnexthop via 10.9.0.2 dev d0 weight 1\n"
                             "default via 172.31.99.1 dev eth0", 4)
    docker, other = mgmt.classify_linux(rs, m_of())
    assert [r.line for r in docker] == ["default via 172.31.99.1 dev eth0"] and other == []


def test_a_head_without_legs_is_not_multipath():
    assert [r.multipath for r in mgmt.parse_ip_route("default proto static\n10.0.0.0/8 dev eth1", 4)] == [False, False]



def test_a_multipath_leg_whose_device_cant_be_read_is_refused_not_dropped():
    """Adversary on the multipath fix: a leg whose device the parser misses (an unknown encap field) was dropped."""
    rs = mgmt.parse_ip_route("10.9.0.0/16 proto static metric 20\n"
                             "\tnexthop encap ip id 1 src 1.1.1.1 dst 2.2.2.2 ttl 0 tos 0 weird via 172.20.20.1 weight 1\n"
                             "\tnexthop via 10.0.0.2 dev eth1 weight 1", 4)
    other = mgmt.classify_linux(rs, m_of())[1]
    assert [r.line for r in other] == ["nexthop encap ip id 1 src 1.1.1.1 dst 2.2.2.2 ttl 0 tos 0 weird via "
                                       "172.20.20.1 weight 1"]


def test_the_encap_ip_key_csum_seq_flags_take_no_value():
    assert mgmt._pairs(["encap", "ip", "id", "1", "key", "csum", "seq", "via", "172.20.20.1", "dev", "eth0"]) == \
        {"via": "172.20.20.1", "dev": "eth0"}
    assert mgmt._pairs(["key", "dev", "eth0"]) == {"dev": "eth0"}
