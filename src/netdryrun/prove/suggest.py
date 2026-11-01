"""Suggested checks for a variant that survived, written from the baseline state the way `record` writes checks.

A suggestion pins what the network does today (the prefixes a session carries, a route that must stay, a best
path's attributes), never the variant's own leaked prefixes: a check fitted to 100.64.0.0/10 would catch this
variant and nothing else. It is text for a human or agent to review; prove never edits netdryrun.yml.
"""
from __future__ import annotations

from ..verify.engine import DiffItem
from ..verify.snapshot import BgpPath, Session, Snapshot
from .variants import Variant

MAX_SUGGESTIONS = 5
GUARDED = ("default_leak", "link_subnet_leak")   # their prefixes are what a standing guard names


def _session_prefixes(base: Snapshot, node: str, vrf: str, neighbor: str) -> list[str]:
    return sorted({k.prefix for k in base.items() if k.kind == "path" and k.node == node and k.vrf == vrf
                   and k.neighbor == neighbor})


def _at(vrf: str) -> dict:
    return {} if vrf == "default" else {"vrf": vrf}


def _attrs_check(node: str, vrf: str, prefix: str, best: BgpPath) -> dict:
    c = {"type": "bgp_route", "node": node, "prefix": prefix, **_at(vrf), "as_path": best.attrs.as_path.render()}
    if best.attrs.local_pref is not None:
        c["local_pref"] = best.attrs.local_pref
    if best.attrs.communities:
        c["communities"] = list(best.attrs.communities)
    return c


def _s(check: dict | None, reason: str) -> dict:
    return {"check": check, "reason": reason}


def suggest(variant: Variant, base: Snapshot, effect: list[DiffItem]) -> list[dict]:
    out: list[dict] = []
    for d in effect:
        k = d.key
        if k.kind == "session" and isinstance(d.before, Session) and d.before.established:
            out.append(_s({"type": "bgp_session", "node": k.node, "neighbor": k.neighbor, **_at(k.vrf)},
                          "the session is established today"))
        elif k.kind == "path" and d.change == "added" and k.neighbor != "local":
            if variant.kind in GUARDED:
                out.append(_s({"type": "route", "node": k.node, "prefix": k.prefix, "protocol": "bgp",
                               "present": False, **_at(k.vrf)}, f"a standing guard: {k.prefix} never via BGP"))
                continue
            today = _session_prefixes(base, k.node, k.vrf, k.neighbor)
            out.append(_s({"type": "bgp_prefixes", "node": k.node, "neighbor": k.neighbor, **_at(k.vrf),
                           "afi": f"{k.afi}-unicast", "exact": len(today)},
                          f"the session's prefix count today, exactly: one more prefix fails it. Today it carries "
                          f"{', '.join(today) or 'nothing'}"))
        elif k.kind == "rib" and d.change == "removed" and k.protocol == "bgp":
            out.append(_s({"type": "route", "node": k.node, "prefix": k.prefix, "protocol": "bgp", **_at(k.vrf)},
                          "the node has this BGP route today"))
        elif k.kind == "path" and d.change == "changed" and isinstance(d.before, BgpPath) and d.before.best:
            out.append(_s(_attrs_check(k.node, k.vrf, k.prefix, d.before), "the best path's attributes today"))
        elif k.kind == "path" and d.change == "removed" and isinstance(d.before, BgpPath) and d.before.best:
            out.append(_s(_attrs_check(k.node, k.vrf, k.prefix, d.before), "the best path today (it moved)"))
    if not out and any(d.key.kind == "adj_out" for d in effect):
        out.append(_s(None, "only what a node advertises changed (to a neighbor no lab node stands for); no check type "
                            "reads advertisements yet, so nothing in netdryrun.yml can catch this: tell the human"))
    unique = []
    for c in out:
        if c not in unique:
            unique.append(c)
    # sessions first (a session down explains the routes it took with it), then counts, routes, attributes
    order = {"bgp_session": 0, "bgp_prefixes": 1, "route": 2, "bgp_route": 3}
    unique.sort(key=lambda c: order[c["check"]["type"]] if c["check"] else 4)
    return unique[:MAX_SUGGESTIONS]
