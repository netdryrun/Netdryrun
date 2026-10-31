"""The fixes for the 0.4 interop findings (research/interop/REPORT.md), beyond the interop agent's own regression
tests (test_interop_04.py): how a `med: 0` check is refused on EOS, and the edges of each change."""
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from netdryrun.checks import EVALUATORS, Unready
from netdryrun.config import Check
from netdryrun.drivers import DriverError, check_supported, eos, junos, srlinux
from netdryrun.lab import ExecResult, Node

FIX = Path(__file__).parent / "fixtures"


def eos_lab():
    return SimpleNamespace(nodes={"a1": Node("a1", "clab-t-a1", "arista_ceos", "ceos:4.36.3M")})


def bgp_route(**params):
    return Check("bgp_route", {"node": "a1", "prefix": "192.168.1.1/32", **params}, "c1", timeout=60)


# ---- IOP-2: EOS prints "med": 0 for a path received with no MED, so a `med: 0` check is refused (exit 2)

def test_a_med_0_check_on_eos_is_refused_before_the_lab_boots():
    with pytest.raises(DriverError) as e:
        check_supported(eos_lab(), bgp_route(med=0))
    assert str(e.value) == ("c1: med: 0 can't be checked on eos: EOS output cannot tell MED 0 from no MED "
                            "(check a non-zero MED, or check this route on another platform)")


def test_a_non_zero_med_check_on_eos_is_accepted_and_reads_the_value():
    check_supported(eos_lab(), bgp_route(med=50))
    check_supported(eos_lab(), bgp_route(as_path="65005 65001"))
    data = json.loads((FIX / "eos_bgp_paths_no_med.txt").read_text())
    for p in data["vrfs"]["default"]["bgpRouteEntries"]["192.168.1.1/32"]["bgpRoutePaths"]:
        p["med"] = 50
    paths = eos.parse_bgp_paths(json.dumps(data), "192.168.1.1/32")
    assert paths and all(p.med == 50 for p in paths)


def test_eos_med_0_reads_as_unknown_so_a_med_0_check_can_never_pass():
    paths = eos.parse_bgp_paths((FIX / "eos_bgp_paths_no_med.txt").read_text(), "192.168.1.1/32")
    assert paths and all(p.med is None for p in paths)


# ---- IOP-3: EOS prints AS sets with spaces; the reference form is {a,b}, as on every other driver

@pytest.mark.parametrize("printed, canon", [
    ("65005 {65004 65006}", "65005 {65004,65006}"),
    ("65005 {65004  65006 65007}", "65005 {65004,65006,65007}"),
    ("{65004}", "{65004}"),
    ("65001 [65010 65011] 65002", "65001 [65010,65011] 65002"),
    ("(65010 65011) 65002", "(65010 65011) 65002"),
    ("65005  65001", "65005 65001"),
    ("", ""),
])
def test_eos_as_path_segments_take_the_reference_form(printed, canon):
    data = json.loads((FIX / "eos_bgp_paths_no_med.txt").read_text())
    for p in data["vrfs"]["default"]["bgpRouteEntries"]["192.168.1.1/32"]["bgpRoutePaths"]:
        p["asPathEntry"]["asPath"] = printed
    paths = eos.parse_bgp_paths(json.dumps(data), "192.168.1.1/32")
    assert paths and all(p.as_path == canon for p in paths)


# ---- IOP-1: Junos omits `metric` when no MED was received

def test_junos_med_0_check_fails_on_a_route_with_no_med():
    from netdryrun.checks import _bgp_route
    from netdryrun.drivers.base import Observation

    paths = junos.parse_bgp_paths((FIX / "junos_route_no_med.txt").read_text(), "192.168.3.1/32", "inet.0")
    d = SimpleNamespace(bgp_paths=lambda prefix, vrf="default": Observation(paths, []))
    ok, detail, _ = _bgp_route(d, {"prefix": "192.168.3.1/32", "med": 0})
    assert not ok and "MED is not set, expected 0" in detail


def test_eos_as_set_printed_with_commas_and_spaces_reads_the_same():
    data = json.loads((FIX / "eos_bgp_paths_no_med.txt").read_text())
    for p in data["vrfs"]["default"]["bgpRouteEntries"]["192.168.1.1/32"]["bgpRoutePaths"]:
        p["asPathEntry"]["asPath"] = "65005 { 65004, 65006 }"
    assert {p.as_path for p in eos.parse_bgp_paths(json.dumps(data), "192.168.1.1/32")} == {"65005 {65004,65006}"}


def test_only_eos_refuses_med_0_and_an_unknown_driver_refuses_nothing():
    frr = SimpleNamespace(nodes={"f1": Node("f1", "clab-t-f1", "linux", "quay.io/frrouting/frr:10.4.1")})
    check_supported(frr, Check("bgp_route", {"node": "f1", "prefix": "10.0.0.0/24", "med": 0}, "c1", timeout=60))
    check_supported(eos_lab(), bgp_route(local_pref=0))
    with pytest.raises(DriverError, match="med: 0 can't be checked on eos"):
        check_supported(eos_lab(), bgp_route(med=0, as_path="65005"))


# ---- IOP-6 (run 2): SR Linux keeps an import-rejected path in its local RIB. It is not received; any other
# invalid reason is one the driver doesn't know, and gives an error, never a verdict.

def _srl_rib(why) -> str:
    row = json.loads((FIX / "srl_rib_rejected.txt").read_text())["route"][0]
    if why is None:
        row.pop("invalid-reason")
    else:
        row["invalid-reason"] = why
    return json.dumps({"route": [row]})


class _SrlLab:
    def __init__(self, rib):
        self.rib = rib

    def exec(self, node, cmd, timeout=60, input=None):
        if "local-rib" in cmd[-1]:
            return ExecResult(cmd, 0, self.rib, "")
        if "attr-set" in cmd[-1]:
            return ExecResult(cmd, 0, (FIX / "srl_attr_set_rejected.txt").read_text(), "")
        if "route-table" in cmd[-1]:
            return ExecResult(cmd, 0, "{\n}", "")
        return ExecResult(cmd, 0, json.dumps({"peer-address": "10.1.2.2", "local-preference": 100}), "")


@pytest.mark.parametrize("why", [None, {}, {"rejected-route": False}])
def test_srl_a_path_with_no_true_invalid_reason_is_still_received(why):
    d = srlinux.SrlDriver(_SrlLab(_srl_rib(why)), "s1")
    ok, detail, _ = EVALUATORS["bgp_route"](d, {"node": "s1", "prefix": "192.168.6.0/24", "present": False})
    assert not ok and "unexpectedly in the BGP table" in detail
    ok, detail, _ = EVALUATORS["route"](d, {"node": "s1", "prefix": "192.168.6.0/24", "protocol": "bgp",
                                             "active": False})
    assert ok, detail


def test_srl_a_rejected_path_is_absent_and_its_failure_does_not_blame_the_next_hop():
    d = srlinux.SrlDriver(_SrlLab(_srl_rib({"rejected-route": True})), "s1")
    ok, detail, _ = EVALUATORS["bgp_route"](d, {"node": "s1", "prefix": "192.168.6.0/24", "as_path": "65005 65006"})
    assert not ok and "unreachable" not in detail


@pytest.mark.parametrize("why", [{"rejected-route": True, "next-hop-unresolved": True}, {"as-loop": True},
                                 {"rejected-route": "true"}, ["rejected-route"], "rejected-route"])
@pytest.mark.parametrize("check", [("bgp_route", {"present": False}),
                                   ("route", {"protocol": "bgp", "active": False}),
                                   ("route", {"present": False})])
def test_srl_an_invalid_reason_the_driver_does_not_know_is_an_error_never_a_verdict(why, check):
    d = srlinux.SrlDriver(_SrlLab(_srl_rib(why)), "s1")
    kind, params = check
    with pytest.raises(DriverError):
        EVALUATORS[kind](d, {"node": "s1", "prefix": "192.168.6.0/24", **params})


def test_srl_an_unknown_reason_on_another_prefix_is_not_read():
    other = json.loads(_srl_rib({"as-loop": True}))
    other["route"][0]["prefix"] = "192.168.7.0/24"
    assert srlinux.parse_routes("{\n}", "192.168.6.0/24", json.dumps(other)) == []


# ---- IOP-7 (run 2): Junos hides import-rejected routes and routes with an unusable next hop alike, so the
# reference count lies from accepted to received. A bound is judged only when the whole range agrees.

def _junos_lab(neighbors="junos_bgp_neighbor_hidden_nexthop.txt", hidden=None):
    """A Junos node; without `hidden` the hidden-route read gets an answer it can't use (the neighbor output)."""
    class Lab:
        calls = []

        def exec(self, node, cmd, timeout=60, input=None):
            self.calls.append(cmd[-1])
            if "receive-protocol" in cmd[-1] and hidden is not None:
                return ExecResult(cmd, 0, hidden if hidden.startswith("{") else (FIX / hidden).read_text(), "")
            return ExecResult(cmd, 0, (FIX / neighbors).read_text(), "")
    return junos.JunosDriver(Lab(), "j1")


@pytest.mark.parametrize("bound, passed, why", [
    ({"min": 205}, True, None), ({"max": 206}, True, None), ({"min": 200, "max": 210}, True, None),
    ({"max": 204}, False, None), ({"min": 207}, False, None), ({"exact": 204}, False, None),
    ({"exact": 207}, False, None),
    ({"max": 205}, False, "can't tell"), ({"exact": 205}, False, "can't tell"), ({"exact": 206}, False, "can't tell"),
    ({"min": 206}, False, "can't tell"), ({"min": 206, "max": 206}, False, "can't tell"),
])
def test_junos_a_bound_is_judged_only_when_the_whole_count_range_agrees(bound, passed, why):
    looped = json.loads((FIX / "junos_rp_hidden_iop7.txt").read_text())
    looped["route-information"][0]["route-table"][0]["rt"][0]["rt-entry"][0]["hidden-reason"] = [{"data": "Looped"}]
    d = _junos_lab(hidden=json.dumps(looped))
    ok, detail, _ = EVALUATORS["bgp_prefixes"](d, {"node": "j1", "neighbor": "10.1.1.2", **bound})
    assert ok is passed, detail
    assert detail.startswith("205 to 206 ipv4-unicast prefixes accepted (1 received route(s) hidden: rejected by "
                             "import policy or with a next hop the node can't use, which its output doesn't tell apart)")
    assert (why in detail) if why else "can't tell" not in detail


@pytest.mark.parametrize("received, err", [(None, "received-prefix-count"), ("204", "more accepted than received")])
def test_junos_a_missing_or_short_received_count_is_an_error(received, err):
    doc = json.loads((FIX / "junos_bgp_neighbor_hidden_nexthop.txt").read_text())
    for peer in doc["bgp-information"][0]["bgp-peer"]:
        for rib in peer.get("bgp-rib", []):
            if received is None:
                rib.pop("received-prefix-count", None)
            else:
                rib["received-prefix-count"] = [{"data": received}]
                rib["accepted-prefix-count"] = [{"data": "205"}]
    with pytest.raises(DriverError, match=err):
        junos.parse_bgp_neighbors(json.dumps(doc))


# With the hidden routes' reasons read, the count is the reference count: received minus rejected by import policy.

def test_junos_the_iop7_count_is_exact_once_the_hidden_reasons_are_read():
    d = _junos_lab(hidden="junos_rp_hidden_iop7.txt")
    n = d.bgp_neighbors().value["10.1.1.2"]
    assert (n.prefixes, n.prefixes_upto) == ({"ipv4-unicast": 206}, {})
    for bound, passed in (({"exact": 206}, True), ({"max": 205}, False), ({"min": 206}, True)):
        ok, detail, _ = EVALUATORS["bgp_prefixes"](d, {"node": "j1", "neighbor": "10.1.1.2", **bound})
        assert ok is passed and detail == "206 ipv4-unicast prefixes accepted", (bound, detail)


def test_junos_live_policy_reject_and_unusable_next_hop_count_two():
    # captured live: 3 received; 192.168.21.0/24 rejected by import policy, 192.168.22.0/24 with a next hop Junos
    # can't use. The reference count is 2 (FRR, EOS and SR Linux count the second one).
    d = _junos_lab("junos_bgp_neighbor_policy_and_nexthop.txt", "junos_rp_hidden.txt")
    n = d.bgp_neighbors().value["10.0.100.2"]
    assert (n.prefixes, n.prefixes_upto) == ({"ipv4-unicast": 2}, {})
    assert d.lab.calls[-1].startswith("cli -c 'show route receive-protocol bgp 10.0.100.2 table inet.0 hidden "
                                      "extensive")


def _hidden_doc(edit) -> str:
    doc = json.loads((FIX / "junos_rp_hidden.txt").read_text())
    edit(doc["route-information"][0]["route-table"][0])
    return json.dumps(doc)


@pytest.mark.parametrize("edit", [
    lambda t: t["rt"].pop(),                                        # fewer hidden routes than received - accepted
    lambda t: t["rt"].append(t["rt"][0]),                           # more
    lambda t: t["rt"][1]["rt-entry"][0].pop("hidden-reason"),       # a hidden route with no reason
    lambda t: t["rt"][1]["rt-entry"][0].update({"hidden-reason": [{}]}),   # an empty one
], ids=["fewer", "more", "no-reason", "empty-reason"])
def test_junos_hidden_routes_that_dont_add_up_keep_the_count_a_range(edit):
    d = _junos_lab("junos_bgp_neighbor_policy_and_nexthop.txt", _hidden_doc(edit))
    n = d.bgp_neighbors().value["10.0.100.2"]
    assert (n.prefixes, n.prefixes_upto) == ({"ipv4-unicast": 1}, {"ipv4-unicast": 3})
    ok, detail, _ = EVALUATORS["bgp_prefixes"](d, {"node": "j1", "neighbor": "10.0.100.2", "exact": 2})
    assert not ok and "can't tell" in detail


@pytest.mark.parametrize("reason", ["Looped", "Martian", "Rejected by import policy (RPKI)", "Unusable path"])
def test_junos_a_hidden_reason_the_driver_does_not_know_keeps_the_count_a_range(reason):
    # cold review: an unknown reason counted as received made `min: 3` pass where the reference count is 2
    doc = _hidden_doc(lambda t: t["rt"][0]["rt-entry"][0].update({"hidden-reason": [{"data": reason}]}))
    d = _junos_lab("junos_bgp_neighbor_policy_and_nexthop.txt", doc)
    n = d.bgp_neighbors().value["10.0.100.2"]
    assert (n.prefixes, n.prefixes_upto, n.prefixes_unread) == ({"ipv4-unicast": 1}, {"ipv4-unicast": 3}, {})
    ok, detail, _ = EVALUATORS["bgp_prefixes"](d, {"node": "j1", "neighbor": "10.0.100.2", "min": 3})
    assert not ok and "can't tell" in detail


@pytest.mark.parametrize("answer", [None, _hidden_doc(lambda t: t.update({"table-name": [{"data": "inet6.0"}]}))],
                         ids=["unreadable", "other-table"])
def test_junos_a_failed_hidden_route_read_is_no_usable_state_not_a_verdict(answer):
    d = _junos_lab("junos_bgp_neighbor_policy_and_nexthop.txt", answer)   # None: answered with the neighbor output
    n = d.bgp_neighbors().value["10.0.100.2"]
    assert "unexpected output" in n.prefixes_unread["ipv4-unicast"]
    ok, detail, _ = EVALUATORS["bgp_prefixes"](d, {"node": "j1", "neighbor": "10.0.100.2", "exact": 2})
    assert not ok and isinstance(detail, Unready) and detail.startswith("error: 1 to 3 ipv4-unicast")
    # a bound the whole range settles is still judged
    assert EVALUATORS["bgp_prefixes"](d, {"node": "j1", "neighbor": "10.0.100.2", "max": 3})[0] is True


@pytest.mark.parametrize("fixture, vrf, peer, table", [
    ("junos_bgp_neighbor.txt", "default", "2001:db8:1::2", "inet6.0"),
    ("junos_bgp_neighbor.txt", "default", "10.0.2.2", "inet.0"),
    ("junos_bgp_neighbor_red.txt", "RED", None, "RED.inet.0"),
])
def test_junos_the_hidden_route_read_names_the_family_and_vrf_table(fixture, vrf, peer, table):
    doc = json.loads((FIX / fixture).read_text())
    for p in doc["bgp-information"][0]["bgp-peer"]:
        for rib in p.get("bgp-rib", []):
            rib["received-prefix-count"] = [{"data": str(int(rib["accepted-prefix-count"][0]["data"]) + 1)}]

    class Lab:
        calls: list = []

        def exec(self, node, cmd, timeout=60, input=None):
            self.calls.append(cmd[-1])
            return ExecResult(cmd, 0, json.dumps(doc) if "show bgp neighbor" in cmd[-1] else "{}", "")
    d = junos.JunosDriver(Lab(), "j1")
    d.bgp_neighbors(vrf)
    hidden = [c for c in d.lab.calls if "receive-protocol" in c]
    assert any(f" table {table} hidden extensive" in c and (peer is None or f"bgp {peer} table" in c) for c in hidden)


def test_junos_a_count_with_nothing_hidden_reads_no_hidden_routes():
    d = _junos_lab("junos_bgp_neighbor_ibgp.txt", "junos_rp_hidden.txt")
    d.bgp_neighbors()
    assert not any("receive-protocol" in c for c in d.lab.calls)
