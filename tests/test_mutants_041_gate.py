"""Malformed entries for the prefix asked, with the exact error a user reads (0.4.1 gate). Tests that fed a malformed
entry under another prefix pinned these before; since an answer for another prefix is an error of its own (64bfd0f),
the entry has to be under the asked prefix to reach these checks."""
import json

import pytest

from netdryrun.drivers import DriverError, eos, frr, junos

J = json.dumps
P = "10.1.0.0/16"


@pytest.mark.parametrize("entry", [{}, {"protocol": 3}, "x"])
def test_frr_route_entry_without_a_protocol(entry):
    with pytest.raises(DriverError) as e:
        frr.parse_routes(J({P: [entry]}), P)
    assert str(e.value) == f"unexpected output from `show ip route <prefix> json`: {P}: {entry}"


@pytest.mark.parametrize("entry", [{"bgpRoutePaths": "x"}, {"bgpRoutePaths": {}}, {}, "x", {"bgpRoutePaths": "y" * 200}])
def test_eos_bgp_entry_without_a_path_list(entry):
    """The entry is quoted up to 150 characters."""
    text = J({"vrfs": {"default": {"vrf": "default", "routerId": "1.1.1.1", "asn": "65001",
                                   "bgpRouteEntries": {P: entry}}}})
    with pytest.raises(DriverError) as e:
        eos.parse_bgp_paths(text, P)
    assert str(e.value) == f"unexpected output from `show ip bgp <prefix> | json`: {P}: {str(entry)[:150]}"


@pytest.mark.parametrize("value", [[1], ["x", {}], "x", {}])
def test_junos_items_that_are_not_a_list_of_objects(value):
    with pytest.raises(DriverError) as e:
        junos._items("show route", {"rt": value}, "rt")
    assert str(e.value) == f"unexpected output from `show route`: rt: {value}"
