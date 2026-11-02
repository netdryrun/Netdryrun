"""Per-platform drivers that turn device state into a common shape."""
from __future__ import annotations

from ..lab import NXOS_KINDS, ROUTEROS_KINDS, Lab, Node
from .base import Driver, DriverError
from .eos import EosDriver
from .frr import FrrDriver
from .junos import JunosDriver
from .nxos import NxosDriver
from .routeros import RouterosDriver
from .sonic import SonicDriver
from .srlinux import SrlDriver

# containerlab kinds for Juniper cJunosEvolved (beta driver)
JUNOS_KINDS = ("juniper_cjunosevolved", "cjunosevolved")

DRIVERS: dict[str, type[Driver]] = {"frr": FrrDriver, "srlinux": SrlDriver, "eos": EosDriver, "sonic": SonicDriver,
                                 "junos": JunosDriver, "nxos": NxosDriver,   # nxos: beta, unreleased
                                 "routeros": RouterosDriver}   # routeros: beta, unreleased


def detect(node: Node) -> str:
    if node.kind in ("nokia_srlinux", "srl"):
        return "srlinux"
    if node.kind in ("arista_ceos", "ceos"):
        return "eos"
    if node.kind in ROUTEROS_KINDS or any(w in node.image.lower() for w in ("mikrotik", "routeros")):
        return "routeros"
    if node.kind in NXOS_KINDS:
        return "nxos"
    if node.kind in JUNOS_KINDS:
        return "junos"
    if node.kind in ("sonic-vs", "sonic_vs") or "sonic" in node.image.lower():
        return "sonic"
    if "frr" in node.image.lower():
        return "frr"
    raise DriverError(
        f"cannot detect driver for node {node.name} (kind={node.kind!r}, image={node.image!r}); "
        f"set nodes.{node.name}.driver in netdryrun.yml to one of {sorted(DRIVERS)}"
    )


def for_node(lab: Lab, node: str, override: str | None = None) -> Driver:
    if node not in lab.nodes:
        raise DriverError(f"node {node!r} is not in the topology (nodes: {', '.join(lab.nodes)})")
    name = override or detect(lab.nodes[node])
    if name not in DRIVERS:
        raise DriverError(f"unknown driver {name!r} for node {node}; expected one of {sorted(DRIVERS)}")
    return DRIVERS[name](lab, node)


def check_supported(lab: Lab, check, override: str | None = None) -> None:
    """Refuse, before deploying, a check the node's driver cannot read (never guess a value): a bgp_route key
    the driver doesn't support, an address family it has no prefix counts for, or a route protocol name it
    never reports."""
    if check.type not in ("bgp_route", "bgp_prefixes", "route") or check.node not in lab.nodes:
        return
    if check.type == "route" and "protocol" not in check.params:
        return
    name = override or detect(lab.nodes[check.node])
    if check.type == "route":
        proto = check.params["protocol"]
        known = getattr(DRIVERS.get(name), "route_protocols", frozenset())
        if proto not in known:
            # a name the node never reports matches nothing, so present: false would always pass (red team RT-0024)
            raise DriverError(f"{check.name}: protocol {proto} is never reported by {name}, so the check could "
                              f"never match a route; use one of {', '.join(sorted(known)) or '(none)'}")
        return
    if check.type == "bgp_prefixes":
        afi = check.params.get("afi", "ipv4-unicast")
        if afi in getattr(DRIVERS.get(name), "unsupported_afis", ()):
            # the count would read as 0, which passes max and exact: refuse instead
            raise DriverError(f"{check.name}: afi {afi} is not supported on {name} (the {name} driver "
                              "can't count prefixes in that family)")
        if "only" in check.params and not getattr(DRIVERS.get(name), "reads_received", False):
            raise DriverError(f"{check.name}: only is not supported on {name} yet (it can't list the prefixes a "
                              "neighbor sent); use exact, or route checks with present: false")
        return
    cls = DRIVERS.get(name)
    keys = sorted(set(check.params) & set(cls.unsupported_bgp_attributes)) if cls else []
    if keys:
        raise DriverError(f"{check.name}: {', '.join(keys)} is not supported on {name}")
    # a value the driver's output can't tell from another state (config.py has checked it is an integer)
    for key, values in (cls.ambiguous_bgp_values if cls else {}).items():
        if key in check.params and check.params[key] in values:
            raise DriverError(f"{check.name}: {key}: {check.params[key]} can't be checked on {name}: "
                              f"{values[check.params[key]]}")


__all__ = ["Driver", "DriverError", "DRIVERS", "check_supported", "detect", "for_node"]
