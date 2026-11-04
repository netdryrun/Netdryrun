"""Mutation on 7446aaf: survivors in the strict reads of Layer 6 rounds 3 to 5. Each test kills mutants by name.

The shape and hop-count tests close real gaps: a segment with a non-string type passed the shape check, and the
aspath length cross-check was pinned only for as-sequence. The message tests pin the text of each parser error, which
reaches a result's detail and so the JSON report: the command it names and the first 150 characters of what it got
(every input here prints longer than that)."""
import pytest

from netdryrun import runner
from netdryrun.drivers import eos, frr, junos, srlinux
from netdryrun.drivers.base import DriverError

LONG = "x" * 300


def _msg(command: str, text: str) -> str:
    return f"unexpected output from `{command}`: {text}"


def _err(fn, *args) -> str:
    with pytest.raises(DriverError) as e:
        fn(*args)
    return str(e.value)


# --- frr._segments ----------------------------------------------------------------------------------------------

def test_frr_counts_an_as_set_as_one_hop_and_a_confederation_segment_as_none():
    """_segments_41, _45, _46, _47, _49, _50, _51: as-set is 1 hop, a confederation segment 0."""
    segs = [{"type": "as-sequence", "list": [65001, 65002]}, {"type": "as-set", "list": [65003, 65004]},
            {"type": "as-confed-sequence", "list": [64512]}]
    assert frr._segments({"aspath": {"segments": segs, "length": 3}}) == [
        ("as-sequence", [65001, 65002]), ("as-set", [65003, 65004]), ("as-confed-sequence", [64512])]


def test_frr_a_confederation_segment_alone_adds_no_hop():
    """_segments_48 (`kind != "as-set"`): it counted a confederation segment as one hop."""
    segs = [{"type": "as-sequence", "list": [65001]}, {"type": "as-confed-sequence", "list": [64512]}]
    assert frr._segments({"aspath": {"segments": segs, "length": 1}}) == [
        ("as-sequence", [65001]), ("as-confed-sequence", [64512])]


def test_frr_a_segment_whose_type_is_not_a_string_is_an_error():
    """_segments_23 (`or` -> `and`): a dict segment with a numeric type passed the shape check."""
    p = {"aspath": {"segments": [{"type": 2, "list": [65001]}], "length": 0}}
    assert _err(frr._segments, p) == _msg(frr.BGP_PATHS_CMD, "aspath segment without its type or list: "
                                          "{'type': 2, 'list': [65001]}")


def test_frr_segment_and_length_errors_in_full():
    """_segments_27, _31, _32, _56, _63."""
    s = {"type": "as-sequence", "list": LONG}
    assert _err(frr._segments, {"aspath": {"segments": [s], "length": 1}}) == _msg(
        frr.BGP_PATHS_CMD, f"aspath segment without its type or list: {str(s)[:150]}")
    ok = [{"type": "as-sequence", "list": [65001]}]
    assert _err(frr._segments, {"aspath": {"segments": ok, "length": "one"}}) == _msg(
        frr.BGP_PATHS_CMD, "not a number: 'one'")
    assert _err(frr._segments, {"aspath": {"segments": ok, "length": 2}}) == _msg(
        frr.BGP_PATHS_CMD, "aspath length 2, but its segments count 1 hops")


def test_frr_a_community_without_its_string_in_full():
    """frr._communities_6, _10."""
    obj = {"list": LONG}
    assert _err(frr._communities, {"community": obj}, "community") == _msg(
        frr.BGP_PATHS_CMD, f"community without its string: {str(obj)[:150]}")


# --- srlinux ----------------------------------------------------------------------------------------------------

def test_srlinux_a_segment_whose_type_is_not_a_string_is_an_error():
    """_as_path_segments_32 (`or` -> `and`)."""
    assert _err(srlinux._as_path_segments, {"segment": [{"type": 2, "member": [65001]}]}) == _msg(
        srlinux.ATTR_CMD, "as-path segment without its type or members: {'type': 2, 'member': [65001]}")


def test_srlinux_as_path_errors_in_full():
    """_as_path_segments_7, _11, _12, _21, _25, _26, _39, _43, _44."""
    bad = {"segment": [], "other": LONG}
    assert _err(srlinux._as_path_segments, bad) == _msg(srlinux.ATTR_CMD, f"as-path: {str(bad)[:150]}")
    notlist = {"segment": LONG}
    assert _err(srlinux._as_path_segments, notlist) == _msg(
        srlinux.ATTR_CMD, f"as-path without its segment list: {str(notlist)[:150]}")
    s = {"type": "as-sequence", "member": LONG}
    assert _err(srlinux._as_path_segments, {"segment": [s]}) == _msg(
        srlinux.ATTR_CMD, f"as-path segment without its type or members: {str(s)[:150]}")


def test_srlinux_communities_and_rib_row_errors_in_full():
    """_communities_14, _18, _19; _best_1; _bgp_learned_3."""
    c = {"community": LONG}
    assert _err(srlinux._communities, c) == _msg(srlinux.ATTR_CMD,
                                                 f"communities without a community list: {str(c)[:150]}")
    assert _err(srlinux._best, {"prefix": "10.0.0.0/24"}) == _msg(
        srlinux.RIB_CMD, "no best-route: {'prefix': '10.0.0.0/24'}")
    assert _err(srlinux._bgp_learned, {"prefix": "10.0.0.0/24"}) == _msg(
        srlinux.RIB_CMD, "no origin-protocol: {'prefix': '10.0.0.0/24'}")


# --- eos._peer, junos._state ------------------------------------------------------------------------------------

def test_eos_a_path_without_its_peer_in_full():
    """eos._peer_3, _4, _15, _16, _26, _30, _31."""
    assert _err(eos._peer, LONG) == _msg(eos.BGP_CMD, f"path without peerEntry: {LONG[:150]}")
    p = {"pad": LONG}
    assert _err(eos._peer, p) == _msg(eos.BGP_CMD, f"no peerEntry: {str(p)[:150]}")
    p = {"peerEntry": LONG}
    assert _err(eos._peer, p) == _msg(eos.BGP_CMD, f"path without peerEntry: {str(p)[:150]}")
    p = {"peerEntry": {"pad": LONG}}
    assert _err(eos._peer, p) == _msg(eos.BGP_CMD, f"no peerAddr: {str(p['peerEntry'])[:150]}")
    p = {"peerEntry": {"peerAddr": 5}, "pad": LONG}
    assert _err(eos._peer, p) == _msg(eos.BGP_CMD, f"path without peerEntry: {str(p)[:150]}")


def test_junos_an_extensive_entry_without_its_state_names_the_command():
    """junos._state_16."""
    cmd = "show route 10.0.0.0/24 extensive"
    assert _err(junos._state, cmd, {"rt-destination": [{"data": "10.0.0.0/24"}]}).startswith(
        _msg(cmd, "no 'rt-entry-state'"))


# --- runner: the never-left detail (in the JSON report) ---------------------------------------------------------

def test_some_lists_five_prefixes_without_a_count():
    """runner._some_9 (`>= 5`): five prefixes read "and 0 more"."""
    five = [f"10.{i}.0.0/16" for i in range(5)]
    assert runner._some(five) == ", ".join(five)
    assert runner._some([*five, "10.9.0.0/16"]) == ", ".join(five) + " and 1 more"


def test_the_never_left_detail_names_each_family_without_a_session():
    """runner._never_left_21: the separator between families."""
    from types import SimpleNamespace
    inj = SimpleNamespace(applied=True, left=False, quiet={}, node="r1",
                          unsent={"ipv4": ["10.66.0.0/16"], "ipv6": ["2001:db8:66::/48"]})
    logs = []
    runner._never_left([inj], [], logs.append)
    assert logs == ["  inconclusive: the injected routes never left r1: no established ipv4 BGP session there carries "
                    "10.66.0.0/16; no established ipv6 BGP session there carries 2001:db8:66::/48, so this scenario "
                    "tested nothing"]


def test_frr_a_stale_flag_that_is_not_a_boolean_in_full():
    """frr._bgp_paths_raw_53, _58."""
    import json
    cmd = "show bgp ipv4 unicast 10.9.9.0/24 json"
    stale = "y" * 60
    text = json.dumps({"prefix": "10.9.9.0/24", "pathCount": 1, "paths": [{"stale": stale}]})
    assert _err(frr._bgp_paths_raw, cmd, text, "10.9.9.0/24") == _msg(cmd, f"stale: {stale[:40]!r}")
