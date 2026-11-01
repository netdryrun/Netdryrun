"""The scenario menu and the capture itself.

A capture runs the driver's own read methods against one lab node, through a Lab that records every command the
driver sends. So the commands are the driver's commands by construction: there is no second list to keep in step.
"""
from __future__ import annotations

import dataclasses
import ipaddress
from dataclasses import dataclass

from ..drivers import DRIVERS
from ..drivers.base import DriverError
from ..lab import ExecResult
from . import CaptureError

# What each scenario reads, what it needs, and how to tell from the driver's reading that the lab really showed it.
# The menu is fixed so every capture maps to a cell a check can pass or fail on (a must-fail cell needs its own).


@dataclass(frozen=True)
class Scenario:
    reads: tuple[str, ...]      # driver reads, in order: neighbors, routes, paths, ping
    needs: tuple[str, ...]      # options it needs: prefix, target
    shows: str                  # what the driver's reading must show, in words (manifest and --help)


SCENARIOS: dict[str, Scenario] = {
    "established": Scenario(("neighbors",), (), "at least one BGP session established"),
    "no-neighbor": Scenario(("neighbors",), (), "at least one configured BGP session that is not established"),
    "route-present": Scenario(("routes", "paths"), ("prefix",), "the prefix in the routing table"),
    "route-absent": Scenario(("routes", "paths"), ("prefix",), "the prefix in neither the routing table nor BGP"),
    "received-not-selected": Scenario(("paths",), ("prefix",), "two or more BGP paths for the prefix, one best"),
    "community": Scenario(("paths",), ("prefix",), "a BGP path for the prefix with a community"),
    "med": Scenario(("paths",), ("prefix",), "a BGP path for the prefix with a MED"),
    "no-med": Scenario(("paths",), ("prefix",), "a BGP path for the prefix with no MED attribute"),
    "local-pref": Scenario(("paths",), ("prefix",), "a BGP path for the prefix with a local preference"),
    "as-path": Scenario(("paths",), ("prefix",), "a BGP path for the prefix with a non-empty AS path"),
    "ping-reply": Scenario(("ping",), ("target",), "every ping answered"),
    "ping-no-reply": Scenario(("ping",), ("target",), "no ping answered"),
}

PING_COUNT = 3


def _jsonable(value):
    """A driver reading as plain JSON (dataclasses, tuples and dicts of them)."""
    if dataclasses.is_dataclass(value):
        return {f.name: _jsonable(getattr(value, f.name)) for f in dataclasses.fields(value)}
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    return value


def shows(scenario: str, reading: dict) -> bool | None:
    """Whether the driver's reading shows the scenario; None where the driver couldn't read it (a NOS whose parser
    isn't written yet: a human reads the outputs instead)."""
    if any(isinstance(v, dict) and "error" in v and len(v) == 1 for v in reading.values()):
        return None
    n = reading.get("neighbors") or {}
    paths = reading.get("paths") or []
    routes = reading.get("routes") or []
    ping = reading.get("ping")
    return {
        "established": lambda: any(x["state"] == "established" for x in n.values()),
        "no-neighbor": lambda: any(x["state"] != "established" for x in n.values()),
        "route-present": lambda: bool(routes),
        "route-absent": lambda: not routes and not paths,
        "received-not-selected": lambda: len(paths) >= 2 and sum(p["best"] for p in paths) == 1,
        "community": lambda: any(p["communities"] or p["large_communities"] for p in paths),
        "med": lambda: any(p["med"] is not None for p in paths),
        "no-med": lambda: bool(paths) and any(p["med"] is None for p in paths),
        "local-pref": lambda: any(p["local_pref"] is not None for p in paths),
        "as-path": lambda: any(p["as_path"] for p in paths),
        "ping-reply": lambda: bool(ping) and ping[0] > 0 and ping[1] == ping[0],
        "ping-no-reply": lambda: bool(ping) and ping[0] > 0 and ping[1] == 0,
    }[scenario]()


class RecordingLab:
    """Stands in for the Lab a driver is given: runs a command only on the one node captured, and records it."""

    def __init__(self, lab, node: str):
        self._lab = lab
        self.node = node
        self.nodes = {node: lab.nodes[node]}
        self.recorded: list[dict] = []

    def exec(self, node: str, cmd: list[str], timeout: float = 60, input: str | None = None) -> ExecResult:
        if node != self.node:
            raise CaptureError(f"the driver asked to run a command on {node!r}; this capture runs only on {self.node!r}")
        if input is not None:
            raise CaptureError(f"the driver sent input to `{' '.join(cmd)}`: capture runs read commands only")
        r = self._lab.exec(node, cmd, timeout=timeout)
        self.recorded.append({"argv": list(cmd), "rc": r.rc, "stdout": r.stdout, "stderr": r.stderr})
        return r


class ReplayLab:
    """A Lab that answers a driver's commands from a bundle, in order. A command the bundle doesn't have next is an
    error: replaying proves the bundle holds exactly what the driver asks for."""

    def __init__(self, node, recorded: list[dict]):
        self.nodes = {node.name: node}
        self._queue = list(recorded)

    def exec(self, node: str, cmd: list[str], timeout: float = 60, input: str | None = None) -> ExecResult:
        if not self._queue:
            raise CaptureError(f"the driver ran `{' '.join(cmd)}`, which the bundle doesn't have")
        nxt = self._queue.pop(0)
        if list(cmd) != nxt["argv"]:
            raise CaptureError(f"the driver ran `{' '.join(cmd)}` where the bundle has `{' '.join(nxt['argv'])}`")
        return ExecResult(list(cmd), nxt["rc"], nxt["stdout"], nxt["stderr"])

    def leftover(self) -> list[dict]:
        return self._queue


def check_params(scenario: str, prefix: str | None, target: str | None, source: str | None) -> dict:
    if scenario not in SCENARIOS:
        raise CaptureError(f"unknown scenario {scenario!r}; one of: {', '.join(SCENARIOS)}")
    sc = SCENARIOS[scenario]
    params: dict = {}
    if "prefix" in sc.needs:
        if not prefix:
            raise CaptureError(f"scenario {scenario} needs --prefix")
        try:
            params["prefix"] = str(ipaddress.ip_network(prefix, strict=True))
        except ValueError:
            raise CaptureError(f"--prefix {prefix!r} is not a prefix (address/length, host bits zero)") from None
    if "target" in sc.needs:
        if not target:
            raise CaptureError(f"scenario {scenario} needs --target")
        for name, value in (("--target", target), ("--source", source)):
            if value is None:
                continue
            try:
                ipaddress.ip_address(value)
            except ValueError:
                raise CaptureError(f"{name} {value!r} is not an IP address") from None
        params["target"] = target
        if source:
            params["source"] = source
    return params


def read(driver, scenario: str, params: dict, vrf: str) -> dict:
    """Run the scenario's reads with the driver; a read the driver can't parse is kept as its error."""
    reading: dict = {}
    for what in SCENARIOS[scenario].reads:
        try:
            if what == "neighbors":
                value = driver.bgp_neighbors(vrf).value
            elif what == "routes":
                value = driver.routes(params["prefix"], vrf).value
            elif what == "paths":
                value = driver.bgp_paths(params["prefix"], vrf).value
            else:
                value = driver.ping(params["target"], params.get("source"), PING_COUNT, vrf).value
            reading[what] = _jsonable(value)
        except (DriverError, NotImplementedError) as e:
            reading[what] = {"error": str(e) or type(e).__name__}
    return reading


def capture(lab, node, driver_name: str, scenario: str, params: dict, vrf: str = "default") -> tuple[list[dict], dict, str | None]:
    """(recorded commands, the driver's reading, the NOS version the node reports) for one scenario."""
    if driver_name not in DRIVERS:
        raise CaptureError(f"no driver {driver_name!r}; one of {sorted(DRIVERS)}")
    rec = RecordingLab(lab, node.name)
    driver = DRIVERS[driver_name](rec, node.name)
    version = driver.nos_version()
    reading = read(driver, scenario, params, vrf)
    return rec.recorded, reading, version
