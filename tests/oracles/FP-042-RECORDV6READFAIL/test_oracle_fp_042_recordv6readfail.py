"""Oracle FP-042-RECORDV6READFAIL (adversary n4i on 57eb8ca, B1 and D1): under `record --no-routes`, a failed IPv6
route read on a driver that can read IPv6 silently drops the ::/0 guard and the IPv6 link-subnet guards.

record._record_vrf, with include_routes=False, turns a DriverError from all_routes(family=6) into a plain warning
("{where}: could not read IPv6 routes (...)"), never an INCOMPLETE BASELINE line, and leaves 6 out of bgp_now. Then
record._guards skips the IPv6 family without a line:

    if fam == 6 and not v6 and 6 not in bgp_now: continue

and drops every IPv6 link subnet (`n not in bgp_now.get(6, {n})`). baseline_gaps is empty, record exits 0, and a
::/0 leaked into the VRF later passes every recorded check. The IPv4 counterpart is an INCOMPLETE line
(`fam not in bgp_now`), and with routes recorded the IPv6 read failure is one too. Only a driver that can't read IPv6
at all (RouterOS: "IPv6 routes are not supported") may stay silent: that is in
tests/test_oracle_guards_fp_042_recordv6readfail.py.

No device output is involved: the node is a fake FRR driver for one PE, pe1, the lab and shapes of
tests/oracles/FP-042-RECORDV6DEFAULT (copied here so this oracle stands alone), with one more address: eth2 also has
2001:db8:1::1/64, so the topology has an IPv6 link subnet. The driver's IPv6 route read fails the way a vtysh timeout
does (`_exec`'s rc != 0 message); every other read, `routes("::/0")` included, answers.

The rule, either fix accepted, for every VRF of pe1 (the default VRF and the other one):
- ::/0: a `route ::/0 protocol bgp present: false` guard with the VRF's `vrf:`, or an `INCOMPLETE BASELINE` line
  (first in the rendered file) naming pe1, the VRF and IPv6 (or ::/0);
- the IPv6 link subnet 2001:db8:1::/64: a `present: false` guard with the VRF's `vrf:`, or such a line naming IPv6 (or
  the subnet).
End to end: after ::/0 leaks into the target VRF of the shape, a recorded check of that VRF fails, or that line is
there.
"""
import ipaddress
from pathlib import Path

import pytest

from netdryrun import record as rec
from netdryrun.checks import run_check
from netdryrun.config import _validate_check
from netdryrun.drivers.base import BgpNeighbor, Driver, DriverError, Observation, Route
from netdryrun.lab import Node

PE = "pe1"
ADDRESSES = {(PE, "eth1"): ["10.0.12.1/24"], (PE, "eth2"): ["10.1.0.1/24", "2001:db8:1::1/64"]}
V6_LINK = "2001:db8:1::/64"

# shape -> the VRF with a BGP instance, no IPv6 BGP and no eBGP session (the FP-042-RECORDV6DEFAULT target)
TARGET = {"svc": "svc", "default": "default", "ibgp": "cust"}
SHAPES = sorted(TARGET)
OTHER_VRFS = ("svc", "cust")
V6_TIMEOUT = "`vtysh -c show ipv6 route json` failed on pe1 (rc=1): % timed out waiting for zebra"
V6_UNSUPPORTED = "IPv6 routes are not supported on routeros yet"


class PeLab:
    """pe1 and its two links; the far ends (isp, ce1) are not routing nodes of this topology."""
    links = [((PE, "eth1"), ("isp", "eth1")), ((PE, "eth2"), ("ce1", "eth1"))]

    def __init__(self, topology):
        self.nodes = {PE: Node(PE, f"clab-t-{PE}", "linux", "quay.io/frrouting/frr:10.4.1")}

    def interface_addresses(self, node, iface):
        return [ipaddress.ip_interface(a) for a in ADDRESSES[(node, iface)]]


class PeDrv(Driver):
    """FRR on pe1 in one of the shapes. `leaked` adds ::/0 via BGP to the target VRF. `v6` is how all_routes answers
    for family 6: "ok" (reads, empty today), "fail" (a transient failure on a driver that reads IPv6) or "unsupported"
    (RouterOS's constant answer)."""
    name = "frr"
    reads_received = True
    unsupported_afis = frozenset()

    def __init__(self, shape, leaked=False, v6="ok"):
        super().__init__(None, PE)
        self.shape = shape
        self.leaked = leaked
        self.v6 = v6
        self.other = "svc" if shape == "svc" else "cust"

    def vrfs(self):
        return Observation([self.other], [])

    def _sessions(self, vrf):
        """address -> (prefix count, eBGP?)"""
        if self.shape == "default":
            return {} if vrf == "default" else {"10.1.0.2": (2, True)}
        if vrf == "default":
            return {"10.0.12.2": (1, True)}
        return {} if self.shape == "svc" else {"10.1.0.2": (1, False)}

    def bgp_neighbors(self, vrf="default"):
        return Observation({a: BgpNeighbor(a, "established", {"ipv4-unicast": n}, external=ext)
                            for a, (n, ext) in self._sessions(vrf).items()}, [])

    def bgp_received(self, neighbor, afi="ipv4-unicast", vrf="default"):
        if afi != "ipv4-unicast":
            return Observation(set(), [])
        if neighbor == "10.0.12.2":
            return Observation({"198.51.100.0/24"}, [])
        if self.shape == "ibgp":
            return Observation({"10.10.0.0/24"}, [])
        return Observation({"10.10.0.0/24", "10.10.1.0/24"}, [])

    def _table(self, vrf, family=4):
        if family == 6:
            return [Route("::/0", "bgp", True)] if self.leaked and vrf == TARGET[self.shape] else []
        if vrf == "default" and self.shape != "default":
            return [Route("198.51.100.0/24", "bgp", True)]
        if vrf == "cust" and self.shape == "default":
            return [Route("10.10.0.0/24", "bgp", True), Route("10.10.1.0/24", "bgp", True)]
        return [Route("10.10.0.0/24", "bgp", True)]

    def all_routes(self, vrf="default", family=4):
        if family == 6 and self.v6 == "fail":
            raise DriverError(V6_TIMEOUT)
        if family == 6 and self.v6 == "unsupported":
            raise DriverError(V6_UNSUPPORTED)
        return Observation(self._table(vrf, family), [])

    def routes(self, prefix, vrf="default"):
        family = 6 if ":" in prefix else 4
        if family == 6 and self.v6 == "unsupported":
            raise DriverError(f"{prefix}: {V6_UNSUPPORTED}")
        return Observation([r for r in self._table(vrf, family) if r.prefix == prefix],
                           [{"cmd": f"show {'ipv6' if family == 6 else 'ip'} route vrf {vrf}"}])


def record(monkeypatch, shape, v6="fail", include_routes=False, drv_class=PeDrv):
    monkeypatch.setattr(rec, "Lab", PeLab)
    monkeypatch.setattr(rec, "detect", lambda node: "frr")
    monkeypatch.setattr(rec, "for_node", lambda lab, name, *a: drv_class(shape, v6=v6))
    return rec.record(Path("t.clab.yml"), include_routes=include_routes, guards=True, sleep=lambda s: None)


def judge(i: int, raw: dict, drv):
    """One recorded check through the real validator and check code, on a fake clock."""
    t = [0.0]
    return run_check(_validate_check(i, dict(raw), 20), drv, clock=lambda: t[0],
                     sleep=lambda s: t.__setitem__(0, t[0] + s))


def in_vrf(checks, vrf):
    return [c for c in checks if c.get("vrf", "default") == vrf]


def absent_guard(checks, vrf, prefix):
    want = {"type": "route", "node": PE, "prefix": prefix, "protocol": "bgp", "present": False}
    return [c for c in in_vrf(checks, vrf) if {k: c.get(k) for k in want} == want]


def gap_lines(data, warnings):
    """Every INCOMPLETE BASELINE line first in the rendered file."""
    lines = []
    for line in rec.render(data, warnings).splitlines():
        if line == "#":
            break
        if line.startswith("# INCOMPLETE BASELINE"):
            lines.append(line)
    return lines


def v6_gap_lines(data, warnings, vrf, *names):
    """The gap lines that name pe1, `vrf` and IPv6 (or one of `names`). For the default VRF a line naming pe1 counts
    when it says "default" or names no other VRF of pe1."""
    out = []
    for line in gap_lines(data, warnings):
        if PE not in line or not ("IPv6" in line or any(n in line for n in names)):
            continue
        if vrf != "default":
            named = f"vrf {vrf}" in line
        else:
            named = "default" in line or not any(f"vrf {v}" in line for v in OTHER_VRFS)
        if named:
            out.append(line)
    return out


def vrfs_of(shape):
    return ("default", PeDrv(shape).other)


CASES = [(s, v) for s in SHAPES for v in vrfs_of(s)]


@pytest.mark.parametrize("shape,vrf", CASES)
def test_a_failed_ipv6_read_under_no_routes_keeps_the_v6_default_guard_or_names_the_gap(monkeypatch, shape, vrf):
    data, warnings = record(monkeypatch, shape)
    checks = data["checks"]
    assert any(c.get("prefix") == "0.0.0.0/0" and c.get("present") is False for c in in_vrf(checks, vrf))   # IPv4
    assert absent_guard(checks, vrf, "::/0") or v6_gap_lines(data, warnings, vrf, "::/0"), (
        f"pe1 is FRR, which reads IPv6 routes, but its IPv6 route read in VRF {vrf} failed once ({V6_TIMEOUT}); "
        "under --no-routes record writes no ::/0 guard for the VRF and no INCOMPLETE BASELINE line, only a plain "
        f"warning, so it exits 0 and a ::/0 leaked into the VRF later passes. Checks of {vrf}: "
        f"{in_vrf(checks, vrf)}; gaps: {rec.baseline_gaps(warnings)}; warnings: {warnings}")


@pytest.mark.parametrize("shape,vrf", CASES)
def test_a_failed_ipv6_read_under_no_routes_keeps_the_v6_link_guard_or_names_the_gap(monkeypatch, shape, vrf):
    data, warnings = record(monkeypatch, shape)
    checks = data["checks"]
    assert absent_guard(checks, vrf, "10.1.0.0/24")   # the IPv4 link subnet of the same link is guarded
    assert absent_guard(checks, vrf, V6_LINK) or v6_gap_lines(data, warnings, vrf, V6_LINK), (
        f"pe1's IPv6 route read in VRF {vrf} failed once ({V6_TIMEOUT}); under --no-routes the guard against the "
        f"IPv6 link subnet {V6_LINK} is dropped with no INCOMPLETE BASELINE line. Checks of {vrf}: "
        f"{in_vrf(checks, vrf)}; gaps: {rec.baseline_gaps(warnings)}")


@pytest.mark.parametrize("shape", SHAPES)
def test_a_leaked_v6_default_fails_the_no_routes_baseline_or_the_gap_is_named(monkeypatch, shape):
    """End to end: record with the IPv6 read failing, then run the recorded checks of the target VRF on the state
    where ::/0 leaked into it (the IPv6 table now reads)."""
    vrf = TARGET[shape]
    data, warnings = record(monkeypatch, shape)
    after = PeDrv(shape, leaked=True)
    mine = in_vrf(data["checks"], vrf)
    failed = [r.check.name for r in (judge(i, raw, after) for i, raw in enumerate(mine)) if not r.passed]
    assert failed or v6_gap_lines(data, warnings, vrf, "::/0"), (
        f"every check recorded (--no-routes) for VRF {vrf} of pe1 passes after ::/0 leaks into it, and no "
        f"INCOMPLETE BASELINE line names the missing guard; record exits {1 if rec.baseline_gaps(warnings) else 0}. "
        f"Checks: {mine}")
