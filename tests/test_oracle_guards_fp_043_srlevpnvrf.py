"""Guards for oracle FP-043-SRLEVPNVRF: they pass before and after its fix.

The fast-fix gate runs tests/oracles/FP-043-SRLEVPNVRF/ and needs every test there to fail on the fix's parent, so the
guards live here, in the unit suite. This file is in the oracle's `evidence:`, so the fix can't change it.
Helpers and the captured data come from the oracle's own module. The guards hold the fix to:
- no path where the EVPN route is gone (leaf2 took lo1.0 out of ipvrf: captures srl2672_fp043_absent_* and
  srl2672_fp043_pece2absent_*): `present: false` still passes there on the current code, and a fix may refuse
  (DriverError) but never reads a path that isn't there;
- the route-target: 10.98.0.0/24 is imported into ipvrf2 only (`imported-network-instances: [ipvrf2]`), so a positive
  `bgp_route vrf ipvrf` for it must not pass (a fix that reads every type-5 route for the prefix would pass it);
- the published workaround (`route ... protocol: bgp present: false`) keeps failing while the route is imported.
"""
import importlib.util
import json
from pathlib import Path

import pytest

from netdryrun.checks import run_check
from netdryrun.config import _validate_check
from netdryrun.drivers.base import DriverError
from netdryrun.drivers.srlinux import SrlDriver

_PATH = Path(__file__).resolve().parent / "oracles" / "FP-043-SRLEVPNVRF" / "test_oracle_fp_043_srlevpnvrf.py"
_SPEC = importlib.util.spec_from_file_location("oracle_fp_043_srlevpnvrf", _PATH)
o = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(o)


def _evpn_prefixes(tag: str) -> dict:
    rib = json.loads(o.fx(f"srl2672_fp043_{tag}_leaf1_default_bgp_rib_evpn.json"))["local-rib"]["ip-prefix-route"]
    # leaf1's own type-5 routes (design B: 10.77.0.0/24 and 10.1.0.0/30 from ipvrf, neighbor 0.0.0.0) have no
    # imported-network-instances
    return {r["ip-prefix"]: r.get("imported-network-instances") for r in rib}


@pytest.mark.parametrize("tag", ["absent", "pece2absent"])
def test_the_absent_captures_hold_no_route_for_the_prefix(tag):
    assert o.PREFIX not in _evpn_prefixes(tag)
    assert _evpn_prefixes(tag)["10.98.0.0/24"] == ["ipvrf2"]
    assert json.loads(o.fx(f"srl2672_fp043_{tag}_leaf1_ipvrf_route_table_route.json")) == {}
    assert json.loads(o.fx(f"srl2672_fp043_{tag}_leaf1_ipvrf_bgp_rib_route.json")) == {}


@pytest.mark.parametrize("tag", ["absent", "pece2absent"])
def test_no_path_is_read_where_the_route_is_gone(tag):
    try:
        paths = SrlDriver(o.CapturedLab(tag), "leaf1").bgp_paths(o.PREFIX, "ipvrf").value
    except DriverError:
        return
    assert paths == []


@pytest.mark.parametrize("tag", ["absent", "pece2absent"])
def test_present_false_passes_where_the_route_is_gone(tag):
    """Without the route, ipvrf's bgp-rib, route table and EVPN RIB have nothing for the prefix (design B: and the
    session to ce1 is up; srl2672_fp043_pece2absent_run.txt passed it live). A fix must pass here, or refuse only for a
    read these captures don't hold ("not captured": the guard can't know what leaf1 would have said). Captured: ipvrf's
    bgp-rib and protocols, the default network-instance's EVPN RIB (`bgp-rib afi-safi evpn evpn` and its `local-rib`)
    and attr-sets. `local-rib ip-prefix-route *` is not: SR Linux 26.7.2 refused it (rc 1, "Missing mandatory
    arguments ['ethernet-tag-id', 'ip-prefix', 'ip-prefix-length', 'neighbor', 'path-id']")."""
    if tag == "pece2absent":
        report = json.loads(o.fx("srl2672_fp043_pece2absent_report.json"))
        assert {c["name"]: c["passed"] for c in report["checks"]} == {
            "pece-ce-session-up": True, "pece-evpn-bgp-route-absent-must-fail": True,
            "pece-evpn-route-bgp-absent-must-fail": True}
    r = o.check(tag, present=False)
    assert r.passed or "not captured" in str(r.detail), r.detail


def test_a_route_imported_into_another_ip_vrf_is_not_a_path_in_this_one():
    assert _evpn_prefixes("present")["10.98.0.0/24"] == ["ipvrf2"]
    c = o.Clock()
    chk = _validate_check(0, {"node": "leaf1", "type": "bgp_route", "vrf": "ipvrf", "prefix": "10.98.0.0/24"}, 20)
    r = run_check(chk, SrlDriver(o.CapturedLab("present"), "leaf1"), clock=c, sleep=c.sleep)
    assert not r.passed, r.detail


@pytest.mark.parametrize("tag", ["present", "pece2"])
def test_the_workaround_fails_while_the_route_is_imported(tag):
    c = o.Clock()
    chk = _validate_check(0, {"node": "leaf1", "type": "route", "vrf": "ipvrf", "prefix": o.PREFIX, "protocol": "bgp",
                              "present": False}, 20)
    r = run_check(chk, SrlDriver(o.CapturedLab(tag), "leaf1"), clock=c, sleep=c.sleep)
    assert not r.passed and "bgp-evpn" in r.detail, r.detail
