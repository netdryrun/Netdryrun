"""inject_routes proves the routes left the injecting node (acceptance round B-5): bgpd's sent-prefix count per peer
(pfxSnt), read before the injection and while the routes are still in, must rise for some peer. Live FRR 10.4.1
captures of examples/frr-bgp (tests/fixtures/SOURCES.yml): sent (3 then 4), and denied outbound on r1 (3 then 3)."""
from pathlib import Path

import pytest

from netdryrun.faults import RouteInjection
from netdryrun.lab import ExecResult, LabError

FX = Path(__file__).parent / "fixtures"


class SummaryLab:
    """Answers the summary command with the next capture; every other command succeeds."""

    def __init__(self, *answers):
        self.answers = list(answers)

    def exec(self, node, cmd, timeout=60, input=None):
        if cmd[-1:] == ["show bgp ipv4 unicast summary json"]:
            return ExecResult(cmd, 0, self.answers.pop(0), "")
        return ExecResult(cmd, 0, "", "")


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
