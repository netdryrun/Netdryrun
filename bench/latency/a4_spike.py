"""A4 spike (not part of the product): restore a pristine CHR from a containerlab snapshot, apply the candidate config,
and time it against a cold boot. Run on the lab machine, under the lab lock, from a checkout:

    python bench/latency/a4_spike.py --work ~/work/a4spike --snapshots ~/ndr-snapshots/a4 --restores 3

Snapshots stay on this machine (they hold a vendor VM's disk and memory): never commit, upload or share them.
Writes <work>/a4.jsonl, one line per step, and prints a summary.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from netdryrun.drivers.base import DriverError  # noqa: E402
from netdryrun.drivers.routeros import RouterosDriver  # noqa: E402
from netdryrun.lab import Lab  # noqa: E402

EXAMPLE = ROOT / "examples" / "mikrotik"
NDR = shutil.which("netdryrun") or "netdryrun"


def sh(cmd: list[str], timeout: float = 1800) -> tuple[int, str, float]:
    t0 = time.monotonic()
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    return p.returncode, (p.stdout + p.stderr)[-4000:], round(time.monotonic() - t0, 1)


def log(out: Path, **row) -> None:
    print(json.dumps(row), flush=True)
    with out.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row) + "\n")


def lab_dir(work: Path, name: str, startup: bool, rsc: str | None = None) -> Path:
    d = work / name
    if d.exists():
        shutil.rmtree(d)
    shutil.copytree(EXAMPLE, d)
    topo = d / "topology.clab.yml"
    text = topo.read_text(encoding="utf-8").replace("name: ndr-mikrotik-frr", f"name: {name}")
    if not startup:
        text = text.replace("      startup-config: configs/r1.rsc\n", "")
    topo.write_text(text, encoding="utf-8")
    if rsc is not None:
        (d / "configs" / "r1.rsc").write_text(rsc, encoding="utf-8")
    return d


def wait_rest(lab: Lab, timeout: float = 900) -> float | None:
    """Seconds until RouterOS answers GET /system/resource over REST inside the container."""
    t0 = time.monotonic()
    drv = RouterosDriver(lab, "r1")
    while time.monotonic() - t0 < timeout:
        try:
            drv._rest("GET", "/system/resource", [], timeout=20)
            return round(time.monotonic() - t0, 1)
        except DriverError:
            time.sleep(2)
    return None


def apply_rsc(lab: Lab, rsc: str) -> tuple[float, list[str], str]:
    """Apply the candidate at runtime: write it as a file over REST, /import it, and read the import's errors from the
    log. Returns (seconds, errors, how)."""
    drv = RouterosDriver(lab, "r1")
    t0 = time.monotonic()
    body = json.dumps({"name": "candidate.rsc", "contents": rsc})
    ev: list = []
    errors: list[str] = []
    how = "PUT /file + POST /import"
    try:
        drv._rest("PUT", "/file", ev, body=body)
    except DriverError as e:   # no /file add on this release: run the script itself
        how = f"POST /execute (PUT /file failed: {e})"
        try:
            drv._rest("POST", "/execute", ev, body=json.dumps({"script": rsc}), timeout=120)
        except DriverError as e2:
            errors.append(str(e2))
    else:
        try:
            drv._rest("POST", "/import", ev, body=json.dumps({"file-name": "candidate.rsc"}), timeout=120)
        except DriverError as e:
            errors.append(str(e))
    rows = drv._rows("/log", [])
    errors += [r["message"] for r in rows if "error" in str(r.get("topics", "")) and "candidate" in str(r.get("message", ""))]
    done = any("NDR r1.rsc imported to the last line" in str(r.get("message", "")) for r in rows)
    if not done:
        errors.append("the import never reached its last line (no marker in the log)")
    return round(time.monotonic() - t0, 1), errors, how


def run_checks(d: Path, deploy: bool, out_json: Path) -> dict:
    cmd = [NDR, "run" if deploy else "check", str(d), "--json", str(out_json), "--no-step-summary"]
    rc, text, secs = sh(cmd)
    try:
        rep = json.loads(out_json.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"exit": rc, "seconds": secs, "status": None, "tail": text[-800:]}
    return {"exit": rc, "seconds": secs, "status": rep["status"], "error": rep.get("error"),
            "failed": [c["name"] for c in rep["checks"] if not c["passed"]],
            "passed": sum(c["passed"] for c in rep["checks"]), "timings": rep.get("timings"),
            "config_load": {n: v.get("config_load") for n, v in rep["environment"].get("nodes", {}).items()}}


def license_id(lab: Lab) -> str | None:
    try:
        obj = RouterosDriver(lab, "r1")._rest("GET", "/system/license", []).obj
        return (obj or {}).get("software-id") or (obj or {}).get("system-id")
    except DriverError:
        return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--work", required=True)
    ap.add_argument("--snapshots", required=True)
    ap.add_argument("--restores", type=int, default=3)
    ap.add_argument("--skip-cold", action="store_true")
    a = ap.parse_args()
    work, snaps = Path(a.work).expanduser(), Path(a.snapshots).expanduser()
    work.mkdir(parents=True, exist_ok=True)
    snaps.mkdir(parents=True, exist_ok=True)
    out = work / "a4.jsonl"
    good = (EXAMPLE / "configs" / "r1.rsc").read_text(encoding="utf-8")
    # A broken candidate: r1 loses its own static default, so the check that wants it fails
    broken = good.replace('/ip route add dst-address=0.0.0.0/0 blackhole comment="static default"\n', "")
    assert broken != good

    # 1. cold references: the example as it is, and with the broken r1 config
    if not a.skip_cold:
        for label, rsc in (("good", good), ("broken", broken)):
            d = lab_dir(work, "ndr-a4-cold", startup=True, rsc=rsc)
            log(out, step="cold", change=label, **run_checks(d, True, work / f"cold-{label}.json"))

    # 2. a pristine CHR: booted with no startup config, then snapshotted
    d = lab_dir(work, "ndr-a4-pristine", startup=False)
    topo = d / "topology.clab.yml"
    rc, text, secs = sh(["containerlab", "deploy", "-t", str(topo), "--reconfigure"])
    lab = Lab(topo)
    up = wait_rest(lab)
    log(out, step="pristine-deploy", rc=rc, deploy_s=secs, rest_answers_after_s=up, license=license_id(lab))
    time.sleep(20)   # let RouterOS finish starting its services before the memory is saved
    rc, text, secs = sh(["containerlab", "tools", "snapshot", "save", "-t", str(topo), "--node-filter", "r1",
                         "--output-dir", str(snaps)])
    tar = snaps / "r1.tar"
    log(out, step="snapshot-save", rc=rc, seconds=secs, bytes=tar.stat().st_size if tar.exists() else None,
        tail=text[-600:])
    sh(["containerlab", "destroy", "-t", str(topo), "--cleanup"])
    if rc != 0 or not tar.exists():
        return 1

    # 3. restore it, apply the candidate at runtime, run the checks on the lab as it is (`check`)
    for i in range(a.restores):
        for label, rsc in (("good", good), ("broken", broken)) if i == 0 else (("good", good),):
            t0 = time.monotonic()
            rc, text, secs = sh(["containerlab", "deploy", "-t", str(topo), "--reconfigure", "--restore", f"r1={tar}"])
            lab = Lab(topo)
            up = wait_rest(lab)
            boot_log = subprocess.run(["docker", "logs", lab.nodes["r1"].container], capture_output=True, text=True)
            restored = "Restoring from snapshot" in (boot_log.stdout + boot_log.stderr)
            try:
                apply_s, errors, how = apply_rsc(lab, rsc)
            except DriverError as e:
                apply_s, errors, how = None, [str(e)], "failed"
            checks = run_checks(d, False, work / f"restore-{i}-{label}.json")
            total = round(time.monotonic() - t0, 1)
            log(out, step="restore", trial=i, change=label, rc=rc, deploy_s=secs, rest_answers_after_s=up,
                restored_from_snapshot=restored, apply_s=apply_s, apply_errors=errors, apply=how, checks=checks,
                total_to_verdict_s=total, license=license_id(lab),
                deploy_tail=re.sub(r"\x1b\[[0-9;]*m", "", text)[-400:] if rc else "")
            sh(["containerlab", "destroy", "-t", str(topo), "--cleanup"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
