"""Oracle FP-042-FRRGRSTALE (repro-042c F-GR): stale graceful-restart paths counted as accepted prefixes.

What the router showed (FRR 10.4.1, containerlab lab ndr-rpgr, captured 2026-11-13; lab files
tests/fixtures/frr1041_rpgr_{topology.clab.yml,checks*.yml,*.conf}, captures tests/fixtures/frr1041_rpgr_r1_*):
- r1 (AS 65001, `bgp graceful-restart`, stalepath-time 300) peers with 10.0.13.2 (AS 65002, graceful restart with
  `preserve-fw-state`, so F-bit true), which sent 10.70.1-4.0/24;
- the peer's config was changed to send 10.70.1-3.0/24 only, with `coalesce-time 90000` holding back its first update
  and End-of-RIB, and its bgpd was killed; watchfrr restarted it on the new config;
- in the window after the session came back (the answer netdryrun read, frr1041_rpgr_r1_neighbors_stale.json):
  Established, ipv4Unicast fBit true, endOfRibStatus.endOfRibRecv false (top-level endOfRibRecv `{}`),
  acceptedPrefixCounter 4; `show bgp ipv4 unicast` lists 4 paths marked `S` (stale), 10.70.4.0/24 among them;
- after End-of-RIB (frr1041_rpgr_r1_neighbors_after_eor.json): endOfRibRecv true, acceptedPrefixCounter 3, 3 paths
  without `S`.
The 0.4.2 FRR driver reads acceptedPrefixCounter as the count, and `bgp_prefixes min` is a positive check that runs
before End-of-RIB settles anything, so `min: 4` passed in the window ("4 ipv4-unicast prefixes accepted",
tests/fixtures/frr1041_rpgr_report.json) though the peer sent 3.

The rule: while End-of-RIB from the peer is pending after a graceful restart, the counter includes stale paths and
settles no count. Neither `min: 4` (false: the peer sends 3) nor `min: 3` (true only by luck, counted on stale paths)
may pass on the window capture; failing or not-ready both satisfy the oracle. After End-of-RIB `min: 3` must pass:
that control is a guard (tests/test_oracle_guards_fp_042_frrgrstale.py), because it passes before the fix too.

Reads the capture doesn't cover answer rc 1 (an unknown command): the oracle knows nothing else r1 would have said.
"""
import json
from pathlib import Path

from netdryrun.checks import run_check
from netdryrun.config import _validate_check
from netdryrun.drivers.frr import FrrDriver
from netdryrun.lab import ExecResult

FX = Path(__file__).resolve().parents[2] / "fixtures"
NEIGHBOR = "10.0.13.2"
NEIGHBORS = "show bgp neighbors json"
STALE = "frr1041_rpgr_r1_neighbors_stale.json"        # inside the stale window, End-of-RIB pending
AFTER_EOR = "frr1041_rpgr_r1_neighbors_after_eor.json"


def fx(name: str) -> str:
    return (FX / name).read_text(encoding="utf-8")


class CapturedLab:
    """r1 as captured at one moment. A command that wasn't captured answers as an unknown command (rc=1)."""

    def __init__(self, neighbors: str):
        self.captured = {NEIGHBORS: neighbors}

    def exec(self, node, cmd, timeout=60, input=None):
        if node == "r1" and cmd[:2] == ["vtysh", "-c"] and len(cmd) == 3 and cmd[2] in self.captured:
            return ExecResult(cmd, 0, fx(self.captured[cmd[2]]), "")
        return ExecResult(cmd, 1, "", f"not captured: {' '.join(cmd)}")


class Clock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t

    def sleep(self, s):
        self.t += max(s, 0.5)


def prefixes_check(capture: str, **raw):
    c = Clock()
    check = _validate_check(0, {"node": "r1", "type": "bgp_prefixes", "neighbor": NEIGHBOR, **raw}, 20)
    return run_check(check, FrrDriver(CapturedLab(capture), "r1"), clock=c, sleep=c.sleep)


def window_facts():
    """What the window capture says: Established, F-bit set, End-of-RIB pending, the counter at 4 (stale paths)."""
    n = json.loads(fx(STALE))[NEIGHBOR]
    g = n["gracefulRestartInfo"]
    assert n["bgpState"] == "Established"
    assert g["ipv4Unicast"]["fBit"] is True and g["ipv4Unicast"]["endOfRibStatus"]["endOfRibRecv"] is False
    assert g["endOfRibRecv"] == {}
    assert n["addressFamilyInfo"]["ipv4Unicast"]["acceptedPrefixCounter"] == 4
    table = fx("frr1041_rpgr_r1_ipv4_stale.txt")
    assert sum(line.startswith(" S>") for line in table.splitlines()) == 4 and " S>  10.70.4.0/24" in table
    assert "10.70.4.0/24" not in fx("frr1041_rpgr_peer_restarted.conf")   # the restarted peer sends 3


def test_min4_does_not_pass_on_stale_paths():
    """The live false pass: `min: 4` passed in the stale window while the peer sent 3. It must not pass."""
    window_facts()
    r = prefixes_check(STALE, min=4)
    assert not r.passed, (f"`bgp_prefixes min: 4` passed with End-of-RIB from {NEIGHBOR} pending and 4 stale paths "
                          f"counted, though the restarted peer sends 3: {r.detail}")


def test_min3_does_not_pass_on_stale_paths():
    """Stale paths settle nothing: `min: 3` must not pass on the same window either, though 3 is the true count."""
    window_facts()
    r = prefixes_check(STALE, min=3)
    assert not r.passed, (f"`bgp_prefixes min: 3` passed on a count of stale paths, End-of-RIB from {NEIGHBOR} "
                          f"pending: {r.detail}")
