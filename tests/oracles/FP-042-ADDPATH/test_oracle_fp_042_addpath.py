"""Oracle FP-042-ADDPATH (red team RT-0066): with add-path, FRR's acceptedPrefixCounter counts paths, not prefixes.

What the router showed (FRR 10.4.1, containerlab lab ndr-repro042, captured 2026-11-12; lab files
tests/fixtures/frr1041_repro042_*, captures tests/fixtures/frr1041_rt0066_*):
- r1 has one eBGP neighbor, 10.0.12.2 (r2). r2 announces 2 prefixes, 10.20.0.0/24 and 10.21.0.0/24, and with
  `neighbor 10.0.12.1 addpath-tx-all-paths` it sends r1 2 paths for each (its own, and r3's through it);
- `show bgp ipv4 unicast neighbors 10.0.12.2 routes` on r1 ends "Displayed 2 routes and 4 total paths", and its JSON
  form says totalRoutes 2, totalPaths 4;
- `show bgp neighbors json` on r1 says acceptedPrefixCounter 4 for ipv4Unicast, and
  neighborCapabilities.addPath.ipv4Unicast.txReceived true (r2 sends r1 several paths per prefix).
The 0.4.2 FRR driver reads acceptedPrefixCounter as the prefix count, so `bgp_prefixes node r1 neighbor 10.0.12.2
min: 4` passed ("4 ipv4-unicast prefixes accepted", tests/fixtures/frr1041_repro042_report.json) with 2 prefixes.

The rule: r1 accepted 2 prefixes from 10.0.12.2. A `min: 4` check must not pass on this capture, and the count the
driver reports for the neighbor's ipv4-unicast must not be 4. A correct count (2) and a refusal (a DriverError, or the
check failing as unreadable) both satisfy the oracle; a count of the paths does not.

Reads the capture doesn't cover answer rc 1 (an unknown command): the oracle knows nothing else r1 would have said.
"""
from pathlib import Path

from netdryrun.checks import run_check
from netdryrun.config import _validate_check
from netdryrun.drivers.base import DriverError
from netdryrun.drivers.frr import FrrDriver
from netdryrun.lab import ExecResult

FX = Path(__file__).resolve().parents[2] / "fixtures"
NEIGHBOR = "10.0.12.2"


def fx(name: str) -> str:
    return (FX / name).read_text(encoding="utf-8")


CAPTURED = {   # vtysh command -> r1's output, as captured
    "show bgp neighbors json": "frr1041_rt0066_r1_bgp_neighbors.json",
    f"show bgp ipv4 unicast neighbors {NEIGHBOR} routes json": "frr1041_rt0066_r1_neighbor_routes.json",
    f"show bgp ipv4 unicast neighbors {NEIGHBOR} routes": "frr1041_rt0066_r1_neighbor_routes.txt",
    "show bgp ipv4 unicast json": "frr1041_rt0066_r1_bgp_ipv4.json",
    "show version": "frr1041_repro042_r1_show_version.txt",
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


def positive(**raw):
    c = Clock()
    check = _validate_check(0, {"node": "r1", "type": "bgp_prefixes", "neighbor": NEIGHBOR, **raw}, 20)
    return run_check(check, FrrDriver(CapturedLab(), "r1"), clock=c, sleep=c.sleep)


def test_driver_prefix_count_is_not_the_add_path_counter():
    """The capture: 2 prefixes, 4 paths, add-path received, counter 4. The driver must not report 4 prefixes."""
    import json
    assert "Displayed 2 routes and 4 total paths" in fx("frr1041_rt0066_r1_neighbor_routes.txt")
    routes = json.loads(fx("frr1041_rt0066_r1_neighbor_routes.json"))
    assert (routes["totalRoutes"], routes["totalPaths"]) == (2, 4)
    n = json.loads(fx("frr1041_rt0066_r1_bgp_neighbors.json"))[NEIGHBOR]
    assert n["neighborCapabilities"]["addPath"]["ipv4Unicast"]["txReceived"] is True
    assert n["addressFamilyInfo"]["ipv4Unicast"]["acceptedPrefixCounter"] == 4
    # red on the current code: the driver's count for the neighbor is the path counter
    try:
        got = FrrDriver(CapturedLab(), "r1").bgp_neighbors().value[NEIGHBOR].prefixes.get("ipv4-unicast")
    except DriverError:
        return   # a refusal: never a count of the paths
    assert got != 4, (f"the driver reports {got} ipv4-unicast prefixes from {NEIGHBOR}: that is acceptedPrefixCounter, "
                      "which counts add-path paths (4), while r1 accepted 2 prefixes")


def test_min_4_does_not_pass_on_two_prefixes():
    """The red team's check: `bgp_prefixes min: 4` passed on 2 prefixes. It must fail (a count of 2, or unreadable)."""
    r = positive(min=4)
    assert not r.passed, f"`min: 4` passed with 2 prefixes accepted from {NEIGHBOR}: {r.detail}"
