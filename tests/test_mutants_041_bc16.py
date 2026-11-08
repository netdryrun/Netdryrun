"""Kill tests for the mutation survivors on bc16bd7 (the angle-5 fixes and the RT-0048 documented limit): the exact
details, errors and evidence the new code gives, so a change to any of them is seen."""
from __future__ import annotations

import json

import pytest
import yaml

from netdryrun.checks import _bgp_route, _via
from netdryrun.config import ConfigError, _StrictLoader, load_yaml
from netdryrun.drivers.base import BgpPath, DriverError, NoSuchInstance, Observation, Route
from netdryrun.drivers.eos import EosDriver
from netdryrun.drivers.frr import FrrDriver, _route, zebra_forwards
from netdryrun.drivers.nxos import _rib_routes
from netdryrun.drivers.sonic import SonicDriver

from test_routeros_driver import body, driver
from test_verdict_drivers import Lab


# ------------------------------------------------------------------------------- checks._via

class _R:   # a route without raw_protocol (a driver that never sets it)
    def __init__(self, protocol):
        self.protocol = protocol


@pytest.mark.parametrize("route,want", [
    (Route("10.0.0.0/24", "ospf6", True, raw_protocol="OSPF3"), "ospf (OSPF3)"),
    (Route("2001:db8::/32", "ospf", True, raw_protocol="ospfv3"), "ospf6 (ospfv3)"),
    (Route("10.0.0.0/24", "ripng", True, raw_protocol="ripng"), "rip (ripng)"),
    (Route("2001:db8::/32", "rip", True, raw_protocol="RIP"), "ripng (RIP)"),
    (Route("10.0.0.0/24", "ospf", True, raw_protocol="OSPF"), "ospf"),         # the same name in another case
    (Route("2001:db8::/32", "ospf6", True, raw_protocol="ospf6"), "ospf6"),
    (Route("10.0.0.0/24", "rip", True, raw_protocol="Rip"), "rip"),
    (Route("2001:db8::/32", "ripng", True, raw_protocol="RIPng"), "ripng"),
    (Route("10.0.0.0/24", "bgp", True, raw_protocol="eBGP"), "bgp"),          # not a family-paired name
    (Route("10.0.0.0/24", "ospf", True), "ospf"),                            # no device name
    (_R("ospf"), "ospf"),
    (_R("rip"), "rip"),
])
def test_via_names_the_device_protocol_only_when_it_differs(route, want):
    assert _via(route) == want


# ------------------------------------------------------------------------------- Route.__post_init__

@pytest.mark.parametrize("prefix,given,want", [("10.0.0.1/24", "ospf6", "ospf"), ("2001:db8::1/64", "rip", "ripng")])
def test_a_prefix_with_host_bits_is_still_named_by_its_family(prefix, given, want):
    assert Route(prefix, given, True).protocol == want


# ------------------------------------------------------------------------------- checks._bgp_route

class _Paths:
    def __init__(self, paths, **attrs):
        self.paths = paths
        self.__dict__.update(attrs)

    def bgp_paths(self, prefix, vrf="default"):
        return Observation(list(self.paths), [{"cmd": "bgp"}])


def _own(origin, best=False):
    return BgpPath(best=best, as_path=None, next_hop=None, local_pref=None, med=None, local_candidate=True,
                   local_origin=origin)


def test_present_false_names_the_first_peer_the_own_prefix_is_advertised_to():
    d = _Paths([_own("advertised by the node to 192.0.2.2"), _own("advertised by the node to 198.51.100.2")])
    assert _bgp_route(d, {"prefix": "10.10.10.1/32", "present": False}) == (
        False, "the node's own route for 10.10.10.1/32 is in its BGP table, advertised by the node to 192.0.2.2",
        [{"cmd": "bgp"}])


def test_the_documented_limit_detail_on_a_driver_without_a_name():
    d = _Paths([], lists_own_bgp_paths=False)
    assert _bgp_route(d, {"prefix": "10.0.0.0/24", "present": False}) == (
        True, "no BGP path (received); a prefix this node originates itself isn't checked on this NOS: guard it on the "
              "neighbor that would receive it", [{"cmd": "bgp"}])


def test_a_positive_check_on_only_an_advertised_own_route_says_so():
    d = _Paths([_own("advertised by the node to 192.0.2.2"), _own("advertised by the node to 198.51.100.2")])
    assert _bgp_route(d, {"prefix": "10.10.10.1/32"}) == (
        False, "no BGP path: only the router's own route, advertised by the node to 192.0.2.2 (check the route on a "
               "neighbor instead)", [{"cmd": "bgp"}])


class _AliasedLarge:
    name = "frr"

    def bgp_paths(self, prefix, vrf="default"):
        return Observation([BgpPath(best=True, as_path="65020", next_hop="10.0.0.2", local_pref=100, med=None,
                                    large_communities=["65020:1:1"])], [{"cmd": "bgp"}])

    def community_aliases(self):
        return Observation({"65020:1:1"}, [{"cmd": "show running-config bgpd"}])


def test_an_alias_makes_large_communities_unreadable_too():
    ok, detail, ev = _bgp_route(_AliasedLarge(), {"prefix": "192.168.2.0/24", "communities": ["65020:1:1"]})
    assert not ok and "missing communities 65020:1:1" in detail and "aliased? 65020:1:1" in detail
    assert ev == [{"cmd": "bgp"}, {"cmd": "show running-config bgpd"}]


# ------------------------------------------------------------------------------- config._StrictLoader

def _err(text):
    with pytest.raises(yaml.constructor.ConstructorError) as e:
        yaml.load(text, Loader=_StrictLoader)
    return str(e.value)


def test_two_merge_keys_name_both_lines():
    text = "a: &a {x: 1}\nb: &b {y: 2}\nc:\n  <<: *a\n  <<: *b\n"
    assert _err(text) == (
        "while reading a mapping\n  in \"<unicode string>\", line 4, column 3:\n      <<: *a\n      ^\n"
        "two `<<` merge keys in one mapping (first on line 4): YAML keeps only one of them; write one `<<: [*a, *b]` "
        "with sources that don't share a key, or the keys themselves\n  in \"<unicode string>\", line 5, column 3:\n"
        "      <<: *b\n      ^")
    with pytest.raises(ConfigError, match=r"at line 5, column 3: two `<<` merge keys in one mapping \(first on line 4\)"):
        load_yaml(text)


def test_merge_sources_sharing_a_key_name_both_lines():
    text = "a: &a {x: 1}\nb: &b\n  x: 2\nc:\n  <<: [*a, *b]\n"
    assert _err(text) == (
        "while reading a mapping\n  in \"<unicode string>\", line 5, column 3:\n      <<: [*a, *b]\n      ^\n"
        "merge sources share the key 'x' (lines 1 and 2): YAML would keep one value without a word; write that key "
        "explicitly\n  in \"<unicode string>\", line 5, column 7:\n      <<: [*a, *b]\n          ^")


def test_a_duplicate_key_names_both_lines():
    text = "a: 1\nb: 2\na: 3\n"
    assert _err(text) == (
        "while reading a mapping\n  in \"<unicode string>\", line 1, column 1:\n    a: 1\n    ^\n"
        "duplicate key 'a' (first defined on line 1)\n  in \"<unicode string>\", line 3, column 1:\n    a: 3\n    ^")


def test_merge_sources_without_a_shared_key_load():
    assert load_yaml("a: &a {x: 1}\nb: &b {y: 2}\nc:\n  <<: [*a, *b]\n  z: 3\n")["c"] == {"x": 1, "y": 2, "z": 3}


@pytest.mark.parametrize("source_a", [
    "{<<: *base}",           # a merge inside a merge source, a single alias
    "{<<: [*base]}",         # ... a list of one
    "{q: 0, <<: *base}",     # ... after a key of its own
])
def test_a_key_a_source_merges_in_itself_counts_as_its_own(source_a):
    with pytest.raises(ConfigError, match="merge sources share the key 'k'"):
        load_yaml(f"base: &base {{k: 1}}\na: &a {source_a}\nb: &b {{k: 2}}\nc:\n  <<: [*a, *b]\n")


def test_a_key_of_its_own_before_a_nested_merge_still_counts():
    with pytest.raises(ConfigError, match="merge sources share the key 'q'"):
        load_yaml("base: &base {k: 1}\na: &a {q: 0, <<: *base}\nb: &b {q: 2}\nc:\n  <<: [*a, *b]\n")


# ------------------------------------------------------------------------------- EOS _bgp_cli

INACTIVE = '{"errors": ["BGP inactive"]}'


def _eos(answer):
    lab = Lab([("show ip bgp", answer), ("show ip route", ROUTE_RED)])
    return EosDriver(lab, "e1"), lab


ROUTE_RED = json.dumps({"vrfs": {"RED": {"routingDisabled": False, "routes": {}}}})


def test_bgp_inactive_is_read_with_its_evidence_and_the_timeout():
    out = " " * 2500 + INACTIVE
    d, lab = _eos((1, out, "e" * 2500))
    ev = []
    with pytest.raises(NoSuchInstance) as e:
        d._bgp_cli("show ip bgp summary | json", ev)
    assert str(e.value) == "BGP is not configured on e1 (`show ip bgp summary | json`: BGP inactive)"
    assert ev == [{"node": "e1", "cmd": "Cli -p 15 -c show ip bgp summary | json", "rc": 1, "output": out[-2000:],
                   "stderr": "e" * 2000}]
    assert lab.calls == [("e1", ["Cli", "-p", "15", "-c", "show ip bgp summary | json"], 60)]


def test_a_bgp_answer_keeps_its_evidence():
    out = "x" * 25000
    d, lab = _eos((0, out, "e" * 2500))
    ev = []
    assert d._bgp_cli("show ip bgp | json", ev) == out
    assert ev == [{"node": "e1", "cmd": "Cli -p 15 -c show ip bgp | json", "rc": 0, "output": out[-20000:],
                   "stderr": "e" * 2000}]
    assert lab.calls == [("e1", ["Cli", "-p", "15", "-c", "show ip bgp | json"], 60)]


@pytest.mark.parametrize("answer,last", [
    ((2, "first\nlast line\n", ""), "last line"),          # no stderr: the last line of stdout
    ((1, "out", "err one\nerr two"), "err two"),            # stderr first
    ((1, "", ""), "no output"),
    ((1, "not json at all", ""), "not json at all"),
])
def test_a_failed_bgp_read_names_the_command_and_the_last_line(answer, last):
    d, _ = _eos(answer)
    with pytest.raises(DriverError) as e:
        d._bgp_cli("show ip bgp | json", [])
    assert not isinstance(e.value, NoSuchInstance)
    assert str(e.value) == f"`Cli -p 15 -c show ip bgp | json` failed on e1 (rc={answer[0]}): {last}"


def test_bgp_paths_without_bgp_confirm_the_vrf_asked_for():
    d, lab = _eos((1, INACTIVE))
    obs = d.bgp_paths("10.0.0.0/24", vrf="RED")
    assert obs.value == []
    assert [e["cmd"] for e in obs.evidence] == ["Cli -p 15 -c show ip bgp 10.0.0.0/24 vrf RED | json",
                                                "Cli -p 15 -c show ip route vrf RED 10.0.0.0/24 | json"]


# ------------------------------------------------------------------------------- FRR / SONiC

def test_a_route_with_an_unknown_protocol_names_its_command():
    with pytest.raises(DriverError) as e:
        _route("10.0.0.0/24", {"protocol": "weird"}, "show ip route json")
    assert str(e.value) == ("unexpected output from `show ip route json`: protocol 'weird' is not one this driver maps "
                            "to a protocol")


@pytest.mark.parametrize("offload", [False, True])
def test_offloaded_that_isnt_a_boolean_is_an_error(offload):
    with pytest.raises(DriverError) as e:
        _route("10.0.0.0/24", {"protocol": "static", "selected": True, "installed": True, "offloaded": "true" * 20},
               "show ip route json", offload)
    assert str(e.value) == ("unexpected output from `show ip route json`: offloaded: not a boolean: '" + ("true" * 10) + "'")


def test_a_failure_flag_that_isnt_a_boolean_names_its_command():
    e1 = {"protocol": "bgp", "selected": True, "installed": True, "queued": "yes" * 20}
    for call in (lambda: zebra_forwards("show ip route json", e1),
                 lambda: _route("10.0.0.0/24", e1, "show ip route json")):
        with pytest.raises(DriverError) as e:
            call()
        assert str(e.value) == ("unexpected output from `show ip route json`: queued: not a boolean: '"
                                + ("yes" * 20)[:40] + "'")


ALL = json.dumps({"10.78.0.0/24": [{"protocol": "static", "selected": True, "installed": True}]})


@pytest.mark.parametrize("cls,active", [(FrrDriver, True), (SonicDriver, False)])
def test_all_routes_on_sonic_needs_the_asic_offload(cls, active):
    d = cls(Lab([("show ip route json", ALL)]), "s1")
    assert [(r.prefix, r.active) for r in d.all_routes().value] == [("10.78.0.0/24", active)]


def test_community_aliases_keep_their_evidence():
    cfg = "Building configuration...\n\nCurrent configuration:\n!\nbgp community alias 65020:100 cust\n!\nend\n"
    obs = FrrDriver(Lab([("show running-config bgpd", cfg)]), "r1").community_aliases()
    assert obs.value == {"cust"}
    assert [e["cmd"] for e in obs.evidence] == ["vtysh -c show running-config bgpd"]


# ------------------------------------------------------------------------------- NX-OS

def test_nxos_keeps_the_client_name_and_names_the_command():
    row = {"TABLE_path": {"ROW_path": [{"clientname": "weird-1", "ubest": "true"}]}}
    with pytest.raises(DriverError) as e:
        _rib_routes("show ip route", "10.0.0.0/24", row)
    assert str(e.value) == "unexpected output from `show ip route`: clientname 'weird-1' is not one this driver maps to a protocol"
    [r] = _rib_routes("show ip route", "10.0.0.0/24", {"TABLE_path": {"ROW_path": {"clientname": "ospf-1", "ubest": "true"}}})
    assert (r.protocol, r.active, r.raw_protocol) == ("ospf", True, "ospf-1")


# ------------------------------------------------------------------------------- RouterOS own paths

def _row(belongs, dst):
    return {".id": "*1", "afi": "ip", "belongs-to": belongs, "bgp-net": "true", "contribution": "candidate",
            "distance": "255", "dst-address": dst, "routing-table": "main"}


def test_routeros_own_paths_are_exactly_one_per_peer_for_the_prefix():
    rows = [_row("bgp-output-198.51.100.2", "10.10.10.1/32"), _row("bgp-output-192.0.2.2", "10.10.10.1/32"),
            _row("bgp-output-203.0.113.9", "fe80::%ether1/64")]   # a scoped link-local row carries no prefix
    d, _ = driver([("/routing/route?dst-address=10.10.10.1/32", body(rows)),
                   ("/routing/table", body([{"name": "main", "invalid": "false"}]))])
    assert d.bgp_paths("10.10.10.1/32").value == [
        BgpPath(best=False, as_path=None, next_hop=None, local_pref=None, med=None, neighbor=peer, local_candidate=True,
                local_origin="advertised by the node to " + peer)
        for peer in ("192.0.2.2", "198.51.100.2")]


# an anchored source is already flattened by the time a later mapping merges it (PyYAML rewrites its `<<` in place),
# so the nested-merge walk in _StrictLoader._keys matters for a source written inline
@pytest.mark.parametrize("source_a", [
    "{<<: *base}",
    "{<<: [*base]}",
    "{q: 0, <<: *base}",
    "{<<: [*other, *base]}",
])
def test_an_inline_source_that_merges_in_a_key_shares_it(source_a):
    with pytest.raises(ConfigError, match="merge sources share the key 'k'"):
        load_yaml(f"base: &base {{k: 1}}\nother: &other {{o: 1}}\nc:\n  <<: [{source_a}, {{k: 2}}]\n")


def test_an_inline_source_keeps_its_own_keys_beside_a_nested_merge():
    with pytest.raises(ConfigError, match="merge sources share the key 'q'"):
        load_yaml("base: &base {k: 1}\nc:\n  <<: [{q: 0, <<: *base}, {q: 2}]\n")


def test_a_recursive_mapping_still_loads():
    data = load_yaml("a: &a {b: *a}\n")
    assert data["a"]["b"] is data["a"]


# a key that can't be a dict key is skipped by the duplicate scan, and the scan goes on: the error names what is wrong
# (fresh mutation review on bc16bd7: a changed scan changed the error, not just its wording)
@pytest.mark.parametrize("text,needle", [
    ("? {a: 1, a: 2}\n: v\n", "duplicate key 'a'"),                 # a duplicate inside a mapping used as a key
    ("? [1]\n: v\na: 1\na: 2\n", "duplicate key 'a'"),             # a duplicate after an unhashable key
    ("c: {<<: [&s {? [*s] : 1}]}\n", "found unconstructable recursive node"),
])
def test_yaml_errors_name_the_first_problem(text, needle):
    with pytest.raises(ConfigError, match=needle):
        load_yaml(text)


def test_routeros_names_the_peer_of_a_session_with_an_empty_name():
    from test_routeros_driver import SESSIONS
    route = {".id": "*2", "afi": "ip", "belongs-to": "bgp-IP-192.0.2.2", "bgp": "true", "bgp.as-path": "65002",
             "bgp.session": "", "contribution": "active", "active": "true", "distance": "20",
             "dst-address": "10.20.0.0/24", "gateway": "192.0.2.2", "routing-table": "main"}
    sessions = [dict(SESSIONS[0], name="", **{"remote.address": "192.0.2.2"}),
                dict(SESSIONS[0], name="XXXX", **{".id": "*2800009", "remote.address": "192.0.2.9"})]
    d, _ = driver([("/routing/route?dst-address=10.20.0.0/24", body([route])),
                   ("/routing/table", body([{"name": "main", "invalid": "false"}])),
                   ("/routing/bgp/session", body(sessions))])
    assert [p.neighbor for p in d.bgp_paths("10.20.0.0/24").value] == ["192.0.2.2"]
