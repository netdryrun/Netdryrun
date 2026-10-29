"""Arista EOS advertisement delay (`neighbor ... out-delay`), read for the settle window (RELEASES.md 0.4.1).

EOS's BGP summary carries no delay, so 0.4 used EOS's default (0) for every peer: a configured out-delay
longer than the settle window lets a leak arrive after a negative check stopped looking. The reader takes
`show ip bgp neighbors vrf <vrf> | json`. These tests are written before the live capture that fixes the
field names (scripts/capture_fixtures.sh eos: eos_bgp_neighbors*.txt): until then they skip, saying so.

What the reader must do, whatever EOS calls the field:
- a peer with `out-delay 7` reads 7.0, the same peer without it 0.0 (EOS's default), from the device's own
  output, never from a constant;
- a peer the detail output doesn't list, or output the parser doesn't know, reads None ("not known"),
  never 0: 0 would claim the window is long enough;
- a failing detail command doesn't fail `bgp_neighbors` (sessions and counts come from the summary), and
  its peers read None.
"""
from __future__ import annotations

from pathlib import Path

import pytest

FIX = Path(__file__).parent / "fixtures"
CAPTURES = ("eos_bgp_neighbors.txt", "eos_bgp_neighbors_outdelay.txt")
pytestmark = pytest.mark.skipif(
    not all((FIX / f).exists() for f in CAPTURES),
    reason="needs the live cEOS capture (scripts/capture_fixtures.sh eos, out-delay phase) to fix EOS's field names")


def read(name: str) -> str:
    return (FIX / name).read_text(encoding="utf-8")


def test_out_delay_is_read_from_the_device():
    from netdryrun.drivers import eos
    assert eos.parse_out_delays(read("eos_bgp_neighbors.txt")) == {"10.0.200.2": 0.0}
    assert eos.parse_out_delays(read("eos_bgp_neighbors_outdelay.txt")) == {"10.0.200.2": 7.0}


def test_driver_sets_adv_interval_per_peer():
    from test_verdict_drivers import Lab

    from netdryrun.drivers.eos import EosDriver
    lab = Lab([("show ip bgp neighbors", read("eos_bgp_neighbors_outdelay.txt")),
               ("show ipv6 bgp summary", '{"vrfs": {"default": {"vrf": "default", "peers": {}}}}'),
               ("show ip bgp summary", read("eos_bgp_summary.txt"))])
    n = EosDriver(lab, "ceos1").bgp_neighbors().value
    assert n["10.0.200.2"].adv_interval == 7.0


@pytest.mark.parametrize("detail", [(1, "", "% error"), "", "{}", '{"vrfs": {}}', "not json"])
def test_unreadable_detail_is_unknown_not_zero(detail):
    from test_verdict_drivers import Lab

    from netdryrun.drivers.eos import EosDriver
    lab = Lab([("show ip bgp neighbors", detail),
               ("show ipv6 bgp summary", '{"vrfs": {"default": {"vrf": "default", "peers": {}}}}'),
               ("show ip bgp summary", read("eos_bgp_summary.txt"))])
    n = EosDriver(lab, "ceos1").bgp_neighbors().value
    assert n["10.0.200.2"].state == "established"       # sessions still read from the summary
    assert n["10.0.200.2"].adv_interval is None


def test_runner_stretches_settle_for_eos_out_delay():
    """End to end through the 0.4 stretch: a 7 s out-delay makes settle and hold at least 9 s."""
    from test_verdict_drivers import Lab

    from netdryrun.drivers.eos import EosDriver
    from netdryrun.runner import ADV_MARGIN
    lab = Lab([("show ip bgp neighbors", read("eos_bgp_neighbors_outdelay.txt")),
               ("show ipv6 bgp summary", '{"vrfs": {"default": {"vrf": "default", "peers": {}}}}'),
               ("show ip bgp summary", read("eos_bgp_summary.txt"))])
    longest = max(n.adv_interval for n in EosDriver(lab, "ceos1").bgp_neighbors().value.values())
    assert longest + ADV_MARGIN == 9.0
