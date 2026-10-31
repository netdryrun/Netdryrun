"""Render corpus/results/results.json into corpus/RESULTS.md, the website's corpus page and one page per case.

Usage: python corpus/render.py              # v1 (frozen): RESULTS.md, the corpus page's v1 results, case pages
       python corpus/render.py --corpus v2  # v2: corpus/v2/RESULTS.md and the corpus page's v2 section
Also prints the launch numbers ({{x}}, {{fp_ping}}, ...) used in the announcement drafts.
"""
from __future__ import annotations

import argparse
import difflib
import json
import re
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
SITE_PAGE = HERE.parent / "website" / "docs" / "corpus.md"
CASE_DIR = HERE.parent / "website" / "docs" / "corpus"   # one page per case: website/docs/corpus/<id>.md
REPO = "https://github.com/netdryrun/Netdryrun"
SPECS = {"ping": "baseline-ping.yml", "sessions": "baseline-sessions.yml", "netdryrun": "intent.yml"}
LABELS = {"ping": "Ping only", "sessions": "All BGP sessions up", "netdryrun": "Netdryrun intent checks"}
MARK = {"correct": "✅", "false pass": "❌ approved a bad change", "false block": "⚠️ blocked a good change", "error": "💥 error"}

# Post-run findings, appended without touching the pre-registered expected verdicts.
AMENDMENTS = HERE / "AMENDMENTS.md"

V2 = HERE / "v2"
V2_MARKER = "<!-- CORPUS-V2 -->"   # the corpus page's v2 section starts here; v1 rendering keeps it intact


def outcome(expected: str, verdict: str) -> str:
    if verdict == "error":
        return "error"
    if verdict == expected:
        return "correct"
    return "false pass" if expected == "unsafe" else "false block"


def nondeterministic(corpus: Path = HERE) -> dict:
    """Cases marked in NONDETERMINISTIC.yml after the run: their verdict follows a race in the lab. Not scored."""
    path = corpus / "NONDETERMINISTIC.yml"
    return (yaml.safe_load(path.read_text(encoding="utf-8")) or {}) if path.exists() else {}


def stats(rows: list[dict], skip=()) -> dict:
    """Scores over the deterministic cases: the IDs in `skip` (nondeterministic) are left out."""
    out = {}
    rows = [r for r in rows if r["id"] not in skip]
    unsafe = [r for r in rows if r["expected"] == "unsafe"]
    for s in LABELS:
        oc = [outcome(r["expected"], r["strategies"][s]["verdict"]) for r in rows]
        out[s] = {
            "correct": oc.count("correct"), "false_pass": oc.count("false pass"),
            "false_block": oc.count("false block"), "error": oc.count("error"),
            "caught": sum(1 for r in unsafe if r["strategies"][s]["verdict"] == "unsafe"),
        }
    out["total"], out["unsafe"], out["safe"] = len(rows), len(unsafe), len(rows) - len(unsafe)
    return out


def results_markdown(data: dict, link=None, h: str = "##", corpus: Path = HERE, amendments: Path = AMENDMENTS) -> str:
    rows, env = data["cases"], data["environment"]
    nd = nondeterministic(corpus)
    st = stats(rows, nd)
    rel = corpus.relative_to(HERE.parent).as_posix()
    lines = [
        f"Generated {env['generated']} with netdryrun {env['netdryrun']}, containerlab {env['containerlab']}, "
        f"FRR {env['frr_image']}, commit `{env.get('commit', '?')}`. Rerun everything with `python corpus/run.py{env.get('rerun_args', '')}`.", "",
        "**Conflict of interest:** the Netdryrun maintainers wrote this corpus and the runner. Expected verdicts were "
        f"committed before any run (see the git history of `{rel}/cases/`). Losses are kept and shown at the same size as the catches.", "",
        (f"{h} Summary ({st['total']} deterministic cases: {st['unsafe']} harmful, {st['safe']} safe; "
         f"{len(nd)} nondeterministic, not scored)" if nd else
         f"{h} Summary ({st['total']} cases: {st['unsafe']} harmful, {st['safe']} safe)"), "",
        "| Strategy | Correct | Harmful changes caught | Approved a bad change | Blocked a good change | Errors |",
        "|---|---|---|---|---|---|",
    ]
    for s, label in LABELS.items():
        x = st[s]
        lines.append(f"| {label} | **{x['correct']}/{st['total']}** | {x['caught']}/{st['unsafe']} | {x['false_pass']} | {x['false_block']} | {x['error']} |")
    lines += ["", f"{h} Every case", "", "| Case | Category | Expected | Ping only | Sessions up | Netdryrun | What Netdryrun flagged |",
              "|---|---|---|---|---|---|---|"]
    for r in rows:
        cells = [MARK[outcome(r["expected"], r["strategies"][s]["verdict"])] for s in LABELS]
        flagged = "; ".join(r["strategies"]["netdryrun"]["failed_checks"]) or "nothing"
        if r["id"] in nd:
            cells = ["🎲 not scored"] * len(LABELS)
            flagged = "nondeterministic in this lab: see below"
        name = f"[{r['title']}]({link(r['id'])})" if link else r["title"]
        lines.append(f"| `{r['id']}` {name} | {r['category']} | {r['expected']} | {' | '.join(cells)} | {flagged} |")
    losses = [r for r in rows if r["id"] not in nd
              and outcome(r["expected"], r["strategies"]["netdryrun"]["verdict"]) != "correct"]
    if nd:
        lines += ["", f"{h} Nondeterministic cases (not scored)", "",
                  "Same build, same machine, same case, different verdicts: the verdict follows a race in the lab, not "
                  "the change. These cases are left out of every score above and listed here with every Netdryrun "
                  f"verdict seen. The case files and expected verdicts are unchanged; the list is in `{rel}/NONDETERMINISTIC.yml`.", ""]
        for cid, x in nd.items():
            row = next((r for r in rows if r["id"] == cid), {"title": cid, "expected": "?"})
            seen = "; ".join(f"{v['when']}, {v['run']}: **{v['verdict']}**" for v in x["netdryrun_verdicts"])
            lines.append(f"- **`{cid}` {row['title']}** (expected {row['expected']}). {x['why'].strip()} "
                         f"Netdryrun verdicts: {seen}.")
    lines += ["", f"{h} Netdryrun's losses", ""]
    if not losses:
        lines.append("None in this run.")
    for r in losses:
        oc = outcome(r["expected"], r["strategies"]["netdryrun"]["verdict"])
        lines.append(f"- **`{r['id']}` {r['title']}** ({oc}). {r.get('note') or r['rationale']}")
    if amendments.exists():
        lines += ["", f"{h} Findings after the run", "", amendments.read_text(encoding="utf-8").strip()]
    return "\n".join(lines) + "\n"


def case_number(case_id: str) -> int:
    return int(case_id.split("-", 1)[0])


def amendments_for(case_id: str) -> list[str]:
    """Paragraphs of AMENDMENTS.md whose bold lead names this case ("**Case 12 ..." or "**Cases 18, 23 ...")."""
    if not AMENDMENTS.exists():
        return []
    out = []
    for para in AMENDMENTS.read_text(encoding="utf-8").strip().split("\n\n"):
        lead = re.match(r"\*\*Cases? ([\d, and]+)", para)
        if lead and case_number(case_id) in {int(n) for n in re.findall(r"\d+", lead.group(1))}:
            out.append(para)
    return out


def edit_diff(edits: list[dict]) -> str:
    """Unified diff of the base configs against the edited ones. Applies edits exactly like run.py's build_workdir."""
    base, edited = {}, {}
    for edit in edits:
        node = edit["node"]
        if node not in base:
            base[node] = edited[node] = (HERE / "base" / "configs" / f"{node}.conf").read_text(encoding="utf-8")
        if "replace" in edit:
            edited[node] = edited[node].replace(edit["replace"], edit.get("with", ""))
        else:
            edited[node] = edited[node].rstrip("\n") + "\n" + edit["append"].rstrip("\n") + "\n!\n"
    chunks = []
    for node in base:
        chunks += difflib.unified_diff(base[node].splitlines(keepends=True), edited[node].splitlines(keepends=True),
                                       f"a/{node}.conf", f"b/{node}.conf", n=3)
    return "".join(chunks)


def describe_check(check: dict) -> str:
    """One plain sentence for a check in a strategy spec."""
    t = check["type"]
    if t == "bgp_session":
        return f"the BGP session from {check['node']} to {check['neighbor']} is established"
    if t == "ping":
        return f"{check['node']} can ping {check['target']} from {check['source']}"
    if t == "route":
        state = "must not be" if check.get("present") is False else "must be"
        return f"{check['prefix']} {state} in {check['node']}'s routing table as a {check.get('protocol', 'any')} route"
    if t == "bgp_prefixes":
        n = check["min"] if check.get("min") == check.get("max") else f"{check.get('min', 0)} to {check.get('max', 'any')}"
        return f"{check['node']} receives exactly {n} prefixes from {check['neighbor']}"
    return t


def load_checks() -> dict[str, dict[str, str]]:
    out = {}
    for s, spec in SPECS.items():
        checks = yaml.safe_load((HERE / "specs" / spec).read_text(encoding="utf-8"))["checks"]
        out[s] = {c["name"]: describe_check(c) for c in checks}
    return out


def meta_description(r: dict) -> str:
    text = f"{r['title']}. Expected {r['expected']}: {r['rationale']}"
    text = " ".join(text.replace('"', "'").replace("`", "").split())
    if len(text) > 160:
        text = text[:157].rsplit(" ", 1)[0].rstrip(".,:;") + "..."
    return text


def case_page(r: dict, env: dict, checks: dict) -> str:
    n = case_number(r["id"])
    verb = "an experienced operator would approve it" if r["expected"] == "safe" else "an experienced operator would reject it"
    title = f"{r['title']}: BGP change test (case {n})".replace('"', "'").replace("`", "")
    lines = [
        "---",
        f'title: "{title}"',
        f'description: "{meta_description(r)}"',
        "---",
        "",
        f"# {r['title']}",
        "",
        f"Case {n} of the [Network Change Verdict Corpus](../corpus.md). Category: **{r['category']}**. "
        f"Expected verdict: **{r['expected']}** ({verb}).",
        "",
        f"## Why it is expected {r['expected']}",
        "",
        r["rationale"],
    ]
    if r.get("note"):
        lines += ["", f"Note: {r['note']}"]
    if r.get("source"):
        lines += ["", f"Source: {r['source']}"]
    lines += ["", "## The config change", ""]
    diff = edit_diff(r["edits"])
    if diff:
        lines += [f"Against the FRR configs of the [base lab]({REPO}/tree/main/corpus/base/configs):", "",
                  "```diff", diff.rstrip("\n"), "```"]
    else:
        lines.append("None: the base lab runs unchanged.")
    lines += ["", "## What each strategy said", "",
              "The expected verdict was committed to git before any run. All three strategies tested the same running lab "
              "([method](../corpus.md#method)).", "",
              "| Strategy | Verdict | Result | Checks that failed |", "|---|---|---|---|"]
    for s, label in LABELS.items():
        st = r["strategies"][s]
        failed = ", ".join(st["failed_checks"]) or "none"
        if st.get("error"):
            failed += f" (error: {st['error']})"
        lines.append(f"| {label} | {st['verdict']} | {MARK[outcome(r['expected'], st['verdict'])]} | {failed} |")
    nd = r["strategies"]["netdryrun"]
    spec = f"[intent spec]({REPO}/blob/main/corpus/specs/intent.yml)"
    lines += ["", "## What Netdryrun flagged", ""]
    if nd["failed_checks"]:
        lines += [f"These checks from the {spec} failed:", ""]
        lines += [f"- **{c}**: {checks['netdryrun'][c]}" for c in nd["failed_checks"]]
    else:
        lines.append(f"Nothing: every check in the {spec} passed, so Netdryrun called the change safe.")
    oc = outcome(r["expected"], nd["verdict"])
    if oc != "correct":
        lines += ["", f"Against the pre-registered verdict this counts as one of Netdryrun's losses ({oc})."]
    found = amendments_for(r["id"])
    if found:
        lines += ["", "## Finding after the run", "",
                  f"The pre-registered verdict above is unchanged. From [AMENDMENTS.md]({REPO}/blob/main/corpus/AMENDMENTS.md):", ""]
        for para in found:
            lines += [para.replace("`scripts/corpus_case12_verify.sh`",
                                   f"[`scripts/corpus_case12_verify.sh`]({REPO}/blob/main/scripts/corpus_case12_verify.sh)"), ""]
        lines.pop()
    lines += ["", "## Reproduce it", "",
              "On Linux or WSL2 with Docker and containerlab, from a checkout of the repository:", "",
              "```bash", f"python corpus/run.py --case {r['id'][:2]}", "```", "",
              f"Case file: [`corpus/cases/{r['id']}.yml`]({REPO}/blob/main/corpus/cases/{r['id']}.yml). "
              f"Published result: netdryrun {env['netdryrun']}, containerlab {env['containerlab']}, "
              f"FRR `{env['frr_image']}`, commit `{env.get('commit', '?')}`, run on {env['generated'][:10]}."]
    return "\n".join(lines) + "\n"


def write_case_pages(data: dict) -> int:
    CASE_DIR.mkdir(exist_ok=True)
    checks = load_checks()
    wanted = {f"{r['id']}.md" for r in data["cases"]}
    for old in CASE_DIR.glob("*.md"):
        if old.name not in wanted:
            old.unlink()
    for r in data["cases"]:
        (CASE_DIR / f"{r['id']}.md").write_text(case_page(r, data["environment"], checks), encoding="utf-8", newline="\n")
    return len(wanted)


def render_v2() -> None:
    """corpus/v2/RESULTS.md plus the v2 section of the corpus page (everything after V2_MARKER)."""
    data = json.loads((V2 / "results" / "results.json").read_text(encoding="utf-8"))
    amend = V2 / "AMENDMENTS.md"
    (V2 / "RESULTS.md").write_text("# Verdict Corpus v2 results\n\n"
                                   + results_markdown(data, lambda i: f"cases/{i}.yml", corpus=V2, amendments=amend),
                                   encoding="utf-8", newline="\n")
    intro = (V2 / "SITE.md").read_text(encoding="utf-8").strip()
    body = results_markdown(data, lambda i: f"{REPO}/blob/main/corpus/v2/cases/{i}.yml", h="###", corpus=V2, amendments=amend)
    body = body.replace("`corpus/v2/cases/`", f"[`corpus/v2/cases/`]({REPO}/tree/main/corpus/v2/cases)")
    head = SITE_PAGE.read_text(encoding="utf-8").split(V2_MARKER)[0].rstrip("\n")
    SITE_PAGE.write_text(head + "\n\n" + V2_MARKER + "\n\n" + intro + "\n\n" + body, encoding="utf-8", newline="\n")
    st = stats(data["cases"], nondeterministic(V2))
    print(f"wrote corpus/v2/RESULTS.md and the v2 section of {SITE_PAGE.name}")
    print(json.dumps({s: st[s] for s in LABELS} | {"total": st["total"], "unsafe": st["unsafe"]}, indent=1))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", choices=["v1", "v2"], default="v1")
    if ap.parse_args().corpus == "v2":
        return render_v2()
    data = json.loads((HERE / "results" / "results.json").read_text(encoding="utf-8"))
    (HERE / "RESULTS.md").write_text("# Verdict Corpus results\n\n" + results_markdown(data, lambda i: f"cases/{i}.yml"),
                                     encoding="utf-8", newline="\n")
    body = results_markdown(data, lambda i: f"corpus/{i}.md")
    page = SITE_PAGE.read_text(encoding="utf-8")
    marker = "<!-- RESULTS -->"
    head = page.split(marker)[0]
    tail = "\n" + V2_MARKER + page.split(V2_MARKER, 1)[1] if V2_MARKER in page else ""
    SITE_PAGE.write_text(head + marker + "\n\n" + body.replace("`corpus/cases/`", "[`corpus/cases/`](https://github.com/netdryrun/Netdryrun/tree/main/corpus/cases)") + tail, encoding="utf-8", newline="\n")
    print(f"wrote {write_case_pages(data)} case pages to {CASE_DIR}")
    st = stats(data["cases"])
    print(json.dumps({
        "30": st["total"], "unsafe": st["unsafe"],
        "x": st["ping"]["correct"], "y": st["sessions"]["correct"], "z": st["netdryrun"]["correct"],
        "fp_ping": st["ping"]["false_pass"], "fp_sessions": st["sessions"]["false_pass"],
        "caught": st["netdryrun"]["caught"],
    }, indent=1))


if __name__ == "__main__":
    main()
