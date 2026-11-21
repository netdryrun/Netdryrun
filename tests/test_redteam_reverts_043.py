"""The EOS red-team driver cases still guard their bugs with the RIB read in place (adversary review of FP-043-EOSAGG,
F1). 0.4.3 added `show rib route` to EosDriver.routes(); three cases had no answer for it and ended in "unexpected
command", counted as caught before the driver logic they guard ran. With each bug put back here, its case must pass,
so tests/test_redteam.py (which asserts it doesn't) catches the revert; without it, the case fails for its own reason.
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from netdryrun.drivers import base, eos
from netdryrun.drivers.base import DriverError

from test_redteam import _run_driver_case

CORPUS = Path(__file__).parent / "redteam"


def _case(stem: str) -> dict:
    return yaml.safe_load((CORPUS / f"{stem}.yml").read_text(encoding="utf-8"))


def _routing_table_only(monkeypatch):
    """RT-0016's bug: only the routing table's selected route is read, so a leak that loses route selection (in the
    BGP table and the RIB, not selected) is never seen."""
    orig = eos.parse_routes
    monkeypatch.setattr(eos, "parse_routes",
                        lambda route_text, bgp_text, prefix, vrf="default", rib_text=None:
                        orig(route_text, None, prefix, vrf, None))


def _ospf_by_name_only(monkeypatch):
    """RT-0025's bug: every OSPF route is `ospf`, IPv6 too, so `protocol: ospf6` never matches an EOS route. Two
    layers guard it now, the EOS map (by family) and Route's family names (RT-0045): the bug is back only with both
    gone."""
    monkeypatch.delitem(base._FAMILY_NAMES, "ospf")
    orig = eos._protocol
    monkeypatch.setattr(eos, "_protocol", lambda rtype, prefix, command=eos.ROUTE_CMD:
                        "ospf" if rtype.lower().startswith("ospf") else orig(rtype, prefix, command))


def _raw_unmapped(monkeypatch):
    """RT-0037's bug: a route type the map doesn't know is passed through raw, which no `protocol` matches."""
    orig = eos._protocol

    def raw(rtype, prefix, command=eos.ROUTE_CMD):
        try:
            return orig(rtype, prefix, command)
        except DriverError:
            return rtype
    monkeypatch.setattr(eos, "_protocol", raw)


CASES = [("RT-0016-eos-leak-received-not-selected", _routing_table_only, "unexpectedly present via bgp"),
         ("RT-0025-eos-ospf6-never-matches", _ospf_by_name_only, "unexpectedly present via ospf6"),
         ("RT-0037-eos-unmapped-route-type-passes-present-false", _raw_unmapped, "nexthopGroupStaticRoute")]


@pytest.mark.parametrize("stem,bug,reason", CASES, ids=[c[0][:7] for c in CASES])
def test_the_case_fails_for_its_own_reason(stem, bug, reason):
    r = _run_driver_case(_case(stem))
    assert r is not None and r.passed is False and reason in r.detail, r and r.detail


@pytest.mark.parametrize("stem,bug,reason", CASES, ids=[c[0][:7] for c in CASES])
def test_putting_the_bug_back_makes_the_case_pass(stem, bug, reason, monkeypatch):
    bug(monkeypatch)
    r = _run_driver_case(_case(stem))
    assert r is not None and r.passed is True, f"{stem} doesn't catch its bug: {r and r.detail}"
