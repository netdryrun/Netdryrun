"""Guards for oracle FP-042-YAMLMERGEDUP: they pass before and after its fix.

The fast-fix gate needs every test in tests/oracles/FP-042-YAMLMERGEDUP/ to fail on the fix's parent, so the guards live
here. This file is in the oracle's `evidence:`, so the fix can't change it. Helpers come from the oracle's own module.

What must keep loading: a merge source without a duplicate (inline, anchored and in a `<<: [..]` list), and a key
written next to `<<` that overrides the merged one (standard YAML merge, documented in config.md: "a key written next to
it overrides the merged one"). What must keep failing: a plain duplicate key, and an anchored mapping with a duplicate
that is also used as a plain value (both refused today).
"""
import importlib.util
from pathlib import Path

import pytest

from netdryrun.config import ConfigError, load

_PATH = Path(__file__).resolve().parent / "oracles" / "FP-042-YAMLMERGEDUP" / "test_oracle_fp_042_yamlmergedup.py"
_SPEC = importlib.util.spec_from_file_location("oracle_fp_042_yamlmergedup", _PATH)
o = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(o)

HEAD = """\
lab: topology.clab.yml
checks:
  - type: bgp_session
    node: r1
    neighbor: 10.0.12.2
"""


def routes(tmp_path, body):
    cfg = load(o.write(tmp_path, HEAD + body))
    return sorted((c.node, c.params["prefix"], c.params.get("present", True)) for c in cfg.checks if c.type == "route")


def test_an_inline_merge_source_without_duplicates_loads(tmp_path):
    body = """\
  - <<: &noleak
      type: route
      protocol: bgp
      present: false
      prefix: 0.0.0.0/0
    node: r1
  - <<: *noleak
    node: r2
"""
    assert routes(tmp_path, body) == [("r1", "0.0.0.0/0", False), ("r2", "0.0.0.0/0", False)]


def test_a_merge_list_without_shared_keys_loads(tmp_path):
    body = """\
  - <<: [{type: route, protocol: bgp, prefix: 0.0.0.0/0}, {present: false}]
    node: r1
"""
    assert routes(tmp_path, body) == [("r1", "0.0.0.0/0", False)]


def test_a_key_next_to_the_merge_overrides_the_merged_one(tmp_path):
    body = """\
  - <<: &noleak
      type: route
      protocol: bgp
      present: false
      prefix: 0.0.0.0/0
    node: r1
  - <<: *noleak
    node: r1
    prefix: 192.0.2.0/24
"""
    assert routes(tmp_path, body) == [("r1", "0.0.0.0/0", False), ("r1", "192.0.2.0/24", False)]


@pytest.mark.parametrize("body", [
    "  - {type: route, node: r1, prefix: 0.0.0.0/0, prefix: 192.0.2.0/24, present: false}\n",
    "  - &g {type: route, node: r1, prefix: 0.0.0.0/0, prefix: 192.0.2.0/24, present: false}\n"
    "  - <<: *g\n    node: r2\n",
], ids=["plain", "anchored-and-used"])
def test_a_duplicate_outside_a_merge_only_source_is_still_refused(tmp_path, body):
    with pytest.raises(ConfigError, match="duplicate key"):
        load(o.write(tmp_path, HEAD + body))
