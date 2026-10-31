"""Capture the FRR fixtures of tests/fixtures/verify from a live lab (tests/fixtures/verify-lab).

    sudo containerlab deploy -t tests/fixtures/verify-lab/topology.clab.yml
    PYTHONPATH=src python scripts/capture_verify_fixtures.py [--out tests/fixtures/verify]
    sudo containerlab destroy -t tests/fixtures/verify-lab/topology.clab.yml --cleanup

It runs verify's own FRR collector on edge1 (so the commands are exactly the ones a snapshot runs), waits until
every session but the one that never comes up is established and two collections are identical, and writes
each command's raw output to one file, under a first line naming the command, the FRR version and the date.
"""
from __future__ import annotations

import argparse
import datetime
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from netdryrun.verify import frr  # noqa: E402

CONTAINER = "clab-ndr-vfy-fixtures-edge1"
NEVER_UP = {("default", "10.0.9.2")}
HEADER = "# live capture: {version}, node edge1 of tests/fixtures/verify-lab, `vtysh -c '{cmd}'`, {date}"


def exec_fn(node: str, argv: list[str]) -> tuple[int, str, str]:
    p = subprocess.run(["docker", "exec", CONTAINER, *argv], capture_output=True, text=True, timeout=60)
    return p.returncode, p.stdout, p.stderr


def file_name(cmd: str) -> str:
    fixed = {frr.VRF_CMD: "show_vrf.txt", frr.NEIGHBORS_CMD: "neighbors.txt",
             frr.ROUTE_CMDS["ipv4"]: "route_v4.txt", frr.ROUTE_CMDS["ipv6"]: "route_v6.txt",
             frr.BGP_CMDS["ipv4"]: "bgp_v4_detail.txt", frr.BGP_CMDS["ipv6"]: "bgp_v6_detail.txt",
             frr.CONFIG_CMD: "running_config.txt"}
    if cmd in fixed:
        return fixed[cmd]
    # show bgp [vrf V] <afi> unicast neighbors N advertised-routes|received-routes detail json
    words = cmd.split()
    vrf = words[words.index("vrf") + 1] if "vrf" in words else "default"
    afi = words[words.index("unicast") - 1]
    nbr = words[words.index("neighbors") + 1].replace(":", "_")
    way = "out" if "advertised-routes" in words else "in"
    return f"adj_{way}_{vrf}_{afi}_{nbr}.txt"


def ready(ns) -> list[str]:
    """Sessions that should be up and aren't."""
    return [f"{k.vrf} {k.neighbor}" for k, v in ns.items.items()
            if k.kind == "session" and not v.established and (k.vrf, k.neighbor) not in NEVER_UP]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", default=str(ROOT / "tests" / "fixtures" / "verify"))
    ap.add_argument("--timeout", type=float, default=240)
    ap.add_argument("--settle", type=float, default=15)
    ap.add_argument("--only", action="append", default=[], metavar="CMD",
                    help="write only this command's fixture (repeat for several): the others stay as captured")
    args = ap.parse_args()
    rc, ver, _ = exec_fn("edge1", ["vtysh", "-c", "show version"])
    version = next((" ".join(ln.split()[:2]) for ln in ver.splitlines() if ln.strip().startswith("FRRouting")), "")
    if rc != 0 or not version:
        print(f"no FRR version from {CONTAINER} (is the lab up?)", file=sys.stderr)
        return 2
    deadline = time.monotonic() + args.timeout
    last = None
    while True:
        raw: list[dict] = []
        try:
            ns = frr.FrrCollector("edge1", exec_fn)._collect(raw)
        except frr.CommandFailed as e:
            ns, why = None, str(e)
        except frr.SnapshotError as e:
            # the parser refused real output: keep what was read, so the difference can be studied
            write(Path(args.out) / "refused", raw, version)
            print(f"the collector refused the live output: {e}; raw outputs in {Path(args.out) / 'refused'}",
                  file=sys.stderr)
            return 1
        else:
            down = ready(ns)
            why = f"sessions not established: {down}" if down else ""
        if ns is not None and not why and last is not None and ns.items == last.items:
            break
        if time.monotonic() > deadline:
            print(f"the lab did not settle: {why or 'the snapshot kept moving'}", file=sys.stderr)
            return 3
        last = ns if not why else None
        time.sleep(args.settle)
    raw = [r for r in ns.raw if not args.only or r["cmd"].removeprefix("vtysh -c '").removesuffix("'") in args.only]
    write(Path(args.out), raw, version)
    print(f"{len(ns.raw)} outputs from {version}; {len(ns.items)} snapshot items")
    return 0


def write(out: Path, raw: list[dict], version: str) -> None:
    date = datetime.date.today().isoformat()
    out.mkdir(parents=True, exist_ok=True)
    for r in raw:
        cmd = r["cmd"].removeprefix("vtysh -c '").removesuffix("'")
        (out / file_name(cmd)).write_text(HEADER.format(version=version, cmd=cmd, date=date) + "\n" + r["output"],
                                          encoding="utf-8")
        print(f"{file_name(cmd)}: {cmd}")


if __name__ == "__main__":
    sys.exit(main())
