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


class RouteInjection:
    """One inject_routes fault on one node. apply() then, whatever happens, restore()."""

    def __init__(self, lab: Lab, node: str, prefixes: list[str], as_path: list[int], budget: float = 60):
        self.lab, self.node, self.prefixes, self.as_path, self.budget = lab, node, prefixes, as_path, budget
        self.asn = ""
        self.applied = False   # set before the config goes in: restore even if applying half-fails
        self.sent_before: dict[tuple[str, str], int] = {}
        self.resets_before: dict[str, tuple] = {}
        # whether the routes left the node: True, False, or None when the counts couldn't be read at restore
        self.left: bool | None = None
        self.quiet: list[str] = []   # the established peers they never reached (left is False)

    def sent(self) -> dict[tuple[str, str], int]:
        """(family, peer) -> the prefixes the node has sent that peer (bgpd's pfxSnt), for each family injected and
        each established session (a session that is down sends nothing, and is not waited for)."""
        out = {}
        for afi in sorted({_afi(p) for p in self.prefixes}):
            peers = json.loads(self._vtysh("-c", f"show bgp {afi} unicast summary json") or "{}").get("peers") or {}
            for peer, info in peers.items():
                if not isinstance(info, dict) or not isinstance(info.get("pfxSnt"), int):
                    raise LabError(f"inject_routes on {self.node}: no sent-prefix count for {peer} "
                                   f"(`show bgp {afi} unicast summary json`)")
                if not isinstance(info.get("state"), str):
                    raise LabError(f"inject_routes on {self.node}: no session state for {peer} "
                                   f"(`show bgp {afi} unicast summary json`)")
                if info["state"] == "Established":
                    out[(afi, peer)] = info["pfxSnt"]
        return out

    def resets(self) -> dict[str, tuple]:
        """peer -> (sessions dropped, last reset reason, last NOTIFICATION code and subcode), from `show bgp neighbors
        json`. A peer that tears the session down because the injected routes exceeded its prefix limit sends a Cease
        NOTIFICATION with subcode 1 (`0601`, "Maximum Number of Prefixes Reached", live FRR 10.4.1): the routes left,
        though the sent count then reads 0 on the session that came back or is still down."""
        data = json.loads(self._vtysh("-c", "show bgp neighbors json") or "{}")
        out = {}
        for peer, info in data.items():
            if not isinstance(info, dict) or not isinstance(info.get("connectionsDropped"), int):
                raise LabError(f"inject_routes on {self.node}: no dropped-session count for {peer} "
                               "(`show bgp neighbors json`)")
            out[peer] = (info["connectionsDropped"], info.get("lastResetDueTo"), info.get("lastErrorCodeSubcode"))
        return out

    def _max_prefix_reset(self, peer: str, now: tuple) -> bool:
        """The peer dropped the session during the injection, and the last drop was its prefix-limit Cease."""
        dropped, due, code = now
        return (dropped > self.resets_before.get(peer, (dropped,))[0] and due == "BGP Notification received"
                and code == "0601")

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
        self.sent_before = self.sent()   # read before anything changes: a count that can't be read stops here
        self.resets_before = self.resets()
        self.applied = True
        self._apply_config(config_lines(self.asn, self.prefixes, self.as_path))
        self._wait(want_present=True)

    def restore(self) -> None:
        if not self.applied:
            return
        # Read while the routes are still in, after the scenario's checks: did every peer that was established when
        # they went in get more prefixes than before, or tear the session down over its prefix limit? A peer that
        # did neither never got them (an outbound filter towards it, a session that went down), and a max: or
        # present: false check on its side passed on nothing (acceptance round B-5). Every peer, not one: the
        # routes reaching one neighbor says nothing about another's side (Layer 6 on b03cb7a). Any other reset
        # proves nothing: inconclusive.
        try:
            after = self.sent()
            resets = self.resets()
            self.quiet = sorted({peer for (afi, peer), n in self.sent_before.items()
                                 if not (after.get((afi, peer), 0) > n
                                         or (peer in resets and self._max_prefix_reset(peer, resets[peer])))})
            self.left = bool(self.sent_before) and not self.quiet
        except (LabError, ValueError):
            self.left = None
        self._apply_config(config_lines(self.asn, self.prefixes, self.as_path, remove=True))
        self._wait(want_present=False)

    def describe(self) -> str:
        return f"{len(self.prefixes)} route(s) on {self.node}"
