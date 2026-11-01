"""NX-OS driver behaviour pinned down so that mutation testing finds no surviving mutant (the lighter beta gate:
mutation testing on the verdict code the driver adds). Like test_verdict_drivers.py for the other drivers: the
exact error messages (which command, what was wrong), every boolean and string form NX-OS uses, the evidence
kept and the timeouts. Each test names what a surviving mutant would have got wrong."""
from __future__ import annotations

import json

import pytest
from test_nxos import Lab, err, live_lab, ok, read

from netdryrun.drivers import nxos
from netdryrun.drivers.base import DriverError, NoSuchInstance, Route
from netdryrun.drivers.nxos import NxosDriver
from netdryrun.lab import ExecResult


def message(fn) -> str:
    with pytest.raises(DriverError) as e:
        fn()
    return str(e.value)


def U(command: str, detail: str) -> str:
    """The message base.unexpected() builds."""
    return f"unexpected output from `{command}`: {' '.join(detail.split())[:200]}"


# ------------------------------------------------------------------------------------------------ _reply / _body

def test_reply_messages_name_the_command_and_quote_the_output():
    assert message(lambda: nxos._reply("show x", "not json")) == U("show x", "not json")
    assert message(lambda: nxos._reply("show x", "[1, 2]")) == U("show x", "[1, 2]")
    assert message(lambda: nxos._reply("show x", '{"id": 1}')) == U("show x", '{"id": 1}')
    assert message(lambda: nxos._reply("show x", '{"result": 5}')) == U("show x", '{"result": 5}')
    assert message(lambda: nxos._reply("show x", '{"result": {"body": null}}')) == U("show x", '{"result": {"body": null}}')
    assert message(lambda: nxos._body("show x", ok([1]))) == U("show x", "body is not an object: [1]")


def test_error_replies_say_what_nxos_said():
    assert message(lambda: nxos._reply("show x", err("% Invalid command\n"))) == "NX-OS error from `show x`: % Invalid command"
    no_data = json.dumps({"jsonrpc": "2.0", "error": {"code": -32602, "message": "Invalid params"}, "id": 1})
    assert message(lambda: nxos._reply("show x", no_data)) == "NX-OS error from `show x`: Invalid params"
    assert message(lambda: nxos._reply("show x", '{"error": {}}')) == "NX-OS error from `show x`: no message"
    assert message(lambda: nxos._reply("show x", '{"error": "boom  now"}')) == "NX-OS error from `show x`: boom now"
    with pytest.raises(NoSuchInstance) as e:
        nxos._reply("show x", err("VRF NOPE does not exist"))
    assert str(e.value) == "NX-OS: VRF NOPE does not exist"
    assert isinstance(e.value, NoSuchInstance)
    long = "x" * 300
    assert message(lambda: nxos._reply("show x", err(long))) == f"NX-OS error from `show x`: {'x' * 200}"


# ------------------------------------------------------------------------------------------------ _rows / _flag / _vrf_rows

def test_rows_messages():
    assert message(lambda: nxos._rows("c", {"a": 1}, "x")) == U("c", "no TABLE_x.ROW_x: {'a': 1}")
    assert message(lambda: nxos._rows("c", {"TABLE_x": {"ROW_x": []}}, "x")) == U("c", "ROW_x: []")
    assert message(lambda: nxos._rows("c", {"TABLE_x": {"ROW_x": [1]}}, "x")) == U("c", "ROW_x: [1]")


@pytest.mark.parametrize("value,expected", [(True, True), (False, False), ("true", True), ("false", False),
                                            ("TRUE", True), ("False", False)])
def test_flag_reads_booleans_and_their_strings(value, expected):
    assert nxos._flag("c", value) is expected


@pytest.mark.parametrize("value", [None, 1, 0, "yes", "", [True]])
def test_flag_refuses_anything_else(value):
    assert message(lambda: nxos._flag("c", value)) == U("c", f"not a boolean: {str(value)[:80]!r}")


def test_vrf_rows_messages():
    body = {"TABLE_vrf": {"ROW_vrf": [{"vrf-name-out": "RED"}, {"vrf-name-out": "BLUE"}]}}
    assert message(lambda: nxos._vrf_rows("c", body, "GREEN")) == U("c", "no answer for vrf GREEN (vrfs: RED, BLUE)")
    assert message(lambda: nxos._vrf_rows("c", {"TABLE_vrf": {"ROW_vrf": {"x": 1}}}, "RED")) == \
        U("c", "vrf row without vrf-name-out: {'x': 1}")
    assert message(lambda: nxos._vrf_rows("c", {}, "RED")) == U("c", "no TABLE_vrf.ROW_vrf: {}")


# ------------------------------------------------------------------------------------------------ routes

def _rib(prefix_rows=None, addrf=True) -> str:
    row = {"vrf-name-out": "default"}
    if addrf:
        af = {"addrf": "ipv4"}
        if prefix_rows is not None:
            af["TABLE_prefix"] = {"ROW_prefix": prefix_rows}
        row["TABLE_addrf"] = {"ROW_addrf": af}
    return ok({"TABLE_vrf": {"ROW_vrf": row}})


NO_BGP = ok({"TABLE_vrf": {"ROW_vrf": {"vrf-name-out": "default"}}})


def test_a_vrf_or_family_without_tables_is_an_empty_answer():
    assert nxos.parse_routes(_rib(addrf=False), NO_BGP, "10.0.0.0/8") == []
    assert nxos.parse_routes(_rib(), NO_BGP, "10.0.0.0/8") == []
    assert nxos.parse_all_routes(_rib(addrf=False)) == []


def test_route_messages():
    cmd = nxos.ROUTE_CMD
    assert message(lambda: nxos.parse_routes(_rib([{"x": 1}]), NO_BGP, "10.0.0.0/8")) == \
        U(cmd, "prefix row without ipprefix: {'x': 1}")
    assert message(lambda: nxos.parse_routes(_rib([{"ipprefix": "nope"}]), NO_BGP, "10.0.0.0/8")) == \
        U(cmd, "not a prefix: 'nope'")
    row = {"ipprefix": "10.0.0.0/8", "TABLE_path": {"ROW_path": {"ubest": "true"}}}
    assert message(lambda: nxos.parse_routes(_rib([row]), NO_BGP, "10.0.0.0/8")) == \
        U(cmd, "path without clientname: {'ubest': 'true'}")
    row = {"ipprefix": "10.0.0.0/8", "TABLE_path": {"ROW_path": {"clientname": "", "ubest": "true"}}}
    assert message(lambda: nxos.parse_routes(_rib([row]), NO_BGP, "10.0.0.0/8")) == \
        U(cmd, "path without clientname: {'clientname': '', 'ubest': 'true'}")
    row = {"ipprefix": "10.0.0.0/8", "TABLE_path": {"ROW_path": {"clientname": "static", "ubest": "maybe"}}}
    assert message(lambda: nxos.parse_routes(_rib([row]), NO_BGP, "10.0.0.0/8")) == U(cmd, "not a boolean: 'maybe'")
    assert message(lambda: nxos.parse_routes(ok({"x": 1}), NO_BGP, "10.0.0.0/8")) == U(cmd, "no TABLE_vrf.ROW_vrf: {'x': 1}")


def test_unknown_client_names_keep_their_own_name():
    row = {"ipprefix": "10.0.0.0/8", "TABLE_path": {"ROW_path": [{"clientname": "rpm-12", "ubest": "true"},
                                                                 {"clientname": "ospf-1", "ubest": True}]}}
    assert nxos.parse_routes(_rib([row]), NO_BGP, "10.0.0.0/8") == [Route("10.0.0.0/8", "rpm", True),
                                                                      Route("10.0.0.0/8", "ospf", True)]


def _bgp(prefix_rows, rd=True, afi=True) -> str:
    safi = {"safi": 1}
    if rd:
        safi["TABLE_rd"] = {"ROW_rd": [{"TABLE_prefix": {"ROW_prefix": r}} for r in prefix_rows]}
    row = {"vrf-name-out": "default"}
    if afi:
        row["TABLE_afi"] = {"ROW_afi": {"afi": 1, "TABLE_safi": {"ROW_safi": safi}}}
    return ok({"TABLE_vrf": {"ROW_vrf": row}})


PATH = {"pathtype": "external", "pathbest": "true", "aspath": "65002", "ipnexthop": "10.0.1.2", "neighbor": "10.0.1.2",
        "neighborid": "2.2.2.2", "metric": 0, "localpref": "100"}


def test_bgp_tables_without_rows_are_empty_and_paths_from_every_rd_count():
    assert nxos.parse_bgp_paths(_bgp([], afi=False), "10.0.0.0/8") == []
    assert nxos.parse_bgp_paths(_bgp([], rd=False), "10.0.0.0/8") == []
    two = _bgp([{"ipprefix": "10.0.0.0/8", "TABLE_path": {"ROW_path": PATH}},
                {"ipprefix": "10.0.0.0/8", "TABLE_path": {"ROW_path": {**PATH, "neighbor": "10.0.1.6", "pathbest": "false"}}}])
    assert [p.neighbor for p in nxos.parse_bgp_paths(two, "10.0.0.0/8")] == ["10.0.1.2", "10.0.1.6"]
    no_rows = ok({"TABLE_vrf": {"ROW_vrf": {"vrf-name-out": "default", "TABLE_afi": {"ROW_afi": {
        "afi": 1, "TABLE_safi": {"ROW_safi": {"safi": 1, "TABLE_rd": {"ROW_rd": {"x": 1}}}}}}}}})
    assert nxos.parse_bgp_paths(no_rows, "10.0.0.0/8") == []


def test_bgp_messages():
    cmd = nxos.BGP_CMD
    assert message(lambda: nxos.parse_bgp_paths(_bgp([{"x": 1}]), "10.0.0.0/8")) == U(cmd, "prefix row without ipprefix: {'x': 1}")
    assert message(lambda: nxos.parse_bgp_paths(_bgp([{"ipprefix": "bad"}]), "10.0.0.0/8")) == U(cmd, "not a prefix: 'bad'")
    assert message(lambda: nxos.parse_bgp_paths(_bgp([{"ipprefix": "10.0.0.0/8"}]), "10.0.0.0/8")) == \
        U(cmd, "no TABLE_path.ROW_path: {'ipprefix': '10.0.0.0/8'}")
    no_safi = ok({"TABLE_vrf": {"ROW_vrf": {"vrf-name-out": "default", "TABLE_afi": {"ROW_afi": {"afi": 1}}}}})
    assert message(lambda: nxos.parse_bgp_paths(no_safi, "10.0.0.0/8")) == U(cmd, "no TABLE_safi.ROW_safi: {'afi': 1}")
    assert message(lambda: nxos.parse_bgp_paths(ok({"y": 2}), "10.0.0.0/8")) == U(cmd, "no TABLE_vrf.ROW_vrf: {'y': 2}")
    assert message(lambda: nxos.parse_bgp_paths("[]", "10.0.0.0/8")) == U(cmd, "[]")


@pytest.mark.parametrize("kind", ["local", "LOCAL", "Aggregate", "redist", "Redistributed"])
def test_the_routers_own_path_types_are_not_learned_whatever_the_case(kind):
    assert nxos._learned({"pathtype": kind, "neighbor": "10.0.1.2"}) is False


def test_learned_and_peer_messages_and_v6_zero():
    assert nxos._learned({"pathtype": "external", "ipv6neighbor": "::"}) is False
    assert nxos._learned({"pathtype": "internal", "neighbor": "10.0.0.9"}) is True
    assert message(lambda: nxos._learned({"neighbor": "1.1.1.1"})) == U(nxos.BGP_CMD, "path without pathtype: {'neighbor': '1.1.1.1'}")
    assert message(lambda: nxos._peer({"pathtype": "external"})) == U(nxos.BGP_CMD, "path without neighbor: {'pathtype': 'external'}")


@pytest.mark.parametrize("text,expected", [
    ("65002 {65004,65005}", "65002 {65004,65005}"),
    ("{65004, 65005}", "{65004,65005}"),
    ("[65010 65011] 65002", "[65010,65011] 65002"),
    ("(65010,65011) 65002", "(65010 65011) 65002"),
    ("65002 65003", "65002 65003"),
])
def test_as_path_segments_and_commas(text, expected):
    assert nxos._as_path(text) == expected


def test_as_path_messages():
    assert message(lambda: nxos._as_path(5)) == U(nxos.BGP_CMD, "aspath: '5'")
    assert message(lambda: nxos._as_path("65002 x")) == U(nxos.BGP_CMD, "aspath: '65002 x'")


def test_communities_in_every_form_nxos_uses():
    assert nxos._communities({"community": "65002:100 no-export"}, "community") == ["65002:100", "65535:65281"]
    assert nxos._communities({"community": ["65002:100"]}, "community") == ["65002:100"]
    assert nxos._communities({}, "community") == []
    assert nxos._communities({"TABLE_community": {"ROW_community": {"community": "65002:1"}}}, "community") == ["65002:1"]
    assert message(lambda: nxos._communities({"community": ["65002:100", 5]}, "community")) == \
        U(nxos.BGP_CMD, "community: \"['65002:100', 5]\"")
    assert message(lambda: nxos._communities({"community": 5}, "community")) == U(nxos.BGP_CMD, "community: '5'")
    assert message(lambda: nxos._communities({"TABLE_community": {"ROW_community": {"x": 1}}}, "community")) == \
        U(nxos.BGP_CMD, "community: [{'x': 1}]")
    assert message(lambda: nxos._communities({"TABLE_community": {"ROW_community": []}}, "community")) == \
        U(nxos.BGP_CMD, "ROW_community: []")


def test_vrf_state_and_ping_reply_messages_and_values():
    row = {"vrf_name": "RED", "vrf_state": 5, "pad": "p" * 200}
    assert message(lambda: nxos.parse_vrf_state(ok({"TABLE_vrf": {"ROW_vrf": row}}), "RED")) == U(nxos.VRF_CMD, str(row)[:150])
    assert message(lambda: nxos.parse_vrf_state(ok({"x": 1}), "RED")) == U(nxos.VRF_CMD, "no TABLE_vrf.ROW_vrf: {'x': 1}")
    assert message(lambda: nxos.parse_vrf_state("nope", "RED")) == U(nxos.VRF_CMD, "nope")
    assert nxos.parse_ping_reply("not json") == (0, 0)
    assert nxos.parse_ping_reply('{"result": {"msg": 5}}') == (0, 0)
    assert nxos.parse_ping_reply('{"result": null}') == (0, 0)


# ------------------------------------------------------------------------------------------------ the driver

class RcLab(Lab):
    """Every answer from one ExecResult (rc, stdout, stderr)."""

    def __init__(self, rc, out, errout):
        super().__init__([])
        self.answer = (rc, out, errout)

    def exec(self, node, cmd, timeout=60, input=None):
        self.calls.append((cmd[3], cmd[4], timeout, node, cmd[5]))
        return ExecResult(list(cmd), *self.answer)


def test_evidence_keeps_the_end_of_long_output_and_names_the_node():
    lab = RcLab(1, "o" * 25000 + "END", "e" * 3000 + "ERR")
    with pytest.raises(DriverError):
        NxosDriver(lab, "n1").bgp_neighbors()
    ev = lab.calls
    assert ev[0][3] == "n1" and ev[0][4] == "60" and ev[0][2] == 75
    d = NxosDriver(Lab([("show bgp ipv6", read("nxos_summary_v6.txt")), ("show bgp ipv4", read("nxos_summary_v4.txt"))]), "n1")
    obs = d.bgp_neighbors()
    assert obs.evidence[0] == {"node": "n1", "cmd": "nxapi cli: show bgp ipv4 unicast summary vrf default", "rc": 0,
                               "output": read("nxos_summary_v4.txt")[-20000:], "stderr": ""}
    lab = RcLab(1, "o" * 25000 + "END", "e" * 3000 + "ERR")
    ev: list = []
    with pytest.raises(DriverError):
        NxosDriver(lab, "n1")._nxapi("show x", ev)
    assert ev == [{"node": "n1", "cmd": "nxapi cli: show x", "rc": 1, "output": ("o" * 25000 + "END")[-20000:],
                   "stderr": ("e" * 3000 + "ERR")[-2000:]}]


def test_ping_evidence_timeouts_and_a_failed_transport():
    lab = RcLab(0, read("nxos_ping_lo.txt"), "")
    obs = NxosDriver(lab, "n1").ping("192.168.20.1", None, 3, "RED")
    assert lab.calls == [("cli_ascii", "ping 192.168.20.1 count 3 vrf RED", 3 * 2 + 30, "n1", str(3 * 2 + 15))]
    assert obs.value == (3, 3)
    assert obs.evidence == [{"node": "n1", "cmd": "nxapi cli_ascii: ping 192.168.20.1 count 3 vrf RED", "rc": 0,
                             "output": read("nxos_ping_lo.txt")[-5000:], "stderr": ""}]
    long_out, long_err = "p" * 6000 + read("nxos_ping_lo.txt"), "s" * 1500
    obs = NxosDriver(RcLab(0, long_out, long_err), "n1").ping("192.168.20.1", "192.168.10.1", 2)
    assert obs.evidence[0]["output"] == long_out[-5000:] and obs.evidence[0]["stderr"] == long_err[-1000:]
    # the helper failed (rc 3) after printing statistics: ping did not run, whatever the output says
    assert NxosDriver(RcLab(3, read("nxos_ping_lo.txt"), "x"), "n1").ping("192.168.20.1", None, 3).value == (0, 0)


def test_every_method_keeps_its_evidence_and_reads_the_vrf_it_was_asked():
    d = NxosDriver(live_lab([("show bgp ipv4 unicast 172.16.2.0/24 vrf RED", read("nxos_bgp_red.txt")),
                             ("show ip route 172.16.2.0/24 vrf RED", read("nxos_route_red.txt"))]), "n1")
    paths = d.bgp_paths("172.16.2.0/24", "RED")
    assert paths.value[0].as_path == "65003 65003 65003"
    assert [e["cmd"] for e in paths.evidence] == ["nxapi cli: show bgp ipv4 unicast 172.16.2.0/24 vrf RED"]
    routes = d.routes("172.16.2.0/24", "RED")
    assert [e["cmd"] for e in routes.evidence] == ["nxapi cli: show ip route 172.16.2.0/24 vrf RED",
                                                   "nxapi cli: show bgp ipv4 unicast 172.16.2.0/24 vrf RED"]
    allr = d.all_routes()
    assert [e["cmd"] for e in allr.evidence] == ["nxapi cli: show ip route vrf default"]
    # a VRF that exists but has no BGP neighbors: confirmed with `show vrf`, which is kept as evidence
    lab = live_lab([("show bgp ipv4 unicast summary vrf RED", read("nxos_summary_red_v6.txt"))])
    obs = NxosDriver(lab, "n1").bgp_neighbors("RED")
    assert obs.value == {} and obs.evidence[-1]["cmd"] == "nxapi cli: show vrf RED"


def test_no_instance_and_missing_vrf_messages():
    with pytest.raises(NoSuchInstance) as e:
        NxosDriver(live_lab(), "n1").bgp_neighbors("EMPTY")
    assert str(e.value) == "no BGP instance in VRF 'EMPTY' on n1 (BGP runs in: RED, default)"
    lab = live_lab([("show bgp vrf all ipv4 unicast summary", ok({"TABLE_vrf": {"ROW_vrf": {"vrf-name-out": "RED"}}}))])
    with pytest.raises(NoSuchInstance) as e:
        NxosDriver(lab, "n1").bgp_neighbors("EMPTY")
    assert str(e.value) == "no BGP instance in VRF 'EMPTY' on n1 (BGP runs in: RED)"
    lab = live_lab([("show vrf EMPTY", ok({"TABLE_vrf": {"ROW_vrf": {"vrf_name": "EMPTY", "vrf_state": "Down"}}}))])
    with pytest.raises(NoSuchInstance) as e:
        NxosDriver(lab, "n1").routes("10.0.0.0/8", "EMPTY")
    assert str(e.value) == "VRF 'EMPTY' is Down on n1"


def test_a_failed_request_says_why_or_no_output():
    """rc != 0: the last line of stderr (else stdout); nothing at all reads `no output`, never an IndexError."""
    for out, errout, why in (("", "", "no output"), ("o1\no2\n", "", "o2"), ("o\n", "e1\ne2\n", "e2")):
        with pytest.raises(DriverError) as e:
            NxosDriver(RcLab(3, out, errout), "n1")._nxapi("show x", [])
        assert str(e.value) == f"`show x` failed on n1 (rc=3): {why}"
