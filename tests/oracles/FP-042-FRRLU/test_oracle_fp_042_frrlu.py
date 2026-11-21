"""Oracle FP-042-FRRLU (RT-0080): a session that carries IPv4 routes over labeled-unicast reads as "doesn't carry
ipv4-unicast", so `bgp_prefixes exact: 0` passes while the peer's IPv4 routes are installed.

What the router showed (FRR 10.4.1, containerlab lab ndr-rplu, captured live 2026-11-15 07:11-07:18 Thailand time;
lab files tests/fixtures/frr1041_rplu_{topology.clab.yml,checks*.yml,r1.conf,r2.conf}, captures
tests/fixtures/frr1041_rplu_r1_*):
- r1 (AS 65001, `no bgp default ipv4-unicast`) has one eBGP session to 10.0.12.2 (r2, AS 65002), activated only under
  `address-family ipv4 labeled-unicast`; r2 sends 10.80.1-3.0/24 over it;
- r1 installs all three as BGP routes in its IPv4 unicast RIB (`B>* 10.80.1.0/24 [20/0] via 10.0.12.2, eth1, label
  implicit-null`), and `show bgp ipv4 unicast` lists them from 10.0.12.2;
- `show bgp neighbors json` (the answer netdryrun read) lists one family for the session, `ipv4LabeledUnicast`, with
  acceptedPrefixCounter 0 (sentPrefixCounter 3); no `ipv4Unicast`.
The 0.4.2 FRR parser (SONiC uses the same one) keeps the families it is given, so `ipv4-unicast` is missing and
checks._bgp_prefixes answers `exact: 0` with "0 ipv4-unicast prefixes (the session doesn't carry ipv4-unicast)".
Live, with `nodes.r1.peers.10.0.12.2.eor: not_sent` (what the End-of-RIB error tells the user to declare), that check
PASSED (tests/fixtures/frr1041_rplu_eor_report.json); without it, the End-of-RIB gate failed it closed first
(tests/fixtures/frr1041_rplu_report.json), which masks the verdict but doesn't make it right.

The rule: on this capture "r1 accepts no IPv4 unicast routes from 10.0.12.2" is false, so `exact: 0` on ipv4-unicast
must not pass, whatever the End-of-RIB state: the tests run the check and the driver read directly, with no gate.
Failing or not-ready both satisfy the oracle. `record` on the same capture must not write that `exact: 0` either
(0.4.2 writes it for every eBGP session that lacks a unicast family, acceptance round B-3), since a baseline that
asserts a false fact passes on the very state it was recorded on.

Guards (they pass before and after the fix) are in tests/test_oracle_guards_fp_042_frrlu.py: a session that really
carries no IPv4 (IPv6 only, no labeled-unicast) still passes `exact: 0` with the "doesn't carry" message, and
`max: 0` on this capture still fails.

Commands the capture doesn't cover answer rc 1 (an unknown command): the oracle knows nothing else r1 would have said.
"""
import json
from pathlib import Path

import pytest

from netdryrun import record as rec
from netdryrun.checks import converge_then_hold, run_check
from netdryrun.config import _validate_check
from netdryrun.drivers.frr import FrrDriver
from netdryrun.drivers.sonic import SonicDriver
from netdryrun.lab import ExecResult, Node

FX = Path(__file__).resolve().parents[2] / "fixtures"
NODE = "r1"
NEIGHBOR = "10.0.12.2"
NEIGHBORS = "show bgp neighbors json"
P = "frr1041_rplu_"

# r1's answers, as captured (the vtysh command -> the fixture holding its output)
LU = {
    NEIGHBORS: P + "r1_neighbors.json",                       # read by netdryrun for the false pass (eor report)
    f"show bgp neighbors {NEIGHBOR} json": P + "r1_neighbor_10.0.12.2.json",
    "show bgp ipv4 unicast json": P + "r1_bgp_ipv4_unicast.json",
    "show bgp ipv4 unicast": P + "r1_bgp_ipv4_unicast.txt",
    "show bgp ipv4 labeled-unicast": P + "r1_bgp_ipv4_labeled_unicast.txt",
    "show ip route json": P + "r1_ip_route.json",
    "show ip route": P + "r1_ip_route.txt",
    "show bgp summary": P + "r1_bgp_summary.txt",
    "show running-config": P + "r1_running_config.txt",
    "show ip route 10.80.1.0/24 json": P + "r1_ip_route_10.80.1.0.json",
    "show bgp ipv4 unicast 10.80.1.0/24 json": P + "r1_bgp_ipv4_unicast_10.80.1.0.json",
}
PREFIXES = ("10.80.1.0/24", "10.80.2.0/24", "10.80.3.0/24")
DRIVERS = {"frr": FrrDriver, "sonic": SonicDriver}


def fx(name: str) -> str:
    return (FX / name).read_text(encoding="utf-8")


class CapturedLab:
    """r1 as captured. `answers` maps a vtysh command to its output text; any other command answers rc 1."""

    def __init__(self, answers: dict[str, str] | None = None):
        self.answers = answers if answers is not None else {cmd: fx(f) for cmd, f in LU.items()}

    def exec(self, node, cmd, timeout=60, input=None):
        if node == NODE and cmd[:2] == ["vtysh", "-c"] and len(cmd) == 3 and cmd[2] in self.answers:
            return ExecResult(cmd, 0, self.answers[cmd[2]], "")
        return ExecResult(cmd, 1, "", f"% Unknown command: {' '.join(cmd[2:])}")


class Clock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t

    def sleep(self, s):
        self.t += max(s, 0.5)


def driver(kind: str, answers: dict[str, str] | None = None):
    return DRIVERS[kind](CapturedLab(answers), NODE)


def prefixes_check(kind: str, answers=None, neighbor=NEIGHBOR, positive=False, **raw):
    """The check as the runner judges a post-convergence bgp_prefixes check (converge, then hold), or as a plain
    positive poll; no End-of-RIB gate either way."""
    c = Clock()
    check = _validate_check(0, {"node": NODE, "type": "bgp_prefixes", "neighbor": neighbor, **raw}, 20)
    run = run_check if positive else converge_then_hold
    return run(check, driver(kind, answers), clock=c, sleep=c.sleep)


def lu_facts():
    """What the capture says: one Established eBGP session that carries only ipv4LabeledUnicast (counter 0), and r1
    has r2's three prefixes installed as BGP routes via 10.0.12.2 and in its BGP IPv4 unicast table."""
    n = json.loads(fx(LU[NEIGHBORS]))[NEIGHBOR]
    assert n["bgpState"] == "Established" and n["nbrExternalLink"] is True
    assert list(n["addressFamilyInfo"]) == ["ipv4LabeledUnicast"]
    assert n["addressFamilyInfo"]["ipv4LabeledUnicast"]["acceptedPrefixCounter"] == 0
    assert list(n["neighborCapabilities"]["multiprotocolExtensions"]) == ["ipv4LabeledUnicast"]
    conf = fx(P + "r1.conf")
    assert "no bgp default ipv4-unicast" in conf and "address-family ipv4 labeled-unicast" in conf
    assert "address-family ipv4 unicast" not in conf
    rib = json.loads(fx(LU["show ip route json"]))
    for p in PREFIXES:
        [r] = rib[p]
        assert r["protocol"] == "bgp" and r["selected"] is True and r["installed"] is True
        assert [h["ip"] for h in r["nexthops"]] == [NEIGHBOR]
        assert f"B>* {p} [20/0] via {NEIGHBOR}, eth1, label implicit-null" in fx(LU["show ip route"])
    table = json.loads(fx(LU["show bgp ipv4 unicast json"]))["routes"]
    assert sorted(table) == list(PREFIXES)
    assert all(path["peerId"] == NEIGHBOR for p in PREFIXES for path in table[p])
    # the live false pass, and the answer it read is the fixture byte for byte
    live = json.loads(fx(P + "eor_report.json"))["checks"][0]
    assert live["params"] == {"node": NODE, "neighbor": NEIGHBOR, "afi": "ipv4-unicast", "exact": 0}
    assert live["passed"] is True and "doesn't carry ipv4-unicast" in live["detail"]
    assert live["evidence"][0]["output"] == fx(LU[NEIGHBORS])


@pytest.mark.parametrize("kind", sorted(DRIVERS))
def test_exact0_ipv4_unicast_does_not_pass_on_a_labeled_unicast_session(kind):
    """The live false pass, judged as the runner judged it (converge, then hold) but with no End-of-RIB gate."""
    lu_facts()
    r = prefixes_check(kind, afi="ipv4-unicast", exact=0)
    assert not r.passed, (f"{kind}: `bgp_prefixes exact: 0` on ipv4-unicast passed for {NEIGHBOR}, whose session "
                          f"carries IPv4 over labeled-unicast and whose 3 prefixes r1 installed via BGP: {r.detail}")


@pytest.mark.parametrize("kind", sorted(DRIVERS))
def test_exact0_ipv4_unicast_does_not_pass_as_a_positive_check(kind):
    """The same claim polled as a positive check: no path through the check code may pass it."""
    lu_facts()
    r = prefixes_check(kind, positive=True, afi="ipv4-unicast", exact=0)
    assert not r.passed, (f"{kind}: `bgp_prefixes exact: 0` on ipv4-unicast passed (positive poll) for {NEIGHBOR}, "
                          f"which sends r1 3 IPv4 routes over labeled-unicast: {r.detail}")


class OneNodeLab:
    """The lab as `record` sees it: r1 only (r2's own answers weren't captured), no links."""
    links: list = []

    def __init__(self, topology):
        self.nodes = {NODE: Node(NODE, f"clab-ndr-rplu-{NODE}", "linux", "quay.io/frrouting/frr:10.4.1")}


def record(monkeypatch, kind: str, answers=None):
    monkeypatch.setattr(rec, "Lab", OneNodeLab)
    monkeypatch.setattr(rec, "detect", lambda node: kind)
    monkeypatch.setattr(rec, "for_node", lambda lab, name, *a: driver(kind, answers))
    return rec.record(Path(P + "topology.clab.yml"), include_routes=False, guards=False, sleep=lambda s: None)


def zero_claims(checks, neighbor, afi):
    """Recorded bgp_prefixes checks on `neighbor`/`afi` that claim no prefix arrives (exact 0 or max 0)."""
    return [c for c in checks if c.get("type") == "bgp_prefixes" and c.get("node") == NODE
            and c.get("neighbor") == neighbor and c.get("afi") == afi and c.get("vrf", "default") == "default"
            and (c.get("exact") == 0 or c.get("max") == 0)]


@pytest.mark.parametrize("kind", sorted(DRIVERS))
def test_record_does_not_write_exact0_ipv4_unicast_for_a_labeled_unicast_session(monkeypatch, kind):
    """0.4.2 record writes `exact: 0` on ipv4-unicast for this session (eBGP without that family, rule B-3): a
    baseline asserting that r1 accepts no IPv4 routes from r2, while r1 has three installed from it."""
    lu_facts()
    data, warnings = record(monkeypatch, kind)
    bad = zero_claims(data["checks"], NEIGHBOR, "ipv4-unicast")
    assert not bad, (f"{kind}: record wrote {bad} for {NEIGHBOR}, whose session carries IPv4 over labeled-unicast "
                     f"(3 prefixes installed via BGP). Checks: {data['checks']}; warnings: {warnings}")
