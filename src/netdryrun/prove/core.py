"""`netdryrun prove`: run a lab's checks against known-bad variants of the network and report which ones every
check still passes. Mutation testing aimed at the network instead of the code.

The loop (phase 1 is this module, driven by an Executor; the live FRR executor follows in phase 2):

1. Run the checks on the lab as it is. Every check must pass, or there is no strength result (exit 2).
2. Take the baseline snapshot (the convergence-stable `verify` snapshot).
3. For each variant: apply it, snapshot, run the checks, revert it (always, whatever happened), snapshot again,
   run the checks again. The post-variant snapshot must equal the baseline and every check must pass again, or the
   run stops (exit 2): later variants would run on a different network.
4. Classify it (classify()). Only a variant with a failing check that has usable state and evidence from that
   variant's own run, on a lab whose routing state changed outside the variant's footprint, is **caught**.

Fail-closed rules, each with a red test (tests/test_prove_guardrails.py):

- a config variant whose running config doesn't show exactly the lines it removes and adds did not take effect:
  error (exit 2), never "no effect";
- a link_down variant with no routing effect did not take effect either: error;
- results must be one per check, fresh (never an object an earlier run returned, never started before the variant
  was applied): otherwise an internal error, never "caught";
- a failing check whose last sample had no usable state (Unready) or no evidence doesn't catch anything;
- failing checks with no routing effect are inconclusive (a flaky check, or state the snapshot doesn't see), never
  "caught" and never "no effect";
- a customer_leak caught only by checks that name the leaked prefixes is not caught (the checks are fitted to the
  variant, not to the fault): survived;
- no variant at all, or none with an effect: no strength result (error and inconclusive), never "caught 0 of 0".
"""
from __future__ import annotations

import ipaddress
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable, Protocol

from ..checks import Result, Unready
from ..config import Check
from ..verify.converge import Inconclusive
from ..verify.engine import DiffItem, diff, far_ends
from ..verify.frr import qualified
from ..verify.snapshot import Snapshot
from .variants import DEFAULT_MAX, LEAK_SPACE, Variant, generate, select

CAUGHT, SURVIVED, NO_EFFECT, INCONCLUSIVE = "caught", "survived", "no_effect", "inconclusive"


class ProveError(RuntimeError):
    """No strength result (exit 2). `kind`: setup (the lab or its checks aren't ready to be proven), apply (a
    variant didn't take effect as written), restore (the lab isn't its baseline any more: discard it), internal."""

    def __init__(self, message: str, kind: str = "setup"):
        super().__init__(message)
        self.kind = kind


class Executor(Protocol):
    """What prove needs from a lab. The live one (phase 2) deploys FRR in containerlab; tests drive a fake."""

    def run_checks(self, checks: list[Check]) -> list[Result]: ...

    def snapshot(self) -> Snapshot | Inconclusive: ...

    def links(self) -> list[tuple[tuple[str, str], tuple[str, str]]]: ...

    def apply(self, variant: Variant) -> None:
        """Apply every part of the variant (variant.parts(): its companion first), then wait for convergence."""

    def revert(self, variant: Variant) -> None:
        """Revert every part, in reverse order, whatever state the apply left; then wait for convergence."""

    def side_state(self) -> dict:
        """State outside the snapshot that a revert must also restore: each node's kernel routes and links, the
        FRR daemons' PIDs (a restarted bgpd reloads frr.conf), the hash of frr.conf on disk. Compared like the
        snapshot: any difference after a revert stops the run."""


@dataclass
class VariantResult:
    variant: Variant
    result: str
    failed: list[Result] = field(default_factory=list)     # caught: the checks that caught it
    effect: list[DiffItem] = field(default_factory=list)   # the routing state that changed outside the footprint
    note: str = ""
    suggested: list[dict] = field(default_factory=list)    # survived: checks a human or agent may review and add


@dataclass
class ProveReport:
    status: str = "error"            # passed (nothing survived), failed (survivors), inconclusive, error
    error: str = ""
    error_kind: str = ""             # with status error: setup, apply, restore (discard the lab) or internal
    checks: list[Check] = field(default_factory=list)
    variants: list[VariantResult] = field(default_factory=list)
    not_run: list[Variant] = field(default_factory=list)
    generated: int = 0
    baseline_items: int = 0
    started: str = ""
    finished: str = ""

    def count(self, result: str) -> int:
        return sum(v.result == result for v in self.variants)

    @property
    def exit_code(self) -> int:
        return {"passed": 0, "failed": 1, "inconclusive": 3}.get(self.status, 2)

    @property
    def summary(self) -> str:
        if self.status == "error":
            return f"no strength result: {self.error}"
        effective = len(self.variants) - self.count(NO_EFFECT)
        text = (f"caught {self.count(CAUGHT)} of {effective} known-bad variants with an effect "
                f"({self.count(SURVIVED)} survived, {self.count(INCONCLUSIVE)} inconclusive; "
                f"{self.count(NO_EFFECT)} more had no effect on routing)")
        if self.not_run:
            text += f"; {len(self.not_run)} generated variant(s) not run (budget)"
        return text + ". A finite set of variants: this does not show that the checks are complete."


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ---------------------------------------------------------------------------------------------------------
# Classification
# ---------------------------------------------------------------------------------------------------------

def footprint(variant: Variant, base: Snapshot, during: Snapshot) -> Callable[[DiffItem], bool]:
    """Whether a diff item is the variant's own mechanism rather than what the network did with it: for a variant
    that announces prefixes, the announcing node's own routes and paths for them, its advertisements of them to
    the other observed nodes, and what those nodes received from it before inbound policy. A leak to a neighbor
    outside the lab stays an effect (nothing in the lab would see it otherwise)."""
    mine = {(p.node, x) for p in variant.parts() for x in p.originates}
    if not mine:
        return lambda d: False
    ends = far_ends(base, during)

    def own(d: DiffItem) -> bool:
        k = d.key
        if (k.node, k.prefix) in mine:
            if k.kind == "rib" or (k.kind == "path" and k.neighbor == "local"):
                return True
            if k.kind == "adj_out" and (k.node, k.vrf, k.neighbor) in ends:
                return True
        far = ends.get((k.node, k.vrf, k.neighbor), ("",))[0]
        return k.kind == "adj_in" and (far, k.prefix) in mine
    return own


def routing_effect(variant: Variant, base: Snapshot, during: Snapshot) -> list[DiffItem]:
    """What changed in the routing state: every difference except running configs and the variant's footprint."""
    own = footprint(variant, base, during)
    return [d for d in diff(base, during) if d.key.kind != "config" and not own(d)]


def took_effect(variant: Variant, base: Snapshot, during: Snapshot) -> str | None:
    """Why a variant did not take effect as written, or None. Each node it changes must lose exactly the config lines
    it removes and gain exactly those it adds, no other node's config may change, and every prefix it announces must
    be in its node's BGP table (`network` is a no-op without a matching route: Grok B2)."""
    removes: dict[str, set[str]] = {}
    adds: dict[str, set[str]] = {}
    for part in variant.parts():
        removes.setdefault(part.node, set()).update(part.removes)
        adds.setdefault(part.node, set()).update(part.adds)
    for n in sorted(set(base.nodes) | set(during.nodes)):
        if n not in base.nodes or n not in during.nodes:
            return f"{n} is not in both snapshots"
        if n not in removes and base.nodes[n].config != during.nodes[n].config:
            return f"the running config of {n} changed too"
    for n in sorted(removes):
        if n not in base.nodes:
            return f"{n} is not in the snapshot"
        before, after = qualified(base.nodes[n].config), qualified(during.nodes[n].config)
        gone, new = sorted(set(before) - set(after)), sorted(set(after) - set(before))
        if gone != sorted(removes[n]) or new != sorted(adds[n]):
            want = [f"-{x}" for x in sorted(removes[n])] + [f"+{x}" for x in sorted(adds[n])]
            got = [f"-{x}" for x in gone] + [f"+{x}" for x in new]
            return (f"{n}'s running config changed by {got or 'nothing'}, expected {want}: it did not take effect as "
                    "written")
    for part in variant.parts():
        local = {k.prefix for k in during.nodes[part.node].items if k.kind == "path" and k.neighbor == "local"}
        missing = [p for p in part.originates if p not in local]
        if missing:
            return f"{part.node} announces {', '.join(missing)} in its config, but its BGP table doesn't have it"
    return None


def sessions_reset(variant: Variant, base: Snapshot, during: Snapshot) -> list[str]:
    """Sessions established at baseline that are down while a variant that doesn't shut one is applied: the apply
    may have reset them (a hard clear, a restarted bgpd: Grok A1), so a catch can't be credited to the variant. A
    neighbor with maximum-prefix may drop on a leak by design: that is the network's own answer, and counts."""
    if variant.kind in ("session_down", "link_down"):
        return []
    from .variants import parse

    out = []
    now_sessions = during.sessions()
    for k, s in sorted(base.sessions().items()):
        now_ = now_sessions.get(k)
        if s.established and not (now_ and now_.established) \
                and not parse(during.nodes[k.node].config).max_prefix(k.neighbor):
            out.append(k.where())
    return out


def _fitted(check: Check, variant: Variant) -> bool:
    """A check that would catch this variant for the wrong reason: one that names a prefix inside the leak space the
    variant announces from (fitted to the variant, not to the fault), or one on the announcing node about exactly a
    prefix it announces itself (its own announcement, not what the network did with it: Grok A4)."""
    if "prefix" not in check.params:
        return False
    try:
        net = ipaddress.ip_network(str(check.params["prefix"]), strict=False)
    except ValueError:
        return False
    for part in variant.parts():
        nets = [ipaddress.ip_network(p) for p in part.originates]
        if net.version == 4 and net.subnet_of(LEAK_SPACE) and any(n.version == 4 and n.subnet_of(LEAK_SPACE) for n in nets):
            return True
        if check.node == part.node and net in nets:
            return True
    return False


def real_failure(r: Result) -> bool:
    """A failed check with usable state and evidence: the network looked wrong to it, not unreadable."""
    return not r.passed and not isinstance(r.detail, Unready) and bool(r.evidence)


def classify(variant: Variant, effect: list[DiffItem], results: list[Result]) -> VariantResult:
    failing = [r for r in results if not r.passed]
    real = [r for r in failing if real_failure(r)]
    fitted = [r for r in real if _fitted(r.check, variant)]
    catching = [r for r in real if r not in fitted]
    if catching and effect:
        return VariantResult(variant, CAUGHT, failed=catching, effect=effect)
    if real and not effect:
        return VariantResult(variant, INCONCLUSIVE, failed=real, note=(
            "checks failed, but the routing state did not change: a flaky check, or state the snapshot doesn't see "
            "(the data plane). Not counted as caught"))
    if failing and not real:
        return VariantResult(variant, INCONCLUSIVE, failed=failing, note=(
            "the only failing checks had no usable state (or no evidence) on their last sample: a lab problem, not "
            "a catch"))
    if not effect:
        return VariantResult(variant, NO_EFFECT, note="nothing changed in the routing state outside the variant's own "
                                                      "announcement: an equivalent variant, or a fault the network "
                                                      "contained")
    note = ""
    if fitted:
        note = (f"only {', '.join(r.check.name for r in fitted)} failed, and those name the variant's own announced "
                "prefixes (the leak space, or the announcing node's own announcement): checks fitted to this variant, "
                "not to the fault. Counted as survived")
    return VariantResult(variant, SURVIVED, effect=effect, note=note)


# ---------------------------------------------------------------------------------------------------------
# The loop
# ---------------------------------------------------------------------------------------------------------

class _Fresh:
    """Results must be new objects, one per check in order, started no earlier than the run that asked for them."""

    def __init__(self):
        self.seen: list[Result] = []

    def check(self, results: list[Result], checks: list[Check], since: str, what: str) -> list[Result]:
        if len(results) != len(checks) or any(r.check is not c for r, c in zip(results, checks, strict=False)):
            raise ProveError(f"internal error: the {what} returned {len(results)} result(s) for {len(checks)} "
                             "check(s), or out of order; no strength result", "internal")
        for r in results:
            if any(r is old for old in self.seen) or (r.started or "") < since:
                raise ProveError(f"internal error: the {what} returned a result from an earlier run ({r.check.name}); "
                                 "no strength result", "internal")
        self.seen += results
        return results


def same_state(a: Snapshot, b: Snapshot) -> list[str]:
    """Where two snapshots differ, as diff item places, including prefix counts (empty when the same)."""
    if set(a.nodes) != set(b.nodes) or a.unobserved != b.unobserved:
        return [f"the observed nodes differ: {sorted(a.nodes)} vs {sorted(b.nodes)}"]
    va, vb = a.stability_view(), b.stability_view()
    return [k.where() for k in sorted(set(va) | set(vb)) if va.get(k) != vb.get(k)]


def _counts(snap: Snapshot) -> dict[tuple[str, str, str], int]:
    out = {}
    for k, s in snap.sessions().items():
        if k.vrf == "default":
            for afi, n in s.prefix_counts:
                out[(k.node, k.neighbor, afi)] = n
    return out


def prove(executor: Executor, checks: list[Check], *, kinds: list[str] | None = None, maximum: int = DEFAULT_MAX,
          log: Callable[[str], None] = lambda _: None, clock: Callable[[], str] = now) -> ProveReport:
    rep = ProveReport(checks=list(checks), started=clock())
    try:
        _prove(executor, rep, kinds, maximum, log, clock)
    except ProveError as e:
        rep.status, rep.error, rep.error_kind = "error", str(e), e.kind
    rep.finished = clock()
    return rep


def _prove(executor: Executor, rep: ProveReport, kinds, maximum: int, log, clock) -> None:
    checks = rep.checks
    if not checks:
        raise ProveError("netdryrun.yml has no checks to prove")
    fresh = _Fresh()
    since = clock()
    base_results = fresh.check(executor.run_checks(checks), checks, since, "baseline run")
    failing = [r.check.name for r in base_results if not r.passed]
    if failing:
        raise ProveError(f"the checks must pass on the lab as it is before they can be proven; {len(failing)} failed: "
                         + "; ".join(failing[:5]))
    base = executor.snapshot()
    if isinstance(base, Inconclusive):
        raise ProveError(f"the baseline snapshot never settled: {base.reason}")
    rep.baseline_items = len(base.items())
    side = executor.side_state()
    configs = {n: ns.config for n, ns in base.nodes.items()}
    variants = generate(configs, executor.links(), checks, _counts(base))
    rep.generated = len(variants)
    try:
        run, rep.not_run = select(variants, kinds, maximum)
    except ValueError as e:
        raise ProveError(str(e)) from None
    if not run:
        raise ProveError("no variant could be generated for this lab (no FRR BGP speaker with sessions, route-maps "
                         "or links matched the selected kinds)")
    for i, v in enumerate(run, 1):
        log(f"[{i}/{len(run)}] {v.description}")
        rep.variants.append(_one(executor, v, checks, base, side, fresh, clock))
        log(f"  {rep.variants[-1].result} (provisional: final once every variant ran and the lab was restored)")
    if rep.count(SURVIVED):
        rep.status = "failed"
    elif rep.count(INCONCLUSIVE) or not rep.count(CAUGHT):
        rep.status = "inconclusive"   # nothing measured, or something unclear: never a strength result
    else:
        rep.status = "passed"


def _one(executor: Executor, v: Variant, checks: list[Check], base: Snapshot, side: dict, fresh: _Fresh,
         clock) -> VariantResult:
    applied_at = clock()
    problem = None
    during: Snapshot | Inconclusive | None = None
    results: list[Result] = []
    try:
        executor.apply(v)
        during = executor.snapshot()
        results = executor.run_checks(checks)
    except Exception as e:   # whatever happened, the revert below runs; the error is reported after it
        problem = f"{type(e).__name__}: {e}" if not isinstance(e, ProveError) else str(e)
    finally:
        try:
            executor.revert(v)
        except Exception as e:
            raise ProveError(f"could not revert variant {v.id}: {e}; the lab is not the baseline any more, so no "
                             "later variant can run", "restore") from None
    restored_at = clock()
    after = executor.snapshot()
    if isinstance(after, Inconclusive):
        raise ProveError(f"after variant {v.id} was reverted, the lab never settled ({after.reason}); no strength "
                         "result", "restore")
    drift = same_state(base, after)
    now_side = executor.side_state()
    drift += [f"{k} (outside the snapshot)" for k in sorted(set(side) | set(now_side)) if side.get(k) != now_side.get(k)]
    if drift:
        raise ProveError(f"after variant {v.id} was reverted, the lab differs from the baseline ({'; '.join(drift[:5])}); "
                         "later variants would run on a different network: no strength result", "restore")
    again = fresh.check(executor.run_checks(checks), checks, restored_at, f"run after reverting {v.id}")
    still = [r.check.name for r in again if not r.passed]
    if still:
        raise ProveError(f"after variant {v.id} was reverted, the snapshot matches the baseline but checks fail: "
                         f"{'; '.join(still[:5])}. A failure that outlives the variant can't be attributed to it",
                         "restore")
    if problem:
        raise ProveError(f"variant {v.id} could not be applied: {problem}", "apply")
    if isinstance(during, Inconclusive):
        return VariantResult(v, INCONCLUSIVE, note=f"the lab never settled with the variant applied: {during.reason}")
    results = fresh.check(results, checks, applied_at, f"run of {v.id}")
    why = took_effect(v, base, during)
    if why:
        raise ProveError(f"variant {v.id}: {why}", "apply")
    effect = routing_effect(v, base, during)
    if v.kind == "link_down" and not effect:
        raise ProveError(f"variant {v.id}: the link went down but nothing changed in the routing state, not even its "
                         "connected route: the link did not go down", "apply")
    reset = sessions_reset(v, base, during)
    if reset:
        return VariantResult(v, INCONCLUSIVE, failed=[r for r in results if not r.passed], effect=effect, note=(
            f"session(s) went down under a variant that doesn't shut one ({'; '.join(reset[:3])}): applying it may "
            "have reset them, so a failing check can't be credited to the variant"))
    out = classify(v, effect, results)
    if out.result == SURVIVED:
        from .suggest import suggest
        out.suggested = suggest(v, base, effect)
    return out
