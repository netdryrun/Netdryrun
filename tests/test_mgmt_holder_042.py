"""mgmt.own_holder (FP-042-SRLNETNS fix): the edges the oracle's own guards don't cover.

containerlab 0.83 runs SR Linux in a namespace holder it makes for the node. The holder's Docker networks become the
node's management networks, so everything refuse_checks did for a node with its own network still holds. Built on the
oracle's captured containers and fake Docker (tests/oracles/FP-042-SRLNETNS/)."""
import importlib.util
from pathlib import Path

from netdryrun import mgmt
from netdryrun.config import _validate_check
from netdryrun.lab import LabError

_PATH = Path(__file__).resolve().parent / "oracles" / "FP-042-SRLNETNS" / "test_oracle_fp_042_srlnetns.py"
_SPEC = importlib.util.spec_from_file_location("oracle_fp_042_srlnetns_edges", _PATH)
o = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(o)


def run(monkeypatch, tmp_path, containers, checks=None):
    lab = o.lab_of(monkeypatch, tmp_path, containers)
    try:
        return mgmt.prepare(lab, o.checks() if checks is None else checks, sleep=lambda s: None), None
    except LabError as e:
        return None, e


def ping(target, source=None):
    raw = {"type": "ping", "node": "srl1", "target": target, **({"source": source} if source else {})}
    return _validate_check(0, raw, 20)


def test_the_holders_networks_are_the_nodes_management_networks(monkeypatch, tmp_path):
    state, error = run(monkeypatch, tmp_path, o.captured())
    assert error is None, error
    m = state["srl1"]
    assert m.holder == "clab-ndr-srl-netns-srl1-netns" and m.mode == "clab"
    assert [str(s) for s in m.subnets] == ["172.20.20.0/24", "3fff:172:20:20::/64"]
    assert m.cid == o.captured()["srl1"]["Id"]              # the node's own id, for a node sharing srl1's namespace
    assert "namespace holder clab-ndr-srl-netns-srl1-netns" in mgmt.describe(m, "nokia_srlinux")


def test_a_ping_over_the_holders_management_network_is_still_refused(monkeypatch, tmp_path):
    for check in (ping("172.20.20.2"), ping("192.168.20.1", source="172.20.20.3")):
        _, error = run(monkeypatch, tmp_path, o.captured(), [check])
        assert error is not None and "management network 172.20.20.0/24" in str(error), error


def test_a_holder_that_doesnt_hold_its_own_namespace_is_refused(monkeypatch, tmp_path):
    for mode in ("host", "none", "container:" + o.captured()["frr1"]["Id"]):
        c = o.captured()
        c["holder"]["HostConfig"]["NetworkMode"] = mode
        _, error = run(monkeypatch, tmp_path, c)
        assert error is not None and "srl1" in str(error), (mode, error)


def test_a_holder_with_only_some_of_the_labels_is_refused(monkeypatch, tmp_path):
    for drop in ("containerlab", "clab-internal-node", "clab-root-node-name"):
        c = o.captured()
        del c["holder"]["Config"]["Labels"][drop]
        _, error = run(monkeypatch, tmp_path, c)
        assert error is not None and "srl1" in str(error), (drop, error)


def test_clab_internal_node_must_be_true(monkeypatch, tmp_path):
    c = o.captured()
    c["holder"]["Config"]["Labels"]["clab-internal-node"] = "false"
    _, error = run(monkeypatch, tmp_path, c)
    assert error is not None and "srl1" in str(error), error


def test_a_lab_without_docker_inspect_container_refuses(monkeypatch, tmp_path):
    lab = o.lab_of(monkeypatch, tmp_path, o.captured())
    m = mgmt.docker_mgmt(lab, "srl1")
    monkeypatch.setattr(type(lab), "docker_inspect_container", None, raising=False)
    assert mgmt.own_holder(lab, "srl1", m) is None
