"""The management path out of the lab (red team round 4, B3; design: design/redteam-041-fixes-round4.md, "e, option A"
and its revision R1-R12).

Docker gives every Linux container a default route over its management interface (`default via 172.20.20.1 dev eth0`),
and containerlab's built-in cEOS config adds `ip route 0.0.0.0/0 <mgmt gw>` in VRF default. With the lab route gone, a
ping left over that path, Docker masqueraded it, and an address the Docker host reaches answered: `expect: success`
passed without the lab. Production has no such route, so the lab loses it too: after deploy and `setup:`, before the
first check, exactly Docker's (or containerlab's) default via the management gateway is deleted, and any other route on a
management device is a run error. It is checked again before the hold, around each scenario and around every ping on
FRR/SONiC. Every failure here is a run error (exit 2), never an unready sample: an unready sample reads as a plain
failure in a lab where other checks passed.
"""
from __future__ import annotations

import ipaddress
import json
import re
from dataclasses import dataclass, field

from .lab import NETNS_HELPER_IMAGE, Lab, LabError

LINUX_KINDS = ("linux", "sonic-vs", "sonic_vs")
EOS_KINDS = ("arista_ceos", "ceos")
JUNOS_KINDS = ("juniper_cjunosevolved", "cjunosevolved")
NOT_CONTAINERS = ("host", "ext-container", "bridge", "ovs-bridge")
# route types that never carry a packet out of the node
_LOCAL_TYPES = ("local", "broadcast", "multicast", "anycast")
_TYPES = _LOCAL_TYPES + ("unicast", "unreachable", "blackhole", "prohibit", "throw", "nat")


class ManagementPathError(LabError):
    """A route out of the lab over the management network: the run can't show what the lab does."""


@dataclass
class Mgmt:
    """A node's management network, from Docker: its networks' subnets and gateways, and the devices holding them."""
    node: str
    mode: str                                   # Docker NetworkMode: "default", a network name, "host", "container:X"
    subnets: list = field(default_factory=list)
    gateways: list = field(default_factory=list)
    devices: set = field(default_factory=set)
    removed: list = field(default_factory=list)  # the routes this run deleted, as they printed
    kind: str = ""                              # "linux", "eos", "junos" or "" (not touched)
    cid: str = ""                               # the container's id (a `container:<id>` network mode names it)
    vrfs: set = field(default_factory=lambda: {"default"})   # Junos: the instances read
    tables: str = "all"                         # "all", or "main" where the node's `ip` can't list every table
    via: str = "container"                      # "container": the node's own `ip`; "helper": NETNS_HELPER_IMAGE


def docker_mgmt(lab: Lab, node: str) -> Mgmt:
    """The container's network mode, and every Docker network it is attached to (each is management: R9)."""
    data = lab.docker_inspect(node)
    try:
        mode = str(data["HostConfig"]["NetworkMode"])
        nets = data["NetworkSettings"]["Networks"] or {}
    except (KeyError, TypeError):
        raise LabError(f"{node}: `docker inspect` printed no network settings, so its management network can't be "
                       "read") from None
    m = Mgmt(node, mode)
    m.cid = str(data.get("Id", ""))
    for name, n in nets.items():
        if not isinstance(n, dict):
            raise LabError(f"{node}: Docker network {name!r} reads {str(n)[:80]}")
        for addr, plen, gw in ((n.get("IPAddress"), n.get("IPPrefixLen"), n.get("Gateway")),
                               (n.get("GlobalIPv6Address"), n.get("GlobalIPv6PrefixLen"), n.get("IPv6Gateway"))):
            if addr:
                m.subnets.append(ipaddress.ip_interface(f"{addr}/{plen}").network)
            if gw:
                m.gateways.append(ipaddress.ip_address(gw))
    return m


# ------------------------------------------------------------------------------------------------- Linux routes

@dataclass
class LinuxRoute:
    line: str
    rtype: str
    prefix: str        # "default" or an address/prefix as printed
    dev: str
    via: str
    proto: str
    table: str
    family: int


def parse_ip_route(text: str, family: int) -> list[LinuxRoute]:
    """`ip [-6] route show [table all]`, iproute2 or busybox text. A multipath route prints its legs on indented
    `nexthop` lines: each leg is its own entry (same prefix, its own via and dev)."""
    out: list[LinuxRoute] = []
    head: dict | None = None
    for raw in text.splitlines():
        if not raw.strip():
            continue
        tok = raw.split()
        if raw[0].isspace():
            if head is None or tok[0] != "nexthop":
                raise LabError(f"`ip route` printed a line it doesn't explain: {raw.strip()[:120]!r}")
            kv = _pairs(tok[1:])
            out.append(LinuxRoute(raw.strip(), head["rtype"], head["prefix"], kv.get("dev", ""), kv.get("via", ""),
                                  head["proto"], head["table"], family))
            head["legs"] += 1
            continue
        rtype = tok[0] if tok[0] in _TYPES else "unicast"
        rest = tok[1:] if tok[0] in _TYPES else tok
        if not rest:
            raise LabError(f"`ip route` printed a route without a destination: {raw[:120]!r}")
        kv = _pairs(rest[1:])
        head = {"rtype": rtype, "prefix": rest[0], "proto": kv.get("proto", ""), "table": kv.get("table", "main"),
                "legs": 0}
        out.append(LinuxRoute(raw.strip(), rtype, rest[0], kv.get("dev", ""), kv.get("via", ""), head["proto"],
                              head["table"], family))
    return out


_FLAGS = frozenset({"onlink", "linkdown", "dead", "pervasive", "offload", "trap", "rt_offload", "rt_trap", "notify",
                    "cache", "lock", "rt_offload_failed", "unresolved"})
# the keys that end an `encap <type> ...` block (whose own fields vary by type: mpls labels, seg6 segments, ip ttl ...)
_KEYS = frozenset({"via", "dev", "proto", "table", "scope", "src", "metric", "pref", "weight", "nhid", "mtu", "expires",
                   "realm", "error", "advmss", "hoplimit"})


def _pairs(tok: list[str]) -> dict:
    """`key value` pairs after the destination; flags (onlink, linkdown, ...) take no value. `via inet6 X` (an IPv4
    route via an IPv6 next hop) reads as via X. The first value of a key wins."""
    kv: dict = {}
    i = 0
    while i < len(tok):
        k = tok[i]
        if k in _FLAGS:
            i += 1
        elif k == "encap":
            i += 2
            while i < len(tok) and tok[i] not in _KEYS:
                i += 1
        elif k == "via" and i + 1 < len(tok) and tok[i + 1] in ("inet", "inet6"):
            kv.setdefault("via", tok[i + 2] if i + 2 < len(tok) else "")
            i += 3
        else:
            kv.setdefault(k, tok[i + 1] if i + 1 < len(tok) else "")
            i += 2
    return kv


def _in_mgmt_subnet(prefix: str, m: Mgmt) -> bool:
    try:
        net = ipaddress.ip_network(prefix, strict=False)
    except ValueError:
        return False
    return any(net == s for s in m.subnets)


def classify_linux(routes: list[LinuxRoute], m: Mgmt) -> tuple[list[LinuxRoute], list[LinuxRoute]]:
    """(Docker's own defaults, to delete; every other route out over a management device, a run error)."""
    docker, other = [], []
    multipath = {(r.family, r.prefix, r.table) for r in routes if r.line.startswith("nexthop")}
    for r in routes:
        if not r.dev and r.rtype == "unicast" and not r.line.startswith("nexthop") and \
                (r.family, r.prefix, r.table) not in multipath:
            # a route printing no device (a nexthop object `nhid N`, an unparsed form) may leave over eth0: refused
            other.append(r)
            continue
        if r.dev not in m.devices or r.rtype in _LOCAL_TYPES:
            continue
        if r.prefix.startswith("fe80:") and not r.via:            # the link-local prefix every interface has
            continue
        if not r.via and r.proto in ("kernel", "") and _in_mgmt_subnet(r.prefix, m):
            continue   # the connected management subnet (busybox prints it without `proto kernel`)
        if not r.via and r.prefix.startswith("ff") and r.family == 6:            # multicast (ff00::/8), table local
            continue
        is_default = r.prefix in ("default", "0.0.0.0/0", "::/0")
        if (is_default and r.via and ipaddress.ip_address(r.via) in m.gateways and r.proto in ("", "boot")
                and r.table == "main" and (r.family, r.prefix, r.table) not in multipath):
            docker.append(r)
        else:
            other.append(r)
    return docker, other


_NO_IP = re.compile(r"(?i)executable file not found|no such file or directory|not found in \$PATH")


def _ip(lab: Lab, m: Mgmt, args: list[str]) -> tuple[int, str, str]:
    """`ip` in the node, as root; where the image has none (nginx, distroless), the same command in the pinned helper
    joined to the node's network namespace. A helper that can't start (an air-gapped host without the image) is a run
    error naming the image to pre-pull."""
    if m.via == "container":
        r = lab.exec_root(m.node, ["ip", *args], timeout=30)
        if not (r.rc in (126, 127) or (r.rc != 0 and _NO_IP.search(r.stderr + r.stdout))):
            return r.rc, r.stdout, r.stderr
        m.via = "helper"
    r = lab.netns_exec(m.node, ["ip", *args], timeout=120)
    if r.rc == 125:   # docker run itself failed: the image couldn't be pulled or the node's namespace joined
        raise LabError(f"{m.node} has no `ip`, and the helper that reads its routes from outside couldn't start: "
                       f"{(r.stderr or r.stdout).strip()[-300:]}. On a host without registry access, run "
                       f"`docker pull {NETNS_HELPER_IMAGE}` first")
    return r.rc, r.stdout, r.stderr


def _scan_linux(lab: Lab, m: Mgmt) -> list[LinuxRoute]:
    routes: list[LinuxRoute] = []
    for fam, flag in ((4, "-4"), (6, "-6")):
        table = ["table", "all"] if m.tables == "all" else []
        rc, out, err = _ip(lab, m, [flag, "route", "show", *table])
        if rc != 0 and m.tables == "all" and fam == 4 and re.search(r"(?i)invalid argument|unknown|usage",
                                                                     err + out):
            # busybox `ip` lists one table at a time: the main table is where Docker puts its route
            rc2, out2, err2 = _ip(lab, m, [flag, "route", "show"])
            if rc2 == 0:
                m.tables, rc, out, err = "main", rc2, out2, err2
        if rc != 0:
            if fam == 6 and re.search(r"(?i)address family not supported", err + out):
                continue   # a node whose kernel has no IPv6 has no IPv6 route out
            raise LabError(f"{m.node}: its routes can't be read (`ip {flag} route show` rc={rc}: "
                           f"{(err or out).strip()[-200:] or 'no output'}), so its route out over the management "
                           "network can't be removed. Give the node iproute2 (or busybox `ip`)")
        routes += parse_ip_route(out, fam)
    return routes


_ADDR_HEAD = re.compile(r"^\d+:\s+([^:@\s]+)(?:@\S+)?:")
_ADDR = re.compile(r"^\s*inet6?\s+(\S+)")


def parse_ip_addr(text: str) -> dict[str, list]:
    """`ip addr show` (iproute2 or busybox): each device's addresses, as interfaces."""
    out: dict[str, list] = {}
    dev = None
    for line in text.splitlines():
        h = _ADDR_HEAD.match(line)
        if h:
            dev = h.group(1)
            out.setdefault(dev, [])
            continue
        a = _ADDR.match(line)
        if a and dev is not None:
            try:
                out[dev].append(ipaddress.ip_interface(a.group(1)))
            except ValueError:
                raise LabError(f"`ip addr show` printed an address it doesn't explain: {line.strip()[:120]!r}") from None
    return out


def _linux_devices(lab: Lab, m: Mgmt) -> None:
    """The devices holding the management subnets: the device of each connected management route (eth0 normally),
    else the device holding a management address (SONiC VS takes eth0 down at boot, which drops its connected and
    default routes but keeps the address: live capture 2026-11-07, sonic_mgmt_eth0_down.txt)."""
    for r in _scan_linux(lab, m):
        if not r.via and r.proto in ("kernel", "") and _in_mgmt_subnet(r.prefix, m) and r.dev:
            m.devices.add(r.dev)
    if not m.devices and m.subnets:
        rc, out, err = _ip(lab, m, ["addr", "show"])
        if rc != 0:
            raise LabError(f"{m.node}: its addresses can't be read (`ip addr show` rc={rc}: "
                           f"{(err or out).strip()[-200:] or 'no output'})")
        for dev, addrs in parse_ip_addr(out).items():
            if any(a.ip in s for a in addrs for s in m.subnets):
                m.devices.add(dev)
    if not m.devices and m.subnets:
        raise LabError(f"{m.node}: no interface holds its management subnet ({', '.join(map(str, m.subnets))}), so its "
                       "management device can't be told apart from a lab interface")


def _offending(node: str, other: list, where: str) -> str:
    return (f"{node} has a route out over the management network ({where}): "
            + "; ".join(getattr(r, "line", str(r)) for r in other[:5])
            + ". A ping over it leaves the lab (Docker reaches beyond it), so the run can't show what the lab does. "
            "Remove it (a route via the management interface is not a lab path)")


def prepare_linux(lab: Lab, m: Mgmt, log) -> None:
    m.kind = "linux"
    _linux_devices(lab, m)
    for dev in sorted(m.devices):   # no router advertisement re-adds an IPv6 default (best effort: R5 catches one)
        if m.via == "helper":
            log(f"note: {m.node}: accept_ra not set (no sysctl in the image); a re-added default is caught before "
                "every ping and phase")
            break
        r = lab.exec_root(m.node, ["sysctl", "-w", f"net.ipv6.conf.{dev}.accept_ra=0"], timeout=30)
        if r.rc != 0:
            log(f"note: {m.node}: accept_ra=0 on {dev} not set ({(r.stderr or r.stdout).strip()[-120:]}); a re-added "
                "default is caught before every ping")
    docker, other = classify_linux(_scan_linux(lab, m), m)
    if other:
        raise ManagementPathError(_offending(m.node, other, "before the checks"))
    for r in docker:
        flag = "-6" if r.family == 6 else "-4"
        rc, out, err = _ip(lab, m, [flag, "route", "del", "default", "via", r.via, "dev", r.dev])
        if rc != 0:
            raise ManagementPathError(f"{m.node}: Docker's default route ({r.line}) could not be deleted "
                                      f"(rc={rc}: {(err or out).strip()[-200:]}); the run won't ping over it")
        m.removed.append(r.line)
    check_linux(lab, m, "after deleting Docker's default route")


def check_linux(lab: Lab, m: Mgmt, when: str) -> None:
    docker, other = classify_linux(_scan_linux(lab, m), m)
    if docker or other:
        raise ManagementPathError(_offending(m.node, docker + other, when))


# ------------------------------------------------------------------------------------------------- cEOS

EOS_MGMT = re.compile(r"^Management\d+(/\d+)*$")


def _eos(lab: Lab, node: str, cmd: str) -> str:
    r = lab.exec(node, ["Cli", "-p", "15", "-c", cmd], timeout=60)
    if r.rc != 0:
        raise LabError(f"{node}: `{cmd}` failed (rc={r.rc}): {(r.stderr or r.stdout).strip()[-200:]}")
    return r.stdout


def classify_eos(text: str, family: int, m: Mgmt) -> tuple[list[tuple[str, str, str]], list[str]]:
    """`show ip[v6] route vrf all | json`: (containerlab's static defaults via the management gateway, as (vrf, prefix,
    gateway); every other route with a via on a Management interface, as text)."""
    try:
        data = json.loads(text)
        vrfs = data["vrfs"]
        assert isinstance(vrfs, dict)
    except (ValueError, KeyError, TypeError, AssertionError):
        raise LabError(f"{m.node}: `show ip{'v6' if family == 6 else ''} route vrf all | json` printed "
                       f"{text.strip()[:150]!r}, so its routes over Management0 can't be read") from None
    ours, other = [], []
    for vrf, v in vrfs.items():
        routes = (v or {}).get("routes")
        if not isinstance(routes, dict):
            raise LabError(f"{m.node}: VRF {vrf} in `show ip route vrf all | json` has no route table")
        for prefix, r in routes.items():
            vias = r.get("vias") if isinstance(r, dict) else None
            if not isinstance(vias, list):
                raise LabError(f"{m.node}: route {prefix} (vrf {vrf}) reads {str(r)[:100]}")
            mg = [x for x in vias if isinstance(x, dict) and EOS_MGMT.match(str(x.get("interface", "")))]
            if not mg:
                continue
            if r.get("routeType") == "connected" and _in_mgmt_subnet(prefix, m):
                continue
            gws = {str(x.get("nexthopAddr", "")) for x in mg}
            if (prefix in ("0.0.0.0/0", "::/0") and r.get("routeType") == "static" and len(mg) == len(vias)
                    and all(g and ipaddress.ip_address(g) in m.gateways for g in gws)):
                ours += [(vrf, prefix, g) for g in sorted(gws)]
            else:
                other.append(f"{prefix} (vrf {vrf}, {r.get('routeType')}) via "
                             + ", ".join(f"{x.get('nexthopAddr') or ''} {x.get('interface')}".strip() for x in mg))
    return ours, other


def _scan_eos(lab: Lab, m: Mgmt):
    ours, other = [], []
    for fam in (4, 6):
        o, x = classify_eos(_eos(lab, m.node, f"show ip{'v6' if fam == 6 else ''} route vrf all | json"), fam, m)
        ours += o
        other += x
    return ours, other


# containerlab's cEOS template: `ip route [vrf V] 0.0.0.0/0 <gw>` and `ipv6 route [vrf V] ::0/0 <gw>` (checked in the
# containerlab binary, 2026-11-06). Read from the config, not the routing table: at deploy the route can be configured
# and not yet installed (Management0 still coming up; live run 2026-11-06), and then appear under the checks.
_EOS_STATIC = re.compile(r"^(ipv6|ip) route (?:vrf (\S+) )?(\S+) (\S+)(.*)$")
EOS_LOAD_WAIT = 180.0


def eos_config_routes(text: str, m: Mgmt) -> tuple[list[str], list[str]]:
    """Config text (`show running-config` or `show startup-config`): (containerlab's defaults via the management
    gateway, as the lines print; every other static route whose next hop is a management gateway or interface)."""
    ours, other = [], []
    for raw in text.splitlines():
        line = raw.strip()
        mt = _EOS_STATIC.match(line)
        if not mt:
            continue
        fam, vrf, prefix, hop, rest = mt.groups()
        try:
            gw = ipaddress.ip_address(hop)
        except ValueError:
            gw = None
        via_mgmt = (gw is not None and gw in m.gateways) or bool(EOS_MGMT.match(hop))
        if not via_mgmt:
            continue
        if prefix in ("0.0.0.0/0", "::0/0", "::/0") and gw is not None and not rest.strip():
            ours.append(line)
        else:
            other.append(line)
    return ours, other


def _eos_key(line: str) -> tuple:
    fam, vrf, prefix, hop, _ = _EOS_STATIC.match(line).groups()
    return fam, vrf or "default", ipaddress.ip_network(prefix, strict=False), ipaddress.ip_address(hop)


def _eos_config(lab: Lab, node: str, which: str) -> str:
    return _eos(lab, node, f"show {which}-config")


def prepare_eos(lab: Lab, m: Mgmt, log, sleep) -> None:
    m.kind = "eos"
    startup, s_other = eos_config_routes(_eos_config(lab, m.node, "startup"), m)
    waited = 0.0
    while True:
        ours, other = eos_config_routes(_eos_config(lab, m.node, "running"), m)
        missing = {_eos_key(x) for x in startup} - {_eos_key(x) for x in ours}
        if not missing or waited >= EOS_LOAD_WAIT:
            break
        sleep(3.0)
        waited += 3.0
    if missing:
        raise ManagementPathError(f"{m.node}: its startup config has containerlab's management route "
                                  f"({'; '.join(sorted(x for x in startup if _eos_key(x) in missing))}) but the "
                                  "running config still "
                                  f"doesn't after {EOS_LOAD_WAIT:g}s, so it can't be removed before the checks")
    if other or s_other:
        raise ManagementPathError(_offending(m.node, sorted(set(other) | set(s_other)), "in its config"))
    if ours:
        _eos(lab, m.node, "\n".join(["configure", *(f"no {ln}" for ln in ours), "end"]))
        m.removed += ours
    check_eos(lab, m, "after deleting containerlab's default route")


def check_eos(lab: Lab, m: Mgmt, when: str) -> None:
    ours, other = eos_config_routes(_eos_config(lab, m.node, "running"), m)
    t_ours, t_other = _scan_eos(lab, m)
    found = ours + other + [f"{p} (vrf {v}) via {g}" for v, p, g in t_ours] + t_other
    if found:
        raise ManagementPathError(_offending(m.node, found, when))


# ------------------------------------------------------------------------------------------------- Junos

def check_junos(lab: Lab, m: Mgmt, when: str) -> None:
    """No containerlab template adds a management default on Junos: one there was configured, so it is a run error
    (never deleted), in the default instance and every VRF a check names (design R2)."""
    from .drivers.junos import JunosDriver
    d = JunosDriver(lab, m.node)
    found = [r for vrf in sorted(m.vrfs) for r in d.management_routes(vrf)]
    if found:
        raise ManagementPathError(_offending(m.node, found, when) + " (on Junos: delete it, or keep management in "
                                  "the mgmt_junos instance)")


# ------------------------------------------------------------------------------------------------- the run

def prepare(lab: Lab, checks: list, log=lambda _: None, sleep=None) -> dict[str, Mgmt]:
    """Before the first check: every lab container's management network read, Docker's (containerlab's) default route
    deleted where the lab's routing table holds it, and the checks refused that would ping over management."""
    state: dict[str, Mgmt] = {}
    if not hasattr(lab, "docker_inspect"):
        # a lab object without Docker: the unit tests' fakes only (lab.Lab always has it; test_mgmt pins that)
        lab.management = state
        return state
    for name, node in sorted(lab.nodes.items()):
        if node.kind in NOT_CONTAINERS:
            continue
        m = docker_mgmt(lab, name)
        state[name] = m
        if m.mode == "host":
            continue                     # the Docker host's own namespace: never touched (R1); checks on it refused
        if m.mode.startswith("container:") or m.mode == "none":
            continue                     # shares another container's namespace (handled there), or has none
        if node.kind in LINUX_KINDS:
            prepare_linux(lab, m, log)
        elif node.kind in EOS_KINDS:
            prepare_eos(lab, m, log, sleep or __import__("time").sleep)
        elif node.kind in JUNOS_KINDS:
            m.kind = "junos"
            m.vrfs |= {c.params.get("vrf", "default") for c in checks if c.node == name}
            check_junos(lab, m, "before the checks")
        log(f"{name}: management default route "
            + (f"removed ({'; '.join(m.removed)})" if m.removed else "none" if m.kind else
               f"not applicable ({node.kind})"))
    refuse_checks(lab, state, checks)
    lab.management = state
    return state


def describe(m: Mgmt, kind: str) -> str:
    if m.mode == "host":
        return "not touched (network-mode host: the Docker host's namespace)"
    if m.mode.startswith("container:"):
        return f"not touched (shares {m.mode[len('container:'):]}'s namespace)"
    if not m.kind:
        return f"not applicable ({kind})"
    how = " (read from outside: no `ip` in the image)" if m.via == "helper" else ""
    return (("removed: " + "; ".join(m.removed)) if m.removed else "none") + how


def _owner(lab: Lab, state: dict, m: Mgmt) -> Mgmt | None:
    """The lab node whose namespace a `container:X` node shares (X by node name, container name or id), else None."""
    target = m.mode[len("container:"):]
    for name, node in lab.nodes.items():
        o = state.get(name)
        if target in (name, node.container) or (o is not None and o.cid and o.cid.startswith(target) and target):
            return o
    return None


def covering(lab: Lab, state: dict, node: str) -> Mgmt | None:
    """The Mgmt whose routes a node's checks run over: its own, or the namespace owner's."""
    m = state.get(node)
    if m is not None and m.mode.startswith("container:"):
        return _owner(lab, state, m)
    return m


NEEDS = {"frr": "linux", "sonic": "linux", "eos": "eos", "junos": "junos"}


def require_covered(lab: Lab, state: dict, node: str, driver: str) -> None:
    """A node a check reads with a routing driver must have had its management route handled (code adversary 2: an
    frr image under another kind, an ext-container)."""
    need = NEEDS.get(driver)
    if need is None or not hasattr(lab, "docker_inspect"):
        return
    m = covering(lab, state, node)
    if m is None or m.kind != need:
        kind = lab.nodes[node].kind if node in lab.nodes else "?"
        raise LabError(f"{node} is read with the {driver} driver, but its kind ({kind}) is not one whose management "
                       "default route Netdryrun removes, so a ping from it could leave the lab over Docker's network. "
                       "Use the kind containerlab documents for that image")


def refuse_checks(lab: Lab, state: dict[str, Mgmt], checks: list) -> None:
    subnets = [s for m in state.values() for s in m.subnets]
    for c in checks:
        m = state.get(c.node)
        if m is not None and (m.mode == "host" or (m.mode.startswith("container:")
                                                   and _owner(lab, state, m) is None)):
            raise LabError(f"check '{c.name}' reads {c.node}, which runs in "
                           + ("the Docker host's network namespace (network-mode: host)" if m.mode == "host" else
                              f"the namespace of {m.mode[len('container:'):]}, which is not a lab node")
                           + ": it would test the host, not the lab")
        if c.type != "ping":
            continue
        for key in ("target", "source"):
            val = c.params.get(key)
            if not val:
                continue
            addr, _, scope = str(val).partition("%")
            ip = ipaddress.ip_address(addr)
            hit = next((s for s in subnets if ip in s), None)
            if hit is not None:
                raise LabError(f"check '{c.name}': {key} {val} is in the lab's management network {hit}: that path "
                               "is Docker's, not the lab's, so the ping says nothing about the network")
            if scope and m is not None and (scope in m.devices or EOS_MGMT.match(scope) or scope in ("eth0", "mgmt0")):
                raise LabError(f"check '{c.name}': {key} {val} is scoped to the management interface {scope}")


def _check(lab: Lab, m: Mgmt, when: str) -> None:
    try:
        if m.kind == "linux":
            check_linux(lab, m, when)
        elif m.kind == "eos":
            check_eos(lab, m, when)
        elif m.kind == "junos":
            check_junos(lab, m, when)
    except ManagementPathError:
        raise
    except Exception as e:   # unreadable is never an unready sample here: the run can't show it stays in the lab
        raise ManagementPathError(f"{m.node}: its routes could not be read {when}: {e}") from e


def recheck(lab: Lab, when: str) -> None:
    """Every touched node again (R5b): after the positive checks, around the hold, around each scenario."""
    for m in getattr(lab, "management", {}).values():
        _check(lab, m, when)


def check_node(lab: Lab, node: str, when: str) -> None:
    """One node, around a ping (R5a): its own routes, or those of the node whose namespace it shares. Nothing to check
    where prepare() didn't run (a lab object without Docker)."""
    state = getattr(lab, "management", {})
    m = covering(lab, state, node) if node in state else None
    if m is not None:
        _check(lab, m, when)
