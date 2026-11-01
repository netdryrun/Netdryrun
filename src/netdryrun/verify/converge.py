"""The convergence-stable snapshot: two full snapshots `settle` seconds apart must be identical.

Identical means every item and the derived facts (prefix counts per session): every configured session
established, or stably not established, on both samples (compared as established or not, never by raw
FSM state), prefix counts stable, every route and path unchanged. A node is not ready, whatever it
repeats, while its RIB is still empty (zebra not up, interfaces not configured yet) or, when it is
expected to run BGP, while it has no BGP state at all (no session and no BGP path: bgpd answers but its
config isn't loaded yet).

Two samples `settle` apart can't see an update that arrives later than `settle`: settle must exceed the
slowest MRAI (advertisement interval) or update-delay in the lab.

A command that fails (vtysh can't reach a daemon that is still starting) is retried until the timeout;
then the snapshot is unreadable, an error (exit 2), never "nothing changed". Output that doesn't match the
schema stops at once. If the snapshots never repeat within `timeout`, the result is Inconclusive, naming
what kept moving.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable

from .frr import CommandFailed, CommandTimedOut
from .snapshot import Snapshot, SnapshotError

POLL = 3.0
ADV_MARGIN = 2.0   # seconds beyond the longest advertisement interval


@dataclass
class Inconclusive:
    reason: str
    moving: list[str]


class SnapshotUnreadable(SnapshotError):
    pass


def _moving(prev: Snapshot, cur: Snapshot, limit: int = 20) -> list[str]:
    a, b = prev.stability_view(), cur.stability_view()
    out = []
    for k in sorted(set(a) | set(b)):
        if a.get(k) != b.get(k):
            what = "appeared" if k not in a else "disappeared" if k not in b else "changed"
            out.append(f"{k.where()} {what}")
            if len(out) >= limit:
                out.append("...")
                break
    return out


def _not_ready(snap: Snapshot, bgp_nodes: set[str] | None = None) -> list[str]:
    """Why nodes aren't ready. `bgp_nodes`: the nodes expected to run BGP (None: every node)."""
    out = []
    for n, ns in sorted(snap.nodes.items()):
        if not any(k.kind == "rib" for k in ns.items):
            out.append(f"{n}: no routes in its RIB yet")
        elif (bgp_nodes is None or n in bgp_nodes) and not any(k.kind in ("session", "path") for k in ns.items):
            out.append(f"{n}: no BGP state yet (no session, no BGP path)")
        stale = sorted({k.where() for k, v in ns.items.items() if k.kind == "path" and "stale" in v.flags})
        out += [f"{x}: path kept stale by graceful restart (waiting for its session's End-of-RIB)" for x in stale]
    return out


def stable_snapshot(collect: Callable[[], Snapshot], *, settle: float, timeout: float,
                    clock: Callable[[], float] = time.monotonic, sleep: Callable[[float], None] = time.sleep,
                    log: Callable[[str], None] = lambda _: None,
                    bgp_nodes: set[str] | None = None) -> Snapshot | Inconclusive:
    t0 = clock()
    prev: Snapshot | None = None
    moving: list[str] = []
    while True:
        try:
            cur = collect()
        except CommandFailed as e:
            prev = None
            if clock() - t0 >= timeout:
                if isinstance(e, CommandTimedOut):
                    return Inconclusive(f"the snapshot was cut: a command never finished within its time limit "
                                        f"before the {timeout:g}s timeout, so the snapshot is incomplete. Retry at most "
                                        "once, then escalate: this says nothing about the change", [str(e)])
                raise SnapshotUnreadable(f"could not read the snapshot within {timeout:g}s: {e}") from None
            sleep(POLL)
            continue
        # a peer sends at most once per advertisement interval: two samples closer than that can miss a route
        # still on its way (0.3.2 multi-vendor audit), so settle covers the longest interval a node reports
        interval, where = max(((ns.adv_interval, n) for n, ns in cur.nodes.items()), default=(0.0, ""))
        if interval > 0 and interval + ADV_MARGIN > settle:
            settle = interval + ADV_MARGIN
            log(f"  {where} has an advertisement interval of {interval:g}s: settle extended to {settle:g}s")
        # an advertise-map is re-evaluated every `bgp conditional-advertisement timer` seconds: a change it makes can
        # land later than that after the lab looks settled (gauntlet 0.4, S2)
        timer, where = max(((ns.cond_adv_timer, n) for n, ns in cur.nodes.items()), default=(0.0, ""))
        if timer > 0 and timer + ADV_MARGIN > settle:
            settle = timer + ADV_MARGIN
            log(f"  {where} has conditional advertisement every {timer:g}s: settle extended to {settle:g}s")
        waiting = _not_ready(cur, bgp_nodes)
        if waiting:
            prev, moving = None, waiting
        elif prev is not None and prev.stability_view() == cur.stability_view():
            log(f"  snapshot stable ({len(cur.items())} items, {clock() - t0:.0f}s)")
            return cur
        elif prev is not None:
            moving = _moving(prev, cur)
            log(f"  still converging: {len(moving)} difference(s) since the last snapshot")
        if clock() - t0 + settle > timeout:
            what = "never became ready" if waiting else "kept moving"
            return Inconclusive(f"the lab's state {what} within {timeout:g}s (two snapshots {settle:g}s apart "
                                "never matched). Retry at most once, then escalate: this says nothing about the change",
                                moving)
        if not waiting:
            prev = cur
        sleep(settle if not waiting else POLL)
