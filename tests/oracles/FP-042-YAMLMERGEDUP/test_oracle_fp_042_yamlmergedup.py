"""Oracle FP-042-YAMLMERGEDUP (angle-5 red team on 82fb052, B-RT-0073): a duplicate key inside a `<<` merge source.

The docs (website/docs/reference/config.md, "Duplicate keys are errors, at any depth: `duplicate key 'present' (first
defined on line 12)`") promise that netdryrun.yml never keeps the last of two equal keys silently. A mapping used only
as a YAML merge source is not checked: `_StrictLoader.construct_mapping` skips every `<<` entry, and PyYAML's
`flatten_mapping` copies the source's pairs without constructing that mapping, so its duplicate is never seen and the
last value wins. A leak guard template written `prefix: 0.0.0.0/0` with a pasted second `prefix: 192.0.2.0/24`
validates, and the guard against the default route is gone: every later run passes a leaked 0.0.0.0/0.

No device output is involved: the file below is the red team's case (candidates/B/RT-0073), and the inline-list form
(`<<: [{..}, {..}]`) is the same hole in a merge list. The rule: loading must raise ConfigError naming the duplicate,
as it does for the same mapping written anywhere else.
"""
from pathlib import Path

from netdryrun.config import ConfigError, load

TOPOLOGY = """\
name: t
topology:
  nodes:
    r1: {kind: linux, image: quay.io/frrouting/frr:10.4.1}
    r2: {kind: linux, image: quay.io/frrouting/frr:10.4.1}
  links:
    - endpoints: ["r1:eth1", "r2:eth1"]
"""

# the red team's file: the guard template is an inline merge source, used only through `<<`
INLINE_SOURCE = """\
lab: topology.clab.yml
checks:
  - type: bgp_session
    node: r1
    neighbor: 10.0.12.2
  - <<: &noleak
      type: route
      protocol: bgp
      present: false
      prefix: 0.0.0.0/0
      node: r1
      prefix: 192.0.2.0/24
  - <<: *noleak
    node: r2
"""

# the same duplicate inside one mapping of a `<<: [..]` merge list
LIST_SOURCE = """\
lab: topology.clab.yml
checks:
  - type: bgp_session
    node: r1
    neighbor: 10.0.12.2
  - <<: [{type: route, protocol: bgp, prefix: 0.0.0.0/0, prefix: 192.0.2.0/24}, {present: false}]
    node: r1
"""


def write(tmp_path: Path, checks: str) -> Path:
    (tmp_path / "topology.clab.yml").write_text(TOPOLOGY, encoding="utf-8")
    path = tmp_path / "netdryrun.yml"
    path.write_text(checks, encoding="utf-8")
    return path


def loads_or_refuses(path: Path):
    """The loaded check list, or None when the file is refused with a ConfigError naming the duplicate key."""
    try:
        cfg = load(path)
    except ConfigError as e:
        assert "duplicate" in str(e).lower() and "prefix" in str(e), f"refused, but not for the duplicate: {e}"
        return None
    return [(c.node, c.params.get("prefix")) for c in cfg.checks if c.type == "route"]


def test_duplicate_key_in_an_inline_merge_source_is_refused(tmp_path):
    loaded = loads_or_refuses(write(tmp_path, INLINE_SOURCE))
    assert loaded is None, (f"a merge source with `prefix:` twice loaded as {loaded}: the guard against 0.0.0.0/0 is "
                            "silently gone (docs: duplicate keys are errors, at any depth)")


def test_duplicate_key_in_a_merge_list_source_is_refused(tmp_path):
    loaded = loads_or_refuses(write(tmp_path, LIST_SOURCE))
    assert loaded is None, f"a `<<: [..]` source with `prefix:` twice loaded as {loaded}"

