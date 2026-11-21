"""PyYAML 6.0.4 lost an override one `<<` level down for one-character keys (it keeps the first of two pairs whose key
strings are the same object, and CPython shares one-character strings) and reversed the order of a merge list for
longer keys (upstream issue 953). These tests pin both ends: a real config with a one-character node name, and the
installed PyYAML's own merge behaviour, so a PyYAML release with the same fault fails here and not for users.
"""
import textwrap

import pytest
import yaml

from netdryrun.config import ConfigError, load, load_yaml


def test_an_override_one_merge_level_down_wins_for_a_one_character_node_name(tmp_path):
    (tmp_path / "topo.clab.yml").write_text("name: t\ntopology:\n  nodes:\n    a: {}\n    b: {}\n")
    p = tmp_path / "netdryrun.yml"
    p.write_text(textwrap.dedent("""
        lab: topo.clab.yml
        nodes:
          <<: &tpl
            <<: &base
              a: {setup: [base-command]}
              b: {setup: [other-command]}
            a: {setup: [override-command]}
        checks:
          - {type: ping, node: a, target: 10.0.0.1}
    """))
    cfg = load(p)
    assert cfg.setup["a"] == ["override-command"]
    assert cfg.setup["b"] == ["other-command"]


def test_the_installed_pyyaml_lets_an_override_one_level_down_win_for_a_one_character_key():
    text = "base: &base {a: 1, bb: 2}\nsrc: &src\n  <<: *base\n  a: 9\n  bb: 8\none:\n  <<: *src\n"
    assert yaml.safe_load(text)["one"] == {"a": 9, "bb": 8}
    assert yaml.load(text, Loader=yaml.SafeLoader)["one"] == {"a": 9, "bb": 8}


def test_the_installed_pyyaml_lets_the_first_source_of_a_merge_list_win():
    # the YAML merge spec: the first mapping of the list wins. netdryrun refuses lists whose sources share a key (below)
    # so a config never reaches this, but it is how PyYAML is meant to behave and a change shows up here
    assert yaml.safe_load("m:\n  <<: [{kk: 1}, {kk: 2}]\n")["m"] == {"kk": 1}
    assert yaml.safe_load("m:\n  <<: [{k: 1}, {k: 2}]\n")["m"] == {"k": 1}


def test_a_merge_list_whose_sources_share_a_key_is_still_refused():
    for key in ("k", "kk"):
        with pytest.raises(ConfigError, match=f"merge sources share the key '{key}'"):
            load_yaml(f"m:\n  <<: [{{{key}: 1}}, {{{key}: 2}}]\n", "t.yml")
