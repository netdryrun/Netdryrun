"""Guards for oracle FP-042-ADDRLOAD: they pass before and after its fix.

The fast-fix gate runs tests/oracles/FP-042-ADDRLOAD/ and needs every test there to fail on the fix's parent, so the
guards live here, in the unit suite. This file is in the oracle's `evidence:`, so the fix can't change it.
Helpers and the captured data come from the oracle's own module (tests/oracles/FP-042-ADDRLOAD/).
"""
import importlib.util
import hashlib
from pathlib import Path

import pytest

from netdryrun.drivers.base import DriverError

_PATH = Path(__file__).resolve().parent / "oracles" / "FP-042-ADDRLOAD" / "test_oracle_fp_042_addrload.py"
_SPEC = importlib.util.spec_from_file_location("oracle_fp_042_addrload", _PATH)
o = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(o)


def test_the_crash_input_is_the_fuzzers():
    data = o.CRASH.read_bytes()
    assert hashlib.sha1(data).hexdigest() == o.CRASH.name.removeprefix("crash-")
    assert data[0] == 0x0A and data[1:].decode("utf-8", "replace").startswith("FFFFFFFFF{")


@pytest.mark.parametrize("name,fixture", o.CASES, ids=o.IDS)
def test_captured_answers_start_with_their_json(name, fixture):
    """The premise: no captured answer has text before its JSON, so refusing it loses nothing seen."""
    assert o.fx(fixture).lstrip()[:1] in ("{", "["), fixture


@pytest.mark.parametrize("name,fixture", o.CASES, ids=o.IDS)
def test_whitespace_around_a_captured_answer_reads_the_same(name, fixture):
    text = o.fx(fixture)
    expected = o.read(name, text)
    assert expected, f"{fixture} reads no addresses: the guard would prove nothing"
    assert o.read(name, "\n  \t" + text + "\n\n") == expected


@pytest.mark.parametrize("name,fixture", o.CASES, ids=o.IDS)
def test_text_after_the_json_raises(name, fixture):
    with pytest.raises(DriverError):
        o.read(name, o.fx(fixture) + "FFFF")
