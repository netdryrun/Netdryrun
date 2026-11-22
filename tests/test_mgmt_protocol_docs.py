"""The protocols whose routes over Docker's default may settle away are listed in the config reference and the
changelog; both lists must name exactly the protocols the code accepts (a review found ripng missing from the docs)."""
import re
from pathlib import Path

from netdryrun import mgmt

ROOT = Path(__file__).resolve().parent.parent
NAMES = {p for p in mgmt._PROTOCOL if not p.isdigit()}


def _listed(text: str) -> set[str]:
    m = re.search(r"\((bgp, ospf, [a-z, ]+?)(?:,\s*one path|\))", text.replace("\n", " ").replace("  ", " "))
    assert m, "protocol list not found"
    return {w.strip() for w in re.split(r",|\bor\b", m.group(1)) if w.strip()}


def test_config_reference_lists_exactly_the_accepted_protocols():
    assert _listed((ROOT / "website" / "docs" / "reference" / "config.md").read_text(encoding="utf-8")) == NAMES


def test_changelog_lists_exactly_the_accepted_protocols():
    text = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    entry = text[text.index("A routing protocol's route over Docker"):]
    assert _listed(entry[:2000]) == NAMES
