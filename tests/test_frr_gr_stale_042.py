"""The edges of the RT-0072 fix beyond its oracle (tests/oracles/FP-042-FRRGRSTALE).

During a BGP graceful restart FRR keeps the peer's paths, marked stale, until End-of-RIB, and acceptedPrefixCounter
counts them. A family whose peer set the F-bit (`gracefulRestartInfo.<afi>.fBit`) and whose End-of-RIB isn't read as
received is no settled count now: `bgp_prefixes` doesn't judge any bound on it, and `record` leaves it out. Every FRR
neighbor capture in tests/fixtures (F-bit false, graceful restart off, End-of-RIB received) reads as before."""
import copy
import json
from pathlib import Path

import pytest

from netdryrun.checks import Unready, _counted, run_check
from netdryrun.config import _validate_check
from netdryrun.drivers.base import BgpNeighbor
from netdryrun.drivers.frr import FrrDriver, gr_stale_window, listed_stale, parse_bgp_neighbors
from netdryrun.drivers.sonic import SonicDriver
from netdryrun.lab import ExecResult
from netdryrun.record import _session_checks

FX = Path(__file__).resolve().parent / "fixtures"
NBR = "10.0.13.2"
STALE = json.loads((FX / "frr1041_rpgr_r1_neighbors_stale.json").read_text(encoding="utf-8"))
AFTER = json.loads((FX / "frr1041_rpgr_r1_neighbors_after_eor.json").read_text(encoding="utf-8"))


def gr(doc):
    return doc[NBR]["gracefulRestartInfo"]


def with_v6(doc, *, v6_recv: bool, v6_fbit: bool = True):
    """The window capture with a second family: ipv6Unicast settled or pending on its own."""
    d = copy.deepcopy(doc)
    n = d[NBR]
    n["addressFamilyInfo"]["ipv6Unicast"] = {"acceptedPrefixCounter": 2}
    g = n["gracefulRestartInfo"]
    g["ipv6Unicast"] = copy.deepcopy(g["ipv4Unicast"])
    g["ipv6Unicast"]["fBit"] = v6_fbit
    g["ipv6Unicast"]["endOfRibStatus"]["endOfRibRecv"] = v6_recv
    if v6_recv:
        g["endOfRibRecv"] = {**g["endOfRibRecv"], "ipv6Unicast": True}
    return d


def unread(doc) -> dict:
    return parse_bgp_neighbors(json.dumps(doc))[NBR].prefixes_unread


# --- the driver's read --------------------------------------------------------------------------------------------

def test_window_capture_is_unsettled_after_eor_is_settled():
    assert set(unread(STALE)) == {"ipv4-unicast"}
    assert "End-of-RIB" in unread(STALE)["ipv4-unicast"] and "(4)" in unread(STALE)["ipv4-unicast"]
    assert unread(AFTER) == {}
    assert parse_bgp_neighbors(json.dumps(AFTER))[NBR].prefixes == {"ipv4-unicast": 3}


def test_the_eor_flag_decides():
    """Mutant: the End-of-RIB flag ignored. The window capture with End-of-RIB received in both reads is settled."""
    d = copy.deepcopy(STALE)
    gr(d)["ipv4Unicast"]["endOfRibStatus"]["endOfRibRecv"] = True
    gr(d)["endOfRibRecv"] = {"ipv4Unicast": True}
    assert unread(d) == {}
    assert unread(STALE) != {}


def test_the_fbit_decides():
    """Mutant: the condition inverted, or the F-bit ignored. F-bit clear, End-of-RIB pending: bgpd flushed the stale
    paths when the session came back (repro-042c F-GR run 1), so the count is the peer's, as before the fix."""
    d = copy.deepcopy(STALE)
    gr(d)["ipv4Unicast"]["fBit"] = False
    assert unread(d) == {}
    d2 = copy.deepcopy(AFTER)
    gr(d2)["ipv4Unicast"]["fBit"] = False
    assert unread(d2) == {}


def test_each_family_reads_its_own_eor():
    """Mutant: the wrong family's End-of-RIB. ipv4 pending with ipv6 received, and the other way round."""
    d = with_v6(STALE, v6_recv=True)
    assert set(unread(d)) == {"ipv4-unicast"}
    d = with_v6(AFTER, v6_recv=False)
    assert set(unread(d)) == {"ipv6-unicast"}
    d = with_v6(AFTER, v6_recv=False, v6_fbit=False)
    assert unread(d) == {}


@pytest.mark.parametrize("per_afi, top", [(True, {}), (False, {"ipv4Unicast": True}), (None, {}),
                                          ("false", {}), (True, None), (True, {"ipv4Unicast": "yes"})])
def test_eor_reads_that_disagree_or_are_unreadable_are_unsettled(per_afi, top):
    d = copy.deepcopy(STALE)
    gr(d)["ipv4Unicast"]["endOfRibStatus"]["endOfRibRecv"] = per_afi
    if top is None:
        del gr(d)["endOfRibRecv"]
    else:
        gr(d)["endOfRibRecv"] = top
    assert "can't be read as received" in unread(d)["ipv4-unicast"]


@pytest.mark.parametrize("fbit", ["true", 1, None, [], {}])
def test_an_fbit_that_isnt_a_boolean_refuses(fbit):
    for doc in (STALE, AFTER):   # even with End-of-RIB received: output this driver doesn't know
        d = copy.deepcopy(doc)
        gr(d)["ipv4Unicast"]["fBit"] = fbit
        assert "doesn't know" in unread(d)["ipv4-unicast"]


def test_a_family_block_that_isnt_an_object_refuses():
    d = copy.deepcopy(AFTER)
    gr(d)["ipv4Unicast"] = "Restart"
    assert "doesn't know" in unread(d)["ipv4-unicast"]


def test_no_fbit_beside_eor_status_fails_closed_until_eor():
    d = copy.deepcopy(STALE)
    del gr(d)["ipv4Unicast"]["fBit"]
    assert set(unread(d)) == {"ipv4-unicast"}
    d = copy.deepcopy(AFTER)
    del gr(d)["ipv4Unicast"]["fBit"]
    assert unread(d) == {}


def test_graceful_restart_off_or_absent_is_unchanged():
    d = copy.deepcopy(STALE)
    gr(d)["localGrMode"] = "Disable*"
    assert unread(d) == {}
    d = copy.deepcopy(STALE)
    del d[NBR]["gracefulRestartInfo"]
    assert unread(d) == {}
    d = copy.deepcopy(STALE)
    del gr(d)["ipv4Unicast"]
    assert unread(d) == {}


def test_a_session_not_established_reads_nothing_unsettled():
    d = copy.deepcopy(STALE)
    d[NBR]["bgpState"] = "Active"
    assert unread(d) == {}


def _frr_neighbor_captures():
    out = []
    for f in sorted(FX.rglob("*")):
        if not f.is_file() or f.name.startswith("frr1041_rpgr_r1_neighbors_stale"):
            continue
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except (ValueError, UnicodeDecodeError):
            continue
        if isinstance(data, dict) and data and all(isinstance(v, dict) and "bgpState" in v for v in data.values()) \
                and any("gracefulRestartInfo" in v for v in data.values()):
            out.append(f)
    return out


CAPTURES = _frr_neighbor_captures()


def test_the_capture_survey_found_the_captures():
    assert len(CAPTURES) >= 15


@pytest.mark.parametrize("f", CAPTURES, ids=lambda f: f.name)
def test_every_other_frr_capture_reads_as_before(f):
    """Every FRR `show bgp neighbors json` capture but the window: no family unsettled, the same counts."""
    text = f.read_text(encoding="utf-8")
    data = json.loads(text)
    for key, n in parse_bgp_neighbors(text).items():
        assert n.prefixes_unread == {}, (f.name, key)
    for addr, info in data.items():
        assert gr_stale_window(addr, info, {}) == {}, (f.name, addr)


# --- the stale paths a listing shows ------------------------------------------------------------------------------

def test_listed_stale_counts_the_flag():
    routes = {"routes": {"10.70.1.0/24": [{"stale": True}, {"valid": True}], "10.70.2.0/24": [{"stale": False}]}}
    assert listed_stale(json.dumps(routes), "cmd") == 1
    assert listed_stale("{}", "cmd") == 0
    with pytest.raises(Exception, match="stale"):
        listed_stale(json.dumps({"routes": {"10.70.1.0/24": [{"stale": "yes"}]}}), "cmd")


# --- the check and record -----------------------------------------------------------------------------------------

class Lab:
    def __init__(self, neighbors: str, listing: str | None = None):
        self.neighbors, self.listing = neighbors, listing

    def exec(self, node, cmd, timeout=60, input=None):
        if cmd[:2] == ["vtysh", "-c"] and cmd[2] == "show bgp neighbors json":
            return ExecResult(cmd, 0, self.neighbors, "")
        if cmd[:2] == ["vtysh", "-c"] and cmd[2].endswith("routes json") and self.listing is not None:
            return ExecResult(cmd, 0, self.listing, "")
        return ExecResult(cmd, 1, "", "not captured")


class Clock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t

    def sleep(self, s):
        self.t += max(s, 0.5)


def check(driver, **raw):
    c = Clock()
    chk = _validate_check(0, {"node": "r1", "type": "bgp_prefixes", "neighbor": NBR, **raw}, 20)
    return run_check(chk, driver, clock=c, sleep=c.sleep)


@pytest.mark.parametrize("cls", [FrrDriver, SonicDriver])
@pytest.mark.parametrize("bound", [{"min": 0, "max": 100}, {"min": 3}, {"min": 4}, {"max": 100}, {"exact": 4}])
def test_no_bound_passes_in_the_window(cls, bound):
    r = check(cls(Lab(json.dumps(STALE)), "r1"), **bound)
    assert not r.passed and "not a settled count" in r.detail and r.samples_unready == r.attempts


@pytest.mark.parametrize("cls", [FrrDriver, SonicDriver])
def test_the_count_settles_after_eor(cls):
    assert check(cls(Lab(json.dumps(AFTER)), "r1"), min=3).passed
    assert not check(cls(Lab(json.dumps(AFTER)), "r1"), min=4).passed


def _addpath(doc):
    d = copy.deepcopy(doc)
    d[NBR]["neighborCapabilities"]["addPath"]["ipv4Unicast"]["txReceived"] = True
    return d


def _listing(stale: bool):
    paths = [{"valid": True, "bestpath": True, **({"stale": True} if stale else {})}]
    return json.dumps({"routes": {f"10.70.{i}.0/24": paths for i in range(1, 4)}})


@pytest.mark.parametrize("cls", [FrrDriver, SonicDriver])
def test_addpath_listing_with_stale_paths_is_unsettled(cls):
    """The listing (add-path from the peer) shows stale paths though the neighbor's state reads settled."""
    d = _addpath(AFTER)
    r = check(cls(Lab(json.dumps(d), _listing(stale=True)), "r1"), min=3)
    assert not r.passed and "stale path" in r.detail
    assert check(cls(Lab(json.dumps(d), _listing(stale=False)), "r1"), min=3).passed


def test_addpath_in_the_window_reads_no_listing():
    lab = Lab(json.dumps(_addpath(STALE)), _listing(stale=False))
    n = FrrDriver(lab, "r1").bgp_neighbors().value[NBR]
    assert "End-of-RIB" in n.prefixes_unread["ipv4-unicast"] and n.prefixes == {"ipv4-unicast": 4}


def test_counted_judges_no_bound_on_an_unsettled_count():
    n = BgpNeighbor(NBR, "established", {"ipv4-unicast": 4}, prefixes_unread={"ipv4-unicast": "why"})
    ok, detail, _ = _counted(n, "ipv4-unicast", 4, 0, None, [])
    assert not ok and isinstance(detail, Unready) and detail.endswith("why")


@pytest.mark.parametrize("mode", ["range", "exact", "min"])
def test_record_leaves_an_unsettled_count_out(mode):
    warnings: list[str] = []
    checks = _session_checks("r1", parse_bgp_neighbors(json.dumps(STALE)), mode, warnings)
    assert not [c for c in checks if c["type"] == "bgp_prefixes" and c["afi"] == "ipv4-unicast"]
    assert any("isn't settled" in w and w.startswith("INCOMPLETE BASELINE") for w in warnings)
    warnings = []
    checks = _session_checks("r1", parse_bgp_neighbors(json.dumps(AFTER)), mode, warnings)
    assert [c for c in checks if c["type"] == "bgp_prefixes" and c["afi"] == "ipv4-unicast"]
