"""Guards for oracle FP-042-LINKDOWNBRIDGE: they pass before and after its fix.

The fast-fix gate needs every test in tests/oracles/FP-042-LINKDOWNBRIDGE/ to fail on the fix's parent, so the guards
live here. This file is in the oracle's `evidence:`, so the fix can't change it. The fake-kernel lab (derived iproute2
output, marked in the oracle's docstring), the BGP drivers and the scenario come from the oracle's own module.

What must keep working while bridge ports get watched:
- a bond that keeps another member stays up: `link_down` on one of its two members watches nothing, does not wait,
  and the route over the bond passes (the session never drops; watching it would time out with exit 2);
- a VLAN subinterface on the downed interface (FP-042-LINKDOWNSTACKED's shape) is still watched on both ends, the run
  waits for r2's side (its 180 s hold time) and the route check then fails;
- a gre tunnel bound to a downed interface (`gre1@eth1`) that carries no BGP session adds no session to wait for: on
  eth1 only the session on eth1 itself is watched, and on eth2 (no session, `gre2@eth2`) the run says no BGP session
  runs over it and passes the untouched check.

The `bonding_masters` case (acceptance risk 1) can't be a guard: it fails on the current code (every `link_down`
exits 2), so it is the oracle's red test `test_bonding_masters_entry_does_not_break_link_down`.
"""
import importlib.util
from pathlib import Path

from netdryrun import runner
from netdryrun.config import Fault, Scenario, _validate_check

_PATH = Path(__file__).resolve().parent / "oracles" / "FP-042-LINKDOWNBRIDGE" / "test_oracle_fp_042_linkdownbridge.py"
_SPEC = importlib.util.spec_from_file_location("oracle_fp_042_linkdownbridge", _PATH)
o = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(o)


def bond_node(n):
    """r<n>: eth1 and eth2 are members of bond0, which holds 10.0.100.n/24."""
    return o.base(n) + [o.Dev("eth1", 5, o.mac(n, 1), [], master="bond0", peer_index=40 + n),
                        o.Dev("eth2", 6, o.mac(n, 1), [], master="bond0", peer_index=50 + n),
                        o.Dev("bond0", 7, o.mac(n, 1), [f"10.0.100.{n}/24", f"fe80::a8c1:abff:fe0{n}:1/64"],
                              kind="bond")]


def test_a_bond_that_keeps_a_member_stays_up(tmp_path, monkeypatch):
    topo = o.topology("rt0078bond", links=[("r1:eth1", "r2:eth1"), ("r1:eth2", "r2:eth2")])
    devices = {"r1": bond_node(1), "r2": bond_node(2), "r3": o.far_end(3)}
    lab, drivers = o.make_lab(tmp_path, monkeypatch, topo, devices, r1_dev="bond0", r2_dev="bond0",
                              cut=o.cut_when_down("eth1", "eth2"))
    watch, _every = runner._link_sessions(lab, [("r1", "eth1")], ["default"], o.driver_for(drivers))
    assert watch == [], f"bond0 keeps eth2, so its session stays up and must not be waited for: {watch}"

    lab, drivers = o.make_lab(tmp_path, monkeypatch, topo, devices, r1_dev="bond0", r2_dev="bond0",
                              cut=o.cut_when_down("eth1", "eth2"))
    results, logs, err = o.run(lab, drivers, o.scenario())
    assert err is None, f"{err}; log: {logs}"
    assert not any("the fault took effect after" in x for x in logs), logs
    assert lab.clock() < 60, f"the run waited {lab.clock():g}s for a session that never drops; log: {logs}"
    assert [r.passed for r in results] == [True], [r.detail for r in results]
    assert lab.devs["r1"]["eth1"].up   # restored


def vlan_node(n):
    """r<n>: eth1 carrying only its link-local; eth1.100 (VLAN 100 on eth1) with 10.0.100.n/24."""
    return o.base(n) + [o.Dev("eth1", 5, o.mac(n, 1), [f"fe80::a8c1:abff:fe0{n}:1/64"], peer_index=40 + n),
                        o.Dev("eth1.100", 6, o.mac(n, 1), [f"10.0.100.{n}/24", f"fe80::a8c1:abff:fe0{n}:1/64"],
                              kind="vlan", lower="eth1", vlan=100),
                        o.Dev("eth2", 7, o.mac(n, 2), [], peer_index=50 + n)]


def test_a_vlan_subinterface_is_still_watched_on_both_ends(tmp_path, monkeypatch):
    devices = {"r1": vlan_node(1), "r2": vlan_node(2), "r3": o.far_end(3)}
    lab, drivers = o.make_lab(tmp_path, monkeypatch, o.topology("rt0078v"), devices, r1_dev="eth1.100",
                              r2_dev="eth1.100")
    watch, every = runner._link_sessions(lab, [("r1", "eth1")], ["default"], o.driver_for(drivers))
    assert sorted(watch) == o.BOTH_ENDS and sorted(every) == o.BOTH_ENDS, (watch, every)

    lab, drivers = o.make_lab(tmp_path, monkeypatch, o.topology("rt0078v"), devices, r1_dev="eth1.100",
                              r2_dev="eth1.100")
    results, logs, err = o.run(lab, drivers, o.scenario())
    assert err is None, f"{err}; log: {logs}"
    assert not any(o.NOTHING_WATCHED in x for x in logs), logs
    assert any("the fault took effect after 180s" in x for x in logs), logs
    assert [r.passed for r in results] == [False], [r.detail for r in results]
    assert lab.devs["r1"]["eth1"].up


def gre_r1():
    """r1: eth1 carrying 10.0.100.1/24 (the session to r2) with gre1@eth1 (10.9.9.1/30) on it; eth2 carrying
    192.168.50.1/24 to r3 with gre2@eth2 (10.9.8.1/30) on it. No BGP session runs over either tunnel."""
    return o.base(1) + [
        o.Dev("eth1", 5, o.mac(1, 1), ["10.0.100.1/24", "fe80::a8c1:abff:fe01:1/64"], peer_index=41),
        o.Dev("eth2", 6, o.mac(1, 2), ["192.168.50.1/24"], peer_index=51),
        o.Dev("gre1", 8, "", ["10.9.9.1/30"], kind="gre", lower="eth1", tunnel=("10.0.100.1", "10.0.100.2", "eth1")),
        o.Dev("gre2", 9, "", ["10.9.8.1/30"], kind="gre", lower="eth2",
              tunnel=("192.168.50.1", "192.168.50.3", "eth2"))]


def test_a_gre_tunnel_without_a_session_adds_nothing_to_wait_for(tmp_path, monkeypatch):
    devices = {"r1": gre_r1(), "r2": o.far_end(2),
               "r3": o.base(3) + [o.Dev("eth1", 5, o.mac(3, 1), ["192.168.50.3/24"], peer_index=43)]}
    lab, drivers = o.make_lab(tmp_path, monkeypatch, o.topology("rt0078g"), devices, r1_dev="eth1")
    get = o.driver_for(drivers)
    watch, every = runner._link_sessions(lab, [("r1", "eth1")], ["default"], get)
    assert sorted(watch) == o.BOTH_ENDS and sorted(every) == o.BOTH_ENDS, (watch, every)
    assert runner._link_sessions(lab, [("r1", "eth2")], ["default"], get) == ([], [])

    lab, drivers = o.make_lab(tmp_path, monkeypatch, o.topology("rt0078g"), devices, r1_dev="eth1")
    logs: list[str] = []
    check = _validate_check(0, {"type": "route", "node": "r2", "prefix": "10.1.0.0/24", "protocol": "bgp"}, 60,
                            prefix="scenarios[0].checks")
    sc = Scenario("r1-r3 link fails", [Fault("link_down", "r1", "eth2")], [check])
    results = runner.run_scenario(lab, sc, drivers, settle=10, hold=10, log=logs.append,
                                  driver_for=o.driver_for(drivers))
    assert any(o.NOTHING_WATCHED in x for x in logs), logs
    assert [r.passed for r in results] == [True], [r.detail for r in results]
    assert lab.devs["r1"]["eth2"].up and lab.devs["r1"]["eth1"].up
