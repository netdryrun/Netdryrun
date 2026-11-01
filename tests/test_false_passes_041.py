"""0.4.1 false-pass fixes: the record closed-world guard (the 0.3.3/0.4.0 advisory) and red team RT-0021..RT-0027.

Each test sets up the state in which the old code passed a check that must fail, and asserts the verdict.
"""
from __future__ import annotations

import pytest

from netdryrun.checks import Unready, _bgp_prefixes, _bgp_route, _route, is_post_convergence
from netdryrun.config import ConfigError, _validate_check, community_name, parse_community
from netdryrun.drivers import DRIVERS, check_supported, eos, frr
from netdryrun.drivers.base import BgpNeighbor, BgpPath, DriverError, Observation, Route
from netdryrun.lab import Lab
from netdryrun.record import MAX_ONLY_PREFIXES, _session_checks

NB = "10.20.1.2"
CUST = "203.0.113.0/25"
LEAK = "203.0.113.128/25"


def check(**raw):
    return _validate_check(0, raw, 30.0)


class Received:
    """A driver with one neighbor and the prefixes it sent."""
    name = "frr"
    reads_received = True

    def __init__(self, count, received, state="established", external=True, error=None):
        self.n = BgpNeighbor(NB, state, {"ipv4-unicast": count}, external=external)
        self.received, self.error = received, error
        self.calls = []

    def bgp_neighbors(self, vrf="default"):
        return Observation({NB: self.n}, [{"cmd": "neighbors"}])

    def bgp_received(self, neighbor, afi="ipv4-unicast", vrf="default"):
        self.calls.append((neighbor, afi, vrf))
        if self.error:
            raise DriverError(self.error)
        return Observation(set(self.received), [{"cmd": "received"}])


# --- the stranger's case: core1 loses `match ip address prefix-list CUST-IN`, the customer's /25 arrives ---------

def test_the_stranger_leak_fails_the_recorded_check():
    """record on the good lab: 1 prefix from the customer. After the change: 2, within the old range 1..3."""
    drv = Received(1, {CUST})
    warnings: list[str] = []
    [session, prefixes] = _session_checks("core1", {NB: drv.n}, "range", warnings, drv=drv)
    assert prefixes == {"type": "bgp_prefixes", "node": "core1", "neighbor": NB, "afi": "ipv4-unicast",
                        "min": 1, "max": 3, "only": [CUST]}
    assert not warnings and session["type"] == "bgp_session"
    c = check(**prefixes)
    after = Received(2, {CUST, LEAK})
    ok, detail, _ = _bgp_prefixes(after, c.params)
    assert ok is False and LEAK in detail
    # 0.3.3 and 0.4.0 recorded the range alone, which passes: the false pass the advisory is about
    old = {k: v for k, v in c.params.items() if k != "only"}
    assert _bgp_prefixes(after, old)[0] is True


def test_a_prefix_that_replaces_another_fails():
    c = check(type="bgp_prefixes", node="r1", neighbor=NB, min=1, max=3, only=[CUST])
    assert _bgp_prefixes(Received(1, {LEAK}), c.params)[0] is False


def test_fewer_prefixes_within_the_set_pass_only_when_the_count_does():
    c = check(type="bgp_prefixes", node="r1", neighbor=NB, only=[CUST, "198.51.100.0/24"])
    assert _bgp_prefixes(Received(1, {CUST}), c.params)[0] is True
    c = check(type="bgp_prefixes", node="r1", neighbor=NB, min=2, only=[CUST, "198.51.100.0/24"])
    assert _bgp_prefixes(Received(1, {CUST}), c.params)[0] is False


def test_only_never_passes_on_a_session_that_is_down_or_a_list_that_is_empty():
    c = check(type="bgp_prefixes", node="r1", neighbor=NB, only=[CUST])
    down = Received(0, set(), state="active")
    assert _bgp_prefixes(down, c.params)[0] is False and not down.calls
    ok, detail, _ = _bgp_prefixes(Received(3, set()), c.params)   # counted but not listed: no answer
    assert ok is False and isinstance(detail, Unready)
    assert _bgp_prefixes(Received(0, set()), c.params)[0] is True   # nothing sent, nothing listed


def test_only_is_a_post_convergence_check():
    assert is_post_convergence(check(type="bgp_prefixes", node="r1", neighbor=NB, only=[CUST]))
    assert is_post_convergence(check(type="bgp_prefixes", node="r1", neighbor=NB, min=1, only=[CUST]))


def test_only_is_validated():
    c = check(type="bgp_prefixes", node="r1", neighbor=NB, only=["10.0.0.1/24", "10.0.0.0/24", "9.0.0.0/8"])
    assert c.params["only"] == ["9.0.0.0/8", "10.0.0.0/24"]
    assert check(type="bgp_prefixes", node="r1", neighbor=NB, afi="ipv6-unicast",
                 only=["2001:db8:0::/48"]).params["only"] == ["2001:db8::/48"]
    assert check(type="bgp_prefixes", node="r1", neighbor=NB, only=[]).params["only"] == []
    for bad in ("10.0.0.0/24", ["nope"], [1], ["2001:db8::/48"], None):
        with pytest.raises(ConfigError):
            check(type="bgp_prefixes", node="r1", neighbor=NB, only=bad)
    with pytest.raises(ConfigError):
        check(type="bgp_prefixes", node="r1", neighbor=NB, afi="evpn", only=[CUST])


def test_record_guards_ebgp_and_unknown_neighbors_not_ibgp():
    for external, guarded in ((True, True), (None, True), (False, False)):
        drv = Received(1, {CUST}, external=external)
        c = _session_checks("r1", {NB: drv.n}, "range", [], drv=drv)[1]
        assert ("only" in c) is guarded and c["min"] == 1 and c["max"] == 3


def test_record_pins_the_count_where_the_set_cannot_be_read():
    cases = [Received(4, {CUST}, error="no such neighbor"), Received(4, set()),
             Received(4, {f"10.{i // 256}.{i % 256}.0/24" for i in range(MAX_ONLY_PREFIXES + 1)})]
    no_support = Received(4, {CUST})
    no_support.reads_received = False
    for drv in cases + [no_support]:
        warnings: list[str] = []
        c = _session_checks("r1", {NB: drv.n}, "range", warnings, drv=drv)[1]
        assert c["exact"] == 4 and not {"min", "max", "only"} & set(c), c
        assert len(warnings) == 1 and "exactly 4" in warnings[0]
    # exact and min modes, and a neighbor that sends nothing, are as before
    drv = Received(4, {CUST})
    assert _session_checks("r1", {NB: drv.n}, "exact", [], drv=drv)[1]["exact"] == 4
    assert "only" not in _session_checks("r1", {NB: drv.n}, "min", [], drv=drv)[1]
    assert _session_checks("r1", {NB: Received(0, set()).n}, "range", [], drv=drv)[1]["exact"] == 0
    assert not drv.calls


# --- check_supported: names a driver never reports, and only where the driver can't list prefixes --------------

def _lab(tmp_path, kind, image):
    (tmp_path / "t.clab.yml").write_text(f"name: t\ntopology:\n  nodes:\n    r1:\n      kind: {kind}\n      image: {image}\n")
    return Lab(tmp_path / "t.clab.yml")


@pytest.mark.parametrize("kind,image,name", [("linux", "quay.io/frrouting/frr:10.4.1", "frr"),
                                             ("nokia_srlinux", "ghcr.io/nokia/srlinux:26.7.2", "srlinux"),
                                             ("ceos", "ceos:4.36.3M", "eos")])
def test_route_protocols_refused_where_the_driver_never_reports_them(tmp_path, kind, image, name):
    lab = _lab(tmp_path, kind, image)
    for proto in ("bgp-evpn", "aggregate", "ospf6", "dhcp", "kernel", "bgp"):
        c = check(type="route", node="r1", prefix="10.0.0.0/24", protocol=proto, present=False)
        if proto in DRIVERS[name].route_protocols:
            check_supported(lab, c)
        else:
            with pytest.raises(DriverError, match="never reported"):
                check_supported(lab, c)
    check_supported(lab, check(type="route", node="r1", prefix="10.0.0.0/24"))   # no protocol: any


def test_every_driver_declares_its_route_protocols_inside_the_config_names():
    from netdryrun.config import PROTOCOLS
    for name, cls in DRIVERS.items():
        assert cls.route_protocols and cls.route_protocols <= set(PROTOCOLS), name
    assert "bgp-evpn" not in DRIVERS["frr"].route_protocols   # RT-0024
    assert "ospf6" in DRIVERS["eos"].route_protocols          # RT-0025


def test_only_is_refused_on_drivers_that_cannot_list_received_prefixes(tmp_path):
    c = check(type="bgp_prefixes", node="r1", neighbor=NB, only=[CUST])
    lab = _lab(tmp_path, "linux", "quay.io/frrouting/frr:10.4.1")
    check_supported(lab, c)
    for name, cls in DRIVERS.items():
        if not cls.reads_received:
            with pytest.raises(DriverError, match="only is not supported"):
                check_supported(lab, c, override=name)
    assert {n for n, cls in DRIVERS.items() if cls.reads_received} == {"frr", "sonic"}


# --- RT-0021: FRR FIB install --------------------------------------------------------------------------------

def test_frr_route_counts_only_when_zebra_says_installed():
    def one(**e):
        return frr._route("10.0.0.0/24", {"protocol": "bgp", **e}).active
    assert one(selected=True, installed=True)
    assert not one(selected=True)
    assert not one(selected=True, installed=True, failed=True)
    assert not one(selected=True, failed=True)
    assert not one(installed=True)


# --- RT-0022, RT-0027: well-known community names ----------------------------------------------------------

@pytest.mark.parametrize("name,value", [("internet", "0:0"), ("accept-own-nexthop", "65535:8"),
                                        ("route-filter-translated-v4", "65535:2"), ("route-filter-v4", "65535:3"),
                                        ("route-filter-translated-v6", "65535:4"), ("route-filter-v6", "65535:5")])
def test_every_name_bgpd_prints_is_its_number(name, value):
    assert parse_community(name) == value and community_name(value) == name


class Paths:
    def __init__(self, paths):
        self.paths = paths

    def bgp_paths(self, prefix, vrf="default"):
        return Observation(self.paths, [])


def _path(**kw):
    return BgpPath(**{"best": True, "as_path": "65020", "next_hop": "10.1.1.2", "local_pref": 100, "med": None,
                      "communities": [], **kw})


def test_without_communities_never_passes_on_a_name_it_cannot_read():
    p = {"node": "r1", "prefix": "10.0.0.0/24"}
    alias = _path(communities=["65020:100", "customer-routes"])   # a bgp community alias, or an unknown name
    assert _bgp_route(Paths([alias]), {**p, "without_communities": ["65020:666"]})[0] is False
    assert _bgp_route(Paths([alias]), {**p, "communities": ["65020:100"]})[0] is True   # must-carry: not affected
    assert _bgp_route(Paths([_path(communities=["65020:100"], large_communities=["65020:1:1"])]),
                      {**p, "without_communities": ["65020:666"]})[0] is True


# --- RT-0023: SR Linux bgp-evpn, RT-0025: EOS ospf6 ------------------------------------------------------------

class Routes:
    def __init__(self, routes):
        self.r = routes

    def routes(self, prefix, vrf="default"):
        return Observation(self.r, [])


def test_protocol_bgp_matches_evpn_and_vpn_routes_and_bgp_evpn_only_its_own():
    evpn = Routes([Route("10.90.0.0/24", "bgp-evpn", True)])
    assert _route(evpn, {"prefix": "10.90.0.0/24", "protocol": "bgp-evpn", "present": False})[0] is False
    assert _route(evpn, {"prefix": "10.90.0.0/24", "protocol": "bgp", "present": False})[0] is False
    assert _route(evpn, {"prefix": "10.90.0.0/24", "protocol": "bgp"})[0] is True
    plain = Routes([Route("10.90.0.0/24", "bgp", True)])
    assert _route(plain, {"prefix": "10.90.0.0/24", "protocol": "bgp-evpn", "present": False})[0] is True
    assert _route(plain, {"prefix": "10.90.0.0/24", "protocol": "bgp-vpn"})[0] is False


@pytest.mark.parametrize("rtype,prefix,proto", [
    ("ospfIntraArea", "2001:db8::/48", "ospf6"), ("ospfExternalType2", "2001:db8::/48", "ospf6"),
    ("ospfIntraArea", "10.0.0.0/24", "ospf"), ("ospfNssaExternalType2", "10.0.0.0/24", "ospf"),
    ("ospfv3IntraArea", "10.0.0.0/24", "ospf6"), ("isisLevel2", "10.0.0.0/24", "isis"),
    ("eBGP", "10.0.0.0/24", "bgp"), ("dropRoute", "10.0.0.0/24", "static")])
def test_eos_route_types(rtype, prefix, proto):
    assert eos._protocol(rtype, prefix) == proto


# --- RT-0026: the router's own route in the SR Linux BGP RIB -------------------------------------------------

def test_a_local_candidate_is_never_the_bgp_best_path():
    p = {"node": "r1", "prefix": "10.2.0.0/24"}
    own = _path(as_path="", next_hop="0.0.0.0", local_candidate=True)
    assert _bgp_route(Paths([own]), p)[0] is False
    assert _bgp_route(Paths([own]), {**p, "as_path": ""})[0] is False
    assert _bgp_route(Paths([own, _path(best=False)]), p)[0] is False   # a received path that isn't best
    assert _bgp_route(Paths([own, _path()]), {**p, "as_path": "65020"})[0] is True


# --- the default min_replies counts from the packets asked for, not the packets sent (red team plausible case) ---

class Pinger:
    def __init__(self, sent, received):
        self.v = (sent, received)

    def ping(self, target, source, count, vrf="default"):
        return Observation(self.v, [{"output": "", "stderr": ""}])


def test_a_ping_that_sent_fewer_packets_needs_as_many_replies():
    from netdryrun.checks import _ping
    p = {"target": "10.0.0.1", "count": 3}
    assert _ping(Pinger(3, 2), p)[0] is True
    assert _ping(Pinger(1, 1), p)[0] is False      # 0.4.0: need max(1, sent - 1) = 1, passed
    assert _ping(Pinger(2, 2), p)[0] is True
    assert _ping(Pinger(1, 1), {**p, "min_replies": 1})[0] is True
    assert _ping(Pinger(1, 1), {"target": "10.0.0.1"})[0] is False   # count defaults to 3
