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
from typing import Any

from .lab import Lab, LabError
from .verify.frr import adj_command, parse_adj
from .verify.snapshot import SnapshotError

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


AF_KEY = {"ipv4": "ipv4Unicast", "ipv6": "ipv6Unicast"}   # `show bgp neighbors json` addressFamilyInfo keys


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


class RouteInjection:
    """One inject_routes fault on one node. apply() then, whatever happens, restore()."""

    def __init__(self, lab: Lab, node: str, prefixes: list[str], as_path: list[int], budget: float = 60,
                 shares_node: bool = False):
        self.lab, self.node, self.prefixes, self.as_path, self.budget = lab, node, prefixes, as_path, budget
        # another inject_routes on the same node in the same scenario: its routes are in at the same time, so a
        # prefix-limit reset can't tell whose routes overflowed the limit (Layer 6 round 4 on bf29e89)
        self.shares_node = shares_node
        self.asn = ""
        self.applied = False   # set before the config goes in: restore even if applying half-fails
        self.peers_before: dict[str, list[str]] = {}   # family -> the peers established when the routes went in
        self.resets_before: dict[str, tuple] = {}
        # whether the routes left the node: True, False, or None when the advertised routes couldn't be read at restore
        self.left: bool | None = None
        self.quiet: dict[str, list[str]] = {}    # established peer -> the injected prefixes it was not sent (left False)
        self.unsent: dict[str, list[str]] = {}   # family -> its injected prefixes, with no session there to carry them
        self.applied_at: float | None = None   # time.monotonic() when the config went in: resets before it prove nothing

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

    def advertised(self, afi: str, peer: str) -> set[str]:
        """The prefixes the node advertises to the peer now: its adj-rib-out after outbound policy, read as strictly
        as verify reads it (prefix family, a path for each prefix, totalPrefixCounter equal to the prefixes listed).
        This, not bgpd's aggregate sent-prefix count, says which prefixes left (Layer 6 round 3 on 5e65852: another
        injection's prefixes raised the count, so routes that were all filtered read as sent)."""
        cmd = adj_command("default", afi, peer, "out")
        return {prefix for prefix, _pid in parse_adj(self._vtysh("-c", cmd), cmd, afi, "out", add_path_tx=False)}

    def resets(self) -> dict[str, tuple]:
        """peer -> (sessions dropped, last reset reason, last NOTIFICATION code and subcode, the session's families,
        milliseconds since the last reset), from `show bgp neighbors json`. A peer that tears the session down because the injected routes exceeded its prefix limit sends a Cease
        NOTIFICATION with subcode 1 (`0601`, "Maximum Number of Prefixes Reached", live FRR 10.4.1): the routes left,
        though the sent count then reads 0 on the session that came back or is still down."""
        data = json.loads(self._vtysh("-c", "show bgp neighbors json") or "{}")
        out = {}
        for peer, info in data.items():
            if not isinstance(info, dict) or not isinstance(info.get("connectionsDropped"), int):
                raise LabError(f"inject_routes on {self.node}: no dropped-session count for {peer} "
                               "(`show bgp neighbors json`)")
            families = info.get("addressFamilyInfo")
            out[peer] = (info["connectionsDropped"], info.get("lastResetDueTo"), info.get("lastErrorCodeSubcode"),
                         frozenset(families) if isinstance(families, dict) else None, info.get("lastResetTimerMsecs"))
        return out

    def _max_prefix_reset(self, peer: str, now: tuple, afi: str, elapsed: float) -> bool:
        """The peer dropped the session after the routes went in (elapsed seconds ago), the last drop was its
        prefix-limit Cease, and the session carries no family but the injected one, so the limit it hit can only be
        that family's (Layer 6 round 2 on eaa323c: an unrelated family's reset, or one from before the injection,
        counted). Anything unread proves nothing."""
        dropped, due, code, families, msecs = now
        return (dropped > self.resets_before.get(peer, (dropped,))[0] and due == "BGP Notification received"
                and code == "0601" and families == frozenset({AF_KEY[afi]})
                and isinstance(msecs, int) and not isinstance(msecs, bool) and msecs <= elapsed * 1000 + 1000)

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
        """Injected prefixes not yet in (or, for removal, still in) the node's own BGP table."""
        have = set()
        for afi in sorted({_afi(p) for p in self.prefixes}):
            data = json.loads(self._vtysh("-c", f"show bgp {afi} unicast json") or "{}")
            have |= set((data.get("routes") or {}))
        return [p for p in self.prefixes if (p in have) != want_present]

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
        self.peers_before = self.established()   # read before anything changes: what can't be read stops here
        self.resets_before = self.resets()
        self.applied = True
        self.applied_at = time.monotonic()
        self._apply_config(config_lines(self.asn, self.prefixes, self.as_path))
        self._wait(want_present=True)

    def restore(self) -> None:
        if not self.applied:
            return
        # Read while the routes are still in, after the scenario's checks. Every peer established in a prefix's
        # family when the routes went in or now must show it: in the advertised routes towards it now, with its session
        # never reset in between; or a prefix-limit reset that only this injection's routes can explain. A peer that
        # does neither never got the prefix (an outbound filter towards it, a session that went down or reset), and a
        # max: or present: false check on its side passed on nothing (acceptance round B-5). Every peer, not one
        # (Layer 6 on b03cb7a); every prefix, not a count (round 2 on eaa323c, round 3 on 5e65852); a peer that came
        # up while they were in, any other reset, and a prefix-limit reset with another injection's routes in on the
        # same node all prove nothing (round 4 on bf29e89). A family no established session carries sent nothing.
        try:
            now = self.established()
            resets = self.resets()
            elapsed = time.monotonic() - (self.applied_at if self.applied_at is not None else time.monotonic())
            quiet: dict[str, list[str]] = {}
            unsent: dict[str, list[str]] = {}
            for afi in sorted({_afi(p) for p in self.prefixes}):
                mine = [p for p in self.prefixes if _afi(p) == afi]
                peers = sorted(set(self.peers_before[afi]) | set(now[afi]))
                if not peers:
                    unsent[afi] = mine
                    continue
                for peer in peers:
                    if peer not in resets or peer not in self.resets_before:
                        quiet.setdefault(peer, []).extend(mine)   # whether its session reset can't be read
                        continue
                    if resets[peer][0] != self.resets_before[peer][0]:
                        if not self.shares_node and self._max_prefix_reset(peer, resets[peer], afi, elapsed):
                            continue
                        quiet.setdefault(peer, []).extend(mine)   # it reset while the routes were in
                        continue
                    got = self.advertised(afi, peer) if peer in now[afi] else set()
                    quiet.setdefault(peer, []).extend(p for p in mine if p not in got)
            self.quiet = {peer: missing for peer, missing in sorted(quiet.items()) if missing}
            self.unsent = unsent
            self.left = not self.quiet and not self.unsent
        except (LabError, ValueError, SnapshotError):
            self.left = None
        self._apply_config(config_lines(self.asn, self.prefixes, self.as_path, remove=True))
        self._wait(want_present=False)

    def describe(self) -> str:
        return f"{len(self.prefixes)} route(s) on {self.node}"
