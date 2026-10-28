"""The scale-test fabric generator (scripts/scale_topology.py) and the release gate's live/scale wiring."""
import importlib.util
import ipaddress
import json
import re
import sys
from pathlib import Path

import pytest
import yaml

from netdryrun import config

ROOT = Path(__file__).resolve().parents[1]


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


topo = load("scale_topology")
gate = load("release_gate")


@pytest.mark.parametrize("leaves", [2, 4, 48, 98])
def test_fabric_shape_and_config_validates(tmp_path, leaves):
    topo.generate(tmp_path, leaves)
    t = yaml.safe_load((tmp_path / "topology.clab.yml").read_text())
    assert t["name"] == f"ndr-scale{leaves}"           # the gate removes only labs named ndr-*
    assert len(t["topology"]["nodes"]) == leaves + 2
    assert len(t["topology"]["links"]) == 2 * leaves
    cfg = config.load(tmp_path / "netdryrun.yml")
    assert len(cfg.checks) == 5 * leaves + 1
    for name in t["topology"]["nodes"]:
        assert (tmp_path / "configs" / f"{name}.conf").exists()


def test_addresses_are_unique_and_peers_match(tmp_path):
    n = 12
    topo.generate(tmp_path, n)
    seen = {}
    for conf in (tmp_path / "configs").glob("*.conf"):
        for ip in re.findall(r"ip address (\S+)", conf.read_text()):
            iface = ipaddress.ip_interface(ip)
            if iface.network.prefixlen == 30:           # lo carries the leaf LAN, checked below
                assert iface.ip not in seen, f"{iface.ip} on {conf.name} and {seen[iface.ip]}"
                seen[iface.ip] = conf.name
    for i in range(1, n + 1):
        leaf = (tmp_path / "configs" / f"leaf{i}.conf").read_text()
        for s in (1, 2):
            spine = (tmp_path / "configs" / f"spine{s}.conf").read_text()
            assert f"neighbor 10.{s}.{i}.1 remote-as {65000 + s - 1}" in leaf
            assert f"neighbor 10.{s}.{i}.2 remote-as {65100 + i}" in spine
        assert f"network 10.200.{i}.0/24" in leaf


def test_exactly_one_leaf_leaks(tmp_path):
    topo.generate(tmp_path, 6, leak=3)
    leaks = [p.name for p in (tmp_path / "configs").glob("*.conf") if "network 0.0.0.0/0" in p.read_text()]
    assert leaks == ["leaf3.conf"]
    topo.generate(tmp_path, 6)
    assert not [p for p in (tmp_path / "configs").glob("*.conf") if "0.0.0.0/0" in p.read_text()]


@pytest.mark.parametrize("n,leak", [(1, None), (251, None), (4, 5), (4, 0)])
def test_bad_sizes_are_rejected(tmp_path, n, leak):
    with pytest.raises(ValueError):
        topo.generate(tmp_path, n, leak)


def test_guards_catch_the_leak():
    """Every leaf has a no-default-route guard and an exact prefix count that a leaked prefix breaks."""
    text = topo.checks(5, 100)
    assert text.count("prefix: 0.0.0.0/0, protocol: bgp, present: false") == 5
    assert text.count("min: 4, max: 4") == 5


def test_gate_runs_scale_script_and_stops_being_manual(monkeypatch, tmp_path):
    src = (ROOT / "scripts" / "release_gate.py").read_text(encoding="utf-8")
    assert "run it by hand" not in src and "live_scale(live, args)" in src

    class Args:
        skip_scale, scale_leaves, strict, version = False, "4", False, "0"
        out = str(tmp_path / "out")

    seen = []

    def fake_run(cmd, **kw):
        seen.append([str(c) for c in cmd])
        out = Path(cmd[cmd.index("--out") + 1])
        out.mkdir(parents=True)
        rec = {"leaves": 4, "nodes": 6, "runs": [
            {"variant": v, "exit": e, "expected_exit": e, "seconds": {"total": 1, "deploy_and_wait": 1, "checks": 1, "destroy": 1},
             "memory_mib": {"per_node_peak": 25}, "result_line": "x", "ok": True, "left_running": 0}
            for v, e in (("pass", 0), ("leak", 1))]}
        (out / "scale-4.json").write_text(json.dumps(rec))
        return gate.Proc(0, "ok", 1.0)

    class Live:
        work = tmp_path
        ndr = "ndr"

        def __init__(self):
            self.layer = gate.Layer("live", Args)
            self.cleaned = []

        def assert_clean(self, id, title):
            self.cleaned.append(id)
    monkeypatch.setattr(gate, "run", fake_run)
    monkeypatch.setattr(gate, "out_dir", lambda args: tmp_path / "gate")
    live = Live()
    gate.live_scale(live, Args)
    [c] = live.layer.checks
    assert (c.id, c.status, c.severity) == ("scale", gate.PASS, gate.BLOCKER)
    assert "--no-lock" in seen[0] and live.cleaned == ["scale-6"]
    Args.skip_scale = True
    live2 = Live()
    gate.live_scale(live2, Args)
    assert live2.layer.checks[0].status == gate.SKIP
