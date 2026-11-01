"""tests/known_false_passes.yml lists every false pass Netdryrun is known to have had, and every test it names exists.

The contributor CI runs those tests from the base branch against a pull request's code, so this list is what a
pull request can't break. A new advisory, a new row on the trust page or a new corpus loss must be added to it.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
ENTRIES = yaml.safe_load((ROOT / "tests" / "known_false_passes.yml").read_text(encoding="utf-8"))
TRUST = (ROOT / "website" / "docs" / "trust.md").read_text(encoding="utf-8")


def _advisory_rows() -> list[str]:
    table = TRUST.split("| Version | What could pass wrongly | Status |", 1)[1].split("\n\n", 1)[0]
    return [ln.split("|")[1].strip() for ln in table.strip().splitlines()[1:]]


def test_ids_are_unique_and_every_entry_is_covered_by_something():
    ids = [e["id"] for e in ENTRIES]
    assert len(ids) == len(set(ids))
    for e in ENTRIES:
        assert e.get("what") and e.get("record"), e["id"]
        assert e.get("tests") or e.get("corpus"), f"{e['id']}: names no test and no corpus case"


def test_every_advisory_is_listed():
    records = {e["record"] for e in ENTRIES}
    for d in sorted((ROOT / "advisories").iterdir()):
        if d.is_dir():
            assert f"advisories/{d.name}/README.md" in records, f"advisories/{d.name} has no entry"


def test_every_row_of_the_trust_page_advisories_table_is_listed():
    rows = _advisory_rows()
    assert len(rows) >= 4
    listed = [e.get("trust") for e in ENTRIES if e.get("trust")]
    assert sorted(rows) == sorted(listed), "each row of the advisories table needs exactly one entry with its Version"


@pytest.mark.parametrize("target", sorted({t for e in ENTRIES for t in e.get("tests") or []}))
def test_every_named_test_exists(target):
    path, _, name = target.partition("::")
    p = ROOT / path
    assert p.is_file(), f"{path} doesn't exist"
    if name:
        names = {n.name for n in ast.walk(ast.parse(p.read_text(encoding="utf-8"))) if isinstance(n, ast.FunctionDef)}
        assert name in names, f"{target}: no such test"


@pytest.mark.parametrize("case", sorted({c for e in ENTRIES for c in e.get("corpus") or []}))
def test_every_named_corpus_case_exists(case):
    version, _, stem = case.partition("/")
    base = ROOT / "corpus" if version == "v1" else ROOT / "corpus" / version
    assert (base / "cases" / f"{stem}.yml").is_file(), case


def test_every_red_team_case_is_run():
    # every RT case file is a known false pass too: test_redteam.py (listed above) runs them all
    assert any("tests/test_redteam.py" in (e.get("tests") or []) for e in ENTRIES)
    assert len(list((ROOT / "tests" / "redteam").glob("RT-*.yml"))) >= 9
    assert re.search(r"glob\(\"RT-\*", (ROOT / "tests" / "test_redteam.py").read_text(encoding="utf-8"))
