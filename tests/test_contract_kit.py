"""The conformance kit tests itself: a reference harness built from the contract's types passes every trap and
control, and for each rule a *naive* harness (what a careless parser hands the core) fails exactly that rule."""
from __future__ import annotations

import pytest

from contract_kit import (AFI4, AFI6, P, P_SUBNETTED, PEER_A, PEER_B, RULES, SCENARIOS, Harness,
                          NotApplicable, assert_conformant, failures, run_kit)
from netdryrun.contract import (Attrs, Cause, CollectionError, Completeness, ConfigLoad, HopKind, LabCommand, NextHop,
                                Origin, Prefix, Provenance, RibEntry, Scope, Session, SessionState, Snapshot, Stage,
                                Tri, AfiState)

PROV = Provenance("r1", ("show route", "show vrf"), 100.0)
FIB = frozenset({Stage.LOC_RIB, Stage.BEST, Stage.FIB})
GW = (NextHop(HopKind.GATEWAY, "10.1.1.1"),)


def snap(items=(), completeness=Completeness.COMPLETE, confirmed=True, cause=None, reason="") -> Snapshot:
    return Snapshot(Scope("r1"), PROV, completeness, tuple(items), cause, reason, confirmed, "show vrf" if confirmed else "",
                    "no pager, row count matches" if completeness is Completeness.COMPLETE else "")


def unknown(cause=Cause.COMMAND_FAILED) -> Snapshot:
    return snap(completeness=Completeness.UNKNOWN, confirmed=False, cause=cause, reason="failed")


def entry(prefix=P, origin=Origin.RECEIVED, stages=FIB, hops=GW, stale=False, peer=PEER_A, **kw) -> RibEntry:
    return RibEntry(prefix, origin, stages, peer, next_hops=hops, stale=stale, **kw)


def sess(peer, state=SessionState.ESTABLISHED, afis=((AFI4, Tri.YES),)) -> Session:
    return Session(f"s-{peer}", peer, configured=Tri.YES, state=state,
                   afis=tuple(AfiState(a, up) for a, up in afis))


def counted(*, accepted=None, received=None, adj_in=None, soft=Tri.UNKNOWN, afi=AFI4) -> Session:
    counts = tuple((st, n) for st, n in ((Stage.ACCEPTED, accepted), (Stage.ADJ_RIB_IN, adj_in)) if n is not None)
    return Session("s", PEER_A, state=SessionState.ESTABLISHED,
                   afis=(AfiState(afi, Tri.YES, counts, soft),))


# What a correct driver hands the core, per rule and kind. (rule, "trap"|"control") -> outcome
GOOD: dict[tuple[str, str], object] = {
    ("C1", "trap"): unknown(), ("C1", "control"): snap([entry()]),
    ("C2", "trap"): snap(completeness=Completeness.TRUNCATED, cause=None), ("C2", "control"): snap([entry()]),
    ("C3", "trap"): snap(completeness=Completeness.UNKNOWN, confirmed=False, cause=Cause.SCOPE_UNCONFIRMED),
    ("C3", "control"): snap(),
    ("C4", "trap"): counted(accepted=3), ("C4", "control"): counted(accepted=3),
    ("C5", "trap"): counted(accepted=3), ("C5", "control"): counted(accepted=3),
    ("C6", "trap"): counted(adj_in=0, soft=Tri.NO), ("C6", "control"): counted(adj_in=0, soft=Tri.YES),
    ("C7", "trap"): snap([entry(stages=frozenset({Stage.LOC_RIB, Stage.BEST}))]), ("C7", "control"): snap([entry()]),
    ("C8", "trap"): snap([entry(hops=(NextHop(HopKind.BLACKHOLE),))]), ("C8", "control"): snap([entry()]),
    ("C9", "trap"): snap([entry(P_SUBNETTED)]), ("C9", "control"): snap([entry()]),
    ("C10", "trap"): snap([entry(stages=frozenset({Stage.LOC_RIB, Stage.BEST}))]), ("C10", "control"): snap([entry()]),
    ("C11", "trap"): snap([sess(PEER_A, SessionState.NO_ROW, ())]), ("C11", "control"): snap([sess(PEER_A)]),
    ("C12", "trap"): snap([sess(PEER_A), sess(PEER_B, SessionState.NOT_ESTABLISHED)]),
    ("C12", "control"): snap([sess(PEER_A), sess(PEER_B, SessionState.NOT_ESTABLISHED)]),
    ("C13", "trap"): snap([entry(), entry(Prefix.parse("198.51.100.0/24"))]),
    ("C13", "control"): snap([entry(), entry(Prefix.parse("198.51.100.0/24"))]),
    ("C14", "trap"): snap([entry()]), ("C14", "control"): snap([entry(attrs=Attrs(local_pref=200))]),
    ("C15", "trap"): snap([sess(PEER_A)]), ("C15", "control"): snap([sess(PEER_A)]),
    ("C16", "trap"): ConfigLoad(verified=False), ("C16", "control"): ConfigLoad(True, evidence="running config"),
    ("C17", "trap"): ConfigLoad(True, evidence="running config", lab_commands=(LabCommand("vtysh -c bad", 1),)),
    ("C17", "control"): ConfigLoad(True, evidence="running config", lab_commands=(LabCommand("ip route del default", 0),)),
    ("C18", "trap"): snap([entry(hops=tuple(NextHop(HopKind.GATEWAY, f"10.1.1.{i}") for i in (1, 2, 3)))]),
    ("C18", "control"): snap([entry(hops=tuple(NextHop(HopKind.GATEWAY, f"10.1.1.{i}") for i in (1, 2)))]),
    ("C19", "trap"): snap([entry(stale=True)]), ("C19", "control"): snap([entry()]),
    ("C20", "trap"): snap([entry(path_id=1), entry(path_id=2, stages=frozenset({Stage.LOC_RIB, Stage.FIB}))]),
    ("C20", "control"): snap([entry()]),
    ("C21", "trap"): snap([entry(hops=(NextHop(HopKind.GATEWAY, "fe80::1", "eth1"),
                                       NextHop(HopKind.GATEWAY, "fe80::1", "eth2")))]),
    ("C21", "control"): snap([entry(hops=(NextHop(HopKind.GATEWAY, "2001:db8::1"),))]),
    ("C22", "trap"): snap([entry(origin=Origin.NETWORK, peer=None)]), ("C22", "control"): snap([entry()]),
    ("C24", "trap"): unknown(), ("C24", "control"): snap([entry()]),
    ("C25", "trap"): CollectionError("row with unknown flag"),
    ("C25", "control"): snap([entry(Prefix.parse("198.51.100.0/24"))]),
    ("C26", "trap"): snap([sess(PEER_A, SessionState.NOT_ESTABLISHED), sess(PEER_B, SessionState.NOT_ESTABLISHED)]),
    ("C26", "control"): snap([sess(PEER_A)]),
    ("C23", "trap"): snap([entry(attrs=Attrs(communities=frozenset({"65000:1"}), communities_complete=False))]),
    ("C23", "control"): snap([entry(attrs=Attrs(communities=frozenset({"65000:1"}), communities_complete=True))]),
}
# C4's trap is judged on an AFI the session does not have; C5 needs the router's received count kept apart
GOOD[("C5", "trap")] = Session("s", PEER_A, state=SessionState.ESTABLISHED, afis=(AfiState(
    AFI4, Tri.YES, ((Stage.ADJ_RIB_IN, 4),)),))      # received 4 known, accepted not derived: UNKNOWN is safe
GOOD[("C12", "trap")] = snap([sess(PEER_A), sess(PEER_B, SessionState.NOT_ESTABLISHED)])
GOOD[("C15", "trap")] = snap([sess(PEER_A)])


class Table(Harness):
    def __init__(self, table):
        self.table = table

    def run(self, rule, kind, variant=0):
        out = self.table[(rule, kind)]
        if isinstance(out, Exception):
            raise out
        return out


# What a careless parser hands the core: the exact shape that caused each false pass. One per rule.
NAIVE: dict[str, object] = {
    "C1": snap(),                                                       # failed command -> empty, complete
    "C2": snap(),                                                       # truncated read as the whole table
    "C3": snap(),                                                       # claims the VRF exists without checking
    "C4": counted(accepted=0, afi=AFI6),                                # unreadable AFI counted as 0 ... see below
    "C5": counted(accepted=4),                                          # received count stored as accepted
    "C6": counted(adj_in=0, soft=Tri.YES),                              # soft-reconfig off, but marked on
    "C7": snap([entry(stages=FIB)]),                                    # best marked installed
    "C8": snap([entry(hops=(NextHop(HopKind.INTERFACE, interface="Null0"),))]),   # blackhole turned into an interface hop
    "C9": snap([entry(Prefix.parse("99.99.99.0/24"))]),                 # mask dropped: /32 became /24
    "C10": snap([entry(stages=FIB)]),                                   # inactive:false read as active
    "C11": snap([sess(PEER_A, SessionState.ESTABLISHED)]),              # no row read as established
    "C12": snap([sess(PEER_B, SessionState.ESTABLISHED), sess(PEER_A, SessionState.NOT_ESTABLISHED)]),  # positional
    "C13": snap([entry(), entry(Prefix.parse("198.51.100.0/24")), entry(Prefix.parse("fe80::/64"))]),
    "C14": snap([entry(attrs=Attrs(local_pref=0))]),                    # missing local-pref became 0
    "C15": snap([sess(PEER_A, afis=((AFI4, Tri.YES), (AFI6, Tri.YES)))]),  # one AFI's state used for all
    "C16": ConfigLoad(True, evidence="running config"),                                   # "no error seen" as verified
    "C17": ConfigLoad(True, evidence="running config", lab_commands=()),                           # failed exec not collected
    "C18": snap([entry(hops=tuple(NextHop(HopKind.GATEWAY, f"10.1.1.{i}") for i in (1, 2)))]),  # extra hop dropped
    "C19": snap([entry(stale=False)]),                                  # stale flag not read
    "C20": snap([entry(path_id=1)]),                                    # add-path paths merged
    "C21": snap([entry(hops=(NextHop(HopKind.GATEWAY, "fe80::1", "eth0"),))]),   # collapsed to one
    "C22": snap([entry(origin=Origin.RECEIVED, peer=PEER_A)]),          # own network statement tagged RECEIVED
    "C23": snap([entry(attrs=Attrs(communities=frozenset(), communities_complete=True))]),   # omitted -> empty
    "C24": snap(),                                                      # the other device's empty table, complete
    "C25": snap(),                                                      # unclassifiable row skipped, rest complete
    "C26": snap([sess(PEER_A), sess(PEER_B)]),                          # every row with a state word is up
}
# more than one careless shape for the same rule: each must fail it too
NAIVE_MORE: dict[str, list[object]] = {
    "C2": [snap(completeness=Completeness.COMPLETE)],                   # "Displayed 20 of 500" read as the whole table
    "C8": [snap()],                                                     # discard route dropped from the table
    "C19": [snap()],                                                    # stale paths deleted, rest COMPLETE
    "C20": [snap([entry(path_id=2)])],                                  # second path overwrote the first
}
# C4's naive parser returns 0 for an AFI it cannot read; the kit asks the session for ipv6-labeled-unicast
NAIVE["C4"] = Session("s", PEER_A, state=SessionState.ESTABLISHED,
                      afis=(AfiState("ipv6-labeled-unicast", Tri.YES, ((Stage.ACCEPTED, 0),)),))


def test_the_kit_has_a_pair_for_every_rule():
    assert RULES == [f"C{i}" for i in range(1, 27)]
    assert len({s.rule for s in SCENARIOS}) == len(SCENARIOS) == 26
    for s in SCENARIOS:
        assert s.source and s.ask and s.name


def test_reference_harness_is_conformant():
    assert_conformant(run_kit(Table(GOOD)))


@pytest.mark.parametrize("rule", RULES)
def test_naive_parser_fails_exactly_that_rule(rule):
    table = dict(GOOD)
    table[(rule, "trap")] = NAIVE[rule]
    bad = failures(run_kit(Table(table)))
    assert bad and all(b.startswith(f"{rule} trap") for b in bad), bad


@pytest.mark.parametrize("rule,i", [(r, i) for r, outs in NAIVE_MORE.items() for i in range(len(outs))])
def test_every_listed_careless_shape_fails_its_rule(rule, i):
    table = dict(GOOD)
    table[(rule, "trap")] = NAIVE_MORE[rule][i]
    bad = failures(run_kit(Table(table)))
    assert bad and all(b.startswith(f"{rule} trap") for b in bad), bad


def test_variants_are_all_run_and_one_bad_variant_fails_the_driver():
    class Fragile(Table):
        variants = 3

        def run(self, rule, kind, variant=0):
            if (rule, kind, variant) == ("C9", "trap", 2):
                return NAIVE["C9"]                      # a parser that breaks on the third surface form
            return super().run(rule, kind)
    results = run_kit(Fragile(GOOD))
    assert len(results) == 26 * 2 * 3
    assert [f for f in failures(results)] == ["C9 trap: the mask was lost: a present /32 read as absent or as another length"]


@pytest.mark.parametrize("rule", RULES)
def test_a_driver_that_refuses_everything_fails_the_controls(rule):
    table = {k: CollectionError("cannot tell") for k in GOOD}
    results = run_kit(Table(table))
    assert [r.status for r in results if r.rule == rule and r.kind == "trap"] == ["pass"]
    assert [r.status for r in results if r.rule == rule and r.kind == "control"] == ["fail"]


def test_an_untyped_crash_is_a_violation_and_not_applicable_must_be_allowed():
    table = dict(GOOD)
    table[("C1", "trap")] = KeyError("routes")
    table[("C20", "trap")] = NotApplicable("this NOS has no add-path")
    table[("C20", "control")] = NotApplicable("this NOS has no add-path")
    results = run_kit(Table(table))
    assert any(r.rule == "C1" and r.status == "fail" and "untyped" in r.message for r in results)
    assert any("C20" in f and "not applicable" in f for f in failures(results))
    assert not [f for f in failures(results, {"C20"}) if f.startswith("C20")]


def test_wrong_outcome_type_is_reported_not_crashed():
    table = dict(GOOD)
    table[("C16", "trap")] = snap()
    [r] = [r for r in run_kit(Table(table)) if r.rule == "C16" and r.kind == "trap"]
    assert r.status == "fail" and "wrong outcome type" in r.message


def test_strict_mode_needs_raw_fixtures_and_two_variants():
    results = run_kit(Table(GOOD), strict=True)
    msgs = failures(results)
    assert any("at least 2 fixture variants" in m for m in msgs)
    assert sum("no raw fixture bytes" in m for m in msgs) == 26 * 2

    class Real(Table):
        variants = 2

        def fixture(self, rule, kind, variant):
            return f"{rule}-{kind}-{variant}".encode()
    assert_conformant(run_kit(Real(GOOD), strict=True))


def test_only_some_rules_may_be_declared_not_applicable():
    results = run_kit(Table(GOOD))
    bad = failures(results, not_applicable={"C1", "C9"})
    assert any(m.startswith("C1:") and "may not be declared" in m for m in bad)
    assert any(m.startswith("C9:") for m in bad)
    assert not failures(results, not_applicable={"C20", "C6"})
