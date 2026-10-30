"""Warm-lab re-verify, 0.4.1 spike (RELEASES.md, agent-speed track): keep the booted lab, apply only the config
diff, reconverge, recheck. Design: docs/WARM-REVERIFY.md. These tests pin the two pure parts before any lab
work:

1. The planner: which diffs can be applied to a running lab, how, and which force a cold boot. Anything it
   can't prove equivalent is cold, with the reason named. Never "warm and hope".
2. The ship gate: on the corpus, a warm run and a cold run of every case must give the same verdict for every
   strategy and fail the same checks. One mismatch keeps warm off.
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from netdryrun import warm

FRR = "quay.io/frrouting/frr:10.4.1"
BINDS = ["configs/daemons:/etc/frr/daemons", "configs/vtysh.conf:/etc/frr/vtysh.conf"]


def _tree(tmp_path: Path, name: str, files: dict[str, str], nodes: dict | None = None) -> Path:
    root = tmp_path / name
    nodes = nodes if nodes is not None else {
        n: {"binds": [*BINDS, f"configs/{n}.conf:/etc/frr/frr.conf"]} for n in ("r1", "r2")}
    topo = {"name": "t", "topology": {"defaults": {"kind": "linux", "image": FRR}, "nodes": nodes,
                                      "links": [{"endpoints": ["r1:eth1", "r2:eth1"]}]}}
    files = {"topology.clab.yml": yaml.safe_dump(topo), "configs/daemons": "bgpd=yes\n",
             "configs/vtysh.conf": "service integrated-vtysh-config\n", "configs/r1.conf": "router bgp 1\n",
             "configs/r2.conf": "router bgp 2\n", **files}
    for rel, text in files.items():
        if text is None:
            continue
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
    return root


def plan(tmp_path, after_files: dict, before_files: dict | None = None, **kw):
    before = _tree(tmp_path, "before", before_files or {}, kw.get("before_nodes"))
    after = _tree(tmp_path, "after", after_files, kw.get("after_nodes"))
    return warm.plan(before, after, "topology.clab.yml")


def test_no_difference_is_warm_with_nothing_to_apply(tmp_path):
    p = plan(tmp_path, {})
    assert p.cold_reason is None and p.steps == []


def test_an_frr_config_edit_is_a_reload_then_a_soft_clear_then_a_proof(tmp_path):
    p = plan(tmp_path, {"configs/r2.conf": "router bgp 2\n neighbor 10.0.0.1 route-map IN in\n"})
    assert p.cold_reason is None
    assert [(s.node, s.action) for s in p.steps] == [("r2", "reload"), ("r2", "soft-clear"), ("r2", "prove")]
    reload, clear, prove = p.steps
    assert reload.command == ["/usr/lib/frr/frr-reload.py", "--reload", "/etc/frr/frr.conf"]
    # a changed inbound policy applies only to updates received after it, unless BGP re-reads them
    assert clear.command == ["vtysh", "-c", "clear bgp * soft"]
    # applied means nothing left to apply: frr-reload's own test mode prints no change
    assert prove.command == ["/usr/lib/frr/frr-reload.py", "--test", "/etc/frr/frr.conf"]


def test_only_changed_nodes_are_touched(tmp_path):
    p = plan(tmp_path, {"configs/r1.conf": "router bgp 1\n bgp router-id 1.1.1.1\n"})
    assert {s.node for s in p.steps} == {"r1"}


@pytest.mark.parametrize("files,reason", [
    ({"configs/daemons": "bgpd=yes\nospfd=yes\n"}, "daemons"),          # a daemon starts or stops
    ({"configs/vtysh.conf": "hostname x\n"}, "vtysh.conf"),
    ({"topology.clab.yml": "name: t\ntopology: {nodes: {r1: {kind: linux, image: x}}}\n"}, "topology"),
])
def test_what_a_reload_cannot_do_is_cold(tmp_path, files, reason):
    p = plan(tmp_path, files)
    assert p.cold_reason and reason in p.cold_reason and p.steps == []


def test_a_node_that_is_not_frr_is_cold(tmp_path):
    nodes = {"r1": {"kind": "nokia_srlinux", "image": "ghcr.io/nokia/srlinux:26.7.2", "startup-config": "configs/r1.conf"},
             "r2": {"binds": [*BINDS, "configs/r2.conf:/etc/frr/frr.conf"]}}
    p = plan(tmp_path, {"configs/r1.conf": "set / system name host-name x\n"}, before_nodes=nodes, after_nodes=nodes)
    assert p.cold_reason and "r1" in p.cold_reason and "no warm path" in p.cold_reason


def test_a_bound_file_other_than_frr_conf_is_cold(tmp_path):
    nodes = {n: {"binds": [*BINDS, f"configs/{n}.conf:/etc/frr/frr.conf", "configs/extra.sh:/run.sh"]} for n in ("r1", "r2")}
    p = plan(tmp_path, {"configs/extra.sh": "echo 2\n"}, before_files={"configs/extra.sh": "echo 1\n"},
             before_nodes=nodes, after_nodes=nodes)
    assert p.cold_reason and "configs/extra.sh" in p.cold_reason


def test_a_changed_file_no_node_uses_changes_nothing(tmp_path):
    p = plan(tmp_path, {"configs/README.md": "notes\n"})
    assert p.cold_reason is None and p.steps == [] and p.ignored == ["configs/README.md"]


def test_a_file_added_or_removed_under_a_bind_is_cold(tmp_path):
    p = plan(tmp_path, {"configs/r2.conf": None}, before_files={})
    assert p.cold_reason and "configs/r2.conf" in p.cold_reason


# ------------------------------------------------------------------------------------------- the ship gate

def _case(verdicts: dict[str, tuple[str, list[str]]]) -> dict:
    return {"strategies": {s: {"verdict": v, "failed_checks": f, "error": None} for s, (v, f) in verdicts.items()}}


def test_identical_runs_pass_the_gate():
    cold = {"cases": [{"id": "01", **_case({"netdryrun": ("safe", []), "ping": ("safe", [])})}]}
    assert warm.equivalence(cold, cold) == []


@pytest.mark.parametrize("warm_case,why", [
    (_case({"netdryrun": ("safe", []), "ping": ("safe", [])}), "verdict"),
    (_case({"netdryrun": ("harmful", ["leak guard", "other"]), "ping": ("safe", [])}), "failed checks"),
])
def test_any_difference_fails_the_gate(warm_case, why):
    cold = {"cases": [{"id": "07", **_case({"netdryrun": ("harmful", ["leak guard"]), "ping": ("safe", [])})}]}
    mismatches = warm.equivalence(cold, {"cases": [{"id": "07", **warm_case}]})
    assert len(mismatches) == 1 and "07" in mismatches[0] and why in mismatches[0]


def test_a_case_missing_from_either_run_fails_the_gate():
    cold = {"cases": [{"id": "01", **_case({"netdryrun": ("safe", [])})}, {"id": "02", **_case({"netdryrun": ("safe", [])})}]}
    warm_run = {"cases": [{"id": "01", **_case({"netdryrun": ("safe", [])})}]}
    assert any("02" in m and "missing" in m for m in warm.equivalence(cold, warm_run))
    assert warm.equivalence({"cases": []}, {"cases": []}) == ["no cases: an empty comparison proves nothing"]


def test_an_error_on_either_side_fails_the_gate():
    ok = _case({"netdryrun": ("safe", [])})
    bad = {"strategies": {"netdryrun": {"verdict": "safe", "failed_checks": [], "error": "deploy failed"}}}
    assert warm.equivalence({"cases": [{"id": "03", **ok}]}, {"cases": [{"id": "03", **bad}]})[0].startswith("03 netdryrun: error")
