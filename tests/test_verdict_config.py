"""Config validation that decides what a check means, or whether it means anything at all.

A value that slips through validation can make a check vacuous (always true) or change what it tests;
a value wrongly refused blocks a valid check. Each test asserts accepted or refused, and the loaded value,
never an error message. Mutation testing holds these boundaries in place.
"""
from __future__ import annotations

import textwrap

import pytest

from netdryrun.config import (MAX_PING_COUNT, MAX_SECONDS, UINT32, ConfigError, Fault, load, load_yaml,
                              parse_community)


def write(tmp_path, body: str, top: str = ""):
    (tmp_path / "topo.clab.yml").write_text("name: t\ntopology:\n  nodes:\n    r1: {image: frr}\n")
    p = tmp_path / "netdryrun.yml"
    p.write_text("lab: topo.clab.yml\n" + top + "checks:\n" + textwrap.indent(textwrap.dedent(body), "  "))
    return p


def one(tmp_path, check: str, top: str = ""):
    return load(write(tmp_path, f"- {check}\n", top)).checks[0]


def refused(tmp_path, check: str, top: str = ""):
    with pytest.raises(ConfigError):
        load(write(tmp_path, f"- {check}\n", top))
    return True


# ----------------------------------------------------------------------------------------------- numbers

def test_local_pref_and_med_up_to_uint32(tmp_path):
    assert one(tmp_path, f"{{type: bgp_route, node: r1, prefix: 10.0.0.0/8, local_pref: {UINT32}}}").params["local_pref"] == UINT32
    assert one(tmp_path, f"{{type: bgp_route, node: r1, prefix: 10.0.0.0/8, med: {UINT32}}}").params["med"] == UINT32
    assert refused(tmp_path, f"{{type: bgp_route, node: r1, prefix: 10.0.0.0/8, local_pref: {UINT32 + 1}}}")
    assert refused(tmp_path, f"{{type: bgp_route, node: r1, prefix: 10.0.0.0/8, med: {UINT32 + 1}}}")


@pytest.mark.parametrize("bounds", ["exact: 3, min: 1", "exact: 3, max: 5", "exact: 3, min: 1, max: 5"])
def test_exact_is_used_on_its_own(tmp_path, bounds):
    assert refused(tmp_path, f"{{type: bgp_prefixes, node: r1, neighbor: 10.0.0.2, {bounds}}}")


def test_min_up_to_max(tmp_path):
    assert one(tmp_path, "{type: bgp_prefixes, node: r1, neighbor: 10.0.0.2, min: 3, max: 3}").params["min"] == 3
    assert refused(tmp_path, "{type: bgp_prefixes, node: r1, neighbor: 10.0.0.2, min: 4, max: 3}")
    assert one(tmp_path, "{type: bgp_prefixes, node: r1, neighbor: 10.0.0.2, min: 4}").params == \
        {"node": "r1", "neighbor": "10.0.0.2", "min": 4}


@pytest.mark.parametrize("count,ok", [(1, True), (MAX_PING_COUNT, True), (0, False), (MAX_PING_COUNT + 1, False)])
def test_ping_count_range(tmp_path, count, ok):
    check = f"{{type: ping, node: r1, target: 10.0.0.9, count: {count}}}"
    if ok:
        assert one(tmp_path, check).params["count"] == count
    else:
        assert refused(tmp_path, check)


@pytest.mark.parametrize("extra,ok", [
    ("min_replies: 1", True), ("min_replies: 3", True), ("min_replies: 4", False), ("min_replies: 0", False),
    ("count: 5, min_replies: 5", True), ("count: 5, min_replies: 6", False), ("count: 1, min_replies: 1", True),
    ("count: 2, min_replies: 3", False), ("min_replies: '2'", False), ("min_replies: true", False),
])
def test_ping_min_replies_range(tmp_path, extra, ok):
    """min_replies runs from 1 to count (3 when count is not given)."""
    check = f"{{type: ping, node: r1, target: 10.0.0.9, {extra}}}"
    if ok:
        assert one(tmp_path, check).params["min_replies"] >= 1
    else:
        assert refused(tmp_path, check)


def test_min_replies_with_expect_failure_is_refused(tmp_path):
    assert refused(tmp_path, "{type: ping, node: r1, target: 10.0.0.9, expect: failure, min_replies: 1}")
    assert one(tmp_path, "{type: ping, node: r1, target: 10.0.0.9, expect: Failure}").params["expect"] == "failure"


@pytest.mark.parametrize("value,ok", [(0.5, True), (1, True), (MAX_SECONDS, True), (0, False), (-1, False),
                                      (MAX_SECONDS + 1, False)])
def test_timeouts_and_holds(tmp_path, value, ok):
    check = f"{{type: route, node: r1, prefix: 10.0.0.0/8, timeout: {value}}}"
    hold = f"{{type: route, node: r1, prefix: 10.0.0.0/8, present: false, hold: {value}}}"
    if ok:
        assert one(tmp_path, check).timeout == float(value)
        assert one(tmp_path, hold).hold == float(value)
        assert load(write(tmp_path, "- {type: route, node: r1, prefix: 10.0.0.0/8}\n", f"timeout: {value}\n")).timeout \
            == float(value)
    else:
        assert refused(tmp_path, check) and refused(tmp_path, hold)
        assert refused(tmp_path, "{type: route, node: r1, prefix: 10.0.0.0/8}", f"timeout: {value}\n")


def test_hold_only_on_post_convergence_checks(tmp_path):
    assert refused(tmp_path, "{type: route, node: r1, prefix: 10.0.0.0/8, hold: 5}")
    assert one(tmp_path, "{type: bgp_prefixes, node: r1, neighbor: 10.0.0.2, max: 5, hold: 5}").hold == 5.0
    assert one(tmp_path, "{type: route, node: r1, prefix: 10.0.0.0/8}").hold is None


def test_default_timeout_reaches_every_check(tmp_path):
    p = write(tmp_path, "- {type: route, node: r1, prefix: 10.0.0.0/8}\n", "timeout: 45\n")
    p.write_text(p.read_text() + textwrap.dedent("""\
        scenarios:
          - name: s
            link_down: {node: r1, interface: eth1}
            checks:
              - {type: route, node: r1, prefix: 10.0.0.0/8}
              - {type: route, node: r1, prefix: 10.0.0.0/8, timeout: 7}
        """))
    cfg = load(p)
    assert cfg.checks[0].timeout == 45.0
    assert [c.timeout for c in cfg.scenarios[0].checks] == [45.0, 7.0]
    assert load(write(tmp_path, "- {type: route, node: r1, prefix: 10.0.0.0/8}\n")).timeout == 120.0


# ----------------------------------------------------------------------------------------------- names and values

def test_check_name_is_kept(tmp_path):
    assert one(tmp_path, "{type: route, node: r1, prefix: 10.0.0.0/8, name: my check}").name == "my check"
    assert one(tmp_path, "{type: route, node: r1, prefix: 10.0.0.0/8}").name   # described when not given


def test_scenario_check_names_carry_the_scenario(tmp_path):
    p = write(tmp_path, "- {type: route, node: r1, prefix: 10.0.0.0/8}\n")
    p.write_text(p.read_text() + "scenarios:\n  - {name: s1, node_isolated: r1, checks: [{type: route, node: r1, "
                                 "prefix: 10.0.0.0/8, name: c}]}\n")
    sc = load(p).scenarios[0]
    assert sc.name == "s1" and sc.checks[0].name == "[s1] c"


@pytest.mark.parametrize("as_path,expected", [('""', ""), ("[65001, 65002]", "65001 65002"), ("65001", "65001"),
                                              ('"65001 {65002,65003}"', "65001 {65002,65003}")])
def test_as_path_values(tmp_path, as_path, expected):
    assert one(tmp_path, f"{{type: bgp_route, node: r1, prefix: 10.0.0.0/8, as_path: {as_path}}}").params["as_path"] \
        == expected


@pytest.mark.parametrize("as_path", ["null", "[]", "1.5", "{a: 1}", "true", "'x'"])
def test_bad_as_path(tmp_path, as_path):
    assert refused(tmp_path, f"{{type: bgp_route, node: r1, prefix: 10.0.0.0/8, as_path: {as_path}}}")


@pytest.mark.parametrize("text,expected", [("65535:65535", "65535:65535"), ("0:0", "0:0"), ("1:65535", "1:65535"),
                                           ("4294967295:1:2", "4294967295:1:2"), ("1:2:4294967295", "1:2:4294967295"),
                                           ("no_export", "65535:65281"), ("065000:01", "65000:1")])
def test_community_limits(text, expected):
    assert parse_community(text) == expected


@pytest.mark.parametrize("text", ["65536:1", "1:65536", "4294967296:1:2", "1:2:4294967296", "1:2:3:4", "1",
                                  "a:b", "1:", ":1", "1:2:3:4:5"])
def test_bad_communities(text):
    with pytest.raises(ValueError):
        parse_community(text)


def test_node_driver_overrides_and_setup(tmp_path):
    cfg = load(write(tmp_path, "- {type: route, node: r1, prefix: 10.0.0.0/8}\n",
                     "nodes:\n  r1: {driver: srlinux, setup: [echo hi]}\n  r2: {setup: echo two}\n"))
    assert cfg.drivers == {"r1": "srlinux"} and cfg.setup == {"r1": ["echo hi"], "r2": ["echo two"]}
    assert load(write(tmp_path, "- {type: route, node: r1, prefix: 10.0.0.0/8}\n")).drivers == {}


@pytest.mark.parametrize("nodes", ["{1: {driver: frr}}", "{' ': {driver: frr}}", "{r1: {driver: iosxr}}",
                                   "{r1: {}}", "{r1: {setup: []}}", "{r1: {setup: ['']}}", "{}", "[]"])
def test_bad_nodes(tmp_path, nodes):
    assert refused(tmp_path, "{type: route, node: r1, prefix: 10.0.0.0/8}", f"nodes: {nodes}\n")


def test_no_scenarios_is_an_empty_list(tmp_path):
    cfg = load(write(tmp_path, "- {type: route, node: r1, prefix: 10.0.0.0/8}\n"))
    assert cfg.scenarios == [] and cfg.setup == {}


# ----------------------------------------------------------------------------------------------- scenarios

def scen(tmp_path, body: str):
    p = write(tmp_path, "- {type: route, node: r1, prefix: 10.0.0.0/8}\n")
    p.write_text(p.read_text() + "scenarios:\n  - " + body + "\n")
    return p


def test_scenario_faults(tmp_path):
    sc = load(scen(tmp_path, "{node_isolated: r1, link_down: {node: r2, interface: eth2}, "
                             "inject_routes: {node: r3, prefixes: ['10.66.0.0/16'], as_path: [65009, 65010]}, "
                             "checks: [{type: route, node: r1, prefix: 10.0.0.0/8}]}")).scenarios[0]
    kinds = {f.kind: f for f in sc.faults}
    assert kinds["node_isolated"] == Fault("node_isolated", "r1")
    assert kinds["link_down"] == Fault("link_down", "r2", "eth2")
    inj = kinds["inject_routes"]
    assert inj.node == "r3" and inj.prefixes == ["10.66.0.0/16"] and inj.as_path == [65009, 65010]
    sc = load(scen(tmp_path, "{node_isolated: {node: r2}, checks: [{type: route, node: r1, prefix: 10.0.0.0/8}]}")).scenarios[0]
    assert sc.faults == [Fault("node_isolated", "r2")]


@pytest.mark.parametrize("body", [
    "{link_down: '', checks: [{type: route, node: r1, prefix: 10.0.0.0/8}]}",
    "{node_isolated: '', checks: [{type: route, node: r1, prefix: 10.0.0.0/8}]}",
    "{inject_routes: '', checks: [{type: route, node: r1, prefix: 10.0.0.0/8}]}",
    "{inject_routes: {node: r1, prefixes: [1]}, checks: [{type: route, node: r1, prefix: 10.0.0.0/8}]}",
    "{inject_routes: {node: r1, prefixes: ['']}, checks: [{type: route, node: r1, prefix: 10.0.0.0/8}]}",
    "{inject_routes: {node: r1, prefixes: []}, checks: [{type: route, node: r1, prefix: 10.0.0.0/8}]}",
    "{inject_routes: {node: r1, prefixes: ['10.6.0.0/16', 3]}, checks: [{type: route, node: r1, prefix: 10.0.0.0/8}]}",
    "{inject_routes: {node: r1, from: 1, count: 2}, checks: [{type: route, node: r1, prefix: 10.0.0.0/8}]}",
    "{inject_routes: {node: r1, prefixes: ['10.6.0.0/16'], as_path: ''}, checks: [{type: route, node: r1, prefix: 10.0.0.0/8}]}",
    "{inject_routes: {node: r1, prefixes: ['10.6.0.0/16'], as_path: []}, checks: [{type: route, node: r1, prefix: 10.0.0.0/8}]}",
    "{inject_routes: {node: 1, prefixes: ['10.6.0.0/16']}, checks: [{type: route, node: r1, prefix: 10.0.0.0/8}]}",
    "{node_isolated: [r1, ''], checks: [{type: route, node: r1, prefix: 10.0.0.0/8}]}",
    "{link_down: {node: r1}, checks: [{type: route, node: r1, prefix: 10.0.0.0/8}]}",
    "{link_down: [r1], checks: [{type: route, node: r1, prefix: 10.0.0.0/8}]}",
    "{link_down: {node: '', interface: eth1}, checks: [{type: route, node: r1, prefix: 10.0.0.0/8}]}",
    "{name: '', node_isolated: r1, checks: [{type: route, node: r1, prefix: 10.0.0.0/8}]}",
    "{node_isolated: r1, checks: []}",
    "{node_isolated: r1}",
    "{checks: [{type: route, node: r1, prefix: 10.0.0.0/8}]}",
])
def test_bad_scenarios(tmp_path, body):
    with pytest.raises(ConfigError):
        load(scen(tmp_path, body))


def test_scenario_must_be_a_mapping(tmp_path):
    with pytest.raises(ConfigError):
        load(scen(tmp_path, "just a string"))


# ----------------------------------------------------------------------------------------------- strict YAML

def test_duplicate_key_after_a_merge_is_refused():
    with pytest.raises(ConfigError):
        load_yaml("base: &b {x: 1}\nm:\n  <<: *b\n  y: 2\n  y: 3\n")
    assert load_yaml("base: &b {x: 1}\nm:\n  <<: *b\n  x: 2\n")["m"] == {"x": 2}


def test_duplicate_keys_are_refused_at_every_level():
    with pytest.raises(ConfigError):
        load_yaml("a: 1\na: 2\n")
    with pytest.raises(ConfigError):
        load_yaml("a: {b: 1, b: 2}\n")
    with pytest.raises(ConfigError):
        load_yaml("- {b: 1, b: 2}\n")
    assert load_yaml("a: {b: [1, {c: 2}]}\n") == {"a": {"b": [1, {"c": 2}]}}


def test_load_errors(tmp_path):
    with pytest.raises(ConfigError):
        load(tmp_path / "missing.yml")
    p = tmp_path / "netdryrun.yml"
    for text in ("", "[1]\n", "checks: []\nlab: x\n", "lab: ''\nchecks: [{type: route}]\n", "checks: [1]\n",
                 "lab: topo.clab.yml\n", "lab: topo.clab.yml\nchecks: {a: 1}\n", "lab: nope.yml\nchecks: [{}]\n",
                 "lab: topo.clab.yml\nextra: 1\nchecks: [{type: route, node: r1, prefix: 10.0.0.0/8}]\n"):
        (tmp_path / "topo.clab.yml").write_text("name: t\n")
        p.write_text(text)
        with pytest.raises(ConfigError):
            load(tmp_path)


def test_config_is_read_as_utf8(monkeypatch, tmp_path):
    import codecs
    from pathlib import Path
    seen = []
    orig = Path.read_text

    def read_text(self, encoding=None, errors=None):
        seen.append(encoding)
        return orig(self, encoding="utf-8", errors=errors)

    p = write(tmp_path, "- {type: route, node: r1, prefix: 10.0.0.0/8, name: 'café'}\n")
    monkeypatch.setattr(Path, "read_text", read_text)
    assert load(p).checks[0].name == "café"
    assert seen and all(enc is not None and codecs.lookup(enc).name == "utf-8" for enc in seen)
