"""Regression tests from the 0.4 interop stress test (interop/, research/interop/REPORT.md).

Shapes captured live on 2026-10-31 in the L1 mixed-5 lab (cJunosEvolved 26.2R1.7-EVO, cEOS 4.36.3M, SR Linux 26.7.2,
FRR 10.4.1), lab addresses only. Each test fails on ndr/release-0.4.0 (81a49b3) and names its finding.
"""
from pathlib import Path

import pytest

from netdryrun.checks import hold_together
from netdryrun.config import Check
from netdryrun.drivers import DriverError, eos, junos
from netdryrun.drivers.base import BgpPath, Observation
from netdryrun.drivers.eos import EosDriver

from test_checks import FakeClock

FIX = Path(__file__).parent / "fixtures"


def read(name: str) -> str:
    return (FIX / name).read_text()


def _best(paths):
    return next(p for p in paths if p.best)


# ---- BLOCKER IOP-1: Junos reads a missing MED as 0, so `med: 0` passes on a path with no MED attribute.
# f1 (FRR) re-advertised 192.168.3.1/32 to j1 with no MED (FRR strips a MED learned from another AS before eBGP;
# its advertised-routes JSON has no `metric`). Junos' JSON for the route has no `metric` element at all.

def test_junos_path_without_med_element_has_no_med():
    best = _best(junos.parse_bgp_paths(read("junos_route_no_med.txt"), "192.168.3.1/32", "inet.0"))
    assert best.as_path == "65005 65003 65003"
    assert best.med is None, "no MED attribute must read as unknown (None), never 0"


def test_junos_path_with_med_0_still_reads_0():
    # control: f1's own network route arrives with MED 0, and Junos prints a `metric` element "0"
    best = _best(junos.parse_bgp_paths(read("junos_route_med0.txt"), "192.168.5.1/32", "inet.0"))
    assert best.med == 0


# ---- BLOCKER IOP-2: cEOS reports `"med": 0` for a path received with no MED, so `med: 0` passes.
# Same f1 advertisement (no `metric` toward a1); SR Linux and FRR receivers report the MED as not set, cEOS's
# `show ip bgp <prefix> | json` has "med": 0 on both paths. Either the driver tells absent from 0, or it refuses
# `med` assertions it can't make on eos (unsupported_bgp_attributes): it must never pass `med: 0` here.

def test_eos_missing_med_never_reads_as_0():
    best = _best(eos.parse_bgp_paths(read("eos_bgp_paths_no_med.txt"), "192.168.1.1/32"))
    assert "med" in EosDriver.unsupported_bgp_attributes or best.med is None


# ---- MAJOR IOP-3: cEOS prints an AS_SET with spaces ("{65004 65006}"); the driver keeps it, so the reference's
# form `as_path: "65005 {65004,65006}"` fails on cEOS while it passes on Junos and SR Linux for the same route.

def test_eos_as_set_is_normalised():
    best = _best(eos.parse_bgp_paths(read("eos_bgp_paths_as_set.txt"), "172.16.0.0/16"))
    assert best.as_path == "65005 {65004,65006}"


# ---- MAJOR IOP-4 (provisional): one unreadable sample fails a post-convergence check outright.
# Live: SR Linux answered one `info from state ... local-rib route 192.168.1.1/32 ...` with rc=1 "Parsing error:
# Unknown token '/'" (the same command succeeded 20 times right after), and C48 failed while the identical C49
# passed. The hold window had room for only one sample. An unreadable sample is not a violation of the
# condition: re-read within the window, and fail (fail-closed) only if the device keeps erroring.

class _FlakyThenGood:
    def __init__(self):
        self.calls = 0

    def bgp_paths(self, prefix, vrf="default"):
        self.calls += 1
        if self.calls == 1:
            raise DriverError("`sr_cli ...` failed on s1 (rc=1): Parsing error: Unknown token '/'")
        return Observation([BgpPath(best=True, as_path="65005 65001", next_hop="10.1.2.2", local_pref=100,
                                    med=None, communities=["65001:100"])], [])


@pytest.mark.xfail(strict=True, reason="IOP-4 is deferred to 0.4.1 (coordinator 2026-10-31): it fails closed today")
def test_one_transient_error_in_the_hold_window_is_reread():
    clock = FakeClock()
    c = Check("bgp_route", {"node": "s1", "prefix": "192.168.1.1/32", "communities": ["65001:100"]},
              "C48 s1 attrs j1-lo std", timeout=120)
    [r] = hold_together([c], {"s1": _FlakyThenGood()}, hold=10, interval=3, clock=clock, sleep=clock.sleep)
    assert r.passed, r.detail
