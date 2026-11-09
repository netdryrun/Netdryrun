"""Oracle FP-042-FRR102: FRR 10.2.1 prints a BGP prefix's paths without pathCount.

What the router showed (tests/fixtures/frr1021_capture.txt, leaf01 of martimy/clab-bgp-frr @ ac5b96c, FRR 10.2.1):
- `show bgp ipv4 unicast <p> json` answers {prefix, version, advertisedTo, paths}: the paths ARE listed, pathCount is
  not printed, for the node's own prefix (one local, sourced path) and for a learned one (two eBGP paths);
- the text form of the same command says how many: "Paths: (1 available, best #1 ...)", "(2 available ...)";
- `... json detail` is not a command on 10.2.1 (rc=1).
The 0.4.1 driver stops on the missing pathCount, so record's guard on each leaf's own LAN prefix is a gap and a route
check on either prefix has no verdict.

Two outcomes are accepted, and nothing else:
1. the driver reads the captured paths (the capture shows they are there): the own LAN prefix's guard passes (zebra
   holds it as connected, BGP has only the node's own path) and the learned prefix's route check passes, with the two
   paths as captured; or
2. a named gap: a DriverError that names the prefix and is not the bare "unexpected output" message.
Never a pass on a guessed absence: an answer that names the prefix and its advertisement but lists no paths is not
"absent" (that shape wasn't captured; it is the one the spec feared), and a pathCount that is printed is still
checked against the paths listed.
"""
import json
from pathlib import Path

import pytest

from netdryrun.checks import hold_check, run_check
from netdryrun.config import _validate_check
from netdryrun.drivers.base import DriverError
from netdryrun.drivers.frr import FrrDriver, parse_bgp_paths
from netdryrun.lab import ExecResult

FX = Path(__file__).resolve().parents[2] / "fixtures"
OWN, LEARNED = "192.168.11.0/24", "192.168.21.0/24"


def fx(name: str) -> str:
    return (FX / name).read_text(encoding="utf-8")


CAPTURED = {   # vtysh command -> leaf01's output, as captured
    f"show bgp ipv4 unicast {OWN} json": "frr1021_own_prefix_json.txt",
    f"show bgp ipv4 unicast {OWN}": "frr1021_own_prefix_text.txt",
    f"show ip route {OWN} json": "frr1021_own_route_json.txt",
    f"show bgp ipv4 unicast {LEARNED} json": "frr1021_learned_prefix_json.txt",
    f"show bgp ipv4 unicast {LEARNED}": "frr1021_learned_prefix_text.txt",
    f"show ip route {LEARNED} json": "frr1021_learned_route_json.txt",
    "show bgp ipv4 unicast json": "frr1021_table_json.txt",
}


class CapturedLab:
    """leaf01 as captured. A command that wasn't captured answers as an unknown command (rc=1), as 10.2.1 did for
    `json detail`: the oracle knows nothing else the router would have said."""

    def __init__(self, overrides: dict | None = None):
        self.overrides = overrides or {}

    def exec(self, node, cmd, timeout=60, input=None):
        if cmd[:2] == ["vtysh", "-c"] and len(cmd) == 3:
            c = cmd[2]
            if c in self.overrides:
                return ExecResult(cmd, 0, self.overrides[c], "")
            if c in CAPTURED:
                return ExecResult(cmd, 0, fx(CAPTURED[c]), "")
            return ExecResult(cmd, 1, f"% Unknown command: {c}\n", "")
        return ExecResult(cmd, 1, "", f"not captured: {' '.join(cmd)}")


class Clock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t

    def sleep(self, s):
        self.t += max(s, 0.5)


def check(**raw):
    return _validate_check(0, {"node": "leaf01", **raw}, 20)


def negative(lab, **raw):
    c = Clock()
    return hold_check(check(**raw), FrrDriver(lab, "leaf01"), hold=10, clock=c, sleep=c.sleep)


def positive(lab, **raw):
    c = Clock()
    return run_check(check(**raw), FrrDriver(lab, "leaf01"), clock=c, sleep=c.sleep)


def named_gap(text: str, prefix: str) -> bool:
    return "unexpected output" not in text and prefix in text


# ------------------------------------------------------------------ red on 0.4.1: the captured answers get a verdict

def test_own_lan_guard_gets_a_verdict_on_the_captured_answer():
    """record's guard on leaf01's own LAN (`route ... protocol: bgp, present: false`): zebra holds 192.168.11.0/24 as
    connected and BGP has only leaf01's own path, so the guard passes; or the gap is named, never 'unexpected'."""
    r = negative(CapturedLab(), type="route", prefix=OWN, protocol="bgp", present=False)
    assert r.passed or named_gap(str(r.detail), OWN), r.detail


def test_learned_route_check_gets_a_verdict_on_the_captured_answer():
    r = positive(CapturedLab(), type="route", prefix=LEARNED, protocol="bgp")
    assert r.passed or named_gap(str(r.detail), LEARNED), r.detail


def test_learned_paths_read_as_captured():
    """Two eBGP paths, both AS path 65000 65002, one best (from spine01), as the JSON and the text answer show.
    defaultLocPrf 100 is from the captured table listing."""
    try:
        paths = parse_bgp_paths(fx("frr1021_learned_prefix_json.txt"), LEARNED, default_local_pref=100)
    except DriverError as e:
        assert named_gap(str(e), LEARNED), str(e)
        return
    assert [p.as_path for p in paths] == ["65000 65002", "65000 65002"]
    assert [p.best for p in paths] == [True, False]
    assert [p.neighbor for p in paths] == ["fe80::a8c1:abff:fe6a:4ffa", "fe80::a8c1:abff:feac:5920"]
    assert "Paths: (2 available, best #1" in fx("frr1021_learned_prefix_text.txt")


# ------------------------------------------------------------------ guards: pass before and after the fix

def test_own_prefix_bgp_route_absent_never_passes():
    """leaf01 advertises 192.168.11.0/24 (advertisedTo eth1, eth2): `bgp_route present: false` must not pass."""
    r = negative(CapturedLab(), type="bgp_route", prefix=OWN, present=False)
    assert not r.passed, r.detail


@pytest.mark.parametrize("kind", ["route", "bgp_route"])
def test_answer_without_paths_never_reads_absent(kind):
    """The shape the spec feared, not captured: the own prefix's answer with its paths list taken out. It names the
    prefix and who it is advertised to, so a BGP route exists: no `present: false` may pass on it."""
    data = json.loads(fx("frr1021_own_prefix_json.txt"))
    del data["paths"]
    lab = CapturedLab({f"show bgp ipv4 unicast {OWN} json": json.dumps(data)})
    raw = {"type": kind, "prefix": OWN, "present": False, **({"protocol": "bgp"} if kind == "route" else {})}
    # for `route`, zebra's captured answer (connected) stays; without the paths a learned BGP path can't be ruled out
    r = negative(lab, **raw)
    assert not r.passed, r.detail


@pytest.mark.parametrize("count", [1, 3])
def test_printed_path_count_is_still_checked(count):
    """Where pathCount IS printed (FRR 10.4.1 prints it: tests/fixtures/frr_bgp_paths_local.txt), a count that
    doesn't match the paths listed is still an error, never one path less or none."""
    data = json.loads(fx("frr1021_learned_prefix_json.txt"))
    data["pathCount"] = count
    with pytest.raises(DriverError):
        parse_bgp_paths(json.dumps(data), LEARNED, default_local_pref=100)
