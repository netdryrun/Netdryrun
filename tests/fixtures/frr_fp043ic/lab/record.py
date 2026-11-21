"""FP-043-FRRIMPORTCHK capture recorder: one phase of one live boot (run by capture.sh, inside WSL).

    record.py <topology> <out_dir> <origin node> <prefix> [checks.yml ...]

Every command netdryrun runs in a node (docker exec), and every boot log it reads, is run here against the live lab,
and its stdout and stderr are kept as the exact bytes Docker returned (answers/NNNN.stdout|.stderr), with node, argv,
rc and time in index.json. Recorded in this order:
1. `netdryrun check <checks.yml> --json report_<stem>.json` for each checks file (in-process: the CLI with its Lab
   recorded), as a user runs it on this lab; the first one also removes Docker's management default routes;
2. what `netdryrun verify` reads on a booted side: expects_bgp, collect() twice (stable_snapshot compares two), the
   config-load read (verify.run.check_config_loaded); the snapshot as snapshot.json;
3. the import-check reads, per BGP instance (from bgpd's running config) and as `vrf all`, text and JSON, with the
   prefix's own paths, zebra's nexthop tracking and the full tables.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
import time
from pathlib import Path

from netdryrun import runner
from netdryrun.lab import ExecResult, Lab


def _text(b: bytes) -> str:   # what lab._run's text=True gives netdryrun (UTF-8, universal newlines)
    return b.decode("utf-8").replace("\r\n", "\n").replace("\r", "\n")


class RecordingLab(Lab):
    def __init__(self, topology: Path, out: Path):
        super().__init__(topology)
        self.out = out
        (out / "answers").mkdir(parents=True, exist_ok=True)
        self.index: list[dict] = []

    def _rec(self, node: str, how: str, argv: list[str], p: subprocess.CompletedProcess) -> ExecResult:
        i = len(self.index) + 1
        (self.out / "answers" / f"{i:04d}.stdout").write_bytes(p.stdout)
        (self.out / "answers" / f"{i:04d}.stderr").write_bytes(p.stderr)
        self.index.append({"n": i, "node": node, "how": how, "argv": argv, "rc": p.returncode,
                           "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())})
        (self.out / "index.json").write_text(json.dumps(self.index, indent=1) + "\n", encoding="utf-8")
        return ExecResult(argv, p.returncode, _text(p.stdout), _text(p.stderr))

    def _docker(self, node, how, flags, cmd, timeout, input=None):
        full = ["docker", "exec", *flags, self.nodes[node].container, *cmd]
        try:
            p = subprocess.run(full, capture_output=True, timeout=timeout,
                               input=input.encode() if input is not None else None)
        except subprocess.TimeoutExpired:
            return ExecResult(cmd, 124, "", f"timed out after {timeout}s")
        return self._rec(node, how, list(cmd), p)

    def exec(self, node, cmd, timeout=60, input=None):
        return self._docker(node, "exec", ["-i"] if input is not None else [], cmd, timeout, input)

    def exec_root(self, node, cmd, timeout=60):
        return self._docker(node, "exec_root", ["-u", "0"], cmd, timeout)

    def boot_log(self, node):
        c = self.nodes[node].container
        s = subprocess.run(["docker", "inspect", "-f", "{{.State.StartedAt}}", c], capture_output=True)
        started = s.stdout.decode().strip()
        p = subprocess.run(["docker", "logs", "--since", started, c], capture_output=True)
        r = self._rec(node, "boot_log", ["docker", "logs", "--since", started], p)
        return ExecResult(r.cmd, r.rc, f"{r.stdout}\n{r.stderr}", r.stderr)   # as Lab.boot_log joins them


def instances(running: str) -> list[str]:
    """`router bgp` headers of bgpd's running config -> the vrf part of a show command ("" for default)."""
    out = []
    for m in re.finditer(r"(?m)^router bgp \S+(?: (vrf|view) (\S+))?\s*$", running):
        out.append("" if not m.group(1) else f" {m.group(1)} {m.group(2)}")
    return out


def main(topology: str, out_dir: str, origin: str, prefix: str, *checks: str) -> None:
    out = Path(out_dir)
    lab = RecordingLab(Path(topology), out)
    runner.Lab = lambda path: lab
    from netdryrun.cli import main as cli
    for c in checks:
        rc = cli(["check", c, "--json", str(out / f"report_{Path(c).stem}.json"), "--no-step-summary"])
        (out / f"report_{Path(c).stem}.exit").write_text(f"{rc}\n", encoding="utf-8")
    from netdryrun.verify.run import check_config_loaded, classify_nodes, collect, expects_bgp
    nodes = classify_nodes(lab, {}, [])

    def exec_fn(node, argv):
        r = lab.exec(node, argv)
        return r.rc, r.stdout, r.stderr
    for n, d in sorted(nodes.items()):
        if d == "frr":
            expects_bgp(exec_fn, n)
    collect(lab, nodes)
    snap = collect(lab, nodes)
    (out / "snapshot.json").write_text(json.dumps(snap.to_json(), indent=1, sort_keys=True) + "\n", encoding="utf-8")
    try:
        check_config_loaded(lab, nodes, "capture")
        (out / "config_loaded.txt").write_text("clean\n", encoding="utf-8")
    except Exception as e:
        (out / "config_loaded.txt").write_text(f"{e}\n", encoding="utf-8")
    for n in sorted(nodes):
        running = lab.exec(n, ["vtysh", "-d", "bgpd", "-c", "show running-config"]).stdout
        lab.exec(n, ["vtysh", "-c", "show running-config"])
        reads = ["show bgp vrf all import-check-table detail", "show bgp vrf all import-check-table detail json",
                 "show bgp vrf all import-check-table", "show bgp vrf all json", "show bgp vrf all nexthop detail",
                 "show ip nht vrf all", "show ip nht", "show ipv6 nht vrf all", "show version", "show vrf"]
        for vrf in instances(running):
            reads += [f"show bgp{vrf} import-check-table detail", f"show bgp{vrf} import-check-table detail json",
                      f"show bgp{vrf} import-check-table", f"show bgp{vrf} import-check-table json"]
        reads += [f"show bgp ipv4 unicast {prefix} json", f"show bgp ipv4 unicast {prefix}",
                  f"show ip route {prefix} json", "show bgp vrf all ipv4 unicast json", "show ip route vrf all json"]
        for cmd in reads:
            lab.exec(n, ["vtysh", "-c", cmd])
        lab.boot_log(n)


if __name__ == "__main__":
    main(*sys.argv[1:])
