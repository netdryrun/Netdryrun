"""RT-0073 (oracle FP-042-YAMLMERGEDUP): a duplicate key inside a mapping used only as a `<<` merge source is refused.

The check is in config._StrictLoader, which every YAML reader of a file that feeds a verdict goes through
(config.load_yaml: netdryrun.yml, the containerlab topology read by lab.py and verify, verify's intent file). These
tests kill: not checking merge sources at all, checking only a single source and not the sources in a `<<: [..]` list,
not following a source's own `<<` (nested merges), and checking a source again after PyYAML flattened it in place (a
false refusal of a legal override in a source used twice).
"""
import pytest

from netdryrun.config import ConfigError, load_yaml


def refused(text: str) -> str:
    with pytest.raises(ConfigError) as e:
        load_yaml(text, "t.yml")
    return str(e.value)


def test_a_duplicate_in_an_anchored_source_used_only_through_a_merge_is_refused():
    msg = refused("- <<: &g\n    x: 1\n    x: 2\n  y: 3\n- <<: *g\n")
    assert "duplicate key 'x'" in msg


def test_a_duplicate_in_one_source_of_a_merge_list_is_refused():
    assert "duplicate key 'p'" in refused("m:\n  <<: [{a: 1}, {p: 1, p: 2}]\n  z: 0\n")


def test_a_duplicate_in_the_source_of_a_source_is_refused():
    # the source merges another mapping that holds the duplicate: every merge depth is checked
    assert "duplicate key 'p'" in refused("m:\n  <<: {<<: {p: 1, p: 2}, q: 1}\n  z: 0\n")


def test_an_override_inside_a_source_used_twice_is_no_duplicate():
    # `&src` merges *base and overrides one of its keys (legal). PyYAML rewrites &src in place on its first use, so a
    # check run again on the rewritten node would see `a` twice and refuse a file that has no duplicate
    text = ("base: &base {a: 1, b: 2}\n"
            "src: &src\n  <<: *base\n  a: 9\n"
            "one:\n  <<: *src\n  c: 1\n"
            "two:\n  <<: *src\n  c: 2\n")
    data = load_yaml(text, "t.yml")
    assert data["one"] == {"a": 9, "b": 2, "c": 1}
    assert data["two"] == {"a": 9, "b": 2, "c": 2}


def test_a_source_without_a_duplicate_still_merges_and_an_explicit_key_still_overrides():
    data = load_yaml("- <<: &g {p: 0.0.0.0/0, present: false}\n  node: r1\n- <<: *g\n  p: 192.0.2.0/24\n", "t.yml")
    assert data == [{"p": "0.0.0.0/0", "present": False, "node": "r1"},
                    {"p": "192.0.2.0/24", "present": False}]


def test_a_topology_file_with_a_duplicate_in_a_merge_source_is_refused(tmp_path):
    # the same loader reads the containerlab topology (lab.py, verify): a kind template with a pasted second `image:`
    text = ("name: t\ntopology:\n  nodes:\n"
            "    r1:\n      <<: &k\n        kind: linux\n        image: a\n        image: b\n"
            "    r2:\n      <<: *k\n")
    assert "duplicate key 'image'" in refused(text)
