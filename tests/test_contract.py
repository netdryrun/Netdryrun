"""Unit tests of the contract's types and consumers (the rules the kit builds on)."""
from __future__ import annotations

import pytest

from netdryrun import contract as c
from netdryrun.contract import (UNKNOWN, Attrs, Cause, CollectionError, Completeness, ConfigLoad, HopKind, Lookup,
                                NextHop, Origin, Prefix, Provenance, RibEntry, Scope, Snapshot, Stage, Tri)

PROV = Provenance("r1", ("show",), 100.0)


def snap(items=(), completeness=Completeness.COMPLETE, confirmed=True, cause=None):
    return Snapshot(Scope("r1"), PROV, completeness, tuple(items), cause, "", confirmed, "show vrf" if confirmed else "")


def route(prefix="10.0.0.0/24", stale=False, stages=(Stage.FIB,)):
    return RibEntry(Prefix.parse(prefix), Origin.CONNECTED, frozenset(stages), stale=stale,
                    next_hops=(NextHop(HopKind.INTERFACE, interface="eth1"),))


# C9 -----------------------------------------------------------------------------------------------------------
def test_prefix_needs_a_length_and_never_guesses():
    with pytest.raises(CollectionError):
        Prefix.parse("10.0.0.1")
    assert str(Prefix.parse("10.0.0.1", default_len=32)) == "10.0.0.1/32"       # mask from a header line
    with pytest.raises(CollectionError):
        Prefix.parse("10.0.0.1/24")                                               # host bits set: not a prefix
    with pytest.raises(CollectionError):
        Prefix.parse("eth0/64")


def test_covering_and_default_routes_do_not_match_an_exact_prefix():
    s = snap([route("10.0.0.0/8"), route("0.0.0.0/0")])
    assert c.route_present(s, Prefix.parse("10.1.2.3/32")) is Lookup.ABSENT


# C1-C3, C19 absence is only decided by a complete, confirmed, fresh snapshot ---------------------------------
@pytest.mark.parametrize("completeness,confirmed,cause", [
    (Completeness.TRUNCATED, True, None), (Completeness.STALE, True, None),
    (Completeness.UNKNOWN, False, Cause.NO_ANSWER), (Completeness.COMPLETE, False, None)])
def test_absence_needs_complete_and_confirmed(completeness, confirmed, cause):
    s = snap(completeness=completeness, confirmed=confirmed, cause=cause)
    assert c.route_present(s, Prefix.parse("10.0.0.0/24")) is Lookup.UNKNOWN


def test_unsupported_is_reported_as_unsupported():
    s = snap(completeness=Completeness.UNSUPPORTED, cause=Cause.NOT_IMPLEMENTED)
    assert c.route_present(s, Prefix.parse("10.0.0.0/24")) is Lookup.UNSUPPORTED


def test_unknown_and_unsupported_snapshots_cannot_carry_items_and_must_say_why():
    with pytest.raises(CollectionError):
        snap([route()], Completeness.UNKNOWN, cause=Cause.NO_ANSWER)
    with pytest.raises(CollectionError):
        snap(completeness=Completeness.UNKNOWN)
    with pytest.raises(CollectionError):
        snap(cause=Cause.NO_ANSWER)           # COMPLETE with a cause


def test_truncated_snapshot_still_proves_presence():
    s = snap([route()], Completeness.TRUNCATED)
    assert c.route_present(s, Prefix.parse("10.0.0.0/24")) is Lookup.PRESENT


def test_a_snapshot_read_before_the_required_time_becomes_stale():
    s = snap()
    assert s.at_least(50.0) is s
    late = s.at_least(150.0)
    assert late.completeness is Completeness.STALE
    assert c.route_present(late, Prefix.parse("10.0.0.0/24")) is Lookup.UNKNOWN


def test_stale_and_unknown_staleness_paths_are_not_live():
    p = Prefix.parse("10.0.0.0/24")
    assert c.route_present(snap([route(stale=True)]), p) is Lookup.UNKNOWN
    assert c.route_present(snap([route(stale=UNKNOWN)]), p) is Lookup.UNKNOWN
    assert c.route_present(snap([route(stale=False)]), p) is Lookup.PRESENT


# C7, C8 ------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("kind", [HopKind.BLACKHOLE, HopKind.REJECT, HopKind.UNRESOLVED])
def test_a_hop_that_does_not_forward_is_not_installed(kind):
    e = RibEntry(Prefix.parse("10.0.0.0/24"), Origin.STATIC, frozenset({Stage.FIB}), next_hops=(NextHop(kind),))
    assert e.installed is Tri.NO
    assert c.installed_route(snap([e]), Prefix.parse("10.0.0.0/24")) is Tri.NO


def test_best_without_fib_is_not_installed_and_no_hops_is_unknown():
    p = Prefix.parse("10.0.0.0/24")
    best_only = RibEntry(p, Origin.RECEIVED, frozenset({Stage.BEST}), "s1")
    assert best_only.installed is Tri.NO
    assert RibEntry(p, Origin.RECEIVED, frozenset({Stage.FIB}), "s1").installed is Tri.UNKNOWN


# C21 ---------------------------------------------------------------------------------------------------------
def test_link_local_next_hop_needs_its_interface():
    with pytest.raises(CollectionError):
        NextHop(HopKind.GATEWAY, "fe80::1")
    assert NextHop(HopKind.GATEWAY, "fe80::1", "eth1") != NextHop(HopKind.GATEWAY, "fe80::1", "eth2")
    with pytest.raises(CollectionError):
        NextHop(HopKind.GATEWAY)


# C22 ---------------------------------------------------------------------------------------------------------
def test_received_path_names_its_session():
    with pytest.raises(CollectionError):
        RibEntry(Prefix.parse("10.0.0.0/24"), Origin.RECEIVED, frozenset())


# C5, C6 counts -----------------------------------------------------------------------------------------------
def test_count_range_is_unknown_for_an_unknown_count():
    assert c.count_in_range(UNKNOWN, 0, 10) is Tri.UNKNOWN
    assert c.count_in_range(3, 1, 3) is Tri.YES
    assert c.count_in_range(4, None, 3) is Tri.NO


# K1-K3 core invariants ---------------------------------------------------------------------------------------
def test_only_yes_passes_and_unknown_never_passes():
    assert c.verdict(Tri.YES) == "pass" and c.verdict(Tri.NO) == "fail"
    assert c.verdict(Tri.UNKNOWN) == "inconclusive" and c.verdict(Tri.UNKNOWN, "fail") == "fail"
    with pytest.raises(ValueError):
        c.verdict(Tri.UNKNOWN, "pass")


def test_all_over_an_empty_set_is_unknown():
    assert c.quantify_all([]) is Tri.UNKNOWN
    assert c.quantify_all([Tri.YES, Tri.YES]) is Tri.YES
    assert c.quantify_all([Tri.YES, Tri.UNKNOWN]) is Tri.UNKNOWN
    assert c.quantify_all([Tri.UNKNOWN, Tri.NO]) is Tri.NO


def test_unknown_sentinel_is_falsy_unique_and_not_zero():
    assert not UNKNOWN and UNKNOWN is not 0 and UNKNOWN != 0 and UNKNOWN == UNKNOWN   # noqa: F632
    assert Attrs().local_pref is UNKNOWN


def test_config_applied_is_yes_only_when_verified_and_clean():
    assert c.config_applied(ConfigLoad(True)) is Tri.YES
    assert c.config_applied(ConfigLoad(False)) is Tri.UNKNOWN
    assert c.config_applied(ConfigLoad(True, rejected=("neighbor x default-orignate",))) is Tri.NO
    assert c.config_applied(ConfigLoad(False, rejected=("x",))) is Tri.NO
