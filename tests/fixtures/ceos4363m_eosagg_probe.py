"""probe.py <label> <driver eos|frr> <node>: run the route checks of the oracle FP-043-EOSAGG through the netdryrun
code on PYTHONPATH (main or fix-eos-nonbgp), against the live lab ndr-eosagg (docker exec), the way the runner judges
a check (hold_together for a post-convergence check, run_check otherwise), and print each verdict. No convergence gate:
the phases are set up and waited for by capture.sh before this runs."""
import subprocess
import sys

from netdryrun.checks import hold_together, is_post_convergence, run_check
from netdryrun.config import _validate_check
from netdryrun.drivers.eos import EosDriver
from netdryrun.drivers.frr import FrrDriver
from netdryrun.lab import ExecResult

PREFIXES = [("v4", "default", "10.66.0.0/16"), ("v6", "default", "2001:db8:66::/48"), ("blue", "blue", "10.67.0.0/16")]
CHECKS = [("bgp-absent", {"protocol": "bgp", "present": False}), ("bgp-active", {"protocol": "bgp"}),
          ("bgp-candidate", {"protocol": "bgp", "active": False}),
          ("agg-absent", {"protocol": "aggregate", "present": False}), ("agg-active", {"protocol": "aggregate"}),
          ("agg-candidate", {"protocol": "aggregate", "active": False}),
          ("any-absent", {"present": False}), ("static-active", {"protocol": "static"})]


class LiveLab:
    def exec(self, node, argv, timeout=60, input=None):
        p = subprocess.run(["docker", "exec", f"clab-ndr-eosagg-{node}", *argv], capture_output=True, text=True,
                           timeout=timeout)
        return ExecResult(list(argv), p.returncode, p.stdout, p.stderr)


class Clock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t

    def sleep(self, s):
        self.t += max(s, 0.5)


label, drv, node = sys.argv[1:4]
cls = EosDriver if drv == "eos" else FrrDriver
for key, vrf, prefix in PREFIXES:
    d = cls(LiveLab(), node)
    try:
        print(f"{label:28} {key:5} routes: {[(r.protocol, r.active, r.raw_protocol) for r in d.routes(prefix, vrf).value]}")
    except Exception as e:
        print(f"{label:28} {key:5} routes: ERROR {type(e).__name__}: {str(e)[:150]}")
    for name, attrs in CHECKS:
        if drv == "frr" and attrs.get("protocol") == "aggregate":
            print(f"{label:28} {key + '-' + name:20} REFUSED (protocol aggregate is never reported by frr)")
            continue
        check = _validate_check(0, {"type": "route", "node": node, "prefix": prefix, "vrf": vrf, **attrs}, 20)
        c = Clock()
        try:
            if is_post_convergence(check):
                [r] = hold_together([check], {node: d}, hold=10, clock=c, sleep=c.sleep)
            else:
                r = run_check(check, d, clock=c, sleep=c.sleep)
            print(f"{label:28} {key + '-' + name:20} passed={r.passed}  {str(r.detail)[:120]}")
        except Exception as e:
            print(f"{label:28} {key + '-' + name:20} ERROR {type(e).__name__}: {str(e)[:150]}")
