"""Guards for oracle FP-043-VRFDEV (red team RT-0053): they pass before and after its fix.

The fast-fix gate runs tests/oracles/FP-043-VRFDEV/ and needs every test there to fail on the fix's parent, so the
guards live here, in the unit suite. This file is in the oracle's `evidence:`, so the fix can't change it. Helpers and
the captured data come from the oracle's own module (tests/oracles/FP-043-VRFDEV/).
"""
import importlib.util
import json
from pathlib import Path

_PATH = Path(__file__).resolve().parent / "oracles" / "FP-043-VRFDEV" / "test_oracle_fp_043_vrfdev.py"
_SPEC = importlib.util.spec_from_file_location("oracle_fp_043_vrfdev", _PATH)
o = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(o)


def test_the_capture_is_what_the_oracle_says():
    s = o.sections()
    in_vrf = json.loads(s["ip -j addr show vrf red"][0])
    assert [d["ifname"] for d in in_vrf] == ["d0"] and all(d.get("master") == "red" for d in in_vrf)
    dev = json.loads(s["ip -j addr show dev red"][0])
    assert [d["ifname"] for d in dev] == ["red"] and "master" not in dev[0]
    assert [a["local"] for a in dev[0]["addr_info"]] == ["10.9.9.9", "10.8.8.1", "2001:db8:99::9"]
    assert s["ping vrf device /32"][1] == 0 and "2 packets received" in s["ping vrf device /32"][0]
    assert s["ping other addr in /24 on vrf device"][1] == 1
    assert "0 packets received" in s["ping other addr in /24 on vrf device"][0]
    assert "local 10.9.9.9 dev red" in s["local table 10"][0]


def test_a_ping_to_an_enslaved_address_is_refused():
    """10.0.23.1 is on d0, enslaved to red: refused as an own address before and after the fix."""
    r = o.ping("10.0.23.1", count=1)
    assert not r.passed and "10.0.23.1" in str(r.detail), r.detail


def test_an_address_in_the_vrf_devices_subnet_is_not_the_nodes():
    """10.8.8.77 is inside red's 10.8.8.0/24 but nobody holds it: the kernel didn't answer (0/2). A ping to it expecting
    failure passes: the device's subnet is not the node's own the way a prefix on lo is."""
    r = o.ping("10.8.8.77", expect="failure")
    assert r.passed, r.detail
