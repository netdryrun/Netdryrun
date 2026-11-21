"""SR Linux: EVPN IP-prefix (type-5) routes imported into an ip-vrf are BGP paths there (red team RT-0058, oracle
FP-043-SRLEVPNVRF, GHSA-ggcf-664f-c9ff case 2).

Built on the oracle's live captures (SR Linux 26.7.2, tests/fixtures/srl2672_fp043_*). Device output that the captures
don't hold is built here and marked DERIVED, each from a named capture.
"""
import copy
import json
from pathlib import Path

import pytest

from netdryrun.checks import run_check
from netdryrun.config import _validate_check
from netdryrun.drivers import srlinux
from netdryrun.drivers.base import DriverError, Route
from netdryrun.drivers.srlinux import SrlDriver
from netdryrun.lab import ExecResult

FX = Path(__file__).resolve().parent / "fixtures"
PREFIX = "10.99.0.0/24"
SR = ["sr_cli", "--output-format", "json"]
RIB = (f"info from state /network-instance ipvrf bgp-rib afi-safi ipv4-unicast ipv4-unicast local-rib route {PREFIX} "
       "neighbor * origin-protocol * path-id *")
TABLE = (f"info from state /network-instance ipvrf route-table ipv4-unicast route {PREFIX} "
         "id * route-type * route-owner * origin-network-instance *")
EVPN = "info from state /network-instance default bgp-rib afi-safi evpn evpn local-rib"
OPER = "info from state /network-instance ipvrf oper-state"


def fx(name: str) -> str:
    return (FX / name).read_text(encoding="utf-8")


def J(d) -> str:
    return json.dumps(d, indent=2)


def evpn(tag: str) -> dict:
    return json.loads(fx(f"srl2672_fp043_{tag}_leaf1_default_evpn_local_rib.json"))


def attr_set(tag: str, index: str) -> str:
    """DERIVED: one attr-set as `... attr-sets attr-set N` answers it (srl2672_fp043_present_leaf1_default_attr_set_6.json
    is that answer for 6), taken from the captured `... attr-sets` listing of the same state."""
    sets = json.loads(fx(f"srl2672_fp043_{tag}_leaf1_default_bgp_rib_attr_sets.json"))["attr-set"]
    [a] = [s for s in sets if s["index"] == index]
    return J(a)


class Node:
    """leaf1: answers the commands in `answers` (sr_cli JSON); any other command fails, rc 1."""

    def __init__(self, answers: dict):
        self.answers, self.asked = answers, []

    def exec(self, node, cmd, timeout=60, input=None):
        self.asked.append(cmd[3] if cmd[:3] == SR else " ".join(cmd))
        if cmd[:3] == SR and len(cmd) == 4 and cmd[3] in self.answers:
            return ExecResult(cmd, 0, self.answers[cmd[3]], "")
        return ExecResult(cmd, 1, "", f"not answered: {' '.join(cmd)}")


def state(tag: str, **over) -> dict:
    p = f"srl2672_fp043_{tag}_leaf1_"
    out = {RIB: fx(p + "ipvrf_bgp_rib_route.json"), TABLE: fx(p + "ipvrf_route_table_route.json"),
           EVPN: fx(p + "default_evpn_local_rib.json"), OPER: fx(p + "ipvrf_oper_state.json")}
    for a in ("6", "9"):
        try:
            out[f"info from state /network-instance default bgp-rib attr-sets attr-set {a}"] = attr_set(tag, a)
        except ValueError:
            pass
    out.update(over)
    return out


class Clock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t

    def sleep(self, s):
        self.t += max(s, 0.5)


def run(answers: dict, **raw):
    c = Clock()
    chk = _validate_check(0, {"node": "leaf1", "vrf": "ipvrf", "prefix": PREFIX, "type": "bgp_route", **raw}, 20)
    return run_check(chk, SrlDriver(Node(answers), "leaf1"), clock=c, sleep=c.sleep)


# ------------------------------------------------------------------------------------------- the EVPN RIB reader

def test_the_imported_path_is_read_from_the_evpn_rib():
    [row] = srlinux.parse_evpn_imports(fx("srl2672_fp043_present_leaf1_default_evpn_local_rib.json"), PREFIX, "ipvrf")
    assert (row["neighbor"], row["route-distinguisher"], row["attr-id"]) == ("2.2.2.2", "2.2.2.2:99", "6")


def test_imported_network_instances_decides_not_the_prefix():
    text = fx("srl2672_fp043_present_leaf1_default_evpn_local_rib.json")
    assert srlinux.parse_evpn_imports(text, "10.98.0.0/24", "ipvrf") == []          # imported into ipvrf2 only
    assert len(srlinux.parse_evpn_imports(text, "10.98.0.0/24", "ipvrf2")) == 1
    assert srlinux.parse_evpn_imports(text, "10.99.0.0/25", "ipvrf") == []           # exact prefix only
    assert srlinux.parse_evpn_imports(text, "10.99.0.1/32", "ipvrf")[0]["ip-prefix-length"] == 32


def test_the_nodes_own_type5_routes_are_never_received():
    """Design B: leaf1 advertises 10.77.0.0/24 (learned from ce1) and 10.1.0.0/30 as its own type-5 routes, neighbor
    0.0.0.0, no imported-network-instances."""
    text = fx("srl2672_fp043_pece2_leaf1_default_evpn_local_rib.json")
    assert srlinux.parse_evpn_imports(text, "10.77.0.0/24", "ipvrf") == []
    assert srlinux.parse_evpn_imports(text, "10.1.0.0/30", "ipvrf") == []


def test_absent_states_have_no_imported_path():
    for tag in ("absent", "pece2absent"):
        assert srlinux.parse_evpn_imports(fx(f"srl2672_fp043_{tag}_leaf1_default_evpn_local_rib.json"), PREFIX,
                                          "ipvrf") == []
    assert srlinux.parse_evpn_imports("{}", PREFIX, "ipvrf") == []


def _one_row(**change) -> str:
    """DERIVED from srl2672_fp043_present_leaf1_default_evpn_local_rib.json: its 10.99.0.0/24 row, changed."""
    d = evpn("present")
    [row] = [r for r in d["ip-prefix-route"] if r["ip-prefix"] == PREFIX]
    for k, v in change.items():
        if v is None:
            row.pop(k.replace("_", "-"), None)
        else:
            row[k.replace("_", "-")] = v
    d["ip-prefix-route"] = [row]
    return J(d)


def test_a_received_path_imported_nowhere_is_refused():
    """A path from a peer that no network-instance imported (invalid, or for a route-target no ip-vrf here imports)
    may be one for ipvrf: unknown, never "absent"."""
    with pytest.raises(DriverError, match="imported into no network-instance"):
        srlinux.parse_evpn_imports(_one_row(imported_network_instances=None), PREFIX, "ipvrf")
    with pytest.raises(DriverError, match="imported into no network-instance"):
        srlinux.parse_evpn_imports(_one_row(imported_network_instances=[]), PREFIX, "ipvrf")
    # the same row from the node itself is its own route
    assert srlinux.parse_evpn_imports(_one_row(imported_network_instances=None, neighbor="0.0.0.0"), PREFIX,
                                      "ipvrf") == []


@pytest.mark.parametrize("change", [
    {"imported_network_instances": "ipvrf"}, {"imported_network_instances": [1]}, {"imported_network_instances": [""]},
    {"neighbor": None}, {"neighbor": "leaf2"}, {"ip_prefix": None}, {"ip_prefix": "x"},
    {"stale_route": None}, {"stale_route": "false"}, {"best_route": None}, {"best_route": "true"},
])
def test_an_evpn_row_of_unknown_shape_is_an_error(change):
    with pytest.raises(DriverError):
        srlinux.parse_evpn_imports(_one_row(**change), PREFIX, "ipvrf")


def test_a_stale_imported_path_is_not_settled():
    with pytest.raises(DriverError, match="not settled"):
        srlinux.parse_evpn_imports(_one_row(stale_route=True), PREFIX, "ipvrf")


@pytest.mark.parametrize("text", [
    J({"ip-prefix-routes": []}), J({"ip-prefix-route": {}}), J({"ip-prefix-route": ["x"]}), J([]), "", "not json",
    J({"ip-prefix-route": [], "local-rib": {}}),
])
def test_an_evpn_rib_of_unknown_shape_is_an_error(text):
    with pytest.raises(DriverError):
        srlinux.parse_evpn_imports(text, PREFIX, "ipvrf")


def test_other_evpn_route_lists_are_known():
    d = evpn("present")
    d.update({"mac-ip-route": [], "imet-route": [], "ethernet-ad-route": [], "ethernet-segment-route": []})
    assert len(srlinux.parse_evpn_imports(J(d), PREFIX, "ipvrf")) == 1


# ------------------------------------------------------------------------------------------- attributes

def test_an_evpn_path_reads_its_attributes_from_the_default_instance():
    row = {"attr-id": "6", "neighbor": "2.2.2.2", "ip-prefix": PREFIX}
    p = srlinux.parse_evpn_attr_set(fx("srl2672_fp043_present_leaf1_default_attr_set_6.json"), row, True)
    assert (p.best, p.next_hop, p.local_pref, p.med, p.as_path, p.neighbor) == (True, "2.2.2.2", 100, None, None, "2.2.2.2")
    assert p.communities == [] and p.large_communities == [] and not p.local_candidate


def _attr6(**change) -> str:
    a = json.loads(fx("srl2672_fp043_present_leaf1_default_attr_set_6.json"))
    a.update(change)
    return J(a)


def test_an_evpn_path_keeps_its_standard_communities():
    """DERIVED: attr-set 6 with a standard and a large community beside the extended ones."""
    comms = copy.deepcopy(json.loads(_attr6())["communities"])
    comms.update({"community": ["65000:7"], "large-community": ["1:2:3"]})
    p = srlinux.parse_evpn_attr_set(_attr6(communities=comms), {"attr-id": "6"}, True)
    assert p.communities == ["65000:7"] and p.large_communities == ["1:2:3"]


@pytest.mark.parametrize("attrs", [
    _attr6(communities={}), _attr6(communities={"ext-community": "target:65000:99"}),
    _attr6(communities={"other": ["x"]}), _attr6(communities=[]), _attr6(index="7"), _attr6(extra=1), "[]",
])
def test_an_evpn_attr_set_of_unknown_shape_is_an_error(attrs):
    with pytest.raises(DriverError):
        srlinux.parse_evpn_attr_set(attrs, {"attr-id": "6"}, True)


def test_a_missing_evpn_attr_set_is_an_error():
    with pytest.raises(DriverError, match="not found"):
        srlinux.parse_evpn_attr_set("{}", {"attr-id": "6"}, True)


# ------------------------------------------------------------------------------------------- bgp_paths and checks

def test_design_a_the_imported_path_is_a_bgp_path():
    node = Node(state("present"))
    [p] = SrlDriver(node, "leaf1").bgp_paths(PREFIX, "ipvrf").value
    assert (p.best, p.next_hop, p.local_pref, p.neighbor, p.local_candidate) == (True, "2.2.2.2", 100, "2.2.2.2", False)
    assert node.asked == [RIB, EVPN, TABLE, "info from state /network-instance default bgp-rib attr-sets attr-set 6"]


def test_design_b_the_bgp_evpn_row_is_the_imported_path_not_the_nodes_own():
    """Design B (srl2672_fp043_pece2_*): ipvrf's bgp-rib lists the route once, neighbor 0.0.0.0, origin-protocol
    bgp-evpn. The path reported is the EVPN one (from 2.2.2.2, its attr-set 9 in default), never an own route."""
    [p] = SrlDriver(Node(state("pece2")), "leaf1").bgp_paths(PREFIX, "ipvrf").value
    assert (p.best, p.next_hop, p.neighbor, p.local_candidate) == (True, "2.2.2.2", "2.2.2.2", False)


@pytest.mark.parametrize("tag", ["present", "pece2"])
def test_present_false_fails_and_a_positive_check_passes_while_imported(tag):
    r = run(state(tag), present=False)
    assert not r.passed and "unexpectedly in the BGP table" in r.detail, r.detail
    r = run(state(tag), next_hop="2.2.2.2", local_pref=100)
    assert r.passed, r.detail


@pytest.mark.parametrize("tag", ["absent", "pece2absent"])
def test_present_false_passes_where_the_route_is_gone(tag):
    r = run(state(tag), present=False)
    assert r.passed and r.detail == "no BGP path", r.detail


def _pece2_rib(**change) -> str:
    """DERIVED from srl2672_fp043_pece2_leaf1_ipvrf_bgp_rib_route.json: its bgp-evpn row, changed."""
    d = json.loads(fx("srl2672_fp043_pece2_leaf1_ipvrf_bgp_rib_route.json"))
    d["route"][0].update(change)
    return J(d)


def test_design_b_the_ip_vrf_choice_decides_best():
    """DERIVED: ipvrf prefers another path (its bgp-evpn row is not best): the EVPN path is not the best there."""
    paths = SrlDriver(Node(state("pece2", **{RIB: _pece2_rib(**{"best-route": False})})), "leaf1").bgp_paths(
        PREFIX, "ipvrf").value
    assert [p.best for p in paths] == [False]
    r = run(state("pece2", **{RIB: _pece2_rib(**{"best-route": False})}), next_hop="2.2.2.2")
    assert not r.passed and "none is best" in r.detail, r.detail


def test_a_bgp_evpn_row_without_an_imported_evpn_path_is_an_error():
    """DERIVED: the pece2 bgp-rib row beside the pece2absent EVPN RIB (no 10.99.0.0/24): two answers that disagree."""
    answers = state("pece2", **{EVPN: fx("srl2672_fp043_pece2absent_leaf1_default_evpn_local_rib.json")})
    with pytest.raises(DriverError, match="no IP-prefix route for it imported there"):
        SrlDriver(Node(answers), "leaf1").bgp_paths(PREFIX, "ipvrf")
    assert not run(answers, present=False).passed


def test_a_bgp_evpn_route_installed_without_an_imported_evpn_path_is_an_error():
    """DERIVED: design A's route table (bgp-evpn, active) beside the absent EVPN RIB."""
    answers = state("present", **{EVPN: fx("srl2672_fp043_absent_leaf1_default_evpn_local_rib.json")})
    with pytest.raises(DriverError, match="installed from bgp-evpn"):
        SrlDriver(Node(answers), "leaf1").bgp_paths(PREFIX, "ipvrf")


def test_bgp_vpn_is_a_rib_the_driver_does_not_read():
    """DERIVED: a bgp-vpn row in ipvrf's bgp-rib, or a bgp-vpn route in its table: never "no path"."""
    answers = state("pece2", **{RIB: _pece2_rib(**{"origin-protocol": "bgp-vpn"})})
    with pytest.raises(DriverError, match="bgp-vpn"):
        SrlDriver(Node(answers), "leaf1").bgp_paths(PREFIX, "ipvrf")
    table = json.loads(fx("srl2672_fp043_present_leaf1_ipvrf_route_table_route.json"))
    table["route"][0]["route-type"] = "bgp-vpn"
    answers = state("absent", **{TABLE: J(table)})
    with pytest.raises(DriverError, match="bgp-vpn"):
        SrlDriver(Node(answers), "leaf1").bgp_paths(PREFIX, "ipvrf")
    assert not run(answers, present=False).passed


def test_the_default_instance_reads_the_evpn_rib_only_for_a_bgp_evpn_row():
    rib = (f"info from state /network-instance default bgp-rib afi-safi ipv4-unicast ipv4-unicast local-rib route "
           f"{PREFIX} neighbor * origin-protocol * path-id *")
    node = Node({rib: "{}"})
    assert SrlDriver(node, "leaf1").bgp_paths(PREFIX).value == [] and node.asked == [rib]
    # DERIVED: the pece2 bgp-evpn row in default's bgp-rib, with nothing imported into default
    node = Node({rib: _pece2_rib(), EVPN: fx("srl2672_fp043_pece2_leaf1_default_evpn_local_rib.json")})
    with pytest.raises(DriverError, match="no IP-prefix route for it imported there"):
        SrlDriver(node, "leaf1").bgp_paths(PREFIX)


# ------------------------------------------------------------------------------------------- routes

def test_routes_sees_an_imported_evpn_path_that_is_not_installed():
    """DERIVED: design A with a static in ipvrf winning the route table (route-type static, active): the imported
    EVPN path is still a BGP route there, so `route protocol: bgp(-evpn) present: false` fails."""
    table = json.loads(fx("srl2672_fp043_present_leaf1_ipvrf_route_table_route.json"))
    table["route"][0]["route-type"] = "static"
    answers = state("present", **{TABLE: J(table)})
    routes = SrlDriver(Node(answers), "leaf1").routes(PREFIX, "ipvrf").value
    assert routes == [Route(PREFIX, "static", True), Route(PREFIX, "bgp-evpn", False)]
    for proto in ("bgp", "bgp-evpn"):
        r = run(answers, type="route", protocol=proto, present=False)
        assert not r.passed and "not selected" in r.detail, r.detail


@pytest.mark.parametrize("tag,present", [("present", True), ("pece2", True), ("absent", False), ("pece2absent", False)])
def test_route_protocol_bgp_evpn_agrees_with_bgp_route(tag, present):
    r = run(state(tag), type="route", protocol="bgp-evpn", present=False)
    assert r.passed is not present, r.detail


def test_parse_routes_lists_a_bgp_evpn_row_beside_an_installed_route_of_another_bgp_kind():
    table = J({"route": [{"ipv4-prefix": PREFIX, "route-type": "bgp", "active": True,
                          "fib-programming": {"suppressed": False, "pending-operation-type": "none",
                                              "last-failed-operation-type": "none"}}]})
    rib = fx("srl2672_fp043_pece2_leaf1_ipvrf_bgp_rib_route.json")
    assert srlinux.parse_routes(table, PREFIX, rib) == [Route(PREFIX, "bgp", True), Route(PREFIX, "bgp-evpn", False)]


# ------------------------------------------------------------------------------------------- adversary on 02a0060

def test_a_route_imported_into_several_ip_vrfs_counts_in_each():
    """DERIVED: the 10.99.0.0/24 row imported into two ip-vrfs, in either order (adversary M4)."""
    for into in (["ipvrf2", "ipvrf"], ["ipvrf", "ipvrf2"]):
        text = _one_row(imported_network_instances=into)
        assert len(srlinux.parse_evpn_imports(text, PREFIX, "ipvrf")) == 1
        assert len(srlinux.parse_evpn_imports(text, PREFIX, "ipvrf2")) == 1
        assert srlinux.parse_evpn_imports(text, PREFIX, "ipvrf3") == []


def test_the_nodes_own_type5_route_never_counts_even_when_it_names_the_vrf():
    """DERIVED: an own row (neighbor 0.0.0.0) that lists ipvrf (adversary M35): still the node's own route."""
    assert srlinux.parse_evpn_imports(_one_row(neighbor="0.0.0.0", imported_network_instances=["ipvrf"]), PREFIX,
                                      "ipvrf") == []
    assert srlinux.parse_evpn_imports(_one_row(neighbor="::", imported_network_instances=["ipvrf"]), PREFIX,
                                      "ipvrf") == []


def test_an_unknown_community_kind_beside_the_extended_ones_is_an_error():
    """DERIVED: attr-set 6's communities (ext-community only) plus a kind the driver doesn't know (adversary M19c):
    read as "no communities", `without_communities` would pass."""
    comms = copy.deepcopy(json.loads(_attr6())["communities"])
    comms["future-community"] = ["x:1"]
    with pytest.raises(DriverError):
        srlinux.parse_evpn_attr_set(_attr6(communities=comms), {"attr-id": "6"}, True)


def _no_lp() -> str:
    a = json.loads(_attr6())
    a.pop("local-pref")
    return J(a)


ATTR6 = "info from state /network-instance default bgp-rib attr-sets attr-set 6"
NEIGHBOR_LP = "info from state /network-instance default protocols bgp neighbor 2.2.2.2 local-preference"


@pytest.mark.parametrize("answer,want", [(J({"local-preference": 150}), 150), ("{}", None)])
def test_an_evpn_attr_set_without_local_pref_takes_the_neighbors(answer, want):
    """DERIVED: attr-set 6 without local-pref (adversary M20, M20b): the default instance's neighbor 2.2.2.2 answers
    its local-preference, or nothing (unknown, never a guessed 100)."""
    node = Node(state("present", **{ATTR6: _no_lp(), NEIGHBOR_LP: answer}))
    [p] = SrlDriver(node, "leaf1").bgp_paths(PREFIX, "ipvrf").value
    assert p.local_pref == want and NEIGHBOR_LP in node.asked


def test_an_unreadable_neighbor_local_pref_is_an_error():
    node = Node(state("present", **{ATTR6: _no_lp()}))   # the neighbor query isn't answered
    with pytest.raises(DriverError):
        SrlDriver(node, "leaf1").bgp_paths(PREFIX, "ipvrf")


def test_no_neighbor_is_asked_for_a_path_from_an_unspecified_address():
    """adversary M38: the fallback never asks about 0.0.0.0 (there is no such neighbor)."""
    node = Node({ATTR6: _no_lp()})
    p = SrlDriver(node, "leaf1")._read_evpn_path({"attr-id": "6", "neighbor": "0.0.0.0", "ip-prefix": PREFIX}, True, [])
    assert p.local_pref is None and node.asked == [ATTR6]


@pytest.mark.parametrize("attr_id", ["6 ; rm", "x", "", None, "-1"])
def test_an_evpn_attr_id_that_is_not_a_number_is_refused(attr_id):
    """DERIVED (adversary M21): the attr-id goes back into a CLI command; only digits are read."""
    d = evpn("present")
    [row] = [r for r in d["ip-prefix-route"] if r["ip-prefix"] == PREFIX]
    row["attr-id"] = attr_id
    node = Node(state("present", **{EVPN: J(d)}))
    with pytest.raises(DriverError, match="attr-id"):
        SrlDriver(node, "leaf1").bgp_paths(PREFIX, "ipvrf")
    assert not any("attr-set" in c for c in node.asked)


# ------------------------------------------------------------------------------------------- two PEs, one prefix
# Live, SR Linux 26.7.2 (srl2672_fp043_twope_*): leaf2 and leaf3 both advertise 10.77.0.0/24 into ipvrf (design A, RDs
# 2.2.2.2:99 and 3.3.3.3:99) and 10.66.0.0/24 into ipvrfb (design B, PE-CE BGP to ce1). In state lp200 leaf1 sets
# local-pref 200 on what it learns from 3.3.3.3: both paths are best-route and imported, and each ip-vrf forwards to
# 3.3.3.3 only. 02a0060 reported the first path in EVPN RIB order (2.2.2.2, local-pref 100), so `next_hop: 2.2.2.2` and
# `local_pref: 100` passed (adversary BLOCKER 1 for design B, MAJOR 2 for design A). In state ecmp the policy is gone and
# each ip-vrf forwards to both VTEPs; in state one leaf3 withdraws, in state absent leaf2 too.

TWO = {"ipvrf": "10.77.0.0/24", "ipvrfb": "10.66.0.0/24"}


def _command(vrf: str, rest: str) -> str | None:
    """The command a twope capture file answers (fx043 capture log), from the rest of its name."""
    prefix = TWO[vrf]
    base = f"info from state /network-instance {vrf} "
    if rest == "bgp_rib_route":
        return (f"{base}bgp-rib afi-safi ipv4-unicast ipv4-unicast local-rib route {prefix} neighbor * origin-protocol * "
                "path-id *")
    if rest == "route_table_route":
        return f"{base}route-table ipv4-unicast route {prefix} id * route-type * route-owner * origin-network-instance *"
    if rest == "oper_state":
        return f"{base}oper-state"
    for name, what in (("nhg_", "route-table next-hop-group "), ("nh_", "route-table next-hop "),
                       ("attr_set_", "bgp-rib attr-sets attr-set ")):
        if rest.startswith(name):
            return base + what + rest[len(name):]
    return None


def two_pe(vrf: str, tag: str = "lp200", **over) -> dict:
    """leaf1's captured answers in state `tag`, for checks on `vrf`."""
    out = {}
    lead = f"srl2672_fp043_twope_{tag}_leaf1_"
    for f in sorted(FX.glob(lead + "*.json")):
        rest = f.stem[len(lead):]
        if rest == "default_evpn_local_rib":
            out[EVPN] = fx(f.name)
        elif rest.startswith("default_attr_set_"):
            out[f"info from state /network-instance default bgp-rib attr-sets attr-set {rest[17:]}"] = fx(f.name)
        elif rest.startswith(vrf + "_") and (cmd := _command(vrf, rest[len(vrf) + 1:])):
            out[cmd] = fx(f.name)
    out.update(over)
    return out


def key(vrf: str, what: str, tag: str = "lp200") -> str:
    """The command of one of `vrf`'s captures in state `tag`: table, rib, nhg, nh, attr."""
    rest = {"table": "route_table_route", "rib": "bgp_rib_route"}.get(what)
    if rest is None:
        lead = f"srl2672_fp043_twope_{tag}_leaf1_{vrf}_{what.replace('attr', 'attr_set')}_"
        [f] = FX.glob(lead + "*.json")
        rest = f.stem[len(f"srl2672_fp043_twope_{tag}_leaf1_{vrf}_"):]
    return _command(vrf, rest)


def run2(vrf: str, answers: dict, **raw):
    c = Clock()
    chk = _validate_check(0, {"node": "leaf1", "vrf": vrf, "prefix": TWO[vrf], "type": "bgp_route", **raw}, 20)
    return run_check(chk, SrlDriver(Node(answers), "leaf1"), clock=c, sleep=c.sleep)


def paths2(vrf: str, answers: dict):
    return SrlDriver(Node(answers), "leaf1").bgp_paths(TWO[vrf], vrf).value


@pytest.mark.parametrize("vrf", ["ipvrf", "ipvrfb"])
def test_two_pes_the_best_path_is_the_one_the_ip_vrf_forwards_with(vrf):
    assert [(p.best, p.next_hop, p.local_pref, p.local_candidate) for p in paths2(vrf, two_pe(vrf))] == \
        [(True, "3.3.3.3", 200, False), (False, "2.2.2.2", 100, False)]


@pytest.mark.parametrize("vrf", ["ipvrf", "ipvrfb"])
@pytest.mark.parametrize("raw", [{"next_hop": "2.2.2.2"}, {"local_pref": 100}, {"present": False}])
def test_two_pes_a_check_on_the_path_the_ip_vrf_does_not_use_fails(vrf, raw):
    """Live false passes on 02a0060: `next_hop: 2.2.2.2` and `local_pref: 100` passed."""
    r = run2(vrf, two_pe(vrf), **raw)
    assert not r.passed, r.detail


@pytest.mark.parametrize("vrf", ["ipvrf", "ipvrfb"])
def test_two_pes_a_check_on_the_path_the_ip_vrf_uses_passes(vrf):
    """Failed on 02a0060: it judged 2.2.2.2 at local-pref 100."""
    r = run2(vrf, two_pe(vrf), next_hop="3.3.3.3", local_pref=200)
    assert r.passed, r.detail


@pytest.mark.parametrize("vrf", ["ipvrf", "ipvrfb"])
def test_two_pes_the_evpn_rib_order_does_not_decide(vrf):
    """DERIVED: the captured EVPN RIB with its rows reversed (adversary M28, M32)."""
    d = json.loads(two_pe(vrf)[EVPN])
    d["ip-prefix-route"].reverse()
    assert [(p.best, p.next_hop) for p in paths2(vrf, two_pe(vrf, **{EVPN: J(d)}))] == \
        [(True, "3.3.3.3"), (False, "2.2.2.2")]


@pytest.mark.parametrize("vrf", ["ipvrf", "ipvrfb"])
def test_two_pes_ecmp_over_both_is_an_error_never_the_first(vrf):
    """Live, state ecmp: the ip-vrf forwards to both VTEPs."""
    answers = two_pe(vrf, "ecmp")
    with pytest.raises(DriverError, match="not exactly one of them"):
        paths2(vrf, answers)
    for raw in ({"next_hop": "2.2.2.2"}, {"next_hop": "3.3.3.3"}, {"present": False}):
        assert not run2(vrf, answers, **raw).passed, raw


@pytest.mark.parametrize("vrf", ["ipvrf", "ipvrfb"])
def test_one_pe_left_its_path_is_best(vrf):
    """Live, state one: leaf3 withdrew, one candidate; the ip-vrf's next hops aren't needed."""
    answers = two_pe(vrf, "one")
    assert [(p.best, p.next_hop, p.local_pref) for p in paths2(vrf, answers)] == [(True, "2.2.2.2", 100)]
    assert run2(vrf, answers, next_hop="2.2.2.2").passed
    assert not run2(vrf, answers, present=False).passed


@pytest.mark.parametrize("vrf", ["ipvrf", "ipvrfb"])
def test_both_pes_gone_present_false_passes(vrf):
    """Live, state absent."""
    answers = two_pe(vrf, "absent")
    assert paths2(vrf, answers) == []
    assert run2(vrf, answers, present=False).passed


def _edit(vrf: str, what: str, change) -> dict:
    """DERIVED: one lp200 capture of `vrf`, changed."""
    k = key(vrf, what)
    d = json.loads(two_pe(vrf)[k])
    change(d)
    return two_pe(vrf, **{k: J(d)})


def _route(**c):
    return lambda d: d["route"][0].update(c)


@pytest.mark.parametrize("vrf", ["ipvrf", "ipvrfb"])
@pytest.mark.parametrize("what,change,match", [
    # the ip-vrf forwards with a static, or holds the EVPN route out of the FIB: nothing says which path is best
    ("table", _route(**{"route-type": "static"}), "forwards with no EVPN route"),
    ("table", _route(active=False), "forwards with no EVPN route"),
    ("table", lambda d: d["route"].append(dict(d["route"][0], id=1)), "2 active bgp-evpn routes"),
    # the VTEP it forwards to is neither path's next hop
    ("nh", lambda d: d.update({"ip-address": "4.4.4.4"}), "not exactly one of them"),
    # answers of unknown shape
    ("nh", lambda d: d.update({"ip-address": "0.0.0.0"}), "unexpected output"),
    ("nh", lambda d: d.update({"ip-address": "x"}), "unexpected output"),
    ("nh", lambda d: d.update({"index": "1"}), "unexpected output"),
    ("nh", lambda d: d.clear(), "unexpected output"),
    ("nhg", lambda d: d.clear(), "unexpected output"),
    ("nhg", lambda d: d.update({"next-hop": []}), "unexpected output"),
    ("nhg", lambda d: d["next-hop"][0].update({"next-hop": "x"}), "unexpected output"),
    ("table", _route(**{"next-hop-group": "x"}), "unexpected output"),
])
def test_two_pes_an_ip_vrf_choice_that_cannot_be_read_is_an_error(vrf, what, change, match):
    """DERIVED from the lp200 captures."""
    answers = _edit(vrf, what, change)
    with pytest.raises(DriverError, match=match):
        paths2(vrf, answers)
    for raw in ({"present": False}, {"next_hop": "2.2.2.2"}, {"next_hop": "3.3.3.3"}):
        assert not run2(vrf, answers, **raw).passed, raw


@pytest.mark.parametrize("vrf", ["ipvrf", "ipvrfb"])
def test_two_pes_with_one_next_hop_are_an_error(vrf):
    """DERIVED: leaf2's attr-set (16 for ipvrf, 17 for ipvrfb) says next hop 3.3.3.3 too: two paths match."""
    k = "info from state /network-instance default bgp-rib attr-sets attr-set " + {"ipvrf": "16", "ipvrfb": "17"}[vrf]
    d = json.loads(two_pe(vrf)[k])
    d["next-hop"] = "3.3.3.3"
    with pytest.raises(DriverError, match="not exactly one of them"):
        paths2(vrf, two_pe(vrf, **{k: J(d)}))


def test_design_b_the_ip_vrf_rows_local_pref_must_agree_with_the_path_it_forwards_with():
    """DERIVED: ipvrfb's bgp-evpn row (attr-set 14) with local-pref 100, the other path's."""
    with pytest.raises(DriverError, match="carries local-pref 100"):
        paths2("ipvrfb", _edit("ipvrfb", "attr", lambda d: d.update({"local-pref": 100})))


def test_design_b_when_the_ip_vrf_prefers_another_path_no_evpn_path_is_best():
    """DERIVED: ipvrfb's bgp-evpn row not best-route: no EVPN path is best, and the ip-vrf's next hops aren't read."""
    answers = _edit("ipvrfb", "rib", lambda d: d["route"][0].update({"best-route": False}))
    node = Node(answers)
    paths = SrlDriver(node, "leaf1").bgp_paths(TWO["ipvrfb"], "ipvrfb").value
    assert [p.best for p in paths] == [False, False]
    assert not any("next-hop" in c for c in node.asked)


@pytest.mark.parametrize("vrf", ["ipvrf", "ipvrfb"])
def test_an_evpn_path_left_unread_is_still_a_received_path(vrf):
    """DERIVED: leaf2's row not best-route, so one candidate and leaf2's path is left unread; it is never a local
    candidate, so `present: false` counts it (adversary M27)."""
    d = json.loads(two_pe(vrf)[EVPN])
    for r in d["ip-prefix-route"]:
        if r["neighbor"] == "2.2.2.2":
            r["best-route"] = False
    answers = two_pe(vrf, **{EVPN: J(d)})
    assert [(p.best, p.neighbor, p.local_candidate) for p in paths2(vrf, answers)] == \
        [(True, "3.3.3.3", False), (False, "2.2.2.2", False)]
    r = run2(vrf, answers, present=False)
    assert not r.passed and "2 path(s)" in r.detail, r.detail


def test_the_ip_vrf_answers_are_read_as_captured():
    a = two_pe("ipvrf")
    assert srlinux.parse_installed_evpn_group(a[key("ipvrf", "table")], "10.77.0.0/24") == "873408401"
    assert srlinux.parse_next_hop_group(a[key("ipvrf", "nhg")], "873408401") == ["873408398"]
    assert srlinux.parse_next_hop_address(a[key("ipvrf", "nh")], "873408398") == "3.3.3.3"
    with pytest.raises(DriverError):   # another group than the one asked for
        srlinux.parse_next_hop_group(a[key("ipvrf", "nhg")], "1")
    with pytest.raises(DriverError):   # another next hop than the one asked for
        srlinux.parse_next_hop_address(a[key("ipvrf", "nh")], "1")


@pytest.mark.parametrize("vrf", ["ipvrf", "ipvrfb"])
def test_two_pes_ecmp_to_a_vtep_no_path_names_is_an_error(vrf):
    """DERIVED: the ip-vrf forwards to 3.3.3.3 (one path's next hop) and to 4.4.4.4 (no path's): not that path alone."""
    base = f"info from state /network-instance {vrf} route-table next-hop "
    nh = json.loads(two_pe(vrf)[key(vrf, "nh")])
    answers = _edit(vrf, "nhg", lambda d: d["next-hop"].append(dict(d["next-hop"][0], id=1, **{"next-hop": "999"})))
    answers[base + "999"] = J({**nh, "index": "999", "ip-address": "4.4.4.4"})
    with pytest.raises(DriverError, match="not exactly one of them"):
        paths2(vrf, answers)


@pytest.mark.parametrize("vrf", ["ipvrf", "ipvrfb"])
@pytest.mark.parametrize("what,change", [
    ("table", _route(**{"next-hop-group": "1 ; rm"})),
    ("table", _route(**{"next-hop-group": True})),
    ("nhg", lambda d: d["next-hop"][0].update({"next-hop": "1 ; rm"})),
    ("nhg", lambda d: d["next-hop"][0].update({"next-hop": "-1"})),
])
def test_a_route_table_index_that_is_not_a_number_never_goes_into_a_command(vrf, what, change):
    """DERIVED: an index from device output goes back into a CLI command only as digits."""
    node = Node(_edit(vrf, what, change))
    with pytest.raises(DriverError, match="unexpected output"):
        SrlDriver(node, "leaf1").bgp_paths(TWO[vrf], vrf)
    assert not any(c.startswith(f"info from state /network-instance {vrf} route-table next-hop") and
                   not c.split()[-1].isdigit() for c in node.asked), node.asked
