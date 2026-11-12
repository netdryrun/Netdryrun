"""Oracle FP-042-VRFDEV (red team RT-0053): an address on the VRF device itself isn't read as the node's own.

What the router showed (FRR 10.4.1, containerlab lab ndr-repro042, captured 2026-11-12; lab files
tests/fixtures/frr1041_repro042_*, captures tests/fixtures/frr1041_rt0053_*):
- r1 has a VRF device RED (`ip link add RED type vrf table 1001`) with 10.255.1.1/32 on the device itself
  (`ip addr add 10.255.1.1/32 dev RED`, a common VRF loopback);
- `ip -j addr show vrf RED` answers `[]`: it lists the interfaces enslaved to RED, not RED;
- `ip -j addr show dev RED` lists 10.255.1.1/32 on RED;
- `ip vrf exec RED ping -c 3 -W 1 10.255.1.1` gets 3/3 replies: the node answers its own address.
The 0.4.2 FRR driver reads a VRF's own addresses from `ip -j addr show vrf <vrf>` only, so the `ping` check node r1
vrf RED target 10.255.1.1 passed ("3/3 replies (need 2)", tests/fixtures/frr1041_repro042_report.json). The ping
never left the node. website/docs/reference/config.md lists it as a known limit, "Fix: 0.4.2".

The rule: 10.255.1.1 is r1's own address in VRF RED. The driver's own addresses for RED include it, or the read
refuses (DriverError); and the ping check to it never passes (refused as an own target, or unreadable).

Reads the capture doesn't cover answer rc 1 (an unknown command): the oracle knows nothing else r1 would have said.
"""
import ipaddress
from pathlib import Path

from netdryrun.checks import run_check
from netdryrun.config import _validate_check
from netdryrun.drivers.base import DriverError
from netdryrun.drivers.frr import FrrDriver
from netdryrun.lab import ExecResult

FX = Path(__file__).resolve().parents[2] / "fixtures"
OWN = "10.255.1.1"

CAPTURED = {   # r1's command -> its output, as captured
    ("ip", "-j", "addr", "show", "vrf", "RED"): "frr1041_rt0053_r1_ip_addr_vrf_RED.json",
    ("ip", "-j", "addr", "show", "dev", "RED"): "frr1041_rt0053_r1_ip_addr_dev_RED.json",
    ("ip", "vrf", "exec", "RED", "ping", "-c", "3", "-W", "1", OWN): "frr1041_rt0053_r1_ping_vrf_own.txt",
}


def fx(name: str) -> str:
    return (FX / name).read_text(encoding="utf-8")


class CapturedLab:
    """r1 as captured. A command that wasn't captured answers as an unknown command (rc=1)."""

    def exec(self, node, cmd, timeout=60, input=None):
        if node == "r1" and tuple(cmd) in CAPTURED:
            return ExecResult(cmd, 0, fx(CAPTURED[tuple(cmd)]), "")
        return ExecResult(cmd, 1, "", f"not captured: {' '.join(cmd)}")


class Clock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t

    def sleep(self, s):
        self.t += max(s, 0.5)


def _ip(a):
    """An address entry from local_addresses (an ip_interface, or a wrapper holding one) as an ip_address."""
    for x in (a, getattr(a, "iface", None)):
        ip = getattr(x, "ip", None)
        if isinstance(ip, (ipaddress.IPv4Address, ipaddress.IPv6Address)):
            return ip
    return None


def test_local_addresses_in_red_include_the_vrf_device_address():
    """The capture lists 10.255.1.1/32 on the VRF device RED: it is r1's own address in RED."""
    assert OWN in fx("frr1041_rt0053_r1_ip_addr_dev_RED.json")
    try:
        addrs = FrrDriver(CapturedLab(), "r1").local_addresses("RED")
    except DriverError:
        return   # a refusal: unreadable is unready, never "not an own address"
    assert ipaddress.ip_address(OWN) in {_ip(a) for a in addrs}, (
        f"r1's own addresses in vrf RED read as {addrs}: {OWN}/32 on the VRF device RED is missing")


def test_ping_to_the_vrf_device_address_does_not_pass():
    """The red team's check: a ping from r1 in vrf RED to 10.255.1.1, r1's own address, passed on 3/3 replies."""
    assert "3 packets received" in fx("frr1041_rt0053_r1_ping_vrf_own.txt")
    c = Clock()
    check = _validate_check(0, {"type": "ping", "node": "r1", "vrf": "RED", "target": OWN}, 20)
    r = run_check(check, FrrDriver(CapturedLab(), "r1"), clock=c, sleep=c.sleep)
    assert not r.passed, f"a ping to r1's own address {OWN} in vrf RED passed: {r.detail}"
