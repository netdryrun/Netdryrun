"""Driver parser fuzzing (RELEASE-GATE layer 3).

Every parser gets truncated, empty, reordered, wrong-type, mutated and garbage output. It must raise a
DriverError or return real data. It must never turn malformed output into "no routes" or "no
sessions", which makes `present: false` pass. Only an answer in the expected structure (a real empty
table) may read as empty. Any exception other than DriverError fails too: the runner reports a
DriverError as a lab problem, anything else as a crash.
"""
import ipaddress
import json
import random
from dataclasses import asdict, dataclass, is_dataclass
from pathlib import Path
from typing import Callable

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from netdryrun.drivers import DriverError, eos, frr, srlinux

FIX = Path(__file__).parent / "fixtures"
SETTINGS = settings(max_examples=60, deadline=None, suppress_health_check=[HealthCheck.too_slow])


def read(name: str) -> str:
    return (FIX / name).read_text()


EOS_NO_ROUTES = json.dumps({"vrfs": {"default": {"routes": {}}}})
EOS_NO_BGP = read("eos_bgp_paths_empty.txt")
SRL_ROW = json.loads(read("srl_bgp_rib_paths.txt"))["route"][0]


# --- what "a real empty answer in the expected structure" looks like, per parser

def _is_net(k) -> bool:
    try:
        ipaddress.ip_network(str(k), strict=False)
        return True
    except ValueError:
        return False


def frr_route_table_empty(d) -> bool:
    return isinstance(d, dict) and all(_is_net(k) and isinstance(v, list) and v for k, v in d.items())


def frr_bgp_empty(d) -> bool:
    if not isinstance(d, dict):
        return False
    return d == {} or (isinstance(d.get("paths"), list) and "prefix" in d and "warning" not in d)


def frr_bgp_route_side_empty(d) -> bool:
    if isinstance(d, dict) and (d.get("bgpNoSuchInstance") or isinstance(d.get("warning"), str)):
        return True  # bgpd: no BGP instance in this VRF (the VRF itself is confirmed by the driver)
    return frr_bgp_empty(d)


def frr_neighbors_empty(d) -> bool:
    return d == {}


def eos_table_empty(key):
    def check(d) -> bool:
        try:
            return isinstance(d["vrfs"]["default"][key], dict) and "errors" not in d
        except (TypeError, KeyError):
            return False
    return check


def srl_list_empty(key):
    def check(d) -> bool:
        return d == {} or (isinstance(d, dict) and isinstance(d.get(key), list))
    return check


@dataclass
class Case:
    id: str
    parse: Callable[[str], object]
    fixtures: list[str]          # real captured outputs that parse to data
    empty_ok: Callable[[object], bool]


CASES = [
    Case("frr.parse_bgp_neighbors", frr.parse_bgp_neighbors,
         ["frr_bgp_neighbors.txt", "sonic_bgp_neighbors.txt"], frr_neighbors_empty),
    Case("frr.parse_routes", lambda t: frr.parse_routes(t, "192.168.3.0/24"), ["frr_route.txt"],
         frr_route_table_empty),
    Case("frr.parse_routes[sonic]", lambda t: frr.parse_routes(t, "192.168.20.0/24"), ["sonic_route.txt"],
         frr_route_table_empty),
    Case("frr.parse_routes[bgp side]", lambda t: frr.parse_routes("{}", "192.168.20.0/24", t),
         ["frr_bgp_paths.txt", "sonic_bgp_paths.txt"], frr_bgp_route_side_empty),
    Case("frr.parse_all_routes", frr.parse_all_routes, ["frr_route.txt", "sonic_route.txt"], frr_route_table_empty),
    Case("frr.parse_bgp_paths", lambda t: frr.parse_bgp_paths(t, "192.168.20.0/24"),
         ["frr_bgp_paths.txt", "sonic_bgp_paths.txt"], frr_bgp_empty),
    Case("frr.parse_bgp_paths[local]", lambda t: frr.parse_bgp_paths(t, "192.168.21.0/24"),
         ["frr_bgp_paths_local.txt"], frr_bgp_empty),
    Case("frr.parse_bgp_paths[v6]", lambda t: frr.parse_bgp_paths(t, "2001:db8:20::/48"),
         ["frr_bgp_paths_v6.txt"], frr_bgp_empty),
    Case("eos.parse_bgp_summary", eos.parse_bgp_summary, ["eos_bgp_summary.txt"], eos_table_empty("peers")),
    Case("eos.parse_routes[route table]", lambda t: eos.parse_routes(t, EOS_NO_BGP, "192.168.20.0/24"),
         ["eos_route.txt"], eos_table_empty("routes")),
    Case("eos.parse_routes[bgp side]", lambda t: eos.parse_routes(EOS_NO_ROUTES, t, "192.168.20.0/24"),
         ["eos_bgp_route.txt"], eos_table_empty("bgpRouteEntries")),
    Case("eos.parse_routes[leak]", lambda t: eos.parse_routes(EOS_NO_ROUTES, t, "0.0.0.0/0"),
         ["eos_leak_bgp.txt"], eos_table_empty("bgpRouteEntries")),
    Case("eos.parse_all_routes", lambda t: eos.parse_all_routes(t), ["eos_route.txt", "eos_leak_route.txt"],
         eos_table_empty("routes")),
    Case("eos.parse_bgp_paths", lambda t: eos.parse_bgp_paths(t, "192.168.20.0/24"),
         ["eos_bgp_paths.txt", "eos_bgp_route.txt"], eos_table_empty("bgpRouteEntries")),
    Case("eos.parse_bgp_paths[local]", lambda t: eos.parse_bgp_paths(t, "192.168.30.1/32"),
         ["eos_bgp_paths_local.txt"], eos_table_empty("bgpRouteEntries")),
    Case("srlinux.parse_bgp_neighbors", srlinux.parse_bgp_neighbors, ["srl_bgp_neighbors.txt"],
         srl_list_empty("neighbor")),
    Case("srlinux.parse_routes[route table]", lambda t: srlinux.parse_routes(t, "192.168.20.0/24", "{}"),
         ["srl_route.txt"], srl_list_empty("route")),
    Case("srlinux.parse_routes[leak table]", lambda t: srlinux.parse_routes(t, "0.0.0.0/0", "{}"),
         ["srl_leak_route.txt"], srl_list_empty("route")),
    Case("srlinux.parse_routes[bgp rib]", lambda t: srlinux.parse_routes("{}", "0.0.0.0/0", t),
         ["srl_leak_rib.txt"], srl_list_empty("route")),
    Case("srlinux.parse_rib_paths", lambda t: srlinux.parse_rib_paths(t, "192.168.20.0/24"),
         ["srl_bgp_rib_paths.txt"], srl_list_empty("route")),
    Case("srlinux.parse_all_routes", lambda t: srlinux.parse_all_routes(t), ["srl_route.txt"], srl_list_empty("route")),
    Case("srlinux.parse_attr_set", lambda t: srlinux.parse_attr_set(t, SRL_ROW),
         ["srl_attr_set_best.txt", "srl_attr_set_backup.txt"], lambda d: False),
]
IDS = [c.id for c in CASES]


def outcome(case: Case, text: str):
    """('raised', None) or ('data', result). Fails on any other exception, and on an empty result
    from input that isn't a real empty answer."""
    try:
        result = case.parse(text)
    except DriverError:
        return "raised", None
    if isinstance(result, (list, dict)) and not result:
        try:
            parsed = json.loads(text)
        except (ValueError, RecursionError):
            parsed = None
        assert parsed is not None and case.empty_ok(parsed), \
            f"{case.id} read malformed output as empty: {text[:300]!r}"
    return "data", result


def canon(result):
    """Order-insensitive form of a parser result, for the reordering property."""
    def norm(v):
        if is_dataclass(v):
            v = asdict(v)
        if isinstance(v, dict):
            return {str(k): norm(x) for k, x in v.items()}
        if isinstance(v, list):
            return sorted((norm(x) for x in v), key=lambda x: json.dumps(x, sort_keys=True))
        return v
    return json.dumps(norm(result), sort_keys=True)


# --- the fixtures themselves still parse to data (sanity for the properties below)

@pytest.mark.parametrize("case", CASES, ids=IDS)
def test_fixtures_parse_to_data(case):
    for name in case.fixtures:
        kind, result = outcome(case, read(name))
        assert kind == "data" and result, f"{case.id} on {name}"


# --- empty

@pytest.mark.parametrize("case", CASES, ids=IDS)
@pytest.mark.parametrize("text", ["", " ", "\n", "\t\r\n  "])
def test_empty_output_raises(case, text):
    with pytest.raises(DriverError):
        case.parse(text)


# --- truncated: every cut of every fixture (sampled for long ones)

@pytest.mark.parametrize("case", CASES, ids=IDS)
def test_truncated_output(case):
    for name in case.fixtures:
        text = read(name).rstrip()
        for cut in range(0, len(text), max(1, len(text) // 300)):
            outcome(case, text[:cut])


# --- garbage text

@pytest.mark.parametrize("case", CASES, ids=IDS)
@SETTINGS
@given(text=st.text(max_size=200))
def test_garbage_text(case, text):
    outcome(case, text)


# --- valid JSON of the wrong type or shape, including keys the parsers look for

KEYS = ["vrfs", "default", "routes", "route", "peers", "neighbor", "paths", "prefix", "bgpRouteEntries",
        "bgpRoutePaths", "bgpState", "peerState", "protocol", "ipv4-prefix", "afi-safi", "session-state",
        "peer-address", "addressFamilyInfo", "acceptedPrefixCounter", "prefixAccepted", "warning", "errors",
        "192.168.20.0/24", "192.168.3.0/24", "0.0.0.0/0", "10.0.0.2", "peer", "peerId", "peerEntry",
        "peerAddr", "origin-protocol", "local-pref", "as-path"]
scalars = st.none() | st.booleans() | st.integers() | st.floats(allow_nan=False) | st.text(max_size=12) | \
    st.sampled_from(KEYS)
json_values = st.recursive(
    scalars,
    lambda inner: st.lists(inner, max_size=4) | st.dictionaries(st.sampled_from(KEYS) | st.text(max_size=8),
                                                                inner, max_size=4),
    max_leaves=20)


@pytest.mark.parametrize("case", CASES, ids=IDS)
@SETTINGS
@given(value=json_values)
def test_wrong_type_json(case, value):
    outcome(case, json.dumps(value))


# --- reordered: same answer, whatever the order of keys and list entries

# Lists whose order carries no meaning (AS path segments and next hops do carry one: not shuffled)
UNORDERED = {"route", "neighbor", "paths", "bgpRoutePaths", "afi-safi"}


def shuffled(node, rnd: random.Random, key=None):
    if isinstance(node, dict):
        items = list(node.items())
        rnd.shuffle(items)
        return {k: shuffled(v, rnd, k) for k, v in items}
    if isinstance(node, list):
        items = [shuffled(v, rnd) for v in node]
        if key in UNORDERED or _is_net(key):  # zebra's entries for one prefix
            rnd.shuffle(items)
        return items
    return node


@pytest.mark.parametrize("case", CASES, ids=IDS)
@SETTINGS
@given(seed=st.integers(0, 2**32 - 1))
def test_reordered_output_reads_the_same(case, seed):
    for name in case.fixtures:
        original = case.parse(read(name))
        again = case.parse(json.dumps(shuffled(json.loads(read(name)), random.Random(seed)), indent=1))
        assert canon(again) == canon(original), case.id


# --- mutated: one container in a real answer replaced by another type, or its key renamed

def containers(node, path=()):
    """Paths to every dict or list below the root."""
    items = node.items() if isinstance(node, dict) else enumerate(node) if isinstance(node, list) else []
    for k, v in items:
        if isinstance(v, (dict, list)):
            yield path + (k,)
            yield from containers(v, path + (k,))


def mutate(doc, path, how, junk):
    parent = doc
    for k in path[:-1]:
        parent = parent[k]
    key = path[-1]
    if how == "rename" and isinstance(parent, dict):
        parent["x-" + junk] = parent.pop(key)
    else:
        old = parent[key]
        choices = [None, 0, 7, True, "", junk, [] if isinstance(old, dict) else {}]
        parent[key] = choices[len(junk) % len(choices)]
    return doc


@pytest.mark.parametrize("case", CASES, ids=IDS)
@SETTINGS
@given(data=st.data())
def test_mutated_output(case, data):
    for name in case.fixtures:
        doc = json.loads(read(name))
        paths = list(containers(doc))
        if not paths:
            continue
        path = data.draw(st.sampled_from(paths))
        how = data.draw(st.sampled_from(["rename", "retype"]))
        junk = data.draw(st.text(min_size=0, max_size=6))
        outcome(case, json.dumps(mutate(doc, path, how, junk)))


# --- parsers whose "nothing" answer is the fail-safe one
# These never answer "no routes". An empty or None result makes the caller raise or fail:
#   frr.parse_vrfs: VRF not listed -> the driver raises "VRF ... does not exist"
#   srlinux.parse_instance_state: None -> the driver raises "network-instance ... does not exist"
#   frr.parse_ping: (0, 0) -> the ping check reports "ping did not run" (failed, never passed)
#   frr.parse_default_local_pref: None -> local-pref "not set", which never equals an expected value
# They are fuzzed for crashes (only DriverError may escape) and for a well-typed answer.

def _ping_ok(r) -> bool:
    return isinstance(r, tuple) and len(r) == 2 and all(isinstance(x, int) and x >= 0 for x in r)


FAIL_SAFE = [
    # eos.parse_out_delays: a neighbor left out -> its advertisement delay is "not known" (None), never 0
    ("eos.parse_out_delays", lambda t: eos.parse_out_delays(t),
     ["eos_bgp_config.txt", "eos_bgp_config_outdelay.txt", "eos_bgp_config_peergroup.txt"],
     lambda r: isinstance(r, dict) and all(isinstance(k, str) and isinstance(v, float) and v >= 0 for k, v in r.items())),
    ("frr.parse_vrfs", lambda t: frr.parse_vrfs(t), ["frr_route.txt"],
     lambda r: isinstance(r, dict) and all(isinstance(k, str) and isinstance(v, bool) for k, v in r.items())),
    ("frr.parse_ping", frr.parse_ping, ["frr_ping.txt", "srl_ping.txt", "eos_ping.txt"], _ping_ok),
    ("frr.parse_default_local_pref", lambda t: frr.parse_default_local_pref(t), ["frr_bgp_table_header.txt"],
     lambda r: r is None or isinstance(r, int)),
    ("srlinux.parse_instance_state", lambda t: srlinux.parse_instance_state(t), ["srl_neighbor_local_pref.txt"],
     lambda r: r is None or isinstance(r, str)),
]
FS_IDS = [c[0] for c in FAIL_SAFE]


def fail_safe_outcome(case, text):
    _, parse, _, valid = case
    try:
        result = parse(text)
    except DriverError:
        return
    assert valid(result), f"{case[0]} returned {result!r} for {text[:200]!r}"


@pytest.mark.parametrize("case", FAIL_SAFE, ids=FS_IDS)
def test_fail_safe_parsers_on_empty_and_truncated(case):
    for text in ["", " ", "\n"]:
        fail_safe_outcome(case, text)
    for name in case[2]:
        text = read(name).rstrip()
        for cut in range(0, len(text) + 1, max(1, len(text) // 300)):
            fail_safe_outcome(case, text[:cut])


@pytest.mark.parametrize("case", FAIL_SAFE, ids=FS_IDS)
@SETTINGS
@given(text=st.text(max_size=200) | json_values.map(json.dumps))
def test_fail_safe_parsers_on_garbage(case, text):
    fail_safe_outcome(case, text)


def test_fail_safe_parsers_read_real_output():
    assert frr.parse_vrfs("netns-based vrfs\nvrf red id 5 table 1001 (configured)\nvrf blue inactive\n") == \
        {"red": True, "blue": False}
    assert frr.parse_ping(read("frr_ping.txt")) == (3, 3)
    assert frr.parse_default_local_pref(read("frr_bgp_table_header.txt")) == 100
    assert srlinux.parse_instance_state('{"name": "red", "oper-state": "up"}') == "up"
    assert srlinux.parse_instance_state("{\n}") is None


# --- coverage meta-test: a new driver or parser without fuzz coverage turns CI red

# Every registered driver, and the parser modules its output goes through (shared ones included)
DRIVER_PARSER_MODULES = {
    "frr": ["netdryrun.drivers.frr"],
    "sonic": ["netdryrun.drivers.sonic", "netdryrun.drivers.frr"],
    "eos": ["netdryrun.drivers.eos", "netdryrun.drivers.frr"],   # parse_ping is FRR's
    "srlinux": ["netdryrun.drivers.srlinux", "netdryrun.drivers.frr"],
}


def _public_parsers(module_name: str) -> set[str]:
    """parse_* functions defined in the module itself (re-exports are covered where they're defined)."""
    import importlib
    import inspect
    module = importlib.import_module(module_name)
    short = module_name.rsplit(".", 1)[1]
    return {f"{short}.{name}" for name, fn in inspect.getmembers(module, inspect.isfunction)
            if name.startswith("parse_") and fn.__module__ == module_name}


def test_every_driver_and_parser_is_fuzzed():
    import importlib
    import inspect

    from netdryrun.drivers import DRIVERS
    fuzzed = {c.id.split("[")[0] for c in CASES} | {c[0] for c in FAIL_SAFE}
    unlisted = sorted(set(DRIVERS) - set(DRIVER_PARSER_MODULES))
    assert not unlisted, f"drivers without fuzz coverage (add them to DRIVER_PARSER_MODULES and CASES): {unlisted}"
    modules = set()
    for name, cls in DRIVERS.items():
        # the modules of the driver class and its driver ancestors must be listed too
        own = {k.__module__ for k in inspect.getmro(cls)
               if k.__module__.startswith("netdryrun.drivers.") and k.__module__ != "netdryrun.drivers.base"}
        missing_mods = sorted(own - set(DRIVER_PARSER_MODULES[name]))
        assert not missing_mods, f"driver {name}: modules not in DRIVER_PARSER_MODULES: {missing_mods}"
        modules |= set(DRIVER_PARSER_MODULES[name])
    # every driver module in the package, registered or not
    pkg = importlib.import_module("netdryrun.drivers")
    import pkgutil
    modules |= {f"netdryrun.drivers.{m.name}" for m in pkgutil.iter_modules(pkg.__path__) if m.name != "base"}
    parsers = set().union(*(_public_parsers(m) for m in modules))
    missing = sorted(parsers - fuzzed)
    assert not missing, f"parsers without fuzz coverage (add a Case or FAIL_SAFE entry): {missing}"
    stale = sorted(fuzzed - parsers)
    assert not stale, f"fuzz cases for parsers that no longer exist: {stale}"
