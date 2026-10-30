"""SR Linux readers: findings of the cold review (fresh reviewer, 2026-10-30), each one a test that failed before the fix.

Every case here is JSON-valid input a reader parsed when it should have raised, or raised something other than SnapshotError.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from netdryrun.verify.snapshot import SnapshotError
from netdryrun.verify.srlinux import parse_attr_set, parse_neighbors, parse_rib_paths, parse_route_table

FIX = Path(__file__).parent / "fixtures"
NEIGHBORS, ROUTES, RIB, ATTRS = "srl_bgp_neighbors.txt", "srl_route.txt", "srl_bgp_rib_paths.txt", "srl_attr_set_best.txt"


def fx(name: str) -> str:
    return (FIX / name).read_text(encoding="utf-8")


def edit(name: str, fn) -> str:
    data = json.loads(fx(name))
    fn(data)
    return json.dumps(data)


def raises(parse, text):
    with pytest.raises(SnapshotError):
        parse(text)


ROUTE = lambda t: parse_route_table(t, "default")            # noqa: E731
NEIGH = lambda t: parse_neighbors(t, "default")              # noqa: E731
RIBP = lambda t: parse_rib_paths(t, "default", "ipv4")       # noqa: E731


# ---- repeated keys and deep nesting ---------------------------------------------------------------------------------
def test_a_repeated_json_key_is_an_error_not_the_last_value():
    # json.loads keeps the last of two equal keys: a smaller result with no error
    raises(NEIGH, fx(NEIGHBORS).replace('"session-state": "established"',
                                        '"session-state": "idle", "session-state": "established"'))
    rows = json.loads(fx(RIB))["route"]
    raises(RIBP, '{"route": ' + json.dumps(rows) + ', "route": ' + json.dumps(rows[1:]) + "}")


def test_absurdly_deep_json_is_a_snapshot_error():
    raises(ROUTE, "[" * 200000)
    raises(ROUTE, '{"route": ' + "[" * 200000)


# ---- route table ------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("fib_edit", [
    lambda f: f.update({"last-successful-operation-type": 7}),
    lambda f: f.update({"suppressed": "false"}),
    lambda f: f.update({"pending-operation-type": "NONE"}),
    lambda f: f.update({"last-failed-operation-type": "explode"}),
    lambda f: f.pop("suppressed"),
])
def test_an_active_routes_fib_state_is_validated_not_guessed(fib_edit):
    raises(ROUTE, edit(ROUTES, lambda d: fib_edit(d["route"][0]["fib-programming"])))


@pytest.mark.parametrize("fib_edit", [lambda f: f.update({"last-successful-operation-type": "delete"}),
                                      lambda f: f.pop("last-successful-operation-type")])
def test_a_route_whose_last_fib_operation_was_not_an_add_is_not_programmed(fib_edit):
    got = ROUTE(edit(ROUTES, lambda d: fib_edit(d["route"][0]["fib-programming"])))
    assert got[("192.168.20.0/24", "bgp")].fib_programmed is False


def test_an_active_route_without_a_fib_state_is_an_error():
    raises(ROUTE, edit(ROUTES, lambda d: d["route"][0].pop("fib-programming")))
    raises(ROUTE, edit(ROUTES, lambda d: d["route"][0].update({"fib-programming": None})))


@pytest.mark.parametrize("update", [
    {"route-limit-exceeded": True}, {"route-limit-exceeded": "no"}, {"next-hop-group-network-instance": "red"},
    {"leaked": "no"}, {"id": "x"}, {"preference": 2 ** 32}, {"route-owner": ""},
])
def test_route_facts_that_are_not_what_the_reader_assumes_raise(update):
    raises(ROUTE, edit(ROUTES, lambda d: d["route"][0].update(update)))


@pytest.mark.parametrize("pop", ["origin-network-instance", "leaked", "id", "next-hop-group"])
def test_an_absent_route_fact_is_an_error_not_a_default(pop):
    raises(ROUTE, edit(ROUTES, lambda d: d["route"][0].pop(pop)))


# ---- addresses -----------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("nh", ["febf::1", "fe80::1", "169.254.1.1", "2001:db8::1", "::ffff:10.0.0.1"])
def test_only_a_plain_ipv4_next_hop_is_read(nh):
    raises(parse_attr_set, edit(ATTRS, lambda d: d.update({"next-hop": nh})))


@pytest.mark.parametrize("peer", ["fe80::1", "2001:db8::2", "::ffff:10.0.100.2"])
def test_a_peer_or_source_that_is_not_plain_ipv4_is_refused(peer):
    raises(NEIGH, edit(NEIGHBORS, lambda d: d["neighbor"][0].update({"peer-address": peer})))
    raises(RIBP, edit(RIB, lambda d: d["route"][0].update({"neighbor": peer})))


# ---- BGP RIB -----------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("update", [
    {"origin-protocol": "teleport"}, {"neighbor": "::"}, {"fib-disabled": True}, {"fib-disabled": "x"},
    {"unused-weight-only": True}, {"neighbor-as": "x"}, {"valid-route": False}, {"neighbor": "0.0.0.0"},
])
def test_rib_facts_that_are_not_settled_or_not_understood_raise(update):
    raises(RIBP, edit(RIB, lambda d: d["route"][0].update(update)))


def test_two_best_paths_for_one_prefix_are_an_error():
    rows = json.loads(fx(RIB))["route"]
    rows[1]["best-route"] = True
    with pytest.raises(SnapshotError, match="best"):
        RIBP(json.dumps({"route": rows}))


# ---- neighbors ---------------------------------------------------------------------------------------------------------------
def _afi(d):
    return next(a for a in d["neighbor"][0]["afi-safi"] if a["afi-safi-name"] == "ipv4-unicast")


@pytest.mark.parametrize("edit_fn", [
    lambda d: _afi(d)["ipv4-unicast"]["prefix-limit-received"].update({"prefix-limit-exceeded": True}),
    lambda d: _afi(d)["ipv4-unicast"]["prefix-limit-received"].update({"bogus": 1}),
    lambda d: _afi(d)["ipv4-unicast"].update({"receive-ipv6-next-hops": True}),
    lambda d: _afi(d)["ipv4-unicast"].update({"advertise-ipv6-next-hops": True}),
    lambda d: d["neighbor"][0]["route-reflector"].update({"client": True}),
    lambda d: d["neighbor"][0]["graceful-restart"].update({"anything": 1}),
    lambda d: d["neighbor"][0]["timers"].update({"anything": 1}),
    lambda d: _afi(d).update({"add-paths": None}),
    lambda d: _afi(d).pop("add-paths"),
    lambda d: _afi(d)["add-paths"].update({"send": True}),
    lambda d: _afi(d).update({"oper-state": "down"}),
    lambda d: _afi(d).update({"admin-state": "disable"}),
    lambda d: d["neighbor"][0].update({"admin-state": "disable"}),
    lambda d: d["neighbor"][0].update({"admin-state": 7}),
    lambda d: d["neighbor"][0].update({"peer-as": 0}),
    lambda d: d["neighbor"][0]["local-as"].update({"as-number": 0}),
])
def test_neighbor_facts_that_contradict_or_are_not_understood_raise(edit_fn):
    raises(NEIGH, edit(NEIGHBORS, edit_fn))


def test_a_session_that_is_not_established_cannot_have_a_family_up():
    def idle(d):
        d["neighbor"][0].update({"session-state": "idle"})
        d["neighbor"][0]["transport"].pop("local-address")
    raises(NEIGH, edit(NEIGHBORS, idle))


# ---- attribute sets -----------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("update", [{"atomic-aggregate": None}, {"atomic-aggregate": 0}])
def test_attribute_flags_are_booleans(update):
    raises(parse_attr_set, edit(ATTRS, lambda d: d.update(update)))


def test_atomic_aggregate_absent_is_an_error():
    raises(parse_attr_set, edit(ATTRS, lambda d: d.pop("atomic-aggregate")))


def test_as_path_segments_are_in_index_order_and_only_sequences_and_sets_are_read():
    two = [{"as-path-index": 0, "type": "as-sequence", "member": [1]}, {"as-path-index": 1, "type": "as-set", "member": [2]}]
    assert parse_attr_set(edit(ATTRS, lambda d: d["as-path"].update({"segment": two}))).as_path.render() == "1 {2}"
    for bad in ([two[1], two[0]], [two[0], {**two[1], "as-path-index": 0}], [{**two[0], "as-path-index": "x"}]):
        raises(parse_attr_set, edit(ATTRS, lambda d, b=bad: d["as-path"].update({"segment": b})))
    for kind in ("AS_SEQUENCE", "seq", "Sequence", "confederation-set", "as-confed-sequence"):
        raises(parse_attr_set, edit(ATTRS, lambda d, k=kind: d["as-path"]["segment"][0].update({"type": k})))
    raises(parse_attr_set, edit(ATTRS, lambda d: d["as-path"]["segment"][0].update({"member": [0]})))


@pytest.mark.parametrize("token", [65020, 4261150820, "  no-export ", "NO_EXPORT", "065020:0100", "local-as", "65020: 1", ""])
def test_a_community_is_read_only_in_the_form_the_device_prints(token):
    raises(parse_attr_set, edit(ATTRS, lambda d: d["communities"].update({"community": [token]})))


def test_well_known_community_names_the_device_prints_are_accepted():
    assert parse_attr_set(edit(ATTRS, lambda d: d["communities"].update({"community": ["no-export"]}))).communities == ("65535:65281",)


@pytest.mark.parametrize("token", [" 65020:1:1", "65020:1:1 ", 1, "65020:1"])
def test_a_large_community_is_read_only_in_the_form_the_device_prints(token):
    raises(parse_attr_set, edit(ATTRS, lambda d: d["communities"].update({"large-community": [token]})))
