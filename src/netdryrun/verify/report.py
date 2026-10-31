"""The `netdryrun.verify/v1` report: JSON (schema in website/docs/schemas/verify-v1.json) and console text."""
from __future__ import annotations

import json
import shlex
from dataclasses import dataclass, field

from .converge import Inconclusive
from .engine import NO_EFFECT, UNTESTED, Index, Match, _flat, config_lines_changed, route_state, show
from .frr import show_command
from .intent import Intent
from .snapshot import Snapshot, _plain

SCHEMA = "netdryrun.verify/v1"
VERDICTS = {
    "matched": "INTENT MATCHED",
    "no_change": "NO BEHAVIOR CHANGE",
    "failed": "UNDECLARED CHANGES: DO NOT APPLY",
    "inconclusive": "INCONCLUSIVE",
    "unhealthy_baseline": "INCONCLUSIVE: UNHEALTHY BASELINE",
    "error": "ERROR: NO VERDICT",
}
EXIT_CODES = {"matched": 0, "no_change": 0, "failed": 1, "error": 2, "inconclusive": 3, "unhealthy_baseline": 3}
NOTICE = ("Explained is not the same as safe: review the declared intent above. This verdict covers the observed "
          "control-plane state of this lab (sessions, RIB, BGP paths, advertisements), nothing else.")
ALLOW_WARNING = ("allow_anywhere weakens the verdict: every change to the listed prefixes is accepted on every node. "
                 "A change that adds or widens it needs a second approver (CODEOWNERS); the CLI can't enforce that.")
NO_GUARDS_WARNING = ("no standing guards ran: nothing checked the after lab against the base branch's netdryrun.yml, "
                     "so an intent that declares a leak explains it. Pass --guards, or keep a netdryrun.yml next to "
                     "the topology in the --before ref.")
INTENT_EDITED_WARNING = ("intent edited in the same change: needs a code-owner review (the intent file differs "
                         "between --before and --after, so the change wrote its own allowlist)")
INCONCLUSIVE_ADVICE = "Retry at most once, then escalate. This says nothing about the change."


@dataclass
class VerifyResult:
    status: str
    topology: str = ""
    before_spec: str = ""
    after_spec: str = ""
    intent: Intent | None = None
    intent_supplied_by: str = "cli"
    match: Match | None = None
    before: Snapshot | None = None
    after: Snapshot | None = None
    error: str = ""
    inconclusive: Inconclusive | None = None
    inconclusive_side: str = ""               # before, after, or rerun (the after side booted again)
    determinism: dict | None = None           # the rerun of an approving verdict: {rerun, identical, differing}
    baseline_problems: list[str] = field(default_factory=list)
    baseline_overridden: bool = False
    guards: dict | None = None
    guards_source: str = "none"             # before-ref, explicit, none
    timings: dict = field(default_factory=dict)
    containers: dict = field(default_factory=dict)
    run_id: str = ""
    started: str = ""
    finished: str = ""
    warnings: list[str] = field(default_factory=list)
    failed_because: list[str] = field(default_factory=list)

    @property
    def verdict(self) -> str:
        return VERDICTS[self.status]

    @property
    def exit_code(self) -> int:
        return EXIT_CODES[self.status]


def _diag(key, containers: dict) -> str:
    cmd = show_command(key)
    container = containers.get(key.node)
    return "docker exec " + shlex.join([container, "vtysh", "-c", cmd]) if container else f"vtysh -c {shlex.quote(cmd)}"


def _summary(d) -> str:
    where = d.key.where()
    if d.key.kind == "config":
        ch = config_lines_changed(d)
        return (f"{where}: {len(ch['added'])} line(s) added, {len(ch['removed'])} removed; {NO_EFFECT} (or declare "
                "it with config_change_on)")
    if d.kind == "session removed":
        return f"{where}: session removed (the neighbor is gone from the config)"
    if d.change != "changed":
        return f"{where}: {d.change}"
    b, a = _flat(d.before), _flat(d.after)
    parts = [f"{f}: {show(b.get(f))} -> {show(a.get(f))}" for f in d.fields if f != "entries"]
    return f"{where}: changed ({'; '.join(parts) if parts else 'entries'})"


def item_json(d, ib: Index, ia: Index, containers: dict) -> dict:
    k = d.key
    out = {"kind": k.kind, "node": k.node, "vrf": k.vrf, "change": d.change}
    if k.kind == "config":
        out.update({"fields": [], "before": None, "after": None, "lines": config_lines_changed(d), "summary": _summary(d),
                    "next_diagnostic": _diag(k, containers)})
        return out
    if k.kind not in ("session", "vrf"):
        out.update({"afi": k.afi, "safi": k.safi, "prefix": k.prefix})
    if k.neighbor:
        out["neighbor"] = k.neighbor
    if k.protocol:
        out["protocol"] = k.protocol
    if k.path_id:
        out["path_id"] = k.path_id
    out["fields"] = list(d.fields)
    if k.kind not in ("session", "vrf"):
        out["route_before"] = route_state(ib, k)
        out["route_after"] = route_state(ia, k)
    out["before"] = _plain(d.before)
    out["after"] = _plain(d.after)
    out["summary"] = _summary(d)
    out["next_diagnostic"] = _diag(k, containers)
    return out


def _intent_json(r: VerifyResult) -> dict | None:
    if r.intent is None:
        return None
    return {"source": r.intent.source, "supplied_by": r.intent_supplied_by,
            "lines": [ln.text for ln in r.intent.lines],
            "allow_anywhere": [a.pattern + ("" if a.vrf == "default" else f" (vrf {a.vrf})") for a in r.intent.allow],
            "file": _plain_yaml(r.intent.echo)}


def _plain_yaml(v):
    """The intent file's own content, made JSON-safe (YAML can hold dates and other non-JSON scalars)."""
    if isinstance(v, dict):
        return {str(k): _plain_yaml(x) for k, x in v.items()}
    if isinstance(v, list):
        return [_plain_yaml(x) for x in v]
    if v is None or isinstance(v, (str, int, float, bool)):
        return v
    return str(v)


def to_dict(r: VerifyResult) -> dict:
    m = r.match
    ib = Index(r.before) if r.before is not None else None
    ia = Index(r.after) if r.after is not None else None
    undeclared, not_happened, declared, allowed = [], [], [], []
    items_total = 0
    if m is not None:
        items_total = len(m.items)
        undeclared = [item_json(d, ib, ia, r.containers) for d in m.undeclared]
        by_key = {d.key: d for d in m.items}
        for lr in m.lines:
            if not lr.happened:
                not_happened.append({"intent": lr.line.index, "line": lr.line.text, "reason": lr.reason})
            else:
                declared.append({"intent": lr.line.index, "line": lr.line.text, "details": lr.details,
                                 "items": [_summary(by_key[k]) for k in sorted(lr.explained) if k in by_key]})
        for i, ds in sorted(m.allowed.items()):
            routes = sorted({(d.key.node, d.key.vrf, d.key.prefix) for d in ds})
            allowed.append({"pattern": r.intent.allow[i].pattern, "vrf": r.intent.allow[i].vrf,
                            "expanded": sorted({d.key.prefix for d in ds}),
                            "routes": [{"node": n, "vrf": v, "prefix": p} for n, v, p in routes],
                            "items": [_summary(d) for d in ds]})
    inc = None
    if r.inconclusive is not None:
        inc = {"side": r.inconclusive_side, "reason": r.inconclusive.reason, "moving": r.inconclusive.moving,
               "advice": INCONCLUSIVE_ADVICE}
    elif r.status == "unhealthy_baseline":
        inc = {"side": "before", "reason": "the before-lab is not a healthy baseline (BGP sessions down); rerun with "
                                           "--allow-unhealthy-baseline to compare anyway",
               "moving": [], "advice": INCONCLUSIVE_ADVICE}
    return {
        "schema": SCHEMA,
        "verdict": r.verdict,
        "status": r.status,
        "notice": NOTICE,
        "intent": _intent_json(r),
        "run_id": r.run_id,
        "started": r.started,
        "finished": r.finished,
        "topology": r.topology,
        "before": r.before_spec,
        "after": r.after_spec,
        "failed_because": r.failed_because,
        "warnings": r.warnings,
        "error": r.error or None,
        "inconclusive": inc,
        "determinism": r.determinism,
        "baseline": {"healthy": not r.baseline_problems, "problems": r.baseline_problems,
                     "overridden": r.baseline_overridden},
        "diff_items": items_total,
        "undeclared": undeclared,
        "not_happened": not_happened,
        "declared": declared,
        "allowed": allowed,
        # running-config lines of an approved change that verify did not see exercised (gauntlet 0.4, R4)
        "untested_config": [{"node": n, **ch} for n, ch in sorted((m.untested if m is not None else {}).items())]
        if r.status in ("matched", "no_change") else [],
        "unobserved": dict(sorted((r.before or r.after).unobserved.items())) if (r.before or r.after) else {},
        "guards": r.guards,
        "guards_source": r.guards_source,
        "timings": r.timings,
        "evidence": {"before": r.before.to_json() if r.before is not None else None,
                     "after": r.after.to_json() if r.after is not None else None},
    }


def to_json(r: VerifyResult) -> str:
    return json.dumps(to_dict(r), indent=2, sort_keys=False) + "\n"


def console(r: VerifyResult, max_items: int = 40) -> str:
    d = to_dict(r)
    lines = [f"verify: {r.verdict}" + (" (warning: no standing guards ran)"
                                       if r.guards_source == "none" and r.status in ("matched", "no_change", "failed")
                                       else "")]
    if d["intent"] is not None:
        lines.append(f"Intent ({d['intent']['source']}, supplied by {d['intent']['supplied_by']}):")
        lines += [f"  [{i}] {t}" for i, t in enumerate(d["intent"]["lines"])] or ["  (none: nothing may change)"]
        lines += [f"  allow_anywhere: {p}" for p in d["intent"]["allow_anywhere"]]
    for w in r.warnings:
        lines.append(f"warning: {w}")
    if r.error:
        lines.append(f"error: {r.error}")
    if d["inconclusive"]:
        lines.append(f"{d['inconclusive']['side']}: {d['inconclusive']['reason']}")
        lines += [f"  moving: {x}" for x in d["inconclusive"]["moving"][:max_items]]
        lines.append(INCONCLUSIVE_ADVICE)
    for p in r.baseline_problems:
        lines.append(f"baseline: {p}")
    if d["undeclared"]:
        lines.append(f"Undeclared changes ({len(d['undeclared'])}):")
        for it in d["undeclared"][:max_items]:
            lines.append(f"  - {it['summary']}")
            lines.append(f"      next: {it['next_diagnostic']}")
        if len(d["undeclared"]) > max_items:
            lines.append(f"  ... and {len(d['undeclared']) - max_items} more (see the JSON report)")
    if d["not_happened"]:
        lines.append("Declared but didn't happen:")
        lines += [f"  - [{x['intent']}] {x['line']}: {x['reason']}" for x in d["not_happened"]]
    if d["declared"]:
        lines.append("Declared and observed:")
        for x in d["declared"]:
            lines.append(f"  - [{x['intent']}] {x['line']} ({len(x['items'])} item(s))")
    for a in d["allowed"]:
        lines.append(f"Allowed by {a['pattern']} (allow_anywhere), {len(a['routes'])} route(s):")
        lines += [f"  - {x['node']}{'' if x['vrf'] == 'default' else ' vrf ' + x['vrf']} {x['prefix']}"
                  for x in a["routes"]]
    if d["untested_config"]:
        lines.append(f"Config lines changed, {UNTESTED}:")
        for u in d["untested_config"]:
            lines += [f"  {u['node']}: + {x}" for x in u["added"]] + [f"  {u['node']}: - {x}" for x in u["removed"]]
    if r.guards is not None:
        lines.append(f"Standing guards ({r.guards.get('source')}): {r.guards.get('status')}, "
                     f"{r.guards.get('passed', 0)} passed, {r.guards.get('failed', 0)} failed")
        for f in r.guards.get("failures", [])[:max_items]:
            lines.append(f"  - {f['check']}: {f['reason']}")
    if r.status in ("matched", "no_change"):
        lines.append(NOTICE)
    return "\n".join(lines)


MD_HEAD = {
    "matched": "✅ Netdryrun verify: INTENT MATCHED",
    "no_change": "✅ Netdryrun verify: NO BEHAVIOR CHANGE",
    "failed": "❌ Netdryrun verify: UNDECLARED CHANGES: DO NOT APPLY",
    "inconclusive": "⏸️ Netdryrun verify: INCONCLUSIVE",
    "unhealthy_baseline": "⏸️ Netdryrun verify: INCONCLUSIVE: UNHEALTHY BASELINE",
    "error": "⚠️ Netdryrun verify: ERROR: NO VERDICT",
}


def markdown(r: VerifyResult, max_items: int = 40) -> str:
    """The PR comment (and job summary) of a verify run: the verdict, the declared intent echoed for the
    reviewer, the undeclared items each with its next diagnostic, the declared lines that didn't happen and
    the standing guards. Everything that can come from a config or the lab is made inert (no HTML, links or
    mentions), as in the run report."""
    from ..report import MAX_MARKDOWN, _md_block, _md_cell, _md_code

    d = to_dict(r)
    lines = [f"### {MD_HEAD[r.status]}", ""]
    if d["intent"] is not None:
        lines.append(f"**Declared intent** ({_md_cell(d['intent']['source'])}, supplied by "
                     f"{_md_cell(d['intent']['supplied_by'])}): review it; explained is not the same as safe.")
        lines += [""] + [f"{i}. {_md_cell(t)}" for i, t in enumerate(d["intent"]["lines"])] \
            if d["intent"]["lines"] else ["", "- none: nothing may change"]
        lines += [f"- allow_anywhere: {_md_code(p)} (weakens the verdict)" for p in d["intent"]["allow_anywhere"]]
        lines.append("")
    lines += [f"> ⚠️ {_md_cell(w)}" for w in r.warnings] + ([""] if r.warnings else [])
    if r.error:
        lines += _md_block(r.error) + [""]
    if d["inconclusive"]:
        lines += [f"> {_md_cell(d['inconclusive']['side'])}: {_md_cell(d['inconclusive']['reason'])}", ">",
                  f"> {INCONCLUSIVE_ADVICE}", ""]
        lines += [f"- moving: {_md_cell(x)}" for x in d["inconclusive"]["moving"][:max_items]]
    lines += [f"- baseline: {_md_cell(p)}" for p in r.baseline_problems]
    tail = []
    if d["undeclared"]:
        tail += [f"**Undeclared changes ({len(d['undeclared'])})**", ""]
        for it in d["undeclared"][:max_items]:
            tail.append(f"- {_md_cell(it['summary'])}<br>next: {_md_code(it['next_diagnostic'])}")
        if len(d["undeclared"]) > max_items:
            tail.append(f"- … and {len(d['undeclared']) - max_items} more (see the JSON report)")
        tail.append("")
    if d["not_happened"]:
        tail += ["**Declared but didn't happen**", ""]
        tail += [f"- [{x['intent']}] {_md_cell(x['line'])}: {_md_cell(x['reason'])}" for x in d["not_happened"]]
        tail.append("")
    if d["declared"]:
        tail += ["**Declared and observed**", ""]
        tail += [f"- [{x['intent']}] {_md_cell(x['line'])} ({len(x['items'])} item(s))" for x in d["declared"]]
        tail.append("")
    for a in d["allowed"]:
        tail.append(f"- allowed by {_md_code(a['pattern'])}: {len(a['routes'])} route(s)")
    if d["untested_config"]:
        tail += [f"**Config lines changed, {UNTESTED}**", ""]
        for u in d["untested_config"]:
            tail += [f"- {_md_cell(u['node'])}: + {_md_code(x)}" for x in u["added"][:max_items]]
            tail += [f"- {_md_cell(u['node'])}: − {_md_code(x)}" for x in u["removed"][:max_items]]
            more = max(0, len(u["added"]) - max_items) + max(0, len(u["removed"]) - max_items)
            if more:
                tail.append(f"- … and {more} more on {_md_cell(u['node'])} (see the JSON report)")
        tail.append("")
    if r.guards is not None:
        tail += [f"**Standing guards** ({_md_cell(r.guards.get('source'))}): {_md_cell(r.guards.get('status'))}, "
                 f"{r.guards.get('passed', 0)} passed, {r.guards.get('failed', 0)} failed", ""]
        tail += [f"- {_md_cell(f['check'])}: {_md_cell(f['reason'])}" for f in r.guards.get("failures", [])[:max_items]]
    elif r.status in ("matched", "no_change", "failed"):
        tail.append("**Standing guards:** none ran.")
    tail += ["", f"<sub>{_md_cell(NOTICE)} Run {_md_cell(r.run_id)} · full evidence in the JSON report.</sub>"]
    text = "\n".join(lines + tail) + "\n"
    if len(text) > MAX_MARKDOWN:    # a GitHub comment holds at most 65536 characters
        return markdown(r, max_items=max(1, max_items // 2)) if max_items > 1 else text[:MAX_MARKDOWN - 100] + "\n…\n"
    return text
