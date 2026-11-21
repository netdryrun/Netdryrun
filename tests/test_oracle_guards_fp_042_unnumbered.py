"""Guards for oracle FP-042-UNNUMBERED: they pass before and after its fix.

The fast-fix gate runs tests/oracles/FP-042-UNNUMBERED/ and needs every test there to fail on the fix's parent, so the
guards live here, in the unit suite. This file is in the oracle's `evidence:`, so the fix can't change it.
Helpers and the captured data come from the oracle's own module (tests/oracles/FP-042-UNNUMBERED/).
"""
import importlib.util
import json
from pathlib import Path

from netdryrun.lab import ExecResult

_PATH = Path(__file__).resolve().parent / "oracles" / "FP-042-UNNUMBERED" / "test_oracle_fp_042_unnumbered.py"
_SPEC = importlib.util.spec_from_file_location("oracle_fp_042_unnumbered", _PATH)
o = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(o)


def test_the_numbered_lan_still_gets_its_guard(monkeypatch):
    data, _ = o.run(monkeypatch, o.CapturedLab())
    assert ("leaf01", "192.168.11.0/24") in o.guarded(data)
    assert ("spine01", "192.168.11.0/24") in o.guarded(data)


def test_link_local_only_without_an_interface_session_stays_a_gap(monkeypatch):
    """spine01 eth1 as captured (link-local only), but no BGP session over eth1: could be an address kept elsewhere
    (SONiC on EthernetN, SR Linux on e1-Y.0), so it stays a gap."""
    answers = o.captured()
    nbrs = json.loads(answers[("spine01", "vtysh -c show bgp neighbors json")])
    del nbrs["eth1"]
    answers[("spine01", "vtysh -c show bgp neighbors json")] = json.dumps(nbrs)
    _, warnings = o.run(monkeypatch, o.CapturedLab(answers))
    assert o.link_gaps(warnings, "spine01", "eth1"), warnings


def test_an_unreadable_interface_stays_a_gap(monkeypatch):
    answers = o.captured()
    answers[("leaf01", "ip -o addr show dev eth1")] = ExecResult([], 1, "", 'Device "eth1" does not exist.')
    _, warnings = o.run(monkeypatch, o.CapturedLab(answers))
    assert o.link_gaps(warnings, "leaf01", "eth1"), warnings


def test_an_unreadable_address_token_is_never_none(monkeypatch):
    """The captured eth1 answer plus a global address line whose address can't be read: a global address is there,
    so it must not read as "link-local only" (Lab.interface_addresses drops a token it can't parse)."""
    answers = o.captured()
    extra = "14: eth1    inet 192.168.300.1/31 scope global eth1\\       valid_lft forever preferred_lft forever\n"
    answers[("leaf01", "ip -o addr show dev eth1")] = answers[("leaf01", "ip -o addr show dev eth1")] + extra
    _, warnings = o.run(monkeypatch, o.CapturedLab(answers))
    assert o.link_gaps(warnings, "leaf01", "eth1"), warnings


def test_a_global_address_next_to_the_session_is_guarded(monkeypatch):
    """eth1 with its interface session and also a global /31: that subnet is guarded, not called unnumbered."""
    answers = o.captured()
    extra = "14: eth1    inet 10.0.0.0/31 scope global eth1\\       valid_lft forever preferred_lft forever\n"
    answers[("leaf01", "ip -o addr show dev eth1")] = answers[("leaf01", "ip -o addr show dev eth1")] + extra
    data, warnings = o.run(monkeypatch, o.CapturedLab(answers))
    assert ("leaf01", "10.0.0.0/31") in o.guarded(data)
    assert not [w for w in o.named(warnings) if "leaf01" in w and "eth1" in w], warnings
