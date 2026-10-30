"""Direct tests of every consumer in contract.py. Each case is a false pass found by a cold review that mutated
the module: a consumer that answered YES (or ABSENT) when it should not have. The kit exercises the same
functions through fixtures; these pin their edges."""
from __future__ import annotations

import pytest

from netdryrun import contract as c
from netdryrun.contract import (UNKNOWN, AfiState, Attrs, CollectionError, Completeness, ConfigLoad, HopKind, LabCommand,
                                Lookup, NextHop, Origin, Prefix, Provenance, RibEntry, Scope, Session, SessionState,
                                Snapshot, Stage, Tri)

P = Prefix.parse("10.0.0.0/24")
FIB = frozenset({Stage.LOC_RIB, Stage.BEST, Stage.FIB})
G1, G2 = NextHop(HopKind.GATEWAY, "10.1.1.1"), NextHop(HopKind.GATEWAY, "10.1.1.2")


def prov(device="r1", derived=None):
    return Provenance(device, ("show route", "show vrf"), 100.0, derived)


def snap(items=(), completeness=Completeness.COMPLETE, confirmed=True, scope=None, derived=None):
    cause = c.Cause.NO_ANSWER if completeness in (Completeness.UNKNOWN, Completeness.UNSUPPORTED) else None
    return Snapshot(scope or Scope("r1"), prov(derived=derived), completeness, tuple(items), cause, "", confirmed,
                    "show vrf" if confirmed else "", "row count matches" if completeness is Completeness.COMPLETE else "")


def entry(prefix=P, hops=(G1,), stale=False, stages=FIB, origin=Origin.STATIC, peer=None, attrs=None):
    return RibEntry(prefix, origin, stages, peer, next_hops=tuple(hops), stale=stale, attrs=attrs or Attrs())


# installed_route: stale entries, stale snapshots, scope, conflicting entries -------------------------------------
def test_installed_needs_a_live_entry():
    assert c.installed_route(snap([entry()]), P) is Tri.YES
    assert c.installed_route(snap([entry(stale=True)]), P) is Tri.UNKNOWN
    assert c.installed_route(snap([entry(stale=UNKNOWN)]), P) is Tri.UNKNOWN
    assert c.installed_route(snap([entry()]).at_least(500.0), P) is Tri.UNKNOWN          # read before settle time


def test_installed_conflicting_or_missing_entries():
    black = entry(hops=(NextHop(HopKind.BLACKHOLE),))
    assert c.installed_route(snap([entry(), black]), P) is Tri.UNKNOWN                     # forwards and discards
    assert c.installed_route(snap([black]), P) is Tri.NO
    assert c.installed_route(snap([entry(hops=(G1, NextHop(HopKind.BLACKHOLE)))]), P) is Tri.NO   # ECMP with a discard
    assert c.installed_route(snap(), P) is Tri.NO                                          # complete, confirmed, absent
    assert c.installed_route(snap(confirmed=False), P) is Tri.UNKNOWN
    assert c.installed_route(snap(completeness=Completeness.TRUNCATED), P) is Tri.UNKNOWN


def test_questions_outside_the_snapshots_scope_are_unknown():
    loc = snap(scope=Scope("r1", stage=Stage.LOC_RIB))
    assert c.route_present(loc, P, Stage.FIB) is Lookup.UNKNOWN                            # LOC_RIB says nothing of FIB
    assert c.route_present(snap(scope=Scope("r1", afi="ipv6-unicast")), P) is Lookup.UNKNOWN
    assert c.route_present(snap(scope=Scope("r1", vrf="red")), P) is Lookup.UNKNOWN
    assert c.route_present(snap(scope=Scope("r1", vrf="red")), P, vrf="red") is Lookup.ABSENT
    assert c.installed_route(snap(scope=Scope("r1", vrf="red")), P) is Tri.UNKNOWN


def test_stale_snapshot_proves_nothing():
    late = snap([entry()]).at_least(500.0)
    assert late.completeness is Completeness.STALE
    assert c.route_present(late, P) is Lookup.UNKNOWN
    assert c.route_present(snap([entry()]).at_least(50.0), P) is Lookup.PRESENT


# next_hops_exactly ------------------------------------------------------------------------------------------
@pytest.mark.parametrize("hops,expected,want", [
    ((G1, G2), ["10.1.1.1", "10.1.1.2"], Tri.YES),
    ((G1,), ["10.1.1.1", "10.1.1.2"], Tri.NO),                                   # a missing member (subset)
    ((G1, G2), ["10.1.1.1"], Tri.NO),                                            # an extra member (superset)
    ((G1, NextHop(HopKind.BLACKHOLE)), ["10.1.1.1"], Tri.NO),                    # blackholed member
    ((G1, NextHop(HopKind.UNRESOLVED)), ["10.1.1.1"], Tri.NO),
    ((NextHop(HopKind.GATEWAY, "fe80::1", "eth1"),), ["fe80::1"], Tri.NO),       # link-local needs its interface
    ((NextHop(HopKind.GATEWAY, "fe80::1", "eth1"),), [("fe80::1", "eth1")], Tri.YES),
    ((NextHop(HopKind.GATEWAY, "fe80::1", "eth1"),), [("fe80::1", "eth2")], Tri.NO),
    ((NextHop(HopKind.INTERFACE, interface="eth1"),), [(None, "eth1")], Tri.YES),
    ((), ["10.1.1.1"], Tri.UNKNOWN)])
def test_next_hop_set_equality(hops, expected, want):
    assert c.next_hops_exactly(snap([entry(hops=hops)]), P, expected) is want


def test_next_hop_set_needs_a_complete_live_confirmed_fib_table():
    ok = ["10.1.1.1"]
    assert c.next_hops_exactly(snap([entry(stale=True)]), P, ok) is Tri.UNKNOWN
    assert c.next_hops_exactly(snap([entry(stale=UNKNOWN)]), P, ok) is Tri.UNKNOWN
    assert c.next_hops_exactly(snap([entry()], Completeness.TRUNCATED), P, ok) is Tri.UNKNOWN
    assert c.next_hops_exactly(snap([entry()], confirmed=False), P, ok) is Tri.UNKNOWN
    assert c.next_hops_exactly(snap([entry(stages=frozenset({Stage.LOC_RIB}))]), P, ok) is Tri.UNKNOWN   # not in the FIB
    assert c.next_hops_exactly(snap([entry()], scope=Scope("r1", stage=Stage.LOC_RIB)), P, ok) is Tri.UNKNOWN
    assert c.next_hops_exactly(snap([entry(), entry(hops=(G2,))]), P, ["10.1.1.1", "10.1.1.2"]) is Tri.YES


# received_from / received_nothing / session_established -----------------------------------------------------
def recv(peer="s1", stages=frozenset({Stage.ADJ_RIB_IN, Stage.LOC_RIB}), origin=Origin.RECEIVED):
    return RibEntry(P, origin, stages, peer if origin is Origin.RECEIVED else None, stale=False)


def test_received_from_checks_origin_session_stage_and_scope():
    assert c.received_from(snap([recv()]), "s1", P) is Lookup.PRESENT
    assert c.received_from(snap([recv()]), "s2", P) is Lookup.ABSENT
    assert c.received_from(snap([recv(origin=Origin.NETWORK)]), "s1", P) is Lookup.ABSENT
    assert c.received_from(snap([recv(stages=frozenset({Stage.ADJ_RIB_OUT}))]), "s1", P) is Lookup.ABSENT
    assert c.received_from(snap([recv()], scope=Scope("r1", vrf="red")), "s1", P) is Lookup.UNKNOWN
    assert c.received_from(snap([recv()], derived=Stage.BEST), "s1", P) is Lookup.UNKNOWN


def counted(state=SessionState.ESTABLISHED, up=Tri.YES, soft=Tri.YES, adj_in=0):
    return Session("s", "10.0.0.1", state=state, afis=(AfiState("ipv4-unicast", up, ((Stage.ADJ_RIB_IN, adj_in),), soft),))


@pytest.mark.parametrize("kw,want", [
    ({}, Tri.YES), ({"adj_in": 1}, Tri.NO), ({"adj_in": 5}, Tri.NO), ({"soft": Tri.NO}, Tri.UNKNOWN),
    ({"soft": Tri.UNKNOWN}, Tri.UNKNOWN), ({"up": Tri.NO}, Tri.UNKNOWN), ({"up": Tri.UNKNOWN}, Tri.UNKNOWN),
    ({"state": SessionState.NOT_ESTABLISHED}, Tri.UNKNOWN), ({"state": SessionState.NO_ROW}, Tri.UNKNOWN)])
def test_received_nothing_needs_an_established_session_and_a_kept_adj_rib_in(kw, want):
    assert c.received_nothing(counted(**kw), "ipv4-unicast") is want


def test_received_nothing_without_the_afi_or_the_count_is_unknown():
    assert c.received_nothing(counted(), "ipv6-unicast") is Tri.UNKNOWN
    s = Session("s", "10.0.0.1", state=SessionState.ESTABLISHED, afis=(AfiState("ipv4-unicast", Tri.YES, (), Tri.YES),))
    assert c.received_nothing(s, "ipv4-unicast") is Tri.UNKNOWN


def sess(peer="10.0.0.1", id_=None, state=SessionState.ESTABLISHED, vrf="default", afi_up=Tri.YES):
    return Session(id_ or f"id-{peer}-{vrf}", peer, vrf, Tri.YES, state, afis=(AfiState("ipv4-unicast", afi_up),))


def test_session_established_edges():
    ok = snap([sess()], scope=Scope("r1"))
    assert c.session_established(ok, "10.0.0.1", "ipv4-unicast") is Tri.YES
    assert c.session_established(ok, "10.0.0.1", "ipv4-unicast", vrf="red") is Tri.UNKNOWN          # asked about another VRF
    red = snap([sess(vrf="red")], scope=Scope("r1"))
    assert c.session_established(red, "10.0.0.1", "ipv4-unicast") is Tri.UNKNOWN                    # wrong scope
    mixed = snap([sess(vrf="red"), sess(peer="10.0.0.9")], scope=Scope("r1"))
    assert c.session_established(mixed, "10.0.0.1", "ipv4-unicast") is Tri.UNKNOWN                  # mixes two VRFs
    assert c.session_established(ok.at_least(500.0), "10.0.0.1", "ipv4-unicast") is Tri.UNKNOWN     # STALE snapshot
    assert c.session_established(snap([sess(), sess(id_="id-x")]), "10.0.0.1", "ipv4-unicast") is Tri.UNKNOWN  # two rows
    assert c.session_established(snap([sess(id_="a"), sess(peer="10.0.0.2", id_="a")]), "10.0.0.1", "ipv4-unicast") is Tri.UNKNOWN
    assert c.session_established(snap([sess(state=SessionState.UNKNOWN)]), "10.0.0.1", "ipv4-unicast") is Tri.UNKNOWN
    assert c.session_established(snap([sess(state=SessionState.NO_ROW)]), "10.0.0.1", "ipv4-unicast") is Tri.NO
    assert c.session_established(snap([sess(afi_up=Tri.NO)]), "10.0.0.1", "ipv4-unicast") is Tri.NO
    assert c.session_established(snap(), "10.0.0.1", "ipv4-unicast") is Tri.NO                      # complete, no such peer
    assert c.session_established(snap(confirmed=False), "10.0.0.1", "ipv4-unicast") is Tri.UNKNOWN
    assert c.session_established(snap(completeness=Completeness.TRUNCATED), "10.0.0.1", "ipv4-unicast") is Tri.UNKNOWN


def test_peer_addresses_compare_as_addresses_not_strings():
    s = snap([sess(peer="2001:db8::1")])
    assert c.session_established(s, "2001:DB8:0::1", "ipv4-unicast") is Tri.YES
    ll = snap([sess(peer="fe80::1%eth1")])
    assert c.session_established(ll, "fe80::1%eth2", "ipv4-unicast") is Tri.NO                      # same address, other interface


def test_every_ignores_nothing_in_another_vrf():
    s = snap([sess(), sess(peer="10.0.0.2", vrf="red")], scope=Scope("r1"))
    assert s.every(lambda x: x.state is SessionState.ESTABLISHED) is Tri.UNKNOWN


# community_absent -------------------------------------------------------------------------------------------
def with_comms(comms, complete, stale=False):
    return entry(attrs=Attrs(communities=comms, communities_complete=complete), stale=stale)


def test_community_absent_edges():
    full = with_comms(frozenset({"65000:1"}), True)
    assert c.community_absent(full, "65000:666") is Tri.YES
    assert c.community_absent(full, "65000:1") is Tri.NO
    assert c.community_absent(with_comms(frozenset({"65000:1"}), False), "65000:666") is Tri.UNKNOWN
    assert c.community_absent(with_comms(frozenset({"65000:1"}), False), "65000:1") is Tri.NO      # present is provable
    assert c.community_absent(with_comms(UNKNOWN, True), "65000:666") is Tri.UNKNOWN
    assert c.community_absent(with_comms(frozenset(), True, stale=True), "65000:666") is Tri.UNKNOWN
    assert c.community_absent(with_comms(frozenset(), True, stale=UNKNOWN), "65000:666") is Tri.UNKNOWN
    named = with_comms(frozenset({"65535:65281"}), True)
    assert c.community_absent(named, "no-export") is Tri.NO                                          # query canonicalised


# counts, config, quantifiers ---------------------------------------------------------------------------------
def test_count_range_boundaries_and_types():
    assert c.count_in_range(3, 3, 3) is Tri.YES
    assert c.count_in_range(2, 3, None) is Tri.NO and c.count_in_range(3, 3, None) is Tri.YES
    assert c.count_in_range(4, None, 3) is Tri.NO and c.count_in_range(3, None, 3) is Tri.YES
    assert c.count_in_range(0, None, None) is Tri.YES
    with pytest.raises(TypeError):
        c.count_in_range(True, 1, 1)
    with pytest.raises(TypeError):
        c.count_in_range("3", 1, 5)


def test_accepted_count_is_the_accepted_stage_only():
    s = Session("s", "p", afis=(AfiState("ipv4-unicast", Tri.YES, ((Stage.ADJ_RIB_IN, 4),)),))
    assert c.accepted_count(s, "ipv4-unicast") is UNKNOWN
    s2 = Session("s", "p", afis=(AfiState("ipv4-unicast", Tri.YES, ((Stage.ADJ_RIB_IN, 4), (Stage.ACCEPTED, 3))),))
    assert c.accepted_count(s2, "ipv4-unicast") == 3 and c.accepted_count(s2, "ipv6-unicast") is UNKNOWN


@pytest.mark.parametrize("text", ["failed to execute command", "% Unknown command: x", "Error: no such file",
                                  "% Invalid input detected at '^' marker", "ERROR: bad"])
def test_a_lab_command_that_exits_zero_with_failure_text_is_a_failure(text):
    load = ConfigLoad(True, lab_commands=(LabCommand("x", 0, text),), evidence="running config")
    assert c.config_applied(load) is Tri.NO


def test_a_verified_load_needs_evidence_and_clean_output_passes():
    with pytest.raises(CollectionError):
        ConfigLoad(True)
    ok = ConfigLoad(True, lab_commands=(LabCommand("ip route del default", 0, "done"),), evidence="boot log")
    assert c.config_applied(ok) is Tri.YES


def test_quantifiers_and_tri_refuse_the_wrong_types():
    for bad in ([None], [Lookup.UNKNOWN, Tri.YES], [UNKNOWN], [Lookup.ABSENT], [True]):
        with pytest.raises(TypeError):
            c.quantify_all(bad)
    with pytest.raises(TypeError):
        c.Tri.of(Lookup.UNKNOWN)
    with pytest.raises(TypeError):
        c.Tri.of(UNKNOWN)
    with pytest.raises(TypeError):
        c.verdict(True)
    assert c.Tri.of(None) is Tri.UNKNOWN and c.Tri.of(True) is Tri.YES and c.Tri.of(False) is Tri.NO


# construction refuses the shapes ----------------------------------------------------------------------------
def test_types_refuse_discards_dressed_as_gateways_and_evidence_not_in_provenance():
    with pytest.raises(CollectionError):
        NextHop(HopKind.GATEWAY, "0.0.0.0")
    with pytest.raises(CollectionError):
        NextHop(HopKind.GATEWAY, "::")
    with pytest.raises(CollectionError):
        NextHop(HopKind.GATEWAY, "Null0")                     # a typed error, not a bare ValueError
    with pytest.raises(CollectionError):
        NextHop(HopKind.INTERFACE)
    with pytest.raises(CollectionError):                      # C24: another device's answer
        Snapshot(Scope("r1"), prov(device="r2"), Completeness.COMPLETE, (), None, "", True, "show vrf", "ok")
    with pytest.raises(CollectionError):                      # scope evidence must be a command that was run
        Snapshot(Scope("r1"), prov(), Completeness.COMPLETE, (), None, "", True, "a", "ok")


def test_defaults_are_unknown_never_a_value():
    a = Attrs()
    assert a.local_pref is UNKNOWN and a.med is UNKNOWN and a.as_path is UNKNOWN and a.communities is UNKNOWN
    assert a.communities_complete is False
    e = RibEntry(P, Origin.STATIC, FIB)
    assert e.stale is UNKNOWN and e.next_hops == () and e.path_id is None
    assert Tri.UNKNOWN is not Tri.YES
    s = Session("s", "p")
    assert s.state is SessionState.UNKNOWN and s.configured is Tri.UNKNOWN


def test_parse_session_state_is_exact():
    with pytest.raises(CollectionError):
        c.parse_session_state("Established(Pfx)x y")
    assert c.parse_session_state("Established") is SessionState.ESTABLISHED
