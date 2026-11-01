"""The diff and matching engine on snapshot pairs: every intent form, the declared-but-didn't-happen path,
allow_anywhere, and the design's red tests (each must give UNDECLARED CHANGES with an empty or honest
intent). Assertions are on statuses and item keys, never on message text."""
from dataclasses import replace

import pytest

from netdryrun.verify.engine import VerifyError, baseline_problems, diff, far_ends, match
from netdryrun.verify.intent import IntentError
from netdryrun.verify.snapshot import ItemKey, NodeSnapshot, PathNextHop, Snapshot, canon_set
from verify_helpers import Lab, add_new_customer_block, attrs, base, intent, nh, path, rib, session


def undeclared(m):
    return {(d.key.kind, d.key.node, d.key.prefix or d.key.neighbor) for d in m.undeclared}


def run(before, after, lines=(), allow=()):
    return match(before.snap(), after.snap(), intent(lines, allow))


# --- the basics --------------------------------------------------------------------------------------------

def test_no_change_with_an_empty_intent():
    m = run(base(), base())
    assert m.status == "no_change" and not m.items


def test_an_intent_on_an_unchanged_lab_did_not_happen():
    m = run(base(), base(), [{"prefix": "10.101.0.0/24", "appears_on": ["up1"]}])
    assert m.status == "failed" and len(m.not_happened) == 1 and not m.undeclared


def test_any_change_with_an_empty_intent_is_undeclared():
    after = base()
    after.drop("cust1", "path", "198.18.0.0/24")
    m = run(base(), after)
    assert m.status == "failed" and undeclared(m) == {("path", "cust1", "198.18.0.0/24")}


def test_diff_refuses_different_node_sets():
    a = base().snap()
    b = base().snap()
    del b.nodes["peer1"]
    with pytest.raises(VerifyError):
        diff(a, b)


# --- appears_on --------------------------------------------------------------------------------------------

def test_appears_on_explains_the_new_route_and_its_advertisements():
    after = add_new_customer_block(base())
    m = run(base(), after, [{"prefix": "10.101.0.0/24", "appears_on": ["edge1", "up1", "peer1"]}])
    assert m.status == "matched", undeclared(m)
    (lr,) = m.lines
    assert {d["node"] for d in lr.details} == {"edge1", "up1", "peer1"}
    up1 = next(d for d in lr.details if d["node"] == "up1")
    assert up1["from"] == "10.0.2.1" and up1["as_path"] == "65000 65101" and up1["next_hop"] == ["10.0.2.1"]


def test_appears_on_covers_only_the_listed_nodes():
    after = add_new_customer_block(base())
    m = run(base(), after, [{"prefix": "10.101.0.0/24", "appears_on": ["up1", "peer1"]}])
    assert m.status == "failed"
    assert undeclared(m) == {("path", "edge1", "10.101.0.0/24"), ("rib", "edge1", "10.101.0.0/24")}


def test_appears_on_a_node_where_it_did_not_appear():
    after = add_new_customer_block(base(), nodes=("edge1", "up1"))
    m = run(base(), after, [{"prefix": "10.101.0.0/24", "appears_on": ["edge1", "up1", "peer1"]}])
    assert m.status == "failed" and [r.line.index for r in m.not_happened] == [0]
    # a line that didn't happen explains nothing
    assert ("path", "up1", "10.101.0.0/24") in undeclared(m)


def test_appears_on_needs_the_route_absent_before():
    m = run(base(), base(), [{"prefix": "10.100.0.0/24", "appears_on": ["up1"]}])
    assert m.status == "failed" and m.not_happened


def test_appears_on_requires_selected_and_fib_installed_by_default():
    after = add_new_customer_block(base())
    after.rib("up1", "10.101.0.0/24", rib("bgp", hops=("10.0.2.1",), fib=False))
    lines = [{"prefix": "10.101.0.0/24", "appears_on": ["edge1", "up1", "peer1"]}]
    assert run(base(), after, lines).status == "failed"
    lines[0]["state"] = "selected"
    assert run(base(), after, lines).status == "matched"


def test_appears_on_as_received_only():
    after = base()
    after.path("up1", "10.101.0.0/24", "10.0.2.1", path(best=False, as_path="65000 65101", next_hop="10.0.2.1"))
    after.adj_out("edge1", "10.0.2.2", "10.101.0.0/24", attrs(as_path="65101", next_hop="10.0.1.2"))
    lines = [{"prefix": "10.101.0.0/24", "appears_on": "up1"}]
    assert run(base(), after, lines).status == "failed"                    # default: must be in the FIB
    lines[0]["state"] = "received"
    assert run(base(), after, lines).status == "matched"
    lines[0]["with"] = {"as_path": "65000 65101"}
    assert run(base(), after, lines).status == "matched"
    lines[0]["with"] = {"as_path": "65000 65999"}
    assert run(base(), after, lines).status == "failed"


def _received_only_on_up1(lab):
    lab.adj_in("up1", "10.0.2.1", "10.101.0.0/24", attrs(as_path="65000 65101", next_hop="10.0.2.1", med=0))
    lab.adj_out("edge1", "10.0.2.2", "10.101.0.0/24", attrs(as_path="65101", next_hop="10.0.1.2"))


@pytest.mark.parametrize("pins,ok", [
    ({"from": "10.0.2.1", "as_path": "65000 65101", "next_hop": "10.0.2.1", "origin": "igp", "med": 0}, True),
    ({"from": "10.0.2.2"}, False),
    ({"communities": []}, False),            # not in the plain received listing: never matched against it
    ({"large_communities": []}, False),
    ({"ext_communities": []}, False),
    ({"cluster_list": []}, False),
    ({"originator_id": None}, False),
])
def test_a_received_route_matches_only_the_attributes_the_received_listing_shows(pins, ok):
    """A route received before inbound policy is read from FRR's plain listing (AS path, origin, MED, local
    preference, weight, next hop): a pin on anything else can't be checked against it, so it never matches."""
    line = {"prefix": "10.101.0.0/24", "appears_on": "up1", "state": "received", "with": pins}
    assert (run(base(), _edit(_received_only_on_up1)(), [line]).status == "matched") is ok


@pytest.mark.parametrize("pins,ok", [
    ({"from": "10.0.2.1", "as_path": "65000 65101", "next_hop": "10.0.2.1", "origin": "igp"}, True),
    ({"protocol": "bgp", "distance": 20}, True),
    ({"from": "10.0.3.1"}, False),
    ({"as_path": "65000 65000 65101"}, False),
    ({"local_pref": 200}, False),
    ({"communities": ["no-export"]}, False),
    ({"protocol": "static"}, False),
    ({"metric": 5}, False),
])
def test_appears_on_with_pins(pins, ok):
    after = add_new_customer_block(base())
    m = run(base(), after, [{"prefix": "10.101.0.0/24", "appears_on": ["edge1"]},
                            {"prefix": "10.101.0.0/24", "appears_on": ["up1"], "with": pins},
                            {"prefix": "10.101.0.0/24", "appears_on": ["peer1"]}])
    assert (m.status == "matched") is ok


def test_an_extra_advertisement_to_a_non_lab_neighbor_is_undeclared():
    after = add_new_customer_block(base())
    after.adj_out("edge1", "198.51.100.9", "10.101.0.0/24", attrs(as_path="65101", next_hop="10.0.1.2"))
    lines = [{"prefix": "10.101.0.0/24", "appears_on": ["edge1", "up1", "peer1"]}]
    m = run(base(), after, lines)
    assert m.status == "failed" and undeclared(m) == {("adj_out", "edge1", "10.101.0.0/24")}
    lines.append({"prefix": "10.101.0.0/24", "advertisement": {"node": "edge1", "neighbor": "198.51.100.9"},
                  "goes": "added"})
    assert run(base(), after, lines).status == "matched"


# --- disappears_from ---------------------------------------------------------------------------------------

def _withdraw_from_peer1(lab):
    lab.drop("edge1", "adj_out", "10.100.0.0/24", neighbor="10.0.3.2")
    lab.drop("peer1", "path", "10.100.0.0/24")
    lab.drop("peer1", "rib", "10.100.0.0/24")
    return lab


def test_disappears_from():
    after = _withdraw_from_peer1(base())
    assert run(base(), after).status == "failed"
    m = run(base(), after, [{"prefix": "10.100.0.0/24", "disappears_from": ["peer1"]}])
    assert m.status == "matched", undeclared(m)


def test_disappears_from_a_node_that_still_has_it():
    after = _withdraw_from_peer1(base())
    m = run(base(), after, [{"prefix": "10.100.0.0/24", "disappears_from": ["peer1", "up1"]}])
    assert m.status == "failed" and m.not_happened


def test_disappears_from_needs_the_route_selected_before():
    before = base()
    before.path("up1", "10.99.0.0/24", "10.0.2.1", path(best=False, as_path="65000", next_hop="10.0.2.1"))
    after = base()
    m = run(before, after, [{"prefix": "10.99.0.0/24", "disappears_from": ["up1"]}])
    assert m.status == "failed" and m.not_happened
    m = run(before, after, [{"prefix": "10.99.0.0/24", "disappears_from": ["up1"], "including_received_only": True}])
    assert m.status == "matched"


def _soft_reconfig_lab():
    lab = base()
    lab.adj_in("edge1", "10.0.2.2", "0.0.0.0/0", attrs(as_path="65002", next_hop="10.0.2.2"))   # filtered inbound
    lab.adj_in("edge1", "10.0.2.2", "203.0.113.0/24", attrs(as_path="65002", next_hop="10.0.2.2"))
    return lab


def test_red_removed_soft_reconfiguration_is_a_received_only_disappearance():
    before = _soft_reconfig_lab()
    after = base()                                       # soft-reconfiguration inbound removed on edge1
    m = run(before, after)
    assert m.status == "failed"
    assert undeclared(m) == {("adj_in", "edge1", "0.0.0.0/0"), ("adj_in", "edge1", "203.0.113.0/24")}
    # 0/0 was received-only: disappears_from without including_received_only didn't happen
    m = run(before, after, [{"prefix": "0.0.0.0/0", "disappears_from": ["edge1"]}])
    assert m.status == "failed" and m.not_happened


def test_soft_reconfiguration_removal_with_an_honest_intent():
    before, after = _soft_reconfig_lab(), base()
    after.drop("edge1", "adj_in")
    m = run(before, after, [{"prefix": "0.0.0.0/0", "disappears_from": ["edge1"], "including_received_only": True}])
    # 203.0.113.0/24 is still selected on edge1, only its pre-policy copy vanished: still undeclared
    assert m.status == "failed" and undeclared(m) == {("adj_in", "edge1", "203.0.113.0/24")}
    assert not m.not_happened


# --- best_path_on ------------------------------------------------------------------------------------------

def _raise_local_pref(lab, value=200):
    lab.path("edge1", "203.0.113.0/24", "10.0.2.2", path(as_path="65002", next_hop="10.0.2.2", local_pref=value))
    return lab


def test_best_path_on_with_listed_values():
    after = _raise_local_pref(base())
    assert run(base(), after).status == "failed"
    m = run(base(), after, [{"prefix": "203.0.113.0/24", "best_path_on": "edge1", "to": {"local_pref": 200}}])
    assert m.status == "matched", undeclared(m)


@pytest.mark.parametrize("to", [{"local_pref": 300}, {"local_pref": 200, "med": 5}, {"med": 5}, {"local_pref": 100}])
def test_best_path_on_listed_values_must_be_exact(to):
    after = _raise_local_pref(base())
    m = run(base(), after, [{"prefix": "203.0.113.0/24", "best_path_on": "edge1", "to": to}])
    assert m.status == "failed" and m.not_happened


def test_best_path_on_unlisted_attributes_are_frozen():
    after = base()
    after.path("edge1", "203.0.113.0/24", "10.0.2.2",
               path(as_path="65002", next_hop="10.0.2.2", local_pref=200, communities=["65000:7"]))
    m = run(base(), after, [{"prefix": "203.0.113.0/24", "best_path_on": "edge1", "to": {"local_pref": 200}}])
    assert m.status == "failed" and m.not_happened
    m = run(base(), after, [{"prefix": "203.0.113.0/24", "best_path_on": "edge1",
                             "to": {"local_pref": 200, "communities": ["65000:7"]}}])
    assert m.status == "matched"


def test_best_path_on_a_node_without_the_route():
    m = run(base(), base(), [{"prefix": "10.77.0.0/24", "best_path_on": "edge1", "to": {"med": 1}}])
    assert m.status == "failed" and m.not_happened


def _two_paths(lab, winner_kw=None, backup_kw=None):
    """198.51.100.0/24 on edge1 from peer1 (best) and up1 (backup), advertised to cust1."""
    lab.path("edge1", "198.51.100.0/24", "10.0.3.2", path(as_path="65003", next_hop="10.0.3.2", **(winner_kw or {})))
    lab.path("edge1", "198.51.100.0/24", "10.0.2.2",
             path(best=False, as_path="65002 65003", next_hop="10.0.2.2", **(backup_kw or {})))
    lab.rib("edge1", "198.51.100.0/24", rib("bgp", hops=("10.0.3.2",)))
    lab.adj_out("edge1", "10.0.1.2", "198.51.100.0/24", attrs(as_path="65003", next_hop="10.0.3.2"))
    lab.learn("cust1", "198.51.100.0/24", "10.0.1.1", "65000 65003")
    return lab


def _swap_winner(lab, key, value):
    lab.path("edge1", "198.51.100.0/24", "10.0.3.2", path(best=False, as_path="65003", next_hop="10.0.3.2"))
    lab.path("edge1", "198.51.100.0/24", "10.0.2.2",
             path(as_path="65002 65003", next_hop="10.0.2.2", **{key: value}))
    lab.rib("edge1", "198.51.100.0/24", rib("bgp", hops=("10.0.2.2",)))
    lab.adj_out("edge1", "10.0.1.2", "198.51.100.0/24", attrs(as_path="65002 65003", next_hop="10.0.2.2"))
    lab.learn("cust1", "198.51.100.0/24", "10.0.1.1", "65000 65002 65003")
    return lab


@pytest.mark.parametrize("key,value", [("weight", 100), ("origin", "igp")])
def test_red_a_weight_or_origin_change_that_swaps_the_winner(key, value):
    backup = {"origin": "incomplete"} if key == "origin" else {}
    before = _two_paths(base(), backup_kw=backup)
    after = _swap_winner(_two_paths(base(), backup_kw=backup), key, value)
    assert run(before, after).status == "failed"
    # an honest intent naming only the attribute: the winner (from, next hop, AS path) is frozen
    m = run(before, after, [{"prefix": "198.51.100.0/24", "best_path_on": "edge1", "to": {key: value}}])
    assert m.status == "failed" and m.not_happened
    # every changed attribute declared, on edge1 and on cust1 (which now sees another AS path)
    full = [{"prefix": "198.51.100.0/24", "best_path_on": "edge1",
             "to": {key: value, "from": "10.0.2.2", "next_hop": "10.0.2.2", "as_path": "65002 65003"}}]
    m = run(before, after, full)
    assert m.status == "failed" and undeclared(m) == {("path", "cust1", "198.51.100.0/24")}
    full.append({"prefix": "198.51.100.0/24", "best_path_on": "cust1", "to": {"as_path": "65000 65002 65003"}})
    assert run(before, after, full).status == "matched"


def test_red_lost_backup_path():
    before = _two_paths(base())
    after = _two_paths(base())
    after.drop("edge1", "path", "198.51.100.0/24", neighbor="10.0.2.2")
    m = run(before, after)
    assert m.status == "failed" and undeclared(m) == {("path", "edge1", "198.51.100.0/24")}
    # the best path is unchanged, so a best-path line can't explain it
    m = run(before, after, [{"prefix": "198.51.100.0/24", "best_path_on": "edge1", "to": {"med": 0}}])
    assert m.status == "failed"


def test_red_fib_swap_with_the_bgp_best_path_unchanged():
    after = base()
    after.rib("edge1", "203.0.113.0/24", rib("bgp", hops=("10.0.2.2",), selected=False, fib=False))
    after.rib("edge1", "203.0.113.0/24", rib("static", hops=("10.0.3.2",), distance=1))
    m = run(base(), after)
    assert m.status == "failed"
    assert undeclared(m) == {("rib", "edge1", "203.0.113.0/24")}
    assert {d.key.protocol for d in m.undeclared} == {"bgp", "static"}
    m = run(base(), after, [{"prefix": "203.0.113.0/24", "best_path_on": "edge1", "to": {"next_hop": "10.0.3.2"}}])
    assert m.status == "failed"


def test_red_large_community_edit():
    after = base()
    after.path("up1", "10.100.0.0/24", "10.0.2.1",
               path(as_path="65000 65101", next_hop="10.0.2.1", large=("65000:1:9",)))
    m = run(base(), after)
    assert m.status == "failed" and undeclared(m) == {("path", "up1", "10.100.0.0/24")}
    assert m.undeclared[0].fields == ("large_communities",)


def test_red_static_distance_change():
    after = base()
    after.rib("edge1", "192.0.2.0/24", rib("static", hops=(), distance=5))
    m = run(base(), after)
    assert m.status == "failed" and undeclared(m) == {("rib", "edge1", "192.0.2.0/24")}
    assert m.undeclared[0].fields == ("distance",)


def test_red_ospf_cost_change():
    after = base()
    after.rib("up1", "10.255.0.9/32", rib("ospf", hops=("10.0.2.1",), distance=110, metric=20))
    m = run(base(), after)
    assert m.status == "failed" and m.undeclared[0].fields == ("metric",)


def test_red_outbound_only_change_toward_an_external_peer():
    after = base()
    after.adj_out("edge1", "198.51.100.9", "192.0.2.0/24", attrs(as_path="65000 65000", next_hop="198.51.100.8"))
    m = run(base(), after)
    assert m.status == "failed" and undeclared(m) == {("adj_out", "edge1", "192.0.2.0/24")}
    # nothing changed on edge1's own best path: a best-path line can't explain it
    m = run(base(), after, [{"prefix": "192.0.2.0/24", "best_path_on": "edge1", "to": {"as_path": "65000"}}])
    assert m.status == "failed"
    adv = {"prefix": "192.0.2.0/24", "advertisement": {"node": "edge1", "neighbor": "198.51.100.9"}}
    assert run(base(), after, [{**adv, "to": {"as_path": "65000 65000"}}]).status == "matched"
    assert run(base(), after, [{**adv, "to": {"as_path": "65000 65000 65000"}}]).status == "failed"
    assert run(base(), after, [{**adv, "goes": "removed"}]).status == "failed"


def test_red_no_export_toward_the_outside():
    after = base()
    after.adj_out("edge1", "198.51.100.9", "192.0.2.0/24",
                  attrs(as_path="", next_hop="198.51.100.8", communities=["no-export"]))
    assert run(base(), after).status == "failed"


def test_best_path_change_explains_the_advertisement_it_propagates():
    before, after = base(), base()
    after.path("edge1", "203.0.113.0/24", "10.0.2.2",
               path(as_path="65002", next_hop="10.0.2.2", local_pref=100, communities=["65000:9"]))
    after.adj_out("edge1", "10.0.1.2", "203.0.113.0/24",
                  attrs(as_path="65002", next_hop="10.0.2.2", communities=["65000:9"]))
    after.learn("cust1", "203.0.113.0/24", "10.0.1.1", "65000 65002", communities=["65000:9"])
    lines = [{"prefix": "203.0.113.0/24", "best_path_on": "edge1", "to": {"communities": ["65000:9"]}},
             {"prefix": "203.0.113.0/24", "best_path_on": "cust1", "to": {"communities": ["65000:9"]}}]
    assert run(before, after, lines).status == "matched"
    # an outbound edit on top (a different community toward cust1) is not the propagated value
    after.adj_out("edge1", "10.0.1.2", "203.0.113.0/24",
                  attrs(as_path="65002", next_hop="10.0.2.2", communities=["65000:9", "65000:66"]))
    assert run(before, after, lines).status == "failed"


# --- session goes down -------------------------------------------------------------------------------------

def _peer1_down(lab):
    lab.session("edge1", "10.0.3.2", session(None, state="active", remote_as=65003))
    lab.session("peer1", "10.0.3.1", session(None, state="active"))
    for p in ("198.18.0.0/24",):
        lab.drop("edge1", "path", p)
        lab.drop("edge1", "rib", p)
    lab.drop("edge1", "adj_out", neighbor="10.0.3.2")
    lab.drop("peer1", "adj_out", neighbor="10.0.3.1")
    lab.drop("peer1", "path", "10.100.0.0/24")
    lab.drop("peer1", "rib", "10.100.0.0/24")
    # consequence beyond the session: cust1 loses the peer route
    lab.drop("edge1", "adj_out", "198.18.0.0/24", neighbor="10.0.1.2")
    lab.drop("cust1", "path", "198.18.0.0/24")
    lab.drop("cust1", "rib", "198.18.0.0/24")
    return lab


def test_session_goes_down_covers_only_routes_learned_over_it():
    after = _peer1_down(base())
    line = {"session": {"node": "edge1", "neighbor": "10.0.3.2", "afi": "ipv4-unicast"}, "goes": "down"}
    m = run(base(), after, [line])
    assert m.status == "failed"
    assert undeclared(m) == {("adj_out", "edge1", "198.18.0.0/24"), ("path", "cust1", "198.18.0.0/24"),
                             ("rib", "cust1", "198.18.0.0/24")}
    (lr,) = m.lines
    learned = {d["node"]: d["routes_learned_over_it"] for d in lr.details}
    assert learned == {"edge1": ["198.18.0.0/24"], "peer1": ["10.100.0.0/24"]}   # both ends of the one session
    m = run(base(), after, [line, {"prefix": "198.18.0.0/24", "disappears_from": ["cust1"]}])
    assert m.status == "matched", undeclared(m)


def test_session_goes_down_but_it_stayed_up():
    m = run(base(), base(), [{"session": {"node": "edge1", "neighbor": "10.0.3.2", "afi": "ipv4-unicast"}, "goes": "down"}])
    assert m.status == "failed" and m.not_happened


def test_session_goes_down_does_not_explain_a_failover():
    before = _two_paths(base())
    after = _two_paths(base())
    after.session("edge1", "10.0.3.2", session(None, state="idle", remote_as=65003))
    after.session("peer1", "10.0.3.1", session(None, state="idle"))
    after.drop("edge1", "path", "198.51.100.0/24", neighbor="10.0.3.2")
    after.path("edge1", "198.51.100.0/24", "10.0.2.2", path(as_path="65002 65003", next_hop="10.0.2.2"))
    after.rib("edge1", "198.51.100.0/24", rib("bgp", hops=("10.0.2.2",)))
    for lab in (before, after):   # keep the rest of the lab as it was, to isolate the failover
        lab.drop("edge1", "adj_out", neighbor="10.0.3.2")
        lab.drop("peer1", "adj_out", neighbor="10.0.3.1")
    after.drop("edge1", "path", "198.18.0.0/24")
    after.drop("edge1", "rib", "198.18.0.0/24")
    after.drop("peer1", "path", "10.100.0.0/24")
    after.drop("peer1", "rib", "10.100.0.0/24")
    m = run(before, after, [{"session": {"node": "edge1", "neighbor": "10.0.3.2", "afi": "ipv4-unicast"}, "goes": "down"}])
    assert m.status == "failed"
    assert ("path", "edge1", "198.51.100.0/24") in undeclared(m)     # the backup became best
    assert ("rib", "edge1", "198.51.100.0/24") in undeclared(m)


def test_session_line_needs_the_afi_even_when_the_session_carries_several():
    before = base()
    before.session("edge1", "10.0.3.2", session("10.0.3.1", afis=("ipv4-unicast", "ipv6-unicast"), remote_as=65003))
    after = base()
    after.session("edge1", "10.0.3.2", session(None, state="active", afis=("ipv4-unicast", "ipv6-unicast")))
    with pytest.raises(IntentError):
        run(before, after, [{"session": {"node": "edge1", "neighbor": "10.0.3.2"}, "goes": "down"}])
    m = run(before, after, [{"session": {"node": "edge1", "neighbor": "10.0.3.2", "afi": "ipv6-unicast"}, "goes": "down"}])
    assert m.status == "failed" and m.not_happened     # evaluated: the far end (peer1) is still established


# --- allow_anywhere ----------------------------------------------------------------------------------------

def test_allow_anywhere_exact_and_glob_expanded_never_supernet():
    after = base()
    after.learn("cust1", "10.200.5.0/24", "10.0.1.1", "65000 65002")
    after.learn("cust1", "10.201.0.0/24", "10.0.1.1", "65000 65002")
    m = run(base(), after, allow=["10.200.*.0/24"])
    assert m.status == "failed" and undeclared(m) == {("path", "cust1", "10.201.0.0/24"),
                                                      ("rib", "cust1", "10.201.0.0/24")}
    assert {d.key.prefix for d in m.allowed[0]} == {"10.200.5.0/24"}
    assert run(base(), after, allow=["10.0.0.0/8"]).status == "failed"            # no containment
    assert run(base(), after, allow=["10.200.5.0/24", "10.201.0.0/24"]).status == "matched"
    assert run(base(), after, allow=[{"prefix": "10.200.*.0/24", "vrf": "cust"}]).status == "failed"


def test_allow_anywhere_never_covers_sessions():
    after = base()
    after.session("edge1", "198.51.100.9", session(None, state="idle", remote_as=64999))
    after.drop("edge1", "adj_out", neighbor="198.51.100.9")
    m = run(base(), after, allow=["192.0.2.0/24"])
    assert m.status == "failed" and undeclared(m) == {("session", "edge1", "198.51.100.9")}


def test_dishonest_intent_declaring_a_leak_matches_the_diff():
    """The engine explains what is declared; it is the base-branch guards that must fail a declared leak
    (see test_verify_run). The verdict wording never says safe."""
    after = base()
    after.adj_out("edge1", "10.0.3.2", "203.0.113.0/24", attrs(as_path="65002", next_hop="10.0.2.2"))
    after.learn("peer1", "203.0.113.0/24", "10.0.3.1", "65000 65002")
    m = run(base(), after, [{"prefix": "203.0.113.0/24", "appears_on": ["peer1"]}])
    assert m.status == "matched"


# --- baseline ----------------------------------------------------------------------------------------------

def test_baseline_problems_list_every_session_not_established():
    lab = base()
    assert baseline_problems(lab.snap()) == []
    lab.session("edge1", "10.0.9.2", session(None, state="active"))
    lab.session("edge1", "10.0.3.2", replace(lab.get("edge1", "session", neighbor="10.0.3.2"), state="connect",
                                             local_address=None))
    probs = baseline_problems(lab.snap())
    assert len(probs) == 2 and all("edge1" in p for p in probs)


# --- best_path_on freezes every path but the new best (review finding 5) ------------------------------------

def test_best_path_on_the_old_best_path_changing_a_listed_attribute_is_undeclared():
    before = _two_paths(base())
    after = _swap_winner(_two_paths(base()), "weight", 100)
    lines = [{"prefix": "198.51.100.0/24", "best_path_on": "edge1",
              "to": {"weight": 100, "from": "10.0.2.2", "next_hop": "10.0.2.2", "as_path": "65002 65003"}},
             {"prefix": "198.51.100.0/24", "best_path_on": "cust1", "to": {"as_path": "65000 65002 65003"}}]
    assert run(before, after, lines).status == "matched"
    # the old best path also changes weight, to a value nobody declared: only the best flag may move on it
    after.path("edge1", "198.51.100.0/24", "10.0.3.2", path(best=False, as_path="65003", next_hop="10.0.3.2", weight=50))
    m = run(before, after, lines)
    assert m.status == "failed" and undeclared(m) == {("path", "edge1", "198.51.100.0/24")}
    assert {d.key.neighbor for d in m.undeclared} == {"10.0.3.2"}


# --- advertisement goes: added carries the best path, or the declared values (review finding 6) -------------

ADV = {"prefix": "10.100.0.0/24", "advertisement": {"node": "edge1", "neighbor": "198.51.100.9"}, "goes": "added"}


def _advertise_to_the_outside(**kw):
    after = base()
    after.adj_out("edge1", "198.51.100.9", "10.100.0.0/24", attrs(**{"as_path": "65101", "next_hop": "198.51.100.8", **kw}))
    return after


def test_advertisement_added_must_carry_the_best_paths_attributes():
    assert run(base(), _advertise_to_the_outside(), [ADV]).status == "matched"
    for kw in ({"as_path": "65101 65101 65101"}, {"communities": ["no-export"]}, {"med": 50}, {"origin": "incomplete"},
               {"large": ("65000:1:2",)}):
        m = run(base(), _advertise_to_the_outside(**kw), [ADV])
        assert m.status == "failed" and m.not_happened, kw
        assert undeclared(m) == {("adj_out", "edge1", "10.100.0.0/24")}


def test_advertisement_added_with_declared_values():
    after = _advertise_to_the_outside(as_path="65101 65101 65101", communities=["no-export"])
    line = {**ADV, "with": {"as_path": "65101 65101 65101", "communities": ["no-export"]}}
    assert run(base(), after, [line]).status == "matched"
    assert run(base(), after, [{**ADV, "with": {"as_path": "65101 65101 65101"}}]).status == "failed"   # communities unlisted
    assert run(base(), after, [{**ADV, "with": {"as_path": "65101 65101", "communities": ["no-export"]}}]).status == "failed"


def test_advertisement_added_without_a_best_path_to_compare_with():
    after = base()
    after.adj_out("edge1", "198.51.100.9", "10.77.0.0/24", attrs(as_path="", next_hop="198.51.100.8"))
    m = run(base(), after, [{**ADV, "prefix": "10.77.0.0/24"}])
    assert m.status == "failed" and m.not_happened


# --- sessions compare as established or not; the raw FSM state is evidence only (review finding 7) ----------

def test_sessions_compare_established_or_not_never_the_raw_state():
    before, after = base(), base()
    before.session("edge1", "10.0.9.2", session(None, state="active"))
    after.session("edge1", "10.0.9.2", session(None, state="connect"))
    assert diff(before.snap(), after.snap()) == []
    assert before.snap().stability_view() == after.snap().stability_view()
    states = {it["value"]["state"] for it in after.snap().to_json()["nodes"]["edge1"]["items"] if it["key"]["kind"] == "session"}
    assert "connect" in states                                         # the raw state stays in the evidence
    after.session("edge1", "10.0.3.2", session(None, state="idle", remote_as=65003))
    (d,) = [d for d in diff(before.snap(), after.snap()) if d.key.kind == "session"]
    assert d.key.neighbor == "10.0.3.2" and "established" in d.fields and "state" not in d.fields


# --- every collected field is compared (review finding 9) -----------------------------------------------------

def test_soft_reconfiguration_on_a_session_is_compared():
    before, after = base(), base()
    s = before.get("edge1", "session", neighbor="10.0.2.2")
    before.session("edge1", "10.0.2.2", replace(s, soft_reconfig_in=("ipv4-unicast",)))
    (d,) = diff(before.snap(), after.snap())
    assert d.key.kind == "session" and d.key.neighbor == "10.0.2.2" and d.fields == ("soft_reconfig_in",)
    m = run(before, after)
    assert m.status == "failed" and undeclared(m) == {("session", "edge1", "10.0.2.2")}


def test_a_vrf_added_or_removed_on_a_node_is_a_diff_item():
    before, after = base().snap(), base().snap()
    after.nodes["edge1"].vrfs = ("cust", "default")
    (d,) = diff(before, after)
    assert (d.key.kind, d.key.node, d.key.vrf, d.change) == ("vrf", "edge1", "cust", "added")
    m = match(before, after, intent(allow=["10.200.*.0/24"]))
    assert m.status == "failed" and [x.key for x in m.undeclared] == [d.key]
    (d,) = diff(after, before)
    assert d.change == "removed"


# --- a neighbor deleted from the config is "session removed", not "goes: down" -------------------------------

def test_a_removed_session_is_its_own_diff_kind_not_goes_down():
    after = _peer1_down(base())
    after.drop("edge1", "session", neighbor="10.0.3.2")                 # edge1's neighbor statement deleted
    line = {"session": {"node": "edge1", "neighbor": "10.0.3.2", "afi": "ipv4-unicast"}, "goes": "down"}
    m = run(base(), after, [line])
    assert m.status == "failed" and m.not_happened and "removed" in m.not_happened[0].reason
    removed = [d for d in m.undeclared if d.key.kind == "session"]
    assert sorted((d.key.node, d.change, d.kind) for d in removed) == [("edge1", "removed", "session removed"),
                                                                    ("peer1", "changed", "session")]


# --- every way a declaration can fail to happen (meta-tested per intent form) ---------------------------------
# Each case: the line didn't happen, so it explains nothing and the verdict fails, whatever else changed. These
# pin the `happened` flag and the reason on every early return of every evaluator (mutation testing found
# returns whose flag could flip to "happened" unnoticed on a lab where nothing else changed).

def _edit(*fns):
    def make():
        lab = base()
        for fn in fns:
            fn(lab)
        return lab
    return make


def _lp(lab, value, med=None):
    lab.learn("edge1", "203.0.113.0/24", "10.0.2.2", "65002", local_pref=value, med=med)


def _drop_best(lab):
    lab.drop("edge1", "path", "203.0.113.0/24")
    lab.drop("edge1", "rib", "203.0.113.0/24")


def _adj_in(lab):
    lab.adj_in("edge1", "10.0.1.2", "10.100.0.0/24", attrs(as_path="65101", next_hop="10.0.1.2"))


def _gone_but_received(lab):
    _adj_in(lab)
    lab.drop("edge1", "path", "10.100.0.0/24")
    lab.drop("edge1", "rib", "10.100.0.0/24")


def _session_down(lab):
    lab.session("edge1", "10.0.2.2", session(None, state="active", remote_as=65002))


def _adv_out(lab, **kw):
    lab.adj_out("edge1", "198.51.100.9", "10.100.0.0/24", attrs(**{"as_path": "65101", "next_hop": "198.51.100.8", **kw}))


OUT = {"node": "edge1", "neighbor": "198.51.100.9"}
S_LINE = {"session": {"node": "edge1", "neighbor": "10.0.2.2", "afi": "ipv4-unicast"}, "goes": "down"}
NEW = {"prefix": "10.101.0.0/24"}
CUST = {"prefix": "10.100.0.0/24"}
UP = {"prefix": "203.0.113.0/24", "best_path_on": "edge1"}
OWN = {"prefix": "192.0.2.0/24", "advertisement": OUT}
DID_NOT_HAPPEN = [
    # appears_on
    ("appears_on on an unchanged lab", base, base, {**NEW, "appears_on": ["up1"]}),
    ("appears_on of a route already there", base, base, {**CUST, "appears_on": ["up1"]}),
    ("appears_on where it stopped short", base, lambda: add_new_customer_block(base(), nodes=("edge1",)),
     {**NEW, "appears_on": ["edge1", "up1"]}),
    ("appears_on with a pin that doesn't match", base, lambda: add_new_customer_block(base()),
     {**NEW, "appears_on": ["edge1"], "with": {"as_path": "65999"}}),
    # disappears_from
    ("disappears_from on an unchanged lab", base, base, {**CUST, "disappears_from": ["up1"]}),
    ("disappears_from of a route never there", base, base, {**NEW, "disappears_from": ["up1"]}),
    ("disappears_from of a route now static", base,
     _edit(lambda lab: lab.drop("up1", "path", "10.100.0.0/24"), lambda lab: lab.drop("up1", "rib", "10.100.0.0/24"),
           lambda lab: lab.rib("up1", "10.100.0.0/24", rib("static", hops=(), distance=1))),
     {**CUST, "disappears_from": ["up1"]}),
    ("disappears_from while still received", _edit(_adj_in), _edit(_gone_but_received),
     {**CUST, "disappears_from": ["edge1"], "including_received_only": True}),
    # best_path_on
    ("best_path_on on an unchanged lab", base, base, {**UP, "to": {"local_pref": 200}}),
    ("best_path_on to another value", base, _edit(lambda lab: _lp(lab, 150)), {**UP, "to": {"local_pref": 200}}),
    ("best_path_on without a best path before", base, base, {**NEW, "best_path_on": "edge1", "to": {"local_pref": 200}}),
    ("best_path_on without a best path after", base, _edit(_drop_best), {**UP, "to": {"local_pref": 200}}),
    ("best_path_on to the value it already had", base, base, {**UP, "to": {"local_pref": 100}}),
    ("best_path_on with an unlisted attribute changed", base, _edit(lambda lab: _lp(lab, 200, med=5)),
     {**UP, "to": {"local_pref": 200}}),
    # session ... goes: down
    ("session that stayed up", base, base, S_LINE),
    ("session that never existed", base, base, {**S_LINE, "session": {**S_LINE["session"], "neighbor": "10.0.9.9"}}),
    ("session that was down before", _edit(_session_down), _edit(_session_down), S_LINE),
    ("session in an address family it doesn't carry", base, _edit(_session_down),
     {**S_LINE, "session": {**S_LINE["session"], "afi": "ipv6-unicast"}}),
    ("session removed from the config", base, _edit(lambda lab: lab.drop("edge1", "session", neighbor="10.0.2.2")),
     S_LINE),
    # advertisement
    ("advertisement added that didn't appear", base, base, {**CUST, "advertisement": OUT, "goes": "added"}),
    ("advertisement added that already existed", base, base, {**OWN, "goes": "added"}),
    ("advertisement added without a best path to compare it with", base,
     _edit(lambda lab: lab.adj_out("edge1", "198.51.100.9", "10.101.0.0/24", attrs(as_path="65101", next_hop="198.51.100.8"))),
     {**NEW, "advertisement": OUT, "goes": "added"}),
    ("advertisement added with a rewritten attribute", base, _edit(lambda lab: _adv_out(lab, med=50)),
     {**CUST, "advertisement": OUT, "goes": "added"}),
    ("advertisement removed that is still there", base, base, {**OWN, "goes": "removed"}),
    ("advertisement removed that never existed", base, base, {**CUST, "advertisement": OUT, "goes": "removed"}),
    ("advertisement changed that doesn't exist", base, base, {**CUST, "advertisement": OUT, "to": {"med": 50}}),
    ("advertisement changed to another value", _edit(_adv_out), _edit(lambda lab: _adv_out(lab, med=40)),
     {**CUST, "advertisement": OUT, "to": {"med": 50}}),
    ("advertisement changed in nothing listed", _edit(_adv_out), _edit(_adv_out),
     {**CUST, "advertisement": OUT, "to": {"med": None}}),
    ("advertisement changed in an unlisted attribute", _edit(_adv_out), _edit(lambda lab: _adv_out(lab, med=50, origin="incomplete")),
     {**CUST, "advertisement": OUT, "to": {"med": 50}}),
    # config_change_on (gauntlet 0.4, R4)
    ("config_change_on with no config change", base, base, {"config_change_on": ["edge1"]}),
    ("config_change_on on one node of two that changed", base,
     _edit(lambda lab: lab.configure("up1", " neighbor 10.0.2.1 description x")),
     {"config_change_on": ["edge1", "up1"]}),
]


@pytest.mark.parametrize("before,after,line", [pytest.param(b, a, ln, id=label) for label, b, a, ln in DID_NOT_HAPPEN])
def test_a_declaration_that_did_not_happen_fails(before, after, line):
    from netdryrun.verify.report import VerifyResult, to_dict

    b, a = before(), after()
    m = run(b, a, [line])
    (lr,) = m.lines
    assert lr.happened is False and lr.explained == set()
    assert lr.line is not None and lr.line.index == 0 and isinstance(lr.reason, str) and lr.reason
    assert m.status == "failed" and m.not_happened == [lr]
    # and the report lists it (the line and its reason)
    res = VerifyResult(status=m.status, match=m, before=b.snap(), after=a.snap(), intent=intent([line]))
    assert to_dict(res)["not_happened"] == [{"intent": 0, "line": lr.line.text, "reason": lr.reason}]


@pytest.mark.parametrize("form", sorted(__import__("netdryrun.verify.intent", fromlist=["FORMS"]).FORMS))
def test_meta_every_intent_form_has_did_not_happen_cases(form):
    """Meta-test: a new intent form (intent.FORMS) needs an evaluator and at least two cases above where its
    declaration doesn't happen and the verdict fails."""
    from netdryrun.verify.engine import EVALUATORS
    from netdryrun.verify.intent import FORMS

    assert set(EVALUATORS) == set(FORMS)
    cases = [label for label, _b, _a, ln in DID_NOT_HAPPEN if form in ln]
    assert len(cases) >= 2, f"intent form {form!r} has no did-not-happen cases in DID_NOT_HAPPEN"


# --- what each form may explain, and nothing more (found by mutation testing) --------------------------------

def test_advertisement_removed_and_changed_when_they_happen():
    assert run(_edit(_adv_out)(), base(), [{**CUST, "advertisement": OUT, "goes": "removed"}]).status == "matched"
    m = run(_edit(lambda lab: _adv_out(lab, med=40))(), _edit(lambda lab: _adv_out(lab, med=50))(),
            [{**CUST, "advertisement": OUT, "to": {"med": 50}}])
    assert m.status == "matched" and m.lines[0].explained


def _withdrawn_by_edge1(lab):
    lab.drop("edge1", "path", "10.100.0.0/24")
    lab.drop("edge1", "rib", "10.100.0.0/24")


def test_disappears_from_with_received_only_explains_the_rib_and_the_received_route():
    line = {**CUST, "disappears_from": ["edge1"], "including_received_only": True}
    m = run(_edit(_adj_in)(), _edit(_withdrawn_by_edge1)(), [line])
    assert m.status == "matched", undeclared(m)
    assert {d.key.kind for d in m.items} == {"rib", "path", "adj_in"}
    # without including_received_only, the route received before inbound policy is not covered
    m = run(_edit(_adj_in)(), _edit(_withdrawn_by_edge1)(), [{**CUST, "disappears_from": ["edge1"]}])
    assert m.status == "failed" and undeclared(m) == {("adj_in", "edge1", "10.100.0.0/24")}


def test_disappears_from_several_nodes_explains_every_one():
    def gone(lab):
        for node in ("up1", "peer1"):
            lab.drop(node, "path", "10.100.0.0/24")
            lab.drop(node, "rib", "10.100.0.0/24")
        lab.drop("edge1", "adj_out", "10.100.0.0/24", neighbor="10.0.2.2")
        lab.drop("edge1", "adj_out", "10.100.0.0/24", neighbor="10.0.3.2")
    m = run(base(), _edit(gone)(), [{**CUST, "disappears_from": ["up1", "peer1"]}])
    assert m.status == "matched", undeclared(m)


def test_appears_on_does_not_explain_another_prefix_advertised_to_the_same_nodes():
    after = add_new_customer_block(base())
    after.adj_out("edge1", "10.0.2.2", "10.77.0.0/24", attrs(as_path="65101", next_hop="10.0.1.2"))
    m = run(base(), after, [{**NEW, "appears_on": ["edge1", "up1", "peer1"]}])
    assert m.status == "failed" and undeclared(m) == {("adj_out", "edge1", "10.77.0.0/24")}


def test_session_goes_down_does_not_explain_a_route_learned_elsewhere():
    after = _peer1_down(base())
    _withdrawn_by_edge1(after)            # learned from cust1, not over the session that went down
    line = {"session": {"node": "edge1", "neighbor": "10.0.3.2", "afi": "ipv4-unicast"}, "goes": "down"}
    m = run(base(), after, [line])
    assert {("path", "edge1", "10.100.0.0/24"), ("rib", "edge1", "10.100.0.0/24")} <= undeclared(m)


def test_best_path_on_med_explains_the_rib_metric():
    def med(lab):
        lab.learn("edge1", "203.0.113.0/24", "10.0.2.2", "65002", local_pref=100, med=50)
        lab.rib("edge1", "203.0.113.0/24", rib("bgp", hops=("10.0.2.2",), metric=50))
    m = run(base(), _edit(med)(), [{**UP, "to": {"med": 50}}])
    assert m.status == "matched", undeclared(m)
    assert ("rib", "edge1", "203.0.113.0/24") in {(d.key.kind, d.key.node, d.key.prefix) for d in m.items}
    # the rib metric alone, declared as a local_pref change, is not explained
    def lp(lab):
        _lp(lab, 200)
        lab.rib("edge1", "203.0.113.0/24", rib("bgp", hops=("10.0.2.2",), metric=50))
    assert ("rib", "edge1", "203.0.113.0/24") in undeclared(run(base(), _edit(lp)(), [{**UP, "to": {"local_pref": 200}}]))


def test_two_best_paths_for_one_prefix_are_refused():
    after = base()
    after.path("edge1", "203.0.113.0/24", "10.0.3.2", path(as_path="65003 65002", next_hop="10.0.3.2"))
    with pytest.raises(VerifyError):
        run(base(), after, [{**UP, "to": {"local_pref": 200}}])


def _cust1_sees(lab, adj_as_path, cust1_as_path, communities=()):
    lab.adj_out("edge1", "10.0.1.2", "203.0.113.0/24", attrs(as_path=adj_as_path, next_hop="10.0.2.2",
                                                             communities=list(communities)))
    lab.learn("cust1", "203.0.113.0/24", "10.0.1.1", cust1_as_path, communities=list(communities))


def test_best_path_on_the_receiver_explains_the_advertisement_it_receives():
    """Only a cust1 line: edge1's advertisement to cust1 changed, and cust1's new best path carries it."""
    line = {"prefix": "203.0.113.0/24", "best_path_on": "cust1", "to": {"communities": ["65000:9"]}}
    after = _edit(lambda lab: _cust1_sees(lab, "65002", "65000 65002", ["65000:9"]))()
    assert run(base(), after, [line]).status == "matched"
    # the advertisement carries a value cust1's best path doesn't have: not what cust1 received
    after.adj_out("edge1", "10.0.1.2", "203.0.113.0/24",
                  attrs(as_path="65002", next_hop="10.0.2.2", communities=["65000:9", "65000:66"]))
    m = run(base(), after, [line])
    assert m.status == "failed" and undeclared(m) == {("adj_out", "edge1", "203.0.113.0/24")}
    # the same change declared on another node explains nothing on edge1's advertisement to cust1
    after = _edit(lambda lab: _cust1_sees(lab, "65002", "65000 65002", ["65000:9"]))()
    m = run(base(), after, [{**line, "best_path_on": "edge1"}])
    assert ("adj_out", "edge1", "203.0.113.0/24") in undeclared(m)


def test_best_path_on_the_receiver_with_an_as_path_change():
    line = {"prefix": "203.0.113.0/24", "best_path_on": "cust1", "to": {"as_path": "65000 65000 65002"}}
    after = _edit(lambda lab: _cust1_sees(lab, "65000 65002", "65000 65000 65002"))()
    assert run(base(), after, [line]).status == "matched"
    # cust1 adds one more ASN than the advertisement explains
    after = _edit(lambda lab: _cust1_sees(lab, "65000 65002", "65000 65000 65000 65002"))()
    m = run(base(), after, [{**line, "to": {"as_path": "65000 65000 65000 65002"}}])
    assert ("adj_out", "edge1", "203.0.113.0/24") in undeclared(m)


def test_best_path_on_the_sender_propagates_an_as_path_change_with_the_same_outbound_prefix():
    def before_fn(lab):
        _cust1_sees(lab, "65000 65002", "65000 65000 65002")

    def after_fn(adj, cust1):
        def make(lab):
            lab.learn("edge1", "203.0.113.0/24", "10.0.2.2", "65002 65002", local_pref=100)   # inbound prepend
            _cust1_sees(lab, adj, cust1)
        return make
    lines = [{"prefix": "203.0.113.0/24", "best_path_on": "edge1", "to": {"as_path": "65002 65002"}},
             {"prefix": "203.0.113.0/24", "best_path_on": "cust1", "to": {"as_path": "65000 65000 65002 65002"}}]
    m = run(_edit(before_fn)(), _edit(after_fn("65000 65002 65002", "65000 65000 65002 65002"))(), lines)
    assert m.status == "matched", undeclared(m)
    # an extra outbound prepend on top is not the propagated path: edge1's line doesn't explain it
    m = run(_edit(before_fn)(), _edit(after_fn("65000 65000 65002 65002", "65000 65000 65000 65002 65002"))(),
            lines[:1])
    assert ("adj_out", "edge1", "203.0.113.0/24") in undeclared(m)


def test_session_goes_down_explains_the_routes_received_over_it():
    def received(lab):
        lab.adj_in("edge1", "10.0.3.2", "198.18.0.0/24", attrs(as_path="65003", next_hop="10.0.3.2"))
    line = {"session": {"node": "edge1", "neighbor": "10.0.3.2", "afi": "ipv4-unicast"}, "goes": "down"}
    m = run(_edit(received)(), _peer1_down(base()), [line, {"prefix": "198.18.0.0/24", "disappears_from": ["cust1"]}])
    assert m.status == "matched", undeclared(m)
    assert ("adj_in", "edge1", "198.18.0.0/24") in {(d.key.kind, d.key.node, d.key.prefix) for d in m.items}


def test_disappears_from_a_route_selected_but_not_in_the_fib():
    def not_in_fib(lab):
        lab.rib("up1", "10.100.0.0/24", rib("bgp", hops=("10.0.2.1",), fib=False))

    def gone(lab):
        lab.drop("up1", "path", "10.100.0.0/24")
        lab.drop("up1", "rib", "10.100.0.0/24")
    assert run(_edit(not_in_fib)(), _edit(gone)(), [{**CUST, "disappears_from": ["up1"]}]).status == "matched"


def test_advertisement_added_checks_local_pref_and_every_pinned_attribute():
    line = {**CUST, "advertisement": OUT, "goes": "added"}
    # a LOCAL_PREF the best path doesn't have is a rewrite
    m = run(base(), _edit(lambda lab: _adv_out(lab, local_pref=300))(), [line])
    assert m.status == "failed" and m.not_happened
    # a pinned attribute outside the advertised set (the next hop) is compared too
    m = run(base(), _edit(_adv_out)(), [{**line, "with": {"next_hop": "198.51.100.99"}}])
    assert m.status == "failed" and m.not_happened
    assert run(base(), _edit(_adv_out)(), [{**line, "with": {"next_hop": "198.51.100.8"}}]).status == "matched"


def test_advertisement_to_next_hop_may_change_its_resolution():
    before = _edit(_adv_out)()
    after = _edit(lambda lab: _adv_out(lab, next_hop="198.51.100.7"))()
    m = run(before, after, [{**CUST, "advertisement": OUT, "to": {"next_hop": ["198.51.100.7"]}}])
    assert m.status == "matched", (m.lines[0].reason, undeclared(m))


MATCHED_BY_FORM = [
    ("appears_on", base, lambda: add_new_customer_block(base()), {**NEW, "appears_on": ["edge1", "up1", "peer1"]},
     {"node", "state"}),
    ("disappears_from", base, _edit(lambda lab: lab.drop("up1", "path", "10.100.0.0/24"),
                                    lambda lab: lab.drop("up1", "rib", "10.100.0.0/24"),
                                    lambda lab: lab.drop("edge1", "adj_out", "10.100.0.0/24", neighbor="10.0.2.2")),
     {**CUST, "disappears_from": ["up1"]}, {"node", "before"}),
    ("best_path_on", base, _edit(lambda lab: _lp(lab, 200)), {**UP, "to": {"local_pref": 200}}, {"node", "before", "after"}),
    ("session", base, lambda: _peer1_down(base()),
     {"session": {"node": "edge1", "neighbor": "10.0.3.2", "afi": "ipv4-unicast"}, "goes": "down"},
     {"node", "neighbor", "routes_learned_over_it"}),
    ("advertisement", base, _edit(_adv_out), {**CUST, "advertisement": OUT, "goes": "added"}, {"node", "neighbor"}),
]


@pytest.mark.parametrize("before,after,line,keys", [pytest.param(b, a, ln, k, id=f) for f, b, a, ln, k in MATCHED_BY_FORM])
def test_the_report_shows_what_each_declared_line_explained(before, after, line, keys):
    from netdryrun.verify.report import VerifyResult, to_dict

    b, a = before(), after()
    m = run(b, a, [line])
    (lr,) = m.lines
    assert lr.happened is True and lr.explained and lr.line is not None
    res = VerifyResult(status=m.status, match=m, before=b.snap(), after=a.snap(), intent=intent([line]))
    (declared,) = to_dict(res)["declared"]
    assert declared["intent"] == 0 and declared["line"] == lr.line.text and declared["items"]
    assert declared["details"] and all(keys <= set(d) for d in declared["details"]), declared["details"]


# --- the rest of the engine's mutation survivors (mutation run of 2026-10-28) ---------------------------------
# Each test names what a mutant got wrong; most are explanations a line must not give (a false pass), the rest
# explanations it must give (a false fail) and what the report shows.

def test_appears_on_an_ipv6_prefix_and_its_primary_next_hop():
    """IPv6 lines key on AFI ipv6; a path's next hop is its global address when it has one (the link-local one
    is resolution), else the link-local one."""
    v6 = "2001:db8:101::/48"

    def learned(lab, hops):
        p = path(as_path="65000 65101")
        lab.path("up1", v6, "10.0.2.1", replace(p, attrs=replace(p.attrs, next_hops=canon_set(hops))))
        lab.rib("up1", v6, rib("bgp", hops=("2001:db8:2::1",)))

    glob, ll = (PathNextHop("2001:db8:2::1", "global", True, True, 0, None),
                PathNextHop("fe80::1", "link-local", True, True, 0, "eth1"))
    line = {"prefix": v6, "appears_on": ["up1"]}
    assert run(base(), _edit(lambda lab: learned(lab, [glob, ll]))(), [line]).status == "matched"
    for hops, pin, ok in (([glob, ll], ["2001:db8:2::1"], True), ([glob, ll], ["2001:db8:2::1", "fe80::1"], False),
                          ([ll], ["fe80::1"], True)):
        m = run(base(), _edit(lambda lab, hops=hops: learned(lab, hops))(), [{**line, "with": {"next_hop": pin}}])
        assert (m.status == "matched") is ok, (hops, pin)


def test_advertisement_with_add_path_ids():
    def two(lab):
        for pid in (1, 2):
            lab._put(ItemKey("adj_out", "edge1", "default", "ipv4", "unicast", "10.100.0.0/24", neighbor="198.51.100.9",
                             path_id=pid), attrs(as_path="65101", next_hop="198.51.100.8"))
    m = run(_edit(two)(), base(), [{**CUST, "advertisement": OUT, "goes": "removed"}])
    assert m.status == "matched", undeclared(m)


def test_advertisement_added_without_local_pref_where_the_best_path_has_one():
    """eBGP doesn't send LOCAL_PREF: an advertisement without it still carries the best path (whose local
    preference is 100) unless the line pins it."""
    def adv(lab):
        lab.adj_out("edge1", "198.51.100.9", "203.0.113.0/24", attrs(as_path="65002", next_hop="10.0.2.2"))
    line = {"prefix": "203.0.113.0/24", "advertisement": OUT, "goes": "added"}
    assert run(base(), _edit(adv)(), [line]).status == "matched"
    assert run(base(), _edit(adv)(), [{**line, "with": {"local_pref": 100}}]).status == "failed"


def test_best_path_on_explains_only_changed_items_of_its_own_prefix_vrf_and_afi():
    line = {**UP, "to": {"local_pref": 200}}

    def backup(lab):          # a new backup path for the prefix: added, not changed
        lab.path("edge1", "203.0.113.0/24", "10.0.3.2", path(best=False, as_path="65003 65002", next_hop="10.0.3.2"))
    m = run(base(), _edit(lambda lab: _lp(lab, 200), backup)(), [line])
    assert {d.key.neighbor for d in m.undeclared} == {"10.0.3.2"}

    def other(lp):            # another prefix from the same neighbor changes the same attribute
        return lambda lab: lab.learn("edge1", "198.51.100.0/24", "10.0.2.2", "65002", local_pref=lp)
    m = run(_edit(other(100))(), _edit(other(200), lambda lab: _lp(lab, 200))(), [line])
    assert undeclared(m) == {("path", "edge1", "198.51.100.0/24")}

    def in_vrf(lp):           # the same prefix in another VRF
        return lambda lab: lab.path("edge1", "203.0.113.0/24", "10.0.2.2",
                                    path(as_path="65002", next_hop="10.0.2.2", local_pref=lp), vrf="cust")
    before, after = _edit(in_vrf(100))(), _edit(in_vrf(200), lambda lab: _lp(lab, 200))()
    m = match(_with_vrf(before), _with_vrf(after), intent([line]))
    assert {(d.key.vrf, d.key.kind) for d in m.undeclared} == {("cust", "path")}


def _with_vrf(lab, vrf="cust"):
    return Snapshot({n: NodeSnapshot(n, "frr", tuple(sorted({"default", vrf})), dict(items)) for n, items in lab.items.items()})


def test_best_path_on_beside_a_line_whose_items_sort_first():
    after = add_new_customer_block(_edit(lambda lab: _lp(lab, 200))())
    m = run(base(), after, [{**NEW, "appears_on": ["edge1", "up1", "peer1"]}, {**UP, "to": {"local_pref": 200}}])
    assert m.status == "matched", undeclared(m)


def test_best_path_on_med_does_not_explain_another_nodes_rib():
    def med(lab):
        lab.learn("edge1", "203.0.113.0/24", "10.0.2.2", "65002", local_pref=100, med=50)
        lab.rib("edge1", "203.0.113.0/24", rib("bgp", hops=("10.0.2.2",), metric=50))
        lab.rib("cust1", "203.0.113.0/24", rib("bgp", hops=("10.0.1.1",), metric=50))
    assert undeclared(run(base(), _edit(med)(), [{**UP, "to": {"med": 50}}])) == {("rib", "cust1", "203.0.113.0/24")}


def test_best_path_on_without_next_hop_does_not_explain_a_fib_next_hop_change():
    def lp_and_fib(lab):
        _lp(lab, 200)
        lab.rib("edge1", "203.0.113.0/24", rib("bgp", hops=("10.0.6.2",)))
    m = run(base(), _edit(lp_and_fib)(), [{**UP, "to": {"local_pref": 200}}])
    assert undeclared(m) == {("rib", "edge1", "203.0.113.0/24")}


def test_best_path_on_explains_an_advertisement_changed_in_exactly_the_listed_attribute():
    def comm(lab):
        lab.learn("edge1", "203.0.113.0/24", "10.0.2.2", "65002", local_pref=100, communities=["65000:9"])
        lab.adj_out("edge1", "10.0.1.2", "203.0.113.0/24", attrs(as_path="65002", next_hop="10.0.2.2", communities=["65000:9"]))
    m = run(base(), _edit(comm)(), [{**UP, "to": {"communities": ["65000:9"]}}])
    assert m.status == "matched", undeclared(m)


def test_best_path_on_details_show_the_listed_values_before_and_after():
    def change(lab):
        lab.learn("edge1", "203.0.113.0/24", "10.0.2.2", "65002 65002", local_pref=200,
                  communities=["65000:9", "65000:10"])
        lab.adj_out("edge1", "10.0.1.2", "203.0.113.0/24", attrs(as_path="65002 65002", next_hop="10.0.2.2",
                                                                 communities=["65000:9", "65000:10"]))
    line = {**UP, "to": {"local_pref": 200, "as_path": "65002 65002", "communities": ["65000:9", "65000:10"], "med": None}}
    m = run(base(), _edit(change)(), [line])
    (detail,) = m.lines[0].details
    assert detail == {"node": "edge1",
                      "before": {"from": "10.0.2.2", "local_pref": "100", "as_path": "'65002'", "communities": "[]",
                                 "med": "null"},
                      "after": {"from": "10.0.2.2", "local_pref": "200", "as_path": "'65002 65002'",
                                "communities": "[65000:10, 65000:9]", "med": "null"}}


def test_best_path_on_from_another_neighbor_may_change_the_peers_own_facts():
    """Listing `from` lets the peer type and router ID change with it (a new best path from another peer)."""
    def both(lab):
        old = lab.get("edge1", "path", "203.0.113.0/24", neighbor="10.0.2.2")
        lab.path("edge1", "203.0.113.0/24", "10.0.3.2", replace(old, best=False, peer_type="internal",
                                                                peer_router_id="10.255.0.4"))

    def swap(lab):
        both(lab)
        old = lab.get("edge1", "path", "203.0.113.0/24", neighbor="10.0.2.2")
        lab.path("edge1", "203.0.113.0/24", "10.0.2.2", replace(old, best=False))
        lab.path("edge1", "203.0.113.0/24", "10.0.3.2", replace(old, peer_type="internal", peer_router_id="10.255.0.4"))
    m = run(_edit(both)(), _edit(swap)(), [{**UP, "to": {"from": "10.0.3.2"}}])
    assert m.lines[0].happened, m.lines[0].reason


def test_appears_on_details_name_the_selected_routes_protocol_and_next_hops():
    after = add_new_customer_block(base())
    m = run(base(), after, [{**NEW, "appears_on": ["edge1", "up1", "peer1"]}])
    up1 = next(d for d in m.lines[0].details if d["node"] == "up1")
    assert (up1["state"], up1["protocol"], up1["next_hops"]) == ("selected and in the FIB", "bgp", ["10.0.2.1"])
    by_interface = replace(nh("10.0.0.1"), ip=None, interface="eth9", kind="interface")
    blackhole = replace(nh("10.0.0.1"), ip=None, interface=None, kind="blackhole")
    after.rib("up1", "10.77.0.0/24", (replace(rib("static", hops=())[0], nexthops=canon_set([by_interface, blackhole])),))
    m = run(base(), after, [{**NEW, "appears_on": ["edge1", "up1", "peer1"]}, {"prefix": "10.77.0.0/24", "appears_on": ["up1"]}])
    (static,) = m.lines[1].details
    assert static == {"node": "up1", "state": "selected and in the FIB", "protocol": "static",
                      "next_hops": ["blackhole", "eth9"]}


def test_pins_on_the_selected_route():
    after = add_new_customer_block(base())
    lines = [{**NEW, "appears_on": ["edge1"]}, {**NEW, "appears_on": ["peer1"]}]
    for pins, ok in (({"metric": 0}, True), ({"metric": 5}, False), ({"distance": 20}, True), ({"distance": 99}, False),
                     ({"protocol": "bgp", "metric": 0, "as_path": "65000 65101"}, True)):
        m = run(base(), after, [*lines, {**NEW, "appears_on": ["up1"], "with": pins}])
        assert (m.status == "matched") is ok, pins


def test_a_received_only_route_pinned_on_a_backup_path():
    """state: received, pinned on a path that isn't the best (or not selected): its source counts."""
    after = base()
    after.path("up1", "10.101.0.0/24", "10.0.2.1", path(best=False, as_path="65000 65101", next_hop="10.0.2.1"))
    after.adj_out("edge1", "10.0.2.2", "10.101.0.0/24", attrs(as_path="65101", next_hop="10.0.1.2"))
    line = {"prefix": "10.101.0.0/24", "appears_on": "up1", "state": "received"}
    assert run(base(), after, [{**line, "with": {"from": "10.0.2.1"}}]).status == "matched"
    assert run(base(), after, [{**line, "with": {"from": "10.0.3.1"}}]).status == "failed"


def _sender_and_cust1(adj, cust1, hops=None):
    def make(lab):
        lab.adj_out("edge1", "10.0.1.2", "203.0.113.0/24", attrs(as_path=adj, next_hop="10.0.2.2"))
        p = path(as_path=cust1, next_hop="10.0.1.1")
        if hops:
            p = replace(p, attrs=replace(p.attrs, next_hops=hops))
        lab.path("cust1", "203.0.113.0/24", "10.0.1.1", p)
    return make


def test_best_path_on_the_receiver_as_path_is_matched_on_its_end():
    line = {"prefix": "203.0.113.0/24", "best_path_on": "cust1"}
    # an iBGP-like receiver: the path received equals the one advertised, before and after
    before = _edit(_sender_and_cust1("65002", "65002"))()
    m = run(before, _edit(_sender_and_cust1("65002 65002", "65002 65002"))(), [{**line, "to": {"as_path": "65002 65002"}}])
    assert m.status == "matched", undeclared(m)
    # the receiver's path doesn't end with the advertised one: not what it received
    m = run(base(), _edit(_sender_and_cust1("65009 65002", "65000 65002 65002"))(),
            [{**line, "to": {"as_path": "65000 65002 65002"}}])
    assert ("adj_out", "edge1", "203.0.113.0/24") in undeclared(m)


def test_best_path_on_the_receiver_next_hop_is_compared_by_address():
    """The advertisement's next hop changed and the receiver's best path now has it: explained by the
    receiver's next_hop line, whatever the receiver's IGP metric to it."""
    hop = (PathNextHop("10.0.1.9", "global", True, True, 20, None),)

    def change(lab):
        _sender_and_cust1("65002", "65000 65002", hop)(lab)
        lab.adj_out("edge1", "10.0.1.2", "203.0.113.0/24", attrs(as_path="65002", next_hop="10.0.1.9"))
        lab.rib("cust1", "203.0.113.0/24", rib("bgp", hops=("10.0.1.9",)))
    line = {"prefix": "203.0.113.0/24", "best_path_on": "cust1", "to": {"next_hop": ["10.0.1.9"]}}
    m = run(base(), _edit(change)(), [line])
    assert m.status == "matched", (m.lines[0].reason, undeclared(m))

    def other(lab):           # an advertised next hop the receiver doesn't use is not explained
        change(lab)
        lab.adj_out("edge1", "10.0.1.2", "203.0.113.0/24", attrs(as_path="65002", next_hop="10.0.1.8"))
    assert ("adj_out", "edge1", "203.0.113.0/24") in undeclared(run(base(), _edit(other)(), [line]))


def _outside(best, adv):
    def make(lab):
        lab.learn("edge1", "203.0.113.0/24", "10.0.2.2", best, local_pref=100)
        lab.adj_out("edge1", "198.51.100.9", "203.0.113.0/24", attrs(as_path=adv, next_hop="10.0.2.2"))
    return make


@pytest.mark.parametrize("before,after,ok", [
    # an outbound prepend of 65000 65000, the same before and after: the new best path propagates
    (("65002", "65000 65000 65002"), ("65002 65002", "65000 65000 65002 65002"), True),
    # an AS_SET at the end of the path (the segment and the flat forms of the same outbound prepend)
    (("{65010,65011}", "65000 {65010,65011}"), ("65002 {65010,65011}", "65000 65002 {65010,65011}"), True),
    # locally originated before (an empty best path): the advertisement was the prepend alone
    (("", "65000"), ("65002", "65000 65002"), True),
    # the outbound prepend grew: not the new best path propagated
    (("65002", "65000 65002"), ("65002 65002", "65000 65000 65002 65002"), False),
    # the advertisement no longer carries the best path at all (an outbound rewrite)
    (("65002", "65000 65002"), ("65002 65002", "65000 65009"), False),
    # neither carries its best path
    (("65002", "65009"), ("65002 65002", "65008"), False),
    # an outbound rewrite that happens to keep the first ASN: not the new best path propagated
    (("65002", "65000 65002"), ("65003", "65000 65009"), False),
])
def test_best_path_on_the_sender_propagates_its_as_path_with_the_same_outbound_prepend(before, after, ok):
    line = {**UP, "to": {"as_path": after[0]}}
    m = run(_edit(_outside(*before))(), _edit(_outside(*after))(), [line])
    assert (("adj_out", "edge1", "203.0.113.0/24") not in undeclared(m)) is ok, (m.lines[0].reason, undeclared(m))


# session ... goes: down explains what was learned over that one session, in its address family and VRF

DOWN = {"session": {"node": "edge1", "neighbor": "10.0.3.2", "afi": "ipv4-unicast"}, "goes": "down"}


def test_session_goes_down_does_not_explain_a_static_route_for_a_prefix_learned_over_it():
    before = _edit(lambda lab: lab.rib("edge1", "198.18.0.0/24", rib("static", hops=("10.0.3.2",), selected=False,
                                                                        fib=False, distance=250), protocol="static"))()
    after = _peer1_down(base())
    m = run(before, after, [DOWN, {"prefix": "198.18.0.0/24", "disappears_from": ["cust1"]}])
    assert {(d.key.kind, d.key.protocol) for d in m.undeclared} == {("rib", "static")}


def test_session_goes_down_keeps_a_rib_entry_whose_prefix_still_has_a_path():
    after = _peer1_down(base())
    after.path("edge1", "198.18.0.0/24", "10.0.2.2", path(best=False, as_path="65002 65003", next_hop="10.0.2.2"))
    m = run(base(), after, [DOWN, {"prefix": "198.18.0.0/24", "disappears_from": ["cust1"]}])
    assert ("rib", "edge1", "198.18.0.0/24") in undeclared(m)


def test_session_goes_down_explains_only_removed_items_of_its_vrf_and_afi():
    def extra(lab):
        lab.path("edge1", "2001:db8:30::/48", "10.0.3.2", path(as_path="65003", next_hop="2001:db8:3::2"))
        lab.path("edge1", "198.18.0.0/24", "10.0.3.2", path(as_path="65003", next_hop="10.0.3.2"), vrf="cust")
    before = _with_vrf(_edit(extra)())
    m = match(before, _with_vrf(_peer1_down(base())),
              intent([DOWN, {"prefix": "198.18.0.0/24", "disappears_from": ["cust1"]}]))
    assert {(d.key.vrf, d.key.afi, d.key.prefix) for d in m.undeclared} == {("default", "ipv6", "2001:db8:30::/48"),
                                                                            ("cust", "ipv4", "198.18.0.0/24")}
    # a path from that neighbor that changed (here: kept as stale) is not "learned over it and now gone"
    after = _peer1_down(base())
    after.path("edge1", "198.18.0.0/24", "10.0.3.2", replace(base().get("edge1", "path", "198.18.0.0/24"), flags=("stale",)))
    assert ("path", "edge1", "198.18.0.0/24") in undeclared(run(base(), after, [DOWN]))


def test_session_goes_down_to_a_neighbor_outside_the_lab_lists_what_was_learned_over_it():
    after = base()
    after.session("edge1", "198.51.100.9", session(None, state="active", remote_as=64999))
    after.drop("edge1", "adj_out", neighbor="198.51.100.9")
    line = {"session": {"node": "edge1", "neighbor": "198.51.100.9", "afi": "ipv4-unicast"}, "goes": "down"}
    m = run(base(), after, [line])
    assert m.status == "matched", undeclared(m)
    assert m.lines[0].details == [{"node": "edge1", "neighbor": "198.51.100.9", "routes_learned_over_it": []}]


def test_far_ends_pair_the_two_ends_of_one_session_only():
    lab = base()
    # peer1 also peers with edge1's up1-facing address, from another address of its own
    lab.session("peer1", "10.0.2.1", session("10.0.7.1"))
    far = far_ends(lab.snap())
    assert far[("edge1", "default", "10.0.2.2")] == ("up1", "default", "10.0.2.1")
    assert ("peer1", "default", "10.0.2.1") not in far


def test_a_session_up_only_after_the_change_still_pairs_its_ends():
    """appears_on explains the advertisement to the node over a session that came up with the change."""
    def up1_down(lab):
        lab.session("edge1", "10.0.2.2", session(None, state="active", remote_as=65002))
        lab.session("up1", "10.0.2.1", session(None, state="active"))
        lab.drop("edge1", "adj_out", neighbor="10.0.2.2")
        lab.drop("up1", "adj_out", neighbor="10.0.2.1")
    after = add_new_customer_block(_edit(up1_down)(), nodes=("edge1", "peer1"))
    after.session("edge1", "10.0.2.2", session("10.0.2.1", remote_as=65002))
    after.session("up1", "10.0.2.1", session("10.0.2.2"))
    after.adj_out("edge1", "10.0.2.2", "10.101.0.0/24", attrs(as_path="65101", next_hop="10.0.1.2"))
    after.learn("up1", "10.101.0.0/24", "10.0.2.1", "65000 65101")
    m = run(_edit(up1_down)(), after, [{**NEW, "appears_on": ["edge1", "up1", "peer1"]}])
    assert ("adj_out", "edge1", "10.101.0.0/24") not in undeclared(m)


def test_the_report_shows_each_undeclared_routes_state_before_and_after():
    from netdryrun.verify.report import VerifyResult, to_dict

    after = add_new_customer_block(base(), nodes=("edge1",))
    after.rib("edge1", "192.0.2.0/24", rib("static", hops=(), distance=1) + rib("static", hops=("10.0.2.2",), distance=250,
                                                                               selected=False, fib=False))
    m = run(base(), after)
    res = VerifyResult(status=m.status, match=m, before=base().snap(), after=after.snap(), intent=intent([]))
    items = {(i["kind"], i["prefix"]): i for i in to_dict(res)["undeclared"]}
    new = items[("rib", "10.101.0.0/24")]
    assert (new["route_before"], new["route_after"]) == ("absent", "selected and in the FIB")
    static = items[("rib", "192.0.2.0/24")]
    discard = "selected and in the FIB as a discard route (blackhole, reject or unreachable: traffic is dropped)"
    assert static["fields"] == ["entries"] and (static["route_before"], static["route_after"]) == (discard, discard)


def test_pins_on_the_reflection_attributes():
    """cluster_list and originator_id are pinnable (`with:`) and must be read from the new path."""
    after = add_new_customer_block(base())
    old = after.get("up1", "path", "10.101.0.0/24")
    after.path("up1", "10.101.0.0/24", "10.0.2.1",
               replace(old, attrs=replace(old.attrs, cluster_list=("10.255.0.2",), originator_id="10.255.0.9")))
    lines = [{**NEW, "appears_on": ["edge1", "peer1"]}]
    for pins, ok in (({"originator_id": "10.255.0.9", "cluster_list": ["10.255.0.2"]}, True),
                     ({"originator_id": "10.255.0.8"}, False), ({"cluster_list": []}, False)):
        m = run(base(), after, [*lines, {**NEW, "appears_on": ["up1"], "with": pins}])
        assert (m.status == "matched") is ok, pins


def test_far_ends_pair_established_sessions_only():
    lab = base()
    lab.session("up1", "10.0.2.1", replace(session("10.0.2.2"), state="active"))   # a local address, not established
    assert ("edge1", "default", "10.0.2.2") not in far_ends(lab.snap())


def test_a_vrf_item_is_present_or_absent():
    before, after = base().snap(), base().snap()
    after = Snapshot({n: replace(ns, vrfs=("cust", "default")) for n, ns in after.nodes.items()})
    items = [d for d in diff(before, after) if d.key.kind == "vrf"]
    assert items and all(d.before is None and d.after is True for d in items)


def test_a_received_only_route_with_several_candidates_matches_on_any_of_them():
    after = base()
    after.path("up1", "10.101.0.0/24", "10.0.2.1", path(best=False, as_path="65000 65101", next_hop="10.0.2.1"))
    after.adj_in("up1", "10.0.2.1", "10.101.0.0/24", attrs(as_path="65000 65000 65101", next_hop="10.0.2.1"))
    after.adj_out("edge1", "10.0.2.2", "10.101.0.0/24", attrs(as_path="65101", next_hop="10.0.1.2"))
    line = {"prefix": "10.101.0.0/24", "appears_on": "up1", "state": "received"}
    for pinned, ok in (("65000 65101", True), ("65000 65000 65101", True), ("65101", False)):
        assert (run(base(), after, [{**line, "with": {"as_path": pinned}}]).status == "matched") is ok, pinned


# --- cold review of 0.4 (layer 6, 2026-10-28) ------------------------------------------------------------------

class _Lab4(Lab):
    NODES = ("a", "c", "d", "b")      # b last: an address-only pairing kept the last match

    def snap(self):
        return Snapshot({n: NodeSnapshot(n, "frr", ("blue", "default"), dict(it)) for n, it in self.items.items()})


def test_cold_2_reused_link_addresses_in_another_vrf_never_pair_the_wrong_nodes():
    """a-b (default) and c-d (VRF blue) both use 10.0.0.1/10.0.0.2: appears_on b must not explain c's new
    advertisement to d (a leak that d filters inbound, so nothing else shows it)."""
    p = "10.9.9.0/24"
    before = _Lab4()
    before.session("a", "10.0.0.2", session("10.0.0.1"))
    before.session("b", "10.0.0.1", session("10.0.0.2"))
    before.session("c", "10.0.0.2", session("10.0.0.1"), vrf="blue")
    before.session("d", "10.0.0.1", session("10.0.0.2"), vrf="blue")
    for n, vrf in (("a", "default"), ("c", "blue")):
        before.path(n, p, "local", path(as_path="", weight=32768, peer_type="local"), vrf=vrf)
        before.rib(n, p, rib("static", hops=(), distance=1), vrf=vrf)
    after = before.copy()
    after.adj_out("a", "10.0.0.2", p, attrs(as_path="", next_hop="10.0.0.1"))
    after.learn("b", p, "10.0.0.1", "65000")
    after.adj_out("c", "10.0.0.2", p, attrs(as_path="", next_hop="10.0.0.1"), vrf="blue")
    m = match(before.snap(), after.snap(), intent([{"prefix": p, "appears_on": ["b"]}]))
    assert m.status == "failed" and {(d.key.node, d.key.vrf) for d in m.undeclared} == {("c", "blue")}
    far = far_ends(before.snap())
    assert far[("a", "default", "10.0.0.2")][0] == "b" and far[("c", "blue", "10.0.0.2")][0] == "d"


def test_cold_2_an_ambiguous_pairing_pairs_nothing():
    lab = base()
    # a second node also peers 10.0.2.1 <-> 10.0.2.2 in the default VRF: which far end is up1's is unknowable
    lab.items["dup"] = {}
    lab.session("dup", "10.0.2.1", session("10.0.2.2"))
    lab.rib("dup", "10.9.255.0/24", rib("connected", hops=()))
    assert ("edge1", "default", "10.0.2.2") not in far_ends(lab.snap())


def test_cold_3_an_added_advertisement_carries_the_best_paths_next_hop_or_the_sender():
    line = {"prefix": "203.0.113.0/24", "advertisement": OUT, "goes": "added"}

    def adv(next_hop):
        return _edit(lambda lab: lab.adj_out("edge1", "198.51.100.9", "203.0.113.0/24",
                                             attrs(as_path="65002", next_hop=next_hop)))()
    assert run(base(), adv("10.0.2.2"), [line]).status == "matched"        # the best path's next hop
    assert run(base(), adv("0.0.0.0"), [line]).status == "matched"         # the sender itself (FRR prints 0.0.0.0)
    m = run(base(), adv("192.0.2.66"), [line])                              # an outbound next-hop rewrite
    assert m.status == "failed" and m.not_happened
    assert run(base(), adv("192.0.2.66"), [{**line, "with": {"next_hop": ["192.0.2.66"]}}]).status == "matched"


def test_cold_8_goes_down_explains_only_the_session_going_down():
    """Other changes to the same session (its remote AS, address families, soft-reconfiguration) ride along
    unseen if goes: down explains the whole session item."""
    after = _peer1_down(base())
    after.session("edge1", "10.0.3.2", session(None, state="active", remote_as=65999))
    m = run(base(), after, [DOWN, {"prefix": "198.18.0.0/24", "disappears_from": ["cust1"]}])
    assert ("session", "edge1", "10.0.3.2") in undeclared(m)
    after = _peer1_down(base())
    after.session("edge1", "10.0.3.2", replace(session(None, state="active", remote_as=65003),
                                                soft_reconfig_in=("ipv4-unicast",)))
    assert ("session", "edge1", "10.0.3.2") in undeclared(run(base(), after, [DOWN, {"prefix": "198.18.0.0/24",
                                                                                    "disappears_from": ["cust1"]}]))
