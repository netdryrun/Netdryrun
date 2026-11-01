"""`netdryrun prove`: how strong a lab's checks are, measured against known-bad variants of the network.

Phase 1 (this build) is the lab-free part: variant generation, classification, restore verification, the
`netdryrun.prove/v1` report and its exit codes, driven by an Executor. The live FRR executor arrives in phase 2;
until then a run without one is an error (exit 2), never a result, and `--plan` lists the variants without a lab.
"""
from __future__ import annotations

from typing import Callable

from ..config import Config
from ..drivers import DriverError, detect
from ..lab import Lab, LabError
from .core import Executor, ProveError, ProveReport, prove, now
from .variants import DEFAULT_MAX, KINDS, Variant, generate, select

LIVE_PENDING = ("live prove runs are not in this build yet (they land in phase 2, after 0.4.1 ships); "
                "use --plan to list the variants without a lab")
BRIDGES = ("bridge", "ovs-bridge")

__all__ = ["DEFAULT_MAX", "KINDS", "LIVE_PENDING", "Executor", "ProveError", "ProveReport", "lab_configs", "plan",
           "prove", "prove_config"]


def frr_nodes(lab: Lab, overrides: dict[str, str]) -> list[str]:
    """The lab's routing nodes, all FRR, or ProveError: prove snapshots FRR only, and a node it can't snapshot could
    hide a variant's effect or a restore that didn't happen."""
    out = []
    for name, node in sorted(lab.nodes.items()):
        if node.kind in BRIDGES:
            continue
        try:
            drv = overrides.get(name) or detect(node)
        except DriverError:
            drv = None
        if drv != "frr":
            raise ProveError(f"node {name} runs {drv or 'something Netdryrun cannot detect'}: prove reads FRR nodes "
                             "only (others follow when their snapshot exists), and a node it can't read could hide a "
                             "variant's effect or a revert that didn't happen")
        out.append(name)
    return out


def lab_configs(cfg: Config) -> tuple[Lab, dict[str, str]]:
    """The lab and each FRR node's config file text, read from the files the topology binds (no lab needed)."""
    from ..verify.run import bind_reach, is_router_config

    try:
        lab = Lab(cfg.lab)
    except LabError as e:
        raise ProveError(str(e)) from None
    nodes = frr_nodes(lab, cfg.drivers)
    texts: dict[str, str] = {n: "" for n in nodes}
    for src, reach in sorted(bind_reach(cfg.lab).items()):
        for node, dest in reach:
            if node in texts and is_router_config(dest):
                try:
                    texts[node] += (cfg.lab.parent / src).read_text(encoding="utf-8") + "\n"
                except (OSError, UnicodeDecodeError) as e:
                    raise ProveError(f"cannot read {src}, the config of {node}: {e}") from None
    return lab, texts


def plan(cfg: Config, kinds: list[str] | None = None, maximum: int = DEFAULT_MAX) -> tuple[list[Variant], list[Variant]]:
    """The variants a run would try, from the config files (no lab). The customer leak sized to a prefix-count range
    needs today's counts, so it only appears in a run."""
    lab, texts = lab_configs(cfg)
    try:
        return select(generate(texts, lab.links, cfg.checks), kinds, maximum)
    except ValueError as e:
        raise ProveError(str(e)) from None


def prove_config(cfg: Config, *, executor: Executor | None = None, kinds: list[str] | None = None,
                 maximum: int = DEFAULT_MAX, log: Callable[[str], None] = lambda _: None) -> ProveReport:
    """prove() on the lab of netdryrun.yml. Without an executor (phase 1 ships none for a live lab): an error report."""
    started = now()
    try:
        lab_configs(cfg)   # FRR only, configs readable: refused before anything starts
        if executor is None:
            raise ProveError(LIVE_PENDING)
    except ProveError as e:
        return ProveReport(status="error", error=str(e), error_kind=e.kind, checks=list(cfg.checks), started=started,
                           finished=now())
    return prove(executor, cfg.checks, kinds=kinds, maximum=maximum, log=log)

