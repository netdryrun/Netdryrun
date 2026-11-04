"""The inject_routes fault: make an FRR node announce extra routes for a scenario, then take them back.

The node gets a blackhole static plus a BGP `network` statement per prefix (and, with as_path, a
route-map that prepends those ASNs), applied with `vtysh -f`. That is how a misbehaving customer
or peer is simulated: what the max-prefix limit or an import filter does with the extra routes is
then up to the network under test.
"""
from __future__ import annotations

import ipaddress
import json
import re
import time
from dataclasses import dataclass
from typing import Any

from .lab import Lab, LabError
from .verify.frr import BGP_CMDS, _best_sent, _dest_paths, _flag, _json, adj_command, parse_adj, parse_attrs
from .verify.snapshot import AsPath, SnapshotError, canon_prefix

ROUTE_MAP = "NDR-INJECT"
MAX_COUNT = 10000
DEFAULT_FROM = "100.64.0.0/24"   # shared address space (RFC 6598): never in a lab's own plan by accident


def parse_inject(where: str, item: Any) -> dict:
    """Validate one inject_routes entry; returns {node, prefixes, as_path}."""
    from .config import explicit_network   # here: config imports this module
    if not isinstance(item, dict) or "node" not in item:
        raise ValueError(f"{where}: inject_routes needs a node")
    unknown = set(item) - {"node", "prefixes", "count", "from", "as_path"}
    if unknown:
        raise ValueError(f"{where}: unknown inject_routes keys {sorted(unknown)}")
    if ("prefixes" in item) == ("count" in item):
        raise ValueError(f"{where}: inject_routes needs either prefixes or count")
    try:
        if "prefixes" in item:
            if "from" in item:
                raise ValueError("from only goes with count")
            raw = item["prefixes"] if isinstance(item["prefixes"], list) else [item["prefixes"]]
            if not raw:
                raise ValueError("prefixes is empty")
            nets = [explicit_network("prefixes", p) for p in raw]
        else:
            count = item["count"]
            if isinstance(count, bool) or not isinstance(count, int) or not 1 <= count <= MAX_COUNT:
                raise ValueError(f"count must be an integer from 1 to {MAX_COUNT}")
            first = explicit_network("from", item.get("from", DEFAULT_FROM))
            nets = [first]
            for _ in range(count - 1):
                nxt = nets[-1].broadcast_address + 1   # raises past the end of the address space
                nets.append(ipaddress.ip_network(f"{nxt}/{first.prefixlen}"))
    except (ValueError, ipaddress.AddressValueError) as e:
        raise ValueError(f"{where}: inject_routes: {e}") from None
    prefixes = list(dict.fromkeys(str(n) for n in nets))
    as_path = item.get("as_path") or []
    as_path = as_path if isinstance(as_path, list) else [as_path]
    for asn in as_path:
        if isinstance(asn, bool) or not isinstance(asn, int) or not 1 <= asn <= 4294967295:
            raise ValueError(f"{where}: inject_routes as_path must be a list of AS numbers")
    return {"node": str(item["node"]), "prefixes": prefixes, "as_path": [int(a) for a in as_path]}


def _family(prefix: str) -> str:
    return "ipv6" if ":" in prefix else "ip"


def _afi(prefix: str) -> str:
    return "ipv6" if ":" in prefix else "ipv4"




def config_lines(asn: str, prefixes: list[str], as_path: list[int], remove: bool = False) -> list[str]:
    """vtysh config that adds (or removes) the injected routes."""
    no = "no " if remove else ""
    rm = f" route-map {ROUTE_MAP}" if as_path and not remove else ""
    lines = [f"{no}{_family(p)} route {p} blackhole" for p in prefixes]
    if as_path and not remove:
        lines += [f"route-map {ROUTE_MAP} permit 10", f" set as-path prepend {' '.join(map(str, as_path))}", "exit"]
    lines.append(f"router bgp {asn}")
    for afi in ("ipv4", "ipv6"):
        nets = [p for p in prefixes if _afi(p) == afi]
        if nets:
            lines += [f" address-family {afi} unicast", *[f"  {no}network {p}{rm}" for p in nets], " exit-address-family"]
    lines.append("exit")
    if as_path and remove:
        lines.append(f"no route-map {ROUTE_MAP}")
    return lines


def bgp_asn(running_config: str) -> str:
    m = re.search(r"^router bgp (\d+)\s*$", running_config, re.M)
    if not m:
        raise LabError("no 'router bgp' in the default VRF")
    return m.group(1)


def conflicts(running_config: str, prefixes: list[str]) -> list[str]:
    """Prefixes the node already announces or routes statically: restoring them afterwards would delete config."""
    taken = set()
    for line in running_config.splitlines():
        w = line.split()
        if w[:1] == ["network"] and len(w) > 1:
            taken.add(w[1])
        elif len(w) > 2 and w[0] in ("ip", "ipv6") and w[1] == "route":
            taken.add(w[2])
    return [p for p in prefixes if p in taken]


@dataclass(frozen=True)
class Session:
    """A BGP session as inject_routes reads it from `show bgp neighbors json`."""
    dropped: int
    dynamic: bool
    up_ms: int | None     # established for this long; None when not established, or unread
    mrai_ms: int | None   # advertisement interval; None when unread


# The prefix-limit proof (0.4.1, owner decision 2026-11-04; spec: design/attributable-limit-proof.md in HQ). A peer whose
# session reset while the routes were in counts as reached only when the peer itself says it sent the injector's
# session a max-prefix Cease. FRR 10.4.1 (tag frr-10.4.1) sends CEASE / MAX_PREFIX (bgpd.h BGP_NOTIFY_CEASE_MAX_PREFIX)
# from one place, bgp_maximum_prefix_overflow() in bgpd/bgp_route.c, when the session's accepted count after inbound
# policy (peer->pcount, acceptedPrefixCounter) is over its maximum for that AFI/SAFI. Its callers: an UPDATE received
# (bgp_route.c, always=0) and setting the limit (peer_maximum_prefix_set() in bgpd.c, always=1: a config change, which
# the only-fault rule and the limit read at apply and at restore leave out). Two flags change what it means:
# `warning-only` sends nothing (prefixAllowedMaxWarning), and `force` adds the routes inbound policy filtered out to
# the count (PEER_FLAG_MAX_PREFIX_FORCE; not in the JSON, so read from the running config): either is not proven.
# The record (bgp_vty.c): lastNotificationReason is the last notification sent or received, so lastResetDueTo must be
# "BGP Notification send" (PEER_DOWN_NOTIFY_SEND, code 14, set when bgp_notify_send_internal() sends a Cease other
# than an admin reset or shutdown). lastResetTimerMsecs counts whole seconds and wraps every 24 hours (gmtime hours,
# no days), so the drop count must also have risen since apply. The strings are pinned to the versions below, from
# the live captures in tests/fixtures (frr_maxpfx_*): any other version is not proven until it has a fixture.
MAXPFX_REASON = "Cease/Maximum Number of Prefixes Reached"
MAXPFX_SENT = "BGP Notification send"
MAXPFX_CODE = 14
PROVEN_FRR = ("10.4.1", "10.4.1_git")
AF_KEYS = {"ipv4": "ipv4Unicast", "ipv6": "ipv6Unicast"}
# bgp_maximum_prefix_overflow()'s log line; bgpd logs nothing unless a `log` destination is configured
MAXPFX_LOG = re.compile(r"%MAXPFXEXCEED: No\. of (IPv[46] Unicast) prefix received from (\S+) (\d+) exceed, limit (\d+)")


@dataclass(frozen=True)
class PeerLimit:
    """A peer's max-prefix limit on the injector's session, as read on the peer node before the routes went in."""
    node: str      # the lab node at the peer's address
    session: str   # the injector's address: the key of the session on that node
    limit: int
    before: int    # prefixes it had accepted on the session
    dropped: int


def _need(record, key: str):
    """record[key], read strictly: a key that isn't there, or a record that isn't a mapping, is an error."""
    if not isinstance(record, dict) or key not in record:
        raise ValueError(f"no {key}")
    return record[key]


def _int(value) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"not a number: {value!r}")
    return value


def _count(n: int, noun: str) -> str:
    return f"{n} {noun}{'' if n == 1 else 'es' if noun.endswith('x') else 's'}"


class RouteInjection:
    """One inject_routes fault on one node. apply() then, whatever happens, restore()."""

    def __init__(self, lab: Lab, node: str, prefixes: list[str], as_path: list[int], budget: float = 60, *,
                 alone: bool = False, is_frr=None):
        self.lab, self.node, self.prefixes, self.as_path, self.budget = lab, node, prefixes, as_path, budget
        # The prefix-limit proof only for the scenario's only fault (anything else could trip a limit too), and only
        # on peers whose node `is_frr` names (the runner's drivers); without either, never
        self.alone, self.is_frr = alone, is_frr
        self.limits: dict[tuple[str, str], PeerLimit] = {}         # (family, peer) -> its limit, read at apply
        self.limits_again: dict[tuple[str, str], PeerLimit] = {}   # read again just before the routes went in
        self.limit_proven: dict[str, str] = {}   # peer -> the max-prefix reset that showed the routes reached it
        self._addrs: dict[str, set[str]] = {}
        self.asn = ""
        self.applied = False   # set before the config goes in: restore even if applying half-fails
        self.peers_before: dict[str, list[str]] = {}   # family -> the peers established when the routes went in
        self.sessions_before: dict[str, Session] = {}  # peer -> its session's drop count, kind and uptime then
        self.applied_at: float | None = None           # time.monotonic() when the routes went in
        self.late: set[str] = set()   # established peers not advertised every prefix before the checks ran
        self.listed_before: dict[str, set[str]] = {}   # peer -> injected prefixes it already had an entry for
        # whether the routes left the node: True, False, or None when the advertised routes couldn't be read at restore
        self.left: bool | None = None
        self.quiet: dict[str, list[str]] = {}    # established peer -> the injected prefixes it was not sent (left False)
        self.unsent: dict[str, list[str]] = {}   # family -> its injected prefixes, with no session there to carry them

    def established(self) -> dict[str, list[str]]:
        """family -> the peers whose session is established, for each family injected (a session that is down sends
        nothing, and is not waited for). `{}` is a family with no session configured (live FRR 10.4.1)."""
        out: dict[str, list[str]] = {}
        for afi in sorted({_afi(p) for p in self.prefixes}):
            cmd = f"show bgp {afi} unicast summary json"
            try:
                data = json.loads(self._vtysh("-c", cmd))
            except ValueError:
                data = None
            if not isinstance(data, dict):
                raise LabError(f"inject_routes on {self.node}: unexpected output from `{cmd}`")
            out[afi] = []
            if data == {}:
                continue
            if not isinstance(data.get("peers"), dict):
                raise LabError(f"inject_routes on {self.node}: no peers (`{cmd}`)")
            for peer, info in data["peers"].items():
                if not isinstance(info, dict) or not isinstance(info.get("state"), str):
                    raise LabError(f"inject_routes on {self.node}: no session state for {peer} "
                                   f"(`show bgp {afi} unicast summary json`)")
                if info["state"] == "Established":
                    out[afi].append(peer)
        return out

    def _as_path(self) -> AsPath:
        """The AS path the injected routes carry in the node's own tables: the prepended ASNs, or none."""
        return AsPath.build([("as-sequence", self.as_path)] if self.as_path else [])

    def advertised(self, afi: str, peer: str) -> set[str]:
        """The injected routes the node advertises to the peer now: its adj-rib-out after outbound policy, read as
        strictly as verify reads it (prefix family, a path for each prefix, totalPrefixCounter equal to the prefixes
        listed). This, not bgpd's aggregate sent-prefix count, says which prefixes left (Layer 6 round 3 on 5e65852).
        A prefix counts only when a path sent for it is the injected one: originated by a network statement
        (`sourced` and `local`, as every live capture marks one) with the injection's AS path, as the adj-rib-out
        shows it, before the local AS is prepended for an eBGP peer (adj_out_default_ipv4_* captures: a network
        route reads `Local`). A prefix the node advertises from another path, a learned one (the hijack case) or
        another of its own, didn't carry the injection (round 7 on 99fe33e). Without add-path the one path sent is
        the best (FRR lists every multipath path, interop IOP-8). With add-path the listing shows the node's paths
        with their per-family TX ids, a path denied to this peer included, so nothing in it proves which path this
        peer got: an add-path peer proves nothing, and is quiet (round 8 on ba4095d). Both destination forms are
        read (_dest_paths)."""
        cmd = adj_command("default", afi, peer, "out")
        text = self._vtysh("-c", cmd)
        parse_adj(text, cmd, afi, "out", add_path_tx=False)   # the whole listing, read strictly
        data = json.loads(text)
        out = set()
        for key, dest in (data["advertisedRoutes"].items() if data else ()):
            prefix = canon_prefix(key, cmd)
            paths = _dest_paths(cmd, prefix, dest, prefix)
            if any(isinstance(p, dict) and "addpathTxId" in p for p in paths):
                return set()
            if len(paths) > 1:
                paths = [_best_sent(cmd, prefix, paths)]
            if any(self._is_injected(cmd, p, f"{prefix} path {i}") for i, p in enumerate(paths)):
                out.add(prefix)
        return out

    def record_listed(self) -> None:
        """Before the config goes in: the injected prefixes each established peer already has an adj-rib-out entry
        for. FRR's advertised-routes view shows the node's current table paths under an existing entry, so once the
        injected path is in the table it reads as advertised to that peer before any UPDATE leaves; with a long
        advertisement interval the checks run while the peer still holds the old path. Such a prefix is never read
        as delivered to that peer (Layer 6 round 9 on 02a96a2), and a listing that can't be read counts as having
        them all."""
        self.listed_before = {}
        for afi, peers in self.peers_before.items():
            mine = {canon_prefix(p) for p in self.prefixes if _afi(p) == afi}
            for peer in peers:
                cmd = adj_command("default", afi, peer, "out")
                try:
                    had = {prefix for prefix, _pid in parse_adj(self._vtysh("-c", cmd), cmd, afi, "out",
                                                               add_path_tx=False)} & mine
                except (LabError, ValueError, SnapshotError):
                    had = mine
                if had:
                    self.listed_before.setdefault(peer, set()).update(had)

    def _is_injected(self, cmd: str, p, where: str) -> bool:
        """The path is the injected route: originated by a network statement (`sourced` and `local`, as every live
        capture marks one) with the injection's AS path. A redistributed or aggregated path of the node's own, or a
        learned one, is not."""
        source, _rx, attrs, _raw = parse_attrs(cmd, p, where)
        return (source == "local" and _flag(cmd, p, "sourced", where) and _flag(cmd, p, "local", where)
                and attrs.as_path == self._as_path())

    def _own_paths(self, afi: str) -> dict[str, list]:
        """prefix -> the node's own (local) paths for each injected prefix of the family, from its BGP table (`show bgp
        vrf all <afi> unicast detail json`, every path read as verify reads it), with whether each is the injected
        route. Several local paths for one prefix (a redistributed static, connected or kernel route, an aggregate)
        are read, not refused (Layer 6 round 8 on ba4095d)."""
        cmd = BGP_CMDS[afi]
        mine = {canon_prefix(p) for p in self.prefixes if _afi(p) == afi}
        try:
            data = _json(cmd, self._vtysh("-c", cmd))
            if not isinstance(data, dict):
                raise SnapshotError(f"unexpected output from `{cmd}`")
            inst = data["default"] if "default" in data else {"routes": {}}
            if not isinstance(inst, dict) or not isinstance(inst.get("routes"), dict):
                raise SnapshotError(f"unexpected output from `{cmd}`: default: no routes")
            out: dict[str, list] = {}
            for key, dest in inst["routes"].items():
                prefix = canon_prefix(key, cmd)
                if prefix not in mine:
                    continue
                for i, p in enumerate(_dest_paths(cmd, prefix, dest, prefix)):
                    where = f"{prefix} path {i}"
                    source, _rx, attrs, _raw = parse_attrs(cmd, p, where)
                    if source == "local":
                        out.setdefault(prefix, []).append((attrs.as_path, self._is_injected(cmd, p, where)))
            return out
        except SnapshotError as e:
            raise LabError(f"inject_routes on {self.node}: {e}") from None

    def sessions(self) -> dict[str, Session]:
        """peer -> its session from `show bgp neighbors json`: the drops (bgpd's connectionsDropped; a change while the
        routes were in is a reset), whether it is a dynamic peer (`bgp listen range`: FRR deletes it when its session
        drops and creates a new one on reconnect, so its count reads 0 across a flap; bgpd adds dynamicPeer only for
        one), how long it has been established (bgpTimerUpMsec, printed for an established session, each capture),
        and its advertisement interval (minBtwnAdvertisementRunsTimerMsecs)."""
        cmd = "show bgp neighbors json"
        try:
            data = json.loads(self._vtysh("-c", cmd))
        except ValueError:
            data = None
        if not isinstance(data, dict):
            raise LabError(f"inject_routes on {self.node}: unexpected output from `{cmd}`")
        out = {}
        for peer, info in data.items():
            if not isinstance(info, dict) or not isinstance(info.get("connectionsDropped"), int):
                raise LabError(f"inject_routes on {self.node}: no dropped-session count for {peer} (`{cmd}`)")
            up = info["bgpTimerUpMsec"] if isinstance(info.get("bgpTimerUpMsec"), int) else None
            mrai = (info["minBtwnAdvertisementRunsTimerMsecs"]
                    if isinstance(info.get("minBtwnAdvertisementRunsTimerMsecs"), int) else None)
            out[peer] = Session(info["connectionsDropped"], "dynamicPeer" in info, up, mrai)
        return out

    def await_delivery(self, settle: float) -> None:
        """Before the scenario's checks: wait until every peer established in a family when the routes went in
        advertises every injected prefix of that family (its adj-rib-out), so the checks never run before the routes
        left (Layer 6 round 6 on 1a597d7). Bounded by twice the longest advertisement interval, plus settle (an
        interval that can't be read counts as bgpd's eBGP default of 30 s, more wait, never less). A peer still
        missing one by then is late, and quiet at restore."""
        mrai = [s.mrai_ms / 1000 if s.mrai_ms is not None else 30.0 for s in self.sessions_before.values()]
        deadline = time.monotonic() + settle + 2 * max(mrai, default=30.0) + 2
        # a peer that already had an entry for an injected prefix can't show it delivered: no use waiting for it
        pending = {(afi, peer) for afi, peers in self.peers_before.items() for peer in peers
                   if not self.listed_before.get(peer)}
        while True:
            for afi, peer in sorted(pending):
                try:
                    got = self.advertised(afi, peer)
                except (LabError, ValueError, SnapshotError):
                    continue   # unreadable now: still pending
                if all(p in got for p in self.prefixes if _afi(p) == afi):
                    pending.discard((afi, peer))
            if not pending or time.monotonic() > deadline:
                break
            time.sleep(2)
        self.late = {peer for _afi, peer in pending}

    def _vtysh(self, *args: str, timeout: float = 120) -> str:
        r = self.lab.exec(self.node, ["vtysh", *args], timeout=timeout)
        if r.rc != 0:
            raise LabError(f"inject_routes on {self.node}: vtysh {' '.join(args)[:80]} failed: {(r.stderr or r.stdout).strip()[-300:]}")
        return r.stdout

    def _apply_config(self, lines: list[str]) -> None:
        path = "/tmp/netdryrun-inject.conf"
        r = self.lab.exec(self.node, ["sh", "-c", f"cat > {path}"], input="\n".join(lines) + "\n", timeout=30)
        if r.rc != 0:
            raise LabError(f"inject_routes on {self.node}: could not write {path}: {(r.stderr or r.stdout).strip()}")
        self._vtysh("-f", path, timeout=300)

    def _missing(self, want_present: bool) -> list[str]:
        """Injected prefixes whose injected path is not yet in (or, for removal, still in) the node's own BGP table:
        a path the node originates with the injection's AS path, read as verify reads the table. The prefix alone
        isn't enough: the node may already hold it from a neighbor, which is the hijack an injection tests (Layer 6
        round 7 on 99fe33e)."""
        have = set()
        for afi in sorted({_afi(p) for p in self.prefixes}):
            have |= {prefix for prefix, paths in self._own_paths(afi).items() if any(inj for _asp, inj in paths)}
        return [p for p in self.prefixes if (canon_prefix(p) in have) != want_present]

    def _wait(self, want_present: bool) -> None:
        deadline = time.monotonic() + self.budget
        while True:
            left = self._missing(want_present)
            if not left:
                return
            if time.monotonic() > deadline:
                verb = "did not appear in" if want_present else "are still in"
                raise LabError(f"inject_routes on {self.node}: {len(left)} prefix(es) {verb} its BGP table "
                               f"after {self.budget:g}s, e.g. {left[0]}")
            time.sleep(2)

    def apply(self) -> None:
        running = self._vtysh("-c", "show running-config")
        try:
            self.asn = bgp_asn(running)
        except LabError as e:
            raise LabError(f"inject_routes on {self.node}: {e}") from None
        taken = conflicts(running, self.prefixes)
        if taken:
            raise LabError(f"inject_routes on {self.node}: {', '.join(taken[:5])} already configured there; "
                           "inject prefixes the node does not announce yet")
        if self.as_path and re.search(rf"^route-map {ROUTE_MAP} ", running, re.M):
            raise LabError(f"inject_routes on {self.node}: route-map {ROUTE_MAP} already exists")
        # a path of the node's own for an injected prefix, with the AS path the injection would carry (a redistributed
        # connected route, say), can't be told from the injected one: what went in, and whether it came out again,
        # couldn't be read (Layer 6 round 8 on ba4095d)
        want = self._as_path()
        own = sorted(p for afi in sorted({_afi(x) for x in self.prefixes}) for p, paths in self._own_paths(afi).items()
                     if any(asp == want for asp, _inj in paths))
        if own:
            raise LabError(f"inject_routes on {self.node}: it already originates {', '.join(own[:5])} itself (a "
                           "redistributed, aggregated or network route) with the AS path the injected routes would "
                           "carry; inject prefixes it doesn't originate, or give the injection an as_path")
        self.peers_before = self.established()   # read before anything changes: what can't be read stops here
        self.sessions_before = self.sessions()
        self.limits = self.read_limits()
        self.record_listed()
        self.limits_again = self.read_limits()   # the count must not move between the two reads
        self.applied = True
        self.applied_at = time.monotonic()
        self._apply_config(config_lines(self.asn, self.prefixes, self.as_path))
        self._wait(want_present=True)

    def restore(self) -> None:
        if not self.applied:
            return
        # Read while the routes are still in, after the scenario's checks. One rule (Layer 6 round 5 on 45f63df,
        # after four rounds of cleverer proofs leaked): a peer was reached only if its session was established when
        # the routes went in, is established now, never reset in between, every injected prefix of its family was in
        # the routes advertised to it before the checks ran (await_delivery), and still is now, read strictly. Never
        # reset: its drop count reads and didn't change, it isn't a dynamic peer (recreated on reconnect, its count
        # reads 0 across a flap), and it has been up at least since the routes went in (round 6 on 1a597d7). Every
        # other peer seen in that family, at apply or now, is quiet: an outbound filter towards it, a session that
        # went down, reset or came up while the checks ran. A prefix-limit reset proves nothing: another node's
        # injection or a rerouted link can trip it too. A family no established session carried at apply sent nothing.
        try:
            now = self.established()
            sessions = self.sessions()
            since_ms = (time.monotonic() - self.applied_at) * 1000 if self.applied_at is not None else None
            quiet: dict[str, list[str]] = {}
            unsent: dict[str, list[str]] = {}
            for afi in sorted({_afi(p) for p in self.prefixes}):
                mine = [p for p in self.prefixes if _afi(p) == afi]
                if not self.peers_before[afi]:
                    unsent[afi] = mine
                for peer in sorted(set(self.peers_before[afi]) | set(now[afi])):
                    then, s = self.sessions_before.get(peer), sessions.get(peer)
                    steady = (peer in self.peers_before[afi] and peer in now[afi] and peer not in self.late
                              and then is not None and s is not None and not then.dynamic and not s.dynamic
                              and s.dropped == then.dropped and since_ms is not None and s.up_ms is not None
                              and s.up_ms + 1000 >= since_ms)   # bgpd counts the uptime in whole seconds
                    got = (self.advertised(afi, peer) if steady else set()) - self.listed_before.get(peer, set())
                    missing = [p for p in mine if p not in got]
                    if missing and peer in self.peers_before[afi]:   # a reset session: the prefix-limit proof
                        why = self._limit_proof(afi, peer, mine)
                        if why:
                            self.limit_proven[peer] = why
                            missing = []
                    quiet.setdefault(peer, []).extend(missing)
            self.quiet = {peer: missing for peer, missing in sorted(quiet.items()) if missing}
            self.unsent = unsent
            self.left = not self.quiet and not self.unsent
        except Exception:   # whatever went wrong reading, the routes are not shown to have left
            self.left = None
        finally:   # and whatever went wrong, the injected config comes out (Layer 6 round 8 on ba4095d)
            self._apply_config(config_lines(self.asn, self.prefixes, self.as_path, remove=True))
            self._wait(want_present=False)

    def read_limits(self) -> dict[tuple[str, str], PeerLimit]:
        """(family, peer) -> the peer's max-prefix limit on this node's session, for each peer established now whose
        address is one lab node's (exactly one), that node on the frr driver, FRR 10.4.1. Nothing for a peer that
        can't be read or doesn't qualify, and nothing at all unless this injection is the scenario's only fault."""
        if not self.alone or self.is_frr is None:
            return {}
        try:
            mine = self._addresses(self.node)
        except (LabError, ValueError):
            return {}
        out = {}
        for afi, peers in self.peers_before.items():
            for peer in peers:
                try:
                    lim = self._peer_limit(afi, peer, mine)
                except (LabError, ValueError, TypeError):
                    lim = None
                if lim is not None:
                    out[(afi, peer)] = lim
        return out

    def _addresses(self, node: str) -> set[str]:
        """The node's interface addresses (`ip -j addr`), read once per injection."""
        if node not in self._addrs:
            r = self.lab.exec(node, ["ip", "-j", "addr"], timeout=30)
            if r.rc != 0:
                raise LabError(f"`ip -j addr` failed on {node}")
            data = json.loads(r.stdout)
            if not isinstance(data, list):
                raise ValueError(f"unexpected output from `ip -j addr` on {node}")
            self._addrs[node] = {_need(a, "local") for i in data for a in _need(i, "addr_info")}
        return self._addrs[node]

    def _peer_limit(self, afi: str, peer: str, mine: set[str]) -> PeerLimit | None:
        owners = [n for n in self.lab.nodes if n != self.node and peer in self._addresses(n)]
        if len(owners) != 1 or not self.is_frr(owners[0]):
            return None
        node = owners[0]
        version = self._peer_vtysh(node, "show version")
        m = re.match(r"FRRouting (\S+) ", version)
        if not m or m.group(1) not in PROVEN_FRR:
            return None
        rec = self._session_record(node, mine)
        limit, accepted = self._family_limit(rec, afi)
        # `force` counts filtered routes too, and `warning-only` never resets: on any limit of the node, not proven
        if re.search(r"^\s*neighbor \S+ maximum-prefix .*\b(force|warning-only)\b",
                     self._peer_vtysh(node, "show running-config"), re.M):
            return None
        return PeerLimit(node, rec["_session"], limit, accepted, _int(_need(rec, "connectionsDropped")))

    def _peer_vtysh(self, node: str, cmd: str) -> str:
        r = self.lab.exec(node, ["vtysh", "-c", cmd], timeout=120)
        if r.rc != 0:
            raise LabError(f"vtysh -c '{cmd}' failed on {node}")
        return r.stdout

    def _session_record(self, node: str, mine: set[str]) -> dict:
        """The peer node's `show bgp neighbors json` entry for this node's session: exactly one of its neighbors is an
        address of this node."""
        data = json.loads(self._peer_vtysh(node, "show bgp neighbors json"))
        keys = [k for k in data if k in mine]
        if len(keys) != 1 or not isinstance(data[keys[0]], dict):
            raise ValueError(f"no single session to {self.node} on {node}")
        return {**data[keys[0]], "_session": keys[0]}

    @staticmethod
    def _family_limit(rec: dict, afi: str) -> tuple[int, int]:
        """(limit, accepted) in the injection's family, which must be the session's only family with a limit (the
        record doesn't say which family tripped), and not warning-only."""
        fams = _need(rec, "addressFamilyInfo")
        if not isinstance(fams, dict):
            raise ValueError("addressFamilyInfo is not a mapping")
        limited = [k for k, v in fams.items() if isinstance(v, dict) and "prefixAllowedMax" in v]
        if limited != [AF_KEYS[afi]]:
            raise ValueError("the injection's family is not the session's only limited family")
        fam = _need(fams, AF_KEYS[afi])
        if "prefixAllowedMaxWarning" in fam:   # FRR prints it, true, only for warning-only
            raise ValueError("warning-only")
        return _int(_need(fam, "prefixAllowedMax")), _int(_need(fam, "acceptedPrefixCounter"))

    def _limit_proof(self, afi: str, peer: str, mine: list[str]) -> str | None:
        """Why the routes reached `peer` though its session reset, or None: the peer node sent this node's session a
        max-prefix Cease after the routes went in, its count before was at or under the limit and the injected
        prefixes it didn't have take it over (the double read at apply equal), the drop count rose, the limit and
        family unchanged, and a log line, if bgpd wrote one, agrees. Anything unread or unexpected: None."""
        lim = self.limits.get((afi, peer))
        if lim is None or lim != self.limits_again.get((afi, peer)) or self.applied_at is None:
            return None
        injected = len({canon_prefix(p) for p in mine} - self.listed_before.get(peer, set()))
        if not lim.before <= lim.limit < lim.before + injected:
            return None
        try:
            t0 = time.monotonic()
            rec = self._session_record(lim.node, {lim.session})
            if (_need(rec, "lastResetDueTo") != MAXPFX_SENT or _need(rec, "lastNotificationReason") != MAXPFX_REASON
                    or _int(_need(rec, "lastResetCode")) != MAXPFX_CODE
                    or _int(_need(rec, "connectionsDropped")) <= lim.dropped
                    or self._family_limit(rec, afi)[0] != lim.limit):
                return None
            # the earliest the reset can have been: whole seconds, plus a second of margin
            if t0 - (_int(_need(rec, "lastResetTimerMsecs")) + 1000) / 1000 - 1 <= self.applied_at:
                return None
        except (LabError, ValueError, TypeError):
            return None
        if self._log_disagrees(lim, afi):
            return None
        return (f"{lim.node} sent {self.node}'s session a max-prefix Cease ({MAXPFX_REASON}) after the routes went in: "
                f"{_count(lim.before, 'prefix')} accepted before, limit {lim.limit}, {injected} injected")

    def _log_disagrees(self, lim: PeerLimit, afi: str) -> bool:
        """A max-prefix log line for the session, if bgpd logged one, must name the family and the limit and a count
        over it. No log (the default: no `log` destination configured) is not a disagreement."""
        try:
            text = self.lab.boot_log(lim.node).stdout
        except (LabError, AttributeError):
            return False
        want = "IPv4 Unicast" if afi == "ipv4" else "IPv6 Unicast"
        for fam, host, count, limit in MAXPFX_LOG.findall(text or ""):
            if host.split("(")[0] == lim.session and (fam != want or int(limit) != lim.limit or int(count) <= lim.limit):
                return True
        return False

    def describe(self) -> str:
        return f"{len(self.prefixes)} route(s) on {self.node}"
