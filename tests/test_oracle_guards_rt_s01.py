"""Guards for oracle RT-S01: they pass before and after its fix.

The fast-fix gate runs tests/oracles/RT-S01/ and needs every test there to fail on the fix's parent, so the guards
live here, in the unit suite. This file is in the oracle's `evidence:`, so the fix can't change it. Helpers and the
captured data come from the oracle's own module (tests/oracles/RT-S01/).
"""
import importlib.util
import json
from pathlib import Path

_PATH = Path(__file__).resolve().parent / "oracles" / "RT-S01" / "test_oracle_rt_s01.py"
_SPEC = importlib.util.spec_from_file_location("oracle_rt_s01", _PATH)
o = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(o)


def test_the_capture_is_what_the_oracle_says():
    """iBGP (the best path's neighbor in the node's own AS), no as-path container on the empty phases, [64666] on the
    prepended one, and SR Linux's own report agreeing."""
    for phase, attr in o.ATTR_ID.items():
        row = json.loads(o.fx(f"srl_rt_s01_{phase}_bgp_rib.txt"))["route"]
        assert len(row) == 1 and row[0]["best-route"] and row[0]["neighbor"] == "10.0.100.2"
        assert row[0]["neighbor-as"] == 65010 and row[0]["attr-id"] == attr
        a = json.loads(o.fx(f"srl_rt_s01_{phase}_attr_set.txt"))
        assert a["index"] == attr and a["local-pref"] == 100
        show = o.fx(f"srl_rt_s01_{phase}_show.txt")
        if phase == "prepended":
            assert a["as-path"]["segment"][0]["member"] == [64666] and "Path            :  i [64666]" in show
        else:
            assert "as-path" not in a and "Path            :  i\n" in show
    assert "autonomous-system 65010" in o.fx("srl_rt_s01_srl1.cli") and "router bgp 65010" in o.fx("srl_rt_s01_frr1.conf")
    assert "remote-as 65010" in o.fx("srl_rt_s01_frr1.conf") and "peer-as 65010" in o.fx("srl_rt_s01_srl1.cli")


def test_the_prepended_path_is_recorded_as_captured():
    check, warnings = o.recorded("prepended")
    assert check["as_path"] == "64666" and check["local_pref"] == 100, check
    assert not o.named_gap(warnings), warnings


def test_local_pref_is_recorded_as_captured():
    check, _ = o.recorded("empty")
    if check is not None:
        assert check.get("local_pref") == 100, check


def test_the_recorded_check_passes_on_the_same_path_again():
    """Recorded on the empty path, run when the path is empty again (attr-set 8): a pass, not a false alarm."""
    check, _ = o.recorded("empty")
    if check is not None:
        r = o.run_on(check, "empty_again")
        assert r.passed, r.detail


def test_the_prepended_check_fails_on_the_empty_path():
    check, _ = o.recorded("prepended")
    r = o.run_on(check, "empty")
    assert not r.passed, r.detail
