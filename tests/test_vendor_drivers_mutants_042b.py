"""Kill tests for surviving mutants in the EOS, SR Linux add-path code (mutation run on 83478f2, group `vendors`).

Every input below is derived: built in this file from the shapes cEOS 4.36.3M and SR Linux 26.7.2 print (see
tests/test_eos_addpath_042.py and tests/test_srl_addpath_042.py), not new fixture files."""
from __future__ import annotations

import json

import pytest

from netdryrun.drivers.base import BgpNeighbor
from netdryrun.drivers.eos import EosDriver, parse_eos_add_path_off
from netdryrun.drivers.srlinux import SrlDriver, _count_add_path_prefixes, srl_add_path_rx
from netdryrun.lab import ExecResult


class Lab:
    """Answers each command with the first rule whose needle is in the command line; records every call."""

    def __init__(self, rules):
        self.rules, self.calls = list(rules), []

    def exec(self, node, cmd, timeout=60, input=None):
        line = " ".join(cmd)
        self.calls.append(line)
        for needle, answer in self.rules:
            if needle in line:
                rc, out = answer if isinstance(answer, tuple) else (0, answer)
                return ExecResult(list(cmd), rc, out, "")
        raise AssertionError(f"unexpected command: {line}")


# ---------------------------------------------------------------- EOS -------------------------------------------------

def eos_summary(vrf="default", **peers):
    return json.dumps({"vrfs": {vrf: {"peers": peers}}})


def eos_peer(addr, vrf="default", caps="default", **families):
    """Derived `show ip|ipv6 bgp neighbors <addr> vrf <vrf> | json`: receivingAddPaths.enabled per family. caps=None
    leaves out neighborCapabilities; caps={} gives it without addPathsCaps."""
    peer = {"peerAddress": addr}
    if caps == "default":
        peer["neighborCapabilities"] = {"addPathsCaps": {
            f: {"receivingAddPaths": {"receiveCapabilityAdvertised": True, "sendCapabilityReceived": on, "enabled": on}}
            for f, on in families.items()}}
    elif caps is not None:
        peer["neighborCapabilities"] = caps
    return json.dumps({"vrfs": {vrf: {"peerList": [peer]}}})


def eos_read(v4_peers, v6_peers=None, rules=()):
    lab = Lab([("ipv6 bgp summary", eos_summary(**(v6_peers or {}))), ("ip bgp summary", eos_summary(**v4_peers)),
               *rules])
    return EosDriver(lab, "ceos1").bgp_neighbors("default").value, lab


def test_eos_two_paths_are_a_range_of_one_to_two_prefixes():
    """mutant 8 (`> 2`): 2 add-path paths read as exactly 2 prefixes, so `min: 2` passed on one prefix."""
    n, lab = eos_read({"10.0.200.2": {"peerState": "Established", "prefixAccepted": 2}},
                      rules=[("bgp neighbors 10.0.200.2", eos_peer("10.0.200.2", ipv4Unicast=True))])
    got = n["10.0.200.2"]
    assert (got.prefixes["ipv4-unicast"], got.prefixes_upto["ipv4-unicast"]) == (1, 2)
    assert lab.calls[-1] == "Cli -p 15 -c show ip bgp neighbors 10.0.200.2 vrf default | json"


def test_eos_a_skipped_peer_does_not_end_the_add_path_reads():
    """mutant 14 (`continue` -> `break`): a first peer with one path (or down) stopped the loop, so a later peer's
    path count was read as its prefix count."""
    peers = {"10.0.200.1": {"peerState": "Established", "prefixAccepted": 1},
             "10.0.200.3": {"peerState": "Active", "prefixAccepted": 0},
             "10.0.200.2": {"peerState": "Established", "prefixAccepted": 4}}
    n, _ = eos_read(peers, rules=[("bgp neighbors 10.0.200.2", eos_peer("10.0.200.2", ipv4Unicast=True))])
    assert list(n)[-1] == "10.0.200.2"
    assert (n["10.0.200.2"].prefixes["ipv4-unicast"], n["10.0.200.2"].prefixes_upto["ipv4-unicast"]) == (1, 4)
    assert n["10.0.200.1"].prefixes["ipv4-unicast"] == 1 and n["10.0.200.1"].prefixes_upto == {}


@pytest.mark.parametrize("peer", ["fe80::2%Et1", "fe80::2%", "fe80::2%Et1%x"])
def test_eos_link_local_peer_is_read_with_the_ipv6_command(peer):
    """mutants 17, 18 (the `%` split): the address is read up to its `%`. Python reads `fe80::2%Et1` as a scoped
    IPv6 address either way, but an empty or doubled scope (`fe80::2%`, `fe80::2%Et1%x`) isn't one, so the mutants
    fell back to IPv4 and read the peer's add-path state with `show ip bgp neighbors`."""
    n, lab = eos_read({}, {peer: {"peerState": "Established", "prefixAccepted": 3}},
                      rules=[("ipv6 bgp neighbors", eos_peer(peer, ipv6Unicast=True))])
    assert lab.calls[-1] == f"Cli -p 15 -c show ipv6 bgp neighbors {peer} vrf default | json"
    (got,) = n.values()
    assert (got.prefixes["ipv6-unicast"], got.prefixes_upto["ipv6-unicast"]) == (1, 3)


@pytest.mark.parametrize("caps", [None, {}, {"addPathsCaps": None}])
def test_eos_add_path_off_without_capabilities_is_no_family_never_a_crash(caps):
    """mutants 41, 49 of parse_eos_add_path_off (`or True`): a peer without neighborCapabilities or addPathsCaps
    raised AttributeError (not a DriverError, so bgp_neighbors crashed) instead of giving no family."""
    assert parse_eos_add_path_off(eos_peer("10.0.200.2", caps=caps), "default", "10.0.200.2") == set()
    n, _ = eos_read({"10.0.200.2": {"peerState": "Established", "prefixAccepted": 4}},
                    rules=[("bgp neighbors 10.0.200.2", eos_peer("10.0.200.2", caps=caps))])
    assert (n["10.0.200.2"].prefixes["ipv4-unicast"], n["10.0.200.2"].prefixes_upto["ipv4-unicast"]) == (1, 4)


# ---------------------------------------------------------------- SR Linux --------------------------------------------

def srl_nbr(peer, received=4, caps=("ADD_PATH",), state="established", receive=True, fam="ipv4-unicast"):
    n = {"peer-address": peer, "session-state": state,
         "afi-safi": [{"afi-safi-name": fam, "oper-state": "up", "received-routes": received, "rejected-routes": 0,
                       "add-paths": {"receive": receive, "send": False}}]}
    if caps is not None:
        n["received-capabilities"] = ["ROUTE_REFRESH", "MP_BGP", *caps]
    return n


def srl_rib(*rows):
    """rows: (prefix, invalid-reason or None, neighbor)."""
    out = []
    for i, (pfx, reason, peer) in enumerate(rows):
        r = {"prefix": pfx, "neighbor": peer, "origin-protocol": "bgp", "path-id": i, "valid-route": reason is None}
        if reason is not None:
            r["invalid-reason"] = reason
        out.append(r)
    return json.dumps({"local-rib": {"route": out}})


@pytest.mark.parametrize("first", [
    srl_nbr("10.0.0.1", state="active"),       # mutant 26: a session that isn't up ended the loop
    srl_nbr("10.0.0.1", caps=()),               # mutant 35: a peer that didn't offer add-path ended the loop
])
def test_srl_a_skipped_neighbor_does_not_end_the_add_path_scan(first):
    """srl_add_path_rx mutants 26, 35 (`continue` -> `break`): the neighbors after a skipped one were never flagged,
    so their received-routes (a count of paths) read as prefixes: 2 prefixes with 2 paths each passed `min: 4`."""
    text = json.dumps({"neighbor": [first, srl_nbr("10.0.0.2")]})
    assert srl_add_path_rx(text) == {("10.0.0.2", "ipv4-unicast")}
    rib = srl_rib(("10.40.0.0/24", None, "10.0.0.2"), ("10.40.0.0/24", None, "10.0.0.2"),
                  ("10.41.0.0/24", None, "10.0.0.2"), ("10.41.0.0/24", None, "10.0.0.2"))
    lab = Lab([("protocols bgp neighbor", text), ("bgp-rib afi-safi ipv4-unicast", rib)])
    got = SrlDriver(lab, "srl1").bgp_neighbors().value["10.0.0.2"]
    assert got.prefixes == {"ipv4-unicast": 2} and got.prefixes_upto == {}


def test_srl_no_unsure_path_clears_an_earlier_range():
    """_count_add_path_prefixes mutants 21, 24 (`pop(None)`): with no unsure path the count is exact, but the range
    (and its reason) set earlier stayed, so a settled count read as a range and `record` left it out."""
    n = BgpNeighbor("10.0.0.2", "established", prefixes={"ipv4-unicast": 3}, prefixes_upto={"ipv4-unicast": 5},
                    prefixes_upto_why={"ipv4-unicast": "earlier range"})
    _count_add_path_prefixes(n, "ipv4-unicast", ["10.40.0.0/24", "10.40.0.0/24", "10.41.0.0/24", "10.41.0.0/24"], [])
    assert n.prefixes == {"ipv4-unicast": 2}
    assert n.prefixes_upto == {} and n.prefixes_upto_why == {}


def test_srl_a_range_above_one_path_is_counted_from_the_rib():
    """_drop_looped mutant 40 (`prefixes_upto.get(None, ...)`): where unsure paths leave a count of 1 to 3 paths, the
    range was left a count of paths instead of being counted from the RIB (1 prefix)."""
    peer = "10.0.0.2"
    text = json.dumps({"neighbor": [srl_nbr(peer, received=3)]})
    rib = srl_rib(("10.40.0.0/24", None, peer), ("10.40.0.0/24", {"next-hop-unresolved": True}, peer),
                  ("10.40.0.0/24", {"next-hop-unresolved": True}, peer))
    lab = Lab([("protocols bgp neighbor", text), ("bgp-rib afi-safi ipv4-unicast", rib)])
    got = SrlDriver(lab, "srl1").bgp_neighbors().value[peer]
    assert got.prefixes == {"ipv4-unicast": 1}
    assert got.prefixes_upto == {"ipv4-unicast": 1}


def test_srl_add_path_flag_for_a_family_the_neighbor_has_no_count_in():
    """_drop_looped mutants 45, 47 (`n.prefixes.get(afi, None)`): a neighbor flagged for add-path in a family it has
    no count in (another neighbor's family) compared None > 1 and raised TypeError; it has nothing to count."""
    a = BgpNeighbor("10.0.0.1", "established", prefixes={"ipv4-unicast": 0})
    b = BgpNeighbor("2001:db8::2", "established", prefixes={"ipv6-unicast": 0})
    neighbors = {"10.0.0.1": a, "2001:db8::2": b}
    lab = Lab([("bgp-rib afi-safi", "{}")])
    SrlDriver(lab, "srl1")._drop_looped("default", neighbors, [], {("10.0.0.1", "ipv6-unicast")})
    assert a.prefixes == {"ipv4-unicast": 0} and b.prefixes == {"ipv6-unicast": 0}
    assert a.prefixes_upto == {} and b.prefixes_upto == {}
