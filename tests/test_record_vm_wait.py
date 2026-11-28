"""`record --deploy` waits for a VM NOS to answer before recording (0.4.1). Its budget was fixed at mgmt.READY_BUDGET
(300 s) whatever --wait said, so an NX-OS 9000v that boots in 318-341 s (0.4.3 acceptance, 2026-11-27: angle1/nxos/
mustfail, three fresh boots measured) was a lab error even with the README's `--wait 900`. A VM node now gets the
larger of READY_BUDGET and --wait. Tested through `netdryrun record` itself, so these fail on the old code by
behaviour (exit 2), not by a signature."""
from netdryrun import cli, lab as labmod, mgmt, record as recmod
from netdryrun.drivers import frr_import_check as ic
from netdryrun.lab import LabError
from netdryrun.lab import Node


class Booting:
    """A VM NOS driver whose BGP read fails until `ready` seconds of waiting have passed (5 s steps)."""

    def __init__(self, ready, slept):
        self.ready, self.slept = ready, slept

    def bgp_neighbors(self, vrf):
        if sum(self.slept) < self.ready:
            raise LabError("n1: NX-OS is not ready (still booting): vrnetlab health is '1 starting'")
        return []


def _record(monkeypatch, tmp_path, ready, wait):
    monkeypatch.setattr(mgmt, "READY_BUDGET", 300.0)    # the shipped value (conftest zeroes it for unit tests)
    slept: list = []
    events: list = []

    class DeployLab:
        name = "t"
        nodes = {"n1": Node("n1", "clab-t-n1", "cisco_n9kv", "vrnetlab/cisco_n9kv:10.4.8"),
                 "f1": Node("f1", "clab-t-f1", "linux", "quay.io/frrouting/frr:10.4.1")}

        def __init__(self, topology):
            pass

        def deploy(self):
            events.append("deploy")

        def destroy(self):
            events.append("destroy")
    drv = Booting(ready, slept)
    topo = tmp_path / "t.clab.yml"
    topo.write_text("name: t\n")
    monkeypatch.setattr(labmod, "Lab", DeployLab)
    monkeypatch.setattr("netdryrun.drivers.for_node", lambda lab, name, override=None: drv)
    monkeypatch.setattr("time.sleep", slept.append)
    monkeypatch.setattr(ic, "candidates", lambda lab, resolve: {})
    monkeypatch.setattr(ic, "guard", lambda lab, nodes, **kw: {})
    monkeypatch.setattr(recmod, "record", lambda *a, **k: (events.append("record") or (
        {"lab": "t", "timeout": 900, "checks": [{"type": "bgp_session", "node": "f1", "neighbor": "10.0.0.1"}]}, [])))
    out = tmp_path / "netdryrun.yml"
    rc = cli.main(["record", str(topo), "--deploy", "--wait", str(wait), "--out", str(out), "--driver", "n1=nxos"])
    return rc, events, slept, out


def test_a_vm_that_boots_past_300s_is_recorded_with_the_readmes_wait(monkeypatch, tmp_path, capsys):
    rc, events, slept, out = _record(monkeypatch, tmp_path, ready=335, wait=900)
    assert rc == 0 and out.exists() and "record" in events
    assert sum(slept[:-1]) == 335 and slept[-1] == 900     # waited until it answered, then the convergence wait
    assert "Waiting for n1 to answer (up to 900s)" in capsys.readouterr().out


def test_the_default_wait_keeps_the_300s_floor(monkeypatch, tmp_path, capsys):
    rc, events, slept, out = _record(monkeypatch, tmp_path, ready=250, wait=45)
    assert rc == 0 and out.exists()
    assert "up to 300s" in capsys.readouterr().out


def test_a_vm_that_never_answers_in_the_wait_is_still_a_lab_error(monkeypatch, tmp_path, capsys):
    rc, events, slept, out = _record(monkeypatch, tmp_path, ready=10 ** 6, wait=600)
    assert rc == 2 and not out.exists() and "record" not in events and events[-1] == "destroy"
    assert "a budget of 600s, so n1 can't be recorded" in capsys.readouterr().err


class BootingFromFirstRead:
    """A VM NOS driver that answers once `ready` seconds have been slept since its own first read."""

    def __init__(self, ready, slept):
        self.ready, self.slept, self.first = ready, slept, None

    def bgp_neighbors(self, vrf):
        if self.first is None:
            self.first = len(self.slept)
        if sum(self.slept[self.first:]) < self.ready:
            raise LabError("still booting: vrnetlab health is '1 starting'")
        return []


def test_two_vm_nodes_each_get_the_whole_budget_in_turn(monkeypatch, tmp_path, capsys):
    """The budget is per node, from its own first read: two NX-OS nodes that each take 335 s both answer in a 600 s
    wait (670 s in all), where a budget shared by the lab would give the second only 265 s."""
    monkeypatch.setattr(mgmt, "READY_BUDGET", 300.0)
    slept: list = []
    events: list = []
    drivers = {"n1": BootingFromFirstRead(335, slept), "n2": BootingFromFirstRead(335, slept)}

    class DeployLab:
        name = "t"
        nodes = {"n1": Node("n1", "clab-t-n1", "cisco_n9kv", "vrnetlab/cisco_n9kv:10.4.8"),
                 "n2": Node("n2", "clab-t-n2", "cisco_n9kv", "vrnetlab/cisco_n9kv:10.4.8"),
                 "f1": Node("f1", "clab-t-f1", "linux", "quay.io/frrouting/frr:10.4.1")}

        def __init__(self, topology):
            pass

        def deploy(self):
            events.append("deploy")

        def destroy(self):
            events.append("destroy")
    topo = tmp_path / "t.clab.yml"
    topo.write_text("name: t\n")
    monkeypatch.setattr(labmod, "Lab", DeployLab)
    monkeypatch.setattr("netdryrun.drivers.for_node", lambda lab, name, override=None: drivers.get(name))
    monkeypatch.setattr("time.sleep", slept.append)
    monkeypatch.setattr(ic, "candidates", lambda lab, resolve: {})
    monkeypatch.setattr(ic, "guard", lambda lab, nodes, **kw: {})
    monkeypatch.setattr(recmod, "record", lambda *a, **k: (events.append("record") or (
        {"lab": "t", "timeout": 900, "checks": [{"type": "bgp_session", "node": "f1", "neighbor": "10.0.0.1"}]}, [])))
    out = tmp_path / "netdryrun.yml"
    rc = cli.main(["record", str(topo), "--deploy", "--wait", "600", "--out", str(out),
                   "--driver", "n1=nxos", "--driver", "n2=nxos"])
    text = capsys.readouterr().out
    assert rc == 0 and out.exists() and "record" in events
    assert "Waiting for n1 to answer (up to 600s)" in text and "Waiting for n2 to answer (up to 600s)" in text
    assert sum(slept[:-1]) == 670 and slept[-1] == 600
