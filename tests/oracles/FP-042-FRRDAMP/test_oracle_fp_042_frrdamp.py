"""Oracle FP-042-FRRDAMP (red team RT-0070): a dampening history entry read as a received, not-selected BGP route.

What the router showed (FRR 10.4.1, containerlab lab ndr-rpdamp, captured 2026-11-13; lab files
tests/fixtures/frr1041_rpdamp_*, captures tests/fixtures/frr1041_rt0070_*):
- r1 has `bgp dampening` and one eBGP neighbor, 10.0.12.2 (isp), which sent 0.0.0.0/0 with default-originate
  (`show bgp ipv4 unicast 0.0.0.0/0 json` before: one valid path, bestpath overall);
- isp then removed default-originate: the default was withdrawn. r1's zebra has no 0.0.0.0/0 (`show ip route
  0.0.0.0/0 json` is `{"0.0.0.0/0":[]}`), while BGP keeps the path as a dampening history entry: the JSON path has
  dampeningHistoryEntry true, no `valid`, no `bestpath`, and the text says "Paths: (1 available, no best path)" and
  "65002, (history entry)".
The 0.4.2 FRR driver reads that history entry as a received BGP path that wasn't selected, so `route node r1 prefix
0.0.0.0/0 protocol bgp active: false` passed ("present via bgp (not selected)",
tests/fixtures/frr1041_rpdamp_report.json) after the route was withdrawn.

The rule: a dampening history entry is a withdrawn route, not a received one. The `active: false` check must not
pass on this capture (failing, or refused as unreadable, both satisfy the oracle), and the driver must not report a
BGP route for 0.0.0.0/0 here (no route, or a refusal).

Reads the capture doesn't cover answer rc 1 (an unknown command): the oracle knows nothing else r1 would have said.
"""
import json
from pathlib import Path

from netdryrun.checks import run_check
from netdryrun.config import _validate_check
from netdryrun.drivers.base import DriverError
from netdryrun.drivers.frr import FrrDriver
from netdryrun.lab import ExecResult

FX = Path(__file__).resolve().parents[2] / "fixtures"
PREFIX = "0.0.0.0/0"


def fx(name: str) -> str:
    return (FX / name).read_text(encoding="utf-8")


CAPTURED = {   # vtysh command -> r1's output after the withdrawal, as captured
    f"show ip route {PREFIX} json": "frr1041_rt0070_r1_ip_route_default.json",
    f"show bgp ipv4 unicast {PREFIX} json": "frr1041_rt0070_r1_bgp_default.json",
    f"show bgp ipv4 unicast {PREFIX}": "frr1041_rt0070_r1_bgp_default_after.txt",
}


class CapturedLab:
    """r1 as captured. A command that wasn't captured answers as an unknown command (rc=1)."""

    def exec(self, node, cmd, timeout=60, input=None):
        if node == "r1" and cmd[:2] == ["vtysh", "-c"] and len(cmd) == 3 and cmd[2] in CAPTURED:
            return ExecResult(cmd, 0, fx(CAPTURED[cmd[2]]), "")
        return ExecResult(cmd, 1, "", f"not captured: {' '.join(cmd)}")


class Clock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t

    def sleep(self, s):
        self.t += max(s, 0.5)


def route_check(**raw):
    c = Clock()
    check = _validate_check(0, {"node": "r1", "type": "route", "prefix": PREFIX, **raw}, 20)
    return run_check(check, FrrDriver(CapturedLab(), "r1"), clock=c, sleep=c.sleep)


def test_driver_reports_no_bgp_route_for_a_history_entry():
    """The capture is a withdrawn default kept as history; the driver must not report it as a BGP route."""
    before = json.loads(fx("frr1041_rt0070_r1_bgp_default_before.json"))["paths"]
    assert len(before) == 1 and before[0]["valid"] is True and before[0]["bestpath"]["overall"] is True
    assert json.loads(fx("frr1041_rt0070_r1_ip_route_default.json")) == {PREFIX: []}
    for name in ("frr1041_rt0070_r1_bgp_default.json", "frr1041_rt0070_r1_bgp_default_after.json"):
        paths = json.loads(fx(name))["paths"]
        assert len(paths) == 1 and paths[0]["dampeningHistoryEntry"] is True
        assert "valid" not in paths[0] and "bestpath" not in paths[0]
    text = fx("frr1041_rt0070_r1_bgp_default_after.txt")
    assert "(1 available, no best path)" in text and "(history entry)" in text
    # red on the current code: the history entry comes back as a BGP route, not selected
    try:
        routes = FrrDriver(CapturedLab(), "r1").routes(PREFIX).value
    except DriverError:
        return   # a refusal: never a received route
    bgp = [r for r in routes if r.protocol == "bgp"]
    assert not bgp, (f"the driver reports {bgp} for {PREFIX}: that is a dampening history entry (no best path, "
                     "not valid), a route isp withdrew")


def test_active_false_does_not_pass_on_a_withdrawn_route():
    """The red team's check: `route protocol bgp active: false` passed on the history entry. It must not pass."""
    r = route_check(protocol="bgp", active=False)
    assert not r.passed, f"`route {PREFIX} protocol bgp active: false` passed after isp withdrew it: {r.detail}"
