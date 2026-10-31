"""Juniper cJunosEvolved driver (beta): parsers against output captured from a live cJunosEvolved
26.2R1.7-EVO lab (tests/fixtures/junos_*.txt, commands in junos_CAPTURES.md), the driver against a fake
node, and a must-fail matrix: every check type, through the real validator and scheduler, on Junos
output where the check must fail."""
import json
from pathlib import Path

import pytest
from test_checks import FakeClock

from netdryrun.checks import converge_then_hold, is_post_convergence, run_check
from netdryrun.config import _validate_check
from netdryrun.drivers import DriverError, junos
from netdryrun.drivers.base import NoSuchInstance
from netdryrun.drivers.junos import JunosDriver
from netdryrun.lab import ExecResult

FIX = Path(__file__).parent / "fixtures"


def read(name: str) -> str:
    return (FIX / name).read_text()


def _obj(d) -> str:
    return json.dumps(d, indent=2)


# ---------------------------------------------------------------- BGP neighbors

def test_neighbors_master():
    n = junos.parse_bgp_neighbors(read("junos_bgp_neighbor.txt"), "master")
    assert set(n) == {"10.0.1.2", "10.0.2.2", "10.0.9.9", "2001:db8:1::2"}   # "+179" stripped
    assert n["10.0.1.2"].state == "established"
    # 5 received; 10.30.0.0/24 rejected by import policy and 10.31.0.0/24 hidden (next hop) aren't accepted
    assert n["10.0.1.2"].prefixes == {"ipv4-unicast": 3}
    # Junos's count can't tell those two apart: up to 5 until the hidden routes' reasons are read (interop IOP-7)
    assert n["10.0.1.2"].prefixes_upto == {"ipv4-unicast": 5} and n["10.0.2.2"].prefixes_upto == {}
    assert n["10.0.2.2"].prefixes == {"ipv4-unicast": 1}
    assert n["2001:db8:1::2"].prefixes == {"ipv6-unicast": 1}
    assert n["10.0.9.9"].state == "idle" and n["10.0.9.9"].prefixes == {}


def test_neighbors_routing_instance():
    n = junos.parse_bgp_neighbors(read("junos_bgp_neighbor_red.txt"), "RED")
    assert set(n) == {"10.0.3.2"} and n["10.0.3.2"].prefixes == {"ipv4-unicast": 1}


def test_neighbors_of_another_instance_are_unexpected():
    """`show bgp neighbor` without `instance` lists every instance: a RED peer must never read as master's."""
    with pytest.raises(DriverError, match="instance 'RED', not 'master'"):
        junos.parse_bgp_neighbors(read("junos_bgp_neighbor_all_idle.txt"), "master")
    with pytest.raises(DriverError, match="not 'RED'"):
        junos.parse_bgp_neighbors(read("junos_bgp_neighbor.txt"), "RED")


def test_no_neighbors_is_empty():
    assert junos.parse_bgp_neighbors(read("junos_bgp_neighbor_none.txt"), "NOPE") == {}


def _peer_doc(mutate):
    d = json.loads(read("junos_bgp_neighbor.txt"))
    mutate(d["bgp-information"][0]["bgp-peer"][0])
    return _obj(d)


@pytest.mark.parametrize("mutate", [
    lambda p: p.pop("bgp-rib"),                                            # established, no counts
    lambda p: p["bgp-rib"][0].pop("accepted-prefix-count"),
    lambda p: p["bgp-rib"][0].update({"accepted-prefix-count": [{"data": "many"}]}),
    lambda p: p.pop("peer-state"),
    lambda p: p.update({"peer-state": [{"data": "Established"}, {"data": "Idle"}]}),
    lambda p: p["bgp-rib"][0].update({"name": [{"data": "RED.inet.0"}]}),  # a RIB of another instance
    lambda p: p.update({"peer-address": [{"data": "10.0.2.2"}]}),         # the same peer twice
], ids=["no-rib", "no-accepted", "bad-count", "no-state", "two-states", "foreign-rib", "duplicate-peer"])
def test_neighbor_shape_errors(mutate):
    with pytest.raises(DriverError, match="unexpected output"):
        junos.parse_bgp_neighbors(_peer_doc(mutate), "master")


def test_neighbor_evpn_rib_is_skipped_and_refused():
    doc = _peer_doc(lambda p: p["bgp-rib"].append({"name": [{"data": "bgp.evpn.0"}],
                                                   "accepted-prefix-count": [{"data": "4"}]}))
    assert junos.parse_bgp_neighbors(doc, "master")["10.0.1.2"].prefixes == {"ipv4-unicast": 3}
    assert "evpn" in JunosDriver.unsupported_afis


@pytest.mark.parametrize("text", ["", "\n", "\nerror: syntax error, expecting <command>: nonsense\n", "{}", "[]",
                                  '{"bgp-information": []}', '{"bgp-information": [{}], "x": 1}'])
def test_neighbor_garbage_raises(text):
    with pytest.raises(DriverError):
        junos.parse_bgp_neighbors(text, "master")


def test_junos_errors_are_named():
    with pytest.raises(DriverError, match="Junos error .* syntax error"):
        junos.parse_bgp_neighbors(read("junos_error_syntax.txt"), "master")
    with pytest.raises(DriverError, match="Junos error"):
        junos.parse_routes(_obj({"xnm:error": [{"message": [{"data": "boom"}]}]}), "10.0.0.0/24")


# ---------------------------------------------------------------- routes

def rts(routes):
    return [(r.protocol, r.active) for r in routes]


def test_routes_best_and_backup_bgp():
    assert rts(junos.parse_routes(read("junos_route_paths.txt"), "10.20.0.0/24")) == [("bgp", True), ("bgp", False)]


def test_route_leak_received_but_not_selected_is_present():
    """The core false-pass class: a leaked default losing to the static on preference."""
    assert rts(junos.parse_routes(read("junos_route_leak.txt"), "0.0.0.0/0")) == [("static", True), ("bgp", False)]


def test_hidden_routes():
    # rejected by import policy: filtered, never accepted (FRR and EOS don't keep it at all)
    assert junos.parse_routes(read("junos_route_hidden_policy.txt"), "10.30.0.0/24") == []
    # hidden because its next hop is unusable: received, so present but not selected
    assert rts(junos.parse_routes(read("junos_route_hidden_nexthop.txt"), "10.31.0.0/24")) == [("bgp", False)]


def test_hidden_with_another_or_no_reason_counts_as_present():
    def doc(reason):
        d = json.loads(read("junos_route_hidden_policy.txt"))
        e = d["route-information"][0]["route-table"][0]["rt"][0]["rt-entry"][0]
        if reason is None:
            e.pop("hidden-reason")
        else:
            e["hidden-reason"] = [{"data": reason}]
        return _obj(d)
    for reason in (None, "AS path loop", "Rejected by import policy, sort of"):
        assert rts(junos.parse_routes(doc(reason), "10.30.0.0/24")) == [("bgp", False)], reason


def test_route_protocol_names():
    assert rts(junos.parse_routes(read("junos_route_static.txt"), "10.99.0.0/24")) == [("static", True)]
    assert rts(junos.parse_routes(read("junos_route_connected.txt"), "10.0.1.0/30")) == [("connected", True)]
    assert rts(junos.parse_routes(read("junos_route_local.txt"), "10.0.1.1/32")) == [("local", True)]
    assert rts(junos.parse_routes(read("junos_route_v6.txt"), "2001:db8:20::/48", "inet6.0")) == [("bgp", True)]
    assert rts(junos.parse_routes(read("junos_route_red.txt"), "10.40.0.0/24", "RED.inet.0")) == [("bgp", True)]


def test_real_empty_answers():
    assert junos.parse_routes(read("junos_route_empty.txt"), "10.88.0.0/24") == []
    # without `all`, a prefix with only hidden routes answers with the table header and no rt
    assert junos.parse_routes(read("junos_route_hidden_only_summary.txt"), "10.30.0.0/24") == []
    # another prefix in the answer (never with `exact`, but checked) is not this one
    assert junos.parse_routes(read("junos_route_paths.txt"), "10.20.0.0/25") == []


def test_no_such_table_is_not_empty():
    with pytest.raises(junos.NoSuchTable):
        junos.parse_routes(read("junos_route_no_table.txt"), "10.88.0.0/24", "NOPE.inet.0")
    with pytest.raises(junos.NoSuchTable):
        junos.parse_bgp_paths(read("junos_route_no_table.txt"), "10.88.0.0/24", "NOPE.inet.0")


def test_answer_for_another_table_is_unexpected():
    with pytest.raises(DriverError, match="table 'RED.inet.0' in the answer for 'inet.0'"):
        junos.parse_routes(read("junos_route_red.txt"), "10.40.0.0/24", "inet.0")


@pytest.mark.parametrize("edit", [
    lambda rt: rt.pop("rt-entry"),
    lambda rt: rt["rt-entry"][0].pop("protocol-name"),
    lambda rt: rt.update({"rt-destination": [{"data": "not-an-ip"}]}),
    lambda rt: rt.update({"rt-entry": {"protocol-name": "BGP"}}),
], ids=["no-entries", "no-protocol", "bad-destination", "entries-not-list"])
def test_route_shape_errors(edit):
    d = json.loads(read("junos_route_paths.txt"))
    edit(d["route-information"][0]["route-table"][0]["rt"][0])
    with pytest.raises(DriverError, match="unexpected output"):
        junos.parse_routes(_obj(d), "10.20.0.0/24")


def test_all_routes():
    routes = {(r.prefix, r.protocol, r.active) for r in junos.parse_all_routes(read("junos_route_table.txt"))}
    assert {("0.0.0.0/0", "static", True), ("0.0.0.0/0", "bgp", False), ("10.20.0.0/24", "bgp", True),
            ("10.0.1.0/30", "connected", True), ("10.0.1.1/32", "local", True)} <= routes
    red = junos.parse_all_routes(read("junos_route_table_red.txt"), "RED.inet.0")
    assert ("10.40.0.0/24", "bgp", True) in {(r.prefix, r.protocol, r.active) for r in red}
    assert junos.parse_all_routes(read("junos_route_table_v6.txt"), "inet6.0")


# ---------------------------------------------------------------- BGP paths

def test_bgp_paths_attributes():
    best, other = junos.parse_bgp_paths(read("junos_route_paths.txt"), "10.20.0.0/24")
    assert best.best and not other.best
    assert (best.as_path, best.next_hop, best.local_pref, best.med, best.neighbor) == \
        ("65002", "10.0.1.2", 100, 50, "10.0.1.2")
    assert best.communities == ["65002:100", "65002:200"] and best.large_communities == ["65002:1:2"]
    assert (other.as_path, other.next_hop, other.med, other.communities) == \
        ("65003 65003 65003", "10.0.2.2", 0, ["65003:20"])


def test_bgp_best_when_a_static_wins_on_preference():
    """FRR calls a BGP path that loses only to a static BGP's best: Junos reports it inactive, reason
    'Route Preference'. It is still the BGP best path for attribute checks."""
    (p,) = junos.parse_bgp_paths(read("junos_route_leak.txt"), "0.0.0.0/0")
    assert p.best and p.as_path == "65002" and p.neighbor == "10.0.1.2"


def test_bgp_paths_hidden():
    assert junos.parse_bgp_paths(read("junos_route_hidden_policy.txt"), "10.30.0.0/24") == []
    (p,) = junos.parse_bgp_paths(read("junos_route_hidden_nexthop.txt"), "10.31.0.0/24")
    assert not p.best and p.next_hop == "10.77.0.1" and p.local_pref is None and p.neighbor == "10.0.1.2"


def test_bgp_paths_of_a_static_route_are_none():
    """Junos keeps the router's own routes out of BGP's view: a static exported into BGP isn't a BGP route."""
    assert junos.parse_bgp_paths(read("junos_route_static.txt"), "10.99.0.0/24") == []


@pytest.mark.parametrize("text,expected", [
    ("AS path: 65002 I", "65002"), ("AS path: I", ""), ("AS path: 65002 65003 ?", "65002 65003"),
    ("AS path: 65002 {65010 65011} E", "65002 {65010,65011}"), ("AS path: (65100 65101) 65002 I", "(65100 65101) 65002"),
    ("AS path: 65002 I (Originator)\n  Cluster list: 10.0.0.1", "65002"),
])
def test_as_path(text, expected):
    assert junos._as_path("c", text) == expected


@pytest.mark.parametrize("text", ["65002 I", "AS path: 65002", "AS path: 65002 [65001] I", "AS path: 65x I", ""])
def test_as_path_unknown_raises(text):
    with pytest.raises(DriverError):
        junos._as_path("c", text)


# ---------------------------------------------------------------- instances and ping

def test_instance():
    assert junos.parse_instance(read("junos_instance_red.txt"), "RED") == ["RED.inet.0"]
    assert "inet.0" in junos.parse_instance(read("junos_instance_master.txt"), "master")
    assert junos.parse_instance(read("junos_instance_none.txt"), "NOPE") is None
    assert junos.parse_instance(read("junos_instance_red.txt"), "BLUE") is None
    with pytest.raises(DriverError):
        junos.parse_instance("", "RED")


@pytest.mark.parametrize("name,expected", [
    ("junos_ping.txt", (3, 3)), ("junos_ping_vrf.txt", (3, 3)), ("junos_ping6.txt", (3, 3)),
    ("junos_ping_noreply.txt", (3, 0)), ("junos_ping_unreachable.txt", (0, 0)),
    ("junos_ping_badsource.txt", (0, 0)), ("junos_ping_no_instance.txt", (0, 0)),
])
def test_ping(name, expected):
    assert junos.parse_ping(read(name)) == expected


def test_ping_garbage_raises():
    for text in ("", "PING 10.0.0.1 ...\n3 packets transmitted, 3 received", read("junos_error_syntax.txt"),
                 _obj({"ping-results": [{"probe-results-summary": [{"probes-sent": [{"data": "1"}],
                                                                    "responses-received": [{"data": "3"}]}]}]})):
        with pytest.raises(DriverError):
            junos.parse_ping(text)


# ---------------------------------------------------------------- the driver against a fake node

class Lab:
    """A cJunosEvolved node: the Junos command inside the SSH hop is answered by the first rule whose
    substring is in it."""

    def __init__(self, rules):
        self.rules, self.calls, self.argv = rules, [], []

    def exec(self, node, cmd, timeout=60, input=None):
        self.argv.append(cmd)
        line = cmd[-1]
        self.calls.append(line)
        for needle, answer in self.rules:
            if needle in line:
                rc, out = answer if isinstance(answer, tuple) else (0, answer)
                return ExecResult(cmd, rc, out, "" if rc == 0 else "ssh: connect to host 176.1.1.1 port 22: refused")
        raise AssertionError(f"unexpected command: {line}")


def test_commands_go_through_the_vm_ssh_hop():
    lab = Lab([("show bgp neighbor instance master", read("junos_bgp_neighbor.txt")),
               ("receive-protocol bgp 10.0.1.2 table inet.0 hidden", read("junos_rp_hidden_lab1.txt"))])
    n = JunosDriver(lab, "j1").bgp_neighbors().value
    assert lab.argv[0][:2] == ["ssh", "-q"] and "root@176.1.1.1" in lab.argv[0]
    assert lab.calls == ["cli -c 'show bgp neighbor instance master | display json | no-more'",
                         "cli -c 'show route receive-protocol bgp 10.0.1.2 table inet.0 hidden extensive "
                         "| display json | no-more'"]
    # 5 received, 1 rejected by import policy: the route hidden for its next hop was received (interop IOP-7)
    assert n["10.0.1.2"].prefixes == {"ipv4-unicast": 4} and n["10.0.1.2"].prefixes_upto == {}


def test_vm_not_reachable_is_an_error():
    """While the VM boots, the SSH hop fails (rc 255): an error on that sample, never 'no sessions'."""
    lab = Lab([("", (255, ""))])
    for call in (lambda d: d.bgp_neighbors(), lambda d: d.routes("10.0.0.0/24"), lambda d: d.bgp_paths("10.0.0.0/24"),
                 lambda d: d.all_routes(), lambda d: d.ping("10.0.0.1", None, 1)):
        with pytest.raises(DriverError, match="rc=255"):
            call(JunosDriver(lab, "j1"))


def test_unknown_instance_raises_everywhere():
    lab = Lab([("show route instance NOPE", read("junos_instance_none.txt")),
               ("show bgp neighbor instance NOPE", read("junos_bgp_neighbor_none.txt")),
               ("NOPE.inet", read("junos_route_no_table.txt"))])
    d = JunosDriver(lab, "j1")
    for call in (lambda: d.bgp_neighbors("NOPE"), lambda: d.routes("10.0.0.0/24", "NOPE"),
                 lambda: d.bgp_paths("10.0.0.0/24", "NOPE"), lambda: d.all_routes("NOPE")):
        with pytest.raises(NoSuchInstance, match="routing-instance 'NOPE' does not exist"):
            call()


def test_existing_instance_without_the_route_or_table_is_empty():
    lab = Lab([("show route instance RED", read("junos_instance_red.txt")),
               ("RED.inet6.0", read("junos_route_no_table.txt")),   # RED has no IPv6
               ("RED.inet.0", read("junos_route_empty.txt"))])
    d = JunosDriver(lab, "j1")
    assert d.routes("10.88.0.0/24", "RED").value == []
    assert d.routes("2001:db8::/32", "RED").value == []
    assert d.bgp_paths("2001:db8::/32", "RED").value == []
    assert d.all_routes("RED", family=6).value == []


def test_table_error_for_a_listed_table_raises():
    lab = Lab([("show route instance RED", read("junos_instance_red.txt")),
               ("RED.inet.0", read("junos_route_no_table.txt"))])
    with pytest.raises(DriverError, match="lists it"):
        JunosDriver(lab, "j1").routes("10.88.0.0/24", "RED")


def test_default_instance_reads_master_tables():
    lab = Lab([("exact table inet.0 all extensive", read("junos_route_leak.txt"))])
    obs = JunosDriver(lab, "j1").routes("0.0.0.0/0")
    assert rts(obs.value) == [("static", True), ("bgp", False)] and len(lab.calls) == 1
    lab = Lab([("show bgp neighbor instance master", read("junos_bgp_neighbor_none.txt"))])
    assert JunosDriver(lab, "j1").bgp_neighbors().value == {}       # master always exists


def test_vrf_master_and_special_names_are_refused():
    lab = Lab([("", "{}")])
    d = JunosDriver(lab, "j1")
    for vrf in ("master", "MASTER", "all", "a'b", "red|x"):
        with pytest.raises(DriverError, match="VRF"):
            d.routes("10.0.0.0/24", vrf)
    assert lab.calls == []


def test_ping_command():
    lab = Lab([("ping", read("junos_ping_vrf.txt"))])
    assert JunosDriver(lab, "j1").ping("10.40.0.1", "10.255.1.1", 3, "RED").value == (3, 3)
    assert lab.calls == ["cli -c 'ping 10.40.0.1 count 3 rapid wait 1 source 10.255.1.1 routing-instance RED"
                         " | display json | no-more'"]


# ---------------------------------------------------------------- must-fail matrix on Junos output

NEIGHBORS = read("junos_bgp_neighbor.txt")
STATE = {
    "show bgp neighbor instance master": NEIGHBORS,
    "receive-protocol bgp 10.0.1.2 table inet.0 hidden": read("junos_rp_hidden_lab1.txt"),
    "10.20.0.0/24 exact table inet.0": read("junos_route_paths.txt"),
    "0.0.0.0/0 exact table inet.0": read("junos_route_leak.txt"),
    "10.30.0.0/24 exact table inet.0": read("junos_route_hidden_policy.txt"),
    "10.31.0.0/24 exact table inet.0": read("junos_route_hidden_nexthop.txt"),
    "10.88.0.0/24 exact table inet.0": read("junos_route_empty.txt"),
    "show route instance NOPE": read("junos_instance_none.txt"),
    "NOPE.inet.0": read("junos_route_no_table.txt"),
    "show bgp neighbor instance NOPE": read("junos_bgp_neighbor_none.txt"),
    "ping 10.0.1.3": read("junos_ping_noreply.txt"),
    "ping 10.88.0.1": read("junos_ping_unreachable.txt"),
    "ping 10.20.0.1 count 3 rapid wait 1 source 10.123.0.1": read("junos_ping_badsource.txt"),
    "ping 10.20.0.1": read("junos_ping.txt"),
    "ping 10.40.0.1": read("junos_ping_no_instance.txt"),
}


def junos_lab(**override):
    state = {**STATE, **override}
    return Lab(list(state.items()))


S = {"type": "bgp_session", "node": "j1"}
PX = {"type": "bgp_prefixes", "node": "j1"}
R = {"type": "route", "node": "j1"}
BR = {"type": "bgp_route", "node": "j1"}
PING = {"type": "ping", "node": "j1"}
SYNTAX = read("junos_error_syntax.txt")

MUST_FAIL = [
    ("session to an idle peer", {**S, "neighbor": "10.0.9.9"}, {}),
    ("session expected down but established", {**S, "neighbor": "10.0.1.2", "state": "down"}, {}),
    ("session to a peer that isn't configured", {**S, "neighbor": "10.9.9.9"}, {}),
    ("session with an unreadable answer", {**S, "neighbor": "10.0.1.2"}, {"show bgp neighbor instance master": SYNTAX}),
    ("session in an unknown instance", {**S, "neighbor": "10.0.1.2", "vrf": "NOPE"}, {}),
    ("prefixes over max", {**PX, "neighbor": "10.0.1.2", "max": 3}, {}),
    ("prefixes under min", {**PX, "neighbor": "10.0.1.2", "min": 5}, {}),
    ("prefixes exact 0 but 3", {**PX, "neighbor": "10.0.1.2", "exact": 0}, {}),
    ("ipv6 prefixes on a v4 session", {**PX, "neighbor": "10.0.1.2", "afi": "ipv6-unicast", "min": 1}, {}),
    ("prefixes of an idle peer read as 0", {**PX, "neighbor": "10.0.9.9", "max": 100}, {}),
    ("prefixes with an unreadable answer", {**PX, "neighbor": "10.0.1.2", "max": 100},
     {"show bgp neighbor instance master": "\n"}),
    ("leaked default absent", {**R, "prefix": "0.0.0.0/0", "present": False}, {}),
    ("leaked default absent via bgp", {**R, "prefix": "0.0.0.0/0", "present": False, "protocol": "bgp"}, {}),
    ("hidden next-hop route absent", {**R, "prefix": "10.31.0.0/24", "present": False}, {}),
    ("hidden next-hop route active", {**R, "prefix": "10.31.0.0/24"}, {}),
    ("route rejected by policy active", {**R, "prefix": "10.30.0.0/24"}, {}),
    ("backup bgp route active via static", {**R, "prefix": "10.20.0.0/24", "protocol": "static"}, {}),
    ("route absent in an unknown instance", {**R, "prefix": "10.88.0.0/24", "present": False, "vrf": "NOPE"}, {}),
    ("route absent with an unreadable answer", {**R, "prefix": "10.88.0.0/24", "present": False},
     {"10.88.0.0/24 exact table inet.0": SYNTAX}),
    ("bgp leak absent", {**BR, "prefix": "0.0.0.0/0", "present": False}, {}),
    ("bgp hidden next-hop path absent", {**BR, "prefix": "10.31.0.0/24", "present": False}, {}),
    ("bgp missing community", {**BR, "prefix": "10.20.0.0/24", "communities": ["65002:999"]}, {}),
    ("bgp carries community", {**BR, "prefix": "10.20.0.0/24", "without_communities": ["65002:100"]}, {}),
    ("bgp large community missing", {**BR, "prefix": "10.20.0.0/24", "communities": ["65002:1:3"]}, {}),
    ("bgp as-path of the backup", {**BR, "prefix": "10.20.0.0/24", "as_path": "65003 65003 65003"}, {}),
    ("bgp med", {**BR, "prefix": "10.20.0.0/24", "med": 0}, {}),
    ("bgp local-pref", {**BR, "prefix": "10.20.0.0/24", "local_pref": 200}, {}),
    ("bgp next hop of the backup", {**BR, "prefix": "10.20.0.0/24", "next_hop": "10.0.2.2"}, {}),
    ("bgp path with no best", {**BR, "prefix": "10.31.0.0/24"}, {}),
    ("bgp absent in an unknown instance", {**BR, "prefix": "10.88.0.0/24", "present": False, "vrf": "NOPE"}, {}),
    ("bgp absent with an unreadable answer", {**BR, "prefix": "10.88.0.0/24", "present": False},
     {"10.88.0.0/24 exact table inet.0": "{}"}),
    ("ping without replies", {**PING, "target": "10.0.1.3"}, {}),
    ("ping unreachable", {**PING, "target": "10.88.0.1"}, {}),
    ("ping from a bad source", {**PING, "target": "10.20.0.1", "source": "10.123.0.1"}, {}),
    ("ping must fail but replies", {**PING, "target": "10.20.0.1", "expect": "failure"}, {}),
    ("ping must fail in an unknown instance", {**PING, "target": "10.40.0.1", "vrf": "NOPE", "expect": "failure"}, {}),
    ("ping with an unreadable answer", {**PING, "target": "10.20.0.1"}, {"ping 10.20.0.1": SYNTAX}),
]


def verdict(raw: dict, override: dict) -> bool:
    check = _validate_check(0, dict(raw), 20)
    clock = FakeClock()
    driver = JunosDriver(junos_lab(**override), "j1")
    if is_post_convergence(check):
        return converge_then_hold(check, driver, hold=10, interval=3, clock=clock, sleep=clock.sleep).passed
    return run_check(check, driver, interval=3, clock=clock, sleep=clock.sleep).passed


@pytest.mark.parametrize("raw,override", [pytest.param(r, o, id=label) for label, r, o in MUST_FAIL])
def test_must_fail_on_junos(raw, override):
    assert verdict(raw, override) is False


@pytest.mark.parametrize("raw", [
    {**S, "neighbor": "10.0.1.2"}, {**S, "neighbor": "10.0.9.9", "state": "down"},
    {**PX, "neighbor": "10.0.1.2", "exact": 4}, {**PX, "neighbor": "2001:db8:1::2", "afi": "ipv6-unicast", "min": 1},
    {**R, "prefix": "0.0.0.0/0", "protocol": "static"}, {**R, "prefix": "10.30.0.0/24", "present": False},
    {**R, "prefix": "0.0.0.0/0", "protocol": "bgp", "active": False},
    {**BR, "prefix": "10.20.0.0/24", "communities": ["65002:100", "65002:1:2"], "as_path": "65002", "med": 50,
     "local_pref": 100, "next_hop": "10.0.1.2"},
    {**BR, "prefix": "10.30.0.0/24", "present": False}, {**BR, "prefix": "0.0.0.0/0", "as_path": "65002"},
    {**PING, "target": "10.20.0.1", "source": "10.255.0.1"}, {**PING, "target": "10.88.0.1", "expect": "failure"},
], ids=lambda r: f"{r['type']}-{r.get('neighbor') or r.get('prefix') or r.get('target')}")
def test_matrix_harness_can_pass(raw):
    """The same harness passes real healthy state, so the must-fail cases fail for the right reason."""
    assert verdict(raw, {}) is True


def _check_types():
    from netdryrun.checks import EVALUATORS
    from netdryrun.config import CHECK_TYPES
    return sorted(set(CHECK_TYPES) | set(EVALUATORS))


@pytest.mark.parametrize("ctype", _check_types())
def test_meta_every_check_type_has_junos_must_fail_cases(ctype):
    """A new check type without must-fail cases on Junos output turns CI red."""
    assert len([1 for _, raw, _ in MUST_FAIL if raw["type"] == ctype]) >= 2, ctype


# ---------------------------------------------------------------- what the driver refuses before deploying

def test_refused_before_deploying():
    from netdryrun.config import Check
    from netdryrun.drivers import check_supported
    from netdryrun.lab import LabError, Node

    class FakeLab:
        nodes = {"j1": Node("j1", "clab-t-j1", "juniper_cjunosevolved", "cjunosevolved:26.2R1.7-EVO")}

    with pytest.raises(DriverError, match="afi evpn is not supported on junos"):
        check_supported(FakeLab(), Check("bgp_prefixes", {"node": "j1", "neighbor": "10.0.0.2", "afi": "evpn"}, "c", 30))
    check_supported(FakeLab(), Check("bgp_prefixes", {"node": "j1", "neighbor": "10.0.0.2", "afi": "ipv6-unicast"},
                                     "c", 30))
    from netdryrun.lab import Lab as RealLab
    lab = RealLab.__new__(RealLab)
    lab.nodes = FakeLab.nodes
    with pytest.raises(LabError, match="cJunosEvolved"):
        lab._require_linux_links("j1")


@pytest.mark.parametrize("name,parse", [
    ("junos_error_not_ready.txt", lambda t: junos.parse_bgp_neighbors(t, "master")),
    ("junos_error_not_ready_route.txt", lambda t: junos.parse_routes(t, "0.0.0.0/0")),
    ("junos_error_not_ready_ping.txt", junos.parse_ping),
])
def test_not_ready_daemon_is_an_error(name, parse):
    """Captured while rpd was starting: an xnm:error (printed as invalid JSON) naming the cause. The ping
    one also carries ping-results; it is still an error, never a ping result."""
    with pytest.raises(DriverError, match="Junos error .*command-handler subsystem is not responding"):
        parse(read(name))
    if "ping" not in name:
        with pytest.raises(DriverError, match="routing subsystem is not running"):
            parse(read(name))


def test_ibgp_next_hop_is_the_protocol_next_hop():
    """iBGP: Junos shows the BGP NEXT_HOP (10.60.0.1) as the protocol next hop and the resolved forwarding
    next hop (10.0.1.2) under nh. next_hop is the BGP attribute, as on every other driver."""
    (p,) = junos.parse_bgp_paths(read("junos_route_ibgp.txt"), "10.50.0.0/24")
    assert (p.best, p.next_hop, p.neighbor, p.as_path, p.local_pref, p.communities) == \
        (True, "10.60.0.1", "10.0.1.2", "", 100, ["65001:50"])
    (q,) = junos.parse_bgp_paths(read("junos_route_ibgp_noexport.txt"), "10.51.0.0/24")
    assert q.local_pref == 200 and q.next_hop == "10.0.1.2" and q.communities == ["65001:51", "65535:65281"]  # no-export, canonical
    n = junos.parse_bgp_neighbors(read("junos_bgp_neighbor_ibgp.txt"), "master")
    assert n["10.0.1.2"].state == "established" and n["10.0.1.2"].prefixes == {"ipv4-unicast": 2}


# ---------------------------------------------------------------- advertisement interval and VRF list (0.4)

def test_adv_interval_is_the_platform_default_when_no_delay_is_configured():
    """Junos sends updates without delay unless `out-delay` is configured, and then prints no timer at all."""
    for name, instance in (("junos_bgp_neighbor.txt", "master"), ("junos_bgp_neighbor_red.txt", "RED"),
                           ("junos_bgp_neighbor_ibgp.txt", "master")):
        assert {n.adv_interval for n in junos.parse_bgp_neighbors(read(name), instance).values()} == {0.0}, name


def test_configured_out_delay_is_read():
    """Captured live with `out-delay 10` on the IPv4 group only: Junos adds `outbound-timer` (seconds)."""
    n = junos.parse_bgp_neighbors(read("junos_bgp_neighbor_outdelay.txt"), "master")
    assert n["10.0.100.2"].adv_interval == 10.0 and n["2001:db8:100::2"].adv_interval == 0.0


def _outdelay_doc(edit):
    d = json.loads(read("junos_bgp_neighbor_outdelay.txt"))
    edit(d["bgp-information"][0]["bgp-peer"][0]["bgp-option-information"][0])
    return _obj(d)


@pytest.mark.parametrize("edit", [
    lambda o: o.update({"outbound-timer": [{"data": "ten"}]}),
    lambda o: o.update({"outbound-timer": [{"data": "-1"}]}),
    lambda o: o.update({"outbound-timer": [{"data": "10"}, {"data": "20"}]}),
    lambda o: o.update({"out-delay": [{"data": "30"}]}),                     # a delay under another name
    lambda o: o["bgp-options"][0].update({"data": "PeerAS Refresh OutDelay"}),
], ids=["not-a-number", "negative", "twice", "other-name", "option-flag"])
def test_an_unreadable_delay_is_never_read_as_none(edit):
    """A delay Junos reports in a shape this driver doesn't know is an error, never 0: a 0 would keep settle
    and hold short while a leak can still be on its way."""
    with pytest.raises(DriverError, match="unexpected output|advertisement delay"):
        junos.parse_bgp_neighbors(_outdelay_doc(edit), "master")


def test_vrfs_lists_vrf_instances_only():
    # captured live: master, CUST (vrf), mgmt_junos (virtual-router: the management instance), two private ones
    assert junos.parse_vrfs(read("junos_instances.txt")) == ["CUST"]
    assert junos.parse_vrfs(read("junos_instance_red.txt")) == ["RED"]
    assert junos.parse_vrfs(read("junos_instance_master.txt")) == []
    with pytest.raises(DriverError):
        junos.parse_vrfs(read("junos_error_syntax.txt"))
    lab = Lab([("show route instance", read("junos_instances.txt"))])
    obs = JunosDriver(lab, "j1").vrfs()
    assert obs.value == ["CUST"] and lab.calls == ["cli -c 'show route instance | display json | no-more'"]


def test_vrf_captures_from_the_live_check_run():
    """The VRF session the live `netdryrun check` read as down, and ping inside the VRF (3/3)."""
    n = junos.parse_bgp_neighbors(read("junos_bgp_neighbor_vrf_idle.txt"), "CUST")
    assert n["10.0.199.2"].state != "established" and n["10.0.199.2"].prefixes == {}
    assert junos.parse_ping(read("junos_ping_vrf_local.txt")) == (3, 3)


# ---------------------------------------------------------------- the remaining error branches (coverage gate)

@pytest.mark.parametrize("edit", [
    lambda p: p.update({"peer-state": [{"data": 5}]}),          # a leaf whose text isn't text
    lambda p: p.update({"peer-state": [{"data": "   "}]}),      # a blank state
], ids=["leaf-not-text", "blank-state"])
def test_neighbor_leaf_shapes(edit):
    with pytest.raises(DriverError, match="unexpected output"):
        junos.parse_bgp_neighbors(_peer_doc(edit), "master")


def test_route_table_error_with_another_message_is_an_error_not_a_missing_table():
    text = _obj({"route-table-error": [{"route-table-error-str": [{"data": "rpd is busy"}]}]})
    with pytest.raises(DriverError, match="rpd is busy") as e:
        junos.parse_routes(text, "10.0.0.0/24")
    assert not isinstance(e.value, junos.NoSuchTable)


def test_route_entry_with_an_empty_protocol_name():
    d = json.loads(read("junos_route_paths.txt"))
    d["route-information"][0]["route-table"][0]["rt"][0]["rt-entry"][0]["protocol-name"] = [{"data": ""}]
    with pytest.raises(DriverError, match="without protocol-name"):
        junos.parse_routes(_obj(d), "10.20.0.0/24")


def test_community_that_isnt_text():
    d = json.loads(read("junos_route_paths.txt"))
    d["route-information"][0]["route-table"][0]["rt"][0]["rt-entry"][0]["communities"][0]["community"][0] = {"data": 7}
    with pytest.raises(DriverError, match="community"):
        junos.parse_bgp_paths(_obj(d), "10.20.0.0/24")


def test_ibgp_next_hop_falls_back_to_the_forwarding_one():
    """A protocol next hop without an address (never seen live): the selected forwarding next hop, never None."""
    d = json.loads(read("junos_route_ibgp.txt"))
    d["route-information"][0]["route-table"][0]["rt"][0]["rt-entry"][0]["protocol-nh"][0].pop("to")
    (p,) = junos.parse_bgp_paths(_obj(d), "10.50.0.0/24")
    assert p.next_hop == "10.0.1.2"


def test_a_command_with_a_quote_never_reaches_the_vm():
    """Every command is built from validated names and addresses; this is the last guard in front of the
    single-quoted string the VM's shell reads."""
    lab = Lab([("", "{}")])
    with pytest.raises(DriverError, match="quote"):
        JunosDriver(lab, "j1")._cli("show route 'x", [])
    assert lab.calls == []


def test_all_routes_through_the_driver():
    lab = Lab([("show route table inet.0", read("junos_route_table.txt"))])
    obs = JunosDriver(lab, "j1").all_routes()
    assert ("0.0.0.0/0", "static", True) in {(r.prefix, r.protocol, r.active) for r in obs.value}
    assert lab.calls == ["cli -c 'show route table inet.0 | display json | no-more'"]
    # an empty table in a VRF is trusted only once the instance is confirmed
    lab = Lab([("show route instance RED", read("junos_instance_red.txt")),
               ("show route table RED.inet.0", read("junos_route_empty.txt"))])
    assert JunosDriver(lab, "j1").all_routes("RED").value == [] and len(lab.calls) == 2
    lab = Lab([("show route instance NOPE", read("junos_instance_none.txt")),
               ("show route table NOPE.inet.0", read("junos_route_empty.txt"))])
    with pytest.raises(NoSuchInstance):
        JunosDriver(lab, "j1").all_routes("NOPE")


def test_a_path_without_any_next_hop_reads_as_unknown():
    """No nh and no protocol-nh: next_hop is None ("?"), which never equals an expected next hop."""
    d = json.loads(read("junos_route_paths.txt"))
    e = d["route-information"][0]["route-table"][0]["rt"][0]["rt-entry"][0]
    e.pop("nh")
    e.pop("protocol-nh", None)
    best = junos.parse_bgp_paths(_obj(d), "10.20.0.0/24")[0]
    assert best.best and best.next_hop is None
