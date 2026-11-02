"""SR Linux `bgp_prefixes`: a route that fails AS-loop detection is not counted (0.4.1).

SR Linux 26.7.2 counts a route that fails BGP loop detection in the neighbor's `received-routes` and not in
`rejected-routes`, so received minus rejected over-counted: `min` and `exact` could pass on routes that are unusable.
Captured live on 2026-11-02 from `examples/srl-frr` unchanged (FRR's allow-all export sends SR Linux's own two routes
back with 65010 in the AS path): the neighbor reads received 3, active 1, rejected 0, and the local RIB holds the two
looped routes as paths from 10.0.100.2 with `invalid-reason: {as-loop: true}`. The driver now subtracts those. FRR
drops such routes and Junos doesn't accept them, so the counts agree across drivers.
"""
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
    assert srlinux.parse_as_loop_counts(read("srl_bgp_rib_loop.txt")) == {"10.0.100.2": 2}
    assert srlinux.parse_as_loop_counts("{\n}") == {}


RIB = f"unexpected output from `{srlinux.RIB_TREE_CMD}`: "


@pytest.mark.parametrize("text,detail", [
    ('{"local-rib": {"route": [{"prefix": "10.0.0.0/8", "neighbor": "10.0.0.2", "invalid-reason": {"next-hop-unresolved": true}}]}}',
     "10.0.0.0/8 from 10.0.0.2: invalid-reason {'next-hop-unresolved': True} is not one this driver reads"),
    ('{"local-rib": {"route": [{"prefix": "10.0.0.0/8", "invalid-reason": {"as-loop": true}}]}}',
     "10.0.0.0/8 from None: a looped path without a neighbor"),
    ('{"local-rib": {"routes": []}}', "{'local-rib': {'routes': []}}"),
    ('{"rib-in-out": {}}', "{'rib-in-out': {}}"),
], ids=["unknown-reason", "looped-without-neighbor", "routes-renamed", "no-local-rib"])
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
