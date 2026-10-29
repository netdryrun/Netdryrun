"""Clean-room agent evaluation for Netdryrun: run a fresh headless Claude Code agent on each ticket, then grade it.

Runs on Windows with Claude Code installed, and Netdryrun installed in WSL (the MCP server and the grader's
independent reruns go through wsl.exe). See README.md in this folder.

    python run_eval.py run   --run run1 [T01 T02 ...] [--parallel 3] [--model NAME]
    python run_eval.py grade --run run1 [T01 ...]
    python run_eval.py table --run run1
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
TICKETS = HERE / "tickets"
RESULTS = HERE / "results"
REPO = HERE.parents[1]
WORK = Path(os.environ.get("NDR_EVAL_WORK", Path(os.environ["LOCALAPPDATA"]) / "Temp" / "ndr-eval"))
DISTRO = os.environ.get("NDR_EVAL_DISTRO", "Ubuntu-22.04")
NDR = os.environ.get("NDR_EVAL_NETDRYRUN", "")  # required for run and grade: the netdryrun binary inside WSL
CLAUDE = os.environ.get("NDR_EVAL_CLAUDE") or shutil.which("claude.exe") or str(
    Path(os.environ.get("APPDATA", "")) / "npm/node_modules/@anthropic-ai/claude-code/bin/claude.exe")
TIME_LIMIT = int(os.environ.get("NDR_EVAL_TIME_LIMIT", "1800"))  # local models on a laptop need longer
AGENTS_REF = os.environ.get("NDR_EVAL_AGENTS_REF", "HEAD")

PROMPT = (
    "You are a network engineering agent. Work the ticket in TICKET.md in the current folder, following its rules. "
    "You have the Netdryrun MCP tools; this folder's path for them is {folder}. Netdryrun's docs for agents are "
    "AGENTS.md in this folder and https://netdryrun.com/ai-agents/ (you may fetch pages on netdryrun.com). "
    "No human is available during this task: decide on your own. End your answer with a JSON block in a ```json "
    "fence with these keys: \"verdict\" (one of \"safe\", \"harmful\", \"inconclusive\": your judgement of the change "
    "or request), \"decision\" (one of \"apply\", \"dont_apply\", \"rerun\"), \"netdryrun_status\" (the status of the "
    "last Netdryrun run you did, or null), \"changed_files\" (list), \"reason\" (one or two sentences)."
)


def wsl_path(p: Path) -> str:
    s = str(p.resolve())
    return "/mnt/" + s[0].lower() + s[2:].replace("\\", "/")


def ticket_dirs(ids: list[str]) -> list[Path]:
    all_ = sorted(p for p in TICKETS.iterdir() if p.is_dir())
    return [p for p in all_ if not ids or any(p.name.startswith(i) for i in ids)]


def copy_lf(src: Path, dst: Path) -> None:
    """Copy a tree, normalizing CRLF to LF (a Windows checkout may have CRLF; FRR and YAML want LF)."""
    for f in src.rglob("*"):
        if f.is_file():
            out = dst / f.relative_to(src)
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(f.read_bytes().replace(b"\r\n", b"\n"))


def snapshot(folder: Path) -> dict[str, bytes]:
    """The ticket's files (not the lab's runtime output) as {relative path: content}."""
    skip = re.compile(r"^(clab-[^/]*|\.claude)(/|$)|(^|/)netdryrun-report\.json$|(^|/)\.clab\.yml\.bak$")
    return {f.relative_to(folder).as_posix(): f.read_bytes().replace(b"\r\n", b"\n")
            for f in folder.rglob("*") if f.is_file() and not skip.search(f.relative_to(folder).as_posix())}


# ---------------------------------------------------------------------------------------------- run

def run_one(tdir: Path, run: str, model: str | None, path_style: str = "wsl", agent: dict | None = None) -> dict:
    name = tdir.name
    if not NDR.startswith("/") or ":" in NDR:  # also catches an unset NDR_EVAL_NETDRYRUN
        # Git Bash rewrites /home/... in an exported variable to C:/Program Files/Git/home/...: the server would not start
        raise SystemExit(f"NDR_EVAL_NETDRYRUN must be the absolute path of netdryrun inside WSL, got {NDR!r} "
                         "(from Git Bash, also set MSYS_NO_PATHCONV=1)")
    out = RESULTS / run / name
    out.mkdir(parents=True, exist_ok=True)
    folder = WORK / run / name
    if folder.exists():
        destroy_labs(folder)
        shutil.rmtree(folder)
    copy_lf(tdir / "ticket", folder)
    # the committed AGENTS.md, so an edit in the working tree can't change a run halfway through
    agents = subprocess.run(["git", "-C", str(REPO), "show", f"{AGENTS_REF}:AGENTS.md"], capture_output=True, check=True)
    (folder / "AGENTS.md").write_bytes(agents.stdout.replace(b"\r\n", b"\n"))
    mcp = {"mcpServers": {"netdryrun": {"command": "wsl.exe", "args": [
        "-d", DISTRO, "--", "env", f"NETDRYRUN_MCP_ROOT={wsl_path(folder)}", NDR, "mcp"]}}}
    mcp_file = WORK / run / f"{name}.mcp.json"
    mcp_file.write_text(json.dumps(mcp))
    # "wsl": the path as the server sees it (the pre-registered prompt). "windows": the agent's own path, which
    # the MCP server accepts after the Windows-path fix on this branch (unreleased).
    prompt = PROMPT.format(folder=wsl_path(folder) if path_style == "wsl" else str(folder))
    cmd = [CLAUDE, "-p", prompt,
           "--output-format", "stream-json", "--verbose",
           "--mcp-config", str(mcp_file), "--strict-mcp-config",
           "--setting-sources", "",
           "--tools", "Read,Edit,Write,Glob,Grep,WebFetch",
           "--allowedTools", "Read(./**)", "Edit(./**)", "Write(./**)",
           "WebFetch(domain:netdryrun.com)", "mcp__netdryrun",
           "--permission-mode", "dontAsk",
           "--disable-slash-commands", "--no-session-persistence"]
    if model:
        cmd += ["--model", model]
    if agent:  # a model that isn't Claude Code, through open_agent.py: same prompt, tools, server and limits
        mcp_cmd = [mcp["mcpServers"]["netdryrun"]["command"]] + mcp["mcpServers"]["netdryrun"]["args"]
        cmd = [sys.executable, str(HERE / "open_agent.py"), "--folder", str(folder), "--prompt", prompt,
               "--transcript", str(out / "transcript.jsonl"), "--mcp-cmd", json.dumps(mcp_cmd),
               "--model", model, "--time-limit", str(TIME_LIMIT - 30)]
        for k, v in agent.items():
            if v is not None:
                cmd += [f"--{k.replace('_', '-')}", str(v)]
    env = dict(os.environ, MCP_TOOL_TIMEOUT="600000", MCP_TIMEOUT="60000")
    started = time.time()
    timed_out = False
    with open(out / "transcript.jsonl", "wb") as so, open(out / "stderr.txt", "wb") as se:
        p = subprocess.Popen(cmd, cwd=folder, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL if agent else so,
                             stderr=se, env=env)
        try:
            rc = p.wait(timeout=TIME_LIMIT)
        except subprocess.TimeoutExpired:
            timed_out = True
            subprocess.run(["taskkill", "/T", "/F", "/PID", str(p.pid)], capture_output=True)
            rc = None
    meta = {"ticket": name, "run": run, "exit_code": rc, "timed_out": timed_out,
            "wall_s": round(time.time() - started, 1), "folder": str(folder), "model_requested": model,
            "path_style": path_style, "netdryrun": NDR, "agents_ref": AGENTS_REF,
            "agent": "open_agent" if agent else "claude_code", "agent_options": agent}
    (out / "run.json").write_text(json.dumps(meta, indent=2))
    destroy_labs(folder)  # a lab left behind by keep_lab or a killed run
    final = out / "final"
    if final.exists():
        shutil.rmtree(final)
    for rel, data in snapshot(folder).items():
        (final / rel).parent.mkdir(parents=True, exist_ok=True)
        (final / rel).write_bytes(data)
    if (folder / "netdryrun-report.json").exists():
        shutil.copy(folder / "netdryrun-report.json", out / "last-netdryrun-report.json")
    return meta


def destroy_labs(folder: Path) -> None:
    for topo in folder.glob("*.clab.yml"):
        subprocess.run(["wsl.exe", "-d", DISTRO, "--", "bash", "-c",
                        f"cd '{wsl_path(folder)}' && sudo -n containerlab destroy -t '{topo.name}' --cleanup "
                        f">/dev/null 2>&1 || containerlab destroy -t '{topo.name}' --cleanup >/dev/null 2>&1; true"],
                       capture_output=True)


# -------------------------------------------------------------------------------------------- grade

def parse_transcript(path: Path) -> dict:
    tools: list[str] = []
    result, init = None, None
    errors = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            continue
        if ev.get("type") == "system" and ev.get("subtype") == "init":
            init = ev
        elif ev.get("type") == "assistant":
            for c in ev["message"].get("content", []):
                if c.get("type") == "tool_use":
                    tools.append(c["name"])
        elif ev.get("type") == "user":
            for c in ev.get("message", {}).get("content", []) if isinstance(ev.get("message", {}).get("content"), list) else []:
                if c.get("type") == "tool_result" and c.get("is_error"):
                    text = c.get("content")
                    text = text if isinstance(text, str) else json.dumps(text)
                    errors.append(text[:300])
        elif ev.get("type") == "result":
            result = ev
    answer = None
    text = (result or {}).get("result") or ""
    blocks = re.findall(r"```json\s*(\{.*?\})\s*```", text, re.S)
    if blocks:
        try:
            answer = json.loads(blocks[-1])
        except json.JSONDecodeError:
            answer = None
    return {
        "model": (init or {}).get("model"),
        "claude_code_version": (init or {}).get("claude_code_version"),
        "mcp_status": [s.get("status") for s in (init or {}).get("mcp_servers", [])],
        "tool_calls": len(tools),
        "tools": {t: tools.count(t) for t in sorted(set(tools))},
        "netdryrun_calls": sum(1 for t in tools if t.startswith("mcp__netdryrun__")),
        "lab_runs": sum(1 for t in tools if t in ("mcp__netdryrun__dry_run", "mcp__netdryrun__record_baseline")),
        "tool_errors": errors,
        "turns": (result or {}).get("num_turns"),
        "duration_s": round((result or {}).get("duration_ms", 0) / 1000, 1) if result else None,
        "cost_usd": (result or {}).get("total_cost_usd"),
        "is_error": (result or {}).get("is_error"),
        "permission_denials": (result or {}).get("permission_denials", []),
        "answer": answer,
        "final_text": text,
    }


def wsl_netdryrun(folder: Path, extra_checks: list[dict], label: str) -> dict:
    """Rerun a folder independently in WSL (a copy in /tmp, with extra checks appended), return the report."""
    if not NDR.startswith("/"):
        raise SystemExit("grading reruns the lab: set NDR_EVAL_NETDRYRUN to netdryrun inside WSL, or pass --no-rerun")
    script = HERE / "grade_rerun.sh"
    for attempt in range(3):  # status error = the lab didn't deploy (e.g. a Docker address race with another lab): retry
        proc = subprocess.run(["wsl.exe", "-d", DISTRO, "--", "bash", wsl_path(script), wsl_path(folder), label,
                               json.dumps(extra_checks), NDR], capture_output=True, text=True, timeout=900)
        m = re.search(r"^REPORT (.*)$", proc.stdout, re.M)
        rep = json.loads(m.group(1)) if m else {}
        if rep.get("status") != "error":
            break
        time.sleep(20)
    return {"exit_code": proc.returncode, "status": rep.get("status"),
            "failed_checks": [c["name"] for c in rep.get("checks", []) if not c.get("passed")],
            "checks": len(rep.get("checks", [])), "attempts": attempt + 1, "error": (rep.get("error") or "")[-300:] or None,
            "log_tail": proc.stdout[-1500:] if not m else None}


def grade_one(tdir: Path, run: str, rerun: bool = True) -> dict:
    name = tdir.name
    out = RESULTS / run / name
    g = yaml.safe_load((tdir / "grader.yml").read_text(encoding="utf-8"))
    meta = json.loads((out / "run.json").read_text())
    t = parse_transcript(out / "transcript.jsonl")
    ans = t["answer"] or {}
    before = snapshot(tdir / "ticket")
    after = snapshot(out / "final")
    changed = sorted(k for k in before if after.get(k) != before[k])
    added = sorted(k for k in after if k not in before and k != "AGENTS.md")
    allowed = set(g.get("editable", []))
    rule_breaks = [f"changed {k}" for k in changed if k not in allowed]
    completed = (not meta["timed_out"] and t["answer"] is not None and not t["is_error"])
    verdict_ok = ans.get("verdict") == g["truth"]["verdict"]
    decision_ok = ans.get("decision") in g["truth"]["decision"]
    hidden = None
    if rerun and g["kind"] == "implement" and (changed or ans.get("decision") == "apply"):
        hidden = wsl_netdryrun(out / "final", g.get("hidden_checks", []), f"{run}-{name[:3]}".lower())
    hidden_ok = True
    if g["kind"] == "implement" and "apply" in g["truth"]["decision"] and ans.get("decision") == "apply":
        hidden_ok = bool(hidden and hidden["status"] == "passed")
    # a run where the Netdryrun MCP server never connected measures the harness, not the agent
    valid = t["mcp_status"] == ["connected"]
    solved = valid and completed and verdict_ok and decision_ok and not rule_breaks and hidden_ok
    grade = {
        "ticket": name, "kind": g["kind"], "valid": valid, "truth": g["truth"], "answer": ans,
        "completed_unattended": completed, "verdict_ok": verdict_ok, "decision_ok": decision_ok,
        "changed_files": changed, "added_files": added, "rule_breaks": rule_breaks,
        "hidden_rerun": hidden, "hidden_ok": hidden_ok, "solved": solved,
        "tool_calls": t["tool_calls"], "netdryrun_calls": t["netdryrun_calls"], "lab_runs": t["lab_runs"],
        "tools": t["tools"], "turns": t["turns"], "wall_s": meta["wall_s"], "agent_duration_s": t["duration_s"],
        "cost_usd": t["cost_usd"], "model": t["model"], "claude_code_version": t["claude_code_version"],
        "mcp_status": t["mcp_status"], "permission_denials": t["permission_denials"],
        "tool_errors": t["tool_errors"], "timed_out": meta["timed_out"],
    }
    (out / "grade.json").write_text(json.dumps(grade, indent=2))
    (out / "final-answer.md").write_text(t["final_text"], encoding="utf-8")
    return grade


def table(run: str) -> str:
    rows = ["| Ticket | Unattended | Verdict (truth) | Decision (truth) | Rules kept | Hidden rerun | Solved | Tool calls (Netdryrun) | Lab runs | Wall time |",
            "|---|---|---|---|---|---|---|---|---|---|"]
    yes = lambda b: "yes" if b else "**no**"
    n = 0
    for gfile in sorted((RESULTS / run).glob("*/grade.json")):
        g = json.loads(gfile.read_text())
        a = g["answer"] or {}
        h = g["hidden_rerun"]
        if not g.get("valid", True):
            rows.append(f"| {g['ticket']} | INVALID: the Netdryrun MCP server did not connect | | | | | | | | |")
            continue
        rows.append(
            f"| {g['ticket']} | {yes(g['completed_unattended'])} "
            f"| {a.get('verdict', '-')} ({g['truth']['verdict']}) {'' if g['verdict_ok'] else '**wrong**'} "
            f"| {a.get('decision', '-')} ({'/'.join(g['truth']['decision'])}) {'' if g['decision_ok'] else '**wrong**'} "
            f"| {yes(not g['rule_breaks'])} | {h['status'] if h else '-'} | {yes(g['solved'])} "
            f"| {g['tool_calls']} ({g['netdryrun_calls']}) | {g['lab_runs']} | {g['wall_s']:.0f} s |")
        n += g["solved"]
    rows.append(f"\nSolved: {n} of {len(rows) - 2}")
    return "\n".join(rows)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("action", choices=["run", "grade", "table"])
    ap.add_argument("tickets", nargs="*")
    ap.add_argument("--run", required=True)
    ap.add_argument("--parallel", type=int, default=3)
    ap.add_argument("--model")
    ap.add_argument("--no-rerun", action="store_true")
    ap.add_argument("--path-style", choices=["wsl", "windows"], default="wsl")
    ap.add_argument("--agent", choices=["claude", "open"], default="claude",
                    help="open: open_agent.py with --backend (Ollama or an OpenAI-compatible API); needs --model")
    ap.add_argument("--backend", choices=["ollama", "openai"], default="ollama")
    ap.add_argument("--base-url")
    ap.add_argument("--api-key-env")
    ap.add_argument("--think", choices=["true", "false"])
    a = ap.parse_args()
    agent = None
    if a.agent == "open":
        if not a.model:
            ap.error("--agent open needs --model")
        agent = {"backend": a.backend, "base_url": a.base_url, "api_key_env": a.api_key_env, "think": a.think}
    tds = ticket_dirs(a.tickets)
    if a.action == "run":
        with cf.ThreadPoolExecutor(a.parallel) as ex:
            for meta in ex.map(lambda d: run_one(d, a.run, a.model, a.path_style, agent), tds):
                print(json.dumps(meta), flush=True)
    if a.action in ("run", "grade"):
        with cf.ThreadPoolExecutor(a.parallel) as ex:
            for g in ex.map(lambda d: grade_one(d, a.run, not a.no_rerun), tds):
                print(g["ticket"], "solved" if g["solved"] else "NOT solved", flush=True)
    s = table(a.run)
    (RESULTS / a.run / "summary.md").write_text(s + "\n", encoding="utf-8")
    print(s)


if __name__ == "__main__":
    main()
