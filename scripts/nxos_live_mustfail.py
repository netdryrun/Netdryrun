#!/usr/bin/env python3
"""Live must-fail coverage for the NX-OS driver: run scripts/labs/nxos-cap/mustfail.yml on a live Nexus 9000v
and check every verdict.

  PYTHONPATH=src python3 scripts/nxos_live_mustfail.py [--report FILE]     # deploys, runs, destroys
  python3 scripts/nxos_live_mustfail.py --check FILE                       # only check an existing report

A "MUST FAIL" check passes this gate only if it failed on usable device state: its last sample must not be
`unready` (a node that never answered fails every check, which proves nothing). Every "MUST PASS" check must
pass, and every check type needs at least one of each. The lab is a VM: take the vendor-VM lab lock first
(/home/ndr/vendor-vm-lab.lock). The lab is named ndr-nxos-mf and only that name is destroyed.
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LAB = ROOT / "scripts" / "labs" / "nxos-cap"
CHECK_TYPES = ("bgp_session", "bgp_prefixes", "route", "bgp_route", "ping")


def verify(report: dict) -> list[str]:
    """Every way the run falls short of the gate; [] when it meets it."""
    problems = []
    if report.get("status") not in ("failed", "passed"):
        problems.append(f"run status is {report.get('status')!r} ({report.get('error') or report.get('inconclusive_reason')}): "
                        "no verdict to check")
    kinds: dict[str, set[str]] = {t: set() for t in CHECK_TYPES}
    for c in report.get("checks", []):
        name, kind = c["name"], ("fail" if c["name"].startswith("MUST FAIL") else
                                 "pass" if c["name"].startswith("MUST PASS") else None)
        if kind is None:
            problems.append(f"{name}: not named MUST FAIL or MUST PASS")
            continue
        kinds.setdefault(c["type"], set()).add(kind)
        last = (c.get("history") or [{}])[-1]
        if kind == "fail" and c["passed"]:
            problems.append(f"{name}: PASSED ({c['detail']})")
        elif kind == "fail" and last.get("unready"):
            problems.append(f"{name}: failed without usable state ({c['detail']}): proves nothing")
        elif kind == "pass" and not c["passed"]:
            problems.append(f"{name}: failed ({c['detail']})")
    for t in CHECK_TYPES:
        missing = {"fail", "pass"} - kinds.get(t, set())
        if missing:
            problems.append(f"{t}: no {' and no '.join(sorted(f'MUST {m.upper()}' for m in missing))} check ran")
    return problems


def run(report_path: Path) -> int:
    work = Path(tempfile.mkdtemp(prefix="ndr-nxos-mf-", dir=Path.home()))
    try:
        shutil.copytree(LAB, work / "lab")
        topo = work / "lab" / "topology.clab.yml"
        topo.write_text(topo.read_text(encoding="utf-8").replace("name: ndr-nxos-cap", "name: ndr-nxos-mf"), encoding="utf-8")
        cmd = [sys.executable, "-m", "netdryrun", "run", str(work / "lab" / "mustfail.yml"), "--json", str(report_path)]
        print("running:", " ".join(cmd), flush=True)
        return subprocess.run(cmd).returncode
    finally:
        shutil.rmtree(work, ignore_errors=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--report", type=Path, default=Path.home() / "nxos-mustfail.json")
    ap.add_argument("--check", type=Path, help="check this report instead of running the lab")
    a = ap.parse_args()
    path = a.check or a.report
    if not a.check:
        rc = run(path)
        print(f"netdryrun exit code {rc}")
    report = json.loads(path.read_text(encoding="utf-8"))
    for c in report.get("checks", []):
        print(f"{'ok ' if c['passed'] == c['name'].startswith('MUST PASS') else 'BAD'} {c['type']:12} "
              f"{c['name'][:60]:60} {c['detail'][:70]}")
    problems = verify(report)
    for p in problems:
        print("PROBLEM:", p)
    print("live must-fail gate:", "MET" if not problems else f"NOT MET ({len(problems)} problems)")
    return 0 if not problems else 1


if __name__ == "__main__":
    sys.exit(main())
