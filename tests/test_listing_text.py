"""The text registries show and search: the MCP Registry description (server.json, 100 characters at most)
and the PyPI summary, which starts with the same sentence so both are found by the same search words."""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORDS = ("BGP", "routing", "containerlab", "verdict")


def test_the_registry_description_is_short_and_searchable():
    d = json.loads((ROOT / "server.json").read_text(encoding="utf-8"))["description"]
    assert len(d) <= 100, len(d)
    assert all(w in d for w in WORDS), d


def test_the_pypi_summary_starts_with_the_registry_description():
    d = json.loads((ROOT / "server.json").read_text(encoding="utf-8"))["description"]
    summary = re.search(r'^description = "(.*)"$', (ROOT / "pyproject.toml").read_text(encoding="utf-8"), re.M).group(1)
    assert summary.startswith(d), summary
