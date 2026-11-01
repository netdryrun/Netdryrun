"""Suggested checks for a survivor, and the classification edges the guardrail tests don't reach."""
from __future__ import annotations

from dataclasses import replace

from netdryrun.checks import Result
from netdryrun.prove import core
from netdryrun.prove.core import CAUGHT, INCONCLUSIVE, NO_EFFECT, SURVIVED
from netdryrun.prove.suggest import MAX_SUGGESTIONS, suggest
from netdryrun.prove.variants import Variant, generate
from netdryrun.verify.engine import DiffItem, diff
from netdryrun.verify.snapshot import ItemKey

import prove_helpers as h
from verify_helpers import attrs, path, session

V = Variant("v", "import_filter", "edge", "d")


def checks(snap_from, snap_to, variant=V):
    return suggest(variant, snap_from, diff(snap_from, snap_to))


def test_a_leak_suggests_the_sessions_exact_count_from_today():
    base = h.custleak()
    out = checks(base, h.custleak(edge_filter=None))
    assert out[0] == {"check": {"type": "bgp_prefixes", "node": "edge", "neighbor": "10.0.1.2", "afi": "ipv4-unicast",
                                "exact": 1},
                      "reason": "the session's prefix count today, exactly: one more prefix fails it. Today it carries "
                                "10.10.0.0/24"}
    assert all(s["check"]["type"] == "bgp_prefixes" for s in out)


def test_a_leaked_default_suggests_the_guard():
    base = h.custleak(edge_filter=None)
    d = Variant("d", "default_leak", "cust", "d", originates=("0.0.0.0/0",))
    out = checks(base, h.custleak(edge_filter=None, cust_extra=["0.0.0.0/0"]), d)
    assert {"check": {"type": "route", "node": "edge", "prefix": "0.0.0.0/0", "protocol": "bgp", "present": False},
            "reason": "a standing guard: 0.0.0.0/0 never via BGP"} in out


def test_a_session_down_suggests_the_session_and_the_routes():
    out = checks(h.custleak(), h.custleak(down=("ce",)))
    got = [s["check"] for s in out]
    assert {"type": "bgp_session", "node": "edge", "neighbor": "10.0.1.2"} in got
    assert {"type": "route", "node": "edge", "prefix": "10.10.0.0/24", "protocol": "bgp"} in got
    assert len(out) <= MAX_SUGGESTIONS


def test_an_attribute_change_pins_todays_best_path():
    base = h.custleak(lp_at={"edge": 200})
    out = checks(base, h.custleak(lp_at={"edge": 50}))
    assert {"check": {"type": "bgp_route", "node": "edge", "prefix": "10.10.0.0/24", "as_path": "65010",
                      "local_pref": 200}, "reason": "the best path's attributes today"} in out


def test_communities_and_another_vrf_are_kept():
    base = h.custleak()
    k = ItemKey("path", "edge", "RED", "ipv4", "unicast", "10.9.0.0/24", neighbor="10.0.1.2")
    before = path(as_path="65010", communities=("65000:1",), local_pref=None)
    after = replace(before, attrs=replace(before.attrs, communities=()))
    out = suggest(V, base, [DiffItem(k, before, after)])
    assert out == [{"check": {"type": "bgp_route", "node": "edge", "prefix": "10.9.0.0/24", "vrf": "RED",
                              "as_path": "65010", "communities": ["65000:1"]},
                    "reason": "the best path's attributes today"}]


def test_a_best_path_that_moved_is_pinned():
    base = h.custleak()
    k = ItemKey("path", "edge", "default", "ipv4", "unicast", "10.10.0.0/24", neighbor="10.0.1.2")
    out = suggest(V, base, [DiffItem(k, path(as_path="65010", local_pref=150), None)])
    assert out == [{"check": {"type": "bgp_route", "node": "edge", "prefix": "10.10.0.0/24", "as_path": "65010",
                              "local_pref": 150}, "reason": "the best path today (it moved)"}]
    assert suggest(V, base, [DiffItem(k, path(best=False, as_path="65010"), None)]) == []


def test_only_advertisements_changed_says_no_check_can_see_it():
    base = h.custleak()
    k = ItemKey("adj_out", "edge", "default", "ipv4", "unicast", "10.10.0.0/24", neighbor="192.0.2.9")
    out = suggest(V, base, [DiffItem(k, None, attrs(next_hop="10.0.1.1"))])
    assert out[0]["check"] is None and "no check type reads advertisements" in out[0]["reason"]
    s = ItemKey("session", "edge", "default", neighbor="10.0.1.2")
    assert suggest(V, base, [DiffItem(s, session("10.0.1.1"), session(None, state="idle")),
                             DiffItem(k, None, attrs())])[-1]["check"]["type"] == "bgp_session"
    # a session that was down before isn't suggested; a local path added is the node's own: nothing to suggest
    assert suggest(V, base, [DiffItem(s, session(None, state="idle"), session("10.0.1.1"))]) == []
    lk = ItemKey("path", "edge", "default", "ipv4", "unicast", "10.10.0.0/24", neighbor="local")
    assert suggest(V, base, [DiffItem(lk, None, path(as_path=""))]) == []


def test_suggestions_are_unique_and_capped():
    base = h.custleak()
    s = ItemKey("session", "edge", "default", neighbor="10.0.1.2")
    d = DiffItem(s, session("10.0.1.1"), session(None, state="idle"))
    assert len(suggest(V, base, [d, d])) == 1
    many = [DiffItem(ItemKey("session", "edge", "default", neighbor=f"10.0.9.{i}"), session("10.0.1.1"),
                     session(None, state="idle")) for i in range(9)]
    assert len(suggest(V, base, many)) == MAX_SUGGESTIONS


# ---------------------------------------------------------------------------------------------------------
# core edges
# ---------------------------------------------------------------------------------------------------------

def test_classify_order_of_rules():
    c = h.evaluate([], h.custleak())
    del c
    from netdryrun.config import load
    chk = load(h.FIXTURE / "netdryrun.yml").checks[0]
    real = Result(chk, False, "state is idle", 1, 0.0, core.now(), [{"cmd": "x"}], [])
    ok = replace(real, passed=True)
    eff = diff(h.custleak(), h.custleak(down=("ce",)))
    assert core.classify(V, eff, [real, ok]).result == CAUGHT
    assert core.classify(V, eff, [real]).failed == [real]
    assert core.classify(V, [], [real]).result == INCONCLUSIVE
    assert core.classify(V, [], [ok]).result == NO_EFFECT
    assert core.classify(V, eff, [ok]).result == SURVIVED and core.classify(V, eff, [ok]).note == ""
    assert core.classify(V, eff, [ok]).effect == eff


def test_took_effect_edges():
    base = h.custleak()
    vs = {v.id: v for v in generate({n: ns.config for n, ns in base.nodes.items()}, h.LINKS)}
    v = vs["default_leak:cust:0.0.0.0/0"]
    configured_only = h.applied(v, base)   # the config lines are in, the route is not in cust's BGP table
    assert "its BGP table doesn't have it" in core.took_effect(v, base, configured_only)
    ok = h.applied(v, h.custleak(cust_extra=["0.0.0.0/0"]))
    assert core.took_effect(v, base, ok) is None
    gone = h.custleak()
    del gone.nodes["up"]
    assert core.took_effect(v, base, gone) == "up is not in both snapshots"
    ghost = replace(v, node="ghost")
    assert core.took_effect(ghost, base, base) == "ghost is not in the snapshot"
    assert core.took_effect(vs["link_down:cust:eth1--edge:eth1"], base, h.custleak(link_down=("ce",))) is None


def test_sessions_reset():
    base = h.custleak()
    down = h.custleak(down=("ce",))
    vs = {v.id: v for v in generate({n: ns.config for n, ns in base.nodes.items()}, h.LINKS)}
    v = vs["attribute_drift:edge:CUST-IN permit 10:+set local-preference 50"]
    assert core.sessions_reset(v, base, down) == ["cust session 10.0.1.1", "edge session 10.0.1.2"]
    assert core.sessions_reset(vs["session_down:cust:10.0.1.1"], base, down) == []
    assert core.sessions_reset(vs["link_down:cust:eth1--edge:eth1"], base, down) == []
    assert core.sessions_reset(v, base, base) == []
    # maximum-prefix on the neighbor: the network dropped it on purpose
    capped = h.with_config(down, "edge", adds=("router bgp 65000 > address-family ipv4 unicast > "
                                               "neighbor 10.0.1.2 maximum-prefix 2",))
    capped = h.with_config(capped, "cust", adds=("router bgp 65010 > address-family ipv4 unicast > "
                                                 "neighbor 10.0.1.1 maximum-prefix 2",))
    assert core.sessions_reset(v, base, capped) == []
    # a session that disappeared counts as down
    gone = h.custleak()
    k = next(k for k in gone.nodes["edge"].items if k.kind == "session" and k.neighbor == "10.0.2.2")
    del gone.nodes["edge"].items[k]
    assert core.sessions_reset(v, base, gone) == ["edge session 10.0.2.2"]


def test_a_reset_under_a_policy_variant_is_inconclusive():
    from netdryrun.config import load
    cks = load(h.FIXTURE / "netdryrun.yml").checks
    base = h.custleak()
    vs = {v.id: v for v in generate({n: ns.config for n, ns in base.nodes.items()}, h.LINKS, cks, core._counts(base))}
    vid = "attribute_drift:edge:CUST-IN permit 10:+set local-preference 50"
    ex = h.FakeExecutor(base, {vid: h.applied(vs[vid], h.custleak(down=("ce",)))})
    res = core._one(ex, vs[vid], cks, base, ex.side_state(), core._Fresh(), core.now)
    assert res.result == INCONCLUSIVE and "may have reset them" in res.note and res.failed and res.effect


def test_fitted_needs_a_prefix():
    from netdryrun.config import load
    cks = load(h.FIXTURE / "netdryrun.yml").checks
    leak = Variant("l", "customer_leak", "cust", "d", originates=("100.64.0.0/24",))
    session_check = cks[0]
    assert not core._fitted(session_check, leak)
    bad = replace(cks[-1], params={**cks[-1].params, "prefix": "not a prefix"})
    assert not core._fitted(bad, leak)
    v6 = replace(cks[-1], params={**cks[-1].params, "node": "cust", "prefix": "2001:db8::/32"})
    assert not core._fitted(v6, Variant("d", "default_leak", "cust", "d", originates=("::/0", "0.0.0.0/0")))
    assert core._fitted(replace(v6, params={**v6.params, "prefix": "::/0"}),
                        Variant("d", "default_leak", "cust", "d", originates=("::/0",)))
    # a default-route guard covers the leak space but isn't fitted to it
    guard = replace(cks[-1], params={**cks[-1].params, "node": "edge", "prefix": "0.0.0.0/0"})
    assert not core._fitted(guard, leak)
    assert core._fitted(replace(guard, params={**guard.params, "prefix": "100.64.0.0/10"}), leak)
    assert core._fitted(replace(guard, params={**guard.params, "prefix": "100.127.255.0/24"}), leak)
    assert not core._fitted(replace(guard, params={**guard.params, "prefix": "100.128.0.0/24"}), leak)
    assert not core._fitted(replace(guard, params={**guard.params, "prefix": "100.64.0.0/24"}),
                            Variant("d", "default_leak", "cust", "d", originates=("0.0.0.0/0",)))


def test_same_state_and_counts():
    a, b = h.custleak(), h.custleak()
    assert core.same_state(a, b) == []
    del b.nodes["up"]
    assert core.same_state(a, b)[0].startswith("the observed nodes differ")
    c = h.custleak()
    c.unobserved["host"] = "a host"
    assert core.same_state(a, c)[0].startswith("the observed nodes differ")
    counts = core._counts(a)
    assert counts[("edge", "10.0.1.2", "ipv4-unicast")] == 1 and counts[("up", "10.0.2.1", "ipv4-unicast")] == 1
    red = h.custleak()
    k = next(k for k in red.nodes["edge"].items if k.kind == "session")
    s = red.nodes["edge"].items.pop(k)
    red.nodes["edge"] = replace(red.nodes["edge"], vrfs=("RED", "default"))
    red.nodes["edge"].items[replace(k, vrf="RED")] = s
    assert (k.node, k.neighbor, "ipv4-unicast") not in core._counts(red)


def test_summary_wording():
    rep = core.ProveReport(status="passed")
    rep.variants = [core.VariantResult(V, CAUGHT), core.VariantResult(V, NO_EFFECT)]
    assert rep.summary == ("caught 1 of 1 known-bad variants with an effect (0 survived, 0 inconclusive; 1 more had "
                           "no effect on routing). A finite set of variants: this does not show that the checks are "
                           "complete.")
    rep.not_run = [V, V]
    assert "; 2 generated variant(s) not run (budget). A finite" in rep.summary
    assert core.ProveReport(status="error", error="x").summary == "no strength result: x"
    assert [core.ProveReport(status=s).exit_code for s in ("passed", "failed", "inconclusive", "error", "?")] == \
        [0, 1, 3, 2, 2]
