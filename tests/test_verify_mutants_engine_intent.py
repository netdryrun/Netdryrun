"""Mutation gate for 0.4: the intent parser and the matching engine. A verify verdict is only as honest as what each
intent line is allowed to explain and what each refusal tells the user, so the reasons, refusals and edge cases that
the 0.4 mutmut run left unpinned are pinned here exactly.
"""
from dataclasses import replace

import pytest

from netdryrun.verify.engine import (DiffItem, Index, VerifyError, config_lines_changed, diff, far_ends, match,
                                     route_state)
from netdryrun.verify.intent import IntentError, parse_intent
from netdryrun.verify.snapshot import ItemKey, NodeSnapshot, Snapshot, canon_set
from verify_helpers import attrs, base, intent, nh, rib, session


def run(before, after, lines=()):
    return match(before.snap(), after.snap(), intent(lines))


def reason(before, after, line):
    m = run(before, after, [line])
    (lr,) = m.lines
    assert not lr.happened and m.status == "failed"
    return lr.reason


def refused(*lines) -> str:
    with pytest.raises(IntentError) as e:
        parse_intent({"intent": list(lines)}, "test")
    return str(e.value)


# ============================================================================================ intent: refusals

NEW = {"prefix": "10.101.0.0/24"}
OUT = {"node": "edge1", "neighbor": "198.51.100.9"}
ADV = {"prefix": "10.100.0.0/24", "advertisement": OUT}


@pytest.mark.parametrize("nodes", [["edge1", "edge1"], [1], "up1", [], [""]])
def test_config_change_on_refuses_anything_but_a_list_of_distinct_node_names(nodes):
    """config_change_on takes a non-empty list of non-empty node names, each once: a bare string is not split into
    characters, a duplicate is refused by this check (not later, as a clash), and a non-string never reaches the
    line text."""
    assert refused({"config_change_on": nodes}) == "intent[0]: config_change_on must be a list of node names, each once"


def test_config_change_on_line_text():
    """The echo of a config_change_on line names every node and says it is not tested."""
    (ln,) = parse_intent({"intent": [{"config_change_on": ["edge1", "up1"]}]}, "test").lines
    assert ln.text == "the running config of edge1, up1 changes (not tested where the lab doesn't exercise it)"


@pytest.mark.parametrize("line,message", [
    ({"appears_on": ["up1"]}, "intent[0]: a appears_on line needs a prefix"),
    ({"prefix": "10.0.0.0/24", "vrf": "all", "appears_on": ["up1"]},
     "intent[0]: bad vrf 'all': name one VRF (letters, digits and . _ : -)"),
    ({**NEW, "appears_on": []}, "intent[0]: appears_on must be a node name or a non-empty list of node names"),
    ({**NEW, "appears_on": ["up1"], "state": "bogus"},
     "intent[0]: state must be one of installed, selected, received, discard, got 'bogus'"),
    ({**NEW, "appears_on": ["up1"], "with": {}}, "intent[0]: with must be a non-empty mapping of attributes"),
    ({**NEW, "appears_on": ["up1"], "state": "received", "with": {"protocol": "bgp"}},
     "intent[0]: protocol, distance and metric pin the selected route; state: received has none"),
    ({**NEW, "disappears_from": []},
     "intent[0]: disappears_from must be a node name or a non-empty list of node names"),
    ({**NEW, "disappears_from": ["up1"], "including_received_only": "yes"},
     "intent[0]: including_received_only must be true or false (unquoted), got 'yes'"),
    ({**NEW, "best_path_on": ["edge1"], "to": {"med": 1}},
     "intent[0]: best_path_on takes one node name (one line per node)"),
    ({**NEW, "best_path_on": "edge1"},
     "intent[0]: best_path_on needs `to:` (the attributes that change, with their new values)"),
    ({**NEW, "best_path_on": "edge1", "to": {}}, "intent[0]: to must be a non-empty mapping of attributes"),
    ({**NEW, "advertisement": {"node": "edge1"}, "goes": "added"},
     "intent[0]: advertisement must be a mapping with exactly node and neighbor"),
    ({**NEW, "advertisement": {"node": "edge1", "neighbor": "x"}, "goes": "added"},
     "intent[0]: advertisement.neighbor must be an IP address, got 'x'"),
    ({**ADV}, "intent[0]: an advertisement line needs exactly one of `goes: added|removed` or `to:`"),
    ({**ADV, "goes": "down"}, "intent[0]: goes must be added or removed for an advertisement, got 'down'"),
    ({**ADV, "to": {}}, "intent[0]: to must be a non-empty mapping of attributes"),
    ({**ADV, "goes": "removed", "with": {"med": 1}},
     "intent[0]: `with:` goes with `goes: added` only (the new advertisement's attributes)"),
    ({**ADV, "goes": "added", "with": {}}, "intent[0]: with must be a non-empty mapping of attributes"),
])
def test_each_refusal_names_the_line_and_the_key(line, message):
    """Every refusal of an intent line names the line (intent[i]) and the key at fault, the only pointer the user gets
    to what to fix; a refusal without them (or with None) is a refusal nobody can act on."""
    assert refused(line) == message


def test_a_bad_prefix_is_refused_with_the_line_named():
    """A prefix with host bits is refused, and the refusal names the line."""
    assert refused({"prefix": "10.0.0.1/24", "appears_on": ["up1"]}).startswith("intent[0]: bad prefix '10.0.0.1/24': ")


# ============================================================================================ intent: one line per thing

@pytest.mark.parametrize("first,second,message", [
    ({"session": {"node": "edge1", "neighbor": "10.0.2.2", "afi": "ipv4-unicast"}, "goes": "down"},
     {"session": {"node": "edge1", "neighbor": "10.0.2.2", "afi": "ipv4-unicast"}, "goes": "down"},
     "intent[1]: about the same session as intent[0] (edge1, default, 10.0.2.2, ipv4-unicast); merge them into one line"),
    ({**ADV, "goes": "added"}, {**ADV, "goes": "removed"},
     "intent[1]: about the same advertisement as intent[0] (edge1, default, 10.100.0.0/24, 198.51.100.9); "
     "merge them into one line"),
    ({"config_change_on": ["edge1"]}, {"config_change_on": ["up1", "edge1"]},
     "intent[1]: about the same config as intent[0] (edge1); merge them into one line"),
    ({**NEW, "appears_on": ["up1"]}, {**NEW, "disappears_from": ["up1"]},
     "intent[1]: about the same route as intent[0] (up1, default, 10.101.0.0/24); merge them into one line"),
])
def test_two_lines_about_the_same_thing_are_refused_naming_what(first, second, message):
    """Two lines about one session, advertisement, config or route are refused, and the refusal says which kind of
    thing and which one (a config line is about the config, not a route with no prefix)."""
    assert refused(first, second) == message


# ============================================================================================ engine: diff and views

def _config_edit():
    after = base()
    after.configure("up1", " neighbor 10.0.2.1 description x")
    return after


def test_the_running_config_is_an_item_in_the_default_vrf():
    """A node's running config is one diff item keyed (config, node, default): the key the report and the
    config_change_on line both use."""
    (d,) = diff(base().snap(), _config_edit().snap())
    assert d.key == ItemKey("config", "up1", "default")


def test_diff_refusal_says_the_node_sets_differ():
    """Snapshots of different node sets are refused with the reason, not a bare error."""
    b = base().snap()
    del b.nodes["peer1"]
    with pytest.raises(VerifyError, match=r"^the snapshots cover different nodes \(before: "):
        diff(base().snap(), b)


def test_route_state_is_empty_for_items_that_are_not_routes():
    """Sessions, VRFs and configs have no route state: the report shows nothing, never "absent"."""
    idx = Index(base().snap())
    for key in (ItemKey("session", "edge1", "default", neighbor="10.0.1.2"), ItemKey("vrf", "edge1", "default"),
                ItemKey("config", "edge1", "default")):
        assert route_state(idx, key) == ""
    assert route_state(idx, ItemKey("rib", "edge1", "default", "ipv4", "unicast", "10.100.0.0/24",
                                    protocol="bgp")) == "selected and in the FIB"


def test_far_ends_pair_across_vrfs_when_no_same_vrf_candidate_exists():
    """A session whose two ends sit in different VRFs is still one session: with no candidate in the same VRF, the
    only candidate pairs (or a session going down on it would leave its far end undeclared)."""
    lab = base()
    lab.drop("edge1", "session", neighbor="10.0.2.2")
    lab.session("edge1", "10.0.2.2", session("10.0.2.1", remote_as=65002), vrf="red")
    far = far_ends(Snapshot({n: NodeSnapshot(n, "frr", ("default", "red"), dict(items), config=lab.configs[n])
                             for n, items in lab.items.items()}))
    assert far[("edge1", "red", "10.0.2.2")] == ("up1", "default", "10.0.2.1")
    assert far[("up1", "default", "10.0.2.1")] == ("edge1", "red", "10.0.2.2")


# ============================================================================================ engine: config lines

def _changed(before, after):
    return config_lines_changed(DiffItem(ItemKey("config", "edge1", "default"), tuple(before), tuple(after)))


@pytest.mark.parametrize("before,after,added,removed", [
    (["x", "x"], ["x", "x", "x"], ["x"], []),
    (["x"], ["x", "x"], ["x"], []),
    (["x", "x"], ["x"], [], ["x"]),
    (["x", "x", "y"], ["x", "x", "z"], ["z"], ["y"]),
])
def test_config_lines_are_compared_as_multisets(before, after, added, removed):
    """A repeated config line counts once per occurrence: one more copy is one added line, one fewer is one
    removed line, and equal copies cancel exactly."""
    assert _changed(before, after) == {"added": added, "removed": removed}


def test_reordered_config_lines_are_listed_as_order_changes():
    """The same lines in another order are a change (FRR's order is the config's): every moved line is listed."""
    assert _changed(["x", "y", "z"], ["y", "x", "z"]) == {
        "added": ["(the order of the lines changed: y)", "(the order of the lines changed: x)"], "removed": []}


# ============================================================================================ engine: match

def test_a_line_that_did_not_happen_does_not_cover_its_nodes_config():
    """A node's config change is covered by a declared change on that node only when the line happened: a line
    that didn't happen leaves the config change undeclared too."""
    m = run(base(), _config_edit(), [{**NEW, "appears_on": ["up1"]}])
    assert m.status == "failed"
    assert [d.key for d in m.undeclared] == [ItemKey("config", "up1", "default")]
    assert m.untested == {}


def test_config_change_on_reason_lists_every_node_that_did_not_change():
    assert reason(base(), base(), {"config_change_on": ["edge1", "up1"]}) == \
        "the running config of edge1, up1 did not change"


# ============================================================================================ engine: disappears_from

def test_disappears_from_a_route_that_was_never_there():
    """A route absent before gets no hint about received-only routes: there was nothing to receive."""
    assert reason(base(), base(), {**NEW, "disappears_from": ["up1"]}) == "up1: the route was absent before"


def test_disappears_from_a_received_only_route_says_what_to_declare():
    """A route only received before (not selected) can only disappear with including_received_only: the reason
    says so."""
    before = base()
    before.adj_in("up1", "10.0.2.1", "10.101.0.0/24", attrs(as_path="65000 65101", next_hop="10.0.2.1"))
    assert reason(before, base(), {**NEW, "disappears_from": ["up1"]}) == (
        "up1: the route was received (not selected) before (a received-only route needs including_received_only: true)")


def test_disappears_from_while_still_received_names_every_neighbor():
    before, after = base(), base()
    after.drop("edge1", "path", "10.100.0.0/24")
    after.drop("edge1", "rib", "10.100.0.0/24")
    for nbr in ("10.0.2.2", "10.0.1.2"):
        after.adj_in("edge1", nbr, "10.100.0.0/24", attrs(as_path="65101", next_hop=nbr))
    line = {"prefix": "10.100.0.0/24", "disappears_from": ["edge1"], "including_received_only": True}
    assert reason(before, after, line) == "edge1: still received (before inbound policy) from 10.0.1.2, 10.0.2.2"


def test_a_discard_route_can_disappear():
    """A blackhole route (selected and in the FIB, dropping traffic) was there before: its removal is a declarable
    disappearance."""
    before = base()
    (entry,) = rib("static", hops=("10.0.2.1",), distance=1)
    hole = replace(nh("10.0.2.1"), kind="blackhole", ip=None, interface=None)
    before.rib("up1", "10.77.0.0/24", (replace(entry, nexthops=canon_set([hole])),))
    m = run(before, base(), [{"prefix": "10.77.0.0/24", "disappears_from": ["up1"]}])
    assert m.status == "matched", [r.reason for r in m.lines]
    assert m.lines[0].details[0]["before"]["state"].startswith("selected and in the FIB as a discard route")


# ============================================================================================ engine: advertisement

def _advertised(**kw):
    after = base()
    after.adj_out("edge1", "198.51.100.9", "10.100.0.0/24",
                  attrs(**{"as_path": "65101", "next_hop": "198.51.100.8", **kw}))
    return after


WHERE = "edge1: the advertisement of 10.100.0.0/24 to 198.51.100.9"


def test_advertisement_added_reason_compares_with_the_best_path():
    """Each rewritten attribute is named with the advertised value and the best path's value, in order."""
    assert reason(base(), _advertised(med=50, origin="incomplete"), {**ADV, "goes": "added"}) == (
        f"{WHERE}: origin is incomplete, the best path has igp; med is 50, the best path has null")


def test_advertisement_added_reason_compares_with_the_declared_value():
    assert reason(base(), _advertised(med=50), {**ADV, "goes": "added", "with": {"med": 40}}) == \
        f"{WHERE}: med is 50, declared 40"


def test_advertisement_added_with_another_nodes_address_as_next_hop_is_a_rewrite():
    """A next hop that is neither the best path's nor one of the advertising node's own addresses is an outbound
    rewrite, even when it is another lab node's session address."""
    assert reason(base(), _advertised(next_hop="10.0.2.2"), {**ADV, "goes": "added"}) == (
        f"{WHERE}: next_hop is [10.0.2.2]: neither the best path's [10.0.1.2] nor edge1 itself (an outbound "
        "rewrite needs with: next_hop)")


def test_a_pinned_next_hop_is_compared_with_the_pin_only():
    """With next_hop pinned, a mismatch is one disagreement with the pin, not also a self-next-hop complaint."""
    line = {**ADV, "goes": "added", "with": {"next_hop": "10.0.9.9"}}
    assert reason(base(), _advertised(next_hop="10.0.2.2"), line) == f"{WHERE}: next_hop is [10.0.2.2], declared [10.0.9.9]"


def test_advertisement_added_without_a_best_path_says_why():
    after = base()
    after.adj_out("edge1", "198.51.100.9", "10.77.0.0/24", attrs(as_path="", next_hop="198.51.100.8"))
    line = {"prefix": "10.77.0.0/24", "advertisement": OUT, "goes": "added"}
    assert reason(base(), after, line) == ("edge1: the advertisement of 10.77.0.0/24 to 198.51.100.9 appeared, but "
                                           "edge1 has no BGP best path for it to compare the advertised attributes with")


def test_advertisement_removed_reasons():
    """A removal that didn't happen says whether the advertisement is still there or never existed."""
    own = {"prefix": "192.0.2.0/24", "advertisement": OUT, "goes": "removed"}
    assert reason(base(), base(), own) == "edge1: the advertisement of 192.0.2.0/24 to 198.51.100.9 is still there"
    assert reason(base(), base(), {**ADV, "goes": "removed"}) == f"{WHERE} did not exist before"


def test_advertisement_changed_reason_lists_every_wrong_value():
    before = _advertised()
    line = {**ADV, "to": {"med": 50, "origin": "egp"}}
    assert reason(before, _advertised(med=40, origin="incomplete"), line) == \
        f"{WHERE}: med is 40, declared 50; origin is incomplete, declared egp"


def test_advertisement_changed_reason_lists_every_unlisted_change():
    after = _advertised(med=50, origin="incomplete", communities=["no-export"])
    assert reason(_advertised(), after, {**ADV, "to": {"med": 50}}) == \
        f"{WHERE}: attributes not listed in `to:` changed too: origin, communities"


def test_a_received_pin_with_no_candidate_path_is_refused_never_a_crash():
    """`state: received` with a BGP pin, on a route with no received-only path and no adj-in entry (its only BGP
    path is the best one, not installed: FRR `table-map`): the line is refused, naming why (Layer 6 review, 0.4)."""
    from netdryrun.verify.engine import RouteView, _pins_ok
    assert _pins_ok({"as_path": "65002"}, RouteView(), "received") == "no received path matches every pinned attribute"


def test_the_intent_file_is_read_as_utf8_whatever_the_locale(tmp_path, monkeypatch):
    """Read under latin-1, UTF-8 byte 0x85 is NEL, a YAML line break: a commented-out `allow_anywhere` entry would
    become live and widen what may change (Layer 6 review, 0.4). The file is always read as UTF-8."""
    import codecs
    from pathlib import Path

    from netdryrun.verify.intent import load_intent
    f = tmp_path / "intent.yml"
    f.write_bytes("intent: []\nallow_anywhere:\n- 10.9.9.0/24\n#Å- 10.0.0.0/8\n".encode("utf-8"))
    real = Path.read_text
    seen = []

    def read_text(self, *args, **kwargs):
        seen.append(kwargs.get("encoding", args[0] if args else None))
        return real(self, *args, **kwargs)
    monkeypatch.setattr(Path, "read_text", read_text)
    load_intent(f)
    assert seen and all(e is not None and codecs.lookup(e).name == "utf-8" for e in seen)
