"""Where each agent got stuck: signals read from every transcript of a run, one row per ticket, into stuck.md.

    python stuck.py RUN [RUN ...]

The signals are mechanical (what the transcript shows); the "first wrong move" column is filled in by hand after
reading the transcript, and kept in results/<run>/notes.json ({"T01-new-block": "..."}) so a rerun keeps it.
"""
from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path

RESULTS = Path(__file__).resolve().parent / "results"
LAB = ("mcp__netdryrun__dry_run", "mcp__netdryrun__record_baseline")


def signals(tdir: Path) -> dict:
    calls, errors, docs, last, mcp = [], [], set(), None, None
    result = {}
    for line in (tdir / "transcript.jsonl").read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            continue
        if ev.get("type") == "system" and ev.get("subtype") == "init":
            mcp = [s.get("status") for s in ev.get("mcp_servers", [])]
        elif ev.get("type") == "assistant":
            for c in ev["message"].get("content", []):
                if c.get("type") == "tool_use":
                    inp = c.get("input") or {}
                    calls.append((c["name"], json.dumps(inp, sort_keys=True)))
                    last = c["name"]
                    target = str(inp.get("path") or inp.get("file_path") or inp.get("url") or "")
                    if "AGENTS.md" in target or "netdryrun.com" in target:
                        docs.add("AGENTS.md" if "AGENTS.md" in target else "website")
        elif ev.get("type") == "user":
            content = ev.get("message", {}).get("content")
            for c in content if isinstance(content, list) else []:
                if c.get("type") == "tool_result" and c.get("is_error"):
                    text = c.get("content")
                    errors.append((text if isinstance(text, str) else json.dumps(text))[:160])
        elif ev.get("type") == "result":
            result = ev
    text = result.get("result") or ""
    repeats = [f"{n.split('__')[-1]} x{k}" for (n, _), k in Counter(calls).items() if k >= 3]
    lab_runs = sum(1 for n, _ in calls if n in LAB)
    end = ("no result" if not result else "stopped: " + text.strip("[]") if text.startswith("[")
           else "answered" if re.search(r"```json\s*\{", text) else "ended without the JSON answer")
    return {"mcp": mcp, "tool_calls": len(calls), "lab_runs": lab_runs, "docs": sorted(docs),
            "errors": len(errors), "first_error": errors[0] if errors else "", "repeats": repeats,
            "last_tool": (last or "-").split("__")[-1], "end": end, "turns": result.get("num_turns")}


def row(tdir: Path, notes: dict) -> str:
    s = signals(tdir)
    g = json.loads((tdir / "grade.json").read_text()) if (tdir / "grade.json").exists() else {}
    a = g.get("answer") or {}
    flags = []
    if s["mcp"] != ["connected"]:
        flags.append("server never connected (invalid)")
    if s["lab_runs"] == 0:
        flags.append("never ran a lab")
    if s["repeats"]:
        flags.append("looped: " + ", ".join(s["repeats"]))
    if g.get("rule_breaks"):
        flags.append("broke a rule: " + ", ".join(g["rule_breaks"]))
    if g and not g.get("verdict_ok"):
        flags.append(f"wrong verdict ({a.get('verdict')} vs {g['truth']['verdict']})")
    if g and g.get("hidden_ok") is False:
        flags.append("its change fails the hidden check")
    cell = lambda x: str(x).replace("|", "\\|").replace("\n", " ")
    return (f"| {tdir.name} | {'yes' if g.get('solved') else '**no**'} | {s['end']} | {s['tool_calls']} / {s['lab_runs']} "
            f"| {', '.join(s['docs']) or 'none'} | {s['errors']}{': ' + cell(s['first_error']) if s['errors'] else ''} "
            f"| {s['last_tool']} | {cell('; '.join(flags)) or '-'} | {cell(notes.get(tdir.name, ''))} |")


def main() -> None:
    for run in sys.argv[1:]:
        base = RESULTS / run
        notes_file = base / "notes.json"
        notes = json.loads(notes_file.read_text(encoding="utf-8")) if notes_file.exists() else {}
        lines = [f"# Where the agents got stuck: {run}", "",
                 "| Ticket | Solved | How it ended | Tool calls / lab runs | Docs read | Tool errors (first) | Last tool | Signals | First wrong move (by hand) |",
                 "|---|---|---|---|---|---|---|---|---|"]
        lines += [row(t, notes) for t in sorted(p for p in base.iterdir() if (p / "transcript.jsonl").exists())]
        (base / "stuck.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
        print("\n".join(lines))


if __name__ == "__main__":
    main()
