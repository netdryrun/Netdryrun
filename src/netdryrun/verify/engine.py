"""The diff between two snapshots and the match against the intent: the verdict.

Every diff item is either explained (by an intent line that happened, or by an allow_anywhere entry) or
undeclared. Every intent line either happened or didn't; a line that didn't happen explains nothing.

  no_change   the diff is empty and the intent declares nothing
  matched     every diff item is explained and every line happened ("explained is not the same as safe")
  failed      an undeclared item, or a line that didn't happen

What each form explains (and nothing else):

  appears_on S          on each node in S, every item for the prefix (RIB entries, BGP paths, received
                        routes), all of them new since the route was absent; and every advertisement of the
                        prefix *to* a node in S (whoever sends it).
  disappears_from S     on each node in S, the removed RIB entries and BGP paths for the prefix (received-only
                        routes before inbound policy only with including_received_only); and every
                        withdrawn advertisement of the prefix to a node in S.
  best_path_on N, to:   on N, the move of the best flag between paths, changes to the new best path in the
                        listed attributes only (to exactly the declared values; every other path, the old
                        best included, may change its best flag only), the BGP RIB entry's next hops (when next_hop is
                        listed) or metric (when med is), and changed advertisements of the prefix, by N or to
                        N, that differ only in listed attributes and carry the new best path's values.
  session goes down     both ends of that one session (each still configured: a neighbor deleted from the
                        config is a "session removed" difference, never covered): its state, the paths, received routes and
                        advertisements over it (in its address family), and the RIB entries of prefixes
                        that were learned only over it and are now gone. Nothing else: a failover to a
                        backup path is a best-path change and needs its own line.
  advertisement         exactly that node's advertisement of the prefix to that neighbor: removed; changed
                        in the listed attributes; or added, carrying the node's best path's attributes (no
                        outbound rewrite), or the values given in `with:` (the rest as on the best path).
  allow_anywhere        any item whose prefix equals an entry or matches an explicit glob (in that VRF).
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field, fields

from .intent import Intent, Line
from .snapshot import BgpAttrs, BgpPath, ItemKey, RibEntry, Session, Snapshot, SnapshotError

STATUSES = ("no_change", "matched", "failed")
STATE_TEXT = {"absent": "absent", "received": "received (not selected)", "selected": "selected (not in the FIB)",
              "installed": "selected and in the FIB",
              "discard": "selected and in the FIB as a discard route (blackhole, reject or unreachable: traffic is dropped)"}
# `to:` attribute -> the BgpAttrs fields it may change; listing next_hop also allows the next hop's
# resolution to change, listing from allows the peer's own facts to change.
ATTR_FIELDS = {"next_hop": ("next_hops",), "from": ()}
COUPLED = {"next_hop": ("next_hop_resolution",), "from": ("peer_type", "peer_router_id")}
# What a new advertisement must carry from the node's best path (outbound policy can rewrite these; the next
# hop, weight and, on eBGP, local preference follow protocol rules). local_pref only where it is sent.
ADV_ATTRS = ("as_path", "origin", "med", "local_pref", "communities", "ext_communities", "large_communities",
             "atomic_aggregate", "aggregator")
# The next hop of a new advertisement: the best path's, or the node itself (FRR lists 0.0.0.0 or ::, or one of the
# node's own session addresses); anything else is an outbound rewrite that a `with: {next_hop: ...}` pin declares.
SELF_NEXT_HOPS = (("0.0.0.0",), ("::",))
# What a route received before inbound policy shows (adj_in: FRR's plain received listing). A `with:` pin on any
# other attribute is never matched against it: unread is not "none".
ADJ_IN_VIEW = ("from", "next_hop", "as_path", "origin", "local_pref", "med", "weight")
UNSEEN = object()
SESSION_DOWN_FIELDS = {"established", "local_address"}   # what a session going down changes, and nothing else


class VerifyError(RuntimeError):
    """The snapshots can't be compared (a different set of nodes, an impossible BGP table)."""


# ---------------------------------------------------------------------------------------------------------
# The diff
# ---------------------------------------------------------------------------------------------------------

@dataclass(frozen=True)
class DiffItem:
    key: ItemKey
    before: object | None
    after: object | None

    @property
    def change(self) -> str:
        return "added" if self.before is None else "removed" if self.after is None else "changed"

    @property
    def kind(self) -> str:
        """The diff kind: the item's kind, except a session gone from the config, which is its own kind
        ("session removed") that `goes: down` never covers."""
        return "session removed" if self.key.kind == "session" and self.after is None else self.key.kind

    @property
    def fields(self) -> tuple[str, ...]:
        """The fields that differ, for a changed item (flattened: a BGP path's attributes by name)."""
        if self.change != "changed":
            return ()
        return changed_fields(self.before, self.after)


def _flat(value) -> dict:
    if isinstance(value, BgpPath):
        out = {f.name: getattr(value, f.name) for f in fields(value) if f.name != "attrs"}
        out.update(_flat(value.attrs))
        return out
    if isinstance(value, (BgpAttrs, Session, RibEntry)):
        return {f.name: getattr(value, f.name) for f in fields(value) if f.compare}
    if isinstance(value, tuple) and len(value) == 1 and isinstance(value[0], RibEntry):
        return _flat(value[0])
    return {"value": value}


def changed_fields(before, after) -> tuple[str, ...]:
    if isinstance(before, tuple) and isinstance(after, tuple) and (len(before) != 1 or len(after) != 1):
        return ("entries",)   # a protocol with several RIB entries for the prefix: compared as a whole
    a, b = _flat(before), _flat(after)
    return tuple(sorted(k for k in set(a) | set(b) if a.get(k) != b.get(k)))


def diff(before: Snapshot, after: Snapshot) -> list[DiffItem]:
    if set(before.nodes) != set(after.nodes) or before.unobserved != after.unobserved:
        raise VerifyError(f"the snapshots cover different nodes (before: {sorted(before.nodes)}, after: "
                          f"{sorted(after.nodes)}); verify compares configs on one topology")
    b, a = before.items(), after.items()
    for snap, items in ((before, b), (after, a)):   # the VRFs each node has, and its running config, are items too
        for n, ns in snap.nodes.items():
            items.update({ItemKey("vrf", n, v): True for v in ns.vrfs})
            items[ItemKey("config", n, "default")] = ns.config
    out = []
    for k in sorted(set(b) | set(a)):
        if b.get(k) != a.get(k):
            out.append(DiffItem(k, b.get(k), a.get(k)))
    return out


# ---------------------------------------------------------------------------------------------------------
# Views over one snapshot
# ---------------------------------------------------------------------------------------------------------

FORWARDING = ("gateway", "interface")   # next-hop kinds that forward; blackhole, reject and unreachable drop


def forwards(nh) -> bool:
    """A next hop that carries traffic: a gateway or interface, active and in the FIB, and when it is recursive,
    resolved by at least one next hop that forwards (an iBGP next hop resolved over a Null0 route drops it:
    cold review of the gauntlet fixes, 1)."""
    if nh.kind not in FORWARDING or not nh.active or not nh.fib:
        return False
    return not nh.recursive or any(forwards(r) for r in nh.resolved_via)


@dataclass
class RouteView:
    rib: dict = field(default_factory=dict)        # protocol -> tuple[RibEntry]
    paths: dict = field(default_factory=dict)      # (source, path id) -> BgpPath
    adj_in: dict = field(default_factory=dict)     # (neighbor, path id) -> BgpAttrs
    adj_out: dict = field(default_factory=dict)    # (neighbor, path id) -> BgpAttrs

    def presence(self) -> str:
        entries = [e for es in self.rib.values() for e in es]
        installed = [e for e in entries if e.selected and e.fib]
        if any(forwards(nh) for e in installed for nh in e.nexthops):
            return "installed"
        if installed:   # every next hop drops the traffic: never "installed" (gauntlet 0.4, R5)
            return "discard"
        if any(e.selected for e in entries):
            return "selected"
        if entries or self.paths or self.adj_in:
            return "received"
        return "absent"

    def selected(self) -> RibEntry | None:
        sel = [e for es in self.rib.values() for e in es if e.selected]
        return sel[0] if sel else None

    def best(self) -> tuple[str, BgpPath] | None:
        best = [(src, p) for (src, _pid), p in self.paths.items() if p.best]
        if len(best) > 1:
            raise VerifyError(f"two best paths for one prefix ({', '.join(s for s, _ in best)})")
        return best[0] if best else None


class Index:
    def __init__(self, snap: Snapshot):
        self.routes: dict[tuple, RouteView] = defaultdict(RouteView)
        self.sessions: dict[tuple[str, str, str], Session] = {}
        for k, v in snap.items().items():
            if k.kind == "session":
                self.sessions[(k.node, k.vrf, k.neighbor)] = v
                continue
            rv = self.routes[(k.node, k.vrf, k.afi, k.prefix)]
            if k.kind == "rib":
                rv.rib[k.protocol] = v
            elif k.kind == "path":
                rv.paths[(k.neighbor, k.path_id)] = v
            elif k.kind == "adj_in":
                rv.adj_in[(k.neighbor, k.path_id)] = v
            else:
                rv.adj_out[(k.neighbor, k.path_id)] = v

    def route(self, node: str, vrf: str, afi: str, prefix: str) -> RouteView:
        return self.routes.get((node, vrf, afi, prefix)) or RouteView()


def far_ends(*snaps: Snapshot) -> dict[tuple[str, str, str], tuple[str, str, str]]:
    """(node, vrf, neighbor) -> (far node, its vrf, the address the far node knows this node by), for
    sessions between two observed nodes, matched on the addresses of an established session. Link addresses
    can repeat (another VRF, another pair of nodes): a candidate in the same VRF wins, and a pairing that is
    still ambiguous pairs nothing (whatever crosses it stays undeclared)."""
    est = set()
    for s in snaps:
        for k, v in s.sessions().items():
            if v.established and v.local_address:
                est.add((k.node, k.vrf, k.neighbor, v.local_address))
    out = {}
    for n, vrf, nbr, local in est:
        cands = {(n2, vrf2, local) for n2, vrf2, nbr2, local2 in est if n2 != n and local2 == nbr and nbr2 == local}
        same_vrf = {c for c in cands if c[1] == vrf}
        pick = same_vrf if same_vrf else cands
        if len(pick) == 1:
            out[(n, vrf, nbr)] = next(iter(pick))
    return out


def primary_next_hops(attrs: BgpAttrs) -> tuple[str, ...]:
    glob = sorted({h.ip for h in attrs.next_hops if h.scope == "global"})
    return tuple(glob or sorted({h.ip for h in attrs.next_hops}))


def attrs_view(attrs: BgpAttrs) -> dict:
    return {"next_hop": primary_next_hops(attrs), "next_hop_resolution": attrs.next_hops, "as_path": attrs.as_path,
            "origin": attrs.origin, "local_pref": attrs.local_pref, "med": attrs.med, "weight": attrs.weight,
            "communities": attrs.communities, "ext_communities": attrs.ext_communities,
            "large_communities": attrs.large_communities, "cluster_list": attrs.cluster_list,
            "originator_id": attrs.originator_id, "atomic_aggregate": attrs.atomic_aggregate,
            "aggregator": attrs.aggregator, "extra": attrs.extra}


def path_view(source: str, path: BgpPath) -> dict:
    v = attrs_view(path.attrs)
    v.update({"from": source, "peer_type": path.peer_type, "peer_router_id": path.peer_router_id,
              "valid": path.valid, "flags": path.flags})
    return v


def _fields_for(to: dict) -> set[str]:
    """The BgpAttrs field names the listed `to:` attributes may change."""
    out: set[str] = set()
    for k in to:
        out.update(ATTR_FIELDS.get(k, (k,)))
    return out


def show(v) -> str:
    from .snapshot import AsPath

    if isinstance(v, AsPath):
        return repr(v.render())
    if isinstance(v, tuple):
        return "[" + ", ".join(map(str, v)) + "]"
    return "null" if v is None else str(v)


# ---------------------------------------------------------------------------------------------------------
# Lines
# ---------------------------------------------------------------------------------------------------------

@dataclass
class LineResult:
    line: Line
    happened: bool
    reason: str = ""                             # why it didn't happen
    explained: set = field(default_factory=set)  # ItemKeys
    details: list = field(default_factory=list)  # what the report shows about it (one dict per node or route)


class _Ctx:
    def __init__(self, before: Snapshot, after: Snapshot, items: list[DiffItem]):
        self.before, self.after = Index(before), Index(after)
        self.items = items
        self.far = far_ends(before, after)

    def route_items(self, node: str, vrf: str, afi: str, prefix: str, kinds=("rib", "path", "adj_in")):
        return [d for d in self.items if d.key.kind in kinds and d.key.node == node and d.key.vrf == vrf
                and d.key.afi == afi and d.key.prefix == prefix]

    def adv_to(self, nodes: set[str], vrf: str, afi: str, prefix: str, change: str) -> set[ItemKey]:
        """Advertisements of the prefix (added or removed) whose receiving end is one of `nodes` in `vrf`."""
        out = set()
        for d in self.items:
            k = d.key
            if k.kind == "adj_out" and k.afi == afi and k.prefix == prefix and d.change == change:
                far = self.far.get((k.node, k.vrf, k.neighbor))
                if far and far[0] in nodes and far[1] == vrf:
                    out.add(k)
        return out


def _route_details(view: RouteView) -> dict:
    sel = view.selected()
    best = view.best()
    d = {"state": STATE_TEXT[view.presence()]}
    if sel is not None:
        d["protocol"] = sel.protocol
        d["next_hops"] = sorted({h.ip or h.interface or h.kind for h in sel.nexthops})
    if best is not None:
        src, p = best
        d.update({"from": src, "next_hop": list(primary_next_hops(p.attrs)), "as_path": p.attrs.as_path.render()})
    return d


def _pins_ok(pins: dict, view: RouteView, state: str) -> str:
    """'' if the new route satisfies every `with:` pin, else why not."""
    if not pins:
        return ""
    sel = view.selected()
    for k in ("protocol", "distance", "metric"):
        if k in pins:
            if sel is None:
                return f"no selected route to compare {k} with"
            got = getattr(sel, k)
            if got != pins[k]:
                return f"{k} is {show(got)}, pinned {show(pins[k])}"
    bgp = {k: v for k, v in pins.items() if k not in ("protocol", "distance", "metric")}
    if not bgp:
        return ""
    if state == "received":
        cands = [path_view(src, p) for (src, _), p in view.paths.items() if not p.best]
        cands += [{**{k: v for k, v in attrs_view(a).items() if k in ADJ_IN_VIEW}, "from": nbr}
                  for (nbr, _), a in view.adj_in.items()]
    else:
        best = view.best()
        if best is None:
            return "the selected route is not a BGP route, so BGP attributes can't match"
        cands = [path_view(*best)]
    for c in cands:
        bad = [k for k, v in bgp.items() if c.get(k, UNSEEN) != v]
        if not bad:
            return ""
    if len(cands) == 1:
        c = cands[0]
        return "; ".join(f"{k} is {show(c.get(k, 'not shown'))}, pinned {show(v)}" for k, v in bgp.items()
                         if c.get(k, UNSEEN) != v)
    return "no received path matches every pinned attribute"


def _appears(ctx: _Ctx, ln: Line) -> LineResult:
    afi = _afi(ln.prefix)
    res = LineResult(ln, True)
    for n in ln.nodes:
        b, a = ctx.before.route(n, ln.vrf, afi, ln.prefix), ctx.after.route(n, ln.vrf, afi, ln.prefix)
        bp, ap = b.presence(), a.presence()
        if bp != "absent":
            return LineResult(ln, False, f"{n}: the route was already there before ({STATE_TEXT[bp]})")
        want = {"installed": ("installed",), "selected": ("selected", "installed"), "received": ("received",),
                "discard": ("discard",)}[ln.state]
        if ap not in want:
            return LineResult(ln, False, f"{n}: after the change the route is {STATE_TEXT[ap]}; declared: {ln.state}")
        why = _pins_ok(ln.pins, a, ln.state)
        if why:
            return LineResult(ln, False, f"{n}: {why}")
        res.explained |= {d.key for d in ctx.route_items(n, ln.vrf, afi, ln.prefix)}
        res.details.append({"node": n, **_route_details(a)})
    res.explained |= ctx.adv_to(set(ln.nodes), ln.vrf, afi, ln.prefix, "added")
    return res


def _disappears(ctx: _Ctx, ln: Line) -> LineResult:
    afi = _afi(ln.prefix)
    res = LineResult(ln, True)
    for n in ln.nodes:
        b, a = ctx.before.route(n, ln.vrf, afi, ln.prefix), ctx.after.route(n, ln.vrf, afi, ln.prefix)
        bp = b.presence()
        ok_before = ("selected", "installed", "discard") + (("received",) if ln.including_received_only else ())
        if bp not in ok_before:
            hint = "" if bp == "absent" else " (a received-only route needs including_received_only: true)"
            return LineResult(ln, False, f"{n}: the route was {STATE_TEXT[bp]} before{hint}")
        if a.rib or a.paths:
            return LineResult(ln, False, f"{n}: the route is still there after the change ({STATE_TEXT[a.presence()]})")
        if ln.including_received_only and a.adj_in:
            return LineResult(ln, False, f"{n}: still received (before inbound policy) from "
                                         f"{', '.join(sorted({nb for nb, _ in a.adj_in}))}")
        kinds = ("rib", "path", "adj_in") if ln.including_received_only else ("rib", "path")
        res.explained |= {d.key for d in ctx.route_items(n, ln.vrf, afi, ln.prefix, kinds) if d.change == "removed"}
        res.details.append({"node": n, "before": _route_details(b)})
    res.explained |= ctx.adv_to(set(ln.nodes), ln.vrf, afi, ln.prefix, "removed")
    return res


def _propagated(field_name: str, before_adj: BgpAttrs, after_adj: BgpAttrs, before_best: BgpAttrs,
                after_best: BgpAttrs) -> bool:
    """A changed field of an advertisement carries the new best path's value (or, for the AS path, the
    same outbound prefix of ASNs in front of the old and the new best path)."""
    got, want = getattr(after_adj, field_name), getattr(after_best, field_name)
    if got == want:
        return True
    if field_name == "as_path":
        def head(adj, best):
            # compared as flat ASN lists (an AS_SET is one token): sequences merge, so comparing segments
            # would see the same prepend in two forms
            fa, fb = adj.as_path.render().split(), best.as_path.render().split()
            if len(fa) >= len(fb) and fa[len(fa) - len(fb):] == fb:
                return tuple(fa[:len(fa) - len(fb)])
            return None
        h1, h2 = head(before_adj, before_best), head(after_adj, after_best)
        return h1 is not None and h1 == h2
    return False


def _received(field_name: str, before_adj: BgpAttrs, after_adj: BgpAttrs, before_best: BgpAttrs,
              after_best: BgpAttrs) -> bool:
    """A changed field of an advertisement *to* the node is what the node now has on its best path (for
    the AS path: the receiver's path ends with the advertised one, with the same ASNs in front before and
    after, e.g. the sender's own AS added on the wire)."""
    if field_name == "as_path":
        def head(adj, best):
            fa, fb = adj.as_path.render().split(), best.as_path.render().split()
            if len(fb) >= len(fa) and fb[len(fb) - len(fa):] == fa:
                return tuple(fb[:len(fb) - len(fa)])
            return None
        h1, h2 = head(before_adj, before_best), head(after_adj, after_best)
        return h1 is not None and h1 == h2
    if field_name == "next_hops":
        return primary_next_hops(after_adj) == primary_next_hops(after_best)
    return getattr(after_adj, field_name) == getattr(after_best, field_name)


def _best_path(ctx: _Ctx, ln: Line) -> LineResult:
    afi = _afi(ln.prefix)
    n = ln.node
    b, a = ctx.before.route(n, ln.vrf, afi, ln.prefix), ctx.after.route(n, ln.vrf, afi, ln.prefix)
    bb, ab = b.best(), a.best()
    if bb is None:
        return LineResult(ln, False, f"{n}: no BGP best path for {ln.prefix} before the change")
    if ab is None:
        return LineResult(ln, False, f"{n}: no BGP best path for {ln.prefix} after the change")
    vb, va = path_view(*bb), path_view(*ab)
    wrong = [f"{k} is {show(va[k])}, declared {show(v)}" for k, v in ln.to.items() if va[k] != v]
    if wrong:
        return LineResult(ln, False, f"{n}: " + "; ".join(wrong))
    if all(vb[k] == v for k, v in ln.to.items()):
        return LineResult(ln, False, f"{n}: none of the listed attributes changed (they already had these values)")
    allowed = set(ln.to) | {c for k in ln.to for c in COUPLED.get(k, ())}
    frozen = [f"{k} {show(vb[k])} -> {show(va[k])}" for k in va if k not in allowed and va[k] != vb[k]]
    if frozen:
        return LineResult(ln, False, f"{n}: attributes not listed in `to:` changed too: {'; '.join(frozen)}")
    may = _fields_for(ln.to)
    new_best = next(sp for sp, p in a.paths.items() if p.best)
    res = LineResult(ln, True, details=[{"node": n, "before": {"from": vb["from"], **_compact(vb, ln.to)},
                                         "after": {"from": va["from"], **_compact(va, ln.to)}}])
    for d in ctx.items:
        k = d.key
        if k.vrf != ln.vrf or k.afi != afi or k.prefix != ln.prefix or d.change != "changed":
            continue
        f = set(d.fields)
        if k.kind == "path" and k.node == n:
            # the new best path: the best flag and the listed attributes (whose values were checked above);
            # every other path, the old best included: the best flag only
            ok = f <= {"best"} | (may if (k.neighbor, k.path_id) == new_best else set())
        elif k.kind == "rib" and k.node == n and k.protocol == "bgp":
            ok = f <= ({"nexthops"} if "next_hop" in ln.to else set()) | ({"metric"} if "med" in ln.to else set())
        elif k.kind == "adj_out" and k.node == n:
            ok = f <= may and all(_propagated(x, d.before, d.after, bb[1].attrs, ab[1].attrs) for x in f)
        elif k.kind == "adj_out":
            far = ctx.far.get((k.node, k.vrf, k.neighbor))
            ok = bool(far) and far[0] == n and far[1] == ln.vrf and far[2] == ab[0] and f <= may                 and all(_received(x, d.before, d.after, bb[1].attrs, ab[1].attrs) for x in f)
        else:
            ok = False
        if ok:
            res.explained.add(k)
    return res


def _compact(view: dict, to: dict) -> dict:
    return {k: show(view[k]) for k in to}


def _session(ctx: _Ctx, ln: Line) -> LineResult:
    n, vrf, nbr = ln.node, ln.vrf, ln.neighbor
    bs = ctx.before.sessions.get((n, vrf, nbr))
    if bs is None:
        return LineResult(ln, False, f"{n}: no BGP session to {nbr} before the change")
    if not bs.established:
        return LineResult(ln, False, f"{n}: the session to {nbr} was not established before ({bs.state})")
    if ln.afi not in bs.afis:
        return LineResult(ln, False, f"{n}: the session to {nbr} doesn't carry {ln.afi} ({', '.join(bs.afis) or 'none'})")
    afis = {ln.afi.split("-")[0]}
    ends = [(n, vrf, nbr)]
    far = ctx.far.get((n, vrf, nbr))
    if far:
        ends.append(far)
    res = LineResult(ln, True)
    if (n, vrf, nbr) not in ctx.after.sessions:
        return LineResult(ln, False, f"{n}: the session to {nbr} was removed from the config (a `session removed` "
                                     "difference); goes: down covers a configured session that stopped, not a "
                                     "deleted neighbor")
    for node, v, peer in ends:
        s = ctx.after.sessions.get((node, v, peer))
        if s is not None and s.established:
            return LineResult(ln, False, f"{node}: the session to {peer} is still established")
    learned: dict[str, list[str]] = {}
    for node, v, peer in ends:
        key = ItemKey("session", node, v, neighbor=peer)
        change = next((d for d in ctx.items if d.key == key), None)
        # a far end that deleted its neighbor stays undeclared, and so does any other change to the session
        # (its remote AS, address families, soft-reconfiguration): goes: down explains the state going down only
        if (node, v, peer) in ctx.after.sessions and change is not None and set(change.fields) <= SESSION_DOWN_FIELDS:
            res.explained.add(key)
        for d in ctx.items:
            k = d.key
            if k.node != node or k.vrf != v or k.kind == "session" or k.afi not in afis or d.change != "removed":
                continue
            if k.kind in ("path", "adj_in", "adj_out") and k.neighbor == peer:
                res.explained.add(k)
                if k.kind == "path":
                    learned.setdefault(node, []).append(k.prefix)
            elif k.kind == "rib" and k.protocol == "bgp":
                bv = ctx.before.route(node, v, k.afi, k.prefix)
                av = ctx.after.route(node, v, k.afi, k.prefix)
                if bv.paths and all(src == peer for src, _ in bv.paths) and not av.paths:
                    res.explained.add(k)
    res.details = [{"node": node, "neighbor": peer, "routes_learned_over_it": sorted(set(learned.get(node, [])))}
                   for node, _v, peer in ends]
    return res


def _advertisement(ctx: _Ctx, ln: Line) -> LineResult:
    afi = _afi(ln.prefix)
    b = {pid: a for (nb, pid), a in ctx.before.route(ln.node, ln.vrf, afi, ln.prefix).adj_out.items() if nb == ln.neighbor}
    a = {pid: x for (nb, pid), x in ctx.after.route(ln.node, ln.vrf, afi, ln.prefix).adj_out.items() if nb == ln.neighbor}
    keys = {ItemKey("adj_out", ln.node, ln.vrf, afi, "unicast", ln.prefix, ln.neighbor, path_id=p) for p in set(b) | set(a)}
    where = f"{ln.node}: the advertisement of {ln.prefix} to {ln.neighbor}"
    if ln.goes == "added":
        if b or not a:
            return LineResult(ln, False, f"{where} {'already existed before' if b else 'did not appear'}")
        best = ctx.after.route(ln.node, ln.vrf, afi, ln.prefix).best()
        if best is None:
            return LineResult(ln, False, f"{where} appeared, but {ln.node} has no BGP best path for it to compare "
                                         "the advertised attributes with")
        want = {**attrs_view(best[1].attrs), **ln.pins}
        own = {(s.local_address,) for (n, _v, _nb), s in ctx.after.sessions.items() if n == ln.node and s.local_address}
        self_hops = set(SELF_NEXT_HOPS) | own
        for adv in a.values():
            got = attrs_view(adv)
            names = [k for k in ADV_ATTRS if k != "local_pref" or adv.local_pref is not None or k in ln.pins]
            names += [k for k in ln.pins if k not in names]
            bad = [f"{k} is {show(got[k])}, {'declared' if k in ln.pins else 'the best path has'} {show(want[k])}"
                   for k in names if got[k] != want[k]]
            if "next_hop" not in ln.pins and got["next_hop"] != want["next_hop"] and got["next_hop"] not in self_hops:
                bad.append(f"next_hop is {show(got['next_hop'])}: neither the best path's {show(want['next_hop'])} nor "
                           f"{ln.node} itself (an outbound rewrite needs with: next_hop)")
            if bad:
                return LineResult(ln, False, f"{where}: " + "; ".join(bad))
    elif ln.goes == "removed":
        if a or not b:
            return LineResult(ln, False, f"{where} {'is still there' if a else 'did not exist before'}")
    else:
        if set(b) != set(a) or len(a) != 1:
            return LineResult(ln, False, f"{where} must exist (once) before and after to change")
        vb, va = attrs_view(next(iter(b.values()))), attrs_view(next(iter(a.values())))
        wrong = [f"{k} is {show(va[k])}, declared {show(v)}" for k, v in ln.to.items() if va[k] != v]
        if wrong:
            return LineResult(ln, False, f"{where}: " + "; ".join(wrong))
        if all(vb[k] == v for k, v in ln.to.items()):
            return LineResult(ln, False, f"{where}: none of the listed attributes changed")
        allowed = set(ln.to) | {c for k in ln.to for c in COUPLED.get(k, ())}
        frozen = [k for k in va if k not in allowed and va[k] != vb[k]]
        if frozen:
            return LineResult(ln, False, f"{where}: attributes not listed in `to:` changed too: {', '.join(frozen)}")
    return LineResult(ln, True, explained={k for k in keys if any(d.key == k for d in ctx.items)},
                      details=[{"node": ln.node, "neighbor": ln.neighbor}])


def _afi(prefix: str) -> str:
    return "ipv6" if ":" in prefix else "ipv4"


def _config_change(ctx: _Ctx, ln: Line) -> LineResult:
    keys = {d.key.node: d.key for d in ctx.items if d.key.kind == "config"}
    missing = [n for n in ln.nodes if n not in keys]
    if missing:
        return LineResult(ln, False, f"the running config of {', '.join(missing)} did not change")
    return LineResult(ln, True, explained={keys[n] for n in ln.nodes})


EVALUATORS = {"appears_on": _appears, "disappears_from": _disappears, "best_path_on": _best_path,
              "session": _session, "advertisement": _advertisement, "config_change_on": _config_change}

NO_EFFECT = "this change has no observable effect in the lab; test it with checks"
UNTESTED = "not tested if the lab doesn't exercise them"


def config_lines_changed(d: DiffItem) -> dict[str, list[str]]:
    """A config item's change as section-qualified lines: what the after config adds and removes."""
    from collections import Counter

    from .frr import qualified

    def minus(xs: list[str], ys: list[str]) -> list[str]:   # xs without ys, as multisets, in xs's order
        left, out = Counter(ys), []
        for x in xs:
            if left[x]:
                left[x] -= 1
            else:
                out.append(x)
        return out
    b, a = qualified(d.before or ()), qualified(d.after or ())
    added, removed = minus(a, b), minus(b, a)
    if not added and not removed:   # the same lines in another order: FRR's order is the config's (cold review 8)
        added = [f"(the order of the lines changed: {ln})" for ln, old in zip(a, b, strict=True) if ln != old]
    return {"added": added, "removed": removed}


# ---------------------------------------------------------------------------------------------------------
# The match
# ---------------------------------------------------------------------------------------------------------

@dataclass
class Match:
    status: str
    items: list[DiffItem]
    undeclared: list[DiffItem]
    lines: list[LineResult]
    allowed: dict[int, list[DiffItem]]          # allow entry index -> the items it explained
    # node -> {"added": [...], "removed": [...]}: running-config lines of an approved change, which verify did
    # not see exercised (UNTESTED); listed in every output
    untested: dict[str, dict[str, list[str]]] = field(default_factory=dict)

    @property
    def not_happened(self) -> list[LineResult]:
        return [r for r in self.lines if not r.happened]


def match(before: Snapshot, after: Snapshot, intent: Intent) -> Match:
    items = diff(before, after)
    ctx = _Ctx(before, after, items)
    results = [EVALUATORS[ln.form](ctx, ln) for ln in intent.lines]
    explained: set[ItemKey] = set()
    for r in results:
        if r.happened:
            explained |= r.explained
    # A node's running-config change is accepted (and listed as untested) where a declared change explains some
    # of that node's behaviour, or a config_change_on line declares it; anywhere else it is undeclared: a change
    # with no observable effect in the lab (gauntlet 0.4, R4)
    # the nodes a happened line names (not every node whose item a line explains: a node that only advertises
    # the declared route is not named, and a config change on it must be declared; cold review 3)
    behaving = {n for r in results if r.happened and r.line.form != "config_change_on" for n in r.line.nodes}
    untested = {}
    for d in items:
        if d.key.kind == "config" and (d.key in explained or d.key.node in behaving):
            explained.add(d.key)
            untested[d.key.node] = config_lines_changed(d)
    allowed: dict[int, list[DiffItem]] = {}
    undeclared = []
    for d in items:
        if d.key in explained:
            continue
        hit = next((i for i, al in enumerate(intent.allow)
                    if d.key.kind not in ("session", "vrf", "config") and al.matches(d.key.prefix, d.key.vrf)), None)
        if hit is not None:
            allowed.setdefault(hit, []).append(d)
            continue
        undeclared.append(d)
    if not items and not intent.lines:
        status = "no_change"
    elif undeclared or any(not r.happened for r in results):
        status = "failed"
    else:
        status = "matched"
    if status != "matched":
        untested = {}
    return Match(status, items, undeclared, results, allowed, untested)


def route_state(index: Index, key: ItemKey) -> str:
    """The route's state on the item's node, for the report (absent, received, selected, in the FIB)."""
    if key.kind in ("session", "vrf", "config"):
        return ""
    return STATE_TEXT[index.route(key.node, key.vrf, key.afi, key.prefix).presence()]


def baseline_problems(before: Snapshot) -> list[str]:
    """Why the before-lab is not a healthy baseline: every BGP session that is not established."""
    return [f"{k.node}{'' if k.vrf == 'default' else f' (vrf {k.vrf})'}: session to {k.neighbor} is {v.state}"
            for k, v in sorted(before.sessions().items()) if not v.established]


__all__ = ["DiffItem", "Index", "Match", "SnapshotError", "VerifyError", "baseline_problems", "diff", "match", "route_state"]
