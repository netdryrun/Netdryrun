"""Check an agent result file (netdryrun-verdict.json, netdryrun.mcp-result/v1) the way an agent reads it.

Usage: python scripts/check_verdict.py FILE EXPECTED_STATUS
Prints the status, the verdict, the failures and the tested files into the log, and exits 1 unless the file
says EXPECTED_STATUS with the matching frozen verdict, failures exactly when something failed, and the
sha256 of netdryrun.yml among the tested files. CI runs it on the reports the Action wrote.
"""
from __future__ import annotations

import json
import re
import sys

VERDICTS = {"passed": "CHECKS PASSED (only what the checks cover)",
            "inconclusive": ("INCONCLUSIVE: the lab did not reach a testable state; this says nothing about your "
                             "change. Do not apply it until a run passes.")}
DO_NOT_APPLY = "DO NOT APPLY THIS CHANGE"


def problems(result: dict, want: str) -> list[str]:
    out = []
    status = result.get("status")
    if status != want:
        out.append(f"status {status!r}, expected {want!r}")
    if result.get("verdict") != VERDICTS.get(status, DO_NOT_APPLY):
        out.append(f"verdict {result.get('verdict')!r} doesn't match status {status!r}")
    if result.get("schema") != "netdryrun.mcp-result/v1":
        out.append(f"schema {result.get('schema')!r}")
    failures, failed = result.get("failures"), result.get("failed")
    if not isinstance(failures, list) or len(failures) != failed:
        out.append(f"{failed!r} failed checks but failures is {failures!r:.80}")
    files = (result.get("tested") or {}).get("files") or {}
    if not re.fullmatch(r"[0-9a-f]{64}", str(files.get("netdryrun.yml", ""))):
        out.append("tested.files has no sha256 of netdryrun.yml")
    return out


def main(argv: list[str]) -> int:
    path, want = argv
    try:
        result = json.load(open(path, encoding="utf-8"))
    except (OSError, ValueError) as e:
        print(f"cannot read {path}: {e}")
        return 1
    tested = result.get("tested") or {}
    print(f"status={result.get('status')} verdict={result.get('verdict')!r} passed={result.get('passed')} "
          f"failed={result.get('failed')} lab_deployed_by_this_run={tested.get('lab_deployed_by_this_run')} "
          f"complete={tested.get('complete')}")
    for f in result.get("failures") or []:
        print(f"  failure: {f.get('check')} -- {f.get('reason')} | next: {f.get('next_diagnostic')}")
    for name, sha in sorted((tested.get("files") or {}).items()):
        print(f"  tested {sha[:12]} {name}")
    wrong = problems(result, want)
    for p in wrong:
        print(f"PROBLEM: {p}")
    return 1 if wrong else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
