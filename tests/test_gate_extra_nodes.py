"""The BGP gate also waits for every other routing node, warning-only (0.4.1 red-team fixes, design round 3 "G", "W2").

Red team B-9005: a leak guard on r1 passed while r2's session to r3 was still coming up, because the gate only watched
r1's own sessions; the leak arrived two hops away after the checks were done. The gate now also waits, up to the same
cap, for every lab node with a routing driver, in the default VRF and every VRF the file's checks name. A node that is
still not settled at the cap never blocks (the documented limit shrinks to the per-hop advertisement interval), but
every post-convergence check carries a warning naming the node and the session. Counts still moving on the check's own
node at the cap go ahead with a warning too (W2).

Each test is red on 1de8d70 (no extra-node wait, no warning).
"""
from __future__ import annotations

from netdryrun import runner
from netdryrun.drivers.base import DriverError

from test_verdict_runner import Clock, FakeLab, chk, leak, make


def gate(e, negatives, all_checks=None, warnings=None, extras=None, lab=None, expected_down=frozenset()):
    return runner._bgp_convergence_gate(negatives, all_checks if all_checks is not None else negatives, e.drivers,
                                        log=e.logs.append, warnings=warnings, lab=lab,
                                        extras=extras if extras is not None else
                                        {n: d for n, d in e.drivers.items()},
                                        expected_down=expected_down)


def codes(warnings, check):
    return [(w["code"], w["node"], w["session"]) for w in warnings.get(id(check), [])]


def test_a_session_down_two_hops_away_is_waited_for_then_warned_on_every_check(monkeypatch):
    e = make(monkeypatch, r1={"neighbors": {"default": {"10.0.12.2": "established"}}},
             r2={"neighbors": {"default": {"10.0.12.1": "established", "10.0.23.3": "active"}}})
    neg = leak("n", timeout=30)
    w: dict = {}
    assert gate(e, [neg], warnings=w) == {}                 # never a block for another node
    assert e.clock.now >= 30                                # it waited the cap for r2
    assert codes(w, neg) == [("gate-session-down", "r2", "10.0.23.3")]
    assert "10.0.23.3" in w[id(neg)][0]["text"]


def test_an_extra_node_that_comes_up_is_waited_for_without_a_warning(monkeypatch):
    e = make(monkeypatch, r1={"neighbors": {"default": {"10.0.12.2": "established"}}},
             r2={"neighbors": {"default": lambda t: {"10.0.23.3": "established" if t >= 12 else "connect"}}})
    neg = leak("n", timeout=60)
    w: dict = {}
    assert gate(e, [neg], warnings=w) == {}
    assert 12 <= e.clock.now < 60 and w == {}


def test_an_extra_node_whose_first_read_fails_is_a_warning(monkeypatch):
    e = make(monkeypatch, r1={"neighbors": {"default": {"10.0.12.2": "established"}}},
             r2={"neighbors_error": DriverError("vtysh: connection refused")})
    neg = leak("n", timeout=60)
    w: dict = {}
    assert gate(e, [neg], warnings=w) == {}
    assert codes(w, neg) == [("gate-unreadable", "r2", None)]
    assert e.clock.now < 60                                 # no wait on a broken CLI


def test_a_routing_node_that_cannot_be_read_at_all_is_a_warning():
    clock = Clock()
    lab = FakeLab(clock, kinds={"r2": ("mikrotik_ros", "mikrotik/routeros:7")})

    def driver_for(node):
        if node == "r2":
            raise DriverError("node r2 runs MikroTik RouterOS, whose driver is an unreleased beta")
        return object()

    extras = runner._routing_nodes(lab, driver_for)
    assert isinstance(extras["r2"], str) and set(extras) == {"r1", "r2", "r3"}


def test_a_host_without_a_routing_driver_is_left_out():
    clock = Clock()
    lab = FakeLab(clock, kinds={"h1": ("linux", "alpine:3")}, nodes=("r1", "h1"))
    from netdryrun.drivers import Undetectable

    def driver_for(node):
        if node == "h1":
            raise Undetectable("cannot detect driver for node h1")
        return object()

    assert set(runner._routing_nodes(lab, driver_for)) == {"r1"}


def test_a_node_without_bgp_is_not_waited_for(monkeypatch):
    # r2 and r3 answer no neighbors (static routing) and no check names BGP on them: no wait, no warning
    e = make(monkeypatch, r1={"neighbors": {"default": {"10.0.12.2": "established"}}})
    neg = leak("n", timeout=60)
    w: dict = {}
    assert gate(e, [neg], warnings=w) == {} and w == {} and e.clock.now < 10


def test_a_node_the_file_says_runs_bgp_with_no_neighbors_at_the_cap_is_a_warning(monkeypatch):
    e = make(monkeypatch, r1={"neighbors": {"default": {"10.0.12.2": "established"}}})
    neg = leak("n", timeout=30)
    other = chk("bgp_session", "r2 up", node="r2", neighbor="10.0.23.3")
    w: dict = {}
    assert gate(e, [neg], all_checks=[neg, other], warnings=w) == {}
    assert codes(w, neg) == [("gate-no-neighbors", "r2", None)]


def test_the_extra_wait_covers_the_vrfs_the_checks_name(monkeypatch):
    e = make(monkeypatch, r1={"neighbors": {"default": {"10.0.12.2": "established"},
                                            "red": {"10.1.12.2": "established"}}},
             r2={"neighbors": {"default": {"10.0.12.1": "established"}, "red": {"10.1.23.3": "idle"}}})
    neg = leak("n", timeout=30, vrf="red")
    w: dict = {}
    assert gate(e, [neg], warnings=w) == {}
    assert codes(w, neg) == [("gate-session-down", "r2", "10.1.23.3")]


def test_a_session_declared_down_is_excluded_at_its_far_end(monkeypatch):
    # r1 declares its session to r2 down; r2's session back to r1 (10.0.12.1) is down too, and is not a warning
    e = make(monkeypatch, r1={"neighbors": {"default": {"10.0.12.2": "idle", "10.0.13.3": "established"}}},
             r2={"neighbors": {"default": {"10.0.12.1": "idle"}}})
    neg = leak("n", timeout=30)
    down = chk("bgp_session", "r1-r2 down", node="r1", neighbor="10.0.12.2", state="down")
    w: dict = {}
    assert gate(e, [neg], all_checks=[neg, down], warnings=w, lab=e.lab) == {}
    assert w == {} and e.clock.now < 30


def test_the_own_node_still_blocks(monkeypatch):
    e = make(monkeypatch, r1={"neighbors": {"default": {"10.0.12.2": "active"}}})
    neg = leak("n", timeout=30)
    assert id(neg) in gate(e, [neg], warnings={})


def test_counts_still_moving_at_the_cap_go_ahead_with_a_warning(monkeypatch):
    e = make(monkeypatch, r1={"neighbors": {"default": lambda t: {"10.0.12.2": ("established",
                                                                                 {"ipv4-unicast": int(t)})}}})
    neg = leak("n", timeout=30)
    w: dict = {}
    assert gate(e, [neg], warnings=w, extras={}) == {}
    assert codes(w, neg) == [("gate-counts-moving", "r1", None)]


def test_a_whole_run_puts_the_warning_on_the_result(monkeypatch):
    e = make(monkeypatch, r1={"neighbors": {"default": {"10.0.12.2": "established"}}, "routes": {"default": lambda t, p: False}},
             r2={"neighbors": {"default": {"10.0.12.1": "established", "10.0.23.3": "active"}},
                 "routes": {"default": lambda t, p: True}})
    rep = e.run([leak("n", timeout=30)], settle=1, hold=3)
    r = rep.results[0]
    assert r.passed and [w["code"] for w in r.warnings] == ["gate-session-down"]


def _lab(addresses, links):
    lab = FakeLab(Clock(), nodes=("r1", "r2", "r3", "r4", "ix"), kinds={"ix": ("bridge", "")}, addresses=addresses,
                  links=links)
    return lab


def test_far_end_exclusion_is_only_the_declared_session_on_a_dual_stack_link():
    """Adversary on 6d66267: declaring r1 -> 10.0.12.2 down excluded r2's IPv6, link-local and unnumbered sessions to r1."""
    lab = _lab({("r1", "eth1"): ["10.0.12.1/30", "2001:db8:12::1/64", "fe80::1/64"],
                ("r2", "eth1"): ["10.0.12.2/30", "2001:db8:12::2/64", "fe80::2/64"]},
               [(("r1", "eth1"), ("r2", "eth1"))])
    assert runner._far_ends(lab, {("r1", "default", "10.0.12.2")}) == {("r2", "default", "10.0.12.1")}


def test_far_end_exclusion_on_a_bridge_is_only_the_peer_that_owns_the_address():
    lab = _lab({("r1", "eth1"): ["10.0.0.1/24"], ("r2", "eth1"): ["10.0.0.2/24"], ("r3", "eth1"): ["10.0.0.3/24"],
                ("r4", "eth1"): ["10.0.0.4/24"]},
               [(("r1", "eth1"), ("ix", "p1")), (("r2", "eth1"), ("ix", "p2")), (("r3", "eth1"), ("ix", "p3")),
                (("r4", "eth1"), ("ix", "p4"))])
    assert runner._far_ends(lab, {("r1", "default", "10.0.0.4")}) == {("r4", "default", "10.0.0.1")}


def test_a_session_down_on_purpose_gets_a_hint(monkeypatch):
    e = make(monkeypatch, r1={"neighbors": {"default": {"10.0.12.2": "established"}}},
             r2={"neighbors": {"default": {"192.0.2.9": "active"}}})
    neg = leak("n", timeout=30)
    w: dict = {}
    gate(e, [neg], warnings=w)
    assert "state: down" in w[id(neg)][0]["text"]
