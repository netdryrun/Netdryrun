"""The attributable prefix-limit proof (0.4.1, owner decision 2026-11-04; spec design/attributable-limit-proof.md in HQ):
a peer whose session reset while injected routes were in counts as reached for that family only when the peer itself
says it sent a max-prefix Cease for exactly the injector's session after the routes went in, the arithmetic says the
injection tripped it (before <= limit < before + injected, before read twice and equal), the injection was the
scenario's only fault, the peer is a lab node on the frr driver, and the limit is in the injection's family. Anything
else stays quiet, and the run inconclusive. Device output: live FRR 10.4.1 captures (frr_maxpfx_*,
tests/fixtures/SOURCES.yml)."""
import copy
import json
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from netdryrun import runner
from netdryrun.faults import RouteInjection
from netdryrun.lab import ExecResult

FX = Path(__file__).parent / "fixtures"
BEFORE = json.loads((FX / "frr_maxpfx_pe1_neighbor_before.txt").read_text(encoding="utf-8"))
TRIPPED = json.loads((FX / "frr_maxpfx_pe1_neighbor_tripped.txt").read_text(encoding="utf-8"))
RETRIPPED = json.loads((FX / "frr_maxpfx_pe1_neighbor_retripped.txt").read_text(encoding="utf-8"))
RUNNING = (FX / "frr_maxpfx_pe1_running_config.txt").read_text(encoding="utf-8")
VERSION = (FX / "frr_show_version_10.4.1.txt").read_text(encoding="utf-8")
CE1, PE1 = "10.0.1.2", "10.0.1.1"            # ce1's and pe1's ends of the customer session
FLOOD = [f"10.100.{i}.0/24" for i in range(16, 216)]   # I8: 200 /24s from 10.100.16.0/24


def addrs(*ips: str) -> str:
    """`ip -j addr` with these IPv4 addresses on eth1, plus a management address unique to the node."""
    return json.dumps([{"ifname": "eth1", "addr_info": [{"family": "inet", "local": ip, "prefixlen": 30} for ip in ips]}])


def neighbor(base: dict, **af_change) -> dict:
    """pe1's record for ce1, with fields of its ipv4Unicast family changed."""
    d = copy.deepcopy(base)
    d[CE1]["addressFamilyInfo"]["ipv4Unicast"].update(af_change)
    return d


def reset(base: dict, **change) -> dict:
    d = copy.deepcopy(base)
    for k, v in change.items():
        if v is None:
            d[CE1].pop(k, None)
        else:
            d[CE1][k] = v
    return d


def summary(peers: dict) -> str:
    return json.dumps({"peers": {p: {"state": s, "pfxSnt": 0} for p, s in peers.items()}})


def steady(peers, dropped=None, up_ms=600000) -> str:
    dropped = dropped or {}
    return json.dumps({p: {"connectionsDropped": dropped.get(p, 0), "addressFamilyInfo": {"ipv4Unicast": {}},
                           "bgpTimerUpMsec": up_ms, "minBtwnAdvertisementRunsTimerMsecs": 0} for p in peers})


class LimitLab:
    """ce1 injects; pe1 is its one peer. pe1's neighbor record is the next of `pe1_records` each read (two at apply,
    one at restore); ce1's own session reads drop as given."""

    def __init__(self, pe1_records, *, running=RUNNING, owners=None, ce1_dropped=1, version=VERSION, log=""):
        self.nodes = {n: SimpleNamespace(name=n, container=f"clab-t-{n}") for n in ("ce1", "pe1", "up1")}
        self.pe1_records = [json.dumps(r) if isinstance(r, dict) else r for r in pe1_records]
        self.running, self.version, self.log = running, version, log
        self.owners = owners if owners is not None else {"ce1": [CE1], "pe1": [PE1], "up1": ["10.0.2.2"]}
        self.ce1_neighbors = [steady([PE1]), steady([PE1]), steady([PE1], {PE1: ce1_dropped}, up_ms=5000)]
        self.asked = []

    def exec(self, node, cmd, timeout=60, input=None):
        c = cmd[-1]
        self.asked.append((node, c))
        if cmd[:3] == ["ip", "-j", "addr"]:
            return ExecResult(cmd, 0, addrs(*self.owners.get(node, [])), "")
        if node == "ce1" and c == "show bgp ipv4 unicast summary json":
            return ExecResult(cmd, 0, summary({PE1: "Established"}), "")
        if node == "ce1" and c == "show bgp neighbors json":
            return ExecResult(cmd, 0, self.ce1_neighbors.pop(0) if self.ce1_neighbors else steady([PE1]), "")
        if node == "pe1" and c == "show bgp neighbors json":
            return ExecResult(cmd, 0, self.pe1_records.pop(0) if self.pe1_records else "{}", "")
        if node == "pe1" and c == "show version":
            return ExecResult(cmd, 0, self.version, "")
        if node == "pe1" and c == "show running-config":
            return ExecResult(cmd, 0, self.running, "")
        if c.endswith(" advertised-routes detail json"):
            return ExecResult(cmd, 0, "{}", "")
        return ExecResult(cmd, 0, "", "")

    def boot_log(self, node):
        return ExecResult(["docker", "logs"], 0, self.log if node == "pe1" else "", "")


def injection(lab, prefixes=FLOOD, *, alone=True, frr=("pe1",), ago=30, listed=None):
    """An injection on ce1 whose routes went in `ago` seconds ago, its peers, sessions and limits read as apply()
    reads them (limits twice, as apply does: once before and once after recording what the peer already had)."""
    inj = RouteInjection(lab, "ce1", list(prefixes), [], alone=alone, is_frr=lambda n: n in frr)
    inj._wait = lambda want_present: None
    inj.asn, inj.applied = "65100", True
    inj.peers_before, inj.sessions_before = inj.established(), inj.sessions()
    inj.limits = inj.read_limits()
    inj.listed_before = listed or {}
    inj.limits_again = inj.read_limits()
    inj.applied_at = time.monotonic() - ago
    return inj


def restored(pe1_records, prefixes=FLOOD, **kw):
    lab = LimitLab(pe1_records, **{k: kw.pop(k) for k in ("running", "owners", "ce1_dropped", "version", "log")
                                   if k in kw})
    inj = injection(lab, prefixes, **kw)
    inj.restore()
    return inj


def proven(inj) -> bool:
    return inj.left is True and PE1 in inj.limit_proven and inj.quiet == {}


def not_proven(inj) -> bool:
    return inj.left is False and inj.quiet == {PE1: inj.prefixes} and inj.limit_proven == {}


# --- the green case: I8 as captured ------------------------------------------------------------------------------

def test_the_captured_i8_trip_proves_the_flood_reached_pe1():
    inj = restored([BEFORE, BEFORE, TRIPPED])
    assert proven(inj)
    assert inj.limit_proven[PE1] == ("pe1 sent ce1's session a max-prefix Cease (Cease/Maximum Number of Prefixes "
                                     "Reached) after the routes went in: 1 prefix accepted before, limit 50, 200 injected")


def test_a_re_trip_after_the_restart_still_proves_it():
    """Coordinator (C): re-trip allowed, not required. After `restart 1` the flood trips it again (2 drops)."""
    assert proven(restored([BEFORE, BEFORE, RETRIPPED], ago=120))   # read 100 s after apply, as captured


def test_the_proof_keeps_the_scenarios_passes():
    inj = restored([BEFORE, BEFORE, TRIPPED])
    check = SimpleNamespace(name="[customer floods 200 prefixes] I8 upstream still receives at most 51 prefixes")
    passed = runner.Result(check, True, "1 prefix", 1, 1.0, "")
    out = runner._never_left([inj], [passed])
    assert [r.passed for r in out] == [True]
    assert out[0].detail == ("1 prefix (injected routes shown to arrive by a max-prefix reset: 10.0.1.1: pe1 sent ce1's "
                             "session a max-prefix Cease (Cease/Maximum Number of Prefixes Reached) after the routes went "
                             "in: 1 prefix accepted before, limit 50, 200 injected)")


# --- (ii) the arithmetic, and case 07 -----------------------------------------------------------------------------

def test_case_07_the_change_brought_the_count_to_49_and_one_more_prefix_is_not_over_the_limit():
    """B = 49, I = 1: 50 is not over 50, so the injection alone can't have tripped it."""
    before = neighbor(BEFORE, acceptedPrefixCounter=49)
    assert not_proven(restored([before, before, TRIPPED], ["10.100.16.0/24"]))


def test_case_07_three_before_and_200_injected_is_attributed():
    """The change (two more /24s on ce1) is deployed before apply, so B includes them: 3 + 200 > 50."""
    before = neighbor(BEFORE, acceptedPrefixCounter=3)
    assert proven(restored([before, before, TRIPPED]))


def test_a_count_already_over_the_limit_before_the_injection_is_never_attributed():
    before = neighbor(BEFORE, acceptedPrefixCounter=51)
    assert not_proven(restored([before, before, TRIPPED]))


def test_a_count_that_changed_between_the_two_reads_at_apply_is_not_proven():
    """The change still growing, or a race: B isn't known."""
    assert not_proven(restored([BEFORE, neighbor(BEFORE, acceptedPrefixCounter=2), TRIPPED]))


def test_prefixes_the_peer_already_had_dont_count_towards_the_injection():
    """I counts only what the injector hadn't advertised to pe1 before: 49 before, 2 injected, one already listed."""
    before = neighbor(BEFORE, acceptedPrefixCounter=49)
    inj = restored([before, before, TRIPPED], ["10.100.16.0/24", "10.100.17.0/24"],
                   listed={PE1: {"10.100.16.0/24"}})
    assert inj.left is False and inj.limit_proven == {}


# --- (i) the record: what reset the session ----------------------------------------------------------------------

def test_a_link_flap_reset_is_not_a_limit_proof():
    """Live shape (frr_v2_inject_linkdown_neighbors): no Cease, "No path to specified Neighbor"."""
    flap = reset(TRIPPED, lastNotificationReason=None, lastNotificationHardReset=None,
                 lastResetDueTo="No path to specified Neighbor", lastResetCode=27)
    assert not_proven(restored([BEFORE, BEFORE, flap]))


def test_a_reset_with_no_record_of_why_is_not_proven():
    bare = reset(TRIPPED, lastNotificationReason=None, lastResetDueTo=None, lastResetCode=None)
    assert not_proven(restored([BEFORE, BEFORE, bare]))


def test_a_max_prefix_cease_pe1_received_is_not_pe1s_limit():
    """ce1's own limit tripping (pe1 received the Cease) says nothing about pe1 accepting the flood."""
    got = reset(TRIPPED, lastResetDueTo="BGP Notification received")
    assert not_proven(restored([BEFORE, BEFORE, got]))


def test_a_cease_with_another_code_or_reason_is_not_proven():
    assert not_proven(restored([BEFORE, BEFORE, reset(TRIPPED, lastResetCode=13)]))
    assert not_proven(restored([BEFORE, BEFORE, reset(TRIPPED, lastNotificationReason="Cease/Administrative Reset")]))


def test_a_max_prefix_record_for_another_session_is_not_proven():
    """pe1's trip is on a different neighbor; its session with ce1 shows a plain drop."""
    other = {"10.0.9.9": TRIPPED[CE1], CE1: reset(TRIPPED, lastNotificationReason=None, lastResetDueTo="Peer closed "
                                                  "the session", lastResetCode=10)[CE1]}
    assert not_proven(restored([BEFORE, BEFORE, other]))


def test_a_later_reset_for_another_reason_replaces_the_proof():
    """(C): a reset after the max-prefix one, for any other reason, fails: the last reset is no longer the limit."""
    later = reset(RETRIPPED, lastNotificationReason=None, lastResetDueTo="No path to specified Neighbor",
                  lastResetCode=27)
    assert not_proven(restored([BEFORE, BEFORE, later]))


def test_a_record_without_a_new_drop_is_not_proven():
    """A max-prefix reason left over from before the injection: the drop count never moved."""
    old = reset(BEFORE, lastNotificationReason="Cease/Maximum Number of Prefixes Reached",
                lastResetDueTo="BGP Notification send", lastResetCode=14, lastResetTimerMsecs=1000)
    assert not_proven(restored([BEFORE, BEFORE, old]))


# --- (iii) timing -------------------------------------------------------------------------------------------------

def test_a_max_prefix_reset_from_before_the_routes_went_in_is_not_proven():
    """The reset is 40 s old, the injection 30 s: it happened before apply."""
    assert not_proven(restored([BEFORE, BEFORE, reset(TRIPPED, lastResetTimerMsecs=40000)], ago=30))


def test_a_reset_within_the_rounding_of_apply_is_not_proven():
    """bgpd counts whole seconds: a reset reading 30 s old for an injection 30.5 s old could be before apply."""
    assert not_proven(restored([BEFORE, BEFORE, reset(TRIPPED, lastResetTimerMsecs=30000)], ago=30.5))


def test_an_unreadable_reset_age_is_not_proven():
    assert not_proven(restored([BEFORE, BEFORE, reset(TRIPPED, lastResetTimerMsecs=None)]))
    assert not_proven(restored([BEFORE, BEFORE, reset(TRIPPED, lastResetTimerMsecs="1000")]))


# --- (iv) the only fault ------------------------------------------------------------------------------------------

def test_another_fault_in_the_scenario_leaves_it_unproven():
    """Another node's injection (or a link down) in the same scenario could have tripped the limit."""
    assert not_proven(restored([BEFORE, BEFORE, TRIPPED], alone=False))


# --- (v) and (0): family, limit, the peer -------------------------------------------------------------------------

def test_an_ipv6_injection_is_never_proven_by_an_ipv4_limit():
    lab = LimitLab([BEFORE, BEFORE, TRIPPED])
    inj = RouteInjection(lab, "ce1", ["2001:db8:66::/48"], [], alone=True, is_frr=lambda n: n == "pe1")
    inj._wait = lambda want_present: None
    inj.asn, inj.applied = "65100", True
    inj.peers_before, inj.sessions_before = {"ipv6": [PE1]}, inj.sessions()
    inj.limits, inj.limits_again, inj.listed_before = inj.read_limits(), inj.read_limits(), {}
    inj.applied_at = time.monotonic() - 30
    inj.established = lambda: {"ipv6": [PE1]}
    inj.restore()
    assert inj.left is False and inj.limit_proven == {}


def test_a_warning_only_limit_is_not_proven():
    warn = RUNNING.replace("maximum-prefix 50 restart 1", "maximum-prefix 50 warning-only")
    assert not_proven(restored([BEFORE, BEFORE, TRIPPED], running=warn))


@pytest.mark.parametrize("change", [{"prefixAllowedMax": None}, {"prefixAllowedMax": "50"},
                                    {"acceptedPrefixCounter": None}, {"prefixAllowedMax": True}])
def test_an_unreadable_limit_or_count_is_not_proven(change):
    before = copy.deepcopy(BEFORE)
    af = before[CE1]["addressFamilyInfo"]["ipv4Unicast"]
    for k, v in change.items():
        af.pop(k) if v is None else af.__setitem__(k, v)
    assert not_proven(restored([before, before, TRIPPED]))


def test_a_limit_that_changed_by_restore_is_not_proven():
    assert not_proven(restored([BEFORE, BEFORE, neighbor(TRIPPED, prefixAllowedMax=100)]))


def test_a_peer_that_is_no_lab_node_is_not_proven():
    assert not_proven(restored([BEFORE, BEFORE, TRIPPED], owners={"ce1": [CE1], "pe1": ["10.0.3.1"], "up1": []}))


def test_a_peer_address_on_two_nodes_is_not_proven():
    assert not_proven(restored([BEFORE, BEFORE, TRIPPED], owners={"ce1": [CE1], "pe1": [PE1], "up1": [PE1]}))


def test_a_peer_on_another_driver_is_not_proven():
    assert not_proven(restored([BEFORE, BEFORE, TRIPPED], frr=()))


def test_by_default_no_injection_is_proven_by_a_limit():
    """Fail closed: a RouteInjection made without alone/is_frr (any caller but the runner's) never uses the proof."""
    lab = LimitLab([BEFORE, BEFORE, TRIPPED])
    inj = RouteInjection(lab, "ce1", FLOOD, [])
    inj._wait = lambda want_present: None
    inj.asn, inj.applied = "65100", True
    inj.peers_before, inj.sessions_before = inj.established(), inj.sessions()
    inj.limits, inj.limits_again, inj.listed_before = inj.read_limits(), inj.read_limits(), {}
    inj.applied_at = time.monotonic() - 30
    inj.restore()
    assert inj.left is False and inj.limit_proven == {}


def test_a_peer_that_came_up_during_the_injection_is_never_proven():
    """(vi): only a peer established when the routes went in."""
    lab = LimitLab([BEFORE, BEFORE, TRIPPED])
    inj = injection(lab)
    inj.peers_before = {"ipv4": []}
    inj.limits = inj.limits_again = inj.read_limits()
    inj.restore()
    assert inj.limit_proven == {} and inj.left is False


def test_an_unreadable_peer_record_at_restore_is_not_proven():
    assert not_proven(restored([BEFORE, BEFORE, "not json"]))


# --- coordinator (B): the I8 checks read established sessions only -------------------------------------------------

def test_an_upstream_session_that_is_down_never_passes_at_most_51():
    """A down session's count is 0, which satisfies `max: 51` on nothing: the check is not passed, whatever the proof
    says about pe1 (checks._bgp_prefixes, live shape of frr_maxpfx_up1_summary_during with the session down)."""
    from netdryrun.checks import _bgp_prefixes
    from netdryrun.drivers.base import BgpNeighbor
    obs = SimpleNamespace(value={"10.0.2.1": BgpNeighbor("10.0.2.1", "active", {"ipv4-unicast": 0})}, evidence=[])
    d = SimpleNamespace(bgp_neighbors=lambda vrf: obs)
    ok, detail, _ = _bgp_prefixes(d, {"neighbor": "10.0.2.1", "max": 51})
    assert (ok, detail) == (False, "session is active; prefix counts are only meaningful when established")


# --- coordinator conditions on the Cease reading (2026-11-04) ------------------------------------------------------

def test_another_frr_version_is_not_proven_until_it_has_a_fixture():
    """The record's strings are pinned to FRR 10.4.1 (show version on the peer node)."""
    assert not_proven(restored([BEFORE, BEFORE, TRIPPED], version=VERSION.replace("10.4.1_git", "10.5.0")))
    assert not_proven(restored([BEFORE, BEFORE, TRIPPED], version=""))


def test_a_forced_limit_counts_filtered_routes_and_is_not_proven():
    """`maximum-prefix N force` adds routes inbound policy filtered out to the count (bgp_maximum_prefix_overflow,
    PEER_FLAG_MAX_PREFIX_FORCE): the trip no longer says what was accepted."""
    forced = RUNNING.replace("maximum-prefix 50 restart 1", "maximum-prefix 50 force restart 1")
    assert not_proven(restored([BEFORE, BEFORE, TRIPPED], running=forced))


def test_a_warning_only_flag_in_the_record_is_not_proven():
    before = neighbor(BEFORE, prefixAllowedMaxWarning=True)
    assert not_proven(restored([before, before, TRIPPED]))


def test_two_limited_families_on_the_session_are_not_proven():
    """The record doesn't say which family tripped."""
    two = copy.deepcopy(BEFORE)
    two[CE1]["addressFamilyInfo"]["ipv6Unicast"] = {"acceptedPrefixCounter": 0, "prefixAllowedMax": 10}
    tripped = copy.deepcopy(TRIPPED)
    tripped[CE1]["addressFamilyInfo"]["ipv6Unicast"] = {"acceptedPrefixCounter": 0, "prefixAllowedMax": 10}
    assert not_proven(restored([two, two, tripped]))


LINE = "2026/11/04 15:01:39 BGP: [ABCDE-FGHIJ] %MAXPFXEXCEED: No. of IPv4 Unicast prefix received from {} {} exceed, limit {}"


def test_a_log_line_that_agrees_is_fine_and_none_is_needed():
    assert proven(restored([BEFORE, BEFORE, TRIPPED], log=LINE.format(CE1, 51, 50)))
    assert proven(restored([BEFORE, BEFORE, TRIPPED], log=""))


def test_a_log_line_that_disagrees_is_not_proven():
    assert not_proven(restored([BEFORE, BEFORE, TRIPPED], log=LINE.format(CE1, 51, 40)))
    assert not_proven(restored([BEFORE, BEFORE, TRIPPED], log=LINE.format(CE1, 50, 50)))
    assert not_proven(restored([BEFORE, BEFORE, TRIPPED], log=LINE.replace("IPv4", "IPv6").format(CE1, 51, 50)))


def test_a_log_line_for_another_session_changes_nothing():
    assert proven(restored([BEFORE, BEFORE, TRIPPED], log=LINE.format("10.0.9.9", 51, 40)))
