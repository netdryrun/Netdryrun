"""inject_routes proves the routes left the injecting node (acceptance round B-5): every injected prefix must be in the
injector's advertised routes (its adj-rib-out after outbound policy) towards every peer that was established in its
family when the routes went in, read while they are still in, unless that peer tore the session down over its prefix
limit after they went in. Layer 6 round 3 on 5e65852: bgpd's aggregate sent-prefix count (pfxSnt), the proof before,
can't say which prefixes left (another injection's prefixes raised it). Session captures: live FRR 10.4.1
(tests/fixtures/SOURCES.yml); the advertised listings are built in the shape of the live frr_adj_out_multipath
capture."""
import copy
import json
import time
from pathlib import Path

import pytest

from netdryrun.faults import RouteInjection
from netdryrun.lab import ExecResult, LabError

FX = Path(__file__).parent / "fixtures"
_LIVE = json.loads((FX / "frr_adj_out_multipath.txt").read_text(encoding="utf-8"))
_DEST = _LIVE["advertisedRoutes"]["192.168.3.1/32"]


def adv(*prefixes: str, total: int | None = None) -> str:
    """An advertised-routes detail listing with these prefixes, one best path each (the live capture's shape)."""
    if not prefixes and total is None:
        return "{}"
    routes = {}
    for p in prefixes:
        dest = copy.deepcopy(_DEST)
        dest.update(prefix=p, pathCount=1, paths=[dest["paths"][0]])
        if ":" in p:
            dest["paths"][0]["nexthops"] = [{"ip": "::", "hostname": "peer", "afi": "ipv6", "scope": "global",
                                             "metric": 0, "accessible": True, "used": True}]
        routes[p] = dest
    doc = {k: v for k, v in _LIVE.items() if k not in ("advertisedRoutes", "totalPrefixCounter")}
    return json.dumps({**doc, "advertisedRoutes": routes,
                       "totalPrefixCounter": len(prefixes) if total is None else total})


class InjectLab:
    """Answers the summary and neighbor commands with the next capture each, and each peer's advertised routes with
    its listing; every other command succeeds."""

    def __init__(self, summaries, neighbors=None, advertised=None, summaries6=()):
        self.summaries, self.summaries6 = list(summaries), list(summaries6)
        # by default every peer's session is steady (never dropped) for the whole injection
        peers = sorted({p for t in [*self.summaries, *self.summaries6] for p in _peers(t)})
        self.neighbors = list(neighbors) if neighbors is not None else [steady(peers)] * 4
        self.advertised = advertised or {}
        self.asked = []

    def exec(self, node, cmd, timeout=60, input=None):
        c = cmd[-1]
        if c == "show bgp ipv4 unicast summary json":
            return ExecResult(cmd, 0, self.summaries.pop(0), "")
        if c == "show bgp ipv6 unicast summary json":
            return ExecResult(cmd, 0, self.summaries6.pop(0), "")
        if c == "show bgp neighbors json":
            return ExecResult(cmd, 0, self.neighbors.pop(0) if self.neighbors else "{}", "")
        if c.endswith(" advertised-routes detail json"):
            self.asked.append(c)
            return ExecResult(cmd, 0, self.advertised[c.split()[-4]], "")
        return ExecResult(cmd, 0, "", "")


def _peers(text: str) -> list[str]:
    try:
        return list(json.loads(text).get("peers") or {})
    except (ValueError, AttributeError):
        return []


def steady(peers, dropped=None) -> str:
    """`show bgp neighbors json` with these peers, each session never dropped (or dropped as given), IPv4 only."""
    dropped = dropped or {}
    return json.dumps({p: {"connectionsDropped": dropped.get(p, 0), "addressFamilyInfo": {"ipv4Unicast": {}}}
                       for p in peers})


def applied(lab, node, prefixes, asn="65001", ago=60, shares_node=False):
    """An injection whose routes went in `ago` seconds ago: the peers and resets read as apply() reads them."""
    inj = RouteInjection(lab, node, prefixes, [], shares_node=shares_node)
    inj._wait = lambda want_present: None
    inj.asn, inj.applied = asn, True
    inj.peers_before, inj.resets_before = inj.established(), inj.resets()
    inj.applied_at = time.monotonic() - ago
    return inj


def summary(peers: dict) -> str:
    return json.dumps({"peers": {p: {"state": s, "pfxSnt": 0} for p, s in peers.items()}})


def live(name):
    return (FX / f"frr_bgp_summary_inject_{name}.txt").read_text(encoding="utf-8")


def v2(name, kind):
    return (FX / f"frr_v2_inject_{name}_{kind}.txt").read_text(encoding="utf-8")


R1 = "100.64.0.0/24"
THREE = ["203.0.113.0/24", "198.51.100.0/24", "192.0.2.0/24"]


def r1(advertised, prefixes=(R1,)):
    """r1 of examples/frr-bgp (both peers established before and after), with these advertised listings."""
    inj = applied(InjectLab([live("before"), live("after")], advertised=advertised), "r1", list(prefixes))
    inj.restore()
    return inj


# --- the routes reached every peer, or didn't --------------------------------------------------------------------

def test_the_peers_established_before_are_read_live():
    inj = applied(InjectLab([live("before")]), "r1", [R1])
    assert inj.peers_before == {"ipv4": ["10.0.12.2", "10.0.13.2"]}


def test_routes_in_every_peers_advertised_routes_left():
    inj = r1({"10.0.12.2": adv("10.0.0.0/24", R1), "10.0.13.2": adv(R1)})
    assert (inj.left, inj.quiet, inj.unsent) == (True, {}, {})
    assert inj.lab.asked == ["show bgp ipv4 unicast neighbors 10.0.12.2 advertised-routes detail json",
                             "show bgp ipv4 unicast neighbors 10.0.13.2 advertised-routes detail json"]


def test_routes_denied_outbound_towards_every_peer_never_left():
    inj = r1({"10.0.12.2": adv("10.0.0.0/24"), "10.0.13.2": adv()})
    assert (inj.left, inj.quiet) == (False, {"10.0.12.2": [R1], "10.0.13.2": [R1]})


def test_routes_that_reached_one_peer_but_not_another_did_not_leave():
    """Layer 6 on b03cb7a: the routes reaching one neighbor says nothing about another's side."""
    inj = r1({"10.0.12.2": adv(R1), "10.0.13.2": adv("10.0.0.0/24")})
    assert (inj.left, inj.quiet) == (False, {"10.0.13.2": [R1]})


def test_a_filter_that_lets_one_of_three_through_names_the_two_held_back():
    """Layer 6 round 2 on eaa323c: every prefix, not one more than before."""
    inj = r1({"10.0.12.2": adv(*THREE), "10.0.13.2": adv("198.51.100.0/24")}, THREE)
    assert (inj.left, inj.quiet) == (False, {"10.0.13.2": ["203.0.113.0/24", "192.0.2.0/24"]})


def test_two_injections_on_one_node_are_each_proven_by_their_own_prefixes():
    """Layer 6 round 3 on 5e65852 (F1): injection A is all filtered, B's three are sent. On the aggregate count, B's
    three made A read as reached; per prefix, A never left and B did."""
    a, b = THREE, ["100.64.1.0/24", "100.64.2.0/24", "100.64.3.0/24"]
    listing = {"10.0.12.2": adv(*b), "10.0.13.2": adv(*b)}
    lab = InjectLab([live("before"), live("before"), live("after"), live("after")], advertised=listing)
    first, second = applied(lab, "r1", a), applied(lab, "r1", b)
    first.restore()
    second.restore()
    assert (first.left, first.quiet) == (False, {"10.0.12.2": a, "10.0.13.2": a})
    assert (second.left, second.quiet) == (True, {})


def test_a_family_no_established_session_carries_never_left_though_the_other_did():
    """Layer 6 round 3 on 5e65852 (F2): an IPv4 and an IPv6 prefix, IPv4 sessions only (`{}` for IPv6, live). The
    IPv4 one reached its peer; the IPv6 one went nowhere, so left is False and the family is named."""
    lab = InjectLab([summary({"10.0.12.2": "Established"})] * 2, summaries6=["{}", "{}"],
                    advertised={"10.0.12.2": adv("203.0.113.0/24")})
    inj = applied(lab, "r1", ["203.0.113.0/24", "2001:db8:99::/48"])
    inj.restore()
    assert (inj.left, inj.quiet, inj.unsent) == (False, {}, {"ipv6": ["2001:db8:99::/48"]})


def test_a_peer_that_was_down_before_the_injection_and_still_is_is_not_waited_for():
    lab = InjectLab([summary({"10.0.12.2": "Established", "10.0.13.2": "Active"})] * 2,
                    advertised={"10.0.12.2": adv(R1)})
    inj = applied(lab, "r1", [R1])
    assert inj.peers_before == {"ipv4": ["10.0.12.2"]}
    inj.restore()
    assert (inj.left, inj.quiet) == (True, {})


def test_a_peer_that_came_up_while_the_routes_were_in_must_show_them_too():
    """Layer 6 round 4 on bf29e89 (F1): only the peers established at apply were read, so a peer that came up during
    the injection and was sent nothing passed. Up at restore, it must show every prefix."""
    lab = InjectLab([summary({"10.0.12.2": "Established", "10.0.13.2": "Active"}),
                     summary({"10.0.12.2": "Established", "10.0.13.2": "Established"})],
                    advertised={"10.0.12.2": adv(R1), "10.0.13.2": adv()})
    inj = applied(lab, "r1", [R1])
    inj.restore()
    assert (inj.left, inj.quiet) == (False, {"10.0.13.2": [R1]})
    lab = InjectLab([summary({"10.0.12.2": "Active"}), summary({"10.0.12.2": "Established"})],
                    advertised={"10.0.12.2": adv(R1)})
    inj = applied(lab, "r1", [R1])   # no session at apply, one at restore that shows it: delivered, not unsent
    inj.restore()
    assert (inj.left, inj.quiet, inj.unsent) == (True, {}, {})


def test_a_session_that_reset_while_the_routes_were_in_did_not_get_them():
    """F2: a hold-timer reset during the injection, the session back and the prefixes re-sent: what the checks saw
    while it was down is unknown, so that peer is quiet."""
    lab = InjectLab([summary({"10.0.12.2": "Established"})] * 2,
                    neighbors=[steady(["10.0.12.2"]), steady(["10.0.12.2"], {"10.0.12.2": 1})],
                    advertised={"10.0.12.2": adv(R1)})
    inj = applied(lab, "r1", [R1])
    inj.restore()
    assert (inj.left, inj.quiet, lab.asked) == (False, {"10.0.12.2": [R1]}, [])


def test_a_peer_whose_resets_cant_be_read_did_not_get_them():
    lab = InjectLab([summary({"10.0.12.2": "Established"})] * 2, neighbors=[steady(["10.0.12.2"]), "{}"],
                    advertised={"10.0.12.2": adv(R1)})
    inj = applied(lab, "r1", [R1])
    inj.restore()
    assert (inj.left, inj.quiet) == (False, {"10.0.12.2": [R1]})


def test_a_peer_that_went_down_while_the_routes_were_in_did_not_get_them():
    lab = InjectLab([summary({"10.0.12.2": "Established"}), summary({"10.0.12.2": "Active"})])
    inj = applied(lab, "r1", [R1])
    inj.restore()
    assert (inj.left, inj.quiet, lab.asked) == (False, {"10.0.12.2": [R1]}, [])


# --- what can't be read is never a delivery ----------------------------------------------------------------------

@pytest.mark.parametrize("listing", [adv(R1, total=2), adv(total=0) + "x", '{"warning": "No such neighbor"}',
                                     json.dumps({"advertisedRoutes": {R1: {"prefix": R1, "paths": []}},
                                                 "totalPrefixCounter": 1})],
                         ids=["count-vs-list", "not-json", "warning", "no-path"])
def test_advertised_routes_that_cant_be_read_are_unknown_not_left(listing):
    inj = r1({"10.0.12.2": listing, "10.0.13.2": adv(R1)})
    assert inj.left is None


def test_an_advertised_listing_of_the_other_family_is_unknown():
    inj = r1({"10.0.12.2": adv("2001:db8::/32"), "10.0.13.2": adv(R1)})
    assert inj.left is None


@pytest.mark.parametrize("text", ['{"peers": {"10.0.12.2": {"pfxSnt": 3}}}', '{"peers": [1]}', '{"other": 1}', "",
                                  "[]"])
def test_a_session_list_that_cant_be_read_stops_the_injection(text):
    with pytest.raises(LabError, match="inject_routes on r1: "):
        RouteInjection(InjectLab([text]), "r1", [R1], []).established()


def test_session_states_unreadable_at_restore_are_unknown_not_left():
    lab = InjectLab([live("before"), '{"peers": {"10.0.12.2": {"pfxSnt": 4}}}'])
    inj = applied(lab, "r1", [R1])
    inj.restore()
    assert inj.left is None


# --- a prefix-limit reset, and only one proven to be the injection's, also shows the routes left ------------------

def v2_injection(after, change=None, ago=60, shares_node=False):
    """ce1 on the corpus v2 lab (FRR 10.4.1, live): before the injection, then `after` while the routes are in."""
    neighbors = json.loads(v2(after, "neighbors"))
    if change:
        neighbors["10.0.1.1"].update(change)
    lab = InjectLab([v2("before", "summary"), v2(after, "summary")],
                    neighbors=[v2("before", "neighbors"), json.dumps(neighbors)],
                    advertised={"10.0.1.1": adv("10.0.0.0/24")})
    inj = applied(lab, "ce1", ["10.100.16.0/24"], asn="65100", ago=ago, shares_node=shares_node)   # reset 15 s old
    inj.restore()
    return inj


def test_the_v2_baseline_reads_live():
    lab = InjectLab([v2("before", "summary")], neighbors=[v2("before", "neighbors")])
    inj = applied(lab, "ce1", ["10.100.16.0/24"], asn="65100")
    assert inj.peers_before == {"ipv4": ["10.0.1.1"]}
    assert inj.resets_before == {"10.0.1.1": (0, None, None, frozenset({"ipv4Unicast"}), None)}


def test_i8_a_prefix_limit_reset_by_the_receiver_means_the_routes_left():
    """Corpus v2 I8, live: ce1 floods, pe1's maximum-prefix tears the session down (ce1 receives Cease 0601)."""
    assert v2_injection("maxprefix").left is True


@pytest.mark.parametrize("after", ["linkdown", "clear"])
def test_any_other_reset_proves_nothing(after):
    """ce1's link to pe1 down, or a clear from ce1: the session reset, not over a prefix limit, and the prefix is not
    in what ce1 advertises: inconclusive."""
    assert v2_injection(after).left is False


def test_a_prefix_limit_reset_on_a_session_with_another_family_proves_nothing():
    assert v2_injection("maxprefix", {"addressFamilyInfo": {"ipv4Unicast": {}, "ipv6Unicast": {}}}).left is False


def test_a_prefix_limit_reset_from_before_the_injection_proves_nothing():
    assert v2_injection("maxprefix", ago=5).left is False


def test_a_prefix_limit_reset_proves_nothing_when_another_injection_shares_the_node():
    """F3: with two injections on ce1, B's overflow tore the session down and proved A delivered, though none of A's
    prefixes was ever advertised. Shared, the reset is nobody's proof."""
    assert v2_injection("maxprefix", shares_node=True).left is False


@pytest.mark.parametrize("change", [{"addressFamilyInfo": None}, {"lastResetTimerMsecs": None}])
def test_a_prefix_limit_reset_with_its_family_or_time_unread_proves_nothing(change):
    assert v2_injection("maxprefix", change).left is False
