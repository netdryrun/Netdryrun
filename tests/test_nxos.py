"""Cisco NX-OS (Nexus 9000v) driver, beta: parsers against output captured from a live n9kv
(tests/fixtures/nxos_*.txt, listed with command and image in nxos_captures.tsv), the NX-API transport,
and the false-pass rules: an error, a missing VRF or output the parser doesn't know is never read as
"no routes", "no sessions" or 0 prefixes."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from netdryrun.drivers import DRIVERS, DriverError, detect, nxos
from netdryrun.drivers.base import NoSuchInstance, Route
from netdryrun.drivers.nxos import NxosDriver
from netdryrun.lab import ExecResult, Lab as RealLab, LabError, Node

FIX = Path(__file__).parent / "fixtures"


def read(name: str) -> str:
    return (FIX / name).read_text()


def ok(body) -> str:
    """An NX-API JSON-RPC success reply (body None = the command printed nothing)."""
    return json.dumps({"jsonrpc": "2.0", "result": None if body is None else {"body": body}, "id": 1})


def err(msg: str, code: int = -32602) -> str:
    return json.dumps({"jsonrpc": "2.0", "error": {"code": code, "message": "Invalid params",
                                                   "data": {"msg": msg}}, "id": 1})


class Lab:
    """A node answering each NX-API command (the argv after the helper) with the first rule whose needle
    is in it. An answer is stdout or (rc, stdout, stderr)."""

    def __init__(self, rules):
        self.rules, self.calls = list(rules), []

    def exec(self, node, cmd, timeout=60, input=None):
        assert cmd[:2] == ["python3", "-c"] and cmd[2] == nxos.HELPER
        method, command = cmd[3], cmd[4]
        self.calls.append((method, command, timeout))
        for needle, answer in self.rules:
            if needle in command:
                rc, out, e = answer if isinstance(answer, tuple) else (0, answer, "")
                return ExecResult(list(cmd), rc, out, e)
        raise AssertionError(f"unexpected command: {command}")

    def commands(self):
        return [c[1] for c in self.calls]


# ------------------------------------------------------------------------------------- registration

def test_registered_and_detected():
    assert DRIVERS["nxos"] is NxosDriver and NxosDriver.name == "nxos"
    for kind in ("cisco_n9kv", "vr-n9kv", "vr-cisco_n9kv"):
        assert detect(Node("n1", "clab-x-n1", kind, "vrnetlab/cisco_n9kv:9300-10.4.8.M")) == "nxos"
    assert NxosDriver.unsupported_afis == frozenset({"evpn"})


def test_link_faults_on_an_nxos_node_are_refused(tmp_path):
    topo = tmp_path / "t.clab.yml"
    topo.write_text("name: t\ntopology:\n  nodes:\n    n1: {kind: cisco_n9kv, image: x}\n    f1: {kind: linux, image: frr}\n"
                    "  links:\n    - endpoints: [n1:eth1, f1:eth1]\n")
    lab = RealLab(topo)
    with pytest.raises(LabError, match="NX-OS nodes"):
        lab._require_linux_links("n1")
    lab._require_linux_links("f1")


# ---------------------------------------------------------------------------------------- transport

def test_helper_failure_is_an_error_never_empty():
    """NX-OS still booting: the helper can't reach NX-API and exits 3. Every state call raises."""
    # the helper's message while the n9kv VM was booting (examples/nxos-frr, live run)
    booting = (3, "", "NX-API not reachable (is NX-OS still booting?): URLError: <urlopen error _ssl.c:1012: "
                      "The handshake operation timed out>\n")
    d = NxosDriver(Lab([("", booting)]), "n1")
    for call in (lambda: d.bgp_neighbors(), lambda: d.routes("10.0.0.0/24"), lambda: d.bgp_paths("10.0.0.0/24"),
                 lambda: d.all_routes()):
        with pytest.raises(DriverError, match="still booting"):
            call()
    assert d.ping("10.0.0.1", None, 2).value == (0, 0)   # ping did not run: reported, never passed


def test_evidence_names_the_nxos_command_not_the_helper():
    lab = Lab([("show bgp", ok(None)), ("show vrf", ok(None))])
    obs = NxosDriver(lab, "n1").bgp_neighbors()
    assert [e["cmd"] for e in obs.evidence] == ["nxapi cli: show bgp ipv4 unicast summary vrf default",
                                                "nxapi cli: show bgp ipv6 unicast summary vrf default"]
    assert all(c[2] == 75 for c in lab.calls)   # the helper times out at 60 s, docker exec 15 s later


@pytest.mark.parametrize("text", ["", "not json", "[]", "[1, 2]", "{}", '{"result": 5}', '{"result": {"x": 1}}',
                                  '{"error": {}}', '{"error": "boom"}', '{"result": {"body": [1]}}'])
def test_reply_shapes_that_are_not_a_body_raise(text):
    with pytest.raises(DriverError):
        nxos._body("show x", text)


def test_reply_null_result_is_none_and_error_is_raised():
    assert nxos._body("show x", ok(None)) is None
    assert nxos._body("show x", "[" + ok({"a": 1}) + "]") == {"a": 1}
    with pytest.raises(DriverError, match="Invalid command"):
        nxos._body("show x", err("% Invalid command at '^' marker."))


def test_rows_one_row_is_an_object_several_a_list():
    assert nxos._rows("c", {"TABLE_x": {"ROW_x": {"a": 1}}}, "x") == [{"a": 1}]
    assert nxos._rows("c", {"TABLE_x": {"ROW_x": [{"a": 1}, {"a": 2}]}}, "x") == [{"a": 1}, {"a": 2}]
    assert nxos._rows("c", {}, "x", required=False) == []
    for bad in ({}, {"TABLE_x": {}}, {"TABLE_x": []}, {"TABLE_x": {"ROW_x": []}}, {"TABLE_x": {"ROW_x": [1]}},
                {"TABLE_x": {"ROW_x": "a"}}, {"TABLE_x": None}):
        with pytest.raises(DriverError):
            nxos._rows("c", bad, "x")


def test_vrf_listed_twice_is_merged_and_a_missing_vrf_is_unexpected():
    body = {"TABLE_vrf": {"ROW_vrf": [{"vrf-name-out": "RED"}, {"vrf-name-out": "RED", "TABLE_af": {}},
                                      {"vrf-name-out": "BLUE"}]}}
    assert len(nxos._vrf_rows("c", body, "RED")) == 2
    with pytest.raises(DriverError, match="no answer for vrf GREEN"):
        nxos._vrf_rows("c", body, "GREEN")


@pytest.mark.parametrize("vrf", ["all", "ALL", "", "a b", "red|x", "*", "x\nshow run"])
def test_bad_vrf_names_are_refused_before_anything_runs(vrf):
    lab = Lab([("", ok(None))])
    d = NxosDriver(lab, "n1")
    for call in (lambda: d.routes("10.0.0.0/24", vrf=vrf), lambda: d.bgp_paths("10.0.0.0/24", vrf=vrf),
                 lambda: d.bgp_neighbors(vrf=vrf), lambda: d.all_routes(vrf=vrf),
                 lambda: d.ping("10.0.0.1", None, 1, vrf=vrf)):
        with pytest.raises(DriverError, match="VRF"):
            call()
    assert lab.calls == []


def test_as_path_forms():
    assert nxos._as_path("") == ""
    assert nxos._as_path("65002 65003 65003") == "65002 65003 65003"
    assert nxos._as_path("65002 {65004 65005}") == "65002 {65004,65005}"
    assert nxos._as_path("(65010 65011) 65002") == "(65010 65011) 65002"
    for bad in ("65002 x", "65002 {}", None, 5, "65002 i"):
        with pytest.raises(DriverError):
            nxos._as_path(bad)


# ------------------------------------------------------------------- parsers, on captured live output

def test_summary_reads_accepted_prefixes_and_every_state():
    """f1 sends four prefixes and n1's inbound route-map denies one: prefixreceived reads 3 (accepted)."""
    n = nxos.parse_bgp_summary(read("nxos_summary_v4.txt"))
    assert {k: (v.state, v.prefixes) for k, v in n.items()} == {
        "10.0.1.2": ("established", {"ipv4-unicast": 3}), "10.0.9.9": ("idle", {"ipv4-unicast": 0})}
    out = {}
    nxos.parse_bgp_summary(read("nxos_summary_v4.txt"), into=out)
    nxos.parse_bgp_summary(read("nxos_summary_v6.txt"), afi="ipv6-unicast", into=out)
    assert out["2001:db8:1::2"].prefixes == {"ipv6-unicast": 1}
    assert nxos.parse_bgp_summary(read("nxos_summary_red.txt"), "RED")["10.0.2.2"].prefixes == {"ipv4-unicast": 1}
    assert nxos.parse_bgp_summary(read("nxos_summary_red_v6.txt"), "RED") == {}   # family without neighbors
    # a family that says it has peers but lists none is unexpected, never "no neighbors"
    doc = json.loads(read("nxos_summary_v4.txt"))
    del doc["result"]["body"]["TABLE_vrf"]["ROW_vrf"]["TABLE_af"]["ROW_af"]["TABLE_saf"]["ROW_saf"]["TABLE_neighbor"]
    with pytest.raises(DriverError, match="TABLE_neighbor"):
        nxos.parse_bgp_summary(json.dumps(doc))
    with pytest.raises(DriverError, match="no answer for vrf RED"):
        nxos.parse_bgp_summary(read("nxos_summary_v4.txt"), "RED")


@pytest.mark.parametrize("name", ["nxos_summary_emptyvrf.txt", "nxos_summary_novrf.txt", "nxos_invalid.txt"])
def test_summary_errors_raise(name):
    with pytest.raises(nxos.CliError):
        nxos.parse_bgp_summary(read(name))


def _strip_bgp_path_from_rib(text: str) -> str:
    """The captured RIB answer for 0.0.0.0/0 with only the static path (some releases list only the
    installed path)."""
    doc = json.loads(text)
    prefix = doc["result"]["body"]["TABLE_vrf"]["ROW_vrf"]["TABLE_addrf"]["ROW_addrf"]["TABLE_prefix"]["ROW_prefix"]
    prefix["TABLE_path"]["ROW_path"] = prefix["TABLE_path"]["ROW_path"][0]
    return json.dumps(doc)


def test_received_but_not_installed_default_is_present():
    """The core false-pass class: the leaked default is BGP's best path but the static (distance 1)
    wins the routing table. NX-OS lists the BGP path in the RIB without `ubest`."""
    routes = nxos.parse_routes(read("nxos_route_default.txt"), read("nxos_bgp_default.txt"), "0.0.0.0/0")
    assert sorted((r.protocol, r.active) for r in routes) == [("bgp", False), ("static", True)]
    # the BGP table alone is enough: a RIB that doesn't list the losing path still reads it as present
    routes = nxos.parse_routes(_strip_bgp_path_from_rib(read("nxos_route_default.txt")), read("nxos_bgp_default.txt"),
                               "0.0.0.0/0")
    assert sorted((r.protocol, r.active) for r in routes) == [("bgp", False), ("static", True)]
    assert [p.best for p in nxos.parse_bgp_paths(read("nxos_bgp_default.txt"), "0.0.0.0/0")] == [True]


def test_routes_on_live_output():
    assert nxos.parse_routes(read("nxos_route_20.txt"), read("nxos_bgp_20.txt"), "192.168.20.0/24") == \
        [Route("192.168.20.0/24", "bgp", True)]
    local = nxos.parse_routes(read("nxos_route_local.txt"), read("nxos_bgp_local.txt"), "192.168.10.1/32")
    assert sorted(r.protocol for r in local) == ["connected", "local"]
    assert nxos.parse_routes(read("nxos_route_v6.txt"), read("nxos_bgp_v6.txt"), "2001:db8:20::/48")[0].active
    red = nxos.parse_routes(read("nxos_route_red.txt"), read("nxos_bgp_red.txt"), "172.16.2.0/24", "RED")
    assert red == [Route("172.16.2.0/24", "bgp", True)]
    # denied by inbound policy: in neither table (NX-OS keeps no rejected paths without soft-reconfiguration)
    assert nxos.parse_routes(read("nxos_route_66.txt"), read("nxos_bgp_66.txt"), "192.168.66.0/24") == []
    # an existing VRF without routes: NX-OS 10.4(8) answered an empty table in one boot and "nothing" (null) in
    # another (captures 2026-10-28 and 2026-10-30); "nothing" is trusted only after `show vrf` (the driver tests)
    assert nxos.parse_routes(read("nxos_route_emptyvrf.txt"), read("nxos_bgp_emptyvrf.txt"), "10.0.0.0/8", "EMPTY") in ([], None)
    assert nxos.parse_routes(read("nxos_route_emptyvrf_null.txt"), read("nxos_bgp_emptyvrf.txt"), "10.0.0.0/8", "EMPTY") is None
    # a VRF that doesn't exist: both commands print nothing, which is not "no routes" until the VRF is confirmed
    assert nxos.parse_routes(read("nxos_route_novrf.txt"), read("nxos_bgp_novrf.txt"), "10.0.0.0/8", "NOPE") is None
    # another VRF's answer is never this VRF's absence
    with pytest.raises(DriverError):
        nxos.parse_routes(read("nxos_route_red.txt"), read("nxos_bgp_red.txt"), "172.16.2.0/24", "default")


def test_bgp_paths_on_live_output():
    [p] = nxos.parse_bgp_paths(read("nxos_bgp_20.txt"), "192.168.20.0/24")
    assert (p.best, p.as_path, p.next_hop, p.local_pref, p.med, p.neighbor) == \
        (True, "65002", "10.0.1.2", 200, 50, "10.0.1.2")
    assert p.communities == ["65002:100", "65002:200"] and p.large_communities == ["65002:1:1"]
    [local] = nxos.parse_bgp_paths(read("nxos_bgp_local.txt"), "192.168.10.1/32")
    assert (local.as_path, local.neighbor, local.med) == ("", None, None)   # its neighborid is the router ID
    [v6] = nxos.parse_bgp_paths(read("nxos_bgp_v6.txt"), "2001:db8:20::/48")
    assert (v6.next_hop, v6.neighbor) == ("2001:db8:1::2", "2001:db8:1::2")
    [red] = nxos.parse_bgp_paths(read("nxos_bgp_red.txt"), "172.16.2.0/24", "RED")
    assert red.as_path == "65003 65003 65003"
    assert nxos.parse_bgp_paths(read("nxos_bgp_66.txt"), "192.168.66.0/24") == []
    assert nxos.parse_bgp_paths(read("nxos_bgp_novrf.txt"), "10.0.0.0/8", "NOPE") is None
    assert nxos.parse_bgp_paths(read("nxos_bgp_20.txt"), "192.168.20.0/25") == []   # exact prefix only


def test_learned_needs_a_path_type_and_an_address():
    assert nxos._learned({"pathtype": "external", "neighbor": "10.0.1.2"})
    assert nxos._learned({"pathtype": "internal", "ipv6neighbor": "2001:db8::2"})
    assert not nxos._learned({"pathtype": "local", "neighbor": "0.0.0.0"})
    assert not nxos._learned({"pathtype": "external", "neighbor": "0.0.0.0"})
    for bad in ({"neighbor": "10.0.1.2"}, {"pathtype": "external"}, {"pathtype": "", "neighbor": "1.1.1.1"},
                {"pathtype": "external", "neighbor": 5}):
        with pytest.raises(DriverError):
            nxos._learned(bad)


def test_all_routes_vrfs_and_ping_on_live_output():
    assert len(nxos.parse_all_routes(read("nxos_all_routes.txt"))) == 7
    assert "bgp" in {r.protocol for r in nxos.parse_all_routes(read("nxos_all_routes_v6.txt"))}
    assert nxos.parse_all_routes(read("nxos_all_routes_emptyvrf.txt"), "EMPTY") in ([], None)
    assert nxos.parse_all_routes(read("nxos_all_routes_emptyvrf_null.txt"), "EMPTY") is None
    assert nxos.parse_all_routes(read("nxos_all_routes_novrf.txt"), "NOPE") is None
    assert nxos.parse_bgp_vrfs(read("nxos_bgp_vrf_list.txt")) == ["RED", "default"]
    assert nxos.parse_vrf_state(read("nxos_vrf_red.txt"), "RED") == "Up"
    assert nxos.parse_vrf_state(read("nxos_vrf_empty.txt"), "EMPTY") == "Up"
    assert nxos.parse_vrf_state(read("nxos_vrf_nope.txt"), "NOPE") is None
    assert nxos.parse_vrf_state(read("nxos_vrf_red.txt"), "BLUE") is None
    pings = {n: nxos.parse_ping_reply(read(f"nxos_{n}.txt")) for n in
             ("ping_ok", "ping_lo", "ping_red", "ping_fail", "ping_novrf", "ping6_ok", "ping_badsrc")}
    assert pings == {"ping_ok": (3, 3), "ping_lo": (3, 3), "ping_red": (3, 3), "ping_fail": (2, 0),
                     "ping_novrf": (0, 0), "ping6_ok": (3, 3), "ping_badsrc": (0, 0)}


# --------------------------------------------------------------- the driver on a node answering live output

def live_lab(extra=()):
    """n1 answering every command with the output captured from the lab (unknown VRF NOPE, VRF EMPTY
    without BGP, VRF RED with one peer). `extra` rules come first."""
    return Lab(list(extra) + [
        ("show bgp vrf all ipv4 unicast summary", read("nxos_bgp_vrf_list.txt")),
        ("show bgp ipv4 unicast summary vrf default", read("nxos_summary_v4.txt")),
        ("show bgp ipv6 unicast summary vrf default", read("nxos_summary_v6.txt")),
        ("show bgp ipv4 unicast summary vrf RED", read("nxos_summary_red.txt")),
        ("show bgp ipv6 unicast summary vrf RED", read("nxos_summary_red_v6.txt")),
        ("summary vrf EMPTY", read("nxos_summary_emptyvrf.txt")),
        ("summary vrf NOPE", read("nxos_summary_novrf.txt")),
        ("show ip route 0.0.0.0/0 vrf default", read("nxos_route_default.txt")),
        ("show bgp ipv4 unicast 0.0.0.0/0 vrf default", read("nxos_bgp_default.txt")),
        ("show ip route 192.168.20.0/24 vrf default", read("nxos_route_20.txt")),
        ("show bgp ipv4 unicast 192.168.20.0/24 vrf default", read("nxos_bgp_20.txt")),
        ("show ip route 10.0.0.0/8 vrf NOPE", read("nxos_route_novrf.txt")),
        ("show bgp ipv4 unicast 10.0.0.0/8 vrf NOPE", read("nxos_bgp_novrf.txt")),
        ("show ip route 10.0.0.0/8 vrf EMPTY", read("nxos_route_emptyvrf.txt")),
        ("show bgp ipv4 unicast 10.0.0.0/8 vrf EMPTY", read("nxos_bgp_emptyvrf.txt")),
        ("show ip route vrf NOPE", read("nxos_all_routes_novrf.txt")),
        ("show ip route vrf EMPTY", read("nxos_all_routes_emptyvrf.txt")),
        ("show ip route vrf default", read("nxos_all_routes.txt")),
        ("show vrf NOPE", read("nxos_vrf_nope.txt")),
        ("show vrf EMPTY", read("nxos_vrf_empty.txt")),
        ("show vrf RED", read("nxos_vrf_red.txt")),
        ("ping 192.168.20.1", read("nxos_ping_lo.txt")),
        ("vrf NOPE", read("nxos_ping_novrf.txt")),
    ])


def test_driver_on_live_output():
    d = NxosDriver(live_lab(), "n1")
    assert set(d.bgp_neighbors().value) == {"10.0.1.2", "10.0.9.9", "2001:db8:1::2"}
    assert set(d.bgp_neighbors("RED").value) == {"10.0.2.2"}
    assert sorted((r.protocol, r.active) for r in d.routes("0.0.0.0/0").value) == [("bgp", False), ("static", True)]
    assert d.bgp_paths("192.168.20.0/24").value[0].local_pref == 200
    assert d.routes("10.0.0.0/8", "EMPTY").value == []          # VRF confirmed: a real absence
    assert len(d.all_routes().value) == 7 and d.all_routes("EMPTY").value == []
    obs = d.ping("192.168.20.1", "192.168.10.1", 3)
    assert obs.value == (3, 3)
    assert obs.evidence[0]["cmd"] == "nxapi cli_ascii: ping 192.168.20.1 count 3 source 192.168.10.1 vrf default"


def test_unknown_vrf_is_never_no_routes():
    """NX-OS prints nothing for routes and BGP paths in a VRF that doesn't exist, exactly as for an
    existing VRF without them. The driver confirms the VRF before trusting the silence."""
    d = NxosDriver(live_lab(), "n1")
    for call in (lambda: d.routes("10.0.0.0/8", "NOPE"), lambda: d.bgp_paths("10.0.0.0/8", "NOPE"),
                 lambda: d.all_routes("NOPE"), lambda: d.bgp_neighbors("NOPE")):
        with pytest.raises(NoSuchInstance, match="NOPE"):
            call()
    assert d.ping("10.0.2.2", None, 2, "NOPE").value == (0, 0)


def test_vrf_without_bgp_has_no_bgp_instance():
    with pytest.raises(NoSuchInstance, match="no BGP instance in VRF 'EMPTY'"):
        NxosDriver(live_lab(), "n1").bgp_neighbors("EMPTY")


def test_summary_error_in_a_vrf_bgp_runs_in_is_an_error_not_no_instance():
    lab = live_lab([("show bgp ipv6 unicast summary vrf default", read("nxos_invalid.txt"))])
    with pytest.raises(nxos.CliError) as e:
        NxosDriver(lab, "n1").bgp_neighbors()
    assert not isinstance(e.value, NoSuchInstance)


def test_bgp_not_running_yet_is_an_error_never_no_neighbors():
    """While vrnetlab is still typing the startup config, NX-API answers but BGP isn't configured: the
    VRF list errors too. That is "no usable state", never "no neighbors"."""
    lab = live_lab([("show bgp", read("nxos_invalid.txt"))])
    with pytest.raises(DriverError) as e:
        NxosDriver(lab, "n1").bgp_neighbors()
    assert not isinstance(e.value, NoSuchInstance)


# ------------------------------------------------- must-fail, per check type, through the NX-OS driver

def _verdict(raw: dict, lab) -> bool:
    """A check (through the real config validator) run by the real evaluators against NxosDriver."""
    from test_checks import FakeClock

    from netdryrun.checks import converge_then_hold, is_post_convergence, run_check
    from netdryrun.config import _validate_check
    check = _validate_check(0, {"node": "n1", **raw}, 12)
    clock, driver = FakeClock(), NxosDriver(lab, "n1")
    if is_post_convergence(check):
        return converge_then_hold(check, driver, hold=6, interval=3, clock=clock, sleep=clock.sleep).passed
    return run_check(check, driver, interval=3, clock=clock, sleep=clock.sleep).passed


NX_MUST_FAIL = [
    # bgp_session
    ("session idle", {"type": "bgp_session", "neighbor": "10.0.9.9"}),
    ("session not configured", {"type": "bgp_session", "neighbor": "10.0.1.99"}),
    ("session must be down but is up", {"type": "bgp_session", "neighbor": "10.0.1.2", "state": "down"}),
    ("session in a VRF that doesn't exist", {"type": "bgp_session", "neighbor": "10.0.2.2", "vrf": "NOPE"}),
    ("session in a VRF without BGP", {"type": "bgp_session", "neighbor": "10.0.2.2", "vrf": "EMPTY"}),
    # bgp_prefixes (accepted: 3 of the 4 sent)
    ("over max", {"type": "bgp_prefixes", "neighbor": "10.0.1.2", "max": 2}),
    ("not exact", {"type": "bgp_prefixes", "neighbor": "10.0.1.2", "exact": 4}),
    ("below min", {"type": "bgp_prefixes", "neighbor": "10.0.1.2", "min": 4}),
    ("over max in ipv6", {"type": "bgp_prefixes", "neighbor": "2001:db8:1::2", "afi": "ipv6-unicast", "max": 0}),
    ("max on an idle session", {"type": "bgp_prefixes", "neighbor": "10.0.9.9", "max": 10}),
    # route
    ("leaked default received but not installed", {"type": "route", "prefix": "0.0.0.0/0", "present": False}),
    ("leaked default via bgp", {"type": "route", "prefix": "0.0.0.0/0", "protocol": "bgp", "present": False}),
    ("leak absent in a VRF that doesn't exist", {"type": "route", "prefix": "10.0.0.0/8", "vrf": "NOPE",
                                                 "present": False}),
    ("route via the wrong protocol", {"type": "route", "prefix": "192.168.20.0/24", "protocol": "static"}),
    ("default must be bgp and active", {"type": "route", "prefix": "0.0.0.0/0", "protocol": "bgp"}),
    # bgp_route
    ("leaked BGP path", {"type": "bgp_route", "prefix": "0.0.0.0/0", "present": False}),
    ("no BGP path in a VRF that doesn't exist", {"type": "bgp_route", "prefix": "10.0.0.0/8", "vrf": "NOPE",
                                                 "present": False}),
    ("wrong local-pref", {"type": "bgp_route", "prefix": "192.168.20.0/24", "local_pref": 100}),
    ("wrong MED", {"type": "bgp_route", "prefix": "192.168.20.0/24", "med": 0}),
    ("missing community", {"type": "bgp_route", "prefix": "192.168.20.0/24", "communities": ["65002:300"]}),
    ("forbidden community", {"type": "bgp_route", "prefix": "192.168.20.0/24", "without_communities": ["65002:100"]}),
    ("forbidden large community", {"type": "bgp_route", "prefix": "192.168.20.0/24",
                                   "without_communities": ["65002:1:1"]}),
    ("wrong as-path", {"type": "bgp_route", "prefix": "192.168.20.0/24", "as_path": "65002 65002"}),
    ("wrong next hop", {"type": "bgp_route", "prefix": "192.168.20.0/24", "next_hop": "10.0.1.1"}),
    # ping
    ("ping must fail but replies", {"type": "ping", "target": "192.168.20.1", "source": "192.168.10.1",
                                    "count": 3, "expect": "failure"}),
    ("ping that gets no replies", {"type": "ping", "target": "192.0.2.1", "count": 2}),
    ("ping in a VRF that doesn't exist", {"type": "ping", "target": "10.0.2.2", "count": 2, "vrf": "NOPE"}),
    ("ping in a VRF that doesn't exist, expect failure", {"type": "ping", "target": "10.0.2.2", "count": 2,
                                                          "vrf": "NOPE", "expect": "failure"}),
]


@pytest.mark.parametrize("raw", [pytest.param(raw, id=label) for label, raw in NX_MUST_FAIL])
def test_must_fail_on_nxos(raw):
    lab = live_lab([("ping 192.0.2.1", read("nxos_ping_fail.txt"))])
    assert _verdict(raw, lab) is False


NX_MUST_PASS = [
    {"type": "bgp_session", "neighbor": "10.0.1.2"},
    {"type": "bgp_session", "neighbor": "10.0.9.9", "state": "down"},
    {"type": "bgp_session", "neighbor": "10.0.2.2", "vrf": "RED"},
    {"type": "bgp_prefixes", "neighbor": "10.0.1.2", "exact": 3},
    {"type": "route", "prefix": "0.0.0.0/0", "protocol": "static"},
    {"type": "route", "prefix": "192.168.20.0/24", "protocol": "bgp"},
    {"type": "route", "prefix": "10.0.0.0/8", "vrf": "EMPTY", "present": False},
    {"type": "bgp_route", "prefix": "192.168.20.0/24", "local_pref": 200, "med": 50, "as_path": "65002",
     "next_hop": "10.0.1.2", "communities": ["65002:100", "65002:1:1"], "without_communities": ["no-export"]},
    {"type": "ping", "target": "192.168.20.1", "source": "192.168.10.1", "count": 3},
]


@pytest.mark.parametrize("raw", NX_MUST_PASS, ids=lambda r: f"{r['type']}:{r.get('prefix', r.get('neighbor', r.get('target')))}")
def test_must_pass_on_nxos(raw):
    """The control: the same live output passes the checks it should, so the must-fail cases fail for the
    reason they name."""
    assert _verdict(raw, live_lab()) is True


def test_every_check_type_has_nxos_must_fail_cases():
    from netdryrun.config import CHECK_TYPES
    for ctype in CHECK_TYPES:
        assert sum(raw["type"] == ctype for _, raw in NX_MUST_FAIL) >= 2, ctype


def test_exact_commands_per_vrf_and_family():
    """Pinned so a mutant reading the default VRF or the IPv4 table instead can't survive."""
    lab = Lab([("show vrf RED", read("nxos_vrf_red.txt")), ("ping", read("nxos_ping6_ok.txt")),
               ("summary", read("nxos_summary_red.txt")), ("", ok(None))])
    d = NxosDriver(lab, "n1")
    assert d.routes("2001:db8:20::/48", "RED").value == []
    assert d.bgp_paths("2001:db8:20::/48", "RED").value == []
    assert d.all_routes("RED", family=6).value == []
    assert d.ping("2001:db8:1::2", "2001:db8:1::1", 4, "RED").value == (3, 3)
    assert lab.commands() == [
        "show ipv6 route 2001:db8:20::/48 vrf RED", "show bgp ipv6 unicast 2001:db8:20::/48 vrf RED", "show vrf RED",
        "show bgp ipv6 unicast 2001:db8:20::/48 vrf RED", "show vrf RED",
        "show ipv6 route vrf RED", "show vrf RED",
        "ping6 2001:db8:1::2 count 4 source 2001:db8:1::1 vrf RED"]
    assert [c[0] for c in lab.calls] == ["cli"] * 7 + ["cli_ascii"]
    assert lab.calls[-1][2] == 4 * 2 + 30
    lab.calls.clear()
    d.bgp_neighbors("RED")
    assert lab.commands() == ["show bgp ipv4 unicast summary vrf RED", "show bgp ipv6 unicast summary vrf RED"]


def test_helper_can_be_quoted_by_the_capture_script():
    """scripts/capture_fixtures.sh passes HELPER inside single quotes to `bash -c`."""
    assert not set("'$`") & set(nxos.HELPER)


@pytest.mark.parametrize("route,all_routes", [("nxos_route_emptyvrf.txt", "nxos_all_routes_emptyvrf.txt"),
                                              ("nxos_route_emptyvrf_null.txt", "nxos_all_routes_emptyvrf_null.txt")])
def test_both_live_shapes_of_an_empty_vrf_are_a_confirmed_absence(route, all_routes):
    """Whichever shape NX-OS answers for an existing VRF without routes, the driver confirms the VRF and reads
    a real absence; for a VRF that doesn't exist, the same "nothing" raises (test_unknown_vrf_is_never_no_routes)."""
    lab = live_lab([("show ip route 10.0.0.0/8 vrf EMPTY", read(route)), ("show ip route vrf EMPTY", read(all_routes))])
    d = NxosDriver(lab, "n1")
    assert d.routes("10.0.0.0/8", "EMPTY").value == [] and d.all_routes("EMPTY").value == []


# ------------------------------------------------------------------------------------------- readiness gate

def _helper_with_health(path) -> str:
    assert nxos.HELPER.count('HEALTH = "/health"') == 1
    return nxos.HELPER.replace('HEALTH = "/health"', f"HEALTH = {str(path)!r}")


@pytest.mark.parametrize("content,why", [(None, "readiness unknown"), ("1 starting", "not ready"),
                                         ("1 VM failed - restarting", "not ready"), ("", "not ready"),
                                         ("0 running\n", "not reachable")])
def test_the_helper_asks_nothing_until_vrnetlab_says_the_config_is_applied(tmp_path, content, why):
    """vrnetlab writes "0 running" only after launch.py has typed the whole startup config; NX-API answers minutes
    earlier. Before that, every request fails (rc 3: no usable state), so no check samples a half-configured
    switch. With "0 running" the helper goes on to NX-API (not running here: "not reachable")."""
    import subprocess
    import sys
    health = tmp_path / "health"
    if content is not None:
        health.write_text(content)
    r = subprocess.run([sys.executable, "-c", _helper_with_health(health), "cli", "show version", "1"],
                       capture_output=True, text=True, timeout=60)
    assert r.returncode == 3 and r.stdout == "" and why in r.stderr


def test_med_zero_is_unknown_and_a_med_zero_check_is_refused(tmp_path):
    """NX-OS prints "metric": 0 for a path received with no MED (live: 0.0.0.0/0 from FRR's default-originate,
    172.16.2.0/24 from a network statement), so 0 can't be told from no MED: read as unknown, and `med: 0` is
    refused before deploying instead of passing on a path that carries no MED."""
    from netdryrun.config import _validate_check
    from netdryrun.drivers import check_supported
    from netdryrun.lab import Lab as RealLab
    assert [p.med for p in nxos.parse_bgp_paths(read("nxos_bgp_default.txt"), "0.0.0.0/0")] == [None]
    assert [p.med for p in nxos.parse_bgp_paths(read("nxos_bgp_red.txt"), "172.16.2.0/24", "RED")] == [None]
    assert [p.med for p in nxos.parse_bgp_paths(read("nxos_bgp_20.txt"), "192.168.20.0/24")] == [50]
    topo = tmp_path / "t.clab.yml"
    topo.write_text("name: t\ntopology:\n  nodes:\n    n1: {kind: cisco_n9kv, image: x}\n")
    lab = RealLab(topo)
    with pytest.raises(DriverError, match="med: 0 can't be checked on nxos: NX-OS output cannot tell MED 0 from no MED"):
        check_supported(lab, _validate_check(0, {"type": "bgp_route", "node": "n1", "prefix": "10.0.0.0/8", "med": 0}, 20))
    check_supported(lab, _validate_check(0, {"type": "bgp_route", "node": "n1", "prefix": "10.0.0.0/8", "med": 50}, 20))


def _vrf_rows(*rows):
    return ok({"TABLE_vrf": {"ROW_vrf": [{"vrf_name": n, "vrf_id": i, "vrf_state": st, "vrf_reason": "--"}
                                         for i, (n, st) in enumerate(rows, 1)]}})


def test_vrfs_for_record_leave_out_default_and_vrnetlabs_management_vrf():
    text = _vrf_rows(("RED", "Up"), ("default", "Up"), ("management", "Up"), ("EMPTY", "Up"), ("OLD", "Down"))
    assert nxos.parse_vrfs(text) == ["EMPTY", "RED"]
    lab = Lab([("show vrf", text)])
    obs = NxosDriver(lab, "n1").vrfs()
    assert obs.value == ["EMPTY", "RED"] and lab.commands() == ["show vrf"]
    with pytest.raises(DriverError):
        nxos.parse_vrfs(ok(None))
    with pytest.raises(DriverError):
        nxos.parse_vrfs(ok({"TABLE_vrf": {"ROW_vrf": {"vrf_name": "RED"}}}))


def test_nos_version_comes_from_show_version():
    assert nxos.parse_version(read("nxos_version.txt")) == "NX-OS 10.4(8)"
    assert nxos.parse_version(ok({"x": 1})) is None
    assert NxosDriver(Lab([("show version", read("nxos_version.txt"))]), "n1").nos_version() == "NX-OS 10.4(8)"
    assert NxosDriver(Lab([("show version", (3, "", "not ready"))]), "n1").nos_version() is None
