"""Guards for oracle FP-042-FRRLU: they pass before and after its fix.

The fast-fix gate runs tests/oracles/FP-042-FRRLU/ and needs every test there to fail on the fix's parent, so the
guards live here, in the unit suite. This file is in the oracle's `evidence:`, so the fix can't change it.
Helpers and the captured data come from the oracle's own module (tests/oracles/FP-042-FRRLU/).

What a fix must keep:
- a session that really carries no IPv4 and no labeled-unicast (the IPv6-only eBGP session 2001:db8:11::2 of
  tests/fixtures/verify/neighbors.txt, FRR 10.4.1 live) still passes `exact: 0` on ipv4-unicast with the
  "doesn't carry" message, and record still writes that `exact: 0` for it (acceptance round B-3);
- the same for ipv6-unicast on an IPv4-only session (10.0.1.2 of tests/fixtures/frr_custleak_neighbors.txt, live);
- on the labeled-unicast capture, `max: 0` on ipv4-unicast still fails.
"""
import importlib.util
import json
from pathlib import Path

import pytest

_PATH = Path(__file__).resolve().parent / "oracles" / "FP-042-FRRLU" / "test_oracle_fp_042_frrlu.py"
_SPEC = importlib.util.spec_from_file_location("oracle_fp_042_frrlu", _PATH)
o = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(o)

V6_ONLY = "2001:db8:11::2"
V4_ONLY = "10.0.1.2"
KINDS = sorted(o.DRIVERS)


def v6_only_answers() -> dict[str, str]:
    """`show bgp neighbors json` for edge1's default VRF, cut from the live `show bgp vrf all neighbors json` capture
    (the default VRF's object without its vrfId/vrfName, the shape FRR prints for the default VRF alone)."""
    text = o.fx("verify/neighbors.txt")
    data = json.loads(text[text.index("{"):])["default"]
    n = data[V6_ONLY]
    assert n["bgpState"] == "Established" and n["nbrExternalLink"] is True
    assert list(n["addressFamilyInfo"]) == ["ipv6Unicast"]
    assert "Labeled" not in json.dumps(n)
    return {o.NEIGHBORS: json.dumps({k: v for k, v in data.items() if isinstance(v, dict)}, indent=2)}


def v4_only_answers() -> dict[str, str]:
    text = o.fx("frr_custleak_neighbors.txt")
    n = json.loads(text)[V4_ONLY]
    assert n["bgpState"] == "Established" and list(n["addressFamilyInfo"]) == ["ipv4Unicast"]
    assert "Labeled" not in text
    return {o.NEIGHBORS: text}


@pytest.mark.parametrize("positive", [False, True], ids=["hold", "poll"])
@pytest.mark.parametrize("kind", KINDS)
def test_exact0_ipv4_passes_on_an_ipv6_only_session(kind, positive):
    r = o.prefixes_check(kind, v6_only_answers(), neighbor=V6_ONLY, positive=positive, afi="ipv4-unicast", exact=0)
    assert r.passed, r.detail
    assert "0 ipv4-unicast prefixes (the session doesn't carry ipv4-unicast)" in r.detail


@pytest.mark.parametrize("kind", KINDS)
def test_exact0_ipv6_passes_on_an_ipv4_only_session(kind):
    r = o.prefixes_check(kind, v4_only_answers(), neighbor=V4_ONLY, afi="ipv6-unicast", exact=0)
    assert r.passed, r.detail
    assert "0 ipv6-unicast prefixes (the session doesn't carry ipv6-unicast)" in r.detail


@pytest.mark.parametrize("kind", KINDS)
def test_record_still_writes_exact0_ipv4_for_an_ipv6_only_ebgp_session(monkeypatch, kind):
    data, warnings = o.record(monkeypatch, kind, v6_only_answers())
    assert o.zero_claims(data["checks"], V6_ONLY, "ipv4-unicast"), (data["checks"], warnings)


@pytest.mark.parametrize("kind", KINDS)
def test_max0_ipv4_fails_on_the_labeled_unicast_capture(kind):
    o.lu_facts()
    r = o.prefixes_check(kind, afi="ipv4-unicast", max=0)
    assert not r.passed, r.detail
