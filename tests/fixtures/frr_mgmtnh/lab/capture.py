"""Live capture: corpus v1 case 19 (next-hop-self removed on pe2 toward pe1), what pe1's routes over the management
network do when Docker's default route is deleted.

Run from the repository root after `corpus/run.py --case 19 --keep --workdir <W>` left the lab up:

    PYTHONPATH=src python capture.py <W>/19-nexthop-self-removed/topology.clab.yml <out dir> [--extras]

Every answer is saved as the exact text `docker exec` returned. The delete is the product's own (mgmt._delete_linux on
the routes mgmt.classify_linux calls Docker's). Then pe1's `ip -4/-6 route show table all` is read every 0.5 s for
60 s. With --extras, after that: a kernel static and an FRR static via the management gateway are added (they must
stay over management), then Docker's default is put back by hand (as a NOS bringing eth0 up again would) and sampled.
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
    topo, out = Path(sys.argv[1]), Path(sys.argv[2])
    extras = "--extras" in sys.argv
    out.mkdir(parents=True, exist_ok=True)
    lab = Lab(topo)
    answers: dict = {}

    def sh(node: str, cmd: list[str]) -> str:
        r = lab.exec_root(node, cmd, timeout=60)
        return r.stdout + (f"\n[stderr] {r.stderr}" if r.stderr.strip() else "") + ("" if r.rc == 0 else f"\n[rc={r.rc}]")

    def vtysh(node: str, c: str) -> str:
        return sh(node, ["vtysh", "-c", c])

    def snap(tag: str) -> None:
        a = {}
        for n in sorted(lab.nodes):
            a[n] = {"ip -4 route show table all": sh(n, ["ip", "-4", "route", "show", "table", "all"]),
                    "ip -6 route show table all": sh(n, ["ip", "-6", "route", "show", "table", "all"])}
        a[NODE].update({
            "ip addr show": sh(NODE, ["ip", "addr", "show"]),
            "show ip nht": vtysh(NODE, "show ip nht"),
            f"show bgp ipv4 unicast {PREFIX}": vtysh(NODE, f"show bgp ipv4 unicast {PREFIX}"),
            f"show ip route {PREFIX}": vtysh(NODE, f"show ip route {PREFIX}"),
            "show ip route 0.0.0.0/0": vtysh(NODE, "show ip route 0.0.0.0/0"),
            "show ipv6 route ::/0": vtysh(NODE, "show ipv6 route ::/0"),
            "show ip route": vtysh(NODE, "show ip route"),
        })
        answers[tag] = a

    def sample(tag: str, seconds: float, step: float = 0.5) -> list[dict]:
        rows, t0 = [], time.monotonic()
        while True:
            t = time.monotonic() - t0
            rows.append({"t": round(t, 3),
                         "v4": sh(NODE, ["ip", "-4", "route", "show", "table", "all"]),
                         "v6": sh(NODE, ["ip", "-6", "route", "show", "table", "all"])})
            if t >= seconds:
                break
            time.sleep(max(0.0, step - ((time.monotonic() - t0) - t)))
        (out / f"samples_{tag}.json").write_text(json.dumps(rows, indent=1) + "\n", encoding="utf-8")
        return rows

    insp = lab.docker_inspect(NODE)
    (out / "inspect_pe1.json").write_text(json.dumps(
        {"HostConfig": {"NetworkMode": insp["HostConfig"]["NetworkMode"]},
         "NetworkSettings": {"Networks": insp["NetworkSettings"]["Networks"]}}, indent=1) + "\n", encoding="utf-8")
    answers["versions"] = {"pe1 show version": vtysh(NODE, "show version")}
    snap("before")

    m = mgmt.docker_mgmt(lab, NODE)
    mgmt._linux_devices(lab, m)
    docker, other = mgmt.classify_linux(mgmt._scan_linux(lab, m), m)
    deleted = {"docker": [r.line for r in docker], "other": [r.line for r in other], "devices": sorted(m.devices)}
    t_del = time.monotonic()
    mgmt._delete_linux(lab, m, docker)
    deleted["delete_seconds"] = round(time.monotonic() - t_del, 3)
    (out / "delete.json").write_text(json.dumps(deleted, indent=1) + "\n", encoding="utf-8")
    sample("after_delete", 60.0)
    snap("after_60s")

    if extras:
        # a user's own routes via the management gateway: they must stay over management (a run error, never waited out)
        gw = str(m.gateways[0])
        answers["add kernel static"] = sh(NODE, ["ip", "route", "add", "10.77.0.0/16", "via", gw, "dev", "eth0",
                                                 "proto", "static"])
        answers["add frr static"] = vtysh(NODE, f"configure terminal\nip route 10.78.0.0/16 {gw}\nend")
        answers["add frr static (vtysh -c form)"] = sh(NODE, ["vtysh", "-c", "configure terminal", "-c",
                                                              f"ip route 10.78.0.0/16 {gw}", "-c", "end"])
        sample("statics", 15.0)
        snap("statics")
        sh(NODE, ["ip", "route", "del", "10.77.0.0/16", "via", gw, "dev", "eth0"])
        answers["del frr static"] = sh(NODE, ["vtysh", "-c", "configure terminal", "-c",
                                              f"no ip route 10.78.0.0/16 {gw}", "-c", "end"])
        sample("statics_removed", 10.0)
        # Docker's default back (as SONiC VS brings eth0 up again): does the BGP route come back over management?
        answers["re-add docker default"] = sh(NODE, ["ip", "route", "add", "default", "via", gw, "dev", "eth0"])
        sample("readded", 30.0)
        snap("readded")
        docker2, _ = mgmt.classify_linux(mgmt._scan_linux(lab, m), m)
        t_del = time.monotonic()
        mgmt._delete_linux(lab, m, docker2)
        answers["second delete"] = {"docker": [r.line for r in docker2], "seconds": round(time.monotonic() - t_del, 3)}
        sample("after_second_delete", 30.0)
        snap("end")
        # millisecond timing, inside the node: Docker's default back, wait until the BGP route is over it again, then
        # the same `ip route del` as mgmt._delete_linux, and the route read in a tight loop (stamped by the node's clock)
        for k in range(3):
            script = (f"ip route add default via {gw} dev eth0; "
                      f"for i in $(seq 1 100); do ip -4 route show {PREFIX} | grep -q 'dev eth0' && break; sleep 0.1; "
                      f"done; echo \"# before: $(ip -4 route show {PREFIX})\"; "
                      f"echo \"@del4 $(date +%s.%N)\"; ip -4 route del default via {gw} dev eth0; "
                      f"for i in $(seq 1 400); do echo \"@ $(date +%s.%N)\"; ip -4 route show {PREFIX}; done")
            answers[f"timed delete {k + 1}"] = sh(NODE, ["sh", "-c", script])
        snap("timed_end")
        # no lab default (up1 stops originating one): the BGP route then has nothing in the lab to resolve over, so
        # with Docker's default gone it must leave the table, not move
        answers["up1 stops default-originate"] = sh("up1", ["vtysh", "-c", "configure terminal", "-c",
                                                           "router bgp 65200", "-c", "address-family ipv4 unicast",
                                                           "-c", "no neighbor 10.0.2.1 default-originate", "-c", "end"])
        sample("no_lab_default", 15.0)
        snap("no_lab_default")
        for k in range(3):
            script = (f"ip route add default via {gw} dev eth0; "
                      f"for i in $(seq 1 100); do ip -4 route show {PREFIX} | grep -q 'dev eth0' && break; sleep 0.1; "
                      f"done; echo \"# before: $(ip -4 route show {PREFIX})\"; "
                      f"echo \"@del4 $(date +%s.%N)\"; ip -4 route del default via {gw} dev eth0; "
                      f"for i in $(seq 1 400); do echo \"@ $(date +%s.%N)\"; ip -4 route show {PREFIX}; done")
            answers[f"timed delete, no lab default {k + 1}"] = sh(NODE, ["sh", "-c", script])
        sample("no_lab_default_after_delete", 30.0)
        snap("no_lab_default_end")

    (out / "answers.json").write_text(json.dumps(answers, indent=1) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
