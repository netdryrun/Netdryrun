"""Oracle FP-042-SRLADDPATH (red team RT-0068): with add-path, SR Linux's received-routes counts paths, not prefixes.

What the router showed (SR Linux 26.7.2, containerlab lab ndr-rpsrl, captured 2026-11-13; lab files
tests/fixtures/srl2672_rpsrl_*, captures tests/fixtures/srl2672_rt0068_*):
- srl1 has one eBGP neighbor, 10.0.100.2 (frr1), with `afi-safi ipv4-unicast add-paths receive true`. frr1 announces
  2 prefixes, 10.40.0.0/24 and 10.41.0.0/24, and with `neighbor 10.0.100.1 addpath-tx-all-paths` it sends srl1 2
  paths for each (its own, and frr2's through it). It also sends srl1's own 2 routes back, which fail AS-loop;
- the neighbor's ipv4-unicast state says received-routes 6, active-routes 2, rejected-routes 0, add-paths receive
  true, and ADD_PATH among received-capabilities;
- the ipv4-unicast BGP-RIB holds 6 paths from 10.0.100.2: 2 invalid (as-loop) and 4 valid, 2 per prefix.
The 0.4.2 SR Linux driver reads received-routes minus the AS-loop paths (6 - 2 = 4) as the prefix count, so
`bgp_prefixes node srl1 neighbor 10.0.100.2 min: 4` passed ("4 ipv4-unicast prefixes accepted",
tests/fixtures/srl2672_rpsrl_report.json) with 2 prefixes.

The rule: srl1 accepted 2 prefixes from 10.0.100.2. A `min: 4` check must not pass on this capture, and the count
the driver reports for the neighbor's ipv4-unicast must not be 4. A correct count (2) and a refusal (a DriverError,
or the check failing as unreadable) both satisfy the oracle; a count of the paths does not.

Reads the capture doesn't cover answer rc 1: the oracle knows nothing else srl1 would have said.
"""
import json
from pathlib import Path

from netdryrun.checks import run_check
from netdryrun.config import _validate_check
from netdryrun.drivers.base import DriverError
from netdryrun.drivers.srlinux import SrlDriver
from netdryrun.lab import ExecResult

FX = Path(__file__).resolve().parents[2] / "fixtures"
NEIGHBOR = "10.0.100.2"


def fx(name: str) -> str:
    return (FX / name).read_text(encoding="utf-8")


CAPTURED = {   # sr_cli arguments -> srl1's output, as captured
    ("--output-format", "json", "info from state /network-instance default protocols bgp neighbor *"):
        "srl2672_rt0068_srl1_bgp_neighbors.json",
    ("--output-format", "json", "info from state /network-instance default bgp-rib afi-safi ipv4-unicast ipv4-unicast"):
        "srl2672_rt0068_srl1_bgp_rib_ipv4.json",
    (f"info from state /network-instance default protocols bgp neighbor {NEIGHBOR}",):
        "srl2672_rt0068_srl1_neighbor_state.txt",
}


class CapturedLab:
    """srl1 as captured. A command that wasn't captured fails (rc=1)."""

    def exec(self, node, cmd, timeout=60, input=None):
        if node == "srl1" and cmd[:1] == ["sr_cli"] and tuple(cmd[1:]) in CAPTURED:
            return ExecResult(cmd, 0, fx(CAPTURED[tuple(cmd[1:])]), "")
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
    check = _validate_check(0, {"node": "srl1", "type": "bgp_prefixes", "neighbor": NEIGHBOR, **raw}, 20)
    return run_check(check, SrlDriver(CapturedLab(), "srl1"), clock=c, sleep=c.sleep)


def test_driver_prefix_count_is_not_the_add_path_paths():
    """The capture: 2 prefixes, 4 valid paths, add-path received, received-routes 6. The driver must not report 4."""
    n = json.loads(fx("srl2672_rt0068_srl1_bgp_neighbors.json"))["neighbor"]
    assert [x["peer-address"] for x in n] == [NEIGHBOR]
    assert "ADD_PATH" in n[0]["received-capabilities"]
    af = next(a for a in n[0]["afi-safi"] if a["afi-safi-name"] == "ipv4-unicast")
    assert af["add-paths"]["receive"] is True
    assert (af["received-routes"], af["active-routes"], af["rejected-routes"]) == (6, 2, 0)
    rib = json.loads(fx("srl2672_rt0068_srl1_bgp_rib_ipv4.json"))["local-rib"]["route"]
    paths = [r for r in rib if r["neighbor"] == NEIGHBOR]
    valid = [r for r in paths if r["valid-route"]]
    assert len(paths) == 6 and len(valid) == 4
    assert sorted(r["prefix"] for r in valid) == ["10.40.0.0/24"] * 2 + ["10.41.0.0/24"] * 2
    assert all(r["invalid-reason"] == {"as-loop": True} for r in paths if not r["valid-route"])
    state = fx("srl2672_rt0068_srl1_neighbor_state.txt")
    assert "received-routes 6" in state and "active-routes 2" in state
    # red on the current code: the driver's count for the neighbor is received-routes minus the AS-loop paths
    try:
        got = SrlDriver(CapturedLab(), "srl1").bgp_neighbors().value[NEIGHBOR].prefixes.get("ipv4-unicast")
    except DriverError:
        return   # a refusal: never a count of the paths
    assert got != 4, (f"the driver reports {got} ipv4-unicast prefixes from {NEIGHBOR}: that counts add-path paths "
                      "(received-routes 6 minus 2 AS-loop paths), while srl1 accepted 2 prefixes")


def test_min_4_does_not_pass_on_two_prefixes():
    """The red team's check: `bgp_prefixes min: 4` passed on 2 prefixes. It must fail (a count of 2, or unreadable)."""
    r = positive(min=4)
    assert not r.passed, f"`min: 4` passed with 2 prefixes accepted from {NEIGHBOR}: {r.detail}"
