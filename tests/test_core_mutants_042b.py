"""Kill tests for the `core` group of the 0.4.2 mutation triage (run on 83478f2).

Inputs here are derived (built in this file), not captured from devices.
"""
import pytest

from netdryrun.config import ConfigError, load_yaml
from netdryrun.verify.engine import DiffItem, RouteView, _pinned_items
from netdryrun.verify.snapshot import ItemKey


def test_self_merging_source_with_a_duplicate_inside_a_mapping_key_reports_the_duplicate():
    """Kills config._StrictLoader._keys mutmut_11, _13, _14 (construct_object(key_node, deep=True) -> deep None,
    omitted, False).

    Derived input: mapping `a` merges itself and `b`, and one of its keys is a mapping with a duplicate key. _check_keys
    on `a` is still in progress when _keys(a) runs, so _keys constructs that key itself; deep=True builds the key
    mapping at once and its duplicate is reported. With deep off, construction is deferred and PyYAML recurses until
    RecursionError escapes load_yaml uncaught instead of a ConfigError naming the duplicate.
    """
    text = "b: &b {y: 1}\na: &a {? {k: 1, k: 2} : 1, <<: [*a, *b]}\n"
    with pytest.raises(ConfigError, match=r"duplicate key 'k'"):
        load_yaml(text)


P = "10.101.0.0/24"


def test_pinned_items_with_a_rib_item_whose_protocol_is_gone_from_the_view():
    """Kills verify.engine._pinned_items mutmut_29 and _31 (view.rib.get(protocol, ()) -> default None).

    Derived input: a static RIB item for the prefix (gone in the after view, so view.rib has no "static" key) beside a
    BGP one. The original treats the missing protocol as no entries; the mutants pass None to _rib_pins_ok, which
    iterates it and raises TypeError. With no pins every item is explained (the documented "No pins: every item").
    """
    static = ItemKey("rib", "edge1", "default", "ipv4", "unicast", P, protocol="static")
    bgp = ItemKey("rib", "edge1", "default", "ipv4", "unicast", P, protocol="bgp")
    items = [DiffItem(static, before=(), after=None), DiffItem(bgp, before=None, after=())]
    view = RouteView(rib={"bgp": ()})
    assert _pinned_items(items, view, {}) == {static, bgp}
