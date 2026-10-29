"""Compare fresh live captures (scripts/capture_fixtures.sh) with the committed fixtures by shape.

  python3 scripts/fixture_shape.py [DIR]       DIR defaults to tests/fixtures

DIR/<name> files replace a committed fixture of the same scenario: any change in shape is drift (exit 1).
DIR/shape/<name> files come from a smaller lab than the committed fixture: keys the fixture has and the capture
lacks are the scenario, keys the capture has and the fixture lacks are the NOS growing something (drift).

Shape of JSON = the set of key paths, with address- and prefix-valued keys written `*`, lists merged.
Shape of text (ping) = the lines with digits written N, as a set.
"""
from __future__ import annotations

import ipaddress
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _wild(key: str) -> str:
    base = key.split("%")[0]
    for parse in (ipaddress.ip_address, ipaddress.ip_network):
        try:
            parse(base)
            return "*"
        except ValueError:
            pass
    return "*" if re.fullmatch(r"[0-9]+", key) else key


def _paths(node, prefix: str, out: set[str]) -> None:
    if isinstance(node, dict):
        for k, v in node.items():
            p = f"{prefix}/{_wild(str(k))}"
            out.add(p)
            _paths(v, p, out)
    elif isinstance(node, list):
        for v in node:
            _paths(v, prefix + "[]", out)
    else:
        out.add(f"{prefix}:{type(node).__name__}")


def shape(text: str) -> set[str]:
    try:
        out: set[str] = set()
        _paths(json.loads(text), "", out)
        return out
    except ValueError:
        return {re.sub(r"[0-9]+(\.[0-9]+)*", "N", line.strip()) for line in text.splitlines() if line.strip()}


def committed_text(name: str, in_place: bool) -> str | None:
    """The committed fixture; when the capture was written over it, git's copy."""
    if in_place:
        r = subprocess.run(["git", "show", f"HEAD:tests/fixtures/{name}"], cwd=ROOT, capture_output=True, text=True,
                           encoding="utf-8")
        return r.stdout if r.returncode == 0 else None
    path = ROOT / "tests" / "fixtures" / name
    return path.read_text(encoding="utf-8") if path.exists() else None


def main(argv: list[str]) -> int:
    out_dir = Path(argv[0]) if argv else ROOT / "tests" / "fixtures"
    in_place = out_dir.resolve() == (ROOT / "tests" / "fixtures").resolve()
    drift = 0
    for same_scenario, folder in ((True, out_dir), (False, out_dir / "shape")):
        kind = "same scenario" if same_scenario else "smaller lab"
        for fresh in sorted(folder.glob("*.txt")):
            old = committed_text(fresh.name, in_place and same_scenario)
            if old is None:
                print(f"NEW      {fresh.name}: no committed fixture to compare ({kind})")
                continue
            a, b = shape(fresh.read_text(encoding="utf-8")), shape(old)
            added, removed = a - b, b - a
            bad = (added | removed) if same_scenario else added
            drift += bool(bad)
            print(f"{'DRIFT   ' if bad else 'same    '} {fresh.name} ({kind})")
            for k in sorted(added):
                print(f"           + {k}   (in the fresh capture only)")
            for k in sorted(removed):
                print(f"           - {k}   ({'in the committed fixture only' if same_scenario else 'the committed fixture is a richer scenario'})")
    print(f"shape drift in {drift} file(s)")
    return 1 if drift else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
