#!/usr/bin/env python3
"""Live must-fail coverage for the RouterOS driver: run scripts/labs/routeros-cap/mustfail.yml on a live CHR and check
every verdict, by the same rules as the NX-OS gate (scripts/nxos_live_mustfail.py).

  PYTHONPATH=src python3 scripts/routeros_live_mustfail.py [--report FILE]     # deploys, runs, destroys
  python3 scripts/routeros_live_mustfail.py --check FILE                       # only check an existing report

The lab is a VM: take the vendor-VM lab lock first (/home/ndr/vendor-vm-lab.lock). The lab is named ndr-routeros-mf
and only that name is destroyed.
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from nxos_live_mustfail import verify  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
LAB = ROOT / "scripts" / "labs" / "routeros-cap"


def run(report_path: Path) -> int:
    work = Path(tempfile.mkdtemp(prefix="ndr-routeros-mf-", dir=Path.home()))
    try:
        shutil.copytree(LAB, work / "lab")
        topo = work / "lab" / "topology.clab.yml"
        topo.write_text(topo.read_text(encoding="utf-8").replace("name: ndr-routeros-cap", "name: ndr-routeros-mf"),
                        encoding="utf-8")
        cmd = [sys.executable, "-m", "netdryrun", "run", str(work / "lab" / "mustfail.yml"), "--json", str(report_path)]
        print("running:", " ".join(cmd), flush=True)
        return subprocess.run(cmd).returncode
    finally:
        shutil.rmtree(work, ignore_errors=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--report", type=Path, default=Path.home() / "routeros-mustfail.json")
    ap.add_argument("--check", type=Path, help="check this report instead of running the lab")
    a = ap.parse_args()
    path = a.check or a.report
    if not a.check:
        print(f"netdryrun exit code {run(path)}")
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
