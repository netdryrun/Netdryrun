"""`record` and a baseline that misses a routing node (acceptance 0.4.1 on d87aa3e, coordinator decision 2026-11-08).

srl1's BGP read failed, `record` dropped it with a warning and exited 0, and a must-fail change on srl1 passed the
recorded baseline; on junos, j1 was still booting at the fixed 45 s wait and nothing on it was recorded. Now a routing
node that is unreadable or ends with no recorded check makes `record` exit 1, `--driver NODE=DRIVER` lets a beta NOS
be recorded, and `record --deploy` waits for VM nodes to answer first."""
from __future__ import annotations

from pathlib import Path

import pytest

from netdryrun import cli, mgmt
from netdryrun import record as rec
from netdryrun.drivers import DriverError, Undetectable
from netdryrun.lab import Node

from test_record import FakeDrv, FakeLab


def _record(monkeypatch, detect, drivers, nodes=None):
    lab = FakeLab(None)
    if nodes is not None:
        lab.nodes = nodes
    monkeypatch.setattr(rec, "Lab", lambda topology: lab)
    monkeypatch.setattr(rec, "detect", detect)
    monkeypatch.setattr(rec, "for_node", lambda lab_, name, *a: drivers[name])
    return rec.record(Path("t.clab.yml"), guards=False)


def test_a_routing_node_whose_bgp_read_fails_is_a_missing_node(monkeypatch):
    class Broken(FakeDrv):
        def bgp_neighbors(self, vrf="default"):
            raise DriverError("2 invalid routes but a count of 1")
    _, warnings = _record(monkeypatch, lambda node: "frr", {"r1": Broken({}), "r2": FakeDrv({"10.0.12.1": {"ipv4-unicast": 1}})})
    assert [w.split(":")[1].strip() for w in warnings if w.startswith(rec.MISSING_NODE)] == ["r1"]


def test_a_host_without_a_driver_is_not_a_missing_node(monkeypatch):
    def detect(node):
        if node.name == "h1":
            raise Undetectable("a plain Linux host")
        return "frr"
    nodes = {"r1": Node("r1", "clab-t-r1", "linux", "frr"), "h1": Node("h1", "clab-t-h1", "linux", "alpine")}
    lab = _ExecLab(nodes, {"h1": False})            # asked: no routing stack in it
    monkeypatch.setattr(rec, "Lab", lambda topology: lab)
    monkeypatch.setattr(rec, "detect", detect)
    monkeypatch.setattr(rec, "for_node", lambda lab_, name, *a: FakeDrv({"10.0.12.2": {"ipv4-unicast": 1}}))
    _, warnings = rec.record(Path("t.clab.yml"), guards=False)
    assert not any(w.startswith(rec.MISSING_NODE) for w in warnings)


def test_a_driver_named_for_a_node_is_used_and_written(monkeypatch):
    seen = []
    lab = FakeLab(None)
    monkeypatch.setattr(rec, "Lab", lambda topology: lab)
    monkeypatch.setattr(rec, "resolve", lambda node, override=None: seen.append((node.name, override)) or override)
    monkeypatch.setattr(rec, "detect", lambda node: pytest.fail("a named driver is resolved, not detected"))
    drv = FakeDrv({"10.0.12.2": {"ipv4-unicast": 1}})
    monkeypatch.setattr(rec, "for_node", lambda lab_, name, *a: drv)
    data, _ = rec.record(Path("t.clab.yml"), guards=False, drivers={"r1": "nxos", "r2": "nxos"})
    assert seen == [("r1", "nxos"), ("r2", "nxos")]
    assert data["nodes"] == {"r1": {"driver": "nxos"}, "r2": {"driver": "nxos"}}


def test_a_driver_for_a_node_not_in_the_topology_is_refused(monkeypatch):
    monkeypatch.setattr(rec, "Lab", lambda topology: FakeLab(None))
    with pytest.raises(ValueError, match="r9"):
        rec.record(Path("t.clab.yml"), drivers={"r9": "nxos"})


def test_the_cli_exits_1_on_a_missing_node_and_still_writes_the_file(tmp_path, monkeypatch, capsys):
    topo = tmp_path / "t.clab.yml"
    topo.write_text("name: t\ntopology:\n  nodes:\n    r1: {kind: linux}\n", encoding="utf-8")

    class L:
        name = "t"

        def __init__(self, path):
            pass
    monkeypatch.setattr("netdryrun.lab.Lab", L)
    monkeypatch.setattr(rec, "record", lambda *a, **k: (
        {"lab": "t.clab.yml", "timeout": 120, "checks": [{"type": "bgp_session", "node": "r2", "neighbor": "10.0.0.1"}]},
        [f"{rec.MISSING_NODE}: r1: no check is recorded on it (...)"]))
    out = tmp_path / "rec.yml"
    assert cli.main(["record", str(topo), "--out", str(out)]) == 1
    assert out.exists() and rec.MISSING_NODE in out.read_text(encoding="utf-8").splitlines()[0]
    assert "has 1 gap(s)" in capsys.readouterr().err


@pytest.mark.parametrize("spec", ["n1", "=nxos", "n1="])
def test_a_driver_option_must_be_node_equals_driver(tmp_path, spec, capsys):
    topo = tmp_path / "t.clab.yml"
    topo.write_text("name: t\ntopology:\n  nodes:\n    r1: {kind: linux}\n", encoding="utf-8")
    assert cli.main(["record", str(topo), "--out", str(tmp_path / "x.yml"), "--driver", spec]) == 2
    assert "write NODE=DRIVER" in capsys.readouterr().err


def test_deploy_waits_for_vm_nodes_only(monkeypatch):
    calls = []
    monkeypatch.setattr(mgmt, "_await_answer", lambda read, node, sleep, budget=None, clock=None, what=None: calls.append(node))

    class Lab:
        nodes = {"j1": Node("j1", "c", "juniper_cjunosevolved", "cj"), "r1": Node("r1", "c", "linux", "frr")}

    class D:
        def bgp_neighbors(self, vrf="default"):
            return None
    monkeypatch.setattr("netdryrun.drivers.for_node", lambda lab, name, override=None: D())
    cli._await_vm_nodes(Lab(), {})
    assert calls == ["j1"]


# ------------------------------------------------------------------------------- code review of the batch

class _ExecLab(FakeLab):
    def __init__(self, nodes, vtysh):
        super().__init__(None)
        self.nodes, self.vtysh = nodes, vtysh

    def exec(self, name, cmd, timeout=60):
        from netdryrun.lab import ExecResult
        if self.vtysh.get(name) is None:
            raise RuntimeError("exec failed")
        return ExecResult(cmd, 0 if self.vtysh[name] else 1, "/usr/bin/vtysh\n" if self.vtysh[name] else "", "")


def _rec_lab(monkeypatch, lab, drivers):
    def detect(node):
        if node.name in drivers:
            return "frr"
        raise Undetectable(f"{node.kind} {node.image}")
    monkeypatch.setattr(rec, "Lab", lambda topology: lab)
    monkeypatch.setattr(rec, "detect", detect)
    monkeypatch.setattr(rec, "for_node", lambda lab_, name, *a: drivers[name])
    return rec.record(Path("t.clab.yml"), guards=False)


def test_a_node_no_driver_recognises_is_missing_unless_it_is_a_host(monkeypatch):
    nodes = {"r1": Node("r1", "c", "linux", "frr"), "x1": Node("x1", "c", "cisco_xrv9k", "xrv"),
             "f1": Node("f1", "c", "linux", "myreg/router:1"), "h1": Node("h1", "c", "linux", "alpine"),
             "b1": Node("b1", "c", "bridge", ""), "q1": Node("q1", "c", "linux", "odd")}
    lab = _ExecLab(nodes, {"f1": True, "h1": False, "q1": None})
    _, warnings = _rec_lab(monkeypatch, lab, {"r1": FakeDrv({"10.0.12.2": {"ipv4-unicast": 1}})})
    missing = sorted(w.split(":")[1].strip() for w in warnings if w.startswith(rec.MISSING_NODE))
    # an XRv, FRR under its own image name, and a container that couldn't be asked (counted, never skipped)
    assert missing == ["f1", "q1", "x1"]
    assert not any(" h1" in w or " b1" in w for w in warnings)


def test_baseline_gaps_are_every_read_gap_but_not_the_size_caps():
    ws = [f"{rec.MISSING_NODE}: r1: ...", "INCOMPLETE BASELINE: r2: could not read IPv4 routes (x)",
          rec._routes_cap("r2", 900, 4), rec._links_cap("r3", 300), "r4: only the default VRF",
          # a gap line that only looks like a cap (a shortened text, or device words) is a gap (FP-042-CAPMSG)
          "INCOMPLETE BASELINE: r2 has 900 BGP routes (IPv4); only the first 50 are recorded",
          "INCOMPLETE BASELINE: r5: could not read BGP state (% only the first 3 words were read)"]
    assert rec.baseline_gaps(ws) == ws[:2] + ws[-2:]


def test_no_bgp_instance_is_a_missing_node_unless_named(monkeypatch):
    """A NOS answers "no BGP instance" while its BGP is still starting (FRR before bgpd loads, cEOS "BGP inactive",
    SONiC before setup): a missing node, unless the user says the node runs no BGP (code review of the batch, M1)."""
    from netdryrun.drivers.base import NoSuchInstance

    class NoBgp(FakeDrv):
        def bgp_neighbors(self, vrf="default"):
            raise NoSuchInstance("no BGP instance")
    drivers = {"r1": NoBgp({}), "r2": FakeDrv({"10.0.12.1": {"ipv4-unicast": 1}})}
    _, warnings = _record(monkeypatch, lambda node: "frr", drivers)
    assert [w.split(":")[1].strip() for w in warnings if w.startswith(rec.MISSING_NODE)] == ["r1"]
    lab = FakeLab(None)
    monkeypatch.setattr(rec, "Lab", lambda topology: lab)
    _, warnings = rec.record(Path("t.clab.yml"), guards=False, no_bgp_ok=frozenset({"r1"}))
    assert not any(w.startswith(rec.MISSING_NODE) for w in warnings)


def test_the_vm_wait_takes_no_bgp_instance_as_an_answer(monkeypatch):
    from netdryrun.drivers.base import NoSuchInstance
    monkeypatch.setattr(mgmt, "READY_BUDGET", 300.0)

    class Lab:
        nodes = {"j1": Node("j1", "c", "juniper_cjunosevolved", "cj"), "v1": Node("v1", "c", "vr-sros", "x")}

    class D:
        def bgp_neighbors(self, vrf="default"):
            raise NoSuchInstance("no BGP")
    monkeypatch.setattr("netdryrun.drivers.for_node", lambda lab, name, override=None: D())
    monkeypatch.setattr("time.sleep", lambda s: pytest.fail("must not wait"))
    cli._await_vm_nodes(Lab(), {})


@pytest.mark.parametrize("args,msg", [(["--driver", "n1=nxso"], "unknown driver"),
                                      (["--driver", "n1=nxos", "--driver", "n1=frr"], "twice")])
def test_driver_option_names_are_checked(tmp_path, args, msg, capsys):
    topo = tmp_path / "t.clab.yml"
    topo.write_text("name: t\ntopology:\n  nodes:\n    n1: {kind: linux}\n", encoding="utf-8")
    assert cli.main(["record", str(topo), "--out", str(tmp_path / "x.yml"), *args]) == 2
    assert msg in capsys.readouterr().err


def test_attributes_say_when_the_best_path_is_the_nodes_own_route():
    from netdryrun.drivers.base import BgpPath, Observation

    class D:
        unsupported_bgp_attributes = frozenset()

        def bgp_paths(self, prefix, vrf="default"):
            return Observation([BgpPath(best=True, as_path="", next_hop="0.0.0.0", local_pref=None, med=None,
                                        local_candidate=True, local_origin="static")], [])
    w: list = []
    assert rec._attribute_check(D(), "s1", "10.9.0.0/24", warnings=w) is None
    assert w and "the node's own route" in w[0]


def test_record_attributes_do_not_pin_communities_on_an_aliasing_node():
    from netdryrun.drivers.base import BgpPath, Observation

    class D:
        unsupported_bgp_attributes = frozenset()

        def bgp_paths(self, prefix, vrf="default"):
            return Observation([BgpPath(best=True, as_path="65020", next_hop="10.0.0.2", local_pref=100, med=None,
                                        communities=["65020:100"])], [])

        def community_aliases(self):
            return Observation({"65020:100"}, [])
    w: list = []
    c = rec._attribute_check(D(), "r1", "10.20.0.0/24", warnings=w)
    assert "communities" not in c and "without_communities" not in c and "bgp community alias" in w[0]
