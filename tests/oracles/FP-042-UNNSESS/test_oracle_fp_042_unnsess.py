"""Oracle FP-042-UNNSESS (red team RT-0066): `record` on unnumbered and point-to-point links leaves gaps unsaid.

The fabric is the FRR 10.2.1 BGP-unnumbered capture (tests/fixtures/frr1021u_capture.txt, martimy/clab-bgp-frr @ ac5b96c):
- leaf01 eth1 and spine01 eth1 hold only an IPv6 link-local address;
- each node's `show bgp neighbors json` keys every session by its interface name: leaf01 has eth1 and eth2, spine01
  has eth1, eth2 and eth3, all Established.

What 0.4.2 (e6522db) does, and what is required:
- (a) **The sessions.** `record` writes no bgp_session or bgp_prefixes check for any of those neighbors ("BGP neighbor
  'eth1' is not an IP address (unnumbered?); not recorded", a plain warning), yet exits 0 with no INCOMPLETE BASELINE
  line. A change that takes a session down or floods it passes the baseline (RT-0066).
  Required: every neighbor is either recorded (a bgp_session check naming it) or an INCOMPLETE BASELINE line naming the
  node and the neighbor, so `record` exits 1.
- (b) **A point-to-point address.** iproute2 prints a point-to-point address as `inet 10.0.0.0 peer 10.0.0.1/31`. The
  address parser reads the token after `inet`, 10.0.0.0, as 10.0.0.0/32, so `record` guards the wrong /32 and exits 0.
  Required: the real /31 (10.0.0.0/31) is guarded, or an INCOMPLETE BASELINE line names the node and the interface.
  Never the /32. This perturbs the captured leaf01 eth3 answer: its inet line is replaced by a peer line in
  iproute2's format. No capture with a peer address exists.
- (c) **169.254.0.0/16.** A numbered link on 169.254.0.0/30 with a BGP session over it reads as link-local only, so
  `record` calls it BGP unnumbered and guards nothing. Required: only fe80::/10 counts as link-local for "unnumbered";
  169.254.0.0/30 is guarded on both ends and not called unnumbered. This perturbs the captured eth1 answers of
  leaf01 and spine01: a 169.254.0.x/30 line is added in iproute2's format.

Everything goes through `record.record` with the real `Lab.interface_addresses` and the real FRR driver's
`bgp_neighbors`, fed the captured answers. The reads the capture doesn't cover (routes, VRFs) answer "nothing".

The tests here fail on the parent. The guards, which pass before and after the fix, are in
tests/test_oracle_guards_fp_042_unnsess.py (listed in ORACLE.yml `evidence:`).
"""
import json
import types
from pathlib import Path

from netdryrun import record as rec
from netdryrun.drivers import Undetectable
from netdryrun.drivers.base import Observation
from netdryrun.drivers.frr import FrrDriver
from netdryrun.lab import ExecResult, Lab, Node

FX = Path(__file__).resolve().parents[2] / "fixtures"
NODES = ("leaf01", "spine01")


def fx(name: str) -> str:
    return (FX / name).read_text(encoding="utf-8")


def captured() -> dict:
    out = {}
    for node in NODES:
        for dev in ("eth1", "eth2", "eth3"):
            out[(node, f"ip -o addr show dev {dev}")] = fx(f"frr1021u_{node}_ip_o_addr_show_dev_{dev}.txt")
        out[(node, "vtysh -c show bgp neighbors json")] = fx(f"frr1021u_{node}_show_bgp_neighbors_json.txt")
    return out


def neighbors(node: str) -> list:
    return list(json.loads(fx(f"frr1021u_{node}_show_bgp_neighbors_json.txt")))


class CapturedLab:
    """leaf01 and spine01 joined by their eth1 (the captured fabric link), and leaf01's LAN eth3 on a bridge."""

    def __init__(self, answers=None):
        self.answers = captured() if answers is None else answers
        self.nodes = {"leaf01": Node("leaf01", "clab-frr-leaf01", "linux", "quay.io/frrouting/frr:10.2.1"),
                      "spine01": Node("spine01", "clab-frr-spine01", "linux", "quay.io/frrouting/frr:10.2.1"),
                      "lan1": Node("lan1", "clab-frr-lan1", "bridge", "")}
        self.links = [(("leaf01", "eth1"), ("spine01", "eth1")), (("leaf01", "eth3"), ("lan1", "p1"))]
        self.interface_addresses = types.MethodType(Lab.interface_addresses, self)   # the real parser

    def exec(self, node, cmd, timeout=60, input=None):
        key = (node, " ".join(cmd))
        if key in self.answers:
            return ExecResult(cmd, 0, self.answers[key], "")
        return ExecResult(cmd, 1, "", f"not captured: {key}")


class Driver(FrrDriver):
    """The real FRR driver for the captured BGP neighbors; what wasn't captured answers "nothing"."""

    def vrfs(self):
        return Observation([], [])

    def all_routes(self, vrf="default", family=4):
        return Observation([], [])

    def routes(self, prefix, vrf="default"):
        return Observation([], [])


def run(monkeypatch, lab):
    def detect(node):
        if node.kind == "bridge":
            raise Undetectable("a bridge")
        return "frr"
    drivers = {n: Driver(lab, n) for n in NODES}
    monkeypatch.setattr(rec, "Lab", lambda topology: lab)
    monkeypatch.setattr(rec, "detect", detect)
    monkeypatch.setattr(rec, "for_node", lambda lab_, name, *a: drivers[name])
    return rec.record(Path("topology.clab.yml"), guards=True, sleep=lambda s: None)


def guarded(data) -> set:
    return {(c["node"], c["prefix"]) for c in data["checks"] if c["type"] == "route" and c.get("present") is False}


def line(node: str, dev: str, inet: str) -> str:
    """An `ip -o addr` line in iproute2's format, for the captured interface number of `dev` on `node`."""
    first = fx(f"frr1021u_{node}_ip_o_addr_show_dev_{dev}.txt").split(":", 1)[0]
    return f"{first}: {dev}    inet {inet} scope global {dev}\\       valid_lft forever preferred_lft forever\n"


def named_unnumbered(warnings, node: str, dev: str) -> list:
    return [w for w in warnings if node in w and dev in w and "unnumbered" in w.lower()
            and not w.startswith("INCOMPLETE") and "BGP neighbor" not in w]


# ------------------------------------------------------------------ red on 0.4.2 (e6522db)

def test_every_unnumbered_neighbor_is_recorded_or_a_named_gap(monkeypatch):
    data, warnings = run(monkeypatch, CapturedLab())
    gaps = rec.baseline_gaps(warnings)
    missing = []
    for node in NODES:
        for nbr in neighbors(node):
            recorded = any(c["type"] == "bgp_session" and c["node"] == node and c.get("neighbor") == nbr
                           for c in data["checks"])
            gap = any(node in w and nbr in w and "neighbor" in w.lower() for w in gaps)
            if not (recorded or gap):
                missing.append(f"{node} {nbr}")
    assert not missing, f"neighbors neither recorded nor a named gap: {missing}; warnings {warnings}"
    assert gaps, "record exits 0 with sessions it didn't record"


def test_a_point_to_point_address_is_its_subnet_or_a_gap(monkeypatch):
    answers = captured()
    eth3 = fx("frr1021u_leaf01_ip_o_addr_show_dev_eth3.txt").splitlines(keepends=True)
    answers[("leaf01", "ip -o addr show dev eth3")] = "".join(
        line("leaf01", "eth3", "10.0.0.0 peer 10.0.0.1/31") if " inet " in x else x for x in eth3)
    data, warnings = run(monkeypatch, CapturedLab(answers))
    g = guarded(data)
    gap = [w for w in rec.baseline_gaps(warnings) if "leaf01" in w and "eth3" in w]
    assert ("leaf01", "10.0.0.0/32") not in g, f"guards a /32 the link isn't: {sorted(g)}"
    assert ("leaf01", "10.0.0.0/31") in g or gap, f"neither the /31 guarded nor a gap: {sorted(g)}; {warnings}"


def test_a_169_254_link_is_numbered_and_guarded(monkeypatch):
    answers = captured()
    for node, addr in (("leaf01", "169.254.0.1/30"), ("spine01", "169.254.0.2/30")):
        answers[(node, "ip -o addr show dev eth1")] += line(node, "eth1", addr)
    data, warnings = run(monkeypatch, CapturedLab(answers))
    g = guarded(data)
    for node in NODES:
        assert (node, "169.254.0.0/30") in g, f"{node}: 169.254.0.0/30 not guarded: {sorted(g)}; {warnings}"
        assert not named_unnumbered(warnings, node, "eth1"), warnings
