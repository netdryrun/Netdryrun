"""Guards for oracle FP-042-LINKDOWNSTACKED: they pass before and after its fix.

The fast-fix gate needs every test in tests/oracles/FP-042-LINKDOWNSTACKED/ to fail on the fix's parent, so the guards
live here. This file is in the oracle's `evidence:`, so the fix can't change it. The fake-kernel lab (derived iproute2
output, marked in the oracle's docstring), the BGP drivers and the scenario come from the oracle's own module.

What must keep working:
- a plain interface carrying the session address (10.0.100.1/30 on r1 eth1 itself): both ends of the session are
  watched, the run waits until r2's side goes down (its 180 s hold time) and the route check then fails;
- an interface with no stacked device and no BGP session over it (r1 eth2 to a Linux host): the run says no BGP session
  runs over it, and a check the fault doesn't touch passes.
"""
import importlib.util
from pathlib import Path

from netdryrun import runner
from netdryrun.config import Fault, Scenario, _validate_check
from netdryrun.drivers.base import DriverError

_PATH = Path(__file__).resolve().parent / "oracles" / "FP-042-LINKDOWNSTACKED" / "test_oracle_fp_042_linkdownstacked.py"
_SPEC = importlib.util.spec_from_file_location("oracle_fp_042_linkdownstacked", _PATH)
o = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(o)

BOTH_ENDS = [("r1", "default", "10.0.100.2"), ("r2", "default", "10.0.100.1")]


def test_a_plain_interface_with_the_session_address_is_watched_on_both_ends(tmp_path, monkeypatch):
    lab, drivers = o.make_lab(tmp_path, monkeypatch, o.plain_devices)
    watch, every = runner._link_sessions(lab, [("r1", "eth1")], ["default"], lambda n: drivers[n])
    assert sorted(watch) == BOTH_ENDS and sorted(every) == BOTH_ENDS

    lab, drivers = o.make_lab(tmp_path, monkeypatch, o.plain_devices)
    results, logs, err = o.run(lab, drivers, o.scenario())
    assert err is None, err
    assert not any(o.NOTHING_WATCHED in x for x in logs), logs
    assert any("the fault took effect after 180s" in x for x in logs), logs
    assert [r.passed for r in results] == [False], [r.detail for r in results]
    assert lab.devs["r1"]["eth1"].up   # restored


def with_host_link(node, n):
    devs = o.plain_devices(node, n)
    if node == "r1":
        devs.append(o.Dev("eth2", 7, "aa:c1:ab:01:00:02", ["192.168.50.1/24", "fe80::a8c1:abff:fe01:2/64"],
                          peer_index=50))
    return devs


def test_an_interface_with_no_session_and_no_stacked_device_still_says_so(tmp_path, monkeypatch):
    topo = o.TOPOLOGY.replace("    br1: {kind: bridge}\n",
                              "    br1: {kind: bridge}\n    h1: {kind: linux, image: alpine:3.20}\n")
    topo += '    - endpoints: ["r1:eth2", "h1:eth1"]\n'
    monkeypatch.setattr(o, "TOPOLOGY", topo)
    lab, drivers = o.make_lab(tmp_path, monkeypatch, with_host_link)

    def driver_for(n):
        if n not in drivers:
            raise DriverError(f"{n} runs no routing daemon")
        return drivers[n]

    assert runner._link_sessions(lab, [("r1", "eth2")], ["default"], driver_for) == ([], [])
    logs: list[str] = []
    check = _validate_check(0, {"type": "route", "node": "r2", "prefix": "10.1.0.0/24", "protocol": "bgp"}, 60,
                            prefix="scenarios[0].checks")
    sc = Scenario("r1-h1 link fails", [Fault("link_down", "r1", "eth2")], [check])
    results = runner.run_scenario(lab, sc, drivers, settle=10, hold=10, log=logs.append, driver_for=driver_for)
    assert any(o.NOTHING_WATCHED in x for x in logs), logs
    assert [r.passed for r in results] == [True], [r.detail for r in results]
    assert lab.devs["r1"]["eth2"].up and lab.devs["r1"]["eth1"].up
