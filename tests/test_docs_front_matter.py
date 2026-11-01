"""Every docs page's front matter must parse as a YAML mapping.

MkDocs prints front matter it can't parse as body text: an unquoted ': ' in a description
put the raw title and description above the H1 of guides/agent-pr (2026-10-30).
"""
from pathlib import Path

import pytest
import yaml

DOCS = Path(__file__).resolve().parent.parent / "website" / "docs"
PAGES = sorted(p for p in DOCS.rglob("*.md") if p.read_text(encoding="utf-8").startswith("---\n"))


@pytest.mark.parametrize("page", PAGES, ids=lambda p: p.relative_to(DOCS).as_posix())
def test_front_matter_is_a_yaml_mapping(page):
    text = page.read_text(encoding="utf-8")
    end = text.index("\n---", 4)
    meta = yaml.safe_load(text[4:end])
    assert isinstance(meta, dict), "front matter must be a mapping"
    assert meta.get("title") and meta.get("description"), "every page needs a title and a description"
