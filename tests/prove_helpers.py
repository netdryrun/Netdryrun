"""Fakes for `netdryrun prove` without a lab: a driver that answers checks from a recorded snapshot, an executor that
plays recorded snapshots per variant, and the customer-leak lab (tests/fixtures/prove-custleak) as a small model.

    cust (65010) --- edge (65000) --- up (65020)
    10.0.1.2   10.0.1.1   10.0.2.1   10.0.2.2

cust announces its own 10.10.0.0/24 and 203.0.113.128/25, which it doesn't own; edge's CUST-IN filter permits only
10.10.0.0/24. up announces 198.51.100.0/24. The checks under test run on these snapshots through the real check
evaluators (checks.EVALUATORS), so a check passes or fails here exactly as its evaluator decides on this state.
"""
from __future__ import annotations

import copy
import json
from dataclasses import replace
from pathlib import Path

from netdryrun.checks import Result, Unready, _evaluate, _sample
from netdryrun.drivers.base import BgpNeighbor, BgpPath, DriverError, Observation, Route
from netdryrun.prove.core import now
from netdryrun.verify.frr import parse_running_config, qualified
from netdryrun.verify.snapshot import NodeSnapshot, Snapshot
from verify_helpers import Lab as SnapLab
from verify_helpers import attrs, path, rib, session

FIXTURE = Path(__file__).parent / "fixtures" / "prove-custleak"
LINKS = [(("cust", "eth1"), ("edge", "eth1")), (("edge", "eth2"), ("up", "eth1"))]


# ---------------------------------------------------------------------------------------------------------
# Checks evaluated on a snapshot
# ---------------------------------------------------------------------------------------------------------

class SnapshotDriver:
    """Answers the driver calls the checks make from one node of a recorded snapshot. The evidence names the
    snapshot item it was read from."""
    name = "snapshot"

    def __init__(self, snap: Snapshot, node: str):
        self.snap, self.node = snap, node
        self.items = snap.nodes[node].items if node in snap.nodes else None

    def _need(self, what: str) -> dict:
        if self.items is None:
            raise DriverError(f"{self.node} is not in the snapshot")
        return self.items

    def _ev(self, cmd: str, value) -> list[dict]:
        return [{"node": self.node, "cmd": cmd, "rc": 0, "output": json.dumps(value, default=str)[:20000], "stderr": ""}]

    def bgp_neighbors(self, vrf: str = "default") -> Observation:
        items = self._need("sessions")
        out = {}
        for k, s in items.items():
            if k.kind == "session" and k.vrf == vrf:
                out[k.neighbor] = BgpNeighbor(k.neighbor, s.state, dict(s.prefix_counts))
        return Observation(out, self._ev(f"snapshot sessions vrf {vrf}", {a: n.__dict__ for a, n in out.items()}))

    def routes(self, prefix: str, vrf: str = "default") -> Observation:
        items = self._need("rib")
        out = [Route(k.prefix, k.protocol, any(e.selected for e in v)) for k, v in sorted(items.items())
               if k.kind == "rib" and k.vrf == vrf and k.prefix == prefix]
        return Observation(out, self._ev(f"snapshot rib {prefix}", [r.__dict__ for r in out]))

    def bgp_paths(self, prefix: str, vrf: str = "default") -> Observation:
        items = self._need("paths")
        out = []
        for k, p in sorted(items.items()):
            if k.kind == "path" and k.vrf == vrf and k.prefix == prefix:
                out.append(BgpPath(best=p.best, as_path=p.attrs.as_path.render(), next_hop=p.attrs.next_hops[0].ip,
                                   local_pref=p.attrs.local_pref if p.attrs.local_pref is not None else 100,
                                   med=p.attrs.med, communities=list(p.attrs.communities),
                                   neighbor=None if k.neighbor == "local" else k.neighbor))
        return Observation(out, self._ev(f"snapshot paths {prefix}", [x.__dict__ for x in out]))

    def ping(self, *a, **k) -> Observation:
        raise DriverError("a snapshot has no data plane")


def evaluate(checks, snap: Snapshot, started: str | None = None) -> list[Result]:
    """One sample of each check on `snap`, as a Result like the runner's."""
    out = []
    for c in checks:
        ok, detail, evidence = _evaluate(c, SnapshotDriver(snap, c.node))
        h = [_sample(0.0, ok, detail)]
        out.append(Result(c, ok, detail, 1, 0.0, started or now(), evidence, h, samples_passed=int(ok),
                          samples_unready=int(not ok and isinstance(detail, Unready))))
    return out


# ---------------------------------------------------------------------------------------------------------
# The executor
# ---------------------------------------------------------------------------------------------------------

class FakeExecutor:
    """Plays recorded snapshots: `base` with nothing applied, `states[variant id]` while that variant is applied,
    `after[variant id]` (default: base) once it is reverted. Unknown variants leave the lab as it is (a variant that
    did nothing). `results` overrides the check results for a variant (a callable taking the checks)."""

    def __init__(self, base: Snapshot, states=None, after=None, links=LINKS, results=None):
        self.base, self.states, self.after = base, dict(states or {}), dict(after or {})
        self.current = base
        self._links = links
        self.results = dict(results or {})
        self.applied: list[str] = []
        self.reverted: list[str] = []
        self.active: str | None = None
        self.fail_apply: set[str] = set()
        self.fail_revert: set[str] = set()
        self.side: dict = {"edge kernel routes": "baseline"}
        self.side_after: dict[str, dict] = {}   # variant id -> the side state its revert leaves

    def links(self):
        return self._links

    def side_state(self):
        return dict(self.side)

    def snapshot(self):
        return self.current

    def run_checks(self, checks):
        if self.active and self.active in self.results:
            return self.results[self.active](checks)
        return evaluate(checks, self.current) if isinstance(self.current, Snapshot) else []

    def apply(self, v):
        self.applied.append(v.id)
        self.active = v.id
        if v.id in self.fail_apply:
            raise RuntimeError("vtysh rejected the line")
        self.current = self.states.get(v.id, self.current)

    def revert(self, v):
        self.reverted.append(v.id)
        self.active = None
        if v.id in self.fail_revert:
            raise RuntimeError("vtysh could not revert")
        self.current = self.after.get(v.id, self.base)
        self.side = self.side_after.get(v.id, self.side)


# ---------------------------------------------------------------------------------------------------------
# Snapshots of the customer-leak lab
# ---------------------------------------------------------------------------------------------------------

def file_config(node: str) -> tuple[str, ...]:
    return parse_running_config((FIXTURE / "configs" / f"{node}.conf").read_text(encoding="utf-8"))


def edit_config(lines: tuple[str, ...], removes=(), adds=()) -> tuple[str, ...]:
    """A config with qualified lines removed and added (each added at the end of its section), as FRR would show it."""
    out = [ln for ln, q in zip(lines, qualified(lines), strict=True) if q not in removes]
    for a in adds:
        parts = a.split(" > ")
        for depth in range(len(parts) - 1):
            header = " > ".join(parts[:depth + 1])
            if header not in qualified(tuple(out)):
                out.append(" " * depth + parts[depth])
        q = qualified(tuple(out))
        parent = " > ".join(parts[:-1])
        at = len(out)
        if parent:
            i = q.index(parent)
            at = i + 1
            while at < len(out) and q[at].startswith(parent + " > "):
                at += 1
        out.insert(at, " " * (len(parts) - 1) + parts[-1])
    return tuple(out)


def custleak(cust_extra=(), edge_filter=("10.10.0.0/24",), originate=None, down=(), lp_at=None, link_down=(),
             configs=None, foreign=True) -> Snapshot:
    """The lab's state. `cust_extra`: more prefixes cust announces; `edge_filter`: what edge's CUST-IN permits (None:
    everything); `originate`: {node: [prefix]} announced by edge or up (a leaked default, a link subnet); `down`:
    sessions shut ("ce": cust-edge, "eu": edge-up); `link_down`: the same, with the link (and its connected routes)
    gone; `lp_at`: {node: the local preference it sets on every route it learns}; `foreign`: whether cust announces
    203.0.113.128/25 (which edge's filter blocks today)."""
    originate, lp_at = originate or {}, lp_at or {}
    down = (*down, *link_down)
    lab = SnapLab.__new__(SnapLab)
    lab.items = {n: {} for n in ("cust", "edge", "up")}
    lab.configs = {n: file_config(n) for n in ("cust", "edge", "up")}
    lab.configs.update(configs or {})
    addr = {("cust", "edge"): ("10.0.1.2", "10.0.1.1"), ("edge", "up"): ("10.0.2.1", "10.0.2.2")}
    addr.update({(b, a): (y, x) for (a, b), (x, y) in list(addr.items())})
    asn = {"cust": 65010, "edge": 65000, "up": 65020}
    is_up = {"ce": "ce" not in down, "eu": "eu" not in down}
    session_of = {frozenset(("cust", "edge")): "ce", frozenset(("edge", "up")): "eu"}
    connected = {"cust": ["10.0.1.0/30"], "edge": ["10.0.1.0/30", "10.0.2.0/30"], "up": ["10.0.2.0/30"]}
    link_net = {"ce": "10.0.1.0/30", "eu": "10.0.2.0/30"}
    for n, prefixes in connected.items():
        for p in prefixes:
            if p not in [link_net[x] for x in link_down]:
                lab.rib(n, p, rib("connected", hops=(), distance=0))
    own = {"cust": ["10.10.0.0/24", *(["203.0.113.128/25"] if foreign else []), *cust_extra], "up": ["198.51.100.0/24", *originate.get("up", [])],
           "edge": list(originate.get("edge", []))}
    for n, prefixes in own.items():
        for p in prefixes:
            if p in ("10.10.0.0/24", "198.51.100.0/24"):
                lab.rib(n, p, rib("connected", hops=(), distance=0))
            else:   # a blackhole static; inactive under a connected route of the same prefix
                lab.rib(n, p, rib("static", hops=(), distance=1, selected=p not in connected[n]))
            lab.path(n, p, "local", path(as_path="", weight=32768, peer_type="local"))
    as_paths = {(n, p): "" for n, prefixes in own.items() for p in prefixes}
    counts: dict[tuple[str, str], int] = {}

    def send(src, dst, prefixes):
        a_src, a_dst = addr[(src, dst)]
        lp = lp_at.get(dst)
        for p in prefixes:
            lab.adj_out(src, a_dst, p, attrs(as_path=as_paths[(src, p)], next_hop=a_src))
            full = " ".join(filter(None, [str(asn[src]), as_paths[(src, p)]]))
            lab.learn(dst, p, a_src, full, local_pref=lp)
            as_paths[(dst, p)] = full
        counts[(dst, a_src)] = len(prefixes)

    from_cust = [p for p in own["cust"] if edge_filter is None or p in edge_filter] if is_up["ce"] else []
    if is_up["ce"]:
        for p in own["cust"]:   # cust advertises everything it has; edge's filter decides what is accepted
            lab.adj_out("cust", "10.0.1.1", p, attrs(as_path="", next_hop="10.0.1.2"))
        for p in from_cust:
            lab.learn("edge", p, "10.0.1.2", "65010", local_pref=lp_at.get("edge"))
            as_paths[("edge", p)] = "65010"
        counts[("edge", "10.0.1.2")] = len(from_cust)
    from_up = list(own["up"]) if is_up["eu"] else []
    if is_up["eu"]:
        send("up", "edge", from_up)
        send("edge", "up", from_cust + own["edge"])
    if is_up["ce"]:
        send("edge", "cust", from_up + own["edge"])
    for pair, (a_me, a_nbr) in addr.items():
        me, other = pair
        up = is_up[session_of[frozenset(pair)]]
        s = session(a_me if up else None, state="established" if up else "idle", remote_as=asn[other],
                    local_as=asn[me])
        lab.session(me, a_nbr, replace(s, prefix_counts=(("ipv4-unicast", counts.get((me, a_nbr), 0)),)) if up else s)
    return Snapshot({n: NodeSnapshot(n, "frr", ("default",), dict(items), config=lab.configs[n])
                     for n, items in lab.items.items()})


def with_config(snap: Snapshot, node: str, removes=(), adds=()) -> Snapshot:
    s = copy.deepcopy(snap)
    ns = s.nodes[node]
    s.nodes[node] = NodeSnapshot(ns.node, ns.driver, ns.vrfs, ns.items, ns.raw, config=edit_config(ns.config, removes, adds))
    return s


def applied(v, state: Snapshot) -> Snapshot:
    """`state` with the running config `v` leaves on its nodes (each part's removed and added lines)."""
    for part in v.parts():
        state = with_config(state, part.node, part.removes, part.adds)
    return state
