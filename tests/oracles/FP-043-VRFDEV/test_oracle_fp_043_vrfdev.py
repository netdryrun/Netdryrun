"""Oracle FP-043-VRFDEV (red team RT-0053): an FRR ping in a VRF to an address on the VRF device itself passes.

What the kernel showed (tests/fixtures/frr1041_vrfdev_capture.txt, written by frr1041_vrfdev_capture.sh):
- **Where:** the pinned FRR image quay.io/frrouting/frr:10.4.1 (iproute2-6.9.0), 2026-11-09, one container.
- **Setup:** VRF device `red` (table 10) with a dummy `d0` enslaved to it (10.0.23.1/30). The VRF device itself holds
  10.9.9.9/32, 10.8.8.1/24 and 2001:db8:99::9/128, the usual Linux idiom for a VRF loopback.
- `ip -j addr show vrf red` lists d0 only, never the VRF device. `ip -j addr show dev red` and `ip -j addr` list red with
  its three addresses.
- `ip vrf exec red ping -c 2 -W 1 10.9.9.9` gets 2/2 replies: the kernel answers it locally (table 10 has `local
  10.9.9.9 dev red`). `... ping 10.8.8.77`, an address in the device's /24 that nobody holds, gets 0/2.
- **netdryrun 0.4.2:** the FRR driver reads the node's own addresses in vrf red with `ip -j addr show vrf red`, so
  10.9.9.9 is not refused as an own address. The ping check runs and passes, though the ping never left the node.

The rule (0.4.1 advisory case 3, fix promised for 0.4.3): the VRF device's own addresses count as the node's. The
driver reads them, and a ping to one of them is refused as an own-address ping, never passed.

Everything goes through the real FrrDriver and `checks.run_check`, fed the captured answers, matched by exact command
line. The checks use `count: 2`, the count the capture's pings used. A command that wasn't captured answers rc 1.

The tests here fail on the parent. The guards, which pass before and after the fix, are in
tests/test_oracle_guards_fp_043_vrfdev.py (listed in ORACLE.yml `evidence:`).
"""
import re
from pathlib import Path

from netdryrun.checks import run_check
from netdryrun.config import _validate_check
from netdryrun.drivers.base import DriverError
from netdryrun.drivers.frr import FrrDriver
from netdryrun.lab import ExecResult

FX = Path(__file__).resolve().parents[2] / "fixtures"
PING = ["ip", "vrf", "exec", "red", "ping", "-W", "1"]


def sections() -> dict:
    """The capture's sections, by their `== <title>` line: (output, rc). rc is the `rc=N` line where one was printed."""
    out, title, lines = {}, None, []
    for line in (FX / "frr1041_vrfdev_capture.txt").read_text(encoding="utf-8").splitlines(keepends=True):
        if line.startswith("== "):
            if title is not None:
                out[title] = lines
            title, lines = line[3:].strip(), []
        else:
            lines.append(line)
    out[title] = lines
    result = {}
    for t, ls in out.items():
        rc = 0
        if ls and re.fullmatch(r"rc=\d+\n?", ls[-1]):
            rc = int(ls[-1].strip()[3:])
            ls = ls[:-1]
        result[t] = ("".join(ls), rc)
    return result


def answers() -> dict:
    s = sections()
    return {
        ("ip", "-j", "addr", "show", "vrf", "red"): s["ip -j addr show vrf red"],
        ("ip", "-j", "addr"): s["ip -j addr"],
        ("ip", "-j", "addr", "show", "dev", "red"): s["ip -j addr show dev red"],
        ("ip", "route", "show", "table", "10"): s["local table 10"],
        ("ip", "vrf", "exec", "red", "ping", "-c", "2", "-W", "1", "10.9.9.9"): s["ping vrf device /32"],
        ("ip", "vrf", "exec", "red", "ping", "-c", "2", "-W", "1", "10.8.8.77"): s["ping other addr in /24 on vrf device"],
        ("ip", "vrf", "exec", "red", "ping", "-c", "1", "-W", "1", "10.0.23.1"): s["ip vrf exec red ping enslaved addr"],
    }


class CapturedLab:
    """r1 as the capture's container: each captured command line answers its captured output and rc."""

    def __init__(self):
        self.answers = answers()

    def exec(self, node, cmd, timeout=60, input=None):
        a = self.answers.get(tuple(cmd))
        if node == "r1" and a is not None:
            return ExecResult(list(cmd), a[1], a[0], "")
        return ExecResult(list(cmd), 1, "", f"not captured: {' '.join(cmd)}")


class Clock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t

    def sleep(self, s):
        self.t += max(s, 0.5)


def ping(target: str, count: int = 2, **more):
    c = Clock()
    check = _validate_check(0, {"type": "ping", "node": "r1", "vrf": "red", "target": target, "count": count, **more}, 20)
    return run_check(check, FrrDriver(CapturedLab(), "r1"), clock=c, sleep=c.sleep)


def own(vrf: str = "red"):
    """r1's own addresses in `vrf` through the real driver: (set of addresses, None), or (None, the DriverError)."""
    try:
        return {str(a.ip) for a in FrrDriver(CapturedLab(), "r1").local_addresses(vrf)}, None
    except DriverError as e:
        return None, e


# ------------------------------------------------------------------ red on 0.4.2 (e6522db)

def test_the_vrf_devices_addresses_are_the_nodes_own():
    addrs, error = own("red")
    assert error is None, f"r1's addresses in vrf red not read: {error}"
    assert {"10.9.9.9", "10.8.8.1", "2001:db8:99::9"} <= addrs, f"the VRF device's addresses are missing: {addrs}"
    assert "10.0.23.1" in addrs, addrs


def test_a_ping_to_the_vrf_device_address_never_passes():
    """10.9.9.9 is on red itself: the kernel answered 2/2 locally. The check must refuse it, naming the target."""
    r = ping("10.9.9.9")
    assert not r.passed, f"passed on a ping that never left r1: {r.detail}"
    assert "10.9.9.9" in str(r.detail), r.detail
