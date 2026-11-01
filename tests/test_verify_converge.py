"""The convergence-stable snapshot loop, on a fake clock."""
from dataclasses import replace

import pytest

from netdryrun.verify.converge import Inconclusive, SnapshotUnreadable, stable_snapshot
from netdryrun.verify.frr import CommandFailed, CommandTimedOut
from netdryrun.verify.snapshot import Snapshot, SnapshotError
from verify_helpers import base, path, session


class Clock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t

    def sleep(self, s):
        self.t += s


def seq(*snaps):
    """A collect() that returns the given snapshots (or raises the given exceptions) in turn, then repeats
    the last one."""
    items = list(snaps)

    def collect():
        x = items.pop(0) if len(items) > 1 else items[0]
        if isinstance(x, Exception):
            raise x
        return x
    return collect


def moved(n):
    lab = base()
    lab.path("edge1", "203.0.113.0/24", "10.0.2.2", path(as_path="65002", next_hop="10.0.2.2", med=n))
    return lab.snap()


def run(collect, settle=10, timeout=120):
    clock = Clock()
    return stable_snapshot(collect, settle=settle, timeout=timeout, clock=clock, sleep=clock.sleep), clock


def test_two_identical_snapshots_settle_apart_are_stable():
    a, b = moved(1), moved(2)
    got, clock = run(seq(a, b, b))
    assert got is not None and not isinstance(got, Inconclusive) and got.items() == b.items()
    assert clock.t == 20          # three samples, settle apart


def test_moving_state_is_inconclusive_and_names_what_moved():
    n = iter(range(1000))
    got, clock = run(lambda: moved(next(n)), timeout=60)
    assert isinstance(got, Inconclusive) and got.moving and any("203.0.113.0/24" in m for m in got.moving)
    assert clock.t <= 60


def test_prefix_counts_must_be_stable_too():
    a, b = base(), base()
    s = b.get("edge1", "session", neighbor="10.0.2.2")
    b.session("edge1", "10.0.2.2", replace(s, prefix_counts=(("ipv4-unicast", 9),)))
    assert a.snap().items() == b.snap().items()                    # the diff ignores counts...
    got, _ = run(seq(a.snap(), b.snap(), a.snap(), b.snap()), timeout=35)
    assert isinstance(got, Inconclusive)                           # ...stability doesn't


def test_sessions_stably_down_are_stable():
    lab = base()
    lab.session("edge1", "10.0.9.2", session(None, state="active"))
    got, _ = run(seq(lab.snap()))
    assert not isinstance(got, Inconclusive)


def test_failed_commands_are_retried_then_unreadable():
    good = base().snap()
    got, _ = run(seq(CommandFailed("vtysh: bgpd not up"), CommandFailed("again"), good, good))
    assert not isinstance(got, Inconclusive)
    with pytest.raises(SnapshotUnreadable):
        run(seq(CommandFailed("vtysh: bgpd not up")), timeout=30)


def test_a_command_cut_by_its_time_limit_is_inconclusive_and_named():
    """No route ceiling in verify mode: the snapshot is complete, or the verdict is INCONCLUSIVE naming what was
    cut. A command that keeps hitting its time limit (a table too large to print in time) is a cut."""
    cut = CommandTimedOut("`vtysh -c 'show bgp vrf all ipv4 unicast detail json'` on edge1 did not finish within 120s")
    got, _ = run(seq(cut), timeout=300)
    assert isinstance(got, Inconclusive) and "cut" in got.reason
    assert got.moving == [str(cut)]
    good = base().snap()
    got, _ = run(seq(cut, good, good))                     # once, then complete: no cut
    assert not isinstance(got, Inconclusive)


def test_a_timed_out_command_is_a_cut_not_a_failure():
    from netdryrun.verify.frr import FrrCollector

    def exec_fn(node, argv):
        return 124, "", "timed out after 120s"
    with pytest.raises(CommandTimedOut) as e:
        FrrCollector("edge1", exec_fn).collect()
    assert "show running-config" in str(e.value) and "edge1" in str(e.value)   # the first command it runs


def test_a_stale_path_means_the_lab_has_not_converged():
    """Live (corpus case 06, the after boot): a session restarted while the lab came up, graceful restart kept
    the old path marked stale, and two samples settle apart still matched. A stale path is waiting for its
    session's End-of-RIB: not ready, and INCONCLUSIVE if it never clears."""
    lab = base()
    old = lab.get("edge1", "path", "203.0.113.0/24", neighbor="10.0.2.2")
    lab.path("edge1", "203.0.113.0/24", "10.0.2.2", replace(old, flags=("stale",)))
    stale, good = lab.snap(), base().snap()
    got, _ = run(seq(stale), timeout=60)
    assert isinstance(got, Inconclusive) and any("stale" in x for x in got.moving)
    got, _ = run(seq(stale, stale, good, good))
    assert got == good


def test_schema_errors_stop_at_once():
    calls = []

    def collect():
        calls.append(1)
        raise SnapshotError("unknown field")
    with pytest.raises(SnapshotError):
        run(collect)
    assert len(calls) == 1


def test_a_node_with_an_empty_rib_is_not_ready():
    lab = base()
    for k in [k for k in lab.items["up1"] if k.kind == "rib"]:
        del lab.items["up1"][k]
    got, _ = run(seq(lab.snap()), timeout=40)
    assert isinstance(got, Inconclusive) and any("up1" in m for m in got.moving)


# --- the stability gate can't take a half-converged lab (review finding 8) ----------------------------------

def _no_bgp_yet(node="up1"):
    """bgpd answers but its config isn't loaded yet: connected routes, no sessions, no BGP paths."""
    lab = base()
    lab.drop(node, "session")
    lab.drop(node, "path")
    return lab


def test_a_node_expected_to_run_bgp_is_not_ready_without_bgp_state():
    got, _ = run(seq(_no_bgp_yet().snap()), timeout=40)
    assert isinstance(got, Inconclusive) and any("up1" in m and "BGP" in m for m in got.moving)
    # the same node, not expected to run BGP (no `router bgp` in its config): ready on its RIB
    clock = Clock()
    got = stable_snapshot(seq(_no_bgp_yet().snap()), settle=10, timeout=40, clock=clock, sleep=clock.sleep,
                          bgp_nodes={"cust1", "edge1", "peer1"})
    assert not isinstance(got, Inconclusive)
    # once its sessions come up, the snapshot is taken with them
    full = base().snap()
    got, _ = run(seq(_no_bgp_yet().snap(), _no_bgp_yet().snap(), full, full))
    assert not isinstance(got, Inconclusive) and got.items() == full.items()


def test_sessions_held_in_active_are_stably_not_established():
    """Held in active (raw state moving between active and connect) for 2 samples: stable, and the before
    snapshot is then an unhealthy baseline (see test_verify_run)."""
    a, b = base(), base()
    a.session("edge1", "10.0.9.2", session(None, state="active"))
    b.session("edge1", "10.0.9.2", session(None, state="connect"))
    got, clock = run(seq(a.snap(), b.snap(), a.snap()))
    assert not isinstance(got, Inconclusive) and clock.t == 10
    from netdryrun.verify.engine import baseline_problems
    assert baseline_problems(got)


def test_an_update_later_than_settle_is_missed_so_settle_must_exceed_it():
    """Documented limit: two snapshots `settle` apart can't see an update that arrives later (an MRAI or
    update-delay longer than settle). With settle above that delay, the update is in the snapshot."""
    early, late = base().snap(), moved(7)
    def collect_at(clock):
        return lambda: early if clock.t < 25 else late
    clock = Clock()
    got = stable_snapshot(collect_at(clock), settle=10, timeout=120, clock=clock, sleep=clock.sleep)
    assert got.items() == early.items()                       # settle 10 < the 25 s delay: missed
    clock = Clock()
    got = stable_snapshot(collect_at(clock), settle=30, timeout=120, clock=clock, sleep=clock.sleep)
    assert got.items() == late.items()                        # settle 30 > the delay: seen


def test_expects_bgp_reads_the_nodes_config():
    from netdryrun.verify.run import expects_bgp
    files = {("r1", "/etc/frr/frr.conf"): "hostname r1\nrouter bgp 65001\n neighbor 10.0.0.2 remote-as 65002\n",
             ("r2", "/etc/frr/frr.conf"): "hostname r2\nrouter ospf\n"}

    def exec_fn(node, argv):
        text = files.get((node, argv[1]))
        return (0, text, "") if text is not None else (1, "", "No such file")
    assert expects_bgp(exec_fn, "r1") and not expects_bgp(exec_fn, "r2") and expects_bgp(exec_fn, "r3")


def test_settle_stretches_to_the_longest_advertisement_interval_a_node_reports():
    """0.3.2 multi-vendor audit, in verify: a node reporting a 60 s advertisement interval can send a route up to
    60 s after the lab looks settled; settle stretches to that interval plus a margin, so the late route is in
    the snapshot (with settle 10 it was missed)."""
    from dataclasses import replace as dc_replace

    def slow(snap):
        return Snapshot({n: dc_replace(ns, adv_interval=60.0 if n == "edge1" else 0.0) for n, ns in snap.nodes.items()},
                        snap.unobserved)
    early, late = slow(base().snap()), slow(moved(7))
    clock = Clock()
    logs = []
    got = stable_snapshot(lambda: early if clock.t < 50 else late, settle=10, timeout=300, clock=clock,
                          sleep=clock.sleep, log=logs.append)
    assert got.items() == late.items()
    assert any("advertisement interval" in x and "edge1" in x for x in logs)
