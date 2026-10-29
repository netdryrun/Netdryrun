"""A plain tool-calling agent for the eval, for models that aren't Claude Code: Ollama, or any OpenAI-compatible API.

It gets what the Claude Code agent gets: the same prompt, file tools confined to the ticket folder, fetches limited
to netdryrun.com, the Netdryrun MCP server's tools, no shell, no human. It writes its transcript in Claude Code's
stream-json shape, so run_eval.py grades both the same way.

    python open_agent.py --folder DIR --prompt TEXT --transcript OUT.jsonl --backend ollama --model qwen3:4b \
        --mcp-cmd '["wsl.exe", "-d", "Ubuntu-ndr", "--", "/path/to/netdryrun", "mcp"]'

For run_arms.py (the unprompted-discovery and with/without evals) it can also have a shell (Git Bash, like Claude
Code's on Windows: --tools files,shell,...), web search (--tools ...,web_search), fetches from any host
(--fetch-hosts '*'), no MCP server at the start (omit --mcp-cmd), MCP servers the agent adds itself (it writes
.mcp.json and ends a turn with RESTART), and more than one ticket in the same session (--next).

Differences from the Claude Code runs, all on purpose and listed in RESULTS.md: a one-line system message saying it
works alone with tools (Claude Code has its own), and long tool results are cut to --max-result characters.
"""
from __future__ import annotations

import argparse
import html
import json
import os
import queue
import re
import shutil
import subprocess
import threading
import time
import urllib.parse
import urllib.request
from pathlib import Path

SYSTEM = ("You are an autonomous agent working alone. Use the tools to read files, edit files and run Netdryrun. "
          "Keep calling tools until the task is done, then give your final answer.")
# run_arms.py: the same line without the tool's name (the discovery and without arms never name it)
SYSTEM_NEUTRAL = ("You are an autonomous agent working alone. Use the tools to do the task. "
                  "Keep calling tools until the task is done, then give your final answer.")
RESTARTED = "The session was restarted with the MCP servers in .mcp.json loaded. Continue the ticket."
FETCH_HOSTS = {"netdryrun.com", "www.netdryrun.com"}
BASH = os.environ.get("NDR_EVAL_BASH") or r"C:\Program Files\Git\bin\bash.exe"


class MCP:
    """A minimal MCP client over stdio (newline-delimited JSON-RPC)."""

    def __init__(self, cmd: list[str], env: dict | None = None, cwd: str | None = None):
        cmd = [shutil.which(cmd[0]) or cmd[0]] + cmd[1:]  # npx, uvx and the like are .cmd shims on Windows
        self.p = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                  env=dict(os.environ, **(env or {})), cwd=cwd)
        self.q: queue.Queue = queue.Queue()
        self.next_id = 0
        threading.Thread(target=self._read, daemon=True).start()

    def _read(self):
        for line in self.p.stdout:
            try:
                self.q.put(json.loads(line))
            except json.JSONDecodeError:
                continue
        self.q.put(None)

    def _send(self, msg: dict):
        self.p.stdin.write((json.dumps(msg) + "\n").encode())
        self.p.stdin.flush()

    def request(self, method: str, params: dict, timeout: float) -> dict:
        self.next_id += 1
        rid = self.next_id
        self._send({"jsonrpc": "2.0", "id": rid, "method": method, "params": params})
        deadline = time.time() + timeout
        while True:
            msg = self.q.get(timeout=max(1, deadline - time.time()))
            if msg is None:
                raise RuntimeError("MCP server exited")
            if msg.get("id") == rid:
                if "error" in msg:
                    raise RuntimeError(json.dumps(msg["error"]))
                return msg["result"]

    def start(self) -> list[dict]:
        self.request("initialize", {"protocolVersion": "2025-06-18", "capabilities": {},
                                    "clientInfo": {"name": "ndr-open-agent", "version": "1"}}, 60)
        self._send({"jsonrpc": "2.0", "method": "notifications/initialized"})
        return self.request("tools/list", {}, 60)["tools"]

    def close(self):
        try:
            self.p.stdin.close()
            self.p.wait(timeout=10)
        except Exception:
            self.p.kill()


def local_tools(groups: set[str], any_host: bool) -> list[dict]:
    def fn(name, desc, props, req):
        return {"type": "function", "function": {"name": name, "description": desc, "parameters": {
            "type": "object", "properties": props, "required": req}}}
    s = {"type": "string"}
    tools = []
    if "files" in groups:
        tools += [
            fn("list_files", "List every file in the current folder (relative paths).", {}, []),
            fn("read_file", "Read a text file in the current folder.", {"path": s}, ["path"]),
            fn("write_file", "Create or overwrite a text file in the current folder.", {"path": s, "content": s}, ["path", "content"]),
            fn("edit_file", "Replace one exact occurrence of old_text with new_text in a file in the current folder.",
               {"path": s, "old_text": s, "new_text": s}, ["path", "old_text", "new_text"]),
        ]
    if "shell" in groups:
        tools.append(fn("shell", "Run a command in a bash shell (Git Bash on Windows) in the current folder and "
                        "return its output and exit code. Each call starts a new shell; the time limit is 10 minutes.",
                        {"command": s}, ["command"]))
    if "web_search" in groups:
        tools.append(fn("web_search", "Search the web. Returns titles, URLs and snippets of the top results.",
                        {"query": s}, ["query"]))
    if "fetch" in groups:
        tools.append(fn("fetch_url", "Fetch a web page as text." if any_host else "Fetch a page on netdryrun.com as text.",
                        {"url": s}, ["url"]))
    return tools


def page_text(page: str) -> str:
    page = re.sub(r"(?s)<(script|style|nav|header|footer)\b.*?</\1>", " ", page)
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", page))).strip()


def web_search(query: str) -> str:
    """DuckDuckGo Lite (no key; its HTML endpoint answers bots with a challenge). Claude Code's WebSearch is a
    different engine: stated in the pre-registration."""
    req = urllib.request.Request("https://lite.duckduckgo.com/lite/", urllib.parse.urlencode({"q": query}).encode(),
                                 {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
    with urllib.request.urlopen(req, timeout=30) as r:
        page = r.read().decode("utf-8", "replace")
    out = []
    for m in re.finditer(r"""(?s)<a[^>]+href="([^"]+)"[^>]*class='result-link'>(.*?)</a>(.*?)(?=class='result-link'|$)""",
                         page):
        snippet = re.search(r"(?s)class='result-snippet'>(.*?)</td>", m.group(3))
        out.append(f"{page_text(m.group(2))}\n{html.unescape(m.group(1))}\n"
                   f"{page_text(snippet.group(1)) if snippet else ''}")
        if len(out) == 10:
            break
    return "\n\n".join(out) or "No results."


class Agent:
    def __init__(self, a: argparse.Namespace):
        self.a = a
        self.folder = Path(a.folder).resolve()
        self.out = open(a.transcript, "w", encoding="utf-8")
        self.groups = set(a.tools.split(","))
        self.any_host = a.fetch_hosts == "*"
        self.servers: dict[str, MCP] = {}
        self.mcp_names: dict[str, tuple[str, str]] = {}  # the tool name the model sees -> (server, tool)
        self.mcp_tools: list[dict] = []

    def emit(self, ev: dict):
        self.out.write(json.dumps(ev) + "\n")
        self.out.flush()

    def inside(self, rel: str) -> Path:
        p = (self.folder / rel).resolve()
        if p != self.folder and self.folder not in p.parents:
            raise ValueError(f"{rel} is outside the current folder")
        return p

    def run_local(self, name: str, args: dict) -> str:
        if name == "list_files" and "files" in self.groups:
            return "\n".join(sorted(f.relative_to(self.folder).as_posix() for f in self.folder.rglob("*")
                                    if f.is_file() and not f.relative_to(self.folder).as_posix().startswith("clab-")))
        if name == "read_file" and "files" in self.groups:
            return self.inside(args["path"]).read_text(encoding="utf-8", errors="replace")
        if name == "write_file" and "files" in self.groups:
            p = self.inside(args["path"])
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(args["content"], encoding="utf-8", newline="\n")
            return f"wrote {args['path']}"
        if name == "edit_file" and "files" in self.groups:
            p = self.inside(args["path"])
            text = p.read_text(encoding="utf-8")
            n = text.count(args["old_text"])
            if n != 1:
                raise ValueError(f"old_text found {n} times in {args['path']}; it must be found exactly once")
            p.write_text(text.replace(args["old_text"], args["new_text"]), encoding="utf-8", newline="\n")
            return f"edited {args['path']}"
        if name == "fetch_url" and "fetch" in self.groups:
            u = urllib.parse.urlparse(args["url"])
            if self.any_host:
                if u.scheme not in ("http", "https"):
                    raise ValueError("only http and https URLs may be fetched")
            elif u.scheme != "https" or u.hostname not in FETCH_HOSTS:
                raise ValueError("only https://netdryrun.com pages may be fetched")
            agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64)" if self.any_host else "ndr-eval"
            with urllib.request.urlopen(urllib.request.Request(args["url"], headers={"User-Agent": agent}),
                                        timeout=30) as r:
                page = r.read().decode("utf-8", "replace")
            return page_text(page) if "<" in page[:1000] else page
        if name == "web_search" and "web_search" in self.groups:
            return web_search(args["query"])
        if name == "shell" and "shell" in self.groups:
            try:
                p = subprocess.run([BASH, "-c", args["command"]], cwd=self.folder, capture_output=True,
                                   timeout=600, stdin=subprocess.DEVNULL)
            except subprocess.TimeoutExpired:
                return "[stopped after 10 minutes]"
            return (p.stdout + p.stderr).decode("utf-8", "replace") + f"\n[exit code {p.returncode}]"
        raise ValueError(f"unknown tool {name}")

    def add_server(self, name: str, cmd: list[str], env: dict | None = None) -> str:
        """Start one MCP server and expose its tools as mcp__<name>__<tool>; returns "connected" or "failed"."""
        try:
            srv = MCP(cmd, env, str(self.folder))
            tools = srv.start()
        except Exception as e:  # the run is graded invalid (or, for a server the agent added, a setup failure)
            self.emit({"type": "system", "subtype": "mcp_error", "server": name, "error": str(e)})
            return "failed"
        self.servers[name] = srv
        for t in tools:
            full = f"mcp__{name}__{t['name']}"
            self.mcp_names[full] = (name, t["name"])
            self.mcp_tools.append({"type": "function", "function": {
                "name": full, "description": t.get("description", ""),
                "parameters": t.get("inputSchema") or {"type": "object", "properties": {}}}})
        return "connected"

    def load_mcp_json(self) -> list[dict]:
        """RESTART: (re)load the servers in the folder's .mcp.json, as a restarted Claude Code would."""
        for srv in self.servers.values():
            srv.close()
        self.servers, self.mcp_names, self.mcp_tools = {}, {}, []
        try:
            conf = json.loads((self.folder / ".mcp.json").read_text(encoding="utf-8")).get("mcpServers", {})
        except Exception as e:
            return [{"name": ".mcp.json", "status": f"unreadable: {e}"}]
        return [{"name": n, "status": self.add_server(n, [c.get("command", "")] + list(c.get("args", [])),
                                                      c.get("env"))} for n, c in conf.items()]

    def chat(self, messages: list[dict], tools: list[dict]) -> dict:
        """One model turn: {"content", "thinking", "tool_calls": [{"id", "name", "arguments"}]}."""
        a = self.a
        if a.backend == "ollama":
            body = {"model": a.model, "messages": messages, "tools": tools, "stream": False, "keep_alive": "30m",
                    "options": {"num_ctx": a.num_ctx, "temperature": a.temperature}}
            if a.think is not None:
                body["think"] = a.think
            url, headers = a.base_url.rstrip("/") + "/api/chat", {}
        else:
            body = {"model": a.model, "messages": messages, "tools": tools, "temperature": a.temperature}
            url = a.base_url.rstrip("/") + "/chat/completions"
            headers = {"Authorization": f"Bearer {os.environ[a.api_key_env]}"}
        req = urllib.request.Request(url, json.dumps(body).encode(), {"Content-Type": "application/json", **headers})
        with urllib.request.urlopen(req, timeout=a.turn_timeout) as r:
            data = json.loads(r.read())
        msg = data["message"] if a.backend == "ollama" else data["choices"][0]["message"]
        calls = []
        for i, tc in enumerate(msg.get("tool_calls") or []):
            f = tc["function"]
            args = f.get("arguments") or {}
            if isinstance(args, str):
                try:
                    args = json.loads(args or "{}")
                except json.JSONDecodeError:
                    args = {"_unparsed": args}
            calls.append({"id": tc.get("id") or f"call_{i}", "name": f["name"], "arguments": args})
        content = msg.get("content") or ""
        thinking = msg.get("thinking") or msg.get("reasoning_content") or ""
        m = re.match(r"(?s)\s*<think>(.*?)</think>\s*(.*)", content)
        if m:
            thinking, content = (thinking + m.group(1)).strip(), m.group(2)
        return {"content": content, "thinking": thinking, "tool_calls": calls, "raw": msg}

    def run(self) -> int:
        a = self.a
        status = self.add_server("netdryrun", json.loads(a.mcp_cmd)) if a.mcp_cmd else None
        tools = lambda: local_tools(self.groups, self.any_host) + self.mcp_tools  # noqa: E731
        self.emit({"type": "system", "subtype": "init", "model": a.model, "agent": f"open_agent/{a.backend}",
                   "mcp_servers": [{"name": "netdryrun", "status": status}] if a.mcp_cmd else [],
                   "tools": [t["function"]["name"] for t in tools()]})
        stages = [{"prompt": a.prompt}] + (json.loads(a.next) if a.next else [])
        messages = [{"role": "system", "content": SYSTEM_NEUTRAL if a.neutral_system else SYSTEM}]
        try:
            for n, stage in enumerate(stages):
                if n:  # the next ticket arrives only after the previous one is answered
                    if stage.get("copy_from"):
                        shutil.copytree(stage["copy_from"], self.folder / stage["copy_to"])
                    self.emit({"type": "system", "subtype": "stage", "stage": n + 1})
                messages.append({"role": "user", "content": stage["prompt"]})
                self.run_stage(messages, tools)
        finally:
            for srv in self.servers.values():
                srv.close()
        return 0

    def run_stage(self, messages: list[dict], tools) -> None:
        """One ticket: turns until a final answer (a RESTART reloads .mcp.json and goes on), then a result event."""
        a = self.a
        started = time.time()
        final, is_error, turns, restarts = "", False, 0, 0
        try:
            while turns < a.max_turns and time.time() - started < a.time_limit:
                turns += 1
                r = self.chat(messages, tools())
                content = [{"type": "thinking", "thinking": r["thinking"]}] if r["thinking"] else []
                content += [{"type": "text", "text": r["content"]}] if r["content"] else []
                content += [{"type": "tool_use", "id": c["id"], "name": c["name"], "input": c["arguments"]}
                            for c in r["tool_calls"]]
                self.emit({"type": "assistant", "message": {"content": content}})
                am = {"role": "assistant", "content": r["content"]}
                if r["tool_calls"]:
                    am["tool_calls"] = [{"id": c["id"], "type": "function", "function": {
                        "name": c["name"], "arguments": c["arguments"] if a.backend == "ollama" else json.dumps(c["arguments"])}}
                        for c in r["tool_calls"]]
                messages.append(am)
                if not r["tool_calls"]:
                    lines = r["content"].strip().splitlines()
                    if a.allow_restart and lines and lines[-1].strip() == "RESTART" and restarts < 2:
                        restarts += 1
                        self.emit({"type": "system", "subtype": "restart", "mcp_servers": self.load_mcp_json()})
                        messages.append({"role": "user", "content": RESTARTED})
                        continue
                    final = r["content"]
                    break
                for c in r["tool_calls"]:
                    err = False
                    try:
                        if c["name"] in self.mcp_names:
                            server, tool = self.mcp_names[c["name"]]
                            res = self.servers[server].request("tools/call", {"name": tool, "arguments": c["arguments"]},
                                                               a.tool_timeout)
                            text = "\n".join(x.get("text", json.dumps(x)) for x in res.get("content", []))
                            err = bool(res.get("isError"))
                        else:
                            text = self.run_local(c["name"], c["arguments"])
                    except Exception as e:
                        text, err = f"Error: {e}", True
                    if len(text) > a.max_result:
                        text = text[:a.max_result] + f"\n[cut: {len(text) - a.max_result} more characters]"
                    self.emit({"type": "user", "message": {"content": [
                        {"type": "tool_result", "tool_use_id": c["id"], "content": text, "is_error": err}]}})
                    tm = {"role": "tool", "content": text, "tool_call_id": c["id"]}
                    if a.backend == "ollama":
                        tm["tool_name"] = c["name"]
                    messages.append(tm)
            else:
                is_error = True
                final = final or f"[stopped: {'turn limit' if turns >= a.max_turns else 'time limit'}]"
        except Exception as e:
            is_error, final = True, f"[agent error: {e}]"
        self.emit({"type": "result", "result": final, "num_turns": turns, "is_error": is_error,
                   "duration_ms": int((time.time() - started) * 1000), "total_cost_usd": 0 if a.backend == "ollama" else None})


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--folder", required=True)
    ap.add_argument("--prompt", required=True)
    ap.add_argument("--transcript", required=True)
    ap.add_argument("--mcp-cmd", help="JSON list: the command that starts `netdryrun mcp` (omit for no server)")
    ap.add_argument("--tools", default="files,fetch", help="comma list of: files, shell, web_search, fetch")
    ap.add_argument("--fetch-hosts", default="netdryrun.com", help="netdryrun.com, or * for any host")
    ap.add_argument("--allow-restart", action="store_true", help="a final answer ending in RESTART loads .mcp.json")
    ap.add_argument("--neutral-system", action="store_true", help="the system line without the tool's name")
    ap.add_argument("--next", help='JSON list of later tickets: [{"prompt", "copy_from", "copy_to"}]')
    ap.add_argument("--backend", choices=["ollama", "openai"], default="ollama")
    ap.add_argument("--base-url", default="http://127.0.0.1:11434")
    ap.add_argument("--api-key-env", default="OPENAI_API_KEY", help="openai backend: the variable holding the key")
    ap.add_argument("--model", required=True)
    ap.add_argument("--think", type=lambda s: s.lower() == "true", default=None, help="ollama: true or false")
    ap.add_argument("--num-ctx", type=int, default=16384)
    ap.add_argument("--temperature", type=float, default=0.2)
    ap.add_argument("--max-turns", type=int, default=60)
    ap.add_argument("--max-result", type=int, default=8000)
    ap.add_argument("--time-limit", type=float, default=1800)
    ap.add_argument("--turn-timeout", type=float, default=900)
    ap.add_argument("--tool-timeout", type=float, default=600)
    return Agent(ap.parse_args()).run()


if __name__ == "__main__":
    raise SystemExit(main())
