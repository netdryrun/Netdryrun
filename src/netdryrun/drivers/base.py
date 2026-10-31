"""Driver interface. Every method returns normalized data plus the raw evidence it came from."""
from __future__ import annotations

import functools
import ipaddress
import json
import re
from dataclasses import dataclass, field

from ..lab import Lab


class DriverError(RuntimeError):
    pass


class NoSuchInstance(DriverError):
    """The device answered, and the VRF (or its BGP instance) asked for does not exist on it: there is
    nothing there, unlike a command that failed or output that couldn't be read. Still an error for a
    check (a check that names a VRF the node doesn't have is wrong); code that only needs to know which
    BGP sessions exist (a scenario's snapshot) can read it as "none"."""


# Same syntax as config.VRF_NAME. Checked again here: the name goes into device CLI strings, and a
# driver must never be handed a name it would read as something else.
_VRF_NAME = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_.:-]{0,63}")
# Names every supported NOS treats as "many VRFs at once" (output keyed by VRF), never one VRF
SPECIAL_VRF_NAMES = frozenset({"all"})


def check_vrf_name(vrf: object) -> str:
    """The VRF name if a driver can ask for exactly that one VRF; DriverError otherwise."""
    if not isinstance(vrf, str) or not _VRF_NAME.fullmatch(vrf):
        raise DriverError(f"bad VRF name {str(vrf)[:70]!r}: use letters, digits and . _ : - (at most 64)")
    if vrf.lower() in SPECIAL_VRF_NAMES:
        raise DriverError(f"VRF {vrf!r} means every VRF on the device, not one VRF; name the VRF to check")
    return vrf


def unexpected(command: str, text: object) -> DriverError:
    """The error for output that doesn't have the structure the parser knows. Never read it as 'nothing'."""
    snippet = " ".join(str(text).split())[:200] or "no output"
    return DriverError(f"unexpected output from `{command}`: {snippet}")


class RepeatedKey(ValueError):
    def __init__(self, key: str):
        super().__init__(key)
        self.key = key


def no_repeated_keys(pairs: list) -> dict:
    """A JSON object whose keys are all different. A repeated key is never "the last one wins": json.loads would
    keep one value and drop the other silently (0.4: Junos repeats `protocol-nh`)."""
    out: dict = {}
    for k, v in pairs:
        if k in out:
            raise RepeatedKey(k)
        out[k] = v
    return out


def load_json(command: str, text: str, object_pairs_hook=no_repeated_keys):
    """JSON from a device command. Empty output is not an empty result: every supported NOS prints a
    JSON document (at least `{}`) for a state query that succeeded. A repeated key in one object is an error,
    unless the driver's hook knows what the repeat means (Junos)."""
    if not isinstance(text, str) or not text.strip():
        raise unexpected(command, "no output")
    try:
        return json.loads(text, object_pairs_hook=object_pairs_hook)
    except RepeatedKey as e:
        raise DriverError(f"`{command}`: repeated key {e.key!r} in one JSON object; refusing to read one of its "
                          "values as the only one") from None
    except (json.JSONDecodeError, RecursionError):
        raise unexpected(command, text) from None


def network(command: str, value: object):
    """A prefix from device output; output with a key that isn't one is unexpected."""
    try:
        return ipaddress.ip_network(str(value), strict=False)
    except ValueError:
        raise unexpected(command, f"not a prefix: {str(value)[:80]!r}") from None


def parser(command: str):
    """Decorator for a parser of `command`'s output: anything that trips over the output's structure
    (a wrong type, a missing key, a bad number) is reported as unexpected output, a DriverError."""
    def wrap(fn):
        @functools.wraps(fn)
        def inner(*args, **kwargs):
            try:
                return fn(*args, **kwargs)
            except DriverError:
                raise
            except (TypeError, ValueError, AttributeError, KeyError, IndexError, RecursionError) as e:
                raise unexpected(command, f"{type(e).__name__}: {e}") from None
        return inner
    return wrap


def as_int(command: str, value: object) -> int:
    if isinstance(value, bool):
        raise unexpected(command, f"not a number: {value!r}")
    try:
        return int(value)
    except (TypeError, ValueError):
        raise unexpected(command, f"not a number: {str(value)[:80]!r}") from None


@dataclass
class BgpNeighbor:
    address: str
    state: str                                          # lower-case, e.g. "established"
    prefixes: dict[str, int] = field(default_factory=dict)  # afi -> accepted/received prefixes
    # afi -> the most the count can be, where the device leaves received routes out of it for a reason its output
    # doesn't give (Junos hides routes import policy rejected and routes whose next hop it can't use alike): the
    # reference count, received minus rejected by import policy, is then from prefixes[afi] to this (interop IOP-7)
    prefixes_upto: dict[str, int] = field(default_factory=dict)
    # afi -> why the hidden routes behind a prefixes_upto range couldn't be read (a failed command, unreadable output)
    prefixes_unread: dict[str, str] = field(default_factory=dict, compare=False)
    # seconds between advertisements to this neighbor (MRAI) as the device reports it, or the platform's default
    # where it reports none; None: not known. A route can arrive this late after the session looks settled.
    # A timer, not the session's identity: not part of equality.
    adv_interval: float | None = field(default=None, compare=False)
    # Scoped link-locals (fe80::1%eth1, fe80::1%eth2) share one key. When several sessions do, they are all listed
    # here and no session or prefix check is evaluated on the key: either session's state or count would answer
    # for the other one.
    ambiguous: list[str] = field(default_factory=list)


@dataclass
class Route:
    prefix: str
    protocol: str   # lower-case, e.g. "bgp", "connected", "static"
    active: bool


@dataclass
class BgpPath:
    """One path for a prefix in the BGP table. None means the attribute could not be read."""
    best: bool
    as_path: str | None             # ASNs separated by spaces, sets as {a,b}; "" for a locally originated route
    next_hop: str | None
    local_pref: int | None          # effective value: the default local preference when the path carries none
    med: int | None                 # None for a path with no MED attribute: a `med` check fails on it, even
                                    # `med: 0` (missing-as-worst makes a missing MED the worst, not 0)
    communities: list[str] = field(default_factory=list)        # canonical (config.parse_community), standard
    large_communities: list[str] = field(default_factory=list)  # canonical a:b:c
    neighbor: str | None = None
    # The router's own non-BGP route listed in its BGP table, possibly not advertised at all (SR Linux lists
    # its static and interface routes this way). Counts for best-path checks, not for `present: false`.
    local_candidate: bool = False

    def all_communities(self) -> list[str]:
        return self.communities + self.large_communities


def canon_communities(tokens) -> list[str]:
    """Device community strings in the canonical form used by netdryrun.yml; unknown names kept as printed."""
    from ..config import parse_community
    out = []
    for t in tokens or []:
        try:
            out.append(parse_community(t))
        except ValueError:
            out.append(str(t).strip().lower())
    return out


def render_as_path(segments: list[tuple[str, list]]) -> str:
    """(segment type, ASNs) pairs to the netdryrun.yml form: sequences space-separated, sets {a,b},
    confederation sequences (a b), confederation sets [a,b]."""
    parts = []
    for kind, members in segments:
        asns = [str(int(a)) for a in members]
        kind = kind.lower().replace("_", "-")
        if kind in ("as-set", "set"):
            parts.append("{" + ",".join(asns) + "}")
        elif "confed" in kind and "set" in kind:
            parts.append("[" + ",".join(asns) + "]")
        elif "confed" in kind:
            parts.append("(" + " ".join(asns) + ")")
        else:
            parts += asns
    return " ".join(parts)


@dataclass
class Observation:
    """What a driver saw, with the raw command output kept as evidence."""
    value: object
    evidence: list[dict]


class Driver:
    name = "base"

    def __init__(self, lab: Lab, node: str):
        self.lab = lab
        self.node = node

    def _exec(self, cmd: list[str], evidence: list[dict], timeout: float = 60) -> str:
        """Run a state command; a failing command is an error, never silently 'empty state'."""
        r = self.lab.exec(self.node, cmd, timeout=timeout)
        evidence.append({"node": self.node, "cmd": " ".join(cmd), "rc": r.rc, "output": r.stdout[-20000:], "stderr": r.stderr[-2000:]})
        if r.rc != 0:
            msg = (r.stderr or r.stdout).strip().splitlines()
            raise DriverError(f"`{' '.join(cmd)}` failed on {self.node} (rc={r.rc}): {msg[-1] if msg else 'no output'}")
        return r.stdout

    def bgp_neighbors(self, vrf: str = "default") -> Observation:
        raise NotImplementedError

    def routes(self, prefix: str, vrf: str = "default") -> Observation:
        raise NotImplementedError

    def ping(self, target: str, source: str | None, count: int, vrf: str = "default") -> Observation:
        raise NotImplementedError

    # bgp_route keys this driver cannot read; a check that uses one is a setup error, never a guess
    unsupported_bgp_attributes: frozenset[str] = frozenset()
    # bgp_route values this driver's output can't tell apart from another state: {key: {value: why}}; a check
    # that asserts one is refused before deploying (fail closed)
    ambiguous_bgp_values: dict[str, dict] = {}
    # bgp_prefixes address families this driver has no prefix counts for (refused before deploying)
    unsupported_afis: frozenset[str] = frozenset()

    def bgp_paths(self, prefix: str, vrf: str = "default") -> Observation:
        """Every path for exactly `prefix` in the BGP table (list[BgpPath]), best path flagged."""
        raise NotImplementedError

    def all_routes(self, vrf: str = "default", family: int = 4) -> Observation:
        """Every route in the table (used by `netdryrun record`)."""
        raise NotImplementedError

    def nos_version(self) -> str | None:
        """The NOS version the node reports, or None where this driver doesn't read it (yet)."""
        return None

    def vrfs(self) -> Observation:
        """The node's active VRFs other than default (list[str], used by `netdryrun record`)."""
        raise DriverError(f"listing VRFs is not supported on {self.name} yet")
