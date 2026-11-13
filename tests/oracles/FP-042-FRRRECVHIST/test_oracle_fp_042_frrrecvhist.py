"""Oracle FP-042-FRRRECVHIST (a cousin of RT-0070): a dampening history entry listed as a prefix the neighbor sends.

The 0.4.2 fix of RT-0070 (oracle FP-042-FRRDAMP) drops history and removed paths from the routes and the prefix count
(`_withdrawn`, `count_neighbor_prefixes`), but not from `parse_received`, which lists the prefixes a neighbor sends
for `bgp_prefixes only:` and for `record`'s closed-world `only` list. With `bgp dampening` on, a prefix the neighbor
has just withdrawn stays in `show bgp ipv4 unicast neighbors N routes json` as a history path (and in its
totalRoutes) until the penalty decays. Then:
- `record` writes the withdrawn prefix into `only`, so the day the neighbor sends it again (a leak coming back), the
  recorded check passes: a false pass;
- an `only:` check reads one more prefix listed than counted and stays not-ready ("counted ... but ... listed")
  while the history entry lasts: a false fail.

Device output. Nothing here was captured for this exact case: the listing is DERIVED in this file (`listing`) from
live FRR 10.4.1 captures, because SOURCES.yml has no kind for a derived file (scripts/contrib_gate.py SOURCE_KINDS):
- its frame (vrfId ... localAS, totalRoutes, totalPaths) and the live 10.20.0.0/24 path are those of
  tests/fixtures/frr1041_rt0066_r1_neighbor_routes.json (r1, AS 65001, router-id 1.1.1.1, neighbor 10.0.12.2 in
  AS 65002: the same addressing as lab ndr-rpdamp), its first (best) path only;
- the 0.0.0.0/0 path is r1's captured path from isp in lab ndr-rpdamp (RT-0070), rewritten into the listing's short
  path form: after the withdrawal from tests/fixtures/frr1041_rt0070_r1_bgp_default.json (dampeningHistoryEntry, no
  `valid`, no `bestpath`), printed as `"history": true` as bgpd prints the flag in a table or neighbor listing (the
  flag name the driver's WITHDRAWN_FLAGS already reads there); before it, from
  tests/fixtures/frr1041_rt0070_r1_bgp_default_before.json (valid, best);
- `show bgp neighbors json` is tests/fixtures/frr1041_rt0066_r1_bgp_neighbors.json with ipv4Unicast
  acceptedPrefixCounter set to the paths that are live (1 with the history entry: FRR's counter leaves history paths
  out, as count_neighbor_prefixes says; 2 once the default is back). Its add-path capability is kept as captured, so
  the driver counts prefixes from the same listing.

The rule: a prefix whose only paths are history (or removed) is not one the neighbor sends. bgp_received must not list
it, `record` must not allow it in `only` (or must pin an exact count instead), the recorded check must fail when the
prefix comes back, and an `only:` check whose real routes match must pass while the history entry is listed.

Reads the derived capture doesn't cover answer rc 1 (an unknown command).
"""
import copy
import json
from pathlib import Path

from netdryrun.checks import run_check
from netdryrun.config import _validate_check
from netdryrun.drivers.base import DriverError
from netdryrun.drivers.frr import FrrDriver
from netdryrun.lab import ExecResult
from netdryrun.record import _session_checks

FX = Path(__file__).resolve().parents[2] / "fixtures"
NEIGHBOR = "10.0.12.2"
LIVE = "10.20.0.0/24"
GONE = "0.0.0.0/0"   # the prefix isp withdrew in lab ndr-rpdamp, kept by r1 as a dampening history entry
NEIGHBORS = "show bgp neighbors json"
ROUTES = f"show bgp ipv4 unicast neighbors {NEIGHBOR} routes json"


def fx(name: str):
    return json.loads((FX / name).read_text(encoding="utf-8"))


def short_path(detail: dict, history: bool) -> dict:
    """One path of r1's `show bgp ipv4 unicast 0.0.0.0/0 json` (captured) in the neighbor listing's short form."""
    nh = detail["nexthops"][0]
    p = {"pathFrom": detail["peer"]["type"], "prefix": "0.0.0.0", "prefixLen": 0, "network": GONE,
         "version": detail["version"], "metric": detail["metric"], "weight": 0, "peerId": detail["peer"]["peerId"],
         "path": detail["aspath"]["string"], "origin": detail["origin"],
         "nexthops": [{"ip": nh["ip"], "hostname": nh["hostname"], "afi": nh["afi"], "used": nh["used"]}]}
    if history:
        assert detail.get("dampeningHistoryEntry") is True and "valid" not in detail and "bestpath" not in detail
        return {"history": True, **p}
    assert detail["valid"] is True and detail["bestpath"]["overall"] is True
    return {"valid": True, "bestpath": True, "selectionReason": "First path received", **p}


def listing(history: bool) -> str:
    """r1's `neighbors 10.0.12.2 routes json`: 10.20.0.0/24 live, and the default as a history entry (history=True,
    after isp withdrew it) or as a valid best path (history=False, the default sent again)."""
    base = fx("frr1041_rt0066_r1_neighbor_routes.json")
    live = base["routes"][LIVE][0]
    assert live["valid"] is True and live["peerId"] == NEIGHBOR
    name = "frr1041_rt0070_r1_bgp_default.json" if history else "frr1041_rt0070_r1_bgp_default_before.json"
    [detail] = fx(name)["paths"]
    assert detail["peer"]["peerId"] == NEIGHBOR
    out = {k: v for k, v in base.items() if k not in ("routes", "totalRoutes", "totalPaths")}
    out["routes"] = {GONE: [short_path(detail, history)], LIVE: [live]}
    out["totalRoutes"], out["totalPaths"] = 2, 2
    return json.dumps(out)


def neighbors(accepted: int) -> str:
    data = copy.deepcopy(fx("frr1041_rt0066_r1_bgp_neighbors.json"))
    n = data[NEIGHBOR]
    assert n["bgpState"] == "Established" and n["remoteAs"] == 65002 and n["localAs"] == 65001
    n["addressFamilyInfo"]["ipv4Unicast"]["acceptedPrefixCounter"] = accepted
    return json.dumps(data)


class DerivedLab:
    """r1 as derived above. A command the derivation doesn't cover answers as an unknown command (rc=1)."""

    def __init__(self, history: bool):
        self.answers = {NEIGHBORS: neighbors(1 if history else 2), ROUTES: listing(history)}

    def exec(self, node, cmd, timeout=60, input=None):
        if node == "r1" and cmd[:2] == ["vtysh", "-c"] and len(cmd) == 3 and cmd[2] in self.answers:
            return ExecResult(cmd, 0, self.answers[cmd[2]], "")
        return ExecResult(cmd, 1, "", f"not captured: {' '.join(cmd)}")


class Clock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t

    def sleep(self, s):
        self.t += max(s, 0.5)


def driver(history: bool) -> FrrDriver:
    return FrrDriver(DerivedLab(history), "r1")


def prefixes_check(raw: dict, history: bool):
    c = Clock()
    check = _validate_check(0, {"node": "r1", "type": "bgp_prefixes", "neighbor": NEIGHBOR, **raw}, 20)
    return run_check(check, driver(history), clock=c, sleep=c.sleep)


def recorded() -> dict:
    """The bgp_prefixes check `record` writes for 10.0.12.2 while the default is a history entry."""
    drv = driver(True)
    warnings: list[str] = []
    checks = _session_checks("r1", drv.bgp_neighbors().value, "range", warnings, "default", drv)
    [c] = [c for c in checks if c["type"] == "bgp_prefixes" and c["afi"] == "ipv4-unicast"]
    return c


def test_bgp_received_leaves_out_a_history_only_prefix():
    """The listing holds 0.0.0.0/0 only as a history path (a route isp withdrew): it isn't a prefix isp sends."""
    [path] = json.loads(listing(True))["routes"][GONE]
    assert path["history"] is True and "valid" not in path and "bestpath" not in path
    assert driver(True).bgp_neighbors().value[NEIGHBOR].prefixes["ipv4-unicast"] == 1   # the history path dropped
    try:
        got = driver(True).bgp_received(NEIGHBOR).value
    except DriverError:
        return   # a refusal: never a received prefix
    assert GONE not in got, (f"bgp_received lists {sorted(got)} from {NEIGHBOR}: {GONE} is only a dampening history "
                             "entry there, a route the neighbor withdrew")


def test_record_does_not_allow_the_withdrawn_prefix_in_only():
    """record's closed-world list is what the neighbor sends today: a history entry isn't."""
    c = recorded()
    assert GONE not in c.get("only", []), (f"record wrote {c}: {GONE} is in `only` though {NEIGHBOR} withdrew it "
                                           "(a dampening history entry), so it may come back unnoticed")


def test_the_recorded_check_fails_when_the_withdrawn_prefix_comes_back():
    """The false pass: the default comes back from isp, a prefix the baseline never saw it send."""
    c = recorded()
    raw = {k: v for k, v in c.items() if k not in ("type", "node", "neighbor")}
    r = prefixes_check(raw, history=False)
    assert not r.passed, f"the recorded check {raw} passed with {GONE} sent again: {r.detail}"


def test_only_check_passes_while_a_history_entry_is_listed():
    """The false fail: 10.20.0.0/24 is the one prefix isp sends, as `only` allows; the history entry is no prefix."""
    r = prefixes_check({"min": 1, "max": 3, "only": [LIVE]}, history=True)
    assert r.passed, (f"`bgp_prefixes only: [{LIVE}]` on {NEIGHBOR} doesn't pass while {GONE} is listed as a "
                      f"dampening history entry: {r.detail}")
