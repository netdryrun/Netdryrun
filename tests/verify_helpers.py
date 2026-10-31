"""Builders for verify snapshots in unit tests: a small lab shaped like the agent demo.

    cust1 (65101) --- edge1 (65000) --- up1 (65002)
                        |    \\
                      peer1   (an external, non-lab neighbor 198.51.100.9)
                     (65003)
"""
from __future__ import annotations

import copy
import re
from pathlib import Path

from netdryrun.verify.intent import parse_intent
from netdryrun.verify.snapshot import (AsPath, BgpAttrs, BgpPath, ItemKey, NextHop, NodeSnapshot, PathNextHop,
                                       RibEntry, Session, Snapshot, canon_community, canon_set)

FIX = Path(__file__).parent / "fixtures" / "verify"
# Every FRR fixture is a live capture (scripts/capture_verify_fixtures.py on tests/fixtures/verify-lab): its first
# line names the FRR version, the node, the command and the date.
LIVE = re.compile(r"# live capture: (FRRouting \S+), node (\S+) of tests/fixtures/verify-lab, `vtysh -c '(.+)'`, "
                  r"(\d{4}-\d\d-\d\d)")


def fixture_header(name: str) -> re.Match:
    m = LIVE.fullmatch((FIX / name).read_text(encoding="utf-8").split("\n", 1)[0])
    assert m, f"{name}: not marked as a live capture"
    return m


def fixture(name: str) -> str:
    """A verify fixture without its header line."""
    fixture_header(name)
    return (FIX / name).read_text(encoding="utf-8").split("\n", 1)[1]


def fixture_commands() -> dict[str, str]:
    """command -> fixture file name, for every fixture."""
    return {fixture_header(f.name).group(3): f.name for f in sorted(FIX.iterdir())}


def nh(ip: str, interface: str = "eth1", fib: bool = True) -> NextHop:
    return NextHop(ip=ip, interface=interface, vrf=None, active=True, fib=fib, directly_connected=False,
                   on_link=False, recursive=False, duplicate=False, kind="gateway", weight=1, labels=(), src=None)


def rib(protocol="bgp", hops=("10.0.0.1",), selected=True, fib=True, distance=20, metric=0) -> tuple[RibEntry, ...]:
    return (RibEntry(protocol=protocol, instance=None, selected=selected, fib=fib, distance=distance, metric=metric,
                     tag=None, table=254, failed=False, nexthops=canon_set(nh(h, fib=fib) for h in hops)),)


def attrs(as_path="", next_hop="0.0.0.0", origin="igp", local_pref=None, med=None, weight=None, communities=(),
          large=(), ext=(), cluster=(), originator=None) -> BgpAttrs:
    return BgpAttrs(origin=origin, as_path=AsPath.parse(as_path),
                    next_hops=(PathNextHop(next_hop, "global", True, True, 0, None),), local_pref=local_pref, med=med,
                    weight=weight, communities=tuple(sorted({canon_community(c) for c in communities})),
                    ext_communities=tuple(sorted(ext)), large_communities=tuple(sorted(large)),
                    cluster_list=tuple(cluster), originator_id=originator, atomic_aggregate=False, aggregator=None)


def path(best=True, peer_type="external", **kw) -> BgpPath:
    return BgpPath(attrs=attrs(**kw), best=best, multipath=False, valid=True, peer_type=peer_type,
                   peer_router_id=None)


def session(local: str | None, state="established", afis=("ipv4-unicast",), remote_as=65000, local_as=65000) -> Session:
    return Session(state=state, remote_as=remote_as, local_as=local_as, afis=afis,
                   local_address=local if state == "established" else None)


class Lab:
    """A mutable set of items per node; .snap() builds the Snapshot."""

    NODES = ("cust1", "edge1", "up1", "peer1")

    def __init__(self):
        self.items: dict[str, dict[ItemKey, object]] = {n: {} for n in self.NODES}
        # each node's normalised running config (frr.parse_running_config)
        self.configs: dict[str, tuple[str, ...]] = {n: ("frr version 10.4.1_git", f"hostname {n}", "router bgp 65000",
                                                        " no bgp ebgp-requires-policy", "exit")
                                                    for n in self.NODES}
        for n in self.NODES:   # every node has a connected route: it is ready
            self.rib(n, f"10.{self.NODES.index(n)}.255.0/24", rib("connected", hops=()))

    def copy(self) -> "Lab":
        return copy.deepcopy(self)

    def _put(self, key: ItemKey, value):
        self.items[key.node][key] = value

    def _afi(self, prefix):
        return "ipv6" if ":" in prefix else "ipv4"

    def session(self, node, nbr, value, vrf="default"):
        self._put(ItemKey("session", node, vrf, neighbor=nbr), value)

    def rib(self, node, prefix, value, protocol=None, vrf="default"):
        protocol = protocol or value[0].protocol
        self._put(ItemKey("rib", node, vrf, self._afi(prefix), "unicast", prefix, protocol=protocol), value)

    def path(self, node, prefix, source, value, vrf="default", path_id=0):
        self._put(ItemKey("path", node, vrf, self._afi(prefix), "unicast", prefix, neighbor=source,
                          path_id=path_id), value)

    def adj_out(self, node, nbr, prefix, value, vrf="default"):
        self._put(ItemKey("adj_out", node, vrf, self._afi(prefix), "unicast", prefix, neighbor=nbr), value)

    def adj_in(self, node, nbr, prefix, value, vrf="default"):
        self._put(ItemKey("adj_in", node, vrf, self._afi(prefix), "unicast", prefix, neighbor=nbr), value)

    def drop(self, node, kind, prefix=None, neighbor=None, protocol=None):
        for k in list(self.items[node]):
            if k.kind == kind and (prefix is None or k.prefix == prefix) and (neighbor is None or k.neighbor == neighbor) \
                    and (protocol is None or k.protocol == protocol):
                del self.items[node][k]

    def get(self, node, kind, prefix=None, neighbor=None, protocol=None):
        hits = [v for k, v in self.items[node].items() if k.kind == kind and (prefix is None or k.prefix == prefix)
                and (neighbor is None or k.neighbor == neighbor) and (protocol is None or k.protocol == protocol)]
        assert len(hits) == 1, hits
        return hits[0]

    def snap(self) -> Snapshot:
        return Snapshot({n: NodeSnapshot(n, "frr", ("default",), dict(items), config=self.configs.get(n, ()))
                         for n, items in self.items.items()})

    def configure(self, node, *lines, under="router bgp 65000"):
        """Add config lines inside a section (after its header line), as FRR's running config shows them."""
        c = list(self.configs[node])
        i = c.index(under) + 1
        self.configs[node] = tuple(c[:i] + list(lines) + c[i:])

    # --- a route originated by `origin_node` and learned over the given hops --------------------------------
    def learn(self, node, prefix, from_addr, as_path, next_hop=None, best=True, **kw):
        self.path(node, prefix, from_addr, path(best=best, as_path=as_path, next_hop=next_hop or from_addr, **kw))
        if best:
            self.rib(node, prefix, rib("bgp", hops=(next_hop or from_addr,)))


def base() -> Lab:
    """The lab before any change."""
    lab = Lab()
    # sessions: (node, neighbor, local address)
    for node, nbr, local, ras in (("edge1", "10.0.1.2", "10.0.1.1", 65101), ("edge1", "10.0.2.2", "10.0.2.1", 65002),
                                  ("edge1", "10.0.3.2", "10.0.3.1", 65003), ("edge1", "198.51.100.9", "198.51.100.8", 64999),
                                  ("cust1", "10.0.1.1", "10.0.1.2", 65000), ("up1", "10.0.2.1", "10.0.2.2", 65000),
                                  ("peer1", "10.0.3.1", "10.0.3.2", 65000)):
        lab.session(node, nbr, session(local, remote_as=ras))
    # the customer's block 10.100.0.0/24: originated by cust1, to up1 and peer1 through edge1
    lab.path("cust1", "10.100.0.0/24", "local", path(as_path="", weight=32768, peer_type="local"))
    lab.rib("cust1", "10.100.0.0/24", rib("static", hops=(), distance=1))
    lab.adj_out("cust1", "10.0.1.1", "10.100.0.0/24", attrs(as_path="", next_hop="10.0.1.2"))
    lab.learn("edge1", "10.100.0.0/24", "10.0.1.2", "65101")
    for node, nbr, peer_addr in (("up1", "10.0.2.2", "10.0.2.1"), ("peer1", "10.0.3.2", "10.0.3.1")):
        lab.adj_out("edge1", nbr, "10.100.0.0/24", attrs(as_path="65101", next_hop="10.0.1.2"))
        lab.learn(node, "10.100.0.0/24", peer_addr, "65000 65101")
    # the customer's new block 10.101.0.0/24 exists on cust1 already (edge1 filters it today)
    lab.path("cust1", "10.101.0.0/24", "local", path(as_path="", weight=32768, peer_type="local"))
    lab.rib("cust1", "10.101.0.0/24", rib("static", hops=(), distance=1))
    lab.adj_out("cust1", "10.0.1.1", "10.101.0.0/24", attrs(as_path="", next_hop="10.0.1.2"))
    # an upstream route 203.0.113.0/24: up1 -> edge1 -> cust1
    lab.path("up1", "203.0.113.0/24", "local", path(as_path="", weight=32768, peer_type="local"))
    lab.rib("up1", "203.0.113.0/24", rib("static", hops=(), distance=1))
    lab.adj_out("up1", "10.0.2.1", "203.0.113.0/24", attrs(as_path="", next_hop="10.0.2.2"))
    lab.learn("edge1", "203.0.113.0/24", "10.0.2.2", "65002", local_pref=100)
    lab.adj_out("edge1", "10.0.1.2", "203.0.113.0/24", attrs(as_path="65002", next_hop="10.0.2.2"))
    lab.learn("cust1", "203.0.113.0/24", "10.0.1.1", "65000 65002")
    # a peer route 198.18.0.0/24: peer1 -> edge1 -> cust1
    lab.path("peer1", "198.18.0.0/24", "local", path(as_path="", weight=32768, peer_type="local"))
    lab.rib("peer1", "198.18.0.0/24", rib("static", hops=(), distance=1))
    lab.adj_out("peer1", "10.0.3.1", "198.18.0.0/24", attrs(as_path="", next_hop="10.0.3.2"))
    lab.learn("edge1", "198.18.0.0/24", "10.0.3.2", "65003")
    lab.adj_out("edge1", "10.0.1.2", "198.18.0.0/24", attrs(as_path="65003", next_hop="10.0.3.2"))
    lab.learn("cust1", "198.18.0.0/24", "10.0.1.1", "65000 65003")
    # edge1's own block, advertised to the external (non-lab) neighbor
    lab.path("edge1", "192.0.2.0/24", "local", path(as_path="", weight=32768, peer_type="local"))
    lab.rib("edge1", "192.0.2.0/24", rib("static", hops=(), distance=1))
    lab.adj_out("edge1", "198.51.100.9", "192.0.2.0/24", attrs(as_path="", next_hop="198.51.100.8"))
    # an OSPF route on up1
    lab.rib("up1", "10.255.0.9/32", rib("ospf", hops=("10.0.2.1",), distance=110, metric=10))
    return lab


def add_new_customer_block(lab: Lab, nodes=("edge1", "up1", "peer1")) -> Lab:
    """The ticket's change: 10.101.0.0/24 now reaches up1 and peer1 through edge1."""
    if "edge1" in nodes:
        lab.learn("edge1", "10.101.0.0/24", "10.0.1.2", "65101")
    for node, nbr, peer_addr in (("up1", "10.0.2.2", "10.0.2.1"), ("peer1", "10.0.3.2", "10.0.3.1")):
        if node in nodes:
            lab.adj_out("edge1", nbr, "10.101.0.0/24", attrs(as_path="65101", next_hop="10.0.1.2"))
            lab.learn(node, "10.101.0.0/24", peer_addr, "65000 65101")
    return lab


def intent(lines=(), allow=()):
    return parse_intent({"intent": list(lines), **({"allow_anywhere": list(allow)} if allow else {})}, "test")
