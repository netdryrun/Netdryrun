"""The angle-5 red team on d87aa3e (2026-11-08), by class (design/redteam-041-angle5-fixes.md in the business repo).
Every test here was red on d87aa3e. The driver cases with crafted or captured output are RT-0044 to RT-0050 in
tests/redteam/; RT-0051 and RT-0052 pin the tests below."""
from __future__ import annotations

import json

import pytest

from netdryrun import record
from netdryrun.config import WELL_KNOWN_COMMUNITIES, ConfigError, load
from netdryrun.drivers.base import BgpPath, Observation, Route

from test_routeros_driver import MAIN, SESSIONS, body, driver, routes_rules


# ------------------------------------------------------------------------------- C1: protocol names by family

@pytest.mark.parametrize("prefix,given,want", [
    ("10.99.0.0/24", "ospf6", "ospf"), ("10.99.0.0/24", "ospf", "ospf"),
    ("2001:db8::/32", "ospf", "ospf6"), ("2001:db8::/32", "ospf6", "ospf6"),
    ("10.99.0.0/24", "ripng", "rip"), ("2001:db8::/32", "rip", "ripng"),
    ("10.99.0.0/24", "isis", "isis"), ("2001:db8::/32", "isis", "isis"), ("10.99.0.0/24", "bgp", "bgp")])
def test_a_route_is_named_by_its_own_family(prefix, given, want):
    assert Route(prefix, given, True).protocol == want


def test_the_device_name_stays_in_the_evidence():
    r = Route("10.99.0.0/24", "ospf6", True, raw_protocol="OSPF3")
    assert (r.protocol, r.raw_protocol) == ("ospf", "OSPF3")
    assert r == Route("10.99.0.0/24", "ospf", True)          # raw_protocol doesn't change equality


def test_a_route_whose_prefix_isnt_a_network_is_an_error():
    with pytest.raises(ValueError):
        Route("not-a-prefix", "ospf", True)


# ------------------------------------------------------------------------------- C2: own paths, RouterOS (RT-0051)

def test_routeros_own_advertised_prefix_fails_bgp_route_absent():
    """routeros_routes_main.txt (live 7.23.8): the node's own 10.10.10.1/32 is listed only as bgp-output rows, one
    per peer it is advertised to. `bgp_route present: false` must fail: the BGP table holds the node's own path."""
    from netdryrun.checks import _bgp_route
    d, _ = driver([*routes_rules("10.10.10.1/32", MAIN), ("/routing/bgp/session", body(SESSIONS))])
    ok, detail, _ = _bgp_route(d, {"prefix": "10.10.10.1/32", "present": False})
    assert not ok and "own" in detail


def test_routeros_own_advertised_prefix_is_not_a_received_path():
    d, _ = driver([*routes_rules("10.10.10.1/32", MAIN), ("/routing/bgp/session", body(SESSIONS))])
    paths = d.bgp_paths("10.10.10.1/32").value
    assert paths and all(p.local_candidate for p in paths)


# ------------------------------------------------------------------------------- C3: YAML merges (RT-0050 too)

def _cfg(tmp_path, checks_yaml):
    (tmp_path / "t.clab.yml").write_text("name: t\ntopology:\n  nodes:\n    r1: {kind: linux}\n    r2: {kind: linux}\n"
                                         "    r3: {kind: linux}\n", encoding="utf-8")
    p = tmp_path / "netdryrun.yml"
    p.write_text("lab: t.clab.yml\nchecks:\n" + checks_yaml, encoding="utf-8")
    return p


def test_a_merge_list_whose_sources_share_a_key_is_refused(tmp_path):
    p = _cfg(tmp_path, "  - &a {type: route, node: r1, prefix: 0.0.0.0/0, protocol: bgp, present: false}\n"
                       "  - &b {type: route, node: r2, prefix: 10.0.0.0/24, protocol: bgp}\n"
                       "  - <<: [*a, *b]\n    node: r3\n")
    with pytest.raises(ConfigError, match="merge"):
        load(p)


def test_an_explicit_key_over_a_merge_stays_allowed(tmp_path):
    p = _cfg(tmp_path, "  - &a {type: route, node: r1, prefix: 0.0.0.0/0, protocol: bgp, present: false}\n"
                       "  - <<: *a\n    node: r3\n")
    assert [c.node for c in load(p).checks] == ["r1", "r3"]


# ------------------------------------------------------------------------------- C4: record --attributes (RT-0052)

class _Drv:
    unsupported_bgp_attributes = frozenset()

    def __init__(self, comms=(), unsupported=()):
        self.comms = list(comms)
        self.unsupported_bgp_attributes = frozenset(unsupported)

    def bgp_paths(self, prefix, vrf="default"):
        return Observation([BgpPath(best=True, as_path="65020", next_hop="10.0.0.2", local_pref=100, med=None,
                                    communities=self.comms)], [])


def test_record_attributes_forbids_every_well_known_community_not_carried_today():
    c = record._attribute_check(_Drv(), "r1", "10.20.0.0/24")
    assert "communities" not in c
    assert {"no-export", "blackhole", "no-advertise"} <= set(c["without_communities"])


def test_record_attributes_keeps_the_communities_it_carries_out_of_the_forbidden_list():
    c = record._attribute_check(_Drv(["65020:100", "65535:65281"]), "r1", "10.20.0.0/24")
    assert c["communities"] == ["65020:100", "no-export"]
    assert "no-export" not in c["without_communities"] and "blackhole" in c["without_communities"]


def test_record_attributes_never_writes_a_key_the_driver_refuses():
    c = record._attribute_check(_Drv(unsupported=["without_communities"]), "r1", "10.20.0.0/24")
    assert "without_communities" not in c


def test_the_forbidden_list_is_every_well_known_name_a_check_accepts():
    c = record._attribute_check(_Drv(), "r1", "10.20.0.0/24")
    from netdryrun.config import parse_community
    assert all(parse_community(x) for x in c["without_communities"])
    assert len({parse_community(x) for x in c["without_communities"]}) == len(
        {v for v in WELL_KNOWN_COMMUNITIES.values()})


# ------------------------------------------------------------------------------- C5: zebra install flags

def _zebra(**flags):
    e = {"protocol": "bgp", "selected": True, "installed": True, "prefix": "192.168.20.0/24"}
    e.update(flags)
    return e


@pytest.mark.parametrize("flag", ["failed", "offloadFailed", "queued", "trapped"])
def test_a_bgp_route_with_a_failure_flag_is_not_active(flag):
    from netdryrun.drivers.frr import _route
    assert _route("192.168.20.0/24", _zebra(**{flag: True})).active is False


@pytest.mark.parametrize("proto", ["connected", "local", "kernel"])
def test_trapped_own_routes_still_forward(proto):
    from netdryrun.drivers.frr import _route
    assert _route("10.0.0.1/32", {**_zebra(trapped=True), "protocol": proto}).active is True


def test_verify_reads_the_same_failure_flags():
    from netdryrun.verify.frr import parse_routes
    entry = dict(_zebra(offloadFailed=True), distance=20, metric=0,
                 nexthops=[{"ip": "10.0.0.2", "afi": "ipv4", "interfaceName": "eth1", "active": True, "fib": True}])
    rib = parse_routes(json.dumps({"default": {"192.168.20.0/24": [entry]}}), "ipv4")
    (e,) = rib["default"][("192.168.20.0/24", "bgp")]
    assert e.fib is False


# ------------------------------------------------------------------------------- C2 on every driver (design rev. 1)

from pathlib import Path  # noqa: E402

from netdryrun.drivers import eos, junos, nxos  # noqa: E402

FX = Path(__file__).parent / "fixtures"


def _fx(name):
    return (FX / name).read_text(encoding="utf-8")


class _Own:
    """A driver answering bgp_paths and routes from real captures."""

    def __init__(self, name, paths, routes=(), lists_own=True):
        self.name, self._paths, self._routes, self.lists_own_bgp_paths = name, paths, list(routes), lists_own
        self.calls = []

    def bgp_paths(self, prefix, vrf="default"):
        return Observation(list(self._paths), [{"cmd": "bgp"}])

    def routes(self, prefix, vrf="default"):
        self.calls.append((prefix, vrf))
        return Observation(list(self._routes), [{"cmd": "route"}])


def test_junos_own_static_fails_bgp_route_absent_closed():
    """junos_route_static.txt (live): 10.99.0.0/24 is a static on the node and nothing in BGP; Junos never lists its
    own routes in the BGP table, even exported, so `present: false` can't pass there."""
    from netdryrun.checks import _bgp_route
    d = _Own("junos", junos.parse_bgp_paths(_fx("junos_route_static.txt"), "10.99.0.0/24"),
             junos.parse_routes(_fx("junos_route_static.txt"), "10.99.0.0/24"), lists_own=False)
    ok, detail, ev = _bgp_route(d, {"prefix": "10.99.0.0/24", "present": False, "vrf": "RED"})
    assert not ok and "own static route" in detail and "junos" in detail
    assert d.calls == [("10.99.0.0/24", "RED")] and ev == [{"cmd": "bgp"}, {"cmd": "route"}]


def test_junos_without_an_own_route_passes_bgp_route_absent():
    from netdryrun.checks import _bgp_route
    d = _Own("junos", [], junos.parse_routes(_fx("junos_route_empty.txt"), "10.99.0.0/24"), lists_own=False)
    assert _bgp_route(d, {"prefix": "10.99.0.0/24", "present": False})[:2] == (
        True, "no BGP path, and no own route for the prefix")


def test_junos_own_route_that_isnt_active_doesnt_block_but_a_bgp_path_fails():
    from netdryrun.checks import _bgp_route
    d = _Own("junos", [], [Route("10.99.0.0/24", "static", False)], lists_own=False)
    assert _bgp_route(d, {"prefix": "10.99.0.0/24", "present": False})[0] is True
    d = _Own("junos", [BgpPath(best=True, as_path="65002", next_hop="10.0.0.2", local_pref=100, med=None)],
             [Route("10.99.0.0/24", "static", True)], lists_own=False)
    ok, detail, _ = _bgp_route(d, {"prefix": "10.99.0.0/24", "present": False})
    assert not ok and "unexpectedly in the BGP table" in detail


@pytest.mark.parametrize("name,fixture,prefix", [("nxos", "nxos_bgp_local.txt", "192.168.10.1/32"),
                                                 ("eos", "eos_bgp_paths_local.txt", "192.168.30.1/32")])
def test_drivers_that_list_their_own_paths_fail_bgp_route_absent(name, fixture, prefix):
    """NX-OS (pathtype local) and EOS list the node's own path in the BGP table (live captures): it fails
    present: false like any path, with no fail-closed read needed."""
    from netdryrun.checks import _bgp_route
    paths = {"nxos": nxos.parse_bgp_paths, "eos": eos.parse_bgp_paths}[name](_fx(fixture), prefix)
    assert paths
    assert _bgp_route(_Own(name, paths), {"prefix": prefix, "present": False})[0] is False


def test_every_driver_says_whether_it_lists_its_own_paths():
    from netdryrun.drivers.eos import EosDriver
    from netdryrun.drivers.frr import FrrDriver
    from netdryrun.drivers.junos import JunosDriver
    from netdryrun.drivers.nxos import NxosDriver
    from netdryrun.drivers.routeros import RouterosDriver
    from netdryrun.drivers.sonic import SonicDriver
    from netdryrun.drivers.srlinux import SrlDriver
    got = {c.__name__: c.lists_own_bgp_paths for c in (FrrDriver, SonicDriver, EosDriver, NxosDriver, RouterosDriver,
                                                       SrlDriver, JunosDriver)}
    assert got == {"FrrDriver": True, "SonicDriver": True, "EosDriver": True, "NxosDriver": True,
                   "RouterosDriver": True, "SrlDriver": True, "JunosDriver": False}


# ------------------------------------------------------------------------------- C5: queued, SONiC offload

def test_a_queued_route_still_counts_as_present_for_present_false():
    """Verifier on the design: unready may only stop a pass; a queued entry is still in the table."""
    from netdryrun.checks import _route as route_check
    from netdryrun.drivers.frr import _route
    r = _route("192.168.20.0/24", _zebra(queued=True))

    class D:
        def routes(self, prefix, vrf="default"):
            return Observation([r], [])
    assert route_check(D(), {"prefix": "192.168.20.0/24", "present": False})[0] is False
    assert route_check(D(), {"prefix": "192.168.20.0/24"})[0] is False


def test_sonic_needs_offloaded_for_bgp_and_static_only():
    from netdryrun.drivers.frr import _route
    assert _route("192.168.20.0/24", _zebra(), offload=True).active is False
    assert _route("192.168.20.0/24", _zebra(offloaded=True), offload=True).active is True
    assert _route("192.168.20.0/24", {**_zebra(), "protocol": "static"}, offload=True).active is False
    assert _route("10.0.0.0/30", {**_zebra(), "protocol": "connected"}, offload=True).active is True
    assert _route("192.168.20.0/24", _zebra()).active is True                      # plain FRR: no ASIC


def test_sonic_live_capture_reads_active():
    from netdryrun.drivers import frr
    routes = frr.parse_routes(_fx("sonic_route.txt"), "192.168.20.0/24", offload=True)
    assert routes and all(r.active for r in routes if r.protocol == "bgp")


def test_verify_waits_while_a_route_install_is_queued():
    from dataclasses import replace as dc_replace

    from netdryrun.verify.converge import _not_ready
    from verify_helpers import base, rib
    lab = base()
    (entry,) = rib("static", hops=(), distance=1)
    lab.rib("cust1", "10.100.0.0/24", (dc_replace(entry, queued=True),))
    assert any("queued" in x for x in _not_ready(lab.snap()))
    assert not any("queued" in x for x in _not_ready(base().snap()))


# ------------------------------------------------------------------------------- C4: record warnings

def test_record_warns_where_it_cant_pin_communities():
    w: list = []
    record._attribute_check(_Drv(unsupported=["without_communities"]), "j1", "10.20.0.0/24", warnings=w)
    assert len(w) == 1 and "j1: 10.20.0.0/24" in w[0] and "can't tell a missing community list" in w[0]
    w = []
    c = record._attribute_check(_Drv(["alias customer-routes", "65020:100"]), "r1", "10.20.0.0/24", warnings=w)
    assert "without_communities" not in c and "alias customer-routes" in w[0]


def test_record_never_picks_the_nodes_own_row_as_the_best_path():
    class D(_Drv):
        def bgp_paths(self, prefix, vrf="default"):
            return Observation([BgpPath(best=True, as_path="", next_hop="0.0.0.0", local_pref=None, med=None,
                                        local_candidate=True, local_origin="static")], [])
    assert record._attribute_check(D(), "s1", "10.20.0.0/24") is None


# ------------------------------------------------------------------------------- C1 across real captures

_NO_EOS_BGP = json.dumps({"vrfs": {"default": {"bgpRouteEntries": {}}}})


@pytest.mark.parametrize("parse", [
    lambda: junos.parse_routes(_fx("junos_route_v6.txt"), "2001:db8:20::/48", "inet6.0"),
    lambda: junos.parse_routes(_fx("junos_route_static.txt"), "10.99.0.0/24"),
    lambda: eos.parse_routes(_fx("eos_ipv6_route_ospf3_ext.txt"), _NO_EOS_BGP, "2001:db8:77::/48"),
    lambda: eos.parse_routes(_fx("eos_route_ospf_nssa.txt"), _NO_EOS_BGP, "172.31.7.0/24"),
])
def test_no_family_paired_name_reaches_a_check_for_the_other_family(parse):
    import ipaddress as ipa
    for r in parse():
        v = ipa.ip_network(r.prefix, strict=False).version
        assert not (v == 4 and r.protocol in ("ospf6", "ripng")) and not (v == 6 and r.protocol in ("ospf", "rip"))


# ------------------------------------------------------------------------------- code review of the fixes

class _Aliased:
    name = "frr"

    def __init__(self, comms, config):
        self.comms, self.config = comms, config

    def bgp_paths(self, prefix, vrf="default"):
        return Observation([BgpPath(best=True, as_path="65020", next_hop="10.0.0.2", local_pref=100, med=None,
                                    communities=list(self.comms))], [])

    def community_aliases(self):
        from netdryrun.drivers import frr
        return Observation(frr.parse_community_aliases(self.config), [{"cmd": "show running-config bgpd"}])


_CFG = "Building configuration...\n\nCurrent configuration:\n!\n{}\n!\nend\n"


@pytest.mark.parametrize("alias_line,printed,check", [
    ("bgp community alias no-export 065020:5", ["65020:5"], {"without_communities": ["no-export"]}),
    ("bgp community alias 65020:777 65020:0100", ["65020:100"], {"communities": ["65020:100"]}),
    ("bgp community alias 65020:777 blackhole", ["65535:666"], {"communities": ["blackhole"]}),
    ("bgp community alias 65020:777 65020:100", ["65020:100"], {"without_communities": ["65020:777"]})])
def test_any_alias_on_the_node_makes_its_communities_unreadable(alias_line, printed, check):
    """Code review of the fix: an alias compared by its written name missed its canonical form (leading zeros, a
    well-known name), so it could still hide or fake a community. With any alias, no community check can pass."""
    from netdryrun.checks import _bgp_route
    ok, detail, ev = _bgp_route(_Aliased(printed, _CFG.format(alias_line)), {"prefix": "192.168.2.0/24", **check})
    assert ok is False and {"cmd": "show running-config bgpd"} in ev


def test_without_aliases_community_checks_read_as_before():
    from netdryrun.checks import _bgp_route
    d = _Aliased(["65020:100"], _CFG.format("router bgp 65001"))
    assert _bgp_route(d, {"prefix": "192.168.2.0/24", "communities": ["65020:100"]})[0] is True


@pytest.mark.parametrize("text", ["% Unknown command: show running-config bgpd", "", "Current configuration:\n!\nbgp"])
def test_an_alias_read_that_isnt_a_whole_config_is_an_error(text):
    from netdryrun.drivers import frr
    from netdryrun.drivers.base import DriverError
    with pytest.raises(DriverError):
        frr.parse_community_aliases(text)


def test_trapped_counts_for_bgp_and_static_only():
    from netdryrun.drivers.frr import _route
    assert _route("10.0.0.0/24", {**_zebra(trapped=True), "protocol": "ospf"}).active is True
    assert _route("10.0.0.0/24", {**_zebra(trapped=True), "protocol": "static"}).active is False


def test_a_merge_source_that_merges_too_is_read_whole(tmp_path):
    p = _cfg(tmp_path, "  - &base {type: route, node: r1, prefix: 0.0.0.0/0, protocol: bgp}\n"
                       "  - &guard {<<: *base, present: false}\n"
                       "  - &other {type: route, node: r2, prefix: 10.0.0.0/24}\n"
                       "  - <<: [*guard, *other]\n    node: r3\n")
    with pytest.raises(ConfigError, match="merge sources share"):
        load(p)


def test_routeros_own_row_detail_says_it_is_advertised():
    from netdryrun.checks import _bgp_route
    d, _ = driver([*routes_rules("10.10.10.1/32", MAIN), ("/routing/bgp/session", body(SESSIONS))])
    ok, detail, _ = _bgp_route(d, {"prefix": "10.10.10.1/32"})
    assert not ok and "advertised by the node to" in detail and "whether it is advertised or not" not in detail


# ------------------------------------------------------------------------------- live captures (2026-11-08)

def test_eos_prints_ospfv3_on_an_ipv4_route_and_it_reads_as_ospf_live():
    """cEOS 4.36.3M, OSPFv3 with address-family ipv4 (lab A): routeType "OSPFv3" on 10.99.3.2/32."""
    routes = eos.parse_routes(_fx("eos_route_ospfv3_ipv4.txt"), _NO_EOS_BGP, "10.99.3.2/32")
    assert [(r.protocol, r.raw_protocol, r.active) for r in routes] == [("ospf", "OSPFv3", True)]


@pytest.mark.parametrize("name,prefix", [("sonic_route_static_offloaded.json", "10.77.0.0/24"),
                                         ("sonic_route_static_orchagent_stopped.json", "10.78.0.0/24")])
def test_sonic_statics_print_offloaded_live(name, prefix):
    """sonic-vs prints offloaded on statics, even one added with orchagent stopped (lab B): the offload rule fails no
    static there, and the F6 state (installed, no offloaded) was not produced by this build."""
    from netdryrun.drivers import frr
    assert [r.active for r in frr.parse_routes(_fx(name), prefix, offload=True)] == [True]


def test_frr_alias_line_reads_from_the_live_config():
    from netdryrun.drivers import frr
    assert frr.parse_community_aliases(_fx("frr_running_config_bgpd_alias.txt")) == {"65020:100"}
