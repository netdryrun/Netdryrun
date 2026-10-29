"""A plain tool-calling agent for the eval, for models that aren't Claude Code: Ollama, or any OpenAI-compatible API.

It gets what the Claude Code agent gets: the same prompt, file tools confined to the ticket folder, fetches limited
to netdryrun.com, the Netdryrun MCP server's tools, no shell, no human. It writes its transcript in Claude Code's
stream-json shape, so run_eval.py grades both the same way.

    python open_agent.py --folder DIR --prompt TEXT --transcript OUT.jsonl --backend ollama --model qwen3:4b \
        --mcp-cmd '["wsl.exe", "-d", "Ubuntu-ndr", "--", "/path/to/netdryrun", "mcp"]'

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
import subprocess
import threading
import time
import urllib.parse
import urllib.request
from pathlib import Path

SYSTEM = ("You are an autonomous agent working alone. Use the tools to read files, edit files and run Netdryrun. "
          "Keep calling tools until the task is done, then give your final answer.")
FETCH_HOSTS = {"netdryrun.com", "www.netdryrun.com"}


class MCP:
    """A minimal MCP client over stdio (newline-delimited JSON-RPC)."""

    def __init__(self, cmd: list[str]):
        self.p = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
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


def local_tools() -> list[dict]:
    def fn(name, desc, props, req):
        return {"type": "function", "function": {"name": name, "description": desc, "parameters": {
            "type": "object", "properties": props, "required": req}}}
    s = {"type": "string"}
    return [
        fn("list_files", "List every file in the current folder (relative paths).", {}, []),
        fn("read_file", "Read a text file in the current folder.", {"path": s}, ["path"]),
        fn("write_file", "Create or overwrite a text file in the current folder.", {"path": s, "content": s}, ["path", "content"]),
        fn("edit_file", "Replace one exact occurrence of old_text with new_text in a file in the current folder.",
           {"path": s, "old_text": s, "new_text": s}, ["path", "old_text", "new_text"]),
        fn("fetch_url", "Fetch a page on netdryrun.com as text.", {"url": s}, ["url"]),
    ]


class Agent:
    def __init__(self, a: argparse.Namespace):
        self.a = a
        self.folder = Path(a.folder).resolve()
        self.out = open(a.transcript, "w", encoding="utf-8")

    def emit(self, ev: dict):
        self.out.write(json.dumps(ev) + "\n")
        self.out.flush()

    def inside(self, rel: str) -> Path:
        p = (self.folder / rel).resolve()
        if p != self.folder and self.folder not in p.parents:
            raise ValueError(f"{rel} is outside the current folder")
        return p

    def run_local(self, name: str, args: dict) -> str:
        if name == "list_files":
            return "\n".join(sorted(f.relative_to(self.folder).as_posix() for f in self.folder.rglob("*")
                                    if f.is_file() and not f.relative_to(self.folder).as_posix().startswith("clab-")))
        if name == "read_file":
            return self.inside(args["path"]).read_text(encoding="utf-8", errors="replace")
        if name == "write_file":
            p = self.inside(args["path"])
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(args["content"], encoding="utf-8", newline="\n")
            return f"wrote {args['path']}"
        if name == "edit_file":
            p = self.inside(args["path"])
            text = p.read_text(encoding="utf-8")
            n = text.count(args["old_text"])
            if n != 1:
                raise ValueError(f"old_text found {n} times in {args['path']}; it must be found exactly once")
            p.write_text(text.replace(args["old_text"], args["new_text"]), encoding="utf-8", newline="\n")
            return f"edited {args['path']}"
        if name == "fetch_url":
            u = urllib.parse.urlparse(args["url"])
            if u.scheme != "https" or u.hostname not in FETCH_HOSTS:
                raise ValueError("only https://netdryrun.com pages may be fetched")
            with urllib.request.urlopen(urllib.request.Request(args["url"], headers={"User-Agent": "ndr-eval"}),
                                        timeout=30) as r:
                page = r.read().decode("utf-8", "replace")
            page = re.sub(r"(?s)<(script|style|nav|header|footer)\b.*?</\1>", " ", page)
            return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", page))).strip()
        raise ValueError(f"unknown tool {name}")

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
        started = time.time()
        mcp, mcp_tools, status = None, [], "failed"
        try:
            mcp = MCP(json.loads(a.mcp_cmd))
            mcp_tools = mcp.start()
            status = "connected"
        except Exception as e:  # the run is graded invalid, like a Claude run whose server never connected
            self.emit({"type": "system", "subtype": "mcp_error", "error": str(e)})
        names = {f"mcp__netdryrun__{t['name']}": t["name"] for t in mcp_tools}
        tools = local_tools() + [{"type": "function", "function": {
            "name": f"mcp__netdryrun__{t['name']}", "description": t.get("description", ""),
            "parameters": t.get("inputSchema") or {"type": "object", "properties": {}}}} for t in mcp_tools]
        self.emit({"type": "system", "subtype": "init", "model": a.model, "agent": f"open_agent/{a.backend}",
                   "mcp_servers": [{"name": "netdryrun", "status": status}], "tools": [t["function"]["name"] for t in tools]})
        messages = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": a.prompt}]
        final, is_error, turns = "", False, 0
        try:
            while turns < a.max_turns and time.time() - started < a.time_limit:
                turns += 1
                r = self.chat(messages, tools)
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
                    final = r["content"]
                    break
                for c in r["tool_calls"]:
                    err = False
                    try:
                        if c["name"] in names:
                            res = mcp.request("tools/call", {"name": names[c["name"]], "arguments": c["arguments"]}, a.tool_timeout)
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
        finally:
            if mcp:
                mcp.close()
        self.emit({"type": "result", "result": final, "num_turns": turns, "is_error": is_error,
                   "duration_ms": int((time.time() - started) * 1000), "total_cost_usd": 0 if a.backend == "ollama" else None})
        return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--folder", required=True)
    ap.add_argument("--prompt", required=True)
    ap.add_argument("--transcript", required=True)
    ap.add_argument("--mcp-cmd", required=True, help="JSON list: the command that starts `netdryrun mcp`")
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
