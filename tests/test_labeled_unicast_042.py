"""A labeled-unicast family is never "doesn't carry <afi>-unicast" (RT-0080, oracle FP-042-FRRLU).

FRR 10.4.1 lists a session activated only for ipv4 labeled-unicast as `ipv4LabeledUnicast` alone (acceptedPrefixCounter
0) while it installs the peer's routes as BGP IPv4 unicast routes (tests/fixtures/frr1041_rplu_*). Drivers keep a family
a check can't name under the device's own name (FRR/SONiC `ipv4LabeledUnicast`, SR Linux `ipv4-labeled-unicast`), and
drivers.base.unicast_unread decides from those names when the unicast count can't be read: the check then fails every
bound with "can't be read", and record leaves it out with an INCOMPLETE BASELINE line.

Mutants these tests kill (each by name below): the other-version skip dropped (ipv6LabeledUnicast blocks ipv4), the
"labeled" condition dropped (a VPN family beside the unicast one blocks it), the condition inverted (an unnamed family
blocks nothing when the unicast family is missing), the check's early return dropped or limited to exact 0, evpn
blocking, record writing an unnamed family's check, record keeping the unicast count beside labeled-unicast, record
writing the B-3 exact 0 beside labeled-unicast.
"""
import json
from pathlib import Path

import pytest

from netdryrun import record as rec
from netdryrun.checks import _bgp_prefixes
from netdryrun.config import _validate_check
from netdryrun.drivers.base import NAMED_FAMILIES, BgpNeighbor, Observation, unicast_unread
from netdryrun.drivers.frr import parse_bgp_neighbors as frr_neighbors
from netdryrun.drivers.srlinux import parse_bgp_neighbors as srl_neighbors

FX = Path(__file__).resolve().parent / "fixtures"
LU_PEER = "10.0.12.2"


def lu_capture() -> dict:
    return json.loads((FX / "frr1041_rplu_r1_neighbors.json").read_text(encoding="utf-8"))


def with_families(families: dict[str, int]) -> str:
    """The live LU capture with its addressFamilyInfo replaced: each family a copy of the captured LU block with the
    given acceptedPrefixCounter."""
    data = lu_capture()
    block = data[LU_PEER]["addressFamilyInfo"]["ipv4LabeledUnicast"]
    data[LU_PEER]["addressFamilyInfo"] = {f: {**block, "acceptedPrefixCounter": c} for f, c in families.items()}
    data[LU_PEER].pop("gracefulRestartInfo", None)
    return json.dumps(data)


class Stub:
    name = "frr"
    reads_received = False

    def __init__(self, neighbors: dict):
        self.neighbors = neighbors

    def bgp_neighbors(self, vrf="default"):
        return Observation(self.neighbors, [{"command": "show bgp neighbors json", "output": "..."}])


def judge(neighbors: dict, neighbor=LU_PEER, **bound):
    check = _validate_check(0, {"type": "bgp_prefixes", "node": "r1", "neighbor": neighbor, **bound}, 20)
    return _bgp_prefixes(Stub(neighbors), check.params)


# ------------------------------------------------------------------------------------------------ unicast_unread

def test_named_families_are_the_ones_config_accepts():
    from netdryrun.config import AFIS
    assert tuple(NAMED_FAMILIES) == tuple(AFIS)


@pytest.mark.parametrize("families,afi,want", [
    # unicast family missing: a labeled-unicast family of that version blocks "doesn't carry"
    ({"ipv4LabeledUnicast": 0}, "ipv4-unicast", ["ipv4LabeledUnicast"]),
    ({"ipv4-labeled-unicast": 3}, "ipv4-unicast", ["ipv4-labeled-unicast"]),          # SR Linux's name
    ({"ipv6LabeledUnicast": 0}, "ipv6-unicast", ["ipv6LabeledUnicast"]),
    ({"ipv6LabeledUnicast": 0, "ipv6Unicast": 0}, "ipv4-unicast", []),                # other version: still "doesn't"
    ({"ipv4LabeledUnicast": 0}, "ipv6-unicast", []),
    ({"ipv6-unicast": 4}, "ipv4-unicast", []),                                       # IPv6-only (the guard)
    ({"evpn": 7}, "ipv4-unicast", []),                                               # EVPN never blocks
    ({}, "ipv4-unicast", []),
    # fail closed: an unnamed family that may be of this version blocks the missing unicast family
    ({"ipv4Vpn": 2}, "ipv4-unicast", ["ipv4Vpn"]),
    ({"linkState": 1}, "ipv4-unicast", ["linkState"]),
    ({"linkState": 1}, "ipv6-unicast", ["linkState"]),
    ({"ipv4Ipv6Mixed": 1}, "ipv6-unicast", ["ipv4Ipv6Mixed"]),                        # both versions named: blocks
    # unicast family listed: only labeled-unicast of this version (or of none) makes its count unread
    ({"ipv4-unicast": 3, "ipv4LabeledUnicast": 0}, "ipv4-unicast", ["ipv4LabeledUnicast"]),
    ({"ipv4-unicast": 3, "labeledUnicast": 0}, "ipv4-unicast", ["labeledUnicast"]),
    ({"ipv4-unicast": 3, "ipv4Vpn": 5, "ipv4Multicast": 1}, "ipv4-unicast", []),
    ({"ipv4-unicast": 3, "ipv6LabeledUnicast": 1}, "ipv4-unicast", []),
    # evpn checks are never affected
    ({"ipv4LabeledUnicast": 0}, "evpn", []),
])
def test_unicast_unread(families, afi, want):
    assert unicast_unread(afi, families) == want


def test_unicast_unread_is_sorted_and_lists_every_blocking_family():
    assert unicast_unread("ipv4-unicast", {"ipv4Vpn": 0, "ipv4LabeledUnicast": 0, "evpn": 1}) == [
        "ipv4LabeledUnicast", "ipv4Vpn"]


# ------------------------------------------------------------------------------------------------ the check

@pytest.mark.parametrize("bound", [{"exact": 0}, {"max": 0}, {"max": 10}, {"min": 1}, {"exact": 3}, {"only": []},
                                   {"only": ["10.80.1.0/24", "10.80.2.0/24", "10.80.3.0/24"]}])
def test_every_bound_on_the_live_lu_session_fails_as_unread(bound):
    r = judge(frr_neighbors(json.dumps(lu_capture())), afi="ipv4-unicast", **bound)
    assert r[0] is False
    assert "ipv4-unicast prefix count of the session to 10.0.12.2 can't be read" in r[1]
    assert "ipv4LabeledUnicast" in r[1] and "doesn't carry" not in r[1]


def test_unicast_count_beside_labeled_unicast_is_unread():
    """Both families listed: nothing says whether the unicast counter includes the LU routes, so no bound is judged on
    it, not even one it meets (a mutant that keeps the count passes `exact: 3` here)."""
    n = frr_neighbors(with_families({"ipv4Unicast": 3, "ipv4LabeledUnicast": 0}))
    assert n[LU_PEER].prefixes == {"ipv4-unicast": 3, "ipv4LabeledUnicast": 0}
    ok, detail, _ = judge(n, afi="ipv4-unicast", exact=3)
    assert ok is False and "can't be read" in detail


def test_vpn_beside_unicast_keeps_the_unicast_count():
    n = frr_neighbors(with_families({"ipv4Unicast": 3, "ipv4Vpn": 9}))
    ok, detail, _ = judge(n, afi="ipv4-unicast", exact=3)
    assert ok is True and detail == "3 ipv4-unicast prefixes accepted"


def test_ipv6_labeled_unicast_session_still_does_not_carry_ipv4():
    n = frr_neighbors(with_families({"ipv6LabeledUnicast": 0}))
    ok, detail, _ = judge(n, afi="ipv4-unicast", exact=0)
    assert ok is True and detail == "0 ipv4-unicast prefixes (the session doesn't carry ipv4-unicast)"
    ok, detail, _ = judge(n, afi="ipv6-unicast", exact=0)
    assert ok is False and "ipv6LabeledUnicast" in detail and "can't be read" in detail


def test_evpn_only_session_still_does_not_carry_unicast():
    n = frr_neighbors(with_families({"l2VpnEvpn": 4}))
    ok, detail, _ = judge(n, afi="ipv4-unicast", exact=0)
    assert ok is True and "doesn't carry ipv4-unicast" in detail
    ok, detail, _ = judge(n, afi="evpn", exact=4)
    assert ok is True


def test_unnamed_family_alone_fails_closed():
    n = frr_neighbors(with_families({"ipv4Vpn": 0}))
    ok, detail, _ = judge(n, afi="ipv4-unicast", exact=0)
    assert ok is False and "ipv4Vpn" in detail


def srl_lu_session() -> str:
    """SR Linux's live neighbor answer with ipv4-unicast down (no counters) and an ipv4-labeled-unicast family up with
    3 routes received, as SR Linux prints every family that is up."""
    data = json.loads((FX / "srl_bgp_neighbors.txt").read_text(encoding="utf-8"))
    nb = data["neighbor"][0]
    fams = []
    for af in nb["afi-safi"]:
        if af["afi-safi-name"] == "ipv4-unicast":
            fams.append({"afi-safi-name": "ipv4-unicast", "admin-state": "disable", "oper-state": "down"})
            fams.append({**af, "afi-safi-name": "ipv4-labeled-unicast", "received-routes": 3, "rejected-routes": 0})
        else:
            fams.append(af)
    nb["afi-safi"] = fams
    data["neighbor"] = [nb]
    return json.dumps(data)


def test_srlinux_labeled_unicast_keeps_its_own_name_and_blocks_exact0():
    n = srl_neighbors(srl_lu_session())
    peer = json.loads(srl_lu_session())["neighbor"][0]["peer-address"]
    assert n[peer].prefixes == {"ipv4-labeled-unicast": 3}
    ok, detail, _ = judge(n, neighbor=peer, afi="ipv4-unicast", exact=0)
    assert ok is False and "ipv4-labeled-unicast" in detail


# ------------------------------------------------------------------------------------------------ record

def session(families: dict[str, int], external=True) -> dict:
    return {LU_PEER: BgpNeighbor(LU_PEER, "established", dict(families), external=external)}


def recorded(families, external=True):
    warnings: list[str] = []
    checks = rec._session_checks("r1", session(families, external), "range", warnings, drv=Stub({}))
    for i, c in enumerate(checks):
        _validate_check(i, dict(c), 20)        # every recorded check is one `run` accepts
    return checks, warnings


def prefix_checks(checks, afi=None):
    return [c for c in checks if c["type"] == "bgp_prefixes" and (afi is None or c["afi"] == afi)]


def test_record_lu_only_ebgp_session():
    checks, warnings = recorded({"ipv4LabeledUnicast": 0})
    assert {"type": "bgp_session", "node": "r1", "neighbor": LU_PEER} in checks
    assert not prefix_checks(checks, "ipv4-unicast")
    assert not [c for c in checks if c.get("afi") not in (None, *NAMED_FAMILIES)]
    # the IPv6 family is still recorded as not carried: an ipv4 labeled-unicast family says nothing about IPv6
    assert prefix_checks(checks, "ipv6-unicast") == [{"type": "bgp_prefixes", "node": "r1", "neighbor": LU_PEER,
                                                      "afi": "ipv6-unicast", "exact": 0}]
    assert warnings == [
        "INCOMPLETE BASELINE: r1: BGP neighbor 10.0.12.2 carries ipv4LabeledUnicast, a family no check can count; not "
        "recorded: a change to the routes it carries isn't caught by this baseline: add route checks by hand",
        "INCOMPLETE BASELINE: r1: BGP neighbor 10.0.12.2 ipv4-unicast: the session lists no ipv4-unicast family but "
        "carries ipv4LabeledUnicast, whose routes the node can install as ipv4-unicast routes, so `exact: 0` on "
        "ipv4-unicast isn't recorded: add route checks by hand",
    ]


def test_record_lu_only_ibgp_session_names_the_family():
    checks, warnings = recorded({"ipv4LabeledUnicast": 0}, external=False)
    assert not prefix_checks(checks)
    assert len(warnings) == 1 and "carries ipv4LabeledUnicast, a family no check can count" in warnings[0]


def test_record_unicast_beside_labeled_unicast_is_a_gap():
    checks, warnings = recorded({"ipv4-unicast": 3, "ipv4LabeledUnicast": 0})
    assert not prefix_checks(checks, "ipv4-unicast")
    assert any(w.startswith("INCOMPLETE BASELINE: r1: BGP neighbor 10.0.12.2 ipv4-unicast: the session also carries "
                            "ipv4LabeledUnicast") for w in warnings)


def test_record_vpn_beside_unicast_records_unicast_and_names_vpn():
    checks, warnings = recorded({"ipv4-unicast": 3, "ipv4Vpn": 5})
    [c] = prefix_checks(checks, "ipv4-unicast")
    assert "ipv4Vpn" not in str(checks)
    assert [w for w in warnings if w.startswith("INCOMPLETE BASELINE")] == [
        "INCOMPLETE BASELINE: r1: BGP neighbor 10.0.12.2 carries ipv4Vpn, a family no check can count; not recorded: "
        "a change to the routes it carries isn't caught by this baseline: add route checks by hand"]


def test_record_ipv6_lu_session_still_writes_exact0_on_ipv4():
    checks, _ = recorded({"ipv6-unicast": 2, "ipv6LabeledUnicast": 0})
    assert {"type": "bgp_prefixes", "node": "r1", "neighbor": LU_PEER, "afi": "ipv4-unicast", "exact": 0} in checks
    assert not prefix_checks(checks, "ipv6-unicast")


def test_record_named_families_unchanged():
    checks, warnings = recorded({"ipv6-unicast": 0})
    assert {"type": "bgp_prefixes", "node": "r1", "neighbor": LU_PEER, "afi": "ipv4-unicast", "exact": 0} in checks
    assert not [w for w in warnings if w.startswith("INCOMPLETE BASELINE")]
