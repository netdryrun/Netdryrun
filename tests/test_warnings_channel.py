"""Convergence warnings reach every output channel (0.4.1 red-team fixes, design round 3 "W").

A warning never changes a verdict, but a reader must see it: on the console line, in the summary line, in the JSON
report (per check and counted at the top), in the Markdown summary the Action posts, and in the MCP result (per check,
never cut with the 300-character detail, and counted at the top, so an agent that reads only `status` still sees it).
"""
import json
from pathlib import Path

import jsonschema

from netdryrun import agent_result, report
from netdryrun.checks import Result
from netdryrun.config import Check, Config
from netdryrun.runner import RunReport, _with_warnings, warn

ROOT = Path(__file__).resolve().parents[1]
TEXT = "convergence: r2's session to 10.0.23.2 was not established when this check ran"


def _report():
    c = Check("route", {"node": "r1", "prefix": "203.0.113.0/24", "present": False}, "r1: no leak", 90)
    r = Result(c, True, "absent (held 10s, 5 samples) " + "x" * 400, 5, 10.2, "t", [], [], samples_passed=5)
    warnings = {}
    warn(warnings, c, "gate-session-down", "r2", TEXT, session="10.0.23.2")
    _with_warnings(warnings)(r)
    rep = RunReport(config=Config(Path("netdryrun.yml"), Path("topology.clab.yml"), 90, []), lab_name="t",
                    started="2026-11-06T00:00:00+00:00", results=[r],
                    environment={"netdryrun": "0.4.1", "containerlab": "0.81.1",
                                 "nodes": {"r1": {"kind": "linux", "image": "quay.io/frrouting/frr:10.4.1"}}})
    return rep, r


def test_the_gate_puts_a_structured_warning_on_the_result_not_in_the_detail():
    _, r = _report()
    assert r.warnings == [{"code": "gate-session-down", "node": "r2", "session": "10.0.23.2", "text": TEXT}]
    assert "warning" not in r.detail and r.passed


def test_the_console_and_summary_lines_show_it():
    rep, r = _report()
    assert TEXT in report.console_line(r)
    assert "1 with a convergence warning" in report.summary_line(rep)


def test_the_json_report_carries_it_per_check_and_at_the_top():
    rep, _ = _report()
    data = json.loads(report.to_json(rep))
    assert data["checks"][0]["warnings"][0]["text"] == TEXT
    assert data["warnings"]["count"] == 1 and data["warnings"]["items"][0]["check"] == "r1: no leak"
    schema = json.loads((ROOT / "website" / "docs" / "schemas" / "report-v1.json").read_text(encoding="utf-8"))
    jsonschema.Draft202012Validator(schema).validate(data)


def test_the_markdown_summary_the_action_posts_shows_it():
    rep, _ = _report()
    md = report.to_markdown(rep)
    assert "convergence warning" in md and "10.0.23.2" in md


def test_the_mcp_result_carries_it_in_full_and_counts_it_at_the_top():
    rep, _ = _report()
    res = agent_result._summary(rep, None, tested={"files": {}, "lab_deployed_by_this_run": True})
    assert res["status"] == "passed"                              # the verdict stands
    assert res["warnings"]["count"] == 1
    check = res["checks"][0]
    assert len(check["detail"]) <= 303 and check["warnings"][0]["text"] == TEXT   # not cut with the detail
