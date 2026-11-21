"""Oracle FP-042-RECORDVRFLISTFAIL (adversary n4f on 606d238, B1): a failed VRF-list read records the default VRF
only, with a plain warning, and exits 0.

record.record():

    vrfs = ["default"]
    try:
        vrfs += [v for v in drv.vrfs().value if v != "default"]
    except DriverError as e:
        warnings.append(f"{name}: only the default VRF is recorded ({e}); add checks for other VRFs by hand")

That `except` covers two different cases. A driver that can't list VRFs (the base Driver.vrfs, "listing VRFs is not
supported on eos yet", as on EOS and SR Linux) is documented, and a plain warning is right there. But a driver that
does list VRFs (FRR, SONiC, Junos, NX-OS, RouterOS) can fail the read: a vtysh, NETCONF/CLI, NX-API or REST timeout on
`show vrf`. Then every non-default VRF goes unrecorded (no session, prefix count, route or guard) and the only trace
is a `# warning:` comment, not a gap marker, so baseline_gaps() is empty and `record` exits 0. cli.md says "Every other
`INCOMPLETE BASELINE` line exits `1` too: a read that failed (a VRF, the routes, a prefix count)".

No device output is involved: the node is a fake FRR driver (a Driver subclass that implements vrfs()) for one PE,
pe1, with the lab and links of tests/oracles/FP-042-RECORDVRF: the default VRF has an eBGP upstream 10.0.12.2 on eth1
(10.0.12.0/24), VRF cust an eBGP customer 10.1.0.2 on eth2 (10.1.0.0/24) sending 10.10.0.0/24 and 10.10.1.0/24.
Here its vrfs() raises DriverError (`show vrf json` timed out), as a real read can.

The rule: the rendered file carries an `INCOMPLETE BASELINE` line (first in the file, so record exits 1) that names
pe1 and the VRF read. End to end: after 0.0.0.0/0 leaks into cust, a recorded check fails, or that line is there.
"""
import ipaddress
from pathlib import Path

from netdryrun import record as rec
from netdryrun.checks import run_check
from netdryrun.config import _validate_check
from netdryrun.drivers.base import BgpNeighbor, Driver, DriverError, Observation, Route
from netdryrun.lab import Node

PE = "pe1"
ADDRESSES = {(PE, "eth1"): "10.0.12.1/24", (PE, "eth2"): "10.1.0.1/24"}
TIMEOUT = "vtysh: `show vrf json` timed out after 60 s"


class PeLab:
    """pe1 and its two links; the far ends (isp, ce1) are not routing nodes of this topology."""
    links = [((PE, "eth1"), ("isp", "eth1")), ((PE, "eth2"), ("ce1", "eth1"))]

    def __init__(self, topology):
        self.nodes = {PE: Node(PE, f"clab-t-{PE}", "linux", "quay.io/frrouting/frr:10.4.1")}

    def interface_addresses(self, node, iface):
        return [ipaddress.ip_interface(ADDRESSES[(node, iface)])]


class PeState(Driver):
    """pe1's state: VRF default with upstream 10.0.12.2, VRF cust with customer 10.1.0.2. `leaked` adds the default
    route to cust. It does not implement vrfs(): the base Driver's "not supported" answer, as on EOS and SR Linux."""
    name = "eos"
    reads_received = True
    unsupported_afis = frozenset()

    def __init__(self, leaked=False):
        super().__init__(None, PE)
        self.leaked = leaked

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


class FrrPe(PeState):
    """The same state on FRR, which implements vrfs(). With `fail`, the VRF read times out."""
    name = "frr"

    def __init__(self, leaked=False, fail=True):
        super().__init__(leaked)
        self.fail = fail

    def vrfs(self):
        if self.fail:
            raise DriverError(TIMEOUT)
        return Observation(["cust"], [])


def record(monkeypatch, drv):
    monkeypatch.setattr(rec, "Lab", PeLab)
    monkeypatch.setattr(rec, "detect", lambda node: drv.name)
    monkeypatch.setattr(rec, "for_node", lambda lab, name, *a: drv)
    return rec.record(Path("t.clab.yml"), guards=True, sleep=lambda s: None)


def judge(i: int, raw: dict, drv):
    """One recorded check through the real validator and check code, on a fake clock."""
    t = [0.0]
    return run_check(_validate_check(i, dict(raw), 20), drv, clock=lambda: t[0],
                     sleep=lambda s: t.__setitem__(0, t[0] + s))


def gap_lines(data, warnings):
    """The INCOMPLETE BASELINE lines first in the rendered file that name pe1 and its VRFs (the VRF-list read)."""
    lines = []
    for line in rec.render(data, warnings).splitlines():
        if line == "#":
            break
        if line.startswith("# INCOMPLETE BASELINE") and PE in line and "vrf" in line.lower():
            lines.append(line)
    return lines


def test_a_failed_vrf_list_read_is_an_incomplete_baseline_line(monkeypatch):
    data, warnings = record(monkeypatch, FrrPe())
    assert any(c["type"] == "bgp_session" for c in data["checks"])   # the default VRF itself is recorded
    named = gap_lines(data, warnings)
    assert named and rec.baseline_gaps(warnings), (
        "pe1's driver lists VRFs (FRR), but its VRF read failed; record writes only a plain warning, records the "
        "default VRF alone and exits 0, so VRF cust has no session, route or guard in the baseline and no "
        f"INCOMPLETE BASELINE line says so. Warnings: {warnings}; gap lines: {rec.baseline_gaps(warnings)}")


def test_a_leaked_default_in_the_unlisted_vrf_fails_the_baseline_or_the_gap_is_named(monkeypatch):
    """End to end: run every recorded check on the state where 0.0.0.0/0 leaked into cust."""
    data, warnings = record(monkeypatch, FrrPe())
    after = FrrPe(leaked=True, fail=False)
    failed = [r.check.name for r in (judge(i, raw, after) for i, raw in enumerate(data["checks"])) if not r.passed]
    assert failed or gap_lines(data, warnings), (
        "every recorded check passes after 0.0.0.0/0 leaks into VRF cust, which went unrecorded because the VRF read "
        f"failed, and no INCOMPLETE BASELINE line names the gap. Checks: {data['checks']}; warnings: {warnings}")
