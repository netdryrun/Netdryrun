"""Oracle FP-042-LINKDOWNBRIDGE (adversary n5d on 5f0b7d7): `link_down` on a port of a bridge that keeps another port.

config.md, Scenario timing, step 1: "Before taking links down, it notes the established BGP sessions that run over
them, on both ends of each link (looking through bridges)", and waits until they are down before the checks run.
Since FP-042-LINKDOWNSTACKED, `runner._link_sessions` also counts the devices stacked on the downed interface
(`_stacked_on` over `Lab.link_tree`), but it counts a bond, bridge or VRF master as down only once every device
enslaved to it goes down. That is right for a bond and wrong for a bridge: a bridge that keeps another port stays up,
yet every peer reachable only through the downed port is cut off. Neither end sees a carrier change, both hold the
session for their hold time (FRR default 180 s), nothing is watched, `_wait_fault_visible` logs "no BGP session runs
over the downed links; relying on the settle and hold windows", and `route 10.1.0.0/24 protocol bgp` on r2 passes on
the state from before the fault.

- (a) Linux: r1 eth1 and eth2 are ports of an in-container bridge br0 holding 10.0.100.1/24; the eBGP session to r2
  (10.0.100.2) runs over eth1, then a containerlab bridge; eth2 goes to r3.
- (b) SONiC VS: vlanmgr enslaves `dummy` to `Bridge`, so `Bridge` never goes down with Ethernet0; the session runs on
  the SVI `Vlan100@Bridge` (10.0.100.1/24). Shape from SONiC's vlanmgr, not captured live (as the adversary says).
- (b') SONiC VS, found while writing (b): the far end of a SONiC port is never looked up. `Lab.peers_of(r1, "Ethernet0")`
  matches the topology's links, which name the container interface (`r1:eth1`), so it finds nobody. On a routed port
  that carries the session address itself, r1's end drops at once with the carrier, r2 behind the clab bridge holds it
  for 180 s, only r1's end is watched, and the route check on r2 passes on the state from before the fault.
- (c) acceptance risk 1: the kernel creates `/sys/class/net/bonding_masters` (a file, not an interface) in every
  network namespace once the bonding module is loaded, so `ls /sys/class/net` lists it. `Lab.link_tree` runs
  `ip -o link show dev bonding_masters`, which fails, and every `link_down`, plain links included, exits 2.

Device output: derived, not captured. The lab is the real `netdryrun.lab.Lab` (topology written to a temporary folder)
whose `exec` is a fake kernel built here (extending FP-042-LINKDOWNSTACKED's). It answers, as iproute2 prints them,
`ip [-o] [-d] [-j] [-4|-6] [-br] link|addr show [dev X]` (`master M` on enslaved devices; under -d the kind: `bridge`,
`bond`, `dummy`, `vlan`, `gre`, `tun`, `vrf`, `veth`, and the slave kind: `bridge_slave`, `bond_slave`, `vrf_slave`;
JSON with `master` and `linkinfo.info_kind`/`info_slave_kind`), `ip link set dev X up|down`, `ls /sys/class/net[/X]`
(upper_/lower_ links, `master`, `brport`, `brif`, `bonding`), `cat /sys/class/net/X/{carrier,operstate,ifindex,iflink,
type}` and `cat /sys/class/net/bonding_masters`, and SONiC's lanemap.ini and `sonic-db-cli CONFIG_DB hget PORT|X
lanes`. Anything else exits 1 ("not in the fake kernel"). Carrier as the kernel keeps it: a VLAN device follows its
lower device; a bridge or bond has carrier while any port or member has it; dummy, gre and VRF devices keep it. The
BGP drivers are fakes on the same clock: an end whose own device loses carrier drops at once; otherwise it holds the
session (and r2 the route 10.1.0.0/24) until 180 s after the path between r1 and r2 broke.

The rule: the session over the downed port is watched (so the run waits until it goes down and the route check
fails), or the scenario stops with a LabError. Never the "no BGP session" line with a judgement made on the state from
before the fault. And a `bonding_masters` entry must not stop a plain `link_down`.
"""
import ipaddress
import json

from netdryrun import runner
from netdryrun.config import Fault, Scenario, _validate_check
from netdryrun.drivers.base import BgpNeighbor, DriverError, Observation, Route
from netdryrun.lab import ExecResult, Lab, LabError

FRR = "quay.io/frrouting/frr:10.4.1"
HOLD_TIME = 180.0
NOTHING_WATCHED = "no BGP session runs over the downed links"
BOTH_ENDS = [("r1", "default", "10.0.100.2"), ("r2", "default", "10.0.100.1")]


def topology(name, r1_kind="linux", r1_image=FRR, extra_nodes="", links=None):
    links = links if links is not None else [("r1:eth1", "br1:br1-p1"), ("r2:eth1", "br1:br1-p2"),
                                             ("r1:eth2", "r3:eth1")]
    text = (f"name: {name}\ntopology:\n  nodes:\n    r1: {{kind: {r1_kind}, image: {r1_image}}}\n"
            f"    r2: {{kind: linux, image: {FRR}}}\n    r3: {{kind: linux, image: alpine:3.20}}\n"
            f"    br1: {{kind: bridge}}\n{extra_nodes}  links:\n")
    return text + "".join(f'    - endpoints: ["{a}", "{b}"]\n' for a, b in links)


class Dev:
    def __init__(self, name, index, mac, addrs=(), kind="veth", lower=None, master=None, vlan=None, peer_index=None,
                 tunnel=None):
        self.name, self.index, self.mac, self.addrs = name, index, mac, list(addrs)
        self.kind, self.lower, self.master, self.vlan = kind, lower, master, vlan
        self.peer_index, self.tunnel = peer_index, tunnel
        self.up = True


def base(n):
    return [Dev("lo", 1, "00:00:00:00:00:00", ["127.0.0.1/8", "::1/128"], kind="loopback"),
            Dev("eth0", 2, f"02:42:ac:14:14:0{n}", [f"172.20.20.{n + 1}/24"], peer_index=30 + n)]


def mac(n, i):
    return f"aa:c1:ab:0{n}:00:0{i}"


def far_end(n):
    """r2/r3: eth1 carrying 10.0.100.n/24 itself."""
    return base(n) + [Dev("eth1", 5, mac(n, 1), [f"10.0.100.{n}/24", f"fe80::a8c1:abff:fe0{n}:1/64"],
                          peer_index=40 + n)]


def bridge_r1():
    """(a) r1: eth1 and eth2 are ports of br0; the SVI address 10.0.100.1/24 sits on br0."""
    return base(1) + [Dev("eth1", 5, mac(1, 1), [], master="br0", peer_index=41),
                      Dev("eth2", 6, mac(1, 2), [], master="br0", peer_index=51),
                      Dev("br0", 7, mac(1, 1), ["10.0.100.1/24", "fe80::a8c1:abff:fe01:1/64"], kind="bridge")]


def sonic_r1():
    """(b) SONiC VS r1: Ethernet0 (on eth1) is a member of Bridge with vlanmgr's dummy; the SVI Vlan100@Bridge holds
    10.0.100.1/24. Ethernet4 (on eth2) is a routed port with no address."""
    return base(1) + [Dev("eth1", 5, mac(1, 1), [], peer_index=41),
                      Dev("eth2", 6, mac(1, 2), [], peer_index=51),
                      Dev("Ethernet0", 10, "52:54:00:12:34:56", [], kind="tun", master="Bridge"),
                      Dev("Ethernet4", 11, "52:54:00:12:34:56", [], kind="tun"),
                      Dev("Bridge", 12, "52:54:00:12:34:56", [], kind="bridge"),
                      Dev("dummy", 13, "6a:2b:9e:01:02:03", [], kind="dummy", master="Bridge"),
                      Dev("Vlan100", 14, "52:54:00:12:34:56", ["10.0.100.1/24", "fe80::5054:ff:fe12:3456/64"],
                          kind="vlan", lower="Bridge", vlan=100)]


def sonic_routed_r1():
    """(b') SONiC VS r1: Ethernet0 (on eth1) is a routed port carrying 10.0.100.1/24 itself."""
    return base(1) + [Dev("eth1", 5, mac(1, 1), [], peer_index=41),
                      Dev("eth2", 6, mac(1, 2), [], peer_index=51),
                      Dev("Ethernet0", 10, "52:54:00:12:34:56", ["10.0.100.1/24", "fe80::5054:ff:fe12:3456/64"],
                          kind="tun"),
                      Dev("Ethernet4", 11, "52:54:00:12:34:56", [], kind="tun")]


def plain_r1():
    """(c) r1: eth1 carrying 10.0.100.1/24 itself; eth2 to r3 with no address."""
    return base(1) + [Dev("eth1", 5, mac(1, 1), ["10.0.100.1/24", "fe80::a8c1:abff:fe01:1/64"], peer_index=41),
                      Dev("eth2", 6, mac(1, 2), [], peer_index=51)]


LANEMAP = "eth1:25,26,27,28\neth2:29,30,31,32\n"
PORT_LANES = {"Ethernet0": "25,26,27,28", "Ethernet4": "29,30,31,32"}


class Clock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t

    def sleep(self, s):
        self.t += s


class KernelLab(Lab):
    """The real Lab, with `exec` answered by a fake kernel per node."""

    def __init__(self, topo, devices, clock, bonding_masters=False):
        super().__init__(topo)
        self.devs = {node: {d.name: d for d in devs} for node, devs in devices.items()}
        self.clock = clock
        self.bonding_masters = bonding_masters
        self.down_at: dict[tuple[str, str], float] = {}
        self.commands: list[tuple[str, str]] = []

    # --- what the kernel shows ----------------------------------------------------------------------------
    def members(self, node, d):
        return [m for m in self.devs[node].values() if m.master == d.name]

    def carrier(self, node, d):
        if not d.up:
            return False
        if d.kind == "vlan":
            return self.carrier(node, self.devs[node][d.lower])
        if d.kind in ("bridge", "bond"):
            return any(self.carrier(node, m) for m in self.members(node, d))
        return True

    def _label(self, d):
        if d.lower:
            return f"{d.name}@{d.lower}"
        return f"{d.name}@if{d.peer_index}" if d.peer_index else d.name

    def _flags(self, node, d):
        if d.kind == "loopback":
            return ["LOOPBACK", "UP", "LOWER_UP"]
        f = ["POINTOPOINT", "NOARP"] if d.kind == "gre" else ["BROADCAST", "MULTICAST"]
        if d.kind == "bond":
            f.append("MASTER")
        if d.master and self.devs[node][d.master].kind == "bond":
            f.append("SLAVE")
        if d.up:
            f.append("UP")
            if self.carrier(node, d):
                f.append("LOWER_UP")
            else:
                f.insert(0, "NO-CARRIER")
        return f

    def _state(self, node, d):
        if d.kind in ("loopback", "dummy", "gre"):
            return "UNKNOWN" if d.up else "DOWN"
        if not d.up:
            return "DOWN"
        if self.carrier(node, d):
            return "UP"
        return "LOWERLAYERDOWN" if d.kind == "vlan" or d.peer_index else "DOWN"

    def _kind_details(self, node, d):
        out = ""
        if d.kind == "vlan":
            out += f"\\    vlan protocol 802.1Q id {d.vlan} <REORDER_HDR> "
        elif d.kind == "veth":
            out += "\\    veth "
        elif d.kind == "bridge":
            out += ("\\    bridge forward_delay 1500 hello_time 200 max_age 2000 ageing_time 30000 stp_state 0 "
                    "priority 32768 vlan_filtering 0 vlan_protocol 802.1Q ")
        elif d.kind == "bond":
            out += "\\    bond mode active-backup miimon 100 updelay 0 downdelay 0 peer_notify_delay 0 "
        elif d.kind == "dummy":
            out += "\\    dummy "
        elif d.kind == "gre":
            local, remote, _ = d.tunnel
            out += f"\\    gre remote {remote} local {local} dev {d.lower} ttl inherit pmtudisc "
        elif d.kind == "tun":
            out += "\\    tun type tap pi off vnet_hdr off persist on "
        elif d.kind == "vrf":
            out += "\\    vrf table 10 "
        if d.master:
            mk = self.devs[node][d.master].kind
            if mk == "bridge":
                out += ("\\    bridge_slave state forwarding priority 32 cost 2 hairpin off guard off root_block off "
                        "fastleave off learning on flood on ")
            elif mk == "bond":
                state = "ACTIVE" if self.carrier(node, d) else "BACKUP"
                out += f"\\    bond_slave state {state} mii_status {'UP' if self.carrier(node, d) else 'DOWN'} "
            elif mk == "vrf":
                out += "\\    vrf_slave table 10 "
        return out

    def _link_line(self, node, d, details):
        mtu = {"loopback": 65536, "gre": 1476}.get(d.kind, 1500 if d.name == "eth0" else 9100)
        master = f" master {d.master}" if d.master else ""
        line = (f"{d.index}: {self._label(d)}: <{','.join(self._flags(node, d))}> mtu {mtu} qdisc noqueue{master} "
                f"state {self._state(node, d)} mode DEFAULT group default qlen 1000\\    ")
        if d.kind == "loopback":
            line += f"link/loopback {d.mac} brd 00:00:00:00:00:00"
        elif d.kind == "gre":
            line += f"link/gre {d.tunnel[0]} peer {d.tunnel[1]}"
        else:
            line += f"link/ether {d.mac} brd ff:ff:ff:ff:ff:ff"
        if d.peer_index:
            line += " link-netnsid 0"
        if details:
            line += " promiscuity 0 allmulti 0 minmtu 68 maxmtu 65535 " + self._kind_details(node, d)
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
                brd = "" if iface.ip.is_loopback or d.kind == "gre" else f" brd {iface.network.broadcast_address}"
                out.append(f"{d.index}: {d.name:<8} inet {a}{brd} scope {scope} {d.name}\\       valid_lft forever "
                           "preferred_lft forever")
            else:
                scope = "host" if iface.ip.is_loopback else "link" if iface.ip.is_link_local else "global"
                out.append(f"{d.index}: {d.name:<8} inet6 {a} scope {scope} \\       valid_lft forever "
                           "preferred_lft forever")
        return out

    def _json(self, node, d, obj, family, details):
        j = {"ifindex": d.index, "ifname": d.name, "flags": self._flags(node, d), "mtu": 9100, "qdisc": "noqueue",
             "operstate": self._state(node, d), "group": "default",
             "link_type": {"loopback": "loopback", "gre": "gre"}.get(d.kind, "ether"), "address": d.mac}
        if d.master:
            j["master"] = d.master
        if d.lower:
            j["link"] = d.lower
        elif d.peer_index:
            j["link_index"] = d.peer_index
            j["link_netnsid"] = 0
        if details and d.kind != "loopback":
            info = {"info_kind": d.kind}
            if d.kind == "vlan":
                info["info_data"] = {"protocol": "802.1Q", "id": d.vlan, "flags": ["REORDER_HDR"]}
            if d.master:
                info["info_slave_kind"] = {"bridge": "bridge_slave", "bond": "bond_slave",
                                           "vrf": "vrf_slave"}[self.devs[node][d.master].kind]
            j["linkinfo"] = info
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
            if d.up:
                self.down_at.pop((node, d.name), None)
            else:
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
        elif rest[:1] == ["master"] and len(rest) == 2:
            devs = [d for d in devs if d.master == rest[1]]
        elif rest:
            return None
        family = 4 if "-4" in opts else 6 if "-6" in opts else 0
        details = bool(opts & {"-d", "-details"})
        if opts & {"-j", "-json"}:
            return 0, json.dumps([self._json(node, d, obj, family, details) for d in devs]) + "\n", ""
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
            return 0, "".join(self._link_line(node, d, details) + "\n" for d in devs), ""
        return 0, "".join(x + "\n" for d in devs for x in self._addr_lines(d, family)), ""

    def _sys(self, node, argv):
        path = argv[1].rstrip("/")
        parts = path.split("/")[4:]   # after /sys/class/net
        devs = self.devs[node]
        if argv[0] == "ls":
            if not parts:
                names = sorted(devs) + (["bonding_masters"] if self.bonding_masters else [])
                return 0, " ".join(sorted(names)) + "\n", ""
            if parts == ["bonding_masters"] and self.bonding_masters:
                return 0, path + "\n", ""
            d = devs.get(parts[0])
            if d is None:
                return 2, "", f"ls: cannot access '{argv[1]}': No such file or directory\n"
            if len(parts) == 2 and parts[1] == "brif" and d.kind == "bridge":
                return 0, "  ".join(sorted(m.name for m in self.members(node, d))) + "\n", ""
            if len(parts) != 1:
                return None
            entries = ["addr_assign_type", "address", "carrier", "dev_id", "flags", "ifindex", "iflink", "mtu",
                       "operstate", "statistics", "subsystem", "type", "uevent"]
            entries += [f"upper_{u.name}" for u in devs.values() if u.lower == d.name and u.kind == "vlan"]
            entries += [f"lower_{d.lower}"] if d.lower and d.kind == "vlan" else []
            if d.master:
                entries += ["master", f"upper_{d.master}"]
                mk = devs[d.master].kind
                entries += ["brport"] if mk == "bridge" else ["bonding_slave"] if mk == "bond" else []
            members = self.members(node, d)
            entries += [f"lower_{m.name}" for m in members]
            entries += ["bridge", "brif"] if d.kind == "bridge" else ["bonding"] if d.kind == "bond" else []
            return 0, "  ".join(sorted(entries)) + "\n", ""
        # cat
        if parts == ["bonding_masters"] and self.bonding_masters:
            return 0, " ".join(d.name for d in devs.values() if d.kind == "bond") + "\n", ""
        if len(parts) != 2 or parts[0] not in devs:
            return 1, "", f"cat: {argv[1]}: No such file or directory\n"
        d, attr = devs[parts[0]], parts[1]
        if attr == "carrier":
            if not d.up:
                return 1, "", f"cat: {argv[1]}: Invalid argument\n"
            return 0, ("1" if self.carrier(node, d) else "0") + "\n", ""
        if attr == "operstate":
            return 0, self._state(node, d).lower() + "\n", ""
        if attr == "ifindex":
            return 0, f"{d.index}\n", ""
        if attr == "iflink":
            low = devs.get(d.lower) if d.lower else None
            return 0, f"{low.index if low else d.peer_index or d.index}\n", ""
        if attr == "type":
            return 0, {"loopback": "772", "gre": "778"}.get(d.kind, "1") + "\n", ""
        return 1, "", f"cat: {argv[1]}: No such file or directory\n"

    def exec(self, node, cmd, timeout=60, input=None):
        argv = list(cmd)
        if argv[:2] in (["sh", "-c"], ["bash", "-c"], ["bash", "-lc"]) and len(argv) == 3:
            argv = argv[2].split()
        self.commands.append((node, " ".join(argv)))
        r = None
        if argv and argv[0] == "ip":
            r = self._ip(node, argv)
        elif argv[:1] in (["ls"], ["cat"]) and len(argv) == 2 and argv[1].rstrip("/").startswith("/sys/class/net"):
            r = self._sys(node, argv)
        elif argv == ["cat", "/usr/share/sonic/hwsku/lanemap.ini"] and self.nodes[node].kind == "sonic-vs":
            r = 0, LANEMAP, ""
        elif argv[:4] == ["sonic-db-cli", "CONFIG_DB", "hget", argv[3] if len(argv) > 3 else ""] and len(argv) == 5 \
                and argv[4] == "lanes" and self.nodes[node].kind == "sonic-vs":
            r = 0, PORT_LANES.get(argv[3].removeprefix("PORT|"), "") + "\n", ""
        if r is None:
            r = 1, "", f"not in the fake kernel: {' '.join(argv)}\n"
        return ExecResult(cmd, *r)


def cut_when_down(*ports):
    """The path between r1 and r2 breaks when every one of r1's `ports` is down: the time it broke, else None."""
    def cut(lab):
        if any(lab.devs["r1"][p].up for p in ports):
            return None
        return max(lab.down_at[("r1", p)] for p in ports)
    return cut


class Bgp:
    """A BGP speaker with one eBGP session (`key`) on its device `dev`: it drops at once when `dev` loses carrier,
    and otherwise holds the session (and, on r2, r1's route 10.1.0.0/24) until HOLD_TIME after the path broke."""
    name = "frr"

    def __init__(self, lab, node, key, dev, cut):
        self.lab, self.node, self.key, self.dev, self.cut = lab, node, key, dev, cut

    def established(self):
        if not self.lab.carrier(self.node, self.lab.devs[self.node][self.dev]):
            return False
        t = self.cut(self.lab)
        return t is None or self.lab.clock() < t + HOLD_TIME

    def bgp_neighbors(self, vrf="default"):
        up = self.established()
        n = BgpNeighbor(self.key, "established" if up else "active", {"ipv4-unicast": 1} if up else {})
        return Observation({self.key: n}, [])

    def routes(self, prefix, vrf="default"):
        if prefix != "10.1.0.0/24":
            return Observation([], [])
        if self.node == "r1":
            return Observation([Route(prefix, "connected", True)], [])
        return Observation([Route(prefix, "bgp", True)] if self.established() else [], [])


def make_lab(tmp_path, monkeypatch, topo_text, devices, r1_dev, r2_dev="eth1", cut=None, bonding_masters=False):
    topo = tmp_path / "topology.clab.yml"
    topo.write_text(topo_text, encoding="utf-8")
    clock = Clock()
    monkeypatch.setattr(runner, "_clock", clock)
    monkeypatch.setattr(runner, "_sleep", clock.sleep)
    lab = KernelLab(topo, devices, clock, bonding_masters=bonding_masters)
    cut = cut or cut_when_down("eth1")
    drivers = {"r1": Bgp(lab, "r1", "10.0.100.2", r1_dev, cut), "r2": Bgp(lab, "r2", "10.0.100.1", r2_dev, cut)}
    return lab, drivers


def driver_for(drivers):
    def get(n):
        if n not in drivers:
            raise DriverError(f"{n} runs no routing daemon")
        return drivers[n]
    return get


def bridge_lab(tmp_path, monkeypatch):
    return make_lab(tmp_path, monkeypatch, topology("rt0078b"),
                    {"r1": bridge_r1(), "r2": far_end(2), "r3": far_end(3)}, r1_dev="br0")


def sonic_lab(tmp_path, monkeypatch):
    return make_lab(tmp_path, monkeypatch, topology("rt0078s", r1_kind="sonic-vs", r1_image="docker-sonic-vs:latest"),
                    {"r1": sonic_r1(), "r2": far_end(2), "r3": far_end(3)}, r1_dev="Vlan100",
                    cut=cut_when_down("Ethernet0"))


def sonic_routed_lab(tmp_path, monkeypatch):
    return make_lab(tmp_path, monkeypatch, topology("rt0078r", r1_kind="sonic-vs", r1_image="docker-sonic-vs:latest"),
                    {"r1": sonic_routed_r1(), "r2": far_end(2), "r3": far_end(3)}, r1_dev="Ethernet0",
                    cut=cut_when_down("Ethernet0"))


def scenario(iface="eth1", timeout=300):
    check = _validate_check(0, {"type": "route", "node": "r2", "prefix": "10.1.0.0/24", "protocol": "bgp"}, timeout,
                            prefix="scenarios[0].checks")
    return Scenario("r1-r2 link fails", [Fault("link_down", "r1", iface)], [check])


def run(lab, drivers, sc):
    logs: list[str] = []
    try:
        results = runner.run_scenario(lab, sc, drivers, settle=10, hold=10, log=logs.append,
                                      driver_for=driver_for(drivers))
    except LabError as e:
        return None, logs, e
    return results, logs, None


def assert_judged_after_the_fault(results, logs, what):
    assert not any(NOTHING_WATCHED in x for x in logs), (
        f"the scenario logged that no BGP session runs over the downed link, while {what}: {logs}")
    assert results and not any(r.passed for r in results), (
        "route 10.1.0.0/24 on r2 passed on the state from before the fault (r2 keeps it for its 180 s hold time): "
        f"{[(r.passed, r.detail) for r in results]}; log: {logs}")


# --- (a) a Linux bridge in r1 that keeps another port ------------------------------------------------------------
def test_link_sessions_finds_the_session_on_a_bridge_that_keeps_another_port(tmp_path, monkeypatch):
    lab, drivers = bridge_lab(tmp_path, monkeypatch)
    try:
        watch, every = runner._link_sessions(lab, [("r1", "eth1")], ["default"], driver_for(drivers))
    except LabError:
        return   # refusing a bridge port whose sessions it can't place is allowed
    assert set(BOTH_ENDS) <= set(watch) and set(BOTH_ENDS) <= set(every), (
        "taking r1 eth1 down cuts r1 (10.0.100.1 on br0, which keeps eth2) off from r2 (10.0.100.2, reachable only "
        f"through eth1); neither end sees a carrier change, but _link_sessions watches {watch} (every: {every}); "
        f"commands: {lab.commands}")


def test_link_down_on_a_bridge_port_is_not_judged_before_the_fault(tmp_path, monkeypatch):
    lab, drivers = bridge_lab(tmp_path, monkeypatch)
    results, logs, err = run(lab, drivers, scenario())
    if err is not None:
        return   # stopping the scenario with an error is allowed
    assert_judged_after_the_fault(results, logs, "r1's eBGP session to r2 runs over eth1 through its bridge br0")


# --- (b) SONiC: Bridge kept up by vlanmgr's dummy member, session on Vlan100@Bridge ---------------------------------
def test_link_sessions_finds_the_sonic_svi_session_over_the_downed_port(tmp_path, monkeypatch):
    lab, drivers = sonic_lab(tmp_path, monkeypatch)
    try:
        watch, every = runner._link_sessions(lab, [("r1", "Ethernet0")], ["default"], driver_for(drivers))
    except LabError:
        return
    near = ("r1", "default", "10.0.100.2")
    assert near in watch and near in every, (
        "taking SONiC r1 Ethernet0 down cuts its SVI Vlan100@Bridge (10.0.100.1/24; Bridge keeps vlanmgr's dummy "
        f"member) off from r2, but _link_sessions watches {watch} (every: {every}); commands: {lab.commands}")


def test_sonic_link_down_on_a_vlan_member_port_is_not_judged_before_the_fault(tmp_path, monkeypatch):
    lab, drivers = sonic_lab(tmp_path, monkeypatch)
    results, logs, err = run(lab, drivers, scenario("Ethernet0"))
    if err is not None:
        return
    assert_judged_after_the_fault(results, logs, "SONiC r1's eBGP session to r2 runs on Vlan100@Bridge over Ethernet0")


# --- (b') SONiC: the far end of a SONiC port (topology names `r1:eth1`, the fault names Ethernet0) ------------------
def test_sonic_port_far_end_is_watched(tmp_path, monkeypatch):
    lab, drivers = sonic_routed_lab(tmp_path, monkeypatch)
    try:
        watch, every = runner._link_sessions(lab, [("r1", "Ethernet0")], ["default"], driver_for(drivers))
    except LabError:
        return
    far = ("r2", "default", "10.0.100.1")
    assert far in watch and far in every, (
        "SONiC r1 Ethernet0 sits on the lab link r1:eth1 -> br1 -> r2:eth1, and r2's session to 10.0.100.1 runs over "
        f"it, but _link_sessions watches {watch} (every: {every}): Lab.peers_of(r1, 'Ethernet0') = "
        f"{lab.peers_of('r1', 'Ethernet0')} (the topology names the container interface eth1)")


def test_sonic_link_down_on_a_routed_port_is_not_judged_before_the_far_end_drops(tmp_path, monkeypatch):
    lab, drivers = sonic_routed_lab(tmp_path, monkeypatch)
    results, logs, err = run(lab, drivers, scenario("Ethernet0"))
    if err is not None:
        return
    assert results and not any(r.passed for r in results), (
        "route 10.1.0.0/24 on r2 passed on the state from before the fault: r2, behind the clab bridge, keeps the "
        "session to SONiC r1 and its route for its 180 s hold time, and only r1's end was watched: "
        f"{[(r.passed, r.detail) for r in results]}; log: {logs}")


# --- (c) acceptance risk 1: /sys/class/net/bonding_masters --------------------------------------------------------
def test_bonding_masters_entry_does_not_break_link_down(tmp_path, monkeypatch):
    lab, drivers = make_lab(tmp_path, monkeypatch, topology("rt0078m"),
                            {"r1": plain_r1(), "r2": far_end(2), "r3": far_end(3)}, r1_dev="eth1",
                            bonding_masters=True)
    try:
        watch, every = runner._link_sessions(lab, [("r1", "eth1")], ["default"], driver_for(drivers))
    except LabError as e:
        raise AssertionError(
            "with the bonding module loaded the kernel lists /sys/class/net/bonding_masters (a file, not an "
            f"interface) in every namespace; a plain link_down must still find its session, but: {e}") from None
    assert sorted(watch) == BOTH_ENDS and sorted(every) == BOTH_ENDS, (watch, every)

    lab, drivers = make_lab(tmp_path, monkeypatch, topology("rt0078m"),
                            {"r1": plain_r1(), "r2": far_end(2), "r3": far_end(3)}, r1_dev="eth1",
                            bonding_masters=True)
    results, logs, err = run(lab, drivers, scenario())
    assert err is None, (
        f"a plain link_down on a host with the bonding module loaded stopped with exit 2: {err}; log: {logs}")
    assert any("the fault took effect after 180s" in x for x in logs), logs
    assert [r.passed for r in results] == [False], [r.detail for r in results]
    assert lab.devs["r1"]["eth1"].up   # restored
