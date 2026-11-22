"""Live capture, timed: corpus v1 case 19's pe1, Docker's own default deleted (the one Docker put there at deploy) with
the same commands as mgmt._delete_linux, inside the node, and the whole IPv4 table read in a tight loop right after,
each read stamped with the node's /proc/uptime (10 ms). Then 60 s of 0.5 s samples from outside.

    PYTHONPATH=src python capture_timed.py <topology> <out dir> lab-default|no-lab-default

no-lab-default: up1 stops originating its default to pe1 first, and the capture waits until pe1's BGP default has
left the kernel (198.51.100.0/24 still over Docker's default), so nothing in the lab can resolve the next hop.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

from netdryrun import mgmt
from netdryrun.lab import Lab

NODE = "pe1"
PREFIX = "198.51.100.0/24"


def main() -> int:
    topo, out, mode = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3]
    out.mkdir(parents=True, exist_ok=True)
    lab = Lab(topo)
    answers: dict = {"mode": mode}

    def sh(node, cmd):
        r = lab.exec_root(node, cmd, timeout=120)
        return r.stdout + (f"\n[stderr] {r.stderr}" if r.stderr.strip() else "") + ("" if r.rc == 0 else f"\n[rc={r.rc}]")

    def vt(node, c):
        return sh(node, ["vtysh", "-c", c])

    def snap(tag):
        answers[tag] = {
            "ip -4 route show table all": sh(NODE, ["ip", "-4", "route", "show", "table", "all"]),
            "ip -6 route show table all": sh(NODE, ["ip", "-6", "route", "show", "table", "all"]),
            "show ip nht": vt(NODE, "show ip nht"),
            f"show bgp ipv4 unicast {PREFIX}": vt(NODE, f"show bgp ipv4 unicast {PREFIX}"),
            f"show ip route {PREFIX}": vt(NODE, f"show ip route {PREFIX}"),
            "show ip route 0.0.0.0/0": vt(NODE, "show ip route 0.0.0.0/0"),
        }

    insp = lab.docker_inspect(NODE)
    (out / "inspect_pe1.json").write_text(json.dumps(
        {"HostConfig": {"NetworkMode": insp["HostConfig"]["NetworkMode"]},
         "NetworkSettings": {"Networks": insp["NetworkSettings"]["Networks"]}}, indent=1) + "\n", encoding="utf-8")
    snap("before")
    if mode == "no-lab-default":
        answers["up1 stops default-originate"] = sh("up1", [
            "vtysh", "-c", "configure terminal", "-c", "router bgp 65200", "-c", "address-family ipv4 unicast",
            "-c", "no neighbor 10.0.2.1 default-originate", "-c", "end"])
        t0 = time.monotonic()
        while time.monotonic() - t0 < 60:
            if 'Known via "bgp"' not in vt(NODE, "show ip route 0.0.0.0/0"):   # zebra's RIB, not only the kernel
                break
            time.sleep(0.5)
        answers["waited for the BGP default to leave (s)"] = round(time.monotonic() - t0, 2)
        time.sleep(5)
        snap("lab default gone")

    m = mgmt.docker_mgmt(lab, NODE)
    mgmt._linux_devices(lab, m)
    docker, other = mgmt.classify_linux(mgmt._scan_linux(lab, m), m)
    answers["classified before the delete"] = {"docker": [r.line for r in docker], "other": [r.line for r in other]}
    dels = "; ".join(f"echo \"@del{r.family} $(cut -d' ' -f1 /proc/uptime)\"; "
                     f"ip -{r.family} route del default via {r.via} dev {r.dev}" for r in docker)
    script = (f"{dels}; for i in $(seq 1 300); do echo \"@ $(cut -d' ' -f1 /proc/uptime)\"; "
              f"ip -4 route show table all; done")
    answers["timed delete"] = sh(NODE, ["sh", "-c", script])
    rows, t0 = [], time.monotonic()
    while True:
        t = time.monotonic() - t0
        rows.append({"t": round(t, 3), "v4": sh(NODE, ["ip", "-4", "route", "show", "table", "all"]),
                     "v6": sh(NODE, ["ip", "-6", "route", "show", "table", "all"])})
        if t >= 60:
            break
        time.sleep(max(0.0, 0.5 - ((time.monotonic() - t0) - t)))
    (out / "samples_after_delete.json").write_text(json.dumps(rows, indent=1) + "\n", encoding="utf-8")
    snap("after_60s")
    (out / "answers.json").write_text(json.dumps(answers, indent=1) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
