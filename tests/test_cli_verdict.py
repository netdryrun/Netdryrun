"""0.3.3 (a): `--verdict FILE` writes the result an agent reads (netdryrun.mcp-result/v1), the same shape the
MCP tools return, so an agent that only sees CI artifacts reads one format. And the PR comment starts with a
fixed, machine-readable header."""
import json
import re
from pathlib import Path

import pytest

from netdryrun import agent_result, cli
from netdryrun.checks import Result
from netdryrun.runner import RunReport

jsonschema = pytest.importorskip("jsonschema")
SCHEMA = json.loads((Path(__file__).resolve().parents[1] / "website/docs/schemas/mcp-result-v1.json")
                    .read_text(encoding="utf-8"))


def _validate(data):
    jsonschema.Draft202012Validator(SCHEMA).validate(data)


@pytest.fixture
def lab(tmp_path):
    (tmp_path / "topology.clab.yml").write_text("name: t\ntopology:\n  nodes:\n    r1: {kind: linux, image: frr}\n")
    (tmp_path / "netdryrun.yml").write_text("lab: topology.clab.yml\nchecks:\n  - {type: route, node: r1, prefix: 10.0.0.0/24}\n")
    return tmp_path


def _fake_run(passed):
    def run(cfg, deploy, keep, **_):
        c = cfg.checks[0]
        return RunReport(config=cfg, results=[Result(c, passed, "ok" if passed else "seen: nothing", 2, 1.0, "t")])
    return run


@pytest.mark.parametrize("passed,status,code", [(True, "passed", 0), (False, "failed", 1)])
def test_run_writes_the_agent_result(lab, monkeypatch, passed, status, code):
    monkeypatch.setattr(cli, "run", _fake_run(passed))
    monkeypatch.setattr(cli, "install_signal_handlers", lambda: None)
    v, j = lab / "verdict.json", lab / "report.json"
    assert cli.main(["run", str(lab), "--verdict", str(v), "--json", str(j)]) == code
    out = json.loads(v.read_text())
    _validate(out)
    assert out["status"] == status and out["verdict"] == agent_result.VERDICTS.get(status, agent_result.DO_NOT_APPLY)
    assert out["evidence_file"] == str(j) and out["tested"]["lab_deployed_by_this_run"] is True
    assert "netdryrun.yml" in out["tested"]["files"] and bool(out["failures"]) == (not passed)


def test_check_on_a_running_lab_says_it_did_not_deploy(lab, monkeypatch):
    monkeypatch.setattr(cli, "run", _fake_run(True))
    monkeypatch.setattr(cli, "install_signal_handlers", lambda: None)
    v = lab / "verdict.json"
    cli.main(["check", str(lab), "--verdict", str(v)])
    assert json.loads(v.read_text())["tested"]["lab_deployed_by_this_run"] is False


def test_a_config_error_writes_the_setup_error(tmp_path, monkeypatch):
    monkeypatch.setattr(cli, "run", lambda *a, **k: pytest.fail("no run"))
    v = tmp_path / "verdict.json"
    assert cli.main(["run", str(tmp_path / "missing"), "--verdict", str(v)]) == 2
    out = json.loads(v.read_text())
    _validate(out)
    assert out["status"] == "error" and out["verdict"] == agent_result.DO_NOT_APPLY and out["error"]


def test_an_interrupted_run_writes_no_verdict_but_error(lab, monkeypatch):
    def interrupted(cfg, **_):
        e = KeyboardInterrupt()
        e.report = RunReport(config=cfg, error="interrupted by SIGTERM: no verdict")
        raise e
    monkeypatch.setattr(cli, "run", interrupted)
    monkeypatch.setattr(cli, "install_signal_handlers", lambda: None)
    v = lab / "verdict.json"
    cli.main(["run", str(lab), "--verdict", str(v)])
    out = json.loads(v.read_text())
    assert out["status"] == "error" and out["verdict"] == agent_result.DO_NOT_APPLY


# ---------------------------------------------------------------------------------------- the PR comment

HEADER = re.compile(r"^<!-- netdryrun-verdict: (\{.*\}) -->\n\*\*Netdryrun: (.+)\*\* · status `([a-z]+)` · "
                    r"(\d+) passed, (\d+) failed\n")


@pytest.mark.parametrize("status", ["passed", "failed", "inconclusive", "error"])
def test_the_comment_header_is_fixed_and_machine_readable(status):
    result = {"schema": agent_result.RESULT_SCHEMA, "status": status, "passed": 3, "failed": 1 if status != "passed" else 0,
              "verdict": agent_result.VERDICTS.get(status, agent_result.DO_NOT_APPLY)}
    h = agent_result.pr_comment_header(result)
    m = HEADER.match(h)
    assert m, h
    data = json.loads(m.group(1))
    assert data == {"schema": agent_result.RESULT_SCHEMA, "status": status, "verdict": result["verdict"],
                    "passed": result["passed"], "failed": result["failed"]}
    assert m.group(2) == result["verdict"] and m.group(3) == status


def test_the_comment_header_never_carries_lab_text_or_a_pass_it_did_not_get():
    # anything outside the known statuses, or a missing result, reads as error and DO NOT APPLY
    for bad in ({}, {"status": "passed --> <script>", "verdict": "x", "passed": "9", "failed": None},
                {"status": "passed", "verdict": "CHECKS PASSED (only what the checks cover)", "passed": 1, "failed": 2}):
        h = agent_result.pr_comment_header(bad)
        m = HEADER.match(h)
        assert m and "-->" not in m.group(1) and "<" not in h.split("\n")[1]
        data = json.loads(m.group(1))
        assert data["status"] == "error" and data["verdict"] == agent_result.DO_NOT_APPLY


def test_a_file_edited_during_the_run_makes_the_agent_result_an_error(lab, monkeypatch):
    def run(cfg, deploy, keep, **_):
        (lab / "netdryrun.yml").write_text((lab / "netdryrun.yml").read_text() + "# edited\n")
        return _fake_run(True)(cfg, deploy, keep)
    monkeypatch.setattr(cli, "run", run)
    monkeypatch.setattr(cli, "install_signal_handlers", lambda: None)
    v = lab / "verdict.json"
    cli.main(["run", str(lab), "--verdict", str(v)])
    out = json.loads(v.read_text())
    _validate(out)
    assert out["status"] == "error" and out["verdict"] == agent_result.DO_NOT_APPLY
    assert out["tested"]["changed_during_run"] == ["netdryrun.yml"]


def test_check_does_not_compare_files_a_running_lab_never_loaded(lab, monkeypatch):
    def run(cfg, deploy, keep, **_):
        (lab / "netdryrun.yml").write_text((lab / "netdryrun.yml").read_text() + "# edited\n")
        return _fake_run(True)(cfg, deploy, keep)
    monkeypatch.setattr(cli, "run", run)
    monkeypatch.setattr(cli, "install_signal_handlers", lambda: None)
    v = lab / "verdict.json"
    cli.main(["check", str(lab), "--verdict", str(v)])
    assert json.loads(v.read_text())["status"] == "passed"   # lab_deployed_by_this_run: false already says it


@pytest.mark.parametrize("topology", [
    "name: t\ntopology:\n  kinds: [1, 2]\n  nodes:\n    r1: {kind: linux, image: frr}\n",
    "name: t\ntopology:\n  groups: [x]\n  nodes:\n    r1: {kind: linux, image: frr, binds: 'configs/r1.conf:/x'}\n",
])
def test_a_malformed_topology_never_crashes_the_agent_result(tmp_path, topology):
    # 0.3.3 cold review 7: --verdict read the topology with no guard and crashed before any report was written
    from netdryrun.runner import load_config
    (tmp_path / "topology.clab.yml").write_text(topology)
    (tmp_path / "netdryrun.yml").write_text("lab: topology.clab.yml\nchecks:\n  - {type: route, node: r1, prefix: 10.0.0.0/24}\n")
    t = agent_result._tested(load_config(tmp_path), deployed=True)
    assert t["complete"] is False and "netdryrun.yml" in t["files"]
