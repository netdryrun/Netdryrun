"""Arista EOS advertisement delay (`neighbor ... out-delay`), read for the settle window (RELEASES.md 0.4.1).

EOS's BGP summary carries no delay, so 0.4 used EOS's default (0) for every peer: a configured out-delay
longer than the settle window lets a leak arrive after a negative check stopped looking.

Live capture, cEOS 4.36.3M, 2026-10-29 (scripts/capture_fixtures.sh eos): `show ip bgp neighbors` does not
show out-delay at all, in JSON or text, even with `neighbor 10.0.200.2 out-delay 7` configured; the two
answers differ only in counters and `lastEvent: ReapplyOutboundPolicy`. So the delay must come from the
BGP configuration (`show running-config section router bgp`). Those tests wait on that capture
(eos_bgp_config*.txt) and skip until it exists.

What the reader must do:
- a peer with `out-delay 7` reads 7.0; one inheriting `out-delay 11` from its peer group reads 11.0; one
  with none reads 0.0 (EOS's default), all from the device's own configuration;
- a VRF's neighbors are read from that VRF's block only;
- a peer the configuration doesn't name, or configuration the parser doesn't know, reads None ("not
  known"), never 0: 0 would claim the window is long enough;
- a failing configuration command doesn't fail `bgp_neighbors` (sessions and counts come from the
  summary), and its peers read None.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

FIX = Path(__file__).parent / "fixtures"
CONFIGS = ("eos_bgp_config.txt", "eos_bgp_config_outdelay.txt", "eos_bgp_config_peergroup.txt")
needs_config = pytest.mark.skipif(
    not all((FIX / f).exists() for f in CONFIGS),
    reason="needs the live cEOS capture of `show running-config section router bgp` "
           "(scripts/capture_fixtures.sh eos) to fix the configuration's format")
EMPTY_V6 = '{"vrfs": {"default": {"vrf": "default", "peers": {}}}}'


def read(name: str) -> str:
    return (FIX / name).read_text(encoding="utf-8")


def test_neighbor_detail_does_not_carry_out_delay():
    """The finding the reader rests on. If a later EOS adds the field, this fails: read it from there."""
    plain, delayed = (json.loads(read(f)) for f in ("eos_bgp_neighbors.txt", "eos_bgp_neighbors_outdelay.txt"))

    def keys(node, out=None):
        out = set() if out is None else out
        if isinstance(node, dict):
            for k, v in node.items():
                out.add(k)
                keys(v, out)
        elif isinstance(node, list):
            for v in node:
                keys(v, out)
        return out
    assert keys(plain) == keys(delayed) - {"keepaliveTimeLeft"}
    assert not [k for k in keys(delayed) if re.search(r"out.?delay|advertisement.?interval|mrai", k, re.I)]
    assert "7" not in {str(v) for v in json.loads(read("eos_bgp_neighbors_outdelay.txt"))["vrfs"]["default"]
                       ["peerList"][0].values() if not isinstance(v, (dict, list))} - \
        {str(v) for v in plain["vrfs"]["default"]["peerList"][0].values() if not isinstance(v, (dict, list))}


@needs_config
def test_out_delay_is_read_from_the_configuration():
    from netdryrun.drivers import eos
    assert eos.parse_out_delays(read("eos_bgp_config.txt")) == {"10.0.200.2": 0.0}
    assert eos.parse_out_delays(read("eos_bgp_config_outdelay.txt")) == {"10.0.200.2": 7.0}
    assert eos.parse_out_delays(read("eos_bgp_config_peergroup.txt")) == {"10.0.200.2": 11.0}


@needs_config
def test_driver_sets_adv_interval_per_peer():
    from test_verdict_drivers import Lab

    from netdryrun.drivers.eos import EosDriver
    lab = Lab([("running-config", read("eos_bgp_config_peergroup.txt")), ("show ipv6 bgp summary", EMPTY_V6),
               ("show ip bgp summary", read("eos_bgp_summary.txt"))])
    assert EosDriver(lab, "ceos1").bgp_neighbors().value["10.0.200.2"].adv_interval == 11.0


@needs_config
@pytest.mark.parametrize("config", [(1, "", "% error"), "", "router bgp 65030\n   garbled line here\n"])
def test_unreadable_configuration_is_unknown_not_zero(config):
    from test_verdict_drivers import Lab

    from netdryrun.drivers.eos import EosDriver
    lab = Lab([("running-config", config), ("show ipv6 bgp summary", EMPTY_V6),
               ("show ip bgp summary", read("eos_bgp_summary.txt"))])
    n = EosDriver(lab, "ceos1").bgp_neighbors().value
    assert n["10.0.200.2"].state == "established"       # sessions still read from the summary
    assert n["10.0.200.2"].adv_interval is None


@needs_config
def test_runner_stretches_settle_for_eos_out_delay():
    """Through the 0.4 stretch: an 11 s inherited out-delay makes settle and hold at least 13 s."""
    from test_verdict_drivers import Lab

    from netdryrun.drivers.eos import EosDriver
    from netdryrun.runner import ADV_MARGIN
    lab = Lab([("running-config", read("eos_bgp_config_peergroup.txt")), ("show ipv6 bgp summary", EMPTY_V6),
               ("show ip bgp summary", read("eos_bgp_summary.txt"))])
    longest = max(n.adv_interval for n in EosDriver(lab, "ceos1").bgp_neighbors().value.values())
    assert longest + ADV_MARGIN == 13.0
