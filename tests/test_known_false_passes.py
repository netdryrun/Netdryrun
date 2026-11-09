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
    records = [e["record"] for e in ENTRIES]
    for d in sorted((ROOT / "advisories").iterdir()):
        if d.is_dir():
            # the record names the advisory first; an accepted limit also names the trust page after it
            own = f"advisories/{d.name}/README.md"
            assert any(r == own or r.startswith(own + ",") for r in records), f"advisories/{d.name} has no entry"


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


def test_an_accepted_limit_is_published_and_pinned():
    """A false pass the owner accepted as a documented limit (2026-11-08) carries its status and decision, and is
    pinned by the red-team corpus's accepted-limit test, which checks every place it is published."""
    statuses = {e.get("status", "fixed") for e in ENTRIES}
    assert statuses <= {"fixed", "accepted-documented-limit"}, statuses
    accepted_cases = set()
    for e in ENTRIES:
        if e.get("status") == "accepted-documented-limit":
            assert e.get("decided"), e["id"]
            assert "trust.md" in e["record"], e["id"]
            if e.get("oracle_spec"):
                # a limit no red-team driver case can hold (a whole command, e.g. record): it is pinned by an oracle
                # spec until the oracle lands (tests/oracles/<ID>/), and then by the oracle itself
                assert not e.get("cases") and (ROOT / e["oracle_spec"]).is_file(), e["id"]
                assert e.get("tests"), e["id"]
                continue
            assert e.get("cases"), e["id"]
            accepted_cases |= set(e["cases"])
            assert "tests/test_redteam.py::test_accepted_limits_are_published_and_still_behave_as_documented" in e["tests"]
    # every red-team case marked accepted_limit is exactly one an accepted entry names, and the set is pinned: a
    # second accepted limit needs this line changed in review (code review of the limit, MAJOR 1)
    import yaml as _yaml
    marked = {_yaml.safe_load(p.read_text(encoding="utf-8"))["id"] for p in (ROOT / "tests" / "redteam").glob("RT-*.yml")
              if _yaml.safe_load(p.read_text(encoding="utf-8")).get("accepted_limit")}
    assert marked == accepted_cases == {"RT-0048", "RT-0053", "RT-0056", "RT-0058", "RT-0063"}, (marked, accepted_cases)
