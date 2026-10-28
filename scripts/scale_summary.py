#!/usr/bin/env python3
"""Turn one scale-test run into a record (phase times, memory, verdict) and print the summary.

Used by scripts/scale_test.sh:  `record` appends a variant's record to scale-<leaves>.json, `show` prints it
(exit 0 only when every variant gave its expected exit code and left no lab running).

The phase times come from the timestamped netdryrun log (`<epoch>\\t<line>`): the run's own progress lines are
the marks, so a change in those lines shows up here as a missing time (None), not as a wrong one.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys


def read_log(path: str) -> list[tuple[float, str]]:
    rows = []
    for ln in open(path, encoding="utf-8", errors="replace"):
        t, _, text = ln.rstrip("\n").partition("\t")
        try:
            rows.append((float(t), text))
        except ValueError:
            pass
    return rows


def first(rows, pattern: str):
    return next((t for t, text in rows if re.search(pattern, text)), None)


def span(a, b):
    return round(b - a, 1) if a is not None and b is not None else None


def memory(path: str, nodes: int) -> dict:
    samples = []
    if os.path.exists(path):
        for ln in open(path, encoding="utf-8"):
            p = ln.split()
            if len(p) == 3 and all(x.lstrip("-").isdigit() for x in p):
                samples.append(tuple(int(x) for x in p))
    loaded = [s for s in samples if s[1] > 0]
    if not loaded:
        return {}
    peak = max(s[1] for s in loaded)
    return {"lab_containers_peak": peak, "per_node_peak": round(peak / nodes, 1),
            "host_available_min": min(s[2] for s in loaded), "samples": len(loaded)}


def record(a) -> int:
    rows = read_log(a.log)
    deploy = first(rows, r"Deploying lab") or a.t0
    check = first(rows, r"\[(PASS|FAIL)\]") or first(rows, r"Convergence checks done")
    conv = first(rows, r"Convergence checks done")
    destroy = first(rows, r"Destroying lab")
    result = [t for _, t in rows if re.match(r"^(PASSED|FAILED|ERROR|INCONCLUSIVE)", t)]
    rec = {"variant": a.variant, "leaves": a.leaves, "nodes": a.nodes, "checks": 5 * a.leaves + 1,
           "exit": a.exit, "expected_exit": a.want, "left_running": a.left,
           "seconds": {"total": span(a.t0, a.t1),
                       "deploy_and_wait": span(deploy, check),      # deploy + readiness, until the first verdict line
                       "convergence_gate": span(deploy, conv),
                       "checks": span(check, destroy),
                       "destroy": span(destroy, a.t1)},
           "memory_mib": memory(a.mem, a.nodes),
           "result_line": result[-1] if result else ""}
    rec["ok"] = rec["exit"] == rec["expected_exit"] and rec["left_running"] == 0
    data = {"leaves": a.leaves, "nodes": a.nodes, "runs": []}
    if os.path.exists(a.out):
        data = json.load(open(a.out, encoding="utf-8"))
    data["runs"] = [r for r in data["runs"] if r["variant"] != a.variant] + [rec]
    json.dump(data, open(a.out, "w", encoding="utf-8"), indent=1)
    print(json.dumps(rec))
    return 0


def show(a) -> int:
    d = json.load(open(a.file, encoding="utf-8"))
    print(f"\n{d['nodes']} nodes ({d['leaves']} leaves)")
    for r in d["runs"]:
        s, m = r["seconds"], r.get("memory_mib") or {}
        print(f"  {r['variant']:<5} {'OK ' if r['ok'] else 'BAD'} exit {r['exit']} (want {r['expected_exit']}) "
              f"total {s['total']} s | deploy+wait {s['deploy_and_wait']} s, checks {s['checks']} s, "
              f"destroy {s['destroy']} s | lab RAM peak {m.get('lab_containers_peak')} MiB = "
              f"{m.get('per_node_peak')} MiB/node | left running {r['left_running']} | {r['result_line'][:60]}")
    return 0 if d["runs"] and all(r["ok"] for r in d["runs"]) else 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("record")
    r.add_argument("--log", required=True)
    r.add_argument("--mem", required=True)
    r.add_argument("--variant", required=True, choices=["pass", "leak"])
    r.add_argument("--leaves", type=int, required=True)
    r.add_argument("--nodes", type=int, required=True)
    r.add_argument("--exit", type=int, required=True)
    r.add_argument("--want", type=int, required=True)
    r.add_argument("--left", type=int, required=True)
    r.add_argument("--t0", type=float, required=True)
    r.add_argument("--t1", type=float, required=True)
    r.add_argument("--out", required=True)
    s = sub.add_parser("show")
    s.add_argument("file")
    a = ap.parse_args()
    return record(a) if a.cmd == "record" else show(a)


if __name__ == "__main__":
    sys.exit(main())
