"""A bgp_prefixes check on an IPv6 neighbor names its afi (acceptance round B-2, 2026-11-02): the default,
ipv4-unicast, is a family such a session usually doesn't carry, so the count read 0 and `max: 3` passed while the
neighbor sent 500 IPv6 prefixes."""
import textwrap

import pytest

from netdryrun.checks import _bgp_prefixes
from netdryrun.config import ConfigError, load
from netdryrun.drivers.base import BgpNeighbor, Observation

TOPO = "name: t\ntopology:\n  nodes:\n    r1: {image: quay.io/frrouting/frr:10.4.1}\n"
HINT = ("is an IPv6 address, but afi defaults to ipv4-unicast: set afi: ipv6-unicast (or afi: ipv4-unicast if this "
        "session carries IPv4 routes)")


def one_check(tmp_path, check):
    (tmp_path / "topo.clab.yml").write_text(TOPO)
    p = tmp_path / "netdryrun.yml"
    p.write_text(textwrap.dedent(f"lab: topo.clab.yml\nchecks:\n  - {check}\n"))
    return p


class V6Only:
    def bgp_neighbors(self, vrf="default"):
        return Observation({"2001:db8:1::2": BgpNeighbor("2001:db8:1::2", "established", {"ipv6-unicast": 500})}, [])


def test_the_false_pass_it_closes():
    """Read as ipv4-unicast, the session's absent family counted 0 and max: 3 passed."""
    assert _bgp_prefixes(V6Only(), {"node": "r1", "neighbor": "2001:db8:1::2", "max": 3})[0] is True
    assert _bgp_prefixes(V6Only(), {"node": "r1", "neighbor": "2001:db8:1::2", "max": 3, "afi": "ipv6-unicast"})[0] is False


@pytest.mark.parametrize("bound", ["max: 3", "exact: 0", "min: 1"])
def test_an_ipv6_neighbor_without_afi_is_refused(tmp_path, bound):
    with pytest.raises(ConfigError) as e:
        load(one_check(tmp_path, f"{{type: bgp_prefixes, node: r1, neighbor: '2001:DB8:1::2', {bound}, name: up}}"))
    assert str(e.value) == f"checks[0] ('up'): neighbor 2001:db8:1::2 {HINT}"


@pytest.mark.parametrize("afi", ["ipv6-unicast", "ipv4-unicast"])
def test_an_ipv6_neighbor_with_afi_written_loads(tmp_path, afi):
    """IPv4 routes over an IPv6 session (RFC 8950) are real: written explicitly, the family is the user's claim."""
    cfg = load(one_check(tmp_path, f"{{type: bgp_prefixes, node: r1, neighbor: '2001:db8:1::2', max: 3, afi: {afi}}}"))
    assert cfg.checks[0].params["afi"] == afi


def test_an_ipv4_neighbor_keeps_its_default(tmp_path):
    cfg = load(one_check(tmp_path, "{type: bgp_prefixes, node: r1, neighbor: 10.0.0.2, max: 3}"))
    assert "afi" not in cfg.checks[0].params
