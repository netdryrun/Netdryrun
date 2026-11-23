"""0.4.3 mutation gate, SR Linux EVPN path reading (bgp_paths, routes, _imported_paths, _evpn_choice,
_read_evpn_path and the parsers under them): which EVPN path an ip-vrf uses, which paths are read, and the exact
errors when an answer can't be read.

Built on the live SR Linux 26.7.2 captures and the helpers of tests/test_srl_evpn_043.py. Answers the captures don't
hold are built here from a named capture and marked DERIVED. Each error is pinned in full: the command it names is the
one whose answer couldn't be read.
"""
import json

import pytest

from netdryrun.drivers import srlinux
from netdryrun.drivers.base import DriverError
from netdryrun.drivers.srlinux import SrlDriver

from test_srl_evpn_043 import (ATTR6, EVPN, NEIGHBOR_LP, PREFIX, RIB, TABLE, TWO, J, Node, _attr6, _b_attr, _edit,
                               _no_lp, _pece2_rib, fx, key, paths2, state, two_pe)


def U(command: str, text: str) -> str:
    """The driver's error for an answer it can't read (drivers.base.unexpected), as the user sees it."""
    return f"unexpected output from `{command}`: {' '.join(text.split())[:200]}"


def error(fn, *args) -> str:
    with pytest.raises(DriverError) as e:
        fn(*args)
    return str(e.value)


def _rows(*changes) -> str:
    """DERIVED from srl2672_fp043_pece2_leaf1_ipvrf_bgp_rib_route.json: one copy of its bgp-evpn row per change."""
    d = json.loads(fx("srl2672_fp043_pece2_leaf1_ipvrf_bgp_rib_route.json"))
    row = d["route"][0]
    d["route"] = [dict(row, **c) for c in changes]
    return J(d)


# ------------------------------------------------------------------------------------------- _index, _imported

def test_a_route_table_index_error_names_the_command_and_the_first_40_characters():
    value = "x" * 50
    assert error(srlinux._index, "show next-hop-group", value) == U("show next-hop-group", f"index {'x' * 40!r}")


def test_a_rib_row_without_origin_protocol_names_the_rib_command():
    """DERIVED: the pece2 bgp-evpn row without origin-protocol: unknown, an error naming the bgp-rib read."""
    d = json.loads(fx("srl2672_fp043_pece2_leaf1_ipvrf_bgp_rib_route.json"))
    del d["route"][0]["origin-protocol"]
    row = json.loads(J(d))["route"][0]
    msg = error(SrlDriver(Node(state("pece2", **{RIB: J(d)})), "leaf1").bgp_paths, PREFIX, "ipvrf")
    assert msg == U(srlinux.RIB_CMD, f"no origin-protocol: {str(row)[:150]}")


# ------------------------------------------------------------------------------------------- attr-set numbers

@pytest.mark.parametrize("field", ["local-pref", "med"])
def test_an_evpn_attr_set_number_that_is_not_one_names_the_attr_set_command(field):
    """DERIVED: attr-set 6 with a local-pref or MED that isn't a number."""
    msg = error(srlinux.parse_evpn_attr_set, _attr6(**{field: "high"}), {"attr-id": "6"}, True)
    assert msg == U(srlinux.ATTR_CMD, "not a number: 'high'")


# ------------------------------------------------------------------------------------------- _imported_paths

def test_paths_from_ribs_the_driver_does_not_read_are_all_named():
    """DERIVED: ipvrf's bgp-rib with its bgp-evpn row and two rows from other BGP RIBs."""
    rib = _rows({}, {"origin-protocol": "bgp-vpn", "neighbor": "2.2.2.2"},
                {"origin-protocol": "bgp-label", "neighbor": "3.3.3.3"})
    msg = error(SrlDriver(Node(state("pece2", **{RIB: rib})), "leaf1").bgp_paths, PREFIX, "ipvrf")
    assert msg == (f"{PREFIX} in network-instance 'ipvrf': a path imported from bgp-label, bgp-vpn, a RIB the srlinux "
                   "driver doesn't read yet")


def test_a_bgp_evpn_row_with_nothing_imported_says_so_in_full():
    answers = state("pece2", **{EVPN: fx("srl2672_fp043_pece2absent_leaf1_default_evpn_local_rib.json")})
    msg = error(SrlDriver(Node(answers), "leaf1").bgp_paths, PREFIX, "ipvrf")
    assert msg == (f"{PREFIX}: network-instance 'ipvrf' lists a bgp-evpn path in its bgp-rib, but the EVPN RIB has no "
                   "IP-prefix route for it imported there")


def test_a_route_installed_from_bgp_vpn_says_so_in_full():
    table = json.loads(fx("srl2672_fp043_present_leaf1_ipvrf_route_table_route.json"))
    table["route"][0]["route-type"] = "bgp-vpn"
    msg = error(SrlDriver(Node(state("absent", **{TABLE: J(table)})), "leaf1").bgp_paths, PREFIX, "ipvrf")
    assert msg == f"{PREFIX} in network-instance 'ipvrf' is installed from bgp-vpn, a RIB the srlinux driver doesn't read yet"


def test_a_route_installed_from_bgp_evpn_with_nothing_imported_says_so_in_full():
    answers = state("present", **{EVPN: fx("srl2672_fp043_absent_leaf1_default_evpn_local_rib.json")})
    msg = error(SrlDriver(Node(answers), "leaf1").bgp_paths, PREFIX, "ipvrf")
    assert msg == (f"{PREFIX} in network-instance 'ipvrf' is installed from bgp-evpn, but the EVPN RIB has no "
                   "IP-prefix route for it imported there")


# ------------------------------------------------------------------------------------------- _evpn_choice

DEFAULT_RIB = ("info from state /network-instance default bgp-rib afi-safi ipv4-unicast ipv4-unicast local-rib route "
               "10.77.0.0/24 neighbor * origin-protocol * path-id *")


def _imported_into_default(best_2222: bool) -> dict:
    """DERIVED (as test_two_candidates_in_the_default_instance_are_an_error): default's bgp-rib lists a bgp-evpn row,
    and the lp200 EVPN RIB has both 10.77.0.0/24 paths imported into default; 2.2.2.2's is best-route or not."""
    row = json.loads(fx("srl2672_fp043_twope_lp200_leaf1_ipvrfb_bgp_rib_route.json"))
    row["route"][0]["prefix"] = "10.77.0.0/24"
    d = json.loads(two_pe("ipvrf")[EVPN])
    for r in d["ip-prefix-route"]:
        if r["ip-prefix"] == "10.77.0.0/24" and r["neighbor"] != "0.0.0.0":
            r["imported-network-instances"] = ["default"]
            if r["neighbor"] == "2.2.2.2":
                r["best-route"] = best_2222
    return {**two_pe("ipvrf"), DEFAULT_RIB: J(row), EVPN: J(d)}


def test_one_best_candidate_in_the_default_instance_is_the_path():
    """No ip-vrf route table to ask in default: the one best-route candidate is the path, never the other one."""
    paths = SrlDriver(Node(_imported_into_default(False)), "leaf1").bgp_paths("10.77.0.0/24").value
    assert [(p.best, p.next_hop, p.neighbor) for p in paths] == [(True, "3.3.3.3", "3.3.3.3"), (False, None, "2.2.2.2")]


def test_two_best_candidates_in_the_default_instance_say_so_in_full():
    msg = error(SrlDriver(Node(_imported_into_default(True)), "leaf1").bgp_paths, "10.77.0.0/24")
    assert msg == ("10.77.0.0/24: 2 EVPN paths imported into network-instance 'default' are best in the EVPN RIB; the "
                   "srlinux driver can't tell which one it uses there")


def test_ecmp_over_both_vteps_says_so_in_full():
    """Live, state ecmp: ipvrf forwards to both VTEPs."""
    msg = error(paths2, "ipvrf", two_pe("ipvrf", "ecmp"))
    assert msg == ("10.77.0.0/24: network-instance 'ipvrf' forwards to 2.2.2.2, 3.3.3.3, and the 2 imported EVPN "
                   "path(s) best in the EVPN RIB have next hops 2.2.2.2, 3.3.3.3: not exactly one of them, so the "
                   "srlinux driver can't tell which one is its best path")


CE_ATTR = "info from state /network-instance ipvrf bgp-rib attr-sets attr-set 12"


def test_the_local_pref_cross_check_reads_only_a_bgp_evpn_row():
    """DERIVED from design A (srl2672_fp043_present_*): ipvrf runs BGP to a CE, whose path (attr-set 12, local-pref
    150) is best and installed, and lists no bgp-evpn row; the EVPN path from 2.2.2.2 (local-pref 100) is imported.
    The CE row is no bgp-evpn row, so its local-pref is never compared with the EVPN path's."""
    rib = _rows({"neighbor": "10.1.0.2", "origin-protocol": "bgp", "attr-id": "12"})
    table = json.loads(fx("srl2672_fp043_present_leaf1_ipvrf_route_table_route.json"))
    table["route"][0].update({"route-type": "bgp", "route-owner": "bgp_mgr"})
    ce = {"index": "12", "origin": "igp", "atomic-aggregate": False, "next-hop": "10.1.0.2", "local-pref": 150,
          "as-path": {"segment": [{"type": "as_sequence", "member": [65010]}]}}
    node = Node(state("present", **{RIB: rib, TABLE: J(table), CE_ATTR: J(ce)}))
    paths = SrlDriver(node, "leaf1").bgp_paths(PREFIX, "ipvrf").value
    assert [(p.neighbor, p.next_hop, p.local_pref) for p in paths] == [("10.1.0.2", "10.1.0.2", 150),
                                                                         ("2.2.2.2", "2.2.2.2", 100)]
    assert node.asked.count(CE_ATTR) == 1   # read once, for the CE path itself


ROW_ATTR = "info from state /network-instance ipvrfb bgp-rib attr-sets attr-set 14"


def test_a_row_attr_id_error_names_the_attr_set_command():
    """DERIVED: ipvrfb's bgp-evpn row (lp200) with an attr-id of 50 letters."""
    answers = _edit("ipvrfb", "rib", lambda d: d["route"][0].update({"attr-id": "x" * 50}))
    assert error(paths2, "ipvrfb", answers) == U(srlinux.ATTR_CMD, f"index {'x' * 40!r}")


def test_a_row_attr_set_that_is_not_json_names_the_attr_set_command():
    assert key("ipvrfb", "attr") == ROW_ATTR
    assert error(paths2, "ipvrfb", two_pe("ipvrfb", **{ROW_ATTR: "[]"})) == U(srlinux.ATTR_CMD, "[]")


def test_a_row_attr_set_without_local_pref_names_it_and_its_first_150_characters():
    """DERIVED: ipvrfb's row attr-set (lp200) without local-pref, with a long AS path (over 150 characters)."""
    def change(d):
        d.pop("local-pref")
        d["as-path"] = {"segment": [{"type": "as_sequence", "member": list(range(65001, 65021))}]}
    answers = _b_attr("lp200", change)
    mine = json.loads(answers[ROW_ATTR])
    assert len(str(mine)) > 151
    assert error(paths2, "ipvrfb", answers) == U(srlinux.ATTR_CMD,
                                                 f"network-instance 'ipvrfb' attr-set 14: {str(mine)[:150]}")


def test_a_row_local_pref_that_is_not_a_number_names_the_attr_set_command():
    answers = _b_attr("lp200", lambda d: d.update({"local-pref": "high"}))
    assert error(paths2, "ipvrfb", answers) == U(srlinux.ATTR_CMD, "not a number: 'high'")


# ------------------------------------------------------------------------------------------- _read_evpn_path

def _read(answers: dict, row: dict):
    return SrlDriver(Node(answers), "leaf1")._read_evpn_path(row, True, [])


def test_an_evpn_attr_id_error_names_the_first_40_characters_and_the_prefix():
    row = {"attr-id": "x" * 50, "neighbor": "2.2.2.2", "ip-prefix": PREFIX}
    assert error(_read, {}, row) == f"unexpected attr-id {'x' * 40!r} for the EVPN route {PREFIX}"


ROW6 = {"attr-id": "6", "neighbor": "2.2.2.2", "ip-prefix": PREFIX}


def test_an_evpn_attr_set_that_is_not_json_names_the_attr_set_command():
    assert error(_read, {ATTR6: "[]"}, ROW6) == U(srlinux.ATTR_CMD, "[]")


@pytest.mark.parametrize("answer,why", [("[]", "[]"), (J({"local-preference": "high"}), "not a number: 'high'")])
def test_a_neighbor_local_pref_that_cannot_be_read_names_the_neighbor_command(answer, why):
    """DERIVED: attr-set 6 without local-pref; the neighbor's answer isn't an object, or its value isn't a number."""
    assert error(_read, {ATTR6: _no_lp(), NEIGHBOR_LP: answer}, ROW6) == U(srlinux.NEIGHBORS_CMD, why)


# ------------------------------------------------------------------------------------------- bgp_paths, routes

def test_an_evpn_path_the_ip_vrf_does_not_prefer_is_still_read():
    """DERIVED (pece2, ipvrf's bgp-evpn row not best): the one path is read in full, never an unread one."""
    node = Node(state("pece2", **{RIB: _pece2_rib(**{"best-route": False})}))
    paths = SrlDriver(node, "leaf1").bgp_paths(PREFIX, "ipvrf").value
    assert [(p.best, p.next_hop, p.local_pref, p.neighbor) for p in paths] == [(False, "2.2.2.2", 100, "2.2.2.2")]
    assert "info from state /network-instance default bgp-rib attr-sets attr-set 9" in node.asked


@pytest.mark.parametrize("vrf", ["ipvrf", "ipvrfb"])
def test_an_evpn_path_that_is_not_best_is_left_unread(vrf):
    """DERIVED: lp200 with leaf2's path not best-route: only the best path's attr-set is read; leaf2's path is listed
    with nothing read (one attr-set read per sample)."""
    d = json.loads(two_pe(vrf)[EVPN])
    for r in d["ip-prefix-route"]:
        if r["neighbor"] == "2.2.2.2":
            r["best-route"] = False
    node = Node(two_pe(vrf, **{EVPN: J(d)}))
    paths = SrlDriver(node, "leaf1").bgp_paths(TWO[vrf], vrf).value
    assert [(p.neighbor, p.next_hop, p.local_pref) for p in paths] == [("3.3.3.3", "3.3.3.3", 200),
                                                                        ("2.2.2.2", None, None)]
    leaf2 = {"ipvrf": "16", "ipvrfb": "17"}[vrf]
    assert f"info from state /network-instance default bgp-rib attr-sets attr-set {leaf2}" not in node.asked


def test_an_installed_evpn_route_is_listed_once_and_the_evpn_rib_not_read():
    """Design A (srl2672_fp043_present_*): the route table's active bgp-evpn route is the route; the EVPN RIB is read
    only when no bgp-evpn route is there."""
    node = Node(state("present"))
    routes = SrlDriver(node, "leaf1").routes(PREFIX, "ipvrf").value
    assert [(r.protocol, r.active) for r in routes] == [("bgp-evpn", True)]
    assert EVPN not in node.asked

