"""Oracle FP-043-VRFLIST: a node whose VRF list can't be read must be a gap in the baseline, never a plain warning.

`record` reads each node's VRF list and records every VRF in it. 0.4.2 (f4b5e6a, record.py:148): when that read fails,
it writes "<node>: only the default VRF is recorded (...)", a plain warning, and goes on. `baseline_gaps` doesn't count
it, so `record` exits 0 while every session and route in the node's other VRFs is missing from the baseline. That is
the RT-0066 pattern (FP-042-UNNSESS): state left out, exit 0.

The rule: a VRF list that couldn't be read is an INCOMPLETE BASELINE line naming the node (and saying the VRFs are what
is missing), so `record` exits 1.

The test goes through `record.record` with the real FRR driver on one node, r1. Its `vtysh -c show vrf` read fails, rc
1. The failure text "zebra is not running" is constructed after the live one bgpd gives (`bgpd is not running`, in
tests/fixtures/report-real-failed-bgpd-down.json); the path it takes is the real one: FrrDriver.vrfs() -> _exec raises
DriverError with the last line. The default VRF reads its live BGP neighbors (tests/fixtures/frr_bgp_neighbors.txt).

The tests here fail on the parent. The guards, which pass before and after the fix, are in
tests/test_oracle_guards_fp_043_vrflist.py (listed in ORACLE.yml `evidence:`).
"""
from pathlib import Path

from netdryrun import record as rec
from netdryrun.drivers.base import Observation
from netdryrun.drivers.frr import FrrDriver
from netdryrun.lab import ExecResult, Node

FX = Path(__file__).resolve().parents[2] / "fixtures"
NEIGHBORS = (FX / "frr_bgp_neighbors.txt").read_text(encoding="utf-8")   # live, FRR example lab
VRF_FAILS = ExecResult([], 1, "", "zebra is not running\n")


class OneNodeLab:
    """r1 (FRR). `show vrf` answers as given; the default VRF's BGP neighbors are the live capture."""

    def __init__(self, show_vrf: ExecResult):
        self.nodes = {"r1": Node("r1", "clab-x-r1", "linux", "quay.io/frrouting/frr:10.4.1")}
        self.links = []
        self.answers = {"vtysh -c show vrf": show_vrf,
                        "vtysh -c show bgp neighbors json": ExecResult([], 0, NEIGHBORS, "")}

    def exec(self, node, cmd, timeout=60, input=None):
        a = self.answers.get(" ".join(cmd))
        return ExecResult(list(cmd), a.rc, a.stdout, a.stderr) if a else ExecResult(list(cmd), 1, "", "not captured")


class Driver(FrrDriver):
    """The real FRR driver; only the route reads are stubbed (empty), so the BGP and VRF reads go through lab.exec."""

    def all_routes(self, vrf="default", family=4):
        return Observation([], [])

    def routes(self, prefix, vrf="default"):
        return Observation([], [])


def record(monkeypatch, lab):
    drv = Driver(lab, "r1")
    monkeypatch.setattr(rec, "Lab", lambda topology: lab)
    monkeypatch.setattr(rec, "detect", lambda node: "frr")
    monkeypatch.setattr(rec, "for_node", lambda lab_, name, *a: drv)
    return rec.record(Path("topology.clab.yml"), sleep=lambda s: None)


def vrf_gaps(warnings, node):
    return [w for w in rec.baseline_gaps(warnings)
            if w.startswith("INCOMPLETE BASELINE") and node in w and "vrf" in w.lower()]


# ------------------------------------------------------------------ red on 0.4.2 (f4b5e6a)

def test_an_unreadable_vrf_list_is_a_gap(monkeypatch):
    _, warnings = record(monkeypatch, OneNodeLab(VRF_FAILS))
    assert vrf_gaps(warnings, "r1"), f"record exits 0 with r1's other VRFs unrecorded: {warnings}"
