"""`netdryrun record`: snapshot a known-good running lab into a netdryrun.yml baseline.

The recorded file asserts today's behavior: every established BGP session stays up, prefix
counts stay in range, no eBGP neighbor sends a prefix it doesn't send today, and every BGP-learned
route stays present. Run it once on the network
as it is (before a change), commit the file, then every future change is tested against it.
"""
from __future__ import annotations

import ipaddress
import math
import time
from datetime import datetime, timezone
from pathlib import Path

import yaml

from . import __version__
from .checks import Unready, _evaluate
from .config import Check, community_name
from .drivers import DriverError, detect, for_node
from .drivers.base import NoSuchInstance, is_bgp
from .lab import Lab, LabError

MAX_ROUTES_PER_NODE = 50
MAX_LINK_GUARDS_PER_NODE = 20
GUARD_SAMPLES = 3   # a guard sample that errors is retried; only a real failing sample means "the lab fails it"
MAX_ONLY_PREFIXES = 500   # a larger received set is recorded as an exact count instead of an `only` list


def prefix_range(count: int) -> dict:
    """The default prefix-count check (0.3.3): today's count as the floor, and headroom for normal growth
    (20%, at least 2) as the ceiling, which still catches a leak that multiplies the count. A neighbor that
    sends nothing stays at exactly 0 (min: 0 would be refused, and any prefix from it is new).
    On its own the headroom lets a small leak pass (0.3.3 and 0.4.0 advisory): `record` adds the closed-world
    `only` list to every eBGP neighbor's range (_closed_world), or pins the count where it can't."""
    if count == 0:
        return {"exact": 0}
    return {"min": count, "max": count + max(2, math.ceil(count / 5))}


def record(topology: Path, include_routes: bool = True, prefix_mode: str = "range", attributes: bool = False,
           guards: bool = True, log=lambda _: None, sleep=time.sleep) -> tuple[dict, list[str]]:
    """Return (netdryrun.yml data, warnings) for the running lab described by `topology`.
    prefix_mode: "range" (default: prefix_range), "exact", or "min".
    With `attributes`, each recorded BGP route also gets a bgp_route check pinning its best path's
    AS path, local preference and communities (not MED or next hop, which follow the topology).
    With `guards` (the default from 0.3.3: a prefix range has room for one leaked default route, so the
    no-default-route guard is what catches it), the standard guard recipes that can be read from the lab: no
    default route via BGP, and no link subnet of the topology via BGP, on every BGP node, except what the node
    learns via BGP today. Guards are recorded in the default VRF only.
    Every VRF the node lists is recorded; a check outside the default VRF carries `vrf:`."""
    if prefix_mode not in ("range", "exact", "min"):
        raise ValueError(f"prefix_mode must be range, exact or min, got {prefix_mode!r}")
    lab = Lab(topology)
    warnings: list[str] = []
    checks: list[dict] = []
    link_subnets = _link_subnets(lab, warnings) if guards else []
    for name, node in lab.nodes.items():
        try:
            detect(node)
        except DriverError:
            warnings.append(f"{name}: no driver for kind={node.kind!r} image={node.image!r}; skipped")
            continue
        drv = for_node(lab, name)
        log(f"recording {name} ({drv.name})")
        if drv.name == "sonic":
            warnings.append(f"{name}: SONiC is configured after boot; add its commands under nodes.{name}.setup "
                            "or the checks will fail on a fresh deploy")
        vrfs = ["default"]
        try:
            vrfs += [v for v in drv.vrfs().value if v != "default"]
        except DriverError as e:
            warnings.append(f"{name}: only the default VRF is recorded ({e}); add checks for other VRFs by hand")
        for vrf in vrfs:
            checks += _record_vrf(drv, name, vrf, warnings, include_routes, prefix_mode, attributes,
                                  link_subnets if guards and vrf == "default" else None, sleep)
    data = {"lab": topology.name, "timeout": 120, "checks": checks}
    return data, warnings


def _record_vrf(drv, name: str, vrf: str, warnings: list[str], include_routes: bool, prefix_mode: str,
                attributes: bool, link_subnets: list[str] | None, sleep) -> list[dict]:
    """One VRF of one node: its sessions, routes and (with `link_subnets`) guards."""
    at = {} if vrf == "default" else {"vrf": vrf}
    where = name if vrf == "default" else f"{name} (vrf {vrf})"
    try:
        neighbors = drv.bgp_neighbors(vrf).value
    except NoSuchInstance as e:
        if vrf == "default":
            warnings.append(f"{where}: could not read BGP state ({e}); skipped")
        return []   # a VRF without a BGP instance: no session or BGP route to record
    except DriverError as e:
        warnings.append(f"{where}: could not read BGP state ({e}); skipped")
        return []
    checks = _session_checks(name, neighbors, prefix_mode, warnings, vrf, drv)
    bgp_now: dict[int, set[str]] = {}   # every BGP route the node has today, received selected or not
    if include_routes or link_subnets is not None:
        for fam in (4, 6):
            try:
                every = [r for r in drv.all_routes(vrf=vrf, family=fam).value if is_bgp(r.protocol)]
            except DriverError as e:
                warnings.append(f"{where}: could not read IPv{fam} routes ({e})")
                continue
            bgp_now[fam] = {r.prefix for r in every}
            if not include_routes:
                continue
            routes = [r for r in every if r.active]
            if len(routes) > MAX_ROUTES_PER_NODE:
                warnings.append(f"INCOMPLETE BASELINE: {where} has {len(routes)} BGP routes (IPv{fam}); only the "
                                f"first {MAX_ROUTES_PER_NODE} are recorded as checks. A change to any other route "
                                "goes unnoticed: add checks for the routes that matter")
            for r in sorted(routes, key=lambda r: r.prefix)[:MAX_ROUTES_PER_NODE]:
                checks.append({"type": "route", "node": name, "prefix": r.prefix, "protocol": "bgp", **at})
                if attributes:
                    try:
                        c = _attribute_check(drv, name, r.prefix, vrf)
                    except DriverError as e:
                        warnings.append(f"{where}: could not read BGP attributes of {r.prefix} ({e})")
                        continue
                    if c:
                        checks.append(c)
    if link_subnets is not None and neighbors:
        checks += _guards(name, drv, neighbors, bgp_now, link_subnets, warnings, sleep=sleep)
    return checks


def _session_checks(name: str, neighbors: dict, prefix_mode: str, warnings: list[str],
                    vrf: str = "default", drv=None) -> list[dict]:
    at = {} if vrf == "default" else {"vrf": vrf}
    where = name if vrf == "default" else f"{name} (vrf {vrf})"
    checks: list[dict] = []
    for addr, n in sorted(neighbors.items()):
        try:
            ipaddress.ip_address(addr)
        except ValueError:
            warnings.append(f"{where}: BGP neighbor {addr!r} is not an IP address (unnumbered?); not recorded")
            continue
        if n.ambiguous:
            warnings.append(f"INCOMPLETE BASELINE: {where}: BGP neighbor {addr} is {len(n.ambiguous)} sessions "
                            f"({', '.join(n.ambiguous)}) that can't be told apart; not recorded: add checks on "
                            "global addresses")
            continue
        if n.state != "established":
            # a session that is down today has nothing to record, so the baseline is partial: said first in the file
            # and on stderr, like every other gap (acceptance round B-4: it was a warning among the others)
            warnings.append(f"INCOMPLETE BASELINE: {where}: BGP neighbor {addr} is {n.state}; not recorded, so a change "
                            "to that session goes unnoticed: bring it up and record again, or add a check by hand")
            continue
        checks.append({"type": "bgp_session", "node": name, "neighbor": addr, **at})
        for afi, count in sorted(n.prefixes.items()):
            if afi in n.prefixes_upto:
                warnings.append(f"INCOMPLETE BASELINE: {where}: BGP neighbor {addr} {afi}: the prefix count is "
                                f"{count} to {n.prefixes_upto[afi]} (hidden routes Netdryrun can't classify); "
                                "not recorded: add a check by hand")
                continue
            c = {"type": "bgp_prefixes", "node": name, "neighbor": addr, "afi": afi, **at}
            if prefix_mode == "exact":
                c["exact"] = count
            elif prefix_mode == "min" and count > 0:
                c["min"] = count
            else:
                c.update(prefix_range(count))
                if count > 0 and n.external is not False:
                    _closed_world(c, drv, where, addr, afi, count, warnings)
            checks.append(c)
        if n.external is not False and "%" not in addr:
            # an eBGP session that doesn't carry a unicast family today: exact 0 there, so the day that family is
            # added and sends a prefix the check fails (acceptance round B-3; a family a session doesn't carry
            # satisfies only exact: 0, see checks._bgp_prefixes)
            for afi in ("ipv4-unicast", "ipv6-unicast"):
                if afi not in n.prefixes:
                    checks.append({"type": "bgp_prefixes", "node": name, "neighbor": addr, "afi": afi, "exact": 0, **at})
    return checks


def _closed_world(c: dict, drv, where: str, addr: str, afi: str, count: int, warnings: list[str]) -> None:
    """The guard a range alone lacks, on an eBGP neighbor (or one whose kind the driver doesn't report): no
    prefix outside today's accepted set may arrive (`only`). Where the set can't be read, the range becomes the
    exact count, and a warning says what that still misses."""
    why = None
    if drv is None or not getattr(drv, "reads_received", False):
        why = f"the {getattr(drv, 'name', '?')} driver can't list the prefixes a neighbor sends"
    elif afi not in ("ipv4-unicast", "ipv6-unicast") or "%" in addr:
        why = f"the prefixes of {afi} from {addr} can't be listed"
    else:
        try:
            got = drv.bgp_received(addr, afi, c.get("vrf", "default")).value
        except DriverError as e:
            got, why = None, f"the prefixes it sends could not be read ({' '.join(str(e).split())})"
        if got is not None and not got:
            why = f"it counts {count} prefixes but lists none"
        elif got is not None and len(got) > MAX_ONLY_PREFIXES:
            why = f"it sends {len(got)} prefixes, more than the {MAX_ONLY_PREFIXES} an only list holds"
        elif got is not None:
            c["only"] = sorted(got, key=lambda p: ipaddress.ip_network(p))
            return
    for k in ("min", "max"):
        c.pop(k, None)
    c["exact"] = count
    warnings.append(f"{where}: BGP neighbor {addr} {afi}: recorded as exactly {count} prefixes, not a range, because "
                    f"{why}. A change that replaces one of its prefixes with another still passes: add route checks "
                    "with present: false for prefixes that must never arrive")


def _link_subnets(lab, warnings: list[str]) -> list[str]:
    """The subnets of the topology's links, from the addresses on their interfaces. An interface whose
    addresses can't be read is a warning: its subnet gets no guard, and the file says so."""
    nets: set = set()
    for end in (e for link in lab.links for e in link):
        node = lab.nodes.get(end[0])
        if node is None or node.kind in ("bridge", "ovs-bridge"):   # a host or bridge endpoint: nothing to read
            continue
        try:
            found = {a.network for a in lab.interface_addresses(*end) if not a.ip.is_link_local}
        except LabError as e:
            warnings.append(f"INCOMPLETE BASELINE: {end[0]}: could not read the addresses of {end[1]} ({e}); its "
                            "link subnet has no guard")
            continue
        if not found:
            # Unnumbered, or the NOS keeps the address elsewhere (SONiC on EthernetN, SR Linux on e1-Y.0 in
            # srbase-default): either way no guard can be written from it, so say so
            warnings.append(f"INCOMPLETE BASELINE: {end[0]}: no global address on {end[1]} where Netdryrun reads "
                            "it (unnumbered, or kept on another interface by the NOS); its link subnet has no guard")
        nets |= found
    return [str(n) for n in sorted(nets, key=lambda n: (n.version, n))]


def _guards(name: str, drv, neighbors: dict, bgp_now: dict[int, set[str]], link_subnets: list[str],
            warnings: list[str], sleep=time.sleep) -> list[dict]:
    """The standard guards for one BGP node: checks that must hold on what the network does today. Each one
    is evaluated on the recording lab with the real check before it is written: a guard the baseline itself
    fails (a default received from upstream but not selected, which the routing table doesn't list) is left
    out, and a warning, a comment in the file, says why. A sample that errors is no answer: it is retried, and
    a guard that never gets a real answer is left out with an INCOMPLETE BASELINE line."""
    v6 = (any(":" in a for a in neighbors) or bool(bgp_now.get(6))   # IPv6 neighbors or routes, or IPv6
          or any("ipv6" in afi for n in neighbors.values() for afi in n.prefixes))   # carried over IPv4
    # an eBGP session that doesn't carry IPv6 today still gets the ::/0 guard, so a family added later can't leak a
    # default unseen (acceptance round B-3), wherever IPv6 routes can be read
    ebgp = any(n.state == "established" and n.external is not False for n in neighbors.values())
    out = []
    for fam, default in ((4, "0.0.0.0/0"), (6, "::/0")):
        if fam == 6 and not v6 and not (ebgp and 6 in bgp_now):
            continue
        if fam not in bgp_now:   # its routes couldn't be read: a guard against what it has today can't be built
            warnings.append(f"INCOMPLETE BASELINE: {name}: IPv{fam} routes could not be read, so no IPv{fam} "
                            "guards (no default route, no link subnet) were recorded for it")
            continue
        if default in bgp_now[fam]:
            warnings.append(f"{name}: learns {default} via BGP today; no 'no default route' guard recorded")
            continue
        out.append({"type": "route", "node": name, "prefix": default, "protocol": "bgp", "present": False})
    # a subnet the node learns via BGP today, or whose family couldn't be read, gets no guard
    links = [n for n in link_subnets if n not in bgp_now.get(6 if ":" in n else 4, {n})]
    if len(links) > MAX_LINK_GUARDS_PER_NODE:
        warnings.append(f"INCOMPLETE BASELINE: {name} has {len(links)} link subnets; only the first "
                        f"{MAX_LINK_GUARDS_PER_NODE} are guarded. A leak of another one goes unnoticed: add guards "
                        "for the ones that matter")
    out += [{"type": "route", "node": name, "prefix": n, "protocol": "bgp", "present": False}
            for n in links[:MAX_LINK_GUARDS_PER_NODE]]
    kept = []
    for g in out:
        check = Check("route", {k: v for k, v in g.items() if k != "type"}, "guard", 30)
        for attempt in range(GUARD_SAMPLES):
            ok, detail, _ = _evaluate(check, drv)
            if ok or not isinstance(detail, Unready):
                break
            if attempt + 1 < GUARD_SAMPLES:
                sleep(2)
        why = " ".join(str(detail).split())
        if ok:
            kept.append(g)
        elif isinstance(detail, Unready):
            warnings.append(f"INCOMPLETE BASELINE: {name}: the guard against {g['prefix']} via BGP could not be "
                            f"evaluated on the lab ({why}); not recorded: add it by hand once the node answers")
        else:
            warnings.append(f"{name}: no guard against {g['prefix']} via BGP: the baseline lab already fails it ({why})")
    return kept


def _attribute_check(drv, node: str, prefix: str, vrf: str = "default") -> dict | None:
    best = next((p for p in drv.bgp_paths(prefix, vrf=vrf).value if p.best), None)
    if best is None:
        return None
    c: dict = {"type": "bgp_route", "node": node, "prefix": prefix, **({} if vrf == "default" else {"vrf": vrf})}
    if best.as_path is not None:
        c["as_path"] = best.as_path
    if best.local_pref is not None:
        c["local_pref"] = best.local_pref
    if best.all_communities():
        c["communities"] = [community_name(x) for x in best.all_communities()]
    return c


def render(data: dict, warnings: list[str]) -> str:
    stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    head = [
        f"# Recorded by netdryrun {__version__} record on {stamp}.",
        "# This is a baseline of the network's behavior when it was recorded. Review it before committing:",
        "# remove anything that is allowed to change, and add negative checks (route present: false,",
        "# ping expect: failure) for things that must never happen. Docs: https://netdryrun.com/reference/config/",
    ]
    # one comment line per warning: device output in a warning must not add YAML (a setup command) to the file
    head += [f"# warning: {' '.join(str(w).split())}" for w in warnings]
    incomplete = [" ".join(str(w).split()) for w in warnings if str(w).startswith("INCOMPLETE BASELINE")]
    if incomplete:   # first in the file, so nobody commits a partial baseline without seeing it
        head = [f"# {w}" for w in incomplete] + ["#"] + head
    return "\n".join(head) + "\n" + yaml.safe_dump(data, sort_keys=False, width=200)
