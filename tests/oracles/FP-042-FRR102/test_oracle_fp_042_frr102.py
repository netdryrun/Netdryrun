"""Oracle FP-042-FRR102: FRR 10.2.1 prints a BGP prefix's paths without pathCount.

What the router showed (tests/fixtures/frr1021_capture.txt, leaf01 of martimy/clab-bgp-frr @ ac5b96c, FRR 10.2.1):
- `show bgp ipv4 unicast <p> json` answers {prefix, version, advertisedTo, paths}: the paths ARE listed, pathCount is
  not printed, for the node's own prefix (one local, sourced path) and for a learned one (two eBGP paths);
- the text form of the same command says how many: "Paths: (1 available, best #1 ...)", "(2 available ...)";
- `... json detail` is not a command on 10.2.1 (rc=1).
The 0.4.1 driver stops on the missing pathCount, so record's guard on each leaf's own LAN prefix is a gap and a route
check on either prefix has no verdict.

The rule (tightened 2026-11-10): the capture shows the paths and how many there are, so the fix must read them.
A named gap is fail-safe but delivers nothing. A fix that reads no route of this capture (897f1e2 alone, whose prefix
match kept FRR's trailing comma) fails here.
1. The driver reads the paths as captured: 2 for the learned prefix (as the text answer's "2 available" says) and 1
   for the own prefix ("1 available"). The route checks on both prefixes pass.
2. `record --attributes --guards` on leaf01 writes the bgp_route check for the learned prefix (AS path 65000 65002) and
   the guard against the own LAN via BGP. No INCOMPLETE BASELINE line names either prefix.
Never a pass on a guessed absence: an answer that names the prefix and its advertisement but lists no paths is not
"absent" (that shape wasn't captured; it is the one the spec feared), and a pathCount that is printed is still
checked against the paths listed.

For the record test, leaf01's eth3 addresses (the LAN 192.168.11.1/24) and its `show bgp neighbors json` come from
the FP-042-UNNUMBERED capture (tests/fixtures/frr1021u_capture.txt). That is the same lab, image and node, captured 8
minutes later. The default local preference read is answered by the captured full table listing (see
CAPTURED). Reads neither capture covers answer rc 1: leaf01's full routing table (zebra's listing, stood in for
by the learned prefix only, which zebra holds as bgp per frr1021_learned_route_json.txt) and the default-route
guards. The test asserts nothing about the gaps those leave, only about the two captured prefixes.

The tests here fail on the parent. The guards, which pass before and after the fix, are in
tests/test_oracle_guards_fp_042_frr102.py (listed in ORACLE.yml `evidence:`).
"""
from pathlib import Path

import types

from netdryrun import record as rec
from netdryrun.checks import hold_check, run_check
from netdryrun.config import _validate_check
from netdryrun.drivers import Undetectable
from netdryrun.drivers.base import DriverError, Observation, Route
from netdryrun.drivers.frr import FrrDriver
from netdryrun.lab import ExecResult, Lab, Node

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
    # the driver reads the default local preference from a table listing's header (defaultLocPrf). That command
    # wasn't captured: leaf01's full table listing above, the same node and moment, answers it (header
    # defaultLocPrf 100, routes listed)
    "show bgp ipv4 unicast 255.255.255.255/32 longer-prefixes json": "frr1021_table_json.txt",
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


def paths_or_error(prefix: str):
    """leaf01's BGP paths for `prefix` through the real driver: (paths, None), or (None, the DriverError)."""
    try:
        return FrrDriver(CapturedLab(), "leaf01").bgp_paths(prefix).value, None
    except DriverError as e:
        return None, e


class RecordLab(CapturedLab):
    """leaf01 and its LAN bridge for `record`: the FRR102 answers, plus eth3's addresses and the BGP neighbors from the
    same node's FP-042-UNNUMBERED capture."""

    def __init__(self):
        super().__init__({"show bgp neighbors json": fx("frr1021u_leaf01_show_bgp_neighbors_json.txt")})
        self.nodes = {"leaf01": Node("leaf01", "clab-frr-leaf01", "linux", "quay.io/frrouting/frr:10.2.1"),
                      "lan1": Node("lan1", "clab-frr-lan1", "bridge", "")}
        self.links = [(("leaf01", "eth3"), ("lan1", "p1"))]
        self.interface_addresses = types.MethodType(Lab.interface_addresses, self)   # the real parser

    def exec(self, node, cmd, timeout=60, input=None):
        if node == "leaf01" and cmd == ["ip", "-o", "addr", "show", "dev", "eth3"]:
            return ExecResult(cmd, 0, fx("frr1021u_leaf01_ip_o_addr_show_dev_eth3.txt"), "")
        return super().exec(node, cmd, timeout, input)


class RecordDriver(FrrDriver):
    """The real FRR driver. Only zebra's full table listing wasn't captured: it lists the learned prefix as bgp, as
    zebra held it (frr1021_learned_route_json.txt). The own prefix is connected, so it isn't a BGP route there."""

    def vrfs(self):
        return Observation([], [])

    def all_routes(self, vrf="default", family=4):
        return Observation([Route(LEARNED, "bgp", True)] if family == 4 else [], [])


def recorded(monkeypatch):
    lab = RecordLab()

    def detect(node):
        if node.kind == "bridge":
            raise Undetectable("a bridge")
        return "frr"
    drv = RecordDriver(lab, "leaf01")
    monkeypatch.setattr(rec, "Lab", lambda topology: lab)
    monkeypatch.setattr(rec, "detect", detect)
    monkeypatch.setattr(rec, "for_node", lambda lab_, name, *a: drv)
    return rec.record(Path("topology.clab.yml"), attributes=True, guards=True, sleep=lambda s: None)


# ------------------------------------------------------------------ red on 0.4.1 and on 897f1e2: the paths are read

def test_learned_paths_read_as_captured():
    """Two eBGP paths, both AS path 65000 65002, one best (from spine01), as the JSON and the text answer show."""
    paths, error = paths_or_error(LEARNED)
    assert error is None, f"no reading of the captured paths: {error}"
    assert len(paths) == 2 and "Paths: (2 available, best #1" in fx("frr1021_learned_prefix_text.txt")
    assert [p.as_path for p in paths] == ["65000 65002", "65000 65002"]
    assert [p.best for p in paths] == [True, False]
    assert [p.neighbor for p in paths] == ["fe80::a8c1:abff:fe6a:4ffa", "fe80::a8c1:abff:feac:5920"]


def test_own_prefix_path_read_as_captured():
    """One path, leaf01's own (`network 192.168.11.0/24`), best: "Paths: (1 available, best #1" in the text answer."""
    paths, error = paths_or_error(OWN)
    assert error is None, f"no reading of the captured path: {error}"
    assert len(paths) == 1 and paths[0].best and "Paths: (1 available, best #1" in fx("frr1021_own_prefix_text.txt")


def test_own_lan_guard_passes_on_the_captured_answer():
    """record's guard on leaf01's own LAN (`route ... protocol: bgp, present: false`): zebra holds 192.168.11.0/24 as
    connected and BGP has only leaf01's own path, so the guard passes. A gap is no verdict."""
    r = negative(CapturedLab(), type="route", prefix=OWN, protocol="bgp", present=False)
    assert r.passed, r.detail


def test_learned_route_check_passes_on_the_captured_answer():
    r = positive(CapturedLab(), type="route", prefix=LEARNED, protocol="bgp")
    assert r.passed, r.detail


def test_record_writes_both_prefixes_without_a_gap(monkeypatch):
    data, warnings = recorded(monkeypatch)
    gaps = [w for w in rec.baseline_gaps(warnings) if OWN in w or LEARNED in w]
    assert gaps == [], gaps
    learned = [c for c in data["checks"] if c["type"] == "bgp_route" and c["prefix"] == LEARNED]
    assert len(learned) == 1 and learned[0].get("as_path") == "65000 65002", data["checks"]
    guard = {"type": "route", "node": "leaf01", "prefix": OWN, "protocol": "bgp", "present": False}
    assert guard in data["checks"], data["checks"]
