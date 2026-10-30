"""Compact agent results (0.4.1): every MCP tool result fits a fixed budget, keeps what decides, and points to
the full evidence.

An agent pays for every token of a result, and a long one pushes the verdict out of its attention. So each
result is compact JSON within mcp_server.RESULT_BUDGET_CHARS. When a run is bigger, parts are cut in a fixed
order, least deciding first; `status`, `verdict`, the counts, `error`, `inconclusive_reason` and
`evidence_file` are never cut, and at least one failure always stays. `truncated` names every cut, with its
count, and `full_result` points to the file that holds everything (fields are only added: the versioning
policy, docs/VERSIONING.md)."""
from __future__ import annotations

import json

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from test_mcp_result_schema import FROZEN, _rep, _res, _validate

from netdryrun import mcp_server
from netdryrun.checks import Unready

BUDGET = mcp_server.RESULT_BUDGET_CHARS
LONG = "x" * 290


def _render(summary: dict) -> tuple[str, dict]:
    text = mcp_server._render(summary, mcp_server.RUN_CUTS)
    return text, json.loads(text)


def _big_run(n_pass=300, n_fail=150, files=200):
    ev = [{"node": "r1", "cmd": "vtysh -c show bgp neighbors json " + "y" * 150, "rc": 0, "output": "z" * 5000, "stderr": ""}]
    results = [_res(True, "state is established " + LONG) for _ in range(n_pass)]
    results += [_res(False, f"failure {i} " + LONG, evidence=ev) for i in range(n_fail)]
    s = mcp_server._summary(_rep(results), "/lab/netdryrun-report.json",
                            tested={"config": "/lab/netdryrun.yml", "lab_deployed_by_this_run": True, "complete": True,
                                    "files": {f"configs/r{i}/frr.conf": "a" * 64 for i in range(files)}})
    return s


def test_budget_is_a_few_thousand_tokens():
    # JSON runs about 3-4 characters per token: the budget is roughly 2,000 to 2,700 tokens
    assert 6000 <= BUDGET <= 10000


def test_small_results_are_complete_and_say_nothing_was_cut():
    s = mcp_server._summary(_rep([_res(True, "state is established"), _res(False)]), "/lab/r.json")
    text, out = _render(s)
    assert out["truncated"] is None
    assert {k: v for k, v in out.items() if k != "truncated"} == json.loads(json.dumps(s))
    assert "\n" not in text   # compact JSON: no indentation spent on whitespace
    _validate(out)


def test_a_huge_run_fits_and_keeps_what_decides():
    s = _big_run()
    text, out = _render(s)
    assert len(text) <= BUDGET
    assert (out["status"], out["verdict"], out["passed"], out["failed"]) == ("failed", FROZEN[1], 300, 150)
    assert out["evidence_file"] == "/lab/netdryrun-report.json"
    assert out["failures"], "at least one failure always stays"
    assert out["failures"][0]["check"] == "r1 check" and out["failures"][0]["reason"].startswith("failure 0 ")
    t = out["truncated"]
    assert t["full_result"] == "/lab/netdryrun-report.json"
    assert len(out["failures"]) + t["omitted"].get("failures", 0) == 150
    assert t["omitted"]["checks"] >= 300   # passing checks go first: their count is in `passed`
    assert len(out["tested"]["files"]) + t["omitted"]["tested.files"] == 200
    _validate(out)


def test_passing_checks_are_cut_before_any_failure():
    s = _big_run(n_pass=400, n_fail=3, files=0)
    _, out = _render(s)
    assert len(out["failures"]) == 3 and "failures" not in out["truncated"]["omitted"]
    # every failed check stays in `checks`; only passing ones were left out
    assert sum(not c["passed"] for c in out["checks"]) == 3
    assert len(out["checks"]) + out["truncated"]["omitted"]["checks"] == 403


def test_inconclusive_and_error_keep_their_reason():
    s = mcp_server._summary(_rep([_res(False, Unready("error: vtysh failed " + LONG)) for _ in range(500)]), None)
    _, out = _render(s)
    assert out["status"] == "inconclusive" and out["verdict"] == FROZEN[2]
    assert out["truncated"]["full_result"] is None   # no evidence file was written: say so, don't invent one
    s = mcp_server._summary(_rep([], "containerlab deploy failed: " + "e" * 5000), None)
    text, out = _render(s)
    assert len(text) <= BUDGET and out["error"].startswith("containerlab deploy failed")


@settings(max_examples=40, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(n_pass=st.integers(0, 600), n_fail=st.integers(0, 300), files=st.integers(0, 200),
       detail=st.text(max_size=400))
def test_every_run_result_fits(n_pass, n_fail, files, detail):
    results = [_res(True, detail) for _ in range(n_pass)] + [_res(False, detail) for _ in range(n_fail)]
    s = mcp_server._summary(_rep(results), "/r.json",
                            tested={"config": "/c", "lab_deployed_by_this_run": True, "complete": True,
                                    "files": {f"f{i}" * 20: "b" * 64 for i in range(files)}})
    text, out = _render(s)
    assert len(text) <= BUDGET
    assert (out["passed"], out["failed"], out["status"]) == (n_pass, n_fail, s["status"])
    if n_fail:
        assert out["failures"]


def _big_verify(n=50, lines=30):
    item = {"kind": "route", "node": "r1", "vrf": "default", "afi": "ipv4", "prefix": "10.0.0.0/24",
            "summary": "s" * 300, "next_diagnostic": "docker exec clab-x-r1 vtysh -c 'show ip route 10.0.0.0/24'"}
    return {"schema": mcp_server.RESULT_SCHEMA, "tool": "verify_change", "verdict": "UNDECLARED CHANGES: DO NOT APPLY",
            "status": "failed", "notice": "n", "intent_source": "mcp",
            "intent": {"source": "mcp", "supplied_by": "mcp", "lines": ["l" * 200] * lines, "allow_anywhere": []},
            "run_id": "r", "failed_because": ["undeclared"], "warnings": [], "error": None, "inconclusive": None,
            "baseline": {"healthy": True, "problems": []}, "diff_items": 400, "undeclared_total": 400,
            "undeclared": [item] * n,
            "not_happened": [{"intent": 0, "line": "l" * 300, "reason": "r" * 300}] * 20,
            "declared": [{"intent": 1, "line": "d" * 300, "items": 5}] * 20, "allowed": [],
            "guards": None, "guards_source": None, "timings": {}, "evidence_file": "/lab/netdryrun-verify-report.json"}


def test_a_huge_verify_result_fits_and_keeps_what_decides():
    text = mcp_server._render(_big_verify(), mcp_server.VERIFY_CUTS)
    out = json.loads(text)
    assert len(text) <= BUDGET
    assert (out["verdict"], out["status"], out["undeclared_total"]) == ("UNDECLARED CHANGES: DO NOT APPLY", "failed", 400)
    assert out["undeclared"] and out["not_happened"], "the reasons it failed stay"
    om = out["truncated"]["omitted"]
    assert om["declared"] >= 1 and len(out["undeclared"]) + om.get("undeclared", 0) == 50
    assert out["truncated"]["full_result"] == "/lab/netdryrun-verify-report.json"


def test_cuts_never_name_a_field_that_decides():
    deciding = {"schema", "status", "verdict", "passed", "failed", "error", "inconclusive_reason", "evidence_file",
                "undeclared_total", "failed_because", "tool"}
    for cuts in (mcp_server.RUN_CUTS, mcp_server.VERIFY_CUTS):
        assert not {c[0] for c in cuts} & deciding


def test_schema_documents_truncated():
    from test_mcp_result_schema import SCHEMA
    assert "truncated" in SCHEMA["$defs"]["run_result"]["properties"]


@pytest.mark.parametrize("cuts", ["RUN_CUTS", "VERIFY_CUTS"])
def test_the_tool_description_says_results_are_bounded(cuts):
    import asyncio
    descriptions = " ".join(t.description for t in asyncio.run(mcp_server.mcp.list_tools()))
    assert "truncated" in descriptions and "evidence_file" in descriptions


def test_the_evidence_file_holds_every_tested_file(tmp_path):
    """What a cut result points to: the full report plus `tested` with every hash."""
    tested = {"config": "/c", "lab_deployed_by_this_run": True, "complete": True,
              "files": {f"f{i}": "c" * 64 for i in range(200)}}
    data = json.loads(mcp_server._evidence_json(_rep([_res(True, "ok")]), tested))
    assert data["schema"] == "netdryrun.report/v1" and data["tested"] == tested
