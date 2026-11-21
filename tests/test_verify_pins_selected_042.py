"""`with:` pins on appears_on describe the route the node selects (oracle FP-042-VERIFYPINSTATIC, red team 042-GV
B-RT-0077, RT-0077).

0.4.0 and 0.4.1 compared BGP pins with bgpd's best path only, and protocol, distance and metric pins with the first
selected RIB entry; every RIB entry for the prefix was explained. So a distance-1 static installed beside the pinned
BGP path got INTENT MATCHED. Now every selected entry must meet the protocol, distance and metric pins, BGP pins need
every selected entry to be BGP's, and a RIB entry the pins don't describe stays undeclared.
"""
from netdryrun.verify.engine import RouteView, _pinned_items, _pins_ok, _rib_pins_ok, match
from verify_helpers import base, intent, path, rib

P = "10.101.0.0/24"
PINS = {"from": "10.0.1.2", "as_path": "65101"}
PARSED = intent([{"prefix": P, "appears_on": "edge1", "with": PINS}]).lines[0].pins   # as the engine gets them


def run(after, line):
    return match(base().snap(), after.snap(), intent([line]))


def _bgp(lab, selected=True):
    lab.path("edge1", P, "10.0.1.2", path(best=True, as_path="65101", next_hop="10.0.1.2"))
    lab.rib("edge1", P, rib(hops=("10.0.1.2",), selected=selected, fib=selected))
    return lab


def static_wins():
    """bgpd keeps its best path from 10.0.1.2; zebra selects and installs a distance-1 static via 10.0.3.2."""
    lab = _bgp(base(), selected=False)
    lab.rib("edge1", P, rib("static", hops=("10.0.3.2",), distance=1), protocol="static")
    return lab


def bgp_wins_with_floating_static():
    """The pinned BGP path is selected and installed; a new floating static (distance 250) sits beside it."""
    lab = _bgp(base())
    lab.rib("edge1", P, rib("static", hops=("10.0.3.2",), selected=False, fib=False, distance=250), protocol="static")
    return lab


def test_bgp_pins_fail_when_a_static_is_the_selected_route():
    m = run(static_wins(), {"prefix": P, "appears_on": "edge1", "with": PINS})
    assert m.status == "failed"
    assert m.lines[0].reason == ("edge1: the selected route is a static route, not BGP, so BGP attributes can't "
                                 "match")


def test_the_same_change_without_pins_still_matches():
    assert run(static_wins(), {"prefix": P, "appears_on": "edge1"}).status == "matched"


def test_a_protocol_static_pin_meets_the_static_that_wins_but_leaves_the_bgp_entry_undeclared():
    m = run(static_wins(), {"prefix": P, "appears_on": "edge1", "with": {"protocol": "static", "distance": 1}})
    assert m.lines[0].happened, m.lines[0].reason
    assert m.status == "failed"
    assert {(d.key.kind, d.key.protocol) for d in m.undeclared} == {("rib", "bgp")}


def test_bgp_pins_leave_a_static_rib_entry_beside_the_pinned_route_undeclared():
    m = run(bgp_wins_with_floating_static(), {"prefix": P, "appears_on": "edge1", "with": PINS})
    assert m.lines[0].happened, m.lines[0].reason
    assert m.status == "failed"
    assert {(d.key.kind, d.key.protocol) for d in m.undeclared} == {("rib", "static")}
    # the pinned BGP path alone is matched (the oracle's guard, here on the unit fixtures)
    assert run(_bgp(base()), {"prefix": P, "appears_on": "edge1", "with": PINS}).status == "matched"


def test_a_protocol_pin_alone_also_leaves_another_protocols_entry_undeclared():
    m = run(bgp_wins_with_floating_static(), {"prefix": P, "appears_on": "edge1", "with": {"protocol": "bgp"}})
    assert m.lines[0].happened and m.status == "failed"
    assert {(d.key.kind, d.key.protocol) for d in m.undeclared} == {("rib", "static")}


def _two_selected():
    return RouteView(rib={"bgp": rib(hops=("10.0.1.2",)), "static": rib("static", hops=("10.0.3.2",), distance=1)})


def test_every_selected_entry_must_meet_a_rib_pin_not_only_the_first():
    v = _two_selected()
    assert _pins_ok({"protocol": "bgp"}, v, "installed") == "protocol is static, pinned bgp"
    assert _pins_ok({"protocol": "static"}, v, "installed") == "protocol is bgp, pinned static"
    assert _pins_ok({"distance": 20}, v, "installed") == "distance is 1, pinned 20"
    assert _pins_ok({"metric": 0}, v, "installed") == ""


def test_bgp_pins_with_a_bgp_and_a_static_selected_name_the_static():
    v = _two_selected()
    v.paths[("10.0.1.2", 0)] = path(best=True, as_path="65101", next_hop="10.0.1.2")
    assert _pins_ok(PARSED, v, "installed") == ("the selected route is a static route, not BGP, so BGP attributes "
                                              "can't match")
    del v.rib["static"]
    assert _pins_ok(PARSED, v, "installed") == ""


def test_no_selected_route_for_a_rib_pin():
    v = RouteView(rib={"bgp": rib(selected=False, fib=False)})
    assert _pins_ok({"distance": 20}, v, "selected") == "no selected route to compare distance with"


def test_rib_pins_ok_per_entry():
    static = rib("static", distance=1)
    assert _rib_pins_ok(static, {})
    assert _rib_pins_ok(static, {"protocol": "static", "distance": 1, "metric": 0})
    assert not _rib_pins_ok(static, {"protocol": "static", "distance": 2})
    assert not _rib_pins_ok(static, {"metric": 7})
    assert not _rib_pins_ok(static, {"from": "10.0.1.2"})          # BGP pins describe BGP's entry only
    assert _rib_pins_ok(rib(), {"from": "10.0.1.2", "protocol": "bgp"})
    two = rib("static", distance=1) + rib("static", selected=False, fib=False, distance=250)
    assert not _rib_pins_ok(two, {"distance": 1})                  # every entry of the tuple, not any


def test_pinned_items_explain_paths_from_the_pinned_neighbor_and_the_described_rib_entries():
    after = bgp_wins_with_floating_static()
    after.path("edge1", P, "10.0.9.9", path(best=False, as_path="65999", next_hop="10.0.9.9"))
    m = match(base().snap(), after.snap(), intent([]))
    items = [d for d in m.undeclared if d.key.prefix == P and d.key.kind in ("rib", "path", "adj_in")]
    view = RouteView(rib={"bgp": after.get("edge1", "rib", P, protocol="bgp"),
                          "static": after.get("edge1", "rib", P, protocol="static")},
                     paths={("10.0.1.2", 0): after.get("edge1", "path", P, neighbor="10.0.1.2"),
                            ("10.0.9.9", 0): after.get("edge1", "path", P, neighbor="10.0.9.9")})
    got = {(k.kind, k.protocol or k.neighbor) for k in _pinned_items(items, view, PARSED)}
    assert got == {("rib", "bgp"), ("path", "10.0.1.2")}
    got = {(k.kind, k.protocol or k.neighbor) for k in _pinned_items(items, view, {})}
    assert got == {("rib", "bgp"), ("rib", "static"), ("path", "10.0.1.2"), ("path", "10.0.9.9")}
    got = {(k.kind, k.protocol or k.neighbor) for k in _pinned_items(items, view, {"protocol": "static"})}
    assert got == {("rib", "static"), ("path", "10.0.1.2"), ("path", "10.0.9.9")}
