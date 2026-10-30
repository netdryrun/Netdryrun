"""The fixes for the 0.4 interop findings (research/interop/REPORT.md), beyond the interop agent's own regression
tests (test_interop_04.py): how a `med: 0` check is refused on EOS, and the edges of each change."""
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from netdryrun.config import Check
from netdryrun.drivers import DriverError, check_supported, eos, junos
from netdryrun.lab import Node

FIX = Path(__file__).parent / "fixtures"


def eos_lab():
    return SimpleNamespace(nodes={"a1": Node("a1", "clab-t-a1", "arista_ceos", "ceos:4.36.3M")})


def bgp_route(**params):
    return Check("bgp_route", {"node": "a1", "prefix": "192.168.1.1/32", **params}, "c1", timeout=60)


# ---- IOP-2: EOS prints "med": 0 for a path received with no MED, so a `med: 0` check is refused (exit 2)

def test_a_med_0_check_on_eos_is_refused_before_the_lab_boots():
    with pytest.raises(DriverError) as e:
        check_supported(eos_lab(), bgp_route(med=0))
    assert str(e.value) == ("c1: med: 0 can't be checked on eos: EOS output cannot tell MED 0 from no MED "
                            "(check a non-zero MED, or check this route on another platform)")


def test_a_non_zero_med_check_on_eos_is_accepted_and_reads_the_value():
    check_supported(eos_lab(), bgp_route(med=50))
    check_supported(eos_lab(), bgp_route(as_path="65005 65001"))
    data = json.loads((FIX / "eos_bgp_paths_no_med.txt").read_text())
    for p in data["vrfs"]["default"]["bgpRouteEntries"]["192.168.1.1/32"]["bgpRoutePaths"]:
        p["med"] = 50
    paths = eos.parse_bgp_paths(json.dumps(data), "192.168.1.1/32")
    assert paths and all(p.med == 50 for p in paths)


def test_eos_med_0_reads_as_unknown_so_a_med_0_check_can_never_pass():
    paths = eos.parse_bgp_paths((FIX / "eos_bgp_paths_no_med.txt").read_text(), "192.168.1.1/32")
    assert paths and all(p.med is None for p in paths)


# ---- IOP-3: EOS prints AS sets with spaces; the reference form is {a,b}, as on every other driver

@pytest.mark.parametrize("printed, canon", [
    ("65005 {65004 65006}", "65005 {65004,65006}"),
    ("65005 {65004  65006 65007}", "65005 {65004,65006,65007}"),
    ("{65004}", "{65004}"),
    ("65001 [65010 65011] 65002", "65001 [65010,65011] 65002"),
    ("(65010 65011) 65002", "(65010 65011) 65002"),
    ("65005  65001", "65005 65001"),
    ("", ""),
])
def test_eos_as_path_segments_take_the_reference_form(printed, canon):
    data = json.loads((FIX / "eos_bgp_paths_no_med.txt").read_text())
    for p in data["vrfs"]["default"]["bgpRouteEntries"]["192.168.1.1/32"]["bgpRoutePaths"]:
        p["asPathEntry"]["asPath"] = printed
    paths = eos.parse_bgp_paths(json.dumps(data), "192.168.1.1/32")
    assert paths and all(p.as_path == canon for p in paths)


# ---- IOP-1: Junos omits `metric` when no MED was received

def test_junos_med_0_check_fails_on_a_route_with_no_med():
    from netdryrun.checks import _bgp_route
    from netdryrun.drivers.base import Observation

    paths = junos.parse_bgp_paths((FIX / "junos_route_no_med.txt").read_text(), "192.168.3.1/32", "inet.0")
    d = SimpleNamespace(bgp_paths=lambda prefix, vrf="default": Observation(paths, []))
    ok, detail, _ = _bgp_route(d, {"prefix": "192.168.3.1/32", "med": 0})
    assert not ok and "MED is not set, expected 0" in detail


def test_eos_as_set_printed_with_commas_and_spaces_reads_the_same():
    data = json.loads((FIX / "eos_bgp_paths_no_med.txt").read_text())
    for p in data["vrfs"]["default"]["bgpRouteEntries"]["192.168.1.1/32"]["bgpRoutePaths"]:
        p["asPathEntry"]["asPath"] = "65005 { 65004, 65006 }"
    assert {p.as_path for p in eos.parse_bgp_paths(json.dumps(data), "192.168.1.1/32")} == {"65005 {65004,65006}"}


def test_only_eos_refuses_med_0_and_an_unknown_driver_refuses_nothing():
    frr = SimpleNamespace(nodes={"f1": Node("f1", "clab-t-f1", "linux", "quay.io/frrouting/frr:10.4.1")})
    check_supported(frr, Check("bgp_route", {"node": "f1", "prefix": "10.0.0.0/24", "med": 0}, "c1", timeout=60))
    check_supported(eos_lab(), bgp_route(local_pref=0))
    with pytest.raises(DriverError, match="med: 0 can't be checked on eos"):
        check_supported(eos_lab(), bgp_route(med=0, as_path="65005"))
