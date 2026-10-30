"""Rerun the false-passes corpus against the installed netdryrun. Needs a lab machine (Docker, containerlab).

    python corpus/v3-false-passes/run_cases.py                  # every case this version should handle
    python corpus/v3-false-passes/run_cases.py --case 03 --dry-run
    python corpus/v3-false-passes/run_cases.py --json out.json

For each case: skip it when the installed netdryrun is older than the case's `expected_from` (those versions are
the ones that passed it wrongly; the point is not to expect otherwise), run the command from the case folder, and
compare the exit code and the messages with case.yml. An `action` case is checked in CI, not here.

A heavy run: take the lab lock first on a shared machine. This script does not start more than one lab at a time.
Exit 0 only when every case that ran gave exactly the pre-registered verdict.
"""
from __future__ import annotations

import argparse
import json
import re
import shlex
import subprocess
import sys
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
CASES = HERE / "cases"


def vtuple(v: str) -> tuple[int, ...]:
    return tuple(int(x) for x in re.findall(r"\d+", v)[:3])


def installed_version() -> str:
    from netdryrun import __version__
    return __version__


def load_cases(prefix: str | None) -> list[tuple[Path, dict]]:
    out = []
    for d in sorted(p for p in CASES.iterdir() if p.is_dir()):
        c = yaml.safe_load((d / "case.yml").read_text(encoding="utf-8"))
        if not prefix or c["id"].startswith(prefix):
            out.append((d, c))
    return out


def judge(c: dict, code: int, output: str) -> list[str]:
    exp = c["expected"]
    problems = []
    if code != exp["exit_code"]:
        problems.append(f"exit {code}, expected {exp['exit_code']}")
    low = output.lower()
    problems += [f"output lacks {m!r}" for m in exp["must_report"] if m.lower() not in low]
    if exp.get("verdict") and exp["verdict"].lower() not in low:
        problems.append(f"output lacks the verdict {exp['verdict']!r}")
    return problems


def run_case(d: Path, c: dict, version: str, dry: bool) -> dict:
    row = {"id": c["id"], "mode": c["mode"], "expected": c["expected"]["status"]}
    if vtuple(version) < vtuple(c["expected_from"]):
        return {**row, "result": "skipped", "why": f"netdryrun {version} is older than {c['expected_from']}: the version "
                f"that passed this case wrongly is not expected to give the verdict"}
    if c["mode"] == "action":
        return {**row, "result": "skipped", "why": "checked in CI on a pull request (see WRITEUP.md)"}
    cmd = shlex.split(c["command"])
    if dry:
        return {**row, "result": "dry-run", "why": f"cd {d.name} && {c['command']}"}
    p = subprocess.run(cmd, cwd=d, capture_output=True, text=True, timeout=3600)
    problems = judge(c, p.returncode, p.stdout + p.stderr)
    return {**row, "result": "match" if not problems else "MISMATCH", "exit_code": p.returncode, "why": "; ".join(problems)}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--case", help="only cases whose id starts with this")
    ap.add_argument("--dry-run", action="store_true", help="print what would run, run nothing")
    ap.add_argument("--json", help="write the results here")
    a = ap.parse_args()
    version = installed_version()
    rows = [run_case(d, c, version, a.dry_run) for d, c in load_cases(a.case)]
    for r in rows:
        print(f"{r['id']:<44} {r['result']:<9} {r.get('why', '')}")
    if a.json:
        Path(a.json).write_text(json.dumps({"netdryrun": version, "cases": rows}, indent=1), encoding="utf-8")
    return 1 if any(r["result"] == "MISMATCH" for r in rows) else 0


if __name__ == "__main__":
    sys.exit(main())
