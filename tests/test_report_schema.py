"""The published JSON Schema for the report (website/docs/schemas/report-v1.json) matches what Netdryrun writes."""
import json
from pathlib import Path

import pytest

from netdryrun import report
from netdryrun.checks import Result, Unready, _sample
from netdryrun.config import Check, Config
from netdryrun.runner import RunReport, run

jsonschema = pytest.importorskip("jsonschema")

ROOT = Path(__file__).parents[1]
SCHEMA = json.loads((ROOT / "website/docs/schemas/report-v1.json").read_text(encoding="utf-8"))
REAL = sorted((Path(__file__).parent / "fixtures").glob("report-real-*.json"))


def _validate(data: dict) -> None:
    jsonschema.Draft202012Validator(SCHEMA).validate(data)


def _report(results=(), error="") -> RunReport:
    return RunReport(config=Config(Path("netdryrun.yml"), Path("topology.clab.yml"), 90, []), lab_name="t",
                     started="2026-10-27T12:00:00+00:00", finished="2026-10-27T12:01:00+00:00",
                     environment={"netdryrun": "0.3.0", "containerlab": "0.71.1", "python": "3.10.12",
                                  "host": "Linux", "nodes": {"r1": {"kind": "linux", "image": "frr"}}},
                     results=list(results), error=error)


def _result(ok: bool, detail: str, ctype="bgp_session", params=None) -> Result:
    c = Check(type=ctype, params=params or {"node": "r1", "neighbor": "10.0.12.2", "state": "established"},
              name="r1 session", timeout=90)
    ev = [{"node": "r1", "cmd": "vtysh -c 'show bgp summary json'", "rc": 0, "output": "{}", "stderr": ""}]
    hist = [_sample(0.5, ok, detail)]
    return Result(c, ok, detail, 1, 0.5, "2026-10-27T12:00:01+00:00", ev, hist,
                  samples_passed=int(ok), samples_unready=int(isinstance(detail, Unready)))


def test_schema_is_valid_draft_2020_12():
    jsonschema.Draft202012Validator.check_schema(SCHEMA)
    assert SCHEMA["properties"]["schema"]["const"] == json.loads(report.to_json(_report()))["schema"]


@pytest.mark.parametrize("results,error,status", [
    ([_result(True, "state is established")], "", "passed"),
    ([_result(True, "state is established"), _result(False, "state is active")], "", "failed"),
    ([_result(False, Unready("error: vtysh failed"))], "", "inconclusive"),
    ([], "containerlab deploy failed: image not found", "error"),
])
def test_every_status_validates(results, error, status):
    rep = _report(results, error)
    assert rep.status == status
    _validate(json.loads(report.to_json(rep)))


def test_report_of_a_run_that_could_not_start_validates(tmp_path):
    # the real code path, no lab started: the run ends in error before any check runs. Where containerlab is
    # installed, the error is the unknown node r9; on CI's unit runners (no containerlab) it's the missing tool.
    # Either way the report of a run that couldn't start must match the schema.
    topo = tmp_path / "topology.clab.yml"
    topo.write_text("name: t\ntopology:\n  nodes:\n    r1: {kind: linux, image: frr}\n", encoding="utf-8")
    check = Check(type="route", params={"node": "r9", "prefix": "10.0.0.0/24"}, name="r9 route", timeout=90)
    data = json.loads(report.to_json(run(Config(tmp_path / "netdryrun.yml", topo, 90, [check]), deploy=False)))
    assert data["status"] == "error" and ("r9" in data["error"] or "not found" in data["error"])
    _validate(data)


def test_schema_rejects_a_wrong_report():
    data = json.loads(report.to_json(_report([_result(True, "state is established")])))
    for broken in ({**data, "status": ""}, {**data, "status": None}, {**data, "schema": "netdryrun.report/v2"},
                   {k: v for k, v in data.items() if k != "checks"}, {**data, "error": "x"}):
        with pytest.raises(jsonschema.ValidationError):
            _validate(broken)


def test_every_check_type_and_status_is_documented_in_the_schema():
    # type and status are open strings (v1 only adds), but every value the code can write is named
    from netdryrun.config import CHECK_TYPES
    types = SCHEMA["$defs"]["check"]["properties"]["type"]["description"]
    assert all(t in types for t in CHECK_TYPES)
    statuses = SCHEMA["properties"]["status"]["description"]
    assert all(s in statuses for s in ("passed", "failed", "error", "inconclusive"))


def test_spec_page_example_validates_and_names_every_status():
    # the open spec (website/docs/spec/verdict-v1.md) shows a document that must match the schema it describes
    import re
    page = (ROOT / "website/docs/spec/verdict-v1.md").read_text(encoding="utf-8")
    example = re.search(r"```json\n(.*?)```", page, re.S).group(1)
    _validate(json.loads(example))
    assert all(f"`{s}`" in page for s in ("passed", "failed", "error", "inconclusive", SCHEMA["properties"]["schema"]["const"]))


@pytest.mark.skipif(not REAL, reason="no captured reports")
@pytest.mark.parametrize("path", REAL, ids=[p.stem for p in REAL])
def test_real_reports_validate(path):
    # reports written by real lab runs (netdryrun run --json), one per status they cover
    _validate(json.loads(path.read_text(encoding="utf-8")))
