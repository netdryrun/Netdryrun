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
