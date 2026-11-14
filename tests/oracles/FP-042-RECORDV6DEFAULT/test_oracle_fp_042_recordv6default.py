"""Oracle FP-042-RECORDV6DEFAULT (adversary n4f on 606d238, C1): a VRF without IPv6 BGP today and without an eBGP
session gets no ::/0 guard, though its IPv6 routes can be read.

record._guards decides per VRF:

    v6 = (IPv6 neighbors) or bool(bgp_now.get(6)) or (an IPv6 family on a session)
    ebgp = any established eBGP session
    if fam == 6 and not v6 and not (ebgp and 6 in bgp_now): continue

`6 in bgp_now` is how record knows the driver reads the VRF's IPv6 routes (all_routes(family=6) answered; RouterOS
raises "IPv6 routes are not supported" and is left out). The acceptance round B-3 rule writes ::/0 "wherever IPv6
routes can be read", but only for a VRF with an eBGP session. A VRF with a BGP instance and readable, empty IPv6
routes and no eBGP session (a sessionless `import vrf` VRF since FP-042-RECORDVRFNOSESS, the default VRF of a node
whose sessions are all in VRFs, or a VRF whose sessions are all iBGP) gets 0.0.0.0/0 and link guards but no ::/0 and
no line. A change that adds `address-family ipv6` + `import vrf` and leaks ::/0 into it passes every recorded check.
The ::/0 guard is evaluated on today's state, where the VRF has no IPv6 BGP route, so it holds on a good baseline.

No device output is involved: the node is a fake FRR driver for one PE, pe1, with the lab and links of
tests/oracles/FP-042-RECORDVRF (eth1 10.0.12.0/24, eth2 10.1.0.0/24). Its IPv6 routes can be read and are empty
today. Three shapes, each with one target VRF:
- "svc": the default VRF has an eBGP upstream 10.0.12.2 (198.51.100.0/24); VRF svc has a BGP instance, no neighbor
  and 10.10.0.0/24 via BGP (imported).
- "default": VRF cust has an eBGP customer 10.1.0.2 (10.10.0.0/24, 10.10.1.0/24); the default VRF has a BGP
  instance, no neighbor and 10.10.0.0/24 via BGP (imported from cust).
- "ibgp": the default VRF has the eBGP upstream; VRF cust has one iBGP IPv4 session to 10.1.0.2 (10.10.0.0/24).

The rule, either fix accepted: the target VRF gets a `route ::/0 protocol bgp present: false` guard with its `vrf:`
(none for the default VRF), or the baseline names the gap in an `INCOMPLETE BASELINE` line (first in the rendered
file) that names pe1, the VRF and IPv6 (or ::/0). End to end: after ::/0 leaks into the target VRF, a recorded check
of that VRF fails, or that line is there.
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
ADDRESSES = {(PE, "eth1"): "10.0.12.1/24", (PE, "eth2"): "10.1.0.1/24"}

# shape -> the VRF with a BGP instance, readable empty IPv6 routes, and no eBGP session
TARGET = {"svc": "svc", "default": "default", "ibgp": "cust"}
SHAPES = sorted(TARGET)
OTHER_VRFS = ("svc", "cust")
V6_UNSUPPORTED = "IPv6 routes are not supported on routeros yet"


class PeLab:
    """pe1 and its two links; the far ends (isp, ce1) are not routing nodes of this topology."""
    links = [((PE, "eth1"), ("isp", "eth1")), ((PE, "eth2"), ("ce1", "eth1"))]

    def __init__(self, topology):
        self.nodes = {PE: Node(PE, f"clab-t-{PE}", "linux", "quay.io/frrouting/frr:10.4.1")}

    def interface_addresses(self, node, iface):
        return [ipaddress.ip_interface(ADDRESSES[(node, iface)])]


class PeDrv(Driver):
    """FRR on pe1 in one of the shapes. `leaked` adds ::/0 via BGP to the target VRF. With `v6=False` the driver
    can't read IPv6 routes (all_routes(family=6) raises, as RouterOS does)."""
    name = "frr"
    reads_received = True
    unsupported_afis = frozenset()

    def __init__(self, shape, leaked=False, v6=True):
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
        if family == 6 and not self.v6:
            raise DriverError(V6_UNSUPPORTED)
        return Observation(self._table(vrf, family), [])

    def routes(self, prefix, vrf="default"):
        family = 6 if ":" in prefix else 4
        return Observation([r for r in self._table(vrf, family) if r.prefix == prefix],
                           [{"cmd": f"show {'ipv6' if family == 6 else 'ip'} route vrf {vrf}"}])


def record(monkeypatch, shape, v6=True, include_routes=True):
    monkeypatch.setattr(rec, "Lab", PeLab)
    monkeypatch.setattr(rec, "detect", lambda node: "frr")
    monkeypatch.setattr(rec, "for_node", lambda lab, name, *a: PeDrv(shape, v6=v6))
    return rec.record(Path("t.clab.yml"), include_routes=include_routes, guards=True, sleep=lambda s: None)


def judge(i: int, raw: dict, drv):
    """One recorded check through the real validator and check code, on a fake clock."""
    t = [0.0]
    return run_check(_validate_check(i, dict(raw), 20), drv, clock=lambda: t[0],
                     sleep=lambda s: t.__setitem__(0, t[0] + s))


def in_vrf(checks, vrf):
    return [c for c in checks if c.get("vrf", "default") == vrf]


def v6_default_guard(checks, vrf):
    want = {"type": "route", "node": PE, "prefix": "::/0", "protocol": "bgp", "present": False}
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


def v6_gap_lines(data, warnings, vrf):
    """The gap lines that name pe1, `vrf` and the IPv6 default. For the default VRF a line naming pe1 counts when it
    says "default" or names no other VRF of pe1."""
    out = []
    for line in gap_lines(data, warnings):
        if PE not in line or not ("::/0" in line or "IPv6" in line):
            continue
        if vrf != "default":
            named = f"vrf {vrf}" in line
        else:
            named = "default" in line or not any(f"vrf {v}" in line for v in OTHER_VRFS)
        if named:
            out.append(line)
    return out


@pytest.mark.parametrize("shape", SHAPES)
def test_a_vrf_whose_ipv6_routes_read_gets_its_v6_default_guard_or_a_gap_line(monkeypatch, shape):
    vrf = TARGET[shape]
    data, warnings = record(monkeypatch, shape)
    checks = data["checks"]
    assert any(c["type"] == "route" and c["prefix"] == "10.10.0.0/24" for c in in_vrf(checks, vrf))   # it is recorded
    assert any(c.get("prefix") == "0.0.0.0/0" and c.get("present") is False for c in in_vrf(checks, vrf))   # IPv4
    guarded = v6_default_guard(checks, vrf)
    named = v6_gap_lines(data, warnings, vrf)
    assert guarded or named, (
        f"pe1's IPv6 routes in VRF {vrf} can be read (empty today) and the VRF has a BGP instance, but as it has no "
        "IPv6 BGP and no eBGP session, record writes no ::/0 guard for it and no INCOMPLETE BASELINE line saying so; "
        f"a ::/0 leaked into it later passes the baseline. Checks of {vrf}: {in_vrf(checks, vrf)}; "
        f"warnings: {warnings}")


@pytest.mark.parametrize("shape", SHAPES)
def test_a_leaked_v6_default_in_the_vrf_fails_the_baseline_or_the_gap_is_named(monkeypatch, shape):
    """End to end: run the recorded checks of that VRF on the state where ::/0 leaked into it."""
    vrf = TARGET[shape]
    data, warnings = record(monkeypatch, shape)
    after = PeDrv(shape, leaked=True)
    mine = in_vrf(data["checks"], vrf)
    failed = [r.check.name for r in (judge(i, raw, after) for i, raw in enumerate(mine)) if not r.passed]
    assert failed or v6_gap_lines(data, warnings, vrf), (
        f"every check recorded for VRF {vrf} of pe1 passes after ::/0 leaks into it, and no INCOMPLETE BASELINE line "
        f"names the missing guard. Checks: {mine}")
