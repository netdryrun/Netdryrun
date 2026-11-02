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
