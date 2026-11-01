"""The known-bad variants `netdryrun prove` runs a lab's checks against, generated from the lab's own FRR configs.

A variant is data, never free text: which node, what it does, the vtysh lines that apply and revert it, the config
lines that show it took effect, and the prefixes it originates itself (its footprint, which is the variant's own
mechanism and never counted as an effect). Variants come from what the lab contains (its BGP speakers, the
route-maps and prefix-lists on their sessions, its links) and from the checks' prefix-count ranges, never from a
change under test.

Kinds, in the order the budget takes them (round robin, first variant of each kind first):

- customer_leak: a BGP speaker announces 1, 2 or N extra /24s from 100.64.0.0/10 (shared address space), none of
  them overlapping anything the lab's configs or checks name; for every prefix-count check with a range up to U on
  its session, today's count C: a paired variant of U-C prefixes (inside the range) and U-C+1 (just outside)
- import_filter: on a route-map or prefix-list used inbound (by `neighbor X route-map M in` or `neighbor X
  prefix-list P in`, or a prefix-list such a route-map matches): a `match` line deleted (same-type matches in a
  clause are ORed, different types ANDed: it can widen or narrow), a deny clause deleted, a prefix-list entry
  deleted, a clause or entry swapped between permit and deny. Each is a candidate whose effect the snapshot judges.
  Where the neighbor is a lab FRR node and today's state shows nothing the filter blocks on that session, the edit
  is composed with a one-prefix leak from the neighbor so it has something to act on (design review, Grok B1);
  where it blocks something already, the edit acts alone. With no state (--plan), both are listed
- session_down: one BGP neighbor shut down (`neighbor X shutdown`), one per session, sessions that carry prefixes
- link_down: one link of the topology down, one per link
- attribute_drift: a `set local-preference` changed on an inbound route-map, or on an outbound one toward a
  confederation peer (local preference is never sent to a plain eBGP neighbor: Grok B6), a `set community` or `set
  as-path prepend` on a session's route-map deleted, or a `set local-preference 50` added to an inbound permit
  entry that sets none
- default_leak: 0.0.0.0/0 (::/0 for IPv6 sessions) originated into BGP
- link_subnet_leak: a link subnet originated into BGP by a node on that link
- more_specific, max_prefix_edge: in the published method, not built yet: listed as not generated
"""
from __future__ import annotations

import ipaddress
import re
from dataclasses import dataclass, field

KINDS = ("customer_leak", "import_filter", "session_down", "link_down", "attribute_drift", "default_leak",
         "link_subnet_leak", "more_specific", "max_prefix_edge")
NOT_BUILT = ("more_specific", "max_prefix_edge")   # in the published method, not generated yet: always "not generated"
LEAK_SPACE = ipaddress.ip_network("100.64.0.0/10")    # RFC 6598: customer_leak prefixes are /24s from it
DEFAULT_MAX = 8
MAX_LEAK = 1024   # the most prefixes one customer_leak variant announces (a range pair above it is left out)
DRIFT_LOCAL_PREF = 50


class VariantError(ValueError):
    """A bad --variants or --max value."""


@dataclass(frozen=True)
class Variant:
    id: str                       # stable across runs of the same lab: kind:node:what
    kind: str
    node: str
    description: str
    apply: tuple[str, ...] = ()           # vtysh config lines (config variants)
    revert: tuple[str, ...] = ()
    removes: tuple[str, ...] = ()         # qualified running-config lines the variant must remove (verify.frr.qualified)
    adds: tuple[str, ...] = ()            # ... and add: the proof that it took effect
    originates: tuple[str, ...] = ()      # prefixes the variant announces itself (inject_routes): its footprint
    link: tuple[str, str] | None = None   # link_down: (node, interface)
    soft_in: tuple[str, ...] = ()         # neighbors to soft-reset inbound once applied and once reverted
    companion: "Variant | None" = None    # applied first and reverted last: the leak a filter variant needs
    # the outer leak of a range pair: (node, neighbor, afi, U) of the prefix-count check it tests; its pass means the
    # range isn't doing its job only if the count measured there reached U+1
    range_top: tuple[str, str, str, int] | None = None

    def parts(self) -> list["Variant"]:
        """The variants applied, in order: the companion first."""
        return [self.companion, self] if self.companion else [self]

    def to_json(self) -> dict:
        out = {"id": self.id, "kind": self.kind, "node": self.node, "description": self.description}
        if self.apply:
            out["apply"] = list(self.apply)
        if self.originates:
            out["originates"] = list(self.originates)
        if self.link:
            out["link"] = f"{self.link[0]}:{self.link[1]}"
        if self.companion:
            out["with"] = self.companion.to_json()
        return out


# ---------------------------------------------------------------------------------------------------------
# Reading an FRR config (running config or the file it was loaded from)
# ---------------------------------------------------------------------------------------------------------

@dataclass
class RouteMapEntry:
    name: str
    action: str
    seq: int
    lines: list[str] = field(default_factory=list)    # its body, stripped

    @property
    def header(self) -> str:
        return f"route-map {self.name} {self.action} {self.seq}"


@dataclass
class Neighbor:
    address: str
    remote_as: str = ""
    shutdown: bool = False
    peer_group: str = ""
    route_maps: dict[tuple[str, str], str] = field(default_factory=dict)     # (afi, "in"/"out") -> route-map
    prefix_lists: dict[tuple[str, str], str] = field(default_factory=dict)   # (afi, "in"/"out") -> prefix-list
    max_prefix: bool = False


@dataclass
class FrrConfig:
    asn: str = ""
    neighbors: dict[str, Neighbor] = field(default_factory=dict)      # IP neighbors and peer-groups alike
    groups: set[str] = field(default_factory=set)
    networks: set[str] = field(default_factory=set)                   # prefixes with a network statement
    statics: set[str] = field(default_factory=set)
    route_maps: dict[str, list[RouteMapEntry]] = field(default_factory=dict)
    prefix_lists: dict[str, list[str]] = field(default_factory=dict)  # name -> its lines, as written
    confed_peers: set[str] = field(default_factory=set)               # `bgp confederation peers` ASNs
    interfaces: dict[str, list[ipaddress.IPv4Interface | ipaddress.IPv6Interface]] = field(default_factory=dict)

    def _inherited(self, address: str, attr: str) -> dict:
        n = self.neighbors[address]
        group = self.neighbors.get(n.peer_group) if n.peer_group else None
        return {**(getattr(group, attr) if group else {}), **getattr(n, attr)}

    def maps_of(self, address: str) -> dict[tuple[str, str], str]:
        """The route-maps on a neighbor, its peer-group's where it sets none itself."""
        return self._inherited(address, "route_maps")

    def lists_of(self, address: str) -> dict[tuple[str, str], str]:
        return self._inherited(address, "prefix_lists")

    def remote_as_of(self, address: str) -> str:
        n = self.neighbors[address]
        group = self.neighbors.get(n.peer_group) if n.peer_group else None
        return n.remote_as or (group.remote_as if group else "")

    def max_prefix(self, address: str) -> bool:
        n = self.neighbors.get(address)
        group = self.neighbors.get(n.peer_group) if n and n.peer_group else None
        return bool(n and (n.max_prefix or (group and group.max_prefix)))

    def confed(self, address: str) -> bool:
        return self.remote_as_of(address) in self.confed_peers

    def ebgp(self, address: str) -> bool:
        ras = self.remote_as_of(address)
        return ras == "external" or (ras.isdigit() and ras != self.asn)

    def ip_neighbors(self) -> list[str]:
        return sorted((a for a in self.neighbors if a not in self.groups and _is_ip(a)), key=_ip_key)

    def addresses(self) -> set[str]:
        return {str(i.ip) for addrs in self.interfaces.values() for i in addrs}


def _is_ip(text: str) -> bool:
    try:
        ipaddress.ip_address(text)
    except ValueError:
        return False
    return True


def _ip_key(text: str):
    a = ipaddress.ip_address(text)
    return a.version, a


def parse(lines) -> FrrConfig:
    """The parts of an FRR config the variants are built from. Only the default VRF's `router bgp` is read."""
    cfg = FrrConfig()
    rm: RouteMapEntry | None = None
    in_bgp = False
    afi = "ipv4"
    iface = ""
    for raw in (lines.splitlines() if isinstance(lines, str) else lines):
        line = raw.rstrip()
        text = line.strip()
        if not text or text.startswith("!"):
            continue
        w = text.split()
        if line == text:   # a top-level line opens a section (or is one)
            rm, in_bgp, iface, afi = None, False, "", "ipv4"
            if w[0] == "route-map" and len(w) == 4 and w[2] in ("permit", "deny") and w[3].isdigit():
                rm = RouteMapEntry(w[1], w[2], int(w[3]))
                cfg.route_maps.setdefault(w[1], []).append(rm)
            elif w[:2] == ["router", "bgp"] and len(w) == 3:
                in_bgp, cfg.asn = True, w[2]
            elif w[0] == "interface" and len(w) >= 2:
                iface = w[1]
                cfg.interfaces.setdefault(iface, [])
            elif w[0] in ("ip", "ipv6") and w[1:2] == ["prefix-list"] and len(w) > 3:
                cfg.prefix_lists.setdefault(w[2], []).append(text)
            elif w[0] in ("ip", "ipv6") and w[1:2] == ["route"] and len(w) > 2:
                cfg.statics.add(w[2])
            continue
        if text in ("exit", "exit-address-family"):
            afi = "ipv4"
            continue
        if rm is not None:
            rm.lines.append(text)
        elif iface and w[0] in ("ip", "ipv6") and len(w) == 3 and w[1] == "address":
            try:
                cfg.interfaces[iface].append(ipaddress.ip_interface(w[2]))
            except ValueError:
                pass
        elif in_bgp:
            if w[0] == "address-family" and len(w) >= 2:
                afi = w[1]
            elif w[:3] == ["bgp", "confederation", "peers"]:
                cfg.confed_peers.update(w[3:])
            elif w[0] == "network" and len(w) >= 2:
                cfg.networks.add(w[1])
            elif w[0] == "neighbor" and len(w) >= 3:
                n = cfg.neighbors.setdefault(w[1], Neighbor(w[1]))
                if w[2] == "remote-as" and len(w) == 4:
                    n.remote_as = w[3]
                elif w[2] == "shutdown":
                    n.shutdown = True
                elif w[2] == "peer-group" and len(w) == 3:
                    cfg.groups.add(w[1])
                elif w[2] == "peer-group" and len(w) == 4:
                    n.peer_group = w[3]
                elif w[2] in ("route-map", "prefix-list") and len(w) == 5 and w[4] in ("in", "out"):
                    (n.route_maps if w[2] == "route-map" else n.prefix_lists)[(afi, w[4])] = w[3]
                elif w[2] == "maximum-prefix":
                    n.max_prefix = True
    return cfg


# ---------------------------------------------------------------------------------------------------------
# Generation
# ---------------------------------------------------------------------------------------------------------

def _q(*parts: str) -> str:
    """A qualified running-config line (verify.frr.qualified): section headers, then the line."""
    return " > ".join(parts)


def _maps_used(cfg: FrrConfig, direction: str | None) -> dict[str, list[str]]:
    """route-map -> the IP neighbors that use it (in `direction`, or either way)."""
    out: dict[str, list[str]] = {}
    for addr in cfg.ip_neighbors():
        for (_afi, d), name in sorted(cfg.maps_of(addr).items()):
            if direction is None or d == direction:
                out.setdefault(name, [])
                if addr not in out[name]:
                    out[name].append(addr)
    return out


def _owner(address: str, configs: dict[str, FrrConfig]) -> str | None:
    owners = [n for n, c in configs.items() if address in c.addresses()]
    return owners[0] if len(owners) == 1 else None


def _entry_lines(entry: RouteMapEntry, header: str) -> tuple[str, ...]:
    return (header, *[f" {b}" for b in entry.lines], "exit")


def _import_filter(node: str, cfg: FrrConfig, configs: dict[str, FrrConfig], leak: list[str],
                   blocked: dict[tuple[str, str], bool] | None) -> list[Variant]:
    plain: list[Variant] = []
    plists: dict[str, list[str]] = {}
    for name, users in sorted(_maps_used(cfg, "in").items()):
        on = f"(inbound from {', '.join(users)})"
        for entry in cfg.route_maps.get(name, []):
            what = entry.header[len("route-map "):]
            for line in entry.lines:
                if not line.startswith("match "):
                    continue
                plain.append(Variant(
                    id=f"import_filter:{node}:{what}:{line}", kind="import_filter",
                    node=node, description=f"{node}: `{line}` deleted from {entry.header} {on}",
                    apply=(entry.header, f" no {line}", "exit"), revert=(entry.header, f" {line}", "exit"),
                    removes=(_q(entry.header, line),), soft_in=tuple(users)))
                m = re.fullmatch(r"match ip(?:v6)? address prefix-list (\S+)", line)
                if m:
                    plists.setdefault(m.group(1), [])
                    plists[m.group(1)] += [u for u in users if u not in plists[m.group(1)]]
            body = tuple(_q(entry.header, b) for b in entry.lines)
            if entry.action == "deny":
                plain.append(Variant(
                    id=f"import_filter:{node}:{what}:deleted", kind="import_filter", node=node,
                    description=f"{node}: {entry.header} deleted {on}",
                    apply=(f"no {entry.header}",), revert=_entry_lines(entry, entry.header),
                    removes=(_q(entry.header), *body), soft_in=tuple(users)))
            other = "deny" if entry.action == "permit" else "permit"
            swapped = f"route-map {entry.name} {other} {entry.seq}"
            plain.append(Variant(
                id=f"import_filter:{node}:{what}:swapped", kind="import_filter", node=node,
                description=f"{node}: {entry.header} turned into {other} {on}",
                apply=(f"no {entry.header}", *_entry_lines(entry, swapped)),
                revert=(f"no {swapped}", *_entry_lines(entry, entry.header)),
                removes=(_q(entry.header), *body),
                adds=(_q(swapped), *(_q(swapped, b) for b in entry.lines)), soft_in=tuple(users)))
    for addr in cfg.ip_neighbors():
        for (_afi, d), name in sorted(cfg.lists_of(addr).items()):
            if d == "in":
                plists.setdefault(name, [])
                if addr not in plists[name]:
                    plists[name].append(addr)
    for plist, users in plists.items():
        for line in cfg.prefix_lists.get(plist, []):
            on = f"(inbound from {', '.join(users)})"
            plain.append(Variant(
                id=f"import_filter:{node}:{line}", kind="import_filter", node=node,
                description=f"{node}: prefix-list entry `{line}` deleted {on}",
                apply=(f"no {line}",), revert=(line,), removes=(_q(line),), soft_in=tuple(users)))
            w = line.split()
            act = next((i for i, x in enumerate(w) if x in ("permit", "deny")), None)
            if act is not None:
                new = " ".join([*w[:act], "deny" if w[act] == "permit" else "permit", *w[act + 1:]])
                plain.append(Variant(
                    id=f"import_filter:{node}:{line}:swapped", kind="import_filter", node=node,
                    description=f"{node}: prefix-list entry `{line}` turned into `{new}` {on}",
                    apply=(f"no {line}", new), revert=(f"no {new}", line), removes=(_q(line),), adds=(_q(new),),
                    soft_in=tuple(users)))
    out = []
    for v in plain:
        far = sorted({o for u in v.soft_in for o in [_owner(u, configs)] if o and o != node and configs[o].asn})
        known = blocked is not None and all((node, u) in blocked for u in v.soft_in)
        blocks = known and any(blocked[(node, u)] for u in v.soft_in)
        if far and leak and not blocks:   # nothing blocked today (or no state to tell): give the edit a leak
            leaker = _originate("customer_leak", far[0], configs[far[0]], leak[:1],
                                f"{far[0]} announces {leak[0]}", f"customer_leak:{far[0]}:with:{v.id}")
            out.append(Variant(**{**v.__dict__, "id": f"{v.id}:+leak:{far[0]}", "companion": leaker,
                                  "description": f"{v.description}, while {far[0]} announces {leak[0]}"}))
        if not (far and leak and known and not blocks):
            out.append(v)
    return out


def _filter_rank(v: Variant) -> int:
    base = v.id.split(":+leak:")[0]
    if base.endswith(":swapped"):
        return 3
    if base.endswith(":deleted"):
        return 2
    return 1 if ":ip prefix-list " in base or ":ipv6 prefix-list " in base else 0


def _attribute_drift(node: str, cfg: FrrConfig) -> list[Variant]:
    out = []
    inbound = _maps_used(cfg, "in")
    for name, users in sorted(_maps_used(cfg, None).items()):
        for entry in cfg.route_maps.get(name, []):
            sets = [b for b in entry.lines if b.startswith("set ")]
            for line in sets:
                w = line.split()
                if w[1] == "local-preference" and len(w) == 3 and w[2].isdigit() and (
                        name in inbound or any(cfg.confed(u) for u in users)):
                    new = f"set local-preference {100 if int(w[2]) != 100 else 200}"
                    apply, adds, what = (entry.header, f" {new}", "exit"), (_q(entry.header, new),), f"`{line}` changed to `{new}`"
                elif w[1] == "community" or w[1:3] == ["as-path", "prepend"]:
                    apply, adds, what = (entry.header, f" no {line}", "exit"), (), f"`{line}` deleted"
                else:
                    continue
                out.append(Variant(
                    id=f"attribute_drift:{node}:{entry.header[len('route-map '):]}:{line}", kind="attribute_drift",
                    node=node, description=f"{node}: {what} in {entry.header} (on {', '.join(users)})",
                    apply=apply, revert=(entry.header, f" {line}", "exit"),
                    removes=(_q(entry.header, line),), adds=adds, soft_in=tuple(users)))
            if entry.action == "permit" and name in inbound and not any(b.startswith("set local-preference") for b in sets):
                new = f"set local-preference {DRIFT_LOCAL_PREF}"
                out.append(Variant(
                    id=f"attribute_drift:{node}:{entry.header[len('route-map '):]}:+{new}", kind="attribute_drift",
                    node=node, description=f"{node}: `{new}` added to {entry.header} (inbound from "
                                           f"{', '.join(inbound[name])})",
                    apply=(entry.header, f" {new}", "exit"), revert=(entry.header, f" no {new}", "exit"),
                    adds=(_q(entry.header, new),), soft_in=tuple(inbound[name])))
    return out


def _session_down(configs: dict[str, FrrConfig], counts: dict[tuple[str, str, str], int] | None) -> list[Variant]:
    out, seen = [], []
    for node, cfg in sorted(configs.items()):
        if not cfg.asn:
            continue
        for addr in cfg.ip_neighbors():
            if cfg.neighbors[addr].shutdown:
                continue
            far = _owner(addr, configs)
            back = [a for a in configs[far].ip_neighbors() if _owner(a, configs) == node] if far else []
            ends = {(node, addr), *((far, a) for a in back)}
            if any(ends & s for s in seen):
                continue   # the same session seen from its other end: one variant per session
            seen.append(ends)
            # a session that carries nothing either way: shutting it is no fault (Grok C6); unknown counts keep it
            if counts is not None and not any(counts.get((n, a, afi)) for n, a in ends for afi in
                                              ("ipv4-unicast", "ipv6-unicast")):
                continue
            line = f"neighbor {addr} shutdown"
            out.append(Variant(
                id=f"session_down:{node}:{addr}", kind="session_down", node=node,
                description=f"{node}: BGP session to {addr}{f' ({far})' if far else ''} shut down",
                apply=(f"router bgp {cfg.asn}", f" {line}", "exit"),
                revert=(f"router bgp {cfg.asn}", f" no {line}", "exit"),
                adds=(_q(f"router bgp {cfg.asn}", line),)))
    return out


def _originate(kind: str, node: str, cfg: FrrConfig, prefixes: list[str], description: str, vid: str) -> Variant:
    """A variant that announces `prefixes` from `node` the way the inject_routes fault does (faults.config_lines)."""
    from ..faults import config_lines

    adds = [_q(f"{'ipv6' if ':' in p else 'ip'} route {p} blackhole") for p in prefixes]
    adds += [_q(f"router bgp {cfg.asn}", f"address-family {'ipv6' if ':' in p else 'ipv4'} unicast", f"network {p}")
             for p in prefixes]
    return Variant(id=vid, kind=kind, node=node, description=description,
                   apply=tuple(config_lines(cfg.asn, prefixes, [])),
                   revert=tuple(config_lines(cfg.asn, prefixes, [], remove=True)), adds=tuple(adds),
                   originates=tuple(prefixes))


def _taken(cfg: FrrConfig) -> set[str]:
    return cfg.statics | cfg.networks


def used_networks(configs: dict[str, FrrConfig], checks=()) -> list:
    """Every network the lab's configs or checks name: a leaked prefix overlapping one could fail a check (a ping
    blackholed, a route shadowed) for a reason that has nothing to do with the leak (Grok A5)."""
    texts = []
    for cfg in configs.values():
        texts += [str(i.network) for addrs in cfg.interfaces.values() for i in addrs]
        texts += list(cfg.networks | cfg.statics)
        texts += [w for lines in cfg.prefix_lists.values() for line in lines for w in line.split() if "/" in w]
    for c in checks:
        texts += [str(c.params[k]) for k in ("prefix", "target", "source") if k in c.params]
    out = []
    for t in texts:
        try:
            out.append(ipaddress.ip_network(t, strict=False))
        except ValueError:
            continue
    return out


def leak_prefixes(count: int, used=()) -> list[str]:
    """`count` /24s of LEAK_SPACE, from its start, that hold none of `used` (a ping target, a route the lab has).
    A network that covers a /24 doesn't rule it out: a guard on all of 100.64.0.0/10 must not switch the leak off."""
    held = {u.supernet(new_prefix=24) for u in used if u.version == 4 and u.prefixlen >= 24 and u.subnet_of(LEAK_SPACE)}
    out = []
    for net in LEAK_SPACE.subnets(new_prefix=24):
        if len(out) == count:
            break
        if net not in held:
            out.append(str(net))
    return out


def _customer_leak(node: str, cfg: FrrConfig, ranges: list[tuple[str, str, str, int, int]], used) -> list[Variant]:
    """`ranges`: (node, neighbor, afi, U, U-C) of each prefix-count check on a session this node is the far end of."""
    if not cfg.asn or not any(cfg.ebgp(a) for a in cfg.ip_neighbors()):
        return []
    sizes: dict[int, tuple[str, tuple | None]] = {1: ("", None), 2: ("", None)}
    for at, nbr, afi, top, extra in sorted(ranges, key=lambda r: r[4]):   # U-C inside the range, U-C+1 just outside
        for n, where, outer in ((extra, "just inside", None), (extra + 1, "just outside", (at, nbr, afi, top))):
            if 0 < n <= MAX_LEAK and (n not in sizes or not sizes[n][0] or (outer and sizes[n][1] is None)):
                sizes[n] = (f" ({where} the prefix-count range of a check on its session)", outer)
    out = []
    for n, (why, outer) in sorted(sizes.items()):
        prefixes = leak_prefixes(n, used)
        if len(prefixes) < n:
            continue
        v = _originate("customer_leak", node, cfg, prefixes, f"{node} announces {n} extra prefix(es) from {LEAK_SPACE}{why}",
                       f"customer_leak:{node}:{n}")
        out.append(Variant(**{**v.__dict__, "range_top": outer}))
    return out


def _default_leak(node: str, cfg: FrrConfig) -> list[Variant]:
    if not cfg.asn or not cfg.ip_neighbors():
        return []
    fams = ["0.0.0.0/0"] + (["::/0"] if any(":" in a for a in cfg.ip_neighbors()) else [])
    return [_originate("default_leak", node, cfg, [d], f"{node} originates {d} into BGP", f"default_leak:{node}:{d}")
            for d in fams if d not in _taken(cfg)]


def _link_subnet_leak(node: str, cfg: FrrConfig, links) -> list[Variant]:
    if not cfg.asn or not cfg.ip_neighbors():
        return []
    mine = [a for link in links for (n, i) in link if n == node for a in cfg.interfaces.get(i, [])]
    out = []
    for net in sorted({a.network for a in mine if not a.ip.is_link_local}, key=lambda n: (n.version, n)):
        if str(net) in _taken(cfg):
            continue
        out.append(_originate("link_subnet_leak", node, cfg, [str(net)],
                              f"{node} originates its link subnet {net} into BGP", f"link_subnet_leak:{node}:{net}"))
    return out


def _link_down(links, frr_nodes: set[str]) -> list[Variant]:
    out = []
    for a, b in links:
        end = a if a[0] in frr_nodes else b if b[0] in frr_nodes else None
        if end is None:
            continue
        out.append(Variant(id=f"link_down:{a[0]}:{a[1]}--{b[0]}:{b[1]}", kind="link_down", node=end[0],
                           description=f"link {a[0]}:{a[1]} -- {b[0]}:{b[1]} down", link=end))
    return out


def headroom(checks, base_counts: dict[tuple[str, str, str], int]) -> dict[str, dict[str, int]]:
    """node -> {neighbor: prefixes a check's range still accepts above today's count (U-C)} for every bgp_prefixes
    check with a max (or an exact count, U = C): the far end of that session is the node whose leak can hide inside
    the range, or just pass its top.
    `base_counts`: (node, neighbor, afi) -> today's count."""
    out: dict[str, dict[str, int]] = {}
    for c in checks:
        p = c.params
        top = p.get("max", p.get("exact"))
        if c.type != "bgp_prefixes" or top is None or p.get("vrf", "default") != "default":
            continue
        now = base_counts.get((p["node"], p["neighbor"], p.get("afi", "ipv4-unicast")))
        if now is not None and top >= now:
            out.setdefault(p["node"], {})[p["neighbor"]] = top - now
    return out


def generate(configs: dict[str, tuple[str, ...] | str], links=(), checks=(),
             base_counts: dict[tuple[str, str, str], int] | None = None,
             blocked: dict[tuple[str, str], bool] | None = None) -> list[Variant]:
    """Every variant for a lab: `configs` maps each FRR node to its config, `links` lists the topology's links as
    ((node, iface), (node, iface)), `checks` and `base_counts` (today's prefix counts; None without a lab) size the
    customer leak pairs on prefix-count ranges and leave out sessions that carry nothing; `blocked` ((node, neighbor)
    -> whether that session's inbound filter drops something today; None without a lab) decides whether a filter
    variant needs a leak to act on."""
    parsed = {n: parse(c) for n, c in sorted(configs.items())}
    links = [tuple(sorted(link)) for link in links]
    used = used_networks(parsed, checks)
    # the leak hides in a range on node X's session to neighbor A: the node that owns A announces it
    by_far: dict[str, list[tuple[str, str, str, int, int]]] = {}
    for c in checks:
        p = c.params
        top = p.get("max", p.get("exact"))
        afi = p.get("afi", "ipv4-unicast")
        now = (base_counts or {}).get((p.get("node"), p.get("neighbor"), afi))
        if c.type != "bgp_prefixes" or top is None or p.get("vrf", "default") != "default" or now is None or top < now:
            continue
        far = _owner(p["neighbor"], parsed)
        if far:
            by_far.setdefault(far, []).append((p["node"], p["neighbor"], afi, top, top - now))
    leak = leak_prefixes(1, used)
    out: list[Variant] = []
    for node, cfg in parsed.items():
        out += _customer_leak(node, cfg, by_far.get(node, []), used)
    # every node's match deletions first (the incident class), then prefix-list deletions, deny clauses, swaps
    filters = [v for node, cfg in parsed.items() for v in _import_filter(node, cfg, parsed, leak, blocked)]
    out += sorted(filters, key=_filter_rank)
    out += _session_down(parsed, base_counts)
    out += _link_down(links, set(parsed))
    for node, cfg in parsed.items():
        out += _attribute_drift(node, cfg)
    for node, cfg in parsed.items():
        out += _default_leak(node, cfg)
    for node, cfg in parsed.items():
        out += _link_subnet_leak(node, cfg, links)
    return out


def select(variants: list[Variant], kinds: list[str] | None = None, maximum: int = DEFAULT_MAX) -> tuple[list[Variant], list[Variant]]:
    """(run, not run): the budget taken round robin over the kinds in KINDS order, so every kind gets its first
    variant before any kind gets a second. `kinds` restricts the kinds; an unknown one is an error."""
    if isinstance(maximum, bool) or not isinstance(maximum, int) or maximum < 1:
        raise VariantError(f"--max must be a whole number of at least 1, got {maximum!r}")
    unknown = sorted(set(kinds or ()) - set(KINDS))
    if unknown:
        raise VariantError(f"unknown variant kind(s) {', '.join(unknown)}; known: {', '.join(KINDS)}")
    wanted = [k for k in KINDS if not kinds or k in kinds]
    queues = {k: [v for v in variants if v.kind == k] for k in wanted}
    run: list[Variant] = []
    while len(run) < maximum and any(queues.values()):
        for k in wanted:
            if queues[k] and len(run) < maximum:
                run.append(queues[k].pop(0))
    chosen = {v.id for v in run}
    return run, [v for v in variants if v.id not in chosen and v.kind in wanted]
