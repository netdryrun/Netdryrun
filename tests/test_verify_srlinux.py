"""verify snapshot, SR Linux: strict parsers for the state we have captured, and the refusals for everything we have not.

A node that can't be snapshotted is refused, never passed (`verify.run.classify_nodes` still refuses SR Linux nodes in 0.4; this
module is the read side that 0.4.1 grows into a collector once the missing captures exist). Rules under test come from the
0.4 gauntlet (R1 link-local next hops, R4 config the lab never exercises, R5 blackhole, R8 detection) and the router-state
contract (design/modular-architecture.md, C1..C26); the PREP.md table in the release branch names the rule beside each test.

Fixtures are the real SR Linux 26.7.2 captures in tests/fixtures (srl_*.txt).
"""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from netdryrun.verify.snapshot import SnapshotError
from netdryrun.verify.srlinux import (
    MISSING_SOURCES,
    SrlCollector,
    parse_attr_set,
    parse_neighbors,
    parse_rib_paths,
    parse_route_table,
)

FIX = Path(__file__).parent / "fixtures"


def fx(name: str) -> str:
    return (FIX / name).read_text(encoding="utf-8")


def edit(name: str, fn) -> str:
    data = json.loads(fx(name))
    fn(data)
    return json.dumps(data)


NEIGHBORS = "srl_bgp_neighbors.txt"
ROUTES = "srl_route.txt"
RIB = "srl_bgp_rib_paths.txt"
ATTRS = "srl_attr_set_best.txt"


# ---- sessions ---------------------------------------------------------------------------------------------------
def test_the_captured_session_is_read_with_its_facts():
    s = parse_neighbors(fx(NEIGHBORS), "default")["10.0.100.2"]
    assert (s.state, s.established, s.remote_as, s.local_as, s.local_address) == ("established", True, 65020, 65010, "10.0.100.1")
    assert s.afis == ("ipv4-unicast",)
    assert s.vrf == "default"


def test_received_active_and_rejected_stay_three_numbers_and_none_is_called_accepted():
    # C5: SR Linux's `received-routes` counts routes that fail loop detection (compat_verified.json), so no counter here
    # may be read as the accepted count
    s = parse_neighbors(fx(NEIGHBORS), "default")["10.0.100.2"]
    c = dict(s.counters["ipv4-unicast"])
    assert c["received-routes"] == 1 and c["active-routes"] == 1 and c["rejected-routes"] == 0
    assert not hasattr(s, "accepted") and "accepted-routes" not in c


def test_only_established_is_up():
    for state, up in (("established", True), ("idle", False), ("active", False), ("connect", False), ("opensent", False),
                      ("openconfirm", False)):
        text = edit(NEIGHBORS, lambda d, st=state: d["neighbor"][0].update({"session-state": st}))
        if not up:   # a session that is not established has no local address to report, and its family is down
            def down(d, st=state):
                d["neighbor"][0].update({"session-state": st})
                d["neighbor"][0]["transport"].pop("local-address")
                for a in d["neighbor"][0]["afi-safi"]:
                    if a["afi-safi-name"] == "ipv4-unicast":
                        a["oper-state"] = "down"
            text = edit(NEIGHBORS, down)
        assert parse_neighbors(text, "default")["10.0.100.2"].established is up


@pytest.mark.parametrize("state", ["Established-ish", "up", "", "established ", 7, None])
def test_an_unknown_session_state_raises(state):
    text = edit(NEIGHBORS, lambda d: d["neighbor"][0].update({"session-state": state}))
    with pytest.raises(SnapshotError):
        parse_neighbors(text, "default")


def test_a_session_without_a_local_address_while_established_raises():
    text = edit(NEIGHBORS, lambda d: d["neighbor"][0]["transport"].pop("local-address"))
    with pytest.raises(SnapshotError, match="local address"):
        parse_neighbors(text, "default")


def test_an_enabled_address_family_verify_does_not_snapshot_is_refused():
    def enable(d):
        for a in d["neighbor"][0]["afi-safi"]:
            if a["afi-safi-name"] == "evpn":
                a["admin-state"] = "enable"
    with pytest.raises(SnapshotError, match="evpn"):
        parse_neighbors(edit(NEIGHBORS, enable), "default")


def test_add_path_receive_is_refused_until_adj_rib_in_is_captured():
    def add_path(d):
        for a in d["neighbor"][0]["afi-safi"]:
            if a["afi-safi-name"] == "ipv4-unicast":
                a["add-paths"]["receive"] = True
    with pytest.raises(SnapshotError, match="add-path"):
        parse_neighbors(edit(NEIGHBORS, add_path), "default")


def test_an_unknown_neighbor_field_raises():
    with pytest.raises(SnapshotError, match="unknown"):
        parse_neighbors(edit(NEIGHBORS, lambda d: d["neighbor"][0].update({"brand-new-flag": True})), "default")


def test_a_session_for_an_unnumbered_or_named_peer_is_refused():
    with pytest.raises(SnapshotError):
        parse_neighbors(edit(NEIGHBORS, lambda d: d["neighbor"][0].update({"peer-address": "ethernet-1/1.0"})), "default")


def test_duplicate_neighbors_are_an_error():
    def dup(d):
        d["neighbor"].append(copy.deepcopy(d["neighbor"][0]))
    with pytest.raises(SnapshotError, match="twice"):
        parse_neighbors(edit(NEIGHBORS, dup), "default")


def test_no_neighbors_is_empty_only_when_the_text_is_the_real_empty_answer():
    assert parse_neighbors("{}", "default") == {}
    for bad in ("", "  ", "[]", "null", "not json", "{\"neighbor\": {}}", "{\"neighbor\": null}"):
        with pytest.raises(SnapshotError):
            parse_neighbors(bad, "default")


# ---- the route table ------------------------------------------------------------------------------------------------
def test_the_captured_route_is_read_with_its_provenance():
    r = parse_route_table(fx(ROUTES), "default")[("192.168.20.0/24", "bgp")]
    assert (r.owner, r.active, r.preference, r.metric) == ("bgp_mgr", True, 170, 0)
    assert r.fib_programmed is True and r.next_hop_group == "44970325"


def test_a_static_default_under_a_bgp_default_is_two_entries_and_the_static_is_active():
    rows = json.loads(fx("srl_leak_route.txt"))["route"]
    rows.append({**rows[0], "route-type": "bgp", "route-owner": "bgp_mgr", "active": False, "preference": 170, "metric": 0,
                 "next-hop-group": "9", "id": 0})
    got = parse_route_table(json.dumps({"route": rows}), "default")
    assert got[("0.0.0.0/0", "static")].active is True and got[("0.0.0.0/0", "bgp")].active is False


def test_a_route_without_an_active_flag_raises_not_inactive():
    with pytest.raises(SnapshotError, match="active"):
        parse_route_table(edit(ROUTES, lambda d: d["route"][0].pop("active")), "default")


@pytest.mark.parametrize("field,value", [("active", "true"), ("active", 1), ("preference", "170"), ("metric", None),
                                         ("route-type", "teleport"), ("route-type", ""), ("ipv4-prefix", "192.168.20.5/24"),
                                         ("ipv4-prefix", "192.168.20.0")])
def test_bad_route_values_raise(field, value):
    with pytest.raises(SnapshotError):
        parse_route_table(edit(ROUTES, lambda d: d["route"][0].update({field: value})), "default")


def test_a_route_with_a_failed_or_pending_fib_operation_is_not_programmed():
    for key, val in (("pending-operation-type", "add"), ("last-failed-operation-type", "add")):
        text = edit(ROUTES, lambda d, k=key, v=val: d["route"][0]["fib-programming"].update({k: v}))
        assert parse_route_table(text, "default")[("192.168.20.0/24", "bgp")].fib_programmed is False
    text = edit(ROUTES, lambda d: d["route"][0]["fib-programming"].update({"suppressed": True}))
    assert parse_route_table(text, "default")[("192.168.20.0/24", "bgp")].fib_programmed is False


def test_an_inactive_route_is_not_programmed_whatever_the_fib_says():
    text = edit(ROUTES, lambda d: d["route"][0].update({"active": False}))
    assert parse_route_table(text, "default")[("192.168.20.0/24", "bgp")].fib_programmed is False


def test_an_unknown_route_field_raises():
    with pytest.raises(SnapshotError, match="unknown"):
        parse_route_table(edit(ROUTES, lambda d: d["route"][0].update({"hardware-offload": "x"})), "default")


def test_a_route_for_another_network_instance_raises():
    with pytest.raises(SnapshotError, match="network instance"):
        parse_route_table(edit(ROUTES, lambda d: d["route"][0].update({"origin-network-instance": "red"})), "default")


def test_the_same_prefix_and_protocol_twice_is_kept_not_merged():
    rows = json.loads(fx(ROUTES))["route"]
    rows.append({**rows[0], "id": 1})
    assert len(parse_route_table(json.dumps({"route": rows}), "default")[("192.168.20.0/24", "bgp")].entries) == 2


def test_an_empty_route_table_is_empty_only_for_the_real_empty_answer():
    assert parse_route_table("{}", "default") == {}
    for bad in ("", "[]", "null", "{\"route\": {}}"):
        with pytest.raises(SnapshotError):
            parse_route_table(bad, "default")


# ---- BGP RIB paths and attribute sets ---------------------------------------------------------------------------------
def test_rib_paths_keep_identity_and_flags():
    paths = parse_rib_paths(fx(RIB), "default", "ipv4")
    best = next(p for p in paths.values() if p.best)
    assert (best.prefix, best.source, best.path_id, best.used, best.valid, best.attr_id) == ("192.168.20.0/24", "10.2.1.2", 0, True, True, "7")
    assert len(paths) == 2 and {p.source for p in paths.values()} == {"10.2.1.2", "10.2.2.2"}


def test_a_stale_path_is_not_settled():
    with pytest.raises(SnapshotError, match="stale"):
        parse_rib_paths(edit(RIB, lambda d: d["route"][0].update({"stale-route": True})), "default", "ipv4")


@pytest.mark.parametrize("value", ["yes", 1, None, "false"])
def test_a_stale_mark_that_is_not_a_boolean_raises(value):
    with pytest.raises(SnapshotError):
        parse_rib_paths(edit(RIB, lambda d: d["route"][0].update({"stale-route": value})), "default", "ipv4")


def test_a_path_missing_its_stale_mark_or_flags_raises():
    for key in ("stale-route", "best-route", "used-route", "valid-route", "attr-id", "path-id", "neighbor"):
        with pytest.raises(SnapshotError):
            parse_rib_paths(edit(RIB, lambda d, k=key: d["route"][0].pop(k)), "default", "ipv4")


def test_two_path_ids_for_one_prefix_and_peer_stay_two_paths():
    rows = json.loads(fx(RIB))["route"]
    extra = {**rows[0], "path-id": 5, "best-route": False, "attr-id": "7"}
    paths = parse_rib_paths(json.dumps({"route": [*rows, extra]}), "default", "ipv4")
    assert sorted(k[3] for k in paths if k[2] == "10.2.1.2") == [0, 5]


def test_the_same_path_twice_is_an_error():
    rows = json.loads(fx(RIB))["route"]
    with pytest.raises(SnapshotError, match="twice"):
        parse_rib_paths(json.dumps({"route": [*rows, rows[0]]}), "default", "ipv4")


def test_the_routers_own_static_in_the_bgp_rib_is_a_local_path_not_a_received_one():
    p = next(iter(parse_rib_paths(fx("srl_leak_rib.txt"), "default", "ipv4").values()))
    assert p.source == "local" and p.protocol == "static" and p.received is False


def test_an_unknown_rib_field_raises_and_an_ipv6_prefix_in_the_ipv4_listing_raises():
    with pytest.raises(SnapshotError, match="unknown"):
        parse_rib_paths(edit(RIB, lambda d: d["route"][0].update({"mystery": 1})), "default", "ipv4")
    with pytest.raises(SnapshotError):
        parse_rib_paths(edit(RIB, lambda d: d["route"][0].update({"prefix": "2001:db8::/32"})), "default", "ipv4")


def test_the_attribute_set_is_read_whole():
    a = parse_attr_set(fx(ATTRS))
    assert (a.origin, a.local_pref, a.med, a.next_hop) == ("igp", 200, 50, "10.2.1.2")
    assert a.as_path.render() == "65020"
    assert a.communities == ("65020:100", "65020:200") and a.large_communities == ("65020:1:1", "65020:2:2")


def test_a_missing_local_pref_stays_unknown_never_a_default():
    a = parse_attr_set(fx("srl_attr_set_backup.txt"))
    assert a.local_pref is None and a.med == 10
    assert a.as_path.render() == "65020 65020 65020"


def test_a_missing_origin_next_hop_or_as_path_raises():
    for key in ("origin", "next-hop", "as-path", "index"):
        with pytest.raises(SnapshotError):
            parse_attr_set(edit(ATTRS, lambda d, k=key: d.pop(k)))


def test_an_attribute_the_snapshot_does_not_compare_is_an_error_not_dropped():
    # an extended community, an aggregator, a cluster list: unseen in the captures, and a change in one would pass unseen
    for extra in ({"aggregator": {"as": 1}}, {"cluster-list": ["1.1.1.1"]}, {"originator-id": "1.1.1.1"}):
        with pytest.raises(SnapshotError, match="unknown"):
            parse_attr_set(edit(ATTRS, lambda d, e=extra: d.update(e)))
    with pytest.raises(SnapshotError, match="unknown"):
        parse_attr_set(edit(ATTRS, lambda d: d["communities"].update({"ext-community": ["rt:1:1"]})))


def test_a_link_local_next_hop_is_refused_until_its_interface_is_captured():
    with pytest.raises(SnapshotError, match="link-local"):
        parse_attr_set(edit(ATTRS, lambda d: d.update({"next-hop": "fe80::1"})))


def test_as_path_segment_types_and_sets_are_normalised():
    def seg(d):
        d["as-path"]["segment"] = [{"as-path-index": 0, "type": "as-sequence", "member": [65001, 65002]},
                                   {"as-path-index": 1, "type": "as-set", "member": [65004, 65003, 65003]}]
    assert parse_attr_set(edit(ATTRS, seg)).as_path.render() == "65001 65002 {65003,65004}"


@pytest.mark.parametrize("bad", [{"type": "as-teleport", "member": [1]}, {"type": "as-sequence", "member": []},
                                 {"type": "as-sequence", "member": ["x"]}, {"type": "as-sequence"}])
def test_a_bad_as_path_segment_raises(bad):
    with pytest.raises(SnapshotError):
        parse_attr_set(edit(ATTRS, lambda d: d["as-path"]["segment"].__setitem__(0, {"as-path-index": 0, **bad})))


def test_communities_are_canonical_and_a_bad_one_raises():
    assert parse_attr_set(edit(ATTRS, lambda d: d["communities"].update({"community": ["no-export", "65020:1"]}))).communities \
        == ("65020:1", "65535:65281")
    with pytest.raises(SnapshotError):
        parse_attr_set(edit(ATTRS, lambda d: d["communities"].update({"community": ["not-a-community"]})))


# ---- every parser is fuzzed the way the check drivers are --------------------------------------------------------------
CASES = [
    ("neighbors", lambda t: parse_neighbors(t, "default"), NEIGHBORS),
    ("routes", lambda t: parse_route_table(t, "default"), ROUTES),
    ("rib", lambda t: parse_rib_paths(t, "default", "ipv4"), RIB),
    ("attrs", parse_attr_set, ATTRS),
]


@pytest.mark.parametrize("name,parse,fixture", CASES, ids=[c[0] for c in CASES])
def test_a_cut_or_empty_answer_raises_or_is_complete_never_a_crash_or_a_smaller_snapshot(name, parse, fixture):
    full = fx(fixture).rstrip()
    whole = parse(full)
    for cut in range(0, len(full), max(1, len(full) // 200)):
        try:
            got = parse(full[:cut])
        except SnapshotError:
            continue
        # a cut that still parses must be the real thing: nothing may be missing from it
        assert got == whole or cut == 0 and got == {}, f"{name}: a {cut}-byte cut parsed to something smaller"


@pytest.mark.parametrize("name,parse,fixture", CASES, ids=[c[0] for c in CASES])
def test_wrong_json_types_raise_snapshot_errors_only(name, parse, fixture):
    for text in ("[]", "[1]", "\"x\"", "7", "true", "null", "{\"a\": 1}", "{\"neighbor\": 1}", "{\"route\": 1}", "{\"index\": 1}"):
        with pytest.raises(SnapshotError):
            parse(text)


# ---- the collector refuses until every source exists ---------------------------------------------------------------
def test_the_collector_refuses_naming_every_missing_source():
    with pytest.raises(SnapshotError) as e:
        SrlCollector("srl1", lambda node, argv: (0, "{}", "")).collect()
    for source in MISSING_SOURCES:
        assert source in str(e.value)


def test_the_collector_runs_no_command_before_it_refuses():
    calls = []
    with pytest.raises(SnapshotError):
        SrlCollector("srl1", lambda node, argv: calls.append((node, argv)) or (0, "{}", "")).collect()
    assert calls == []


def test_every_missing_source_names_why_it_is_needed():
    assert MISSING_SOURCES and all(isinstance(k, str) and isinstance(v, str) and len(v) > 20 for k, v in MISSING_SOURCES.items())
