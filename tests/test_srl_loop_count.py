"""SR Linux `bgp_prefixes`: a route that fails AS-loop detection is not counted (0.4.1).

SR Linux 26.7.2 counts a route that fails BGP loop detection in the neighbor's `received-routes` and not in
`rejected-routes`, so received minus rejected over-counted: `min` and `exact` could pass on routes that are unusable.
Captured live on 2026-11-02 from `examples/srl-frr` unchanged (FRR's allow-all export sends SR Linux's own two routes
back with 65010 in the AS path): the neighbor reads received 3, active 1, rejected 0, and the local RIB holds the two
looped routes as paths from 10.0.100.2 with `invalid-reason: {as-loop: true}`. The driver now subtracts those. FRR
drops such routes and Junos doesn't accept them, so the counts agree across drivers.
"""
import json

import pytest

from netdryrun.drivers import srlinux
from netdryrun.drivers.base import DriverError
from netdryrun.lab import ExecResult
from pathlib import Path

FIX = Path(__file__).parent / "fixtures"


def read(name: str) -> str:
    return (FIX / name).read_text(encoding="utf-8")


class Lab:
    def __init__(self, rules):
        self.rules, self.calls = rules, []

    def exec(self, node, cmd, timeout=60, input=None):
        line = " ".join(cmd)
        self.calls.append(line)
        for needle, answer in self.rules:
            if needle in line:
                return ExecResult(cmd, 0, answer, "")
        raise AssertionError(f"unexpected command: {line}")


def lab():
    return Lab([("protocols bgp neighbor", read("srl_bgp_neighbors_loop.txt")),
                ("bgp-rib afi-safi ipv4-unicast ipv4-unicast", read("srl_bgp_rib_loop.txt"))])


def test_the_counter_alone_over_counts():
    # the neighbor counters by themselves: 3 received, 0 rejected (the over-count the fix removes)
    assert srlinux.parse_bgp_neighbors(read("srl_bgp_neighbors_loop.txt"))["10.0.100.2"].prefixes == {"ipv4-unicast": 3}


def test_a_route_that_fails_as_loop_detection_is_not_counted():
    lab_ = lab()
    n = srlinux.SrlDriver(lab_, "srl1").bgp_neighbors()
    assert n.value["10.0.100.2"].prefixes == {"ipv4-unicast": 1}
    assert lab_.calls[-1].endswith("info from state /network-instance default bgp-rib afi-safi ipv4-unicast ipv4-unicast")


def test_as_loop_counts_per_neighbor():
    assert srlinux.parse_as_loop_counts(read("srl_bgp_rib_loop.txt")) == {"10.0.100.2": (2, 0)}
    assert srlinux.parse_as_loop_counts("{\n}") == {}


RIB = f"unexpected output from `{srlinux.RIB_TREE_CMD}`: "


@pytest.mark.parametrize("text,detail", [
    ('{"local-rib": {"route": [{"prefix": "10.0.0.0/8", "invalid-reason": {"as-loop": true}}]}}',
     "10.0.0.0/8 from None: an invalid path without a neighbor"),
    ('{"local-rib": {"routes": []}}', "{'local-rib': {'routes': []}}"),
    ('{"rib-in-out": {}}', "{'rib-in-out': {}}"),
], ids=["looped-without-neighbor", "routes-renamed", "no-local-rib"])
def test_as_loop_count_errors(text, detail):
    with pytest.raises(DriverError) as e:
        srlinux.parse_as_loop_counts(text)
    assert str(e.value) == RIB + detail


def test_more_looped_routes_than_received_is_an_error():
    rib = read("srl_bgp_rib_loop.txt").replace('"10.0.100.0/30"', '"10.0.100.4/30"')  # same loops, counted again
    lab_ = Lab([("protocols bgp neighbor", read("srl_bgp_neighbors_loop.txt").replace('"received-routes": 3', '"received-routes": 1')),
                ("bgp-rib afi-safi ipv4-unicast ipv4-unicast", rib)])
    with pytest.raises(DriverError) as e:
        srlinux.SrlDriver(lab_, "srl1").bgp_neighbors()
    assert str(e.value) == (f"unexpected output from `{srlinux.NEIGHBORS_CMD}`: "
                            "10.0.100.2 ipv4-unicast: 2 looped routes but a count of 1 (received minus rejected)")


def _two_neighbors(first_received: int, second_family_up: bool = True) -> str:
    """Two neighbors: 10.0.0.1 (no looped paths) listed first, then 10.0.100.2 (two looped paths in the live RIB)."""
    import json
    d = json.loads(read("srl_bgp_neighbors_loop.txt"))
    other = json.loads(json.dumps(d["neighbor"][0]))
    other["peer-address"] = "10.0.0.1"
    for af in other["afi-safi"]:
        if af["afi-safi-name"] == "ipv4-unicast":
            af["received-routes"] = first_received
    if not second_family_up:
        for af in d["neighbor"][0]["afi-safi"]:
            if af["afi-safi-name"] == "ipv4-unicast":
                af.update({"oper-state": "down", "admin-state": "disable"})
                for k in ("received-routes", "rejected-routes", "active-routes", "suppressed-routes"):
                    af.pop(k, None)
    d["neighbor"] = [other] + d["neighbor"]
    return json.dumps(d)


def _driver(neighbors: str):
    return srlinux.SrlDriver(Lab([("protocols bgp neighbor", neighbors),
                                  ("bgp-rib afi-safi ipv4-unicast ipv4-unicast", read("srl_bgp_rib_loop.txt"))]), "srl1")


def test_every_neighbor_gets_its_own_loops_off():
    """A neighbor without looped paths (listed first) doesn't stop the next one's loops coming off."""
    n = _driver(_two_neighbors(first_received=4)).bgp_neighbors().value
    assert n["10.0.0.1"].prefixes == {"ipv4-unicast": 4} and n["10.0.100.2"].prefixes == {"ipv4-unicast": 1}


def test_loops_of_a_family_a_neighbor_doesnt_count_are_ignored():
    """10.0.100.2's IPv4 family is down here (not counted) while the RIB still lists its looped paths."""
    n = _driver(_two_neighbors(first_received=4, second_family_up=False)).bgp_neighbors().value
    assert n["10.0.0.1"].prefixes == {"ipv4-unicast": 4} and n["10.0.100.2"].prefixes == {}


def test_as_many_looped_routes_as_received_counts_zero():
    neighbors = read("srl_bgp_neighbors_loop.txt").replace('"received-routes": 3', '"received-routes": 2')
    assert _driver(neighbors).bgp_neighbors().value["10.0.100.2"].prefixes == {"ipv4-unicast": 0}


# --- Layer 6 on b03cb7a: a path with any reason but exactly {as-loop} or exactly {rejected-route} ------------------

def _nb(received, rejected):
    return ('{"neighbor": [{"peer-address": "10.0.0.2", "session-state": "established", "afi-safi": [{"afi-safi-name": '
            f'"ipv4-unicast", "oper-state": "up", "received-routes": {received}, "rejected-routes": {rejected}}}]}}]}}')


def _rib(*reasons):
    rows = ", ".join('{"prefix": "10.9.%d.0/24", "neighbor": "10.0.0.2", "origin-protocol": "bgp", "valid-route": false, '
                     '"invalid-reason": %s}' % (i, json.dumps(r)) for i, r in enumerate(reasons))
    return '{"local-rib": {"route": [%s]}}' % rows


def _read(received, rejected, *reasons):
    lab_ = Lab([("protocols bgp neighbor", _nb(received, rejected)), ("bgp-rib afi-safi ipv4-unicast", _rib(*reasons))])
    n = srlinux.SrlDriver(lab_, "srl1").bgp_neighbors().value["10.0.0.2"]
    return n.prefixes["ipv4-unicast"], n.prefixes_upto.get("ipv4-unicast")


def test_a_path_both_looped_and_rejected_is_not_subtracted_twice():
    """It may sit in rejected-routes already (then received minus rejected is right) or not (then it comes off): the
    count is a range, so `max: 2` can't pass on 4 received, 1 rejected (it passed on 2)."""
    assert _read(4, 1, {"as-loop": True, "rejected-route": True}) == (2, 3)


def test_an_invalid_reason_the_driver_does_not_know_makes_a_range_not_an_error():
    """next-hop-unresolved: whether SR Linux counts it in received-routes isn't known, so the count is a range; the
    other neighbors' reads go on (it raised and broke every BGP read on the node)."""
    assert _read(3, 0, {"next-hop-unresolved": True}, {"as-loop": True}) == (1, 2)


def test_exact_reasons_stay_exact():
    assert _read(4, 1, {"as-loop": True}, {"rejected-route": True}) == (2, None)


def test_a_range_is_judged_only_when_both_ends_agree():
    from netdryrun.checks import _counted
    from netdryrun.drivers.base import BgpNeighbor
    n = BgpNeighbor("10.0.0.2", "established", {"ipv4-unicast": 2}, prefixes_upto={"ipv4-unicast": 3})
    assert _counted(n, "ipv4-unicast", 2, 0, 2, [])[0] is False


def test_unsure_paths_above_the_count_clip_the_range_at_zero():
    """An unsure path may already be in rejected-routes (both flags: acceptance 0.4.1 on d87aa3e, an import policy
    that rejects looped routes, 2 such paths with a count of 1), so looped plus unsure can outnumber the count: the
    range runs from 0, never below it, and never an error that breaks every BGP read on the node."""
    assert _read(2, 0, {"as-loop": True}, {"as-loop": True}, {"next-hop-unresolved": True}) == (0, 0)
    assert _read(1, 0, {"as-loop": True, "rejected-route": True}, {"as-loop": True, "rejected-route": True}) == (0, 1)
