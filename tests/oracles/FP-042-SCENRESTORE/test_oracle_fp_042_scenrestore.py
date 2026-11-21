"""Oracle FP-042-SCENRESTORE (angle-5 red team on 82fb052, B-RT-0076): scenario restore brings up a link the lab keeps shut.

config.md: "Links and injected routes are always restored afterwards, even if a check fails". `run_scenario` builds its
plan from `Lab.data_interfaces` (every entry of /sys/class/net except lo/eth0/mgmt0/docker0, with no admin state read)
and, in `finally`, runs `ip link set dev X up` on every interface it took down. An interface that was already
administratively down before the scenario (a backup link the lab keeps shut with containerlab `exec: [ip link set eth2
down]`, or `shutdown` in frr.conf) comes back UP, so every later scenario runs on a network with an extra link.

No device output is involved. The lab here is the real `netdryrun.lab.Lab` (read from a three-router topology written
to a temporary folder) whose `exec` is a fake kernel: it keeps each interface's admin flag and answers the commands
Lab sends (`ls /sys/class/net`, `ip -o link show dev X`, `ip link set dev X up|down`, `ip -o addr show dev X`) the way
iproute2 prints them. r1's eth2 (the backup link to r2) is admin-down before the scenario. The scenario is the red
team's: `node_isolated: r1` with one ping check, run through the real `runner.run_scenario`.

The rule: restore returns each link to the state it was found in. After the scenario r1 eth2 is still down. For a
`link_down` that names an interface already down, the scenario may also be refused (LabError) instead; what it must
not do is leave the interface up.
"""
import ipaddress

from netdryrun import runner
from netdryrun.config import Fault, Scenario, _validate_check
from netdryrun.drivers.base import Observation
from netdryrun.lab import ExecResult, Lab, LabError

TOPOLOGY = """\
name: rt0076
topology:
  nodes:
    r1: {kind: linux, image: quay.io/frrouting/frr:10.4.1}
    r2: {kind: linux, image: quay.io/frrouting/frr:10.4.1}
    r3: {kind: linux, image: quay.io/frrouting/frr:10.4.1}
  links:
    - endpoints: ["r1:eth1", "r3:eth1"]
    - endpoints: ["r1:eth2", "r2:eth2"]
    - endpoints: ["r3:eth2", "r2:eth1"]
"""

ADDRESSES = {("r1", "eth1"): "10.0.13.1/24", ("r1", "eth2"): "10.0.12.1/24", ("r2", "eth1"): "10.0.23.2/24",
             ("r2", "eth2"): "10.0.12.2/24", ("r3", "eth1"): "10.0.13.3/24", ("r3", "eth2"): "10.0.23.3/24"}


class KernelLab(Lab):
    """The real Lab, with `exec` answered by a fake kernel that keeps each interface's admin flag."""

    def __init__(self, topology, shut=()):
        super().__init__(topology)
        self.up = {end: end not in shut for end in ADDRESSES}
        self.commands: list[tuple[str, str]] = []

    def exec(self, node, cmd, timeout=60, input=None):
        self.commands.append((node, " ".join(cmd)))
        ifaces = sorted(i for n, i in ADDRESSES if n == node)
        if cmd == ["ls", "/sys/class/net"]:
            return ExecResult(cmd, 0, " ".join(["eth0", "lo", *ifaces]) + "\n", "")
        if cmd[:4] == ["ip", "-o", "link", "show"] and cmd[-1] in ifaces:
            i = cmd[-1]
            flags = "BROADCAST,MULTICAST,UP,LOWER_UP" if self.up[(node, i)] else "BROADCAST,MULTICAST"
            state = "UP" if self.up[(node, i)] else "DOWN"
            return ExecResult(cmd, 0, f"12: {i}@if13: <{flags}> mtu 9500 qdisc noqueue state {state} mode DEFAULT "
                                      "group default \\    link/ether aa:c1:ab:00:00:01 brd ff:ff:ff:ff:ff:ff\n", "")
        if cmd[:3] == ["ip", "link", "set"] and cmd[-2] in ifaces and cmd[-1] in ("up", "down"):
            self.up[(node, cmd[-2])] = cmd[-1] == "up"
            return ExecResult(cmd, 0, "", "")
        if cmd[:4] == ["ip", "-o", "addr", "show"] and cmd[-1] in ifaces:
            a = ADDRESSES[(node, cmd[-1])]
            return ExecResult(cmd, 0, f"12: {cmd[-1]}    inet {a} scope global {cmd[-1]}\\       valid_lft forever "
                                      "preferred_lft forever\n", "")
        return ExecResult(cmd, 1, "", f"not in the fake kernel: {' '.join(cmd)}")


class NoBgpDriver:
    """A node with no BGP session (the scenario then waits on nothing) whose pings all answer."""
    name = "frr"
    own_address_families = frozenset({4, 6})

    def bgp_neighbors(self, vrf="default"):
        return Observation({}, [])

    def local_addresses(self, vrf="default"):
        return [ipaddress.ip_interface("10.0.13.3/24"), ipaddress.ip_interface("10.0.23.3/24")]

    def ping(self, target, source, count, vrf="default"):
        return Observation((count, count), [{"output": "", "stderr": ""}])


def make_lab(tmp_path, shut=(("r1", "eth2"),)):
    topo = tmp_path / "topology.clab.yml"
    topo.write_text(TOPOLOGY, encoding="utf-8")
    return KernelLab(topo, shut)


def scenario(*faults):
    check = _validate_check(0, {"type": "ping", "node": "r3", "target": "10.0.23.2"}, 20, prefix="scenarios[0].checks")
    return Scenario("rt0076", list(faults), [check])


def run(monkeypatch, lab, sc):
    t = [0.0]
    monkeypatch.setattr(runner, "_clock", lambda: t[0])
    monkeypatch.setattr(runner, "_sleep", lambda s: t.__setitem__(0, t[0] + s))
    drivers = {n: NoBgpDriver() for n in lab.nodes}
    return runner.run_scenario(lab, sc, drivers, settle=0, hold=1, driver_for=lambda n: drivers[n])


def test_node_isolated_leaves_a_shut_link_shut(monkeypatch, tmp_path):
    lab = make_lab(tmp_path)
    assert lab.admin_up("r1", "eth1") and not lab.admin_up("r1", "eth2")   # the lab before the scenario
    run(monkeypatch, lab, scenario(Fault("node_isolated", "r1")))
    assert not lab.admin_up("r1", "eth2"), (
        "after `node_isolated: r1`, restore ran `ip link set dev eth2 up` on r1 eth2, which was administratively down "
        f"before the scenario: {[c for c in lab.commands if 'eth2 up' in c[1]]}")


def test_link_down_on_a_shut_link_never_leaves_it_up(monkeypatch, tmp_path):
    lab = make_lab(tmp_path)
    try:
        run(monkeypatch, lab, scenario(Fault("link_down", "r1", "eth2")))
    except LabError:
        pass   # refusing a fault on an interface that is already down is allowed
    assert not lab.admin_up("r1", "eth2"), "after `link_down: r1 eth2` on a shut eth2, restore brought it up"
