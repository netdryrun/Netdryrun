"""The Atheris fuzzers in fuzz/ (ClusterFuzzLite runs them), checked in the normal suite without Atheris: they import,
every seed runs through them without a finding, and the open findings stay pinned.

The fuzzers' targets and oracles are tests/test_driver_fuzz.py's own, so a parser added there is fuzzed too.
"""
from __future__ import annotations

import contextlib
import importlib
import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
FUZZ = ROOT / "fuzz"


@pytest.fixture(scope="module")
def fuzzers():
    """fuzz_parsers and fuzz_config, imported with a stand-in for atheris (only its import hook is used at import)."""
    stub = types.ModuleType("atheris")
    stub.instrument_imports = lambda **_: contextlib.nullcontext()
    saved = sys.modules.get("atheris")
    sys.modules["atheris"] = stub
    sys.path.insert(0, str(FUZZ))
    try:
        mods = {name: importlib.import_module(name) for name in ("fuzz_parsers", "fuzz_config")}
        yield mods
    finally:
        sys.path.remove(str(FUZZ))
        for name in ("fuzz_parsers", "fuzz_config"):
            sys.modules.pop(name, None)
        if saved is None:
            sys.modules.pop("atheris", None)
        else:
            sys.modules["atheris"] = saved


def test_every_property_test_target_is_fuzzed(fuzzers):
    import test_driver_fuzz as oracle

    names = [n for n, _ in fuzzers["fuzz_parsers"].TARGETS]
    assert names == [c.id for c in oracle.CASES] + [c[0] for c in oracle.FAIL_SAFE]
    assert len(names) >= 40


def test_every_parser_seed_runs_clean(fuzzers):
    fp = fuzzers["fuzz_parsers"]
    seeds = fp.seeds()
    assert len(seeds) >= len(fp.TARGETS)
    for name, data in seeds.items():
        fp.TestOneInput(data)    # an AssertionError or any exception but DriverError is a finding


def test_every_config_seed_runs_clean_and_seeds_reach_the_checks(fuzzers):
    fc = fuzzers["fuzz_config"]
    seeds = fc.seeds()
    assert any("frr-bgp" in n for n in seeds) and any(n.startswith("0.3.0-false-pass") for n in seeds)
    for data in seeds.values():
        fc.TestOneInput(data)


def test_the_config_oracle_catches_a_dropped_key(fuzzers, monkeypatch):
    """The oracle itself must fail when a key is accepted and dropped (a validator bug planted here)."""
    fc = fuzzers["fuzz_config"]
    from netdryrun import config

    real = config._validate_check

    def drops_prefix(i, raw, timeout, prefix="checks"):
        check = real(i, raw, timeout, prefix)
        check.params.pop("prefix", None)
        return check
    monkeypatch.setattr(config, "_validate_check", drops_prefix)
    seed = next(v for k, v in fc.seeds().items() if k == "frr-bgp-netdryrun.yml")
    with pytest.raises(AssertionError, match="dropped"):
        fc.TestOneInput(seed)


# ---- open findings: each stays a strict xfail until fixed, then the marker comes off ---------------------------
FINDINGS = FUZZ / "findings"


@pytest.mark.xfail(strict=True, reason="open fuzz finding 2026-11-01 (reported to the coordinator): the live "
                   "junos_route_leak capture with its BGP rt-entry removed (rt-entry-count still 2, one Static entry "
                   "left) reads as no BGP path, so `present: false` on that path would pass. The oracle also rejects "
                   "real static-only answers (junos_route_static), so the oracle or the parser needs a decision")
def test_finding_junos_bgp_paths_entry_dropped(fuzzers):
    fuzzers["fuzz_parsers"].TestOneInput((FINDINGS / "junos-bgp-paths-entry-dropped.bin").read_bytes())
