#!/usr/bin/env python3
"""Write the compatibility page as it would render with every registered driver released, to docs/compat-draft-0.4.1.md.

The published page (website/docs/reference/compatibility.md) leaves out drivers in sync_facts.UNRELEASED; this renders the
same page with that set emptied, so the release can see what it will say before the switch. Nothing public changes.
  python scripts/compat_draft.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "tests"), str(ROOT / "src")]
import compat_matrix  # noqa: E402
import sync_facts  # noqa: E402

withheld = sorted(sync_facts.UNRELEASED)
sync_facts.UNRELEASED = set()
page = compat_matrix.render()
header = (f"<!-- DRAFT, unpublished. The compatibility page as it would render with every driver on this branch released "
          f"({', '.join(withheld)}).\nRegenerate: python scripts/compat_draft.py. The published page "
          f"website/docs/reference/compatibility.md is unchanged until the release that ships them. -->\n")
out = ROOT / "docs" / "compat-draft-0.4.1.md"
out.write_text(header + page, encoding="utf-8", newline="\n")
print(f"wrote {out.relative_to(ROOT)} ({len(page.splitlines())} lines; withheld on the public page: {', '.join(withheld)})")
