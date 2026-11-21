"""Oracle FP-043-SRLEVPNVRF (red team RT-0058, GHSA-ggcf-664f-c9ff case 2): on SR Linux, `bgp_route present: false` in
an ip-vrf doesn't see an EVPN IP-prefix (type-5) route imported into that ip-vrf.

What the routers showed (SR Linux 26.7.2, containerlab lab srl-evpn-oracle, captured 2026-11-21; lab files
tests/fixtures/srl2672_fp043_*.cli / *.clab.yml / *netdryrun.yml, captures tests/fixtures/srl2672_fp043_*):
- leaf1 and leaf2 run iBGP EVPN (AS 65000) between their system0 addresses in the default network-instance. Each has
  ip-vrf `ipvrf` (vxlan1.99, evi 99, route-target 65000:99) and ip-vrf `ipvrf2` (vxlan1.98, evi 98, route-target
  65000:98). leaf2 has lo1.0 (10.99.0.1/24) in ipvrf and lo2.0 (10.98.0.1/24) in ipvrf2, advertised as IP-prefix routes.
- Design A, the usual EVPN layer-3 design (captures srl2672_fp043_present_* and, after leaf2 took lo1.0 out of ipvrf,
  srl2672_fp043_absent_*): leaf1's ipvrf has no `protocols bgp`. With the route, leaf1's default EVPN local-rib holds
  ip-prefix-route 10.99.0.0/24 from 2.2.2.2, best and used, `imported-network-instances: [ipvrf]`, attr-set 6 with
  target:65000:99; ipvrf's route-table holds 10.99.0.0/24 route-type bgp-evpn, active. ipvrf's own bgp-rib answers {}.
- Design B, an ip-vrf with a PE-CE BGP session (captures srl2672_fp043_pece2_* and srl2672_fp043_pece2absent_*): the
  same lab plus ce1 (FRR 10.4.1, AS 65100) on leaf1 ethernet-1/2.0 in ipvrf, with `protocols bgp` in ipvrf. With the
  route, ipvrf's bgp-rib lists 10.99.0.0/24 once: neighbor 0.0.0.0, origin-protocol bgp-evpn, best (the EVPN route
  re-originated into the ip-vrf's BGP, attr-set 11, next-hop 0.0.0.0).

The current driver:
- A: reads ipvrf's bgp-rib ({}), confirms ipvrf is up and answers "no BGP path", so `bgp_route vrf ipvrf prefix
  10.99.0.0/24 present: false` passes (the red team's case). `netdryrun check` on the live lab didn't get there: no BGP
  neighbors in ipvrf, so the gate marked the check not evaluated (srl2672_fp043_present_single_run.txt, exit 3).
- B: reads the bgp-evpn row as the router's own route (origin-protocol isn't bgp) and passes "no BGP path (received);
  a prefix this node originates itself isn't checked". `netdryrun check` on the live lab PASSED it
  (srl2672_fp043_pece2_run.txt): a false pass end to end, beside `route ... protocol: bgp present: false`, which failed.

The rule: an EVPN route imported into the ip-vrf is a BGP path there. On both captures `present: false` must not
pass; the driver must not report "no BGP path" for ipvrf. A path (read from the EVPN RIB, or the bgp-evpn row taken as
received) and a refusal (a DriverError, or the check failing as unreadable) both satisfy the oracle.

Reads the captures don't cover answer rc 1: the oracle knows nothing else leaf1 would have said.
"""
import json
from pathlib import Path

from netdryrun.checks import run_check
from netdryrun.config import _validate_check
from netdryrun.drivers.base import DriverError
from netdryrun.drivers.srlinux import SrlDriver
from netdryrun.lab import ExecResult

FX = Path(__file__).resolve().parents[2] / "fixtures"
PREFIX = "10.99.0.0/24"


def fx(name: str) -> str:
    return (FX / name).read_text(encoding="utf-8")


def captured(tag: str) -> dict:
    """sr_cli --output-format json <command> -> leaf1's answer, as captured in state `tag`."""
    p = f"srl2672_fp043_{tag}_leaf1_"
    out = {
        f"info from state /network-instance ipvrf bgp-rib afi-safi ipv4-unicast ipv4-unicast local-rib route {PREFIX} "
        "neighbor * origin-protocol * path-id *": p + "ipvrf_bgp_rib_route.json",
        "info from state /network-instance ipvrf bgp-rib afi-safi ipv4-unicast ipv4-unicast local-rib route "
        "10.98.0.0/24 neighbor * origin-protocol * path-id *": p + "ipvrf_bgp_rib_route_q.json",
        "info from state /network-instance ipvrf oper-state": p + "ipvrf_oper_state.json",
        f"info from state /network-instance ipvrf route-table ipv4-unicast route {PREFIX} "
        "id * route-type * route-owner * origin-network-instance *": p + "ipvrf_route_table_route.json",
        "info from state /network-instance ipvrf route-table ipv4-unicast route 10.98.0.0/24 "
        "id * route-type * route-owner * origin-network-instance *": p + "ipvrf_route_table_route_q.json",
        "info from state /network-instance ipvrf route-table ipv4-unicast route * "
        "id * route-type * route-owner * origin-network-instance *": p + "ipvrf_route_table.json",
        "info from state /network-instance ipvrf2 route-table ipv4-unicast route * "
        "id * route-type * route-owner * origin-network-instance *": p + "ipvrf2_route_table.json",
        "info from state /network-instance ipvrf bgp-rib": p + "ipvrf_bgp_rib.json",
        "info from state /network-instance ipvrf protocols": p + "ipvrf_protocols.json",
        "info from state /network-instance ipvrf2 protocols": p + "ipvrf2_protocols.json",
        "info from state /network-instance default bgp-rib afi-safi evpn evpn": p + "default_bgp_rib_evpn.json",
        "info from state /network-instance default bgp-rib afi-safi evpn evpn local-rib": p + "default_evpn_local_rib.json",
        "info from state /network-instance default bgp-rib attr-sets": p + "default_bgp_rib_attr_sets.json",
        "info from state /network-instance default bgp-rib attr-sets attr-set 6": p + "default_attr_set_6.json",
        "info from state /network-instance default protocols bgp neighbor *": p + "default_bgp_neighbors.json",
    }
    if tag.startswith("pece2"):
        out["info from state /network-instance ipvrf protocols bgp neighbor *"] = p + "ipvrf_bgp_neighbors.json"
        out["info from state /network-instance ipvrf bgp-rib afi-safi ipv4-unicast ipv4-unicast"] = \
            p + "ipvrf_bgp_rib_ipv4.json"
    if tag == "pece2":
        out["info from state /network-instance ipvrf bgp-rib attr-sets attr-set 11"] = p + "ipvrf_attr_set_11.json"
    return out


class CapturedLab:
    """leaf1 as captured in one state. A command that wasn't captured fails (rc=1)."""

    def __init__(self, tag: str):
        self.answers = captured(tag)

    def exec(self, node, cmd, timeout=60, input=None):
        if node == "leaf1" and cmd[:3] == ["sr_cli", "--output-format", "json"] and len(cmd) == 4 \
                and cmd[3] in self.answers:
            return ExecResult(cmd, 0, fx(self.answers[cmd[3]]), "")
        return ExecResult(cmd, 1, "", f"not captured: {' '.join(cmd)}")


class Clock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t

    def sleep(self, s):
        self.t += max(s, 0.5)


def check(tag: str, **raw):
    c = Clock()
    chk = _validate_check(0, {"node": "leaf1", "type": "bgp_route", "vrf": "ipvrf", "prefix": PREFIX, **raw}, 20)
    return run_check(chk, SrlDriver(CapturedLab(tag), "leaf1"), clock=c, sleep=c.sleep)


def evpn_row(tag: str) -> dict:
    rib = json.loads(fx(f"srl2672_fp043_{tag}_leaf1_default_bgp_rib_evpn.json"))["local-rib"]["ip-prefix-route"]
    rows = [r for r in rib if r["ip-prefix"] == PREFIX]
    assert len(rows) == 1
    return rows[0]


def installed_via_evpn(tag: str) -> None:
    routes = json.loads(fx(f"srl2672_fp043_{tag}_leaf1_ipvrf_route_table_route.json"))["route"]
    assert [(r["ipv4-prefix"], r["route-type"], r["active"]) for r in routes] == [(PREFIX, "bgp-evpn", True)]


def test_no_bgp_ipvrf_driver_sees_the_imported_evpn_path():
    """Design A: the EVPN route is imported into ipvrf and installed; the driver must not answer "no BGP path"."""
    row = evpn_row("present")
    assert row["imported-network-instances"] == ["ipvrf"]
    assert (row["neighbor"], row["valid-route"], row["best-route"], row["used-route"]) == ("2.2.2.2", True, True, True)
    attrs = json.loads(fx("srl2672_fp043_present_leaf1_default_attr_set_6.json"))
    assert attrs["index"] == row["attr-id"] == "6" and "target:65000:99" in attrs["communities"]["ext-community"]
    assert "bgp" not in json.loads(fx("srl2672_fp043_present_leaf1_ipvrf_protocols.json"))   # no protocols bgp
    assert json.loads(fx("srl2672_fp043_present_leaf1_ipvrf_bgp_rib_route.json")) == {}
    installed_via_evpn("present")
    # red on the current code: ipvrf's own bgp-rib is empty, so the driver reports no path
    try:
        paths = SrlDriver(CapturedLab("present"), "leaf1").bgp_paths(PREFIX, "ipvrf").value
    except DriverError:
        return   # a refusal: never "no BGP path"
    assert paths, (f"the driver reports no BGP path for {PREFIX} in ipvrf, while leaf1's EVPN RIB holds it from 2.2.2.2 "
                   "with imported-network-instances [ipvrf] and ipvrf's route table has it via bgp-evpn")


def test_no_bgp_ipvrf_present_false_does_not_pass():
    """Design A, the red team's check: `bgp_route vrf ipvrf present: false` passed with the route imported."""
    r = check("present", present=False)
    assert not r.passed, f"`present: false` passed with {PREFIX} imported into ipvrf over EVPN: {r.detail}"


def test_pece_ipvrf_present_false_does_not_pass():
    """Design B: ipvrf runs BGP to a CE; its bgp-rib lists the EVPN route as origin-protocol bgp-evpn from 0.0.0.0.
    `netdryrun check` passed `present: false` on the live lab ("a prefix this node originates itself")."""
    row = evpn_row("pece2")
    assert row["imported-network-instances"] == ["ipvrf"] and row["neighbor"] == "2.2.2.2"
    rib = json.loads(fx("srl2672_fp043_pece2_leaf1_ipvrf_bgp_rib_route.json"))["route"]
    assert [(x["prefix"], x["neighbor"], x["origin-protocol"], x["best-route"]) for x in rib] == \
        [(PREFIX, "0.0.0.0", "bgp-evpn", True)]
    installed_via_evpn("pece2")
    report = json.loads(fx("srl2672_fp043_pece2_report.json"))
    live = {c["name"]: c["passed"] for c in report["checks"]}
    assert live == {"pece-ce-session-up": True, "pece-evpn-bgp-route-absent-must-fail": True,
                    "pece-evpn-route-bgp-absent-must-fail": False}
    r = check("pece2", present=False)
    assert not r.passed, f"`present: false` passed with {PREFIX} imported into ipvrf over EVPN: {r.detail}"
