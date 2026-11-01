"""Red tests for the guardrails of `netdryrun prove` (design: check strength, "Guardrails (fail closed)").

Each test builds the state a live run would record (tests/prove_helpers.py: the customer-leak lab as snapshots, the
checks evaluated on them by the real check evaluators) and asserts the result prove must give, above all that it never
reports a false "caught", a false "no effect" or a strength result on a polluted lab.
"""
from __future__ import annotations

from dataclasses import replace

import pytest
import yaml

from netdryrun.checks import Result, Unready
from netdryrun.config import load as load_config_file
from netdryrun.prove import core
from netdryrun.prove.core import CAUGHT, INCONCLUSIVE, NO_EFFECT, SURVIVED, prove
from netdryrun.prove.variants import generate, leak_prefixes

import prove_helpers as h

PLAIN = "import_filter:edge:CUST-IN permit 10:match ip address prefix-list CUST-IN"
FILTER = PLAIN + ":+leak:cust"   # the same, while cust announces one more prefix: the first import_filter variant
LEAK1 = ["100.64.0.0/24"]


@pytest.fixture(scope="module")
def old_checks():
    """The checks 0.3.3 and 0.4.0 `record` wrote on the good config (prefix ranges, routes, guards)."""
    return load_config_file(h.FIXTURE / "netdryrun.yml").checks


def checks_from(tmp_path, edit):
    data = yaml.safe_load((h.FIXTURE / "netdryrun.yml").read_text(encoding="utf-8"))
    data["checks"] = edit(data["checks"])
    (tmp_path / "configs").mkdir()
    for f in (h.FIXTURE / "configs").iterdir():
        (tmp_path / "configs" / f.name).write_text(f.read_text(encoding="utf-8"), encoding="utf-8")
    (tmp_path / "topology.clab.yml").write_text((h.FIXTURE / "topology.clab.yml").read_text(encoding="utf-8"),
                                                encoding="utf-8")
    (tmp_path / "netdryrun.yml").write_text(yaml.safe_dump(data), encoding="utf-8")
    return load_config_file(tmp_path / "netdryrun.yml").checks


def variants(checks, base=None):
    base = base or h.custleak()
    return {v.id: v for v in generate({n: ns.config for n, ns in base.nodes.items()}, h.LINKS, checks,
                                      core._counts(base))}


def filter_removed(vs):
    """The stranger's case: edge's customer filter lost its match line, so whatever cust sends is accepted: its
    203.0.113.128/25 and the prefix the variant has it announce."""
    return h.applied(vs[FILTER], h.custleak(cust_extra=LEAK1, edge_filter=None))


# ---------------------------------------------------------------------------------------------------------
# The stranger's case (must-fail corpus case of the design)
# ---------------------------------------------------------------------------------------------------------

def test_old_record_checks_let_the_import_filter_variant_survive(old_checks):
    vs = variants(old_checks)
    ex = h.FakeExecutor(h.custleak(), {FILTER: filter_removed(vs)})
    rep = prove(ex, old_checks, kinds=["import_filter"], maximum=1)
    assert [v.variant.id for v in rep.variants] == [FILTER]
    (v,) = rep.variants
    assert v.result == SURVIVED, v
    assert rep.status == "failed" and rep.exit_code == 1
    unnoticed = {d.key.where() for d in v.effect}
    assert "edge 203.0.113.128/25 path from 10.0.1.2" in unnoticed and "up 203.0.113.128/25 [bgp]" in unnoticed
    assert {"type": "bgp_prefixes", "node": "edge", "neighbor": "10.0.1.2", "afi": "ipv4-unicast", "exact": 1} in \
        [s["check"] for s in v.suggested]
    assert "edge 100.64.0.0/24 path from 10.0.1.2" in unnoticed
    assert not any(d.key.node == "cust" for d in v.effect)   # cust's own announcement is the variant's footprint
    assert "caught 0 of 1" in rep.summary and "does not show that the checks are complete" in rep.summary


def test_the_plain_filter_variant_survives_on_what_the_customer_sends_today(old_checks):
    """Without the companion leak: cust's own 203.0.113.128/25, which it doesn't own, gets in (the stranger's run)."""
    from netdryrun.prove.core import _Fresh, _one

    vs = variants(old_checks)
    base = h.custleak()
    ex = h.FakeExecutor(base, {PLAIN: h.applied(vs[PLAIN], h.custleak(edge_filter=None))})
    res = _one(ex, vs[PLAIN], old_checks, base, ex.side_state(), _Fresh(), core.now)
    assert res.result == SURVIVED
    assert "edge 203.0.113.128/25 path from 10.0.1.2" in {d.key.where() for d in res.effect}


def test_a_run_that_reports_the_old_checks_as_strong_fails(old_checks):
    """The whole default budget on the old checks: the filter variant must be among the survivors."""
    base = h.custleak()
    vs = variants(old_checks, base)
    run = {v.variant.id: v.result for v in prove(h.FakeExecutor(base, default_states(vs)), old_checks).variants}
    assert run[FILTER] == SURVIVED
    assert run["session_down:cust:10.0.1.1"] == CAUGHT
    assert run["customer_leak:cust:1"] == NO_EFFECT   # edge's filter works on the good config: contained


def default_states(vs):
    leak = lambda n: h.custleak(cust_extra=leak_prefixes(n))  # noqa: E731
    states = {
        "customer_leak:cust:1": leak(1), "customer_leak:cust:2": leak(2),
        FILTER: h.custleak(cust_extra=LEAK1, edge_filter=None),
        "session_down:cust:10.0.1.1": h.custleak(down=("ce",)),
        "link_down:cust:eth1--edge:eth1": h.custleak(link_down=("ce",)),
        "attribute_drift:cust:ALLOW-ALL permit 10:+set local-preference 50": h.custleak(lp_at={"cust": 50}),
        "default_leak:cust:0.0.0.0/0": h.custleak(cust_extra=["0.0.0.0/0"]),
        "link_subnet_leak:cust:10.0.1.0/30": h.custleak(cust_extra=["10.0.1.0/30"]),
    }
    return {k: h.applied(vs[k], s) for k, s in states.items()}


def test_exact_counts_catch_the_import_filter_variant(tmp_path):
    def exact(checks):
        for c in checks:
            if c["type"] == "bgp_prefixes":
                c.pop("max"), c.pop("min")
                c["exact"] = 1
        return checks
    checks = checks_from(tmp_path, exact)
    vs = variants(checks)
    rep = prove(h.FakeExecutor(h.custleak(), {FILTER: filter_removed(vs)}), checks, kinds=["import_filter"], maximum=1)
    (v,) = rep.variants
    assert v.result == CAUGHT
    assert {r.check.node for r in v.failed} == {"edge", "up"} and all(r.evidence for r in v.failed)
    assert rep.status == "passed" and rep.exit_code == 0


def test_041_only_lists_catch_the_import_filter_variant(tmp_path):
    """The 0.4.1 `record` checks (prefix lists per eBGP session) must catch it. `only:` comes with 0.4.1: this branch
    runs it once it is rebased onto the release (phase 2)."""
    from netdryrun.config import CHECK_TYPES
    if "only" not in CHECK_TYPES["bgp_prefixes"]["optional"]:
        pytest.skip("bgp_prefixes `only:` is not in this base (0.4.1 adds it); runs after the rebase onto 0.4.1")
    only = {("edge", "10.0.1.2"): ["10.10.0.0/24"], ("edge", "10.0.2.2"): ["198.51.100.0/24"],
            ("cust", "10.0.1.1"): ["198.51.100.0/24"], ("up", "10.0.2.1"): ["10.10.0.0/24"]}

    def add_only(checks):
        for c in checks:
            if c["type"] == "bgp_prefixes":
                c["only"] = only[(c["node"], c["neighbor"])]
        return checks
    checks = checks_from(tmp_path, add_only)
    vs = variants(checks)
    (v,) = prove(h.FakeExecutor(h.custleak(), {FILTER: filter_removed(vs)}), checks, kinds=["import_filter"],
                 maximum=1).variants
    assert v.result == CAUGHT


# ---------------------------------------------------------------------------------------------------------
# A false "caught"
# ---------------------------------------------------------------------------------------------------------

def stale_results(source):
    return lambda checks: source


def test_caught_needs_results_from_the_variants_own_run(old_checks):
    """An executor that hands back an earlier run's results (one where checks failed) is an internal error."""
    vs = variants(old_checks)
    earlier = h.evaluate(old_checks, h.custleak(down=("ce",)), started="2000-01-01T00:00:00+00:00")
    ex = h.FakeExecutor(h.custleak(), {FILTER: filter_removed(vs)}, results={FILTER: stale_results(earlier)})
    rep = prove(ex, old_checks, kinds=["import_filter"], maximum=1)
    assert rep.status == "error" and rep.exit_code == 2 and "earlier run" in rep.error
    assert not rep.variants


def test_a_result_object_reused_from_an_earlier_call_is_refused(old_checks):
    vs = variants(old_checks)
    failing = h.evaluate(old_checks, h.custleak(down=("ce",)))
    ex = h.FakeExecutor(h.custleak(), {FILTER: filter_removed(vs),
                                       PLAIN: h.applied(vs[PLAIN], h.custleak(edge_filter=None))},
                        results={FILTER: stale_results(failing), PLAIN: stale_results(failing)})
    rep = prove(ex, old_checks, kinds=["import_filter"], maximum=2)
    assert rep.status == "error" and "earlier run" in rep.error


def test_results_must_cover_every_check_in_order(old_checks):
    vs = variants(old_checks)
    ex = h.FakeExecutor(h.custleak(), {FILTER: filter_removed(vs)},
                        results={FILTER: lambda checks: h.evaluate(checks[1:], filter_removed(vs))})
    rep = prove(ex, old_checks, kinds=["import_filter"], maximum=1)
    assert rep.status == "error" and "result(s) for" in rep.error


def unready(results):
    return [replace(r, passed=False, detail=Unready("error: vtysh: bgpd is not running"), evidence=[])
            if r.check.type == "bgp_session" else r for r in results]


def test_failures_with_no_usable_state_are_never_a_catch(old_checks):
    vs = variants(old_checks)
    ex = h.FakeExecutor(h.custleak(), {FILTER: filter_removed(vs)},
                        results={FILTER: lambda checks: unready(h.evaluate(checks, filter_removed(vs)))})
    (v,) = prove(ex, old_checks, kinds=["import_filter"], maximum=1).variants
    assert v.result == INCONCLUSIVE and "no usable state" in v.note


def test_a_failure_without_evidence_is_not_a_catch():
    c = load_config_file(h.FIXTURE / "netdryrun.yml").checks[0]
    r = Result(c, False, "state is idle", 1, 0.0, core.now(), [], [])
    assert not core.real_failure(r)
    assert core.real_failure(replace(r, evidence=[{"cmd": "x"}]))
    assert not core.real_failure(replace(r, evidence=[{"cmd": "x"}], detail=Unready("error: x")))
    assert not core.real_failure(replace(r, passed=True, evidence=[{"cmd": "x"}]))


def test_failing_checks_without_a_routing_effect_are_inconclusive(old_checks):
    """A check that fails while the routing state is the baseline (a flake, or the data plane) is not a catch."""
    vs = variants(old_checks)
    v = vs[PLAIN]
    unchanged = h.applied(v, h.custleak())   # the line is gone, but nothing it filtered is accepted
    flaky = lambda checks: [replace(r, passed=False, detail="state is idle") if i == 0 else r  # noqa: E731
                            for i, r in enumerate(h.evaluate(checks, unchanged))]
    from netdryrun.prove.core import _Fresh, _one
    base = h.custleak()
    ex = h.FakeExecutor(base, {v.id: unchanged}, results={v.id: flaky})
    res = _one(ex, v, old_checks, base, ex.side_state(), _Fresh(), core.now)
    assert res.result == INCONCLUSIVE and "not counted as caught" in res.note.lower()


def test_a_check_on_the_leak_prefix_is_stepped_around(tmp_path):
    """A check written for the variant's own leak prefix doesn't catch it: the leak moves to the next free /24."""
    def fitted(checks):
        return checks + [{"type": "route", "node": "edge", "prefix": "100.64.0.0/24", "protocol": "bgp", "present": False}]
    checks = checks_from(tmp_path, fitted)
    vid = "customer_leak:cust:1"
    vs = variants(checks, h.custleak(edge_filter=None))
    assert vs[vid].originates == ("100.64.1.0/24",)
    leaky = h.applied(vs[vid], h.custleak(cust_extra=["100.64.1.0/24"], edge_filter=None))
    (v,) = prove(h.FakeExecutor(h.custleak(edge_filter=None), {vid: leaky}), checks, kinds=["customer_leak"],
                 maximum=1).variants
    assert v.result == SURVIVED


def test_a_catch_only_by_checks_on_the_variants_own_prefixes_is_survived(old_checks):
    """Defence in depth: classify() never credits a check that names the leak, or the announcing node's own prefix."""
    vs = variants(old_checks)
    v = vs["customer_leak:cust:1"]
    on_leak = replace(old_checks[-1], params={"node": "edge", "prefix": "100.64.0.0/24", "protocol": "bgp",
                                              "present": False})
    on_own = replace(old_checks[-1], params={"node": "cust", "prefix": "100.64.0.0/24", "protocol": "bgp",
                                             "present": False})
    effect = core.diff(h.custleak(), h.custleak(edge_filter=None))
    for c in (on_leak, on_own):
        r = Result(c, False, "unexpectedly present via bgp", 1, 0.0, core.now(), [{"cmd": "x"}], [])
        res = core.classify(v, effect, [r])
        assert res.result == SURVIVED and "fitted to this variant" in res.note
    d = vs["default_leak:cust:0.0.0.0/0"]
    guard_on_cust = replace(old_checks[-1], params={"node": "cust", "prefix": "0.0.0.0/0", "protocol": "bgp",
                                                    "present": False})
    r = Result(guard_on_cust, False, "unexpectedly present via bgp", 1, 0.0, core.now(), [{"cmd": "x"}], [])
    assert core.classify(d, effect, [r]).result == SURVIVED   # cust's own default isn't what the network did
    guard_on_edge = replace(guard_on_cust, params={**guard_on_cust.params, "node": "edge"})
    r = Result(guard_on_edge, False, "unexpectedly present via bgp", 1, 0.0, core.now(), [{"cmd": "x"}], [])
    assert core.classify(d, effect, [r]).result == CAUGHT     # edge accepting it is


def test_fitted_is_only_about_the_customer_leak(tmp_path):
    c = load_config_file(h.FIXTURE / "netdryrun.yml").checks
    guard = next(x for x in c if x.params.get("prefix") == "0.0.0.0/0")
    vs = variants(c)
    assert not core._fitted(guard, vs["default_leak:cust:0.0.0.0/0"])
    assert core._fitted(replace(guard, params={**guard.params, "prefix": "100.64.0.0/24"}), vs["customer_leak:cust:1"])
    assert not core._fitted(replace(guard, params={**guard.params, "prefix": "100.63.0.0/16"}), vs["customer_leak:cust:1"])
    assert not core._fitted(c[0], vs["customer_leak:cust:1"])   # no prefix: a session check


# ---------------------------------------------------------------------------------------------------------
# A false "no effect"
# ---------------------------------------------------------------------------------------------------------

def test_a_config_variant_that_did_not_take_effect_is_an_error(old_checks):
    """vtysh accepted nothing: the snapshot is the baseline, which must not read as 'no effect'."""
    ex = h.FakeExecutor(h.custleak(), {})
    rep = prove(ex, old_checks, kinds=["import_filter"], maximum=1)
    assert rep.status == "error" and rep.exit_code == 2 and "did not take effect" in rep.error
    assert ex.reverted == [FILTER]


def test_a_variant_that_changed_more_config_than_it_says_is_an_error(old_checks):
    vs = variants(old_checks)
    extra = h.with_config(filter_removed(vs), "edge", adds=("router bgp 65000 > bgp bestpath as-path ignore",))
    rep = prove(h.FakeExecutor(h.custleak(), {FILTER: extra}), old_checks, kinds=["import_filter"], maximum=1)
    assert rep.status == "error" and "did not take effect" in rep.error


def test_a_config_change_on_another_node_is_an_error(old_checks):
    vs = variants(old_checks)
    other = h.with_config(filter_removed(vs), "up", adds=("router bgp 65020 > neighbor 10.0.2.1 shutdown",))
    rep = prove(h.FakeExecutor(h.custleak(), {FILTER: other}), old_checks, kinds=["import_filter"], maximum=1)
    assert rep.status == "error" and "running config of up changed too" in rep.error


def test_a_link_down_with_no_effect_did_not_happen(old_checks):
    rep = prove(h.FakeExecutor(h.custleak(), {}), old_checks, kinds=["link_down"], maximum=1)
    assert rep.status == "error" and "did not go down" in rep.error


def test_a_contained_leak_is_no_effect_not_survived(old_checks):
    """cust announces 100.64.0.0/24 and edge filters it: only cust's own announcement changed (the footprint)."""
    vid = "customer_leak:cust:1"
    vs = variants(old_checks)
    (v,) = prove(h.FakeExecutor(h.custleak(), {vid: h.applied(vs[vid], h.custleak(cust_extra=leak_prefixes(1)))}),
                 old_checks, kinds=["customer_leak"], maximum=1).variants
    assert v.result == NO_EFFECT


def test_a_leak_that_gets_through_is_an_effect(old_checks):
    vid = "customer_leak:cust:1"
    base = h.custleak(edge_filter=None)
    vs = variants(old_checks, base)
    leaky = h.applied(vs[vid], h.custleak(cust_extra=leak_prefixes(1), edge_filter=None))
    (v,) = prove(h.FakeExecutor(base, {vid: leaky}), old_checks, kinds=["customer_leak"], maximum=1).variants
    assert v.result == SURVIVED   # one more prefix sits inside every recorded range
    assert {d.key.node for d in v.effect} == {"edge", "up"}


def test_the_footprint_is_only_the_announcing_node_and_what_its_lab_neighbors_received():
    base = h.custleak()
    vs = variants([], base)
    v = vs["customer_leak:cust:1"]
    during = h.applied(v, h.custleak(cust_extra=leak_prefixes(1), edge_filter=None))
    own = core.footprint(v, base, during)
    kinds = {(d.key.node, d.key.kind): own(d) for d in core.diff(base, during) if d.key.kind != "config"}
    assert kinds[("cust", "rib")] and kinds[("cust", "path")] and kinds[("cust", "adj_out")]
    assert not kinds[("edge", "path")] and not kinds[("edge", "rib")] and not kinds[("up", "path")]
    assert not kinds[("edge", "adj_out")]
    # a variant that announces nothing has no footprint
    sd = vs["session_down:cust:10.0.1.1"]
    assert not any(core.footprint(sd, base, during)(d) for d in core.diff(base, during))


def test_a_leak_to_a_neighbor_outside_the_lab_stays_an_effect():
    """cust's advertisement to a neighbor no lab node stands for is the only place the leak shows: not footprint."""
    from netdryrun.verify.snapshot import ItemKey
    from verify_helpers import attrs

    base = h.custleak()
    vs = variants([], base)
    v = vs["customer_leak:cust:1"]
    during = h.applied(v, h.custleak(cust_extra=leak_prefixes(1)))
    key = ItemKey("adj_out", "cust", "default", "ipv4", "unicast", "100.64.0.0/24", neighbor="192.0.2.99")
    during.nodes["cust"].items[key] = attrs(next_hop="10.0.1.2")
    assert [d.key for d in core.routing_effect(v, base, during)] == [key]
    # and adj_in on a lab node is footprint only when it came from the announcing node
    ki = ItemKey("adj_in", "edge", "default", "ipv4", "unicast", "100.64.0.0/24", neighbor="10.0.1.2")
    ko = ItemKey("adj_in", "edge", "default", "ipv4", "unicast", "100.64.0.0/24", neighbor="10.0.2.2")
    during.nodes["edge"].items[ki] = attrs(next_hop="10.0.1.2")
    during.nodes["edge"].items[ko] = attrs(next_hop="10.0.2.2")
    assert {d.key for d in core.routing_effect(v, base, during)} == {key, ko}


# ---------------------------------------------------------------------------------------------------------
# A polluted lab between variants
# ---------------------------------------------------------------------------------------------------------

def test_a_lab_not_back_to_its_baseline_stops_the_run(old_checks):
    vs = variants(old_checks)
    ex = h.FakeExecutor(h.custleak(), {FILTER: filter_removed(vs)}, after={FILTER: h.custleak(edge_filter=None)})
    rep = prove(ex, old_checks, kinds=["import_filter"], maximum=2)
    assert rep.status == "error" and rep.exit_code == 2 and "differs from the baseline" in rep.error
    assert len(ex.applied) == 1   # no later variant ran on the polluted lab


def test_a_config_left_behind_is_pollution_even_with_the_same_routes(old_checks):
    vs = variants(old_checks)
    ex = h.FakeExecutor(h.custleak(), {FILTER: filter_removed(vs)},
                        after={FILTER: h.with_config(h.custleak(), "edge", removes=vs[FILTER].removes)})
    rep = prove(ex, old_checks, kinds=["import_filter"], maximum=2)
    assert rep.status == "error" and "edge running config" in rep.error


def test_prefix_counts_left_different_are_pollution(old_checks):
    """Prefix counts are not part of verify's diff; the restore check compares them too."""
    vs = variants(old_checks)
    base = h.custleak()
    after = h.custleak()
    k = next(k for k in after.nodes["edge"].items if k.kind == "session" and k.neighbor == "10.0.1.2")
    after.nodes["edge"].items[k] = replace(after.nodes["edge"].items[k], prefix_counts=(("ipv4-unicast", 7),))
    assert not core.diff(base, after)
    rep = prove(h.FakeExecutor(base, {FILTER: filter_removed(vs)}, after={FILTER: after}), old_checks,
                kinds=["import_filter"], maximum=1)
    assert rep.status == "error" and "session 10.0.1.2" in rep.error


def test_a_revert_that_fails_stops_the_run(old_checks):
    vs = variants(old_checks)
    ex = h.FakeExecutor(h.custleak(), {FILTER: filter_removed(vs)})
    ex.fail_revert.add(FILTER)
    rep = prove(ex, old_checks, kinds=["import_filter"], maximum=2)
    assert rep.status == "error" and "could not revert" in rep.error and len(ex.applied) == 1


def test_a_variant_that_fails_to_apply_is_still_reverted_and_checked(old_checks):
    vs = variants(old_checks)
    ex = h.FakeExecutor(h.custleak(), {FILTER: filter_removed(vs)})
    ex.fail_apply.add(FILTER)
    rep = prove(ex, old_checks, kinds=["import_filter"], maximum=2)
    assert ex.reverted == [FILTER]
    assert rep.status == "error" and "could not be applied" in rep.error and "vtysh rejected" in rep.error


def test_checks_that_fail_after_a_clean_revert_stop_the_run(old_checks):
    vs = variants(old_checks)
    calls = {"n": 0}

    class Flaky(h.FakeExecutor):
        def run_checks(self, checks):
            out = super().run_checks(checks)
            calls["n"] += 1
            if calls["n"] == 3:   # baseline, the variant's run, then the run after the revert
                out = [replace(r, passed=False, detail="state is idle") if i == 0 else r for i, r in enumerate(out)]
            return out
    rep = prove(Flaky(h.custleak(), {FILTER: filter_removed(vs)}), old_checks, kinds=["import_filter"], maximum=1)
    assert rep.status == "error" and "can't be attributed" in rep.error


def test_a_lab_that_never_settles_after_a_revert_stops_the_run(old_checks):
    from netdryrun.verify.converge import Inconclusive
    vs = variants(old_checks)
    ex = h.FakeExecutor(h.custleak(), {FILTER: filter_removed(vs)}, after={FILTER: Inconclusive("kept moving", [])})
    rep = prove(ex, old_checks, kinds=["import_filter"], maximum=1)
    assert rep.status == "error" and "never settled" in rep.error


def test_a_variant_that_never_settles_is_inconclusive(old_checks):
    from netdryrun.verify.converge import Inconclusive
    ex = h.FakeExecutor(h.custleak(), {FILTER: Inconclusive("kept moving", ["edge x"])})
    rep = prove(ex, old_checks, kinds=["import_filter"], maximum=1)
    (v,) = rep.variants
    assert v.result == INCONCLUSIVE and "kept moving" in v.note
    assert rep.status == "inconclusive" and rep.exit_code == 3


# ---------------------------------------------------------------------------------------------------------
# No strength result where nothing was measured
# ---------------------------------------------------------------------------------------------------------

def test_failing_baseline_checks_give_no_strength_result(old_checks):
    ex = h.FakeExecutor(h.custleak(down=("ce",)))
    rep = prove(ex, old_checks)
    assert rep.status == "error" and rep.exit_code == 2 and "must pass on the lab as it is" in rep.error
    assert not ex.applied


def test_an_unsettled_baseline_gives_no_strength_result(old_checks):
    from netdryrun.verify.converge import Inconclusive

    class Unsettled(h.FakeExecutor):
        def snapshot(self):
            return Inconclusive("kept moving", [])
    rep = prove(Unsettled(h.custleak()), old_checks)
    assert rep.status == "error" and "never settled" in rep.error


def test_no_checks_no_result():
    rep = prove(h.FakeExecutor(h.custleak()), [])
    assert rep.status == "error" and "no checks" in rep.error


def test_no_variant_no_result(old_checks):
    ex = h.FakeExecutor(h.custleak(), links=[])
    rep = prove(ex, old_checks, kinds=["link_down"])
    assert rep.status == "error" and rep.exit_code == 2 and "no variant" in rep.error
    assert "caught" not in rep.summary


def test_only_no_effect_variants_are_inconclusive_not_passed(old_checks):
    vs = variants(old_checks)
    vid = "customer_leak:cust:1"
    rep = prove(h.FakeExecutor(h.custleak(), {vid: h.applied(vs[vid], h.custleak(cust_extra=leak_prefixes(1)))}),
                old_checks, kinds=["customer_leak"], maximum=1)
    assert rep.status == "inconclusive" and rep.exit_code == 3
    assert "caught 0 of 0" in rep.summary


def test_bad_kinds_or_budget_are_errors(old_checks):
    for kw in ({"kinds": ["nope"]}, {"maximum": 0}, {"maximum": True}):
        rep = prove(h.FakeExecutor(h.custleak()), old_checks, **kw)
        assert rep.status == "error" and rep.exit_code == 2, kw
