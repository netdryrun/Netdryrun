"""cEOS with no BGP configured answers every BGP read with exactly `{"errors": ["BGP inactive"]}`, rc 1 (cEOS 4.36.3M,
eos_bgp_inactive.txt, live 2026-11-08). A `route` check on such a node was an error on every sample (angle-5 live lab
A). Only that exact answer means "no BGP"; any other failure stays an error."""
from __future__ import annotations

from pathlib import Path

import pytest

from netdryrun.drivers.base import DriverError, NoSuchInstance
from netdryrun.drivers.eos import EosDriver

from test_verdict_drivers import Lab

FX = Path(__file__).parent / "fixtures"
INACTIVE = (FX / "eos_bgp_inactive.txt").read_text(encoding="utf-8")
ROUTE = (FX / "eos_route_ospfv3_ipv4.txt").read_text(encoding="utf-8")


def _drv(bgp_answer):
    return EosDriver(Lab([("show ip route", ROUTE), ("show ip bgp", bgp_answer), ("show ipv6 bgp", bgp_answer)]), "e1")


def test_a_route_check_on_a_node_without_bgp_reads_the_routing_table():
    routes = _drv((1, INACTIVE)).routes("10.99.3.2/32").value
    assert [(r.protocol, r.active) for r in routes] == [("ospf", True)]


def test_bgp_paths_on_a_node_without_bgp_are_none():
    assert _drv((1, INACTIVE)).bgp_paths("10.99.3.2/32").value == []


def test_bgp_neighbors_on_a_node_without_bgp_is_no_instance():
    with pytest.raises(NoSuchInstance, match="BGP is not configured on e1"):
        _drv((1, INACTIVE)).bgp_neighbors()


@pytest.mark.parametrize("answer", [
    (1, '{"errors": ["BGP inactive", "and something else"]}'),
    (1, '{"errors": ["% Invalid input"]}'),
    (2, INACTIVE),
    (1, "BGP inactive"),
    (1, ""),
])
def test_any_other_failure_stays_an_error(answer):
    with pytest.raises(DriverError) as e:
        _drv(answer).routes("10.99.3.2/32")
    assert not isinstance(e.value, NoSuchInstance)
