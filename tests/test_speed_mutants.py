"""Mutation follow-up for the speed work (test_speed.py): the fail-fast rule, phase timings and the Junos connection,
pinned exactly enough that a changed condition, key or number is noticed."""
import pytest

from netdryrun import runner
from netdryrun.checks import Missing, Quiescence, Result, RoundMemo, _evaluate_all, run_round_robin
from netdryrun.drivers.base import BgpNeighbor, DriverError, NoSuchInstance, Observation, Route
from netdryrun.drivers.frr import quiescence_timer_of
from netdryrun.drivers.junos import MUX_OPTS, MUX_START, VM_SSH, JunosDriver
from netdryrun.lab import ExecResult, Node
from test_runner_robustness import FakeLab, World, cfg, chk, install
from test_speed import FRR_PLAIN, NO_REPLY, ROUTE, Clock, JLab, Net, check, rr


class Vrfs(Net):
    """Per-VRF state: neighbors_by[vrf](t), rib_by[(vrf, family)](t); a VRF or table not listed doesn't exist."""

    def __init__(self, clock, neighbors_by, rib_by, **kw):
        super().__init__(clock, **kw)
        self.neighbors_by, self.rib_by = neighbors_by, rib_by

    def bgp_neighbors(self, vrf="default"):
        if vrf not in self.neighbors_by:
            raise NoSuchInstance(f"no VRF {vrf}")
        return Observation({a: BgpNeighbor(a, s, {"ipv4-unicast": n}, adv_interval=self.adv)
                            for a, (s, n) in self.neighbors_by[vrf](self.clock.t).items()}, [])

    def all_routes(self, vrf="default", family=4):
        if (vrf, family) not in self.rib_by:
            raise NoSuchInstance(f"no table {vrf} {family}")
        return Observation(self.rib_by[(vrf, family)](self.clock.t), [])


def UP(t):
    return {"10.0.0.2": ("established", 3)}


def DOWN(t):
    return {"10.9.0.2": ("active", 0)}


def STILL(t):
    return [Route("10.0.0.0/30", "connected", True)]


def MOVING(t):
    return [Route(f"2001:db8:{int(t // 3) % 250:x}::/48", "bgp", True)]


@pytest.mark.parametrize("why,neighbors_by,rib_by,vrfs", [
    ("a VRF a check names has a session down", {"default": UP, "red": DOWN},
     {("default", 4): STILL, ("default", 6): STILL}, {"red"}),
    ("a later VRF has a session down, after one the node does not have", {"default": UP, "red": DOWN},
     {("default", 4): STILL, ("default", 6): STILL}, {"blue", "red"}),
    ("the IPv6 table keeps moving", {"default": UP}, {("default", 4): STILL, ("default", 6): MOVING}, set()),
    ("the IPv6 table keeps moving where IPv4 has no table", {"default": UP}, {("default", 6): MOVING}, set()),
    ("the table of a VRF keeps moving", {"default": UP, "red": UP},
     {("default", 4): STILL, ("default", 6): STILL, ("red", 4): MOVING, ("red", 6): STILL}, {"red"}),
])
def test_every_vrf_and_both_families_must_hold_still(why, neighbors_by, rib_by, vrfs):
    c = Clock()
    d = Vrfs(c, neighbors_by, rib_by)
    [r] = rr([check("route", **ROUTE)], {"r1": d}, c, Quiescence({"r1": d}, vrfs, 10.0))
    assert "ended early" not in r.detail and r.duration >= 90, why


def test_a_ping_in_a_vrf_is_judged_by_the_table_of_that_vrf():
    c = Clock()
    d = Vrfs(c, {"default": UP, "red": UP},
             {("default", 4): lambda t: [Route("192.168.3.0/24", "bgp", True)], ("default", 6): STILL,
              ("red", 4): STILL, ("red", 6): STILL}, ping=NO_REPLY)
    [r] = rr([check("ping", target="192.168.3.1", vrf="red")], {"r1": d}, c, Quiescence({"r1": d}, {"red"}, 10.0))
    assert "ended early" in r.detail


def test_quiescence_needs_three_samples_spanning_the_window_exactly():
    c = Clock()
    d = Net(c)
    [r] = rr([check("route", **ROUTE)], {"r1": d}, c, Quiescence({"r1": d}, (), 6.0))
    assert r.duration == 6.0   # samples at 0, 3 and 6 s: three of them, the window apart from first to last


def test_a_check_that_read_missing_after_the_stretch_began_keeps_waiting():
    """A reads missing from the start, B only from 3 s (its first read failed). The stretch began with A, so B had a
    sample in it that wasn't missing: B waits out its timeout while A ends early."""
    c = Clock()

    class Late(Net):
        def routes(self, prefix, vrf="default"):
            if prefix == "192.168.4.0/24" and self.clock.t < 3:
                raise DriverError("zebra is still starting")
            return super().routes(prefix, vrf)
    d = Late(c)
    seen = []
    a, b = run_round_robin([check("route", prefix="192.168.3.0/24"), check("route", prefix="192.168.4.0/24")],
                           {"r1": d}, clock=c, sleep=c.sleep, quiet=Quiescence({"r1": d}, (), 10.0),
                           on_result=seen.append)
    assert "ended early" in a.detail and a.passed is False
    assert "ended early" not in b.detail and b.duration >= 90
    assert len(seen) == 2   # each result reported once


def test_a_check_whose_reads_fail_again_is_no_longer_missing():
    c = Clock()

    class Gone(Net):
        def routes(self, prefix, vrf="default"):
            if self.clock.t >= 3:
                raise DriverError("zebra stopped answering")
            return super().routes(prefix, vrf)
    d = Gone(c)
    [r] = rr([check("route", **ROUTE)], {"r1": d}, c, Quiescence({"r1": d}, (), 10.0))
    assert "ended early" not in r.detail and r.duration >= 90


def test_one_check_that_may_not_end_early_does_not_stop_another_that_may():
    c = Clock()
    d = Net(c, ping=NO_REPLY, rib=lambda t: [Route("192.168.3.0/24", "bgp", True)])
    ping, route = rr([check("ping", target="192.168.3.1"), check("route", prefix="10.99.0.0/24")], {"r1": d}, c,
                     Quiescence({"r1": d}, (), 10.0))
    assert "ended early" not in ping.detail and "ended early" in route.detail


def test_an_early_end_keeps_its_evidence_timing_and_wording_on_any_clock():
    c = Clock()
    c.t = 1000.0

    class Ev(Net):
        def routes(self, prefix, vrf="default"):
            return Observation([], [{"node": "r1", "cmd": "show ip route", "output": "{}"}])
    d = Ev(c)
    [r] = rr([check("route", **ROUTE)], {"r1": d}, c, Quiescence({"r1": d}, (), 10.0))
    assert r.passed is False and r.duration == 12.0
    assert r.evidence == [{"node": "r1", "cmd": "show ip route", "output": "{}"}]
    assert r.detail.endswith("(ended early at 12s of its 90s timeout: the lab was quiescent for 12s, every BGP "
                             "session established and no prefix count or routing table changing)")


def test_first_ready_is_seconds_with_one_decimal():
    class Slow(Net):
        def routes(self, prefix, vrf="default"):
            self.clock.t += 1.234
            return super().routes(prefix, vrf)
    c = Clock()
    [r] = rr([check("route", **ROUTE, timeout=1)], {"r1": Slow(c)}, c)
    assert r.first_ready == 1.2


def test_missing_details_say_what_is_missing():
    c = Clock()
    d = Net(c, neighbors=lambda t: {"10.0.0.2": ("established", 0)},
            ping=lambda t: Observation((0, 0), [{"output": "", "stderr": "connect: Network is unreachable"}]))
    out = _evaluate_all([check("route", prefix="10.9.0.0/24"), check("bgp_prefixes", neighbor="10.0.0.2", min=1),
                         check("ping", target="10.9.0.1")], {"r1": d})
    assert [str(x[1]) for x in out] == ["not active; seen: nothing", "0 ipv4-unicast prefixes accepted",
                                        "0/3 replies (destination unreachable: Network is unreachable)"]
    assert all(isinstance(x[1], Missing) for x in out)
    above = Net(c, neighbors=lambda t: {"10.0.0.2": ("established", 9)})
    [(ok, detail, _)] = _evaluate_all([check("bgp_prefixes", neighbor="10.0.0.2", min=1, max=5)], {"r1": above})
    assert not ok and not isinstance(detail, Missing)   # too many is never "missing"


def test_routed_reads_prefixes_with_host_bits():
    q = Quiescence({}, (), 10.0)
    q.ribs[("r1", "default", 4)] = [Route("192.168.3.1/24", "bgp", True)]
    assert q.routed("r1", "default", "192.168.3.9")


def test_the_round_memo_passes_keyword_arguments_through():
    d = Net(Clock())
    memo = RoundMemo({"r1": d})
    assert memo["r1"].all_routes(vrf="default", family=6).value == []
    assert memo["r1"].all_routes(vrf="default", family=4).value


def test_frr_ignores_an_advertise_map_in_a_comment():
    assert quiescence_timer_of(FRR_PLAIN + "! neighbor 10.0.12.2 advertise-map A exist-map B\n") == 0.0


def test_junos_starts_the_shared_connection_on_its_own_node_exactly():
    lab = JLab()
    nodes = []
    lab.exec_detached = lambda node, cmd, timeout=15: nodes.append((node, cmd))
    JunosDriver(lab, "j1")._cli("show route instance master", [])
    assert nodes == [("j1", ["sh", "-c", MUX_START])]
    assert lab.argv[0] == [*VM_SSH[:-1], *MUX_OPTS, VM_SSH[-1],
                           "cli -c 'show route instance master | display json | no-more'"]
    assert "BatchMode=yes" in lab.argv[0]


class _Lab:
    def __init__(self, nodes):
        self.nodes = {n: Node(n, f"c-{n}", kind, "img") for n, kind in nodes}


def test_routing_drivers_skips_bridges_and_needs_every_other_node():
    drivers = {"r1": object(), "r2": object()}

    def driver_for(n):
        if n not in drivers:
            raise DriverError(f"no driver for {n}")
        return drivers[n]
    for kind in ("bridge", "ovs-bridge"):
        assert runner._routing_drivers(_Lab([("br", kind), ("r1", "linux"), ("r2", "linux")]), driver_for) == drivers
    assert runner._routing_drivers(_Lab([("r1", "linux"), ("h1", "linux")]), driver_for) is None
    assert runner._routing_drivers(_Lab([("br", "bridge")]), driver_for) is None


def test_ready_is_when_the_slowest_node_first_answered():
    rs = [Result(check("route", node=n, **ROUTE), True, "", 1, 0, "", first_ready=t)
          for n, t in (("r1", 3.0), ("r1", 9.0), ("r2", 6.0))]
    assert runner._ready_after(rs) == 6.0
    rs.append(Result(check("route", node="r3", **ROUTE), False, "", 1, 0, "", first_ready=None))
    assert runner._ready_after(rs) is None


def test_the_run_watches_the_vrfs_its_checks_name_with_its_settle(tmp_path, monkeypatch):
    w = World()
    lab = FakeLab(w, nodes=("r1",))
    install(monkeypatch, w, lab, {"r1": Net(w, route=lambda t, prefix: True)})
    made = []
    monkeypatch.setattr(runner, "Quiescence", lambda *a: made.append(a) or Quiescence(*a))
    runner.run(cfg(tmp_path, [chk("route", "red route", node="r1", prefix="10.0.0.0/24", vrf="red"),
                              chk("route", "plain", node="r1", prefix="10.1.0.0/24")]), settle=30.0)
    [(nodes, vrfs, settle)] = made
    assert set(nodes) == {"r1"} and vrfs == {"red"} and settle == 30.0


def test_phase_timings_are_rounded_to_a_tenth_from_any_start(tmp_path, monkeypatch):
    w = World()
    w.t = 500.0
    lab = FakeLab(w, nodes=("r1",))

    def deploy():
        w.t += 1.234
        return ExecResult([], 0, "", "")
    lab.deploy = deploy
    install(monkeypatch, w, lab, {"r1": Net(w, route=lambda t, prefix: True)})
    rep = runner.run(cfg(tmp_path, [chk("route", "plain", node="r1", prefix="10.1.0.0/24")]))
    assert rep.timings["deploy"] == 1.2 and rep.timings["total"] == round(w.t - 500.0, 1)
    assert all(isinstance(v, float) for k, v in rep.timings.items() if k not in ("ended_early", "ready"))
