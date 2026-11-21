"""Oracle FP-043-EOSNONBGP (GHSA-ggcf-664f-c9ff case 1, red team RT-0056 and RT-0063): on Arista EOS, `route ...
present: false` with a protocol other than bgp passes while a route of that protocol is in the RIB but not selected.

EOS's `show ip route <prefix> | json` lists only the route the RIB selected for a prefix. The driver (0.2.0 to 0.4.2)
reads not-selected candidates from the BGP table only, so a valid static or OSPF route that lost route selection is
never seen. `show rib route ip vrf <vrf> <prefix> | json` lists every candidate per protocol, with `bestRoute` on each.

Captured live (cEOS 4.36.3M with FRR 10.4.1, lab ndr-fp043, 2026-11-21; tests/fixtures/SOURCES.yml), every file the
Cli stdout of ceos1 byte for byte:
- rt0056: eBGP default from frr1 selected (preference 200); `ip route 0.0.0.0/0 10.0.201.2 250` configured, valid
  (rt0056sel: with the eBGP session shut, it is the selected route) and not selected. Live, netdryrun 0.4.2 passed
  `route ceos1 0.0.0.0/0 protocol static present: false` (ceos4363m_fp043_rt0056_check.txt).
- rt0063: `ip route 0.0.0.0/0 Null0` selected (preference 1); frr1's OSPF external default (110) in the RIB, not
  selected (ospfsel: with the Null0 route removed, it is the selected route); no BGP default. Live, netdryrun 0.4.2
  passed `route ceos1 0.0.0.0/0 protocol ospf present: false` (ceos4363m_fp043_rt0063_check.txt).

The lab below answers exactly the commands captured in that phase, with the captured bytes; any other command answers
rc 1 with EOS's "% Invalid input" (no output is derived). The tests go through the runner's public path (the check as
netdryrun.yml states it, `hold_together` for a post-convergence check, the driver's `routes()`), not through any
parser name.

The rule: a route EOS holds as a candidate for the prefix, selected or not, counts as present for `present: false`,
whatever its protocol, as FRR, SONiC and NX-OS already do. Guards (healthy phases, the selected cases, exact-prefix
matching on EOS's longest-match answers) are in tests/test_oracle_guards_fp_043_eosnonbgp.py.
"""
from pathlib import Path

from netdryrun.checks import hold_together, is_post_convergence, run_check
from netdryrun.config import _validate_check
from netdryrun.drivers.eos import EosDriver
from netdryrun.lab import ExecResult

FX = Path(__file__).resolve().parents[2] / "fixtures"
NODE = "ceos1"
DEFAULT = "0.0.0.0/0"

# command -> captured file suffix, per phase (what was captured in that phase; nothing else is answered)
STD = {
    f"show ip route vrf default {DEFAULT} | json": "ip_route.json",
    f"show ip bgp {DEFAULT} vrf default | json": "ip_bgp.json",
    f"show rib route ip vrf default {DEFAULT} | json": "rib_route.json",
    f"show rib route ip vrf default {DEFAULT}": "rib_route.txt",
}
PHASES = {
    "rt0056": {**STD,
               f"show ip route vrf default {DEFAULT} detail": "ip_route_detail.txt",
               "show ip route vrf default static": "ip_route_static.txt",
               "show ip route vrf default 9.9.9.0/24 | json": "ip_route_9.json",
               "show ip bgp 9.9.9.0/24 vrf default | json": "ip_bgp_9.json",
               "show rib route ip vrf default 9.9.9.0/24 | json": "rib_route_9.json",
               "show running-config": "running_config.txt"},
    "rt0056sel": {f"show ip route vrf default {DEFAULT} | json": "ip_route.json",
                  f"show rib route ip vrf default {DEFAULT} | json": "rib_route.json"},
    "healthyA": STD,
    "rt0063": {**STD,
               f"show ip route vrf default {DEFAULT} detail": "ip_route_detail.txt",
               "show ip route vrf default ospf": "ip_route_ospf.txt",
               "show ip ospf database": "ospf_database.txt",
               "show running-config": "running_config.txt"},
    "ospfsel": {f"show ip route vrf default {DEFAULT} | json": "ip_route.json",
                f"show rib route ip vrf default {DEFAULT} | json": "rib_route.json"},
    "healthyB": STD,
}


def fx(phase: str, suffix: str) -> str:
    return (FX / f"ceos4363m_fp043_{phase}_{suffix}").read_text(encoding="utf-8")


class CapturedLab:
    """ceos1 in one captured phase: each captured command answers its captured bytes (rc 0, empty stderr, as
    captured); any other command answers rc 1, the way EOS refuses a command it doesn't know."""

    def __init__(self, phase: str):
        self.phase = phase
        self.asked: list[str] = []

    def exec(self, node, cmd, timeout=60, input=None):
        cmd = list(cmd)
        if node == NODE and cmd[:4] == ["Cli", "-p", "15", "-c"] and len(cmd) == 5:
            self.asked.append(cmd[4])
            suffix = PHASES[self.phase].get(cmd[4])
            if suffix is not None:
                return ExecResult(cmd, 0, fx(self.phase, suffix), "")
            return ExecResult(cmd, 1, f"\n> {cmd[4]}\n% Invalid input at line 1\n", "")
        return ExecResult(cmd, 1, "", f"not captured in phase {self.phase}: {' '.join(cmd)}")


class Clock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t

    def sleep(self, s):
        self.t += max(s, 0.5)


def route_check(phase: str, prefix: str = DEFAULT, **attrs):
    """The check as netdryrun.yml states it, run the way the runner runs it (a post-convergence check is held)."""
    check = _validate_check(0, {"type": "route", "node": NODE, "prefix": prefix, **attrs}, 20)
    lab = CapturedLab(phase)
    driver = EosDriver(lab, NODE)
    c = Clock()
    if is_post_convergence(check):
        [r] = hold_together([check], {NODE: driver}, hold=10, clock=c, sleep=c.sleep)
    else:
        r = run_check(check, driver, clock=c, sleep=c.sleep)
    return r, lab


def candidates(phase: str, prefix: str = DEFAULT):
    lab = CapturedLab(phase)
    return EosDriver(lab, NODE).routes(prefix, "default").value, lab


def rib_says(phase: str) -> dict:
    """{protocol key: bestRoute} for 0.0.0.0/0 in the phase's captured `show rib route ip` (the device's own view)."""
    import json
    d = json.loads(fx(phase, "rib_route.json"))["vrfs"]["default"]["ribRoutesByProtocol"]
    return {k: v["ribRoutes"][DEFAULT]["bestRoute"] for k, v in d.items() if DEFAULT in v["ribRoutes"]}


def test_rt0056_floating_static_behind_bgp_default_fails_static_present_false():
    """RT-0056: the static default (250) is in the RIB, valid and not selected; `protocol: static, present: false`
    passed on 0.4.2, live and here."""
    assert rib_says("rt0056") == {"staticConfig": False, "bgp": True}
    r, lab = route_check("rt0056", protocol="static", present=False)
    assert not r.passed, (f"`route {DEFAULT} protocol static present: false` passed on EOS while `show rib route ip` "
                          f"lists the floating static (preference 250, not selected): {r.detail} (asked: {lab.asked})")


def test_rt0056_driver_reports_the_not_selected_static_candidate():
    """The driver's own answer for the prefix holds the static candidate, not active, beside the selected eBGP route."""
    routes, lab = candidates("rt0056")
    seen = sorted((x.protocol, x.active) for x in routes if x.prefix == DEFAULT)
    assert ("static", False) in seen and ("bgp", True) in seen, (
        f"EOS routes({DEFAULT}) read {seen} while the RIB holds static (not selected) and bgp (selected); "
        f"asked: {lab.asked}")


def test_rt0063_ospf_default_behind_static_null0_fails_ospf_present_false():
    """RT-0063: frr1's OSPF default (110) is in the RIB and loses to `ip route 0.0.0.0/0 Null0` (1); `protocol: ospf,
    present: false` passed on 0.4.2, live and here."""
    assert rib_says("rt0063") == {"staticConfig": True, "ospf": False}
    r, lab = route_check("rt0063", protocol="ospf", present=False)
    assert not r.passed, (f"`route {DEFAULT} protocol ospf present: false` passed on EOS while `show rib route ip` "
                          f"lists the OSPF default (preference 110, not selected): {r.detail} (asked: {lab.asked})")


def test_rt0063_driver_reports_the_not_selected_ospf_candidate():
    routes, lab = candidates("rt0063")
    seen = sorted((x.protocol, x.active) for x in routes if x.prefix == DEFAULT)
    assert ("ospf", False) in seen and ("static", True) in seen, (
        f"EOS routes({DEFAULT}) read {seen} while the RIB holds static (selected, Null0) and ospf (not selected); "
        f"asked: {lab.asked}")
