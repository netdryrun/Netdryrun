"""Oracle FP-043-EOSAGG (red team RT-0087; the known false passes RT-0085 and RT-0086): on Arista EOS the router's
own BGP aggregate (`aggregate-address`) gets a protocol name that depends on whether it won route selection, and that
name differs from FRR's for the same aggregate.

- Selected: `show ip route` lists it as routeType `bgpAggregate`, read as protocol `aggregate`, and its BGP-table path
  is the node's own (no peer), so no `bgp` route is seen. `route ... protocol: bgp, present: false` passes; FRR (and
  NX-OS) read the same aggregate as `bgp` and fail that check (RT-0085, shape a).
- Not selected, losing to a static for the same prefix (`ip route <prefix> Null0`, corpus v2 case 18's setup): the
  routing table lists only the static; the RIB (`show rib route ip`) lists the aggregate under `bgp`, not best; the
  BGP table lists one own path with `localAgg: true`. main doesn't read the RIB, so `protocol: bgp, present: false`
  passes there; ndr/fix-eos-nonbgp reads the RIB entry as a `bgp` candidate, so `protocol: aggregate, present: false`
  passes there (RT-0086, shape b).

The expected behaviour (README.md in this folder): one name for the router's own BGP aggregate on every driver, `bgp`,
as FRR reports it, selected or not. Whatever else EOS accepts for it (`aggregate` as an EOS-only alias, or a refusal
of `protocol: aggregate` before the run), a check naming the aggregate never reads it as absent while it is in the
RIB.

Captured live (cEOS 4.36.3M ceos1 and FRR 10.4.1 frr2 with the same BGP aggregates and the same changes, lab
ndr-eosagg, 2026-11-21; tests/fixtures/SOURCES.yml). Every answer is the stdout of the device, byte for byte; any
other command answers rc 1. The checks are judged through the runner's public path (the check as netdryrun.yml states
it, `check_supported` for the refusal before a run, `hold_together` for a post-convergence check, the driver's
`routes()`), on EOS and on FRR from their own captures of the same phase.
"""
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from netdryrun.checks import hold_together, is_post_convergence, run_check
from netdryrun.config import _validate_check
from netdryrun.drivers import DriverError, check_supported
from netdryrun.drivers.eos import EosDriver
from netdryrun.drivers.frr import FrrDriver
from netdryrun.lab import ExecResult

FX = Path(__file__).resolve().parents[2] / "fixtures"

# key -> (vrf, prefix, EOS family word, FRR afi)
PREFIXES = {"v4": ("default", "10.66.0.0/16", "ip", "ipv4"),
            "v6": ("default", "2001:db8:66::/48", "ipv6", "ipv6"),
            "blue": ("blue", "10.67.0.0/16", "ip", "ipv4")}
PHASES = ("sel", "selms", "exact", "exactstatic", "static", "healthystatic", "healthy")
# the checks the oracle asks, as netdryrun.yml states them
CHECKS = {"bgp-absent": {"protocol": "bgp", "present": False},
          "bgp-active": {"protocol": "bgp"},
          "bgp-candidate": {"protocol": "bgp", "active": False},
          "agg-absent": {"protocol": "aggregate", "present": False},
          "agg-active": {"protocol": "aggregate"},
          "agg-candidate": {"protocol": "aggregate", "active": False},
          "any-absent": {"present": False},
          "static-active": {"protocol": "static"}}
BGP_CHECKS = ("bgp-absent", "bgp-active", "bgp-candidate", "any-absent")


def eos_commands(key: str) -> dict:
    vrf, p, fam, _ = PREFIXES[key]
    return {f"show {fam} route vrf {vrf} {p} | json": f"{key}_ip_route.json",
            f"show rib route {fam} vrf {vrf} {p} | json": f"{key}_rib_route.json",
            f"show {fam} bgp {p} vrf {vrf} | json": f"{key}_ip_bgp.json",
            f"show rib route {fam} vrf {vrf} {p}": f"{key}_rib_route.txt",
            f"show {fam} bgp {p} vrf {vrf}": f"{key}_ip_bgp.txt"}


def frr_commands(key: str) -> dict:
    vrf, p, fam, afi = PREFIXES[key]
    vp = "" if vrf == "default" else f" vrf {vrf}"
    return {f"show {fam} route{vp} {p} json": f"{key}_ip_route.json",
            f"show bgp{vp} {afi} unicast {p} json": f"{key}_bgp.json",
            f"show {fam} route{vp} {p}": f"{key}_ip_route.txt",
            f"show bgp{vp} {afi} unicast {p}": f"{key}_bgp.txt",
            "show vrf": "vrf.txt"}


DUTS = {"eos": ("ceos1", "ceos4363m_eosagg", EosDriver, ["Cli", "-p", "15", "-c"], eos_commands),
        "frr": ("frr2", "frr1041_eosagg", FrrDriver, ["vtysh", "-c"], frr_commands)}


def fx(dut: str, phase: str, suffix: str) -> str:
    return (FX / f"{DUTS[dut][1]}_{phase}_{suffix}").read_text(encoding="utf-8")


class CapturedLab:
    """One node in one captured phase: each captured command answers its captured bytes (rc 0, empty stderr, as
    captured); any other command answers rc 1, the way the device refuses a command it doesn't know."""

    def __init__(self, dut: str, phase: str):
        self.dut, self.phase = dut, phase
        self.asked: list[str] = []
        self.table = {}
        for key in PREFIXES:
            self.table.update(DUTS[dut][4](key))

    def exec(self, node, cmd, timeout=60, input=None):
        cmd = list(cmd)
        name, _, _, argv, _ = DUTS[self.dut]
        if node == name and cmd[:len(argv)] == argv and len(cmd) == len(argv) + 1:
            self.asked.append(cmd[-1])
            suffix = self.table.get(cmd[-1])
            if suffix is not None:
                return ExecResult(cmd, 0, fx(self.dut, self.phase, suffix), "")
            return ExecResult(cmd, 1, f"\n> {cmd[-1]}\n% Invalid input at line 1\n", "")
        return ExecResult(cmd, 1, "", f"not captured in phase {self.phase}: {' '.join(cmd)}")


class Clock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t

    def sleep(self, s):
        self.t += max(s, 0.5)


def verdict(dut: str, phase: str, key: str, check: str) -> tuple[str, str]:
    """("PASS" | "FAIL" | "REFUSED", detail) for one check, judged the way `netdryrun run`/`check` judges it."""
    node, _, cls, _, _ = DUTS[dut]
    vrf, prefix, _, _ = PREFIXES[key]
    spec = {"type": "route", "node": node, "prefix": prefix, **CHECKS[check]}
    if vrf != "default":
        spec["vrf"] = vrf
    c = _validate_check(0, spec, 20)
    try:   # the refusal before deploying: a protocol name the driver never reports
        check_supported(SimpleNamespace(nodes={node: None}), c, dut)
    except DriverError as e:
        return "REFUSED", str(e)
    lab = CapturedLab(dut, phase)
    driver = cls(lab, node)
    clock = Clock()
    if is_post_convergence(c):
        [r] = hold_together([c], {node: driver}, hold=10, clock=clock, sleep=clock.sleep)
    else:
        r = run_check(c, driver, clock=clock, sleep=clock.sleep)
    if not r.passed and r.samples_unready:
        return "ERROR", f"{r.detail} (asked: {lab.asked})"   # an unreadable answer: neither verdict
    return ("PASS" if r.passed else "FAIL"), f"{r.detail} (asked: {lab.asked})"


def table(phase: str, key: str, checks=BGP_CHECKS) -> dict:
    return {c: (verdict("eos", phase, key, c)[0], verdict("frr", phase, key, c)[0]) for c in checks}


def own_aggregate_in_eos_rib(phase: str, key: str) -> bool:
    """The device's own view: the BGP table holds the node's own aggregate path (routeType.localAgg) and the RIB
    holds a bgp entry for the prefix."""
    vrf, prefix, _, _ = PREFIXES[key]
    bgp = json.loads(fx("eos", phase, f"{key}_ip_bgp.json"))["vrfs"][vrf]["bgpRouteEntries"]
    own = [p for p in bgp.get(prefix, {}).get("bgpRoutePaths", []) if p["routeType"].get("localAgg")]
    rib = json.loads(fx("eos", phase, f"{key}_rib_route.json"))["vrfs"][vrf]["ribRoutesByProtocol"]
    return bool(own) and prefix in rib.get("bgp", {}).get("ribRoutes", {})


# the phases in which the router's own aggregate is in the RIB, and whether it is the selected route there
AGG_PHASES = {"sel": True, "selms": True, "exact": True, "exactstatic": False, "static": False}
SELECTED = [(ph, k) for ph, sel in AGG_PHASES.items() if sel for k in PREFIXES]
BEHIND_STATIC = [(ph, k) for ph, sel in AGG_PHASES.items() if not sel for k in PREFIXES]


@pytest.mark.parametrize("phase,key", [(ph, k) for ph, k in SELECTED if not (ph == "exact" and k != "blue")])
def test_selected_own_aggregate_fails_bgp_present_false_as_on_frr(phase, key):
    """Shape a (RT-0085): the aggregate is selected and nothing is learned for the prefix (in `exact`, VRF blue has
    no peer, so nothing). FRR fails `protocol: bgp, present: false` on the same aggregate; EOS passed it."""
    assert own_aggregate_in_eos_rib(phase, key)
    assert verdict("frr", phase, key, "bgp-absent")[0] == "FAIL"
    v, detail = verdict("eos", phase, key, "bgp-absent")
    assert v == "FAIL", (f"{phase} {key}: `route {PREFIXES[key][1]} protocol bgp present: false` is {v} on EOS while "
                         f"the node's own BGP aggregate is the selected route (FRR: FAIL): {detail}")


@pytest.mark.parametrize("phase,key", SELECTED)
def test_selected_own_aggregate_passes_bgp_present_true_as_on_frr(phase, key):
    """The same name both ways: the selected aggregate is the active bgp route, as FRR reports it."""
    assert verdict("frr", phase, key, "bgp-active")[0] == "PASS"
    v, detail = verdict("eos", phase, key, "bgp-active")
    assert v == "PASS", (f"{phase} {key}: `route {PREFIXES[key][1]} protocol bgp` is {v} on EOS while the node's own "
                         f"BGP aggregate is the selected route (FRR: PASS): {detail}")


@pytest.mark.parametrize("phase,key", BEHIND_STATIC)
def test_own_aggregate_behind_a_static_is_never_absent(phase, key):
    """Shape b (RT-0086, corpus v2 case 18's setup): a static for the prefix wins; the aggregate is in the RIB (bgp,
    not best) and in the BGP table (localAgg). `protocol: bgp, present: false` must fail, as on FRR (main passed it),
    and `protocol: aggregate, present: false` must not pass (ndr/fix-eos-nonbgp passes it): failed or refused."""
    assert own_aggregate_in_eos_rib(phase, key)
    assert verdict("frr", phase, key, "bgp-absent")[0] == "FAIL"
    bgp, bgp_detail = verdict("eos", phase, key, "bgp-absent")
    agg, agg_detail = verdict("eos", phase, key, "agg-absent")
    assert bgp == "FAIL" and agg in ("FAIL", "REFUSED"), (
        f"{phase} {key}: with the own aggregate in the RIB behind a static, EOS judged `protocol: bgp, present: false` "
        f"{bgp} ({bgp_detail}) and `protocol: aggregate, present: false` {agg} ({agg_detail}); FRR fails the first and "
        "refuses the second")


@pytest.mark.parametrize("phase,key", SELECTED + BEHIND_STATIC)
def test_same_bgp_verdicts_as_frr_on_the_same_scenario(phase, key):
    """The rule: one protocol vocabulary across drivers, tested on the same scenario. Every bgp check, and the
    any-protocol absence check, gets FRR's verdict; and the aggregate is never absent while it is in the RIB."""
    got = table(phase, key)
    agg = verdict("eos", phase, key, "agg-absent")[0]
    diff = {c: v for c, v in got.items() if v[0] != v[1]}
    assert not diff and agg != "PASS", (
        f"{phase} {key}: EOS vs FRR verdicts that differ {diff} (EOS, FRR); EOS `protocol: aggregate, present: false`: "
        f"{agg}")
