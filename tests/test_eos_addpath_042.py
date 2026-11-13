"""The edges of the RT-0069 fix beyond its oracle (tests/oracles/FP-042-EOSADDPATH).

With additional-paths receive, EOS's prefixAccepted counts paths. For each established peer with more than one path
accepted in a family, the driver reads `show ip|ipv6 bgp neighbors <peer> vrf <vrf> | json`; unless that family's
`receivingAddPaths.enabled` is exactly false, the P paths become the range 1 to P prefixes (judged only where the
whole range agrees). No EOS per-neighbor route listing is captured, so the prefixes aren't counted from one."""
import json
from pathlib import Path

import pytest

from netdryrun.checks import _counted
from netdryrun.drivers.eos import EosDriver, parse_eos_add_path_off
from test_verdict_drivers import Lab, eos_peer, eos_summary

FX = Path(__file__).parent / "fixtures"
PEER = "10.0.200.2"


def fx(name):
    return (FX / name).read_text(encoding="utf-8")


def read(v4=4, v6=0, peer_answer=None, vrf="default", peer=PEER, state="Established"):
    v4s = eos_summary(vrf, **{peer: {"peerState": state, "prefixAccepted": v4}})
    v6s = eos_summary(vrf, **{peer: {"peerState": state, "prefixAccepted": v6}})
    rules = [("ipv6 bgp summary", v6s), ("ip bgp summary", v4s)]
    if peer_answer is not None:
        rules.append(("bgp neighbors", peer_answer))
    lab = Lab(rules)
    return EosDriver(lab, "ceos1").bgp_neighbors(vrf).value, lab


def test_the_capture_reads_a_range_never_the_path_count():
    n, lab = read(peer_answer=fx("ceos4363m_rt0069_ceos1_ip_bgp_neighbor.json"))
    got = n[PEER]
    assert got.prefixes["ipv4-unicast"] == 1 and got.prefixes_upto["ipv4-unicast"] == 4
    assert "prefixAccepted (4) counts paths" in got.prefixes_unread["ipv4-unicast"]
    assert lab.lines()[-1] == f"Cli -p 15 -c show ip bgp neighbors {PEER} vrf default | json"
    ok, detail, _ = _counted(got, "ipv4-unicast", 1, 4, None, [])            # min 4: no verdict
    assert ok is False and "error" in str(detail)
    ok, _, _ = _counted(got, "ipv4-unicast", 1, 0, 4, [])                    # max 4 holds for any value in range
    assert ok is True
    ok, _, _ = _counted(got, "ipv4-unicast", 1, 0, 3, [])                    # max 3: no verdict
    assert ok is False


def test_add_path_off_reads_prefix_accepted():
    n, _ = read(peer_answer=fx("eos_eor_received.txt"))       # live: receivingAddPaths enabled false
    assert n[PEER].prefixes == {"ipv4-unicast": 4, "ipv6-unicast": 0} and n[PEER].prefixes_upto == {}


@pytest.mark.parametrize("answer", [
    eos_peer(PEER, ipv4Unicast=True),
    eos_peer(PEER),                                                          # no family entry
    eos_peer("10.0.200.9", ipv4Unicast=False),                               # another peer
    eos_peer(PEER, vrf="red", ipv4Unicast=False),                            # another VRF
    eos_peer(PEER, ipv6Unicast=False),                                       # only the other family is off
    json.dumps({"vrfs": {"default": {"peerList": [{"peerAddress": PEER, "neighborCapabilities": {"addPathsCaps": {
        "ipv4Unicast": {"receivingAddPaths": {"enabled": "false"}}}}}]}}}),  # not a clear false
    "not json", "[]", (1, "% error"),
])
def test_anything_but_a_clear_false_is_a_range(answer):
    n, _ = read(peer_answer=answer)
    assert (n[PEER].prefixes["ipv4-unicast"], n[PEER].prefixes_upto["ipv4-unicast"]) == (1, 4)
    assert n[PEER].prefixes_unread["ipv4-unicast"]


def test_a_failed_read_says_so():
    n, _ = read(peer_answer=(1, "% Invalid input"))
    assert "couldn't be read" in n[PEER].prefixes_unread["ipv4-unicast"]


def test_one_path_or_none_needs_no_read():
    for count in (0, 1):
        n, lab = read(v4=count)                                              # no neighbors rule: a read would fail
        assert n[PEER].prefixes == {"ipv4-unicast": count, "ipv6-unicast": 0}
        assert len(lab.lines()) == 2


def test_a_session_that_is_not_up_is_not_read():
    n, lab = read(state="Active")
    assert len(lab.lines()) == 2 and n[PEER].prefixes["ipv4-unicast"] == 4


def test_ipv6_peer_and_vrf():
    answer = eos_peer("2001:db8::2", vrf="red", ipv6Unicast=True)
    n, lab = read(v4=0, v6=6, peer_answer=answer, vrf="red", peer="2001:db8::2")
    assert lab.lines()[-1] == "Cli -p 15 -c show ipv6 bgp neighbors 2001:db8::2 vrf red | json"
    assert (n["2001:db8::2"].prefixes["ipv6-unicast"], n["2001:db8::2"].prefixes_upto["ipv6-unicast"]) == (1, 6)
    assert n["2001:db8::2"].prefixes["ipv4-unicast"] == 0 and "ipv4-unicast" not in n["2001:db8::2"].prefixes_upto


def test_each_family_follows_its_own_state():
    n, _ = read(v4=4, v6=3, peer_answer=eos_peer(PEER, ipv4Unicast=False, ipv6Unicast=True))
    assert n[PEER].prefixes == {"ipv4-unicast": 4, "ipv6-unicast": 1}
    assert n[PEER].prefixes_upto == {"ipv6-unicast": 3}


def test_parse_add_path_off():
    assert parse_eos_add_path_off(fx("ceos4363m_rt0069_ceos1_ip_bgp_neighbor.json"), "default", PEER) == set()
    assert parse_eos_add_path_off(fx("eos_eor_received.txt"), "default", PEER) == {"ipv4-unicast"}
    assert parse_eos_add_path_off(fx("eos_eor_received.txt"), "default", "10.0.200.3") == set()
    assert parse_eos_add_path_off(fx("eos_eor_received.txt"), "red", PEER) == set()
    two = json.loads(eos_peer(PEER, ipv4Unicast=False))
    two["vrfs"]["default"]["peerList"] *= 2                                  # the peer twice: which one is it?
    assert parse_eos_add_path_off(json.dumps(two), "default", PEER) == set()
