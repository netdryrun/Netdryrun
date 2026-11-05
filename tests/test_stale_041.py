"""Stale paths are never present or gone (0.4.1 red-team fixes, design round 3 "R4").

Junos marks a plain graceful-restart stale route only in bgp-rt-flag ("Stale Accepted") while rt-entry-state still reads
"Active Ext" (captured live): the driver read rt-entry-state alone. On 1de8d70 the live capture still failed closed, for
another reason: with `routing-options graceful-restart` configured, Junos prints a table-level `restart-state`
("Complete") that the strict parser didn't know, so every route read on such a router was an error. This batch accepts
`restart-state` (only "Complete"; any other value is a table still being rebuilt, not settled), which makes the
bgp-rt-flag read the only guard: both land together. Every Junos path read reads both marks, a kept BGP entry without
bgp-rt-flag is an error, and a path carrying LLGR_STALE (65535:6) is refused on every driver that reads communities.

Red on 1de8d70: the stale captures raise "unknown element 'restart-state'", not the stale refusal; the helper-only case
(a stale route in a table without restart-state, Junos helper mode being on by default) passed there as active.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from netdryrun.drivers import DRIVERS, junos
from netdryrun.drivers.base import BgpPath, DriverError, Observation

FX = Path(__file__).parent / "fixtures"
PFX = "192.168.20.0/24"


@pytest.mark.parametrize("name", ["junos_route_stale_gr.txt", "junos_route_stale_llgr.txt"])
def test_junos_route_and_path_reads_refuse_a_stale_route(name):
    text = (FX / name).read_text(encoding="utf-8")
    with pytest.raises(DriverError, match="stale"):
        junos.parse_routes(text, PFX)
    with pytest.raises(DriverError, match="stale"):
        junos.parse_bgp_paths(text, PFX)


def test_junos_bgp_entry_without_its_flag_is_an_error():
    text = (FX / "junos_route_stale_gr.txt").read_text(encoding="utf-8")
    # drop the flag leaf: the stale mark can no longer be read
    i = text.index('"bgp-rt-flag"')
    j = text.index("],", i) + 2
    with pytest.raises(DriverError, match="bgp-rt-flag"):
        junos.parse_routes(text[:i] + text[j:], PFX)


def test_a_live_non_stale_junos_route_still_reads():
    assert junos.parse_routes((FX / "junos_route_leak.txt").read_text(encoding="utf-8"),
                              "0.0.0.0/0") is not None


@pytest.mark.parametrize("name", sorted(DRIVERS))
def test_every_driver_refuses_an_llgr_stale_path(name):
    cls = DRIVERS[name]
    assert getattr(cls.bgp_paths, "_llgr_checked", False), f"{name}.bgp_paths skips the LLGR_STALE refusal"
    path = BgpPath(best=True, as_path="65002", next_hop="10.0.0.2", local_pref=100, med=None,
                   communities=["65535:6"], neighbor="10.0.0.2")
    sub = type("Sub", (cls,), {"bgp_paths": lambda self, prefix, vrf="default": Observation([path], [])})
    with pytest.raises(DriverError, match="LLGR_STALE"):
        sub.__new__(sub).bgp_paths(PFX)


def test_junos_stale_route_in_a_table_without_restart_state_is_refused():
    """The helper-only case: the same live entry, in a table that doesn't print restart-state."""
    text = (FX / "junos_route_stale_gr.txt").read_text(encoding="utf-8")
    i = text.index('"restart-state"')
    j = text.index("],", i) + 2
    with pytest.raises(DriverError, match="stale"):
        junos.parse_routes(text[:i] + text[j:], PFX)


def test_junos_table_still_restarting_is_not_settled():
    text = (FX / "junos_route_leak.txt").read_text(encoding="utf-8")
    i = text.index('"table-name"')
    text = text[:i] + '"restart-state" : [{"data" : "Pending"}], ' + text[i:]
    with pytest.raises(DriverError, match="not settled"):
        junos.parse_routes(text, "0.0.0.0/0")
