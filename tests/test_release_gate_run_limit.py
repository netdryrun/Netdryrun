"""The gate's limit on an example run is longer than the run's own timeout (gate on e741c7e, 2026-11-02): junos-frr
says `timeout: 1800` and the gate killed `netdryrun run` at 1800 s too, so the run never printed which check was still
waiting; the record showed one passed check and "[timed out after 1800 s]". netdryrun times out first and reports."""
from pathlib import Path

from test_release_gate_cleanup import load_gate

ROOT = Path(__file__).resolve().parents[1]


def test_every_example_gets_its_own_timeout_plus_deploy_and_destroy():
    gate = load_gate()
    for cfg in sorted((ROOT / "examples").glob("*/netdryrun.yml")):
        own = gate.run_timeout(cfg.parent)
        assert gate.run_limit(cfg.parent) == own + gate.DEPLOY_AND_DESTROY > own
    assert gate.run_timeout(ROOT / "examples" / "junos-frr") == 1800


def test_the_default_timeout_when_the_config_names_none(tmp_path):
    gate = load_gate()
    (tmp_path / "netdryrun.yml").write_text("lab: topology.clab.yml\nchecks: []\n")
    assert gate.run_timeout(tmp_path) == 120


def test_the_example_run_uses_the_limit(monkeypatch, tmp_path):
    gate = load_gate()
    (tmp_path / "ex").mkdir()
    (tmp_path / "ex" / "netdryrun.yml").write_text("lab: t.yml\ntimeout: 600   # a VM\nchecks: []\n")
    seen = {}
    monkeypatch.setattr(gate, "run", lambda cmd, **kw: seen.setdefault("timeout", kw["timeout"]))
    live = gate.Live.__new__(gate.Live)
    live.work, live.ndr = tmp_path, "netdryrun"
    live.netdryrun_run(tmp_path / "ex")
    assert seen["timeout"] == 600 + gate.DEPLOY_AND_DESTROY
