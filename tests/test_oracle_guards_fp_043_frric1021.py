"""Guards for oracle FP-043-FRRIC1021: what is right before the fix stays right after it.

The same captures as tests/oracles/FP-043-FRRIC1021 (the committed unnumbered lab on FRR 10.2.1 and 10.4.1, captured
live 2026-11-25):
- the captures say what the oracle claims (versions, the two forms of the interface line, the live lab error);
- the 10.4.1 answers read as before: text and JSON agree on every router, and the guard finds the lab registered;
- the 10.2.1 JSON answers read as their entries (they did before the fix too);
- an interface line of neither form (`  if <name>` or `  if <name>, ifindex <n>`) stays refused, by the parser and by
  the guard, which ends in an error rather than a verdict. Those answers are DERIVED: each is a live answer with only
  that line changed.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from netdryrun.drivers import frr_import_check as ic

_spec = importlib.util.spec_from_file_location(
    "oracle_fp_043_frric1021",
    Path(__file__).resolve().parent / "oracles" / "FP-043-FRRIC1021" / "test_oracle_fp_043_frric1021.py")
o = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(o)

TEXT = "show_bgp_importchecktable_detail"
JSON = "show_bgp_importchecktable_detail_json"
IF_LINE = {"1021": "  if lo", "1041": "  if lo, ifindex 1"}
VERSION = {"1021": "FRRouting 10.2.1_git", "1041": "FRRouting 10.4.1_git"}
# DERIVED interface lines of neither form: each replaces the live `  if lo` line of a 10.2.1 answer
REFUSED = [
    pytest.param("  if lo, ifindex x", id="ifindex-not-a-number"),
    pytest.param("  iflo", id="no-space"),
    pytest.param("  if  lo", id="two-spaces"),
    pytest.param("  if lo extra", id="trailing-word"),
    pytest.param("  if lo,ifindex 1", id="no-space-after-comma"),
    pytest.param("  if lo, ifindex 1 extra", id="ifindex-then-word"),
    pytest.param("  if", id="no-name"),
    pytest.param("   if lo", id="three-space-indent"),
]


def derived_text(router: str, line: str) -> str:
    """DERIVED: the 10.2.1 text table of `router` with its first `  if lo` line replaced by `line`."""
    text = o.fx("1021", router, TEXT)
    assert f"\n{IF_LINE['1021']}\n" in text
    return text.replace(f"\n{IF_LINE['1021']}\n", f"\n{line}\n", 1)


@pytest.mark.parametrize("version", [pytest.param(v, id=f"frr-{v}") for v in ("1021", "1041")])
def test_captures_say_what_the_oracle_claims(version):
    for r in o.ROUTERS:
        assert o.fx(version, r, "show_version").startswith(VERSION[version] + f" ({r})"), r
        assert f"frr version {VERSION[version].split()[1]}" in o.fx(version, r, "bgpd_running_config")
    for r in o.WITH_NETWORKS:
        lines = o.fx(version, r, TEXT).splitlines()
        nets = o.networks(version, r)
        assert [ln for ln in lines if ln.startswith("  if")] == [IF_LINE[version]] * len(nets), lines
    assert o.networks(version, "r2") == []
    assert o.fx(version, "r2", TEXT) == "Current BGP import check cache:\n"
    log = (o.FX / "record1021-b046245.log").read_text(encoding="utf-8")
    for r in o.WITH_NETWORKS:
        assert f"{r}: `show bgp import-check-table detail`: a line this check doesn't know: '  if lo'" in log
    assert "No verdict." in log


@pytest.mark.parametrize("router", [pytest.param(r, id=f"10.4.1-{r}") for r in o.ROUTERS])
def test_frr_1041_tables_read_as_their_entries(router):
    want = o.expected_entries("1041", router)
    assert sorted(p[0] for e in want for p in e.paths) == o.networks("1041", router)
    assert o.read_or_error(ic.parse_table_text, "1041", router, TEXT) == (want, None)
    assert o.read_or_error(ic.parse_table_json, "1041", router, JSON) == (want, None)
    # the same lab on 10.2.1 holds the same entries
    assert want == o.expected_entries("1021", router)


@pytest.mark.parametrize("router", [pytest.param(r, id=f"10.2.1-{r}") for r in o.ROUTERS])
def test_frr_1021_json_tables_read_as_their_entries(router):
    want = o.expected_entries("1021", router)
    assert o.read_or_error(ic.parse_table_json, "1021", router, JSON) == (want, None)


def test_frr_1021_empty_text_table_reads_as_empty():
    assert o.read_or_error(ic.parse_table_text, "1021", "r2", TEXT) == ([], None)


@pytest.mark.parametrize("remedy", [pytest.param(True, id="deployed"), pytest.param(False, id="not-deployed")])
def test_frr_1041_guard_finds_every_router_registered(remedy):
    lab = o.CapturedLab("1041")
    assert o.guarded(lab, remedy) == ({r: "registered" for r in o.ROUTERS}, None)
    assert not any(cmd[:3] == ["vtysh", "-c", "configure terminal"] for _n, cmd in lab.asked), lab.asked


@pytest.mark.parametrize("line", REFUSED)
def test_an_interface_line_of_neither_form_is_refused(line):
    with pytest.raises(ic.Unknown, match="a line this check doesn't know"):
        ic.parse_table_text(derived_text("r1", line), TEXT)


@pytest.mark.parametrize("line", REFUSED[:4])
def test_guard_on_an_interface_line_of_neither_form_is_an_error(line):
    lab = o.CapturedLab("1021", derived={("r3", TEXT): derived_text("r3", line)})
    found, err = o.guarded(lab, remedy=True)
    assert found is None and err is not None
    assert "r3: `show bgp import-check-table detail`: a line this check doesn't know" in str(err), str(err)
    assert "No verdict." in str(err)
