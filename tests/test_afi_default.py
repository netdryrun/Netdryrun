"""A bgp_prefixes check on an IPv6 neighbor names its afi (acceptance round B-2, 2026-11-02): the default,
ipv4-unicast, is a family such a session usually doesn't carry, so the count read 0 and `max: 3` passed while the
neighbor sent 500 IPv6 prefixes."""
import textwrap

import pytest

from netdryrun.checks import Unready, _bgp_prefixes
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


P = {"node": "r1", "neighbor": "2001:db8:1::2"}


@pytest.mark.parametrize("bound", [{"max": 3}, {"min": 0}, {"min": 1, "max": 5}, {"exact": 2},
                                   {"min": 0, "only": ["10.1.0.0/24"]}, {"exact": 0, "only": []}])
def test_a_family_the_session_does_not_carry_is_never_counted_as_0(bound):
    """Read as ipv4-unicast, the family the session doesn't carry counted 0 and max: 3 passed (the false pass)."""
    ok, detail, _ = _bgp_prefixes(V6Only(), {**P, "afi": "ipv4-unicast", **bound})
    # a failure on state that was read (the session's families), never a count and never "unreadable"
    assert ok is False and not isinstance(detail, Unready)
    assert detail == "the session to 2001:db8:1::2 doesn't carry ipv4-unicast"


def test_exact_0_on_a_family_the_session_does_not_carry_passes_and_says_why():
    """Nothing of that family can arrive, which is all `exact: 0` claims (what record writes, B-3)."""
    ok, detail, _ = _bgp_prefixes(V6Only(), {**P, "afi": "ipv4-unicast", "exact": 0})
    assert ok is True and detail == "0 ipv4-unicast prefixes (the session doesn't carry ipv4-unicast)"


def test_once_the_family_is_added_and_sends_a_prefix_exact_0_fails():
    class Added:
        def bgp_neighbors(self, vrf="default"):
            return Observation({"2001:db8:1::2": BgpNeighbor("2001:db8:1::2", "established",
                                                             {"ipv6-unicast": 500, "ipv4-unicast": 1})}, [])
    ok, detail, _ = _bgp_prefixes(Added(), {**P, "afi": "ipv4-unicast", "exact": 0})
    assert ok is False and detail == "1 ipv4-unicast prefixes accepted"
    assert _bgp_prefixes(V6Only(), {**P, "afi": "ipv6-unicast", "max": 3})[0] is False   # the carried family counts


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


# --- on a live capture (FRR 10.4.1, examples/frr-customer-leak: two eBGP sessions carrying ipv4-unicast only) ---

def _live():
    from pathlib import Path

    from netdryrun.drivers import frr
    text = (Path(__file__).parent / "fixtures" / "frr_custleak_neighbors.txt").read_text(encoding="utf-8")
    return frr.parse_bgp_neighbors(text)


class Live:
    def __init__(self, neighbors):
        self.neighbors = neighbors

    def bgp_neighbors(self, vrf="default"):
        return Observation(self.neighbors, [])


def test_live_family_not_carried_exact_0_passes_and_max_fails():
    d = Live(_live())
    assert _bgp_prefixes(d, {"node": "edge", "neighbor": "10.0.1.2", "afi": "ipv6-unicast", "exact": 0}) == \
        (True, "0 ipv6-unicast prefixes (the session doesn't carry ipv6-unicast)", [])
    assert _bgp_prefixes(d, {"node": "edge", "neighbor": "10.0.1.2", "afi": "ipv6-unicast", "max": 3}) == \
        (False, "the session to 10.0.1.2 doesn't carry ipv6-unicast", [])
    assert _bgp_prefixes(d, {"node": "edge", "neighbor": "10.0.1.2", "afi": "ipv4-unicast", "max": 3})[0] is True


def test_record_writes_exact_0_for_the_family_not_carried_and_it_fails_once_that_family_sends_a_prefix():
    """B-3: record on the live capture writes ipv6-unicast exact 0 for each eBGP session; the day IPv6 is added to
    the customer session and a prefix arrives, the recorded check fails."""
    from netdryrun.config import _validate_check
    from netdryrun.record import _session_checks
    neighbors = _live()
    checks = _session_checks("edge", neighbors, "range", [])
    v6 = [c for c in checks if c.get("afi") == "ipv6-unicast"]
    assert v6 == [{"type": "bgp_prefixes", "node": "edge", "neighbor": a, "afi": "ipv6-unicast", "exact": 0}
                  for a in ("10.0.1.2", "10.0.2.2")]
    check = _validate_check(0, dict(v6[0]), 30)
    assert _bgp_prefixes(Live(neighbors), check.params)[0] is True          # the baseline passes its own check
    added = dict(neighbors)
    added["10.0.1.2"] = BgpNeighbor("10.0.1.2", "established", {"ipv4-unicast": 1, "ipv6-unicast": 1}, external=True)
    assert _bgp_prefixes(Live(added), check.params) == (False, "1 ipv6-unicast prefixes accepted", [])
