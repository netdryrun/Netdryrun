"""Differential test: the CLI, the MCP server and the GitHub Action give the same verdict for the same run.

Each surface has its own code between the runner's RunReport and what the user acts on: the CLI's exit
code and JSON, the MCP tool's status and "verdict" line, the Action's result script (inline Python in
action.yml) and the `if:` of its failing step. A false pass can hide in any of them while the runner is
right. One report per case goes through all of them, and only `passed` may ever read as a pass.

Also: the knobs that change a verdict (`--settle`, `--hold`) have the same defaults on every surface.
"""
from __future__ import annotations

import inspect
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from netdryrun import cli, runner
from netdryrun.checks import Result, Unready
from netdryrun.config import Check, load
from netdryrun.runner import RunReport

ROOT = Path(__file__).resolve().parents[1]
ACTION = yaml.safe_load((ROOT / "action.yml").read_text(encoding="utf-8"))
STEPS = {s.get("id") or s.get("name"): s for s in ACTION["runs"]["steps"]}
EXIT = {"passed": 0, "failed": 1, "error": 2, "inconclusive": 3}
VERDICT = {"passed": "CHECKS PASSED (only what the checks cover)", "failed": "DO NOT APPLY THIS CHANGE",
           "error": "DO NOT APPLY THIS CHANGE",
           "inconclusive": "INCONCLUSIVE: the lab did not reach a testable state; this says nothing about your "
                           "change. Do not apply it until a run passes."}

TOPO = "name: t\ntopology:\n  nodes:\n    r1: {kind: linux, image: quay.io/frrouting/frr:10.4.1}\n"
CONFIG = ("lab: topology.clab.yml\nchecks:\n"
          "  - {type: bgp_session, node: r1, neighbor: 10.0.0.2}\n"
          "  - {type: route, node: r1, prefix: 10.66.0.0/16, present: false}\n")


@pytest.fixture
def lab_dir(tmp_path):
    (tmp_path / "topology.clab.yml").write_text(TOPO)
    (tmp_path / "netdryrun.yml").write_text(CONFIG)
    return tmp_path


def _result(check: Check, passed: bool, unready: bool = False) -> Result:
    detail = Unready("`vtysh` failed") if unready else ("ok" if passed else "state is idle")
    return Result(check, passed, detail, attempts=3, duration=6.0, started="2026-10-28T00:00:00+00:00",
                  samples_passed=3 if passed else 0, samples_unready=3 if unready else 0)


def _report(cfg, case: str) -> RunReport:
    c1, c2 = cfg.checks
    rep = RunReport(config=cfg, lab_name="t", started="2026-10-28T00:00:00+00:00", finished="2026-10-28T00:01:00+00:00")
    if case == "passed":
        rep.results = [_result(c1, True), _result(c2, True)]
    elif case == "one check failed":
        rep.results = [_result(c1, True), _result(c2, False)]
    elif case == "every check failed":
        rep.results = [_result(c1, False), _result(c2, False)]
    elif case == "inconclusive":
        rep.results = [_result(c1, False, unready=True), _result(c2, False, unready=True)]
    elif case == "no checks ran":
        rep.results = []
    elif case == "error after results":
        rep.results = [_result(c1, True), _result(c2, True)]
        rep.error = "could not restore link r1:eth1"
    return rep


CASES = ["passed", "one check failed", "every check failed", "inconclusive", "no checks ran", "error after results"]
EXPECTED = {"passed": "passed", "one check failed": "failed", "every check failed": "failed",
            "inconclusive": "inconclusive", "no checks ran": "failed", "error after results": "error"}


# ------------------------------------------------------------------------------------------- surfaces

def via_cli(lab_dir, rep, monkeypatch) -> tuple[int, str]:
    monkeypatch.setattr(cli, "run", lambda *a, **k: rep)
    monkeypatch.setattr(cli, "install_signal_handlers", lambda: None)
    out = lab_dir / "cli-report.json"
    code = cli.main(["check", str(lab_dir), "--json", str(out), "--no-step-summary"])
    return code, json.loads(out.read_text(encoding="utf-8"))["status"]


def via_mcp(lab_dir, rep, monkeypatch) -> dict:
    mcp_server = pytest.importorskip("netdryrun.mcp_server")
    monkeypatch.setattr(mcp_server, "run", lambda *a, **k: rep)
    return json.loads(mcp_server._execute(str(lab_dir), deploy=False, keep=True))


def action_result_script() -> str:
    run = STEPS["result"]["run"]
    m = re.search(r"<<'EOF'\n(.*?)\n\s*EOF\s*$", run, re.S)
    assert m, "the Action's result step no longer runs an inline Python heredoc: update this test"
    lines = m.group(1).splitlines()
    indent = min(len(x) - len(x.lstrip()) for x in lines if x.strip())
    return "\n".join(x[indent:] for x in lines)


def via_action(tmp_path, report_path: Path | None, exit_code: str) -> dict:
    """Run the Action's own result script, as the composite step does."""
    gh_out = tmp_path / "github_output"
    gh_out.write_text("")
    env = {**os.environ, "NDR_JSON": str(report_path or tmp_path / "missing.json"), "NDR_EXIT": exit_code,
           "GITHUB_OUTPUT": str(gh_out)}
    subprocess.run([sys.executable, "-c", action_result_script()], env=env, check=True, timeout=60)
    return dict(line.split("=", 1) for line in gh_out.read_text().splitlines() if line)


def action_job_fails(outputs: dict[str, dict[str, str]]) -> bool:
    """Evaluate the `if:` of the Action's failing step (the step that turns the job red) on step outputs."""
    expr = STEPS["Fail on failed checks"]["if"]
    py = re.sub(r"steps\.([\w-]+)\.outputs\.([\w-]+)", lambda m: repr(outputs.get(m.group(1), {}).get(m.group(2), "")), expr)
    py = py.replace("||", " or ").replace("&&", " and ").replace("always()", "True").replace("success()", "True")
    assert re.fullmatch(r"[\s'\w.!=()-]*", py), f"unexpected expression in action.yml: {expr}"
    return bool(eval(py, {"__builtins__": {}}, {}))  # noqa: S307 - only literals, comparisons and boolean operators


# ---------------------------------------------------------------------------------------------- tests

@pytest.mark.parametrize("case", CASES)
def test_every_surface_gives_the_same_verdict(case, lab_dir, tmp_path, monkeypatch):
    cfg = load(lab_dir / "netdryrun.yml")
    rep = _report(cfg, case)
    want = EXPECTED[case]
    assert rep.status == want and rep.exit_code == EXIT[want]

    code, cli_status = via_cli(lab_dir, rep, monkeypatch)
    assert (code, cli_status) == (EXIT[want], want)

    mcp = via_mcp(lab_dir, rep, monkeypatch)
    assert mcp["status"] == want
    assert mcp["verdict"] == VERDICT[want]   # the frozen v1 strings; only passed reads as a pass
    assert len(mcp["failures"]) == mcp["failed"] and (want != "passed" or not mcp["failures"])
    assert json.loads((lab_dir / "netdryrun-report.json").read_text())["status"] == want

    action = via_action(tmp_path, lab_dir / "cli-report.json", str(code))
    assert action["status"] == want
    assert action_job_fails({"run": {"exit_code": str(code)}, "result": action}) == (want != "passed")


@pytest.mark.parametrize("report_status,exit_code", [
    ("failed", "0"), ("error", "0"), ("inconclusive", "0"),   # a report that contradicts a clean exit
    (None, "0"),                                              # no report at all
    ("passed", "1"), ("passed", "2"), ("passed", ""),          # a passing report from a run that didn't exit 0
    ("passed", "143"),
])
def test_the_action_never_goes_green_on_a_report_and_exit_code_that_disagree(report_status, exit_code, tmp_path):
    """The Action's status output already cross-checks the report against the exit code. The job result
    must follow it: a contradiction is never a green job (before this test, exit 0 with a failed report
    gave status=error and a passing job)."""
    path = None
    if report_status:
        path = tmp_path / "r.json"
        path.write_text(json.dumps({"status": report_status, "summary": {"passed": 1, "failed": 0}}))
    out = via_action(tmp_path, path, exit_code)
    assert out["status"] == "error"
    assert action_job_fails({"run": {"exit_code": exit_code}, "result": out})


def test_the_action_maps_statuses_like_the_runner():
    script = action_result_script()
    m = re.search(r"EXIT = (\{.*?\})", script)
    assert m, "the Action's result script no longer has its EXIT map"
    assert {k: int(v) for k, v in eval(m.group(1), {"__builtins__": {}}).items()} == EXIT  # noqa: S307 - a dict literal
    for status, code in EXIT.items():
        if status != "error":
            assert RunReport.exit_code.fget(type("R", (), {"status": status})()) == code


# ------------------------------------------------------------------------ defaults that change verdicts

def _run_defaults() -> dict:
    sig = inspect.signature(runner.run)
    return {k: sig.parameters[k].default for k in ("settle", "hold")}


@pytest.mark.parametrize("command", ["run", "check"])
def test_cli_defaults_match_the_runner(command, lab_dir, monkeypatch):
    seen = {}

    def fake_run(cfg, **kw):
        seen.update(kw)
        return _report(cfg, "passed")
    monkeypatch.setattr(cli, "run", fake_run)
    monkeypatch.setattr(cli, "install_signal_handlers", lambda: None)
    assert cli.main([command, str(lab_dir), "--no-step-summary"]) == 0
    assert {k: seen[k] for k in ("settle", "hold")} == _run_defaults()
    assert seen["deploy"] is (command == "run")


def test_mcp_uses_the_runner_defaults(lab_dir, monkeypatch):
    mcp_server = pytest.importorskip("netdryrun.mcp_server")
    seen = {}

    def fake_run(cfg, **kw):
        seen.update(kw)
        return _report(cfg, "passed")
    monkeypatch.setattr(mcp_server, "run", fake_run)
    mcp_server.dry_run(str(lab_dir))
    assert seen["deploy"] is True and seen["keep"] is False
    # settle and hold are not passed, so they are run()'s defaults; if MCP ever passes them, they must match
    assert {k: seen.get(k, v) for k, v in _run_defaults().items()} == _run_defaults()
    mcp_server.run_checks(str(lab_dir))
    assert seen["deploy"] is False


def test_action_defaults_and_flags_match_the_cli():
    inputs = ACTION["inputs"]
    assert {k: float(inputs[k]["default"]) for k in ("settle", "hold")} == _run_defaults()
    cmd = STEPS["run"]["run"]
    # the Action passes them through, and writes the JSON report its result step reads
    for flag, var in (("--settle", "NDR_SETTLE"), ("--hold", "NDR_HOLD"), ("--json", "NDR_JSON")):
        assert re.search(rf'{flag} "\${var}"', cmd), f"the Action's run step no longer passes {flag}"
    assert re.search(r"netdryrun run ", cmd), "the Action runs something other than `netdryrun run`"
    # each mode records the exit code of its own netdryrun command, right after it
    for mode in ("run", "verify"):
        command = re.search(rf"netdryrun {mode} (?:[^\n]*\\\n)*[^\n]*\n\s*code=\$\?\n", cmd)
        assert command, f"{mode} mode no longer records the exit code of its own command, right after it"
    assert 'echo "exit_code=$code"' in cmd
