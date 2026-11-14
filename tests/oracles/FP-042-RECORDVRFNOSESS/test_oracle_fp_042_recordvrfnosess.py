"""Oracle FP-042-RECORDVRFNOSESS (adversary n4c on cf460d6, B1): a VRF with BGP routes but no BGP session is recorded
with no guard and no gap line.

The FP-042-RECORDVRF fix gives every VRF its guards, but only `if link_subnets is not None and neighbors:` in
record._record_vrf. A VRF with a BGP instance and BGP routes but no neighbor is the normal shape of a shared-services
or route-leak VRF (FRR `router bgp 65000 vrf svc` + `import vrf ...`). Its BGP routes are recorded as `route` checks
with `vrf: svc`, but it gets no `0.0.0.0/0` guard, no warning and no INCOMPLETE BASELINE line. The advisory's own leak
example (FRR `import vrf default`) is exactly what feeds such a VRF, and a default leaked into it then passes every
recorded check. The same holds for the default VRF of a node whose BGP sessions are all in VRFs while its default VRF
holds BGP routes imported from them (pre-existing since 0.3.3; the same fix covers it).

No device output is involved: the node is a fake FRR driver for one PE, pe1, with the lab and links of
tests/oracles/FP-042-RECORDVRF (eth1 10.0.12.0/24, eth2 10.1.0.0/24). Two shapes:
- "vrf": the default VRF has an eBGP upstream 10.0.12.2 and 198.51.100.0/24; VRF svc has a BGP instance, no
  neighbor, and 10.10.0.0/24 via BGP (imported).
- "default": VRF cust has an eBGP customer 10.1.0.2 sending 10.10.0.0/24 and 10.10.1.0/24; the default VRF has a BGP
  instance, no neighbor, and 10.10.0.0/24 via BGP (imported from cust).
Both shapes also list VRF mgmt, which has no BGP instance (NoSuchInstance): nothing is expected for it.

The rule, either fix accepted: the sessionless VRF gets a `route 0.0.0.0/0 protocol bgp present: false` guard with
its `vrf:` (none for the default VRF), or the baseline names the gap in an `INCOMPLETE BASELINE` line (first in the
rendered file) that names pe1 and the VRF. End to end: after the leak, a recorded check of that VRF fails, or that
line is there.
"""
import ipaddress
from pathlib import Path

import pytest

from netdryrun import record as rec
from netdryrun.checks import run_check
from netdryrun.config import _validate_check
from netdryrun.drivers.base import BgpNeighbor, NoSuchInstance, Observation, Route
from netdryrun.lab import Node

PE = "pe1"
ADDRESSES = {(PE, "eth1"): "10.0.12.1/24", (PE, "eth2"): "10.1.0.1/24"}

# shape -> the VRF that has a BGP instance and BGP routes but no session
SESSIONLESS = {"vrf": "svc", "default": "default"}
SHAPES = sorted(SESSIONLESS)


class PeLab:
    """pe1 and its two links; the far ends (isp, ce1) are not routing nodes of this topology."""
    links = [((PE, "eth1"), ("isp", "eth1")), ((PE, "eth2"), ("ce1", "eth1"))]

    def __init__(self, topology):
        self.nodes = {PE: Node(PE, f"clab-t-{PE}", "linux", "quay.io/frrouting/frr:10.4.1")}

    def interface_addresses(self, node, iface):
        return [ipaddress.ip_interface(ADDRESSES[(node, iface)])]


class PeDrv:
    """FRR on pe1 in one of the two shapes. `leaked` adds 0.0.0.0/0 via BGP to the sessionless VRF."""
    name = "frr"
    reads_received = True
    unsupported_afis = frozenset()

    def __init__(self, shape, leaked=False):
        self.shape = shape
        self.leaked = leaked
        self.other = "svc" if shape == "vrf" else "cust"

    def vrfs(self):
        return Observation([self.other, "mgmt"], [])

    def _sessions(self, vrf):
        if vrf == "mgmt":
            raise NoSuchInstance("BGP instance for VRF mgmt not found")
        if self.shape == "vrf":
            return {"10.0.12.2": 1} if vrf == "default" else {}
        return {} if vrf == "default" else {"10.1.0.2": 2}

    def bgp_neighbors(self, vrf="default"):
        return Observation({a: BgpNeighbor(a, "established", {"ipv4-unicast": n}, external=True)
                            for a, n in self._sessions(vrf).items()}, [])

    def bgp_received(self, neighbor, afi="ipv4-unicast", vrf="default"):
        if neighbor == "10.0.12.2":
            return Observation({"198.51.100.0/24"}, [])
        return Observation({"10.10.0.0/24", "10.10.1.0/24"}, [])

    def _table(self, vrf):
        if vrf == "mgmt":
            return []
        if self.shape == "vrf":
            table = [Route("198.51.100.0/24", "bgp", True)] if vrf == "default" else [Route("10.10.0.0/24", "bgp", True)]
        else:
            table = ([Route("10.10.0.0/24", "bgp", True)] if vrf == "default"
                     else [Route("10.10.0.0/24", "bgp", True), Route("10.10.1.0/24", "bgp", True)])
        if self.leaked and vrf == SESSIONLESS[self.shape]:
            table = table + [Route("0.0.0.0/0", "bgp", True)]
        return table

    def all_routes(self, vrf="default", family=4):
        return Observation(self._table(vrf) if family == 4 else [], [])

    def routes(self, prefix, vrf="default"):
        return Observation([r for r in self._table(vrf) if r.prefix == prefix], [{"cmd": f"show ip route vrf {vrf}"}])


def record(monkeypatch, shape):
    monkeypatch.setattr(rec, "Lab", PeLab)
    monkeypatch.setattr(rec, "detect", lambda node: "frr")
    monkeypatch.setattr(rec, "for_node", lambda lab, name, *a: PeDrv(shape))
    return rec.record(Path("t.clab.yml"), guards=True, sleep=lambda s: None)


def judge(i: int, raw: dict, drv):
    """One recorded check through the real validator and check code, on a fake clock."""
    t = [0.0]
    return run_check(_validate_check(i, dict(raw), 20), drv, clock=lambda: t[0],
                     sleep=lambda s: t.__setitem__(0, t[0] + s))


def in_vrf(checks, vrf):
    return [c for c in checks if c.get("vrf", "default") == vrf]


def default_guard(checks, vrf):
    want = {"type": "route", "node": PE, "prefix": "0.0.0.0/0", "protocol": "bgp", "present": False}
    return [c for c in in_vrf(checks, vrf) if {k: c.get(k) for k in want} == want]


def gap_lines(data, warnings, vrf):
    """The INCOMPLETE BASELINE lines first in the rendered file that name pe1 and `vrf`. For the default VRF a line
    naming pe1 counts when it says "default" or names no other VRF of pe1."""
    lines = []
    for line in rec.render(data, warnings).splitlines():
        if line == "#":
            break
        if not (line.startswith("# INCOMPLETE BASELINE") and PE in line):
            continue
        if vrf != "default":
            named = vrf in line
        else:
            named = "default" in line or not any(v in line for v in ("svc", "cust", "mgmt"))
        if named:
            lines.append(line)
    return lines


@pytest.mark.parametrize("shape", SHAPES)
def test_a_sessionless_vrf_with_bgp_routes_gets_its_default_route_guard_or_a_gap_line(monkeypatch, shape):
    vrf = SESSIONLESS[shape]
    data, warnings = record(monkeypatch, shape)
    checks = data["checks"]
    assert any(c["type"] == "route" and c["prefix"] == "10.10.0.0/24" for c in in_vrf(checks, vrf))   # it is recorded
    guarded = default_guard(checks, vrf)
    named = gap_lines(data, warnings, vrf)
    assert guarded or named, (
        f"record covers VRF {vrf} of pe1 (its BGP route 10.10.0.0/24 is recorded) but, as the VRF has no BGP session, "
        "writes no 0.0.0.0/0 guard for it and no INCOMPLETE BASELINE line saying so; a default leaked into it passes "
        f"the baseline. Checks of {vrf}: {in_vrf(checks, vrf)}; warnings: {warnings}")


@pytest.mark.parametrize("shape", SHAPES)
def test_a_leaked_default_in_the_sessionless_vrf_fails_the_baseline_or_the_gap_is_named(monkeypatch, shape):
    """End to end: run the recorded checks of that VRF on the leaked state."""
    vrf = SESSIONLESS[shape]
    data, warnings = record(monkeypatch, shape)
    after = PeDrv(shape, leaked=True)
    mine = in_vrf(data["checks"], vrf)
    failed = [r.check.name for r in (judge(i, raw, after) for i, raw in enumerate(mine)) if not r.passed]
    assert failed or gap_lines(data, warnings, vrf), (
        f"every check recorded for VRF {vrf} of pe1 passes after 0.0.0.0/0 leaks into it, and no INCOMPLETE BASELINE "
        f"line names the missing guard. Checks: {mine}")
