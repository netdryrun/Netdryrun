"""Juniper cJunosEvolved driver (beta): Junos CLI `| display json`, read through the container's VM.

The cJunosEvolved container runs Junos in a VM. Its own `cli -c` ignores the command and opens an
interactive CLI, so commands go over the container's internal SSH hop to the VM, as the container's
`cli` wrapper does: `ssh root@176.1.1.1 "cli -c '<command> | display json | no-more'"`.

Junos answers every command with exit code 0, errors included (`error: syntax error ...` as text).
Output that isn't the JSON document a parser knows is an error, never "nothing":

- An unknown routing table is an explicit `route-table-error`. An instance that exists without that
  table (no IPv6 in a VRF) has no routes there; one that doesn't exist raises NoSuchInstance.
- An unknown BGP instance answers exactly like one without peers, so an empty neighbor list in a VRF
  is trusted only after `show route instance <vrf>` confirms the instance.
- Routes are read with `all`, which includes hidden routes. A hidden BGP route rejected by import policy
  is filtered: Junos keeps it for `show route ... hidden` only, and it can never be used (FRR and EOS
  don't keep it at all). A hidden BGP route for any other reason (an unusable next hop) was received and
  is kept: it counts as present but not selected, like an invalid path on FRR, EOS and SR Linux.

Netdryrun's `default` VRF is the Junos `master` instance (tables `inet.0`, `inet6.0`); a VRF `X` is the
routing-instance `X` (tables `X.inet.0`, `X.inet6.0`).
"""
from __future__ import annotations

import ipaddress
import re

from .base import (BgpNeighbor, BgpPath, Driver, DriverError, NoSuchInstance, Observation, Route, as_int, canon_communities,
                   RepeatedKey, check_vrf_name, load_json, parser, render_as_path, unexpected)
from .frr import _canon_addr

# The container's own SSH hop to the Junos VM (its `cli` wrapper uses the same key and address)
VM_SSH = ["ssh", "-q", "-i", "/root/.ssh/sshkey", "-o", "StrictHostKeyChecking=no", "-o", "BatchMode=yes",
          "root@176.1.1.1"]

# Junos protocol-name -> the shared vocabulary used in netdryrun.yml (FRR's names)
PROTOCOLS = {"bgp": "bgp", "direct": "connected", "local": "local", "static": "static", "aggregate": "aggregate",
             "ospf": "ospf", "ospf3": "ospf6", "is-is": "isis", "rip": "rip", "ripng": "ripng"}

NEIGHBORS_CMD = "show bgp neighbor instance <instance>"
ROUTE_CMD = "show route <prefix> exact table <table> all extensive"
HIDDEN_CMD = "show route receive-protocol bgp <peer> table <table> hidden extensive"
ALL_ROUTES_CMD = "show route table <table>"
INSTANCE_CMD = "show route instance <instance>"
PING_CMD = "ping <target> count <n> rapid"

# The one hidden reason that means "filtered on the way in": a route that was never accepted
REJECTED = "rejected by import policy"
# Hidden reasons that mean "received, but its next hop can't be used": FRR, SR Linux and EOS count such a route as
# received (live capture, interop IOP-7). A prefix count is exact only when every hidden route has one of these
# reasons or REJECTED; any other reason (a loop, a martian, ...) may be one another platform doesn't count.
NEXT_HOP_UNUSABLE = frozenset({"protocol nexthop is not on the interface"})
_ORIGINS = {"I", "E", "?"}
# Every element Junos 26.2 prints in these containers (tests/fixtures/junos_*.txt)
ROUTE_INFORMATION_KEYS = frozenset({"attributes", "route-table"})
ROUTE_TABLE_KEYS = frozenset({"table-name", "destination-count", "total-route-count", "active-route-count",
                              "holddown-route-count", "hidden-route-count", "rt", "comment"})
BGP_INFORMATION_KEYS = frozenset({"attributes", "bgp-peer"})
# Timer elements of a peer that aren't an advertisement delay (holdtime is the session's hold timer)
KNOWN_TIMERS = frozenset({"outbound-timer", "peer-stale-route-time-configured"})
INSTANCE_INFORMATION_KEYS = frozenset({"attributes", "instance-core"})


class NoSuchTable(DriverError):
    """`route-table-error`: Junos has no routing table by that name. The driver then reads the instance:
    an instance without the table has no routes there; a missing instance is NoSuchInstance."""


def _instance(vrf: str) -> str:
    return "master" if vrf == "default" else vrf


def _table(vrf: str, family: int) -> str:
    base = "inet6.0" if family == 6 else "inet.0"
    return base if vrf == "default" else f"{vrf}.{base}"


# `"data" : "..."` in an xnm:error answer, which Junos 26.2 prints as invalid JSON (a comma is missing)
_ERROR_MESSAGE = re.compile(r'"message"\s*:\s*\[\s*\{\s*"data"\s*:\s*"([^"]*)"')


def _join_repeats(pairs: list) -> dict:
    """Junos's JSON repeats an element's key inside one object (live: `protocol-nh` at two indent levels of one
    route entry). Every Junos element is a list, so the repeats are joined in order; a repeat that isn't a list
    is not a Junos element and is refused."""
    out: dict = {}
    for k, v in pairs:
        if k not in out:
            out[k] = v
        elif isinstance(out[k], list) and isinstance(v, list):
            out[k] = out[k] + v
        else:
            raise RepeatedKey(k)
    return out


def load_junos_json(command: str, text: str):
    return load_json(command, text, object_pairs_hook=_join_repeats)


def _json(command: str, text: str) -> dict:
    if isinstance(text, str) and text.lstrip().lower().startswith("error:"):
        raise DriverError(f"Junos error from `{command}`: {' '.join(text.split())[:200]}")
    if isinstance(text, str) and '"xnm:error"' in text:
        # e.g. "the routing subsystem is not running" while rpd starts: an error on that sample
        messages = "; ".join(dict.fromkeys(_ERROR_MESSAGE.findall(text))) or "xnm:error"
        raise DriverError(f"Junos error from `{command}`: {messages[:200]}")
    data = load_junos_json(command, text)
    if not isinstance(data, dict):
        raise unexpected(command, text)
    for key in data:
        if "error" in str(key) and key != "route-table-error":
            raise DriverError(f"Junos error from `{command}`: {str(data[key])[:200]}")
    return data


def _items(command: str, node: dict, key: str) -> list[dict]:
    """A Junos JSON element: a list of objects, or absent (an optional container Junos leaves out)."""
    if key not in node:
        return []
    value = node[key]
    if not isinstance(value, list) or not all(isinstance(v, dict) for v in value):
        raise unexpected(command, f"{key}: {str(value)[:150]}")
    return value


def _one(command: str, node: dict, key: str) -> dict | None:
    """An element that occurs at most once."""
    items = _items(command, node, key)
    if len(items) > 1:
        raise unexpected(command, f"{key} more than once: {str(items)[:150]}")
    return items[0] if items else None


def _root(command: str, data: dict, key: str, allowed: frozenset | None = None) -> dict:
    """The answer's single top-level element (`route-information`, `bgp-information`, ...)."""
    if set(data) != {key}:
        raise unexpected(command, f"expected only {key!r}: {str(data)[:150]}")
    node = _one(command, data, key)
    if node is None:
        raise unexpected(command, data)
    _known(command, node, allowed)
    return node


def _known(command: str, node: dict, allowed: frozenset | None) -> None:
    """Containers whose list of entries is optional (no peers, no routes): a key outside the ones Junos
    prints there may be the list renamed, which would read as "nothing". Unexpected instead."""
    extra = sorted(set(node) - allowed) if allowed is not None else []
    if extra:
        raise unexpected(command, f"unknown element {extra[0]!r}")


def _leaf(command: str, node: dict, key: str, required: bool = True) -> str | None:
    """A leaf's text: `"key": [{"data": "value"}]`. An empty flag element (`[{}]`) reads as ""."""
    item = _one(command, node, key)
    if item is None:
        if required:
            raise unexpected(command, f"no {key!r}: {str(node)[:150]}")
        return None
    value = item.get("data", "")
    if not isinstance(value, str):
        raise unexpected(command, f"{key}: {str(value)[:80]}")
    return value


def _strip_port(addr: str) -> str:
    """`10.0.1.2+179` (the TCP port of an established session) -> `10.0.1.2`."""
    return addr.split("+", 1)[0]


# --------------------------------------------------------------------------------------------- BGP neighbors

_UNICAST_RIBS = {"inet.0": "ipv4-unicast", "inet6.0": "ipv6-unicast"}


def _afi(command: str, rib: str, instance: str) -> str | None:
    """A peer's RIB name -> the netdryrun address family; None for families without a count here (EVPN,
    VPN, labeled unicast). A unicast RIB of another instance is unexpected: its count must never be read
    as this instance's."""
    own = rib if instance == "master" else rib[len(instance) + 1:] if rib.startswith(f"{instance}.") else None
    if own in _UNICAST_RIBS:
        return _UNICAST_RIBS[own]
    if rib.rsplit(".", 2)[-2:] in (["inet", "0"], ["inet6", "0"]):
        raise unexpected(command, f"RIB {rib!r} is not in instance {instance!r}")
    return None


@parser(NEIGHBORS_CMD)
def parse_bgp_neighbors(text: str, instance: str = "master") -> dict[str, BgpNeighbor]:
    """`show bgp neighbor instance <instance>`. A peer of another instance in the answer is unexpected
    (it would be read as one of this instance's). Prefix counts are Junos's accepted-prefix-count: received
    minus the routes it hides, whether import policy rejected them or it can't use their next hop. The output
    doesn't tell those apart, so where they differ the received count is kept as the most the count can be
    (prefixes_upto; interop IOP-7) until the hidden routes' reasons are read (JunosDriver.bgp_neighbors)."""
    info = _root(NEIGHBORS_CMD, _json(NEIGHBORS_CMD, text), "bgp-information", BGP_INFORMATION_KEYS)
    out = {}
    for peer in _items(NEIGHBORS_CMD, info, "bgp-peer"):
        addr = _strip_port(_leaf(NEIGHBORS_CMD, peer, "peer-address"))
        state = _leaf(NEIGHBORS_CMD, peer, "peer-state").strip()
        rti = _leaf(NEIGHBORS_CMD, peer, "peer-cfg-rti")
        if not addr or not state:
            raise unexpected(NEIGHBORS_CMD, str(peer)[:150])
        if rti != instance:
            raise unexpected(NEIGHBORS_CMD, f"peer {addr} is in instance {rti!r}, not {instance!r}")
        state = state.split()[0].lower()
        ribs = _items(NEIGHBORS_CMD, peer, "bgp-rib")
        if state == "established" and not ribs:
            # an established session lists its RIBs; without them every count would read 0
            raise unexpected(NEIGHBORS_CMD, f"{addr}: established without bgp-rib")
        prefixes, upto = {}, {}
        for rib in ribs:
            afi = _afi(NEIGHBORS_CMD, _leaf(NEIGHBORS_CMD, rib, "name"), instance)
            if afi is not None:
                prefixes[afi] = as_int(NEIGHBORS_CMD, _leaf(NEIGHBORS_CMD, rib, "accepted-prefix-count"))
                received = as_int(NEIGHBORS_CMD, _leaf(NEIGHBORS_CMD, rib, "received-prefix-count"))
                if received < prefixes[afi]:
                    raise unexpected(NEIGHBORS_CMD, f"{addr}: {afi}: more accepted than received")
                if received > prefixes[afi]:
                    upto[afi] = received
        key = _canon_addr(addr)
        if key in out:
            raise unexpected(NEIGHBORS_CMD, f"peer {addr} listed twice")
        out[key] = BgpNeighbor(addr, state, prefixes, upto, adv_interval=_adv_interval(peer, addr))
    return out


@parser(HIDDEN_CMD)
def parse_hidden_received(text: str, table: str) -> tuple[int, int] | None:
    """`show route receive-protocol bgp <peer> table <table> hidden extensive`: (the peer's hidden routes, how
    many of them import policy rejected), or None when a hidden route gives no reason, or one that is neither
    REJECTED nor in NEXT_HOP_UNUSABLE."""
    hidden = rejected = 0
    for rt in _tables(HIDDEN_CMD, text, table):
        for e in _items(HIDDEN_CMD, rt, "rt-entry"):
            reason = (_leaf(HIDDEN_CMD, e, "hidden-reason", required=False) or "").strip().lower()
            if reason != REJECTED and reason not in NEXT_HOP_UNUSABLE:
                return None
            hidden += 1
            rejected += reason == REJECTED
    return hidden, rejected


_DELAY = re.compile(r"delay|timer", re.I)


def _adv_interval(peer: dict, addr: str) -> float:
    """The session's advertisement interval in seconds. Junos sends updates without delay (platform default
    0) unless `out-delay` is configured; then it prints `outbound-timer` in the peer's options (captured
    live, 26.2R1.7-EVO). Any other delay-like element or option flag is a shape not captured yet: an error,
    never 0, which would keep settle and hold short while a leak may still be on its way."""
    options = _one(NEIGHBORS_CMD, peer, "bgp-option-information") or {}
    timer = _leaf(NEIGHBORS_CMD, options, "outbound-timer", required=False)
    others = [k for k in (*peer, *options) if _DELAY.search(str(k)) and k not in KNOWN_TIMERS]
    flags = [_leaf(NEIGHBORS_CMD, options, k, required=False) or "" for k in options if k.startswith("bgp-options")]
    if others or any(_DELAY.search(f) for f in flags):
        raise DriverError(f"peer {addr}: an advertisement delay in a form this driver doesn't read "
                          f"({', '.join(others) or 'an option flag'}); unexpected output, never read as no delay")
    if timer is None:
        return 0.0
    seconds = as_int(NEIGHBORS_CMD, timer)
    if seconds < 0:
        raise unexpected(NEIGHBORS_CMD, f"{addr}: outbound-timer {timer!r}")
    return float(seconds)


INSTANCES_CMD = "show route instance"
VRF_TYPES = ("vrf", "virtual-router")   # routing instances with their own tables, as a VRF elsewhere
MGMT_INSTANCE = "mgmt_junos"           # the management instance (`management-instance`): not the network's


@parser(INSTANCES_CMD)
def parse_vrfs(text: str) -> list[str]:
    """`show route instance`: the routing instances that work as VRFs (master is the default VRF)."""
    info = _root(INSTANCES_CMD, _json(INSTANCES_CMD, text), "instance-information", INSTANCE_INFORMATION_KEYS)
    return sorted(_leaf(INSTANCES_CMD, c, "instance-name") for c in _items(INSTANCES_CMD, info, "instance-core")
                  if (_leaf(INSTANCES_CMD, c, "instance-type", required=False) or "") in VRF_TYPES
                  and _leaf(INSTANCES_CMD, c, "instance-name") != MGMT_INSTANCE)


@parser(INSTANCE_CMD)
def parse_instance(text: str, instance: str) -> list[str] | None:
    """`show route instance <instance>`: the instance's routing tables, None when it doesn't exist."""
    info = _root(INSTANCE_CMD, _json(INSTANCE_CMD, text), "instance-information", INSTANCE_INFORMATION_KEYS)
    cores = _items(INSTANCE_CMD, info, "instance-core")
    found = [c for c in cores if _leaf(INSTANCE_CMD, c, "instance-name") == instance]
    if not found:
        return None
    return [_leaf(INSTANCE_CMD, r, "irib-name") for r in _items(INSTANCE_CMD, found[0], "instance-rib")]


# --------------------------------------------------------------------------------------------- routes

def _tables(command: str, text: str, table: str) -> list[dict]:
    """The `rt` elements of `table`; NoSuchTable when the table doesn't exist (`route-table-error`)."""
    data = _json(command, text)
    if "route-table-error" in data:
        err = _one(command, _root(command, data, "route-table-error"), "route-table-error-str")
        msg = str((err or {}).get("data", ""))
        if "no routing tables matching" not in msg.lower():
            raise DriverError(f"Junos error from `{command}`: {msg[:200] or data}")
        raise NoSuchTable(f"no routing table {table} (`{command}`)")
    info = _root(command, data, "route-information", ROUTE_INFORMATION_KEYS)
    rts = []
    for t in _items(command, info, "route-table"):
        _known(command, t, ROUTE_TABLE_KEYS)
        name = _leaf(command, t, "table-name")
        if name != table:  # an answer for another table must never read as this table's (empty) answer
            raise unexpected(command, f"table {name!r} in the answer for {table!r}")
        rts += _items(command, t, "rt")
    return rts


def _destination(command: str, rt: dict):
    """`rt-destination` plus `rt-prefix-length` (extensive), or a destination with its length (terse)."""
    dest = _leaf(command, rt, "rt-destination")
    length = _leaf(command, rt, "rt-prefix-length", required=False)
    text = f"{dest}/{length}" if length is not None else dest
    if "/" not in text:
        raise unexpected(command, f"not a prefix: {text[:80]!r}")
    try:
        return ipaddress.ip_network(text, strict=False)
    except ValueError:
        raise unexpected(command, f"not a prefix: {text[:80]!r}") from None


def _entries(command: str, rt: dict) -> list[dict]:
    entries = _items(command, rt, "rt-entry")
    if not entries:
        raise unexpected(command, f"route without rt-entry: {str(rt)[:150]}")
    for e in entries:
        if not _leaf(command, e, "protocol-name"):
            raise unexpected(command, f"rt-entry without protocol-name: {str(e)[:150]}")
    return entries


def _protocol(command: str, e: dict) -> str:
    name = _leaf(command, e, "protocol-name").strip().lower()
    return PROTOCOLS.get(name, name)


def _active(command: str, e: dict) -> bool:
    return _leaf(command, e, "active-tag", required=False) == "*" and not _hidden(command, e)


def _hidden(command: str, e: dict) -> bool:
    state = _leaf(command, e, "rt-entry-state", required=False) or ""
    return "Hidden" in state.split() or "hidden-reason" in e


def _filtered(command: str, e: dict) -> bool:
    """A hidden route rejected by import policy: never accepted, never usable (see the module docstring)."""
    reason = _leaf(command, e, "hidden-reason", required=False)
    return _hidden(command, e) and reason is not None and reason.strip().lower() == REJECTED


def _matching(command: str, text: str, prefix: str, table: str) -> list[dict]:
    want = ipaddress.ip_network(prefix)
    rts = _tables(command, text, table)
    return [e for rt in rts if _destination(command, rt) == want for e in _entries(command, rt)]


@parser(ROUTE_CMD)
def parse_routes(text: str, prefix: str, table: str = "inet.0") -> list[Route]:
    """Every route for exactly `prefix` in `table`, hidden ones included, minus BGP routes rejected by import
    policy. NoSuchTable when the table doesn't exist (the driver then reads the instance)."""
    entries = _matching(ROUTE_CMD, text, prefix, table)
    return [Route(prefix, _protocol(ROUTE_CMD, e), _active(ROUTE_CMD, e))
            for e in entries if not _filtered(ROUTE_CMD, e)]


@parser(ALL_ROUTES_CMD)
def parse_all_routes(text: str, table: str = "inet.0") -> list[Route]:
    rts = _tables(ALL_ROUTES_CMD, text, table)
    return [Route(str(_destination(ALL_ROUTES_CMD, rt)), _protocol(ALL_ROUTES_CMD, e), _active(ALL_ROUTES_CMD, e))
            for rt in rts for e in _entries(ALL_ROUTES_CMD, rt)]


# --------------------------------------------------------------------------------------------- BGP paths

_AS_TOKEN = re.compile(r"\{[\d ,]*\}|\([\d ]*\)|\d+|\S+")


def _as_path(command: str, text: str) -> str:
    """Junos `AS path: 65002 {65010 65011} I` -> `65002 {65010,65011}`; `AS path: I` (local) -> "".
    Sets are {a b}, confederation sequences (a b). Anything else (a bracketed local AS, an unknown token, no
    origin) is unexpected."""
    line = text.strip().splitlines()[0] if text and text.strip() else ""
    if not line.startswith("AS path:"):
        raise unexpected(command, f"as-path {text[:80]!r}")
    segments: list[tuple[str, list]] = []
    for tok in _AS_TOKEN.findall(line[len("AS path:"):]):
        if tok in _ORIGINS:
            return render_as_path(segments)
        if tok.isdigit():
            segments.append(("as-sequence", [tok]))
        elif tok.startswith("{"):
            segments.append(("as-set", tok[1:-1].replace(",", " ").split()))
        elif tok.startswith("("):
            segments.append(("as-confed-sequence", tok[1:-1].split()))
        else:
            raise unexpected(command, f"as-path token {tok!r} in {line[:80]!r}")
    raise unexpected(command, f"as-path without origin: {line[:80]!r}")


def _next_hop(command: str, e: dict) -> str | None:
    """The BGP next hop: the protocol next hop when Junos shows one (iBGP, resolved recursively), else the
    forwarding next hop (eBGP: the neighbor): the selected one, or the one address all of them name. Several
    different addresses with none selected is refused, never "the first listed" (0.4: repeated `protocol-nh`)."""
    for key in ("protocol-nh", "nh"):
        hops = _items(command, e, key)
        chosen = [h for h in hops if "selected-next-hop" in h] or hops
        tos = list(dict.fromkeys(_canon_addr(t) for t in (_leaf(command, h, "to", required=False) for h in chosen)
                                 if t))
        if len(tos) > 1:
            raise unexpected(command, f"{key}: several next hops ({', '.join(tos[:4])}) and none selected")
        if tos:
            return tos[0]
    return None


def _communities(command: str, e: dict) -> tuple[list[str], list[str]]:
    holder = _one(command, e, "communities")
    if holder is None:
        return [], []
    values = []
    for c in _items(command, holder, "community"):
        v = c.get("data")
        if not isinstance(v, str):
            raise unexpected(command, f"community {str(c)[:80]}")
        values.append(v)
    large = [v[len("large:"):] for v in values if v.lower().startswith("large:")]
    std = [v for v in values if not v.lower().startswith("large:")]
    return canon_communities(std), canon_communities(large)


@parser(ROUTE_CMD + " (bgp)")
def parse_bgp_paths(text: str, prefix: str, table: str = "inet.0") -> list[BgpPath]:
    """BGP routes for exactly `prefix` in `table`: every received path, hidden ones included (an unusable
    next hop), minus routes rejected by import policy. NoSuchTable when the table doesn't exist.

    The best path is the active BGP route. When a route of another protocol is active (a static default
    beats a leaked BGP one on preference), BGP's own best is the first BGP route whose only reason to lose
    is that preference: Junos lists entries in selection order."""
    cmd = ROUTE_CMD
    entries = _matching(cmd, text, prefix, table)
    bgp = [e for e in entries if _protocol(cmd, e) == "bgp" and not _filtered(cmd, e)]
    best = next((e for e in bgp if _active(cmd, e)), None)
    if best is None and any(_active(cmd, e) for e in entries):
        best = next((e for e in bgp if not _hidden(cmd, e)
                     and (_leaf(cmd, e, "inactive-reason", required=False) or "").lower() == "route preference"), None)
    out = []
    for e in bgp:
        std, large = _communities(cmd, e)
        lp = _leaf(cmd, e, "local-preference", required=False)
        med = _leaf(cmd, e, "metric", required=False)
        out.append(BgpPath(
            best=e is best,
            as_path=_as_path(cmd, _leaf(cmd, e, "as-path")),
            next_hop=_next_hop(cmd, e),
            local_pref=as_int(cmd, lp) if lp is not None else None,
            med=as_int(cmd, med) if med is not None else None,   # no `metric` element: no MED received (interop IOP-1)
            communities=std,
            large_communities=large,
            neighbor=_canon_addr(_leaf(cmd, e, "gateway", required=False) or "") or None,
        ))
    return out


# --------------------------------------------------------------------------------------------- ping

@parser(PING_CMD)
def parse_ping(text: str) -> tuple[int, int]:
    """(sent, received) from `probe-results-summary`; (0, 0) when ping didn't run (no summary: a bad
    source, an unknown instance, no route). `ping-failure` is no guide: Junos sets it on a 3/3 ping too."""
    results = _root(PING_CMD, _json(PING_CMD, text), "ping-results")
    summary = _one(PING_CMD, results, "probe-results-summary")
    if summary is None:
        return 0, 0
    sent = as_int(PING_CMD, _leaf(PING_CMD, summary, "probes-sent"))
    received = as_int(PING_CMD, _leaf(PING_CMD, summary, "responses-received"))
    if sent < 0 or received < 0 or received > sent:
        raise unexpected(PING_CMD, f"{received} of {sent} probes")
    return sent, received


# --------------------------------------------------------------------------------------------- driver

class JunosDriver(Driver):
    name = "junos"
    # bgp_neighbors reads the inet.0 and inet6.0 RIB counts only: an EVPN count would always read 0
    unsupported_afis = frozenset({"evpn"})

    def _vrf(self, vrf: str) -> str:
        vrf = check_vrf_name(vrf)
        if vrf.lower() == "master":  # Junos's own name for the default instance: one spelling only
            raise DriverError("VRF 'master' is the Junos name for the default instance; use vrf: default")
        return vrf

    def _cli(self, command: str, evidence: list[dict], timeout: float = 60) -> str:
        if "'" in command:  # the command goes inside single quotes on the VM's shell
            raise DriverError(f"refusing a Junos command with a quote: {command[:80]!r}")
        return self._exec([*VM_SSH, f"cli -c '{command} | display json | no-more'"], evidence, timeout=timeout)

    def _confirm_instance(self, vrf: str, table: str | None, evidence: list[dict]) -> bool:
        """Before an empty answer is trusted. True when the instance has `table`, False when it exists without
        it (no routes there); NoSuchInstance when the instance doesn't exist."""
        instance = _instance(vrf)
        ribs = parse_instance(self._cli(f"show route instance {instance}", evidence), instance)
        if ribs is None:
            raise NoSuchInstance(f"routing-instance {vrf!r} does not exist on {self.node}")
        return table is None or table in ribs

    def vrfs(self) -> Observation:
        ev: list[dict] = []
        return Observation(parse_vrfs(self._cli(INSTANCES_CMD, ev)), ev)

    def bgp_neighbors(self, vrf: str = "default") -> Observation:
        vrf = self._vrf(vrf)
        ev: list[dict] = []
        neighbors = parse_bgp_neighbors(self._cli(f"show bgp neighbor instance {_instance(vrf)}", ev), _instance(vrf))
        if not neighbors and vrf != "default":
            self._confirm_instance(vrf, None, ev)
        for n in neighbors.values():
            for afi in list(n.prefixes_upto):
                self._count_hidden(n, afi, vrf, ev)
        return Observation(neighbors, ev)

    def _count_hidden(self, n: BgpNeighbor, afi: str, vrf: str, ev: list[dict]) -> None:
        """The reference count, received minus rejected by import policy, from the reasons of the routes Junos
        hid. When they can't all be read, the count stays the range from accepted to received (interop IOP-7);
        a failed read is kept in prefixes_unread, so a check that can't be judged says the node gave no usable
        state, not that the network is wrong."""
        try:
            peer = str(ipaddress.ip_address(n.address))   # from device output, going back into a CLI string
        except ValueError:
            n.prefixes_unread[afi] = f"peer address {n.address!r} can't be used in a command"
            return
        table = _table(vrf, 6 if afi == "ipv6-unicast" else 4)
        try:
            counts = parse_hidden_received(self._cli(f"show route receive-protocol bgp {peer} table {table} "
                                                     "hidden extensive", ev), table)
        except DriverError as e:
            n.prefixes_unread[afi] = str(e)
            return
        received = n.prefixes_upto[afi]
        if counts is not None and counts[0] == received - n.prefixes[afi]:
            n.prefixes[afi] = received - counts[1]
            del n.prefixes_upto[afi]

    def _no_table(self, vrf: str, table: str, ev: list[dict]) -> list:
        """`route-table-error`: the instance must exist, and must not list the table; then it has no routes."""
        if self._confirm_instance(vrf, table, ev):
            raise DriverError(f"`show route` says table {table} doesn't exist, but routing-instance "
                              f"{_instance(vrf)!r} lists it")
        return []

    def _route_query(self, prefix: str, vrf: str, parse, ev: list[dict]):
        table = _table(vrf, ipaddress.ip_network(prefix).version)
        try:
            found = parse(self._cli(f"show route {prefix} exact table {table} all extensive", ev), prefix, table)
        except NoSuchTable:
            return self._no_table(vrf, table, ev)
        if not found and vrf != "default":
            self._confirm_instance(vrf, None, ev)
        return found

    def routes(self, prefix: str, vrf: str = "default") -> Observation:
        vrf = self._vrf(vrf)
        ev: list[dict] = []
        return Observation(self._route_query(prefix, vrf, parse_routes, ev), ev)

    def bgp_paths(self, prefix: str, vrf: str = "default") -> Observation:
        vrf = self._vrf(vrf)
        ev: list[dict] = []
        return Observation(self._route_query(prefix, vrf, parse_bgp_paths, ev), ev)

    def all_routes(self, vrf: str = "default", family: int = 4) -> Observation:
        vrf = self._vrf(vrf)
        ev: list[dict] = []
        table = _table(vrf, family)
        try:
            routes = parse_all_routes(self._cli(f"show route table {table}", ev), table)
        except NoSuchTable:
            return Observation(self._no_table(vrf, table, ev), ev)
        if not routes and vrf != "default":
            self._confirm_instance(vrf, None, ev)
        return Observation(routes, ev)

    def ping(self, target: str, source: str | None, count: int, vrf: str = "default") -> Observation:
        vrf = self._vrf(vrf)
        ev: list[dict] = []
        cmd = f"ping {ipaddress.ip_address(target)} count {int(count)} rapid wait 1"
        if source:
            cmd += f" source {ipaddress.ip_address(source)}"
        if vrf != "default":
            cmd += f" routing-instance {vrf}"
        return Observation(parse_ping(self._cli(cmd, ev, timeout=count * 2 + 30)), ev)
