"""Strict netdryrun.yml validation: every field has a type and allowed values, unknown keys and duplicate
keys are errors, and every config the project ships (examples, corpus specs, docs snippets) still loads.

Each regression test names the audit finding it pins down (audit C, 2026-10-27). They fail on the
validator before this change: the bad value was accepted and the check silently meant something else.
"""
import re
import shutil
import textwrap
from pathlib import Path

import pytest
import yaml

from netdryrun.checks import _route, is_post_convergence
from netdryrun.config import AFIS, DRIVER_NAMES, PROTOCOLS, Check, ConfigError, load, load_yaml
from netdryrun.drivers import DRIVERS
from netdryrun.drivers.base import Observation

ROOT = Path(__file__).resolve().parent.parent
TOPO = "name: t\ntopology:\n  nodes:\n    r1: {image: quay.io/frrouting/frr:10.4.1}\n"


def write(tmp_path, body):
    (tmp_path / "topo.clab.yml").write_text(TOPO)
    p = tmp_path / "netdryrun.yml"
    p.write_text(textwrap.dedent(body))
    return p


def one_check(tmp_path, check):
    return write(tmp_path, f"lab: topo.clab.yml\nchecks:\n  - {check}\n")


# --- B1: route.present must be a real boolean ---------------------------------------------------------

@pytest.mark.parametrize("value", ['"false"', '"true"', "'no'", "0", "1", "~", "''", "[]", "{}", "1.0"])
@pytest.mark.parametrize("ctype", ["route", "bgp_route"])
def test_b1_present_must_be_a_real_boolean(tmp_path, ctype, value):
    with pytest.raises(ConfigError, match=r"checks\[0\].*present must be true or false"):
        load(one_check(tmp_path, f"{{type: {ctype}, node: r1, prefix: 10.66.0.0/16, present: {value}}}"))


@pytest.mark.parametrize("value", ['"false"', "0", "~", "''"])
def test_b1_active_must_be_a_real_boolean(tmp_path, value):
    with pytest.raises(ConfigError, match="active must be true or false"):
        load(one_check(tmp_path, f"{{type: route, node: r1, prefix: 10.66.0.0/16, active: {value}}}"))


@pytest.mark.parametrize("value", ["true", "false", "yes", "no"])
def test_b1_yaml_booleans_still_work(tmp_path, value):
    cfg = load(one_check(tmp_path, f"{{type: route, node: r1, prefix: 10.66.0.0/16, present: {value}}}"))
    assert cfg.checks[0].params["present"] is (value in ("true", "yes"))


@pytest.mark.parametrize("present", [0, None, "", "false"])
def test_b1_evaluator_and_scheduler_agree_on_non_boolean_present(present):
    """Defense in depth behind the validator: a check built in code with a non-boolean present is scheduled
    as a positive check (is_post_convergence tests `is False`), so the evaluator must treat it as positive
    too. Before, the evaluator tested truthiness and passed `present: 0` at boot on an empty routing table."""
    c = Check(type="route", params={"node": "r1", "prefix": "10.66.0.0/16", "present": present}, name="x", timeout=5)
    assert not is_post_convergence(c)

    class Empty:
        def routes(self, prefix, vrf="default"):
            return Observation([], [])

    ok, detail, _ = _route(Empty(), c.params)
    assert not ok, detail


# --- B2: afi must be a family the drivers report ------------------------------------------------------

@pytest.mark.parametrize("afi,hint", [("ipv4", "ipv4-unicast"), ("ipv6_unicast", "ipv6-unicast"),
                                      ("v4", "ipv4-unicast"), ("l2vpn-evpn", "evpn"), ("ipv4-multicast", None),
                                      ("''", None), ("~", None), ("4", None), ("[ipv4-unicast]", None)])
def test_b2_afi_must_be_known(tmp_path, afi, hint):
    with pytest.raises(ConfigError, match=r"checks\[0\].*afi must be one of") as e:
        load(one_check(tmp_path, f"{{type: bgp_prefixes, node: r1, neighbor: 10.0.0.2, max: 10, afi: {afi}}}"))
    if hint:
        assert f"did you mean {hint!r}" in str(e.value)


def test_b2_afi_is_case_insensitive_and_canonical(tmp_path):
    cfg = load(one_check(tmp_path, "{type: bgp_prefixes, node: r1, neighbor: 10.0.0.2, max: 10, afi: IPv6-Unicast}"))
    assert cfg.checks[0].params["afi"] == "ipv6-unicast"
    assert set(AFIS) == {"ipv4-unicast", "ipv6-unicast", "evpn"}


# --- B3: protocol must be a name the drivers report ---------------------------------------------------

@pytest.mark.parametrize("proto,hint", [("ebgp", "bgp"), ("iBGP", "bgp"), ("bgp4", "bgp"), ("direct", "connected"),
                                        ("ospfv3", "ospf6"), ("statc", "static"), ("''", None), ("~", None),
                                        ("1", None), ("[bgp]", None)])
def test_b3_protocol_must_be_known(tmp_path, proto, hint):
    with pytest.raises(ConfigError, match=r"checks\[0\].*protocol .* is not a protocol name") as e:
        load(one_check(tmp_path, f"{{type: route, node: r1, prefix: 10.66.0.0/16, protocol: {proto}, present: false}}"))
    if hint:
        assert f"did you mean {hint!r}" in str(e.value)


def test_b3_protocol_is_case_insensitive(tmp_path):
    cfg = load(one_check(tmp_path, "{type: route, node: r1, prefix: 10.66.0.0/16, protocol: BGP}"))
    assert cfg.checks[0].params["protocol"] == "bgp"
    assert {"bgp", "connected", "local", "static", "ospf", "ospf6", "isis", "aggregate", "kernel"} <= set(PROTOCOLS)


# --- B4: unknown keys at the top level and under nodes.<name> -----------------------------------------

def test_b4_unknown_top_level_key_is_an_error(tmp_path):
    with pytest.raises(ConfigError, match=r"unknown top-level keys \['scenario'\]; did you mean 'scenarios'\?"):
        load(write(tmp_path, """
            lab: topo.clab.yml
            checks:
              - {type: ping, node: r1, target: 10.0.0.1}
            scenario:
              - link_down: {node: r1, interface: eth1}
                checks: [{type: ping, node: r1, target: 10.0.0.1}]
        """))


@pytest.mark.parametrize("key,hint", [("senarios", "scenarios"), ("check", "checks"), ("node", "nodes"),
                                      ("timout", "timeout"), ("labs", "lab"), ("hold", None), ("settle", None)])
def test_b4_top_level_typos(tmp_path, key, hint):
    with pytest.raises(ConfigError, match="unknown top-level keys") as e:
        load(write(tmp_path, f"lab: topo.clab.yml\n{key}: 1\nchecks:\n  - {{type: ping, node: r1, target: 10.0.0.1}}\n"))
    if hint:
        assert f"did you mean {hint!r}" in str(e.value)


@pytest.mark.parametrize("node_cfg,msg", [
    ("{drvier: frr}", r"nodes\.r1: unknown keys \['drvier'\]; did you mean 'driver'"),
    ("{setpu: [x]}", r"nodes\.r1: unknown keys \['setpu'\]; did you mean 'setup'"),
    ("{driver: frrr}", r"nodes\.r1\.driver: unknown driver 'frrr'; did you mean 'frr'"),
    ("{driver: FRR}", "unknown driver"),
    ("{}", "must be a mapping with driver"),
    ("~", "must be a mapping with driver"),
    ("frr", "must be a mapping with driver"),
    ("{setup: []}", "setup must be a list"),
])
def test_b4_node_settings_are_strict(tmp_path, node_cfg, msg):
    with pytest.raises(ConfigError, match=msg):
        load(write(tmp_path, f"lab: topo.clab.yml\nnodes:\n  r1: {node_cfg}\nchecks:\n  - {{type: ping, node: r1, target: 10.0.0.1}}\n"))


def test_driver_names_match_the_drivers():
    assert set(DRIVER_NAMES) == set(DRIVERS)


@pytest.mark.parametrize("scenario,msg", [
    ("{name: x, linkdown: {node: r1, interface: eth1}, checks: [{type: ping, node: r1, target: 10.0.0.1}]}",
     r"scenarios\[0\] \('x'\): unknown keys \['linkdown'\]; did you mean 'link_down'"),
    ("{link_down: {node: r1, interface: eth1, iface: eth2}, checks: [{type: ping, node: r1, target: 10.0.0.1}]}",
     r"link_down: unknown keys \['iface'\]"),
    ("{node_isolated: {node: r1, nod: r2}, checks: [{type: ping, node: r1, target: 10.0.0.1}]}",
     r"node_isolated: unknown keys \['nod'\]"),
    ("{inject_routes: {node: r1, count: 5, form: 10.0.0.0/24}, checks: [{type: ping, node: r1, target: 10.0.0.1}]}",
     r"inject_routes: unknown keys \['form'\]; did you mean 'from'"),
    ("{link_down: [], checks: [{type: ping, node: r1, target: 10.0.0.1}]}", "link_down is empty"),
    ("{node_isolated: r1, checks: [{type: ping, node: r1, target: 10.0.0.1, colour: red}]}",
     r"scenarios\[0\]\.checks\[0\]: unknown keys \['colour'\]"),
    ("{node_isolated: r1, checks: {type: ping, node: r1, target: 10.0.0.1}}", "checks must be a list"),
])
def test_scenario_and_fault_keys_are_strict(tmp_path, scenario, msg):
    with pytest.raises(ConfigError, match=msg):
        load(write(tmp_path, f"lab: topo.clab.yml\nchecks:\n  - {{type: ping, node: r1, target: 10.0.0.1}}\nscenarios:\n  - {scenario}\n"))


def test_unknown_check_key_suggests_the_right_one(tmp_path):
    with pytest.raises(ConfigError, match=r"checks\[0\] \('leak'\): unknown keys \['presnt'\] for type route; "
                                          r"did you mean 'present'"):
        load(one_check(tmp_path, "{type: route, name: leak, node: r1, prefix: 10.66.0.0/16, presnt: false}"))


def test_unknown_check_type_suggests(tmp_path):
    with pytest.raises(ConfigError, match="unknown type 'bgp_sesion'; did you mean 'bgp_session'"):
        load(one_check(tmp_path, "{type: bgp_sesion, node: r1, neighbor: 10.0.0.2}"))


# --- m1: duplicate YAML keys ---------------------------------------------------------------------------

def test_m1_duplicate_top_level_key_is_an_error(tmp_path):
    with pytest.raises(ConfigError, match=r"duplicate key 'checks' \(first defined on line 2\)"):
        load(write(tmp_path, """\
            lab: topo.clab.yml
            checks:
              - {type: route, node: r1, prefix: 10.66.0.0/16, present: false}
            checks:
              - {type: bgp_session, node: r1, neighbor: 10.0.0.2}
        """))


def test_m1_duplicate_key_inside_a_check_is_an_error(tmp_path):
    with pytest.raises(ConfigError, match="duplicate key 'present'"):
        load(write(tmp_path, """
            lab: topo.clab.yml
            checks:
              - type: route
                node: r1
                prefix: 10.66.0.0/16
                present: true
                present: false
        """))


def test_yaml_merge_keys_still_work():
    data = load_yaml("base: &b {type: route, node: r1}\nc: {<<: *b, node: r2}\n")
    assert data["c"] == {"type": "route", "node": "r2"}


def test_bad_yaml_is_a_config_error(tmp_path):
    with pytest.raises(ConfigError, match="not valid YAML"):
        load(write(tmp_path, "lab: topo.clab.yml\nchecks: [\n"))


# --- m3: numeric fields that made a check vacuous or were silently ignored ------------------------------

@pytest.mark.parametrize("check,msg", [
    ("{type: ping, node: r1, target: 10.0.0.1, min_replies: 0}", "min_replies must be an integer from 1 to count"),
    ("{type: ping, node: r1, target: 10.0.0.1, count: 2, min_replies: 3}", r"from 1 to count \(2\)"),
    ("{type: ping, node: r1, target: 10.0.0.1, count: 0}", "count must be an integer from 1"),
    ("{type: ping, node: r1, target: 10.0.0.1, count: '3'}", "count must be an integer from 1"),
    ("{type: ping, node: r1, target: 10.0.0.1, expect: failure, min_replies: 1}", "min_replies only applies"),
    ("{type: route, node: r1, prefix: 10.0.0.0/8, hold: 30}", "hold only applies to post-convergence checks"),
    ("{type: bgp_session, node: r1, neighbor: 10.0.0.2, hold: 30}", "hold only applies"),
    ("{type: bgp_prefixes, node: r1, neighbor: 10.0.0.2, min: 1, hold: 30}", "hold only applies"),
    ("{type: ping, node: r1, target: 10.0.0.1, hold: 30}", "hold only applies"),
    ("{type: bgp_prefixes, node: r1, neighbor: 10.0.0.2, min: 0}", "min: 0 on its own always passes"),
    ("{type: ping, node: r1, target: 10.0.0.1, timeout: '30'}", "timeout must be a positive number"),
    ("{type: ping, node: r1, target: 10.0.0.1, timeout: .inf}", "timeout must be a positive number"),
    ("{type: route, node: r1, prefix: 10.0.0.0/8, present: false, hold: 0}", "hold must be a positive number"),
    ("{type: route, node: r1, prefix: 10.0.0.0/8, present: false, hold: true}", "hold must be a positive number"),
    ("{type: route, node: r1, prefix: 10.0.0.0/8, present: false, active: false}", "active only applies"),
    ("{type: route, node: r1, prefix: 10.0.0.0/8, vrf: all}", "vrf 'all' is not supported"),
    ("{type: route, node: r1, prefix: 10.0.0.0/8, vrf: ALL}", "vrf 'all' is not supported"),
    ("{type: route, node: r1, prefix: 167772160}", "prefix must be an IP prefix written as a string"),
    ("{type: route, node: r1, prefix: 10.0.0.0/8, name: ''}", "name must be a non-empty string"),
    ("{type: route, node: '', prefix: 10.0.0.0/8}", "node must be a non-empty string"),
    ("{type: bgp_session, node: r1, neighbor: 10.0.0.2, state: ~}", "state must be one of"),
    ("{type: ping, node: r1, target: 10.0.0.1, expect: ~}", "expect must be"),
])
def test_m3_numeric_and_value_rules(tmp_path, check, msg):
    with pytest.raises(ConfigError, match=msg):
        load(one_check(tmp_path, check))


@pytest.mark.parametrize("body,msg", [
    ("lab: topo.clab.yml\ntimeout: 2m\nchecks: [{type: ping, node: r1, target: 10.0.0.1}]\n", "timeout must be"),
    ("lab: topo.clab.yml\ntimeout: 0\nchecks: [{type: ping, node: r1, target: 10.0.0.1}]\n", "timeout must be"),
    ("lab: topo.clab.yml\nnodes: [r1]\nchecks: [{type: ping, node: r1, target: 10.0.0.1}]\n", "nodes must be a mapping"),
    ("lab: topo.clab.yml\nnodes:\nchecks: [{type: ping, node: r1, target: 10.0.0.1}]\n", "nodes must be a mapping"),
    ("lab: topo.clab.yml\nchecks: {type: ping, node: r1, target: 10.0.0.1}\n", "checks must be a list"),
    ("lab: topo.clab.yml\nscenarios: []\nchecks: [{type: ping, node: r1, target: 10.0.0.1}]\n", "scenarios must be"),
    ("lab: topo.clab.yml\nscenarios:\nchecks: [{type: ping, node: r1, target: 10.0.0.1}]\n", "scenarios must be"),
    ("lab: 1\nchecks: [{type: ping, node: r1, target: 10.0.0.1}]\n", "lab must be a non-empty string"),
    ("lab: topo.clab.yml\nchecks: [{type: ping, node: r1, target: 10.0.0.1}, 5]\n", r"checks\[1\]: must be a mapping"),
])
def test_top_level_types(tmp_path, body, msg):
    with pytest.raises(ConfigError, match=msg):
        load(write(tmp_path, body))


def test_valid_numeric_values_still_load(tmp_path):
    cfg = load(write(tmp_path, """
        lab: topo.clab.yml
        timeout: 90.5
        checks:
          - {type: ping, node: r1, target: 10.0.0.1, count: 5, min_replies: 5, timeout: 10}
          - {type: ping, node: r1, target: 10.0.0.2, expect: failure, count: 1, hold: 20}
          - {type: bgp_prefixes, node: r1, neighbor: 10.0.0.2, min: 0, max: 5, hold: 15.5}
          - {type: bgp_prefixes, node: r1, neighbor: 10.0.0.2, exact: 0}
          - {type: route, node: r1, prefix: 10.0.0.0/8, present: false, hold: 20, vrf: 100}
          - {type: bgp_route, node: r1, prefix: 10.0.0.0/8, without_communities: ['1:1'], hold: 20}
          - {type: bgp_session, node: r1, neighbor: 10.0.0.2, state: Down, hold: 20}
    """))
    assert cfg.timeout == 90.5
    assert [c.hold for c in cfg.checks] == [None, 20.0, 15.5, None, 20.0, 20.0, 20.0]
    assert cfg.checks[4].params["vrf"] == "100"
    assert cfg.checks[6].params["state"] == "down"


# --- every config the project ships still validates -----------------------------------------------------

def _shipped_configs():
    files = sorted(ROOT.glob("examples/**/netdryrun.yml")) + sorted(ROOT.glob("packs/**/netdryrun.yml"))
    return [pytest.param(f, id=str(f.relative_to(ROOT))) for f in files]


@pytest.mark.parametrize("path", _shipped_configs())
def test_every_shipped_example_validates(path):
    assert load(path).checks


def _corpus_specs():
    out = []
    for corpus in (ROOT / "corpus", ROOT / "corpus" / "v2"):
        for spec in sorted((corpus / "specs").glob("*.yml")):
            out.append(pytest.param(spec, corpus / "base" / "topology.clab.yml", id=str(spec.relative_to(ROOT))))
    return out


@pytest.mark.parametrize("spec,topology", _corpus_specs())
def test_every_corpus_spec_validates(tmp_path, spec, topology):
    # corpus/run.py copies each spec next to the base topology before running it
    shutil.copy(topology, tmp_path / "topology.clab.yml")
    shutil.copy(spec, tmp_path / spec.name)
    assert load(tmp_path / spec.name).checks


@pytest.mark.parametrize("case", [pytest.param(p, id=str(p.relative_to(ROOT)))
                                  for p in sorted(ROOT.glob("corpus/**/cases/*.yml"))])
def test_every_corpus_case_file_parses_strictly(case):
    data = load_yaml(case.read_text(encoding="utf-8"), str(case))   # no duplicate keys
    assert isinstance(data, dict) and {"id", "expected", "edits"} <= set(data)


def test_there_is_something_to_validate():
    assert len(_shipped_configs()) >= 10 and len(_corpus_specs()) == 6


YAML_BLOCK = re.compile(r"^```ya?ml[^\n]*\n(.*?)^```", re.S | re.M)


def _doc_snippets():
    files = sorted((ROOT / "website" / "docs").rglob("*.md")) + [ROOT / "website" / "docs" / "llms-full.txt",
                                                                  ROOT / "README.md", ROOT / "AGENTS.md"]
    out = []
    for f in files:
        if not f.exists():
            continue
        text = f.read_text(encoding="utf-8")
        for m in YAML_BLOCK.finditer(text):
            line = text.count("\n", 0, m.start()) + 1
            out.append(pytest.param(m.group(1), id=f"{f.relative_to(ROOT)}:{line}"))
    return out


def _as_config(snippet: str):
    """The snippet as a whole netdryrun.yml, or None if it is not one (a workflow, a topology, ...)."""
    try:
        data = yaml.safe_load(snippet)
    except yaml.YAMLError:
        if re.search(r"^\s*(- )?type: (bgp_session|bgp_prefixes|route|bgp_route|ping)\b", snippet, re.M):
            raise
        return None
    ping = {"type": "ping", "node": "r1", "target": "10.0.0.1"}
    if isinstance(data, dict) and ("lab" in data or "checks" in data or "scenarios" in data) \
            and not {"jobs", "topology", "on"} & set(data):
        data = dict(data)
        data["lab"] = "topo.clab.yml"
        data.setdefault("checks", [ping])
        # a fragment that shows only how to write a fault leaves the scenario's checks out
        for sc in data.get("scenarios") or []:
            if isinstance(sc, dict):
                sc.setdefault("checks", [ping])
        return data
    if isinstance(data, dict) and data.get("type") in ("bgp_session", "bgp_prefixes", "route", "bgp_route", "ping"):
        return {"lab": "topo.clab.yml", "checks": [data]}
    if isinstance(data, list) and data and all(isinstance(x, dict) and "type" in x for x in data):
        return {"lab": "topo.clab.yml", "checks": data}
    return None


@pytest.mark.parametrize("snippet", _doc_snippets())
def test_every_docs_snippet_validates(tmp_path, snippet):
    """Every netdryrun.yml example in the docs must load with the real validator, so the docs can't drift."""
    data = _as_config(snippet)
    if data is None:
        pytest.skip("not a netdryrun.yml snippet")
    # the snippet's own text goes through the strict loader too (duplicate keys)
    load_yaml(snippet)
    (tmp_path / "topo.clab.yml").write_text(TOPO)
    (tmp_path / "netdryrun.yml").write_text(yaml.safe_dump(data, sort_keys=False))
    assert load(tmp_path / "netdryrun.yml").checks


def test_config_reference_snippets_are_covered():
    snippets = [p for p in _doc_snippets() if p.id.startswith("website/docs/reference/config.md")]
    assert sum(_as_config(p.values[0]) is not None for p in snippets) >= 7


# --- 0.3.2 cold review, finding 3: an IPv6 scope ID is copied into device CLI commands --------------------

@pytest.mark.parametrize("target", ['"fe80::1%x\nconfigure\nno router bgp 65000"', '"fe80::1%eth1 ; reload"',
                                    '"fe80::1%"', '"fe80::1%a\tb"'])
def test_ipv6_scope_id_must_be_an_interface_name(tmp_path, target):
    # ipaddress accepts any text after %, newlines included; the address reaches vtysh, Cli and sr_cli commands
    with pytest.raises(ConfigError, match=r"checks\[0\].*scope"):
        load(one_check(tmp_path, f"{{type: ping, node: r1, target: {target}}}"))


def test_ipv6_scope_id_with_an_interface_name_still_loads(tmp_path):
    cfg = load(one_check(tmp_path, '{type: ping, node: r1, target: "fe80::1%eth1.100"}'))
    assert cfg.checks[0].params["target"] == "fe80::1%eth1.100"


@pytest.mark.parametrize("check", [
    '{{type: bgp_session, node: r1, neighbor: "{a}"}}',
    '{{type: ping, node: r1, target: "{a}"}}',
    '{{type: ping, node: r1, target: "fe80::2", source: "{a}"}}',
    '{{type: bgp_route, node: r1, prefix: 10.0.0.0/24, next_hop: "{a}"}}',
])
@pytest.mark.parametrize("address", ["fe80::1%x\nconfigure",      # the scope is everything after the first %:
                                     "fe80::1%eth1%x\nconfigure",  # an interface name, then more text,
                                     "fe80::1%x\ny%eth1"])         # or text ending in an interface name
def test_every_address_key_refuses_a_scope_that_is_not_an_interface_name(tmp_path, check, address):
    with pytest.raises(ConfigError, match=r"checks\[0\].*scope"):
        load(one_check(tmp_path, check.format(a=address)))
