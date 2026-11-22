"""Guards for oracle FP-043-MGMTNH (tests/oracles/FP-043-MGMTNH): what must stay a run error, or keep working, once
prepare lets a route that left with Docker's default go. They pass before the fix and after it.

All states are live FRR 10.4.1 captures (tests/fixtures/frr_mgmtnh, corpus v1 case 19's lab; SOURCES.yml), served by
the same replay fake as the oracle: Docker's defaults are deleted by the product's own commands, and after the IPv4
delete pe1's table follows the capture on a clock moved by each `docker exec` and each sleep prepare asks for.

- A user's own route via the management gateway stays after the delete (t1 and t3: a kernel static and an FRR static,
  both still on eth0 15 s later): a run error, and the wait before it is bounded.
- A BGP route still over management after the bound (t5 and t6: up1 sends no default, so nothing in the lab covers the
  next hop, and FRR 10.4.1 kept the route on eth0 for the whole 60 s after the delete, `show ip nht` still saying
  "resolved via kernel, prefix 0.0.0.0/0" with no default left in zebra): a run error, never waited out forever.
- A route that left and is back on eth0 before a ping (t4's route line, back in t4's settled table): the check before
  the ping ends the run and the ping never runs.
- Docker's default back later on a node whose routes are its own (pe2 in t1, live table with Docker's default):
  deleted again before the ping, recorded, and the ping runs.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from fakes import UnexpectedCommand
from netdryrun import mgmt
from netdryrun.drivers.frr import FrrDriver
from netdryrun.lab import ExecResult, Node
from netdryrun.mgmt import ManagementPathError

FX = Path(__file__).parent / "fixtures" / "frr_mgmtnh"
ROUTE_OUT = "198.51.100.0/24 nhid 7 via 172.20.20.1 dev eth0 proto bgp metric 20"
DOCKER4 = "default via 172.20.20.1 dev eth0"
DOCKER6 = "default via 3fff:172:20:20::1 dev eth0 metric 1024 pref medium"
EXEC_S = 0.1
BOUND = 30.0          # the most prepare may sleep before it judges (the oracle's README: settle bound and why)
SLEEP_LIMIT = 600.0


def load(trial: str, name: str):
    return json.loads((FX / trial / name).read_text(encoding="utf-8"))


def samples(trial: str, name: str = "samples_after_delete.json") -> list[tuple[float, str, str]]:
    p = load(trial, name)
    return [(t, p["tables"][i4], p["tables"][i6]) for t, i4, i6 in p["samples"]]


def lines(text: str) -> list[str]:
    return [ln.strip() for ln in text.split("\n")]


def without(text: str, line: str) -> str:
    return "\n".join(ln for ln in text.split("\n") if ln.strip() != line)


class ReplayLab:
    """One node as captured: `before` until Docker's IPv4 default is deleted, then `after(s)`; IPv6 loses Docker's
    default when it is deleted. `now` (when set) overrides both: the table a test puts there later."""

    def __init__(self, node: str, inspect: dict, before4: str, before6: str, after=None):
        self.node = node
        self.nodes = {node: Node(node, f"clab-ndr-corpus-{node}", "linux", "quay.io/frrouting/frr:10.4.1")}
        self.inspect = inspect
        self.before = {4: before4, 6: before6}
        self.after = after or (lambda s: without(before4, DOCKER4))
        self.now: dict[int, str] = {}
        self.clock = self.slept = 0.0
        self.deleted: dict[int, float] = {}
        self.pings: list = []

    def docker_inspect(self, node):
        return self.inspect

    def sleep(self, s: float) -> None:
        self.slept += s
        self.clock += s
        if self.slept > SLEEP_LIMIT:
            raise RuntimeError(f"prepare slept {self.slept:g}s in all: no bound")

    def table(self, fam: int) -> str:
        if fam in self.now:
            return self.now[fam]
        if fam == 4:
            return self.after(self.clock - self.deleted[4]) if 4 in self.deleted else self.before[4]
        return without(self.before[6], DOCKER6) if 6 in self.deleted else self.before[6]

    def exec_root(self, node, cmd, timeout=60):
        self.clock += EXEC_S
        cmd = list(cmd)
        if node == self.node and cmd[:2] == ["sysctl", "-w"] and cmd[2].endswith(".accept_ra=0"):
            return ExecResult(cmd, 0, cmd[2].replace("=", " = ") + "\n", "")
        if node == self.node and cmd[0] == "ip" and cmd[1] in ("-4", "-6"):
            fam = int(cmd[1][1])
            if cmd[2:] == ["route", "show", "table", "all"]:
                return ExecResult(cmd, 0, self.table(fam), "")
            mine = DOCKER4 if fam == 4 else DOCKER6
            if cmd[2:] == ["route", "del", "default", "via", mine.split()[2], "dev", "eth0"]:
                if mine not in lines(self.table(fam)):
                    return ExecResult(cmd, 2, "", "RTNETLINK answers: No such process\n")
                if fam in self.now:
                    self.now[fam] = without(self.now[fam], mine)
                else:
                    self.deleted[fam] = self.clock
                return ExecResult(cmd, 0, "", "")
        raise UnexpectedCommand(" ".join(map(str, cmd)))

    def exec(self, node, cmd, timeout=60, input=None):
        if node == self.node and cmd[0] == "ping":
            self.pings.append(cmd)
            return ExecResult(cmd, 0, "3 packets transmitted, 3 received, 0% packet loss\n", "")
        raise UnexpectedCommand(" ".join(map(str, cmd)))


def pe1_before(trial: str) -> dict:
    b = load(trial, "answers.json")["before"]
    return b["pe1"] if "pe1" in b else b


def prepare(lab: ReplayLab) -> str | None:
    try:
        mgmt.prepare(lab, [], log=lambda _: None, sleep=lab.sleep)
    except ManagementPathError as e:
        return str(e)
    return None


# ------------------------------------------------------------------------------------------- the capture itself

def test_the_capture_holds_what_the_oracle_says():
    for trial in ("t1", "t2", "t3", "t4", "t5", "t6"):
        assert DOCKER4 in lines(pe1_before(trial)["ip -4 route show table all"]), trial
        assert ROUTE_OUT in lines(pe1_before(trial)["ip -4 route show table all"]), trial
        assert ("pe1 has a route out over the management network (before the checks): " + ROUTE_OUT
                in (FX / trial / "corpus_run.txt").read_text(encoding="utf-8")), trial
    for trial in ("t1", "t2", "t3", "t4"):             # up1's default there: the route moved to eth2
        last = samples(trial)[-1][1]
        assert ROUTE_OUT not in lines(last) and any(
            ln.startswith("198.51.100.0/24 nhid") and "via 10.0.2.2 dev eth2 proto bgp" in ln for ln in lines(last))
    for trial in ("t5", "t6"):                         # no lab default: it stayed on eth0 for all 60 s
        assert all(ROUTE_OUT in lines(v4) and DOCKER4 not in lines(v4) for _, v4, _ in samples(trial))
        assert samples(trial)[-1][0] >= 60
        assert "resolved via kernel, prefix 0.0.0.0/0" in load(trial, "answers.json")["after_60s"]["show ip nht"]


# ------------------------------------------------------------------------------------------- still run errors

@pytest.mark.parametrize("trial", ["t1", "t3"])
def test_a_static_route_via_the_management_gateway_that_stays_is_a_run_error(trial):
    """Live: `ip route add 10.77.0.0/16 via 172.20.20.1 dev eth0 proto static` and FRR `ip route 10.78.0.0/16
    172.20.20.1` stay on eth0 with Docker's default gone (15 s of samples). With Docker's default too (its live line,
    as at deploy), prepare must still end the run, naming both, after a bounded wait."""
    statics = samples(trial, "samples_statics.json")
    v4 = statics[0][1]
    assert DOCKER4 not in lines(v4)
    lab = ReplayLab("pe1", load(trial, "inspect_pe1.json"), DOCKER4 + " \n" + v4, pe1_before(trial)[
        "ip -6 route show table all"], after=lambda s: [x for t, x, _ in statics if t <= s][-1] if s >= 0 else v4)
    err = prepare(lab)
    assert err is not None and "10.77.0.0/16 via 172.20.20.1 dev eth0 proto static" in err \
        and "10.78.0.0/16 nhid 7 via 172.20.20.1 dev eth0 proto 196 metric 20" in err, err
    assert lab.slept <= BOUND


@pytest.mark.parametrize("trial", ["t5", "t6"])
def test_a_bgp_route_still_over_management_after_the_bound_is_a_run_error(trial):
    """Live: with no lab default, FRR 10.4.1 kept 198.51.100.0/24 on eth0 for 60 s after Docker's default was deleted.
    prepare may wait, but only up to its bound, and then ends the run naming the route."""
    rows = samples(trial)
    b = pe1_before(trial)
    lab = ReplayLab("pe1", load(trial, "inspect_pe1.json"), b["ip -4 route show table all"],
                    b["ip -6 route show table all"], after=lambda s: [x for t, x, _ in rows if t <= s or t == 0][-1])
    err = prepare(lab)
    assert err is not None and ROUTE_OUT in err and err.startswith("pe1 has a route out over the management network"), err
    assert lab.slept <= BOUND


def test_a_route_back_on_management_before_a_ping_ends_the_run():
    """t4 settled (Docker's default gone, the route on eth2): prepare has nothing to do. Then the route is back on
    eth0 (its live line): the check before the ping ends the run, and the ping never runs."""
    settled = samples("t4")[-1]
    lab = ReplayLab("pe1", load("t4", "inspect_pe1.json"), settled[1], settled[2])
    assert prepare(lab) is None
    assert lab.management["pe1"].removed == []
    lab.now[4] = "\n".join(ROUTE_OUT + " " if ln.startswith("198.51.100.0/24") else ln for ln in settled[1].split("\n"))
    with pytest.raises(ManagementPathError, match="before the ping to 198.51.100.1.*198.51.100.0/24 nhid 7 via "
                                                  "172.20.20.1 dev eth0"):
        FrrDriver(lab, "pe1").ping("198.51.100.1", None, 3)
    assert lab.pings == []


# ------------------------------------------------------------------------------------------- still repaired

def test_dockers_default_back_later_is_deleted_again_recorded_and_the_ping_runs():
    """pe2 in t1 (its live table, Docker's defaults and nothing else on eth0; pe2 is on pe1's management network, so
    pe1's `docker inspect` stands for it): prepare deletes and records them; Docker's IPv4 default back before a ping
    (as SONiC VS brings eth0 up again) is deleted again and recorded, and the ping runs."""
    pe2 = load("t1", "answers.json")["before"]["pe2"]
    lab = ReplayLab("pe2", load("t1", "inspect_pe1.json"), pe2["ip -4 route show table all"],
                    pe2["ip -6 route show table all"])
    assert prepare(lab) is None
    m = lab.management["pe2"]
    assert m.removed == [DOCKER4, DOCKER6]
    lab.now[4] = pe2["ip -4 route show table all"]
    FrrDriver(lab, "pe2").ping("10.0.4.2", None, 3)
    assert len(lab.pings) == 1 and DOCKER4 not in lines(lab.table(4))
    assert m.readded == [f"{DOCKER4} (before the ping to 10.0.4.2)"]
    assert "back and removed again: " + DOCKER4 in mgmt.describe(m, "linux")
