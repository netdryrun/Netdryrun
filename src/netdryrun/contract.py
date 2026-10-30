"""The router-state contract (0.4.2 draft): what a driver must hand the verdict core, and nothing weaker.

Pure typing and logic, no I/O, not yet used by any shipped driver. Every rule C1..C23 comes from a false pass or
near miss we actually saw (design/modular-architecture.md in the HQ repo has the table with its sources);
`tests/contract_kit.py` is the conformance kit that turns each rule into a must-fail test any driver has to pass.

The shape, in one paragraph. A driver returns `Snapshot`s: items plus a *scope* (node, VRF, AFI, RIB stage, peer),
*provenance* (commands, device, time) and a *completeness* (COMPLETE, TRUNCATED, STALE, UNSUPPORTED, UNKNOWN).
Whether something is absent is never read from `items`: the only way to ask is `lookup()`, which answers ABSENT
only for a COMPLETE snapshot whose scope was confirmed. Anything a command did not show is the sentinel `UNKNOWN`,
never a default. Types refuse to be built in the shapes that caused false passes (a prefix without a mask, a
link-local next hop without an interface), so a parser cannot produce them by accident.
"""
from __future__ import annotations

import enum
import ipaddress
import re
from dataclasses import dataclass, field
from typing import Generic, Iterable, TypeVar

T = TypeVar("T")


class CollectionError(RuntimeError):
    """A driver could not tell. The only acceptable way to fail: never an empty result (C1)."""


class Tri(enum.Enum):
    """A three-valued answer. UNKNOWN is never a pass: the core maps it to INCONCLUSIVE (K1)."""
    YES = "yes"
    NO = "no"
    UNKNOWN = "unknown"

    @staticmethod
    def of(value: bool | None) -> Tri:
        if value is not None and not isinstance(value, bool):
            raise TypeError(f"Tri.of takes a bool or None, got {value!r}")
        return Tri.UNKNOWN if value is None else Tri.YES if value else Tri.NO


class _Unknown:
    """The value of an attribute the command did not show (C14, C23). Falsy, equal only to itself."""
    _instance: _Unknown | None = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __repr__(self) -> str:
        return "UNKNOWN"

    def __bool__(self) -> bool:
        return False


UNKNOWN = _Unknown()


class Stage(enum.Enum):
    """Where in the router a route or count was read (C5). They are different facts, never interchangeable."""
    ADJ_RIB_IN = "adj-rib-in"      # received from the peer, before policy
    ACCEPTED = "accepted"          # after inbound policy
    LOC_RIB = "loc-rib"            # candidates in the BGP table
    BEST = "best"                  # BGP's best path for the prefix
    FIB = "fib"                    # installed for forwarding
    ADJ_RIB_OUT = "adj-rib-out"    # advertised to a peer


class Completeness(enum.Enum):
    COMPLETE = "complete"          # the whole table for this scope was read and parsed
    TRUNCATED = "truncated"        # cut off (output limit, timeout, partial page): presence provable, absence not
    STALE = "stale"                # read before the point the check needs (e.g. before the settle time) (C19)
    UNSUPPORTED = "unsupported"    # this NOS/driver cannot read this stage, AFI or attribute (C4)
    UNKNOWN = "unknown"            # could not be read or its scope not confirmed; see `cause`


class Cause(enum.Enum):
    COMMAND_FAILED = "command-failed"          # non-zero exit, non-2xx, error text with exit 0 (C1)
    NO_ANSWER = "no-answer"                    # transport failure, VM not up (C1)
    SCOPE_UNCONFIRMED = "scope-unconfirmed"    # VRF/table/instance not confirmed to exist (C3)
    NOT_COLLECTED = "not-collected"            # e.g. soft-reconfig off: Adj-RIB-In is not kept (C6)
    NOT_IMPLEMENTED = "not-implemented"
    OMITTED_BY_COMMAND = "omitted-by-command"  # the show command does not print it (C23)


class Origin(enum.Enum):
    RECEIVED = "received"          # a path a peer sent (C22)
    NETWORK = "network"            # this router's own network/redistribute/aggregate statement
    REDISTRIBUTED = "redistributed"
    AGGREGATE = "aggregate"
    CONNECTED = "connected"
    STATIC = "static"


class HopKind(enum.Enum):
    GATEWAY = "gateway"
    INTERFACE = "interface"
    BLACKHOLE = "blackhole"
    REJECT = "reject"
    UNRESOLVED = "unresolved"


# ---------------------------------------------------------------------------------------------------------------
# Identity types that refuse the shapes that caused false passes
# ---------------------------------------------------------------------------------------------------------------

@dataclass(frozen=True)
class Prefix:
    """An exact prefix. Built only from text with an explicit length (C9): a bare `10.0.0.1` is refused, because a
    parser that dropped the mask (IOS XE prints children of `N/L is subnetted` without one) turns a /32 into a /24
    and makes `present: false` pass."""
    net: ipaddress.IPv4Network | ipaddress.IPv6Network

    @staticmethod
    def parse(text: str, *, default_len: int | None = None) -> Prefix:
        """`default_len` is for a caller that has the mask from elsewhere (a header line); it is never guessed."""
        s = str(text).strip()
        if "/" not in s:
            if default_len is None:
                raise CollectionError(f"prefix {s!r} has no length: the mask must come from the output, not a guess")
            s = f"{s}/{default_len}"
        try:
            return Prefix(ipaddress.ip_network(s, strict=True))
        except ValueError as e:
            raise CollectionError(f"not a prefix: {s!r} ({e})") from None

    def __str__(self) -> str:
        return str(self.net)


@dataclass(frozen=True)
class NextHop:
    kind: HopKind
    address: str | None = None
    interface: str | None = None           # required for a link-local address (C21)
    resolved_via: str | None = None        # the next hop the router resolved it to, when it recurses

    def __post_init__(self):
        if self.kind is HopKind.INTERFACE and not self.interface:
            raise CollectionError("an interface next hop needs the interface")
        if self.kind is HopKind.GATEWAY:
            if not self.address:
                raise CollectionError("a gateway next hop needs an address")
            try:
                ip = ipaddress.ip_address(self.address.split("%")[0])
            except ValueError:
                raise CollectionError(f"next hop {self.address!r} is not an address") from None
            if ip.is_unspecified:
                raise CollectionError(f"next hop {self.address} is the unspecified address: a discard, not a gateway")
            if ip.is_link_local and not self.interface:
                raise CollectionError(f"link-local next hop {self.address} without its interface: fe80::1 on two "
                                      "interfaces are two different neighbors")

    @property
    def forwards(self) -> bool:
        """Traffic really leaves through it: a blackhole, a reject and an unresolved hop do not (C8)."""
        return self.kind in (HopKind.GATEWAY, HopKind.INTERFACE)


@dataclass(frozen=True)
class Attrs:
    """BGP attributes of one path. Each is a value or UNKNOWN; a missing local-pref is not 0 (C14)."""
    local_pref: int | _Unknown = UNKNOWN
    med: int | _Unknown = UNKNOWN
    as_path: str | _Unknown = UNKNOWN
    communities: frozenset[str] | _Unknown = UNKNOWN   # canonical strings (config.parse_community)
    # True only when the command that produced this entry prints all communities; a non-detail show does not (C23)
    communities_complete: bool = False


@dataclass(frozen=True)
class RibEntry:
    """One path or route for one exact prefix, with the stages it was seen at."""
    prefix: Prefix
    origin: Origin
    stages: frozenset[Stage]
    peer: str | None = None                # session id (C12), for RECEIVED paths
    path_id: int | None = None             # add-path identity (C20)
    next_hops: tuple[NextHop, ...] = ()
    stale: bool | _Unknown = UNKNOWN      # graceful-restart / LLGR stale flag (C19)
    attrs: Attrs = field(default_factory=Attrs)

    def __post_init__(self):
        if self.origin is Origin.RECEIVED and not self.peer:
            raise CollectionError("a RECEIVED path must name the session it came from")

    @property
    def best(self) -> bool:
        return Stage.BEST in self.stages

    @property
    def installed(self) -> Tri:
        """Installed means in the FIB with a next hop that forwards (C7, C8). BEST alone is not installed."""
        if Stage.FIB not in self.stages:
            return Tri.NO
        if not self.next_hops:
            return Tri.UNKNOWN
        return Tri.of(all(h.forwards for h in self.next_hops))


# ---------------------------------------------------------------------------------------------------------------
# Snapshots: the only way a driver hands state to the core
# ---------------------------------------------------------------------------------------------------------------

@dataclass(frozen=True)
class Scope:
    node: str
    vrf: str = "default"
    afi: str = "ipv4-unicast"
    stage: Stage | None = None
    peer: str | None = None


@dataclass(frozen=True)
class Provenance:
    device: str                            # the node the answer was VERIFIED to come from (hostname/identity check)
    commands: tuple[str, ...]
    observed_at: float                     # when the oldest command in `commands` STARTED, not when parsing ended
    derived_from: Stage | None = None      # set when a value was computed, e.g. accepted = received minus filtered (C5)

    def __post_init__(self):
        if not self.commands or not self.device:
            raise CollectionError("provenance needs the device and the commands the snapshot was read with")


@dataclass(frozen=True)
class Snapshot(Generic[T]):
    scope: Scope
    provenance: Provenance
    completeness: Completeness
    items: tuple[T, ...] = ()
    cause: Cause | None = None
    reason: str = ""
    scope_confirmed: bool = False          # the VRF/table/instance was shown to exist (C3)
    scope_evidence: str = ""               # the command that showed it; required when scope_confirmed (auditable)
    # Why COMPLETE is true: "no pager marker, row count 12 equals the device's own total". Required for COMPLETE.
    # A short command is not complete by being successful: hidden routes, terse next hops and "Displayed 20 of 500"
    # all exit 0 (C2).
    complete_evidence: str = ""

    def __post_init__(self):
        c = self.completeness
        if c in (Completeness.UNSUPPORTED, Completeness.UNKNOWN):
            if self.items:
                raise CollectionError(f"a {c.value} snapshot cannot carry items")
            if self.cause is None:
                raise CollectionError(f"a {c.value} snapshot must say why (cause)")
        if self.provenance.device != self.scope.node:
            raise CollectionError(f"answer verified as coming from {self.provenance.device!r}, asked of "
                                  f"{self.scope.node!r}: another device's table is not this node's (C24)")
        if self.scope_confirmed and self.scope_evidence not in self.provenance.commands:
            raise CollectionError("scope_confirmed needs scope_evidence: a command in provenance.commands that "
                                  "showed the VRF/table exists")
        if c is Completeness.COMPLETE and self.cause is not None:
            raise CollectionError("a COMPLETE snapshot has no cause")
        if c is Completeness.COMPLETE and not self.complete_evidence:
            raise CollectionError("a COMPLETE snapshot needs complete_evidence: what shows the whole table was read")

    def lookup(self, match) -> Lookup:
        """Is something matching present? The only place absence is decided (C1-C3, C19)."""
        if self.completeness is Completeness.STALE:
            return Lookup.UNKNOWN                   # read before the time the check needs: proves nothing (C19)
        hits = [i for i in self.items if match(i)]
        live = [i for i in hits if getattr(i, "stale", False) is False]   # an unknown stale flag is not "live"
        if live:
            return Lookup.PRESENT
        if hits:                                    # only stale or unknown-staleness matches: not proof either way
            return Lookup.UNKNOWN
        if self.completeness is Completeness.UNSUPPORTED:
            return Lookup.UNSUPPORTED
        if self.completeness is Completeness.COMPLETE and self.scope_confirmed:
            return Lookup.ABSENT
        return Lookup.UNKNOWN

    def none(self, match) -> Tri:
        """'No item matches' (a leak check): YES only for an ABSENT lookup, NO for a live match, else UNKNOWN."""
        found = self.lookup(match)
        return Tri.YES if found is Lookup.ABSENT else Tri.NO if found is Lookup.PRESENT else Tri.UNKNOWN

    def every(self, match) -> Tri:
        """'Every item satisfies match' (all sessions up): needs the whole table, so COMPLETE and confirmed; an empty
        table is UNKNOWN (K2); a stale or unknown-staleness item is UNKNOWN (K3)."""
        if self.completeness is not Completeness.COMPLETE or not self.scope_confirmed or not self.items:
            return Tri.UNKNOWN
        if any(getattr(i, "stale", False) is not False or getattr(i, "vrf", self.scope.vrf) != self.scope.vrf
               for i in self.items):
            return Tri.UNKNOWN
        return Tri.of(all(match(i) for i in self.items))

    def at_least(self, not_before: float) -> Snapshot[T]:
        """The same snapshot, relabelled STALE when it was read before the time the check needs (C19)."""
        if self.provenance.observed_at >= not_before or self.completeness is not Completeness.COMPLETE:
            return self
        return Snapshot(self.scope, self.provenance, Completeness.STALE, self.items, None,
                        "read before the required time", self.scope_confirmed,
                        self.scope_evidence, self.complete_evidence)


class Lookup(enum.Enum):
    PRESENT = "present"
    ABSENT = "absent"
    UNKNOWN = "unknown"
    UNSUPPORTED = "unsupported"


def _answers(snap: Snapshot, vrf: str, prefix: Prefix | None = None, stage: Stage | None = None) -> bool:
    """Does this snapshot's scope cover the question? A LOC_RIB snapshot says nothing about the FIB, an IPv6
    snapshot nothing about an IPv4 prefix, and another VRF's table nothing about this one."""
    s = snap.scope
    if s.vrf != vrf:
        return False
    if stage is not None and s.stage is not None and s.stage is not stage:
        return False
    if prefix is not None and not s.afi.startswith(f"ipv{prefix.net.version}-"):
        return False
    return True


def route_present(snap: Snapshot[RibEntry], prefix: Prefix, stage: Stage = Stage.FIB, vrf: str = "default") -> Lookup:
    """Is exactly `prefix` present at `stage`? A covering or default route never matches (C9). A snapshot of another
    scope, or one read too early (STALE), is UNKNOWN."""
    if not _answers(snap, vrf, prefix, stage):
        return Lookup.UNKNOWN
    return snap.lookup(lambda e: e.prefix == prefix and stage in e.stages)


def installed_route(snap: Snapshot[RibEntry], prefix: Prefix, vrf: str = "default") -> Tri:
    """A route that forwards: a live FIB entry with a gateway/interface next hop; a blackhole is not (C7, C8). A
    stale entry, a STALE snapshot, or entries that disagree are UNKNOWN (C19)."""
    if not _answers(snap, vrf, prefix, Stage.FIB) or snap.completeness in (
            Completeness.STALE, Completeness.UNKNOWN, Completeness.UNSUPPORTED):
        return Tri.UNKNOWN
    fib = [e for e in snap.items if e.prefix == prefix and Stage.FIB in e.stages]
    if any(e.stale is not False for e in fib):
        return Tri.UNKNOWN
    states = {e.installed for e in fib}
    if states == {Tri.YES}:
        return Tri.YES
    if not fib:
        return Tri.NO if snap.completeness is Completeness.COMPLETE and snap.scope_confirmed else Tri.UNKNOWN
    if Tri.UNKNOWN in states or Tri.YES in states:
        return Tri.UNKNOWN                                  # a forwarding entry beside a blackhole: ambiguous
    return Tri.NO


_RECEIVED_STAGES = frozenset({Stage.ADJ_RIB_IN, Stage.ACCEPTED, Stage.LOC_RIB})


def received_from(snap: Snapshot[RibEntry], session_id: str, prefix: Prefix, vrf: str = "default") -> Lookup:
    """Did the session `session_id` (the router's own id, C12; resolve an address through the sessions snapshot)
    send this prefix? Only a RECEIVED path of that session, seen at a receive stage, counts (C22); a path that is
    only in Adj-RIB-Out does not. A sender inferred from derived data is not the sender: UNKNOWN."""
    if snap.provenance.derived_from is not None or not _answers(snap, vrf, prefix):
        return Lookup.UNKNOWN
    return snap.lookup(lambda e: e.prefix == prefix and e.origin is Origin.RECEIVED and e.peer == session_id
                       and bool(e.stages & _RECEIVED_STAGES))


def hop_key(h: NextHop) -> tuple[str | None, str | None]:
    """A next hop's identity: its address, plus the interface when the address is link-local (C21); an interface
    hop is its interface."""
    if h.kind is HopKind.INTERFACE:
        return (None, h.interface)
    ll = h.address is not None and ipaddress.ip_address(h.address.split("%")[0]).is_link_local
    return (h.address, h.interface if ll else None)


def next_hops_exactly(snap: Snapshot[RibEntry], prefix: Prefix, expected: Iterable[str | tuple[str, str]],
                      vrf: str = "default") -> Tri:
    """The installed next-hop set equals `expected` (addresses; (address, interface) for a link-local). 'Any
    match' passes when one member is stale, blackholed or leaked, so this needs a COMPLETE snapshot, live
    entries, every member forwarding, and set equality (C18, C19, C21)."""
    if (snap.completeness is not Completeness.COMPLETE or not snap.scope_confirmed
            or not _answers(snap, vrf, prefix, Stage.FIB)):
        return Tri.UNKNOWN
    fib = [e for e in snap.items if e.prefix == prefix and Stage.FIB in e.stages]
    if not fib or any(e.stale is not False for e in fib):
        return Tri.UNKNOWN
    hops = [h for e in fib for h in e.next_hops]
    if not hops:
        return Tri.UNKNOWN
    if not all(h.forwards for h in hops):
        return Tri.NO                                       # a blackholed or unresolved member is a leak
    want = {(x, None) if isinstance(x, str) else tuple(x) for x in expected}
    return Tri.of({hop_key(h) for h in hops} == want)


def community_absent(entry: RibEntry, community: str) -> Tri:
    """'Community C is not on the path' needs a complete, live list; the query is canonicalised the way the
    entry's list is (C23)."""
    from .config import parse_community
    try:
        community = parse_community(community)
    except ValueError:
        community = str(community).strip().lower()
    if entry.stale is not False or entry.attrs.communities is UNKNOWN:
        return Tri.UNKNOWN
    if community in entry.attrs.communities:
        return Tri.NO
    return Tri.YES if entry.attrs.communities_complete else Tri.UNKNOWN


# ---------------------------------------------------------------------------------------------------------------
# Sessions
# ---------------------------------------------------------------------------------------------------------------

class SessionState(enum.Enum):
    ESTABLISHED = "established"
    NOT_ESTABLISHED = "not-established"
    NO_ROW = "no-row"              # configured, but the router shows no session for it (C11)
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class AfiState:
    afi: str
    up: Tri
    # counts by the stage they were read at; a missing stage is UNKNOWN, never 0 (C5, C6)
    counts: tuple[tuple[Stage, int], ...] = ()
    soft_reconfig_in: Tri = Tri.UNKNOWN

    def count(self, stage: Stage) -> int | _Unknown:
        return dict(self.counts).get(stage, UNKNOWN)


@dataclass(frozen=True)
class Session:
    id: str                         # the router's own session/connection name, never a list position (C12)
    peer: str
    vrf: str = "default"
    configured: Tri = Tri.UNKNOWN
    state: SessionState = SessionState.UNKNOWN
    reason: str = ""
    afis: tuple[AfiState, ...] = ()

    def afi(self, afi: str) -> AfiState | None:
        return next((a for a in self.afis if a.afi == afi), None)


_DOWN_STATES = frozenset({"idle", "connect", "active", "opensent", "openconfirm", "closing", "clearing", "deleted",
                          "notification", "shutdown"})


def parse_session_state(text: str) -> SessionState:
    """The FSM text a router prints, to a state (C26). Only exactly 'established' (or 'estab') is up; the known down
    states - including 'Idle (Admin)' and 'Idle (PfxCt)', where a prefix limit has dropped the feed - are
    NOT_ESTABLISHED; any other text raises, so a new state word is never read as up or as nothing."""
    words = str(text).strip().lower().replace("(", " ").replace(")", " ").split()
    if len(words) == 1 and words[0] in ("established", "estab"):
        return SessionState.ESTABLISHED
    if words and words[0] in _DOWN_STATES:
        return SessionState.NOT_ESTABLISHED
    raise CollectionError(f"unknown BGP session state {str(text)[:40]!r}")


def _same_peer(a: str, b: str) -> bool:
    try:
        return (ipaddress.ip_address(a.split("%")[0]) == ipaddress.ip_address(b.split("%")[0])
                and a.partition("%")[2] == b.partition("%")[2])
    except ValueError:
        return a == b


def session_established(snap: Snapshot[Session], peer: str, afi: str, vrf: str = "default") -> Tri:
    """Is the session with `peer` in `vrf` up for `afi`? No row, a different session, another VRF's row, an AFI that
    was not negotiated, or a STALE snapshot is not YES (C11, C12, C15, C19). A COMPLETE snapshot without the peer
    says the router does not know it: NO."""
    if snap.completeness is Completeness.STALE or snap.scope.vrf != vrf:
        return Tri.UNKNOWN
    if any(s.vrf != snap.scope.vrf for s in snap.items):
        return Tri.UNKNOWN                              # a snapshot that mixes VRFs is not one table
    rows = [s for s in snap.items if _same_peer(s.peer, peer)]
    if len(rows) > 1 or len({s.id for s in snap.items}) != len(snap.items):
        return Tri.UNKNOWN                              # ambiguous or duplicate ids, never pick one
    if not rows:
        return Tri.NO if snap.completeness is Completeness.COMPLETE and snap.scope_confirmed else Tri.UNKNOWN
    s = rows[0]
    if s.state is not SessionState.ESTABLISHED:
        return Tri.NO if s.state in (SessionState.NOT_ESTABLISHED, SessionState.NO_ROW) else Tri.UNKNOWN
    a = s.afi(afi)
    return a.up if a is not None else Tri.UNKNOWN


def accepted_count(session: Session, afi: str) -> int | _Unknown:
    """Prefixes accepted from the peer after inbound policy. The received count is a different number (C5)."""
    a = session.afi(afi)
    return a.count(Stage.ACCEPTED) if a else UNKNOWN


def count_in_range(count: int | _Unknown, low: int | None, high: int | None) -> Tri:
    if count is UNKNOWN:
        return Tri.UNKNOWN
    if isinstance(count, bool) or not isinstance(count, int):
        raise TypeError(f"a count is an int or UNKNOWN, not {count!r}")
    return Tri.of((low is None or count >= low) and (high is None or count <= high))


def received_nothing(session: Session, afi: str) -> Tri:
    """'The peer sent no prefixes' - provable only for an established session whose Adj-RIB-In is kept
    (soft-reconfig inbound on) and counted (C6)."""
    a = session.afi(afi)
    if (session.state is not SessionState.ESTABLISHED or a is None or a.up is not Tri.YES
            or a.soft_reconfig_in is not Tri.YES):
        return Tri.UNKNOWN
    n = a.count(Stage.ADJ_RIB_IN)
    return Tri.UNKNOWN if n is UNKNOWN else Tri.of(n == 0)


# ---------------------------------------------------------------------------------------------------------------
# Applied configuration and lab commands (C16, C17)
# ---------------------------------------------------------------------------------------------------------------

@dataclass(frozen=True)
class LabCommand:
    """A command the lab ran for the node (a topology `exec:`, a `setup:` line)."""
    command: str
    rc: int
    output: str = ""


# output that says a command failed although it exited 0 (containerlab's logged exec failure, vtysh/IOS/EOS errors)
_FAILED_OUTPUT = re.compile(r"(?im)(failed to execute command|% ?(unknown|invalid|ambiguous|incomplete)|"
                            r"command incomplete|^error\b|\berror:)")


@dataclass(frozen=True)
class ConfigLoad:
    """Did the node run the configuration the checks assume? `rejected` lists lines the NOS refused.
    `verified` is False when the driver has no way to know (cEOS, SR Linux, SONiC startup config in 0.3.3); True
    needs `evidence`: what was compared with what (the daemon's running config, the boot log) (C16)."""
    verified: bool
    rejected: tuple[str, ...] = ()
    lab_commands: tuple[LabCommand, ...] = ()
    evidence: str = ""

    def __post_init__(self):
        if self.verified and not self.evidence:
            raise CollectionError("a verified config load needs evidence: what was read to verify it")


def config_applied(load: ConfigLoad) -> Tri:
    """YES only when verified, nothing was rejected and every lab command exited 0 without failure text. An
    unverified load is UNKNOWN, stated in the report as 'not verified', never 'clean' (C16); a failed lab command
    is NO even when it exited 0 (C17)."""
    if load.rejected or any(c.rc != 0 or _FAILED_OUTPUT.search(c.output) for c in load.lab_commands):
        return Tri.NO
    return Tri.YES if load.verified else Tri.UNKNOWN


# ---------------------------------------------------------------------------------------------------------------
# Core-side invariants the contract relies on (K1-K3). They live in the verdict core; restated here so that the
# kit can prove a module cannot weaken them.
# ---------------------------------------------------------------------------------------------------------------

def quantify_all(values: Iterable[Tri]) -> Tri:
    """'all of these' over an empty set is UNKNOWN, not YES (K2); one UNKNOWN among YES is UNKNOWN; any NO is NO.
    Anything that is not a Tri (a Lookup, a bool, None) is a bug in the caller, not a pass."""
    vs = list(values)
    for v in vs:
        if not isinstance(v, Tri):
            raise TypeError(f"quantify_all takes Tri values, got {v!r}")
    if not vs:
        return Tri.UNKNOWN
    if Tri.NO in vs:
        return Tri.NO
    return Tri.UNKNOWN if Tri.UNKNOWN in vs else Tri.YES


def verdict(answer: Tri, on_unknown: str = "inconclusive") -> str:
    """K1: only YES passes. `on_unknown` can name a stricter outcome, never `pass`."""
    if not isinstance(answer, Tri):
        raise TypeError(f"verdict takes a Tri, got {answer!r}")
    if on_unknown not in ("inconclusive", "fail"):
        raise ValueError("on_unknown can be 'inconclusive' or 'fail'; unknown and unsupported never pass")
    return "pass" if answer is Tri.YES else "fail" if answer is Tri.NO else on_unknown
