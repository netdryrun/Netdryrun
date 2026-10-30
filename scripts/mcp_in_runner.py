"""0.3.3 spike (d): the Netdryrun MCP server inside a CI runner, driven by a scripted MCP client.

This is what a coding agent that runs on a CI runner would do, minus the language model: start `netdryrun mcp`
over stdio, list the tools, call `dry_run` on a lab that must pass and one that must fail, and read the result
contract; then the same through start_run and get_result, each call answering within seconds. It shows that
the server, containerlab and Docker work inside the runner; it says nothing about
whether a given hosted agent lets you add the server (see the spike write-up).

Usage (on a runner with Docker and containerlab, as the Action does): python scripts/mcp_in_runner.py --out FILE
Exit 0 only when every expectation holds.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXPECT = [("examples/frr-bgp", "passed"), ("examples/frr-bgp-broken", "failed")]


def server_command() -> tuple[str, list[str]]:
    """containerlab needs root on GitHub-hosted runners: run the server as the Action runs netdryrun, with
    only PATH and HOME (no job tokens)."""
    if os.geteuid() == 0:
        return "netdryrun", ["mcp"]
    return "sudo", ["env", "-i", f"PATH={os.environ['PATH']}", "HOME=/root", "netdryrun", "mcp"]


def problems_with(result: dict, want: str, schema: dict | None) -> list[str]:
    """What is wrong with one dry_run result, judged on status and the v1 contract (not on the text)."""
    out = []
    if result.get("status") != want:
        out.append(f"status {result.get('status')!r}, expected {want!r} ({result.get('error') or ''})")
    if want == "passed" and result.get("failures"):
        out.append("a passed result lists failures")
    if want == "failed" and not result.get("failures"):
        out.append("a failed result has no failures entry")
    if not (result.get("tested") or {}).get("files"):
        out.append("no tested.files")
    if schema is not None:
        import jsonschema
        try:
            jsonschema.Draft202012Validator(schema).validate(result)
        except jsonschema.ValidationError as e:
            out.append(f"not valid against mcp-result-v1.json: {e.message}")
    return out


async def drive(timeout: float) -> dict:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    cmd, args = server_command()
    schema_path = ROOT / "website" / "docs" / "schemas" / "mcp-result-v1.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    report: dict = {"server": [cmd, *args[-2:]], "calls": [], "ok": True}
    started = time.monotonic()
    async with stdio_client(StdioServerParameters(command=cmd, args=args)) as (r, w):
        async with ClientSession(r, w) as s:
            await s.initialize()
            report["handshake_s"] = round(time.monotonic() - started, 1)
            report["tools"] = sorted(t.name for t in (await s.list_tools()).tools)
            for path, want in EXPECT:
                t0 = time.monotonic()
                res = await asyncio.wait_for(s.call_tool("dry_run", {"path": str(ROOT / path)}), timeout)
                result = json.loads(res.content[0].text)
                wrong = problems_with(result, want, schema)
                report["calls"].append({"path": path, "want": want, "status": result.get("status"),
                                        "verdict": result.get("verdict"), "seconds": round(time.monotonic() - t0, 1),
                                        "problems": wrong})
                report["ok"] = report["ok"] and not wrong
            # the asynchronous shape: every call answers within seconds, the polled result is dry_run's
            if "start_run" in report["tools"]:
                report["async"] = await _async_run(s, schema, timeout)
                report["ok"] = report["ok"] and not report["async"]["problems"]
    return report


async def _async_run(s, schema: dict, timeout: float) -> dict:
    path, want = EXPECT[0]
    t0 = time.monotonic()
    started = json.loads((await asyncio.wait_for(s.call_tool("start_run", {"path": str(ROOT / path)}), 10)).content[0].text)
    out = {"path": path, "start_s": round(time.monotonic() - t0, 1), "polls": 0, "slowest_poll_s": 0.0, "problems": []}
    if started.get("status") != "running" or "verdict" in started:
        out["problems"].append(f"start_run answered {started}")
        return out
    result = started
    while result.get("status") == "running" and time.monotonic() - t0 < timeout:
        await asyncio.sleep(min(float(started.get("poll_after_s", 15)), 15))
        p0 = time.monotonic()
        result = json.loads((await asyncio.wait_for(s.call_tool("get_result", {"run_id": started["run_id"]}), 10)).content[0].text)
        out["polls"] += 1
        out["slowest_poll_s"] = max(out["slowest_poll_s"], round(time.monotonic() - p0, 1))
    out["seconds"], out["status"] = round(time.monotonic() - t0, 1), result.get("status")
    out["problems"] += problems_with(result, want, schema)
    if result.get("run_id") != started["run_id"]:
        out["problems"].append("the finished result has another run_id")
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--timeout", type=float, default=600, help="seconds per dry_run call")
    a = ap.parse_args()
    try:
        report = asyncio.run(drive(a.timeout))
    except Exception as e:   # the spike's answer is "it did not work, and why", never a traceback alone
        report = {"ok": False, "error": f"{type(e).__name__}: {e}"}
    Path(a.out).write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
