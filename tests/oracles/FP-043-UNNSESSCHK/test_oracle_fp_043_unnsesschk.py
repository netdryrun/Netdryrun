"""Oracle FP-043-UNNSESSCHK: an FRR BGP-unnumbered session (`neighbor eth1 interface`) gets no check at all.

The lab (tests/fixtures/unnsesschk1021_capture.txt and unnsesschk1041_capture.txt; the same three-node lab on FRR 10.2.1
and on FRR 10.4.1): r2 (AS 65000) has two BGP-unnumbered eBGP sessions, eth1 to r1 (AS 65001, ipv4-unicast:
10.1.1.0/24 and 10.1.2.0/24) and eth2 to r3 (AS 65002, ipv4-unicast 10.3.1.0/24 and ipv6-unicast 2001:db8:3::/64).
bgpd keys both sessions by their interface name in `show bgp neighbors json`. Captured on r2 in three states, byte
for byte:
- `up`: both sessions Established;
- `down`: r1 configured `neighbor eth1 shutdown` (a change that takes the unnumbered session down);
- `more`: r1 announces a third prefix, 10.1.3.0/24 (a change that sends a prefix the session doesn't send today).

What 0.4.2 (f59999b) does, and what is required:
- (a) **record.** `record` writes no bgp_session or bgp_prefixes check for eth1 or eth2: each is an INCOMPLETE
  BASELINE line ("a check can't name yet"), so on an unnumbered fabric record exits 1 and the baseline guards no
  session. Required: each established interface-named session is recorded with the checks a numbered eBGP session
  gets (bgp_session; bgp_prefixes per family it carries, with `only` where the driver lists the prefixes), and no
  INCOMPLETE BASELINE line names it. The recorded checks pass on `up`, and fail on `down` and on `more`.
- (b) **The check.** netdryrun.yml refuses `neighbor: eth1` ("does not appear to be an IPv4 or IPv6 address"), so
  no check can be written by hand either. Required: a bgp_session and a bgp_prefixes check naming the interface
  load, pass on `up`, and FAIL (a real failure, not "not ready") on `down` and on `more`.
- (c) **Other drivers.** An interface-named neighbor on a driver that keys sessions by address could only ever read
  "not configured": it must be refused before deploying (check_supported raises), never run. 0.4.2 doesn't refuse it
  (check_supported returns).

FRR 10.2.1 prints no `totalRoutes` in `neighbors N routes json`, which the driver requires before it trusts the
listing (for any neighbor, numbered too), so there `record` pins the count (`exact`) instead of writing `only`, as for
a numbered session on that version; FRR 10.4.1 prints it, and `only` is written and judged.

Everything goes through the real FRR driver fed the captured answers (keyed by the exact vtysh/ip command), the real
config validation and the real check evaluation. The reads the capture doesn't cover (routes, VRFs) answer
"nothing", as in oracle FP-042-UNNSESS.
"""
import types
from pathlib import Path

import pytest

from netdryrun import record as rec
from netdryrun.checks import Unready, _evaluate
from netdryrun.config import Check, ConfigError, _validate_check
from netdryrun.drivers import DriverError, Undetectable, check_supported
from netdryrun.drivers.base import Observation
from netdryrun.drivers.frr import FrrDriver
from netdryrun.lab import ExecResult, Lab, Node

FX = Path(__file__).resolve().parents[2] / "fixtures"
VERSIONS = {"1021": "quay.io/frrouting/frr:10.2.1", "1041": "quay.io/frrouting/frr:10.4.1"}
EXPECTED = {"eth1": ["ipv4-unicast"], "eth2": ["ipv4-unicast", "ipv6-unicast"]}
R1_NOW = ["10.1.1.0/24", "10.1.2.0/24"]


def fx(name: str) -> str:
    return (FX / name).read_text(encoding="utf-8")


def answers(ver: str, state: str) -> dict:
    """The captured answers of r2 on FRR `ver` in `state`, keyed by the command line the driver runs."""
    out = {("r2", "vtysh -c show bgp neighbors json"): fx(f"unnsesschk{ver}_r2_neighbors_{state}.json")}
    for nbr, fams in EXPECTED.items():
        for fam in fams:
            v = fam.split("-")[0]
            name = f"unnsesschk{ver}_r2_{nbr}_{v}_routes_{state}.json"
            if (FX / name).exists():
                out[("r2", f"vtysh -c show bgp {v} unicast neighbors {nbr} routes json")] = fx(name)
    for dev in ("eth1", "eth2"):
        out[("r2", f"ip -o addr show dev {dev}")] = fx(f"unnsesschk{ver}_r2_ip_o_addr_show_dev_{dev}.txt")
    return out


class CapturedLab:
    """r2 and its two unnumbered links (to r1 and r3, whose own answers aren't read: they are not recorded here)."""

    def __init__(self, ver: str, state: str = "up"):
        self.answers = answers(ver, state)
        self.nodes = {n: Node(n, f"clab-ndr-unnsess-{n}", "linux", VERSIONS[ver]) for n in ("r1", "r2", "r3")}
        self.links = [(("r2", "eth1"), ("r1", "eth1")), (("r2", "eth2"), ("r3", "eth1"))]
        self.interface_addresses = types.MethodType(Lab.interface_addresses, self)   # the real parser

    def exec(self, node, cmd, timeout=60, input=None):
        key = (node, " ".join(cmd))
        if key in self.answers:
            return ExecResult(cmd, 0, self.answers[key], "")
        return ExecResult(cmd, 1, "", f"not captured: {key}")


class Driver(FrrDriver):
    """The real FRR driver for the captured BGP state; what wasn't captured answers "nothing"."""

    def vrfs(self):
        return Observation([], [])

    def all_routes(self, vrf="default", family=4):
        return Observation([], [])

    def routes(self, prefix, vrf="default"):
        return Observation([], [])


def recorded(monkeypatch, ver: str) -> tuple[dict, list]:
    lab = CapturedLab(ver, "up")

    def detect(node):
        if node.name != "r2":
            raise Undetectable("not recorded in this oracle")
        return "frr"
    monkeypatch.setattr(rec, "Lab", lambda topology: lab)
    monkeypatch.setattr(rec, "detect", detect)
    monkeypatch.setattr(rec, "for_node", lambda lab_, name, *a: Driver(lab, name))
    return rec.record(Path("topology.clab.yml"), guards=True, sleep=lambda s: None)


def load(raw: dict):
    try:
        return _validate_check(0, dict(raw), 60)
    except ConfigError as e:
        raise AssertionError(f"netdryrun.yml refuses a check naming the unnumbered session: {e}") from None


def judge(raw: dict, ver: str, state: str):
    return _evaluate(load(raw), Driver(CapturedLab(ver, state), "r2"))


def fails(raw: dict, ver: str, state: str) -> bool:
    """A real failure on `state`: not passed, and not "not ready" (which reads inconclusive, never a verdict)."""
    ok, detail, _ = judge(raw, ver, state)
    return not ok and not isinstance(detail, Unready)


SESSION = {"type": "bgp_session", "node": "r2", "neighbor": "eth1"}
EXACT = {"type": "bgp_prefixes", "node": "r2", "neighbor": "eth1", "afi": "ipv4-unicast", "exact": 2}
ONLY = {"type": "bgp_prefixes", "node": "r2", "neighbor": "eth1", "afi": "ipv4-unicast", "min": 2, "max": 4,
        "only": R1_NOW}


# ------------------------------------------------------------------ red on 0.4.2 (f59999b)

@pytest.mark.parametrize("ver", sorted(VERSIONS))
def test_record_writes_the_unnumbered_sessions_checks(monkeypatch, ver):
    data, warnings = recorded(monkeypatch, ver)
    checks = [c for c in data["checks"] if c["node"] == "r2"]
    for nbr, fams in EXPECTED.items():
        assert {"type": "bgp_session", "node": "r2", "neighbor": nbr} in checks, \
            f"no bgp_session for {nbr}: {checks}; {warnings}"
        for fam in fams:
            mine = [c for c in checks if c["type"] == "bgp_prefixes" and c.get("neighbor") == nbr
                    and c.get("afi") == fam]
            assert len(mine) == 1, f"{nbr} {fam}: {mine}; {warnings}"
    eth1 = next(c for c in checks if c["type"] == "bgp_prefixes" and c.get("neighbor") == "eth1"
                and c.get("afi") == "ipv4-unicast")
    if ver == "1041":   # the listing carries totalRoutes: eBGP gets `only`, as a numbered session does
        assert eth1.get("only") == R1_NOW, f"eth1 is eBGP: its prefixes are listed as for a numbered session: {eth1}"
    else:               # no totalRoutes: the count is pinned, never a bare range
        assert eth1.get("only") == R1_NOW or eth1.get("exact") == 2, eth1
    # the family eth1 doesn't carry is pinned to exactly 0 from the live capture, as for a numbered eBGP session
    assert {"type": "bgp_prefixes", "node": "r2", "neighbor": "eth1", "afi": "ipv6-unicast", "exact": 0} in checks,         f"eth1 carries no IPv6 today: exact 0 expected: {checks}"
    # (r1 and r3 aren't recorded here: their own link addresses are no gap of this oracle)
    named = [w for w in rec.baseline_gaps(warnings) if "BGP neighbor" in w and ("eth1" in w or "eth2" in w)]
    assert not named, f"the recorded sessions are still named as gaps: {named}"
    for c in checks:
        load(c)


@pytest.mark.parametrize("ver", sorted(VERSIONS))
def test_the_recorded_checks_pass_unchanged_and_fail_on_the_changes(monkeypatch, ver):
    data, warnings = recorded(monkeypatch, ver)
    mine = [c for c in data["checks"] if c["node"] == "r2" and c["type"] in ("bgp_session", "bgp_prefixes")
            and c.get("neighbor") in EXPECTED]
    assert mine, f"nothing recorded for the unnumbered sessions: {warnings}"
    for c in mine:
        ok, detail, _ = judge(c, ver, "up")
        assert ok, f"{c} fails on the state it was recorded from: {detail}"
    for state in ("down", "more"):
        failing = [c for c in mine if c["neighbor"] == "eth1" and fails(c, ver, state)]
        assert failing, f"no recorded check on eth1 fails on `{state}`"
    prefixes = [c for c in mine if c["neighbor"] == "eth1" and c["type"] == "bgp_prefixes"
                and c["afi"] == "ipv4-unicast"]
    assert prefixes and all(fails(c, ver, "more") for c in prefixes), f"10.1.3.0/24 passes {prefixes}"


@pytest.mark.parametrize("ver", sorted(VERSIONS))
def test_a_session_check_naming_the_interface_passes_up_and_fails_down(ver):
    ok, detail, _ = judge(SESSION, ver, "up")
    assert ok, detail
    ok, detail, _ = judge(SESSION, ver, "down")
    assert not ok and not isinstance(detail, Unready), f"the session went down and the check says {ok}: {detail}"


@pytest.mark.parametrize("ver", sorted(VERSIONS))
def test_a_prefix_count_naming_the_interface_fails_on_a_new_prefix(ver):
    ok, detail, _ = judge(EXACT, ver, "up")
    assert ok, detail
    assert fails(EXACT, ver, "more"), f"r1 sent a third prefix and `exact: 2` says {judge(EXACT, ver, 'more')[:2]}"
    assert fails(EXACT, ver, "down"), f"the session is down and the prefix check says {judge(EXACT, ver, 'down')[:2]}"


def test_an_only_list_naming_the_interface_fails_on_a_new_prefix():
    ok, detail, _ = judge(ONLY, "1041", "up")
    assert ok, detail
    ok, detail, _ = judge(ONLY, "1041", "more")
    assert not ok and not isinstance(detail, Unready) and "10.1.3.0/24" in detail, \
        f"r1 sent 10.1.3.0/24 (within max: 4) and the check says {ok}: {detail}"


def test_a_driver_that_keys_sessions_by_address_refuses_an_interface():
    class TwoNodes:
        nodes = {"eos1": Node("eos1", "clab-t-eos1", "arista_ceos", "ceos:4.36.3M"),
                 "srl1": Node("srl1", "clab-t-srl1", "nokia_srlinux", "ghcr.io/nokia/srlinux:26.7.2")}
    for node in TwoNodes.nodes:
        for ctype, extra in (("bgp_session", {"state": "established"}),
                             ("bgp_prefixes", {"afi": "ipv4-unicast", "max": 4})):
            c = Check(type=ctype, params={"node": node, "neighbor": "eth1", **extra}, name=f"{node} {ctype}",
                      timeout=1)
            try:
                check_supported(TwoNodes(), c)
            except DriverError:
                continue
            raise AssertionError(f"{node} {ctype} on an interface name isn't refused: it could only read "
                                 "'not configured'")
