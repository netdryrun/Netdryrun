"""The `netdryrun.prove/v1` report: JSON (schema in website/docs/schemas/prove-v1.json) and console text."""
from __future__ import annotations

import json

from .. import __version__
from ..verify.engine import show
from .core import CAUGHT, INCONCLUSIVE, NO_EFFECT, SURVIVED, ProveReport, VariantResult
from .variants import KINDS

SCHEMA = "netdryrun.prove/v1"
MAX_EFFECT = 20        # effect items per variant in the report
MAX_EVIDENCE = 4000    # characters of evidence output per failed check
MAX_VALUE = 300        # characters of each value in an effect item
VERDICTS = {
    "passed": "NO VARIANT SURVIVED (only these variants)",
    "failed": "BLIND SPOTS FOUND: DO NOT RELY ON THESE CHECKS FOR THEM",
    "inconclusive": "NO VARIANT HAD AN EFFECT: NO STRENGTH RESULT",
    "error": "ERROR: NO STRENGTH RESULT",
}
LIMITS = (
    "Only the variants listed were run: a finite, generated set. No variant surviving does not show that the checks "
    "are complete.",
    "Only the top-level checks of netdryrun.yml are proven; scenario checks are not run under variants.",
    "The routing state is the FRR snapshot of `netdryrun verify` (sessions, RIB, BGP paths, advertisements, default "
    "VRF variants only): an effect outside it is not seen.",
    "A leak that a lab node filters counts as no effect, even where the announcing node's export policy let it out.",
)


def _evidence(r) -> list[dict]:
    out = []
    for e in r.evidence[-3:]:
        out.append({"node": e.get("node"), "cmd": e.get("cmd"), "output": str(e.get("output", ""))[-MAX_EVIDENCE:]})
    return out


def _effect(v: VariantResult) -> list[dict]:
    def value(x):
        return None if x is None else show(x)[:MAX_VALUE]
    return [{"where": d.key.where(), "change": d.change, "before": value(d.before), "after": value(d.after)}
            for d in v.effect[:MAX_EFFECT]]


def variant_json(v: VariantResult) -> dict:
    out = {**v.variant.to_json(), "result": v.result}
    if v.failed:
        out["failed_checks"] = [{"name": r.check.name, "type": r.check.type, "node": r.check.node,
                                 "detail": str(r.detail), "evidence": _evidence(r)} for r in v.failed]
    if v.effect:
        out["effect"] = _effect(v)
        out["effect_items"] = len(v.effect)
    if v.suggested:
        out["suggested_checks"] = v.suggested
    if v.note:
        out["note"] = v.note
    return out


def _by_kind(rep: ProveReport) -> dict:
    out = {}
    for k in KINDS:
        mine = [v for v in rep.variants if v.variant.kind == k]
        if mine:
            out[k] = {r: sum(v.result == r for v in mine) for r in (CAUGHT, SURVIVED, NO_EFFECT, INCONCLUSIVE)}
    return out


def to_dict(rep: ProveReport) -> dict:
    # On an error no variant result stands (a later restore failure may mean earlier variants ran on a polluted lab):
    # what ran is kept under `partial` for debugging, never under `variants` or in the counts (design review, Grok E5)
    done = [] if rep.status == "error" else rep.variants
    return {
        "schema": SCHEMA,
        "netdryrun": __version__,
        "status": rep.status,
        "verdict": VERDICTS[rep.status],
        "exit_code": rep.exit_code,
        "summary": rep.summary,
        "error": rep.error or None,
        "error_kind": rep.error_kind or None,
        "counts": {"caught": sum(v.result == CAUGHT for v in done), "survived": sum(v.result == SURVIVED for v in done),
                   "no_effect": sum(v.result == NO_EFFECT for v in done),
                   "inconclusive": sum(v.result == INCONCLUSIVE for v in done), "run": len(done),
                   "generated": rep.generated, "not_run": len(rep.not_run)},
        "by_kind": _by_kind(rep) if done else {},
        "not_generated": list(rep.not_generated),
        "checks": [c.name for c in rep.checks],
        "variants": [variant_json(v) for v in done],
        "partial": [variant_json(v) for v in rep.variants] if rep.status == "error" else [],
        "not_run": [v.to_json() for v in rep.not_run],
        "limits": list(LIMITS),
        "started": rep.started,
        "finished": rep.finished,
    }


def to_json(rep: ProveReport) -> str:
    return json.dumps(to_dict(rep), indent=2) + "\n"


def console(rep: ProveReport) -> str:
    lines = [VERDICTS[rep.status], rep.summary]
    if rep.status == "error":
        if rep.error_kind == "restore":
            lines.append("The lab is not its baseline any more: destroy it before any other run.")
        return "\n".join(lines)
    by_kind = _by_kind(rep)
    if by_kind:
        lines.append("By kind: " + "; ".join(f"{k} {c[CAUGHT]} caught, {c[SURVIVED]} survived, {c[NO_EFFECT]} no effect"
                                             + (f", {c[INCONCLUSIVE]} inconclusive" if c[INCONCLUSIVE] else "")
                                             for k, c in by_kind.items()))
    marks = {CAUGHT: "caught", SURVIVED: "SURVIVED", NO_EFFECT: "no effect", INCONCLUSIVE: "inconclusive"}
    for v in rep.variants:
        lines.append(f"  [{marks[v.result]}] {v.variant.description}")
        for r in v.failed[:3]:
            lines.append(f"      failed: {r.check.name}: {' '.join(str(r.detail).split())[:160]}")
        if v.result == SURVIVED:
            for d in v.effect[:5]:
                lines.append(f"      unnoticed: {d.key.where()} {d.change}")
            for c in v.suggested:
                what = json.dumps(c["check"]) if c["check"] else "no check type can see this"
                lines.append(f"      suggested (review it): {what} ({c['reason']})")
        if v.note:
            lines.append(f"      note: {v.note}")
    if rep.not_run:
        lines.append(f"  not run (budget, raise --max): {', '.join(v.id for v in rep.not_run[:10])}"
                     + (" ..." if len(rep.not_run) > 10 else ""))
    if rep.status == "failed":
        lines.append("Add a check that catches each survivor, or tell the human which blind spot remains. "
                     "prove never edits netdryrun.yml.")
    return "\n".join(lines)
