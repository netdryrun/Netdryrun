"""Warm-lab re-verify (0.4.1 spike): the plan for applying a config change to a lab that is already running,
and the gate that keeps it off until it is proven. Design and status: docs/WARM-REVERIFY.md.

Nothing here touches a lab. `plan` decides from the two config trees alone; anything it can't prove a reload
reproduces is a cold boot, with the reason named. `equivalence` compares a cold and a warm corpus run; warm
ships only when it returns no mismatch.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

import yaml

FRR_CONF = "/etc/frr/frr.conf"
FRR_RELOAD = "/usr/lib/frr/frr-reload.py"


@dataclass
class Step:
    node: str
    action: str          # reload, soft-clear, prove
    command: list[str]


@dataclass
class WarmPlan:
    steps: list[Step] = field(default_factory=list)
    cold_reason: str | None = None     # set: boot cold, and say why
    ignored: list[str] = field(default_factory=list)   # changed files no node uses


def _files(root: Path) -> dict[str, bytes]:
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in sorted(root.rglob("*")) if p.is_file()}


def _is_frr(node: dict, defaults: dict) -> bool:
    kind = node.get("kind", defaults.get("kind", ""))
    image = str(node.get("image", defaults.get("image", "")))
    return kind == "linux" and "frr" in image.lower()


def _bound(topology: dict, topo_dir: PurePosixPath) -> dict[str, tuple[str, str]]:
    """Every file a node reads from the host: tree-relative path -> (node, path in the container or a role)."""
    t = topology.get("topology") or {}
    defaults = t.get("defaults") or {}
    out: dict[str, tuple[str, str]] = {}
    for name, node in (t.get("nodes") or {}).items():
        node = node or {}
        binds = list(defaults.get("binds") or []) + list(node.get("binds") or [])
        for b in binds:
            src, _, dst = str(b).partition(":")
            out[str(topo_dir / src)] = (name, dst.split(":")[0])
        for key in ("startup-config", "license"):
            if node.get(key):
                out[str(topo_dir / str(node[key]))] = (name, key)
    return out


def plan(before: Path, after: Path, topology: str) -> WarmPlan:
    """How to take a lab booted from `before` to `after` without a reboot, or why it can't be done.

    Warm only for an FRR node whose bound frr.conf changed: frr-reload applies the difference, `clear bgp *
    soft` makes BGP re-read what it already received and re-send what it advertised (a changed inbound
    route-map otherwise applies only to updates received afterwards), and frr-reload's test mode must then
    print no difference (the change landed). Everything else is cold."""
    b, a = _files(before), _files(after)
    if b.get(topology) != a.get(topology):
        return WarmPlan(cold_reason="the topology file changed")
    topo = yaml.safe_load(a[topology].decode("utf-8")) or {}
    topo_dir = PurePosixPath(topology).parent
    bound = _bound(topo, topo_dir)
    t = topo.get("topology") or {}
    defaults, nodes = t.get("defaults") or {}, t.get("nodes") or {}
    result = WarmPlan()
    changed_nodes: list[str] = []
    for rel in sorted(set(b) | set(a)):
        if b.get(rel) == a.get(rel) or rel == topology:
            continue
        if rel not in bound:
            if any(rel.startswith(src.rstrip("/") + "/") for src in bound):
                return WarmPlan(cold_reason=f"{rel} changed inside a bound folder")
            result.ignored.append(rel)
            continue
        node, target = bound[rel]
        if rel not in b or rel not in a:
            return WarmPlan(cold_reason=f"{rel} was added or removed")
        if not _is_frr(nodes.get(node) or {}, defaults):
            return WarmPlan(cold_reason=f"{rel} changed on {node}, which is not an FRR node: no warm path proven")
        if target != FRR_CONF:
            name = PurePosixPath(target).name if target.startswith("/") else target
            return WarmPlan(cold_reason=f"{rel} ({name} on {node}) changed: a reload can't apply it")
        changed_nodes.append(node)
    for node in changed_nodes:
        result.steps += [Step(node, "reload", [FRR_RELOAD, "--reload", FRR_CONF]),
                         Step(node, "soft-clear", ["vtysh", "-c", "clear bgp * soft"]),
                         Step(node, "prove", [FRR_RELOAD, "--test", FRR_CONF])]
    return result


def equivalence(cold: dict, warm: dict) -> list[str]:
    """Every case where a warm run disagrees with the cold run of the same corpus (results.json shape): a
    different verdict, different failed checks, an error on either side, or a case only one run has."""
    c = {x["id"]: x for x in cold.get("cases", [])}
    w = {x["id"]: x for x in warm.get("cases", [])}
    if not c and not w:
        return ["no cases: an empty comparison proves nothing"]
    out = []
    for cid in sorted(set(c) | set(w)):
        if cid not in c or cid not in w:
            out.append(f"{cid}: missing from the {'warm' if cid not in w else 'cold'} run")
            continue
        cs, ws = c[cid]["strategies"], w[cid]["strategies"]
        for s in sorted(set(cs) | set(ws)):
            a, b = cs.get(s), ws.get(s)
            if a is None or b is None:
                out.append(f"{cid} {s}: missing from the {'warm' if b is None else 'cold'} run")
            elif a.get("error") or b.get("error"):
                out.append(f"{cid} {s}: error (cold {a.get('error')!r}, warm {b.get('error')!r})")
            elif a["verdict"] != b["verdict"]:
                out.append(f"{cid} {s}: verdict cold {a['verdict']}, warm {b['verdict']}")
            elif sorted(a.get("failed_checks") or []) != sorted(b.get("failed_checks") or []):
                out.append(f"{cid} {s}: failed checks differ (cold {sorted(a['failed_checks'])}, "
                           f"warm {sorted(b['failed_checks'])})")
    return out
