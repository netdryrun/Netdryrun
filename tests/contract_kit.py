"""Conformance kit for the router-state contract (src/netdryrun/contract.py).

A driver proves itself against the kit alone, before it can merge. For each rule C1..C23 the kit has

  - a TRAP: a raw device answer that has produced (or nearly produced) a false pass, and
  - a CONTROL: the healthy twin of it, so a driver cannot pass by refusing everything.

The driver author writes a `Harness` whose `run(rule, kind)` feeds the driver the raw fixture the scenario's `ask`
describes (captured live output, per NOS version) and returns what the driver hands the core: a `Snapshot`,
a `Session` or a `ConfigLoad`. The kit then judges the outcome with the contract's own consumers, so a trap
passes only when the core cannot be made to pass on it.

  - TRAP outcome: acceptable if the driver refuses (raises CollectionError, fail closed) or returns something whose
    consumption is UNKNOWN / NO. Not acceptable: anything that lets the check pass.
  - CONTROL outcome: must be the correct positive answer; a refusal here is a failure.
  - A rule the NOS cannot show at all is declared `NotApplicable(reason)`, counted and listed, never skipped
    silently. `assert_conformant` takes the set of rules a driver may declare not applicable.

    results = run_kit(MyHarness())
    assert_conformant(results, not_applicable={"C20"})
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from netdryrun import contract as c
from netdryrun.contract import (UNKNOWN, CollectionError, Completeness, ConfigLoad, Lookup, Prefix, Session,
                                Snapshot, Tri)

P = Prefix.parse("192.0.2.1/32")
P_SUBNETTED = Prefix.parse("99.99.99.91/32")
PEER_A, PEER_B = "10.0.0.1", "10.0.0.2"
AFI4, AFI6 = "ipv4-unicast", "ipv6-unicast"
COMMUNITY = "65000:666"


class NotApplicable(Exception):
    """The NOS cannot show this at all (say why). Counted; never a silent skip."""


class Harness:
    # Real harnesses also define `fixture(rule, kind, variant) -> bytes`: the captured raw device output that
    # run() parses with the driver's real parser. `run_kit(strict=True)` refuses a harness without them.
    variants = 1      # how many surface forms of each fixture the harness can feed (CRLF, reordered rows, other versions)

    def run(self, rule: str, kind: str, variant: int = 0):          # kind: "trap" | "control"
        raise NotImplementedError


@dataclass(frozen=True)
class Scenario:
    rule: str
    name: str
    source: str                                   # the real case it comes from
    ask: str                                      # the raw fixture the driver is fed, in words
    trap: Callable[[object], str | None]          # None = safe; a string = how it would let a check pass
    control: Callable[[object], str | None]       # None = right answer; a string = what was wrong


def _expect(ok: bool, message: str) -> str | None:
    return None if ok else message


def _is(kind) -> Callable[[object], bool]:
    return lambda o: isinstance(o, kind)


def _snap(o) -> Snapshot:
    if type(o) is not Snapshot:
        raise TypeError(f"expected a Snapshot, got {type(o).__name__}")
    return o


def _sess(o) -> Session:
    if type(o) is not Session:
        raise TypeError(f"expected a Session, got {type(o).__name__}")
    return o


def _cfg(o) -> ConfigLoad:
    if type(o) is not ConfigLoad:
        raise TypeError(f"expected a ConfigLoad, got {type(o).__name__}")
    return o


def _entry(snap: Snapshot, prefix=P):
    return next((e for e in snap.items if e.prefix == prefix), None)


SCENARIOS: list[Scenario] = [
    Scenario("C1", "a failed collection is not an empty table",
             "0.3.0 advisory (error read as 'no routes'); MikroTik 7.23 (non-2xx, no answer); NX-OS transport",
             "the lookup command for 192.0.2.1/32 fails: non-zero exit, exit 0 with an error text, or no answer",
             lambda o: _expect(c.route_present(_snap(o), P) is Lookup.UNKNOWN
                               and _snap(o).completeness is not Completeness.COMPLETE,
                               "a failed command must give UNKNOWN from a non-COMPLETE snapshot (not absent, not present)"),
             lambda o: _expect(c.route_present(_snap(o), P) is Lookup.PRESENT, "healthy answer: 192.0.2.1/32 is present")),
    Scenario("C2", "truncated output cannot prove absence",
             "gauntlet: output limits and timeouts; 'truncated' state in the 0.4.2 review",
             "the table output is cut mid-way, or ends with `Displayed 20 of 500` and exit 0; 198.51.100.0/24 is not in what was read",
             lambda o: _expect(c.route_present(_snap(o), Prefix.parse("198.51.100.0/24")) is Lookup.UNKNOWN
                               and _snap(o).completeness is not Completeness.COMPLETE,
                               "a truncated table must give UNKNOWN from a non-COMPLETE snapshot"),
             lambda o: _expect(c.route_present(_snap(o), Prefix.parse("198.51.100.0/24")) is Lookup.ABSENT,
                               "a complete table without 198.51.100.0/24 must prove it absent")),
    Scenario("C3", "an empty answer needs a confirmed scope",
             "NX-OS empty-VRF trap; MikroTik: unknown routing-table answers 200 with an empty list; 0.3.0 `vrf: all`",
             "an empty answer for VRF NOPE, which the router was never asked to confirm exists",
             lambda o: _expect(c.route_present(_snap(o), P) is Lookup.UNKNOWN,
                               "an empty answer for an unconfirmed VRF must be UNKNOWN"),
             lambda o: _expect(c.route_present(_snap(o), P) is Lookup.ABSENT,
                               "an empty answer for a VRF confirmed to exist is absent")),
    Scenario("C4", "unsupported is stated, never zero",
             "`unsupported_afis` in drivers/__init__ (a count that reads 0 passes max); MikroTik IPv6 unverified",
             "a check asks the accepted count for an AFI this NOS/driver cannot read",
             lambda o: _expect(c.accepted_count(_sess(o), "ipv6-labeled-unicast") is UNKNOWN,
                               "an unreadable AFI gave a number"),
             lambda o: _expect(c.accepted_count(_sess(o), AFI4) == 3, "the supported AFI must give its count (3)")),
    Scenario("C5", "received is not accepted",
             "MikroTik: `prefix-count` is the RECEIVED count; cEOS CLI blends received/accepted/best",
             "the peer sent 4 prefixes, inbound policy rejected 1; the router's session row shows 4",
             lambda o: _expect(c.accepted_count(_sess(o), AFI4) in (3, UNKNOWN),
                               "the received count (4) was read as accepted"),
             lambda o: _expect(c.accepted_count(_sess(o), AFI4) == 3, "accepted must be 3 (derived and marked so)")),
    Scenario("C6", "not collected is not 'nothing sent'",
             "0.4.2 review: with soft-reconfig inbound off an empty Adj-RIB-In means not collected",
             "soft-reconfig inbound is off; the Adj-RIB-In for the peer shows 0 prefixes",
             lambda o: _expect(c.received_nothing(_sess(o), AFI4) is not Tri.YES,
                               "an Adj-RIB-In that is not kept read as 'the peer sent nothing'"),
             lambda o: _expect(c.received_nothing(_sess(o), AFI4) is Tri.YES,
                               "soft-reconfig on and 0 received means the peer sent nothing")),
    Scenario("C7", "best is not installed",
             "MikroTik `best-candidate`: BGP's best outranked by a static default (the leaked-default shape)",
             "192.0.2.1/32: BGP's best path exists but a better protocol owns the FIB entry",
             lambda o: _expect(c.installed_route(_snap(o), P) is not Tri.YES, "a best-but-not-installed path read as installed"),
             lambda o: _expect(c.installed_route(_snap(o), P) is Tri.YES, "a route in the FIB with a gateway is installed")),
    Scenario("C8", "a blackhole or unresolved next hop is not installed",
             "gauntlet R5: `appears_on` satisfied by `ip route X Null0` + redistribute static",
             "192.0.2.1/32 is in the FIB with a blackhole (or unresolved) next hop",
             lambda o: _expect(c.installed_route(_snap(o), P) is not Tri.YES
                               and c.route_present(_snap(o), P) is Lookup.PRESENT,
                               "a blackhole read as installed, or dropped from the table (the prefix must stay, as a discard entry)"),
             lambda o: _expect(c.installed_route(_snap(o), P) is Tri.YES, "a gateway next hop is installed")),
    Scenario("C9", "prefixes are exact and keep their mask",
             "IOS XE: children of 'N/L is subnetted' print without a mask; a dropped mask hides a /32 (false absent)",
             "the table prints 99.99.99.91 under a '99.0.0.0/32 is subnetted' header; the check asks for 99.99.99.91/32",
             lambda o: _expect(c.route_present(_snap(o), P_SUBNETTED) is Lookup.PRESENT,
                               "the mask was lost: a present /32 read as absent or as another length"),
             lambda o: _expect(c.route_present(_snap(o), P) is Lookup.PRESENT, "a full-form 192.0.2.1/32 row is present")),
    Scenario("C10", "a missing 'active' key is not 'not inactive'",
             "MikroTik: an inactive BGP route has `inactive: false` and no `active` key",
             "a BGP route row with `inactive: \"false\"` and no `active` key (it is not installed)",
             lambda o: _expect(c.installed_route(_snap(o), P) is not Tri.YES, "`inactive: false` read as installed"),
             lambda o: _expect(c.installed_route(_snap(o), P) is Tri.YES, "`active: true` is installed")),
    Scenario("C11", "configured is not established; no row is not up",
             "MikroTik: a connection that cannot start has no session row; 0.3.x no-neighbor rule",
             f"a BGP connection to {PEER_A} is configured but the router lists no session for it",
             lambda o: _expect(c.session_established(_snap(o), PEER_A, AFI4) is not Tri.YES, "a missing session row read as up"),
             lambda o: _expect(c.session_established(_snap(o), PEER_A, AFI4) is Tri.YES, "an established row is up")),
    Scenario("C12", "sessions are matched by identity, not by position",
             "MikroTik: sessions are named `<connection>-<n>`; scoped link-locals share one key (BgpNeighbor.ambiguous)",
             f"two sessions listed, {PEER_A} established first, {PEER_B} down second; the check asks about {PEER_B}",
             lambda o: _expect(c.session_established(_snap(o), PEER_B, AFI4) is not Tri.YES,
                               "another session's state answered for the peer asked about"),
             lambda o: _expect(c.session_established(_snap(o), PEER_A, AFI4) is Tri.YES, "the established peer is up")),
    Scenario("C13", "interface and scoped rows are never prefixes",
             "MikroTik: /routing/route lists `belongs-to: interface` rows (`ether3`, `fe80::%ether3/64`)",
             "the table lists two real prefixes plus interface rows and a scoped link-local",
             lambda o: _expect({str(e.prefix) for e in _snap(o).items} == {"192.0.2.1/32", "198.51.100.0/24"}
                               and all(type(e) is c.RibEntry for e in _snap(o).items),
                               "a pseudo row became a route entry, or a real prefix was dropped"),
             lambda o: _expect({str(e.prefix) for e in _snap(o).items} == {"192.0.2.1/32", "198.51.100.0/24"},
                               "exactly the two real prefixes expected")),
    Scenario("C14", "a missing attribute is unknown, not a default",
             "BgpPath docs (`med: None` fails even `med: 0`); MikroTik: missing `bgp.local-pref` is not 0",
             "a path row carries no local-pref (and no way to know the router's default)",
             lambda o: _expect(_entry(_snap(o)).attrs.local_pref is UNKNOWN, "an absent local-pref became a number"),
             lambda o: _expect(_entry(_snap(o)).attrs.local_pref == 200, "a printed local-pref of 200 must be kept")),
    Scenario("C15", "session state is per address family",
             "0.4.2 review: per-AFI neighbor state; `bgp_prefixes afi:` refused when unsupported",
             f"{PEER_A} is established for ipv4-unicast; the check asks about ipv6-unicast (not negotiated)",
             lambda o: _expect(c.session_established(_snap(o), PEER_A, AFI6) is not Tri.YES,
                               "an IPv4 session answered for IPv6"),
             lambda o: _expect(c.session_established(_snap(o), PEER_A, AFI4) is Tri.YES, "ipv4-unicast is up")),
    Scenario("C16", "applied config is verified, or stated unverified",
             "advisory 0.3.2 (FRR skipped a rejected line); F2/F3 (SR Linux startup config); MikroTik import stops at the first error",
             "the NOS has no command that proves its startup config loaded (or the load failed)",
             lambda o: _expect(c.config_applied(_cfg(o)) is not Tri.YES, "an unverifiable or failed config load read as clean"),
             lambda o: _expect(c.config_applied(_cfg(o)) is Tri.YES, "a verified load with nothing rejected is applied")),
    Scenario("C17", "a failed lab command is an error, not a log line",
             "advisory 0.3.3 / F1: containerlab logs a failed `exec:` and exits 0",
             "a topology `exec:` line exited 1 for this node; containerlab still exited 0",
             lambda o: _expect(c.config_applied(_cfg(o)) is Tri.NO, "a failed exec: command did not fail the node's state"),
             lambda o: _expect(c.config_applied(_cfg(o)) is Tri.YES, "every command exited 0")),
    Scenario("C18", "a next-hop set check needs set equality",
             "0.4.2 review: 'any match' passes when one member is stale, blackholed or leaked",
             "192.0.2.1/32 has next hops {10.1.1.1, 10.1.1.2, 10.1.1.3} installed; the check expects {10.1.1.1, 10.1.1.2}",
             lambda o: _expect(c.next_hops_exactly(_snap(o), P, ["10.1.1.1", "10.1.1.2"]) is not Tri.YES,
                               "a leaked third next hop passed a set check"),
             lambda o: _expect(c.next_hops_exactly(_snap(o), P, ["10.1.1.1", "10.1.1.2"]) is Tri.YES,
                               "exactly the expected set must pass")),
    Scenario("C19", "stale paths prove neither presence nor absence",
             "0.4.2 review: graceful-restart / LLGR stale flags",
             "192.0.2.1/32 is present only as a graceful-restart stale path",
             lambda o: _expect(c.route_present(_snap(o), P) is Lookup.UNKNOWN,
                               "a stale path must give UNKNOWN: present would pass a presence check, and dropping it "
                               "(then COMPLETE) would pass an absence check"),
             lambda o: _expect(c.route_present(_snap(o), P) is Lookup.PRESENT, "a live path is present")),
    Scenario("C20", "add-path keeps path identity",
             "0.4.2 review: add-path path ids; best is per prefix, not per path",
             "the peer sent two paths for 192.0.2.1/32 with path ids 1 and 2 (multipath: both may be installed)",
             lambda o: _expect(sorted(str(e.path_id) for e in _snap(o).items if e.prefix == P) == ["1", "2"],
                               "add-path or multipath paths merged into one"),
             lambda o: _expect(len(_snap(o).items) == 1, "a single path stays one entry")),
    Scenario("C21", "a link-local next hop is address plus interface",
             "gauntlet R1: `_boot_free` collapsed every link-local to `fe80::`, hiding a configured wrong next hop",
             "192.0.2.1/32 via fe80::1 on eth1 and via fe80::1 on eth2",
             lambda o: _expect(len({(h.address, h.interface) for e in _snap(o).items for h in e.next_hops}) == 2,
                               "two link-local next hops on different interfaces collapsed into one"),
             lambda o: _expect(len({(h.address, h.interface) for e in _snap(o).items for h in e.next_hops}) == 1,
                               "a global next hop is one hop")),
    Scenario("C22", "'the peer sent P' needs a path received from that peer",
             "MikroTik `bgp-output` candidates; gauntlet R5 (redistribute static); `local_candidate` in BgpPath",
             f"192.0.2.1/32 is in the BGP table only through this router's own network statement, or its sender was inferred "
             f"from the next hop, or only {PEER_B} sent it (two peers in the fixture); the check asks if {PEER_A} sent it",
             lambda o: _expect(c.received_from(_snap(o), PEER_A, P) is not Lookup.PRESENT,
                               "a locally originated route read as 'the peer sent it'"),
             lambda o: _expect(c.received_from(_snap(o), PEER_A, P) is Lookup.PRESENT, "a path received from the peer counts")),
    Scenario("C24", "the answer must come from the node asked",
             "Grok review: docker exec into the wrong container (bgp vs host), vtysh against another file; exit 0",
             "the command answered with another device's hostname (r2 asked of r1), healthy and complete",
             lambda o: _expect(c.route_present(_snap(o), P) is not Lookup.ABSENT
                               and _snap(o).completeness is not Completeness.COMPLETE,
                               "another device's answer was taken as this node's COMPLETE table"),
             lambda o: _expect(c.route_present(_snap(o), P) is Lookup.PRESENT, "the right device's answer is read")),
    Scenario("C25", "a row the parser cannot classify aborts the collection",
             "Grok review: `except: continue` on a refused row, then COMPLETE; IOS XE masks, unknown flags",
             "the table has 198.51.100.0/24 on a row with a flag the parser does not know, and nothing else unusual",
             lambda o: _expect(c.route_present(_snap(o), Prefix.parse("198.51.100.0/24")) is not Lookup.ABSENT,
                               "an unclassifiable row was skipped and the rest called COMPLETE"),
             lambda o: _expect(c.route_present(_snap(o), Prefix.parse("198.51.100.0/24")) is Lookup.PRESENT,
                               "a fully classifiable row is present")),
    Scenario("C26", "only 'established' is up; unknown state text raises",
             "Grok review: any row mapped to Established; `Idle (PfxCt)` after a prefix limit dropped the feed",
             f"{PEER_A} is listed as `Idle (PfxCt)` (and {PEER_B} as `Active`); the rest of the table is healthy",
             lambda o: _expect(c.session_established(_snap(o), PEER_A, AFI4) is not Tri.YES
                               and c.session_established(_snap(o), PEER_B, AFI4) is not Tri.YES,
                               "a down or prefix-limited session read as established"),
             lambda o: _expect(c.session_established(_snap(o), PEER_A, AFI4) is Tri.YES, "`Established` is up")),
    Scenario("C23", "an attribute the command omits is unknown",
             "0.4.2 review: non-detail shows omit communities; gauntlet R6 (Adj-RIB-Out shown before encoding)",
             f"the best path is shown by a command that does not print communities; the check asks that {COMMUNITY} is absent",
             lambda o: _expect(c.community_absent(_entry(_snap(o)), COMMUNITY) is not Tri.YES,
                               "'community absent' passed on a list the command never printed"),
             lambda o: _expect(c.community_absent(_entry(_snap(o)), COMMUNITY) is Tri.YES,
                               "a complete community list without it proves it absent")),
]

SCENARIOS.sort(key=lambda s: int(s.rule[1:]))
RULES = [s.rule for s in SCENARIOS]


@dataclass(frozen=True)
class Result:
    rule: str
    kind: str
    status: str           # pass | fail | n/a
    message: str = ""


def _judge(scenario: Scenario, kind: str, harness: Harness, variant: int = 0) -> Result:
    judge = scenario.trap if kind == "trap" else scenario.control
    try:
        outcome = harness.run(scenario.rule, kind, variant)
    except NotApplicable as e:
        return Result(scenario.rule, kind, "n/a", str(e) or "not applicable")
    except CollectionError as e:
        if kind == "trap":
            return Result(scenario.rule, kind, "pass", f"refused (fail closed): {str(e)[:100]}")
        return Result(scenario.rule, kind, "fail", f"refused a healthy answer: {str(e)[:100]}")
    except Exception as e:  # noqa: BLE001 - an untyped crash is a violation, whatever it is
        return Result(scenario.rule, kind, "fail", f"untyped {type(e).__name__}: {str(e)[:100]} (raise CollectionError)")
    try:
        problem = judge(outcome)
    except (TypeError, AttributeError) as e:
        return Result(scenario.rule, kind, "fail", f"wrong outcome type: {e}")
    return Result(scenario.rule, kind, "pass" if problem is None else "fail", problem or "")


def run_kit(harness: Harness, strict: bool = False) -> list[Result]:
    """Every trap and control, once per fixture variant the harness offers. A driver that keys on one surface form of
    a fixture (its prefix, its error string, a pager token) is caught by the variants, which the driver's own tests
    supply: reordered rows, CRLF, a syslog line above the table, another software version."""
    variants = max(1, int(getattr(harness, "variants", 1)))
    results = [_judge(s, kind, harness, v) for s in SCENARIOS for kind in ("trap", "control") for v in range(variants)]
    if strict:   # the mode a real driver's tests use: raw captured fixtures on disk, at least two surface forms
        if variants < 2:
            results.append(Result("*", "kit", "fail", "strict: the harness must supply at least 2 fixture variants"))
        for s in SCENARIOS:
            for kind in ("trap", "control"):
                for v in range(variants):
                    raw = harness.fixture(s.rule, kind, v) if hasattr(harness, "fixture") else None
                    if not raw:
                        results.append(Result(s.rule, kind, "fail", f"strict: no raw fixture bytes (variant {v})"))
    return results


# Rules a NOS may genuinely be unable to show. Every other rule must be demonstrated by every driver.
MAY_BE_NOT_APPLICABLE = frozenset({"C4", "C6", "C16", "C19", "C20", "C23"})


def failures(results: list[Result], not_applicable: set[str] = frozenset()) -> list[str]:
    out = [f"{r.rule} {r.kind}: {r.message}" for r in results if r.status == "fail"]
    out += [f"{r}: may not be declared not applicable (allowed only for {sorted(MAY_BE_NOT_APPLICABLE)})"
            for r in sorted(set(not_applicable) - MAY_BE_NOT_APPLICABLE)]
    out += [f"{r.rule} {r.kind}: declared not applicable ({r.message}) but the rule is required"
            for r in results if r.status == "n/a" and r.rule not in not_applicable]
    return out


def assert_conformant(results: list[Result], not_applicable: set[str] = frozenset()) -> None:
    bad = failures(results, not_applicable)
    assert not bad, "contract violations:\n  " + "\n  ".join(bad)
