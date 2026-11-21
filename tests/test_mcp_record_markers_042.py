"""Oracle FP-042-MCPMISSNODE: the record_baseline MCP tool names every first-line gap marker `record` can produce.

record.GAP_MARKERS is the one list: render puts a warning first in the file exactly when it starts with one of them,
baseline_gaps (the CLI's exit 1) reads the same list, and the tool description is built from it. These tests kill a
description that names one marker only, a render that puts a line first with a marker outside the list, and a
baseline_gaps that drops the missing-node line.
"""
import asyncio

from netdryrun import mcp_server
from netdryrun import record as rec


def description() -> str:
    tools = {t.name: " ".join(t.description.split()) for t in asyncio.run(mcp_server.mcp.list_tools())}
    return tools["record_baseline"]


def test_every_gap_marker_is_named_in_the_description():
    desc = description()
    assert set(rec.GAP_MARKERS) == {"INCOMPLETE BASELINE", rec.MISSING_NODE}
    for marker in rec.GAP_MARKERS:
        assert f'"# {marker}"' in desc, (marker, desc)


def test_render_puts_first_exactly_the_lines_with_a_gap_marker():
    warnings = [f"{rec.MISSING_NODE}: r1: no check is recorded on it",
                "INCOMPLETE BASELINE: r2: could not read IPv6 routes (x)",
                "r3: learns 0.0.0.0/0 via BGP today; no 'no default route' guard recorded"]
    text = rec.render({"lab": "t.clab.yml", "timeout": 120, "checks": []}, warnings)
    head = text.split("\n#\n", 1)[0].splitlines()
    assert head == [f"# {w}" for w in warnings[:2]]
    assert all(line.removeprefix("# ").startswith(rec.GAP_MARKERS) for line in head)


def test_the_missing_node_line_makes_record_exit_1():
    line = f"{rec.MISSING_NODE}: r1: no check is recorded on it"
    assert rec.baseline_gaps([line, "r3: a plain warning"]) == [line]
