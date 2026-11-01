"""Coverage-guided fuzzing (Atheris) of every device-output parser, where a false pass would hide.

  python fuzz/fuzz_parsers.py fuzz/seeds/parsers -max_total_time=60     local run (pip install atheris)

ClusterFuzzLite builds and runs it (.clusterfuzzlite/, .github/workflows/cflite.yml). The input's first byte picks a
target, the rest is the device's output. The targets and their oracles are the property tests' own
(tests/test_driver_fuzz.py), so the fuzzer and the tests can't drift apart:

- CASES: parsers whose empty reading makes a negative check pass. A finding is any exception but DriverError, or
  an empty reading from output that is not a real empty answer.
- FAIL_SAFE: parsers whose result must stay in a safe range (a ping count, a version or nothing). A finding is any
  exception but DriverError, or a result outside that range.

Every finding is a possible false pass or crash: report it, never silence it.
"""
from __future__ import annotations

import sys
from pathlib import Path

import atheris

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tests"))

with atheris.instrument_imports(include=["netdryrun"]):
    import test_driver_fuzz as oracle  # noqa: E402  (the property tests' targets and oracles)


def _targets():
    out = [(c.id, lambda text, c=c: oracle.outcome(c, text)) for c in oracle.CASES]
    out += [(c[0], lambda text, c=c: oracle.fail_safe_outcome(c, text)) for c in oracle.FAIL_SAFE]
    return out


TARGETS = _targets()


def seeds() -> dict[str, bytes]:
    """file name -> seed: each target's own captured fixtures, behind its selector byte."""
    out = {}
    for i, case in enumerate([*oracle.CASES, *oracle.FAIL_SAFE]):
        fixtures = case.fixtures if hasattr(case, "fixtures") else case[2]
        for name in fixtures:
            out[f"{i:03d}-{name}"] = bytes([i]) + oracle.read(name).encode("utf-8")
    return out


def TestOneInput(data: bytes) -> None:
    if not data:
        return
    _name, run = TARGETS[data[0] % len(TARGETS)]
    run(data[1:].decode("utf-8", "replace"))


def main() -> None:
    atheris.Setup(sys.argv, TestOneInput)
    atheris.Fuzz()


if __name__ == "__main__":
    main()
