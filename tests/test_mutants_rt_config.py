"""Mutation-survivor tests for config validation: peers, ping targets, only, bgp_route regex, nodes.

Each test pins exact messages and values so message-text and boolean-operator mutants cannot survive."""
from __future__ import annotations

import re

import pytest

from netdryrun.config import (AS_PATH_PROBES, ConfigError, DRIVER_NAMES, _is_network, _only, _ping_target,
                              _validate_bgp_route, _validate_check, _validate_nodes, _validate_peers)

W = "w.peers"


def refused(fn, *args):
    with pytest.raises(ConfigError) as ei:
        fn(*args)
    return str(ei.value)


def peers(p):
    return refused(_validate_peers, W, "r1", p)


# ------------------------------------------------------------------------------------------------ _validate_peers

MAP_MSG = "w.peers: must be a mapping of neighbor address (or <vrf>/<address>) to settings"


@pytest.mark.parametrize("p", [{}, [], "10.0.0.1", 5, None])
def test_peers_must_be_a_non_empty_mapping(p):
    assert peers(p) == MAP_MSG


@pytest.mark.parametrize("key", ["", "  ", 5, None])
def test_peer_key_must_be_a_non_empty_string(key):
    assert peers({key: {"eor": "not_sent"}}) == f"{W}.{key}: a peer is named by its address, or <vrf>/<address>"


def test_a_network_key_is_not_split_at_its_slash():
    assert peers({"10.0.0.1/32": {"eor": "not_sent"}}) == (
        f"{W}.10.0.0.1/32: '10.0.0.1/32' is not an IP address (name a peer by its address, or <vrf>/<address>)")


def test_a_vrf_peer_splits_at_the_last_slash():
    assert peers({"a/b/10.0.0.1": {"eor": "not_sent"}}) == f"{W}.a/b/10.0.0.1: 'a/b' is not a VRF name"
    assert _validate_peers(W, "r1", {"red/10.0.0.1": {"eor": "not_sent"}}) == {("r1", "red", "10.0.0.1")}
    assert _validate_peers(W, "r1", {"/10.0.0.1": {"eor": "not_sent"}}) == {("r1", "default", "10.0.0.1")}


def test_a_bare_non_address_is_refused_with_its_text():
    assert peers({"nope": {"eor": "not_sent"}}) == (
        f"{W}.nope: 'nope' is not an IP address (name a peer by its address, or <vrf>/<address>)")
    assert peers({"red/nope": {"eor": "not_sent"}}) == (
        f"{W}.red/nope: 'nope' is not an IP address (name a peer by its address, or <vrf>/<address>)")


@pytest.mark.parametrize("s", [{}, [], "not_sent", None, 3])
def test_peer_settings_must_be_a_non_empty_mapping(s):
    assert peers({"10.0.0.1": s}) == f"{W}.10.0.0.1: must be a mapping, e.g. {{eor: not_sent}}"


def test_unknown_peer_setting_is_named_with_its_location():
    assert peers({"10.0.0.1": {"eor": "not_sent", "x": 1}}) == (
        f"{W}.10.0.0.1: unknown keys ['x']; allowed: eor")


def test_eor_value_is_checked_and_echoed():
    assert peers({"10.0.0.1": {"eor": "sent"}}) == (
        f"{W}.10.0.0.1.eor: the only value is not_sent (the peer never sends End-of-RIB), got 'sent'")
    assert peers({"10.0.0.1": {"eor": None}}) == (
        f"{W}.10.0.0.1.eor: the only value is not_sent (the peer never sends End-of-RIB), got None")


def test_bad_vrf_name_is_refused_with_its_text():
    assert peers({"red!/10.0.0.1": {"eor": "not_sent"}}) == f"{W}.red!/10.0.0.1: 'red!' is not a VRF name"


def test_scoped_address_is_refused_with_its_text():
    assert peers({"fe80::1%eth0": {"eor": "not_sent"}}) == (
        f"{W}.fe80::1%eth0: name the peer by its address without a scope (the gate keys sessions that way)")


# ------------------------------------------------------------------------------------------------ _is_network

def test_is_network_accepts_networks_with_host_bits_and_refuses_text():
    assert _is_network("10.0.0.0/8") is True
    assert _is_network("10.0.0.1/24") is True
    assert _is_network("2001:db8::1/64") is True
    assert _is_network("10.0.0.1") is True
    assert _is_network("red/10.0.0.1") is False
    assert _is_network("nope") is False


# ------------------------------------------------------------------------------------------------ _only

def test_only_host_bits_get_the_dedicated_message():
    assert refused(_only, "w", ["10.1.1.77/24"], "ipv4-unicast") == (
        "w: only: 10.1.1.77/24 has host bits set; write the network, 10.1.1.0/24")
    assert refused(_only, "w", ["2001:db8::1/64"], "ipv6-unicast") == (
        "w: only: 2001:db8::1/64 has host bits set; write the network, 2001:db8::/64")
    assert _only("w", ["10.1.1.0/24", "10.0.0.0/8"], "ipv4-unicast") == ["10.0.0.0/8", "10.1.1.0/24"]


# ------------------------------------------------------------------------------------------------ _ping_target

def ping(target, source=None):
    p = {"target": target}
    if source:
        p["source"] = source
    return refused(_ping_target, "w", p)


def why(target, text):
    assert ping(target) == (f"w: target {target} is {text}: a ping to it never leaves the node, so it "
                            "says nothing about the network")


def test_ping_target_refusals_each_have_their_exact_reason():
    why("0.0.0.0", "unspecified")
    why("::", "unspecified")
    why("127.0.0.1", "a loopback address")
    why("::1", "a loopback address")
    why("224.0.0.1", "a multicast address")
    why("ff02::1", "a multicast address")
    why("255.255.255.255", "the limited broadcast address")


def test_ping_target_scope_is_stripped_before_the_checks():
    why("::1%lo", "a loopback address")
    why("ff02::1%eth0", "a multicast address")
    assert ping("fe80::1%eth0", "fe80::1") == (
        "w: target fe80::1%eth0 is the source address: the node pings itself")
    assert ping("fe80::1", "fe80::1%eth0") == "w: target fe80::1 is the source address: the node pings itself"
    assert ping("10.0.0.1", "10.0.0.1") == "w: target 10.0.0.1 is the source address: the node pings itself"


def test_ping_target_ok_cases_return_none():
    assert _ping_target("w", {"target": "10.0.0.2"}) is None
    assert _ping_target("w", {"target": "10.0.0.2", "source": "10.0.0.1"}) is None
    assert _ping_target("w", {"target": "fe80::2%eth0", "source": "fe80::1%eth0"}) is None


def test_validate_check_passes_its_location_to_the_ping_target_check():
    with pytest.raises(ConfigError) as ei:
        _validate_check(0, {"type": "ping", "node": "r1", "target": "127.0.0.1"}, 30)
    assert str(ei.value) == ("checks[0]: target 127.0.0.1 is a loopback address: a ping to it never leaves the "
                             "node, so it says nothing about the network")


# ------------------------------------------------------------------------------------------------ _validate_bgp_route

def test_as_path_regex_matching_everything_lists_every_probe():
    learned = [p for p in AS_PATH_PROBES if p]
    listed = ", ".join(repr(x) for x in learned)
    assert refused(_validate_bgp_route, "w", {"as_path_regex": ".*"}) == (
        f"w: as_path_regex '.*' matches every AS path (it matched all of {listed}), so the check would assert "
        "nothing")


# ------------------------------------------------------------------------------------------------ _validate_nodes

def test_node_name_must_be_a_string():
    assert refused(_validate_nodes, "w", {"nodes": {5: {"driver": "frr"}}}) == "w: nodes.5: node names must be strings"
    assert refused(_validate_nodes, "w", {"nodes": {"": {"driver": "frr"}}}) == "w: nodes.: node names must be strings"


def test_unknown_driver_lists_every_driver():
    assert refused(_validate_nodes, "w", {"nodes": {"r1": {"driver": "zzz"}}}) == (
        f"w: nodes.r1.driver: unknown driver 'zzz'; use one of {', '.join(DRIVER_NAMES)}")


def test_peers_of_several_nodes_accumulate_and_errors_carry_the_node_location():
    data = {"nodes": {"r1": {"peers": {"10.0.0.1": {"eor": "not_sent"}}},
                      "r2": {"peers": {"10.0.0.2": {"eor": "not_sent"}}}}}
    drivers, setup, eor = _validate_nodes("w", data)
    assert eor == {("r1", "default", "10.0.0.1"), ("r2", "default", "10.0.0.2")}
    assert refused(_validate_nodes, "w", {"nodes": {"r1": {"peers": {"nope": {"eor": "not_sent"}}}}}) == (
        "w: nodes.r1.peers.nope: 'nope' is not an IP address (name a peer by its address, or <vrf>/<address>)")


@pytest.mark.parametrize("v", ["", 5, None])
def test_as_path_regex_that_isnt_a_non_empty_string_is_refused_exactly(v):
    from netdryrun.config import _validate_check
    with pytest.raises(ConfigError, match=r"^checks\[0\]: as_path_regex must be a non-empty regular expression "
                                          r"string, got " + re.escape(repr(v)) + "$"):
        _validate_check(0, {"type": "bgp_route", "node": "r1", "prefix": "10.0.0.0/8", "as_path_regex": v}, 30)


def test_a_nodes_error_names_the_config_file(tmp_path):
    from netdryrun.config import load
    (tmp_path / "t.clab.yml").write_text("name: t\ntopology: {nodes: {r1: {kind: linux}}}\n")
    cfg = tmp_path / "netdryrun.yml"
    cfg.write_text("lab: t.clab.yml\nnodes: {r1: {driver: nope}}\n"
                   "checks: [{type: route, node: r1, prefix: 10.0.0.0/8, present: false}]\n")
    with pytest.raises(ConfigError) as e:
        load(cfg)
    assert str(e.value).startswith(f"{cfg}: nodes.r1.driver: unknown driver 'nope'")
