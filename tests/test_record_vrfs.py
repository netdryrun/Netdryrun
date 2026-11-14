"""`netdryrun record` beyond the default VRF (0.3.3 cross-platform review, scheduled for 0.4): every active VRF a
driver can list is recorded, its checks carrying `vrf:`; a driver that can't list VRFs yet records the default
VRF and says so in a warning, never silently."""
from pathlib import Path

import pytest

from netdryrun import record as rec
from netdryrun.drivers.base import BgpNeighbor, Driver, DriverError, Observation, Route
from netdryrun.drivers.frr import FrrDriver
from netdryrun.drivers.sonic import SonicDriver
from netdryrun.lab import ExecResult, Node

LIVE_SHOW_VRF = (Path(__file__).parent / "fixtures" / "verify" / "show_vrf.txt").read_text(encoding="utf-8").split("\n", 1)[1]


class OneCommandLab:
    def __init__(self, text):
        self.text = text

    def exec(self, node, cmd, timeout=60, input=None):
        return ExecResult(cmd, 0, self.text, "")


@pytest.mark.parametrize("cls", [FrrDriver, SonicDriver])
def test_frr_lists_its_active_vrfs(cls):
    assert cls(OneCommandLab(LIVE_SHOW_VRF), "edge1").vrfs().value == ["cust"]      # live FRR 10.4.1 output
    text = "vrf red id 5 table 1001 (configured)\nvrf blue inactive (configured)\n"
    assert cls(OneCommandLab(text), "r1").vrfs().value == ["red"]                   # an inactive VRF has no state


class Drv:
    name = "frr"
    reads_received = True

    def bgp_received(self, neighbor, afi="ipv4-unicast", vrf="default"):
        return Observation({"default": {"203.0.113.0/25", "203.0.113.128/25"},
                            "cust": {"10.201.0.0/25", "10.201.0.128/25"}}[vrf], [])

    def __init__(self, vrfs=None):
        self._vrfs = vrfs

    def vrfs(self):
        if self._vrfs is None:
            raise DriverError("listing VRFs is not supported on this platform yet")
        return Observation(list(self._vrfs), [])

    def bgp_neighbors(self, vrf="default"):
        addr = {"default": "10.0.0.2", "cust": "10.10.1.2"}[vrf]
        return Observation({addr: BgpNeighbor(addr, "established", {"ipv4-unicast": 2})}, [])

    def all_routes(self, vrf="default", family=4):
        if family == 6:
            return Observation([], [])
        prefix = {"default": "203.0.113.0/24", "cust": "10.201.0.0/24"}[vrf]
        return Observation([Route(prefix, "bgp", True)], [])

    def routes(self, prefix, vrf="default"):   # what a guard reads: no default route anywhere
        return Observation([], [{"cmd": "show route"}])


def _record(monkeypatch, drv, guards=False):
    class FakeLab:
        links: list = []

        def __init__(self, topology):
            self.nodes = {"edge1": Node("edge1", "clab-t-edge1", "linux", "quay.io/frrouting/frr:10.4.1")}
    monkeypatch.setattr(rec, "Lab", FakeLab)
    monkeypatch.setattr(rec, "detect", lambda node: "frr")
    monkeypatch.setattr(rec, "for_node", lambda lab, name: drv)
    return rec.record(Path("t.clab.yml"), guards=guards, sleep=lambda s: None)


def test_record_covers_every_vrf_the_driver_lists(monkeypatch):
    data, warnings = _record(monkeypatch, Drv(vrfs=["cust"]))
    checks = data["checks"]
    assert {"type": "bgp_session", "node": "edge1", "neighbor": "10.0.0.2"} in checks
    assert {"type": "bgp_session", "node": "edge1", "neighbor": "10.10.1.2", "vrf": "cust"} in checks
    assert {"type": "route", "node": "edge1", "prefix": "10.201.0.0/24", "protocol": "bgp", "vrf": "cust"} in checks
    assert {"type": "route", "node": "edge1", "prefix": "203.0.113.0/24", "protocol": "bgp"} in checks
    assert {"type": "bgp_prefixes", "node": "edge1", "neighbor": "10.10.1.2", "afi": "ipv4-unicast", "vrf": "cust",
            "min": 2, "max": 4, "only": ["10.201.0.0/25", "10.201.0.128/25"]} in checks
    assert not warnings


class NoVrfList(Drv):
    """A driver without its own vrfs(): the base Driver's "not supported" answer (EOS, SR Linux)."""
    vrfs = Driver.vrfs


def test_a_driver_that_cannot_list_vrfs_records_the_default_one_and_says_so(monkeypatch):
    data, warnings = _record(monkeypatch, NoVrfList())
    assert all("vrf" not in c for c in data["checks"]) and data["checks"]
    assert warnings == ["edge1: only the default VRF is recorded (listing VRFs is not supported on frr yet); add "
                        "checks for other VRFs by hand"]
    assert not rec.baseline_gaps(warnings)


def test_a_driver_whose_vrf_list_read_fails_is_an_incomplete_baseline(monkeypatch):
    """A driver that lists VRFs and whose read fails leaves every other VRF unrecorded: a gap line, exit 1
    (FP-042-RECORDVRFLISTFAIL), never the plain warning of a driver that can't list them."""
    data, warnings = _record(monkeypatch, Drv(vrfs=None))
    assert all("vrf" not in c for c in data["checks"]) and data["checks"]
    assert rec.baseline_gaps(warnings) == warnings == [
        "INCOMPLETE BASELINE: edge1: could not list its VRFs (listing VRFs is not supported on this platform yet), "
        "so only the default VRF is recorded and no other VRF has a session, route or guard: fix the read and record "
        "again, or add checks for other VRFs by hand"]


def test_a_vrf_without_bgp_is_skipped_quietly_and_a_node_without_bgp_still_warns(monkeypatch):
    from netdryrun.drivers.base import NoSuchInstance

    class NoBgpIn(Drv):
        def __init__(self, missing):
            super().__init__(vrfs=["cust"])
            self.missing = missing

        def bgp_neighbors(self, vrf="default"):
            if vrf == self.missing:
                raise NoSuchInstance(f"no BGP instance in {vrf}")
            return super().bgp_neighbors(vrf)
    data, warnings = _record(monkeypatch, NoBgpIn("cust"))
    assert not any(c.get("vrf") == "cust" for c in data["checks"]) and not warnings
    data, warnings = _record(monkeypatch, NoBgpIn("default"))
    assert any("could not read BGP state" in w for w in warnings)
    assert any(c.get("vrf") == "cust" for c in data["checks"])


def test_guards_are_recorded_in_every_vrf_with_its_vrf(monkeypatch):
    """0.3.3's guards (no default route via BGP) merged with 0.4's VRFs. Until 0.4.2 a guard was written for the
    default VRF only, so a default leaked into a customer VRF passed the baseline (RT-0076, oracle FP-042-RECORDVRF).
    From 0.4.2 every VRF with a BGP instance gets the guards, sessions or not (FP-042-RECORDVRFNOSESS), with its
    `vrf:`. A VRF whose service is a default route learns it today, and a guard is never written against what a VRF learns today (next test)."""
    data, _ = _record(monkeypatch, Drv(vrfs=["cust"]), guards=True)
    guards = [c for c in data["checks"] if c.get("present") is False]
    assert {"type": "route", "node": "edge1", "prefix": "0.0.0.0/0", "protocol": "bgp", "present": False} in guards
    assert {"type": "route", "node": "edge1", "prefix": "0.0.0.0/0", "protocol": "bgp", "present": False,
            "vrf": "cust"} in guards
    assert any(c.get("vrf") == "cust" for c in data["checks"] if c.get("present") is not False)


def test_a_vrf_that_learns_a_default_today_gets_no_default_guard(monkeypatch):
    class DefaultInCust(Drv):
        def all_routes(self, vrf="default", family=4):
            got = super().all_routes(vrf, family)
            if vrf == "cust" and family == 4:
                return Observation(got.value + [Route("0.0.0.0/0", "bgp", True)], [])
            return got

    data, warnings = _record(monkeypatch, DefaultInCust(vrfs=["cust"]), guards=True)
    guards = [c for c in data["checks"] if c.get("present") is False]
    assert [c.get("vrf", "default") for c in guards if c["prefix"] == "0.0.0.0/0"] == ["default"]
    assert any(w.startswith("edge1 (vrf cust): learns 0.0.0.0/0 via BGP today") for w in warnings)
