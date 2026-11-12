"""The edges of the RT-0066 and RT-0053 fixes beyond their oracles (tests/oracles/FP-042-ADDPATH, FP-042-VRFDEV).

RT-0066: with add-path from the peer, FRR's acceptedPrefixCounter counts paths; the driver counts the prefixes the
neighbor's routes listing gives, and a listing that disagrees with the counter is an error, never a count.
RT-0053: in a named VRF, an address on the VRF device itself is the node's own."""
import ipaddress
import json

import pytest

from netdryrun.drivers.base import DriverError
from netdryrun.drivers.frr import FrrDriver, add_path_rx, count_neighbor_prefixes
from netdryrun.drivers.sonic import SonicDriver
from test_verdict_drivers import Lab


def nbr(tx=None, state="Established", counter=4, fam="ipv4Unicast", caps=True):
    entry = {"rxAdvertisedAndReceived": True, "rxAdvertised": True, "rxReceived": True}
    if tx is not None:
        entry["txReceived"] = tx
    n = {"bgpState": state, "addressFamilyInfo": {fam: {"acceptedPrefixCounter": counter}}}
    if caps:
        n["neighborCapabilities"] = {"addPath": {fam: entry}}
    return json.dumps({"10.0.12.2": n})


def listing(prefixes=2, paths_each=2):
    return json.dumps({"routes": {f"10.2{i}.0.0/24": [{"valid": True}] * paths_each for i in range(prefixes)},
                       "totalPaths": prefixes * paths_each})


def test_peer_without_add_path_tx_reads_the_counter_and_nothing_else():
    lab = Lab([("neighbors json", nbr(tx=None, counter=3))])
    n = FrrDriver(lab, "r1").bgp_neighbors().value["10.0.12.2"]
    assert n.prefixes == {"ipv4-unicast": 3} and lab.lines() == ["vtysh -c show bgp neighbors json"]


@pytest.mark.parametrize("cls", [FrrDriver, SonicDriver])
def test_peer_with_add_path_tx_counts_distinct_prefixes(cls):
    lab = Lab([("neighbors json", nbr(tx=True)), ("neighbors 10.0.12.2 routes json", listing(2, 2))])
    n = cls(lab, "r1").bgp_neighbors().value["10.0.12.2"]
    assert n.prefixes == {"ipv4-unicast": 2}
    assert lab.lines()[-1] == "vtysh -c show bgp ipv4 unicast neighbors 10.0.12.2 routes json"


def test_in_a_vrf_the_listing_is_read_in_that_vrf():
    lab = Lab([("neighbors json", nbr(tx=True)), ("neighbors 10.0.12.2 routes json", listing(2, 2))])
    FrrDriver(lab, "r1").bgp_neighbors("red")
    assert lab.lines()[-1] == "vtysh -c show bgp vrf red ipv4 unicast neighbors 10.0.12.2 routes json"


def test_ipv6_family_reads_the_ipv6_listing():
    lab = Lab([("neighbors json", nbr(tx=True, fam="ipv6Unicast")), ("routes json", listing(2, 2))])
    n = FrrDriver(lab, "r1").bgp_neighbors().value["10.0.12.2"]
    assert n.prefixes == {"ipv6-unicast": 2}
    assert lab.lines()[-1] == "vtysh -c show bgp ipv6 unicast neighbors 10.0.12.2 routes json"


def test_unknown_add_path_capability_is_read_as_may_send():
    for text in (nbr(caps=False), json.dumps({"10.0.12.2": {
            "bgpState": "Established", "addressFamilyInfo": {"ipv4Unicast": {"acceptedPrefixCounter": 4}},
            "neighborCapabilities": {"addPath": {}}}})):
        assert add_path_rx(text) == {("10.0.12.2", "10.0.12.2", "ipv4-unicast")}
    assert add_path_rx(nbr(tx="false")) == {("10.0.12.2", "10.0.12.2", "ipv4-unicast")}   # not a clear false


def test_a_session_that_is_not_up_is_not_read():
    assert add_path_rx(nbr(tx=True, state="Active")) == set()
    lab = Lab([("neighbors json", nbr(tx=True, state="Idle (Admin)", counter=0))])
    FrrDriver(lab, "r1").bgp_neighbors()
    assert len(lab.lines()) == 1


def test_a_listing_that_disagrees_with_the_counter_is_an_error():
    for text in (listing(2, 1), listing(3, 2), json.dumps({"routes": {}})):
        with pytest.raises(DriverError):
            count_neighbor_prefixes(text, "cmd", 4)
    lab = Lab([("neighbors json", nbr(tx=True, counter=5)), ("routes json", listing(2, 2))])
    with pytest.raises(DriverError, match="acceptedPrefixCounter is 5"):
        FrrDriver(lab, "r1").bgp_neighbors()


def test_an_unreadable_listing_is_an_error_not_zero():
    for text in ("", "not json", json.dumps({"routes": []}), json.dumps({"routes": {"10.20.0.0/24": {}}}),
                 json.dumps([])):
        with pytest.raises(DriverError):
            count_neighbor_prefixes(text, "cmd", 0 if text == "" else 2)


def test_an_empty_listing_matches_a_zero_counter():
    assert count_neighbor_prefixes("{}", "cmd", 0) == 0
    assert count_neighbor_prefixes(json.dumps({"routes": {}}), "cmd", 0) == 0


def vrf_lab(dev_answer):
    enslaved = json.dumps([{"ifname": "eth2", "master": "RED", "addr_info": [{"local": "10.1.0.1", "prefixlen": 30}]}])
    return Lab([("ip -j addr show vrf RED", enslaved), ("ip -j addr show dev RED", dev_answer)])


def test_a_vrf_device_address_is_the_nodes_own():
    dev = json.dumps([{"ifname": "RED", "addr_info": [{"local": "10.255.1.1", "prefixlen": 32}]}])
    got = FrrDriver(vrf_lab(dev), "r1").local_addresses("RED")
    assert ipaddress.ip_interface("10.255.1.1/32") in got and ipaddress.ip_interface("10.1.0.1/30") in got


def test_an_unreadable_vrf_device_is_an_error():
    for dev in ((1, "", "Device \"RED\" does not exist."), "[{\"addr_info\": [5]}]", "not json"):
        with pytest.raises(DriverError):
            FrrDriver(vrf_lab(dev), "r1").local_addresses("RED")


def test_the_default_vrf_reads_one_command():
    lab = Lab([("ip -j addr", json.dumps([{"ifname": "lo", "addr_info": []}]))])
    FrrDriver(lab, "r1").local_addresses()
    assert lab.lines() == ["ip -j addr"]


# Layer 6 review of the fix (night 3): the edges it named


def test_add_path_in_a_family_without_a_listing_is_a_range_never_the_path_count():
    from netdryrun.checks import _counted
    lab = Lab([("neighbors json", nbr(tx=True, fam="l2VpnEvpn", counter=4))])
    n = FrrDriver(lab, "r1").bgp_neighbors().value["10.0.12.2"]
    assert n.prefixes["evpn"] == 1 and n.prefixes_upto["evpn"] == 4 and "evpn" in n.prefixes_unread
    assert len(lab.lines()) == 1                                    # no listing read for EVPN
    ok, detail, _ = _counted(n, "evpn", n.prefixes["evpn"], 4, None, [])     # min 4: 1 to 4 prefixes
    assert ok is False and "error" in str(detail)                    # no verdict, never a pass
    ok, _, _ = _counted(n, "evpn", n.prefixes["evpn"], 0, 10, [])           # every value in range is within
    assert ok is True


def test_a_dual_stack_session_reads_each_flagged_family():
    text = json.dumps({"10.0.12.2": {
        "bgpState": "Established",
        "addressFamilyInfo": {"ipv4Unicast": {"acceptedPrefixCounter": 4}, "ipv6Unicast": {"acceptedPrefixCounter": 6}},
        "neighborCapabilities": {"addPath": {"ipv4Unicast": {"txReceived": True}, "ipv6Unicast": {"txReceived": True}}}}})
    lab = Lab([("neighbors json", text), ("ipv4 unicast neighbors 10.0.12.2 routes", listing(2, 2)),
               ("ipv6 unicast neighbors 10.0.12.2 routes", listing(3, 2))])
    n = FrrDriver(lab, "r1").bgp_neighbors().value["10.0.12.2"]
    assert n.prefixes == {"ipv4-unicast": 2, "ipv6-unicast": 3}


def test_an_unnumbered_neighbor_is_named_by_its_interface():
    text = json.dumps({"eth1": {"bgpState": "Established",
                                "addressFamilyInfo": {"ipv4Unicast": {"acceptedPrefixCounter": 4}},
                                "neighborCapabilities": {"addPath": {"ipv4Unicast": {"txReceived": True}}}}})
    lab = Lab([("neighbors json", text), ("neighbors eth1 routes json", listing(2, 2))])
    FrrDriver(lab, "r1").bgp_neighbors()
    assert lab.lines()[-1] == "vtysh -c show bgp ipv4 unicast neighbors eth1 routes json"


def test_history_and_removed_paths_are_not_counted():
    routes = {"10.20.0.0/24": [{"valid": True}, {"history": True}],
              "10.21.0.0/24": [{"valid": True}, {"valid": True}],
              "10.22.0.0/24": [{"removed": True}]}
    assert count_neighbor_prefixes(json.dumps({"routes": routes}), "cmd", 3) == 2


def test_sonic_in_a_vrf_reads_the_listing_in_that_vrf():
    lab = Lab([("neighbors json", nbr(tx=True)), ("routes json", listing(2, 2))])
    n = SonicDriver(lab, "r1").bgp_neighbors("red").value["10.0.12.2"]
    assert n.prefixes == {"ipv4-unicast": 2}
    assert lab.lines()[-1] == "vtysh -c show bgp vrf red ipv4 unicast neighbors 10.0.12.2 routes json"
