"""Edge cases of `netdryrun prove` that mutation testing showed no other test pinned (mutmut on src/netdryrun/prove).
Each test names the behaviour it holds; the equivalent mutants are accepted, each with its reason, in
releases/0.5.0-prove/accepted.json."""
from __future__ import annotations

import ipaddress
from dataclasses import replace
from datetime import datetime
from types import SimpleNamespace

from netdryrun.checks import Result
from netdryrun.config import load as load_config_file
from netdryrun.prove import core
from netdryrun.prove import report as preport
from netdryrun.prove import variants as V
from netdryrun.prove.core import CAUGHT, INCONCLUSIVE, SURVIVED, prove
from netdryrun.prove.suggest import suggest
from netdryrun.prove.variants import Variant, leak_prefixes
from netdryrun.verify.engine import DiffItem
from netdryrun.verify.snapshot import ItemKey

import prove_helpers as h
from test_prove_variants import CONFIGS
from verify_helpers import attrs, path, rib, session

CHECKS = load_config_file(h.FIXTURE / "netdryrun.yml").checks
FILTER = "import_filter:edge:CUST-IN permit 10:match ip address prefix-list CUST-IN"


def variants(base, checks=CHECKS):
    return {v.id: v for v in V.generate({n: ns.config for n, ns in base.nodes.items()}, h.LINKS, checks,
                                        core._counts(base), core.blocked(base))}


# ---------------------------------------------------------------------------------------------------------
# parse
# ---------------------------------------------------------------------------------------------------------

def test_parse_edges():
    c = V.parse(" stray indented line\n neighbor 9.9.9.9 remote-as 9\n ip address 10.9.0.1/24\n"
                "ip route 10.7.0.0/16\nipv6 route 2001:db8:7::/48 blackhole\nip route\n"
                "ip prefix-list P\nip prefix-list Q x\nipv6 prefix-list P6 seq 5 permit 2001:db8::/32\n"
                "line vty\n ip address 10.8.0.1/24\n"
                "interface eth1\n ip address 10.6.0.1/24 secondary\n ip address 10.5.0.1/24\n"
                "route-map M permit 10\n set local-preference 5\n!\n match ip address prefix-list P\n"
                "router bgp 1\n neighbor\n bgp router-id 1.1.1.1\n neighbor 10.0.0.2 remote-as 2\n"
                " neighbor 10.0.0.2 route-map R in\n neighbor 10.0.0.2 route-map\n"
                " neighbor eth2 interface remote-as external\n"
                " address-family ipv6 unicast\n  neighbor 10.0.0.2 route-map A in\n exit\n"
                " neighbor 10.0.0.2 route-map B out\n address-family ipv6\n  neighbor 10.0.0.2 route-map C in\n"
                " address-family ipv4\n  neighbor 10.0.0.2 route-map D in\n")
    assert c.statics == {"10.7.0.0/16", "2001:db8:7::/48"}
    assert c.prefix_lists == {"Q": ["ip prefix-list Q x"], "P6": ["ipv6 prefix-list P6 seq 5 permit 2001:db8::/32"]}
    assert set(c.interfaces) == {"eth1"} and [str(i) for i in c.interfaces["eth1"]] == ["10.5.0.1/24"]
    assert c.route_maps["M"][0].lines == ["set local-preference 5", "match ip address prefix-list P"]
    assert set(c.neighbors) == {"10.0.0.2", "eth2"} and c.neighbors["10.0.0.2"].address == "10.0.0.2"
    assert c.neighbors["eth2"].address == "eth2" and c.ip_neighbors() == ["10.0.0.2"]
    assert c.maps_of("10.0.0.2") == {("ipv4", "in"): "D", ("ipv6", "in"): "C", ("ipv4", "out"): "B"}
    assert V._is_ip("eth2") is False and V._is_ip("10.0.0.2") is True


def test_route_map_on_the_router_level_counts_as_ipv4():
    c = V.parse("router bgp 1\n neighbor 10.0.0.2 remote-as 2\n neighbor 10.0.0.2 route-map R in\n")
    assert c.maps_of("10.0.0.2") == {("ipv4", "in"): "R"}


# ---------------------------------------------------------------------------------------------------------
# generation
# ---------------------------------------------------------------------------------------------------------

def test_import_filter_edges():
    c = ("ip prefix-list P seq 5 permit 10.0.0.0/8\nip prefix-list P description x\n"
         "route-map A permit 10\n set community 1:1\n match ip address prefix-list P\nexit\n"
         "route-map B permit 10\n match ip address prefix-list P\nexit\n"
         "router bgp 1\n neighbor 10.0.0.2 remote-as 2\n neighbor 10.0.0.6 remote-as 3\n"
         " neighbor 10.0.0.10 remote-as 4\n address-family ipv4 unicast\n"
         "  neighbor 10.0.0.2 route-map A in\n  neighbor 10.0.0.6 route-map B in\n  neighbor 10.0.0.10 route-map GONE in\n"
         "  neighbor 10.0.0.2 prefix-list P in\n address-family ipv6 unicast\n  neighbor 10.0.0.2 prefix-list P in\n")
    vs = {v.id: v for v in V.generate({"r": c})}
    assert "import_filter:r:A permit 10:match ip address prefix-list P" in vs   # a set line before the match
    p = vs["import_filter:r:ip prefix-list P seq 5 permit 10.0.0.0/8"]
    assert p.soft_in == ("10.0.0.2", "10.0.0.6")   # both route-maps' neighbors, each once
    assert "import_filter:r:ip prefix-list P description x" in vs   # deleted, but no permit/deny to swap
    assert "import_filter:r:ip prefix-list P description x:swapped" not in vs
    sw = vs["import_filter:r:ip prefix-list P seq 5 permit 10.0.0.0/8:swapped"]
    assert sw.apply == ("no ip prefix-list P seq 5 permit 10.0.0.0/8", "ip prefix-list P seq 5 deny 10.0.0.0/8")


def test_filter_rank():
    for vid, rank in (("import_filter:r:M permit 10:match x", 0), ("import_filter:r:ip prefix-list P seq 5 permit x", 1),
                      ("import_filter:r:ipv6 prefix-list P seq 5 permit x", 1), ("import_filter:r:M deny 5:deleted", 2),
                      ("import_filter:r:M permit 10:swapped", 3), ("import_filter:r:M permit 10:swapped:+leak:x", 3),
                      ("import_filter:r:ip prefix-list P seq 5 deny x:swapped", 3)):
        assert V._filter_rank(Variant(vid, "import_filter", "r", "d")) == rank, vid


def test_session_down_edges():
    a = "router bgp 1\n neighbor 10.0.0.2 remote-as 2\n neighbor 10.0.0.2 shutdown\n neighbor 10.0.0.6 remote-as 3\n"
    vs = [v.id for v in V.generate({"a": "hostname a\n", "b": a}) if v.kind == "session_down"]
    assert vs == ["session_down:b:10.0.0.6"]   # a shut neighbor is skipped, the next one isn't; a node without BGP too
    d = next(v for v in V.generate({"b": a}) if v.kind == "session_down")
    assert d.description == "b: BGP session to 10.0.0.6 shut down"


def test_originate_ipv6_and_link_subnet_edges():
    c = ("interface eth1\n ip address 10.0.0.1/30\ninterface eth2\n ip address 10.0.0.5/30\n"
         "interface eth3\n ip address 10.0.0.9/30\n"
         "router bgp 1\n neighbor 2001:db8::2 remote-as 2\n address-family ipv4 unicast\n  network 10.0.0.0/30\n")
    links = [(("r", "eth1"), ("x", "eth1")), (("r", "eth2"), ("x", "eth2")), (("r", "eth9"), ("x", "eth9"))]
    vs = {v.id: v for v in V.generate({"r": c}, links)}
    assert [i for i in vs if i.startswith("link_subnet_leak")] == ["link_subnet_leak:r:10.0.0.4/30"]
    d6 = vs["default_leak:r:::/0"]
    assert d6.adds == ("ipv6 route ::/0 blackhole", "router bgp 1 > address-family ipv6 unicast > network ::/0")
    assert d6.revert == ("no ipv6 route ::/0 blackhole", "router bgp 1", " address-family ipv6 unicast",
                         "  no network ::/0", " exit-address-family", "exit")
    assert not [i for i in V.generate({"r": "router bgp 1\n"}, links) if i.kind == "link_subnet_leak"]


def test_link_down_takes_the_frr_end_wherever_it_sorts():
    vs = V.generate({"z": "hostname z\n"}, [(("a", "eth1"), ("b", "eth1")), (("a", "eth2"), ("z", "eth3"))])
    assert [(v.id, v.link) for v in vs] == [("link_down:a:eth2--z:eth3", ("z", "eth3"))]


def test_headroom_and_ranges_edges():
    checks = [SimpleNamespace(type="route", params={"node": "edge", "prefix": "1.0.0.0/8"}),
              SimpleNamespace(type="bgp_prefixes", params={"node": "edge", "neighbor": "10.0.1.2", "max": 4,
                                                           "afi": "ipv6-unicast"})]
    counts = {("edge", "10.0.1.2", "ipv6-unicast"): 1}
    assert V.headroom(checks, counts) == {"edge": {"10.0.1.2": 3}}
    gen = {v.id: v for v in V.generate(CONFIGS, h.LINKS, checks, counts)}
    assert gen["customer_leak:cust:4"].range_top == ("edge", "10.0.1.2", "ipv6-unicast", 4)
    exact = [SimpleNamespace(type="bgp_prefixes", params={"node": "edge", "neighbor": "10.0.1.2", "exact": 1})]
    gen = {v.id: v for v in V.generate(CONFIGS, h.LINKS, exact, {("edge", "10.0.1.2", "ipv4-unicast"): 1})}
    assert gen["customer_leak:cust:1"].range_top == ("edge", "10.0.1.2", "ipv4-unicast", 1)   # U = C: outer is 1
    assert gen["customer_leak:cust:2"].description == "cust announces 2 extra prefix(es) from 100.64.0.0/10"


def test_two_ranges_with_the_same_outer_leak_keep_the_first_by_headroom():
    cfg = V.parse(CONFIGS["cust"])
    out = V._customer_leak("cust", cfg, [("b", "10.0.0.9", "ipv4-unicast", 5, 2), ("a", "10.0.0.8", "ipv4-unicast", 5, 2),
                                         ("c", "10.0.0.7", "ipv4-unicast", 9, 1)], [])
    by = {v.id: v for v in out}
    assert by["customer_leak:cust:3"].range_top == ("b", "10.0.0.9", "ipv4-unicast", 5)   # order of the checks
    assert by["customer_leak:cust:2"].range_top == ("c", "10.0.0.7", "ipv4-unicast", 9)   # outer wins over inner
    assert "just inside" in by["customer_leak:cust:1"].description and by["customer_leak:cust:1"].range_top is None


def test_used_networks_edges():
    a, b = V.parse("interface e1\n ip address 10.1.0.1/24\n"), V.parse("interface e1\n ip address 10.2.0.1/24\n"
                                                                     "router bgp 1\n address-family ipv4 unicast\n"
                                                                     "  network 10.3.0.0/24\n")
    checks = [SimpleNamespace(params={"prefix": "not a prefix", "source": "100.64.5.9"}),
              SimpleNamespace(params={"prefix": "100.64.6.1/24"})]
    nets = {str(n) for n in V.used_networks({"a": a, "b": b}, checks)}
    assert {"10.1.0.0/24", "10.2.0.0/24", "10.3.0.0/24", "100.64.5.9/32", "100.64.6.0/24"} <= nets


# ---------------------------------------------------------------------------------------------------------
# core
# ---------------------------------------------------------------------------------------------------------

def test_now_is_utc():
    assert core.now().endswith("+00:00") and datetime.fromisoformat(core.now()).utcoffset().total_seconds() == 0


def test_prove_records_its_clock_and_logs_progress():
    base = h.custleak()
    vs = variants(base)
    sd = "session_down:cust:10.0.1.1"
    lines = []
    rep = prove(h.FakeExecutor(base, {sd: h.applied(vs[sd], h.custleak(down=("ce",)))}), CHECKS,
                kinds=["session_down"], maximum=1, log=lines.append, clock=lambda: "2026-01-01T00:00:00+00:00")
    assert rep.started == rep.finished == "2026-01-01T00:00:00+00:00"
    assert lines == ["[1/1] cust: BGP session to 10.0.1.1 (edge) shut down",
                     "  caught (provisional: final once every variant ran and the lab was restored)"]


def test_fresh_checks_lengths_and_empty_start_times():
    f = core._Fresh()
    rs = h.evaluate(CHECKS, h.custleak())
    try:
        f.check(rs[:-1], CHECKS, "", "x")
        raise AssertionError("a short result list must be refused")
    except core.ProveError as e:
        assert e.kind == "internal"
    try:
        core._Fresh().check([replace(rs[0], started="")] + rs[1:], CHECKS, "2026", "x")
        raise AssertionError("a result with no start time is from no run")
    except core.ProveError as e:
        assert "earlier run" in str(e)


def test_more_than_five_names_are_cut():
    base = h.custleak()
    rep = prove(h.FakeExecutor(h.custleak(down=("ce", "eu"))), CHECKS)
    assert rep.error.split("failed: ")[1].count("; ") == 4   # five names
    vs = variants(base)
    many = h.custleak(edge_filter=None, cust_extra=leak_prefixes(4))
    rep = prove(h.FakeExecutor(base, {FILTER: h.applied(vs[FILTER], h.custleak(edge_filter=None))},
                               after={FILTER: many}), CHECKS, kinds=["import_filter"], maximum=1)
    assert rep.error_kind == "restore" and rep.error.split("baseline (")[1].split(")")[0].count("; ") == 4


def test_a_restore_with_only_new_path_ids_is_the_baseline():
    base = h.custleak()
    vs = variants(base)
    k = next(k for k in base.nodes["edge"].items if k.kind == "path" and k.neighbor == "10.0.1.2")
    renumbered = h.custleak()
    renumbered.nodes["edge"].items[replace(k, path_id=7)] = renumbered.nodes["edge"].items.pop(k)
    rep = prove(h.FakeExecutor(base, {FILTER: h.applied(vs[FILTER], h.custleak(edge_filter=None))},
                               after={FILTER: renumbered}), CHECKS, kinds=["import_filter"], maximum=1)
    assert rep.status == "failed"


def test_side_state_that_loses_a_key_is_drift():
    base = h.custleak()
    vs = variants(base)
    ex = h.FakeExecutor(base, {FILTER: h.applied(vs[FILTER], h.custleak(edge_filter=None))})
    ex.side_after = {FILTER: {}}
    rep = prove(ex, CHECKS, kinds=["import_filter"], maximum=1)
    assert rep.error_kind == "restore" and "edge kernel routes (outside the snapshot)" in rep.error


def test_session_down_on_a_node_with_other_sessions():
    base = h.custleak()
    vs = variants(base)
    sd = "session_down:edge:10.0.2.2"
    first = "session_down:cust:10.0.1.1"
    rep = prove(h.FakeExecutor(base, {sd: h.applied(vs[sd], h.custleak(down=("eu",))),
                                      first: h.applied(vs[first], h.custleak(down=("ce",)))}), CHECKS,
                kinds=["session_down"], maximum=2)
    assert [v.result for v in rep.variants if v.variant.id == sd] == [CAUGHT]


def test_the_range_note_when_the_session_is_gone():
    base = h.custleak(edge_filter=None)
    v = Variant("customer_leak:cust:2", "customer_leak", "cust", "d", originates=tuple(leak_prefixes(2)),
                range_top=("edge", "10.0.1.2", "ipv4-unicast", 3))
    during = h.custleak(cust_extra=leak_prefixes(2), edge_filter=None)
    k = next(k for k in during.nodes["edge"].items if k.kind == "session" and k.neighbor == "10.0.1.2")
    del during.nodes["edge"].items[k]
    ok = lambda checks: [replace(r, passed=True) for r in h.evaluate(checks, during)]  # noqa: E731
    ex = h.FakeExecutor(base, {v.id: during}, results={v.id: ok})
    res = core._one(ex, v, CHECKS, base, ex.side_state(), core._Fresh(), core.now)
    assert res.result == SURVIVED and res.note.endswith("(it is 0): judged by its effect like any other variant")
    assert res.note.startswith("session(s) went down")


def test_took_effect_needs_a_local_path_not_any_entry():
    base = h.custleak()
    v = Variant("default_leak:cust:0.0.0.0/0", "default_leak", "cust", "d", originates=("0.0.0.0/0",))
    during = h.custleak()
    during.nodes["cust"].items[ItemKey("rib", "cust", "default", "ipv4", "unicast", "0.0.0.0/0", protocol="static")] = \
        rib("static", hops=())
    assert "doesn't have it" in core.took_effect(v, base, during)
    during.nodes["cust"].items[ItemKey("path", "cust", "default", "ipv4", "unicast", "0.0.0.0/0",
                                       neighbor="10.0.1.1")] = path(as_path="65000")
    assert "doesn't have it" in core.took_effect(v, base, during)


def test_footprint_uses_sessions_from_either_snapshot():
    """A pre-policy copy over a session established only while the variant is applied is still the variant's own."""
    base = h.custleak()
    k = next(k for k in base.nodes["edge"].items if k.kind == "session" and k.neighbor == "10.0.1.2")
    base.nodes["edge"].items[k] = session(None, state="idle", remote_as=65010)
    kc = next(k for k in base.nodes["cust"].items if k.kind == "session")
    base.nodes["cust"].items[kc] = session(None, state="idle", remote_as=65000, local_as=65010)
    v = Variant("customer_leak:cust:1", "customer_leak", "cust", "d", originates=("100.64.0.0/24",))
    during = h.custleak()
    own = core.footprint(v, during)
    pre = ItemKey("adj_in", "edge", "default", "ipv4", "unicast", "100.64.0.0/24", neighbor="10.0.1.2")
    assert own(DiffItem(pre, None, attrs()))


def test_blocked_reads_each_session_and_skips_other_vrfs():
    base = h.custleak()
    assert core.blocked(base) == {("cust", "10.0.1.1"): False, ("edge", "10.0.1.2"): True,
                                  ("edge", "10.0.2.2"): False, ("up", "10.0.2.1"): False}
    red = h.custleak()
    for n, nbr, local in (("aa", "10.9.0.2", "10.9.0.1"), ("ab", "10.9.0.1", "10.9.0.2")):
        from netdryrun.verify.snapshot import NodeSnapshot
        red.nodes[n] = NodeSnapshot(n, "frr", ("RED", "default"), {
            ItemKey("session", n, "RED", neighbor=nbr): session(local),
            ItemKey("rib", n, "RED", "ipv4", "unicast", "10.9.0.0/30", protocol="connected"): rib("connected", hops=())})
    assert core.blocked(red) == core.blocked(base)   # the RED sessions sort first and are skipped, not the end


def test_canonical_keeps_every_node_field():
    s = h.custleak()
    s.unobserved["host"] = "a host"
    ns = s.nodes["edge"]
    from netdryrun.verify.snapshot import NodeSnapshot
    s.nodes["edge"] = NodeSnapshot(ns.node, "frr", ns.vrfs, ns.items, [{"cmd": "x"}], 7.0, ns.config, 9.0)
    c = core.canonical(s)
    e = c.nodes["edge"]
    assert (e.driver, e.raw, e.adv_interval, e.cond_adv_timer) == ("frr", [{"cmd": "x"}], 7.0, 9.0)
    assert c.unobserved == {"host": "a host"}


def test_canonical_ranks_by_value_not_by_id():
    a, b = h.custleak(), h.custleak()
    k = ItemKey("path", "edge", "default", "ipv4", "unicast", "10.9.0.0/24", neighbor="10.0.1.2")
    p1, p2 = path(as_path="65010", local_pref=100), path(best=False, as_path="65010 65010")
    a.nodes["edge"].items.update({replace(k, path_id=3): p1, replace(k, path_id=7): p2})
    b.nodes["edge"].items.update({replace(k, path_id=1): p2, replace(k, path_id=4): p1})
    assert core.same_state(core.canonical(a), core.canonical(b)) == []


def test_fitted_reads_a_prefix_with_host_bits():
    leak = Variant("l", "customer_leak", "cust", "d", originates=("100.64.0.0/24",))
    c = replace(CHECKS[-1], params={"node": "edge", "prefix": "100.64.0.1/24", "protocol": "bgp", "present": False})
    assert core._fitted(c, leak)


def test_classify_keeps_the_variant_and_the_failures():
    v = Variant("x", "import_filter", "edge", "d")
    real = Result(CHECKS[0], False, "state is idle", 1, 0.0, core.now(), [{"cmd": "x"}], [])
    res = core.classify(v, [], [real])
    assert res.variant is v and res.failed == [real] and res.result == INCONCLUSIVE


# ---------------------------------------------------------------------------------------------------------
# suggest and report
# ---------------------------------------------------------------------------------------------------------

def test_suggestions_are_ordered_by_kind():
    base = h.custleak()
    s = ItemKey("session", "edge", "default", neighbor="10.0.1.2")
    pk = ItemKey("path", "edge", "default", "ipv4", "unicast", "10.10.0.0/24", neighbor="10.0.1.2")
    add = ItemKey("path", "edge", "default", "ipv4", "unicast", "100.64.0.0/24", neighbor="10.0.1.2")
    rk = ItemKey("rib", "edge", "default", "ipv4", "unicast", "198.51.100.0/24", protocol="bgp")
    ao = ItemKey("adj_out", "edge", "default", "ipv4", "unicast", "1.0.0.0/8", neighbor="9.9.9.9")
    effect = [DiffItem(ao, None, attrs()), DiffItem(pk, path(as_path="65010", local_pref=200),
                                                    path(as_path="65010", local_pref=50)),
              DiffItem(rk, rib(), None), DiffItem(add, None, path(as_path="65010")),
              DiffItem(s, session("10.0.1.1"), session(None, state="idle"))]
    got = [c["check"]["type"] for c in suggest(Variant("v", "import_filter", "edge", "d"), base, effect)]
    assert got == ["bgp_session", "bgp_prefixes", "route", "bgp_route"]


def test_guards_for_several_leaked_routes():
    base = h.custleak()
    v = Variant("d", "default_leak", "cust", "d", originates=("0.0.0.0/0",))
    effect = [DiffItem(ItemKey("path", n, "default", "ipv4", "unicast", "0.0.0.0/0", neighbor=a), None,
                       path(as_path="65010")) for n, a in (("edge", "10.0.1.2"), ("up", "10.0.2.1"))]
    assert [c["check"]["node"] for c in suggest(v, base, effect)] == ["edge", "up"]


def test_a_count_change_suggests_no_session_check():
    base = h.custleak()
    k = next(k for k in base.nodes["edge"].items if k.kind == "session" and k.neighbor == "10.0.1.2")
    before = base.nodes["edge"].items[k]
    after = replace(before, prefix_counts=(("ipv4-unicast", 2),))
    assert suggest(Variant("v", "import_filter", "edge", "d"), base, [DiffItem(k, before, after)]) == []
    removed = suggest(Variant("v", "import_filter", "edge", "d"), base, [DiffItem(k, before, None)])
    assert removed[0]["check"] == {"type": "bgp_session", "node": "edge", "neighbor": "10.0.1.2"}


def test_attribute_pins_use_the_effective_local_preference():
    base = h.custleak()
    pk = ItemKey("path", "edge", "default", "ipv4", "unicast", "10.10.0.0/24", neighbor="10.0.1.2")
    out = suggest(Variant("v", "attribute_drift", "edge", "d"), base,
                  [DiffItem(pk, path(as_path="65010"), path(as_path="65010", local_pref=50))])
    assert out[0]["check"]["local_pref"] == 100


def test_evidence_is_the_last_three_entries_cut_to_size():
    ev = [{"node": f"n{i}", "cmd": f"c{i}", "output": "x" * (preport.MAX_EVIDENCE + 10)} for i in range(5)]
    ev.append({"node": "n5", "cmd": "c5"})
    r = Result(CHECKS[0], False, "d", 1, 0.0, core.now(), ev, [])
    got = preport._evidence(r)
    assert [e["cmd"] for e in got] == ["c3", "c4", "c5"]
    assert got[0] == {"node": "n3", "cmd": "c3", "output": "x" * preport.MAX_EVIDENCE} and got[2]["output"] == ""


def test_reports_partial_and_by_kind_only_where_they_belong():
    base = h.custleak()
    vs = variants(base)
    sd = "session_down:cust:10.0.1.1"
    ok = prove(h.FakeExecutor(base, {sd: h.applied(vs[sd], h.custleak(down=("ce",)))}), CHECKS,
               kinds=["session_down"], maximum=1)
    assert preport.to_dict(ok)["partial"] == [] and preport.to_dict(ok)["by_kind"]
    second = "session_down:edge:10.0.2.2"
    ex = h.FakeExecutor(base, {sd: h.applied(vs[sd], h.custleak(down=("ce",))),
                               second: h.applied(vs[second], h.custleak(down=("eu",)))})
    ex.side_after = {second: {}}
    bad = prove(ex, CHECKS, kinds=["session_down"], maximum=2)
    d = preport.to_dict(bad)
    assert d["by_kind"] == {} and len(d["partial"]) == 1 and d["variants"] == []
    assert preport.to_json(bad).startswith('{\n  "schema"')


def test_select_error_text():
    try:
        V.select([], ["nope", "zz"])
    except V.VariantError as e:
        assert str(e) == ("unknown variant kind(s) nope, zz; known: customer_leak, import_filter, session_down, link_down, "
                          "attribute_drift, default_leak, link_subnet_leak, more_specific, max_prefix_edge")
    assert ipaddress.ip_network("100.64.0.0/10") == V.LEAK_SPACE


def test_the_range_note_stands_alone_without_another_note():
    base = h.custleak(edge_filter=None)
    v = Variant("customer_leak:cust:2", "customer_leak", "cust", "d", originates=tuple(leak_prefixes(2)),
                range_top=("edge", "10.0.1.2", "ipv4-unicast", 3))
    during = h.custleak(cust_extra=leak_prefixes(2), edge_filter=None)
    ok = lambda checks: [replace(r, passed=True) for r in h.evaluate(checks, during)]  # noqa: E731
    ex = h.FakeExecutor(base, {v.id: during}, results={v.id: ok})
    res = core._one(ex, v, CHECKS, base, ex.side_state(), core._Fresh(), core.now)
    assert res.note.startswith("edge's count from 10.0.1.2 reached 4")


def test_blocked_counts_only_the_nodes_own_paths_from_that_neighbor():
    base = h.custleak()
    k = ItemKey("path", "up", "default", "ipv4", "unicast", "203.0.113.128/25", neighbor="10.0.1.2")
    base.nodes["up"].items[k] = path(as_path="65010")
    a = ItemKey("adj_out", "up", "default", "ipv4", "unicast", "203.0.113.128/25", neighbor="10.0.1.2")
    base.nodes["up"].items[a] = attrs()
    assert core.blocked(base)[("edge", "10.0.1.2")] is True


def test_took_effect_names_every_missing_prefix():
    v = Variant("customer_leak:cust:2", "customer_leak", "cust", "d", originates=("100.64.0.0/24", "100.64.1.0/24"))
    assert core.took_effect(v, h.custleak(), h.custleak()) == (
        "cust announces 100.64.0.0/24, 100.64.1.0/24 in its config, but its BGP table doesn't have it")


def test_a_node_with_bgp_but_no_neighbor_leaks_no_link_subnet():
    c = "interface eth1\n ip address 10.0.0.1/30\nrouter bgp 1\n"
    assert not [v for v in V.generate({"r": c}, [(("r", "eth1"), ("x", "eth1"))]) if v.kind == "link_subnet_leak"]


def test_a_quiet_session_before_a_busy_one_on_the_same_node():
    c = "router bgp 1\n neighbor 10.0.0.2 remote-as 2\n neighbor 10.0.0.6 remote-as 3\n"
    counts = {("r", "10.0.0.2", "ipv4-unicast"): 0, ("r", "10.0.0.6", "ipv4-unicast"): 4}
    assert [v.id for v in V.generate({"r": c}, base_counts=counts) if v.kind == "session_down"] == ["session_down:r:10.0.0.6"]


def test_an_undefined_inbound_prefix_list_gives_no_variant():
    c = "router bgp 1\n neighbor 10.0.0.2 remote-as 2\n address-family ipv4 unicast\n  neighbor 10.0.0.2 prefix-list NONE in\n"
    assert not [v for v in V.generate({"r": c}) if v.kind == "import_filter"]


def test_remote_as_of_a_neighbor_with_none():
    c = V.parse("router bgp 1\n neighbor 10.0.0.2 shutdown\n")
    assert c.remote_as_of("10.0.0.2") == "" and not c.ebgp("10.0.0.2")


def test_fresh_refuses_out_of_order_results():
    rs = h.evaluate(CHECKS, h.custleak())
    try:
        core._Fresh().check([rs[1], rs[0], *rs[2:]], CHECKS, "", "x")
        raise AssertionError("out of order must be refused")
    except core.ProveError as e:
        assert "out of order" in str(e)


def test_the_count_suggestion_lists_every_prefix_today():
    base = h.custleak(edge_filter=None)
    k = ItemKey("path", "edge", "default", "ipv4", "unicast", "100.64.0.0/24", neighbor="10.0.1.2")
    (s,) = suggest(Variant("v", "import_filter", "edge", "d"), base, [DiffItem(k, None, path(as_path="65010"))])
    assert s["reason"].endswith("Today it carries 10.10.0.0/24, 203.0.113.128/25") and s["check"]["exact"] == 2
