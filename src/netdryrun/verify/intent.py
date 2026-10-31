"""The intent file: what a change is meant to do, one line per prefix or session.

    intent:
      - prefix: 10.101.0.0/24
        appears_on: [edge1, up1, peer1]       # absent before; after: selected and in the FIB (state: installed)
        with: {from: 10.0.1.2, as_path: "65101"}
      - prefix: 203.0.113.0/24
        best_path_on: edge1
        to: {local_pref: 200}                 # listed values exact, every other attribute frozen
      - session: {node: edge1, neighbor: 10.0.9.2, afi: ipv4-unicast}
        goes: down                            # afi: always (validated before anything boots)
      - prefix: 192.0.2.128/25
        disappears_from: [cust1]              # selected before; gone after
        including_received_only: true
      - prefix: 198.51.100.0/24
        advertisement: {node: edge1, neighbor: 192.0.2.9}
        goes: added                           # or removed, or to: {...}; added carries the best path's
                                              # attributes, or the ones given in with: {...}
    allow_anywhere: ["10.200.*.0/24"]          # `*` = one whole octet; /16 reach at most; explicit length

Validation is strict: an unknown key, a wrong type, a prefix with host bits, two lines about the same
thing, or a node that is not in the topology is an IntentError (exit 2). A line without `vrf` means the
default VRF only.
"""
from __future__ import annotations

import ipaddress
import re
from dataclasses import dataclass, field

from ..config import VRF_NAME, ConfigError, load_yaml
from .frr import PROTOCOLS
from .snapshot import (AFI_SAFIS, ORIGINS, AsPath, SnapshotError, canon_community, canon_ext_community, canon_ip,
                       canon_large_community)


class IntentError(ValueError):
    pass


TOP_KEYS = ("intent", "allow_anywhere")
FORMS = ("appears_on", "disappears_from", "best_path_on", "session", "advertisement", "config_change_on")
STATES = ("installed", "selected", "received", "discard")
# Attributes `to:` may set on a best path (or an advertisement), and `with:` may pin on a new route
BGP_ATTRS = ("from", "next_hop", "as_path", "origin", "local_pref", "med", "weight", "communities",
             "ext_communities", "large_communities", "cluster_list", "originator_id")
WITH_KEYS = BGP_ATTRS + ("protocol", "distance", "metric")
LINE_KEYS = {
    "appears_on": {"prefix", "vrf", "appears_on", "state", "with"},
    "disappears_from": {"prefix", "vrf", "disappears_from", "including_received_only"},
    "best_path_on": {"prefix", "vrf", "best_path_on", "to"},
    "session": {"session", "goes"},
    "advertisement": {"prefix", "vrf", "advertisement", "goes", "to", "with"},
    "config_change_on": {"config_change_on"},
}
SESSION_KEYS = ("node", "neighbor", "vrf", "afi")
ADVERTISEMENT_KEYS = ("node", "neighbor")


@dataclass(frozen=True)
class Line:
    index: int
    form: str
    text: str                               # one-line human echo
    prefix: str | None = None
    vrf: str = "default"
    nodes: tuple[str, ...] = ()             # appears_on / disappears_from targets, or the one node of the line
    state: str = "installed"
    pins: dict = field(default_factory=dict)
    to: dict = field(default_factory=dict)
    including_received_only: bool = False
    neighbor: str | None = None
    afi: str | None = None                  # session lines: "ipv4-unicast" / "ipv6-unicast"
    goes: str | None = None

    @property
    def node(self) -> str:
        return self.nodes[0]


# How far an allow_anywhere glob may reach: its wildcards only stand for octets (hextets) past this many bits
GLOB_REACH = {4: 16, 6: 48}


def _groups(net) -> tuple[int, ...]:
    """A network address as its octets (IPv4) or hextets (IPv6)."""
    b = net.network_address.packed
    return tuple(b) if net.version == 4 else tuple(int.from_bytes(b[i:i + 2], "big") for i in range(0, 16, 2))


@dataclass(frozen=True)
class Allow:
    pattern: str
    vrf: str
    glob: bool
    version: int = 0
    groups: tuple = ()        # a glob: per octet (hextet) its value, or None for `*`
    length: int = 0           # a glob: the prefix length, always explicit

    def matches(self, prefix: str, vrf: str) -> bool:
        """Exact prefix, or a glob whose `*` stands for one whole octet (hextet) with the same explicit
        prefix length. Never supernet containment."""
        if vrf != self.vrf:
            return False
        if not self.glob:
            return prefix == self.pattern
        try:
            net = ipaddress.ip_network(prefix, strict=True)
        except ValueError:
            return False
        if net.version != self.version or net.prefixlen != self.length:
            return False
        return all(w is None or w == g for w, g in zip(self.groups, _groups(net), strict=True))


@dataclass
class Intent:
    lines: list[Line]
    allow: list[Allow]
    source: str
    echo: dict              # the file's content, normalised, echoed at the top of every report

    @property
    def empty(self) -> bool:
        return not self.lines and not self.allow

    def nodes(self) -> set[str]:
        return {n for ln in self.lines for n in ln.nodes}


def _where(i: int) -> str:
    return f"intent[{i}]"


def _prefix(where: str, value) -> str:
    if not isinstance(value, str):
        raise IntentError(f"{where}: prefix must be a string such as 10.0.0.0/24, got {value!r}")
    try:
        net = ipaddress.ip_network(value.strip(), strict=True)
    except ValueError as e:
        raise IntentError(f"{where}: bad prefix {value!r}: {e} (write the network address, e.g. 10.0.0.0/24)") from None
    if "/" not in value:
        raise IntentError(f"{where}: write the prefix length too ({net})")
    return str(net)


def _vrf(where: str, value) -> str:
    if value is None:
        return "default"
    if not isinstance(value, str) or not VRF_NAME.fullmatch(value) or value.lower() == "all":
        raise IntentError(f"{where}: bad vrf {value!r}: name one VRF (letters, digits and . _ : -)")
    return value


def _nodes(where: str, key: str, value) -> tuple[str, ...]:
    items = [value] if isinstance(value, str) else value
    if not isinstance(items, list) or not items or not all(isinstance(n, str) and n for n in items):
        raise IntentError(f"{where}: {key} must be a node name or a non-empty list of node names")
    if len(set(items)) != len(items):
        raise IntentError(f"{where}: {key} lists a node twice")
    return tuple(items)


def _ip(where: str, key: str, value) -> str:
    try:
        return canon_ip(value, f"{where}: {key}")
    except SnapshotError:
        raise IntentError(f"{where}: {key} must be an IP address, got {value!r}") from None


def _int_or_null(where: str, key: str, value):
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 0xFFFFFFFF:
        raise IntentError(f"{where}: {key} must be an integer 0..4294967295 or null (absent), got {value!r}")
    return value


def _attr(where: str, key: str, value):
    """One `with:`/`to:` value in its canonical form (the form the snapshot uses)."""
    try:
        if key == "from":
            return "local" if value == "local" else _ip(where, key, value)
        if key == "next_hop":
            vals = value if isinstance(value, list) else [value]
            if not vals:
                raise IntentError(f"{where}: next_hop needs at least one address")
            return tuple(sorted({_ip(where, key, v) for v in vals}))
        if key == "as_path":
            return AsPath.parse(value)
        if key == "origin":
            if value not in ORIGINS:
                raise IntentError(f"{where}: origin must be one of {', '.join(ORIGINS)}, got {value!r}")
            return value
        if key in ("local_pref", "med", "weight"):
            return _int_or_null(where, key, value)
        if key in ("communities", "large_communities", "ext_communities"):
            if not isinstance(value, list):
                raise IntentError(f"{where}: {key} must be a list (the exact set; [] for none)")
            fn = {"communities": canon_community, "large_communities": canon_large_community,
                  "ext_communities": canon_ext_community}[key]
            return tuple(sorted({fn(v) for v in value}))
        if key == "cluster_list":
            if not isinstance(value, list):
                raise IntentError(f"{where}: cluster_list must be a list of router IDs, in order")
            return tuple(_ip(where, key, v) for v in value)
        if key == "originator_id":
            return None if value is None else _ip(where, key, value)
        if key == "protocol":
            if value not in PROTOCOLS:
                raise IntentError(f"{where}: unknown protocol {value!r}")
            return value
        if key in ("distance", "metric"):
            if value is None:
                raise IntentError(f"{where}: {key} must be an integer")
            return _int_or_null(where, key, value)
    except SnapshotError as e:
        raise IntentError(f"{where}: {key}: {e}") from None
    raise IntentError(f"{where}: unknown attribute {key!r}")   # pragma: no cover - keys are checked first


def _attrs(where: str, key: str, value, allowed: tuple[str, ...]) -> dict:
    if not isinstance(value, dict) or not value:
        raise IntentError(f"{where}: {key} must be a non-empty mapping of attributes")
    unknown = sorted(set(value) - set(allowed))
    if unknown:
        raise IntentError(f"{where}: {key}: unknown attribute(s) {', '.join(map(str, unknown))}; "
                          f"allowed: {', '.join(allowed)}")
    return {k: _attr(f"{where}: {key}", k, v) for k, v in value.items()}


def _bool(where: str, key: str, value) -> bool:
    if not isinstance(value, bool):
        raise IntentError(f"{where}: {key} must be true or false (unquoted), got {value!r}")
    return value


def _line(i: int, raw) -> Line:
    where = _where(i)
    if not isinstance(raw, dict):
        raise IntentError(f"{where}: each intent line must be a mapping, got {type(raw).__name__}")
    forms = [f for f in FORMS if f in raw]
    if len(forms) != 1:
        raise IntentError(f"{where}: each line needs exactly one of {', '.join(FORMS)} (got {forms or 'none'})")
    form = forms[0]
    unknown = sorted(set(map(str, raw)) - LINE_KEYS[form])
    if unknown:
        raise IntentError(f"{where}: unknown key(s) {', '.join(unknown)} for a {form} line; "
                          f"allowed: {', '.join(sorted(LINE_KEYS[form]))}")
    if form == "session":
        s = raw["session"]
        if not isinstance(s, dict) or not {"node", "neighbor"} <= set(s) or set(s) - set(SESSION_KEYS):
            raise IntentError(f"{where}: session must be a mapping with node, neighbor and afi (and optional vrf)")
        if raw.get("goes") != "down":
            raise IntentError(f"{where}: a session line needs `goes: down` (the only session change verify 0.4 declares)")
        if not isinstance(s["node"], str) or not s["node"]:
            raise IntentError(f"{where}: session.node must be a node name")
        afi = s.get("afi")
        if afi is None:
            raise IntentError(f"{where}: a session line needs afi: ({' or '.join(AFI_SAFIS)}), the address family "
                              "whose routes it covers; it is checked before anything boots")
        if afi not in AFI_SAFIS:
            raise IntentError(f"{where}: session.afi must be one of {', '.join(AFI_SAFIS)}, got {afi!r}")
        nbr = _ip(where, "session.neighbor", s["neighbor"])
        vrf = _vrf(where, s.get("vrf"))
        text = f"session {s['node']} -> {nbr}{'' if vrf == 'default' else f' (vrf {vrf})'}" \
               f"{f' {afi}' if afi else ''} goes down"
        return Line(i, form, text, vrf=vrf, nodes=(s["node"],), neighbor=nbr, afi=afi, goes="down")

    if form == "config_change_on":
        # a running-config change the lab doesn't exercise (a description, a policy for routes the lab doesn't
        # carry): declared, never tested, and listed in every output (gauntlet 0.4, R4)
        nodes = raw["config_change_on"]
        if not isinstance(nodes, list) or not nodes or not all(isinstance(n, str) and n for n in nodes) \
                or len(set(nodes)) != len(nodes):
            raise IntentError(f"{where}: config_change_on must be a list of node names, each once")
        return Line(i, form, f"the running config of {', '.join(nodes)} changes (not tested where the lab doesn't "
                             "exercise it)", nodes=tuple(nodes))

    if "prefix" not in raw:
        raise IntentError(f"{where}: a {form} line needs a prefix")
    prefix = _prefix(where, raw["prefix"])
    vrf = _vrf(where, raw.get("vrf"))
    in_vrf = "" if vrf == "default" else f" (vrf {vrf})"
    if form == "appears_on":
        nodes = _nodes(where, form, raw[form])
        state = raw.get("state", "installed")
        if state not in STATES:
            raise IntentError(f"{where}: state must be one of {', '.join(STATES)}, got {state!r}")
        pins = _attrs(where, "with", raw["with"], WITH_KEYS) if "with" in raw else {}
        if state == "received" and {"protocol", "distance", "metric"} & set(pins):
            raise IntentError(f"{where}: protocol, distance and metric pin the selected route; state: received has none")
        text = f"{prefix}{in_vrf} appears on {', '.join(nodes)}" + ("" if state == "installed" else f" ({state})")
        return Line(i, form, text, prefix, vrf, nodes, state=state, pins=pins)
    if form == "disappears_from":
        nodes = _nodes(where, form, raw[form])
        incl = _bool(where, "including_received_only", raw.get("including_received_only", False))
        text = f"{prefix}{in_vrf} disappears from {', '.join(nodes)}" + (" (including received-only)" if incl else "")
        return Line(i, form, text, prefix, vrf, nodes, including_received_only=incl)
    if form == "best_path_on":
        node = raw[form]
        if not isinstance(node, str) or not node:
            raise IntentError(f"{where}: best_path_on takes one node name (one line per node)")
        if "to" not in raw:
            raise IntentError(f"{where}: best_path_on needs `to:` (the attributes that change, with their new values)")
        to = _attrs(where, "to", raw["to"], BGP_ATTRS)
        text = f"{prefix}{in_vrf} best path on {node} changes to " + ", ".join(f"{k}={_show(v)}" for k, v in to.items())
        return Line(i, form, text, prefix, vrf, (node,), to=to)
    # advertisement
    adv = raw["advertisement"]
    if not isinstance(adv, dict) or set(adv) != set(ADVERTISEMENT_KEYS) or not isinstance(adv["node"], str):
        raise IntentError(f"{where}: advertisement must be a mapping with exactly node and neighbor")
    nbr = _ip(where, "advertisement.neighbor", adv["neighbor"])
    has_goes, has_to = "goes" in raw, "to" in raw
    if has_goes == has_to:
        raise IntentError(f"{where}: an advertisement line needs exactly one of `goes: added|removed` or `to:`")
    if has_goes and raw["goes"] not in ("added", "removed"):
        raise IntentError(f"{where}: goes must be added or removed for an advertisement, got {raw['goes']!r}")
    adv_attrs = tuple(a for a in BGP_ATTRS if a != "from")
    to = _attrs(where, "to", raw["to"], adv_attrs) if has_to else {}
    if "with" in raw and raw.get("goes") != "added":
        raise IntentError(f"{where}: `with:` goes with `goes: added` only (the new advertisement's attributes)")
    pins = _attrs(where, "with", raw["with"], adv_attrs) if "with" in raw else {}
    change = raw["goes"] if has_goes else "changes to " + ", ".join(f"{k}={_show(v)}" for k, v in to.items())
    if pins:
        change += " with " + ", ".join(f"{k}={_show(v)}" for k, v in pins.items())
    text = f"{prefix}{in_vrf} advertised by {adv['node']} to {nbr}: {change}"
    return Line(i, form, text, prefix, vrf, (adv["node"],), pins=pins, to=to, neighbor=nbr, goes=raw.get("goes"))


def _show(v) -> str:
    if isinstance(v, AsPath):
        return repr(v.render())
    if isinstance(v, tuple):
        return "[" + ", ".join(map(str, v)) + "]"
    return "null" if v is None else str(v)


def _allow(i: int, raw) -> Allow:
    where = f"allow_anywhere[{i}]"
    vrf = "default"
    if isinstance(raw, dict):
        if not {"prefix"} <= set(raw) <= {"prefix", "vrf"}:
            raise IntentError(f"{where}: a mapping entry has prefix (and optional vrf)")
        vrf = _vrf(where, raw.get("vrf"))
        raw = raw["prefix"]
    if not isinstance(raw, str) or not raw.strip():
        raise IntentError(f"{where}: an entry is a prefix or a glob such as 10.200.*.0/24")
    text = raw.strip()
    if re.search(r"[?\[\]{}]", text):
        raise IntentError(f"{where}: {text!r}: the only wildcard is `*`, standing for one whole octet (or hextet)")
    if "*" not in text:
        return Allow(_prefix(where, text), vrf, False)
    return _glob(where, text, vrf)


def _glob(where: str, text: str, vrf: str) -> Allow:
    """A glob: an address with `*` for whole octets (IPv4) or hextets (IPv6) and an explicit prefix length.
    The wildcards may only stand past the first 16 bits (IPv4) or 48 bits (IPv6), and inside the length."""
    hint = "e.g. 10.200.*.0/24 or 2001:db8:1:*::/64"
    m = re.fullmatch(r"([0-9A-Fa-f:.*]+)/([0-9]{1,3})", text)
    if not m:
        raise IntentError(f"{where}: glob {text!r} needs an explicit numeric prefix length ({hint})")
    addr, length = m.group(1), int(m.group(2))
    if ":" not in addr:
        version, bits, parts = 4, 8, addr.split(".")
        ok = len(parts) == 4 and all(p == "*" or re.fullmatch(r"[0-9]{1,3}", p) and int(p) <= 255 for p in parts)
    else:
        version, bits = 6, 16
        if addr.count("::") > 1:
            raise IntentError(f"{where}: glob {text!r}: `::` appears twice")
        if "::" in addr:
            left, right = addr.split("::")
            lp, rp = (left.split(":") if left else []), (right.split(":") if right else [])
            parts = lp + ["0"] * (8 - len(lp) - len(rp)) + rp if len(lp) + len(rp) < 8 else []
        else:
            parts = addr.split(":")
        ok = len(parts) == 8 and all(p == "*" or re.fullmatch(r"[0-9A-Fa-f]{1,4}", p) for p in parts)
    if not ok:
        raise IntentError(f"{where}: glob {text!r} is malformed: `*` stands for one whole octet (hextet) ({hint})")
    if length > (32 if version == 4 else 128):
        raise IntentError(f"{where}: glob {text!r}: prefix length /{length} is too long")
    wild = [i for i, p in enumerate(parts) if p == "*"]
    for i in wild:
        if i * bits < GLOB_REACH[version]:
            raise IntentError(f"{where}: glob {text!r} reaches wider than /{GLOB_REACH[version]}: write the first "
                              f"{GLOB_REACH[version] // bits} {'octets' if version == 4 else 'hextets'} literally "
                              f"({hint})")
        if i * bits >= length:
            raise IntentError(f"{where}: glob {text!r}: a `*` past the prefix length /{length} matches nothing")
    groups = tuple(None if p == "*" else int(p, 10 if version == 4 else 16) for p in parts)
    filled = ".".join(str(g or 0) for g in groups) if version == 4 else ":".join(f"{g or 0:x}" for g in groups)
    try:
        ipaddress.ip_network(f"{filled}/{length}", strict=True)
    except ValueError:
        raise IntentError(f"{where}: glob {text!r} has host bits set past /{length}") from None
    return Allow(text, vrf, True, version, groups, length)


def _identity(ln: Line) -> list[tuple]:
    """What a line is about, for refusing two lines on the same thing."""
    if ln.form == "session":
        return [("session", ln.node, ln.vrf, ln.neighbor, ln.afi)]
    if ln.form == "advertisement":
        return [("advertisement", ln.node, ln.vrf, ln.prefix, ln.neighbor)]
    if ln.form == "config_change_on":
        return [("config", n) for n in ln.nodes]
    return [("route", n, ln.vrf, ln.prefix) for n in ln.nodes]


def parse_intent(data, source: str = "<intent>") -> Intent:
    if not isinstance(data, dict):
        raise IntentError(f"{source}: an intent file is a mapping with `intent:` (a list, [] for none)")
    unknown = sorted(set(map(str, data)) - set(TOP_KEYS))
    if unknown:
        raise IntentError(f"{source}: unknown top-level key(s) {', '.join(unknown)}; allowed: {', '.join(TOP_KEYS)}")
    if "intent" not in data:
        raise IntentError(f"{source}: missing `intent:` (write `intent: []` to declare that nothing changes)")
    raw_lines = data["intent"]
    if raw_lines is None or not isinstance(raw_lines, list):
        raise IntentError(f"{source}: intent must be a list ([] for none)")
    lines = [_line(i, raw) for i, raw in enumerate(raw_lines)]
    raw_allow = data.get("allow_anywhere", [])
    if not isinstance(raw_allow, list):
        raise IntentError(f"{source}: allow_anywhere must be a list of prefixes or globs")
    allow = [_allow(i, a) for i, a in enumerate(raw_allow)]
    seen: dict[tuple, int] = {}
    for ln in lines:
        for ident in _identity(ln):
            # a route on a node may be the subject of one appears/disappears/best-path line only; a session
            # of one line per address family (or one line for all of them)
            if ident[0] == "session":
                clash = [k for k in seen if k[:4] == ident[:4] and (k[4] is None or ident[4] is None or k[4] == ident[4])]
            else:
                clash = [ident] if ident in seen else []
            if clash:
                raise IntentError(f"{_where(ln.index)}: about the same {ident[0]} as intent[{seen[clash[0]]}] "
                                  f"({', '.join(str(x) for x in ident[1:] if x)}); merge them into one line")
            seen[ident] = ln.index
    patterns = [(a.pattern, a.vrf) for a in allow]
    if len(set(patterns)) != len(patterns):
        raise IntentError(f"{source}: allow_anywhere lists an entry twice")
    echo = {"intent": raw_lines, "allow_anywhere": raw_allow}
    return Intent(lines, allow, source, echo)


def load_intent(path) -> Intent:
    from pathlib import Path

    p = Path(path)
    try:
        text = p.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as e:
        raise IntentError(f"{p}: cannot read the intent file: {e}") from None
    return parse_intent_text(text, str(p))


def parse_intent_text(text: str, source: str = "<intent>") -> Intent:
    """An intent given as YAML (or JSON) text rather than a file: the same validation as a file."""
    try:
        data = load_yaml(text, source)
    except ConfigError as e:
        raise IntentError(str(e)) from None
    return parse_intent(data, source)


def check_nodes(intent: Intent, nodes: dict[str, str]) -> None:
    """Every node the intent names must be in the topology and observed. `nodes` maps every topology node
    to its driver, or to "" for a node verify doesn't snapshot (a bridge, a host you named unobserved)."""
    for ln in intent.lines:
        for n in ln.nodes:
            if n not in nodes:
                raise IntentError(f"{_where(ln.index)}: unknown node {n!r}; the topology has {', '.join(sorted(nodes))}")
            if not nodes[n]:
                raise IntentError(f"{_where(ln.index)}: node {n!r} is not observed by verify (no routing driver), "
                                  "so nothing can be declared about it")
