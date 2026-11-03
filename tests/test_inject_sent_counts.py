"""inject_routes proves the routes left the injecting node (acceptance round B-5): bgpd's sent-prefix count per peer
(pfxSnt), read before the injection and while the routes are still in, must rise for some peer. Live FRR 10.4.1
captures of examples/frr-bgp (tests/fixtures/SOURCES.yml): sent (3 then 4), and denied outbound on r1 (3 then 3)."""
import json
import time
from pathlib import Path

import pytest

from netdryrun.faults import RouteInjection
from netdryrun.lab import ExecResult, LabError

FX = Path(__file__).parent / "fixtures"


class SummaryLab:
    """Answers the summary and neighbor commands with the next capture each; every other command succeeds."""

    def __init__(self, *answers, neighbors=()):
        self.answers, self.neighbors = list(answers), list(neighbors)

    def exec(self, node, cmd, timeout=60, input=None):
        if cmd[-1:] == ["show bgp ipv4 unicast summary json"]:
            return ExecResult(cmd, 0, self.answers.pop(0), "")
        if cmd[-1:] == ["show bgp neighbors json"]:
            return ExecResult(cmd, 0, self.neighbors.pop(0) if self.neighbors else "{}", "")
        return ExecResult(cmd, 0, "", "")


def v2(name, kind):
    return (FX / f"frr_v2_inject_{name}_{kind}.txt").read_text(encoding="utf-8")


def v2_injection(after):
    """ce1 on the corpus v2 lab (FRR 10.4.1): before the injection, then `after` while the routes are still in."""
    lab = SummaryLab(v2("before", "summary"), v2(after, "summary"),
                     neighbors=[v2("before", "neighbors"), v2(after, "neighbors")])
    inj = RouteInjection(lab, "ce1", ["10.100.16.0/24"], [])
    inj._wait = lambda want_present: None
    inj.asn, inj.applied = "65100", True
    inj.sent_before, inj.resets_before = inj.sent(), inj.resets()
    inj.applied_at = time.monotonic() - 60   # the capture's reset is 15 s old: inside a 60 s injection
    return inj


def test_i8_a_prefix_limit_reset_by_the_receiver_means_the_routes_left():
    """Corpus v2 I8, live: ce1 floods 200 prefixes, pe1's maximum-prefix 50 tears the session down (ce1 receives
    Cease 0601). The sent count then reads 0, but the routes left: the scenario is judged as usual."""
    inj = v2_injection("maxprefix")
    inj.restore()
    assert inj.left is True


@pytest.mark.parametrize("after", ["linkdown", "clear"])
def test_any_other_reset_proves_nothing(after):
    """ce1's link to pe1 down (No path to specified Neighbor), or a clear from ce1 (no reason on ce1's side): the
    session reset, but not over a prefix limit, so the routes are not shown to have left: inconclusive."""
    inj = v2_injection(after)
    inj.restore()
    assert inj.left is False


def test_the_v2_baseline_reads_live():
    inj = v2_injection("maxprefix")
    assert inj.sent_before == {("ipv4", "10.0.1.1"): 5}
    assert inj.resets_before == {"10.0.1.1": (0, None, None, frozenset({"ipv4Unicast"}), None)}


def injection(*names):
    lab = SummaryLab(*[(FX / f"frr_bgp_summary_inject_{n}.txt").read_text(encoding="utf-8") for n in names])
    inj = RouteInjection(lab, "r1", ["100.64.0.0/24"], [])
    inj._wait = lambda want_present: None
    inj.asn, inj.applied = "65001", True
    inj.sent_before = inj.sent()
    return inj


def test_sent_counts_per_peer_live():
    assert injection("before").sent_before == {("ipv4", "10.0.12.2"): 3, ("ipv4", "10.0.13.2"): 3}


def test_routes_that_were_sent_left():
    inj = injection("before", "after")
    inj.restore()
    assert inj.left is True


def test_routes_denied_outbound_on_the_injector_never_left():
    inj = injection("denied_before", "denied_after")
    inj.restore()
    assert inj.left is False


def test_counts_unreadable_at_restore_are_unknown_not_left():
    inj = injection("before")
    inj.lab.answers.append('{"peers": {"10.0.12.2": {"state": "Established"}}}')
    inj.restore()
    assert inj.left is None


def test_a_count_missing_before_the_injection_stops_it():
    lab = SummaryLab('{"peers": {"10.0.12.2": {"pfxSnt": "3"}}}')
    with pytest.raises(LabError) as e:
        RouteInjection(lab, "r1", ["100.64.0.0/24"], []).sent()
    assert str(e.value) == ("inject_routes on r1: no sent-prefix count for 10.0.12.2 "
                            "(`show bgp ipv4 unicast summary json`)")


# --- Layer 6 on b03cb7a: the routes must leave towards every established peer, not just one ------------------------

def _after(**counts):
    """The live `after` capture with some peers' sent counts (or states) changed."""
    import json
    d = json.loads((FX / "frr_bgp_summary_inject_after.txt").read_text(encoding="utf-8"))
    for peer, change in counts.items():
        d["peers"][peer.replace("_", ".")].update(change)
    return json.dumps(d)


def test_routes_that_reached_one_peer_but_not_another_did_not_leave():
    """r1 injects, its outbound filter towards 10.0.13.2 holds them back, 10.0.12.2 gets them: a check on the far
    side of 10.0.13.2 passed on nothing. Inconclusive, naming the peer (it was left=True)."""
    lab = SummaryLab((FX / "frr_bgp_summary_inject_before.txt").read_text(encoding="utf-8"),
                     _after(**{"10_0_13_2": {"pfxSnt": 3}}))
    inj = RouteInjection(lab, "r1", ["100.64.0.0/24"], [])
    inj._wait = lambda want_present: None
    inj.asn, inj.applied = "65001", True
    inj.sent_before, inj.resets_before = inj.sent(), inj.resets()
    inj.restore()
    assert (inj.left, inj.quiet) == (False, ["10.0.13.2"])


def test_a_peer_that_was_down_before_the_injection_is_not_waited_for():
    before = _after(**{"10_0_12_2": {"pfxSnt": 3}, "10_0_13_2": {"pfxSnt": 0, "state": "Active"}})
    lab = SummaryLab(before, _after(**{"10_0_13_2": {"pfxSnt": 0, "state": "Active"}}))
    inj = RouteInjection(lab, "r1", ["100.64.0.0/24"], [])
    inj._wait = lambda want_present: None
    inj.asn, inj.applied = "65001", True
    inj.sent_before, inj.resets_before = inj.sent(), inj.resets()
    assert inj.sent_before == {("ipv4", "10.0.12.2"): 3}
    inj.restore()
    assert (inj.left, inj.quiet) == (True, [])


def test_a_peer_without_a_state_stops_the_injection():
    lab = SummaryLab('{"peers": {"10.0.12.2": {"pfxSnt": 3}}}')
    with pytest.raises(LabError) as e:
        RouteInjection(lab, "r1", ["100.64.0.0/24"], []).sent()
    assert str(e.value) == ("inject_routes on r1: no session state for 10.0.12.2 "
                            "(`show bgp ipv4 unicast summary json`)")


# --- Layer 6 round 2 on eaa323c: all the injected prefixes, and a reset proven to be theirs -------------------------

def _counts(before, after, prefixes):
    lab = SummaryLab(json.dumps({"peers": {"10.0.12.2": {"pfxSnt": before, "state": "Established"}}}),
                     json.dumps({"peers": {"10.0.12.2": {"pfxSnt": after, "state": "Established"}}}))
    inj = RouteInjection(lab, "r1", prefixes, [])
    inj._wait = lambda want_present: None
    inj.asn, inj.applied = "65001", True
    inj.sent_before, inj.resets_before = inj.sent(), inj.resets()
    inj.restore()
    return inj.left, inj.quiet


THREE = ["203.0.113.0/24", "198.51.100.0/24", "192.0.2.0/24"]


def test_a_filter_that_lets_one_of_three_through_has_not_sent_them():
    """pfxSnt 4 -> 5 with three injected: two were held back, and a check on that side passed on nothing (left)."""
    assert _counts(4, 5, THREE) == (False, ["10.0.12.2"])


def test_all_three_sent_left():
    assert _counts(4, 7, THREE) == (True, [])


def _maxprefix(change, applied_ago=60):
    after = json.loads(v2("maxprefix", "neighbors"))
    after["10.0.1.1"].update(change)
    lab = SummaryLab(v2("before", "summary"), v2("maxprefix", "summary"),
                     neighbors=[v2("before", "neighbors"), json.dumps(after)])
    inj = RouteInjection(lab, "ce1", ["10.100.16.0/24"], [])
    inj._wait = lambda want_present: None
    inj.asn, inj.applied = "65100", True
    inj.sent_before, inj.resets_before = inj.sent(), inj.resets()
    inj.applied_at = time.monotonic() - applied_ago
    inj.restore()
    return inj.left


def test_a_prefix_limit_reset_on_a_session_with_another_family_proves_nothing():
    """The session carries IPv6 too: the limit it hit may be IPv6's, so the IPv4 routes aren't shown to have left."""
    assert _maxprefix({"addressFamilyInfo": {"ipv4Unicast": {}, "ipv6Unicast": {}}}) is False


def test_a_prefix_limit_reset_from_before_the_injection_proves_nothing():
    """The capture's reset is 15 s old; an injection 5 s ago can't have caused it."""
    assert _maxprefix({}, applied_ago=5) is False


@pytest.mark.parametrize("change", [{"addressFamilyInfo": None}, {"lastResetTimerMsecs": None}])
def test_a_prefix_limit_reset_with_its_family_or_time_unread_proves_nothing(change):
    assert _maxprefix(change) is False
