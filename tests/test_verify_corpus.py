"""verify's 0.4 acceptance cases from corpus v1, on snapshots captured live (FRR 10.4.1): `netdryrun verify` on
corpus/base against the case's edits, with no hand-written guards. Live reruns: see design/verify_change.md.

  18  `redistribute connected` on pe1     must fail with an empty intent
  23  pe1 originates 8.8.8.0/24           must fail with an empty intent
  06  the customer adds 10.100.1.0/24     must pass once that prefix is declared (declared growth)
"""
import json
from pathlib import Path

import pytest

from netdryrun.verify.engine import match
from netdryrun.verify.intent import parse_intent_text
from netdryrun.verify.snapshot import Snapshot

FIX = Path(__file__).parent / "fixtures" / "verify-corpus"
EMPTY = "intent: []\n"


def load(case):
    d = json.loads((FIX / f"{case}.json").read_text(encoding="utf-8"))
    return d, Snapshot.from_json(d["before"]), Snapshot.from_json(d["after"])


@pytest.mark.parametrize("case,leak", [
    ("18-redistribute-connected", "10.0.1.0/30"),            # an infrastructure /30 toward the customer
    ("23-fat-finger-third-party-origin", "8.8.8.0/24"),
])
def test_an_unsafe_change_fails_with_an_empty_intent(case, leak):
    d, before, after = load(case)
    assert d["verdict"] == "UNDECLARED CHANGES: DO NOT APPLY"           # what the live run said
    m = match(before, after, parse_intent_text(EMPTY, "empty"))
    assert m.status == "failed"
    assert any(x.key.node == "ce1" and x.key.prefix == leak for x in m.undeclared), sorted({x.key.where() for x in m.undeclared})


def test_declared_growth_passes():
    d, before, after = load("06-customer-adds-prefix")
    assert d["verdict"] == "INTENT MATCHED"
    # ce1 originates the block from a Null0 anchor (`ip route 10.100.1.0/24 Null0`): on ce1 the route drops
    # traffic, so from 0.4's gauntlet fix (R5) it is declared as a discard route, never as "installed"
    m = match(before, after, parse_intent_text(d["intent"], "case 06 as run live"))
    assert m.status == "failed" and any("ce1" in lr.reason and "discard" in lr.reason for lr in m.lines)
    declared = d["intent"].replace("appears_on: [ce1, pe1, pe2, up1, peer1]",
                                   "appears_on: [ce1]\n    state: discard\n  - prefix: 10.100.1.0/24\n"
                                   "    appears_on: [pe1, pe2, up1, peer1]")
    m = match(before, after, parse_intent_text(declared, "case 06"))
    assert m.status == "matched" and not m.undeclared
    # the same change undeclared fails, and declaring it on fewer nodes leaves the rest undeclared
    assert match(before, after, parse_intent_text(EMPTY, "empty")).status == "failed"
    fewer = declared.replace("appears_on: [pe1, pe2, up1, peer1]", "appears_on: [pe1]")
    m = match(before, after, parse_intent_text(fewer, "fewer"))
    assert m.status == "failed" and {x.key.node for x in m.undeclared} >= {"up1", "peer1"}


def test_the_captured_snapshots_include_ipv6_where_frr_reports_it():
    """IPv6 unicast is in the snapshot wherever the driver reports it (the corpus lab has link-local IPv6 only)."""
    _d, before, _a = load("06-customer-adds-prefix")
    assert any(k.afi == "ipv6" and k.kind == "rib" for k in before.items())
