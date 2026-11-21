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

The tests run each design on one live run that holds every read the fixed driver sends (the same lab redeployed
unchanged, 2026-11-22): design A on srl2672_fp043_rt58_* (next-hop-group 3530614221, its one next hop 2.2.2.2), design
B on srl2672_fp043_pece2b_* (default attr-set 8, ipvrf attr-set 10, next-hop-group 3692599526, its one next hop
2.2.2.2). Every answer comes from that one run, and they assert the driver's own reason (the imported path from 2.2.2.2;
"unexpectedly in the BGP table"), never only "did not pass".

Every lab here, the captured states too, fails the test on a read it holds no answer for: the oracle never answers
for leaf1, and a harness error or an unanswered fake read is never a catch (fixes db
FX-0.4.3-redteam-fake-unanswered-command).
"""
import json
from pathlib import Path

import pytest

from netdryrun.checks import run_check
from netdryrun.config import _validate_check
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


class StrictLab:
    """leaf1 answering `answers` (sr_cli --output-format json <command> -> a fixture). A read it holds no answer for
    fails the test (pytest.fail, which the driver and run_check can't turn into a verdict or a refusal)."""

    def __init__(self, answers: dict):
        self.answers, self.unanswered = answers, []

    def exec(self, node, cmd, timeout=60, input=None):
        if node == "leaf1" and cmd[:3] == SR and len(cmd) == 4 and cmd[3] in self.answers:
            return ExecResult(cmd, 0, fx(self.answers[cmd[3]]), "")
        self.unanswered.append(" ".join(cmd))
        pytest.fail(f"unanswered read on {node}: {' '.join(cmd)} (the capture holds no answer for it; an unanswered "
                    "read is never a catch)", pytrace=False)


class CapturedLab(StrictLab):
    """leaf1 as captured in one state (present, absent, pece2, pece2absent)."""

    def __init__(self, tag: str):
        super().__init__(captured(tag))


SR = ["sr_cli", "--output-format", "json"]
RT58 = "srl2672_fp043_rt58_leaf1_"
NHG, NH = "3530614221", "3530614219"   # the group ipvrf's route names in the rt58 run, and its one next hop
PECE2B = "srl2672_fp043_pece2b_leaf1_"
B_NHG, B_NH = "3692599526", "3692599523"   # the same in the pece2b run


def live_run(tag: str) -> dict:
    """sr_cli --output-format json <command> -> leaf1's answer in one live run (the commands as
    tests/fixtures/SOURCES.yml records them): rt58 = design A, pece2b = design B."""
    rib = (f"info from state /network-instance ipvrf bgp-rib afi-safi ipv4-unicast ipv4-unicast local-rib route {PREFIX} "
           "neighbor * origin-protocol * path-id *")
    table = (f"info from state /network-instance ipvrf route-table ipv4-unicast route {PREFIX} "
             "id * route-type * route-owner * origin-network-instance *")
    evpn = "info from state /network-instance default bgp-rib afi-safi evpn evpn local-rib"
    group = "info from state /network-instance ipvrf route-table next-hop-group "
    hop = "info from state /network-instance ipvrf route-table next-hop "
    if tag == "rt58":
        p = RT58
        return {rib: p + "ipvrf_bgp_rib_route.json", table: p + "ipvrf_route_table_route.json",
                evpn: p + "default_evpn_local_rib.json",
                "info from state /network-instance ipvrf oper-state": p + "ipvrf_oper_state.json",
                "info from state /network-instance default bgp-rib attr-sets attr-set 6": p + "default_attr_set_6.json",
                group + NHG: p + f"ipvrf_nhg_{NHG}.json", hop + NH: p + f"ipvrf_nh_{NH}.json"}
    if tag == "pece2b":
        p = PECE2B
        return {rib: p + "ipvrf_bgp_rib_route.json", table: p + "ipvrf_route_table_route.json",
                evpn: p + "default_evpn_local_rib.json",
                "info from state /network-instance default bgp-rib attr-sets attr-set 8": p + "default_attr_set_8.json",
                "info from state /network-instance ipvrf bgp-rib attr-sets attr-set 10": p + "ipvrf_attr_set_10.json",
                group + B_NHG: p + f"ipvrf_nhg_{B_NHG}.json", hop + B_NH: p + f"ipvrf_nh_{B_NH}.json"}
    raise ValueError(tag)


class LiveRun(StrictLab):
    """leaf1 in one live run (rt58 or pece2b)."""

    def __init__(self, tag: str = "rt58"):
        super().__init__(live_run(tag))


class Clock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t

    def sleep(self, s):
        self.t += max(s, 0.5)


def check(lab, **raw):
    c = Clock()
    chk = _validate_check(0, {"node": "leaf1", "type": "bgp_route", "vrf": "ipvrf", "prefix": PREFIX, **raw}, 20)
    return run_check(chk, SrlDriver(lab, "leaf1"), clock=c, sleep=c.sleep)


def evpn_row(tag: str) -> dict:
    rib = json.loads(fx(f"srl2672_fp043_{tag}_leaf1_default_bgp_rib_evpn.json"))["local-rib"]["ip-prefix-route"]
    rows = [r for r in rib if r["ip-prefix"] == PREFIX]
    assert len(rows) == 1
    return rows[0]


def installed_via_evpn(tag: str) -> None:
    routes = json.loads(fx(f"srl2672_fp043_{tag}_leaf1_ipvrf_route_table_route.json"))["route"]
    assert [(r["ipv4-prefix"], r["route-type"], r["active"]) for r in routes] == [(PREFIX, "bgp-evpn", True)]


def test_no_bgp_ipvrf_driver_sees_the_imported_evpn_path():
    """Design A (live run rt58): the EVPN route is imported into ipvrf and installed; the driver must report that path,
    read from the run's answers alone."""
    rib = json.loads(fx(RT58 + "default_evpn_local_rib.json"))["ip-prefix-route"]
    [row] = [r for r in rib if r["ip-prefix"] == PREFIX]
    assert row["imported-network-instances"] == ["ipvrf"]
    assert (row["neighbor"], row["valid-route"], row["best-route"], row["used-route"]) == ("2.2.2.2", True, True, True)
    attrs = json.loads(fx(RT58 + "default_attr_set_6.json"))
    assert attrs["index"] == row["attr-id"] == "6" and "target:65000:99" in attrs["communities"]["ext-community"]
    # no `protocols bgp` in ipvrf: the lab input the run was deployed from (SOURCES.yml)
    assert not [x for x in fx("srl2672_fp043_leaf1.cli").splitlines()
                if x.startswith("set / network-instance ipvrf protocols bgp ")]
    assert json.loads(fx(RT58 + "ipvrf_bgp_rib_route.json")) == {}
    routes = json.loads(fx(RT58 + "ipvrf_route_table_route.json"))["route"]
    assert [(r["ipv4-prefix"], r["route-type"], r["active"], r["next-hop-group"]) for r in routes] == \
        [(PREFIX, "bgp-evpn", True, NHG)]
    assert [h["next-hop"] for h in json.loads(fx(RT58 + f"ipvrf_nhg_{NHG}.json"))["next-hop"]] == [NH]
    assert json.loads(fx(RT58 + f"ipvrf_nh_{NH}.json"))["ip-address"] == "2.2.2.2"
    # red on the current code: ipvrf's own bgp-rib is empty, so the driver reports no path
    lab = LiveRun()
    paths = SrlDriver(lab, "leaf1").bgp_paths(PREFIX, "ipvrf").value
    assert not lab.unanswered, lab.unanswered
    assert paths, (f"the driver reports no BGP path for {PREFIX} in ipvrf, while leaf1's EVPN RIB holds it from 2.2.2.2 "
                   "with imported-network-instances [ipvrf] and ipvrf's route table has it via bgp-evpn")
    assert [(p.best, p.next_hop, p.neighbor, p.local_candidate) for p in paths] == \
        [(True, "2.2.2.2", "2.2.2.2", False)], \
        f"the driver doesn't report the imported EVPN path from 2.2.2.2 as ipvrf's best received path: {paths}"


def test_no_bgp_ipvrf_present_false_does_not_pass():
    """Design A, the red team's check: `bgp_route vrf ipvrf present: false` passed with the route imported. It must
    fail with the driver's verdict on the run's answers, not through an unanswered read or a refusal."""
    lab = LiveRun()
    r = check(lab, present=False)
    assert not lab.unanswered, lab.unanswered
    assert not r.passed, f"`present: false` passed with {PREFIX} imported into ipvrf over EVPN: {r.detail}"
    assert "unexpectedly in the BGP table" in r.detail and "2.2.2.2" in r.detail, \
        f"`present: false` failed, but not because the driver saw the imported path from 2.2.2.2: {r.detail}"


def test_pece_ipvrf_present_false_does_not_pass():
    """Design B (live run pece2b): ipvrf runs BGP to a CE; its bgp-rib lists the EVPN route once, origin-protocol
    bgp-evpn from 0.0.0.0. `netdryrun check` passed `present: false` on the live lab (pece2 run, "a prefix this node
    originates itself"). It must fail with the driver's verdict on the pece2b run's answers alone."""
    rib = json.loads(fx(PECE2B + "default_evpn_local_rib.json"))["ip-prefix-route"]
    [row] = [r for r in rib if r["ip-prefix"] == PREFIX]
    assert row["imported-network-instances"] == ["ipvrf"] and row["neighbor"] == "2.2.2.2" and row["attr-id"] == "8"
    assert "target:65000:99" in json.loads(fx(PECE2B + "default_attr_set_8.json"))["communities"]["ext-community"]
    own = json.loads(fx(PECE2B + "ipvrf_bgp_rib_route.json"))["route"]
    assert [(x["prefix"], x["neighbor"], x["origin-protocol"], x["best-route"], x["attr-id"]) for x in own] == \
        [(PREFIX, "0.0.0.0", "bgp-evpn", True, "10")]
    routes = json.loads(fx(PECE2B + "ipvrf_route_table_route.json"))["route"]
    assert [(r["ipv4-prefix"], r["route-type"], r["active"], r["next-hop-group"]) for r in routes] == \
        [(PREFIX, "bgp-evpn", True, B_NHG)]
    assert [h["next-hop"] for h in json.loads(fx(PECE2B + f"ipvrf_nhg_{B_NHG}.json"))["next-hop"]] == [B_NH]
    assert json.loads(fx(PECE2B + f"ipvrf_nh_{B_NH}.json"))["ip-address"] == "2.2.2.2"
    # the original false pass, end to end on the live lab (the pece2 run, the same design)
    report = json.loads(fx("srl2672_fp043_pece2_report.json"))
    live = {c["name"]: c["passed"] for c in report["checks"]}
    assert live == {"pece-ce-session-up": True, "pece-evpn-bgp-route-absent-must-fail": True,
                    "pece-evpn-route-bgp-absent-must-fail": False}
    lab = LiveRun("pece2b")
    r = check(lab, present=False)
    assert not lab.unanswered, lab.unanswered
    assert not r.passed, f"`present: false` passed with {PREFIX} imported into ipvrf over EVPN: {r.detail}"
    assert "unexpectedly in the BGP table" in r.detail and "2.2.2.2" in r.detail, \
        f"`present: false` failed, but not because the driver saw the imported path from 2.2.2.2: {r.detail}"
