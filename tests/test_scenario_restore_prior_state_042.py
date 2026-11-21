"""RT-0074 (oracle FP-042-SCENRESTORE): a scenario restores each link to the state it was found in.

run_scenario reads every planned link's admin flag before anything changes. A link already down is left alone by
`node_isolated` (no `down`, no `up` after), a `link_down` on it is refused before anything changes, and an admin flag
that can't be read stops the scenario before anything changes (never read as "down"). These tests kill: restoring every
data interface, skipping the read, reading an unreadable flag as down, and restoring a link twice when two faults name
it. The fake-kernel lab comes from the oracle's module.
"""
import importlib.util
from pathlib import Path

import pytest

from netdryrun.config import Fault
from netdryrun.lab import ExecResult, LabError

_PATH = Path(__file__).resolve().parent / "oracles" / "FP-042-SCENRESTORE" / "test_oracle_fp_042_scenrestore.py"
_SPEC = importlib.util.spec_from_file_location("oracle_fp_042_scenrestore_unit", _PATH)
o = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(o)


def sets(lab):
    return [(n, c) for n, c in lab.commands if c.startswith("ip link set")]


def test_node_isolated_never_touches_a_shut_link(monkeypatch, tmp_path):
    lab = o.make_lab(tmp_path)
    o.run(monkeypatch, lab, o.scenario(Fault("node_isolated", "r1")))
    assert sets(lab) == [("r1", "ip link set dev eth1 down"), ("r1", "ip link set dev eth1 up")]
    assert lab.admin_up("r1", "eth1") and not lab.admin_up("r1", "eth2")


def test_link_down_on_a_shut_link_is_refused_before_anything_changes(monkeypatch, tmp_path):
    lab = o.make_lab(tmp_path)
    with pytest.raises(LabError, match="already administratively down"):
        o.run(monkeypatch, lab, o.scenario(Fault("link_down", "r1", "eth1"), Fault("link_down", "r1", "eth2")))
    assert sets(lab) == []   # the up link r1 eth1 was not taken down either


def test_node_isolated_with_every_link_shut_is_refused(monkeypatch, tmp_path):
    lab = o.make_lab(tmp_path, shut=(("r1", "eth1"), ("r1", "eth2")))
    with pytest.raises(LabError, match="would change nothing"):
        o.run(monkeypatch, lab, o.scenario(Fault("node_isolated", "r1")))
    assert sets(lab) == []


def test_a_link_two_faults_name_is_taken_down_and_restored_once(monkeypatch, tmp_path):
    lab = o.make_lab(tmp_path, shut=())
    o.run(monkeypatch, lab, o.scenario(Fault("link_down", "r1", "eth1"), Fault("node_isolated", "r1")))
    assert sets(lab).count(("r1", "ip link set dev eth1 up")) == 1
    assert sets(lab).count(("r1", "ip link set dev eth1 down")) == 1
    assert all(lab.admin_up(n, i) for n, i in o.ADDRESSES)


def test_an_unreadable_admin_flag_stops_the_scenario_before_anything_changes(monkeypatch, tmp_path):
    lab = o.make_lab(tmp_path, shut=())
    real = lab.exec

    def exec_(node, cmd, timeout=60, input=None):
        if node == "r1" and cmd[:4] == ["ip", "-o", "link", "show"] and cmd[-1] == "eth2":
            lab.commands.append((node, " ".join(cmd)))
            return ExecResult(cmd, 1, "", "Cannot find device")
        return real(node, cmd, timeout, input)

    lab.exec = exec_
    with pytest.raises(LabError, match="could not read the state of eth2"):
        o.run(monkeypatch, lab, o.scenario(Fault("node_isolated", "r1")))
    assert sets(lab) == []
