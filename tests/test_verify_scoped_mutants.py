"""Mutation gate for 0.4: the verdict-path functions of the verify package, each behaviour pinned so that a flipped
condition, a changed constant or a removed line fails a test (the scoped survivors of the 0.4 mutmut run, and the
code added after it: configured link-locals, the conditional-advertisement stretch, untested config).
"""
import pytest

from netdryrun.verify import converge, frr
from netdryrun.verify.converge import Inconclusive, SnapshotUnreadable, _not_ready, stable_snapshot
from netdryrun.verify.engine import Match
from netdryrun.verify.frr import CommandFailed, CommandTimedOut
from netdryrun.verify.report import EXIT_CODES, VERDICTS, VerifyResult, to_dict
from netdryrun.verify.snapshot import ItemKey, NodeSnapshot, Snapshot, SnapshotError, canon_set, value_matches_kind

from test_verify_converge import Clock, _no_bgp_yet, moved, seq
from verify_helpers import base, path, rib, session


# ============================================================================================ frr: link-locals

def test_boot_free_strips_the_zone_before_naming_the_address():
    """FRR prints a link-local next hop with its zone (`fe80::1%eth1`): the zone is cut before the lookup, or the
    owner's name is never found and every such next hop collapses to fe80::."""
    with frr.link_local_owners({"fe80::a8c1:abff:feb5:4b08": "fe80::%peer1:eth1"}):
        assert frr._boot_free("fe80::a8c1:abff:feb5:4b08%eth1") == "fe80::%peer1:eth1"
    assert frr._boot_free("fe80::1%eth1") == "fe80::"


def test_boot_free_looks_up_and_keeps_the_canonical_form():
    """The same address written another way (upper case, zeros spelled out) is the same next hop: looked up and
    kept in its canonical form, or two boots that print it differently would differ."""
    with frr.link_local_owners({"fe80::a8c1:abff:feb5:4b08": "fe80::%peer1:eth1"}, configured={"fe80::dead"}):
        assert frr._boot_free("FE80:0:0:0:A8C1:ABFF:FEB5:4B08") == "fe80::%peer1:eth1"
        assert frr._boot_free("FE80::DEAD") == "fe80::dead"
        assert frr._boot_free("fe80::99") == "fe80::"          # neither owned nor configured: per-boot, collapsed


def test_boot_free_leaves_every_address_that_is_not_ipv6_link_local():
    """Only IPv6 link-locals are per-boot: a global IPv6 next hop and an IPv4 link-local (169.254/16) are compared
    as written, with or without the lab's addresses."""
    for ip in ("2001:db8::1", "169.254.1.1", "10.0.0.1"):
        assert frr._boot_free(ip) == ip
        with frr.link_local_owners({}):
            assert frr._boot_free(ip) == ip


def test_link_local_owners_without_names_collapses_even_configured_addresses():
    """No lab addresses (a fixture parse): every link-local is fe80::, whatever the config names."""
    with frr.link_local_owners(None, configured={"fe80::dead"}):
        assert frr._boot_free("fe80::dead") == "fe80::"


def test_link_local_owners_restores_the_outer_context_even_on_error():
    """The owners are per node: leaving a node's block (normally or by an error) must restore the outer ones, or
    the next node is collected with another node's addresses."""
    with frr.link_local_owners({"fe80::1": "fe80::%r1:eth1"}):
        with frr.link_local_owners({}, configured={"fe80::2"}):
            assert frr._boot_free("fe80::1") == "fe80::" and frr._boot_free("fe80::2") == "fe80::2"
        assert frr._boot_free("fe80::1") == "fe80::%r1:eth1" and frr._boot_free("fe80::2") == "fe80::"
        with pytest.raises(RuntimeError):
            with frr.link_local_owners({}):
                raise RuntimeError("collect failed")
        assert frr._boot_free("fe80::1") == "fe80::%r1:eth1"
    assert frr._boot_free("fe80::1") == "fe80::"


IP6 = ("    inet6 fe80::9/64 scope link\n"                   # before any interface header: owned by nothing
       "3: eth1@if7: <BROADCAST,UP>\n"
       "    inet6 fe80::1/64\n"                              # two fields only
       "    inet 169.254.0.1/16 scope link\n"                # IPv4: not an IPv6 link-local
       "    inet6 bogus/64 scope link\n"                     # unreadable: skipped, the rest still read
       "    inet6 2001:db8::1/64 scope global\n"
       "    inet6 FE80::A/64 scope link\n"
       "4: eth2: <BROADCAST,UP>\n"
       "    inet6 fe80::2/64 scope link\n")


def test_parse_link_local_reads_only_ipv6_link_locals_under_an_interface():
    """An address is named by the interface it is listed under; a line outside any interface, an IPv4 or global
    address, or an unreadable one is not an owner, and one bad line doesn't end the listing."""
    assert frr.parse_link_local(IP6, "r1") == {"fe80::1": "r1:eth1", "fe80::a": "r1:eth1", "fe80::2": "r1:eth2"}


def test_parse_link_local_blanks_an_address_two_interfaces_of_the_node_share():
    """Which interface a shared address means depends on the link: blanked, and it stays blank; listed twice on
    one interface it is still that interface's."""
    two = "3: eth1: <UP>\n    inet6 fe80::1/64\n4: eth2: <UP>\n    inet6 fe80::1/64\n5: eth3: <UP>\n    inet6 fe80::1/64\n"
    assert frr.parse_link_local(two, "r1") == {"fe80::1": ""}
    twice = "3: eth1: <UP>\n    inet6 fe80::1/64\n    inet6 fe80::1/64\n"
    assert frr.parse_link_local(twice, "r1") == {"fe80::1": "r1:eth1"}


def test_link_local_names_keeps_only_addresses_one_interface_owns():
    """An address on two nodes, or blanked on one node, is left out (kept as written); one owner names it."""
    assert frr.link_local_names({"r1": {"fe80::1": "r1:eth1", "fe80::5": "r1:eth2"},
                                 "r3": {"fe80::1": "r3:eth2", "fe80::6": ""}}) == {"fe80::5": "fe80::%r1:eth2"}


def test_configured_link_locals_reads_every_link_local_token():
    """A trailing colon (prose in a description) is not part of the address, an invalid token doesn't stop the
    line, and fe80 inside a global address is not a link-local."""
    lines = (" description to fe80::5: uplink", "x fe80:1:2:3:4:5:6:7:8:9 fe80::beef",
             " neighbor 2001:db8:fe80::1 remote-as 1")
    assert frr.configured_link_locals(lines) == frozenset({"fe80::5", "fe80::beef"})
    assert frr.configured_link_locals(()) == frozenset()


# ======================================================================================= frr: running config

def test_parse_running_config_drops_only_frr_framing():
    """Header, separators (at any indent), blank and whitespace-only lines, `end` and trailing spaces go; every
    command keeps its indentation and its order (the indent is the section structure)."""
    text = ("Building configuration...\n\nCurrent configuration:\n!\nfrr version 10.4.1_git\n   \nrouter bgp 1\n"
            " neighbor 10.0.0.2 remote-as 2   \n !\n  address-family ipv4 unicast\nexit\n!\nend\n")
    assert frr.parse_running_config(text) == ("frr version 10.4.1_git", "router bgp 1", " neighbor 10.0.0.2 remote-as 2",
                                              "  address-family ipv4 unicast", "exit")


def test_qualified_names_each_line_by_its_sections():
    """A changed line is listed with the sections above it; a dedent closes sections, a top-level line has none."""
    lines = ("router bgp 1", " neighbor a remote-as 2", " address-family ipv4 unicast", "  network 10.0.0.0/8",
             " exit-address-family", "exit", "hostname r1")
    assert frr.qualified(lines) == [
        "router bgp 1", "router bgp 1 > neighbor a remote-as 2", "router bgp 1 > address-family ipv4 unicast",
        "router bgp 1 > address-family ipv4 unicast > network 10.0.0.0/8", "router bgp 1 > exit-address-family",
        "exit", "hostname r1"]


def test_qualified_does_not_open_a_section_on_a_line_that_skips_a_level():
    """A line indented two levels below its parent is not a section header for what follows."""
    assert frr.qualified(("router bgp 1", "   deep", "  x")) == ["router bgp 1", "router bgp 1 > deep",
                                                                 "router bgp 1 > x"]


def test_cond_adv_timer_is_the_longest_configured_timer_with_an_advertise_map():
    """Two BGP instances with their own timers: settle must cover the slower one. No advertise-map: no scanner,
    0, even with a timer; a route-map whose name merely contains advertise-map is not one."""
    adv = "  neighbor 10.0.2.2 advertise-map ADV exist-map EXIST"
    assert frr.cond_adv_timer((" bgp conditional-advertisement timer 30", adv,
                               " bgp conditional-advertisement timer 45")) == 45.0
    assert frr.cond_adv_timer((adv,)) == frr.DEFAULT_COND_ADV_TIMER == 60.0
    assert frr.cond_adv_timer((" bgp conditional-advertisement timer 30",)) == 0.0
    assert frr.cond_adv_timer(("  neighbor 10.0.2.2 route-map advertise-mapper out",)) == 0.0


# ======================================================================================== converge: _not_ready

def test_a_session_or_a_bgp_path_alone_is_bgp_state():
    """Either one shows bgpd has its config: a node with sessions and no paths (nothing learned yet, nothing to
    learn) or paths and no sessions is ready; with neither it isn't, unless it isn't expected to run BGP."""
    no_paths = base()
    no_paths.drop("up1", "path")
    assert _not_ready(no_paths.snap()) == []
    no_sessions = base()
    no_sessions.drop("up1", "session")
    assert _not_ready(no_sessions.snap()) == []
    assert _not_ready(_no_bgp_yet().snap()) == ["up1: no BGP state yet (no session, no BGP path)"]
    assert _not_ready(_no_bgp_yet().snap(), {"edge1"}) == []
    assert _not_ready(_no_bgp_yet().snap(), {"up1"}) == ["up1: no BGP state yet (no session, no BGP path)"]


def test_an_empty_rib_is_reported_once_per_node_in_node_order():
    lab = _no_bgp_yet("up1")
    lab.drop("up1", "rib")
    lab.drop("cust1", "rib")
    assert _not_ready(lab.snap()) == ["cust1: no routes in its RIB yet", "up1: no routes in its RIB yet"]


# ================================================================================== converge: stable_snapshot

class LateClock(Clock):
    """A monotonic clock that doesn't start at 0, as time.monotonic() doesn't: only differences may count."""

    def __init__(self):
        super().__init__()
        self.t = 1000.0


def go(collect, settle=10, timeout=120, clock=None, **kw):
    clock = clock or Clock()
    logs = []
    got = stable_snapshot(collect, settle=settle, timeout=timeout, clock=clock, sleep=clock.sleep, log=logs.append,
                          **kw)
    return got, clock, logs


def counted(collect):
    calls = []

    def f():
        calls.append(1)
        return collect()
    return f, calls


def test_elapsed_time_is_measured_from_the_start_not_from_zero():
    """With a clock that starts at 1000 s, a failed first read is retried, the timeout is still 120 s away, and the
    log reports the time taken."""
    good = base().snap()
    got, clock, logs = go(seq(CommandFailed("bgpd not up"), good, good), clock=LateClock())
    assert got is good and clock.t == 1013
    assert f"  snapshot stable ({len(good.items())} items, 13s)" in logs
    n = iter(range(1000))
    got, clock, _ = go(lambda: moved(next(n)), timeout=30, clock=LateClock())
    assert isinstance(got, Inconclusive) and clock.t == 1030


def test_a_failing_read_is_retried_up_to_the_timeout_inclusive():
    """Reads every POLL seconds; the read at exactly the timeout is the last one, and the error names the timeout
    and the failure."""
    collect, calls = counted(seq(CommandFailed("vtysh: bgpd not up")))
    with pytest.raises(SnapshotUnreadable) as e:
        go(collect, timeout=30)
    assert len(calls) == 11 and str(e.value) == "could not read the snapshot within 30s: vtysh: bgpd not up"


def test_a_failure_between_two_samples_restarts_the_comparison():
    """A read that fails between two identical samples breaks the pair: two fresh samples settle apart are needed."""
    a = base().snap()
    got, clock, _ = go(seq(a, CommandFailed("x"), a, a))
    assert got is a and clock.t == 23


def test_a_cut_command_says_to_retry_once_and_escalate():
    cut = CommandTimedOut("`show bgp` on edge1 did not finish within 120s")
    got, _, _ = go(seq(cut), timeout=300)
    assert got.reason == ("the snapshot was cut: a command never finished within its time limit before the 300s "
                          "timeout, so the snapshot is incomplete. Retry at most once, then escalate: this says "
                          "nothing about the change")


def test_inconclusive_with_nothing_moving_names_nothing():
    """A settle longer than the timeout can't take two samples: INCONCLUSIVE, with an empty list of what moved
    (never a placeholder)."""
    got, _, _ = go(seq(base().snap()), settle=10, timeout=5)
    assert isinstance(got, Inconclusive) and got.moving == []
    assert got.reason == ("the lab's state kept moving within 5s (two snapshots 10s apart never matched). Retry at "
                          "most once, then escalate: this says nothing about the change")


def test_never_ready_and_kept_moving_are_told_apart():
    got, _, _ = go(seq(_no_bgp_yet().snap()), timeout=40)
    assert got.reason == ("the lab's state never became ready within 40s (two snapshots 10s apart never matched). "
                          "Retry at most once, then escalate: this says nothing about the change")
    n = iter(range(1000))
    got, _, logs = go(lambda: moved(next(n)), timeout=60)
    assert got.reason.startswith("the lab's state kept moving within 60s ")
    assert "  still converging: 1 difference(s) since the last snapshot" in logs


def test_a_pair_that_matches_exactly_at_the_timeout_is_stable():
    """The last sample may land exactly at the timeout: a pair matching there is a snapshot, not INCONCLUSIVE."""
    got, clock, _ = go(seq(moved(1), moved(2), moved(2)), timeout=20)
    assert not isinstance(got, Inconclusive) and clock.t == 20


def test_a_node_not_ready_is_polled_and_resets_the_pair():
    """While a node isn't ready the loop polls (3 s), not settle; a not-ready sample between two good ones breaks
    the pair, and is never compared as half of one."""
    good, early = base().snap(), _no_bgp_yet().snap()
    got, clock, logs = go(seq(early, good, good))
    assert got is good and clock.t == converge.POLL + 10
    assert not any("still converging" in line for line in logs)
    got, clock, _ = go(seq(good, early, good, good))
    assert got is good and clock.t == 10 + converge.POLL + 10


def timed(adv=None, cond=None):
    """base() with advertisement intervals / conditional-advertisement timers per node."""
    snap = base().snap()
    for n, v in (adv or {}).items():
        snap.nodes[n].adv_interval = v
    for n, v in (cond or {}).items():
        snap.nodes[n].cond_adv_timer = v
    return snap


@pytest.mark.parametrize("attr", ["adv", "cond"])
def test_settle_stretches_to_a_timer_plus_the_margin_and_only_then(attr):
    """settle becomes timer + ADV_MARGIN when that is longer, never shorter; a zero timer stretches nothing,
    a 1 s timer does; equal is no stretch and no log line."""
    def t(value, settle):
        got, clock, logs = go(seq(timed(**{attr: {"edge1": value}})), settle=settle)
        assert not isinstance(got, Inconclusive)
        return clock.t, logs
    assert t(0.0, 1)[0] == 1
    assert t(1.0, 1)[0] == 1 + converge.ADV_MARGIN
    assert t(5.0, 6)[0] == 5 + converge.ADV_MARGIN
    took, logs = t(8.0, 10)
    assert took == 10 and not any("settle extended" in line for line in logs)


def test_settle_stretch_logs_name_the_slowest_node():
    _, _, logs = go(seq(timed(adv={"edge1": 3.0, "up1": 5.0}, cond={"cust1": 6.0, "edge1": 4.0})), settle=6)
    assert "  up1 has an advertisement interval of 5s: settle extended to 7s" in logs
    assert "  cust1 has conditional advertisement every 6s: settle extended to 8s" in logs


def test_settle_covers_the_longer_of_both_timers():
    got, clock, _ = go(seq(timed(adv={"edge1": 20.0}, cond={"up1": 30.0})))
    assert clock.t == 32
    got, clock, _ = go(seq(timed(adv={"edge1": 40.0}, cond={"up1": 30.0})))
    assert clock.t == 42


def test_a_snapshot_with_no_nodes_keeps_settle():
    """No node, no timer: settle stays as given (no default interval)."""
    empty = Snapshot({})
    got, clock, _ = go(seq(empty), settle=1)
    assert got is empty and clock.t == 1


# ============================================================================================ snapshot keys

def raises(fn, *a, **kw) -> str:
    with pytest.raises(SnapshotError) as e:
        fn(*a, **kw)
    return str(e.value)


RIB = dict(afi="ipv4", safi="unicast", prefix="10.0.0.0/8", protocol="bgp")


def test_item_key_needs_a_known_kind_a_node_and_a_vrf():
    assert raises(ItemKey, "bogus", "edge1", "default") == "item key: unknown kind 'bogus'"
    assert raises(ItemKey, "vrf", "edge1", "") == "item key: node and vrf are required"
    assert raises(ItemKey, "vrf", "", "default") == "item key: node and vrf are required"


@pytest.mark.parametrize("kind", ["vrf", "config"])
@pytest.mark.parametrize("field", [dict(afi="ipv4"), dict(safi="unicast"), dict(prefix="10.0.0.0/8"),
                                   dict(neighbor="10.0.0.2"), dict(protocol="bgp"), dict(path_id=1)])
def test_vrf_and_config_keys_carry_nothing_else(kind, field):
    """Any one extra field makes a vrf/config key a different key that compares unequal to the real one."""
    ItemKey(kind, "edge1", "default")
    assert raises(ItemKey, kind, "edge1", "default", **field).startswith(f"item key: bad {kind} key ItemKey(")


@pytest.mark.parametrize("field", [dict(neighbor=""), dict(afi="ipv4"), dict(prefix="10.0.0.0/8"),
                                   dict(protocol="bgp")])
def test_a_session_key_is_a_neighbor_and_nothing_route_like(field):
    ItemKey("session", "edge1", "default", neighbor="10.0.0.2")
    kw = {"neighbor": "10.0.0.2", **field}
    assert raises(ItemKey, "session", "edge1", "default", **kw).startswith("item key: bad session key ItemKey(")


@pytest.mark.parametrize("field", [dict(afi="ipv5"), dict(safi="multicast"), dict(prefix="")])
def test_a_route_key_needs_a_known_family_and_a_prefix(field):
    ItemKey("rib", "edge1", "default", **RIB)
    assert raises(ItemKey, "rib", "edge1", "default", **{**RIB, **field}).startswith("item key: bad key ItemKey(")


def test_a_route_key_prefix_matches_its_family_and_protocol_is_rib_only():
    assert raises(ItemKey, "rib", "edge1", "default", **{**RIB, "afi": "ipv6"}) == "item key: 10.0.0.0/8 is not ipv6"
    no_proto = {**RIB, "protocol": ""}
    assert raises(ItemKey, "rib", "edge1", "default", **no_proto).startswith("item key: protocol only on rib items ")
    assert raises(ItemKey, "path", "edge1", "default", neighbor="local", **RIB).startswith(
        "item key: protocol only on rib items ")
    assert raises(ItemKey, "path", "edge1", "default", **no_proto) == "item key: path needs a neighbor"


def test_a_node_snapshot_refuses_foreign_items_unknown_vrfs_and_bad_values():
    k = ItemKey("rib", "edge1", "default", **RIB)
    other = ItemKey("rib", "up1", "default", **RIB)
    assert raises(NodeSnapshot, "edge1", "frr", ("default",), {other: rib()}) == \
        f"edge1: item {other!r} of another node"
    red = ItemKey("rib", "edge1", "red", **RIB)
    assert raises(NodeSnapshot, "edge1", "frr", ("default",), {red: rib()}) == "edge1: item in unknown VRF 'red'"
    assert raises(NodeSnapshot, "edge1", "frr", ("default",), {k: path()}) == \
        "edge1: bad value for edge1 10.0.0.0/8 [bgp]"


def test_value_matches_kind_only_for_item_kinds_and_canonical_ribs():
    """vrf/config are not item kinds; a RIB value is a non-empty canonical (sorted, deduplicated) tuple of RIB
    entries, else two equal RIBs could compare unequal."""
    assert not value_matches_kind("vrf", ("default",)) and not value_matches_kind("config", ())
    assert not value_matches_kind("bogus", rib())
    a, b = canon_set([rib("bgp")[0], rib("static", hops=(), distance=1)[0]])
    assert value_matches_kind("rib", (a, b))
    assert not value_matches_kind("rib", (b, a))
    assert not value_matches_kind("rib", (a, a))
    assert not value_matches_kind("rib", ())
    assert not value_matches_kind("rib", ("x",))
    assert not value_matches_kind("rib", [a, b])
    assert value_matches_kind("path", path()) and not value_matches_kind("path", session("10.0.0.1"))


def test_items_gathers_every_node():
    lab = base()
    snap = lab.snap()
    assert len(snap.items()) == sum(len(v) for v in lab.items.values())
    assert {k.node for k in snap.items()} == set(lab.NODES)


def test_stability_view_carries_each_nodes_vrfs_config_and_prefix_counts():
    """A VRF appearing or the running config changing between samples is movement, named as the node's VRFs or
    running config."""
    snap = base().snap()
    view = snap.stability_view()
    assert view[ItemKey("vrf", "edge1", "default")] == ("default",)
    assert view[ItemKey("config", "edge1", "default")] == snap.nodes["edge1"].config
    k = ItemKey("session", "edge1", "default", neighbor="10.0.2.2")
    assert view[k] == (snap.items()[k], snap.items()[k].prefix_counts)
    other = base().snap()
    other.nodes["edge1"].vrfs = ("default", "red")
    assert snap.stability_view() != other.stability_view()
    assert converge._moving(snap, other) == ["edge1 vrf default changed"]
    other = base().snap()
    other.nodes["edge1"].config = ()
    assert converge._moving(snap, other) == ["edge1 running config changed"]


# ================================================================================================== report

def test_every_status_has_its_verdict_and_exit_code():
    """The verdict text and the exit code are the contract CI gates on."""
    want = {"matched": ("INTENT MATCHED", 0), "no_change": ("NO BEHAVIOR CHANGE", 0),
            "failed": ("UNDECLARED CHANGES: DO NOT APPLY", 1), "error": ("ERROR: NO VERDICT", 2),
            "inconclusive": ("INCONCLUSIVE", 3), "unhealthy_baseline": ("INCONCLUSIVE: UNHEALTHY BASELINE", 3)}
    assert set(VERDICTS) == set(EXIT_CODES) == set(want)
    for status, (text, code) in want.items():
        r = VerifyResult(status=status)
        assert (r.verdict, r.exit_code) == (text, code)
        d = to_dict(r)
        assert (d["verdict"], d["status"]) == (text, status)


def test_an_error_report_has_no_items_no_unobserved_and_no_evidence():
    d = to_dict(VerifyResult(status="error", error=""))
    assert d["diff_items"] == 0 and d["unobserved"] == {} and d["error"] is None
    assert d["evidence"] == {"before": None, "after": None} and d["inconclusive"] is None


def test_an_unhealthy_baseline_says_why_and_how_to_override():
    d = to_dict(VerifyResult(status="unhealthy_baseline", before=base().snap(), baseline_problems=["x down"]))
    assert d["inconclusive"] == {
        "side": "before", "reason": "the before-lab is not a healthy baseline (BGP sessions down); rerun with "
                                    "--allow-unhealthy-baseline to compare anyway",
        "moving": [], "advice": "Retry at most once, then escalate. This says nothing about the change."}
    assert d["baseline"] == {"healthy": False, "problems": ["x down"], "overridden": False}


@pytest.mark.parametrize("side", ["before", "after"])
def test_unobserved_nodes_are_reported_from_whichever_side_exists(side):
    """An inconclusive or error run may have only one snapshot: its unobserved nodes are still reported, sorted."""
    snap = base().snap()
    snap.unobserved = {"s1": "sonic-vs", "a1": "srl"}
    d = to_dict(VerifyResult(status="inconclusive", **{side: snap}))
    assert list(d["unobserved"].items()) == [("a1", "srl"), ("s1", "sonic-vs")]
    assert d["evidence"][side] == snap.to_json()


def test_evidence_carries_both_snapshots():
    before, after = base().snap(), moved(3)
    d = to_dict(VerifyResult(status="failed", before=before, after=after))
    assert d["evidence"] == {"before": before.to_json(), "after": after.to_json()}


@pytest.mark.parametrize("status,listed", [("matched", True), ("no_change", True), ("failed", False),
                                           ("inconclusive", False), ("error", False)])
def test_untested_config_is_listed_only_with_an_approval(status, listed):
    """Untested lines qualify an approval; next to any other verdict they would read as part of a pass."""
    m = Match("matched", [], [], [], {}, {"edge1": {"added": ["x"], "removed": []}})
    d = to_dict(VerifyResult(status=status, match=m, before=base().snap(), after=base().snap()))
    assert d["untested_config"] == ([{"node": "edge1", "added": ["x"], "removed": []}] if listed else [])
