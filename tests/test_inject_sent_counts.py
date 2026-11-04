"""inject_routes proves the routes left the injecting node (acceptance round B-5) by one rule (Layer 6 round 5 on
45f63df, after four rounds of cleverer proofs leaked): a peer was reached only if its session was established when
the routes went in, is established at restore, never dropped in between, and every injected prefix of its family is
in the injector's advertised routes towards it (its adj-rib-out after outbound policy), read strictly. Every other
peer seen in that family is quiet; a prefix-limit reset proves nothing. Session captures: live FRR 10.4.1
(tests/fixtures/SOURCES.yml); the advertised listings are built in the shape of the live frr_adj_out_multipath
capture."""
import copy
import json
import time
from pathlib import Path

import pytest

from netdryrun.faults import RouteInjection
from netdryrun.lab import ExecResult, LabError
from verify_helpers import fixture

FX = Path(__file__).parent / "fixtures"
# live edge1 adj-rib-out (FRR 10.4.1): 192.0.2.0/24 is a network statement (sourced, local, peer 0.0.0.0, AS path
# `Local`), the shape an injected route takes; frr_adj_out_multipath's 192.168.3.1/32 is a path learned from a peer
_LIVE = json.loads(fixture("adj_out_default_ipv4_10.0.2.2.txt"))
_INJECTED = _LIVE["advertisedRoutes"]["192.0.2.0/24"]["paths"][0]
_LEARNED = json.loads((FX / "frr_adj_out_multipath.txt").read_text(encoding="utf-8"))["advertisedRoutes"][
    "192.168.3.1/32"]["paths"][0]


def _path(template, prefix, as_path=(), **change):
    p = copy.deepcopy(template)
    if template is _INJECTED and as_path:
        p["aspath"] = {"string": " ".join(map(str, as_path)), "length": len(as_path),
                       "segments": [{"type": "as-sequence", "list": list(as_path)}]}
    if ":" in prefix:
        p["nexthops"] = [{"ip": "::", "hostname": "peer", "afi": "ipv6", "scope": "global", "metric": 0,
                          "accessible": True, "used": True}]
    p.update(change)
    return p


def listing(routes: dict, total: int | None = None) -> str:
    """An advertised-routes detail listing: prefix -> its paths, in the live capture's shape."""
    if not routes and total is None:
        return "{}"
    doc = {k: v for k, v in _LIVE.items() if k not in ("advertisedRoutes", "totalPrefixCounter")}
    return json.dumps({**doc, "totalPrefixCounter": len(routes) if total is None else total, "advertisedRoutes": {
        p: {"prefix": p, "pathCount": len(paths), "paths": paths} for p, paths in routes.items()}})


def adv(*prefixes: str, total: int | None = None, as_path=()) -> str:
    """The node advertising these prefixes as its injected routes: network-statement paths with the injection's AS
    path (Layer 6 round 7 on 99fe33e: built from a learned path before, which is the gap itself)."""
    return listing({p: [_path(_INJECTED, p, as_path)] for p in prefixes}, total)


def learned(*prefixes: str) -> str:
    """The node advertising these prefixes from a path it learned from a peer, not the injected one."""
    return listing({p: [_path(_LEARNED, p, bestpath={"overall": True})] for p in prefixes})


class InjectLab:
    """Answers the summary and neighbor commands with the next capture each, and each peer's advertised routes with
    its listing; every other command succeeds."""

    def __init__(self, summaries, neighbors=None, advertised=None, summaries6=(), advertised_before=None):
        self.summaries, self.summaries6 = list(summaries), list(summaries6)
        # by default every peer's session is steady (never dropped) for the whole injection
        peers = sorted({p for t in [*self.summaries, *self.summaries6] for p in _peers(t)})
        self.neighbors = list(neighbors) if neighbors is not None else [steady(peers)] * 4
        self.advertised = advertised or {}
        self.advertised_before = advertised_before or {}   # each peer's listing before the config goes in
        self.phase, self.asked = "after", []

    def exec(self, node, cmd, timeout=60, input=None):
        c = cmd[-1]
        if c == "show bgp ipv4 unicast summary json":
            return ExecResult(cmd, 0, self.summaries.pop(0), "")
        if c == "show bgp ipv6 unicast summary json":
            return ExecResult(cmd, 0, self.summaries6.pop(0), "")
        if c == "show bgp neighbors json":
            return ExecResult(cmd, 0, self.neighbors.pop(0) if self.neighbors else "{}", "")
        if c.endswith(" advertised-routes detail json"):
            if self.phase == "before":
                return ExecResult(cmd, 0, self.advertised_before.get(c.split()[-4], "{}"), "")
            self.asked.append(c)
            return ExecResult(cmd, 0, self.advertised[c.split()[-4]], "")
        return ExecResult(cmd, 0, "", "")


def _peers(text: str) -> list[str]:
    try:
        return list(json.loads(text).get("peers") or {})
    except (ValueError, AttributeError):
        return []


def steady(peers, dropped=None, up_ms=600000, **extra) -> str:
    """`show bgp neighbors json` with these peers, each session never dropped (or dropped as given) and up for ten
    minutes (or `up_ms`), IPv4 only, in the shape of the live frr_bgp_neighbors capture."""
    dropped = dropped or {}
    return json.dumps({p: {"connectionsDropped": dropped.get(p, 0), "addressFamilyInfo": {"ipv4Unicast": {}},
                           "bgpTimerUpMsec": up_ms, "minBtwnAdvertisementRunsTimerMsecs": 0, **extra} for p in peers})


def applied(lab, node, prefixes, asn="65001", ago=60):
    """An injection whose routes went in `ago` seconds ago: the peers and sessions read as apply() reads them."""
    inj = RouteInjection(lab, node, prefixes, [])
    inj._wait = lambda want_present: None
    inj.asn, inj.applied = asn, True
    inj.peers_before, inj.sessions_before = inj.established(), inj.sessions()
    if isinstance(lab, InjectLab):
        lab.phase = "before"
        inj.record_listed()
        lab.phase = "after"
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


@pytest.mark.parametrize("listing", [adv(), adv(R1)], ids=["sent-nothing", "sent-it-at-the-end"])
def test_a_peer_that_came_up_while_the_routes_were_in_is_quiet(listing):
    """Round 4 (F1): a peer that came up during the injection and was sent nothing passed. Round 5 (F1, a regression
    from bf29e89): one that showed the prefix at restore counted as reached, though the checks ran while it had no
    session. Either way it's quiet, and its advertised routes aren't even read."""
    lab = InjectLab([summary({"10.0.12.2": "Established", "10.0.13.2": "Active"}),
                     summary({"10.0.12.2": "Established", "10.0.13.2": "Established"})],
                    advertised={"10.0.12.2": adv(R1), "10.0.13.2": listing})
    inj = applied(lab, "r1", [R1])
    inj.restore()
    assert (inj.left, inj.quiet) == (False, {"10.0.13.2": [R1]})
    assert lab.asked == ["show bgp ipv4 unicast neighbors 10.0.12.2 advertised-routes detail json"]


def test_a_family_with_no_session_at_apply_never_left_even_if_one_came_up():
    lab = InjectLab([summary({"10.0.12.2": "Active"}), summary({"10.0.12.2": "Established"})],
                    advertised={"10.0.12.2": adv(R1)})
    inj = applied(lab, "r1", [R1])
    inj.restore()
    assert (inj.left, inj.quiet, inj.unsent) == (False, {"10.0.12.2": [R1]}, {"ipv4": [R1]})


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


# --- a prefix-limit reset proves nothing (Layer 6 round 5 on 45f63df: another node's injection or a rerouted link
# can trip it too) ---------------------------------------------------------------------------------------------------

def v2_injection(after):
    """ce1 on the corpus v2 lab (FRR 10.4.1, live): before the injection, then `after` while the routes are in."""
    lab = InjectLab([v2("before", "summary"), v2(after, "summary")],
                    neighbors=[v2("before", "neighbors"), v2(after, "neighbors")],
                    advertised={"10.0.1.1": adv("10.100.16.0/24")})
    inj = applied(lab, "ce1", ["10.100.16.0/24"], asn="65100")
    inj.restore()
    return inj


def test_the_v2_baseline_reads_live():
    from netdryrun.faults import Session
    lab = InjectLab([v2("before", "summary")], neighbors=[v2("before", "neighbors")])
    inj = applied(lab, "ce1", ["10.100.16.0/24"], asn="65100")
    assert (inj.peers_before, inj.sessions_before) == ({"ipv4": ["10.0.1.1"]}, {"10.0.1.1": Session(0, False, 13000, 0)})


# --- round 6 on 1a597d7: a reset the drop count can't show, and routes advertised only after the checks -------------

def _one_peer(before, after, listing=None, ago=60):
    lab = InjectLab([summary({"10.0.12.2": "Established"})] * 2, neighbors=[before, after],
                    advertised={"10.0.12.2": listing or adv(R1)})
    inj = applied(lab, "r1", [R1], ago=ago)
    inj.restore()
    return inj


def test_a_dynamic_peer_is_never_counted_as_reached():
    """`bgp listen range`: FRR recreates the peer on reconnect, so its drop count reads 0 across a flap."""
    inj = _one_peer(steady(["10.0.12.2"], dynamicPeer=True), steady(["10.0.12.2"], dynamicPeer=True))
    assert (inj.left, inj.quiet) == (False, {"10.0.12.2": [R1]})


def test_a_drop_count_that_went_down_is_a_reset():
    inj = _one_peer(steady(["10.0.12.2"], {"10.0.12.2": 3}), steady(["10.0.12.2"], {"10.0.12.2": 0}))
    assert (inj.left, inj.quiet) == (False, {"10.0.12.2": [R1]})


@pytest.mark.parametrize("up_ms", [20000, None], ids=["shorter", "unread"])
def test_a_session_up_for_less_than_the_injection_reset_while_the_routes_were_in(up_ms):
    """The drop count didn't move, but the session has been up for 20 s of a 60 s injection (or its uptime doesn't
    read): it reset in between, so the peer is quiet."""
    after = steady(["10.0.12.2"], up_ms=up_ms) if up_ms else json.dumps(
        {"10.0.12.2": {"connectionsDropped": 0, "addressFamilyInfo": {"ipv4Unicast": {}}}})
    inj = _one_peer(steady(["10.0.12.2"]), after, ago=60)
    assert (inj.left, inj.quiet) == (False, {"10.0.12.2": [R1]})


def test_a_session_up_since_before_the_injection_is_steady():
    inj = _one_peer(steady(["10.0.12.2"], up_ms=5000), steady(["10.0.12.2"], up_ms=65000), ago=60)
    assert (inj.left, inj.quiet) == (True, {})


class LateLab(InjectLab):
    """The peer's advertised routes: empty for the first `late` reads, then with the prefix."""

    def __init__(self, late, **kw):
        super().__init__([summary({"10.0.12.2": "Established"})] * 2, **kw)
        self.late, self.reads = late, 0

    def exec(self, node, cmd, timeout=60, input=None):
        if cmd[-1].endswith(" advertised-routes detail json"):
            self.reads += 1
            self.advertised = {"10.0.12.2": adv() if self.reads <= self.late else adv(R1)}
        return super().exec(node, cmd, timeout, input)


def test_the_checks_wait_until_every_peer_is_sent_the_routes(monkeypatch):
    monkeypatch.setattr("netdryrun.faults.time.sleep", lambda s: None)
    lab = LateLab(2)
    inj = applied(lab, "r1", [R1])
    inj.await_delivery(settle=10)
    assert (inj.late, lab.reads) == (set(), 3)
    inj.restore()
    assert (inj.left, inj.quiet) == (True, {})


def test_a_peer_not_sent_the_routes_within_the_bound_is_quiet_even_if_they_arrive_later(monkeypatch):
    """Advertised only after the checks ran: the checks saw nothing, so the peer is quiet though restore finds them."""
    clock = iter(range(0, 10000, 5))
    monkeypatch.setattr("netdryrun.faults.time.monotonic", lambda: float(next(clock)))
    monkeypatch.setattr("netdryrun.faults.time.sleep", lambda s: None)
    lab = LateLab(1000)
    inj = applied(lab, "r1", [R1])
    inj.await_delivery(settle=10)
    assert inj.late == {"10.0.12.2"}
    lab.late = 0
    inj.restore()
    assert (inj.left, inj.quiet) == (False, {"10.0.12.2": [R1]})


@pytest.mark.parametrize("after", ["maxprefix", "linkdown", "clear"])
def test_any_reset_while_the_routes_were_in_means_the_peer_did_not_get_them(after):
    """Corpus v2, live: pe1's maximum-prefix tore the session down (ce1 received Cease 0601), ce1's link went down, or
    ce1 cleared the session. Each is a reset; the prefix-limit one used to prove delivery, and no longer does: a
    max-prefix scenario asserts the receiver's session state, and the counts behind it are inconclusive."""
    inj = v2_injection(after)
    assert (inj.left, inj.quiet) == (False, {"10.0.1.1": ["10.100.16.0/24"]})


# --- round 7 on 99fe33e: the advertised path must be the injected one, not the prefix from another path ------------

def test_a_prefix_advertised_from_a_learned_path_did_not_carry_the_injection():
    """The hijack case: r1 already sends 100.64.0.0/24, learned from a peer. The injected path never left (filtered,
    or lost on best path), yet the prefix was in the listing, so the wait ended at once and restore said left."""
    inj = r1({"10.0.12.2": learned(R1), "10.0.13.2": adv(R1)})
    assert (inj.left, inj.quiet) == (False, {"10.0.12.2": [R1]})


def test_an_advertised_path_with_another_as_path_did_not_carry_the_injection():
    lab = InjectLab([live("before"), live("after")],
                    advertised={"10.0.12.2": adv(R1), "10.0.13.2": adv(R1, as_path=(65099,))})
    inj = RouteInjection(lab, "r1", [R1], [65099])
    inj._wait = lambda want_present: None
    inj.asn, inj.applied = "65001", True
    inj.peers_before, inj.sessions_before = inj.established(), inj.sessions()
    inj.applied_at = time.monotonic() - 60
    inj.restore()
    assert (inj.left, inj.quiet) == (False, {"10.0.12.2": [R1]})   # sent without the prepend: not the injected path


def test_an_add_path_peer_proves_nothing_and_is_quiet():
    """Round 8 on ba4095d (F1): with add-path the listing shows the node's paths with per-family TX ids, a path denied
    to this peer included, so the injected path listed with an id doesn't prove this peer got it."""
    both = listing({R1: [_path(_LEARNED, R1, addpathTxId=1), _path(_INJECTED, R1, addpathTxId=2)]})
    inj = r1({"10.0.12.2": both, "10.0.13.2": adv(R1)})
    assert (inj.left, inj.quiet) == (False, {"10.0.12.2": [R1]})


def test_a_destination_listed_as_a_bare_path_list_is_read():
    """Round 8 (F4): FRR may list a destination as its paths alone; advertised() crashed on it with a TypeError."""
    bare = json.loads(adv(R1))
    bare["advertisedRoutes"][R1] = bare["advertisedRoutes"][R1]["paths"]
    inj = r1({"10.0.12.2": json.dumps(bare), "10.0.13.2": adv(R1)})
    assert (inj.left, inj.quiet) == (True, {})


def test_restore_removes_the_injected_config_whatever_goes_wrong_reading():
    """Round 8 (F4): an unexpected error while reading the delivery left the injected config in the lab."""
    class Boom(InjectLab):
        def exec(self, node, cmd, timeout=60, input=None):
            if cmd[-1].endswith(" advertised-routes detail json") and self.phase == "after":
                raise TypeError("unexpected shape")
            return super().exec(node, cmd, timeout, input)
    lab = Boom([live("before"), live("after")])
    inj = applied(lab, "r1", [R1])
    removed = []
    inj._apply_config = removed.append
    inj.restore()
    assert inj.left is None and removed and any(ln.startswith("  no network 100.64.0.0/24") for ln in removed[0])


def test_without_add_path_only_the_best_path_is_sent():
    """FRR lists every multipath path, but sends only the best without add-path: an injected path that isn't best
    never left (interop IOP-8)."""
    lost = listing({R1: [_path(_LEARNED, R1, bestpath={"overall": True}),
                         _path(_INJECTED, R1, bestpath={"overall": False})]})
    inj = r1({"10.0.12.2": lost, "10.0.13.2": adv(R1)})
    assert (inj.left, inj.quiet) == (False, {"10.0.12.2": [R1]})


def _table(*learned_only: str, injected: tuple = ()) -> str:
    """`show bgp vrf all ipv4 unicast detail json` on edge1 (live), with prefixes the node holds only as learned, and
    prefixes it holds as its own network routes."""
    doc = json.loads(fixture("bgp_v4_detail.txt"))
    routes = doc["default"]["routes"]
    own = copy.deepcopy(routes["192.0.2.0/24"])
    other = next(copy.deepcopy(v) for v in routes.values() if not any("sourced" in p or "local" in p for p in v))
    for p in learned_only:
        routes[p] = copy.deepcopy(other)
    for p in injected:
        routes[p] = copy.deepcopy(own)
    doc["default"].update(totalRoutes=len(routes), totalPaths=sum(len(v) for v in routes.values()))
    return json.dumps(doc)


class TableLab:
    def __init__(self, text):
        self.text = text

    def exec(self, node, cmd, timeout=60, input=None):
        return ExecResult(cmd, 0, self.text if cmd[-1] == "show bgp vrf all ipv4 unicast detail json" else "", "")


def test_the_injection_waits_for_its_own_path_not_a_learned_one_for_the_prefix():
    """_missing looked for the prefix in the node's table: one it already held from a neighbor read as injected."""
    inj = RouteInjection(TableLab(_table(R1)), "r1", [R1], [])
    assert inj._missing(want_present=True) == [R1]
    inj = RouteInjection(TableLab(_table(injected=(R1,))), "r1", [R1], [])
    assert inj._missing(want_present=True) == [] and inj._missing(want_present=False) == [R1]


def _with_redistributed(text: str, prefix: str) -> str:
    """The table with one more local path for `prefix`: a redistributed route (sourced, not local, origin incomplete,
    empty AS path), as a `redistribute static|connected|kernel` puts beside a network route."""
    doc = json.loads(text)
    routes = doc["default"]["routes"]
    redis = copy.deepcopy(json.loads(fixture("bgp_v4_detail.txt"))["default"]["routes"]["192.0.2.0/24"][0])
    redis.pop("local", None)
    redis.pop("bestpath", None)
    redis["origin"] = "incomplete"
    routes.setdefault(prefix, []).append(redis)
    doc["default"].update(totalRoutes=len(routes), totalPaths=sum(len(v) for v in routes.values()))
    return json.dumps(doc)


def test_other_local_paths_for_the_prefix_are_read_not_refused():
    """Round 8 (F2): `redistribute static` puts the injection's own blackhole static beside its network route: two
    local paths, which the table reader refused, so inject_routes errored on a common config."""
    inj = RouteInjection(TableLab(_with_redistributed(_table(injected=(R1,)), R1)), "r1", [R1], [])
    assert inj._missing(want_present=True) == []


class ApplyLab(TableLab):
    def exec(self, node, cmd, timeout=60, input=None):
        if cmd[-1] == "show running-config":
            return ExecResult(cmd, 0, "router bgp 65001\n", "")
        return super().exec(node, cmd, timeout, input)


def test_a_prefix_the_node_already_originates_with_the_same_as_path_is_refused():
    """Round 8 (F3): a redistributed connected route for the prefix (empty AS path) read as the injected path before
    the config went in, and restore then waited for it to go and timed out. Refused, with what to do instead."""
    lab = ApplyLab(_with_redistributed(_table(), R1))
    with pytest.raises(LabError, match="already originates 100.64.0.0/24 itself"):
        RouteInjection(lab, "r1", [R1], []).apply()
    assert RouteInjection(lab, "r1", [R1], [])._missing(want_present=True) == [R1]   # and it isn't the injected one


def test_the_injection_s_as_path_tells_its_route_from_the_node_s_own():
    inj = RouteInjection(ApplyLab(_with_redistributed(_table(), R1)), "r1", [R1], [65099])
    assert [p for p, paths in inj._own_paths("ipv4").items() if any(a == inj._as_path() for a, _i in paths)] == []


# --- round 9 on 02a96a2: an entry the peer already had for an injected prefix ---------------------------------------

def test_a_prefix_the_peer_already_had_an_entry_for_is_never_read_as_delivered():
    """The hijack setup: r1 learned 100.64.0.0/24 from N and advertised it to 10.0.12.2 before the injection. FRR
    then shows the injected path under that existing entry as soon as it is in the table, before any UPDATE leaves:
    with a long advertisement interval the checks ran while the peer still held N's path."""
    lab = InjectLab([live("before"), live("after")], advertised={"10.0.12.2": adv(R1), "10.0.13.2": adv(R1)},
                    advertised_before={"10.0.12.2": learned(R1)})
    inj = applied(lab, "r1", [R1])
    assert inj.listed_before == {"10.0.12.2": {R1}}
    inj.restore()
    assert (inj.left, inj.quiet) == (False, {"10.0.12.2": [R1]})


def test_a_listing_that_cant_be_read_before_the_injection_counts_as_having_them_all():
    lab = InjectLab([live("before"), live("after")], advertised={"10.0.12.2": adv(R1), "10.0.13.2": adv(R1)},
                    advertised_before={"10.0.13.2": "not json"})
    inj = applied(lab, "r1", [R1])
    inj.restore()
    assert (inj.left, inj.quiet) == (False, {"10.0.13.2": [R1]})


def test_the_wait_does_not_wait_for_a_peer_that_already_had_the_prefix(monkeypatch):
    monkeypatch.setattr("netdryrun.faults.time.sleep", lambda s: (_ for _ in ()).throw(AssertionError("waited")))
    lab = InjectLab([live("before")], advertised={"10.0.13.2": adv(R1)},
                    advertised_before={"10.0.12.2": learned(R1)})
    inj = applied(lab, "r1", [R1])
    inj.await_delivery(settle=10)
    assert inj.late == set() and lab.asked == ["show bgp ipv4 unicast neighbors 10.0.13.2 advertised-routes detail json"]


# --- a prefix limit that resets the session (Verdict Corpus v2, I8; known limitation since 0.4.1) ------------------

def test_a_prefix_limit_reset_during_the_injection_is_inconclusive_never_passed():
    """Corpus v2 I8 on the 0.4.1 gate (candidate 7532310): ce1 floods 200 /24s from its /16, pe1's `maximum-prefix 50
    restart 1` shuts the session, and a minute later it is back with every prefix re-sent. A prefix-limit reset is not
    proof that the routes reached pe1 (another node or the change itself can trip it), so pe1 is quiet, every check the
    scenario passed becomes not passed with a NeverLeft detail, and the run is inconclusive (exit 3), never passed."""
    from types import SimpleNamespace

    from netdryrun import runner
    flood = [f"10.100.{i}.0/24" for i in range(16, 216)]
    pe1 = "10.0.1.1"
    lab = InjectLab([summary({pe1: "Established"})] * 2,
                    neighbors=[steady([pe1]), steady([pe1], {pe1: 1}, up_ms=20000)],
                    advertised={pe1: adv(*flood)})
    inj = applied(lab, "ce1", flood, asn="65100", ago=90)
    inj.restore()
    assert (inj.left, inj.quiet, lab.asked) == (False, {pe1: flood}, [])   # the re-sent listing isn't even read

    check = SimpleNamespace(name="[customer floods 200 prefixes] I8 upstream still receives at most 51 prefixes")
    passed = runner.Result(check, True, "48 prefixes", 1, 1.0, "")
    out = runner._never_left([inj], [passed])
    assert [r.passed for r in out] == [False] and isinstance(out[0].detail, runner.NeverLeft)
    assert out[0].detail.startswith(f"inconclusive: the injected routes on ce1 did not all reach its BGP peers: {pe1} "
                                    "was not sent 10.100.16.0/24, 10.100.17.0/24, 10.100.18.0/24, 10.100.19.0/24, "
                                    "10.100.20.0/24 and 195 more")
    report = runner.RunReport(config=None, results=out)
    assert (report.status, report.exit_code) == ("inconclusive", 3)
