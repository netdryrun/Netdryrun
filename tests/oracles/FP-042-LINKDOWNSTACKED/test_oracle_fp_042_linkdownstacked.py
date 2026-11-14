"""Oracle FP-042-LINKDOWNSTACKED (red team 042-GV, B-RT-0078): `link_down` on a VLAN-trunk parent watches no session.

config.md, Scenario timing, step 1: "Before taking links down, it notes the established BGP sessions that run over
them, on both ends of each link (looking through bridges)", and waits until they are down before the checks run.
`runner._link_sessions` finds those sessions from the addresses of the downed interface itself (`ip -o addr show dev
eth1`). When the session addresses live on a device stacked on it (a VLAN subinterface `eth1.100@eth1`), eth1 has only
its link-local, no neighbor matches, nothing is watched, and `_wait_fault_visible` logs "no BGP session runs over the
downed links; relying on the settle and hold windows" and returns at once. r2 sits behind a containerlab bridge, so it
gets no carrier event: it keeps the eBGP session to r1 and r1's route 10.1.0.0/24 until its hold timer expires (FRR
default 180 s). The scenario's settle, reach and hold all run inside that window, and `route 10.1.0.0/24 protocol bgp`
on r2 passes in a lab with no backup path.

Device output: derived, not captured. The lab is the real `netdryrun.lab.Lab` (from the red team's topology, written
to a temporary folder) whose `exec` is a fake kernel built here. It answers, as iproute2 prints them,
`ip [-o] [-d] [-j] [-4|-6] link|addr show [dev X]` (one line per device with -o; `eth1.100@eth1` with its VLAN details
under -d; JSON with -j), `ip link set dev X up|down`, and `ls /sys/class/net[/X]` (with the kernel's `upper_eth1.100`
and `lower_eth1` links). Anything else exits 1 ("not in the fake kernel"). Downing eth1 takes eth1.100's carrier
(LOWERLAYERDOWN, still admin-up), as the kernel does. The BGP drivers are fakes on the same clock: r1's session to
10.0.100.2 goes idle at once when its eth1 goes down; r2's session to 10.0.100.1, and r1's route on r2, stay until
180 s after the fault (its hold time). The scenario is the red team's: `link_down {node: r1, interface: eth1}` with
`route 10.1.0.0/24 protocol bgp` on r2.

The rule: the session over the stacked device is watched on both ends (so the run waits for r2's side to go down and
the route check fails), or the scenario stops with a LabError. Never the "no BGP session" line with a judgement made
on the state from before the fault.
"""
import ipaddress
import json

from netdryrun import runner
from netdryrun.config import Fault, Scenario, _validate_check
from netdryrun.drivers.base import BgpNeighbor, Observation, Route
from netdryrun.lab import ExecResult, Lab, LabError

TOPOLOGY = """\
name: rt0078
topology:
  nodes:
    r1: {kind: linux, image: quay.io/frrouting/frr:10.4.1}
    r2: {kind: linux, image: quay.io/frrouting/frr:10.4.1}
    br1: {kind: bridge}
  links:
    - endpoints: ["r1:eth1", "br1:br1-p1"]
    - endpoints: ["r2:eth1", "br1:br1-p2"]
"""
HOLD_TIME = 180.0
NOTHING_WATCHED = "no BGP session runs over the downed links"


class Dev:
    def __init__(self, name, index, mac, addrs=(), parent=None, vlan=None, peer_index=None):
        self.name, self.index, self.mac, self.addrs = name, index, mac, list(addrs)
        self.parent, self.vlan, self.peer_index = parent, vlan, peer_index
        self.up = True


def stacked_devices(node, n):
    """r<n>: eth1 (veth to the bridge) carrying only its link-local; eth1.100 (VLAN 100 on eth1) with 10.0.100.n/30."""
    mac = f"aa:c1:ab:0{n}:00:01"
    return [Dev("lo", 1, "00:00:00:00:00:00", ["127.0.0.1/8", "::1/128"]),
            Dev("eth0", 2, f"02:42:ac:14:14:0{n}", [f"172.20.20.{n + 1}/24"], peer_index=30 + n),
            Dev("eth1", 5, mac, [f"fe80::a8c1:abff:fe0{n}:1/64"], peer_index=40 + n),
            Dev("eth1.100", 6, mac, [f"10.0.100.{n}/30", f"fe80::a8c1:abff:fe0{n}:1/64"], parent="eth1", vlan=100)]


def plain_devices(node, n):
    """r<n>: eth1 (veth to the bridge) with 10.0.100.n/30 on it, no stacked device."""
    mac = f"aa:c1:ab:0{n}:00:01"
    return [Dev("lo", 1, "00:00:00:00:00:00", ["127.0.0.1/8", "::1/128"]),
            Dev("eth0", 2, f"02:42:ac:14:14:0{n}", [f"172.20.20.{n + 1}/24"], peer_index=30 + n),
            Dev("eth1", 5, mac, [f"10.0.100.{n}/30", f"fe80::a8c1:abff:fe0{n}:1/64"], peer_index=40 + n)]


class Clock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t

    def sleep(self, s):
        self.t += s


class KernelLab(Lab):
    """The real Lab, with `exec` answered by a fake kernel per node."""

    def __init__(self, topology, devices, clock):
        super().__init__(topology)
        self.devs = {n: {d.name: d for d in devices(n, i)} for i, n in ((1, "r1"), (2, "r2"))}
        self.clock = clock
        self.down_at: dict[tuple[str, str], float] = {}
        self.commands: list[tuple[str, str]] = []

    # --- what the kernel shows ----------------------------------------------------------------------------
    def carrier(self, node, d):
        if not d.up:
            return False
        return self.carrier(node, self.devs[node][d.parent]) if d.parent else True

    def _label(self, d):
        if d.parent:
            return f"{d.name}@{d.parent}"
        return f"{d.name}@if{d.peer_index}" if d.peer_index else d.name

    def _flags(self, node, d):
        if d.name == "lo":
            return ["LOOPBACK", "UP", "LOWER_UP"]
        f = ["BROADCAST", "MULTICAST"]
        if d.up:
            f.append("UP")
            if self.carrier(node, d):
                f.append("LOWER_UP")
            else:
                f.insert(0, "NO-CARRIER")
        return f

    def _state(self, node, d):
        if d.name == "lo":
            return "UNKNOWN"
        if not d.up:
            return "DOWN"
        return "UP" if self.carrier(node, d) else "LOWERLAYERDOWN"

    def _link_line(self, node, d, details):
        mtu = 65536 if d.name == "lo" else 9500 if d.name != "eth0" else 1500
        kind = "loopback" if d.name == "lo" else "ether"
        brd = "00:00:00:00:00:00" if d.name == "lo" else "ff:ff:ff:ff:ff:ff"
        line = (f"{d.index}: {self._label(d)}: <{','.join(self._flags(node, d))}> mtu {mtu} qdisc noqueue state "
                f"{self._state(node, d)} mode DEFAULT group default qlen 1000\\    link/{kind} {d.mac} brd {brd}")
        if d.peer_index:
            line += " link-netnsid 0"
        if details:
            line += " promiscuity 0 allmulti 0 minmtu 68 maxmtu 65535 "
            if d.vlan:
                line += f"\\    vlan protocol 802.1Q id {d.vlan} <REORDER_HDR> "
            elif d.peer_index:
                line += "\\    veth "
            line += "addrgenmode eui64 numtxqueues 1 numrxqueues 1 gso_max_size 65536 gso_max_segs 65535"
        return line

    def _addr_lines(self, d, family):
        out = []
        for a in d.addrs:
            iface = ipaddress.ip_interface(a)
            if family and iface.version != family:
                continue
            if iface.version == 4:
                scope = "host" if iface.ip.is_loopback else "global"
                brd = "" if iface.ip.is_loopback else f" brd {iface.network.broadcast_address}"
                out.append(f"{d.index}: {d.name:<8} inet {a}{brd} scope {scope} {d.name}\\       valid_lft forever "
                           "preferred_lft forever")
            else:
                scope = "host" if iface.ip.is_loopback else "link" if iface.ip.is_link_local else "global"
                out.append(f"{d.index}: {d.name:<8} inet6 {a} scope {scope} \\       valid_lft forever "
                           "preferred_lft forever")
        return out

    def _json(self, node, d, obj, family):
        j = {"ifindex": d.index, "ifname": d.name, "flags": self._flags(node, d), "mtu": 9500, "qdisc": "noqueue",
             "operstate": self._state(node, d), "group": "default", "link_type": "loopback" if d.name == "lo" else "ether",
             "address": d.mac}
        if d.parent:
            j["link"] = d.parent
            j["linkinfo"] = {"info_kind": "vlan", "info_data": {"protocol": "802.1Q", "id": d.vlan,
                                                                 "flags": ["REORDER_HDR"]}}
        elif d.peer_index:
            j["link_index"] = d.peer_index
            j["link_netnsid"] = 0
        if obj == "addr":
            infos = []
            for a in d.addrs:
                iface = ipaddress.ip_interface(a)
                if family and iface.version != family:
                    continue
                infos.append({"family": "inet" if iface.version == 4 else "inet6", "local": str(iface.ip),
                              "prefixlen": iface.network.prefixlen,
                              "scope": "host" if iface.ip.is_loopback else
                              "link" if iface.ip.is_link_local else "global",
                              "valid_life_time": 4294967295, "preferred_life_time": 4294967295})
            j["addr_info"] = infos
        return j

    def _ip(self, node, argv):
        args = argv[1:]
        opts = set()
        while args and args[0].startswith("-"):
            opts.add(args.pop(0))
        if args[:2] == ["link", "set"] and len(args) == 5 and args[2] == "dev" and args[4] in ("up", "down"):
            d = self.devs[node].get(args[3])
            if d is None:
                return 1, "", f'Cannot find device "{args[3]}"\n'
            d.up = args[4] == "up"
            if not d.up:
                self.down_at.setdefault((node, d.name), self.clock())
            return 0, "", ""
        obj = {"link": "link", "l": "link", "addr": "addr", "address": "addr", "a": "addr"}.get(args[0] if args else "")
        rest = args[1:]
        if rest[:1] == ["show"] or rest[:1] == ["list"]:
            rest = rest[1:]
        if obj is None or opts - {"-o", "-oneline", "-d", "-details", "-j", "-json", "-4", "-6", "-p", "-br"}:
            return None
        devs = list(self.devs[node].values())
        if rest[:1] == ["dev"] and len(rest) == 2 or len(rest) == 1 and rest[0] != "up":
            name = rest[-1]
            if name not in self.devs[node]:
                return 1, "", f'Device "{name}" does not exist.\n'
            devs = [self.devs[node][name]]
        elif rest:
            return None
        family = 4 if "-4" in opts else 6 if "-6" in opts else 0
        if opts & {"-j", "-json"}:
            return 0, json.dumps([self._json(node, d, obj, family) for d in devs]) + "\n", ""
        if "-br" in opts:
            lines = []
            for d in devs:
                st = self._state(node, d)
                if obj == "link":
                    lines.append(f"{self._label(d):<16} {st:<14} {d.mac} <{','.join(self._flags(node, d))}>")
                else:
                    addrs = [a for a in d.addrs if not family or ipaddress.ip_interface(a).version == family]
                    lines.append(f"{self._label(d):<16} {st:<14} {' '.join(addrs)} ")
            return 0, "\n".join(lines) + "\n", ""
        if obj == "link":
            return 0, "".join(self._link_line(node, d, opts & {"-d", "-details"}) + "\n" for d in devs), ""
        return 0, "".join(x + "\n" for d in devs for x in self._addr_lines(d, family)), ""

    def exec(self, node, cmd, timeout=60, input=None):
        argv = list(cmd)
        if argv[:2] in (["sh", "-c"], ["bash", "-c"], ["bash", "-lc"]) and len(argv) == 3:
            argv = argv[2].split()
        self.commands.append((node, " ".join(argv)))
        r = None
        if argv and argv[0] == "ip":
            r = self._ip(node, argv)
        elif argv[:1] == ["ls"] and len(argv) == 2 and argv[1].rstrip("/") == "/sys/class/net":
            r = 0, " ".join(sorted(self.devs[node])) + "\n", ""
        elif argv[:1] == ["ls"] and len(argv) == 2 and argv[1].startswith("/sys/class/net/"):
            name = argv[1].rstrip("/").rsplit("/", 1)[1]
            d = self.devs[node].get(name)
            if d is None:
                r = 2, "", f"ls: cannot access '{argv[1]}': No such file or directory\n"
            else:
                entries = ["addr_assign_type", "address", "carrier", "dev_id", "flags", "ifindex", "iflink", "mtu",
                           "operstate", "statistics", "subsystem", "type", "uevent"]
                entries += [f"upper_{u.name}" for u in self.devs[node].values() if u.parent == name]
                entries += [f"lower_{d.parent}"] if d.parent else []
                r = 0, "  ".join(sorted(entries)) + "\n", ""
        if r is None:
            r = 1, "", f"not in the fake kernel: {' '.join(argv)}\n"
        return ExecResult(cmd, *r)


class R1:
    """FRR on r1: its eBGP session to r2 (10.0.100.2) runs over eth1.100 (or eth1); it drops at once with the carrier."""
    name = "frr"

    def __init__(self, lab):
        self.lab = lab

    def bgp_neighbors(self, vrf="default"):
        dev = self.lab.devs["r1"].get("eth1.100") or self.lab.devs["r1"]["eth1"]
        up = self.lab.carrier("r1", dev)
        n = BgpNeighbor("10.0.100.2", "established" if up else "idle", {"ipv4-unicast": 1} if up else {})
        return Observation({"10.0.100.2": n}, [])

    def routes(self, prefix, vrf="default"):
        return Observation([Route(prefix, "connected", True)] if prefix == "10.1.0.0/24" else [], [])


class R2:
    """FRR on r2, behind the bridge: no carrier change, so its session to r1 (10.0.100.1) and r1's route 10.1.0.0/24
    stay until its hold time runs out after r1's eth1 went down."""
    name = "frr"

    def __init__(self, lab):
        self.lab = lab

    def alive(self):
        t = self.lab.down_at.get(("r1", "eth1"))
        return t is None or self.lab.clock() < t + HOLD_TIME or self.lab.devs["r1"]["eth1"].up

    def bgp_neighbors(self, vrf="default"):
        up = self.alive()
        n = BgpNeighbor("10.0.100.1", "established" if up else "active", {"ipv4-unicast": 1} if up else {})
        return Observation({"10.0.100.1": n}, [])

    def routes(self, prefix, vrf="default"):
        return Observation([Route(prefix, "bgp", True)] if prefix == "10.1.0.0/24" and self.alive() else [], [])


def make_lab(tmp_path, monkeypatch, devices=stacked_devices):
    topo = tmp_path / "topology.clab.yml"
    topo.write_text(TOPOLOGY, encoding="utf-8")
    clock = Clock()
    monkeypatch.setattr(runner, "_clock", clock)
    monkeypatch.setattr(runner, "_sleep", clock.sleep)
    lab = KernelLab(topo, devices, clock)
    return lab, {"r1": R1(lab), "r2": R2(lab)}


def scenario(timeout=300, iface="eth1"):
    check = _validate_check(0, {"type": "route", "node": "r2", "prefix": "10.1.0.0/24", "protocol": "bgp"}, timeout,
                            prefix="scenarios[0].checks")
    return Scenario("r1-r2 link fails", [Fault("link_down", "r1", iface)], [check])


def run(lab, drivers, sc):
    logs: list[str] = []
    try:
        results = runner.run_scenario(lab, sc, drivers, settle=10, hold=10, log=logs.append,
                                      driver_for=lambda n: drivers[n])
    except LabError as e:
        return None, logs, e
    return results, logs, None


def test_link_sessions_finds_the_session_on_the_vlan_subinterface(tmp_path, monkeypatch):
    lab, drivers = make_lab(tmp_path, monkeypatch)
    try:
        watch, every = runner._link_sessions(lab, [("r1", "eth1")], ["default"], lambda n: drivers[n])
    except LabError:
        return   # refusing a link whose sessions it can't find is allowed
    want = {("r1", "default", "10.0.100.2"), ("r2", "default", "10.0.100.1")}
    assert want <= set(watch) and want <= set(every), (
        f"taking r1 eth1 down drops the eBGP session r1 10.0.100.1 <-> r2 10.0.100.2 that runs over eth1.100@eth1, "
        f"but _link_sessions watches {watch} (every: {every}); commands: {lab.commands}")


def test_link_down_on_a_vlan_trunk_parent_is_not_judged_before_the_fault(tmp_path, monkeypatch):
    lab, drivers = make_lab(tmp_path, monkeypatch)
    results, logs, err = run(lab, drivers, scenario())
    if err is not None:
        return   # stopping the scenario with an error is allowed
    assert not any(NOTHING_WATCHED in x for x in logs), (
        "the scenario logged that no BGP session runs over r1 eth1, while r1's eBGP session to r2 runs over its VLAN "
        f"subinterface eth1.100@eth1: {logs}")
    assert results and not any(r.passed for r in results), (
        "route 10.1.0.0/24 on r2 passed on the state from before the fault (r2 keeps it for its 180 s hold time): "
        f"{[(r.passed, r.detail) for r in results]}; log: {logs}")

