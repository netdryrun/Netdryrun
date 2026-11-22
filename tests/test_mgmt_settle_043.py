"""prepare_linux deletes Docker's defaults before it judges a routing protocol's route over them (oracle FP-043-MGMTNH).

The real `mgmt.prepare_linux` runs on the live FRR 10.4.1 captures of corpus v1 case 19's lab (tests/fixtures/frr_mgmtnh,
t1-t6), replayed by the guards' fake (tests/test_oracle_guards_fp_043_mgmtnh.py): Docker's defaults are deleted by the
product's own commands, and pe1's table then follows the capture on a clock moved by each `docker exec` and each sleep.

- t1-t4 (up1's default is there): the route moves to eth2; the run goes on, and the record and log name the route.
- t5, t6 and t3's extra (no lab default): FRR keeps the route on eth0; a run error after exactly the bound.
- Docker's default back with the route (t1's extra, the default re-added by hand): a run error at once, no wait.
- A route that can't have ridden on Docker's default (static, FRR static, another table, a multipath leg, a next hop
  that isn't the gateway, no Docker default of its family): a run error before anything is deleted.
"""
from __future__ import annotations

import pytest

from netdryrun import mgmt
from netdryrun.lab import ExecResult, LabError
from netdryrun.mgmt import ManagementPathError
from test_oracle_guards_fp_043_mgmtnh import (DOCKER4, DOCKER6, ROUTE_OUT, ReplayLab, lines, load, pe1_before,
                                              samples, without)

WHY = ("It resolved its next hop only through Docker's default route, and the node kept it on the management network "
       "after that route was deleted: the lab has no path of its own for it")


def replay(rows: list) -> callable:
    """The IPv4 table s seconds after the IPv4 delete: the last sample taken by then (the first one before any)."""
    return lambda s: ([v4 for t, v4 in rows if t <= s] or [rows[0][1]])[-1]


def timed_rows(trial: str) -> list:
    """t4: the node's own reads after its delete (stamped by /proc/uptime), then the 0.5 s samples that followed."""
    p = load(trial, "answers.json")["timed delete"]
    t0 = float(next(x for x in p["marks"] if x.startswith("@del4")).split()[1])
    reads = [(round(float(s) - t0, 3), p["answers"][i]) for s, i in p["reads"]]
    return reads + [(t + reads[-1][0], v4) for t, v4, _ in samples(trial)]


def case19(trial: str) -> ReplayLab:
    b = pe1_before(trial)
    rows = timed_rows(trial) if trial == "t4" else [(t, v4) for t, v4, _ in samples(trial)]
    return ReplayLab("pe1", load(trial, "inspect_pe1.json"), b["ip -4 route show table all"],
                     b["ip -6 route show table all"], after=replay(rows))


def run(lab: ReplayLab) -> tuple[mgmt.Mgmt, list[str], str | None]:
    m = mgmt.docker_mgmt(lab, lab.node)
    logs: list[str] = []
    try:
        mgmt.prepare_linux(lab, m, logs.append, lab.sleep)
    except ManagementPathError as e:
        return m, logs, str(e)
    return m, logs, None


@pytest.mark.parametrize("trial", ["t1", "t2", "t3", "t4"])
def test_the_route_leaves_with_dockers_default_and_the_run_goes_on(trial):
    lab = case19(trial)
    m, logs, err = run(lab)
    assert err is None, err
    assert m.removed == [DOCKER4, DOCKER6] and m.left == [ROUTE_OUT] and m.readded == []
    assert ROUTE_OUT not in lines(lab.table(4)) and DOCKER4 not in lines(lab.table(4))
    assert lab.slept <= mgmt.SETTLE_WAIT
    assert [x for x in logs if "left the management network" in x] == [
        f"pe1: left the management network once Docker's default route was removed: {ROUTE_OUT} "
        f"(after {lab.slept:g}s)"]
    assert mgmt.describe(m, "linux") == (f"removed: {DOCKER4}; {DOCKER6}; left the management network once it was "
                                         f"removed: {ROUTE_OUT}")


def test_a_read_inside_zebras_reresolution_waits_one_step():
    """t4 read with no exec delay: the first read after the delete still has the route on eth0 (0.07 s), one 0.5 s
    step later it is on eth2."""
    lab = case19("t4")
    lab.exec_root = _no_delay(lab)
    m, _, err = run(lab)
    assert err is None, err
    assert lab.slept == mgmt.SETTLE_STEP and m.left == [ROUTE_OUT]


def _no_delay(lab):
    real = lab.exec_root

    def exec_root(node, cmd, timeout=60):
        r = real(node, cmd, timeout)
        lab.clock -= 0.1
        return r
    return exec_root


def stale(trial: str) -> ReplayLab:
    if trial == "t3":   # t3's extra: up1 stopped its default after deploy, then Docker's default deleted
        rows = [(t, v4) for t, v4, _ in samples("t3", "samples_no_lab_default_after_delete.json")]
        b = pe1_before("t3")
        return ReplayLab("pe1", load("t3", "inspect_pe1.json"), DOCKER4 + " \n" + rows[0][1],
                         b["ip -6 route show table all"], after=replay(rows))
    return case19(trial)


@pytest.mark.parametrize("trial", ["t5", "t6", "t3"])
def test_a_route_the_node_keeps_on_management_is_a_run_error_after_the_bound(trial):
    lab = stale(trial)
    m, logs, err = run(lab)
    assert err == mgmt._offending("pe1", mgmt.parse_ip_route(ROUTE_OUT, 4),
                                  f"{mgmt.SETTLE_WAIT:g}s after deleting Docker's default route") + ". " + WHY
    assert lab.slept == mgmt.SETTLE_WAIT == 10.0
    assert m.removed == [DOCKER4, DOCKER6] and m.left == []
    assert not any("left the management network" in x for x in logs)


def test_dockers_default_back_with_the_route_is_a_run_error_at_once():
    """t1's extra: Docker's IPv4 default put back by hand pulls the route back onto eth0 at the first read."""
    rows = [(t, v4) for t, v4, _ in samples("t1", "samples_readded.json")]
    b = pe1_before("t1")
    lab = ReplayLab("pe1", load("t1", "inspect_pe1.json"), b["ip -4 route show table all"],
                    b["ip -6 route show table all"], after=replay(rows))
    m, _, err = run(lab)
    assert err is not None and err.startswith(
        f"pe1 has a route out over the management network (after deleting Docker's default route): {DOCKER4}; "
        f"{ROUTE_OUT}."), err
    assert lab.slept == 0 and m.left == []


def test_a_static_that_appears_during_the_wait_is_a_run_error_at_once():
    static = "10.77.0.0/16 via 172.20.20.1 dev eth0 proto static"
    rows = [(t, v4 + "\n" + static) for t, v4, _ in samples("t5")]
    b = pe1_before("t5")
    lab = ReplayLab("pe1", load("t5", "inspect_pe1.json"), b["ip -4 route show table all"],
                    b["ip -6 route show table all"], after=replay(rows))
    m, _, err = run(lab)
    assert err is not None and static in err and "after deleting Docker's default route)" in err, err
    assert lab.slept == 0 and m.left == []


def test_an_unreadable_table_during_the_wait_is_a_run_error():
    lab = stale("t5")
    real = lab.exec_root

    def exec_root(node, cmd, timeout=60):
        if 4 in lab.deleted and cmd[2:] == ["route", "show", "table", "all"]:
            return ExecResult(cmd, 1, "", "Cannot open netlink socket\n")
        return real(node, cmd, timeout)
    lab.exec_root = exec_root
    with pytest.raises(LabError, match="its routes can't be read"):
        mgmt.prepare_linux(lab, mgmt.docker_mgmt(lab, "pe1"), lambda _: None, lab.sleep)
    assert lab.slept == 0


NOT_DOCKERS = [
    "198.51.100.0/24 via 172.20.20.1 dev eth0 proto static",            # a user's static
    "198.51.100.0/24 nhid 7 via 172.20.20.1 dev eth0 proto 196 metric 20",   # FRR's static
    "198.51.100.0/24 via 172.20.20.1 dev eth0 proto kernel",
    "198.51.100.0/24 via 172.20.20.1 dev eth0 proto boot",
    "198.51.100.0/24 via 172.20.20.1 dev eth0",
    "198.51.100.0/24 via 172.20.20.1 dev eth0 proto zebra",
    "198.51.100.0/24 nhid 7 via 172.20.20.9 dev eth0 proto bgp metric 20",   # a BGP peer on the management subnet
    "198.51.100.0/24 nhid 7 via 172.20.20.1 dev eth0 table 10 proto bgp metric 20",
    "198.51.100.0/24 nhid 7 proto bgp metric 20",                            # no device
    "198.51.100.0/24 proto bgp metric 20\n\tnexthop via 172.20.20.1 dev eth0 weight 1\n"
    "\tnexthop via 10.0.2.2 dev eth2 weight 1",                             # a multipath leg
    "unreachable 198.51.100.0/24 dev eth0 proto bgp metric 20",
]


@pytest.mark.parametrize("route", NOT_DOCKERS)
def test_a_route_that_cant_have_ridden_on_dockers_default_ends_the_run_before_any_delete(route):
    b = pe1_before("t1")
    v4 = without(b["ip -4 route show table all"], ROUTE_OUT) + "\n" + route
    lab = ReplayLab("pe1", load("t1", "inspect_pe1.json"), v4, b["ip -6 route show table all"])
    m, _, err = run(lab)
    assert err is not None and err.startswith(
        "pe1 has a route out over the management network (before the checks): "), err
    assert lab.deleted == {} and m.removed == [] and lab.slept == 0


def test_a_bgp_route_with_no_docker_default_of_its_family_ends_the_run_before_any_delete():
    b = pe1_before("t1")
    for v4, v6 in ((without(b["ip -4 route show table all"], DOCKER4), b["ip -6 route show table all"]),
                   (b["ip -4 route show table all"].replace("default via 172.20.20.1 dev eth0",
                                                            "default via 172.20.20.1 dev eth0 proto static"),
                    b["ip -6 route show table all"])):
        lab = ReplayLab("pe1", load("t1", "inspect_pe1.json"), v4, v6)
        m, _, err = run(lab)
        assert err is not None and ROUTE_OUT in err and "(before the checks)" in err, err
        assert lab.deleted == {} and m.removed == []


@pytest.mark.parametrize("proto", ["bgp", "ospf", "isis", "186", "188"])
def test_each_routing_protocol_name_and_number_is_waited_out(proto):
    line = ROUTE_OUT.replace("proto bgp", f"proto {proto}")
    b = pe1_before("t1")
    v4 = b["ip -4 route show table all"].replace(ROUTE_OUT, line)
    lab = ReplayLab("pe1", load("t1", "inspect_pe1.json"), v4, b["ip -6 route show table all"],
                    after=lambda s: without(without(v4, DOCKER4), line) if s >= 1.0 else without(v4, DOCKER4))
    m, _, err = run(lab)
    assert err is None, err
    assert m.left == [line] and lab.slept == 1.0
