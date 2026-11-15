"""Kill tests for the surviving `drivers.frr` / `drivers.base.unicast_unread` mutants of the 0.4.2 mutation run
(83478f2). Every input here is DERIVED: built in the test from the shapes FRR 10.4.1 prints (see the captures in
tests/fixtures), and some deliberately not what a device prints, to pin the parser's fail-closed edges."""
import ipaddress
import json

import pytest

from netdryrun.drivers.base import DriverError, unicast_unread
from netdryrun.drivers.frr import FrrDriver, add_path_rx, count_neighbor_prefixes, gr_stale_window
from netdryrun.lab import ExecResult


class Lab:
    """Answers each command with the first rule whose needle is in the command line; anything else is a test failure."""

    def __init__(self, rules):
        self.rules, self.calls = list(rules), []

    def exec(self, node, cmd, timeout=60, input=None):
        line = " ".join(cmd)
        self.calls.append(line)
        for needle, answer in self.rules:
            if needle in line:
                return ExecResult(list(cmd), 0, answer, "")
        raise AssertionError(f"unexpected command: {line}")


# ------------------------------------------------------------------ derived neighbor and listing shapes

PENDING = {"fBit": True, "endOfRibStatus": {"endOfRibRecv": False, "endOfRibSend": True}}


def gr(local="Helper*", **blocks):
    return {"localGrMode": local, "remoteGrMode": "Restart", "endOfRibRecv": {}, **blocks}


def nbr(families, state="Established", addpath=None, grinfo=None):
    """One neighbor of `show bgp neighbors json`: families {frrAfi: acceptedPrefixCounter}, addpath {frrAfi: entry}."""
    n = {"bgpState": state,
         "addressFamilyInfo": {afi: {"acceptedPrefixCounter": c} for afi, c in families.items()}}
    if addpath is not None:
        n["neighborCapabilities"] = {"addPath": addpath}
    if grinfo is not None:
        n["gracefulRestartInfo"] = grinfo
    return n


def listing(prefixes=2, paths_each=2, path=None):
    p = path if path is not None else {"valid": True}
    return json.dumps({"routes": {f"10.2{i}.0.0/24": [p] * paths_each for i in range(prefixes)},
                       "totalPaths": prefixes * paths_each})


TX = {"txReceived": True}


# ------------------------------------------------------------------ gr_stale_window

def test_gr_mode_is_disable_only_after_stripping_the_star():
    """Kills gr_stale_window_19 (rstrip("XX*XX")): "DisableX" is not Disable, so a pending family stays unsettled."""
    info = nbr({"ipv4Unicast": 4}, grinfo=gr(local="DisableX", ipv4Unicast=PENDING))
    assert "ipv4-unicast" in gr_stale_window("10.0.0.1", info, {"ipv4-unicast": 4})


def test_a_family_without_a_gr_block_doesnt_stop_the_scan():
    """Kills gr_stale_window_36 (continue -> break): the first family has no GR block, the second is pending."""
    info = nbr({"ipv4Unicast": 4, "ipv6Unicast": 4}, grinfo=gr(ipv6Unicast=PENDING))
    assert set(gr_stale_window("10.0.0.1", info, {"ipv4-unicast": 4, "ipv6-unicast": 4})) == {"ipv6-unicast"}


def test_an_unnamed_family_keeps_its_own_name():
    """Kills gr_stale_window_39/40/41 (AFI_NAMES.get(afi) without the default): a family this driver doesn't rename
    (labeled unicast) is marked unsettled under its own name, never under None."""
    info = nbr({"ipv4LabeledUnicast": 3}, grinfo=gr(ipv4LabeledUnicast=PENDING))
    out = gr_stale_window("10.0.0.1", info, {"ipv4LabeledUnicast": 3})
    assert set(out) == {"ipv4LabeledUnicast"}


def test_an_unknown_gr_block_doesnt_stop_the_scan():
    """Kills gr_stale_window_59 (continue -> break): an unreadable block, then a pending family: both unsettled."""
    info = nbr({"ipv4Unicast": 4, "ipv6Unicast": 4}, grinfo=gr(ipv4Unicast="junk", ipv6Unicast=PENDING))
    assert set(gr_stale_window("10.0.0.1", info, {"ipv4-unicast": 4, "ipv6-unicast": 4})) == {
        "ipv4-unicast", "ipv6-unicast"}


def test_a_family_with_fbit_clear_doesnt_stop_the_scan():
    """Kills gr_stale_window_73 (continue -> break): F-bit clear in the first family, pending in the second."""
    info = nbr({"ipv4Unicast": 4, "ipv6Unicast": 4},
               grinfo=gr(ipv4Unicast={"fBit": False, "endOfRibStatus": {"endOfRibRecv": False}}, ipv6Unicast=PENDING))
    assert set(gr_stale_window("10.0.0.1", info, {"ipv4-unicast": 4, "ipv6-unicast": 4})) == {"ipv6-unicast"}


def test_fbit_set_without_eor_status_is_unsettled_not_a_crash():
    """Kills gr_stale_window_81 (status.get on a non-dict): F-bit set and no endOfRibStatus reads as unsettled."""
    info = nbr({"ipv4Unicast": 4}, grinfo=gr(ipv4Unicast={"fBit": True}))
    out = gr_stale_window("10.0.0.1", info, {"ipv4-unicast": 4})
    assert "ipv4-unicast" in out and "can't be read as received" in out["ipv4-unicast"]


# ------------------------------------------------------------------ add_path_rx

def test_add_path_rx_reads_the_first_word_of_the_state():
    """Kills add_path_rx_19 (split()[:2]): the FSM state is the first word, as parse_bgp_neighbors reads it."""
    text = json.dumps({"10.0.0.1": nbr({"ipv4Unicast": 4}, state="Established (derived)", addpath={"ipv4Unicast": TX})})
    assert add_path_rx(text) == {("10.0.0.1", "10.0.0.1", "ipv4-unicast")}


def test_add_path_rx_goes_past_a_session_that_is_down():
    """Kills add_path_rx_23 (continue -> break): an idle neighbor listed first, an add-path one after it."""
    text = json.dumps({"10.0.0.1": nbr({}, state="Idle"),
                       "10.0.0.2": nbr({"ipv4Unicast": 4}, addpath={"ipv4Unicast": TX})})
    assert add_path_rx(text) == {("10.0.0.2", "10.0.0.2", "ipv4-unicast")}


def test_add_path_tx_advertised_and_received_alone_flags_the_session():
    """Kills add_path_rx_58/59/60 (the txAdvertisedAndReceived key renamed): FRR prints that key alone, without
    txReceived, when add-path TX is both advertised and received; the peer then sends several paths per prefix."""
    text = json.dumps({"10.0.0.1": nbr({"ipv4Unicast": 4}, addpath={"ipv4Unicast": {"txAdvertisedAndReceived": True}})})
    assert add_path_rx(text) == {("10.0.0.1", "10.0.0.1", "ipv4-unicast")}


def test_add_path_rx_keeps_an_unnamed_familys_own_name():
    """Kills add_path_rx_65/66/67 (AFI_NAMES.get(afi) without the default): the family is named as FRR names it."""
    text = json.dumps({"10.0.0.1": nbr({"ipv4LabeledUnicast": 4}, addpath={"ipv4LabeledUnicast": TX})})
    assert add_path_rx(text) == {("10.0.0.1", "10.0.0.1", "ipv4LabeledUnicast")}


# ------------------------------------------------------------------ count_neighbor_prefixes

def test_a_listing_without_routes_is_unexpected_even_for_a_zero_counter():
    """Kills count_neighbor_prefixes_19 (default {} for any answer): a non-empty answer without `routes` is output
    this parser doesn't know, never 0 prefixes."""
    with pytest.raises(DriverError):
        count_neighbor_prefixes(json.dumps({"totalPaths": 0}), "cmd", 0)


# ------------------------------------------------------------------ FrrDriver.bgp_neighbors

def test_an_ambiguous_link_local_kept_down_is_not_refined():
    """Kills bgp_neighbors_38 (`or` -> `and`): two sessions to fe80::1 on two interfaces, the established one with
    add-path; the kept (down) one lists no family, so no listing is read and nothing raises."""
    text = json.dumps({"fe80::1%eth1": nbr({"ipv4Unicast": 4}, addpath={"ipv4Unicast": TX}),
                       "fe80::1%eth2": nbr({}, state="Idle")})
    lab = Lab([("neighbors json", text)])
    n = FrrDriver(lab, "r1").bgp_neighbors().value["fe80::1"]
    assert n.state == "idle" and lab.calls == ["vtysh -c show bgp neighbors json"]


def test_a_gr_window_neighbor_doesnt_stop_the_add_path_refinement():
    """Kills bgp_neighbors_42 (continue -> break): 10.0.0.1 is in a graceful-restart window (count unread), 10.0.0.2
    has add-path with 2 prefixes x 2 paths: its count is 2, never the counter's 4 paths."""
    text = json.dumps({
        "10.0.0.1": nbr({"ipv4Unicast": 4}, addpath={"ipv4Unicast": TX}, grinfo=gr(ipv4Unicast=PENDING)),
        "10.0.0.2": nbr({"ipv4Unicast": 4}, addpath={"ipv4Unicast": TX})})
    lab = Lab([("neighbors json", text), ("neighbors 10.0.0.2 routes json", listing(2, 2))])
    v = FrrDriver(lab, "r1").bgp_neighbors().value
    assert "ipv4-unicast" in v["10.0.0.1"].prefixes_unread
    assert v["10.0.0.2"].prefixes == {"ipv4-unicast": 2}


def test_an_evpn_add_path_family_doesnt_stop_the_refinement():
    """Kills bgp_neighbors_66 (continue -> break): add-path in EVPN (a range) and in IPv4 unicast (listing read)."""
    text = json.dumps({"10.0.0.1": nbr({"ipv4Unicast": 4, "l2VpnEvpn": 4},
                                       addpath={"ipv4Unicast": TX, "l2VpnEvpn": TX})})
    lab = Lab([("neighbors json", text), ("neighbors 10.0.0.1 routes json", listing(2, 2))])
    n = FrrDriver(lab, "r1").bgp_neighbors().value["10.0.0.1"]
    assert n.prefixes["ipv4-unicast"] == 2 and n.prefixes_upto["evpn"] == 4


def test_a_stale_listing_doesnt_stop_the_refinement():
    """Kills bgp_neighbors_86 (continue -> break): 10.0.0.1's listing has stale paths (unread), 10.0.0.2 is counted."""
    text = json.dumps({"10.0.0.1": nbr({"ipv4Unicast": 4}, addpath={"ipv4Unicast": TX}),
                       "10.0.0.2": nbr({"ipv4Unicast": 4}, addpath={"ipv4Unicast": TX})})
    lab = Lab([("neighbors json", text),
               ("neighbors 10.0.0.1 routes json", listing(2, 2, path={"valid": True, "stale": True})),
               ("neighbors 10.0.0.2 routes json", listing(2, 2))])
    v = FrrDriver(lab, "r1").bgp_neighbors().value
    assert "ipv4-unicast" in v["10.0.0.1"].prefixes_unread
    assert v["10.0.0.2"].prefixes == {"ipv4-unicast": 2}


@pytest.mark.parametrize("answer", [
    "[]",                                                                    # listed_stale_8: not an object
    json.dumps({"routes": {"10.20.0.0/24": 5}}),                             # listed_stale_17: paths not a list
    json.dumps({"routes": {"10.20.0.0/24": [{"stale": "yes"}] * 4}}),        # listed_stale_28: flag not a boolean
])
def test_an_unreadable_listing_is_a_driver_error(answer):
    """Kills listed_stale_8/17/28: an unreadable add-path listing is a DriverError (a named read failure), never an
    AttributeError, TypeError or KeyError escaping the driver."""
    text = json.dumps({"10.0.0.1": nbr({"ipv4Unicast": 4}, addpath={"ipv4Unicast": TX})})
    lab = Lab([("neighbors json", text), ("neighbors 10.0.0.1 routes json", answer)])
    with pytest.raises(DriverError):
        FrrDriver(lab, "r1").bgp_neighbors()


# ------------------------------------------------------------------ base.unicast_unread

def test_a_family_naming_both_versions_blocks():
    """Kills unicast_unread_9/10 (own name mangled): a name with both ipv4 and ipv6 isn't "the other version only"."""
    assert unicast_unread("ipv4-unicast", ["ipv6ipv4Mixed"]) == ["ipv6ipv4Mixed"]


def test_separators_in_a_family_name_are_dropped():
    """Kills unicast_unread_30/32 (separators kept or replaced): "ipv4Label-edUnicast" is labeled unicast."""
    assert unicast_unread("ipv4-unicast", ["ipv4-unicast", "ipv4Label-edUnicast"]) == ["ipv4Label-edUnicast"]


def test_an_other_version_family_doesnt_stop_the_scan():
    """Kills unicast_unread_38 (continue -> break): FRR lists IPv4 families first; ipv6 labeled unicast still blocks
    an ipv6-unicast count."""
    assert unicast_unread("ipv6-unicast", ["ipv4LabeledUnicast", "ipv6LabeledUnicast"]) == ["ipv6LabeledUnicast"]


def test_an_unlabeled_family_doesnt_stop_the_scan():
    """Kills unicast_unread_44 (continue -> break): multicast before labeled unicast, the unicast count listed."""
    assert unicast_unread("ipv4-unicast", ["ipv4-unicast", "ipv4Multicast", "ipv4LabeledUnicast"]) == [
        "ipv4LabeledUnicast"]


# ------------------------------------------------------------------ FrrDriver.local_addresses

def test_the_vrf_device_address_is_kept_whatever_its_master():
    """Kills local_addresses_64 (skip_enslaved=True on the VRF device): the device's own address is the node's,
    read without the enslaved filter (derived: a master key on the device)."""
    dev = json.dumps([{"ifname": "RED", "master": "x", "addr_info": [{"local": "10.255.1.1", "prefixlen": 32}]}])
    lab = Lab([("ip -j addr show vrf RED", "[]"), ("ip -j addr show dev RED", dev)])
    assert ipaddress.ip_interface("10.255.1.1/32") in FrrDriver(lab, "r1").local_addresses("RED")
