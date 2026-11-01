"""Coverage-guided fuzzing (Atheris) of the netdryrun.yml loader: the 0.3.0 false-pass class.

  python fuzz/fuzz_config.py fuzz/seeds/config -max_total_time=60     local run (pip install atheris)

The 0.3.0 advisory was a check that passed without testing what the file said: a key misspelled or a value of the
wrong type, accepted and then ignored. The target is runner.load_config, the loader every entry point uses (CLI, MCP,
Action): it turns every failure into a ConfigError, so a crash there can only end a run as an error, never a pass.
A finding is an accepted check (top level or in a scenario) that doesn't say what the file said:
- its file entry has a key the parsed check doesn't keep (let through, then dropped);
- `present` is anything but a real boolean (a quoted "false" read as true is advisory 0.3.0 #2).
Anything but a ConfigError escaping load_config is a finding too.
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import atheris

with atheris.instrument_imports(include=["netdryrun"]):
    from netdryrun import config
    from netdryrun.runner import load_config

LAB = Path(tempfile.mkdtemp(prefix="ndr-fuzz-config-"))
(LAB / "lab.clab.yml").write_text("name: fuzz\ntopology:\n  nodes:\n    r1: {kind: linux, image: frr:10}\n",
                                  encoding="utf-8")
CFG = LAB / "netdryrun.yml"


def _dropped(raw, check) -> set:
    return set(raw) - set(config.COMMON_KEYS) - set(check.params) if isinstance(raw, dict) else set()


def TestOneInput(data: bytes) -> None:
    text = data.decode("utf-8", "replace")
    CFG.write_text(text, encoding="utf-8")
    try:
        cfg = load_config(CFG)
    except config.ConfigError:
        return
    raw = config.load_yaml(text)
    pairs = list(zip(raw.get("checks") or [], cfg.checks))
    for sc_raw, sc in zip(raw.get("scenarios") or [], cfg.scenarios):
        pairs += list(zip(sc_raw.get("checks") or [], sc.checks))
    for raw_check, check in pairs:
        dropped = _dropped(raw_check, check)
        assert not dropped, f"check {check.name!r} accepted with {sorted(dropped)} and dropped them"
        if "present" in check.params:
            assert isinstance(check.params["present"], bool), f"check {check.name!r}: present is {check.params['present']!r}"


def seeds() -> dict[str, bytes]:
    """file name -> seed: every shipped netdryrun.yml, the 0.3.0 advisory's files, pointed at the fuzz lab."""
    root = Path(__file__).resolve().parent.parent
    out = {}
    for p in sorted([*root.glob("examples/*/netdryrun.yml"), *root.glob("advisories/0.3.0-false-pass/*.yml")]):
        lines = p.read_text(encoding="utf-8").splitlines()
        text = "\n".join("lab: lab.clab.yml" if ln.startswith("lab:") else ln for ln in lines) + "\n"
        out[f"{p.parent.name}-{p.name}"] = text.encode("utf-8")
    return out


def main() -> None:
    atheris.Setup(sys.argv, TestOneInput)
    atheris.Fuzz()


if __name__ == "__main__":
    main()
