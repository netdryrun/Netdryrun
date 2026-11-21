"""Oracle FP-042-EOSADDPATH (red team RT-0069): with additional-paths, cEOS's prefixAccepted counts paths.

What the router showed (cEOS 4.36.3M, containerlab lab ndr-rpeos, captured 2026-11-13; lab files
tests/fixtures/ceos4363m_rpeos_*, captures tests/fixtures/ceos4363m_rt0069_*):
- ceos1 has one eBGP neighbor, 10.0.200.2 (frr1), with `neighbor 10.0.200.2 additional-paths receive`. frr1
  announces 2 prefixes, 10.40.0.0/24 and 10.41.0.0/24, and with addpath-tx-all-paths it sends ceos1 2 paths for each
  (its own, and frr2's through it);
- `show ip bgp` on ceos1 lists 4 paths from 10.0.200.2 for the 2 prefixes, one active each;
- `show ip bgp summary | json` (with and without `vrf default`) says prefixAccepted 4, prefixReceived 4;
- `show ip bgp neighbors 10.0.200.2 | json` says addPathsCaps.ipv4Unicast.receivingAddPaths enabled, and
  prefixesReceived 4.
The 0.4.2 EOS driver reads the summary's prefixAccepted as the prefix count, so `bgp_prefixes node ceos1 neighbor
10.0.200.2 min: 4` passed ("4 ipv4-unicast prefixes accepted", tests/fixtures/ceos4363m_rpeos_report.json) with 2
prefixes.

The rule: ceos1 accepted 2 prefixes from 10.0.200.2. A `min: 4` check must not pass on this capture, and the count
the driver reports for the neighbor's ipv4-unicast must not be 4. A correct count (2) and a refusal (a DriverError,
or the check failing as unreadable) both satisfy the oracle; a count of the paths does not.

The captured commands answer as captured; `show ip bgp neighbors 10.0.200.2 vrf default | json` answers like the
same command without `vrf default` (the same neighbor, in the default VRF). Anything else answers rc 1: the oracle
knows nothing else ceos1 would have said.
"""
import json
from pathlib import Path

from netdryrun.checks import run_check
from netdryrun.config import _validate_check
from netdryrun.drivers.base import DriverError
from netdryrun.drivers.eos import EosDriver
from netdryrun.lab import ExecResult

FX = Path(__file__).resolve().parents[2] / "fixtures"
NEIGHBOR = "10.0.200.2"


def fx(name: str) -> str:
    return (FX / name).read_text(encoding="utf-8")


CAPTURED = {   # Cli command -> ceos1's output, as captured
    "show ip bgp summary vrf default | json": "ceos4363m_rt0069_ceos1_ip_bgp_summary_vrf.json",
    "show ipv6 bgp summary vrf default | json": "ceos4363m_rt0069_ceos1_ipv6_bgp_summary_vrf.json",
    "show ip bgp summary | json": "ceos4363m_rt0069_ceos1_ip_bgp_summary.json",
    f"show ip bgp neighbors {NEIGHBOR} | json": "ceos4363m_rt0069_ceos1_ip_bgp_neighbor.json",
    f"show ip bgp neighbors {NEIGHBOR} vrf default | json": "ceos4363m_rt0069_ceos1_ip_bgp_neighbor.json",
    "show ip bgp": "ceos4363m_rt0069_ceos1_ip_bgp.txt",
}


class CapturedLab:
    """ceos1 as captured. A command that wasn't captured fails (rc=1)."""

    def exec(self, node, cmd, timeout=60, input=None):
        if node == "ceos1" and cmd[:4] == ["Cli", "-p", "15", "-c"] and len(cmd) == 5 and cmd[4] in CAPTURED:
            return ExecResult(cmd, 0, fx(CAPTURED[cmd[4]]), "")
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
    check = _validate_check(0, {"node": "ceos1", "type": "bgp_prefixes", "neighbor": NEIGHBOR, **raw}, 20)
    return run_check(check, EosDriver(CapturedLab(), "ceos1"), clock=c, sleep=c.sleep)


def test_driver_prefix_count_is_not_the_add_path_counter():
    """The capture: 2 prefixes, 4 paths, add-path receive, prefixAccepted 4. The driver must not report 4 prefixes."""
    rows = [ln.split() for ln in fx("ceos4363m_rt0069_ceos1_ip_bgp.txt").splitlines() if f" {NEIGHBOR} " in ln]
    nets = [r[2] if r[1] == ">" else r[1] for r in rows]
    assert sorted(nets) == ["10.40.0.0/24"] * 2 + ["10.41.0.0/24"] * 2
    for name in ("ceos4363m_rt0069_ceos1_ip_bgp_summary_vrf.json", "ceos4363m_rt0069_ceos1_ip_bgp_summary.json"):
        peer = json.loads(fx(name))["vrfs"]["default"]["peers"][NEIGHBOR]
        assert (peer["prefixAccepted"], peer["prefixReceived"]) == (4, 4)
    nb = json.loads(fx("ceos4363m_rt0069_ceos1_ip_bgp_neighbor.json"))["vrfs"]["default"]["peerList"]
    assert [p["peerAddress"] for p in nb] == [NEIGHBOR]
    caps = nb[0]["neighborCapabilities"]["addPathsCaps"]["ipv4Unicast"]["receivingAddPaths"]
    assert caps["enabled"] is True and caps["sendCapabilityReceived"] is True
    # red on the current code: the driver's count for the neighbor is the summary's prefixAccepted (paths)
    try:
        got = EosDriver(CapturedLab(), "ceos1").bgp_neighbors().value[NEIGHBOR].prefixes.get("ipv4-unicast")
    except DriverError:
        return   # a refusal: never a count of the paths
    assert got != 4, (f"the driver reports {got} ipv4-unicast prefixes from {NEIGHBOR}: that is prefixAccepted, "
                      "which counts additional paths (4), while ceos1 accepted 2 prefixes")


def test_min_4_does_not_pass_on_two_prefixes():
    """The red team's check: `bgp_prefixes min: 4` passed on 2 prefixes. It must fail (a count of 2, or unreadable)."""
    r = positive(min=4)
    assert not r.passed, f"`min: 4` passed with 2 prefixes accepted from {NEIGHBOR}: {r.detail}"
