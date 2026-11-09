#!/usr/bin/env python3
"""labrun: start a long gate run (live, acceptance, a corpus refresh) so that it can't die or stall unnoticed, and
stop it cleanly. 0.4.2 plan, step 1 (HQ design/release-checks-0.4.2-plan.md).

What broke in 0.4.1, and what this does about it:
- A launcher's `&` left SIGINT ignored for the whole run (G2), and a launch that never ran was found hours later.
  `start` runs the command in its own session with SIGINT, SIGQUIT and SIGTERM at their defaults, under a watcher
  process that is not part of the run. The run itself (release_gate.py) writes a receipt after its first real step;
  `start` returns only when the receipt is there (exit 0) or the launch has failed (exit 1), within --receipt-timeout.
- A run that hangs: the run writes a heartbeat every 30 s; the watcher marks it `stalled` and stops it when the
  heartbeat is older than --stale seconds.
- A run that exits without finishing: the run writes done.json at its end; an exit without it is
  `exited-without-result`, whatever the exit code.
- Pauses and host sleep counted against timeouts: nothing is SIGSTOPped any more. `pause` asks the run to hold at the
  next case boundary (the run keeps beating while it holds). The watcher measures wall-clock gaps from outside the run:
  a gap longer than --gap seconds (host sleep, a frozen WSL VM) is recorded in result.json as a taint, and a case whose
  time overlaps a taint is never a verdict (gate_records.py).

Commands (state in --state DIR/<id>/, default ~/.cache/netdryrun-labrun):
  start --id ID [options] -- CMD...   start CMD; exit 0 once it wrote its receipt, 1 if the launch failed
  status ID                           print run.json, the receipt, the heartbeat age and result.json
  wait ID                             block until the run ends; exit 0 only for state ok
  pause ID / resume ID                hold at the next case boundary / continue
  stop ID                             SIGTERM the run's process group, SIGKILL after 30 s, check it is gone

Exit codes: 0 ok, 1 the run failed or the launch failed, 2 usage or state error.
"""
from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

STATE = Path(os.environ.get("LABRUN_STATE", Path.home() / ".cache" / "netdryrun-labrun"))
TICK = float(os.environ.get("LABRUN_TICK", "2"))   # watcher poll interval, seconds (tests shorten it)
BEAT = 30.0           # heartbeat interval, seconds
STOP_GRACE = 30.0     # SIGTERM to SIGKILL, seconds
ENDED = ("ok", "failed", "launch-failed", "stalled", "exited-without-result", "stopped")


# ---- small helpers ------------------------------------------------------------------------------------------------
def write_json(path: Path, data: dict) -> None:
    """Atomic: a reader never sees half a file. The temp name is per process and per thread: the heartbeat thread and
    the run's own beat() (hold_if_paused, phase) write heartbeat.json at once, and a shared temp file let one thread's
    os.replace find it gone and kill the run before done() (PR #6, Python 3.10, exited-without-result)."""
    tmp = path.with_name(f".{path.name}.{os.getpid()}.{threading.get_ident()}.tmp")
    tmp.write_text(json.dumps(data, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def read_json(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def group_alive(pgid: int) -> bool:
    try:
        os.killpg(pgid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _default_signals() -> None:   # runs in the child between fork and exec
    for s in (signal.SIGINT, signal.SIGQUIT, signal.SIGTERM, signal.SIGHUP):
        signal.signal(s, signal.SIG_DFL)


# ---- the run's side (imported by release_gate.py) -----------------------------------------------------------------
def run_dir() -> Path | None:
    d = os.environ.get("LABRUN_DIR")
    return Path(d) if d else None


def receipt(**info) -> None:
    """Called by the run after its first real step (G2 passed). No-op outside labrun."""
    d = run_dir()
    if d:
        write_json(d / "receipt.json", {"pid": os.getpid(), "wall": time.time(), **info})


def done(code: int, summary: str = "") -> None:
    d = run_dir()
    if d:
        write_json(d / "done.json", {"pid": os.getpid(), "wall": time.time(), "code": code, "summary": summary})


class Heartbeat:
    """A daemon thread that writes heartbeat.json every `every` seconds: wall clock, monotonic clock, the current
    phase, and whether the run is holding for a pause."""

    def __init__(self, every: float = BEAT):
        self.dir, self.every, self.phase, self.held = run_dir(), every, "start", False
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._loop, name="labrun-heartbeat", daemon=True)

    def start(self) -> "Heartbeat":
        if self.dir:
            self.beat()
            self._thread.start()
        return self

    def beat(self) -> None:
        if self.dir:
            write_json(self.dir / "heartbeat.json", {"pid": os.getpid(), "wall": time.time(),
                                                     "mono": time.monotonic(), "phase": self.phase,
                                                     "held": self.held})

    def _loop(self) -> None:
        while not self._stop.wait(self.every):
            self.beat()

    def stop(self) -> None:
        self._stop.set()


HEART: Heartbeat | None = None


def phase(name: str) -> None:
    """Name the case the run is in (shown by `status`, used to attribute a taint)."""
    if HEART:
        HEART.phase = name
        HEART.beat()


def hold_if_paused(poll: float = 5.0) -> float:
    """At a case boundary: while a pause is requested, hold (beating). Returns the seconds held."""
    d = run_dir()
    if not d or not (d / "pause").exists():
        return 0.0
    t0 = time.monotonic()
    if HEART:
        HEART.held = True
        HEART.beat()
    print(f"labrun: paused at a case boundary ({d / 'pause'})", flush=True)
    while (d / "pause").exists():
        time.sleep(poll)
    if HEART:
        HEART.held = False
        HEART.beat()
    held = time.monotonic() - t0
    print(f"labrun: resumed after {held:.0f} s", flush=True)
    return held


# ---- the watcher --------------------------------------------------------------------------------------------------
def watch(d: Path, cmd: list[str], receipt_timeout: float, stale: float, gap: float, *,
          clock=time.time, sleep=time.sleep, popen=subprocess.Popen) -> dict:
    """Start cmd and watch it until it ends. Writes run.json and result.json in d; returns the result."""
    env = {**os.environ, "LABRUN_DIR": str(d), "LABRUN_ID": d.name}
    log = open(d / "run.log", "ab")
    proc = popen(cmd, stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT, env=env,
                 start_new_session=True, preexec_fn=_default_signals)
    started = clock()
    write_json(d / "run.json", {"id": d.name, "cmd": cmd, "pid": proc.pid, "pgid": proc.pid, "watcher": os.getpid(),
                                "started": started})
    taints: list[dict] = []
    state, why, last, grace_until = None, "", started, 0.0
    while True:
        sleep(TICK)
        t = clock()
        if t - last > gap:                         # the watcher itself didn't run: host sleep, a frozen VM
            taints.append({"from": last, "to": t, "seconds": round(t - last, 1)})
            grace_until = t + stale                # the run gets a full --stale to beat again after it
        last = t
        rc = proc.poll()
        if rc is not None:
            if (d / "stop-requested").exists():
                state, why = "stopped", f"stopped by `labrun stop`, exit {rc}"
            elif not (d / "done.json").exists():
                state = "launch-failed" if not (d / "receipt.json").exists() else "exited-without-result"
                why = f"exit {rc} without " + ("a receipt" if state == "launch-failed" else "done.json")
            else:
                state, why = ("ok" if rc == 0 else "failed"), f"exit {rc}"
            break
        if not (d / "receipt.json").exists():
            if t - started > receipt_timeout:
                state, why = "launch-failed", f"no receipt within {receipt_timeout:.0f} s"
                break
            continue
        hb = read_json(d / "heartbeat.json") or {}
        age = t - float(hb.get("wall") or (read_json(d / "receipt.json") or {}).get("wall") or started)
        if age > stale and t > grace_until:
            state, why = "stalled", f"no heartbeat for {age:.0f} s (phase {hb.get('phase', '?')})"
            break
    if proc.poll() is None:                        # launch-failed or stalled: take the whole group down
        kill_group(proc.pid, sleep=sleep, clock=clock, reap=proc.poll)
        proc.wait()
    result = {"id": d.name, "state": state, "why": why, "rc": proc.returncode, "started": started, "ended": clock(),
              "taints": taints, "done": read_json(d / "done.json")}
    write_json(d / "result.json", result)
    log.close()
    return result


def kill_group(pgid: int, *, sleep=time.sleep, clock=time.time, grace: float = STOP_GRACE, reap=None) -> bool:
    """SIGTERM the group, SIGKILL after grace; True when it is gone. The watcher passes reap (its child's poll), so
    its own child doesn't linger as a zombie that still counts as alive."""
    try:
        os.killpg(pgid, signal.SIGTERM)
    except ProcessLookupError:
        return True
    t0 = clock()
    while clock() - t0 < grace:
        if reap:
            reap()
        if not group_alive(pgid):
            break
        sleep(0.5)
    if group_alive(pgid):
        try:
            os.killpg(pgid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        sleep(0.5)
        if reap:
            reap()
    return not group_alive(pgid)


# ---- commands -----------------------------------------------------------------------------------------------------
def cmd_start(args) -> int:
    d = args.state / args.id
    if d.exists() and not (d / "result.json").exists() and (d / "run.json").exists():
        print(f"labrun: {args.id} is already running ({d})", file=sys.stderr)
        return 2
    if d.exists():
        for f in d.iterdir():
            f.unlink()
    d.mkdir(parents=True, exist_ok=True)
    watcher = subprocess.Popen(
        [sys.executable, os.path.abspath(__file__), "--state", str(args.state), "_watch",
         "--receipt-timeout", str(args.receipt_timeout), "--stale", str(args.stale), "--gap", str(args.gap), str(d),
         "--", *args.cmd],
        stdin=subprocess.DEVNULL, stdout=open(d / "watcher.log", "ab"), stderr=subprocess.STDOUT,
        start_new_session=True, preexec_fn=_default_signals)
    deadline = time.time() + args.receipt_timeout + 10
    while time.time() < deadline:
        if (d / "receipt.json").exists():
            print(f"labrun: {args.id} started (receipt {d / 'receipt.json'}; watcher pid {watcher.pid})")
            return 0
        res = read_json(d / "result.json")
        if res:
            print(f"labrun: {args.id} {res['state']}: {res['why']} (log {d / 'run.log'})", file=sys.stderr)
            return 1
        if watcher.poll() is not None and not (d / "result.json").exists():
            wlog = d / "watcher.log"
            log = wlog.read_text(encoding="utf-8", errors="replace") if wlog.exists() else ""
            print(f"labrun: {args.id}: the watcher died (exit {watcher.returncode}):\n{log[-1500:]}", file=sys.stderr)
            return 1
        time.sleep(0.5)
    print(f"labrun: {args.id}: no receipt and no result after {args.receipt_timeout + 10:.0f} s", file=sys.stderr)
    return 1


def cmd_status(args) -> int:
    d = args.state / args.id
    if not (d / "run.json").exists():
        print(f"labrun: no run {args.id} in {args.state}", file=sys.stderr)
        return 2
    hb = read_json(d / "heartbeat.json")
    out = {"run": read_json(d / "run.json"), "receipt": read_json(d / "receipt.json"),
           "heartbeat_age_s": round(time.time() - hb["wall"], 1) if hb else None,
           "phase": hb and hb.get("phase"), "held": hb and hb.get("held"),
           "paused": (d / "pause").exists(), "result": read_json(d / "result.json")}
    print(json.dumps(out, indent=1))
    return 0


def cmd_wait(args) -> int:
    d = args.state / args.id
    while not (d / "result.json").exists():
        if not (d / "run.json").exists():
            print(f"labrun: no run {args.id}", file=sys.stderr)
            return 2
        time.sleep(5)
    res = read_json(d / "result.json") or {}
    print(f"labrun: {args.id} {res.get('state')}: {res.get('why')}; {len(res.get('taints') or [])} taint(s)")
    return 0 if res.get("state") == "ok" else 1


def cmd_pause(args, on: bool) -> int:
    d = args.state / args.id
    if not (d / "run.json").exists():
        print(f"labrun: no run {args.id}", file=sys.stderr)
        return 2
    p = d / "pause"
    p.touch() if on else p.unlink(missing_ok=True)
    print(f"labrun: {args.id} {'will hold at the next case boundary' if on else 'resumed'}")
    return 0


def cmd_stop(args) -> int:
    d = args.state / args.id
    run = read_json(d / "run.json")
    if not run:
        print(f"labrun: no run {args.id}", file=sys.stderr)
        return 2
    (d / "stop-requested").touch()
    gone = kill_group(int(run["pgid"]))
    print(f"labrun: {args.id} process group {run['pgid']} " + ("is gone" if gone else "is STILL RUNNING"))
    return 0 if gone else 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--state", type=Path, default=STATE)
    sub = ap.add_subparsers(dest="action", required=True)
    s = sub.add_parser("start")
    s.add_argument("--id", required=True)
    w = sub.add_parser("_watch")
    w.add_argument("dir", type=Path)
    for p in (s, w):
        p.add_argument("--receipt-timeout", type=float, default=90.0)
        p.add_argument("--stale", type=float, default=90.0)
        p.add_argument("--gap", type=float, default=60.0)
        p.add_argument("command", nargs=argparse.REMAINDER)
    for name in ("status", "wait", "pause", "resume", "stop"):
        sub.add_parser(name).add_argument("id")
    args = ap.parse_args(argv)
    if args.action in ("start", "_watch"):
        args.cmd = args.command[1:] if args.command[:1] == ["--"] else args.command
        if not args.cmd:
            ap.error(f"{args.action}: give the command after --")
    if args.action == "_watch":
        try:
            res = watch(args.dir, args.cmd, args.receipt_timeout, args.stale, args.gap)
        except Exception as e:   # never a silent watcher: the launch is failed, with the reason
            write_json(args.dir / "result.json", {"id": args.dir.name, "state": "launch-failed", "rc": None,
                                                  "why": f"watcher error: {type(e).__name__}: {e}", "taints": [],
                                                  "done": None})
            raise
        return 0 if res["state"] == "ok" else 1
    return {"start": cmd_start, "status": cmd_status, "wait": cmd_wait, "stop": cmd_stop,
            "pause": lambda a: cmd_pause(a, True), "resume": lambda a: cmd_pause(a, False)}[args.action](args)


if __name__ == "__main__":
    sys.exit(main())
