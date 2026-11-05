"""0.4.1 mutation gate, config.py: the default check names shown in reports (_describe), the exact rejection
messages of _validate_check, and the bgp_prefixes `only` list (_only).

A wrong default name misleads the reader of a report about what was tested; a wrong or missing rejection
message hides why a config was refused. Every string is pinned in full.
"""
from __future__ import annotations

import pytest

from netdryrun.config import PROTOCOLS, ConfigError, _describe, _only, _validate_check

NB = "10.0.0.2"
P4 = "10.1.0.0/24"


def check(**raw):
    return _validate_check(0, raw, 30.0)


def refused(**raw) -> str:
    with pytest.raises(ConfigError) as e:
        check(**raw)
    return str(e.value)


# --- default names (_describe through _validate_check) ---------------------------------------------------

NAMES = [
    # bgp_session
    ({"type": "bgp_session", "node": "r1", "neighbor": NB}, "r1: BGP session to 10.0.0.2 is established"),
    ({"type": "bgp_session", "node": "r1", "neighbor": NB, "state": "Idle"}, "r1: BGP session to 10.0.0.2 is idle"),
    # bgp_prefixes
    ({"type": "bgp_prefixes", "node": "r1", "neighbor": NB, "exact": 5}, "r1: prefixes from 10.0.0.2 = 5"),
    ({"type": "bgp_prefixes", "node": "r1", "neighbor": NB, "min": 1}, "r1: prefixes from 10.0.0.2 >= 1"),
    ({"type": "bgp_prefixes", "node": "r1", "neighbor": NB, "max": 7}, "r1: prefixes from 10.0.0.2 <= 7"),
    ({"type": "bgp_prefixes", "node": "r1", "neighbor": NB, "min": 2, "max": 7},
     "r1: prefixes from 10.0.0.2 >= 2 and <= 7"),
    ({"type": "bgp_prefixes", "node": "r1", "neighbor": NB, "only": ["10.9.0.0/24", "10.8.0.0/24"]},
     "r1: prefixes from 10.0.0.2 only from 2 recorded prefix(es)"),
    ({"type": "bgp_prefixes", "node": "r1", "neighbor": NB, "min": 1, "max": 3, "only": ["10.9.0.0/24"]},
     "r1: prefixes from 10.0.0.2 >= 1 and <= 3 and only from 1 recorded prefix(es)"),
    ({"type": "bgp_prefixes", "node": "r1", "neighbor": NB, "exact": 1, "only": ["10.9.0.0/24"]},
     "r1: prefixes from 10.0.0.2 = 1 and only from 1 recorded prefix(es)"),
    # route
    ({"type": "route", "node": "r1", "prefix": P4}, "r1: route 10.1.0.0/24 is present"),
    ({"type": "route", "node": "r1", "prefix": P4, "present": True}, "r1: route 10.1.0.0/24 is present"),
    ({"type": "route", "node": "r1", "prefix": P4, "present": False}, "r1: route 10.1.0.0/24 is absent"),
    ({"type": "route", "node": "r1", "prefix": "10.1.0.7/24", "protocol": "BGP"},
     "r1: route 10.1.0.0/24 via bgp is present"),
    ({"type": "route", "node": "r1", "prefix": P4, "protocol": "static", "present": False},
     "r1: route 10.1.0.0/24 via static is absent"),
    # bgp_route
    ({"type": "bgp_route", "node": "r1", "prefix": P4}, "r1: BGP best path for 10.1.0.0/24 exists"),
    ({"type": "bgp_route", "node": "r1", "prefix": P4, "present": True}, "r1: BGP best path for 10.1.0.0/24 exists"),
    ({"type": "bgp_route", "node": "r1", "prefix": P4, "present": False}, "r1: no BGP path for 10.1.0.0/24"),
    ({"type": "bgp_route", "node": "r1", "prefix": P4, "communities": ["65000:100", "NO_EXPORT"]},
     "r1: BGP best path for 10.1.0.0/24 has communities 65000:100 no-export"),
    ({"type": "bgp_route", "node": "r1", "prefix": P4, "without_communities": ["65000:1", "blackhole"]},
     "r1: BGP best path for 10.1.0.0/24 has no communities 65000:1 blackhole"),
    ({"type": "bgp_route", "node": "r1", "prefix": P4, "without_communities": "65000:01"},
     "r1: BGP best path for 10.1.0.0/24 has no communities 65000:1"),
    ({"type": "bgp_route", "node": "r1", "prefix": P4, "as_path": "65002  65003"},
     "r1: BGP best path for 10.1.0.0/24 has as-path '65002 65003'"),
    ({"type": "bgp_route", "node": "r1", "prefix": P4, "as_path": ""},
     "r1: BGP best path for 10.1.0.0/24 has as-path ''"),
    ({"type": "bgp_route", "node": "r1", "prefix": P4, "as_path_regex": "^65002_"},
     "r1: BGP best path for 10.1.0.0/24 has as-path matching /^65002_/"),
    ({"type": "bgp_route", "node": "r1", "prefix": P4, "local_pref": 200},
     "r1: BGP best path for 10.1.0.0/24 has local-pref 200"),
    ({"type": "bgp_route", "node": "r1", "prefix": P4, "local_pref": 0},
     "r1: BGP best path for 10.1.0.0/24 has local-pref 0"),
    ({"type": "bgp_route", "node": "r1", "prefix": P4, "med": 50}, "r1: BGP best path for 10.1.0.0/24 has MED 50"),
    ({"type": "bgp_route", "node": "r1", "prefix": P4, "next_hop": "2001:db8:0::9"},
     "r1: BGP best path for 10.1.0.0/24 has next hop 2001:db8::9"),
    ({"type": "bgp_route", "node": "r1", "prefix": P4, "communities": ["65000:100"], "without_communities": ["65000:2"],
      "as_path": "65002", "as_path_regex": "_65003$", "local_pref": 100, "med": 0, "next_hop": "10.0.0.9"},
     "r1: BGP best path for 10.1.0.0/24 has communities 65000:100, no communities 65000:2, as-path '65002', "
     "as-path matching /_65003$/, local-pref 100, MED 0, next hop 10.0.0.9"),
    # ping
    ({"type": "ping", "node": "r1", "target": "10.0.0.9"}, "r1: ping 10.0.0.9 expects success"),
    ({"type": "ping", "node": "r1", "target": "10.0.0.9", "expect": "FAILURE"}, "r1: ping 10.0.0.9 expects failure"),
    ({"type": "ping", "node": "r1", "target": "10.0.0.9", "source": "10.0.0.1"},
     "r1: ping 10.0.0.9 from 10.0.0.1 expects success"),
    ({"type": "ping", "node": "r1", "target": "10.0.0.9", "source": "10.0.0.1", "expect": "failure"},
     "r1: ping 10.0.0.9 from 10.0.0.1 expects failure"),
]


@pytest.mark.parametrize(("raw", "name"), NAMES, ids=[n for _, n in NAMES])
def test_default_check_name(raw, name):
    assert check(**raw).name == name


def test_explicit_name_wins_over_the_default():
    assert check(type="ping", node="r1", target="10.0.0.9", name="core reachability").name == "core reachability"


def test_describe_defaults_when_called_with_raw_params():
    # _describe's own defaults, for params that skipped canonicalisation
    assert _describe("bgp_prefixes", {"node": "r1", "neighbor": NB}) == "r1: prefixes from 10.0.0.2 counted"
    assert _describe("ping", {"node": "r1", "target": "10.0.0.9"}) == "r1: ping 10.0.0.9 expects success"
    assert _describe("ping", {"node": "r1", "target": "10.0.0.9", "source": ""}) == "r1: ping 10.0.0.9 expects success"
    assert _describe("route", {"node": "r1", "prefix": P4, "protocol": ""}) == "r1: route 10.1.0.0/24 is present"
    assert _describe("route", {"node": "r1", "prefix": P4, "present": None}) == "r1: route 10.1.0.0/24 is present"
    assert _describe("bgp_route", {"node": "r1", "prefix": P4, "communities": [], "without_communities": []}) == \
        "r1: BGP best path for 10.1.0.0/24 exists"
    assert _describe("other", {"node": "r1"}) == "other"


# --- _validate_check rejection messages ------------------------------------------------------------------

def test_bad_state_message_suggests_the_close_state():
    assert refused(type="bgp_session", node="r1", neighbor=NB, state="establised") == (
        "checks[0]: state must be one of idle, connect, active, opensent, openconfirm, established, down, "
        "got 'establised'; did you mean 'established'?")


def test_bad_afi_message_lists_the_families():
    assert refused(type="bgp_prefixes", node="r1", neighbor=NB, min=1, afi="ipv4") == (
        "checks[0]: afi must be one of ipv4-unicast, ipv6-unicast, evpn, got 'ipv4'; did you mean 'ipv4-unicast'?")


PROTOCOL_LIST = ", ".join(PROTOCOLS)


@pytest.mark.parametrize("proto", ["eBGP", "ebgp", "ibgp", "IBGP"])
def test_ebgp_ibgp_protocol_explains_why(proto):
    assert refused(type="route", node="r1", prefix=P4, protocol=proto) == (
        f"checks[0]: protocol {proto!r} is not a protocol name the drivers report; did you mean 'bgp'? "
        f"(drivers report eBGP and iBGP routes alike as bgp); use one of {PROTOCOL_LIST}")


def test_unknown_protocol_has_no_bgp_explanation():
    msg = refused(type="route", node="r1", prefix=P4, protocol="zzqq")
    assert msg == f"checks[0]: protocol 'zzqq' is not a protocol name the drivers report; use one of {PROTOCOL_LIST}"
    msg = refused(type="route", node="r1", prefix=P4, protocol=5)
    assert msg == f"checks[0]: protocol 5 is not a protocol name the drivers report; use one of {PROTOCOL_LIST}"
    assert "eBGP" not in refused(type="route", node="r1", prefix=P4, protocol="direkt")


@pytest.mark.parametrize(("prefix", "proto", "msg"), [
    (P4, "ospf6", "protocol ospf6 never carries an IPv4 prefix (10.1.0.0/24); use ospf"),
    (P4, "RIPng", "protocol ripng never carries an IPv4 prefix (10.1.0.0/24); use rip"),
    ("2001:db8::/48", "ospf", "protocol ospf never carries an IPv6 prefix (2001:db8::/48); use ospf6"),
    ("2001:db8::/48", "rip", "protocol rip never carries an IPv6 prefix (2001:db8::/48); use ripng"),
])
def test_protocol_of_the_other_family_is_refused(prefix, proto, msg):
    assert refused(type="route", node="r1", prefix=prefix, protocol=proto) == f"checks[0]: {msg}"


def test_protocol_of_the_right_family_is_accepted():
    assert check(type="route", node="r1", prefix=P4, protocol="OSPF").params["protocol"] == "ospf"
    assert check(type="route", node="r1", prefix="2001:db8::/48", protocol="ripng").params["protocol"] == "ripng"


def test_active_with_present_false_is_refused():
    assert refused(type="route", node="r1", prefix=P4, present=False, active=True) == (
        "checks[0]: active only applies to present: true (present: false already means no matching route at all, "
        "selected or not)")
    assert check(type="route", node="r1", prefix=P4, active=False).params["active"] is False
    assert check(type="route", node="r1", prefix=P4, present=True, active=True).params["active"] is True


@pytest.mark.parametrize(("expect", "hint"), [("sucess", "; did you mean 'success'?"),
                                              ("failur", "; did you mean 'failure'?"), ("maybe", "")])
def test_bad_expect_message(expect, hint):
    assert refused(type="ping", node="r1", target="10.0.0.9", expect=expect) == (
        f"checks[0]: expect must be 'success' or 'failure', got {expect!r}{hint}")


def test_ping_expect_is_canonical():
    assert check(type="ping", node="r1", target="10.0.0.9").params["expect"] == "success"
    assert check(type="ping", node="r1", target="10.0.0.9", expect="Success").params["expect"] == "success"


def test_min_replies_with_expect_failure_is_refused():
    assert refused(type="ping", node="r1", target="10.0.0.9", expect="failure", min_replies=1) == (
        "checks[0]: min_replies only applies to expect: success (expect: failure passes only with 0 replies)")


def test_bgp_route_errors_carry_the_check_location():
    assert refused(type="bgp_route", node="r1", prefix=P4, communities=[]) == (
        "checks[0]: communities must list at least one community")
    assert refused(type="bgp_route", node="r1", prefix=P4, name="edge", without_communities=[]) == (
        "checks[0] ('edge'): without_communities must list at least one community")


def test_timeout_and_hold_errors_carry_the_check_location():
    assert refused(type="ping", node="r1", target="10.0.0.9", timeout=0) == (
        "checks[0]: timeout must be a positive number of seconds (at most 86400), got 0")
    assert refused(type="ping", node="r1", target="10.0.0.9", expect="failure", hold=-1) == (
        "checks[0]: hold must be a positive number of seconds (at most 86400), got -1")
    c = check(type="ping", node="r1", target="10.0.0.9", expect="failure", timeout=12, hold=5)
    assert (c.timeout, c.hold) == (12.0, 5.0)


def test_hold_on_a_check_that_is_not_post_convergence_is_refused():
    assert refused(type="bgp_session", node="r1", neighbor=NB, hold=10) == (
        "checks[0]: hold only applies to post-convergence checks (present: false, a bgp_route attribute, "
        "expect: failure, a state other than established, max or exact); this check passes after 2 consecutive "
        "passing samples, so hold would be ignored")


# --- bgp_prefixes `only` (_only) ---------------------------------------------------------------------------

def test_only_is_canonical_sorted_and_deduplicated():
    assert _only("w", ["192.0.2.0/24", "10.0.0.0/24", "10.0.0.0/24"], "ipv4-unicast") == ["10.0.0.0/24", "192.0.2.0/24"]
    with pytest.raises(ConfigError, match="host bits"):   # red team B-9004: never silently widened
        _only("w", ["10.0.0.5/24"], "ipv4-unicast")
    assert _only("w", ["2001:db8:0::/48"], "ipv6-unicast") == ["2001:db8::/48"]
    assert _only("w", [], "ipv4-unicast") == []
    c = check(type="bgp_prefixes", node="r1", neighbor=NB, only=["10.9.0.0/24", "10.8.0.0/24"])
    assert c.params["only"] == ["10.8.0.0/24", "10.9.0.0/24"]
    c = check(type="bgp_prefixes", node="r1", neighbor=NB, afi="IPv6-Unicast", only=["2001:db8:0::/64"])
    assert c.params["only"] == ["2001:db8::/64"]


def test_only_rejection_messages():
    with pytest.raises(ConfigError, match=r"^w: only applies to afi ipv4-unicast or ipv6-unicast, not evpn$"):
        _only("w", ["10.0.0.0/24"], "evpn")
    with pytest.raises(ConfigError, match=r"^w: only must be a list of prefixes written as strings, got '10.0.0.0/24'$"):
        _only("w", "10.0.0.0/24", "ipv4-unicast")
    with pytest.raises(ConfigError, match=r"^w: only must be a list of prefixes written as strings, got \[167772160\]$"):
        _only("w", [167772160], "ipv4-unicast")
    with pytest.raises(ConfigError,
                       match=r"^w: only: '10.0.0.300/24' does not appear to be an IPv4 or IPv6 network$"):
        _only("w", ["10.0.0.300/24"], "ipv4-unicast")
    with pytest.raises(ConfigError, match=r"^w: only: 2001:db8::/32 is not an ipv4-unicast prefix$"):
        _only("w", ["2001:db8::/32"], "ipv4-unicast")
    with pytest.raises(ConfigError, match=r"^w: only: 10.0.0.0/8 is not an ipv6-unicast prefix$"):
        _only("w", ["10.0.0.0/8"], "ipv6-unicast")


def test_only_errors_carry_the_check_location():
    assert refused(type="bgp_prefixes", node="r1", neighbor=NB, afi="evpn", only=["10.0.0.0/24"]) == (
        "checks[0]: only applies to afi ipv4-unicast or ipv6-unicast, not evpn")
