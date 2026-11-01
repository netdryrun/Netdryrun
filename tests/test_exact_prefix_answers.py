"""What each driver's prefix commands answer for a prefix that isn't there, on live captures (2026-11-02,
tests/fixtures/SOURCES.yml): 192.168.20.0/25 asked while 192.168.20.0/24 is installed.

Only cEOS `show ip route <prefix>` answers with the longest match (the covering /24), so only there is a route for
another prefix skipped. Every other command answers for exactly the prefix asked, so a row for another prefix there
is unexpected output (tests in each driver's file), never "not there": read as absent, it made `present: false` pass.
"""
import json
from pathlib import Path

import pytest

from netdryrun.drivers import DriverError, eos, nxos, srlinux

FIXTURES = Path(__file__).parent / "fixtures"
ASKED = "192.168.20.0/25"


def read(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def test_eos_route_answers_with_the_covering_route_and_it_is_skipped():
    text = read("eos_route_longest_match.txt")
    assert "192.168.20.0/24" in text
    assert eos.parse_routes(text, read("eos_bgp_paths_more_specific_absent.txt"), ASKED) == []


def test_eos_bgp_answers_nothing_for_an_absent_prefix():
    assert eos.parse_bgp_paths(read("eos_bgp_paths_more_specific_absent.txt"), ASKED) == []


def test_nxos_answers_nothing_for_an_absent_prefix():
    route, bgp = read("nxos_route_more_specific_absent.txt"), read("nxos_bgp_more_specific_absent.txt")
    assert "192.168.20.0/24" not in route + bgp
    assert nxos.parse_routes(route, bgp, ASKED) == []
    assert nxos.parse_bgp_paths(bgp, ASKED) == []


def test_srlinux_answers_nothing_for_an_absent_prefix():
    rib = read("srl_bgp_rib_more_specific_absent.txt")
    assert srlinux.parse_routes(read("srl_route_more_specific_absent.txt"), ASKED, rib) == []
    assert srlinux.parse_rib_paths(rib, ASKED) == []


def test_eos_bgp_entry_key_that_is_not_a_prefix_names_the_bgp_command():
    data = json.loads(read("eos_bgp_paths_more_specific_absent.txt"))
    data["vrfs"]["default"]["bgpRouteEntries"] = {"x": {"totalPaths": 0, "bgpRoutePaths": []}}
    with pytest.raises(DriverError) as e:
        eos.parse_bgp_paths(json.dumps(data), ASKED)
    assert str(e.value) == "unexpected output from `show ip bgp <prefix> | json`: not a prefix: 'x'"
