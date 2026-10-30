"""Run the Network Change Verdict Corpus.

For every case: build the base lab, apply the case's config edits, deploy once, then evaluate
three test strategies against the same running lab:

  ping      - baseline A: "ping after the change"
  sessions  - baseline B: "all BGP sessions are up"
  netdryrun - the intent spec (specs/intent.yml), identical for every case

Each strategy's verdict (SAFE = all its checks passed) is compared with the case's expected
verdict, which was written before any run. Results go to results/results.json and RESULTS.md.

Usage (Linux/WSL, containerlab + docker available):
  python corpus/run.py                 # all cases
  python corpus/run.py --case 09       # cases whose id starts with 09
  python corpus/run.py --keep --case 01
  python corpus/run.py --corpus v2     # corpus v2 (corpus/v2/: its own base lab, spec and cases)
"""
from __future__ import annotations

import argparse
import json
import platform
import shutil
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import yaml

from netdryrun import __version__
from netdryrun.config import load
from netdryrun.lab import Lab
from netdryrun.runner import run

HERE = Path(__file__).resolve().parent
CORPORA = {"v1": HERE, "v2": HERE / "v2"}   # v1 lives at the top of corpus/ and is frozen
STRATEGIES = {"ping": "baseline-ping.yml", "sessions": "baseline-sessions.yml", "netdryrun": "intent.yml"}
NONDETERMINISTIC_RUNS = 3   # a case whose verdict follows a race in the lab runs this many times (NONDETERMINISTIC.yml)


class CaseError(ValueError):
    pass


def nondeterministic(corpus: Path = HERE) -> dict:
    """Case IDs marked in NONDETERMINISTIC.yml after the run: excluded from the score, run several times."""
    path = corpus / "NONDETERMINISTIC.yml"
    return (yaml.safe_load(path.read_text(encoding="utf-8")) or {}) if path.exists() else {}


def load_cases(prefix: str | None, corpus: Path = HERE) -> list[dict]:
    cases = []
    for path in sorted((corpus / "cases").glob("*.yml")):
        case = yaml.safe_load(path.read_text(encoding="utf-8"))
        case["file"] = path.name
        for key in ("id", "title", "category", "expected", "rationale"):
            if key not in case:
                raise CaseError(f"{path.name}: missing {key}")
        if case["expected"] not in ("safe", "unsafe"):
            raise CaseError(f"{path.name}: expected must be safe or unsafe")
        if not prefix or case["id"].startswith(prefix):
            cases.append(case)
    return cases


def build_workdir(case: dict, root: Path, corpus: Path = HERE) -> tuple[Path, list[dict]]:
    """Copy the base lab and apply the case's edits. Every edit must match exactly once."""
    work = root / case["id"]
    if work.exists():
        shutil.rmtree(work)
    shutil.copytree(corpus / "base", work)
    for spec in STRATEGIES.values():
        shutil.copy(corpus / "specs" / spec, work / spec)
    diff = []
    for i, edit in enumerate(case.get("edits", [])):
        cfg = work / "configs" / f"{edit['node']}.conf"
        text = cfg.read_text(encoding="utf-8")
        if "replace" in edit:
            n = text.count(edit["replace"])
            if n != 1:
                raise CaseError(f"{case['id']} edit {i}: 'replace' text found {n} times in {edit['node']}.conf (need 1)")
            text = text.replace(edit["replace"], edit.get("with", ""))
        elif "append" in edit:
            text = text.rstrip("\n") + "\n" + edit["append"].rstrip("\n") + "\n!\n"
        else:
            raise CaseError(f"{case['id']} edit {i}: needs 'replace' or 'append'")
        cfg.write_text(text, encoding="utf-8")
        diff.append({k: v for k, v in edit.items()})
    return work, diff


def evaluate(case: dict, root: Path, keep: bool, corpus: Path = HERE) -> dict:
    work, diff = build_workdir(case, root, corpus)
    lab = Lab(work / "topology.clab.yml")
    row = {k: case.get(k) for k in ("id", "title", "category", "expected", "rationale", "source", "note")}
    row["edits"] = diff
    t0 = time.monotonic()
    try:
        lab.deploy()
        row["strategies"] = {}
        for name, spec in STRATEGIES.items():
            rep = run(load(work / spec), deploy=False, settle=10, hold=10)
            verdict = {"passed": "safe", "failed": "unsafe"}.get(rep.status, "error")
            row["strategies"][name] = {
                "verdict": verdict,
                "correct": verdict == case["expected"],
                "failed_checks": [r.check.name for r in rep.results if not r.passed],
                "error": rep.error or None,
            }
    finally:
        if not keep:
            lab.destroy()
    row["seconds"] = round(time.monotonic() - t0)
    return row


def outcome(expected: str, verdict: str) -> str:
    if verdict == "error":
        return "error"
    if verdict == expected:
        return "correct"
    return "false pass" if expected == "unsafe" else "false block"


def write_results(rows: list[dict], out: Path, env: dict, corpus: Path = HERE) -> None:
    out.mkdir(exist_ok=True)
    (out / "results.json").write_text(json.dumps({"schema": "netdryrun.corpus/v1", "environment": env, "cases": rows}, indent=2))
    names = list(STRATEGIES)
    lines = [
        "# Verdict Corpus results", "",
        f"Generated {env['generated']} with netdryrun {env['netdryrun']}, containerlab {env['containerlab']}, "
        f"FRR {env['frr_image']}. Rerun with `python corpus/run.py{env.get('rerun_args', '')}`.", "",
        "**Conflict of interest:** the Netdryrun maintainers wrote this corpus and the runner. "
        "Expected verdicts were recorded before running. Losses are kept.", "",
        "## Summary", "",
        "| Strategy | Correct | False passes (bad change approved) | False blocks (good change rejected) | Errors |",
        "|---|---|---|---|---|",
    ]
    scored = [r for r in rows if not r.get("nondeterministic")]
    for s in names:
        oc = [outcome(r["expected"], r["strategies"][s]["verdict"]) for r in scored]
        lines.append(f"| {s} | {oc.count('correct')}/{len(scored)} | {oc.count('false pass')} | {oc.count('false block')} | {oc.count('error')} |")
    lines += ["", "## Cases", "", "| Case | Category | Expected | Ping | Sessions | Netdryrun | What Netdryrun flagged |", "|---|---|---|---|---|---|---|"]
    mark = {"correct": "✅", "false pass": "❌ false pass", "false block": "⚠️ false block", "error": "💥 error"}
    for r in rows:
        cells = [mark[outcome(r["expected"], r["strategies"][s]["verdict"])] for s in names]
        if r.get("nondeterministic"):
            cells = ["🎲 not scored"] * len(names)
        flagged = "; ".join(r["strategies"]["netdryrun"]["failed_checks"]) or "nothing"
        lines.append(f"| `{r['id']}` {r['title']} | {r['category']} | {r['expected']} | {' | '.join(cells)} | {flagged} |")
    losses = [r for r in scored if outcome(r["expected"], r["strategies"]["netdryrun"]["verdict"]) != "correct"]
    lines += ["", "## Netdryrun losses", ""]
    if not losses:
        lines.append("None in this run.")
    for r in losses:
        lines.append(f"- **`{r['id']}` {r['title']}**: {outcome(r['expected'], r['strategies']['netdryrun']['verdict'])}. {r.get('note') or ''}")
    (corpus / "RESULTS.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _git_commit() -> str:
    import subprocess
    r = subprocess.run(["git", "-C", str(HERE), "rev-parse", "--short", "HEAD"], capture_output=True, text=True)
    dirty = subprocess.run(["git", "-C", str(HERE), "status", "--porcelain", "--", "src", "corpus"], capture_output=True, text=True)
    return (r.stdout.strip() or "unknown") + ("+dirty" if dirty.stdout.strip() else "")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", help="only run cases whose id starts with this")
    ap.add_argument("--keep", action="store_true", help="leave each lab running (debugging; use with --case)")
    ap.add_argument("--corpus", choices=sorted(CORPORA), default="v1", help="which corpus to run (default v1)")
    ap.add_argument("--workdir", help="where case labs are built (default ~/.cache/netdryrun/corpus[-v2])")
    args = ap.parse_args()
    corpus = CORPORA[args.corpus]
    cases = load_cases(args.case, corpus)
    suffix = "" if args.corpus == "v1" else f"-{args.corpus}"
    root = Path(args.workdir or Path.home() / ".cache" / "netdryrun" / f"corpus{suffix}")
    root.mkdir(parents=True, exist_ok=True)
    clab = Lab(corpus / "base" / "topology.clab.yml")
    env = {
        "generated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "netdryrun": __version__, "containerlab": clab.version(),
        "frr_image": next(iter(clab.nodes.values())).image, "host": platform.platform(),
        "commit": _git_commit(),
    }
    if args.corpus != "v1":
        env["corpus"] = args.corpus
        env["rerun_args"] = f" --corpus {args.corpus}"
    nd = nondeterministic(corpus)
    rows = []
    for case in cases:
        print(f"== {case['id']}: {case['title']} (expected {case['expected']})", flush=True)
        try:
            n = NONDETERMINISTIC_RUNS if case["id"] in nd else 1
            # --keep keeps only the last run's lab: an earlier one left running would collide with the next deploy
            runs = [evaluate(case, root, args.keep and i == n - 1, corpus) for i in range(n)]
            row = runs[0]
            if n > 1:   # the first run stays the row's verdict; every run is kept
                row["nondeterministic"] = True
                row["runs"] = [{s: r["strategies"][s]["verdict"] for s in STRATEGIES} for r in runs]
        except CaseError as e:
            print(f"   CASE ERROR: {e}", flush=True)
            return 2
        rows.append(row)
        print("   " + "  ".join(f"{s}={row['strategies'][s]['verdict']}" for s in STRATEGIES)
              + f"  ({row['seconds']}s)" + (f"  nondeterministic, runs: {row['runs']}" if row.get("runs") else ""),
              flush=True)
    if not args.case:
        write_results(rows, corpus / "results", env, corpus)
        print(f"wrote {corpus.relative_to(HERE.parent).as_posix()}/RESULTS.md and results/results.json")
    else:
        print(json.dumps(rows, indent=1)[:4000])
    return 0


if __name__ == "__main__":
    sys.exit(main())
