"""Oracle FP-042-RECORDVRF (angle-5 red team on 82fb052, B-RT-0074): `record` guards the default VRF only, silently.

website/docs/reference/cli.md says `record` "From 0.4 ... covers every active VRF on FRR and SONiC, each check with its
`vrf:`", and that its guards are written "on each BGP node, no default route via BGP ... and no link subnet of the
topology via BGP"; every baseline gap is an `# INCOMPLETE BASELINE` line first in the file. In 0.4.2 record.record()
passes the link subnets (and so turns the guards on) only for `vrf == "default"`. A VRF with an eBGP customer gets its
sessions and routes recorded with `vrf:`, but no `0.0.0.0/0` guard and no line saying so. A change that leaks the
default into the VRF (FRR `import vrf default` under `router bgp 65000 vrf cust`) then passes every recorded check of
the VRF. The red team's demo (candidates/B/scripts/rt0074_record_vrf_guards.py) shows it on `_record_vrf`; this oracle
runs the real `record.record()`.

No device output is involved: the node is a fake FRR driver (the shape of tests/test_record_vrfs.py) for one PE, pe1:
the default VRF has an eBGP upstream 10.0.12.2 on eth1 (10.0.12.0/24), VRF cust an eBGP customer 10.1.0.2 on eth2
(10.1.0.0/24, the attachment link) sending 10.10.0.0/24 and 10.10.1.0/24. Neither VRF has a default route today. The
lab is a fake with those two links and pe1's addresses on them (the peers are not in the topology's nodes).

The rule, either fix accepted: VRF cust gets a `route 0.0.0.0/0 protocol bgp present: false` guard carrying
`vrf: cust`, or the baseline names the gap in an `INCOMPLETE BASELINE` line (first in the rendered file) that names pe1
and cust. End to end: after the leak, a recorded check of cust fails, or that line is there.

Not asserted: the guard on the cust attachment subnet 10.1.0.0/24 that record writes without `vrf:` (so in pe1's
default VRF). The red team called it pointless; it is not a false pass, and in the default VRF it still catches the
customer subnet leaking into the global table, so a fix may keep it, move it into cust, or drop it.
"""
import ipaddress
from pathlib import Path

from netdryrun import record as rec
from netdryrun.checks import run_check
from netdryrun.config import _validate_check
from netdryrun.drivers.base import BgpNeighbor, Observation, Route
from netdryrun.lab import Node

PE = "pe1"
ADDRESSES = {(PE, "eth1"): "10.0.12.1/24", (PE, "eth2"): "10.1.0.1/24"}


class PeLab:
    """pe1 and its two links; the far ends (isp, ce1) are not routing nodes of this topology."""
    links = [((PE, "eth1"), ("isp", "eth1")), ((PE, "eth2"), ("ce1", "eth1"))]

    def __init__(self, topology):
        self.nodes = {PE: Node(PE, f"clab-t-{PE}", "linux", "quay.io/frrouting/frr:10.4.1")}

    def interface_addresses(self, node, iface):
        return [ipaddress.ip_interface(ADDRESSES[(node, iface)])]


class PeDrv:
    """FRR on pe1: VRF default with upstream 10.0.12.2, VRF cust with customer 10.1.0.2. `leaked` adds the default
    route to cust (the change the guards exist for)."""
    name = "frr"
    reads_received = True
    unsupported_afis = frozenset()

    def __init__(self, leaked=False):
        self.leaked = leaked

    def vrfs(self):
        return Observation(["cust"], [])

    def bgp_neighbors(self, vrf="default"):
        addr, n = ("10.0.12.2", 1) if vrf == "default" else ("10.1.0.2", 2)
        return Observation({addr: BgpNeighbor(addr, "established", {"ipv4-unicast": n}, external=True)}, [])

    def bgp_received(self, neighbor, afi="ipv4-unicast", vrf="default"):
        return Observation({"198.51.100.0/24"} if vrf == "default" else {"10.10.0.0/24", "10.10.1.0/24"}, [])

    def _table(self, vrf):
        if vrf == "default":
            return [Route("198.51.100.0/24", "bgp", True)]
        table = [Route("10.10.0.0/24", "bgp", True), Route("10.10.1.0/24", "bgp", True)]
        return table + ([Route("0.0.0.0/0", "bgp", True)] if self.leaked else [])

    def all_routes(self, vrf="default", family=4):
        return Observation(self._table(vrf) if family == 4 else [], [])

    def routes(self, prefix, vrf="default"):
        return Observation([r for r in self._table(vrf) if r.prefix == prefix], [{"cmd": f"show ip route vrf {vrf}"}])


def record(monkeypatch, drv=None):
    monkeypatch.setattr(rec, "Lab", PeLab)
    monkeypatch.setattr(rec, "detect", lambda node: "frr")
    monkeypatch.setattr(rec, "for_node", lambda lab, name, *a: drv or PeDrv())
    return rec.record(Path("t.clab.yml"), guards=True, sleep=lambda s: None)


def judge(i: int, raw: dict, drv):
    """One recorded check through the real validator and check code, on a fake clock."""
    t = [0.0]
    return run_check(_validate_check(i, dict(raw), 20), drv, clock=lambda: t[0],
                     sleep=lambda s: t.__setitem__(0, t[0] + s))


def default_guard(checks, vrf):
    want = {"type": "route", "node": PE, "prefix": "0.0.0.0/0", "protocol": "bgp", "present": False}
    return [c for c in checks if {k: c.get(k) for k in want} == want and c.get("vrf", "default") == vrf]


def gap_lines(data, warnings):
    """The INCOMPLETE BASELINE lines first in the rendered file that name pe1 and VRF cust."""
    lines = []
    for line in rec.render(data, warnings).splitlines():
        if line == "#":
            break
        if line.startswith("# INCOMPLETE BASELINE") and PE in line and "cust" in line:
            lines.append(line)
    return lines


def test_a_recorded_vrf_gets_its_default_route_guard_or_a_gap_line(monkeypatch):
    data, warnings = record(monkeypatch)
    checks = data["checks"]
    assert any(c.get("vrf") == "cust" and c["type"] == "bgp_session" for c in checks)   # cust itself is recorded
    guarded = default_guard(checks, "cust")
    named = gap_lines(data, warnings)
    assert guarded or named, (
        "record covers VRF cust (its session and routes carry vrf: cust) but writes no 0.0.0.0/0 guard for it and no "
        "INCOMPLETE BASELINE line saying so; a default leaked into cust passes the baseline. Guards written: "
        f"{[c for c in checks if c.get('present') is False]}; warnings: {warnings}")


def test_a_leaked_default_in_the_vrf_fails_the_baseline_or_the_gap_is_named(monkeypatch):
    """The red team's end-to-end form: run the recorded VRF checks on the leaked state."""
    data, warnings = record(monkeypatch)
    after = PeDrv(leaked=True)
    cust = [c for c in data["checks"] if c.get("vrf") == "cust"]
    failed = [r.check.name for r in (judge(i, raw, after) for i, raw in enumerate(cust)) if not r.passed]
    assert failed or gap_lines(data, warnings), (
        "every check recorded for VRF cust passes after 0.0.0.0/0 leaks into it, and no INCOMPLETE BASELINE line "
        "names the missing guard")
