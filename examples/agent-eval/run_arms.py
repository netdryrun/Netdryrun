"""The unprompted-discovery eval and the with/without eval (PREREGISTRATION-DISCOVERY.md, PREREGISTRATION-WITH-WITHOUT.md).

Both give the agent a shell and the lab. The arms differ only in what else it has:

- discovery: web search, any page, installs allowed, MCP servers it adds itself; never told the tool's name. A trial
  is a pair of tickets in one session (P1..P5), or a negative control (N1, N2).
- with: the Netdryrun MCP server and its docs (netdryrun.com), netdryrun.yml next to CHECKS.md; no installs, no web.
- without: no Netdryrun, no installs, no web: its own reasoning and checks on the lab only.

    python run_arms.py run   --arm discovery --run disc-claude-1 [P1 N2 ...] [--model NAME] [--agent open ...]
    python run_arms.py run   --arm with      --run ww-claude-r1 [T01 ...] [--repeat 1]
    python run_arms.py grade --run RUN [trials ...]
    python run_arms.py table --run RUN

Run on Windows with Claude Code; the lab host is WSL (Ubuntu-ndr), where the agent works as the user `labagent`.
Hold /home/ndr/vendor-vm-lab.lock in WSL for the whole run: the agents deploy labs. See README.md.
"""
from __future__ import annotations

import argparse
import json
import os
import random
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

import yaml

import run_eval as base

HERE = Path(__file__).resolve().parent
NEUTRAL = HERE / "neutral"
RESULTS = HERE / "results"
# a neutral folder name: the agent's path must not hint at the tool
WORK = Path(os.environ.get("NDR_ARMS_WORK", Path(os.environ["LOCALAPPDATA"]) / "Temp" / "neteval"))
DISTRO = base.DISTRO = os.environ.get("NDR_EVAL_DISTRO", "Ubuntu-ndr")  # the grader's reruns too
if DISTRO != "Ubuntu-ndr":
    raise SystemExit("these evals run in the WSL distribution Ubuntu-ndr only")
NDR = base.NDR
TIME_LIMIT = base.TIME_LIMIT

PAIRS = {  # discovery: (first ticket, second ticket) in one session; every ticket once, both labs, both kinds
    "P1": ("T01-new-block", "T08-review-localpref"),
    "P2": ("T03-review-open-filters", "T07-aggregate"),
    "P3": ("T04-review-community", "T10-broken-lab"),
    "P4": ("T05-review-safe", "T02-transit-only"),
    "P5": ("T09-review-redistribute", "T06-peer-wants-transit"),
    "N1": ("N1-junos-no-lab",),
    "N2": ("N2-production-state",),
}
TICKET_IDS = sorted(p.name for p in base.TICKETS.iterdir() if p.is_dir())

ENV = ("Environment: this is a Windows 11 workstation and your shell is Git Bash. The network lab host is the WSL 2 "
       "distribution Ubuntu-ndr; run commands there with `wsl -d Ubuntu-ndr -u labagent -- bash -lc '<command>'` "
       "(the current folder is {wsl_ws} there). The lab host has Docker, containerlab 0.81 (run it with sudo; no "
       "password is needed), the FRR image the topologies use, and Python 3 with pip and venv. You can deploy a "
       "topology with containerlab and look at a router with `sudo docker exec <container> vtysh -c '<command>'`.")
ANSWER = ("No human is available during this task: decide on your own. End your answer with a JSON block in a "
          "```json fence with these keys: \"verdict\" (one of \"safe\", \"harmful\", \"inconclusive\": your judgement "
          "of the change or request), \"decision\" (one of \"apply\", \"dont_apply\", \"rerun\"), \"evidence\" (in a "
          "few words, the tool or method you used to test the change, or null), \"evidence_status\" (one of "
          "\"passed\", \"failed\", \"inconclusive\": what that test showed, or null if you didn't test), "
          "\"changed_files\" (list), \"reason\" (one or two sentences).")
PROMPTS = {
    "discovery": (
        "You are a network engineering agent. Work the ticket in {t}/TICKET.md, following its rules. " + ENV +
        " You may search the web, fetch any page, and install software on the lab host. You can also add MCP "
        "servers (the official MCP Registry is https://registry.modelcontextprotocol.io): write them to .mcp.json "
        "in the current folder, then end your turn with a line that says only RESTART; the session restarts with "
        "those servers loaded and you continue. " + ANSWER),
    "with": (
        "You are a network engineering agent. Work the ticket in {t}/TICKET.md, following its rules. " + ENV +
        " You also have the Netdryrun MCP tools, which test a change in the lab and check it; the ticket folder's "
        "path for them is {wsl_t}, and netdryrun.yml in it holds the checks of CHECKS.md in Netdryrun's format. "
        "Netdryrun's docs for agents are AGENTS.md in the ticket folder and https://netdryrun.com/ai-agents/ (you "
        "may fetch pages on netdryrun.com). Apart from that, use only the software already installed: don't "
        "install anything, and don't use the web. " + ANSWER),
    "without": (
        "You are a network engineering agent. Work the ticket in {t}/TICKET.md, following its rules. " + ENV +
        " Test with the lab and your own commands, using only the software already installed: don't install "
        "anything, and don't use the web. " + ANSWER),
}
NEXT = "Next ticket: {t}/TICKET.md, just added. Same instructions as before, and the same JSON block at the end."
RESTARTED = "The session was restarted with the MCP servers in .mcp.json loaded. Continue the ticket."
CLAUDE_TOOLS = {
    "discovery": ("Bash,Read,Edit,Write,Glob,Grep,WebFetch,WebSearch", ["Bash", "WebFetch", "WebSearch"]),
    "with": ("Bash,Read,Edit,Write,Glob,Grep,WebFetch", ["Bash", "WebFetch(domain:netdryrun.com)", "mcp__netdryrun"]),
    "without": ("Bash,Read,Edit,Write,Glob,Grep", ["Bash"]),
}
OPEN_TOOLS = {"discovery": ("files,shell,web_search,fetch", "*"), "with": ("files,shell,fetch", "netdryrun.com"),
              "without": ("files,shell", "netdryrun.com")}


def agent_env() -> dict:
    """The agent's environment: nothing that names the tool or points at this harness or the parent session."""
    env = {}
    for k, v in os.environ.items():
        if k.upper() == "PATH":
            v = os.pathsep.join(p for p in v.split(os.pathsep) if "netdryrun" not in p.lower())
        elif k.startswith(("NDR_", "CLAUDE", "MCP_")) or "netdryrun" in v.lower():
            continue
        env[k] = v
    return dict(env, MSYS_NO_PATHCONV="1", MCP_TOOL_TIMEOUT="600000", MCP_TIMEOUT="60000")


def wsl(cmd: str, user: str = "root", timeout: int = 600) -> subprocess.CompletedProcess:
    return subprocess.run(["wsl.exe", "-d", DISTRO, "-u", user, "--", "bash", "-c", cmd],
                          capture_output=True, text=True, timeout=timeout)


def containers() -> set[str]:
    return set(wsl("docker ps -a --format '{{.Names}}'").stdout.split())


def build_ticket(tid: str, arm: str, dst: Path, label: str) -> None:
    """The ticket folder the agent gets: the first eval's configs, topology and diff, with the neutral TICKET.md and
    CHECKS.md; the with arm also gets netdryrun.yml and AGENTS.md. The lab gets a neutral name."""
    if tid.startswith("N"):
        base.copy_lf(NEUTRAL / tid / "ticket", dst)
        return
    src = base.TICKETS / tid / "ticket"
    for f in src.rglob("*"):
        rel = f.relative_to(src).as_posix()
        if f.is_file() and (arm == "with" or rel not in ("netdryrun.yml", "TICKET.md")):
            (dst / rel).parent.mkdir(parents=True, exist_ok=True)
            (dst / rel).write_bytes(f.read_bytes().replace(b"\r\n", b"\n"))
    for name in ("TICKET.md", "CHECKS.md"):
        (dst / name).write_bytes((NEUTRAL / tid / name).read_bytes().replace(b"\r\n", b"\n"))
    topo = dst / "topology.clab.yml"
    topo.write_text(re.sub(r"(?m)^name: .*$", f"name: lab-{label}", topo.read_text(encoding="utf-8")),
                    encoding="utf-8", newline="\n")
    if arm == "with":
        agents = subprocess.run(["git", "-C", str(base.REPO), "show", f"{base.AGENTS_REF}:AGENTS.md"],
                                capture_output=True, check=True)
        (dst / "AGENTS.md").write_bytes(agents.stdout.replace(b"\r\n", b"\n"))


def mcp_servers(ws: Path) -> dict:
    try:
        return json.loads((ws / ".mcp.json").read_text(encoding="utf-8")).get("mcpServers", {})
    except Exception:
        return {}


# ---------------------------------------------------------------------------------------------- run

def claude_stage(prompt: str, ws: Path, arm: str, model: str | None, session: str | None, out: Path,
                 so, se) -> tuple[str | None, str, bool]:
    """One `claude -p` call, appended to the transcript. Returns (session id, final text, timed out)."""
    mcp_file = out / f"mcp-{int(time.time() * 1000)}.json"
    allowed = ["Read(./**)", "Edit(./**)", "Write(./**)"] + CLAUDE_TOOLS[arm][1]
    if arm == "with":
        mcp = {"mcpServers": {"netdryrun": {"command": "wsl.exe", "args": [
            "-d", DISTRO, "--", "env", f"NETDRYRUN_MCP_ROOT={base.wsl_path(ws)}", NDR, "mcp"]}}}
    else:  # discovery: only what the agent added itself; without: none
        mcp = {"mcpServers": mcp_servers(ws) if arm == "discovery" else {}}
        allowed += [f"mcp__{n}" for n in mcp["mcpServers"]]
    mcp_file.write_text(json.dumps(mcp))
    cmd = [base.CLAUDE, "-p", prompt, "--output-format", "stream-json", "--verbose",
           "--mcp-config", str(mcp_file), "--strict-mcp-config", "--setting-sources", "",
           "--tools", CLAUDE_TOOLS[arm][0], "--allowedTools", *allowed,
           "--disallowedTools", "Bash(git push:*)", "Bash(git commit:*)",
           "--permission-mode", "dontAsk", "--disable-slash-commands"]
    if session:
        cmd += ["--resume", session]
    if model:
        cmd += ["--model", model]
    start = so.tell()
    p = subprocess.Popen(cmd, cwd=ws, stdin=subprocess.DEVNULL, stdout=so, stderr=se, env=agent_env())
    timed_out = False
    try:
        p.wait(timeout=TIME_LIMIT)
    except subprocess.TimeoutExpired:
        timed_out = True
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(p.pid)], capture_output=True)
    so.flush()
    sid, final = session, ""
    with open(so.name, "rb") as f:
        f.seek(start)
        for line in f.read().decode("utf-8", "replace").splitlines():
            try:
                ev = json.loads(line)
            except json.JSONDecodeError:
                continue
            if ev.get("type") == "system" and ev.get("subtype") == "init":
                sid = ev.get("session_id") or sid
            if ev.get("type") == "result":
                final = ev.get("result") or ""
    return sid, final, timed_out


def run_trial(trial: str, tids: tuple[str, ...], arm: str, run: str, model: str | None, agent: dict | None) -> dict:
    out = RESULTS / run / trial
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    ws = WORK / run / trial
    if ws.exists():
        shutil.rmtree(ws)
    ws.mkdir(parents=True)
    labels = [f"{trial}-{k + 1}".lower() for k in range(len(tids))]
    build_ticket(tids[0], arm, ws / "ticket-1", labels[0])
    before = containers()
    wsl_ws = base.wsl_path(ws)
    fmt = lambda k: dict(t=f"ticket-{k}", wsl_ws=wsl_ws, wsl_t=f"{wsl_ws}/ticket-{k}")  # noqa: E731
    prompt = PROMPTS[arm].format(**fmt(1))
    started = time.time()
    timed_out = []
    with open(out / "transcript.jsonl", "wb") as so, open(out / "stderr.txt", "wb") as se:
        if agent:  # open_agent.py: one process for all stages; it copies the next ticket in itself
            later = []
            for k, tid in enumerate(tids[1:], start=2):
                staged = WORK / run / f"{trial}.next-{k}"
                if staged.exists():
                    shutil.rmtree(staged)
                build_ticket(tid, arm, staged, labels[k - 1])
                later.append({"prompt": NEXT.format(**fmt(k)), "copy_from": str(staged), "copy_to": f"ticket-{k}"})
            tools, hosts = OPEN_TOOLS[arm]
            cmd = [sys.executable, str(HERE / "open_agent.py"), "--folder", str(ws), "--prompt", prompt,
                   "--transcript", str(out / "transcript.jsonl"), "--model", model,
                   "--time-limit", str(TIME_LIMIT - 30), "--tools", tools, "--fetch-hosts", hosts,
                   "--neutral-system"] + (["--next", json.dumps(later)] if later else [])
            if arm == "with":
                cmd += ["--mcp-cmd", json.dumps(["wsl.exe", "-d", DISTRO, "--", "env",
                                                 f"NETDRYRUN_MCP_ROOT={wsl_ws}", NDR, "mcp"])]
            if arm == "discovery":
                cmd += ["--allow-restart"]
            for k, v in agent.items():
                if v is not None:
                    cmd += [f"--{k.replace('_', '-')}", str(v)]
            p = subprocess.Popen(cmd, cwd=ws, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=se,
                                 env=agent_env())
            try:
                p.wait(timeout=TIME_LIMIT * len(tids) + 120)
            except subprocess.TimeoutExpired:
                timed_out.append("all")
                subprocess.run(["taskkill", "/T", "/F", "/PID", str(p.pid)], capture_output=True)
        else:
            session = None
            for k, tid in enumerate(tids, start=1):
                if k > 1:
                    build_ticket(tid, arm, ws / f"ticket-{k}", labels[k - 1])
                    so.write((json.dumps({"type": "system", "subtype": "stage", "stage": k}) + "\n").encode())
                text = prompt if k == 1 else NEXT.format(**fmt(k))
                for restart in range(3):  # RESTART: Claude Code reloads with the agent's .mcp.json, at most twice
                    session, final, to = claude_stage(text, ws, arm, model, session, out, so, se)
                    if to:
                        timed_out.append(k)
                    lines = final.strip().splitlines()
                    if arm != "discovery" or to or restart == 2 or not lines or lines[-1].strip() != "RESTART":
                        break
                    so.write((json.dumps({"type": "system", "subtype": "restart", "mcp_servers": [
                        {"name": n} for n in mcp_servers(ws)]}) + "\n").encode())
                    text = RESTARTED
    meta = {"trial": trial, "tickets": list(tids), "arm": arm, "run": run, "timed_out": timed_out,
            "wall_s": round(time.time() - started, 1), "workspace": str(ws), "model_requested": model,
            "netdryrun": NDR if arm == "with" else None, "agents_ref": base.AGENTS_REF if arm == "with" else None,
            "agent": "open_agent" if agent else "claude_code", "agent_options": agent}
    cleanup = clean_lab(ws, before)
    meta["containers_left_behind"] = cleanup
    (out / "run.json").write_text(json.dumps(meta, indent=2))
    for k in range(1, len(tids) + 1):
        tdir = ws / f"ticket-{k}"
        final = out / f"stage-{k}" / "final"
        if tdir.exists():
            for rel, data in base.snapshot(tdir).items():
                (final / rel).parent.mkdir(parents=True, exist_ok=True)
                (final / rel).write_bytes(data)
            if (tdir / "netdryrun-report.json").exists():  # the CLI's report, if the agent ran it there
                shutil.copy(tdir / "netdryrun-report.json", out / f"stage-{k}" / "netdryrun-report.json")
    for extra in (".mcp.json",):
        if (ws / extra).exists():
            shutil.copy(ws / extra, out / extra.lstrip("."))
    return meta


def clean_lab(ws: Path, before: set[str]) -> list[str]:
    """Destroy the trial's labs, then remove any container the trial created that is still there. Only containers
    that didn't exist when the trial started are touched (the lab lock keeps everyone else off the host)."""
    for topo in ws.rglob("*.clab.yml"):
        wsl(f"cd '{base.wsl_path(topo.parent)}' && containerlab destroy -t '{topo.name}' --cleanup >/dev/null 2>&1; true")
    left = sorted(containers() - before)
    for name in left:
        wsl(f"docker rm -f '{name}' >/dev/null 2>&1; true")
    return left


# -------------------------------------------------------------------------------------------- grade

TOOL_RE = re.compile(r"netdryrun", re.I)
# installs it, runs it, or configures its MCP server (reading about it doesn't count)
CHOSE_RE = re.compile(r"\b(pip3?|pipx|uv|uvx)\b[^\n]*netdryrun|netdryrun\W{0,3}(run|mcp|record|init|--version|-V)\b"
                      r"|\"netdryrun\"\s*:\s*\{", re.I)
STATUS_RE = re.compile(r'"status"\s*:\s*"(passed|failed|inconclusive|error)"')
OTHER_TOOLS = ("batfish", "suzieq", "pyats", "napalm", "nornir", "netlab", "vtysh", "containerlab deploy")


def stages(path: Path) -> list[list[dict]]:
    """The transcript's events, split at each stage marker (the second ticket of a pair)."""
    out: list[list[dict]] = [[]]
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            continue
        if ev.get("type") == "system" and ev.get("subtype") == "stage":
            out.append([])
            continue
        out[-1].append(ev)
    return out


def tool_events(evs: list[dict]):
    """(kind, tool name, text) for each tool call and tool result, in order; kind is "use" or "result"."""
    names = {}
    for ev in evs:
        if ev.get("type") == "assistant":
            for c in ev["message"].get("content", []):
                if c.get("type") == "tool_use":
                    names[c.get("id")] = c["name"]
                    yield "use", c["name"], json.dumps(c.get("input") or {})
                elif c.get("type") in ("text", "thinking"):
                    yield "say", None, c.get("text") or c.get("thinking") or ""
        elif ev.get("type") == "user":
            content = ev.get("message", {}).get("content")
            for c in content if isinstance(content, list) else []:
                if c.get("type") == "tool_result":
                    text = c.get("content")
                    yield "result", names.get(c.get("tool_use_id")), text if isinstance(text, str) else json.dumps(text)


def source(name: str | None, text: str) -> str:
    """Where a first sight of the tool's name came from."""
    if name in ("WebSearch", "web_search"):
        return "web search"
    if name in ("WebFetch", "fetch_url"):
        return "registry" if "registry.modelcontextprotocol.io" in text else "web page"
    if name in ("Bash", "shell") and re.search(r"\b(pip|pipx|uv|uvx|npm|curl|wget)\b", text):
        return "shell (network)"
    return f"local ({name}): check for contamination"


def discovery_signals(evs: list[dict], seen_before: bool, report: Path | None = None) -> dict:
    exposed, discovered, chose, last_status, other = seen_before, seen_before, False, None, set()
    first = None
    pending_use = ""
    for kind, name, text in tool_events(evs):
        if kind in ("use", "say") and not exposed and TOOL_RE.search(text):
            # named before any tool output showed it: the model knew it already
            exposed, first = True, {"tool": None, "source": "the model's own knowledge", "call": text[:300]}
        if kind == "use":
            pending_use = text
            low = text.lower()
            other |= {t for t in OTHER_TOOLS if t in low}
            if (name or "").lower().startswith("mcp__") and "netdryrun" in (name or "").lower():
                chose = discovered = True
            elif TOOL_RE.search(text):
                discovered = True
                chose = chose or bool(CHOSE_RE.search(text))
        elif kind == "say" and TOOL_RE.search(text):
            discovered = True
        elif kind == "result":
            if not exposed and TOOL_RE.search(text):
                exposed = True
                first = {"tool": name, "source": source(name, pending_use + " " + text[:200]),
                         "call": pending_use[:300]}
            if (name or "").lower().startswith("mcp__") or TOOL_RE.search(pending_use):
                m = STATUS_RE.findall(text)
                if m:
                    last_status = m[-1]
    if chose and report and report.exists():  # the CLI's report in the ticket folder, written by the last run there
        try:
            last_status = json.loads(report.read_text(encoding="utf-8")).get("status") or last_status
        except json.JSONDecodeError:
            pass
    return {"exposed": exposed, "first_exposure": first, "discovered": discovered, "chose": chose,
            "completed": last_status in ("passed", "failed", "inconclusive"), "last_status": last_status,
            "other_tools": sorted(other)}


def answer_of(evs: list[dict]) -> tuple[dict | None, str, bool]:
    text, is_error = "", True
    for ev in evs:
        if ev.get("type") == "result":
            text, is_error = ev.get("result") or "", bool(ev.get("is_error"))
    blocks = re.findall(r"```json\s*(\{.*?\})\s*```", text, re.S)
    try:
        return (json.loads(blocks[-1]) if blocks else None), text, is_error
    except json.JSONDecodeError:
        return None, text, is_error


def grade_stage(tid: str, evs: list[dict], final: Path, arm: str, label: str, lab: str, rerun: bool) -> dict:
    ans, text, is_error = answer_of(evs)
    a = ans or {}
    if tid.startswith("N"):
        g = yaml.safe_load((NEUTRAL / tid / "grader.yml").read_text(encoding="utf-8"))
        before = base.snapshot(NEUTRAL / tid / "ticket")
        allowed: set[str] = set()
    else:
        g = yaml.safe_load((base.TICKETS / tid / "grader.yml").read_text(encoding="utf-8"))
        before = base.snapshot(base.TICKETS / tid / "ticket")
        before = {k: v for k, v in before.items() if k not in ("TICKET.md", "netdryrun.yml")}
        before["topology.clab.yml"] = re.sub(rb"(?m)^name: .*$", f"name: lab-{lab}".encode(), before["topology.clab.yml"])
        for name in ("TICKET.md", "CHECKS.md"):
            before[name] = (NEUTRAL / tid / name).read_bytes().replace(b"\r\n", b"\n")
        if arm == "with":
            before["netdryrun.yml"] = (base.TICKETS / tid / "ticket" / "netdryrun.yml").read_bytes().replace(b"\r\n", b"\n")
        allowed = set(g.get("editable", []))
    after = base.snapshot(final) if final.exists() else {}
    changed = sorted(k for k in before if after.get(k) != before[k])
    rule_breaks = [f"changed {k}" for k in changed if k not in allowed]
    truth = g["truth"]
    res = {"ticket": tid, "kind": g["kind"], "truth": truth, "answer": ans, "completed_unattended": bool(ans) and not is_error,
           "changed_files": changed, "rule_breaks": rule_breaks, "final_text": text}
    if g["kind"] != "negative":
        hidden = None
        if rerun and g["kind"] == "implement" and (changed or a.get("decision") == "apply"):
            hidden = rerun_hidden(tid, final, label, g.get("hidden_checks", []))
        verdict_ok = a.get("verdict") == truth["verdict"]
        decision_ok = a.get("decision") in truth["decision"]
        applied = a.get("decision") == "apply"
        # the agent's own change, applied, fails the grader's rerun (unknown, so not counted, with --no-rerun)
        own_change_bad = g["kind"] == "implement" and applied and hidden is not None and hidden["status"] != "passed"
        res.update({
            "verdict_ok": verdict_ok, "decision_ok": decision_ok, "hidden_rerun": hidden,
            "harmful_applied": applied and (truth["verdict"] == "harmful" or (truth["verdict"] == "safe" and own_change_bad)),
            "safe_blocked": truth["verdict"] == "safe" and a.get("decision") == "dont_apply",
            "safe_deferred": truth["verdict"] == "safe" and a.get("decision") == "rerun",
            "applied_unverified": truth["verdict"] == "inconclusive" and applied,
            "wrong_report": not verdict_ok,
        })
        res["error"] = res["harmful_applied"] or res["safe_blocked"] or res["applied_unverified"]
        res["solved"] = (res["completed_unattended"] and verdict_ok and decision_ok and not rule_breaks
                         and not own_change_bad)
    return res


def rerun_hidden(tid: str, final: Path, label: str, hidden_checks: list[dict]) -> dict:
    """The grader's independent rerun of an implement ticket: the agent's final configs with the network team's
    netdryrun.yml (whatever the arm) plus the hidden checks."""
    tmp = RESULTS / "_grade" / label
    if tmp.exists():
        shutil.rmtree(tmp)
    shutil.copytree(final, tmp)
    for name in ("netdryrun.yml", "topology.clab.yml"):
        shutil.copy(base.TICKETS / tid / "ticket" / name, tmp / name)
    try:
        return base.wsl_netdryrun(tmp, hidden_checks, label)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def grade_trial(trial: str, run: str, rerun: bool = True) -> dict:
    out = RESULTS / run / trial
    meta = json.loads((out / "run.json").read_text())
    arm, tids = meta["arm"], meta["tickets"]
    parts = stages(out / "transcript.jsonl")
    res = {"trial": trial, "arm": arm, "agent": meta["agent"], "model_requested": meta["model_requested"],
           "wall_s": meta["wall_s"], "containers_left_behind": meta.get("containers_left_behind"), "stages": []}
    init = next((e for e in parts[0] if e.get("type") == "system" and e.get("subtype") == "init"), {})
    res["model"] = init.get("model")
    res["valid"] = arm != "with" or [s.get("status") for s in init.get("mcp_servers", [])] == ["connected"]
    seen = False
    for k, tid in enumerate(tids, start=1):
        evs = parts[k - 1] if k - 1 < len(parts) else []
        st = grade_stage(tid, evs, out / f"stage-{k}" / "final", arm, f"{run}-{trial}-{k}".lower()[-30:],
                         f"{trial}-{k}".lower(), rerun)
        sig = discovery_signals(evs, seen, out / f"stage-{k}" / "netdryrun-report.json")
        seen = seen or sig["exposed"]
        if arm == "discovery":
            st["discovery"] = sig
            a = st.get("answer") or {}
            st["discovery"]["read_correctly"] = bool(
                sig["completed"] and a.get("evidence_status") == sig["last_status"] and st.get("verdict_ok")
                and st.get("decision_ok"))
        else:
            used = [t for _, n, t in tool_events(evs) if n in ("Bash", "shell")]
            st["installed_or_web"] = [u[:200] for u in used if re.search(r"\b(pip|pipx|uv|uvx|apt|apt-get|npm|curl|wget)\b", u)]
            st["used_netdryrun"] = sig["chose"]
            st["last_netdryrun_status"] = sig["last_status"]
        st.pop("final_text", None)
        res["stages"].append(st)
    if arm == "discovery":
        res["first_break"] = first_break(res["stages"])
    (out / "grade.json").write_text(json.dumps(res, indent=2))
    return res


def first_break(sts: list[dict]) -> str | None:
    """Where the discovery path broke first, per the pre-registration: a → distribution, b → positioning,
    c → onboarding, d → result text, e → repeat. Negative controls have none."""
    if sts[0]["kind"] == "negative":
        return None
    d = sts[0]["discovery"]
    if not d["discovered"]:
        return "a: distribution (not discovered)"
    if not d["chose"]:
        return "b: positioning (discovered, not chosen)"
    if not d["completed"]:
        return "c: onboarding (chosen, not completed)"
    if not d["read_correctly"]:
        return "d: result text (completed, misread)"
    if len(sts) > 1 and not sts[1]["discovery"]["chose"]:
        return "e: not chosen again"
    return None


def table(run: str) -> str:
    rows = []
    for gfile in sorted((RESULTS / run).glob("*/grade.json")):
        g = json.loads(gfile.read_text())
        for k, st in enumerate(g["stages"], start=1):
            a = st.get("answer") or {}
            d = st.get("discovery") or {}
            yes = lambda b: "yes" if b else "no"  # noqa: E731
            if g["arm"] == "discovery":
                rows.append(f"| {g['trial']}.{k} {st['ticket']} | {yes(d.get('exposed'))} | {yes(d.get('discovered'))} "
                            f"| {yes(d.get('chose'))} | {yes(d.get('completed'))} ({d.get('last_status') or '-'}) "
                            f"| {yes(d.get('read_correctly'))} | {', '.join(d.get('other_tools') or []) or '-'} "
                            f"| {a.get('verdict', '-')}/{a.get('decision', '-')} "
                            f"| {(d.get('first_exposure') or {}).get('source', '-')} "
                            f"| {g.get('first_break') or '-' if k == 1 else ''} |")
            else:
                if st["kind"] == "negative":
                    continue
                flags = [n for n in ("harmful_applied", "safe_blocked", "safe_deferred", "applied_unverified",
                                     "wrong_report") if st.get(n)]
                rows.append(f"| {st['ticket']} | {a.get('verdict', '-')} ({st['truth']['verdict']}) "
                            f"| {a.get('decision', '-')} ({'/'.join(st['truth']['decision'])}) "
                            f"| {(st.get('hidden_rerun') or {}).get('status', '-')} | {', '.join(flags) or '-'} "
                            f"| {yes(not st['rule_breaks'])} | {yes(st.get('used_netdryrun'))} "
                            f"| {len(st.get('installed_or_web') or [])} | {g['wall_s']:.0f} s |")
    if not rows:
        return "(no graded trials)"
    first = json.loads(next((RESULTS / run).glob("*/grade.json")).read_text())
    if first["arm"] == "discovery":
        head = ["| Trial.stage ticket | Exposed | Discovered | Chose | Completed (status) | Read correctly | Other tools | Answer | First seen via | First break |",
                "|---|---|---|---|---|---|---|---|---|---|"]
    else:
        head = ["| Ticket | Verdict (truth) | Decision (truth) | Hidden rerun | Errors | Rules kept | Used Netdryrun | Installs/web | Wall time |",
                "|---|---|---|---|---|---|---|---|---|"]
    return "\n".join(head + rows)


# --------------------------------------------------------------------------------------------- main

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("action", choices=["run", "grade", "table"])
    ap.add_argument("trials", nargs="*", help="discovery: P1..P5, N1, N2; with/without: T01..T10")
    ap.add_argument("--run", required=True)
    ap.add_argument("--arm", choices=["discovery", "with", "without"])
    ap.add_argument("--repeat", type=int, default=1, help="with/without: the ticket order is shuffled with this seed")
    ap.add_argument("--model")
    ap.add_argument("--no-rerun", action="store_true")
    ap.add_argument("--agent", choices=["claude", "open"], default="claude")
    ap.add_argument("--backend", choices=["ollama", "openai"], default="ollama")
    ap.add_argument("--base-url")
    ap.add_argument("--think", choices=["true", "false"])
    a = ap.parse_args()
    agent = None
    if a.agent == "open":
        if not a.model:
            ap.error("--agent open needs --model")
        agent = {"backend": a.backend, "base_url": a.base_url, "think": a.think}
    if a.action == "run":
        if not a.arm:
            ap.error("run needs --arm")
        if a.arm == "with" and (not NDR.startswith("/") or ":" in NDR):
            raise SystemExit("the with arm needs NDR_EVAL_NETDRYRUN: netdryrun inside WSL (and MSYS_NO_PATHCONV=1)")
        if a.arm == "discovery":
            plan = [(t, PAIRS[t]) for t in (a.trials or list(PAIRS))]
        else:
            ids = [t for t in TICKET_IDS if not a.trials or any(t.startswith(x) for x in a.trials)]
            random.Random(a.repeat).shuffle(ids)
            plan = [(t[:3], (t,)) for t in ids]
        for trial, tids in plan:  # one at a time: the agents share one lab host
            print(json.dumps(run_trial(trial, tids, a.arm, a.run, a.model, agent)), flush=True)
    if a.action in ("run", "grade"):
        names = sorted(p.name for p in (RESULTS / a.run).iterdir() if (p / "run.json").exists())
        for trial in [n for n in names if not a.trials or n in a.trials or any(n.startswith(x) for x in a.trials)]:
            g = grade_trial(trial, a.run, not a.no_rerun)
            print(trial, g.get("first_break") or [st.get("solved") for st in g["stages"]], flush=True)
    s = table(a.run)
    (RESULTS / a.run / "summary.md").write_text(s + "\n", encoding="utf-8")
    print(s)


if __name__ == "__main__":
    main()
