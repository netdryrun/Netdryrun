"""Verdict Corpus v2 case 18 follows an FRR import-check race in the lab (0.3.3 release gate, 2026-10-29: the same
build gave unsafe, unsafe, safe). It is listed in corpus/v2/NONDETERMINISTIC.yml, left out of every score and shown
with every verdict seen; the case file and its expected verdict are unchanged."""
import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


render = _load("corpus_render", ROOT / "corpus" / "render.py")
sync_facts = _load("sync_facts", ROOT / "scripts" / "sync_facts.py")
V2 = ROOT / "corpus" / "v2"
CASE = "18-aggregate-discard-route-removed"


def test_the_v2_score_leaves_out_the_nondeterministic_case():
    data = json.loads((V2 / "results" / "results.json").read_text(encoding="utf-8"))
    st = render.stats(data["cases"], render.nondeterministic(V2))
    assert (st["total"], st["unsafe"], st["netdryrun"]["correct"], st["ping"]["correct"], st["sessions"]["correct"]) \
        == (17, 10, 16, 9, 7)
    assert render.stats(data["cases"])["total"] == 18   # nothing is hidden from the data itself


def test_the_v2_results_page_lists_case_18_with_its_verdicts_and_scores_16_of_17():
    data = json.loads((V2 / "results" / "results.json").read_text(encoding="utf-8"))
    md = render.results_markdown(data, corpus=V2, amendments=V2 / "AMENDMENTS.md")
    assert "## Summary (17 deterministic cases: 10 harmful, 7 safe; 1 nondeterministic, not scored)" in md
    assert "| Netdryrun intent checks | **16/17** |" in md
    row = next(line for line in md.splitlines() if line.startswith(f"| `{CASE}`"))
    assert "🎲 not scored" in row and "✅" not in row
    section = md.split("## Nondeterministic cases (not scored)")[1].split("## Netdryrun's losses")[0]
    assert CASE in section and section.count("**unsafe**") == 3 and section.count("**safe**") == 3
    losses = md.split("## Netdryrun's losses")[1].split("## Findings after the run")[0]
    assert CASE not in losses


def test_the_status_lines_say_16_of_17_and_name_case_18():
    f = sync_facts.facts()
    c2 = f["corpus_v2"]
    assert (c2["cases"], c2["netdryrun"], c2["nondeterministic"]) == (17, 16, [18])
    b = sync_facts.blocks(f)
    for name in ("readme_status", "site_status"):
        assert ("Netdryrun 16 of 17 deterministic cases correct, ping-only 9/17, all-sessions-up 7/17; case 18 is "
                "nondeterministic in this lab and excluded from the score (listed with its reruns)") in b[name], name
        assert "17/18" not in b[name] and "On v2 (18 cases" in b[name]
    assert "v2: **16 of 17** deterministic cases" in b["built_accuracy"] and "17/18" not in b["built_accuracy"]
