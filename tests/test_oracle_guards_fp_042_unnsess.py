"""Guards for oracle FP-042-UNNSESS (red team RT-0066): they pass before and after its fix.

The fast-fix gate runs tests/oracles/FP-042-UNNSESS/ and needs every test there to fail on the fix's parent, so the
guards live here, in the unit suite. This file is in the oracle's `evidence:`, so the fix can't change it. Helpers and
the captured data come from the oracle's own module (tests/oracles/FP-042-UNNSESS/).
"""
import importlib.util
from pathlib import Path

_PATH = Path(__file__).resolve().parent / "oracles" / "FP-042-UNNSESS" / "test_oracle_fp_042_unnsess.py"
_SPEC = importlib.util.spec_from_file_location("oracle_fp_042_unnsess", _PATH)
o = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(o)


def test_the_capture_is_what_the_oracle_says():
    assert o.neighbors("leaf01") == ["eth1", "eth2"] and o.neighbors("spine01") == ["eth1", "eth2", "eth3"]
    for node in o.NODES:
        eth1 = o.fx(f"frr1021u_{node}_ip_o_addr_show_dev_eth1.txt")
        assert " inet6 fe80:" in eth1 and " inet " not in eth1


def test_the_unnumbered_link_is_still_named_and_unguarded(monkeypatch):
    """FP-042-UNNUMBERED's deliverable: link-local only plus a session over it is BGP unnumbered, said by name."""
    data, warnings = o.run(monkeypatch, o.CapturedLab())
    for node in o.NODES:
        assert o.named_unnumbered(warnings, node, "eth1"), warnings


def test_the_numbered_lan_keeps_its_guard(monkeypatch):
    data, _ = o.run(monkeypatch, o.CapturedLab())
    assert ("leaf01", "192.168.11.0/24") in o.guarded(data)
    assert ("spine01", "192.168.11.0/24") in o.guarded(data)


def test_an_ordinary_address_still_reads_as_its_subnet(monkeypatch):
    """A global /31 on the captured eth1 (no peer form): its subnet is guarded, the link isn't called unnumbered."""
    answers = o.captured()
    answers[("leaf01", "ip -o addr show dev eth1")] += o.line("leaf01", "eth1", "10.0.1.0/31")
    data, warnings = o.run(monkeypatch, o.CapturedLab(answers))
    assert ("leaf01", "10.0.1.0/31") in o.guarded(data)
    assert not o.named_unnumbered(warnings, "leaf01", "eth1"), warnings
