"""Latency benchmark: run example labs cold, N times, with a good and a broken change, and report p50/p95 per phase.

    python bench/latency/bench.py run --lab frr-bgp --change good --change missing -n 10 \
        --netdryrun .venv/bin/netdryrun --label after --out bench/latency/results/after.jsonl
    python bench/latency/bench.py report bench/latency/results/*.jsonl > bench/latency/results/REPORT.md

`run` copies the example to a scratch folder, applies the change, runs `netdryrun run <folder> --json` as a
subprocess (any version: `--netdryrun` names the executable, so a base release and a candidate can be compared
on one host), and appends one JSON line per trial: the label, lab, change, trial, wall-clock seconds, exit code,
status, the run's phase timings (Netdryrun 0.4.1 and later; older versions report only the wall clock) and an
environment fingerprint (host, CPU, cores, RAM, kernel, Docker, containerlab, image digests). Every trial is a
cold boot: deploy, checks, destroy.

`report` prints, per (label, lab, change), the status counts and p50/p95/max of the wall clock and of every phase,
and a verdict-agreement table across labels: a (lab, change) whose status differs between labels is listed first.

Run it on the lab machine under the shared lab lock, one trial at a time. Never publish a table with cEOS in it
(Arista's licence forbids publishing benchmark results).
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EXAMPLES = ROOT / "examples"
PHASES = ("deploy", "boot", "ready", "converge", "settle", "checks", "destroy")


# ------------------------------------------------------------------------------------------- changes
# Each change edits the scratch copy of an example. "good" leaves it as it is. A broken change must make the run
# fail: "missing" removes a route the checks expect (a positive check fails, the case fail-fast shortens), "leak"
# is the example's own bad change (a negative check fails).

def _drop_line(path: Path, line: str) -> None:
    text = path.read_text(encoding="utf-8")
    if line + "\n" not in text:
        raise SystemExit(f"{path}: no line {line!r} to remove (the example changed?)")
    path.write_text(text.replace(line + "\n", "", 1), encoding="utf-8")


def _frr_bgp_leak(d: Path) -> None:
    shutil.copyfile(EXAMPLES / "frr-bgp-broken" / "r2-bad.conf", d / "configs" / "r2.conf")


CHANGES = {
    "frr-bgp": {
        "good": lambda d: None,
        "missing": lambda d: _drop_line(d / "configs" / "r3.conf", "  network 192.168.3.0/24"),
        "leak": _frr_bgp_leak,
    },
    "srl-frr": {
        "good": lambda d: None,
        "missing": lambda d: _drop_line(d / "configs" / "frr1.conf", "  network 192.168.20.0/24"),
    },
}


# verify (FRR only): the change and the intent that declares it. The after side announces one more prefix from r3.
def _frr_bgp_announce(d: Path) -> None:
    conf = d / "configs" / "r3.conf"
    text = conf.read_text(encoding="utf-8")
    for old, new in ((" ip address 192.168.3.1/24\n", " ip address 192.168.3.1/24\n ip address 192.168.33.1/24\n"),
                     ("  network 192.168.3.0/24\n", "  network 192.168.3.0/24\n  network 192.168.33.0/24\n")):
        if old not in text:
            raise SystemExit(f"{conf}: no line {old.strip()!r} (the example changed?)")
        text = text.replace(old, new, 1)
    conf.write_text(text, encoding="utf-8")


VERIFY_CHANGES = {
    "frr-bgp": {"announce": (_frr_bgp_announce, "intent:\n  - prefix: 192.168.33.0/24\n    appears_on: [r1, r2, r3]\n")},
}
NEVER_PUBLISH = ("arista-frr",)   # cEOS: Arista's EULA forbids publishing benchmark results


# --------------------------------------------------------------------------------------- environment

def _out(cmd: list[str]) -> str:
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=60).stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        return ""


def fingerprint(netdryrun: str) -> dict:
    cpu = ""
    try:
        cpu = next((ln.split(":", 1)[1].strip() for ln in Path("/proc/cpuinfo").read_text().splitlines()
                    if ln.startswith("model name")), "")
    except OSError:
        pass
    mem = ""
    try:
        mem = next((ln.split()[1] for ln in Path("/proc/meminfo").read_text().splitlines()
                    if ln.startswith("MemTotal")), "")
    except OSError:
        pass
    clab = re.search(r"version:\s*(\S+)", _out(["containerlab", "version"]))
    return {"host": platform.node(), "cpu": cpu, "cores": os.cpu_count(), "mem_kb": mem, "kernel": platform.release(),
            "docker": _out(["docker", "version", "--format", "{{.Server.Version}}"]),
            "containerlab": clab.group(1) if clab else "", "netdryrun": _out([netdryrun, "--version"]),
            "loadavg": os.getloadavg()[0] if hasattr(os, "getloadavg") else None}


# ----------------------------------------------------------------------------------------------- run

def trial(lab: str, change: str, netdryrun: str, work: Path) -> dict:
    d = work / lab
    if d.exists():
        shutil.rmtree(d)
    shutil.copytree(EXAMPLES / lab, d)
    CHANGES[lab][change](d)
    report = work / f"{lab}-{change}.json"
    report.unlink(missing_ok=True)
    t0 = time.monotonic()
    p = subprocess.run([netdryrun, "run", str(d), "--json", str(report), "--no-step-summary"],
                       capture_output=True, text=True)
    wall = round(time.monotonic() - t0, 1)
    row = {"wall_s": wall, "exit_code": p.returncode, "status": None, "timings": {}, "failed": [], "images": {}}
    try:
        rep = json.loads(report.read_text(encoding="utf-8"))
        row["status"] = rep["status"]
        row["timings"] = rep.get("timings") or {}
        row["failed"] = [c["name"] for c in rep["checks"] if not c["passed"]]
        row["images"] = {n: v.get("image_digest") for n, v in (rep["environment"].get("nodes") or {}).items()}
        row["error"] = rep.get("error")
    except (OSError, ValueError, KeyError) as e:
        row["error"] = f"no report: {e}; stderr: {p.stderr[-500:]}"
    return row


def verify_trial(lab: str, change: str, netdryrun: str, work: Path, extra: list[str]) -> dict:
    """One `netdryrun verify` of the example (before) against the example with the change (after)."""
    for side in ("before", "after"):
        d = work / side
        if d.exists():
            shutil.rmtree(d)
        shutil.copytree(EXAMPLES / lab, d)
    edit, intent = VERIFY_CHANGES[lab][change]
    edit(work / "after")
    (work / "intent.yml").write_text(intent, encoding="utf-8")
    report = work / f"{lab}-{change}-verify.json"
    report.unlink(missing_ok=True)
    topo = work / "before" / "topology.clab.yml"
    t0 = time.monotonic()
    p = subprocess.run([netdryrun, "verify", str(topo), "--before", str(work / "before"), "--after", str(work / "after"),
                        "--intent", str(work / "intent.yml"), "--json", str(report), *extra], capture_output=True, text=True)
    wall = round(time.monotonic() - t0, 1)
    row = {"wall_s": wall, "exit_code": p.returncode, "status": None, "timings": {}, "failed": []}
    try:
        rep = json.loads(report.read_text(encoding="utf-8"))
        row["status"], row["timings"], row["error"] = rep["status"], rep.get("timings") or {}, rep.get("error")
        row["failed"] = [u.get("summary", "") for u in rep.get("undeclared", [])]
    except (OSError, ValueError, KeyError) as e:
        row["error"] = f"no report: {e}; stderr: {p.stderr[-500:]}"
    return row


def cmd_run(args) -> int:
    table = VERIFY_CHANGES if args.mode == "verify" else CHANGES
    for lab in args.lab:
        if lab not in table:
            raise SystemExit(f"unknown lab {lab!r} for {args.mode}; known: {', '.join(table)}")
        for change in args.change:
            if change not in table[lab]:
                raise SystemExit(f"{lab}: unknown change {change!r}; known: {', '.join(table[lab])}")
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="ndr-bench-", dir=args.work))
    env = fingerprint(args.netdryrun)
    try:
        for i in range(args.n):
            for lab in args.lab:
                for change in args.change:
                    one = (verify_trial(lab, change, args.netdryrun, work, args.extra or []) if args.mode == "verify"
                           else trial(lab, change, args.netdryrun, work))
                    row = {"label": args.label, "mode": args.mode, "lab": lab, "change": change, "trial": i,
                           "started": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                           **one, "env": {**env, "loadavg": os.getloadavg()[0]}}
                    with out.open("a", encoding="utf-8") as f:
                        f.write(json.dumps(row) + "\n")
                    print(f"{args.label} {lab} {change} #{i}: {row['status']} (exit {row['exit_code']}) in "
                          f"{row['wall_s']}s {row['timings'] or ''}", flush=True)
    finally:
        shutil.rmtree(work, ignore_errors=True)
    return 0


# -------------------------------------------------------------------------------------------- report

def pct(values: list[float], q: float) -> float | None:
    """The q-quantile by the nearest-rank method (p50, p95 of a handful of runs: no interpolation)."""
    vals = sorted(v for v in values if v is not None)
    if not vals:
        return None
    k = max(0, min(len(vals) - 1, -(-round(q * 100) * len(vals) // 100) - 1))
    return vals[k]


def _fmt(v) -> str:
    return "" if v is None else f"{v:g}"


def cmd_report(args) -> int:
    rows = []
    for p in args.files:
        rows += [json.loads(ln) for ln in Path(p).read_text(encoding="utf-8").splitlines() if ln.strip()]
    if any(r["lab"] in NEVER_PUBLISH for r in rows):
        print("<!-- contains cEOS rows: internal only, never publish -->")
    groups: dict[tuple, list] = {}
    for r in rows:
        groups.setdefault((r.get("mode", "run"), r["label"], r["lab"], r["change"]), []).append(r)
    for mode, phases in (("run", PHASES), ("verify", VERIFY_PHASES)):
        mine = {k[1:]: v for k, v in groups.items() if k[0] == mode}
        if mine:
            _table(mine, phases)
            print()
    print("Verdict agreement across labels (every trial of a lab and change must end with the same status):")
    print()
    by_case: dict[tuple, dict] = {}
    for r in rows:
        by_case.setdefault((r.get("mode", "run"), r["lab"], r["change"]), {}).setdefault(r["label"], set()).add(r["status"])
    bad = 0
    for (mode, lab, change), labels in sorted(by_case.items()):
        seen = set().union(*labels.values())
        ok = len(seen) == 1
        bad += not ok
        print(f"- {mode} {lab} {change}: {'same' if ok else 'DIFFERENT'} ("
              + "; ".join(f"{lb}: {', '.join(sorted(map(str, s)))}" for lb, s in sorted(labels.items())) + ")")
    return 1 if bad else 0


VERIFY_PHASES = ("before_s", "after_s", "rerun_before_s", "rerun_after_s")


def _table(groups: dict, phases) -> None:
    print("| label | lab | change | n | statuses | wall p50 | wall p95 | wall max | "
          + " | ".join(f"{ph} p50/p95" for ph in phases) + " |")
    print("|" + "---|" * (8 + len(phases)))
    for (label, lab, change), rs in sorted(groups.items(), key=lambda kv: (kv[0][1], kv[0][2], kv[0][0])):
        statuses = {}
        for r in rs:
            statuses[r["status"]] = statuses.get(r["status"], 0) + 1
        walls = [r["wall_s"] for r in rs]
        cells = []
        for ph in phases:
            vals = [r["timings"].get(ph) for r in rs if isinstance(r["timings"].get(ph), (int, float))]
            cells.append(f"{_fmt(pct(vals, .5))}/{_fmt(pct(vals, .95))}" if vals else "")
        st = ", ".join(f"{k} {v}" for k, v in sorted(statuses.items(), key=lambda kv: str(kv[0])))
        print(f"| {label} | {lab} | {change} | {len(rs)} | {st} | {_fmt(pct(walls, .5))} | {_fmt(pct(walls, .95))} | "
              f"{_fmt(max(walls))} | " + " | ".join(cells) + " |")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="run trials and append them to a JSONL file")
    r.add_argument("--lab", action="append", required=True, help=f"example lab ({', '.join(CHANGES)}); repeatable")
    r.add_argument("--change", action="append", required=True, help="good, missing or leak; repeatable")
    r.add_argument("-n", type=int, default=10, help="trials per lab and change (default 10)")
    r.add_argument("--netdryrun", default="netdryrun", help="the netdryrun executable to time")
    r.add_argument("--label", required=True, help="a name for this set of trials (before, after, a commit)")
    r.add_argument("--out", required=True, help="JSONL file to append to")
    r.add_argument("--work", default=None, help="scratch folder (default: the system temp folder)")
    r.add_argument("--mode", choices=("run", "verify"), default="run", help="time `netdryrun run` (default) or `verify`")
    r.add_argument("--extra", action="append", help="an extra argument for netdryrun (e.g. --extra=--serial); repeatable")
    rep = sub.add_parser("report", help="p50/p95 per phase from JSONL files")
    rep.add_argument("files", nargs="+")
    args = ap.parse_args(argv)
    return cmd_run(args) if args.cmd == "run" else cmd_report(args)


if __name__ == "__main__":
    sys.exit(main())
