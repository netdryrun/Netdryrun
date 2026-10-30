"""The 0.3.3 MCP-in-runner spike judges a result on status and the v1 contract, never on its text."""
import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("mcp_in_runner", ROOT / "scripts" / "mcp_in_runner.py")
spike = importlib.util.module_from_spec(spec)
sys.modules["mcp_in_runner"] = spike
spec.loader.exec_module(spike)

TESTED = {"tested": {"files": {"netdryrun.yml": "a" * 64}}}


def test_status_decides_and_the_contract_is_checked():
    assert spike.problems_with({"status": "passed", "failures": [], **TESTED}, "passed", None) == []
    assert spike.problems_with({"status": "failed", "failures": [{"check": "x"}], **TESTED}, "failed", None) == []
    assert spike.problems_with({"status": "failed", "failures": [{"check": "x"}], **TESTED}, "passed", None)
    assert spike.problems_with({"status": "failed", "failures": [], **TESTED}, "failed", None)   # no failures entry
    assert spike.problems_with({"status": "passed", "failures": []}, "passed", None)             # no tested.files


def test_the_server_runs_with_only_path_and_home(monkeypatch):
    monkeypatch.setattr(spike.os, "geteuid", lambda: 1000, raising=False)
    monkeypatch.setenv("PATH", "/opt/py/bin:/usr/bin")
    cmd, args = spike.server_command()
    assert cmd == "sudo" and args == ["env", "-i", "PATH=/opt/py/bin:/usr/bin", "HOME=/root", "netdryrun", "mcp"]
