"""SR Linux `bgp_prefixes`: a route that fails AS-loop detection must not count (0.4.1 item, waiting for its live capture).

Known limit (tests/compat_verified.json, SR Linux): the driver counts the neighbor's `received-routes`, which on SR Linux 26.7.2
includes routes that fail BGP loop detection and are unusable. A live run on 2026-10-28 read 3 where one prefix was usable and
`rejected-routes` read 0, so `min` and `exact` can pass on a count that includes unusable routes.

The capture that run came from was not kept, and the existing fixtures (`srl_bgp_neighbors.txt`: received 1, active 1,
rejected 0) have no looped route, so there is no honest red test to write yet. Writing one from an assumed counter would
codify a guess. What the live capture must contain, taken once under the lab lock:
  1. the `examples/srl-frr` lab with the FRR peer advertising one usable prefix and two prefixes whose AS path contains the
     SR Linux router's own AS (the second FRR peer or `set as-path prepend <srl ASN>` on the peer's outbound route-map);
  2. `info from state /network-instance default protocols bgp neighbor *` (the counters: received-routes, active-routes,
     rejected-routes, suppressed-routes, received-routes-withdrawn-due-to-error);
  3. the per-route listing that marks usable routes (`.../neighbor <ip> received-routes ipv4` and `.../local-rib`), to find the
     field or the counter that excludes the looped routes.
Then: the fixture goes in tests/fixtures as `srl_bgp_neighbors_loop.txt`, the red test below asserts the count equals the usable
routes (1, not 3), the driver reads that counter, and every SR Linux `bgp_prefixes` must-fail cell stays red-then-green.
"""
import pytest

pytestmark = pytest.mark.skip(reason="needs the live SR Linux capture with AS-loop routes (see the module docstring)")


def test_a_route_that_fails_as_loop_detection_is_not_counted():
    raise AssertionError("write this from srl_bgp_neighbors_loop.txt once it is captured")
