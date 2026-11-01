"""Track A speed work (0.4.1): phase timings, one shared read per node per round, fail-fast on a quiescent lab,
parallel verify boots, the cached base snapshot, the reused Junos SSH connection and the Action's plumbing.

Every speed-up here may only make a failing run fail sooner; none may turn a fail into a pass, and none may
shorten settle, hold or the confirmation spacing."""
import json
import re
import threading
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from netdryrun import runner
from netdryrun.checks import (Missing, Quiescence, RoundMemo, Unready, _evaluate_all, hold_together,
                              run_round_robin)
from netdryrun.config import Check
from netdryrun.drivers.base import BgpNeighbor, Driver, DriverError, NoSuchInstance, Observation, Route
from netdryrun.drivers.frr import FrrDriver, quiescence_timer_of
from netdryrun.drivers.junos import MUX_OPTS, JunosDriver
from netdryrun.drivers.sonic import SonicDriver
from netdryrun.lab import ExecResult, Node
from netdryrun.report import to_json
from netdryrun.verify import run as vrun
from netdryrun.verify.converge import Inconclusive
from test_runner_robustness import FakeLab, World, cfg, chk, install
from test_verify_run import fake_side, intent_file, make_lab, side_dir, NEW_BLOCK
from verify_helpers import add_new_customer_block, base

ROOT = Path(__file__).parents[1]


# ------------------------------------------------------------------------------------------- fakes

class Clock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t

    def sleep(self, s):
        self.t += max(0.0, s)


class Net:
    """A node whose state is a function of the clock: neighbors(t) -> {addr: (state, prefixes)}, rib(t) -> [Route],
    route(t, prefix) -> bool. Every read is counted."""

    def __init__(self, clock, neighbors=None, rib=None, route=None, timer=0.0, adv=0.0, ping=None):
        self.clock = clock
        self._neighbors = neighbors or (lambda t: {"10.0.0.2": ("established", 3)})
        self._rib = rib or (lambda t: [Route("10.0.0.0/30", "connected", True)])
        self._route = route or (lambda t, prefix: False)
        self.timer, self.adv, self._ping = timer, adv, ping
        self.reads: dict[str, int] = {}
        self.name = "frr"

    def nos_version(self):
        return None

    def _count(self, what):
        self.reads[what] = self.reads.get(what, 0) + 1

    def quiescence_timer(self):
        self._count("timer")
        return self.timer

    def bgp_neighbors(self, vrf="default"):
        self._count("bgp_neighbors")
        return Observation({a: BgpNeighbor(a, s, {"ipv4-unicast": n}, adv_interval=self.adv)
                            for a, (s, n) in self._neighbors(self.clock.t).items()}, [])

    def routes(self, prefix, vrf="default"):
        self._count("routes")
        return Observation([Route(prefix, "bgp", True)] if self._route(self.clock.t, prefix) else [], [])

    def bgp_paths(self, prefix, vrf="default"):
        self._count("bgp_paths")
        return Observation([], [])

    def all_routes(self, vrf="default", family=4):
        self._count(f"all_routes{family}")
        return Observation(self._rib(self.clock.t) if family == 4 else [], [])

    def ping(self, target, source, count, vrf="default"):
        self._count("ping")
        if self._ping:
            return self._ping(self.clock.t)
        return Observation((0, 0), [{"output": "", "stderr": "connect: Network is unreachable"}])


def check(ctype, node="r1", timeout=90, **params):
    return Check(type=ctype, params={"node": node, **params}, name=f"{ctype} {params}", timeout=timeout)


def rr(checks, drivers, clock, quiet=None):
    return run_round_robin(checks, drivers, clock=clock, sleep=clock.sleep, quiet=quiet)


ROUTE = dict(prefix="192.168.3.0/24", protocol="bgp")


# ------------------------------------------------------------------------- A1: one read per round

def test_checks_on_one_node_share_one_read_per_round():
    c = Clock()
    d = Net(c)
    cs = [check("bgp_session", neighbor="10.0.0.2", state="established"), check("bgp_prefixes", neighbor="10.0.0.2", min=1),
          check("route", **ROUTE), check("route", **ROUTE, active=False)]
    out = _evaluate_all(cs, {"r1": d})
    assert [ok for ok, _, _ in out] == [True, True, False, False]
    assert d.reads == {"bgp_neighbors": 1, "routes": 1}


def test_each_round_reads_the_state_again():
    c = Clock()
    d = Net(c, neighbors=lambda t: {"10.0.0.2": ("active" if t < 6 else "established", 3)})
    r = rr([check("bgp_session", neighbor="10.0.0.2", state="established"),
            check("bgp_prefixes", neighbor="10.0.0.2", min=1)], {"r1": d}, c)
    assert all(x.passed for x in r)
    assert d.reads["bgp_neighbors"] == r[0].attempts   # one read per round, never a stale one


def test_a_shared_read_that_fails_fails_every_check_that_needed_it():
    class Broken(Net):
        def bgp_neighbors(self, vrf="default"):
            self._count("bgp_neighbors")
            raise DriverError("`vtysh -c show bgp neighbors json` failed on r1 (rc=1): bgpd is not running")
    d = Broken(Clock())
    out = _evaluate_all([check("bgp_session", neighbor="10.0.0.2", state="established"),
                         check("bgp_prefixes", neighbor="10.0.0.2", min=1)],
                        {"r1": d})
    assert [ok for ok, _, _ in out] == [False, False]
    assert all(isinstance(detail, Unready) and "bgpd is not running" in detail for _, detail, _ in out)
    assert d.reads == {"bgp_neighbors": 1}


def test_pings_are_never_shared():
    d = Net(Clock())
    _evaluate_all([check("ping", target="10.0.0.9"), check("ping", target="10.0.0.9")], {"r1": d})
    assert d.reads == {"ping": 2}


def test_each_caller_gets_its_own_copy():
    d = Net(Clock())
    memo = RoundMemo({"r1": d})
    a, b = memo["r1"].bgp_neighbors("default"), memo["r1"].bgp_neighbors("default")
    a.value["10.0.0.2"].state = "idle"
    assert b.value["10.0.0.2"].state == "established" and d.reads == {"bgp_neighbors": 1}
    assert memo["r1"].bgp_neighbors(vrf="default").value   # keyword arguments are another key, still answered


def test_concurrent_callers_wait_for_the_one_read():
    started, release = threading.Event(), threading.Event()

    class Slow(Net):
        def bgp_neighbors(self, vrf="default"):
            self._count("bgp_neighbors")
            started.set()
            release.wait(5)
            return super().bgp_neighbors(vrf)
    d = Slow(Clock())
    memo = RoundMemo({"r1": d})
    out = []
    ts = [threading.Thread(target=lambda: out.append(memo["r1"].bgp_neighbors("default"))) for _ in range(4)]
    for t in ts:
        t.start()
    started.wait(5)
    release.set()
    for t in ts:
        t.join(5)
    assert len(out) == 4 and d.reads["bgp_neighbors"] == 2   # Slow counts twice: its own and Net's


# --------------------------------------------------------------- A2: fail fast on a quiescent lab

def quiet_for(drivers, settle=10.0):
    return Quiescence(drivers, (), settle)


def test_a_missing_route_in_a_lab_that_stopped_changing_fails_early():
    c = Clock()
    d = Net(c)
    [r] = rr([check("route", **ROUTE)], {"r1": d}, c, quiet_for({"r1": d}))
    assert not r.passed and "ended early" in r.detail and r.duration < 20
    assert "not active via bgp" in r.detail


def test_without_quiescence_it_waits_out_the_timeout():
    c = Clock()
    d = Net(c)
    [r] = rr([check("route", **ROUTE)], {"r1": d}, c)
    assert not r.passed and "ended early" not in r.detail and r.duration >= 90


@pytest.mark.parametrize("why,net", [
    ("a session is down", dict(neighbors=lambda t: {"10.0.0.2": ("established", 3), "10.0.0.6": ("active", 0)})),
    ("no BGP neighbors at all", dict(neighbors=lambda t: {})),
    ("the driver can't tell its late timers", dict(timer=None)),
    ("the advertisement interval is unknown", dict(adv=None)),
    ("prefix counts keep moving", dict(neighbors=lambda t: {"10.0.0.2": ("established", int(t // 3))})),
    ("the routing table keeps moving", dict(rib=lambda t: [Route(f"10.{int(t // 3) % 250}.0.0/16", "bgp", True)])),
])
def test_it_never_ends_early_unless_the_whole_lab_is_quiescent(why, net):
    c = Clock()
    d = Net(c, **net)
    [r] = rr([check("route", **ROUTE)], {"r1": d}, c, quiet_for({"r1": d}))
    assert not r.passed and "ended early" not in r.detail and r.duration >= 90, why


def test_another_node_still_converging_keeps_it_waiting():
    c = Clock()
    r1 = Net(c)
    r3 = Net(c, neighbors=lambda t: {"10.0.13.1": ("connect" if t < 60 else "established", 0 if t < 60 else 1)})
    [r] = rr([check("route", **ROUTE)], {"r1": r1}, c, quiet_for({"r1": r1, "r3": r3}))
    assert r.duration >= 70   # quiescent only from 60s, when r3's session is up: then the window again


def test_a_route_that_arrives_after_the_lab_moves_again_still_passes():
    """Counts settle, then move again at 40s (a slower peer), and the route lands at 45s: the stretch before 40s was
    too short to count as quiescent, so the check gets its pass."""
    c = Clock()
    d = Net(c, neighbors=lambda t: {"10.0.0.2": ("established", 3 if t < 40 else 4)},
            route=lambda t, prefix: t >= 45)
    [r] = rr([check("route", **ROUTE)], {"r1": d}, c, Quiescence({"r1": d}, (), 50.0))
    assert r.passed


def test_the_window_covers_the_longest_advertisement_interval():
    c = Clock()
    d = Net(c, adv=30.0)
    [r] = rr([check("route", **ROUTE)], {"r1": d}, c, quiet_for({"r1": d}))
    assert "ended early" in r.detail and r.duration >= 32


def test_the_window_covers_conditional_advertisement():
    c = Clock()
    d = Net(c, timer=60.0)
    [r] = rr([check("route", **ROUTE)], {"r1": d}, c, quiet_for({"r1": d}))
    assert "ended early" in r.detail and r.duration >= 62


def test_a_check_that_ever_passed_never_ends_early():
    c = Clock()
    d = Net(c, route=lambda t, prefix: 3 <= t < 6)   # one passing sample, then gone
    [r] = rr([check("route", **ROUTE)], {"r1": d}, c, quiet_for({"r1": d}))
    assert not r.passed and "ended early" not in r.detail and "flapping" in r.detail


def test_a_session_check_never_ends_early():
    c = Clock()
    d = Net(c)
    [r] = rr([check("bgp_session", neighbor="10.9.9.9", state="established")], {"r1": d}, c, quiet_for({"r1": d}))
    assert not r.passed and "ended early" not in r.detail and r.duration >= 90


def test_a_ping_ends_early_only_when_its_node_has_no_route_to_the_target():
    c = Clock()
    no_route = Net(c)
    [r] = rr([check("ping", target="192.168.3.1")], {"r1": no_route}, c, quiet_for({"r1": no_route}))
    assert "ended early" in r.detail
    c = Clock()
    routed = Net(c, rib=lambda t: [Route("192.168.3.0/24", "bgp", True)])
    [r] = rr([check("ping", target="192.168.3.1")], {"r1": routed}, c, quiet_for({"r1": routed}))
    assert "ended early" not in r.detail and r.duration >= 90


def test_a_ping_that_got_no_reply_is_not_missing():
    c = Clock()
    d = Net(c, ping=lambda t: Observation((3, 0), [{"output": "3 packets transmitted, 0 received", "stderr": ""}]))
    [r] = rr([check("ping", target="192.168.3.1")], {"r1": d}, c, quiet_for({"r1": d}))
    assert "ended early" not in r.detail and r.duration >= 90


def test_a_fingerprint_read_that_fails_starts_the_count_again():
    c = Clock()

    class Flaky(Net):
        def all_routes(self, vrf="default", family=4):
            if int(self.clock.t // 3) % 3 == 0:
                raise DriverError("zebra is busy")
            return super().all_routes(vrf, family)
    d = Flaky(c)
    [r] = rr([check("route", **ROUTE)], {"r1": d}, c, quiet_for({"r1": d}))
    assert "ended early" not in r.detail and r.duration >= 90


def test_missing_vrfs_count_as_nothing_there_but_other_errors_do_not():
    c = Clock()

    class NoVrf(Net):
        def bgp_neighbors(self, vrf="default"):
            if vrf != "default":
                raise NoSuchInstance("no such VRF")
            return super().bgp_neighbors(vrf)
    d = NoVrf(c)
    [r] = rr([check("route", **ROUTE)], {"r1": d}, c, Quiescence({"r1": d}, {"red"}, 10.0))
    assert "ended early" in r.detail


def test_prefix_minimum_and_bgp_path_failures_are_missing_but_down_sessions_are_not():
    c = Clock()
    up = Net(c, neighbors=lambda t: {"10.0.0.2": ("established", 0)})
    down = Net(c, neighbors=lambda t: {"10.0.0.2": ("active", 0)})
    [(_, low, _)] = _evaluate_all([check("bgp_prefixes", neighbor="10.0.0.2", min=1)], {"r1": up})
    [(_, sess, _)] = _evaluate_all([check("bgp_prefixes", neighbor="10.0.0.2", min=1)], {"r1": down})
    [(_, path, _)] = _evaluate_all([check("bgp_route", prefix="192.168.3.0/24")], {"r1": up})
    assert isinstance(low, Missing) and isinstance(path, Missing) and not isinstance(sess, Missing)


def test_post_convergence_checks_are_untouched():
    c = Clock()
    d = Net(c)
    [r] = hold_together([check("route", prefix="0.0.0.0/0", present=False)], {"r1": d}, hold=10, clock=c, sleep=c.sleep)
    assert r.passed and "held" in r.detail


@settings(max_examples=400, deadline=None)
@given(gaps=st.lists(st.floats(min_value=0, max_value=1), min_size=1, max_size=6),
       mrai=st.sampled_from([0.0, 5.0, 30.0]), timer=st.sampled_from([0.0, 60.0]),
       settle=st.sampled_from([0.0, 10.0, 30.0]))
def test_property_a_route_that_would_pass_never_ends_early(gaps, mrai, timer, settle):
    """The model behind the rule: in a lab whose drivers know every timer (Driver.quiescence_timer), a change only
    follows the one before it by less than the window (an advertisement interval, a timer, or the settle time): the
    boot at 0s, prefix counts that move at each gap, and the route last. Whatever the gaps, a check whose route
    arrives before its timeout must pass."""
    window = max(settle, 10.0, mrai + 2.0 if mrai else 0.0, timer + 2.0 if timer else 0.0)
    times, t = [], 0.0
    for g in gaps:
        t += g * (window - 0.01)
        times.append(t)
    arrive, changes = times[-1], times[:-1]
    if arrive >= 85:
        return
    c = Clock()
    d = Net(c, neighbors=lambda t: {"10.0.0.2": ("established", 3 + sum(t >= x for x in changes))}, adv=mrai,
            timer=timer, route=lambda t, prefix: t >= arrive)
    [r] = rr([check("route", **ROUTE)], {"r1": d}, c, Quiescence({"r1": d}, (), max(settle, 10.0)))
    assert r.passed, (r.detail, times)


# ---------------------------------------------------------- drivers: what may still change later

FRR_PLAIN = """frr version 10.4.1
!
router bgp 65001
 neighbor 10.0.12.2 remote-as 65002
 address-family ipv4 unicast
  network 192.168.1.0/24
 exit-address-family
!
"""


@pytest.mark.parametrize("extra,expected", [
    ("", 0.0),
    (" neighbor 10.0.12.2 advertise-map A exist-map B\n", 60.0),
    (" bgp conditional-advertisement timer 20\n neighbor 10.0.12.2 advertise-map A non-exist-map B\n", 20.0),
    ("router ospf\n network 10.0.0.0/8 area 0\n", None),
    ("router isis CORE\n", None),
    ("router ospf6\n", None),
    (" bgp dampening\n", None),
    (" bgp update-delay 120\n", None),
    (" bgp graceful-restart\n", None),
    (" neighbor 10.0.12.2 graceful-restart-helper\n", None),
    ("mpls ldp\n", None),
    (" bgp max-med on-startup 300\n", None),
    (" bgp graceful-restart-disable\n", 0.0),
    ("! router ospf in a comment\n", 0.0),
])
def test_frr_says_what_could_still_change_later(extra, expected):
    assert quiescence_timer_of(FRR_PLAIN.replace(" exit-address-family\n", extra + " exit-address-family\n")
                               if extra.startswith(" ") else FRR_PLAIN + extra) == expected


def test_unreadable_frr_config_means_unknown():
    with pytest.raises(DriverError):
        quiescence_timer_of("")

    class Lab:
        def exec(self, node, cmd, timeout=60, input=None):
            return ExecResult(cmd, 1, "", "vtysh: connect failed")
    assert FrrDriver(Lab(), "r1").quiescence_timer() is None


def test_other_drivers_never_claim_quiescence():
    class Lab:
        def exec(self, node, cmd, timeout=60, input=None):
            return ExecResult(cmd, 0, FRR_PLAIN, "")
    assert FrrDriver(Lab(), "r1").quiescence_timer() == 0.0
    assert SonicDriver(Lab(), "r1").quiescence_timer() is None
    assert Driver(Lab(), "r1").quiescence_timer() is None


# --------------------------------------------------------------------------- A0: phase timings

def test_a_run_reports_its_phase_timings(tmp_path, monkeypatch):
    w = World()
    lab = FakeLab(w)
    d = Net(w, route=lambda t, prefix: t >= 6 and prefix != "0.0.0.0/0")
    install(monkeypatch, w, lab, {"r1": d, "r2": Net(w), "r3": Net(w)})
    c = cfg(tmp_path, [chk("route", "r1 route", node="r1", prefix="192.168.3.0/24"),
                       chk("route", "no default", node="r1", prefix="0.0.0.0/0", present=False)])
    rep = runner.run(c)
    t = rep.timings
    assert rep.status == "passed"
    assert {"deploy", "boot", "ready", "converge", "settle", "checks", "destroy", "total", "ended_early"} <= set(t)
    assert t["settle"] == 10.0 and t["converge"] >= 9 and t["ready"] == 0.0 and t["ended_early"] == []
    assert t["total"] >= t["converge"] + t["settle"]
    assert json.loads(to_json(rep))["timings"] == t


def test_a_check_run_on_a_kept_lab_has_no_deploy_or_destroy(tmp_path, monkeypatch):
    w = World()
    lab = FakeLab(w)
    install(monkeypatch, w, lab, {"r1": Net(w, route=lambda t, prefix: True)})
    rep = runner.run(cfg(tmp_path, [chk("route", "r1 route", node="r1", prefix="192.168.3.0/24")]), deploy=False)
    assert "deploy" not in rep.timings and "destroy" not in rep.timings and "converge" in rep.timings


def test_a_run_lists_the_checks_that_ended_early(tmp_path, monkeypatch):
    w = World()
    lab = FakeLab(w, nodes=("r1",))
    install(monkeypatch, w, lab, {"r1": Net(w)})
    rep = runner.run(cfg(tmp_path, [chk("route", "r1 route", node="r1", prefix="192.168.3.0/24")]))
    assert rep.status == "failed" and rep.timings["ended_early"] == ["r1 route"]
    rep = runner.run(cfg(tmp_path, [chk("route", "r1 route", node="r1", prefix="192.168.3.0/24")]), fail_fast=False)
    assert rep.status == "failed" and rep.timings["ended_early"] == [] and rep.results[0].duration >= 120


def test_a_node_without_a_driver_keeps_every_check_waiting(tmp_path, monkeypatch):
    w = World()
    lab = FakeLab(w, nodes=("r1", "h1"))
    install(monkeypatch, w, lab, {"r1": Net(w)})   # h1: no driver (a host could run a BGP speaker)
    rep = runner.run(cfg(tmp_path, [chk("route", "r1 route", node="r1", prefix="192.168.3.0/24")]))
    assert rep.timings["ended_early"] == [] and rep.results[0].duration >= 120


def test_the_report_schema_describes_the_timings():
    schema = json.loads((ROOT / "website/docs/schemas/report-v1.json").read_text(encoding="utf-8"))
    assert "timings" in schema["properties"] and "timings" not in schema["required"]
    vschema = json.loads((ROOT / "website/docs/schemas/verify-v1.json").read_text(encoding="utf-8"))
    assert {"phases", "parallel", "rerun_before_cached"} <= set(vschema["properties"]["timings"]["properties"])


# ---------------------------------------------------------------- A3: verify boots in parallel

TOPO_TEXT = """# a comment
name: vlab
topology:
  nodes:
    r1: {kind: linux, image: quay.io/frrouting/frr:10.4.1, binds: [configs/r1.conf:/etc/frr/frr.conf]}
"""


def test_each_parallel_lab_gets_its_own_name_next_to_the_topology(tmp_path):
    topo = tmp_path / "topology.clab.yml"
    topo.write_text(TOPO_TEXT)
    a, b = vrun.unique_topology(topo, "b123456"), vrun.unique_topology(topo, "a123456")
    assert a.parent == b.parent == tmp_path and a != b
    assert vrun.Lab(a).name == "vlab-b123456" and vrun.Lab(b).name == "vlab-a123456"
    assert a.read_text().replace("vlab-b123456", "vlab") == TOPO_TEXT   # nothing else changes
    assert vrun.Lab(a).nodes["r1"].container == "clab-vlab-b123456-r1"


@pytest.mark.parametrize("text", [
    TOPO_TEXT.replace("name: vlab", "name: 'vlab'"),
    TOPO_TEXT.replace("name: vlab", "name: vlab   # the lab"),
    TOPO_TEXT + "prefix: ''\n",
    TOPO_TEXT + "mgmt:\n  network: fixed\n  ipv4-subnet: 172.100.100.0/24\n",
    TOPO_TEXT.replace("binds:", "mgmt-ipv4: 172.20.20.11, binds:"),
])
def test_a_topology_that_would_collide_boots_one_side_after_the_other(tmp_path, text):
    topo = tmp_path / "topology.clab.yml"
    topo.write_text(text)
    assert vrun.unique_topology(topo, "b123456") is None


def run_both(tmp_path, before_snap, after_snap, parallel, **kw):
    lab = make_lab(tmp_path)
    b = side_dir(tmp_path, lab, "before")
    a = side_dir(tmp_path, lab, "after", edit="! edge1 after\n")
    side = fake_side(before_snap, after_snap, raise_on=kw.pop("raise_on", None))
    res = vrun.verify(str(lab / "topology.clab.yml"), str(b), str(a), str(intent_file(tmp_path, NEW_BLOCK)),
                      side_fn=side, parallel=parallel, **kw)
    return res, side


def _snaps(case):
    good_b, good_a = base().snap(), add_new_customer_block(base()).snap()
    return {
        "matched": (good_b, good_a, {}),
        "no change declared": (good_b, good_b, {}),
        "inconclusive before": (Inconclusive("never settled", ["x"]), good_a, {}),
        "inconclusive after": (good_b, Inconclusive("never settled", ["x"]), {}),
        "before errors": (good_b, good_a, {"raise_on": "before"}),
        "after errors": (good_b, good_a, {"raise_on": "after"}),
        "rerun before errors": (good_b, good_a, {"raise_on": "rerun-before"}),
    }[case]


@pytest.mark.parametrize("case", ["matched", "no change declared", "inconclusive before", "inconclusive after",
                                  "before errors", "after errors", "rerun before errors"])
def test_parallel_boots_give_the_verdict_of_serial_boots(tmp_path, case):
    b, a, kw = _snaps(case)
    serial, s_side = run_both(tmp_path / "s", b, a, parallel=False, **kw)
    par, p_side = run_both(tmp_path / "p", b, a, parallel=True, **kw)
    assert (par.status, par.error, par.exit_code) == (serial.status, serial.error, serial.exit_code), case
    assert par.timings["parallel"] is True and serial.timings["parallel"] is False
    assert {lb for lb, _ in s_side.calls} <= {lb for lb, _ in p_side.calls}


def test_parallel_sides_boot_under_different_lab_names(tmp_path):
    seen = []
    good_b, good_a = base().snap(), add_new_customer_block(base()).snap()
    inner = fake_side(good_b, good_a)

    def side(label, topology, on_up=None):
        seen.append((label, vrun.Lab(Path(topology)).name))
        return inner(label, topology, on_up)
    lab = make_lab(tmp_path)
    res = vrun.verify(str(lab / "topology.clab.yml"), str(side_dir(tmp_path, lab, "before")),
                      str(side_dir(tmp_path, lab, "after", edit="! edge1 after\n")),
                      str(intent_file(tmp_path, NEW_BLOCK)), side_fn=side, parallel=True)
    assert res.status == "matched"
    names = dict(seen)
    assert set(names) == {"before", "after", "rerun-before", "rerun-after"}
    assert len(set(names.values())) == 4 and all(n.startswith("vlab-") for n in names.values())


def test_a_rerun_that_differs_is_inconclusive_in_parallel_too(tmp_path):
    good_b, good_a = base().snap(), add_new_customer_block(base()).snap()
    other = add_new_customer_block(base(), nodes=("edge1",)).snap()
    calls = {"n": 0}

    def side(label, topology, on_up=None):
        calls["n"] += 1
        return {"before": good_b, "after": good_a, "rerun-before": good_b, "rerun-after": other}[label], 1.0, None
    lab = make_lab(tmp_path)
    for parallel in (False, True):
        res = vrun.verify(str(lab / "topology.clab.yml"), str(side_dir(tmp_path / str(parallel), lab, "before")),
                          str(side_dir(tmp_path / str(parallel), lab, "after", edit="! edge1 after\n")),
                          str(intent_file(tmp_path, NEW_BLOCK)), side_fn=side, parallel=parallel)
        assert res.status == "inconclusive" and res.determinism["identical"] is False


def test_the_cached_base_snapshot_stands_for_the_before_rerun_only(tmp_path, monkeypatch):
    monkeypatch.setenv("NETDRYRUN_CACHE", str(tmp_path / "cache"))
    monkeypatch.setattr(vrun, "base_snapshot_key", lambda *a, **k: "k" * 64)
    good_b, good_a = base().snap(), add_new_customer_block(base()).snap()
    first, side1 = run_both(tmp_path / "1", good_b, good_a, parallel=False, reuse_base_snapshot=True)
    assert first.status == "matched" and [lb for lb, _ in side1.calls].count("rerun-before") == 1
    assert (tmp_path / "cache" / "snapshots" / ("k" * 64 + ".json")).is_file()
    second, side2 = run_both(tmp_path / "2", good_b, good_a, parallel=False, reuse_base_snapshot=True)
    labels = [lb for lb, _ in side2.calls]
    assert second.status == "matched" and "rerun-before" not in labels and labels.count("before") == 1
    assert "rerun-after" in labels   # the after side is still booted twice
    assert second.determinism["before_from_cache"] == "k" * 64 and second.timings["rerun_before_cached"] is True


def test_a_cached_base_that_differs_is_not_deterministic(tmp_path, monkeypatch):
    monkeypatch.setenv("NETDRYRUN_CACHE", str(tmp_path / "cache"))
    monkeypatch.setattr(vrun, "base_snapshot_key", lambda *a, **k: "c" * 64)
    vrun.save_cached_snapshot("c" * 64, add_new_customer_block(base(), nodes=("edge1",)).snap())
    res, _ = run_both(tmp_path, base().snap(), add_new_customer_block(base()).snap(), parallel=True,
                      reuse_base_snapshot=True)
    assert res.status == "inconclusive" and res.determinism["identical"] is False


def test_no_cache_key_without_every_image_digest(tmp_path):
    lab_dir = make_lab(tmp_path)
    side = vrun.materialize(str(side_dir(tmp_path, lab_dir, "before")), "before", lab_dir / "topology.clab.yml",
                            tmp_path / "work")
    lab = vrun.Lab(lab_dir / "topology.clab.yml")
    lab.image_digest = lambda image: None
    lab.version = lambda: "0.81.1"
    assert vrun.base_snapshot_key(side, lab, {"edge1": "frr"}, {}, 15.0) is None
    lab.image_digest = lambda image: "quay.io/frrouting/frr@sha256:" + "0" * 64
    k1 = vrun.base_snapshot_key(side, lab, {"edge1": "frr"}, {}, 15.0)
    assert k1 and k1 != vrun.base_snapshot_key(side, lab, {"edge1": "frr"}, {}, 20.0)
    assert k1 != vrun.base_snapshot_key(side, lab, {"edge1": "frr"}, {"edge1": ["ip link"]}, 15.0)
    lab.version = lambda: "unknown"
    assert vrun.base_snapshot_key(side, lab, {"edge1": "frr"}, {}, 15.0) is None


def test_in_parallel_hands_back_values_and_errors_in_order():
    out = vrun.in_parallel([lambda: 1, lambda: (_ for _ in ()).throw(ValueError("x")), lambda: 3])
    assert out[0] == (True, 1) and out[2] == (True, 3) and out[1][0] is False and isinstance(out[1][1], ValueError)


def test_collect_reads_nodes_at_once_and_raises_the_first_error_in_order(monkeypatch):
    calls = []

    class Collector:
        def __init__(self, n, exec_fn, owners):
            self.n = n

        def collect(self):
            calls.append(self.n)
            if self.n in ("r2", "r3"):
                raise vrun.SnapshotError(f"bad {self.n}")
            return self.n
    monkeypatch.setattr(vrun, "FrrCollector", Collector)
    lab = vrun.Lab.__new__(vrun.Lab)
    lab.nodes = {n: Node(n, f"c-{n}", "linux", "frr") for n in ("r1", "r2", "r3")}
    lab.exec = lambda node, argv, timeout=60: ExecResult(argv, 1, "", "")
    with pytest.raises(vrun.SnapshotError, match="bad r2"):
        vrun.collect(lab, {"r1": "frr", "r2": "frr", "r3": "frr"})
    assert sorted(calls) == ["r1", "r2", "r3"]


# ------------------------------------------------------------------------- Junos: one SSH connection

class JLab:
    def __init__(self, rc=0):
        self.argv, self.detached, self.rc = [], [], rc

    def exec(self, node, cmd, timeout=60, input=None):
        self.argv.append(cmd)
        return ExecResult(cmd, self.rc, '{"route-instance-information": []}', "" if self.rc == 0 else "refused")

    def exec_detached(self, node, cmd, timeout=15):
        self.detached.append(cmd)
        return ExecResult(cmd, 0, "", "")


def test_junos_commands_share_one_ssh_connection_once_the_vm_answers():
    lab = JLab()
    d = JunosDriver(lab, "j1")
    for _ in range(3):
        d._cli("show route instance master", [])
    assert all(a[:2] == ["ssh", "-q"] and a[-2] == "root@176.1.1.1" for a in lab.argv)
    assert all(" ".join(MUX_OPTS) in " ".join(a) and "ControlMaster=no" in a for a in lab.argv)
    assert len(lab.detached) == 1 and "ControlMaster=yes" in lab.detached[0][-1] and "-O check" in lab.detached[0][-1]


def test_junos_starts_no_connection_while_the_vm_does_not_answer():
    lab = JLab(rc=255)
    with pytest.raises(DriverError):
        JunosDriver(lab, "j1")._cli("show route instance master", [])
    assert lab.detached == []


def test_junos_without_a_shared_connection_still_answers():
    class NoDetach(JLab):
        def exec_detached(self, node, cmd, timeout=15):
            raise OSError("docker exec -d is not available")
    assert JunosDriver(NoDetach(), "j1")._cli("show route instance master", [])


# ------------------------------------------------------------------------------- the Action

ACTION = (ROOT / "action.yml").read_text(encoding="utf-8")


def test_the_action_pulls_images_in_the_background_and_waits_before_the_run():
    pull, wait, run = (ACTION.index(s) for s in ("name: Start pulling the lab's images", "name: Wait for the image pulls",
                                                 "name: Run Netdryrun"))
    assert pull < ACTION.index("name: Install containerlab") < wait < run
    assert "nohup docker pull" in ACTION and "kill -0" in ACTION


def test_the_action_caches_a_checked_containerlab_package():
    assert re.search(r"uses: actions/cache@[0-9a-f]{40}\s+# v\d", ACTION)
    assert "sha256sum --check" in ACTION and "checksums.txt" in ACTION
    assert ACTION.index("sha256sum --check") < ACTION.index('sudo dpkg -i "$dir/$pkg"')


def test_the_action_skips_destroy_only_on_a_hosted_runner_when_asked():
    assert re.search(r'skip-destroy:\n    description: .*\n    default: "false"', ACTION)
    assert ('if [ "$NDR_SKIP_DESTROY" = true ] && [ "${RUNNER_ENVIRONMENT:-}" = github-hosted ]; then\n'
            '              keep=(--keep)') in ACTION
    verify = ACTION[ACTION.index("          verify)"):ACTION.index("          *)")]
    assert "--keep" not in verify   # verify keeps its own rules
