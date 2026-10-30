"""Graceful restart: a stale path is neither present nor gone, on every driver whose output marks it.

During a peer's graceful restart the router keeps the peer's paths, marked stale, until the peer re-sends them or the stale
timer ends. A route check that read a stale path as an ordinary one could pass on a route that is about to disappear (or fail
`present: false` on one that is). FRR already refuses such a read (`DriverError`: not settled). These tests make EOS,
NX-OS and SR Linux do the same, from the captures we already have: each real capture carries an explicit stale field
(`stale` on EOS, `pathstaled` on NX-OS, `stale-route` on SR Linux), and each test flips that field in the real capture.
Live graceful-restart captures come later; until then a stale mark we have never seen is read from the field the NOS prints.

Red first: before the drivers read the field, every `raises` test here passes silently on a stale path.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from netdryrun.drivers import DriverError, eos, nxos, srlinux

FIX = Path(__file__).parent / "fixtures"


def fx(name: str) -> str:
    return (FIX / name).read_text(encoding="utf-8")


def flip(text: str, pattern: str, replacement: str) -> str:
    out, n = re.subn(pattern, replacement, text, count=1)
    assert n == 1, f"the capture no longer has {pattern!r}: has its format changed?"
    return out


# ---- the captures parse as they are (the controls) -----------------------------------------------------------------------
def test_unedited_captures_still_parse():
    assert eos.parse_bgp_paths(fx("eos_bgp_paths.txt"), "192.168.20.0/24")
    assert nxos.parse_bgp_paths(fx("nxos_bgp_20.txt"), "192.168.20.0/24")
    assert srlinux.parse_rib_paths(fx("srl_bgp_rib_paths.txt"), "192.168.20.0/24")


# ---- Arista EOS: `"stale": false` on every path ----------------------------------------------------------------------
EOS_STALE = (r'"stale":\s*false', '"stale": true')


def test_eos_stale_path_is_not_settled_for_bgp_paths():
    with pytest.raises(DriverError, match="stale"):
        eos.parse_bgp_paths(flip(fx("eos_bgp_paths.txt"), *EOS_STALE), "192.168.20.0/24")


def test_eos_stale_path_is_not_settled_for_routes():
    with pytest.raises(DriverError, match="stale"):
        eos.parse_routes(fx("eos_route.txt"), flip(fx("eos_bgp_route.txt"), *EOS_STALE), "192.168.20.0/24")


def test_eos_stale_path_in_the_leak_capture_is_not_settled_either():
    with pytest.raises(DriverError, match="stale"):
        eos.parse_routes(fx("eos_leak_route.txt"), flip(fx("eos_leak_bgp.txt"), *EOS_STALE), "0.0.0.0/0")


@pytest.mark.parametrize("value", ['"yes"', "1", "null", '"true"'])
def test_eos_stale_field_of_an_unknown_type_is_an_error_not_false(value):
    with pytest.raises(DriverError):
        eos.parse_bgp_paths(flip(fx("eos_bgp_paths.txt"), r'"stale":\s*false', f'"stale": {value}'), "192.168.20.0/24")


# ---- Cisco NX-OS: `"pathstaled": "false"` on every path -------------------------------------------------------------
NXOS_STALE = (r'("pathstaled":\s*)"false"', r'\1"true"')


def test_nxos_stale_path_is_not_settled_for_bgp_paths():
    with pytest.raises(DriverError, match="stale"):
        nxos.parse_bgp_paths(flip(fx("nxos_bgp_20.txt"), *NXOS_STALE), "192.168.20.0/24")


def test_nxos_stale_path_is_not_settled_for_routes():
    with pytest.raises(DriverError, match="stale"):
        nxos.parse_routes(fx("nxos_route_20.txt"), flip(fx("nxos_bgp_20.txt"), *NXOS_STALE), "192.168.20.0/24")


@pytest.mark.parametrize("value", ['"yes"', '"1"', "null", '""'])
def test_nxos_pathstaled_of_an_unknown_value_is_an_error_not_false(value):
    with pytest.raises(DriverError):
        nxos.parse_bgp_paths(flip(fx("nxos_bgp_20.txt"), r'("pathstaled":\s*)"false"', rf"\1{value}"), "192.168.20.0/24")


# ---- Nokia SR Linux: `"stale-route": false` on every Local-RIB row ------------------------------------------------------
SRL_STALE = (r'"stale-route":\s*false', '"stale-route": true')


def test_srl_stale_path_is_not_settled_for_rib_paths():
    with pytest.raises(DriverError, match="stale"):
        srlinux.parse_rib_paths(flip(fx("srl_bgp_rib_paths.txt"), *SRL_STALE), "192.168.20.0/24")


def test_srl_stale_path_is_not_settled_for_routes():
    with pytest.raises(DriverError, match="stale"):
        srlinux.parse_routes(fx("srl_route.txt"), "192.168.20.0/24", flip(fx("srl_bgp_rib_paths.txt"), *SRL_STALE))


@pytest.mark.parametrize("value", ['"yes"', "1", "null", '"true"'])
def test_srl_stale_route_of_an_unknown_type_is_an_error_not_false(value):
    with pytest.raises(DriverError):
        srlinux.parse_rib_paths(flip(fx("srl_bgp_rib_paths.txt"), r'"stale-route":\s*false', f'"stale-route": {value}'),
                                "192.168.20.0/24")
