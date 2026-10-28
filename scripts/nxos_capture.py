#!/usr/bin/env python3
"""Run NX-OS commands on a cisco_n9kv node the way the nxos driver does (NX-API from inside the
container), for exploration and for capturing test fixtures.

  PYTHONPATH=src python3 scripts/nxos_capture.py CONTAINER "show version"            # print the reply
  PYTHONPATH=src python3 scripts/nxos_capture.py CONTAINER --ascii "ping 10.0.1.2"    # cli_ascii
  PYTHONPATH=src python3 scripts/nxos_capture.py CONTAINER --save NAME "show ..."     # tests/fixtures/nxos_NAME.txt

Every saved fixture is listed in tests/fixtures/nxos_captures.tsv with its command, rc and image version.
"""
from __future__ import annotations

import argparse
import datetime
import json
import subprocess
import sys
from pathlib import Path

from netdryrun.drivers.nxos import HELPER

FIX = Path(__file__).resolve().parent.parent / "tests" / "fixtures"


def run(container: str, method: str, command: str, timeout: float = 60) -> subprocess.CompletedProcess:
    return subprocess.run(["docker", "exec", container, "python3", "-c", HELPER, method, command, str(timeout)],
                          capture_output=True, text=True, timeout=timeout + 30)


def image(container: str) -> str:
    r = subprocess.run(["docker", "inspect", "-f", "{{.Config.Image}}", container], capture_output=True, text=True)
    return r.stdout.strip()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("container")
    ap.add_argument("command")
    ap.add_argument("--ascii", action="store_true", help="method cli_ascii (text) instead of cli (JSON)")
    ap.add_argument("--save", metavar="NAME")
    a = ap.parse_args()
    method = "cli_ascii" if a.ascii else "cli"
    r = run(a.container, method, a.command)
    if a.save:
        (FIX / f"nxos_{a.save}.txt").write_text(r.stdout)
        with open(FIX / "nxos_captures.tsv", "a") as f:
            f.write("\t".join([f"nxos_{a.save}.txt", method, a.command, str(r.returncode), image(a.container),
                               datetime.date.today().isoformat()]) + "\n")
    try:
        print(json.dumps(json.loads(r.stdout), indent=1))
    except ValueError:
        print(r.stdout)
    if r.stderr:
        print(f"[stderr] {r.stderr.strip()}", file=sys.stderr)
    print(f"[rc] {r.returncode}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
