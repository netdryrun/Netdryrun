"""The capture target must be a containerlab lab node, and nothing else.

Netdryrun never touches production, and capture keeps that promise: it takes a containerlab topology and a node name
from it (never an address or a hostname), and before running anything it asks Docker for that node's container and
checks the labels containerlab puts on every container it creates. A container someone else started, a node
containerlab only refers to (`host`, `ext-container`, a bridge) or a lab that isn't running is refused.
"""
from __future__ import annotations

import json
from pathlib import Path

from ..lab import Lab, LabError, Node, _run
from . import CaptureError

# Topology kinds that are not lab nodes containerlab created: the host itself, a container it doesn't manage,
# bridges and other links. Nothing to capture on them, and some are not part of the lab at all.
NOT_LAB_NODES = frozenset({"host", "ext-container", "bridge", "ovs-bridge", "macvlan", "k8s-kind"})


def lab_node(topology: Path, node: str) -> tuple[Lab, Node]:
    """The lab and the node to capture from, once Docker confirms the node is a running container of this
    containerlab lab. CaptureError otherwise; nothing has run on any device yet."""
    try:
        lab = Lab(Path(topology))
    except LabError as e:
        raise CaptureError(f"not a containerlab topology: {e}") from None
    if node not in lab.nodes:
        raise CaptureError(f"node {node!r} is not in {topology} (nodes: {', '.join(lab.nodes) or 'none'}); capture "
                           "only runs on a node of a containerlab lab")
    n = lab.nodes[node]
    if n.kind in NOT_LAB_NODES:
        raise CaptureError(f"node {node!r} is kind {n.kind!r}, which containerlab doesn't run as a lab node; "
                           "capture only runs on lab nodes")
    r = _run(["docker", "inspect", "--format", "{{json .Config.Labels}} {{.State.Running}}", n.container], timeout=60)
    if r.rc != 0:
        raise CaptureError(f"no container {n.container!r} for node {node!r}: deploy the lab first "
                           f"({(r.stderr or r.stdout).strip()[-200:] or 'docker inspect failed'})")
    text = r.stdout.strip()
    labels_text, _, running = text.rpartition(" ")
    try:
        labels = json.loads(labels_text or "null") or {}
    except ValueError:
        raise CaptureError(f"could not read the labels of {n.container!r}: {text[:200]!r}") from None
    if not isinstance(labels, dict):
        raise CaptureError(f"could not read the labels of {n.container!r}: {text[:200]!r}")
    if labels.get("containerlab") != lab.name or labels.get("clab-node-name") != node:
        raise CaptureError(
            f"{n.container!r} is not node {node!r} of containerlab lab {lab.name!r} (its labels say lab "
            f"{labels.get('containerlab')!r}, node {labels.get('clab-node-name')!r}); capture only runs on a "
            "container containerlab created for this topology")
    if running != "true":
        raise CaptureError(f"{n.container!r} is not running; start the lab first")
    return lab, n
