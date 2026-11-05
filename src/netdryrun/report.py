"""Render a run as console text, JSON evidence, Markdown and JUnit XML."""
from __future__ import annotations

import json
import re
from xml.sax.saxutils import escape, quoteattr

from .checks import Result
from .runner import RunReport

ICON = {True: "PASS", False: "FAIL"}
MAX_MARKDOWN = 65000  # characters; GitHub rejects a comment over 65536 (the Action adds a marker line)


def console_line(r: Result) -> str:
    line = f"  [{ICON[r.passed]}] {r.check.name} -- {r.detail} ({r.duration}s)"
    return line + "".join(f"\n      warning: {w['text']}" for w in r.warnings)


def all_warnings(rep: RunReport) -> list[dict]:
    """Every convergence warning of the run, each naming its check: the top-level list of the JSON report and the
    MCP result, so a reader of the status alone still sees that some checks ran with one."""
    return [{"check": r.check.name, **w} for r in rep.results for w in r.warnings]


def summary_line(rep: RunReport) -> str:
    if rep.error:
        return f"ERROR: {rep.error}"
    if rep.status == "inconclusive":
        return (f"INCONCLUSIVE: {rep.inconclusive_reason} ({rep.failed} of {len(rep.results)} checks failed; "
                "this says nothing about the change)")
    warned = sum(1 for r in rep.results if r.warnings)
    tail = f"; {warned} with a convergence warning" if warned else ""
    return f"{rep.status.upper()}: {rep.passed} passed, {rep.failed} failed ({len(rep.results)} checks{tail})"


def to_json(rep: RunReport) -> str:
    data = {
        "schema": "netdryrun.report/v1",
        "status": rep.status,
        "lab": rep.lab_name,
        "config": str(rep.config.path),
        "started": rep.started,
        "finished": rep.finished,
        "error": rep.error or None,
        "inconclusive_reason": rep.inconclusive_reason,
        "environment": rep.environment,
        "summary": {"passed": rep.passed, "failed": rep.failed, "total": len(rep.results)},
        "warnings": {"count": len(all_warnings(rep)), "items": all_warnings(rep)},
        "checks": [
            {
                "name": r.check.name,
                "type": r.check.type,
                "params": r.check.params,
                "passed": r.passed,
                "detail": r.detail,
                "attempts": r.attempts,
                "duration_s": r.duration,
                "started": r.started,
                "history": r.history,
                "evidence": r.evidence,
                "warnings": r.warnings,
            }
            for r in rep.results
        ],
    }
    return json.dumps(data, indent=2)


def _md_text(text: str) -> str:
    """Text from a config, a topology or device output, made inert for a PR comment: no HTML (which
    could hide the rest of the comment), no links or images, and no @mentions or #references that
    would notify people or link other issues."""
    t = str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    t = t.replace("[", "\\[").replace("]", "\\]")
    return re.sub(r"([@#])(?=\w)", "\\1\u200b", t)


def _md_cell(text: str) -> str:
    return " ".join(_md_text(text).replace("|", "\\|").split())


def _ticks(text: str) -> int:
    """Length of the longest run of backticks in `text`."""
    return max((len(m) for m in re.findall(r"`+", text)), default=0)


def _md_code(text: str) -> str:
    """An inline code span that `text` cannot break out of."""
    t = " ".join(str(text).split())
    fence = "`" * (_ticks(t) + 1)
    return f"{fence} {t} {fence}"


def _md_block(text: str) -> list[str]:
    """A fenced code block that `text` cannot close early."""
    fence = "`" * max(3, _ticks(str(text)) + 1)
    return [fence, str(text), fence]


# Lines that say which route or path the device selected: the proof behind "(not selected)" or "best path".
# They often sit after the window around the prefix (FRR lists the losing BGP route before the selected one).
_PROOF = re.compile(r'"(selected|installed|bestpath|best-route)"\s*:')
_PROOF_CONTEXT = re.compile(r'"(protocol|route-type|routeType)"\s*:')
MAX_PROOF_LINES = 8


def _evidence_excerpt(output: str, params: dict, max_lines: int = 15) -> str:
    """The part of a raw command output a reviewer needs: lines mentioning the prefix or neighbor
    under test (with a little context), else the first lines, plus any later line that shows what the
    device selected (with the protocol it belongs to). Kept short enough to paste in a PR."""
    rows = output.splitlines()
    if len(rows) <= max_lines:
        return "\n".join(rows)
    keys = [str(params[k]) for k in ("prefix", "neighbor", "target") if params.get(k)]
    hits = [i for i, row in enumerate(rows) if any(k in row for k in keys)] if keys else []
    start = max(0, hits[0] - 2) if hits else 0
    end = start + max_lines          # rows[start:end] is the window
    shown = list(range(start, min(end, len(rows))))
    extra: list[int] = []
    for i in range(end, len(rows)):
        if len(extra) >= MAX_PROOF_LINES or not _PROOF.search(rows[i]):
            continue
        ctx = next((j for j in range(i - 1, end - 1, -1) if _PROOF_CONTEXT.search(rows[j])), None)
        for j in (ctx, i):
            if j is not None and j not in extra:
                extra.append(j)
    out, last = [], None
    for i in shown + sorted(extra):
        if last is not None and i != last + 1:
            out.append("...")
        out.append(rows[i])
        last = i
    if last is not None and last < len(rows) - 1:
        out.append("...")
    return "\n".join(out)


def to_markdown(rep: RunReport) -> str:
    head = {"passed": "✅ Netdryrun passed", "failed": "❌ Netdryrun failed", "error": "⚠️ Netdryrun could not run",
            "inconclusive": "⏸️ Netdryrun inconclusive: the lab never reached a testable state"}[rep.status]
    lines = [f"### {head}", ""]
    if rep.error:
        lines += _md_block(rep.error)
        return "\n".join(lines) + "\n"
    if rep.status == "inconclusive":
        lines += [f"> {_md_cell(rep.inconclusive_reason)}", ">",
                  "> This says nothing about the change, good or bad. Rerun once the lab comes up.", ""]
    warned = [r for r in rep.results if r.warnings]
    if warned:
        lines += [f"> ⚠️ {len(warned)} check(s) ran with a convergence warning (the verdict stands; see below):", ">"]
        lines += [f"> - {_md_cell(r.check.name)}: {_md_cell(w['text'])}" for r in warned[:10] for w in r.warnings[:3]]
        lines += [""]
    lines += [f"**{rep.passed} passed, {rep.failed} failed** on lab {_md_code(rep.lab_name)}", "",
              "| | Check | Result | Time |", "|---|---|---|---|"]
    tail = []
    failures = [r for r in rep.results if not r.passed]
    for r in failures[:5]:
        # every command of the final sample (a route check reads the routing table and the BGP table)
        evs = [ev for ev in r.evidence[-3:] if ev]
        if not evs:
            continue
        tail += ["", f"<details><summary>Evidence: {_md_cell(r.check.name)}</summary>"]
        for ev in evs:
            out = _evidence_excerpt(ev.get("output") or ev.get("stderr") or "", r.check.params)
            tail += ["", _md_code(f"{ev['node']}$ {ev['cmd']}"), "", *_md_block(out)]
        tail += ["", "</details>"]
    env = rep.environment
    tail += ["", f"<sub>netdryrun {_md_cell(env.get('netdryrun', '?'))} · "
             f"containerlab {_md_cell(env.get('containerlab', '?'))} · "
             f"{rep.started} · full evidence in the JSON report</sub>"]
    # A GitHub comment holds at most 65536 characters: a big (recorded) lab can have more rows than
    # that, so the table stops early and says how many it left out. Failures come first, so they stay.
    room = MAX_MARKDOWN - sum(len(x) + 1 for x in lines + tail) - 200
    rows = sorted(rep.results, key=lambda r: r.passed)  # failures first
    for i, r in enumerate(rows):
        row = f"| {'✅' if r.passed else '❌'} | {_md_cell(r.check.name)} | {_md_cell(r.detail)} | {r.duration}s |"
        room -= len(row) + 1
        if room < 0:
            left = rows[i:]
            bad = sum(not x.passed for x in left)
            lines.append(f"| | … {len(left)} more checks ({bad} failed, {len(left) - bad} passed) | "
                         "not shown: too many for one comment; all are in the JSON report | |")
            break
        lines.append(row)
    return "\n".join(lines + tail) + "\n"


def to_junit(rep: RunReport) -> str:
    cases = []
    # inconclusive: the checks could not run meaningfully, which JUnit calls an error, not a failure
    tag = "error" if rep.status == "inconclusive" else "failure"
    for r in rep.results:
        body = "" if r.passed else f"<{tag} message={quoteattr(r.detail)}>{escape(json.dumps(r.evidence, indent=1)[:20000])}</{tag}>"
        cases.append(f'  <testcase classname="netdryrun.{r.check.type}" name={quoteattr(r.check.name)} time="{r.duration}">{body}</testcase>')
    errors = 1 if rep.error else 0
    if rep.error:
        cases.append(f'  <testcase classname="netdryrun" name="lab"><error message={quoteattr(rep.error)}/></testcase>')
    tests = len(rep.results) + errors
    failures = rep.failed
    if tag == "error":
        errors, failures = rep.failed, 0
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<testsuite name="netdryrun" tests="{tests}" failures="{failures}" errors="{errors}">\n'
        + "\n".join(cases) + "\n</testsuite>\n"
    )
