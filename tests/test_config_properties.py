"""Property tests for strict config (release gate, layer 3): Hypothesis generates wrong types, typos,
unknown keys and empty values at every level of netdryrun.yml. Each must be a ConfigError (exit 2),
never a config that loads into a check that means something else, and never a crash."""
from __future__ import annotations

import copy
import ipaddress
import math
import string

import pytest
import yaml
from hypothesis import HealthCheck, assume, given, settings
from hypothesis import strategies as st

from netdryrun.checks import is_post_convergence
from netdryrun.config import (
    AFIS,
    BGP_STATES,
    CHECK_TYPES,
    COMMON_KEYS,
    INJECT_KEYS,
    LINK_DOWN_KEYS,
    NODE_KEYS,
    PROTOCOLS,
    SCENARIO_KEYS,
    TOP_LEVEL_KEYS,
    VRF_NAME,
    ConfigError,
    load,
)

PROPS = settings(max_examples=300, deadline=None, suppress_health_check=[HealthCheck.too_slow])

BASE = {
    "lab": "topo.clab.yml",
    "timeout": 90,
    "nodes": {"r1": {"driver": "frr", "setup": ["true"]}},
    "checks": [
        {"type": "bgp_session", "node": "r1", "neighbor": "10.0.0.2", "state": "established", "vrf": "blue",
         "name": "session", "timeout": 30},
        {"type": "bgp_prefixes", "node": "r1", "neighbor": "10.0.0.2", "min": 1, "max": 10, "afi": "ipv4-unicast",
         "hold": 20, "vrf": "red"},
        {"type": "route", "node": "r1", "prefix": "10.0.0.0/8", "present": False, "protocol": "bgp", "hold": 20},
        {"type": "route", "node": "r1", "prefix": "10.1.0.0/16", "present": True, "active": False,
         "vrf": "blue"},
        {"type": "bgp_route", "node": "r1", "prefix": "10.4.0.0/16", "present": False, "vrf": "blue", "hold": 20},
        {"type": "bgp_route", "node": "r1", "prefix": "10.2.0.0/16", "communities": ["65000:1"],
         "without_communities": ["65000:2"], "as_path": "65002", "as_path_regex": "^65002", "local_pref": 100,
         "med": 0, "next_hop": "10.0.0.2"},
        {"type": "ping", "node": "r1", "target": "10.0.0.9", "source": "10.0.0.1", "count": 3, "min_replies": 2,
         "expect": "success", "vrf": "blue"},
        {"type": "ping", "node": "r1", "target": "10.0.0.8", "expect": "failure", "hold": 15},
        {"type": "bgp_prefixes", "node": "r1", "neighbor": "10.0.0.2", "exact": 2, "only": ["10.66.0.0/16"]},
    ],
    "scenarios": [
        {"name": "uplink", "link_down": {"node": "r1", "interface": "eth1"}, "node_isolated": {"node": "r2"},
         "inject_routes": {"node": "r1", "count": 5, "from": "10.100.0.0/24", "as_path": [65400]},
         "checks": [{"type": "route", "node": "r1", "prefix": "10.3.0.0/16", "protocol": "bgp"}]},
        {"inject_routes": {"node": "r1", "prefixes": ["10.200.0.0/24"]},
         "checks": [{"type": "bgp_prefixes", "node": "r1", "neighbor": "10.0.0.2", "max": 1}]},
    ],
}

ALL_KEYS = (set(TOP_LEVEL_KEYS) | set(NODE_KEYS) | set(SCENARIO_KEYS) | set(LINK_DOWN_KEYS) | set(INJECT_KEYS)
            | set(COMMON_KEYS) | {k for s in CHECK_TYPES.values() for k in s["required"] + s["optional"]} | {"r1"})


def _allowed(path: tuple, mapping: dict) -> set:
    if path == ():
        return set(TOP_LEVEL_KEYS)
    if path == ("nodes",):
        return set(mapping)          # node names are free-form
    if path[0] == "nodes":
        return set(NODE_KEYS)
    if "link_down" in path:
        return set(LINK_DOWN_KEYS)
    if "inject_routes" in path:
        return set(INJECT_KEYS)
    if "node_isolated" in path:
        return {"node"}
    if "type" in mapping:
        spec = CHECK_TYPES[mapping["type"]]
        return set(spec["required"]) | set(spec["optional"]) | set(COMMON_KEYS)
    return set(SCENARIO_KEYS)


def _mappings(obj=BASE, path=()):
    """Every mapping in BASE with its path: top level, nodes, nodes.r1, checks, scenarios, faults."""
    if isinstance(obj, dict):
        yield path, obj
        for k, v in obj.items():
            yield from _mappings(v, path + (k,))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from _mappings(v, path + (i,))


MAPPINGS = [p for p, _ in _mappings()]
FIELDS = [(p, k) for p, m in _mappings() for k in m]


def _get(data, path):
    for k in path:
        data = data[k]
    return data


@pytest.fixture(scope="module")
def labdir(tmp_path_factory):
    d = tmp_path_factory.mktemp("props")
    (d / "topo.clab.yml").write_text("name: t\ntopology:\n  nodes:\n    r1: {}\n    r2: {}\n")
    return d


def _load(labdir, data):
    p = labdir / "netdryrun.yml"
    p.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True), encoding="utf-8")
    return load(p)


def test_base_config_is_valid(labdir):
    cfg = _load(labdir, BASE)
    assert len(cfg.checks) == len(BASE["checks"]) and len(cfg.scenarios) == 2


# --- unknown keys at every level ----------------------------------------------------------------------

KEY_ALPHABET = string.ascii_lowercase + "_-"


@PROPS
@given(path=st.sampled_from(MAPPINGS), key=st.text(KEY_ALPHABET, min_size=1, max_size=14),
       value=st.one_of(st.none(), st.booleans(), st.integers(), st.text(max_size=5)))
def test_unknown_key_anywhere_is_an_error(labdir, path, key, value):
    assume(key not in ALL_KEYS)
    data = copy.deepcopy(BASE)
    target = _get(data, path)
    if path == ("nodes",):
        target[key] = value   # a new node with bad settings
    else:
        target[key] = value
    with pytest.raises(ConfigError) as e:
        _load(labdir, data)
    if path != ("nodes",):
        assert repr(key) in str(e.value) or key in str(e.value)


# --- typos of existing keys at every level ---------------------------------------------------------------

def _typos(word: str):
    letters = st.sampled_from(string.ascii_lowercase + "_")
    i = st.integers(0, max(0, len(word) - 1))
    return st.one_of(
        i.map(lambda n: word[:n] + word[n + 1:]),                                   # drop a letter
        st.tuples(i, letters).map(lambda t: word[:t[0]] + t[1] + word[t[0]:]),     # insert a letter
        st.tuples(i, letters).map(lambda t: word[:t[0]] + t[1] + word[t[0] + 1:]),  # replace a letter
        i.map(lambda n: word[:n] + word[n + 1:n + 2] + word[n:n + 1] + word[n + 2:]),  # swap two letters
        st.just(word + "s"), st.just(word.upper()), st.just(word.capitalize()), st.just(word.replace("_", "-")),
    )


@PROPS
@given(field=st.sampled_from([f for f in FIELDS if f[0] != ("nodes",)]), data=st.data())
def test_typo_of_any_key_is_an_error(labdir, field, data):
    path, key = field
    new = data.draw(_typos(key), label="typo")
    cfg = copy.deepcopy(BASE)
    target = _get(cfg, path)
    assume(new and new != key and new not in _allowed(path, target))
    target[new] = target.pop(key)
    with pytest.raises(ConfigError):
        _load(labdir, cfg)


# --- wrong types and empty values for every field ----------------------------------------------------------

EMPTY = [None, "", [], {}]
SECONDS = [0, -1, "30", "2m", True, False, float("inf"), float("nan"), 86401, *EMPTY]
IP = ["x", "10.0.0.0/8", "300.1.1.1", 167772162, True, *EMPTY]
NON_NEG = [-1, "5", 1.5, True, False, *EMPTY]
BOOL = ["false", "true", "no", "yes", 0, 1, 1.0, *EMPTY]
BAD = {
    "lab": [1, True, "nope.yml", *EMPTY],
    "timeout": SECONDS, "hold": SECONDS,
    "nodes": ["x", 1, *EMPTY], "r1": ["frr", 1, *EMPTY],
    "driver": ["FRR", "juniper", "frrr", 1, True, *EMPTY],
    "setup": [[1], [""], ["  "], 1, *EMPTY],
    "checks": ["x", 1, [None], [1], ["x"], *EMPTY],
    "scenarios": ["x", 1, [None], [1], *EMPTY],
    "type": ["bgp", "routes", "bgp-session", 1, True, *EMPTY],
    "name": [1, True, "   ", *EMPTY],
    "node": [1, True, "  ", *EMPTY],
    "neighbor": IP, "target": IP, "source": IP, "next_hop": IP,
    "prefix": ["x", "10.0.0.0/33", 167772160, True, *EMPTY],
    "present": BOOL, "active": BOOL,
    "state": ["up", "establised", "Established ", 1, True, *EMPTY],
    "vrf": ["all", "ALL", "has space", "a/b", "-x", True, 1.5, *EMPTY],
    "afi": ["ipv4", "v6", "ipv6_unicast", "ipv4-multicast", 4, True, ["ipv4-unicast"], *EMPTY],
    "protocol": ["ebgp", "ibgp", "direct", "bgp4", "ospfv2", 1, True, ["bgp"], *EMPTY],
    "min": NON_NEG, "max": NON_NEG, "exact": NON_NEG,
    "local_pref": [*NON_NEG, 2 ** 32], "med": [*NON_NEG, 2 ** 32],
    "count": [0, -1, "3", 1.5, True, 10001, *EMPTY],
    "min_replies": [0, -1, "2", 1.5, True, 4, *EMPTY],
    "expect": ["fail", "succeed", True, 0, *EMPTY],
    "communities": ["65000:70000", "bogus", [1], 3600, [None], *EMPTY],
    "without_communities": ["65000:70000", "bogus", [1], 3600, [None], *EMPTY],
    "as_path": ["x", "65002 abc", True, 1.5, *EMPTY[:1], [], {}],
    "as_path_regex": ["(", 1, True, *EMPTY],
    "link_down": ["eth1", 1, {"node": "r1"}, {"interface": "eth1"}, *EMPTY],
    "interface": ["eth 1", "a/b", 1, "x" * 16, *EMPTY],
    "node_isolated": [1, True, {"node": None}, *EMPTY],
    "inject_routes": ["r1", 1, {"node": "r1"}, *EMPTY],
    "from": [1, True, "x", *EMPTY],
    "prefixes": [1, [1], "x", ["x"], *EMPTY],
    # [] is a valid `only` (nothing may arrive); an IPv6 prefix is the wrong family for the default afi
    "only": ["10.0.0.0/24", ["x"], [1], ["10.0.0.0/33"], ["2001:db8::/48"], [None], 1, True, None, "", {}],
}
# as_path "" is the valid empty AS path; {} and [] are not paths
BAD["as_path"] = ["x", "65002 abc", True, 1.5, None, [], {}]
BAD_FIELDS = [(p, k) for p, k in FIELDS if k in BAD]


def test_every_field_has_bad_values():
    assert {k for _, k in FIELDS} <= set(BAD) | {"r2"}, "add bad values for a new field"


@PROPS
@given(field=st.sampled_from(BAD_FIELDS), data=st.data())
def test_wrong_type_or_empty_value_anywhere_is_an_error(labdir, field, data):
    path, key = field
    bad = data.draw(st.sampled_from(BAD[key]), label="value")
    cfg = copy.deepcopy(BASE)
    _get(cfg, path)[key] = bad
    with pytest.raises(ConfigError):
        _load(labdir, cfg)


@pytest.mark.parametrize("field", BAD_FIELDS, ids=lambda f: ".".join(map(str, f[0] + (f[1],))))
def test_every_bad_value_of_every_field_is_an_error(labdir, field):
    """The exhaustive version of the property above: every listed bad value, at every place it can go."""
    path, key = field
    for bad in BAD[key]:
        cfg = copy.deepcopy(BASE)
        _get(cfg, path)[key] = bad
        with pytest.raises(ConfigError):
            _load(labdir, cfg)
            pytest.fail(f"{path}.{key} = {bad!r} loaded")


# --- fuzzed checks: either a ConfigError, or a check whose every field means what it says ----------------------

def _value_pool(key):
    good = {
        "node": ["r1"], "name": ["a check"], "neighbor": ["10.0.0.2", "2001:db8::2"], "target": ["10.0.0.9"],
        "source": ["10.0.0.1"], "next_hop": ["10.0.0.2"], "prefix": ["10.0.0.0/8", "2001:db8::/32"],
        "present": [True, False], "active": [True, False], "state": list(BGP_STATES) + ["Established"],
        "vrf": ["default", "blue", 100], "afi": list(AFIS) + ["IPv4-Unicast"], "protocol": list(PROTOCOLS) + ["BGP"],
        "min": [0, 1, 5], "max": [0, 1, 10], "exact": [0, 2], "local_pref": [100], "med": [0],
        "count": [1, 3, 5], "min_replies": [1, 2, 3], "expect": ["success", "failure", "FAILURE"],
        "communities": [["65000:1"], "no-export"], "without_communities": [["65000:2"]], "as_path": ["65002", "", 65002],
        "as_path_regex": ["^65002"], "timeout": [5, 30.5], "hold": [10, 20.5],
    }.get(key, [])
    return st.sampled_from(good + BAD.get(key, [None]))


@st.composite
def fuzzed_check(draw):
    ctype = draw(st.sampled_from(sorted(CHECK_TYPES)))
    spec = CHECK_TYPES[ctype]
    keys = list(spec["required"]) + draw(st.lists(st.sampled_from(list(spec["optional"]) + ["name", "timeout", "hold"]),
                                                  unique=True, max_size=6))
    check = {"type": ctype}
    for k in keys:
        check[k] = draw(_value_pool(k))
    return check


def _assert_meaningful(c):
    p = c.params
    for key in ("present", "active"):
        assert key not in p or isinstance(p[key], bool)
    assert "afi" not in p or p["afi"] in AFIS
    assert "protocol" not in p or p["protocol"] in PROTOCOLS
    for key in ("min", "max", "exact", "local_pref", "med"):
        assert key not in p or (type(p[key]) is int and p[key] >= 0)
    if c.type == "bgp_prefixes":
        assert {"min", "max", "exact"} & set(p)
        assert set(p) & {"min", "max", "exact"} != {"min"} or p["min"] >= 1, "min: 0 alone is vacuous"
    if c.type == "ping":
        assert type(p.get("count", 3)) is int and 1 <= p.get("count", 3)
        assert "min_replies" not in p or (type(p["min_replies"]) is int and 1 <= p["min_replies"] <= p.get("count", 3))
        assert p["expect"] in ("success", "failure")
    if c.type == "bgp_session":
        assert p["state"] in BGP_STATES
    for key in ("neighbor", "target", "source", "next_hop"):
        assert key not in p or str(ipaddress.ip_address(p[key])) == p[key]
    assert "prefix" not in p or str(ipaddress.ip_network(p["prefix"])) == p["prefix"]
    assert "vrf" not in p or (VRF_NAME.fullmatch(p["vrf"]) and p["vrf"].lower() != "all")
    assert isinstance(c.timeout, float) and math.isfinite(c.timeout) and c.timeout > 0
    assert c.hold is None or (math.isfinite(c.hold) and c.hold > 0 and is_post_convergence(c))
    assert isinstance(c.name, str) and c.name.strip()


@settings(max_examples=600, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(check=fuzzed_check())
def test_fuzzed_check_is_an_error_or_meaningful(labdir, check):
    try:
        cfg = _load(labdir, {"lab": "topo.clab.yml", "checks": [check]})
    except ConfigError:
        return
    _assert_meaningful(cfg.checks[0])


# --- arbitrary YAML never crashes the loader -------------------------------------------------------------------

yaml_values = st.recursive(
    st.one_of(st.none(), st.booleans(), st.integers(-5, 70000), st.floats(allow_nan=True), st.text(max_size=8),
              st.sampled_from(["lab", "checks", "type", "route", "ping", "r1", "10.0.0.1", "10.0.0.0/8", "false"])),
    lambda children: st.one_of(st.lists(children, max_size=4),
                               st.dictionaries(st.sampled_from(sorted(ALL_KEYS)) | st.text(max_size=6), children,
                                               max_size=5)),
    max_leaves=25,
)


@PROPS
@given(data=yaml_values)
def test_arbitrary_yaml_is_loaded_or_refused_never_crashes(labdir, data):
    try:
        cfg = _load(labdir, data)
    except ConfigError:
        return
    for c in cfg.checks + [c for sc in cfg.scenarios for c in sc.checks]:
        _assert_meaningful(c)


@PROPS
@given(text=st.text(alphabet=string.printable, max_size=200))
def test_arbitrary_text_is_loaded_or_refused_never_crashes(labdir, text):
    p = labdir / "netdryrun.yml"
    p.write_text(text, encoding="utf-8")
    try:
        load(p)
    except ConfigError:
        pass



@pytest.mark.parametrize("lab", ["\x00", "a\x00b.clab.yml", "x" * 5000])
def test_a_lab_path_no_file_can_have_is_a_config_error(labdir, lab):
    """Hypothesis found `lab: "\x00"` crashed load() with a ValueError (embedded null byte) on Python 3.13."""
    with pytest.raises(ConfigError, match="is not a usable path|not found"):
        _load(labdir, {"lab": lab, "checks": [{"type": "bgp_session", "node": "r1", "neighbor": "10.0.0.2"}]})
