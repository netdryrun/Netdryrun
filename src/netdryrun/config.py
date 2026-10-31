"""Load and validate netdryrun.yml."""
from __future__ import annotations

import difflib
import ipaddress
import math
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from .faults import parse_inject

CHECK_TYPES = {
    "bgp_session": {"required": ("node", "neighbor"), "optional": ("state", "vrf")},
    "bgp_prefixes": {"required": ("node", "neighbor"), "optional": ("min", "max", "exact", "afi", "vrf")},
    "route": {"required": ("node", "prefix"), "optional": ("present", "protocol", "vrf", "active")},
    "bgp_route": {"required": ("node", "prefix"), "optional": ("present", "vrf", "communities", "without_communities",
                                                              "as_path", "as_path_regex", "local_pref", "med", "next_hop")},
    "ping": {"required": ("node", "target"), "optional": ("source", "expect", "vrf", "count", "min_replies")},
}
BGP_ATTRIBUTES = ("communities", "without_communities", "as_path", "as_path_regex", "local_pref", "med", "next_hop")
COMMON_KEYS = ("type", "name", "timeout", "hold")
BGP_STATES = ("idle", "connect", "active", "opensent", "openconfirm", "established", "down")  # down = any state except established
# Names that end up inside device CLI strings (vtysh -c, sr_cli, Cli -c) or command arguments: letters,
# digits and . _ : - only, so a name can never carry a newline, a pipe or a second command
VRF_NAME = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_.:-]{0,63}")
INTERFACE_NAME = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_.@-]{0,14}")   # Linux: at most 15 characters, no / or :

TOP_LEVEL_KEYS = ("lab", "timeout", "checks", "nodes", "scenarios")
NODE_KEYS = ("driver", "setup")
DRIVER_NAMES = ("frr", "srlinux", "eos", "sonic", "junos", "nxos")   # must match drivers.DRIVERS (a test keeps them in sync)
SCENARIO_KEYS = ("name", "link_down", "node_isolated", "inject_routes", "checks")
LINK_DOWN_KEYS = ("node", "interface")
INJECT_KEYS = ("node", "prefixes", "count", "from", "as_path")
# Address families the drivers report prefix counts for. Anything else would read as 0 prefixes,
# which silently satisfies max and exact, so it is refused at load time.
AFIS = ("ipv4-unicast", "ipv6-unicast", "evpn")
AFI_HINTS = {"ipv4": "ipv4-unicast", "v4": "ipv4-unicast", "ipv4_unicast": "ipv4-unicast",
             "ipv4unicast": "ipv4-unicast", "ipv6": "ipv6-unicast", "v6": "ipv6-unicast",
             "ipv6_unicast": "ipv6-unicast", "ipv6unicast": "ipv6-unicast",
             "l2vpn-evpn": "evpn", "l2vpn_evpn": "evpn", "l2vpnevpn": "evpn"}
# Route protocols as the drivers report them after normalization (FRR's zebra names; SR Linux and EOS
# names are mapped onto these, see the protocol-names table in the docs). A name outside this set
# would match nothing, which silently satisfies present: false, so it is refused at load time.
PROTOCOLS = ("bgp", "connected", "local", "static", "kernel", "ospf", "ospf6", "isis", "rip", "ripng", "aggregate",
             "eigrp", "babel", "nhrp", "table", "sharp", "pbr", "openfabric", "bgp-evpn", "bgp-vpn", "dhcp", "arp-nd",
             "gribi")
PROTOCOL_HINTS = {"ebgp": "bgp", "ibgp": "bgp",
                  "bgp4": "bgp", "direct": "connected", "attached": "connected", "host": "local",
                  "ospfv2": "ospf", "ospfv3": "ospf6", "is-is": "isis", "static-route": "static"}
MAX_SECONDS = 86400.0
MAX_PING_COUNT = 1000
UINT32 = 0xFFFFFFFF


class ConfigError(ValueError):
    pass


# Well-known communities (RFC 1997, 3765, 7611, 7999, 8326, 8642, 9494) by the name most CLIs print
WELL_KNOWN_COMMUNITIES = {
    "graceful-shutdown": "65535:0", "accept-own": "65535:1", "llgr-stale": "65535:6", "no-llgr": "65535:7",
    "blackhole": "65535:666", "no-export": "65535:65281", "no-advertise": "65535:65282",
    "no-export-subconfed": "65535:65283", "local-as": "65535:65283", "no-peer": "65535:65284",
}
_COMMUNITY_NAMES = {v: k for k, v in WELL_KNOWN_COMMUNITIES.items() if k != "local-as"}


def parse_community(text: str) -> str:
    """Canonical form of a standard (`65000:100`), large (`65000:1:2`) or well-known (`no-export`)
    community: numbers without leading zeros, well-known names as their 65535:x value."""
    t = str(text).strip().lower().replace("_", "-")
    if t in WELL_KNOWN_COMMUNITIES:
        return WELL_KNOWN_COMMUNITIES[t]
    parts = t.split(":")
    if len(parts) in (2, 3) and all(x.isdigit() for x in parts):
        nums = [int(x) for x in parts]
        limit = 0xFFFF if len(parts) == 2 else 0xFFFFFFFF
        if all(n <= limit for n in nums):
            return ":".join(str(n) for n in nums)
    raise ValueError(f"bad community {text!r}: use 65000:100 (standard), 65000:1:2 (large) or a well-known name "
                     f"({', '.join(sorted(WELL_KNOWN_COMMUNITIES))})")


def community_name(canonical: str) -> str:
    """How a canonical community is shown in reports: well-known ones by name."""
    return _COMMUNITY_NAMES.get(canonical, canonical)


def normalize_as_path(value: Any) -> str:
    """An AS path as space-separated ASNs; AS sets as {a,b}. "" is the empty path (a locally originated route)."""
    if isinstance(value, bool):
        raise ValueError("as_path must be a string such as '65002 65003'")
    if isinstance(value, int):
        return str(value)
    if isinstance(value, list):
        return " ".join(str(normalize_as_path(v)) for v in value)
    text = re.sub(r"\s*,\s*", ",", str(value).strip())
    tokens = text.split()
    if not all(re.fullmatch(r"\d+|\{\d+(,\d+)*\}|\(\d+|\d+\)|\(\d+\)", t) for t in tokens):
        raise ValueError(f"bad as_path {value!r}: use ASNs separated by spaces, for example '65002 65003'")
    return " ".join(tokens)


@dataclass
class Check:
    type: str
    params: dict[str, Any]
    name: str
    timeout: float
    hold: float | None = None  # per-check hold window for post-convergence checks

    @property
    def node(self) -> str:
        return self.params["node"]


@dataclass
class Config:
    path: Path
    lab: Path
    timeout: float
    checks: list[Check]
    drivers: dict[str, str] = field(default_factory=dict)  # node -> driver override
    scenarios: list["Scenario"] = field(default_factory=list)
    setup: dict[str, list[str]] = field(default_factory=dict)   # node -> commands run after deploy


@dataclass
class Fault:
    kind: str          # "link_down", "node_isolated" or "inject_routes"
    node: str
    interface: str | None = None
    prefixes: list[str] = field(default_factory=list)   # inject_routes
    as_path: list[int] = field(default_factory=list)    # inject_routes: ASNs prepended to the injected routes

    def describe(self) -> str:
        if self.kind == "inject_routes":
            return f"{self.node} injects {len(self.prefixes)} route(s)"
        return f"{self.node} {self.interface} down" if self.kind == "link_down" else f"{self.node} isolated"


@dataclass
class Scenario:
    name: str
    faults: list[Fault]
    checks: list[Check]


def _describe(ctype: str, p: dict[str, Any]) -> str:
    if ctype == "bgp_session":
        return f"{p['node']}: BGP session to {p['neighbor']} is {p.get('state', 'established')}"
    if ctype == "bgp_prefixes":
        rng = []
        if "exact" in p:
            rng.append(f"= {p['exact']}")
        if "min" in p:
            rng.append(f">= {p['min']}")
        if "max" in p:
            rng.append(f"<= {p['max']}")
        return f"{p['node']}: prefixes from {p['neighbor']} {' and '.join(rng) or 'counted'}"
    if ctype == "route":
        verb = "absent" if p.get("present", True) is False else "present"
        via = f" via {p['protocol']}" if p.get("protocol") else ""
        return f"{p['node']}: route {p['prefix']}{via} is {verb}"
    if ctype == "bgp_route":
        if p.get("present", True) is False:
            return f"{p['node']}: no BGP path for {p['prefix']}"
        parts = []
        if p.get("communities"):
            parts.append("communities " + " ".join(community_name(c) for c in p["communities"]))
        if p.get("without_communities"):
            parts.append("no communities " + " ".join(community_name(c) for c in p["without_communities"]))
        if "as_path" in p:
            parts.append(f"as-path '{p['as_path']}'")
        if "as_path_regex" in p:
            parts.append(f"as-path matching /{p['as_path_regex']}/")
        for key, label in (("local_pref", "local-pref"), ("med", "MED"), ("next_hop", "next hop")):
            if key in p:
                parts.append(f"{label} {p[key]}")
        return f"{p['node']}: BGP best path for {p['prefix']} " + (f"has {', '.join(parts)}" if parts else "exists")
    if ctype == "ping":
        exp = p.get("expect", "success")
        src = f" from {p['source']}" if p.get("source") else ""
        return f"{p['node']}: ping {p['target']}{src} expects {exp}"
    return ctype


def _suggest(word: Any, choices: Any, hints: dict[str, str] | None = None) -> str:
    """ "; did you mean 'x'?" for a misspelled key or value, or "" when nothing is close."""
    if not isinstance(word, str):
        return ""
    low = word.lower()
    if hints and low in hints:
        return f"; did you mean {hints[low]!r}?"
    close = difflib.get_close_matches(low, [str(c) for c in choices], n=1, cutoff=0.6)
    return f"; did you mean {close[0]!r}?" if close else ""


def _reject_unknown(where: str, raw: dict, allowed: Any, what: str = "key", context: str = "") -> None:
    unknown = [k for k in raw if k not in allowed]
    if unknown:
        hints = "".join(_suggest(k, allowed).replace("; did you mean", f"; for {k!r} did you mean")
                        for k in unknown) if len(unknown) > 1 else _suggest(unknown[0], allowed)
        raise ConfigError(f"{where}: unknown {what}s {[str(k) for k in unknown]}{context}{hints}; "
                          f"allowed: {', '.join(sorted(allowed))}")


def _is_int(v: Any) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


def _is_number(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def _seconds(where: str, key: str, v: Any) -> float:
    if not _is_number(v) or not 0 < v <= MAX_SECONDS:
        raise ConfigError(f"{where}: {key} must be a positive number of seconds (at most {int(MAX_SECONDS)}), "
                          f"got {v!r}")
    return float(v)


def _string(where: str, key: str, v: Any) -> str:
    if not isinstance(v, str) or not v.strip():
        raise ConfigError(f"{where}: {key} must be a non-empty string, got {v!r}")
    return v


def _bool(where: str, key: str, v: Any) -> bool:
    # A quoted "false", 0, null or '' must never silently flip a check's meaning
    if not isinstance(v, bool):
        raise ConfigError(f"{where}: {key} must be true or false (unquoted), got {v!r}")
    return v


def _check_where(prefix: str, i: int, raw: Any) -> str:
    where = f"{prefix}[{i}]"
    if isinstance(raw, dict) and isinstance(raw.get("name"), str) and raw["name"].strip():
        where += f" ({raw['name']!r})"
    return where


def _validate_check(i: int, raw: Any, default_timeout: float, prefix: str = "checks") -> Check:
    where = _check_where(prefix, i, raw)
    if not isinstance(raw, dict):
        raise ConfigError(f"{where}: must be a mapping (type: ..., node: ...), got {raw!r}")
    ctype = raw.get("type")
    if not isinstance(ctype, str) or ctype not in CHECK_TYPES:
        raise ConfigError(f"{where}: unknown type {ctype!r}{_suggest(ctype, CHECK_TYPES)}; "
                          f"expected one of {sorted(CHECK_TYPES)}")
    spec = CHECK_TYPES[ctype]
    allowed = set(spec["required"]) | set(spec["optional"]) | set(COMMON_KEYS)
    _reject_unknown(where, raw, allowed, context=f" for type {ctype}")
    for key in spec["required"]:
        if key not in raw:
            raise ConfigError(f"{where}: missing required key {key!r}")
    if "name" in raw:
        _string(where, "name", raw["name"])
    params = {k: v for k, v in raw.items() if k not in COMMON_KEYS}
    _string(where, "node", params["node"])
    for key in ("prefix", "neighbor", "target", "source", "next_hop"):
        if key in params and not isinstance(params[key], str):
            raise ConfigError(f"{where}: {key} must be an IP {'prefix' if key == 'prefix' else 'address'} "
                              f"written as a string, got {params[key]!r}")
    for key in ("neighbor", "target", "source", "next_hop"):
        # ipaddress accepts any text after % (spaces, newlines), and the address reaches device CLI commands
        if key in params and "%" in params[key] and not INTERFACE_NAME.fullmatch(params[key].split("%", 1)[1]):
            raise ConfigError(f"{where}: {key} {params[key]!r}: an IPv6 scope (after %) must be an interface name")
    try:
        # canonical spellings so 2001:db8:0::1 in YAML matches 2001:db8::1 on the device
        if ctype in ("route", "bgp_route"):
            params["prefix"] = str(ipaddress.ip_network(params["prefix"], strict=False))
        for key in ("neighbor", "target", "source", "next_hop"):
            if key in params:
                params[key] = str(ipaddress.ip_address(params[key]))
    except ValueError as e:
        raise ConfigError(f"{where}: {e}") from None
    if "next_hop" in params and ipaddress.ip_address(params["next_hop"].split("%")[0]).is_link_local:
        # devices report a link-local next hop without its interface, and two sessions can share one (fe80::1 on
        # eth1 and on eth2): a path through either would match, so the check can't say which one it tests
        raise ConfigError(f"{where}: next_hop {params['next_hop']!r} is link-local: it names no interface, and two "
                          "sessions can share it, so Netdryrun can't tell which path it is. Check a global next hop, "
                          "or the path's AS path or communities")
    for key in ("min", "max", "exact", "local_pref", "med"):
        if key in params and (not _is_int(params[key]) or params[key] < 0):
            raise ConfigError(f"{where}: {key} must be a non-negative integer, got {params[key]!r}")
    for key in ("local_pref", "med"):
        if key in params and params[key] > UINT32:
            raise ConfigError(f"{where}: {key} must be at most {UINT32}")
    if "exact" in params and ({"min", "max"} & set(params)):
        raise ConfigError(f"{where}: use exact on its own, or min/max, not both")
    if params.get("min", 0) > params.get("max", float("inf")):
        raise ConfigError(f"{where}: min is greater than max")
    for key in ("present", "active"):
        if key in params:
            _bool(where, key, params[key])
    if "vrf" in params:
        v = params["vrf"]
        if isinstance(v, bool) or not isinstance(v, (str, int)):
            raise ConfigError(f"{where}: vrf must be a VRF name, got {v!r}")
        params["vrf"] = str(v)
        if not VRF_NAME.fullmatch(params["vrf"]):
            raise ConfigError(f"{where}: bad vrf {params['vrf']!r}: use letters, digits and . _ : - (at most 64)")
        if params["vrf"].lower() == "all":
            # devices answer "vrf all" keyed by each VRF's name, which the drivers read as "no routes"
            raise ConfigError(f"{where}: vrf 'all' is not supported: name one VRF per check")
    if ctype == "bgp_session":
        state = params.get("state", "established")
        if not isinstance(state, str) or state.lower() not in BGP_STATES:
            raise ConfigError(f"{where}: state must be one of {', '.join(BGP_STATES)}, got {state!r}"
                              f"{_suggest(state, BGP_STATES)}")
        params["state"] = state.lower()
    if ctype == "bgp_prefixes":
        bounds = {"min", "max", "exact"} & set(params)
        if not bounds:
            raise ConfigError(f"{where}: bgp_prefixes needs at least one of min, max or exact")
        if bounds == {"min"} and params["min"] == 0:
            raise ConfigError(f"{where}: min: 0 on its own always passes; use min: 1 or more, or add max")
        if "afi" in params:
            afi = params["afi"]
            if not isinstance(afi, str) or afi.lower() not in AFIS:
                raise ConfigError(f"{where}: afi must be one of {', '.join(AFIS)}, got {afi!r}"
                                  f"{_suggest(afi, AFIS, AFI_HINTS)}")
            params["afi"] = afi.lower()
    if ctype == "route":
        if "protocol" in params:
            proto = params["protocol"]
            if not isinstance(proto, str) or proto.lower() not in PROTOCOLS:
                why = (" (drivers report eBGP and iBGP routes alike as bgp)"
                       if isinstance(proto, str) and proto.lower() in ("ebgp", "ibgp") else "")
                raise ConfigError(f"{where}: protocol {proto!r} is not a protocol name the drivers report"
                                  f"{_suggest(proto, PROTOCOLS, PROTOCOL_HINTS)}{why}; "
                                  f"use one of {', '.join(PROTOCOLS)}")
            params["protocol"] = proto.lower()
        if params.get("present", True) is False and "active" in params:
            raise ConfigError(f"{where}: active only applies to present: true (present: false already "
                              "means no matching route at all, selected or not)")
    if ctype == "ping":
        expect = params.get("expect", "success")
        if not isinstance(expect, str) or expect.lower() not in ("success", "failure"):
            raise ConfigError(f"{where}: expect must be 'success' or 'failure', got {expect!r}"
                              f"{_suggest(expect, ('success', 'failure'))}")
        params["expect"] = expect.lower()
        if "count" in params and (not _is_int(params["count"]) or not 1 <= params["count"] <= MAX_PING_COUNT):
            raise ConfigError(f"{where}: count must be an integer from 1 to {MAX_PING_COUNT}, got {params['count']!r}")
        if "min_replies" in params:
            if params["expect"] == "failure":
                raise ConfigError(f"{where}: min_replies only applies to expect: success "
                                  "(expect: failure passes only with 0 replies)")
            count = params.get("count", 3)
            if not _is_int(params["min_replies"]) or not 1 <= params["min_replies"] <= count:
                raise ConfigError(f"{where}: min_replies must be an integer from 1 to count ({count}), "
                                  f"got {params['min_replies']!r}")
    if ctype == "bgp_route":
        _validate_bgp_route(where, params)
    timeout = _seconds(where, "timeout", raw["timeout"]) if "timeout" in raw else default_timeout
    hold = _seconds(where, "hold", raw["hold"]) if "hold" in raw else None
    check = Check(type=ctype, params=params, name=raw.get("name") or _describe(ctype, params), timeout=timeout,
                  hold=hold)
    if hold is not None:
        from .checks import is_post_convergence   # checks imports this module
        if not is_post_convergence(check):
            raise ConfigError(f"{where}: hold only applies to post-convergence checks (present: false, "
                              "a bgp_route attribute, expect: failure, a state other than established, max "
                              "or exact); this check passes after 2 consecutive passing samples, so hold would be "
                              "ignored")
    return check


def _validate_bgp_route(where: str, params: dict[str, Any]) -> None:
    attrs = [k for k in BGP_ATTRIBUTES if k in params]
    if params.get("present", True) is False and attrs:
        raise ConfigError(f"{where}: present: false means no BGP path at all, so it can't be combined with "
                          f"{', '.join(attrs)}; to forbid a community on the best path use without_communities")
    for key in ("communities", "without_communities"):
        if key not in params:
            continue
        raw = params[key] if isinstance(params[key], list) else [params[key]]
        if not raw:
            raise ConfigError(f"{where}: {key} must list at least one community")
        for c in raw:
            if isinstance(c, (int, float)) and not isinstance(c, bool):
                # YAML 1.1 reads 65000:10 (and 65000:1:2) unquoted as a base-60 number
                raise ConfigError(f"{where}: {key}: write communities as quoted strings, for example '65000:10'; "
                                  "YAML reads some unquoted values like 65000:10 as numbers")
            if not isinstance(c, str):
                raise ConfigError(f"{where}: {key}: bad community {c!r}: write it as a quoted string")
        try:
            params[key] = [parse_community(c) for c in raw]
        except ValueError as e:
            raise ConfigError(f"{where}: {key}: {e}") from None
    both = set(params.get("communities", [])) & set(params.get("without_communities", []))
    if both:
        raise ConfigError(f"{where}: {', '.join(sorted(both))} is in both communities and without_communities")
    if "as_path" in params:
        v = params["as_path"]
        if v is None or isinstance(v, (float, dict)) or (isinstance(v, list) and not v):
            raise ConfigError(f"{where}: as_path must be a string such as '65002 65003' (\"\" for the empty path), "
                              f"got {v!r}")
        try:
            params["as_path"] = normalize_as_path(v)
        except ValueError as e:
            raise ConfigError(f"{where}: {e}") from None
    if "as_path_regex" in params:
        v = params["as_path_regex"]
        if not isinstance(v, str) or not v:
            raise ConfigError(f"{where}: as_path_regex must be a non-empty regular expression string, got {v!r}")
        try:
            re.compile(v)
        except re.error as e:
            raise ConfigError(f"{where}: as_path_regex is not a valid regular expression: {e}") from None


class _StrictLoader(yaml.SafeLoader):
    """SafeLoader that refuses duplicate mapping keys. PyYAML keeps the last one silently, so a second
    `checks:` block (or `present: true` ... `present: false`) would drop the first without a word."""

    def construct_mapping(self, node, deep=False):
        if isinstance(node, yaml.MappingNode):
            seen: dict[Any, int] = {}
            for key_node, _ in node.value:
                if key_node.tag == "tag:yaml.org,2002:merge":
                    continue   # `<<: *anchor` merges are allowed, and explicit keys override them
                key = self.construct_object(key_node, deep=True)
                try:
                    first = seen.get(key)
                except TypeError:
                    continue   # unhashable key: SafeLoader reports it
                if first is not None:
                    raise yaml.constructor.ConstructorError(
                        "while reading a mapping", node.start_mark,
                        f"duplicate key {key!r} (first defined on line {first + 1})", key_node.start_mark)
                seen[key] = key_node.start_mark.line
        return super().construct_mapping(node, deep=deep)


def load_yaml(text: str, source: str = "<yaml>") -> Any:
    """Parse YAML strictly (duplicate keys are an error); any YAML error becomes a ConfigError."""
    try:
        return yaml.load(text, Loader=_StrictLoader)  # a SafeLoader subclass: no arbitrary objects
    except yaml.YAMLError as e:
        # one line, with the position: PyYAML's own message spans several lines with a caret drawing
        mark = getattr(e, "problem_mark", None)
        where = f" at line {mark.line + 1}, column {mark.column + 1}" if mark is not None else ""
        problem = getattr(e, "problem", None) or str(e).splitlines()[0]
        raise ConfigError(f"{source}: not valid YAML{where}: {' '.join(str(problem).split())}") from None


def load(path: str | Path) -> Config:
    path = Path(path)
    if path.is_dir():
        path = path / "netdryrun.yml"
    if not path.exists():
        raise ConfigError(f"{path}: not found")
    data = load_yaml(path.read_text(encoding="utf-8"), str(path))
    if data is None:
        data = {}
    if not isinstance(data, dict):
        raise ConfigError(f"{path}: top level must be a mapping")
    _reject_unknown(str(path), data, TOP_LEVEL_KEYS, "top-level key")
    if "lab" not in data:
        raise ConfigError(f"{path}: missing 'lab' (path to the containerlab topology file)")
    _string(str(path), "lab", data["lab"])
    lab = (path.parent / data["lab"]).resolve()
    if not lab.is_file():
        raise ConfigError(f"{path}: lab file {lab} not found")
    timeout = _seconds(str(path), "timeout", data["timeout"]) if "timeout" in data else 120.0
    raw_checks = data.get("checks")
    if not raw_checks:
        raise ConfigError(f"{path}: no checks defined")
    if not isinstance(raw_checks, list):
        raise ConfigError(f"{path}: checks must be a list of checks")
    checks = [_validate_check(i, c, timeout) for i, c in enumerate(raw_checks)]
    drivers, setup = _validate_nodes(str(path), data)
    scenarios: list[Scenario] = []
    if "scenarios" in data:
        if not isinstance(data["scenarios"], list) or not data["scenarios"]:
            raise ConfigError(f"{path}: scenarios must be a non-empty list of scenarios (or leave the key out)")
        scenarios = [_validate_scenario(i, sc, timeout) for i, sc in enumerate(data["scenarios"])]
    return Config(path=path, lab=lab, timeout=timeout, checks=checks, drivers=drivers, scenarios=scenarios, setup=setup)


def _validate_nodes(where: str, data: dict) -> tuple[dict[str, str], dict[str, list[str]]]:
    drivers: dict[str, str] = {}
    setup: dict[str, list[str]] = {}
    if "nodes" not in data:
        return drivers, setup
    nodes_cfg = data["nodes"]
    if not isinstance(nodes_cfg, dict) or not nodes_cfg:
        raise ConfigError(f"{where}: nodes must be a mapping of node name to settings (or leave the key out)")
    for k, v in nodes_cfg.items():
        node_where = f"{where}: nodes.{k}"
        if not isinstance(k, str) or not k.strip():
            raise ConfigError(f"{node_where}: node names must be strings")
        if not isinstance(v, dict) or not v:
            raise ConfigError(f"{node_where}: must be a mapping with driver and/or setup, got {v!r}")
        _reject_unknown(node_where, v, NODE_KEYS)
        if "driver" in v:
            if v["driver"] not in DRIVER_NAMES:
                raise ConfigError(f"{node_where}.driver: unknown driver {v['driver']!r}"
                                  f"{_suggest(v['driver'], DRIVER_NAMES)}; use one of {', '.join(DRIVER_NAMES)}")
            drivers[k] = v["driver"]
        if "setup" in v:
            cmds = v["setup"] if isinstance(v["setup"], list) else [v["setup"]]
            if not cmds or not all(isinstance(x, str) and x.strip() for x in cmds):
                raise ConfigError(f"{node_where}.setup must be a list of shell commands")
            setup[k] = cmds
    return drivers, setup


def _validate_scenario(i: int, raw: Any, default_timeout: float) -> Scenario:
    where = _check_where("scenarios", i, raw)
    if not isinstance(raw, dict):
        raise ConfigError(f"{where}: must be a mapping")
    _reject_unknown(where, raw, SCENARIO_KEYS)
    if "name" in raw:
        _string(where, "name", raw["name"])
    for key in ("link_down", "node_isolated", "inject_routes"):
        if key in raw and raw[key] in (None, "", [], {}):
            raise ConfigError(f"{where}: {key} is empty")
    faults = []
    for item in _as_list(raw.get("link_down")):
        if not isinstance(item, dict):
            raise ConfigError(f"{where}: link_down needs node and interface, got {item!r}")
        _reject_unknown(f"{where}: link_down", item, LINK_DOWN_KEYS)
        if not {"node", "interface"} <= set(item):
            raise ConfigError(f"{where}: link_down needs node and interface")
        _string(f"{where}: link_down", "node", item["node"])
        if not isinstance(item["interface"], str) or not INTERFACE_NAME.fullmatch(item["interface"]):
            raise ConfigError(f"{where}: bad interface {item['interface']!r}: use a Linux interface name such as eth1")
        faults.append(Fault("link_down", item["node"], item["interface"]))
    for item in _as_list(raw.get("node_isolated")):
        if isinstance(item, dict):
            _reject_unknown(f"{where}: node_isolated", item, ("node",))
            node = item.get("node")
        else:
            node = item
        if not isinstance(node, str) or not node.strip():
            raise ConfigError(f"{where}: node_isolated needs a node name, got {node!r}")
        faults.append(Fault("node_isolated", node))
    for item in _as_list(raw.get("inject_routes")):
        if isinstance(item, dict):
            _reject_unknown(f"{where}: inject_routes", item, INJECT_KEYS)
            if "node" in item:
                _string(f"{where}: inject_routes", "node", item["node"])
            # parse_inject reads these with str(), so a bare 1 would become the prefix 0.0.0.1/32
            if "from" in item:
                _string(f"{where}: inject_routes", "from", item["from"])
            if "prefixes" in item:
                pfx = item["prefixes"] if isinstance(item["prefixes"], list) else [item["prefixes"]]
                if not pfx or not all(isinstance(x, str) and x.strip() for x in pfx):
                    raise ConfigError(f"{where}: inject_routes prefixes must be a prefix or a list of prefixes "
                                      f"written as strings, got {item['prefixes']!r}")
            if "as_path" in item and item["as_path"] in (None, "", [], {}):
                raise ConfigError(f"{where}: inject_routes as_path is empty")
        try:
            inj = parse_inject(where, item)
        except ValueError as e:
            raise ConfigError(str(e)) from None
        faults.append(Fault("inject_routes", inj["node"], prefixes=inj["prefixes"], as_path=inj["as_path"]))
    if not faults:
        raise ConfigError(f"{where}: define at least one fault (link_down, node_isolated or inject_routes)")
    raw_checks = raw.get("checks")
    if not raw_checks:
        raise ConfigError(f"{where}: no checks defined")
    if not isinstance(raw_checks, list):
        raise ConfigError(f"{where}: checks must be a list of checks")
    name = str(raw.get("name") or ", ".join(f.describe() for f in faults))
    checks = [_validate_check(j, c, default_timeout, prefix=f"scenarios[{i}].checks") for j, c in enumerate(raw_checks)]
    for c in checks:
        c.name = f"[{name}] {c.name}"
    return Scenario(name=name, faults=faults, checks=checks)


def _as_list(v: Any) -> list:
    if v is None:
        return []
    return v if isinstance(v, list) else [v]
