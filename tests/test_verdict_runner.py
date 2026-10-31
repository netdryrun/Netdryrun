"""Runner verdict logic: run(), run_scenario(), the post-convergence BGP gate and the fault-visibility wait.

A whole run is driven on a fake clock, against a fake lab and VRF-aware fake drivers whose state is a
function of time. The checks module is NOT wrapped, so the clock and sleep the runner passes down are the
ones that are used. Each test asserts a status, a verdict, which checks ran, what the lab was asked to do
or how long the run waited, never a message text.
"""
from __future__ import annotations

import ipaddress
import signal
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

import pytest

from netdryrun import runner
from netdryrun.checks import Result
from netdryrun.config import Check, Config, Fault, Scenario
from netdryrun.drivers.base import BgpNeighbor, BgpPath, DriverError, NoSuchInstance, Observation, Route
from netdryrun.lab import ExecResult, Lab, LabError, Node


# ----------------------------------------------------------------------------------------------- fakes

class Clock:
    def __init__(self, start=1000.0):
        self.start = self.t = start
        self.sleeps: list[float] = []

    def __call__(self):
        return self.t

    def sleep(self, s):
        assert s >= 0
        self.sleeps.append(s)
        self.t += s
        assert len(self.sleeps) < 5000, "a wait that never ends"

    @property
    def now(self):
        return self.t - self.start


class FakeLab:
    def __init__(self, clock, nodes=("r1", "r2", "r3"), kinds=None, existing=(), running=None, destroy_rc=0,
                 destroy_error=None, deploy_error=None, addresses=None, links=None, set_link_error=None):
        self.clock, self.name, self.topology = clock, "t", Path("t.clab.yml")
        kinds = kinds or {}
        self.nodes = {n: Node(n, f"clab-t-{n}", *kinds.get(n, ("linux", "quay.io/frrouting/frr:10.4.1")))
                      for n in nodes}
        self.links = links if links is not None else [(("r1", "eth1"), ("r2", "eth1")), (("r2", "eth2"), ("r3", "eth1"))]
        self.existing, self.running = set(existing), running
        self.destroy_rc, self.destroy_error, self.deploy_error = destroy_rc, destroy_error, deploy_error
        self.addresses = addresses if addresses is not None else {("r1", "eth1"): ["10.0.12.1/30"],
                                                                  ("r2", "eth1"): ["10.0.12.2/30"]}
        self.set_link_error = set_link_error or {}
        self.events: list[tuple] = []
        self.deployed = self.destroyed = 0
        self.locked = False
        self.active_during_checks = None

    def check_tools(self):
        pass

    def version(self):
        return "test"

    def acquire_lock(self):
        self.locked = True
        self.events.append(("lock",))

    def release_lock(self):
        self.locked = False
        self.events.append(("unlock",))

    def existing_containers(self):
        return self.existing

    def image_digest(self, image):
        return {"quay.io/frrouting/frr:10.4.1": "quay.io/frrouting/frr@sha256:" + "a" * 64}.get(image)

    def deploy(self):
        self.deployed += 1
        self.events.append(("deploy",))
        if self.deploy_error:
            raise self.deploy_error
        return ExecResult([], 0, "", "")

    def destroy(self):
        self.destroyed += 1
        self.events.append(("destroy",))
        if self.destroy_error:
            raise self.destroy_error
        return ExecResult([], self.destroy_rc, "", "boom" if self.destroy_rc else "")

    def running_containers(self):
        if self.running is not None:
            return set(self.running)
        return {n.container for n in self.nodes.values()}

    def boot_log(self, node):   # a clean FRR boot: every config line loaded
        return ExecResult([], 0, "[45|bgpd] done", "")

    def run_setup(self, node, cmds, log=None):
        self.events.append(("setup", node, tuple(cmds), log is not None))

    def _require_linux_links(self, node):
        self.events.append(("require", node))

    def data_interfaces(self, node):
        return {"r1": ["eth1", "eth2"]}.get(node, ["eth1"])

    def set_link(self, node, iface, up):
        self.events.append(("link", node, iface, up, self.clock.now))
        err = self.set_link_error.get((node, iface, up))
        if err:
            raise err
        return ExecResult([], 0, "", "")

    def interface_addresses(self, node, iface):
        return [ipaddress.ip_interface(a) for a in self.addresses.get((node, iface), [])]

    def peers_of(self, node, iface):
        return Lab.peers_of(self, node, iface)

    def link_events(self):
        return [e[1:4] for e in self.events if e[0] == "link"]


def _at(v, t):
    return v(t) if callable(v) else v


class Drv:
    """neighbors: {vrf: value or fn(t)} where value is {addr: state or (state, {afi: n})};
    routes: {vrf: fn(t, prefix) -> bool (present and active)};
    paths: {vrf: fn(t, prefix) -> list[BgpPath]}. A VRF not listed is an error (for neighbors, the
    device saying it has no such VRF)."""

    def __init__(self, clock, neighbors=None, routes=None, ping=None, neighbors_error=None, on_call=None, paths=None):
        self.clock, self.neighbors, self.routes_ = clock, neighbors or {}, routes or {}
        self.paths_ = paths or {}
        self.ping_, self.neighbors_error, self.on_call = ping, neighbors_error, on_call
        self.calls: list[tuple] = []
        self.name = "frr"

    def nos_version(self):
        return "FRRouting 10.4.1_git"

    def bgp_neighbors(self, vrf="default"):
        self.calls.append(("bgp_neighbors", vrf, self.clock.now))
        if self.on_call:
            self.on_call()
        err = _at(self.neighbors_error, self.clock.now)
        if err:
            raise err
        if vrf not in self.neighbors:
            raise NoSuchInstance(f"no VRF {vrf}")
        out = {}
        for a, s in _at(self.neighbors[vrf], self.clock.now).items():
            state, pfx, interval = (s, {"ipv4-unicast": 3}, 0.0) if isinstance(s, str) else (*s, 0.0)[:3]
            out[a] = BgpNeighbor(a, state, dict(pfx), adv_interval=interval)
        return Observation(out, [{"cmd": "nbr"}])

    def routes(self, prefix, vrf="default"):
        self.calls.append(("routes", prefix, vrf, self.clock.now))
        if self.on_call:
            self.on_call()
        if vrf not in self.routes_:
            raise DriverError(f"no VRF {vrf}")
        present = self.routes_[vrf](self.clock.now, prefix)
        return Observation([Route(prefix, "bgp", True)] if present else [], [{"cmd": "rt"}])

    def bgp_paths(self, prefix, vrf="default"):
        self.calls.append(("bgp_paths", prefix, vrf, self.clock.now))
        if vrf not in self.paths_:
            raise DriverError(f"no VRF {vrf}")
        return Observation(self.paths_[vrf](self.clock.now, prefix), [{"cmd": "bgp"}])

    def ping(self, target, source, count, vrf="default"):
        self.calls.append(("ping", target, vrf, self.clock.now))
        return self.ping_(self.clock.now)


def always(t, p):
    return True


def never(t, p):
    return False


def up(*addrs):
    return {"default": {a: "established" for a in addrs}}


class Env:
    def __init__(self, monkeypatch, clock, lab, drivers):
        self.clock, self.lab, self.drivers = clock, lab, drivers
        self.for_node_calls: list[tuple] = []
        self.supported_calls: list[tuple] = []
        self.injections: list = []
        self.logs: list[str] = []
        self.results: list[Result] = []
        monkeypatch.setattr(runner, "_clock", clock)
        monkeypatch.setattr(runner, "_sleep", clock.sleep)
        monkeypatch.setattr(runner, "Lab", lambda path: lab)

        def for_node(lab_, node, override=None):
            assert lab_ is lab
            self.for_node_calls.append((node, override))
            return drivers[node]

        monkeypatch.setattr(runner, "for_node", for_node)

        def check_supported(lab_, c, override=None):
            assert lab_ is lab
            self.supported_calls.append((c.name, override))

        monkeypatch.setattr(runner, "check_supported", check_supported)
        env = self

        class Injection:
            def __init__(self, lab_, node, prefixes, as_path):
                assert lab_ is lab
                self.node, self.prefixes, self.as_path, self.applied, self.restored = node, prefixes, as_path, False, 0
                env.injections.append(self)

            def describe(self):
                return f"{self.node}"

            def apply(self):
                self.applied = True
                env.lab.events.append(("inject", self.node, self.clock_now()))

            def restore(self):
                self.restored += 1
                env.lab.events.append(("uninject", self.node))

            def clock_now(self):
                return env.clock.now

        monkeypatch.setattr(runner, "RouteInjection", Injection)

    def run(self, checks, scenarios=(), drivers_cfg=None, setup=None, **kw):
        cfg = Config(path=Path("netdryrun.yml"), lab=Path("t.clab.yml"), timeout=120, checks=list(checks),
                     drivers=drivers_cfg or {}, scenarios=list(scenarios), setup=setup or {})
        kw.setdefault("deploy", False)
        return runner.run(cfg, on_result=self.results.append, log=self.logs.append, **kw)


def chk(ctype, name, node="r1", timeout=30, hold=None, **params):
    return Check(type=ctype, params={"node": node, **params}, name=name, timeout=timeout, hold=hold)


def route(name, node="r1", prefix="10.9.9.0/24", **kw):
    return chk("route", name, node=node, prefix=prefix, **kw)


def leak(name, node="r1", prefix="10.66.0.0/16", **kw):
    return chk("route", name, node=node, prefix=prefix, present=False, **kw)


def by_name(rep):
    return {r.check.name: r for r in rep.results}


def iso(s):
    return isinstance(s, str) and datetime.fromisoformat(s).utcoffset().total_seconds() == 0


def make(monkeypatch, nodes=("r1", "r2", "r3"), **drivers_kw):
    clock = Clock()
    lab = FakeLab(clock, nodes=nodes)
    drivers = {n: Drv(clock, **drivers_kw.get(n, {"neighbors": up(), "routes": {"default": always}})) for n in nodes}
    return Env(monkeypatch, clock, lab, drivers)


# ----------------------------------------------------------------------------------------------- run(): phases

def test_negative_checks_run_after_convergence_and_hold(monkeypatch):
    """A leak arriving during the hold window fails; a positive check is never held."""
    e = make(monkeypatch, r1={"neighbors": up("10.0.12.2"),
                              "routes": {"default": lambda t, p: p == "10.9.9.0/24" or t >= 20}})
    pos, neg = route("pos"), leak("neg")
    rep = e.run([neg, pos], settle=10, hold=10)
    assert rep.status == "failed"
    assert by_name(rep)["pos"].passed and not by_name(rep)["neg"].passed
    assert [r.check.name for r in rep.results] == ["neg", "pos"]          # the user's order
    assert sorted(r.check.name for r in e.results) == ["neg", "pos"]      # each reported once
    assert e.results[0].check is pos                                      # positives finish first
    assert iso(rep.started) and iso(rep.finished)


def test_post_convergence_check_is_not_judged_on_two_early_samples(monkeypatch):
    e = make(monkeypatch, r1={"neighbors": up("10.0.12.2"), "routes": {"default": lambda t, p: t >= 8}})
    rep = e.run([leak("neg")], settle=10, hold=10)
    assert rep.status == "failed"


def test_positive_check_passes_on_two_samples_and_is_not_held(monkeypatch):
    e = make(monkeypatch, r1={"neighbors": up(), "routes": {"default": lambda t, p: t < 5}})
    rep = e.run([route("pos")], settle=10, hold=10)
    assert rep.status == "passed" and e.clock.now == 3.0


def test_settle_waits_at_least_30s_when_nothing_proved_convergence(monkeypatch):
    e = make(monkeypatch, r1={"neighbors": up("10.0.12.2"), "routes": {"default": never}})
    rep = e.run([leak("neg")], settle=10, hold=10)
    assert rep.status == "passed" and 30.0 in e.clock.sleeps and 10.0 not in e.clock.sleeps[:3]
    e = make(monkeypatch, r1={"neighbors": up("10.0.12.2"), "routes": {"default": lambda t, p: p == "10.9.9.0/24"}})
    rep = e.run([leak("neg"), route("pos")], settle=10, hold=10)
    assert rep.status == "passed" and 10.0 in e.clock.sleeps and 30.0 not in e.clock.sleeps
    e = make(monkeypatch, r1={"neighbors": up("10.0.12.2"), "routes": {"default": never}})
    e.run([leak("neg")], settle=45, hold=10)
    assert 45.0 in e.clock.sleeps


def test_run_defaults_settle_and_hold_10s(monkeypatch):
    e = make(monkeypatch, r1={"neighbors": up(), "routes": {"default": lambda t, p: p == "10.9.9.0/24"}})
    cfg = Config(path=Path("x"), lab=Path("t"), timeout=120, checks=[route("pos"), leak("neg")])
    rep = runner.run(cfg, deploy=False)
    assert rep.status == "passed"
    assert e.clock.sleeps.count(10.0) == 1
    assert by_name(rep)["neg"].duration == 10.0


def test_hold_is_passed_to_the_post_convergence_checks(monkeypatch):
    # the leak arrives 15 s into the hold: caught with hold=20, not with the default 10
    def routes(start):
        return {"default": lambda t, p: p == "10.9.9.0/24" or t >= start}

    e = make(monkeypatch, r1={"neighbors": up("10.0.12.2"), "routes": routes(3 + 10 + 15)})
    assert e.run([route("pos"), leak("neg")], settle=10, hold=20).status == "failed"
    e = make(monkeypatch, r1={"neighbors": up("10.0.12.2"), "routes": routes(3 + 10 + 15)})
    assert e.run([route("pos"), leak("neg")], settle=10, hold=10).status == "passed"


def test_checks_wait_on_the_runner_clock(monkeypatch):
    """Durations come from the runner's clock (the one tests and the CLI share), for every phase."""
    e = make(monkeypatch, r1={"neighbors": up("10.0.12.2"), "routes": {"default": lambda t, p: p == "10.9.9.0/24" and t >= 6}})
    rep = e.run([route("pos"), leak("neg")], settle=10, hold=10)
    assert by_name(rep)["pos"].duration == 9.0 and by_name(rep)["neg"].duration == 10.0
    assert e.clock.now == 9 + 3 + 10 + 10   # positives, the gate's second sample, settle, hold


def test_bgp_route_attribute_is_not_judged_on_a_temporary_best_path(monkeypatch):
    """A best path via the first session up is replaced once a slower session (preferred) comes up at t=20:
    next_hop must not pass on the early path; it is judged after the BGP gate, the settle and the hold."""
    def paths(t, p):
        return [BgpPath(True, "65002 65009", "10.0.12.2" if t < 20 else "10.0.13.3", 100, 0)]

    def nbrs(t):
        return {"10.0.12.2": "established", "10.0.13.3": "established" if t >= 20 else "active"}

    e = make(monkeypatch, r1={"neighbors": {"default": nbrs}, "paths": {"default": paths}})
    rep = e.run([chk("bgp_route", "nh", prefix="10.9.0.0/16", next_hop="10.0.12.2")], settle=10, hold=10)
    assert rep.status == "failed"
    # the same check holds on the final best path
    e = make(monkeypatch, r1={"neighbors": {"default": nbrs}, "paths": {"default": paths}})
    rep = e.run([chk("bgp_route", "nh", prefix="10.9.0.0/16", next_hop="10.0.13.3")], settle=10, hold=10)
    assert rep.status == "passed" and by_name(rep)["nh"].attempts > 2
    assert min(c[3] for c in e.drivers["r1"].calls if c[0] == "bgp_paths") >= 20


def test_not_converged_checks_are_reported_once_and_not_held(monkeypatch):
    e = make(monkeypatch, r1={"neighbors": up("10.0.12.2"), "routes": {"default": always}},
             r3={"neighbors": {"default": {"10.0.23.2": "active"}}, "routes": {"default": never}})
    checks = [chk("bgp_session", "s", neighbor="10.0.12.2", state="established"),
              leak("neg", node="r3", timeout=12), leak("neg2", node="r1", prefix="10.77.0.0/16")]
    e.drivers["r1"].routes_ = {"default": lambda t, p: p != "10.77.0.0/16"}
    rep = e.run(checks, settle=10, hold=10)
    names = [r.check.name for r in rep.results]
    assert names == ["s", "neg", "neg2"] and len(e.results) == 3
    r = by_name(rep)["neg"]
    assert r.passed is False and not any(c[0] == "routes" for c in e.drivers["r3"].calls)
    assert by_name(rep)["neg2"].passed and rep.status == "failed"
    assert all(isinstance(x, Result) for x in e.results)
    assert sorted(x.check.name for x in e.results) == ["neg", "neg2", "s"]


def test_gate_uses_positive_results_to_skip_dead_nodes(monkeypatch):
    """A node whose positive checks never got usable state already waited out their timeout: no second wait."""
    e = make(monkeypatch, r1={"neighbors_error": DriverError("bgpd down"), "routes": {"default": never}})
    checks = [chk("bgp_session", "s", neighbor="10.0.12.2", timeout=9), leak("neg", timeout=60)]
    rep = e.run(checks, settle=10, hold=10)
    assert rep.status == "inconclusive"
    assert e.clock.now == 9 + 10 + 10   # session timeout, settle, hold: the gate did not wait 60 s


def test_gate_warning_when_a_node_never_answers(monkeypatch):
    e = make(monkeypatch, r1={"neighbors": up(), "routes": {"default": lambda t, p: p == "10.9.9.0/24"}},
             r3={"neighbors_error": DriverError("no bgpd"), "routes": {"default": never}})
    rep = e.run([route("pos"), leak("neg", node="r3", timeout=9)], settle=10, hold=10)
    assert rep.status == "passed" and len(e.logs) == 2


def test_node_without_bgp_neighbors_yet_is_not_converged(monkeypatch):
    """r1's BGP config is applied only at t=40 (until then it reports no neighbors at all), and the leak
    arrives over the new session at t=50. Only post-convergence checks: the gate must keep waiting."""
    e = make(monkeypatch, r1={"neighbors": {"default": lambda t: {"10.0.12.2": "established"} if t >= 40 else {}},
                              "routes": {"default": lambda t, p: t >= 50}})
    rep = e.run([leak("neg", timeout=60)], settle=10, hold=10)
    assert rep.status == "failed"


def test_node_that_never_reports_bgp_neighbors_is_released_at_the_cap_with_a_warning(monkeypatch):
    e = make(monkeypatch, r1={"neighbors": up(), "routes": {"default": never}})
    rep = e.run([leak("neg", timeout=24), leak("neg2", prefix="10.77.0.0/16", timeout=12)], settle=10, hold=10)
    assert rep.status == "passed"                      # the verdict is unchanged
    assert e.clock.now == 24 + 30 + 10                 # waited the cap, then the settle and the hold
    plain = make(monkeypatch, r1={"neighbors": up("10.0.12.2"), "routes": {"default": never}})
    ref = plain.run([leak("neg", timeout=24), leak("neg2", prefix="10.77.0.0/16", timeout=12)], settle=10, hold=10)
    for name in ("neg", "neg2"):                       # the warning is recorded on each gated check
        assert by_name(rep)[name].detail != by_name(ref)[name].detail
        assert by_name(rep)[name].detail.startswith(by_name(ref)[name].detail)   # the check's own detail is kept
    assert len(e.logs) == len(plain.logs) + 1


def test_results_of_every_phase_are_kept(monkeypatch):
    e = make(monkeypatch, r1={"neighbors": up(), "routes": {"default": lambda t, p: p == "10.9.9.0/24"}})
    rep = e.run([route("a"), leak("b"), route("c", prefix="10.8.0.0/16")], settle=10, hold=10)
    assert [r.check.name for r in rep.results] == ["a", "b", "c"]
    assert [r.passed for r in rep.results] == [True, True, False]


def test_report_started(monkeypatch):
    e = make(monkeypatch)
    rep = e.run([route("a")])
    assert iso(rep.started) and rep.lab_name == "t"
    assert rep.environment["nodes"]["r1"] == {"kind": "linux", "image": "quay.io/frrouting/frr:10.4.1",
                                              "config_load": "clean", "nos_version": "FRRouting 10.4.1_git",
                                              "image_digest": "quay.io/frrouting/frr@sha256:" + "a" * 64}
    assert set(rep.environment) == {"netdryrun", "containerlab", "python", "host", "nodes"}


# ----------------------------------------------------------------------------------------------- run(): setup

def test_drivers_get_the_configured_override(monkeypatch):
    e = make(monkeypatch)
    sc = Scenario("s", [Fault("link_down", "r1", "eth9")], [route("[s] x", node="r3")])
    e.run([route("a"), route("b", node="r2")], [sc], drivers_cfg={"r2": "srlinux"})
    assert ("r2", "srlinux") in e.for_node_calls and ("r1", None) in e.for_node_calls
    assert ("r3", None) in e.for_node_calls
    assert all(o == "srlinux" for n, o in e.for_node_calls if n == "r2")
    assert e.supported_calls == [("a", None), ("b", "srlinux"), ("[s] x", None)]


@pytest.mark.parametrize("what", ["check", "scenario_check", "fault", "setup"])
def test_unknown_nodes_are_an_error_before_deploying(monkeypatch, what):
    e = make(monkeypatch)
    checks, scenarios, setup = [route("a")], [], {}
    if what == "check":
        checks = [route("a", node="r9")]
    elif what == "scenario_check":
        scenarios = [Scenario("s", [Fault("link_down", "r1", "eth1")], [route("x", node="r9")])]
    elif what == "fault":
        scenarios = [Scenario("s", [Fault("link_down", "r9", "eth1")], [route("x")])]
    else:
        setup = {"r9": ["true"]}
    rep = e.run(checks, scenarios, setup=setup, deploy=True)
    assert rep.status == "error" and e.lab.deployed == 0 and e.lab.destroyed == 0


def test_inject_routes_needs_an_frr_node(monkeypatch):
    clock = Clock()
    lab = FakeLab(clock, kinds={"r2": ("nokia_srlinux", "srl")})
    e = Env(monkeypatch, clock, lab, {n: Drv(clock, neighbors=up(), routes={"default": always}) for n in lab.nodes})
    sc = Scenario("s", [Fault("inject_routes", "r2", prefixes=["10.66.0.0/16"])], [route("x")])
    assert e.run([route("a")], [sc]).status == "error" and not e.injections
    # an frr override on that node makes it acceptable
    e = Env(monkeypatch, clock, lab, e.drivers)
    assert e.run([route("a")], [sc], drivers_cfg={"r2": "frr"}).status == "passed" and e.injections
    # and an override to another driver refuses an FRR image
    lab2 = FakeLab(clock)
    e = Env(monkeypatch, clock, lab2, {n: Drv(clock, neighbors=up(), routes={"default": always}) for n in lab2.nodes})
    sc = Scenario("s", [Fault("inject_routes", "r1", prefixes=["10.66.0.0/16"])], [route("x")])
    assert e.run([route("a")], [sc], drivers_cfg={"r1": "eos"}).status == "error"


def _cfg(checks, scenarios=(), drivers=None):
    return Config(path=Path("netdryrun.yml"), lab=Path("t.clab.yml"), timeout=120, checks=list(checks),
                  drivers=drivers or {}, scenarios=list(scenarios), setup={})


def test_preflight_only_detects_drivers_when_full():
    """run() finds a node without a driver after deploying; only validate (full=True) refuses it before."""
    lab = FakeLab(Clock(), kinds={"r3": ("linux", "alpine:3")})
    cfg = _cfg([route("a", node="r3")])
    runner.preflight(cfg, lab)
    with pytest.raises(DriverError):
        runner.preflight(cfg, lab, full=True)
    runner.preflight(_cfg([route("a", node="r3")], drivers={"r3": "frr"}), lab, full=True)
    assert not any(ev[0] == "require" for ev in lab.events)


def test_preflight_full_checks_link_faults_only():
    lab = FakeLab(Clock())
    sc = Scenario("s", [Fault("inject_routes", "r1", prefixes=["10.66.0.0/16"]), Fault("link_down", "r2", "eth1"),
                        Fault("node_isolated", "r3")], [route("x")])
    runner.preflight(_cfg([route("a")], [sc]), lab)
    assert lab.events == []
    runner.preflight(_cfg([route("a")], [sc]), lab, full=True)
    assert lab.events == [("require", "r2"), ("require", "r3")]


def test_deploy_setup_and_destroy(monkeypatch):
    e = make(monkeypatch)
    seen = {}
    e.drivers["r1"].on_call = lambda: seen.setdefault("active", e.lab in runner._ACTIVE)
    rep = e.run([route("a")], setup={"r2": ["echo 1", "echo 2"]}, deploy=True)
    assert rep.status == "passed" and e.lab.deployed == 1 and e.lab.destroyed == 1
    assert ("setup", "r2", ("echo 1", "echo 2"), True) in e.lab.events
    assert seen["active"] is True and e.lab not in runner._ACTIVE
    assert e.lab.events[0] == ("lock",) and e.lab.events[-1] == ("unlock",)


def test_no_deploy_means_no_setup_and_no_destroy(monkeypatch):
    e = make(monkeypatch)
    rep = e.run([route("a")], setup={"r2": ["echo 1"]}, deploy=False)
    assert rep.status == "passed" and e.lab.deployed == 0 and e.lab.destroyed == 0
    assert not any(ev[0] == "setup" for ev in e.lab.events) and not any(ev[0] == "lock" for ev in e.lab.events)


def test_keep_leaves_the_lab_and_never_registers_it(monkeypatch):
    e = make(monkeypatch)
    seen = {}
    e.drivers["r1"].on_call = lambda: seen.setdefault("active", e.lab in runner._ACTIVE)
    rep = e.run([route("a")], deploy=True, keep=True)
    assert rep.status == "passed" and e.lab.destroyed == 0 and seen["active"] is False and not e.lab.locked


@pytest.mark.parametrize("ok,destroyed", [(True, 1), (False, 0)])
def test_keep_on_failure(monkeypatch, ok, destroyed):
    e = make(monkeypatch, r1={"neighbors": up(), "routes": {"default": always if ok else never}})
    rep = e.run([route("a", timeout=6)], deploy=True, keep_on_failure=True)
    assert rep.status == ("passed" if ok else "failed") and e.lab.destroyed == destroyed
    assert e.lab not in runner._ACTIVE


def test_keep_on_failure_does_not_apply_to_an_interrupted_run(monkeypatch):
    e = make(monkeypatch)

    def interrupt():
        raise KeyboardInterrupt

    e.drivers["r1"].on_call = interrupt
    with pytest.raises(KeyboardInterrupt) as exc:
        e.run([route("a")], deploy=True, keep_on_failure=True)
    rep = exc.value.report
    assert rep.status == "error" and rep.error and e.lab.destroyed == 1 and rep.finished


def test_interrupted_by_sigterm(monkeypatch):
    e = make(monkeypatch)

    def interrupt():
        raise runner.Interrupted(signal.SIGTERM)

    e.drivers["r1"].on_call = interrupt
    with pytest.raises(runner.Interrupted) as exc:
        e.run([route("a")], deploy=True)
    assert exc.value.report.status == "error" and exc.value.signum == signal.SIGTERM and e.lab.destroyed == 1


def test_signal_during_cleanup_is_raised_after_it(monkeypatch):
    e = make(monkeypatch)

    @contextmanager
    def deferred():
        yield [signal.SIGTERM, signal.SIGINT]

    monkeypatch.setattr(runner, "_signals_deferred", deferred)
    with pytest.raises(runner.Interrupted) as exc:
        e.run([route("a")], deploy=True)
    assert exc.value.signum == signal.SIGTERM and e.lab.destroyed == 1
    rep = exc.value.report
    assert rep.status == "error" and rep.error and rep.results[0].passed


def test_signal_during_cleanup_keeps_an_earlier_error(monkeypatch):
    e = make(monkeypatch)
    e.lab.existing = {"clab-t-r1"}

    @contextmanager
    def deferred():
        yield [signal.SIGHUP]

    monkeypatch.setattr(runner, "_signals_deferred", deferred)
    with pytest.raises(runner.Interrupted) as exc:
        e.run([route("a")], deploy=True)
    assert exc.value.report.error and exc.value.signum == signal.SIGHUP


def test_no_signal_during_cleanup_after_an_interrupt(monkeypatch):
    """The run was already interrupted: a signal recorded during cleanup doesn't replace it."""
    e = make(monkeypatch)

    def interrupt():
        raise runner.Interrupted(signal.SIGINT)

    e.drivers["r1"].on_call = interrupt

    @contextmanager
    def deferred():
        yield [signal.SIGTERM]

    monkeypatch.setattr(runner, "_signals_deferred", deferred)
    with pytest.raises(runner.Interrupted) as exc:
        e.run([route("a")], deploy=True)
    assert exc.value.signum == signal.SIGINT


def test_a_running_lab_is_refused(monkeypatch):
    e = make(monkeypatch)
    e.lab.existing = {"clab-t-r1"}
    rep = e.run([route("a")], deploy=True)
    assert rep.status == "error" and e.lab.deployed == 0 and e.lab.destroyed == 0 and not e.lab.locked


def test_missing_containers_are_an_error(monkeypatch):
    e = make(monkeypatch)
    e.lab.running = {"clab-t-r1", "clab-t-r2"}
    rep = e.run([route("a")], deploy=True)
    assert rep.status == "error" and e.lab.destroyed == 1
    e = make(monkeypatch)
    e.lab.running = {"clab-t-r1", "clab-t-r2"}
    assert e.run([route("a")], deploy=False).status == "error"


def test_cleanup_trouble_never_hides_the_results(monkeypatch):
    for kw in ({"destroy_rc": 1}, {"destroy_error": RuntimeError("docker gone")}):
        e = make(monkeypatch)
        for k, v in kw.items():
            setattr(e.lab, k, v)
        rep = e.run([route("a")], deploy=True)
        assert rep.status == "passed" and e.lab.destroyed == 1 and e.lab not in runner._ACTIVE and not e.lab.locked


def test_deploy_failure_is_an_error_and_the_lab_is_destroyed(monkeypatch):
    e = make(monkeypatch)
    e.lab.deploy_error = LabError("no image")
    rep = e.run([route("a")], deploy=True)
    assert rep.status == "error" and e.lab.destroyed == 1


def test_internal_error_is_an_error(monkeypatch, capsys):
    e = make(monkeypatch)
    e.lab.deploy_error = RuntimeError("boom")
    monkeypatch.setenv("NETDRYRUN_DEBUG", "1")
    rep = e.run([route("a")], deploy=True)
    assert rep.status == "error" and rep.exit_code == 2 and "Traceback" in capsys.readouterr().err


@pytest.mark.parametrize("value", [-1, float("inf"), float("nan"), True, "10", None])
def test_bad_settle_or_hold_is_an_error(monkeypatch, value):
    for key in ("settle", "hold"):
        e = make(monkeypatch)
        rep = e.run([route("a")], deploy=True, **{key: value})
        assert rep.status == "error" and e.lab.deployed == 0


@pytest.mark.parametrize("value", [0, 0.0, 1e9])
def test_good_settle_and_hold(monkeypatch, value):
    e = make(monkeypatch)
    assert e.run([route("a")], settle=value, hold=value).status == "passed"


@pytest.mark.parametrize("value,env", [("1", True), ("yes", True), ("true", True), ("", False), ("0", False),
                                       ("false", False), ("no", False), (None, False)])
def test_debug_flag(monkeypatch, value, env):
    if value is None:
        monkeypatch.delenv("NETDRYRUN_DEBUG", raising=False)
    else:
        monkeypatch.setenv("NETDRYRUN_DEBUG", value)
    assert runner._debug() is env


# ----------------------------------------------------------------------------------------------- run(): scenarios

def _recovering(e, fault_node="r1", gone_until=None):
    """r3's route 10.1.0.0/24 is lost while a link is down (and until `gone_until` after restore)."""
    lab = e.lab

    def routes(t, p):
        if p != "10.1.0.0/24":
            return True
        down = [ev for ev in lab.events if ev[0] == "link"]
        if down and down[-1][3] is False:
            return False
        if gone_until is not None and down and t < gone_until:
            return False
        return True

    e.drivers["r3"].routes_ = {"default": routes}


def test_scenario_recovery_is_checked(monkeypatch):
    e = make(monkeypatch)
    _recovering(e, gone_until=10 ** 6)
    base = route("base", node="r3", prefix="10.1.0.0/24")
    sc = Scenario("s", [Fault("link_down", "r1", "eth1")], [route("[s] other", node="r2")])
    rep = e.run([base], [sc], settle=10, hold=10)
    assert rep is not None and rep.status == "failed"
    names = [r.check.name for r in rep.results]
    assert names == ["base", "[s] other", "[after s] recovers: base"]
    stuck = rep.results[-1]
    assert not stuck.passed and stuck.check.type == "route" and stuck.check.params["node"] == "r3"
    assert e.results[-1] is stuck and len(e.results) == 3


def test_recovered_network_adds_nothing(monkeypatch):
    e = make(monkeypatch)
    _recovering(e)
    base = route("base", node="r3", prefix="10.1.0.0/24")
    sc = Scenario("s", [Fault("link_down", "r1", "eth1")], [route("[s] other", node="r2")])
    rep = e.run([base], [sc], settle=10, hold=10)
    assert rep.status == "passed" and [r.check.name for r in rep.results] == ["base", "[s] other"]


def test_only_passing_positive_checks_must_recover(monkeypatch):
    e = make(monkeypatch)
    e.drivers["r1"].routes_ = {"default": lambda t, p: p == "10.9.9.0/24"}
    broken = route("broken", prefix="10.5.0.0/16", timeout=6)       # failed before the scenario
    guard = leak("guard")                                           # passed, but post-convergence
    sc = Scenario("s", [Fault("link_down", "r1", "eth1")], [route("[s] x", node="r2")])
    rep = e.run([broken, guard], [sc], settle=10, hold=10)
    assert [r.check.name for r in rep.results] == ["broken", "guard", "[s] x"]
    # the leak guard is not re-run as a "recovery" check: it only matters after convergence
    e = make(monkeypatch)
    e.drivers["r1"].routes_ = {"default": lambda t, p: p == "10.9.9.0/24" or e.lab.link_events()}
    rep = e.run([guard], [sc], settle=10, hold=10)
    assert rep.status == "passed" and [r.check.name for r in rep.results] == ["guard", "[s] x"]


def test_later_scenarios_are_skipped_when_the_network_does_not_recover(monkeypatch):
    e = make(monkeypatch)
    _recovering(e, gone_until=10 ** 6)
    base = route("base", node="r3", prefix="10.1.0.0/24")
    s1 = Scenario("s1", [Fault("link_down", "r1", "eth1")], [route("[s1] x", node="r2")])
    s2 = Scenario("s2", [Fault("link_down", "r2", "eth2")], [route("[s2] y", node="r2")])
    rep = e.run([base], [s1, s2], settle=10, hold=10)
    assert [r.check.name for r in rep.results] == ["base", "[s1] x", "[after s1] recovers: base"]
    assert ("r2", "eth2", False) not in e.lab.link_events()


def test_scenario_results_are_reported(monkeypatch):
    e = make(monkeypatch)
    sc = Scenario("s", [Fault("link_down", "r1", "eth1")], [route("[s] pos", node="r2"), leak("[s] neg", node="r2")])
    e.drivers["r2"].routes_ = {"default": lambda t, p: p == "10.9.9.0/24"}
    rep = e.run([route("base")], [sc], settle=10, hold=10)
    assert rep.status == "passed" and [r.check.name for r in rep.results] == ["base", "[s] pos", "[s] neg"]
    assert [r.check.name for r in e.results] == ["base", "[s] pos", "[s] neg"]


# ----------------------------------------------------------------------------------------------- run_scenario

def direct(e, sc, settle=10, hold=10, driver_for=None):
    return runner.run_scenario(e.lab, sc, e.drivers, settle=settle, hold=hold, on_result=e.results.append,
                               log=e.logs.append, driver_for=driver_for)


def test_link_down_is_applied_and_restored(monkeypatch):
    e = make(monkeypatch)
    sc = Scenario("s", [Fault("link_down", "r1", "eth1")], [route("x", node="r3")])
    results = direct(e, sc)
    assert e.lab.link_events() == [("r1", "eth1", False), ("r1", "eth1", True)]
    assert ("require", "r1") in e.lab.events
    assert [r.passed for r in results] == [True] and len(e.results) == 1
    assert e.clock.sleeps[0] == 10 and e.clock.sleeps[-1] == 10   # settle before the checks and after restoring


def test_node_isolated_downs_every_data_interface(monkeypatch):
    e = make(monkeypatch)
    direct(e, Scenario("s", [Fault("node_isolated", "r1")], [route("x", node="r3")]))
    assert e.lab.link_events() == [("r1", "eth1", False), ("r1", "eth2", False), ("r1", "eth1", True),
                                   ("r1", "eth2", True)]


def test_inject_routes_is_applied_and_restored(monkeypatch):
    e = make(monkeypatch)
    sc = Scenario("s", [Fault("inject_routes", "r2", prefixes=["10.66.0.0/16"], as_path=[65009]),
                        Fault("link_down", "r1", "eth1")], [route("x", node="r3")])
    direct(e, sc)
    [inj] = e.injections
    assert (inj.node, inj.prefixes, inj.as_path, inj.applied, inj.restored) == ("r2", ["10.66.0.0/16"], [65009], True, 1)
    assert ("r1", "eth1", False) in e.lab.link_events()        # a later fault still applies
    assert e.clock.sleeps.count(10) == 2


def test_inject_only_scenario_settles_after_restoring(monkeypatch):
    e = make(monkeypatch)
    direct(e, Scenario("s", [Fault("inject_routes", "r2", prefixes=["10.66.0.0/16"])], [route("x", node="r3")]))
    assert e.clock.sleeps[0] == 10 and e.clock.sleeps[-1] == 10 and e.clock.sleeps.count(10) == 2
    assert not e.lab.link_events()


def test_scenario_restores_even_when_a_check_crashes(monkeypatch):
    e = make(monkeypatch)
    e.drivers["r3"].on_call = lambda: (_ for _ in ()).throw(KeyboardInterrupt())
    sc = Scenario("s", [Fault("inject_routes", "r2", prefixes=["10.66.0.0/16"]), Fault("link_down", "r1", "eth1")],
                  [route("x", node="r3")])
    with pytest.raises(KeyboardInterrupt):
        direct(e, sc)
    assert ("r1", "eth1", True) in e.lab.link_events() and e.injections[0].restored == 1


def test_a_link_that_cannot_be_restored_stops_the_run(monkeypatch):
    e = make(monkeypatch)
    e.lab.set_link_error = {("r1", "eth1", True): LabError("stuck")}
    with pytest.raises(LabError):
        direct(e, Scenario("s", [Fault("link_down", "r1", "eth1"), Fault("link_down", "r2", "eth2")],
                           [route("x", node="r3")]))
    assert ("r2", "eth2", True) in e.lab.link_events()        # the other link is still restored


def test_an_injection_that_cannot_be_restored_stops_the_run(monkeypatch):
    e = make(monkeypatch)
    sc = Scenario("s", [Fault("inject_routes", "r2", prefixes=["10.66.0.0/16"])], [route("x", node="r3")])
    orig = runner.RouteInjection

    class Failing(orig):
        def restore(self):
            raise LabError("stuck")

    monkeypatch.setattr(runner, "RouteInjection", Failing)
    with pytest.raises(LabError):
        direct(e, sc)


def test_scenario_waits_for_bgp_over_the_downed_link_and_settles(monkeypatch):
    e = make(monkeypatch)
    lab = e.lab

    def down_after(delay):
        def f(t):
            ev = [x for x in lab.events if x[0] == "link" and not x[3]]
            return "idle" if ev and t >= ev[0][4] + delay else "established"
        return f

    e.drivers["r1"].neighbors = {"default": lambda t: {"10.0.12.2": down_after(20)(t)}}
    e.drivers["r2"].neighbors = {"default": lambda t: {"10.0.12.1": down_after(20)(t)}}
    direct(e, Scenario("s", [Fault("link_down", "r1", "eth1")], [route("x", node="r3", timeout=60)]))
    assert e.clock.sleeps[:8] == [3, 3, 3, 3, 3, 3, 3, 10]   # seen down at t=21, then the settle


def test_scenario_checks_in_another_vrf_watch_that_vrf(monkeypatch):
    e = make(monkeypatch)
    for n in ("r1", "r2"):
        e.drivers[n].neighbors = {"default": {}, "blue": {}}
    direct(e, Scenario("s", [Fault("link_down", "r1", "eth1")], [route("x", node="r3", vrf="blue")]))
    e.drivers["r3"].routes_["blue"] = always
    assert ("bgp_neighbors", "blue", 0.0) in e.drivers["r1"].calls
    assert ("bgp_neighbors", "default", 0.0) in e.drivers["r1"].calls


def test_scenario_negative_checks_are_held(monkeypatch):
    e = make(monkeypatch)
    e.drivers["r3"].routes_ = {"default": lambda t, p: p == "10.9.9.0/24" or t >= 10 + 3 + 3 + 8}
    results = direct(e, Scenario("s", [Fault("link_down", "r1", "eth1")],
                                 [route("pos", node="r3"), leak("neg", node="r3")]), hold=10)
    assert [r.check.name for r in results] == ["pos", "neg"] and [r.passed for r in results] == [True, False]
    assert [r.check.name for r in e.results] == ["pos", "neg"]
    e = make(monkeypatch)
    # positives: settle 10, reach 3, hold 20 (to t=33); then the leak guard holds 20 s and the leak comes at 48
    e.drivers["r3"].routes_ = {"default": lambda t, p: p == "10.9.9.0/24" or t >= 10 + 3 + 20 + 15}
    results = direct(e, Scenario("s", [Fault("link_down", "r1", "eth1")],
                                 [route("pos", node="r3"), leak("neg", node="r3")]), hold=20)
    assert [r.passed for r in results] == [True, False]


def _injected_at(lab):
    ev = [x for x in lab.events if x[0] == "inject"]
    return ev[0][2] if ev else None


def test_scenario_negative_checks_wait_for_the_bgp_gate(monkeypatch):
    """inject_routes: the injected routes reach r3 over 30 s (its prefix count from r2 climbs every sample),
    the leak among them last. The leak guard must not be judged until r3's counts are stable."""
    e = make(monkeypatch)

    def since(t):
        at = _injected_at(e.lab)
        return None if at is None else t - at

    e.drivers["r3"].neighbors = {"default": lambda t: {"10.0.23.2": (
        "established", {"ipv4-unicast": 3 + int(min(since(t) or 0, 30))})}}
    e.drivers["r3"].routes_ = {"default": lambda t, p: since(t) is not None and since(t) >= 30}
    sc = Scenario("s", [Fault("inject_routes", "r2", prefixes=["10.66.0.0/16"])], [leak("neg", node="r3", timeout=60)])
    [r] = direct(e, sc)
    assert not r.passed
    # a session over a downed link is expected down: it doesn't hold the gate
    e = _r1_with_another_session(monkeypatch, "established")
    [r] = direct(e, Scenario("s", [Fault("link_down", "r1", "eth1")], [leak("neg", node="r1", timeout=60)]))
    assert r.passed and e.clock.now < 60
    # any other session that stays down blocks it: not evaluated, after the cap
    e = _r1_with_another_session(monkeypatch, "active")
    neg = leak("neg", node="r1", timeout=20)
    [r] = direct(e, Scenario("s", [Fault("link_down", "r1", "eth1")], [neg]))
    assert not r.passed and not any(c[0] == "routes" for c in e.drivers["r1"].calls)
    assert [x.check for x in e.results] == [neg]
    # ...unless a check says it is down on purpose (in the scenario, or at the top level)
    down = chk("bgp_session", "down", neighbor="10.0.13.3", state="down")
    for in_scenario in (True, False):
        e = _r1_with_another_session(monkeypatch, "active")
        sc = Scenario("s", [Fault("link_down", "r1", "eth1")], [neg] + ([down] if in_scenario else []))
        results = runner.run_scenario(e.lab, sc, e.drivers, settle=10, hold=10, baseline_checks=[] if in_scenario else [down])
        assert all(x.passed for x in results)


def _r1_with_another_session(monkeypatch, state):
    """r1-r2 over r1 eth1 (down once the link is), plus r1's session to 10.0.13.3 in `state`; no leak."""
    e = make(monkeypatch)
    e.drivers["r1"].neighbors = {"default": lambda t: {"10.0.12.2": "idle" if e.lab.link_events() else "established",
                                                       "10.0.13.3": state}}
    e.drivers["r2"].neighbors = {"default": lambda t: {"10.0.12.1": "idle" if e.lab.link_events() else "established"}}
    e.drivers["r1"].routes_ = {"default": never}
    return e


def test_scenario_positive_that_fails_in_the_hold(monkeypatch):
    e = make(monkeypatch)
    e.drivers["r3"].routes_ = {"default": lambda t, p: t < 10 + 3 + 6}
    [r] = direct(e, Scenario("s", [Fault("link_down", "r1", "eth1")], [route("pos", node="r3")]), hold=10)
    assert not r.passed and isinstance(r.detail, str) and r.detail != r.history[-1]["detail"]
    assert r.attempts == 2 + 3 and r.samples_passed == 2 + 2 and r.samples_unready == 0
    assert [h["t"] for h in r.history] == [0.0, 3.0, 3.0, 6.0, 9.0] and r.duration == 9.0 and iso(r.started)


def test_scenario_positive_merged_fields(monkeypatch):
    e = make(monkeypatch)
    e.drivers["r3"].routes_ = {"default": lambda t, p: t >= 10 + 3}
    [r] = direct(e, Scenario("s", [Fault("link_down", "r1", "eth1")], [route("pos", node="r3")]), hold=10)
    assert r.passed and r.attempts == 3 + 5 and r.samples_passed == 2 + 5
    assert [h["t"] for h in r.history] == [0.0, 3.0, 6.0, 6.0, 9.0, 12.0, 15.0, 16.0]
    assert r.duration == 16.0 and [x.check.name for x in e.results] == ["pos"]


def test_scenario_positive_unready_samples_are_added(monkeypatch):
    e = make(monkeypatch)
    calls = {"n": 0}

    def flaky(t, p):
        calls["n"] += 1
        if calls["n"] == 1:
            raise DriverError("not yet")
        return t < 10 + 6 + 3 or True

    e.drivers["r3"].routes_ = {"default": flaky}
    e.drivers["r3"].routes_ = {"default": lambda t, p: (_ for _ in ()).throw(DriverError("x")) if t < 10 + 1 else True}
    [r] = direct(e, Scenario("s", [Fault("link_down", "r1", "eth1")], [route("pos", node="r3")]), hold=3)
    assert r.passed and r.samples_unready == 1 and r.attempts == 3 + 2


def test_scenario_positive_long_history(monkeypatch):
    e = make(monkeypatch)
    e.drivers["r3"].routes_ = {"default": lambda t, p: t >= 10 + 90}
    [r] = direct(e, Scenario("s", [Fault("link_down", "r1", "eth1", )], [route("pos", node="r3", timeout=200)]),
                 hold=90)
    assert r.passed and len(r.history) == 50 and r.attempts == 32 + 31


def test_scenario_with_fractional_timing(monkeypatch):
    e = make(monkeypatch)
    e.drivers["r3"].routes_ = {"default": always}
    [r] = direct(e, Scenario("s", [Fault("link_down", "r1", "eth1")], [route("pos", node="r3")]), hold=1.25,
                 settle=0.25)
    assert r.passed and r.duration == 4.2 and r.history[-1]["t"] == 4.2


def test_run_scenario_without_driver_for_builds_missing_drivers(monkeypatch):
    e = make(monkeypatch)
    drivers = dict(e.drivers)
    e.drivers = {"r3": drivers["r3"]}
    results = runner.run_scenario(e.lab, Scenario("s", [Fault("link_down", "r1", "eth1")], [route("x", node="r3")]),
                                  e.drivers, settle=10, hold=10)
    assert [r.passed for r in results] == [True]
    assert sorted(e.for_node_calls) == [("r1", None), ("r2", None)] and set(e.drivers) == {"r1", "r2", "r3"}
    # a driver already there is not rebuilt
    e.for_node_calls.clear()
    runner.run_scenario(e.lab, Scenario("s", [Fault("link_down", "r1", "eth1")], [route("x", node="r3")]),
                        e.drivers, settle=10, hold=10)
    assert e.for_node_calls == []


# ----------------------------------------------------------------------------------------------- sessions over links

def sessions(e, links, vrfs=("default",)):
    return runner._sessions_over_links(e.lab, links, list(vrfs), lambda n: e.drivers[n])


def test_sessions_over_links_on_the_faulted_node(monkeypatch):
    e = make(monkeypatch)
    e.drivers["r1"].neighbors = {"default": {"10.0.12.2": "established", "10.0.12.1": "established",
                                             "10.9.9.9": "established", "eth1": "established",
                                             "10.0.12.3": "idle", "eth2": "established"}}
    e.drivers["r2"].neighbors = {"default": {}}
    assert sessions(e, [("r1", "eth1")]) == [("r1", "default", "10.0.12.2"), ("r1", "default", "eth1")]


def test_sessions_over_links_any_state(monkeypatch):
    e = make(monkeypatch)
    e.drivers["r1"].neighbors = {"default": {"10.0.12.2": "established", "10.0.12.3": "idle", "10.9.9.9": "idle"}}
    e.drivers["r2"].neighbors = {"default": {"10.0.12.1": "active"}}
    assert runner._sessions_over_links(e.lab, [("r1", "eth1")], ["default"], lambda n: e.drivers[n], any_state=True) == [
        ("r1", "default", "10.0.12.2"), ("r1", "default", "10.0.12.3"), ("r2", "default", "10.0.12.1")]
    assert sessions(e, [("r1", "eth1")]) == [("r1", "default", "10.0.12.2")]


def test_sessions_over_links_on_the_far_end(monkeypatch):
    e = make(monkeypatch)
    e.drivers["r1"].neighbors = {"default": {}}
    e.drivers["r2"].neighbors = {"default": {"10.0.12.1": "established", "eth1": "established",
                                             "10.0.12.2": "established", "10.0.12.5": "established",
                                             "eth2": "established"},
                                 "blue": {"10.0.12.1": "established", "eth1": "active"}}
    assert sessions(e, [("r1", "eth1")], ("default", "blue")) == [
        ("r2", "blue", "10.0.12.1"), ("r2", "default", "10.0.12.1"), ("r2", "default", "eth1")]
    assert ("bgp_neighbors", "blue", 0.0) in e.drivers["r2"].calls


def test_sessions_over_links_per_vrf_and_unreadable(monkeypatch):
    e = make(monkeypatch)
    e.drivers["r1"].neighbors = {"blue": {"10.0.12.2": "established"}}   # no default VRF on r1: nothing there
    e.drivers["r2"].neighbors = {"default": {}}
    assert sessions(e, [("r1", "eth1")], ("default", "blue")) == [("r1", "blue", "10.0.12.2")]
    calls = [c for c in e.drivers["r1"].calls if c[0] == "bgp_neighbors"]
    assert [c[1] for c in calls] == ["default", "blue"]                  # each (node, vrf) read once
    # BGP state that can't be read is not "no sessions": no way to tell which sessions the fault takes down
    e.drivers["r2"].neighbors_error = DriverError("no bgpd")
    with pytest.raises(LabError):
        sessions(e, [("r1", "eth1")], ("default", "blue"))
    e = make(monkeypatch)
    e.drivers["r1"].neighbors_error = DriverError("cli timeout")
    with pytest.raises(LabError):
        sessions(e, [("r1", "eth1")])


def test_sessions_over_links_node_without_a_driver_has_nothing_to_watch(monkeypatch):
    """A host at the far end that no driver can read (a Linux client) runs no BGP Netdryrun can observe."""
    e = make(monkeypatch)
    e.drivers["r1"].neighbors = {"default": {"10.0.12.2": "established"}}

    def driver_for(n):
        if n == "r2":
            raise DriverError("cannot detect driver for node r2")
        return e.drivers[n]

    assert runner._sessions_over_links(e.lab, [("r1", "eth1")], ["default"], driver_for) == [("r1", "default", "10.0.12.2")]


def test_unreadable_snapshot_stops_the_scenario_before_any_fault(monkeypatch):
    """The far end's BGP state can't be read when the scenario starts: no verdict (exit 2), and no link is
    taken down, instead of a scenario judged without the "fault took effect" wait."""
    e = make(monkeypatch)
    # r2's session over the link would go down with it; its state is unreadable just when the scenario starts
    e.drivers["r2"].neighbors_error = lambda t: DriverError("vtysh timed out") if 3 <= t < 6 else None
    e.drivers["r2"].neighbors = {"default": lambda t: {"10.0.12.1": "established" if t < 6 else "idle"}}
    sc = Scenario("s", [Fault("link_down", "r2", "eth1")], [route("[s] x", node="r3")])
    rep = e.run([route("a")], [sc], settle=0, hold=0)
    assert rep.status == "error" and rep.exit_code == 2
    assert e.lab.link_events() == []
    # the faulted node's interface addresses can't be read: the same
    e = make(monkeypatch)

    def no_addresses(node, iface):
        raise LabError(f"could not read the addresses of {node} {iface}")

    e.lab.interface_addresses = no_addresses
    rep = e.run([route("a")], [Scenario("s", [Fault("link_down", "r1", "eth1")], [route("[s] x", node="r3")])])
    assert rep.status == "error" and e.lab.link_events() == []


def test_interface_addresses_that_cannot_be_read_are_an_error(monkeypatch):
    lab = Lab.__new__(Lab)
    lab.nodes = {"r1": Node("r1", "clab-t-r1", "linux", "frr")}
    answers = {"rc": 1}
    monkeypatch.setattr(lab, "exec", lambda node, cmd, timeout=60, input=None: ExecResult(
        cmd, answers["rc"], "4: eth1    inet 10.0.12.1/30 brd 10.0.12.3 scope global eth1" if answers["rc"] == 0 else "",
        "Device \"eth1\" does not exist." if answers["rc"] else ""))
    with pytest.raises(LabError):
        lab.interface_addresses("r1", "eth1")
    answers["rc"] = 0
    assert [str(a) for a in lab.interface_addresses("r1", "eth1")] == ["10.0.12.1/30"]


def test_sessions_over_links_ipv6_and_scoped_keys(monkeypatch):
    e = make(monkeypatch)
    e.lab.addresses = {("r1", "eth1"): ["2001:db8:12::1/64"]}
    e.drivers["r1"].neighbors = {"default": {"2001:db8:12::2": "established", "fe80::2%eth1": "established"}}
    e.drivers["r2"].neighbors = {"default": {"2001:db8:12::1%eth1": "established"}}
    assert sessions(e, [("r1", "eth1")]) == [("r1", "default", "2001:db8:12::2"),
                                             ("r2", "default", "2001:db8:12::1%eth1")]


# ----------------------------------------------------------------------------------------------- fault visible

SC = Scenario("s", [Fault("link_down", "r1", "eth1")], [])


def wait(e, watch, timeout):
    return runner._wait_fault_visible(watch, lambda n: e.drivers[n], timeout, SC, log=e.logs.append)


def test_wait_fault_visible_returns_when_every_session_is_down(monkeypatch):
    e = make(monkeypatch)
    e.drivers["r1"].neighbors = {"default": lambda t: {"10.0.12.2": "idle" if t >= 4 else "established"}}
    e.drivers["r2"].neighbors = {"blue": lambda t: {"10.0.12.1": "idle" if t >= 7 else "established"}}
    wait(e, [("r1", "default", "10.0.12.2"), ("r2", "blue", "10.0.12.1")], 30)
    assert e.clock.now == 9 and e.clock.sleeps == [3, 3, 3]


def test_wait_fault_visible_session_gone_counts_as_down(monkeypatch):
    e = make(monkeypatch)
    e.drivers["r1"].neighbors = {"default": lambda t: {} if t >= 3 else {"10.0.12.2": "established"}}
    wait(e, [("r1", "default", "10.0.12.2")], 30)
    assert e.clock.now == 3


def test_wait_fault_visible_times_out(monkeypatch):
    e = make(monkeypatch)
    e.drivers["r1"].neighbors = {"default": {"10.0.12.2": "established"}}
    with pytest.raises(LabError):
        wait(e, [("r1", "default", "10.0.12.2")], 10)
    assert e.clock.sleeps == [3, 3, 3, 1] and e.clock.now == 10


def test_wait_fault_visible_unreadable_state_is_not_proof(monkeypatch):
    e = make(monkeypatch)
    e.drivers["r1"].neighbors_error = DriverError("cli down")
    e.drivers["r2"].neighbors = {"default": {"10.0.12.1": "idle"}}
    with pytest.raises(LabError):
        wait(e, [("r1", "default", "10.0.12.2"), ("r2", "default", "10.0.12.1")], 6)


def test_wait_fault_visible_with_nothing_to_watch(monkeypatch):
    e = make(monkeypatch)
    wait(e, [], 30)
    assert e.clock.sleeps == [] and e.logs


def test_wait_fault_visible_fractional_deadline(monkeypatch):
    e = make(monkeypatch)
    e.drivers["r1"].neighbors = {"default": {"10.0.12.2": "established"}}
    with pytest.raises(LabError):
        wait(e, [("r1", "default", "10.0.12.2")], 3.5)
    assert e.clock.sleeps == [3, 0.5]


# ----------------------------------------------------------------------------------------------- the BGP gate

def gate(e, negatives, all_checks=None, positive_results=(), warnings=None):
    return runner._bgp_convergence_gate(negatives, all_checks if all_checks is not None else negatives, e.drivers,
                                        log=e.logs.append, positive_results=list(positive_results),
                                        warnings=warnings)


def test_gate_needs_two_identical_established_samples(monkeypatch):
    e = make(monkeypatch)
    e.drivers["r1"].neighbors = {"default": {"10.0.12.2": "established", "10.0.13.3": "established"}}
    assert gate(e, [leak("n")]) == {} and e.clock.sleeps == [3]


def test_gate_waits_for_prefix_counts_to_settle(monkeypatch):
    e = make(monkeypatch)
    e.drivers["r1"].neighbors = {"default": lambda t: {"10.0.12.2": ("established", {"ipv4-unicast": min(int(t), 6)})}}
    assert gate(e, [leak("n")]) == {}
    assert e.clock.now == 9   # counts 0, 3, 6, 6


def test_gate_counts_that_never_settle_dont_block(monkeypatch):
    e = make(monkeypatch)
    e.drivers["r1"].neighbors = {"default": lambda t: {"10.0.12.2": ("established", {"ipv4-unicast": int(t)})}}
    assert gate(e, [leak("n", timeout=9)]) == {} and e.clock.now == 9


def test_gate_down_sample_resets_the_streak(monkeypatch):
    e = make(monkeypatch)
    states = {0: "established", 3: "idle", 6: "established", 9: "established"}
    e.drivers["r1"].neighbors = {"default": lambda t: {"10.0.12.2": states.get(round(t), "established")}}
    assert gate(e, [leak("n")]) == {} and e.clock.now == 9


def test_gate_unreadable_sample_resets_the_streak(monkeypatch):
    e = make(monkeypatch)
    e.drivers["r1"].neighbors = {"default": up("10.0.12.2")["default"]}
    e.drivers["r1"].neighbors_error = lambda t: DriverError("x") if round(t) == 3 else None
    assert gate(e, [leak("n")]) == {} and e.clock.now == 9


def test_gate_blocks_a_node_whose_session_never_comes_up(monkeypatch):
    e = make(monkeypatch)
    e.clock.t += 0.25
    e.drivers["r1"].neighbors = {"default": lambda t: {"10.0.12.2": "established" if t < 3 else "active"}}
    a, b = leak("a", timeout=7.5), leak("b", timeout=9.75)
    blocked = gate(e, [a, b])
    assert set(blocked) == {id(a), id(b)}
    r = blocked[id(a)]
    assert r.check is a and r.passed is False and r.attempts == 5 and r.duration == 9.8 and iso(r.started)
    assert r.evidence == [] and r.samples_passed == 0 and r.samples_unready == 0
    assert [h["passed"] for h in r.history] == [True, False, False, False, False]
    assert [h["t"] for h in r.history] == [0.0, 3.0, 6.0, 9.0, 9.8]
    assert e.clock.sleeps == [3, 3, 3, 0.75]


def test_gate_blocked_result_counts_unready_samples(monkeypatch):
    e = make(monkeypatch)
    e.drivers["r1"].neighbors = {"default": {"10.0.12.2": "active"}}
    e.drivers["r1"].neighbors_error = lambda t: DriverError("x") if t >= 3 else None
    [r] = gate(e, [leak("a", timeout=9)]).values()
    assert r.samples_unready == 3 and r.attempts == 4
    assert [bool(h.get("unready")) for h in r.history] == [False, True, True, True]
    assert all(h["passed"] is False for h in r.history)


def test_gate_keeps_the_last_50_samples(monkeypatch):
    e = make(monkeypatch)
    e.drivers["r1"].neighbors = {"default": {"10.0.12.2": "active"}}
    [r] = gate(e, [leak("a", timeout=300)]).values()
    assert r.attempts == 101 and len(r.history) == 50 and r.history[0]["t"] == 153.0


def test_gate_reads_each_checks_vrf(monkeypatch):
    e = make(monkeypatch)
    e.drivers["r1"].neighbors = {"default": {"10.0.12.2": "active"}, "blue": {"10.0.12.2": "established"}}
    assert gate(e, [leak("n", vrf="blue", timeout=9)]) == {}
    assert {c[1] for c in e.drivers["r1"].calls} == {"blue"}
    e = make(monkeypatch)
    e.drivers["r1"].neighbors = {"default": {"10.0.12.2": "established"}, "blue": {"10.0.12.2": "active"}}
    assert len(gate(e, [leak("n", vrf="blue", timeout=9)])) == 1


def test_gate_ignores_sessions_expected_down_in_their_vrf(monkeypatch):
    e = make(monkeypatch)
    e.drivers["r1"].neighbors = {"blue": {"10.0.12.2": "established", "10.0.99.9": "idle"}}
    down = chk("bgp_session", "gone", neighbor="10.0.99.9", state="down", vrf="blue")
    neg = leak("n", vrf="blue", timeout=9)
    assert gate(e, [neg], [down, neg]) == {}
    # the same neighbor expected down in another VRF doesn't excuse it here
    e = make(monkeypatch)
    e.drivers["r1"].neighbors = {"blue": {"10.0.12.2": "established", "10.0.99.9": "idle"}}
    other = chk("bgp_session", "gone", neighbor="10.0.99.9", state="down")
    assert len(gate(e, [neg], [other, neg])) == 1


def test_gate_a_session_expected_established_still_blocks(monkeypatch):
    e = make(monkeypatch)
    e.drivers["r1"].neighbors = {"default": {"10.0.12.2": "active"}}
    want_up = chk("bgp_session", "up", neighbor="10.0.12.2", state="established")
    plain = chk("bgp_session", "up2", neighbor="10.0.12.2")
    prefix_check = chk("bgp_prefixes", "p", neighbor="10.0.12.2", min=1)
    neg = leak("n", timeout=9)
    assert len(gate(e, [neg], [want_up, plain, prefix_check, neg])) == 1


def test_gate_skips_nodes_whose_positive_checks_never_got_state(monkeypatch):
    e = make(monkeypatch)
    e.drivers["r1"].neighbors = {"default": {"10.0.12.2": "active"}}
    dead = Result(route("p"), False, "x", 3, 9.0, "t", samples_unready=3)
    neg = leak("n", timeout=9)
    assert gate(e, [neg], positive_results=[dead]) == {} and e.drivers["r1"].calls == []
    for alive in (Result(route("p"), False, "x", 3, 9.0, "t", samples_unready=2),
                  Result(route("p"), False, "x", 0, 9.0, "t", samples_unready=0)):
        e = make(monkeypatch)
        e.drivers["r1"].neighbors = {"default": {"10.0.12.2": "active"}}
        assert len(gate(e, [neg], positive_results=[alive])) == 1
    e = make(monkeypatch)
    e.drivers["r1"].neighbors = {"default": {"10.0.12.2": "active"}}
    other_node = Result(route("p", node="r2"), False, "x", 3, 9.0, "t", samples_unready=3)
    assert len(gate(e, [neg], positive_results=[other_node])) == 1


def test_gate_ping_only_node_without_bgp_is_not_waited_for(monkeypatch):
    e = make(monkeypatch)
    e.drivers["r1"].neighbors_error = DriverError("no bgpd")
    p = chk("ping", "p", target="10.9.9.9", expect="failure", timeout=60)
    assert gate(e, [p]) == {} and e.clock.now == 0 and not e.logs


def test_gate_node_that_errors_first_but_has_other_checks_is_waited_for(monkeypatch):
    e = make(monkeypatch)
    e.drivers["r1"].neighbors = {"default": {"10.0.12.2": "active"}}
    e.drivers["r1"].neighbors_error = lambda t: DriverError("starting") if t < 1 else None
    assert len(gate(e, [leak("n", timeout=9)])) == 1 and e.clock.now == 9
    # a ping-only node that answers first and errors later is still waited for
    e = make(monkeypatch)
    e.drivers["r1"].neighbors = {"default": {"10.0.12.2": "active"}}
    e.drivers["r1"].neighbors_error = lambda t: DriverError("crash") if t >= 3 else None
    p = chk("ping", "p", target="10.9.9.9", expect="failure", timeout=9)
    assert len(gate(e, [p])) == 1 and e.clock.now == 9


def test_gate_node_that_never_answers_goes_ahead_with_a_warning(monkeypatch):
    e = make(monkeypatch)
    e.drivers["r1"].neighbors_error = DriverError("no bgpd")
    assert gate(e, [leak("n", timeout=9)]) == {} and e.clock.now == 9 and len(e.logs) == 1


def test_gate_waits_for_a_node_that_reports_no_bgp_neighbors(monkeypatch):
    e = make(monkeypatch)
    e.drivers["r1"].neighbors = {"default": lambda t: {"10.0.12.2": "established"} if t >= 7 else {}}
    warnings = {}
    assert gate(e, [leak("n", timeout=30)], warnings=warnings) == {} and e.clock.now == 12 and warnings == {}
    # never any neighbor: released at the cap, not blocked, with a warning for each gated check
    e = make(monkeypatch)
    e.drivers["r1"].neighbors = {"default": {}}
    a, b = leak("a", timeout=9), leak("b", timeout=5)
    warnings = {}
    assert gate(e, [a, b], warnings=warnings) == {} and e.clock.now == 9
    assert set(warnings) == {id(a), id(b)} and all(isinstance(w, str) and w for w in warnings.values())
    # neighbors seen, then none at the cap: still released with a warning
    e = make(monkeypatch)
    e.drivers["r1"].neighbors = {"default": lambda t: {"10.0.12.2": "active"} if t < 3 else {}}
    warnings = {}
    assert gate(e, [a], warnings=warnings) == {} and set(warnings) == {id(a)}
    # no neighbors, then a session that stays down: blocked as before, no warning
    e = make(monkeypatch)
    e.drivers["r1"].neighbors = {"default": lambda t: {"10.0.12.2": "active"} if t >= 3 else {}}
    warnings = {}
    assert set(gate(e, [a], warnings=warnings)) == {id(a)} and warnings == {}


def test_gate_ping_only_node_with_no_bgp_neighbors_is_waited_for(monkeypatch):
    """The ping-only exemption is for a node whose first answer is an error; {} is an answer."""
    e = make(monkeypatch)
    e.drivers["r1"].neighbors = {"default": {}}
    p = chk("ping", "p", target="10.9.9.9", expect="failure", timeout=9)
    warnings = {}
    assert gate(e, [p], warnings=warnings) == {} and e.clock.now == 9 and set(warnings) == {id(p)}


def test_gate_groups_are_independent(monkeypatch):
    e = make(monkeypatch)
    e.drivers["r1"].neighbors_error = DriverError("no bgpd")         # sorted first, errors every round
    e.drivers["r2"].neighbors = {"default": {"10.0.12.1": "established"}}
    e.drivers["r3"].neighbors = {"default": {"10.0.23.2": "active"}}
    a, b, c = leak("a", timeout=9), leak("b", node="r2", timeout=30), leak("c", node="r3", timeout=6)
    blocked = gate(e, [a, b, c])
    assert set(blocked) == {id(c)}
    assert [x[2] for x in e.drivers["r2"].calls] == [0.0, 3.0]
    assert e.clock.sleeps == [3, 3, 3]


def test_gate_with_no_negatives(monkeypatch):
    e = make(monkeypatch)
    assert gate(e, []) == {} and e.clock.sleeps == []


# ----------------------------------------------------------------------------------------------- small helpers

def test_check_duration():
    for ok in (0, 0.0, 5, 1e12):
        runner._check_duration("x", ok)
    for bad in (-0.1, float("inf"), float("nan"), True, False, "1", None, [1]):
        with pytest.raises(runner.RunError):
            runner._check_duration("x", bad)


def test_ip():
    assert runner._ip("10.0.0.1") == ipaddress.ip_address("10.0.0.1")
    assert runner._ip("fe80::1%eth1") == ipaddress.ip_address("fe80::1")
    assert runner._ip("eth1") is None


def test_now_is_utc():
    assert iso(runner._now())


def test_error_report(tmp_path):
    rep = runner.error_report(tmp_path, "bad")
    assert rep.status == "error" and rep.exit_code == 2 and rep.error == "bad"
    assert rep.config.path == tmp_path / "netdryrun.yml" and rep.config.checks == [] and rep.config.timeout == 0.0
    assert rep.config.lab == Path() and iso(rep.started) and rep.started == rep.finished
    f = tmp_path / "x.yml"
    assert runner.error_report(f, "e").config.path == f


def test_signals():
    assert runner.signal_name(signal.SIGTERM) == "SIGTERM" and runner.signal_name(999) == "signal 999"
    assert runner.signal_exit_code(signal.SIGINT) == 130
    e = runner.Interrupted(signal.SIGHUP)
    assert e.signum == signal.SIGHUP and isinstance(e, KeyboardInterrupt) and str(e) == "SIGHUP"
    with pytest.raises(runner.Interrupted) as exc:
        runner._raise_interrupted(signal.SIGTERM, None)
    assert exc.value.signum == signal.SIGTERM
    assert runner._catchable_signals("SIGTERM", "NOPE") == [signal.SIGTERM]


@pytest.mark.skipif(not hasattr(signal, "SIGHUP"), reason="POSIX signals")
def test_install_signal_handlers(monkeypatch):
    seen = {}
    monkeypatch.setattr(runner.signal, "signal", lambda s, h: seen.__setitem__(s, h))
    runner.install_signal_handlers()
    assert seen == {signal.SIGTERM: runner._raise_interrupted, signal.SIGHUP: runner._raise_interrupted}
    seen.clear()
    import threading
    t = threading.Thread(target=runner.install_signal_handlers)
    t.start()
    t.join()
    assert seen == {}


# ----------------------------------------------------------------------------------------------- loading a config

@pytest.mark.parametrize("text", [
    "lab: t.clab.yml\ntimeout: soon\nchecks: [{type: route, node: r1, prefix: 10.0.0.0/8}]\n",
    "lab: t.clab.yml\nchecks: {a: 1}\n",
    "lab: t.clab.yml\nchecks: [{type: route, node: r1, prefix: 10.0.0.0/8}]\nscenarios: {a: 1}\n",
    "lab: t.clab.yml\nchecks: [{type: route, node: r1, prefix: 10.0.0.0/8}]\nnodes: [r1]\n",
    "lab: t.clab.yml\nchecks: [{type: route, node: r1, prefix: 10.0.0.0/8}]\nnodes: {r1: frr}\n",
    "lab: t.clab.yml\nchecks: [{type: route, node: r1, prefix: 10.0.0.0/8}]\n  bad: [\n",
    "[1, 2]\n",
])
def test_load_config_errors_are_config_errors(tmp_path, text):
    (tmp_path / "t.clab.yml").write_text("name: t\n")
    (tmp_path / "netdryrun.yml").write_text(text)
    with pytest.raises(runner.ConfigError):
        runner.load_config(tmp_path)


def test_shape_problem(tmp_path):
    p = tmp_path / "netdryrun.yml"
    cases = {
        "timeout: soon\n": True, "timeout: '30'\n": False, "timeout: 30\n": False, "timeout: [1]\n": True,
        "timeout: null\n": False, "checks: {}\n": True, "checks: []\n": False, "scenarios: 1\n": True,
        "scenarios: []\n": False, "nodes: []\n": True, "nodes: {}\n": False, "nodes: {r1: x}\n": True,
        "nodes: {r1: null}\n": False, "nodes: {r1: {driver: frr}}\n": False, "[1]\n": False, "a: [\n": False,
        "nodes: null\n": False,
    }
    for text, problem in cases.items():
        p.write_text(text)
        assert (runner._shape_problem(p) is not None) is problem, text


def test_yaml_problem():
    import yaml
    try:
        yaml.safe_load("a: [\n")
    except yaml.YAMLError as e:
        assert runner._yaml_problem(e)
    assert runner._yaml_problem(yaml.YAMLError("plain"))


def test_config_path(tmp_path):
    assert runner._config_path(tmp_path) == tmp_path / "netdryrun.yml"
    assert runner._config_path(tmp_path / "x.yml") == tmp_path / "x.yml"


# ----------------------------------------------------------------------------------------------- more edges

def test_scenario_drivers_built_mid_scenario_get_their_override(monkeypatch):
    """r2 has no check of its own: its driver is first needed to watch the BGP session over the downed link."""
    e = make(monkeypatch)
    sc = Scenario("s", [Fault("link_down", "r1", "eth1")], [route("[s] x", node="r3")])
    rep = e.run([route("a")], [sc], drivers_cfg={"r2": "srlinux"})
    assert rep.status == "passed"
    assert ("r2", "srlinux") in e.for_node_calls and ("r2", None) not in e.for_node_calls


def test_one_signal_during_cleanup(monkeypatch):
    e = make(monkeypatch)

    @contextmanager
    def deferred():
        yield [signal.SIGTERM]

    monkeypatch.setattr(runner, "_signals_deferred", deferred)
    with pytest.raises(runner.Interrupted) as exc:
        e.run([route("a")], deploy=True)
    assert exc.value.signum == signal.SIGTERM and exc.value.report.status == "error"


def test_gate_down_group_does_not_stop_the_round(monkeypatch):
    e = make(monkeypatch)
    e.drivers["r1"].neighbors = {"default": {"10.0.12.2": "active"}}       # sorted first, down every round
    e.drivers["r2"].neighbors = {"default": {"10.0.12.1": "established"}}
    a, b = leak("a", timeout=6), leak("b", node="r2", timeout=30)
    assert set(gate(e, [a, b])) == {id(a)}
    assert [x[2] for x in e.drivers["r2"].calls] == [0.0, 3.0]


def test_gate_discarded_ping_node_does_not_stop_the_round(monkeypatch):
    e = make(monkeypatch)
    e.drivers["r1"].neighbors_error = DriverError("no bgpd")              # sorted first, ping-only: discarded
    e.drivers["r2"].neighbors = {"default": {"10.0.12.1": "established"}}
    p = chk("ping", "p", target="10.9.9.9", expect="failure", timeout=60)
    assert gate(e, [p, leak("b", node="r2", timeout=30)]) == {}
    assert [x[2] for x in e.drivers["r2"].calls] == [0.0, 3.0] and e.clock.now == 3


def test_inject_only_scenario_downs_no_link(monkeypatch):
    e = make(monkeypatch)
    e.drivers["r2"].neighbors = {"default": {"10.0.12.1": "established"}}
    direct(e, Scenario("s", [Fault("inject_routes", "r2", prefixes=["10.66.0.0/16"])], [route("x", node="r3")]))
    assert ("require", "r2") not in e.lab.events and not e.lab.link_events()
    assert not any(c[0] == "bgp_neighbors" for c in e.drivers["r2"].calls)


def test_scenario_watches_only_the_vrfs_its_checks_use(monkeypatch):
    e = make(monkeypatch)
    direct(e, Scenario("s", [Fault("link_down", "r1", "eth1")], [route("x", node="r3")]))
    assert {c[1] for c in e.drivers["r1"].calls if c[0] == "bgp_neighbors"} == {"default"}


def test_scenario_positive_unready_in_the_hold_is_counted(monkeypatch):
    e = make(monkeypatch)

    def routes(t, p):
        if t >= 10 + 3 + 3:
            raise DriverError("cli gone")
        return True

    e.drivers["r3"].routes_ = {"default": routes}
    [r] = direct(e, Scenario("s", [Fault("link_down", "r1", "eth1")], [route("pos", node="r3")]), hold=10)
    assert not r.passed and r.samples_unready == 1 and r.attempts == 2 + 2


def test_load_config_turns_any_crash_into_a_config_error(monkeypatch, tmp_path):
    (tmp_path / "netdryrun.yml").write_text("checks: []\n")

    def boom(path):
        raise RuntimeError("bug")

    monkeypatch.setattr(runner, "load", boom)
    with pytest.raises(runner.ConfigError):
        runner.load_config(tmp_path)
    with pytest.raises(runner.ConfigError):
        runner.load_config(tmp_path / "netdryrun.yml")


def test_config_files_are_read_as_utf8(monkeypatch, tmp_path):
    import codecs
    seen = []
    orig = Path.read_text

    def read_text(self, encoding=None, errors=None):
        seen.append(encoding)
        return orig(self, encoding="utf-8", errors=errors)

    monkeypatch.setattr(Path, "read_text", read_text)
    (tmp_path / "netdryrun.yml").write_text("timeout: soon\n", encoding="utf-8")
    runner._shape_problem(tmp_path / "netdryrun.yml")
    assert seen and all(enc is not None and codecs.lookup(enc).name == "utf-8" for enc in seen)


# ----------------------------------------------------------------------------------------------- re-audit of the 0.3.1 review fixes

def test_gate_unreadable_after_no_neighbors_blocks_at_the_cap(monkeypatch):
    """No neighbors first, then BGP state that can't be read until the cap: the last answer is not
    "no neighbors" any more, so the node is blocked (not released as a node without BGP)."""
    e = make(monkeypatch)
    e.drivers["r1"].neighbors = {"default": {}}
    e.drivers["r1"].neighbors_error = lambda t: DriverError("x") if t >= 3 else None
    a = leak("a", timeout=9)
    warnings = {}
    assert set(gate(e, [a], warnings=warnings)) == {id(a)} and warnings == {}


def test_gate_no_neighbors_sample_resets_the_streak(monkeypatch):
    """established, none, established (same counts), then down: the empty sample breaks the streak, so the
    gate never sees 2 identical established samples in a row and blocks at the cap."""
    e = make(monkeypatch)

    def nbrs(t):
        t = round(t)
        if t == 3:
            return {}
        return {"10.0.12.2": "established" if t in (0, 6) else "active"}

    e.drivers["r1"].neighbors = {"default": nbrs}
    a = leak("a", timeout=15)
    blocked = gate(e, [a])
    assert set(blocked) == {id(a)}
    assert [h["passed"] for h in blocked[id(a)].history][:3] == [True, False, True]


def test_gate_blocked_result_counts_no_neighbor_samples_as_unready(monkeypatch):
    """A blocked node's samples with no neighbors at all are failing, unready samples (they decide whether
    the run is inconclusive); a session that is down is a failing, readable sample."""
    e = make(monkeypatch)
    e.drivers["r1"].neighbors = {"default": lambda t: {"10.0.12.2": "active"} if t >= 3 else {}}
    [r] = gate(e, [leak("a", timeout=9)]).values()
    assert r.attempts == 4 and r.samples_unready == 1 and r.samples_passed == 0
    assert [bool(h.get("unready")) for h in r.history] == [True, False, False, False]
    assert all(h["passed"] is False for h in r.history)


def test_gate_no_neighbors_group_does_not_stop_the_round(monkeypatch):
    e = make(monkeypatch)
    e.drivers["r1"].neighbors = {"default": {}}                             # sorted first, empty every round
    e.drivers["r2"].neighbors = {"default": {"10.0.12.1": "active"}}
    a, b = leak("a", timeout=9), leak("b", node="r2", timeout=6)
    blocked = gate(e, [a, b])
    assert set(blocked) == {id(b)}
    assert [x[2] for x in e.drivers["r2"].calls] == [0.0, 3.0, 6.0]


def test_run_scenario_gate_ignores_sessions_a_top_level_check_expects_down(monkeypatch):
    """run() hands the top-level checks to each scenario: a session a top-level bgp_session check expects
    down doesn't hold the scenario's BGP gate."""
    e = _r1_with_another_session(monkeypatch, "active")
    down = chk("bgp_session", "down", neighbor="10.0.13.3", state="down")
    sc = Scenario("s", [Fault("link_down", "r1", "eth1")], [leak("[s] neg", node="r1", timeout=20)])
    rep = e.run([down], [sc], settle=10, hold=10)
    assert rep.status == "passed" and all(r.passed for r in rep.results)
    assert any(c[0] == "routes" for c in e.drivers["r1"].calls)       # the scenario's check was evaluated


def test_run_scenario_gate_skips_a_node_whose_positive_checks_never_got_state(monkeypatch):
    """As at the top level: a scenario node whose positive checks never got usable state is not gated."""
    e = make(monkeypatch)
    e.drivers["r1"].neighbors = {"default": {"10.0.13.3": "active", "10.0.14.4": "active"}}
    e.drivers["r1"].routes_ = {}                                         # every route read fails: unready
    pos = route("pos", node="r1", timeout=9)
    neg = chk("bgp_session", "neg", node="r1", neighbor="10.0.13.3", state="down", timeout=30)
    sc = Scenario("s", [Fault("inject_routes", "r2", prefixes=["10.66.0.0/16"])], [pos, neg])
    results = {r.check.name: r for r in direct(e, sc)}
    assert results["pos"].passed is False and results["pos"].samples_unready == results["pos"].attempts
    assert results["neg"].passed is True


def test_run_scenario_holds_post_convergence_checks_for_its_hold(monkeypatch):
    """The scenario's hold applies to its post-convergence checks: settle to t=10, the gate releases at 13,
    the leak comes 15 s into the hold. Caught with hold=20, not with 10."""
    for hold, caught in ((20, True), (10, False)):
        e = make(monkeypatch)
        e.drivers["r3"].neighbors = up("10.0.23.2")
        e.drivers["r3"].routes_ = {"default": lambda t, p: t >= 13 + 15}
        [r] = direct(e, Scenario("s", [Fault("link_down", "r1", "eth1")], [leak("neg", node="r3", timeout=30)]),
                     hold=hold)
        assert r.passed is not caught


def test_run_scenario_far_end_without_a_driver(monkeypatch):
    """A host at the far end of a downed link that no driver can read has nothing to watch; the scenario
    goes on and its checks are judged."""
    e = make(monkeypatch)
    e.drivers["r1"].neighbors = {"default": {}}

    def driver_for(n):
        if n == "r2":
            raise DriverError("cannot detect driver for node r2")
        return e.drivers[n]

    results = direct(e, Scenario("s", [Fault("link_down", "r1", "eth1")], [route("x", node="r3")]),
                     driver_for=driver_for)
    assert [r.passed for r in results] == [True]
    assert e.lab.link_events() == [("r1", "eth1", False), ("r1", "eth1", True)]


def test_run_scenario_gate_warning_is_added_to_each_check(monkeypatch):
    """A scenario node that reports no BGP neighbors up to the cap: its post-convergence checks go ahead,
    each with the gate's warning added to its own detail. The verdict is unchanged."""
    def scenario():
        return Scenario("s", [Fault("link_down", "r1", "eth1")], [leak("neg", node="r3", timeout=12)])

    e = make(monkeypatch)                                                  # r3 reports no neighbors
    e.drivers["r3"].routes_ = {"default": never}
    [r] = direct(e, scenario())
    ref_env = make(monkeypatch)
    ref_env.drivers["r3"].neighbors = up("10.0.23.2")
    ref_env.drivers["r3"].routes_ = {"default": never}
    [ref] = direct(ref_env, scenario())
    assert r.passed and ref.passed
    assert r.detail != ref.detail and r.detail.startswith(ref.detail)
    assert e.results[0].detail == r.detail



# ----------------------------------------------------------------- advertisement intervals stretch the windows

def test_a_leak_slowed_by_a_peers_advertisement_interval_is_still_seen(monkeypatch):
    """0.3.2 multi-vendor audit: r2 sends to r1 at most every 60 s (its advertisement interval), so a leak can
    reach r1 at t=45 s, after the default settle and hold (10 s each): the negative check sampled a prefix
    count stable at 0 and passed. The windows stretch to the longest interval any session reports."""
    slow = {"default": {"10.0.12.1": ("established", {"ipv4-unicast": 3}, 60.0)}}
    e = make(monkeypatch, r1={"neighbors": up("10.0.12.2"), "routes": {"default": lambda t, p: t >= 45}},
             r2={"neighbors": slow, "routes": {"default": always}})
    rep = e.run([leak("neg")], settle=10, hold=10)
    assert rep.status == "failed" and not by_name(rep)["neg"].passed
    assert any("advertisement interval" in line and "60" in line for line in e.logs)


def test_short_advertisement_intervals_leave_the_windows_alone(monkeypatch):
    e = make(monkeypatch, r1={"neighbors": up("10.0.12.2"), "routes": {"default": never}})
    rep = e.run([leak("neg")], settle=10, hold=10)
    assert rep.status == "passed" and not any("advertisement interval" in line for line in e.logs)
# ----------------------------------------------------------------------------------------------- never testable

def _bgpd_off_everywhere(monkeypatch):
    nodes = ("r1", "r2", "r3")
    return make(monkeypatch, **{n: {"neighbors_error": DriverError("bgpd is not running"),
                                    "routes": {"default": never}} for n in nodes})


def test_a_lab_that_never_reached_a_testable_state_is_inconclusive_with_scenarios_too(monkeypatch):
    """bgpd off on every node: the main checks already show the lab never gave usable state, so the run is
    inconclusive (exit 3) whether or not the file has scenarios; no fault is applied to a lab that never
    converged, and the scenario's snapshot never gets to stop it with exit 2."""
    checks = [chk("bgp_session", "s", neighbor="10.0.12.2", timeout=9), route("r", timeout=9)]
    plain = _bgpd_off_everywhere(monkeypatch).run(checks, settle=0, hold=0)
    assert plain.status == "inconclusive" and plain.exit_code == 3
    e = _bgpd_off_everywhere(monkeypatch)
    # as in examples/frr-bgp: the scenario faults and checks r1, a node the main checks show never gave state
    sc = Scenario("s", [Fault("link_down", "r1", "eth1")], [route("[s] x")])
    rep = e.run(checks, [sc], settle=0, hold=0)
    assert rep.status == "inconclusive" and rep.exit_code == 3 and not rep.error
    assert rep.inconclusive_reason == plain.inconclusive_reason
    assert e.lab.link_events() == [] and e.injections == []
    assert [r.check.name for r in rep.results] == ["s", "r"]
    assert any("scenario" in line and "skipped" in line for line in e.logs)


def test_unreadable_snapshot_after_a_readable_failure_is_still_an_error(monkeypatch):
    """Only a lab that never gave usable state skips its scenarios. A main phase that failed on readable
    state is a finding, and the scenario's unreadable snapshot still stops the run with exit 2 naming the node."""
    e = make(monkeypatch, r1={"neighbors": up("10.0.12.2"), "routes": {"default": never}},
             r2={"neighbors_error": DriverError("bgpd is not running"), "routes": {"default": never}})
    sc = Scenario("s", [Fault("link_down", "r1", "eth1")], [route("[s] x", node="r3")])
    rep = e.run([route("r", timeout=9)], [sc], settle=0, hold=0)
    assert rep.status == "error" and rep.exit_code == 2 and "r2" in rep.error
    assert e.lab.link_events() == []


def test_scenarios_on_nodes_that_gave_state_still_run_after_an_unready_main_phase(monkeypatch):
    """0.3.2 cold review, finding 2: the main checks are all on r1, which never gives state, but the scenario
    faults r2 and checks r3, both readable. Its readable failure is a finding (exit 1), not inconclusive."""
    e = make(monkeypatch, r1={"neighbors_error": DriverError("bgpd is not running"), "routes": {"default": never}},
             r2={"neighbors": up("10.0.12.1"), "routes": {"default": always}},
             r3={"neighbors": up(), "routes": {"default": never}})
    sc = Scenario("s", [Fault("link_down", "r2", "eth2")], [route("[s] x", node="r3", timeout=9)])
    main = [chk("bgp_session", "s", neighbor="10.0.12.2", timeout=9)]
    assert e.run(main, settle=0, hold=0).status == "inconclusive"   # alone, the main phase never got state
    e = make(monkeypatch, r1={"neighbors_error": DriverError("bgpd is not running"), "routes": {"default": never}},
             r2={"neighbors": up("10.0.12.1"), "routes": {"default": always}},
             r3={"neighbors": up(), "routes": {"default": never}})
    rep = e.run(main, [sc], settle=0, hold=0)
    assert rep.status == "failed" and rep.exit_code == 1
    assert ("r2", "eth2", False) in e.lab.link_events()


def test_agent_eval_t10_bgpd_off_everywhere_is_inconclusive_not_an_error(monkeypatch):
    """Agent eval T10 (examples/agent-eval): FRR with bgpd=no on every router. The main checks never read any
    routing state (pings read cleanly: 0 replies), and the scenario faults and checks r1. 0.3.1 stopped at the
    scenario snapshot with status error, which an agent read as a verdict on the change."""
    def dead(t):
        return Observation((3, 0), [{"stderr": ""}])
    e = make(monkeypatch, **{n: {"neighbors_error": DriverError("bgpd is not running"), "routes": {},
                                 "ping": dead} for n in ("r1", "r2", "r3")})
    checks = [route("TICKET r2", node="r2", prefix="192.168.11.0/24", timeout=9, protocol="bgp"),
              route("TICKET r3", node="r3", prefix="192.168.11.0/24", timeout=9, protocol="bgp"),
              chk("ping", "TICKET ping", node="r2", target="192.168.11.1", timeout=9),
              chk("bgp_session", "s1", neighbor="10.0.12.2", timeout=9),
              chk("bgp_prefixes", "p1", neighbor="10.0.12.2", min=1, max=10, timeout=9),
              route("r1 route", prefix="192.168.3.0/24", timeout=9, protocol="bgp"),
              chk("ping", "r1 ping", target="192.168.3.1", timeout=9),
              leak("no default", prefix="0.0.0.0/0", timeout=9)]
    sc = Scenario("r1-r2 link fails", [Fault("link_down", "r1", "eth1")],
                  [route("[s] r1 route", prefix="192.168.2.0/24", timeout=9),
                   chk("bgp_session", "[s] down", neighbor="10.0.12.2", state="down", timeout=9)])
    rep = e.run(checks, [sc], settle=0, hold=0)
    assert rep.status == "inconclusive" and rep.exit_code == 3 and not rep.error
    assert e.lab.link_events() == []
    from netdryrun.mcp_server import INCONCLUSIVE, _summary
    assert _summary(rep, None)["verdict"] == INCONCLUSIVE


def test_a_bgp_node_with_no_neighbors_at_the_cap_fails_its_post_convergence_checks(monkeypatch):
    """0.3.2 multi-vendor audit (Grok; the 0.3.1 'remaining limit'): r1's BGP config never loads, so it answers
    with no neighbors at all. Its leak guards would pass on the empty table. The file says r1 runs BGP (a
    `protocol: bgp` route check and a prefix-count check), so at the cap its post-convergence checks are not
    evaluated: failed, every sample unready, never passed."""
    e = make(monkeypatch, r1={"neighbors": up(), "routes": {"default": never}})
    checks = [leak("leak", protocol="bgp", timeout=24),
              chk("bgp_prefixes", "max", neighbor="10.0.12.2", max=3, timeout=12)]
    rep = e.run(checks, settle=10, hold=10)
    assert rep.status != "passed" and rep.exit_code != 0
    r = by_name(rep)["leak"]
    assert not r.passed and r.detail.startswith("not evaluated: r1 reported no BGP neighbors")
    assert r.attempts and r.samples_unready == r.attempts
    assert rep.status == "inconclusive"   # nothing anywhere gave usable state


def test_a_bgp_node_with_no_neighbors_beside_a_working_node_is_a_failure(monkeypatch):
    e = make(monkeypatch, r1={"neighbors": up(), "routes": {"default": never}},
             r2={"neighbors": up("10.0.12.1"), "routes": {"default": always}})
    rep = e.run([leak("leak", protocol="bgp", timeout=24), route("r2 ok", node="r2", timeout=24)], settle=10, hold=10)
    assert rep.status == "failed" and rep.exit_code == 1   # r2 shows a working network: a finding, not inconclusive


def test_a_node_without_bgp_checks_is_still_released_at_the_cap(monkeypatch):
    # a static-routing node (no BGP check on it anywhere) may answer with no neighbors for good
    e = make(monkeypatch, r1={"neighbors": up(), "routes": {"default": never}})
    assert e.run([leak("neg", timeout=24)], settle=10, hold=10).status == "passed"


@pytest.mark.parametrize("bgp_check", [
    lambda: chk("bgp_session", "s down", neighbor="10.0.12.9", state="down", timeout=24),
    lambda: chk("bgp_prefixes", "max", neighbor="10.0.12.2", max=3, timeout=24),
    lambda: chk("bgp_route", "attr", prefix="192.168.2.0/24", as_path="65002", timeout=24),
    lambda: route("bgp route", prefix="192.168.9.0/24", protocol="BGP", present=False, timeout=24),
], ids=["bgp_session", "bgp_prefixes", "bgp_route", "route-protocol-bgp"])
def test_each_kind_of_bgp_check_marks_its_node_as_running_bgp(monkeypatch, bgp_check):
    # one BGP check of any kind on the node is enough: the plain leak guard beside it is then not evaluated
    e = make(monkeypatch, r1={"neighbors": up(), "routes": {"default": never}, "paths": {"default": lambda t, p: []}})
    rep = e.run([leak("plain leak guard", timeout=24), bgp_check()], settle=0, hold=0)
    assert by_name(rep)["plain leak guard"].detail.startswith("not evaluated: r1 reported no BGP neighbors")


def test_the_no_neighbors_result_is_a_complete_failed_result(monkeypatch):
    e = make(monkeypatch, r1={"neighbors": up(), "routes": {"default": never}})
    rep = e.run([leak("leak", protocol="bgp", timeout=240)], settle=0, hold=0)
    r = by_name(rep)["leak"]
    assert r.passed is False and r.samples_passed == 0 and r.evidence == []
    assert isinstance(r.duration, float) and r.duration >= 240
    assert iso(r.started)
    assert len(r.history) == 50 and r.attempts > 50 and r.samples_unready == r.attempts   # last 50 kept, all counted
    assert all(h.get("unready") for h in r.history)


# ------------------------------------------------------------------- a config the NOS rejected is never a pass

def test_a_rejected_config_line_makes_the_run_an_error_never_a_pass(monkeypatch):
    """Live repro (FRR 10.4.1): a misspelled change line was skipped at boot and every check passed. Every
    check passing on a node whose config didn't load cleanly is status error (exit 2), naming the node and
    the line."""
    e = make(monkeypatch, r1={"neighbors": up("10.0.12.2"), "routes": {"default": never}})
    clean = e.lab.boot_log
    log = "[45|bgpd] sending configuration\nline 18: % Unknown command[31]:   neighbor 10.0.12.1 default-orignate\n"
    e.lab.boot_log = lambda node: ExecResult([], 0, log, "") if node == "r2" else clean(node)
    rep = e.run([leak("neg")], settle=10, hold=10)
    assert rep.status == "error" and rep.exit_code == 2
    assert "r2" in rep.error and "default-orignate" in rep.error
    assert by_name(rep)["neg"].passed                       # the results are kept as evidence
    assert rep.environment["nodes"]["r2"]["config_load"] == [
        "line 18: neighbor 10.0.12.1 default-orignate (Unknown command)"]
    assert rep.environment["nodes"]["r1"]["config_load"] == "clean"


def test_a_driver_that_cannot_verify_the_load_says_so(monkeypatch):
    e = make(monkeypatch, r1={"neighbors": up("10.0.12.2"), "routes": {"default": never}})
    e.lab.nodes["r3"] = Node("r3", "clab-t-r3", "juniper_cjunosevolved", "cjunosevolved:25.2R1.8-EVO")
    e.drivers["r3"].name = "junos"
    rep = e.run([leak("neg")], settle=10, hold=10)
    assert rep.status == "passed"
    assert rep.environment["nodes"]["r3"]["config_load"] == "not verified on junos"


def test_the_report_names_each_nodes_image_digest_and_nos_version(monkeypatch):
    """A verdict is tied to what ran: the image by digest (a tag can move) and the version the NOS reports. Not
    readable is null, never a guess."""
    e = make(monkeypatch, r1={"neighbors": up("10.0.12.2"), "routes": {"default": always}})
    e.drivers["r3"].nos_version = lambda: None
    e.lab.image_digest = lambda image: None
    rep = e.run([route("pos")])
    nodes = rep.environment["nodes"]
    assert nodes["r1"]["nos_version"] == "FRRouting 10.4.1_git" and nodes["r3"]["nos_version"] is None
    assert all(n["image_digest"] is None for n in nodes.values())
def test_the_fault_wait_names_every_session_still_up_even_after_an_unreadable_node(monkeypatch):
    """0.3.3 adversarial review (mutant _wait_fault_visible_20): an unreadable node must not stop the scan, so
    the error names a later node whose session over the downed link is still established."""
    clock = Clock()
    monkeypatch.setattr(runner, "_clock", clock)
    monkeypatch.setattr(runner, "_sleep", clock.sleep)
    a = Drv(clock, neighbors_error=DriverError("vtysh timed out"))
    b = Drv(clock, neighbors={"default": {"10.0.12.1": "established"}})
    sc = Scenario("s", [Fault("link_down", "r1", "eth1")], [route("x")])
    with pytest.raises(LabError) as e:
        runner._wait_fault_visible([("r1", "default", "10.0.12.2"), ("r2", "default", "10.0.12.1")],
                                   {"r1": a, "r2": b}.__getitem__, 9, sc)
    assert "r1: BGP state unreadable" in str(e.value) and "r2 -> 10.0.12.1" in str(e.value)
