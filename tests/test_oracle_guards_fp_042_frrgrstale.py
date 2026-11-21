"""Guards for oracle FP-042-FRRGRSTALE: they pass before and after its fix.

The fast-fix gate runs tests/oracles/FP-042-FRRGRSTALE/ and needs every test there to fail on the fix's parent, so the
guards live here, in the unit suite. This file is in the oracle's `evidence:`, so the fix can't change it.
Helpers and the captured data come from the oracle's own module (tests/oracles/FP-042-FRRGRSTALE/).

Only `show bgp neighbors json` was captured after End-of-RIB (the one command netdryrun read there); any other read
answers rc 1, so a fix must judge a settled session from that answer.
"""
import importlib.util
import json
from pathlib import Path

_PATH = Path(__file__).resolve().parent / "oracles" / "FP-042-FRRGRSTALE" / "test_oracle_fp_042_frrgrstale.py"
_SPEC = importlib.util.spec_from_file_location("oracle_fp_042_frrgrstale", _PATH)
o = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(o)


def test_min3_passes_after_end_of_rib():
    """The control: once End-of-RIB arrived (3 paths, none stale), `min: 3` passes, as it did live."""
    n = json.loads(o.fx(o.AFTER_EOR))[o.NEIGHBOR]
    g = n["gracefulRestartInfo"]
    assert n["bgpState"] == "Established" and n["addressFamilyInfo"]["ipv4Unicast"]["acceptedPrefixCounter"] == 3
    assert g["ipv4Unicast"]["endOfRibStatus"]["endOfRibRecv"] is True and g["endOfRibRecv"] == {"ipv4Unicast": True}
    table = o.fx("frr1041_rpgr_r1_ipv4_after_eor.txt")
    assert sum(line.startswith(" *>") for line in table.splitlines()) == 3 and " S" not in table.split("Network")[1]
    r = o.prefixes_check(o.AFTER_EOR, min=3)
    assert r.passed, r.detail
