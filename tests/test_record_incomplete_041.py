"""Every part of the network `record` couldn't read is an INCOMPLETE BASELINE (rule 2), not a plain warning (Layer 6
on b03cb7a: an SR Linux node whose BGP read failed lost all its sessions with "could not read BGP state; skipped")."""
import pytest
from test_record import FakeDrv, run_record

from netdryrun import record as rec
from netdryrun.drivers import DriverError


class Broken(FakeDrv):
    def __init__(self, what, *a, **k):
        super().__init__(*a, **k)
        self.what = what

    def bgp_neighbors(self, vrf="default"):
        if self.what == "bgp":
            raise DriverError("unexpected output from `show bgp`")
        return super().bgp_neighbors(vrf)

    def all_routes(self, vrf="default", family=4):
        if self.what == "routes":
            raise DriverError("unexpected output from `show route`")
        return super().all_routes(vrf, family)

    def bgp_paths(self, prefix, vrf="default"):
        raise DriverError("unexpected output from `show bgp paths`")


def incomplete(warnings, node="r1"):
    return [w for w in warnings if w.startswith(f"INCOMPLETE BASELINE: {node}")]


@pytest.mark.parametrize("what,kw,text", [
    ("bgp", {}, "INCOMPLETE BASELINE: r1: could not read BGP state (unexpected output from `show bgp`), so no "
                "session, prefix count or BGP route of r1 is recorded: fix the read and record again, or add checks "
                "by hand"),
    ("routes", {"include_routes": True}, "INCOMPLETE BASELINE: r1: could not read IPv4 routes (unexpected output from "
                                         "`show route`), so none is recorded as a check: fix the read and record "
                                         "again, or add checks by hand"),
])
def test_a_read_that_failed_is_an_incomplete_baseline(monkeypatch, what, kw, text):
    drivers = {"r1": Broken(what, {"10.0.12.2": {"ipv4-unicast": 1}}, routes4=["192.168.2.0/24"]), "r2": FakeDrv({})}
    _, warnings = run_record(monkeypatch, drivers, **kw)
    assert text in incomplete(warnings)


def test_attributes_that_could_not_be_read_are_an_incomplete_baseline(monkeypatch):
    drivers = {"r1": Broken("attrs", {"10.0.12.2": {"ipv4-unicast": 1}}, routes4=["192.168.2.0/24"]),
               "r2": FakeDrv({})}
    _, warnings = run_record(monkeypatch, drivers, include_routes=True, attributes=True)
    assert [w for w in incomplete(warnings) if "BGP attributes of 192.168.2.0/24" in w] == [
        "INCOMPLETE BASELINE: r1: could not read BGP attributes of 192.168.2.0/24 (unexpected output from `show bgp "
        "paths`), so they are not recorded: fix the read and record again, or add a bgp_route check by hand"]


def test_a_node_without_a_driver_is_an_incomplete_baseline(monkeypatch):
    drivers = {"r1": FakeDrv({}), "r2": FakeDrv({})}

    def detect(node):
        if node.name == "r1":
            raise DriverError("no driver")
        return "frr"

    from test_record import FakeLab
    lab = FakeLab(None)
    monkeypatch.setattr(rec, "Lab", lambda topology: lab)
    monkeypatch.setattr(rec, "detect", detect)
    monkeypatch.setattr(rec, "for_node", lambda lab_, name: drivers[name])
    from pathlib import Path
    _, warnings = rec.record(Path("t.clab.yml"))
    assert any(w.startswith("INCOMPLETE BASELINE: r1: no driver for kind=") and w.endswith(
        "nothing on it is recorded: add checks by hand") for w in warnings)
