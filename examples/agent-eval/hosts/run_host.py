"""Run one stage of an open-source agent host (Goose, OpenHands, Cline) on the lab host, as the user labagent.

Runs inside WSL (Ubuntu-ndr) with the system Python; run_arms.py calls it with a JSON spec:

    python3 run_host.py SPEC.json

The spec: host, model, ollama (URL), home (the trial's own HOME, kept across its stages), cwd (the trial's
folder), prompt, session (the name or id from the previous stage, or null), time_limit (seconds), out (where to
write the stage's events, JSONL in the format run_arms.py grades). The host starts with a clean environment: no
Windows PATH, nothing that names the tool, and a HOME holding only the host's own settings. MCP servers the agent
wrote to .mcp.json in the folder are given to the host in its own format; servers it added through the host's
own commands stay in the host's settings in that HOME.
"""
from __future__ import annotations

import glob
import json
import os
import shlex
import subprocess
import sys
import time

HOSTS = "/opt/agent-hosts"
PATH = f"{HOSTS}/bin:{HOSTS}/node/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
SHELL_TOOLS = {"shell", "execute_command", "terminal", "execute_bash", "run_commands", "bash"}
FETCH_TOOLS = {"fetch", "web_fetch", "web_scrape", "fetch_web_content"}
SEARCH_TOOLS = {"web_search", "search_web"}


def servers(cwd: str) -> dict:
    try:
        with open(os.path.join(cwd, ".mcp.json")) as f:
            return json.load(f).get("mcpServers", {}) or {}
    except Exception:
        return {}


def norm(name: str, builtin: set[str]) -> str:
    """The grader's names: shell, fetch_url, web_search, mcp__<server>__<tool>; others as the host calls them."""
    low = name.lower()
    if low in SHELL_TOOLS:
        return "shell"
    if low in FETCH_TOOLS:
        return "fetch_url"
    if low in SEARCH_TOOLS:
        return "web_search"
    if "__" in name and name.split("__", 1)[0] not in builtin and not name.startswith("mcp__"):
        return "mcp__" + name
    return name


def ev_assistant(content: list) -> dict:
    return {"type": "assistant", "message": {"content": content}}


def ev_results(results: list) -> dict:
    return {"type": "user", "message": {"content": results}}


# ------------------------------------------------------------------------------------------------ goose

GOOSE_BUILTIN = {"developer", "extensionmanager", "apps", "todo", "chatrecall", "skills", "summon", "analyze",
                 "computercontroller", "memory", "tutorial", "autovisualiser", "platform", "code_execution"}


def goose(spec: dict, env: dict) -> tuple[list[str], callable]:
    env.update(GOOSE_PROVIDER="ollama", GOOSE_MODEL=spec["model"], OLLAMA_HOST=spec["ollama"], GOOSE_MODE="auto",
               GOOSE_DISABLE_KEYRING="1")
    name = spec["session"] or spec["name"]
    cmd = ["goose", "run", "--name", name, "--with-builtin", "developer", "--output-format", "stream-json",
           "-t", spec["prompt"]]
    if spec["session"]:
        cmd.insert(2, "--resume")
    for n, s in servers(spec["cwd"]).items():
        if s.get("command"):
            envs = " ".join(f"{k}={shlex.quote(str(v))}" for k, v in (s.get("env") or {}).items())
            cmd += ["--with-extension", f"{n}:{envs + ' ' if envs else ''}" + shlex.join([s["command"], *s.get("args", [])])]
        elif s.get("url"):
            cmd += ["--with-streamable-http-extension", s["url"]]

    def transcript(seen: int) -> tuple[list[dict], str, int]:
        p = subprocess.run(["goose", "session", "export", "--name", name, "--format", "json"], env=env,
                           capture_output=True, text=True)
        try:
            msgs = json.loads(p.stdout).get("conversation") or []
        except json.JSONDecodeError:
            return [], "", seen
        evs, final = [], ""
        names = {}
        for m in msgs[seen:]:
            content = []
            if m["role"] == "assistant":
                for c in m.get("content", []):
                    if c.get("type") == "text":
                        content.append({"type": "text", "text": c["text"]})
                        final = c["text"]
                    elif c.get("type") == "thinking":
                        content.append({"type": "thinking", "thinking": c.get("thinking", "")})
                    elif c.get("type") == "toolRequest":
                        call = (c.get("toolCall") or {}).get("value") or {}
                        names[c["id"]] = call.get("name", "?")
                        content.append({"type": "tool_use", "id": c["id"], "name": norm(call.get("name", "?"), GOOSE_BUILTIN),
                                        "host_name": call.get("name"), "input": call.get("arguments") or {}})
                if content:
                    evs.append(ev_assistant(content))
                    if any(c["type"] == "tool_use" for c in content):
                        final = ""
            elif m["role"] == "user":
                for c in m.get("content", []):
                    if c.get("type") == "toolResponse":
                        r = (c.get("toolResult") or {}).get("value") or (c.get("toolResult") or {}).get("error") or {}
                        text = "\n".join(x.get("text", "") for x in r.get("content", []) if isinstance(x, dict)) \
                            if isinstance(r, dict) else str(r)
                        content.append({"type": "tool_result", "tool_use_id": c["id"], "content": text})
                if content:
                    evs.append(ev_results(content))
        return evs, final, len(msgs)

    return cmd, transcript


def merge_servers(path: str, cwd: str) -> None:
    """Add the servers of .mcp.json to a host settings file in the mcpServers format, keeping the ones there."""
    try:
        cur = json.load(open(path))
    except Exception:
        cur = {}
    cur.setdefault("mcpServers", {}).update(servers(cwd))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    json.dump(cur, open(path, "w"), indent=2)


def text_of(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(text_of(c) for c in content)
    if isinstance(content, dict):
        if "text" in content and isinstance(content["text"], str):
            return content["text"]
        if "result" in content or "query" in content:
            return f"$ {content.get('query', '')}\n{text_of(content.get('result', content.get('error', '')))}"
        return json.dumps(content)
    return "" if content is None else str(content)


# -------------------------------------------------------------------------------------------- openhands

def unwrap(text: str) -> str:
    """OpenHands' final message is sometimes {"message": ..., "summary": ...}: the answer is the message."""
    try:
        d = json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return text
    return d["message"] if isinstance(d, dict) and isinstance(d.get("message"), str) else text


OPENHANDS_BUILTIN = {"terminal", "file_editor", "task_tracker", "task", "finish", "think", "invoke_skill", "browser", "glob", "grep"}


def openhands(spec: dict, env: dict) -> tuple[list[str], callable]:
    env.update(LLM_MODEL=f"ollama_chat/{spec['model']}", LLM_BASE_URL=spec["ollama"], LLM_API_KEY="ollama",
               OPENHANDS_SUPPRESS_BANNER="1")
    convs = os.path.join(spec["home"], ".openhands", "conversations")
    merge_servers(os.path.join(spec["home"], ".openhands", "mcp.json"), spec["cwd"])
    cmd = ["openhands", "--headless", "--json", "--override-with-envs", "-t", spec["prompt"]]
    if spec["session"]:
        cmd += ["--resume", spec["session"]]

    def transcript(seen: int) -> tuple[list[dict], str, int]:
        dirs = sorted(glob.glob(os.path.join(convs, "*")), key=os.path.getmtime)
        if not dirs:
            return [], "", seen
        conv = os.path.join(convs, (spec["session"] or "").replace("-", "")) if spec["session"] else dirs[-1]
        spec["_session"] = os.path.basename(conv)
        files = sorted(glob.glob(os.path.join(conv, "events", "event-*.json")))
        evs, final = [], ""
        for f in files[seen:]:
            e = json.load(open(f))
            kind = e.get("kind")
            if kind == "ActionEvent":
                content = []
                if e.get("reasoning_content"):
                    content.append({"type": "thinking", "thinking": e["reasoning_content"]})
                for t in e.get("thought") or []:
                    if t.get("text"):
                        content.append({"type": "text", "text": t["text"]})
                call = e.get("tool_call") or {}
                name = e.get("tool_name") or call.get("name") or "?"
                try:
                    args = json.loads(call.get("arguments") or "{}")
                except json.JSONDecodeError:
                    args = {"raw": call.get("arguments")}
                is_mcp = (e.get("action") or {}).get("kind", "").startswith("MCP") or name not in OPENHANDS_BUILTIN
                content.append({"type": "tool_use", "id": e.get("tool_call_id") or e["id"],
                                "name": ("mcp__" + name if is_mcp and not name.startswith("mcp__") else norm(name, OPENHANDS_BUILTIN)),
                                "host_name": name, "input": args})
                evs.append(ev_assistant(content))
                final = unwrap(args.get("message", "")) if name == "finish" else ""
            elif kind == "ObservationEvent" or kind == "AgentErrorEvent" or kind == "UserRejectObservation":
                obs = e.get("observation") or {}
                text = text_of(obs.get("content")) if obs else e.get("error", "")
                evs.append(ev_results([{"type": "tool_result", "tool_use_id": e.get("tool_call_id"), "content": text}]))
            elif kind == "MessageEvent" and e.get("source") == "agent":
                msg = e.get("llm_message") or {}
                final = unwrap(text_of(msg.get("content")))
                evs.append(ev_assistant([{"type": "text", "text": final}]))
        return evs, final, len(files)

    return cmd, transcript


# ------------------------------------------------------------------------------------------------ cline

CLINE_BUILTIN = {"run_commands", "read_files", "editor", "search_codebase", "fetch_web_content", "web_fetch",
                 "ask_question", "skills", "spawn_agent", "submit_and_exit", "apply_patch", "write_file"}


def cline(spec: dict, env: dict) -> tuple[list[str], callable]:
    data = os.path.join(spec["home"], ".cline", "data")
    merge_servers(os.path.join(data, "settings", "cline_mcp_settings.json"), spec["cwd"])
    if not os.path.exists(os.path.join(data, "settings", "providers.json")):
        # Cline's own ollama provider takes no base URL; Ollama's OpenAI-compatible endpoint, same server and model
        subprocess.run(["cline", "auth", "-p", "openai", "-k", "ollama", "-b", spec["ollama"] + "/v1",
                        "-m", spec["model"]], env=env, cwd=spec["cwd"], capture_output=True, timeout=120)
    cmd = ["cline", "--json", "-P", "openai", "-m", spec["model"], "-c", spec["cwd"],
           "-t", str(max(60, spec["time_limit"] - 30))]
    if spec["session"]:
        cmd += ["--id", spec["session"]]
    cmd.append(spec["prompt"])

    def transcript(seen: int) -> tuple[list[dict], str, int]:
        paths = glob.glob(os.path.join(data, "sessions", "*", "*.messages.json"))
        if spec["session"]:
            paths = [p for p in paths if os.path.basename(p).startswith(spec["session"])] or paths
        if not paths:
            return [], "", seen
        path = max(paths, key=os.path.getmtime)
        spec["_session"] = os.path.basename(path).split(".")[0]
        msgs = json.load(open(path)).get("messages", [])
        evs, final = [], ""
        for m in msgs[seen:]:
            content = []
            for c in m.get("content", []) if isinstance(m.get("content"), list) else []:
                if c.get("type") == "text" and m["role"] == "assistant":
                    content.append({"type": "text", "text": c["text"]})
                    final = c["text"]
                elif c.get("type") == "thinking":
                    content.append({"type": "thinking", "thinking": c.get("thinking", "")})
                elif c.get("type") == "tool_use":
                    content.append({"type": "tool_use", "id": c["id"], "name": norm(c["name"], CLINE_BUILTIN),
                                    "host_name": c["name"], "input": c.get("input") or {}})
                    final = ""
                elif c.get("type") == "tool_result":
                    content.append({"type": "tool_result", "tool_use_id": c.get("tool_use_id"),
                                    "content": text_of(c.get("content"))})
            if content:
                evs.append(ev_assistant(content) if m["role"] == "assistant" else ev_results(content))
        return evs, final, len(msgs)

    return cmd, transcript


# --------------------------------------------------------------------------------------------- main

def main() -> None:
    spec = json.load(open(sys.argv[1]))
    os.makedirs(spec["home"], exist_ok=True)
    env = {"HOME": spec["home"], "PATH": PATH, "LANG": "C.UTF-8", "TERM": "dumb", "USER": "labagent",
           "LOGNAME": "labagent", "SHELL": "/bin/bash"}
    cmd, transcript = {"goose": goose, "openhands": openhands, "cline": cline}[spec["host"]](spec, env)
    state_file = os.path.join(spec["home"], ".stage-state.json")
    state = json.load(open(state_file)) if os.path.exists(state_file) else {"seen": 0}
    if not spec["session"]:  # a new session: its messages start at 0
        state["seen"] = 0
    start = time.time()
    with open(spec["raw"], "ab") as raw:
        p = subprocess.Popen(cmd, cwd=spec["cwd"], env=env, stdin=subprocess.DEVNULL, stdout=raw, stderr=raw,
                             start_new_session=True)
        timed_out = False
        try:
            p.wait(timeout=spec["time_limit"])
        except subprocess.TimeoutExpired:
            timed_out = True
            os.killpg(p.pid, 9)
            p.wait()
    evs, final, seen = transcript(state["seen"])
    session = spec.get("_session") or spec["session"] or spec["name"]
    state.update(seen=seen, session=session)
    json.dump(state, open(state_file, "w"))
    head = {"type": "system", "subtype": "init", "host": spec["host"], "model": spec["model"],
            "session_id": session, "mcp_servers": [{"name": n} for n in servers(spec["cwd"])]}
    tail = {"type": "result", "result": final, "is_error": timed_out or p.returncode != 0, "timed_out": timed_out,
            "returncode": p.returncode, "duration_ms": int((time.time() - start) * 1000)}
    with open(spec["out"], "w") as f:
        for ev in [head, *evs, tail]:
            f.write(json.dumps(ev) + "\n")


if __name__ == "__main__":
    main()
