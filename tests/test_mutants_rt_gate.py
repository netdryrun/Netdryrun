"""The convergence gate's exact outputs on every path the 0.4.1 red-team batch added (mutation triage of 22e1f95).

Each test pins the whole observable result of one gate path: the warnings (code, node, session and text), the blocked
results (detail, attempts, samples, duration), the log lines and the time waited. Pinned text is part of what a reader
and an agent act on (the warning names the session to fix, or the declaration to add), so it is tested, not accepted.
"""
from __future__ import annotations

import ipaddress

import pytest

from netdryrun import checks, runner
from netdryrun.drivers.base import BgpPath, DriverError, NoSuchInstance, Observation
from netdryrun.drivers.stale import refuse_llgr_stale

from test_verdict_runner import chk, leak, make


class EorDrv:
    def __init__(self, inner, eor):
        self.inner, self.eor = inner, eor

    def __getattr__(self, k):
        return getattr(self.inner, k)

    def end_of_rib(self, vrf, neighbors):
        return self.eor(self.inner.clock.now, vrf)


def gate(e, negatives, extras=None, all_checks=None, warnings=None, reported=None, not_sent=frozenset(),
         expected_down=frozenset()):
    w = {} if warnings is None else warnings
    blocked = runner._bgp_convergence_gate(negatives, all_checks or negatives, e.drivers, log=e.logs.append,
                                           warnings=w, extras=extras or {}, eor_reported=reported,
                                           eor_not_sent=not_sent, expected_down=expected_down)
    return blocked, w


def warns(w, c):
    return [(x["code"], x["node"], x["session"], x["text"]) for x in w.get(id(c), [])]


# ------------------------------------------------------------------------------------------- extra nodes

@pytest.mark.parametrize("vrf,where", [("default", ""), ("red", " (vrf red)")])
def test_extra_session_down_warning_exactly(monkeypatch, vrf, where):
    e = make(monkeypatch, r1={"neighbors": {vrf: {"10.0.12.2": "established"}}},
             r2={"neighbors": {vrf: {"10.0.23.3": "active", "10.0.23.9": "idle"}}})
    neg = leak("n", timeout=30, **({} if vrf == "default" else {"vrf": vrf}))
    blocked, w = gate(e, [neg], extras={"r2": e.drivers["r2"]})
    assert blocked == {}
    hint = ("If it is down on purpose, add a bgp_session check on r2 with state: down for it: the gate then doesn't "
            "wait for it")
    assert warns(w, neg) == [
        ("gate-session-down", "r2", "10.0.23.3",
         f"convergence: r2's session to 10.0.23.3{where} was not established (active) when this check ran (waited 30s). "
         + hint),
        ("gate-session-down", "r2", "10.0.23.9",
         f"convergence: r2's session to 10.0.23.9{where} was not established (idle) when this check ran (waited 30s). "
         + hint)]
    assert e.logs[-2:] == ["warning: " + t for *_, t in warns(w, neg)]
    assert e.clock.now == 30


def test_extra_first_read_failure_warning_exactly(monkeypatch):
    e = make(monkeypatch, r1={"neighbors": {"default": {"10.0.12.2": "established"}}},
             r2={"neighbors_error": DriverError("vtysh:   connection\n refused")})
    neg = leak("n", timeout=30)
    blocked, w = gate(e, [neg], extras={"r2": e.drivers["r2"]})
    assert warns(w, neg) == [("gate-unreadable", "r2", None,
                              "convergence: r2's BGP state could not be read before this check ran "
                              "(vtysh: connection refused)")]
    assert e.clock.now == 3     # r1 settles on its second sample; r2 is not waited for


def test_extra_node_without_a_driver_warning_exactly(monkeypatch):
    e = make(monkeypatch, r1={"neighbors": {"default": {"10.0.12.2": "established"}}})
    neg = leak("n", timeout=30)
    blocked, w = gate(e, [neg], extras={"r9": "node r9 runs MikroTik RouterOS, a beta"})
    assert warns(w, neg) == [("gate-unreadable", "r9", None,
                              "convergence: r9 was not watched before this check ran (node r9 runs MikroTik RouterOS, "
                              "a beta)")]


def test_extra_read_failing_later_warns_at_the_cap_with_the_error(monkeypatch):
    e = make(monkeypatch, r1={"neighbors": {"default": {"10.0.12.2": "established"}}},
             r2={"neighbors": {"red": {"10.0.23.3": "established"}},
                 "neighbors_error": lambda t: DriverError("cli  gone") if t > 0 else None})
    neg = leak("n", timeout=30, vrf="red")
    e.drivers["r1"].neighbors = {"red": {"10.0.12.2": "established"}}
    blocked, w = gate(e, [neg], extras={"r2": e.drivers["r2"]})
    assert warns(w, neg) == [("gate-unreadable", "r2", None,
                              "convergence: r2's BGP state (vrf red) could not be read by the cap (30s): cli gone")]


def test_extra_no_such_instance_on_a_bgp_node_is_waited_for_then_unreadable(monkeypatch):
    e = make(monkeypatch, r1={"neighbors": {"default": {"10.0.12.2": "established"}}},
             r2={"neighbors_error": NoSuchInstance("no BGP instance")})
    neg = leak("n", timeout=12)
    other = chk("bgp_session", "r2 up", node="r2", neighbor="10.0.23.3")
    blocked, w = gate(e, [neg], extras={"r2": e.drivers["r2"]}, all_checks=[neg, other])
    assert warns(w, neg) == [("gate-unreadable", "r2", None,
                              "convergence: r2's BGP state could not be read by the cap (12s): no BGP instance")]
    assert e.clock.now == 12


def test_extra_no_neighbors_on_a_bgp_node_warning_exactly(monkeypatch):
    e = make(monkeypatch, r1={"neighbors": {"default": {"10.0.12.2": "established"}}})
    neg = leak("n", timeout=12)
    other = chk("bgp_route", "r2 has it", node="r2", prefix="10.0.0.0/8")
    blocked, w = gate(e, [neg], extras={"r2": e.drivers["r2"]}, all_checks=[neg, other])
    assert warns(w, neg) == [("gate-no-neighbors", "r2", None,
                              "convergence: r2 reported no BGP neighbors by the cap (12s), although checks in the file "
                              "expect BGP on it")]


def test_extra_counts_moving_warning_exactly(monkeypatch):
    e = make(monkeypatch, r1={"neighbors": {"default": {"10.0.12.2": "established"}}},
             r2={"neighbors": {"default": lambda t: {"10.0.23.3": ("established", {"ipv4-unicast": int(t)})}}})
    neg = leak("n", timeout=12)
    blocked, w = gate(e, [neg], extras={"r2": e.drivers["r2"]})
    assert warns(w, neg) == [("gate-counts-moving", "r2", None,
                              "convergence: r2's BGP prefix counts were still changing when this check ran (waited 12s)")]


def test_extra_eor_pending_warning_exactly(monkeypatch):
    e = make(monkeypatch, r1={"neighbors": {"default": {"10.0.12.2": "established"}}},
             r2={"neighbors": {"default": {"10.0.23.3": "established", "10.0.23.4": "established"}}})
    e.drivers["r2"] = EorDrv(e.drivers["r2"], lambda t, v: {"10.0.23.3": {"*": "unknown"},
                                                           "10.0.23.4": {"ipv6-unicast": "pending"}})
    neg = leak("n", timeout=12)
    blocked, w = gate(e, [neg], extras={"r2": e.drivers["r2"]})
    assert warns(w, neg) == [
        ("gate-eor-pending", "r2", "10.0.23.3", "convergence: r2's session to 10.0.23.3 had not sent End-of-RIB (all "
         "families: unknown) when this check ran (waited 12s); its routes may still have been arriving"),
        ("gate-eor-pending", "r2", "10.0.23.4", "convergence: r2's session to 10.0.23.4 had not sent End-of-RIB "
         "(ipv6-unicast: pending) when this check ran (waited 12s); its routes may still have been arriving")]


def test_extra_warnings_skip_blocked_checks_and_reach_every_other(monkeypatch):
    e = make(monkeypatch, r1={"neighbors": {"default": {"10.0.12.2": "established"}}},
             r3={"neighbors": {"default": {"10.0.13.1": "active"}}},
             r2={"neighbors": {"default": {"10.0.23.3": "idle"}}})
    a, b = leak("a", timeout=12), leak("b", node="r3", timeout=12)
    blocked, w = gate(e, [a, b], extras={"r2": e.drivers["r2"]})
    assert set(blocked) == {id(b)}
    assert [x[0] for x in warns(w, a)] == ["gate-session-down"] and id(b) not in w


def test_extras_are_not_read_for_dead_nodes_or_without_groups(monkeypatch):
    e = make(monkeypatch, r1={"neighbors": {"default": {"10.0.12.2": "established"}}},
             r2={"neighbors": {"default": {"10.0.23.3": "idle"}}})
    blocked, w = gate(e, [], extras={"r2": e.drivers["r2"]})
    assert blocked == {} and w == {} and e.drivers["r2"].calls == []


def test_an_extra_node_named_by_the_checks_own_vrf_group_is_not_doubled(monkeypatch):
    e = make(monkeypatch, r1={"neighbors": {"default": {"10.0.12.2": "established"}, "red": {"10.1.12.2": "idle"}}})
    neg = leak("n", timeout=12, vrf="red")
    blocked, w = gate(e, [neg], extras={"r1": e.drivers["r1"]})
    assert set(blocked) == {id(neg)}                       # own group (r1, red) blocks
    assert sorted(c[1] for c in e.drivers["r1"].calls if c[0] == "bgp_neighbors")[:1] == ["default"]


# ------------------------------------------------------------------------------------------- own node

def test_own_eor_block_exactly(monkeypatch):
    e = make(monkeypatch, r1={"neighbors": {"red": {"10.0.12.2": "established"}}})
    e.drivers["r1"] = EorDrv(e.drivers["r1"], lambda t, v: {"10.0.12.2": {"ipv4-unicast": "pending", "*": "unknown"}})
    neg = leak("n", timeout=9, vrf="red")
    blocked, w = gate(e, [neg])
    r = blocked[id(neg)]
    assert r.detail == ("not evaluated: End-of-RIB not received on r1 (vrf red) from: 10.0.12.2 (all families: unknown), "
                        "10.0.12.2 (ipv4-unicast: pending) after waiting 9s. A post-convergence check only means "
                        "something once the node's neighbors have sent their whole table (End-of-RIB). For a peer that "
                        "never sends End-of-RIB, declare nodes.r1.peers.red/<address>.eor: not_sent")
    assert (r.passed, r.attempts, r.samples_passed, r.samples_unready, r.duration) == (False, 4, 0, 0, 9.0)
    assert [h["passed"] for h in r.history] == [False] * 4


def test_own_eor_block_in_the_default_vrf_names_the_plain_declaration(monkeypatch):
    e = make(monkeypatch, r1={"neighbors": {"default": {"10.0.12.2": "established"}}})
    e.drivers["r1"] = EorDrv(e.drivers["r1"], lambda t, v: {"10.0.12.2": {"ipv4-unicast": "pending"}})
    neg = leak("n", timeout=3)
    r = gate(e, [neg])[0][id(neg)]
    assert r.detail.endswith("declare nodes.r1.peers.<address>.eor: not_sent")
    assert "End-of-RIB not received on r1 from: 10.0.12.2 (ipv4-unicast: pending)" in r.detail


def test_own_counts_moving_warning_exactly(monkeypatch):
    e = make(monkeypatch, r1={"neighbors": {"red": lambda t: {"10.0.12.2": ("established", {"ipv4-unicast": int(t)})}}})
    neg = leak("n", timeout=9, vrf="red")
    blocked, w = gate(e, [neg])
    text = "convergence: r1's BGP prefix counts (vrf red) were still changing when this check ran (waited 9s)"
    assert blocked == {} and warns(w, neg) == [("gate-counts-moving", "r1", None, text)]
    assert e.logs[-1] == "warning: " + text


def test_untracked_warning_exactly_and_once(monkeypatch):
    e = make(monkeypatch, r1={"neighbors": {"red": {"10.0.12.2": "established", "10.0.12.6": "established"}}})
    e.drivers["r1"] = EorDrv(e.drivers["r1"], lambda t, v: {"10.0.12.2": {"*": "untracked"},
                                                           "10.0.12.6": {"ipv4-unicast": "received"}})
    a, b = leak("a", timeout=9, vrf="red"), leak("b", timeout=9, vrf="red", prefix="10.77.0.0/16")
    reported: set = set()
    blocked, w = gate(e, [a, b], reported=reported)
    text = ("convergence: r1's session to 10.0.12.2 (vrf red) doesn't negotiate graceful restart, so its End-of-RIB "
            "can't be tracked; the gate judged it by stable prefix counts only (a route can still arrive later)")
    assert warns(w, a) == [("eor-untracked", "r1", "10.0.12.2", text)] and id(b) not in w
    assert reported == {("r1", "red", "10.0.12.2")} and e.logs[-1] == "warning: " + text


def test_excluded_and_declared_sessions_dont_wait_for_end_of_rib(monkeypatch):
    e = make(monkeypatch, r1={"neighbors": {"default": {"10.0.12.2": "established", "10.0.12.6": "established"}}})
    e.drivers["r1"] = EorDrv(e.drivers["r1"], lambda t, v: {"10.0.12.2": {"*": "unknown"},
                                                           "10.0.12.6": {"ipv4-unicast": "pending"}})
    neg = leak("n", timeout=9)
    blocked, w = gate(e, [neg], expected_down={("r1", "default", "10.0.12.6")},
                      not_sent={("r1", "default", "10.0.12.2")})
    assert blocked == {} and w == {} and e.clock.now == 3


def test_a_raising_end_of_rib_reads_unknown_for_established_sessions_only(monkeypatch):
    e = make(monkeypatch, r1={"neighbors": {"default": {"10.0.12.2": "established"}}})

    def boom(t, v):
        raise RuntimeError("bug")
    e.drivers["r1"] = EorDrv(e.drivers["r1"], boom)
    neg = leak("n", timeout=3)
    r = gate(e, [neg])[0][id(neg)]
    assert "10.0.12.2 (all families: unknown)" in r.detail


def test_end_of_rib_is_read_for_the_vrf_of_the_group(monkeypatch):
    seen = []
    e = make(monkeypatch, r1={"neighbors": {"red": {"10.0.12.2": "established"}}})
    e.drivers["r1"] = EorDrv(e.drivers["r1"], lambda t, v: seen.append(v) or {})
    gate(e, [leak("n", timeout=9, vrf="red")])
    assert set(seen) == {"red"}


# ------------------------------------------------------------------------------------------- _ping, LLGR

def test_ping_reads_own_addresses_in_the_checks_vrf_and_names_the_node(monkeypatch):
    asked = []

    class D:
        def local_addresses(self, vrf="default"):
            asked.append(vrf)
            return [ipaddress.ip_interface("10.0.12.1/30")]

        def ping(self, *a):
            raise AssertionError("never pinged")
    c = chk("ping", "self", node="r7", target="10.0.12.1", vrf="red")
    with pytest.raises(DriverError) as e:
        checks._ping(D(), c.params)
    assert asked == ["red"]
    assert str(e.value) == ("ping target 10.0.12.1 is an address of r7 itself (10.0.12.1/30): the ping never leaves the "
                            "node, so it says nothing about the network")
    asked.clear()
    with pytest.raises(DriverError):
        checks._ping(D(), chk("ping", "self", node="r7", target="10.0.12.1").params)
    assert asked == ["default"]


def _path(neighbor):
    return BgpPath(best=True, as_path="65002", next_hop="10.0.0.2", local_pref=100, med=None,
                   communities=["65000:1", "65535:6"], neighbor=neighbor)


@pytest.mark.parametrize("neighbor,shown", [("10.0.0.2", "10.0.0.2"), (None, "?")])
def test_llgr_stale_refusal_exactly(neighbor, shown):
    with pytest.raises(DriverError) as e:
        refuse_llgr_stale("10.1.0.0/16", [_path(neighbor)])
    assert str(e.value) == (f"10.1.0.0/16: BGP path from {shown} carries LLGR_STALE (65535:6): long-lived graceful "
                            "restart in progress, not settled")
    refuse_llgr_stale("10.1.0.0/16", [BgpPath(best=True, as_path="", next_hop=None, local_pref=None, med=None)])
    refuse_llgr_stale("10.1.0.0/16", None)


def test_the_llgr_wrapper_passes_prefix_and_vrf_and_returns_the_observation():
    from netdryrun.drivers.base import Driver
    seen = []
    obs = Observation([], [{"cmd": "x"}])

    class D(Driver):
        name = "t"

        def bgp_paths(self, prefix, vrf="default"):
            """own doc"""
            seen.append((prefix, vrf))
            return obs
    d = D.__new__(D)
    assert d.bgp_paths("10.0.0.0/8", "red") is obs and d.bgp_paths("10.0.0.0/8") is obs
    assert seen == [("10.0.0.0/8", "red"), ("10.0.0.0/8", "default")]
    assert D.bgp_paths.__doc__ == "own doc" and D.bgp_paths._llgr_checked is True

    class E(D):   # inherits the wrapped method: not wrapped twice
        pass
    assert E.bgp_paths is D.bgp_paths

    class F(Driver):   # no bgp_paths of its own: nothing to wrap
        name = "f"
    assert "bgp_paths" not in F.__dict__


def test_ping_unreachable_detail_quotes_the_whole_match():
    class D:
        def local_addresses(self, vrf="default"):
            return []

        def ping(self, target, source, count, vrf="default"):
            return Observation((0, 0), [{"output": "", "stderr": "ping: connect: Network is unreachable"}])
    ok, detail, _ = checks._ping(D(), chk("ping", "p", target="192.0.2.9").params)
    assert (ok, detail) == (False, "0/3 replies (destination unreachable: Network is unreachable)")


def test_a_class_that_reuses_a_wrapped_bgp_paths_is_not_wrapped_twice():
    from netdryrun.drivers.base import Driver
    calls = []

    class D(Driver):
        name = "t"

        def bgp_paths(self, prefix, vrf="default"):
            calls.append(self.node)
            return Observation([_path("10.0.0.2")], [])

    class D2(Driver):
        name = "t2"
        bgp_paths = D.bgp_paths
    assert D2.bgp_paths is D.bgp_paths
    d = D.__new__(D)
    d.node = "r1"
    with pytest.raises(DriverError) as e:
        d.bgp_paths("10.9.0.0/16")
    assert calls == ["r1"] and str(e.value).startswith("10.9.0.0/16: BGP path from 10.0.0.2 carries LLGR_STALE")
