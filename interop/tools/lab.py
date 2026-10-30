"""Drive the interop labs on the lab VM (run under the lab lock, from tools/run_<lab>.sh).

    lab.py fresh LAB VARIANT TAG [--keep]   build, `netdryrun run`, JSON to results/LAB/VARIANT-fresh-TAG.json
    lab.py check LAB VARIANT TAG            `netdryrun check` (check.yml, short timeout) on the running lab
    lab.py apply LAB OVERLAY                change the running lab (overlay's `apply`), then wait for it to spread
    lab.py revert LAB OVERLAY               undo it (overlay's `revert`), then wait
    lab.py probe LAB OVERLAY TAG            raw state the overlay names, to results/LAB/VARIANT-probe-TAG.txt
    lab.py destroy LAB                      containerlab destroy --cleanup of this lab's own topology

Only containers named clab-<this lab's name>-<node> are ever touched.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build import LABS, build, overlays  # noqa: E402

HERE = Path(__file__).resolve().parents[1]
BUILD = Path(os.path.expanduser("~/interop/build"))
RESULTS = HERE / "results"
VENV = Path(os.path.expanduser("~/interop/venv/bin"))
SPREAD = 45   # seconds after a change before checks run: route-map timers, MRAI, EOS policy re-evaluation
VM_SSH = ["ssh", "-q", "-i", "/root/.ssh/sshkey", "-o", "StrictHostKeyChecking=no", "-o", "BatchMode=yes",
          "root@176.1.1.1"]


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def labname(lab: str) -> str:
    return yaml.safe_load((BUILD / lab / "base" / "topology.clab.yml").read_text())["name"]


def container(lab: str, node: str) -> str:
    return f"clab-{labname(lab)}-{node}"


def sh(cmd: list[str], stdin: str | None = None, timeout: float = 300) -> subprocess.CompletedProcess:
    r = subprocess.run(cmd, input=stdin, capture_output=True, text=True, timeout=timeout)
    log(f"$ {' '.join(cmd)[:160]} -> rc={r.returncode}")
    out = (r.stdout + r.stderr).strip()
    if out:
        print("   " + out[-1500:].replace("\n", "\n   "), flush=True)
    return r


def dexec(lab: str, node: str, args: list[str], stdin: str | None = None, timeout: float = 300):
    return sh(["docker", "exec", *(["-i"] if stdin is not None else []), container(lab, node), *args], stdin, timeout)


def run_step(lab: str, step: dict) -> bool:
    node = step["node"]
    if "vtysh" in step:
        args = ["vtysh", "-c", "conf t"]
        for line in step["vtysh"]:
            args += ["-c", line]
        ok = dexec(lab, node, args).returncode == 0
        dexec(lab, node, ["vtysh", "-c", "clear bgp * soft"])
        return ok
    if "vtysh_file" in step:
        src = HERE / Path(LABS[lab][2]).parent / step["vtysh_file"]
        tmp = Path("/tmp") / f"ndr-interop-{lab}-{src.name}"
        tmp.write_bytes(src.read_bytes().replace(b"\r\n", b"\n"))
        sh(["docker", "cp", str(tmp), f"{container(lab, node)}:/tmp/ndr-overlay.conf"])
        ok = dexec(lab, node, ["vtysh", "-f", "/tmp/ndr-overlay.conf"], timeout=900).returncode == 0
        dexec(lab, node, ["vtysh", "-c", "clear bgp * soft"])
        return ok
    if "eos" in step:
        return dexec(lab, node, ["Cli", "-p", "15", "-c", "configure\n" + "\n".join(step["eos"]) + "\nend\n"]).returncode == 0
    if "srl" in step:
        text = "enter candidate private\n" + "\n".join(step["srl"]) + "\ncommit now\nquit\n"
        return dexec(lab, node, ["sr_cli"], stdin=text).returncode == 0
    if "junos" in step:
        lines = step["junos"] if isinstance(step["junos"], list) else [step["junos"]]
        text = "configure private\n" + "\n".join(lines) + "\ncommit and-quit\nexit\n"
        return dexec(lab, node, [*VM_SSH, "cli"], stdin=text, timeout=600).returncode == 0
    if "junos_op" in step:
        return dexec(lab, node, [*VM_SSH, f"cli -c '{step['junos_op']} | no-more'"]).returncode == 0
    raise SystemExit(f"unknown step {step}")


def probe_cmd(step: dict) -> list[str]:
    if "junos" in step:
        return [*VM_SSH, f"cli -c '{step['junos']} | no-more'"]
    if "srl" in step:
        return ["sr_cli", step["srl"]]
    if "eos" in step:
        return ["Cli", "-p", "15", "-c", step["eos"]]
    if "vtysh1" in step:
        return ["vtysh", "-c", step["vtysh1"]]
    raise SystemExit(f"unknown probe {step}")


def main(argv: list[str]) -> int:
    op, lab = argv[0], argv[1]
    (RESULTS / lab).mkdir(parents=True, exist_ok=True)
    if op in ("fresh", "refusal") or not (BUILD / lab / "base" / "check.yml").exists():
        build(lab, "base", BUILD / lab / "base")   # only between labs: a running lab's dir is left alone
    nd = str(VENV / "netdryrun")
    if op == "fresh":
        variant, tag = argv[2], argv[3]
        d = build(lab, variant, BUILD / lab / variant)
        out = RESULTS / lab / f"{variant}-fresh-{tag}.json"
        log(f"FRESH {lab} {variant} #{tag} -> {out.name}")
        t0 = time.time()
        r = subprocess.run([nd, "run", str(d / "netdryrun.yml"), "--json", str(out), "--no-step-summary",
                            *(["--keep"] if "--keep" in argv else [])])
        log(f"FRESH {lab} {variant} #{tag} exit {r.returncode} in {time.time() - t0:.0f}s")
        return r.returncode
    if op == "refusal":
        cid = argv[2]
        out = RESULTS / lab / f"refuse{cid}-refusal-1.json"
        before = subprocess.run(["docker", "ps", "-a", "-q"], capture_output=True, text=True).stdout.split()
        r = subprocess.run([nd, "run", str(BUILD / lab / "base" / f"refuse-{cid}.yml"), "--json", str(out),
                            "--no-step-summary"], capture_output=True, text=True)
        after = subprocess.run(["docker", "ps", "-a", "-q"], capture_output=True, text=True).stdout.split()
        v = subprocess.run([nd, "validate", str(BUILD / lab / "base" / f"refuse-{cid}.yml")], capture_output=True, text=True)
        log(f"REFUSAL {lab} {cid}: run exit {r.returncode}, containers before/after {len(before)}/{len(after)}; "
            f"validate exit {v.returncode}")
        print("   run: " + (r.stdout + r.stderr).strip()[-600:])
        print("   validate: " + (v.stdout + v.stderr).strip()[-400:])
        return r.returncode
    if op == "check":
        variant, tag = argv[2], argv[3]
        out = RESULTS / lab / f"{variant}-reapply-{tag}.json"
        log(f"CHECK {lab} {variant} #{tag} -> {out.name}")
        t0 = time.time()
        r = subprocess.run([nd, "check", str(BUILD / lab / "base" / "check.yml"), "--json", str(out), "--no-step-summary"])
        log(f"CHECK {lab} {variant} #{tag} exit {r.returncode} in {time.time() - t0:.0f}s")
        return r.returncode
    if op in ("apply", "revert"):
        ov = overlays(lab)[argv[2]]
        ok = all([run_step(lab, s) for s in ov[op]])
        wait = ov.get("spread", SPREAD)
        log(f"{op.upper()} {lab} {argv[2]}: {'ok' if ok else 'A STEP FAILED'}; waiting {wait}s")
        time.sleep(wait)
        return 0 if ok else 5
    if op == "probe":
        ov, tag = overlays(lab)[argv[2]], argv[3]
        out = RESULTS / lab / f"{argv[2]}-probe-{tag}.txt"
        with out.open("w") as f:
            for s in ov.get("probe", []):
                r = subprocess.run(["docker", "exec", container(lab, s["node"]), *probe_cmd(s)], capture_output=True,
                                   text=True, timeout=120)
                f.write(f"===== {s['node']}: {' '.join(probe_cmd(s))[-120:]}\n{r.stdout}{r.stderr}\n")
        log(f"PROBE {lab} {argv[2]} -> {out.name}")
        return 0
    if op == "destroy":
        topo = BUILD / lab / "base" / "topology.clab.yml"
        return subprocess.run(["containerlab", "destroy", "-t", str(topo), "--cleanup"]).returncode
    raise SystemExit(__doc__)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
