"""Write each fuzzer's seed corpus from the repository's own captures and configs.

  python fuzz/seeds.py OUT_DIR          writes OUT_DIR/parsers/* and OUT_DIR/config/*

Imports the fuzzers only for their seeds() functions; atheris must be installed.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import fuzz_config  # noqa: E402
import fuzz_parsers  # noqa: E402


def main(out: Path) -> None:
    for name, mod in (("parsers", fuzz_parsers), ("config", fuzz_config)):
        d = out / name
        d.mkdir(parents=True, exist_ok=True)
        for fname, data in mod.seeds().items():
            (d / fname).write_bytes(data)
        print(f"{d}: {len(list(d.iterdir()))} seeds")


if __name__ == "__main__":
    main(Path(sys.argv[1] if len(sys.argv) > 1 else "fuzz/seeds"))
