"""Oracle FP-043-MGMTNH: a BGP route that reaches the management network only through Docker's default ends the run.

Corpus v1 case 19 (next-hop-self removed on pe2 toward pe1; expected unsafe) ends in a run error for all three
strategies, live on FRR 10.4.1 (tests/fixtures/frr_mgmtnh, six fresh deploys):

    pe1 has a route out over the management network (before the checks): 198.51.100.0/24 nhid 7 via 172.20.20.1 dev
    eth0 proto bgp metric 20. ...

pe1 learns 198.51.100.0/24 from pe2 with peer1's address 10.0.4.2 as next hop, which no lab route covers. pe1 resolves
next hops via a default ("Resolve via default: on" in `show ip nht`), and while Docker's default is there zebra prefers
it (kernel, distance 0) over up1's BGP default (distance 20): `10.0.4.2 resolved via kernel, prefix 0.0.0.0/0, via
172.20.20.1, eth0`. `mgmt.prepare_linux` reads the routes before it deletes Docker's default and stops on that route,
although it exists only because of the default the product is about to delete.

What the lab did once Docker's default was deleted (the same `ip -4 route del default via 172.20.20.1 dev eth0` and
`ip -6 ...` as `mgmt._delete_linux`):
- t1, t2, t3 (deleted by `mgmt._delete_linux` itself, then `ip route show table all` every 0.5 s for 60 s): at the
  first read after the delete returned, and for all 60 s, up1's BGP default is in the kernel and 198.51.100.0/24 is via
  10.0.2.2 dev eth2, inside the lab. Nothing is left on eth0 but the connected management subnet.
- t4 (deleted inside the node, the whole table read in a tight loop stamped with /proc/uptime, 10 ms): the route is
  still on eth0 for about 0.07 s (up1's default enters the kernel after about 0.01 s), then moves to eth2 for good.
- t5, t6 (up1 told to stop originating its default first, so nothing in the lab covers 10.0.4.2): the route stays on
  eth0 for the whole 60 s; that state is the guards' (tests/test_oracle_guards_fp_043_mgmtnh.py), not this oracle's.

So for case 19 the run error is the lab's, not the change's: in production there is no Docker default, and pe1 would
resolve the route over up1's default, exactly as the lab does a moment after the delete. The expected verdict comes
from the checks that follow (customer reaches peer), not from a run error.

The red tests run `mgmt.prepare` on a fake lab that answers with the captured tables. Docker's defaults are deleted by
the commands the product sends; after the IPv4 delete pe1's table follows the capture on a clock that moves with every
`docker exec` (EXEC_S) and every sleep the code asks prepare's `sleep` for. Every other command is refused.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from fakes import UnexpectedCommand
from netdryrun import mgmt
from netdryrun.lab import ExecResult, Node
from netdryrun.mgmt import ManagementPathError

ROOT = Path(__file__).resolve().parents[3]
FX = ROOT / "tests" / "fixtures" / "frr_mgmtnh"
NODE = "pe1"
ROUTE_OUT = "198.51.100.0/24 nhid 7 via 172.20.20.1 dev eth0 proto bgp metric 20"
DOCKER4 = "default via 172.20.20.1 dev eth0"
DOCKER6 = "default via 3fff:172:20:20::1 dev eth0 metric 1024 pref medium"
EXEC_S = 0.1          # one `docker exec` (live: mgmt._delete_linux's two deletes took 0.21 s and 0.26 s)
SLEEP_LIMIT = 600.0   # a fake clock that runs away is a broken fix, never a hang


def load(trial: str, name: str):
    return json.loads((FX / trial / name).read_text(encoding="utf-8"))


def samples(trial: str, name: str = "samples_after_delete.json") -> list[tuple[float, str, str]]:
    p = load(trial, name)
    return [(t, p["tables"][i4], p["tables"][i6]) for t, i4, i6 in p["samples"]]


def timed(trial: str) -> list[tuple[float, str]]:
    """The node's own loop after its IPv4 delete: (seconds after the delete by /proc/uptime, the IPv4 table)."""
    p = load(trial, "answers.json")["timed delete"]
    t0 = float(next(m for m in p["marks"] if m.startswith("@del4")).split()[1])
    return [(round(float(s) - t0, 3), p["answers"][i]) for s, i in p["reads"]]


def without(text: str, line: str) -> str:
    return "\n".join(ln for ln in text.split("\n") if ln.strip() != line)


class ReplayLab:
    """pe1 as the capture shows it. `before` answers until Docker's IPv4 default is deleted; from then on `after(s)`
    gives the IPv4 table s seconds after that delete. The IPv6 table loses Docker's IPv6 default when it is deleted
    (the live IPv6 tables after the delete are exactly that)."""

    def __init__(self, trial: str, before4: str, before6: str, after, exec_s: float = EXEC_S, addr: str = ""):
        self.nodes = {NODE: Node(NODE, "clab-ndr-corpus-pe1", "linux", "quay.io/frrouting/frr:10.4.1")}
        self.inspect = load(trial, "inspect_pe1.json")
        self.before = {4: before4, 6: before6}
        self.after = after
        self.exec_s = exec_s
        self.addr = addr
        self.clock = 0.0
        self.slept = 0.0
        self.deleted: dict[int, float] = {}
        self.calls: list[tuple] = []

    def docker_inspect(self, node):
        return self.inspect

    def sleep(self, s: float) -> None:
        self.slept += s
        self.clock += s
        if self.slept > SLEEP_LIMIT:
            raise RuntimeError(f"prepare slept {self.slept:g}s in all: no bound")

    def table(self, fam: int) -> str:
        if fam == 4:
            return self.after(self.clock - self.deleted[4]) if 4 in self.deleted else self.before[4]
        return without(self.before[6], DOCKER6) if 6 in self.deleted else self.before[6]

    def exec_root(self, node, cmd, timeout=60):
        self.calls.append((node, tuple(cmd)))
        self.clock += self.exec_s
        cmd = list(cmd)
        if node == NODE and cmd[:2] == ["sysctl", "-w"] and cmd[2].endswith(".accept_ra=0"):
            return ExecResult(cmd, 0, cmd[2].replace("=", " = ") + "\n", "")
        if node == NODE and cmd == ["ip", "addr", "show"] and self.addr:
            return ExecResult(cmd, 0, self.addr, "")
        if node == NODE and cmd[0] == "ip" and cmd[1] in ("-4", "-6"):
            fam = int(cmd[1][1])
            if cmd[2:] == ["route", "show", "table", "all"]:
                return ExecResult(cmd, 0, self.table(fam), "")
            mine = DOCKER4 if fam == 4 else DOCKER6
            via = mine.split()[2]
            if cmd[2:] == ["route", "del", "default", "via", via, "dev", "eth0"]:
                if fam in self.deleted or mine not in [ln.strip() for ln in self.before[fam].split("\n")]:
                    return ExecResult(cmd, 2, "", "RTNETLINK answers: No such process\n")
                self.deleted[fam] = self.clock
                return ExecResult(cmd, 0, "", "")
        raise UnexpectedCommand(" ".join(map(str, cmd)))

    def exec(self, node, cmd, timeout=60, input=None):
        raise UnexpectedCommand(" ".join(map(str, cmd)))


def from_samples(trial: str):
    """t1-t3: the 0.5 s samples began when mgmt._delete_linux returned (delete.json's delete_seconds after the IPv4
    delete began); before the first one the first one stands (t4 shows the route settled 0.07 s after the delete)."""
    rows = samples(trial)
    start = load(trial, "delete.json")["delete_seconds"]

    def after(s: float) -> str:
        hit = [v4 for t, v4, _ in rows if t + start <= s]
        return hit[-1] if hit else rows[0][1]
    return after


def from_timed(trial: str):
    """t4: the node's own reads, by their stamps; after the last one (0.33 s), the 0.5 s samples that followed."""
    reads, rows = timed(trial), samples(trial)
    last = reads[-1][0]

    def after(s: float) -> str:
        if s <= last:
            hit = [v4 for t, v4 in reads if t <= s]
            return hit[-1] if hit else reads[0][1]
        hit = [v4 for t, v4, _ in rows if t + last <= s]
        return hit[-1] if hit else rows[0][1]
    return after


def case19(trial: str, exec_s: float = EXEC_S) -> ReplayLab:
    a = load(trial, "answers.json")["before"]
    pe1 = a[NODE] if NODE in a else a
    return ReplayLab(trial, pe1["ip -4 route show table all"], pe1["ip -6 route show table all"],
                     from_timed(trial) if trial == "t4" else from_samples(trial), exec_s, pe1.get("ip addr show", ""))


def prepare(lab: ReplayLab, logs: list) -> str | None:
    """mgmt.prepare as the runner calls it; the management-path error it raised, or None."""
    try:
        mgmt.prepare(lab, [], log=logs.append, sleep=lab.sleep)
    except ManagementPathError as e:
        return str(e)
    return None


def judged_now(lab: ReplayLab):
    m = lab.management[NODE]
    routes = mgmt.parse_ip_route(lab.table(4), 4) + mgmt.parse_ip_route(lab.table(6), 6)
    return mgmt.classify_linux(routes, m)


@pytest.mark.parametrize("trial", ["t1", "t2", "t3", "t4"])
def test_a_route_over_dockers_default_that_moves_into_the_lab_is_no_run_error(trial):
    """Case 19's state, live: once Docker's default is deleted the route is via up1 (eth2). prepare deletes Docker's
    defaults and lets the lab settle before it judges; the run goes on to its checks."""
    lab = case19(trial)
    logs: list[str] = []
    err = prepare(lab, logs)
    assert err is None, f"{trial}: prepare ended the run on a route that leaves with Docker's default: {err}"
    m = lab.management[NODE]
    assert m.removed == [DOCKER4, DOCKER6], m.removed
    docker, other = judged_now(lab)
    assert (docker, other) == ([], []), (docker, other)
    assert ROUTE_OUT not in lab.table(4) and "via 10.0.2.2 dev eth2" in lab.table(4).split("198.51.100.0/24")[1]


def test_a_read_inside_zebras_reresolution_is_not_the_verdict():
    """t4, read at once after the delete (no time for a `docker exec`): for about 0.07 s the route is still on eth0.
    A faster host or a bigger table gets that read; prepare must wait (with its `sleep`) until the management device
    holds nothing but its own subnet, within a bound, instead of judging the first read after the delete."""
    lab = case19("t4", exec_s=0.0)
    logs: list[str] = []
    err = prepare(lab, logs)
    assert err is None, f"prepare judged the read taken inside zebra's re-resolution: {err}"
    assert judged_now(lab) == ([], [])
    assert 0 < lab.slept <= 30, lab.slept


def test_the_run_record_names_the_route_that_left_the_management_network():
    """A route that was over the management network before the delete and left it after is recorded (the
    environment's management_default for pe1, mgmt.describe), so a reader sees why the run went on."""
    lab = case19("t4")
    err = prepare(lab, [])
    assert err is None, err
    said = mgmt.describe(lab.management[NODE], "linux")
    assert "198.51.100.0/24" in said and said.startswith("removed: " + DOCKER4), said
