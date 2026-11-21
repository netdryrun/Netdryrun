"""`netdryrun record` fixes for oracles FP-042-RECORDVRFLISTFAIL and FP-042-RECORDV6DEFAULT (adversary n4f on 606d238,
B1 and C1).

B1: a driver that lists VRFs (its own vrfs(): FRR, SONiC, Junos, NX-OS, RouterOS) whose VRF-list read fails writes an
INCOMPLETE BASELINE line naming the node and the VRF list (record exits 1); a driver without its own vrfs() (the base
"not supported" answer: EOS, SR Linux) keeps the plain warning. C1: every VRF with a BGP instance whose IPv6 routes can
be read gets the `::/0 present: false` guard with its `vrf:`, IPv6 BGP or eBGP session today or not.

These tests kill: the plain warning kept for a driver that lists VRFs (and for one that inherits FRR's, SONiC), the
gap line for a driver that can't list them, a gap line that doesn't name the node or the VRF list, the old eBGP-only
::/0 rule, a ::/0 guard without the VRF's `vrf:`, a ::/0 guard where IPv6 routes can't be read, no ::/0 guard with
--no-routes, a ::/0 guard against what a VRF learns today, and an unevaluable ::/0 guard not named as a gap.
"""
import importlib.util
from pathlib import Path

import pytest

from netdryrun import record as rec
from netdryrun.drivers import DRIVERS
from netdryrun.drivers.base import BgpNeighbor, Driver, DriverError, Observation, Route
from netdryrun.drivers.sonic import SonicDriver


def _load(name, folder, module):
    path = Path(__file__).resolve().parent / "oracles" / folder / module
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


lf = _load("oracle_recordvrflistfail_unit", "FP-042-RECORDVRFLISTFAIL", "test_oracle_fp_042_recordvrflistfail.py")
v6 = _load("oracle_recordv6default_unit", "FP-042-RECORDV6DEFAULT", "test_oracle_fp_042_recordv6default.py")

GAP = ("INCOMPLETE BASELINE: pe1: could not list its VRFs ({e}), so only the default VRF is recorded and no other VRF "
       "has a session, route or guard: fix the read and record again, or add checks for other VRFs by hand")


# --- B1: the VRF-list read ---

def test_the_drivers_that_list_vrfs_are_the_ones_with_their_own_vrfs():
    own = sorted(n for n, cls in DRIVERS.items() if cls.vrfs is not Driver.vrfs)
    assert own == ["frr", "junos", "nxos", "routeros", "sonic"]   # cli.md: the drivers record covers VRFs on


def test_a_failed_vrf_list_read_is_one_exact_gap_line(monkeypatch):
    data, warnings = lf.record(monkeypatch, lf.FrrPe())
    gaps = rec.baseline_gaps(warnings)
    assert gaps == [GAP.format(e=lf.TIMEOUT)], warnings
    assert not [w for w in warnings if w.startswith("pe1: only the default VRF")], warnings
    assert rec.render(data, warnings).splitlines()[0] == f"# {GAP.format(e=lf.TIMEOUT)}"
    assert {c.get("vrf", "default") for c in data["checks"]} == {"default"}   # the default VRF is still recorded


def test_a_driver_without_its_own_vrfs_keeps_the_plain_warning(monkeypatch):
    _, warnings = lf.record(monkeypatch, lf.PeState())
    assert "pe1: only the default VRF is recorded (listing VRFs is not supported on eos yet); add checks for other " \
           "VRFs by hand" in warnings
    assert not rec.baseline_gaps(warnings), warnings


class SonicPe(SonicDriver):
    """A real SonicDriver (vrfs() inherited from FrrDriver) whose vtysh times out; the rest is the oracle's state."""

    def __init__(self):
        super().__init__(None, "pe1")
        self.state = lf.PeState()

    def _exec(self, cmd, evidence, *a, **k):
        raise DriverError("vtysh: `show vrf` timed out after 60 s")

    def bgp_neighbors(self, vrf="default"):
        return self.state.bgp_neighbors(vrf)

    def bgp_received(self, neighbor, afi="ipv4-unicast", vrf="default"):
        return self.state.bgp_received(neighbor, afi, vrf)

    def all_routes(self, vrf="default", family=4):
        return self.state.all_routes(vrf, family)

    def routes(self, prefix, vrf="default"):
        return self.state.routes(prefix, vrf)


def test_an_inherited_vrfs_counts_sonic_vrf_read_failure_is_a_gap(monkeypatch):
    drv = SonicPe()
    with pytest.raises(DriverError):
        drv.vrfs()
    _, warnings = lf.record(monkeypatch, drv)
    assert rec.baseline_gaps(warnings) == [GAP.format(e="vtysh: `show vrf` timed out after 60 s")], warnings


# --- C1: ::/0 wherever IPv6 routes can be read ---

def v6_guards(checks):
    return sorted((c.get("vrf", "default"), c) for c in checks
                  if c.get("prefix") == "::/0" and c.get("present") is False)


@pytest.mark.parametrize("shape", v6.SHAPES)
@pytest.mark.parametrize("include_routes", [True, False])
def test_every_vrf_with_readable_ipv6_routes_gets_its_v6_default_guard_with_its_vrf(monkeypatch, shape,
                                                                                    include_routes):
    data, warnings = v6.record(monkeypatch, shape, include_routes=include_routes)
    want = []
    for vrf in sorted(("default", v6.PeDrv(shape).other)):
        at = {} if vrf == "default" else {"vrf": vrf}
        want.append((vrf, {"type": "route", "node": "pe1", "prefix": "::/0", "protocol": "bgp", "present": False,
                           **at}))
    assert v6_guards(data["checks"]) == want
    assert not rec.baseline_gaps(warnings), warnings


def test_the_ibgp_only_default_vrf_gets_the_v6_default_guard(monkeypatch):
    """The old rule kept ::/0 for an established eBGP session only: an iBGP-only VRF went without."""

    class IbgpOnly(v6.PeDrv):
        def _sessions(self, vrf):
            return {"10.0.12.2": (1, False)} if vrf == "default" else {}

    monkeypatch.setattr(rec, "Lab", v6.PeLab)
    monkeypatch.setattr(rec, "detect", lambda node: "frr")
    monkeypatch.setattr(rec, "for_node", lambda lab, name, *a: IbgpOnly("svc"))
    data, _ = rec.record(Path("t.clab.yml"), guards=True, sleep=lambda s: None)
    assert {"type": "route", "node": "pe1", "prefix": "::/0", "protocol": "bgp", "present": False} in data["checks"]


@pytest.mark.parametrize("shape", v6.SHAPES)
def test_no_v6_default_guard_or_new_gap_where_ipv6_routes_cannot_be_read(monkeypatch, shape):
    data, warnings = v6.record(monkeypatch, shape, v6=False, include_routes=False)
    assert not v6_guards(data["checks"])
    assert not rec.baseline_gaps(warnings), warnings


class LearnsV6DefaultInSvc(v6.PeDrv):
    """VRF svc learns ::/0 today: no ::/0 guard there, a plain line says so; the default VRF keeps its own."""

    def _table(self, vrf, family=4):
        if family == 6 and vrf == "svc":
            return [Route("::/0", "bgp", True)]
        return super()._table(vrf, family)


def test_no_v6_default_guard_against_what_the_vrf_learns_today(monkeypatch):
    monkeypatch.setattr(rec, "Lab", v6.PeLab)
    monkeypatch.setattr(rec, "detect", lambda node: "frr")
    monkeypatch.setattr(rec, "for_node", lambda lab, name, *a: LearnsV6DefaultInSvc("svc"))
    data, warnings = rec.record(Path("t.clab.yml"), guards=True, sleep=lambda s: None)
    assert [v for v, _ in v6_guards(data["checks"])] == ["default"]
    assert "pe1 (vrf svc): learns ::/0 via BGP today; no 'no default route' guard recorded" in warnings
    assert not rec.baseline_gaps(warnings), warnings


class V6GuardUnreadable(v6.PeDrv):
    def routes(self, prefix, vrf="default"):
        if ":" in prefix and vrf == "svc":
            raise DriverError("vtysh: timed out")
        return super().routes(prefix, vrf)


def test_an_unevaluable_v6_default_guard_is_a_named_gap(monkeypatch):
    monkeypatch.setattr(rec, "Lab", v6.PeLab)
    monkeypatch.setattr(rec, "detect", lambda node: "frr")
    monkeypatch.setattr(rec, "for_node", lambda lab, name, *a: V6GuardUnreadable("svc"))
    data, warnings = rec.record(Path("t.clab.yml"), guards=True, sleep=lambda s: None)
    assert [v for v, _ in v6_guards(data["checks"])] == ["default"]
    gaps = rec.baseline_gaps(warnings)
    assert len(gaps) == 1 and gaps[0].startswith("INCOMPLETE BASELINE: pe1 (vrf svc): the guard against ::/0 via BGP "
                                                  "could not be evaluated on the lab"), warnings


def test_ipv6_neighbors_whose_routes_cannot_be_read_still_name_the_gap(monkeypatch):
    """v6 carried (an IPv6 session) but IPv6 routes unreadable: the INCOMPLETE line stays (unchanged since 0.3.3)."""

    class V6Session(v6.PeDrv):
        def bgp_neighbors(self, vrf="default"):
            if vrf == "default":
                return Observation({"2001:db8::2": BgpNeighbor("2001:db8::2", "established", {"ipv6-unicast": 0},
                                                               external=True)}, [])
            return super().bgp_neighbors(vrf)

    monkeypatch.setattr(rec, "Lab", v6.PeLab)
    monkeypatch.setattr(rec, "detect", lambda node: "frr")
    monkeypatch.setattr(rec, "for_node", lambda lab, name, *a: V6Session("svc", v6=False))
    _, warnings = rec.record(Path("t.clab.yml"), include_routes=False, guards=True, sleep=lambda s: None)
    assert rec.baseline_gaps(warnings) == [
        "INCOMPLETE BASELINE: pe1: IPv6 routes could not be read, so no IPv6 guards (no default route, no link subnet) "
        "were recorded for it"], warnings
