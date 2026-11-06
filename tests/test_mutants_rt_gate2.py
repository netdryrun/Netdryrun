"""The convergence gate, sample by sample (mutation triage of 22e1f95): which nodes are read and when, which state the
warning at the cap names after the state changed, and the exact own-node results. Companion of test_mutants_rt_gate.py.
"""
from __future__ import annotations

import pytest

from netdryrun import checks, runner
from netdryrun.drivers.base import DriverError, NoSuchInstance

from test_mutants_rt_gate import EorDrv, gate, warns
from test_verdict_runner import chk, leak, make


def nb_calls(drv, vrf="default"):
    return [c[2] for c in drv.calls if c[0] == "bgp_neighbors" and c[1] == vrf]


def test_a_failing_first_read_of_an_extra_is_read_once(monkeypatch):
    e = make(monkeypatch, r1={"neighbors": {"default": {"10.0.12.2": "established"}}},
             r2={"neighbors_error": DriverError("refused")})
    gate(e, [leak("n", timeout=30)], extras={"r2": e.drivers["r2"]})
    assert nb_calls(e.drivers["r2"]) == [0]


def test_no_bgp_on_a_non_bgp_extra_is_read_once(monkeypatch):
    e = make(monkeypatch, r1={"neighbors": {"default": {"10.0.12.2": "established"}}})
    gate(e, [leak("n", timeout=30)], extras={"r2": e.drivers["r2"]})
    assert nb_calls(e.drivers["r2"]) == [0]


def test_a_non_bgp_extra_whose_neighbors_vanish_later_is_waited_for(monkeypatch):
    e = make(monkeypatch, r1={"neighbors": {"default": {"10.0.12.2": "established"}}},
             r2={"neighbors": {"default": lambda t: {"10.0.23.3": "established"} if t == 0 else {}}})
    neg = leak("n", timeout=9)
    blocked, w = gate(e, [neg], extras={"r2": e.drivers["r2"]})
    assert nb_calls(e.drivers["r2"]) == [0, 3, 6, 9]
    assert [x[0] for x in warns(w, neg)] == ["gate-no-neighbors"]


def test_a_later_read_failure_after_no_such_instance_keeps_waiting(monkeypatch):
    e = make(monkeypatch, r1={"neighbors": {"default": {"10.0.12.2": "established"}}},
             r2={"neighbors_error": lambda t: NoSuchInstance("no BGP yet") if t == 0 else DriverError("cli down")})
    neg = leak("n", timeout=9)
    other = chk("bgp_session", "r2 up", node="r2", neighbor="10.0.23.3")
    blocked, w = gate(e, [neg], extras={"r2": e.drivers["r2"]}, all_checks=[neg, other])
    assert nb_calls(e.drivers["r2"]) == [0, 3, 6, 9]
    assert warns(w, neg) == [("gate-unreadable", "r2", None,
                              "convergence: r2's BGP state could not be read by the cap (9s): cli down")]


def test_an_error_without_text_is_named_by_its_type(monkeypatch):
    e = make(monkeypatch, r1={"neighbors": {"default": {"10.0.12.2": "established"}}},
             r2={"neighbors": {"default": {"10.0.23.3": "established"}},
                 "neighbors_error": lambda t: DriverError("") if t > 0 else None})
    neg = leak("n", timeout=9)
    blocked, w = gate(e, [neg], extras={"r2": e.drivers["r2"]})
    assert warns(w, neg)[0][3] == "convergence: r2's BGP state could not be read by the cap (9s): DriverError"


def test_long_errors_are_cut_at_200_characters(monkeypatch):
    long = "x" * 150 + " " + "y" * 100
    e = make(monkeypatch, r1={"neighbors": {"default": {"10.0.12.2": "established"}}},
             r2={"neighbors_error": DriverError(long)},
             r3={"neighbors": {"default": {"10.0.13.1": "established"}},
                 "neighbors_error": lambda t: DriverError(long) if t > 0 else None})
    neg = leak("n", timeout=9)
    blocked, w = gate(e, [neg], extras={"r2": e.drivers["r2"], "r3": e.drivers["r3"]})
    texts = {x[1]: x[3] for x in warns(w, neg)}
    assert texts["r2"].endswith("(" + long[:200] + ")") and texts["r3"].endswith(": " + long[:200])


def test_a_recovered_extra_warns_about_its_last_state_not_an_earlier_error(monkeypatch):
    e = make(monkeypatch, r1={"neighbors": {"default": {"10.0.12.2": "established"}}},
             r2={"neighbors": {"default": lambda t: {"10.0.23.3": ("established", {"ipv4-unicast": int(t)})}},
                 "neighbors_error": lambda t: DriverError("blip") if t == 3 else None})
    neg = leak("n", timeout=9)
    blocked, w = gate(e, [neg], extras={"r2": e.drivers["r2"]})
    assert [x[0] for x in warns(w, neg)] == ["gate-counts-moving"]


@pytest.mark.parametrize("later", ["error", "empty", "moving"])
def test_a_session_down_earlier_doesnt_stick(monkeypatch, later):
    def nbrs(t):
        if t == 0:
            return {"10.0.23.3": "active"}
        if later == "empty":
            return {}
        return {"10.0.23.3": ("established", {"ipv4-unicast": int(t)})}
    err = (lambda t: DriverError("gone") if t > 0 else None) if later == "error" else None
    e = make(monkeypatch, r1={"neighbors": {"default": {"10.0.12.2": "established"}}},
             r2={"neighbors": {"default": nbrs}, "neighbors_error": err})
    neg = leak("n", timeout=9)
    other = chk("bgp_session", "r2 up", node="r2", neighbor="10.0.23.3")
    blocked, w = gate(e, [neg], extras={"r2": e.drivers["r2"]}, all_checks=[neg, other])
    want = {"error": "gate-unreadable", "empty": "gate-no-neighbors", "moving": "gate-counts-moving"}[later]
    assert [x[0] for x in warns(w, neg)] == [want]


def test_a_node_without_a_driver_doesnt_delay_the_others(monkeypatch):
    e = make(monkeypatch, r1={"neighbors": {"default": {"10.0.12.2": "established"}}})
    gate(e, [leak("n", timeout=30)], extras={"a0": "no driver"})
    assert e.clock.now == 3


def test_a_failing_first_read_doesnt_delay_the_others(monkeypatch):
    e = make(monkeypatch, r1={"neighbors": {"default": {"10.0.12.2": "established"}}},
             r2={"neighbors_error": DriverError("refused")})
    e.drivers["a0"] = e.drivers.pop("r2")
    gate(e, [leak("n", timeout=30)], extras={"a0": e.drivers["a0"]})
    assert e.clock.now == 3


def test_an_extra_is_read_through_its_own_driver(monkeypatch):
    e = make(monkeypatch, r1={"neighbors": {"default": {"10.0.12.2": "established"}}},
             r2={"neighbors": {"default": {"10.0.23.3": "idle"}}})
    other = e.drivers.pop("r2")
    neg = leak("n", timeout=9)
    blocked, w = gate(e, [neg], extras={"r2": other})
    assert [x[0] for x in warns(w, neg)] == ["gate-session-down"]


def test_dead_extras_are_skipped_without_skipping_the_rest(monkeypatch):
    e = make(monkeypatch, r1={"neighbors": {"default": {"10.0.12.2": "established"}}},
             r3={"neighbors": {"default": {"10.0.13.1": "idle"}}})
    dead = checks.Result(chk("route", "a0 x", node="a0", prefix="10.0.0.0/8"), False, "x", 2, 1.0, "t", [], [],
                         samples_unready=2)
    neg = leak("n", timeout=9)
    w: dict = {}
    blocked = runner._bgp_convergence_gate([neg], [neg], e.drivers, log=e.logs.append, warnings=w,
                                           positive_results=[dead],
                                           extras={"a0": e.drivers["r2"], "r3": e.drivers["r3"]})
    assert blocked == {} and [x[1] for x in warns(w, neg)] == ["r3"]
    assert nb_calls(e.drivers["r2"]) == []


def test_end_of_rib_gets_the_neighbors_just_read(monkeypatch):
    got = []
    e = make(monkeypatch, r1={"neighbors": {"default": {"10.0.12.2": "established"}}})

    class D:
        def __init__(self, inner):
            self.inner = inner

        def __getattr__(self, k):
            return getattr(self.inner, k)

        def end_of_rib(self, vrf, neighbors):
            got.append(sorted(neighbors))
            return {}
    e.drivers["r1"] = D(e.drivers["r1"])
    gate(e, [leak("n", timeout=9)])
    assert got and got[0] == ["10.0.12.2"]


def test_an_excluded_session_first_doesnt_hide_a_pending_one(monkeypatch):
    e = make(monkeypatch, r1={"neighbors": {"default": {"10.0.12.1": "established", "10.0.12.9": "established"}}})
    e.drivers["r1"] = EorDrv(e.drivers["r1"], lambda t, v: {"10.0.12.1": {"*": "unknown"},
                                                           "10.0.12.9": {"ipv4-unicast": "pending"}})
    neg = leak("n", timeout=3)
    blocked, _ = gate(e, [neg], expected_down={("r1", "default", "10.0.12.1")})
    assert id(neg) in blocked


def test_untracked_seen_once_is_still_reported(monkeypatch):
    e = make(monkeypatch, r1={"neighbors": {"default": {"10.0.12.2": "established"}}})
    e.drivers["r1"] = EorDrv(e.drivers["r1"], lambda t, v: {"10.0.12.2": {"*": "untracked"}} if t == 0 else
                             {"10.0.12.2": {"ipv4-unicast": "received"}})
    neg = leak("n", timeout=9)
    blocked, w = gate(e, [neg], reported=set())
    assert [x[0] for x in warns(w, neg)] == ["eor-untracked"]


def test_untracked_goes_to_the_first_check_that_ran(monkeypatch):
    e = make(monkeypatch, r1={"neighbors": {"default": {"10.0.12.2": "active"}}},
             r2={"neighbors": {"default": {"10.0.23.3": "established"}}})
    e.drivers["r2"] = EorDrv(e.drivers["r2"], lambda t, v: {"10.0.23.3": {"*": "untracked"}})
    a, b = leak("a", timeout=6), leak("b", node="r2", timeout=6)
    blocked, w = gate(e, [a, b], reported=set())
    assert set(blocked) == {id(a)} and [x[0] for x in warns(w, b)] == ["eor-untracked"] and id(a) not in w


def test_one_reported_untracked_session_doesnt_hide_another(monkeypatch):
    e = make(monkeypatch, r1={"neighbors": {"default": {"10.0.12.2": "established", "10.0.12.6": "established"}}})
    e.drivers["r1"] = EorDrv(e.drivers["r1"], lambda t, v: {"10.0.12.2": {"*": "untracked"},
                                                           "10.0.12.6": {"*": "untracked"}})
    neg = leak("n", timeout=6)
    blocked, w = gate(e, [neg], reported={("r1", "default", "10.0.12.2")})
    assert [(x[0], x[2]) for x in warns(w, neg)] == [("eor-untracked", "10.0.12.6")]
    assert warns(w, neg)[0][3].startswith("convergence: r1's session to 10.0.12.6 doesn't negotiate")


def test_end_of_rib_pending_resets_the_streak(monkeypatch):
    e = make(monkeypatch, r1={"neighbors": {"default": {"10.0.12.2": "established"}}})
    e.drivers["r1"] = EorDrv(e.drivers["r1"], lambda t, v: {"10.0.12.2": {"ipv4-unicast":
                                                           "pending" if t == 3 else "received"}})
    gate(e, [leak("n", timeout=30)])
    assert e.clock.now == 9          # samples at 0 (1), 3 (pending: 0), 6 (1), 9 (2)


def test_own_down_block_exactly(monkeypatch):
    e = make(monkeypatch, r1={"neighbors": {"red": {"10.0.12.2": "active", "10.0.12.6": "idle"}},
                              "neighbors_error": lambda t: DriverError("blip") if t == 3 else None})
    neg = leak("n", timeout=6, vrf="red")
    r = gate(e, [neg])[0][id(neg)]
    assert r.detail == ("not evaluated: BGP session(s) on r1 (vrf red) not established: 10.0.12.2 (active), "
                        "10.0.12.6 (idle) after waiting 6s. A post-convergence check only means something once every "
                        "BGP session on its node is up (a leak can arrive over any of them). If a session is down on "
                        "purpose, add a bgp_session check with state: down for it")
    assert r.check is neg and r.evidence == [] and r.started.endswith("+00:00")
    assert (r.attempts, r.samples_passed, r.samples_unready) == (3, 0, 1)
    assert [h["detail"] for h in r.history] == [
        "BGP session(s) on r1 (vrf red) not established: 10.0.12.2 (active), 10.0.12.6 (idle)",
        "BGP state unreadable on r1: blip",
        "BGP session(s) on r1 (vrf red) not established: 10.0.12.2 (active), 10.0.12.6 (idle)"]


def test_own_no_neighbors_block_exactly(monkeypatch):
    e = make(monkeypatch, r1={"neighbors": {"red": {}}})
    neg = leak("n", timeout=6, vrf="red")
    other = chk("bgp_session", "r1 up", node="r1", neighbor="10.0.12.2", vrf="red")
    r = gate(e, [neg], all_checks=[neg, other])[0][id(neg)]
    assert r.detail == ("not evaluated: r1 reported no BGP neighbors (vrf red) by the cap (6s), although checks in the "
                        "file expect BGP on it. A post-convergence check means nothing before the node's BGP sessions "
                        "exist")
    assert (r.attempts, r.samples_unready) == (3, 3)
    assert [h["detail"] for h in r.history] == ["no BGP neighbors at all on r1 (vrf red)"] * 3


def test_own_no_neighbors_without_bgp_checks_warns_exactly(monkeypatch):
    e = make(monkeypatch, r1={"neighbors": {"red": {}}})
    neg = leak("n", timeout=6, vrf="red")
    blocked, w = gate(e, [neg])
    text = "r1 (vrf red) reported no BGP neighbors for 6s; the check was evaluated without BGP convergence"
    assert blocked == {} and warns(w, neg) == [("no-bgp-neighbors", "r1", None, text)]
    assert e.logs[-1] == "warning: " + text


def test_settled_and_down_samples_are_named(monkeypatch):
    e = make(monkeypatch, r1={"neighbors": {"default": lambda t: {"10.0.12.2": "established" if t < 3 else "idle"}}})
    neg = leak("n", timeout=3)
    r = gate(e, [neg])[0][id(neg)]
    assert [h["detail"] for h in r.history] == ["every BGP session established",
                                                "BGP session(s) on r1 not established: 10.0.12.2 (idle)"]


def test_eor_wait_samples_are_named(monkeypatch):
    e = make(monkeypatch, r1={"neighbors": {"default": {"10.0.12.2": "established"}}})
    e.drivers["r1"] = EorDrv(e.drivers["r1"], lambda t, v: {"10.0.12.2": {"ipv4-unicast": "pending"}})
    neg = leak("n", timeout=3)
    r = gate(e, [neg])[0][id(neg)]
    assert [h["detail"] for h in r.history] == ["End-of-RIB not received on r1 from: 10.0.12.2 (ipv4-unicast: pending)"] * 2


def test_a_long_wait_keeps_the_last_50_samples(monkeypatch):
    e = make(monkeypatch, r1={"neighbors": {"default": {"10.0.12.2": "idle"}}})
    neg = leak("n", timeout=300)
    r = gate(e, [neg])[0][id(neg)]
    assert r.attempts == 101 and len(r.history) == 50 and r.history[-1]["t"] == 300


def test_untracked_in_the_default_vrf_has_no_vrf_part(monkeypatch):
    e = make(monkeypatch, r1={"neighbors": {"default": {"10.0.12.2": "established"}}})
    e.drivers["r1"] = EorDrv(e.drivers["r1"], lambda t, v: {"10.0.12.2": {"*": "untracked"}})
    neg = leak("n", timeout=6)
    blocked, w = gate(e, [neg], reported=set())
    assert warns(w, neg)[0][3].startswith("convergence: r1's session to 10.0.12.2 doesn't negotiate graceful restart")


def test_own_eor_block_result_fields_exactly(monkeypatch):
    e = make(monkeypatch, r1={"neighbors": {"default": {"10.0.12.2": "established"}},
                              "neighbors_error": lambda t: DriverError("blip") if t == 3 else None})
    e.drivers["r1"] = EorDrv(e.drivers["r1"], lambda t, v: {"10.0.12.2": {"ipv4-unicast": "pending"}})
    neg = leak("n", timeout=4.25)
    r = gate(e, [neg])[0][id(neg)]
    assert r.check is neg and r.evidence == [] and r.started.endswith("+00:00")
    assert (r.attempts, r.samples_passed, r.samples_unready) == (3, 0, 1)
    assert r.duration == 4.2 and isinstance(r.duration, float)


def test_own_down_block_duration_is_rounded_to_a_tenth(monkeypatch):
    e = make(monkeypatch, r1={"neighbors": {"default": {"10.0.12.2": "idle"}}})
    neg = leak("n", timeout=4.25)
    r = gate(e, [neg])[0][id(neg)]
    assert r.duration == 4.2 and isinstance(r.duration, float)


def test_own_no_neighbors_block_duration_is_rounded_to_a_tenth(monkeypatch):
    e = make(monkeypatch, r1={"neighbors": {"default": {}}})
    neg = leak("n", timeout=4.25)
    other = chk("bgp_session", "r1 up", node="r1", neighbor="10.0.12.2")
    r = gate(e, [neg], all_checks=[neg, other])[0][id(neg)]
    assert r.duration == 4.2 and isinstance(r.duration, float)


def test_a_long_eor_wait_keeps_the_last_50_samples(monkeypatch):
    e = make(monkeypatch, r1={"neighbors": {"default": {"10.0.12.2": "established"}}})
    e.drivers["r1"] = EorDrv(e.drivers["r1"], lambda t, v: {"10.0.12.2": {"ipv4-unicast": "pending"}})
    neg = leak("n", timeout=300)
    r = gate(e, [neg])[0][id(neg)]
    assert r.attempts == 101 and len(r.history) == 50 and r.history[0]["t"] == 153


def test_an_extra_reads_end_of_rib_through_its_own_driver(monkeypatch):
    e = make(monkeypatch, r1={"neighbors": {"default": {"10.0.12.2": "established"}}},
             r2={"neighbors": {"default": {"10.0.23.3": "established"}}})
    other = EorDrv(e.drivers.pop("r2"), lambda t, v: {"10.0.23.3": {"ipv4-unicast": "pending"}})
    neg = leak("n", timeout=6)
    blocked, w = gate(e, [neg], extras={"r2": other})
    assert [x[0] for x in warns(w, neg)] == ["gate-eor-pending"]


def test_a_node_waiting_for_end_of_rib_doesnt_delay_the_others(monkeypatch):
    e = make(monkeypatch, r1={"neighbors": {"default": {"10.0.12.2": "established"}}},
             r2={"neighbors": {"default": {"10.0.23.3": "established"}}})
    e.drivers["a1"] = EorDrv(e.drivers.pop("r2"), lambda t, v: {"10.0.23.3": {"ipv4-unicast": "pending"}})
    a, b = leak("a", node="a1", timeout=9), leak("b", timeout=9)
    gate(e, [a, b])
    assert nb_calls(e.drivers["r1"]) == [0, 3]
