"""scripts/check_verdict.py, which CI runs on the agent result the Action wrote, agrees with the package."""
import importlib.util
import sys
from pathlib import Path

from netdryrun import agent_result

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("check_verdict", ROOT / "scripts" / "check_verdict.py")
cv = importlib.util.module_from_spec(spec)
sys.modules["check_verdict"] = cv
spec.loader.exec_module(cv)

SHA = "a" * 64


def result(status, failed=0, failures=None, files=None):
    return {"schema": agent_result.RESULT_SCHEMA, "status": status, "failed": failed,
            "failures": failures if failures is not None else [{"check": "x"}] * failed,
            "verdict": agent_result.VERDICTS.get(status, agent_result.DO_NOT_APPLY),
            "tested": {"files": files if files is not None else {"netdryrun.yml": SHA}}}


def test_the_script_uses_the_frozen_verdicts():
    assert cv.VERDICTS == agent_result.VERDICTS and cv.DO_NOT_APPLY == agent_result.DO_NOT_APPLY


def test_a_matching_result_has_no_problems():
    assert cv.problems(result("passed"), "passed") == []
    assert cv.problems(result("failed", 1), "failed") == []


def test_each_mismatch_is_a_problem():
    assert cv.problems(result("failed", 1), "passed")                               # wrong status
    assert cv.problems({**result("failed", 1), "verdict": "CHECKS PASSED (only what the checks cover)"}, "failed")
    assert cv.problems(result("failed", 1, failures=[]), "failed")                  # failures missing
    assert cv.problems(result("passed", files={}), "passed")                        # no tested netdryrun.yml
    assert cv.problems({**result("passed"), "schema": "x"}, "passed")
