"""Repeated keys in device JSON are never "last one wins" (0.4 release finding, next-NOS session, 2026-10-30).

Junos's live route captures (tests/fixtures/junos_route_ibgp.txt, junos_route_ibgp_noexport.txt) repeat
`protocol-nh` inside one object: once at indent 16 and again at indent 24 with its resolution. Plain json.loads keeps
only the last, and the driver reads that key for a path's next hop: with two different next hops it would judge
one as if it were the only one. Junos's repeats are joined (each value is a list of elements); a repeat that isn't
a list, or next hops that disagree with none selected, is an error. Every other driver refuses a repeated key: no
FRR, EOS, SONiC or SR Linux capture has one, so a future one is an error, not silent data loss."""
import json
from pathlib import Path

import pytest

from netdryrun.drivers import junos
from netdryrun.drivers.base import DriverError, load_json

FIX = Path(__file__).parent / "fixtures"


def capture(name):
    text = (FIX / name).read_text(encoding="utf-8")
    return text[text.index("{"):]


def test_other_drivers_refuse_a_repeated_key():
    with pytest.raises(DriverError, match="repeated key"):
        load_json("show ip bgp summary | json", '{"vrfs": {"default": {}}, "vrfs": {}}')
    with pytest.raises(DriverError, match="repeated key"):
        load_json("show bgp vrf all neighbors json", '{"a": {"x": 1, "x": 2}}')
    assert load_json("show x", '{"a": [1], "b": {"c": 2}}') == {"a": [1], "b": {"c": 2}}


def protocol_nh(node) -> list[list]:
    """Every `protocol-nh` value in a parsed document."""
    if isinstance(node, dict):
        return [v for k, v in node.items() if k == "protocol-nh"] + [x for v in node.values() for x in protocol_nh(v)]
    if isinstance(node, list):
        return [x for v in node for x in protocol_nh(v)]
    return []


def test_junos_joins_a_repeated_list_element():
    for name in ("junos_route_ibgp.txt", "junos_route_ibgp_noexport.txt"):
        found = protocol_nh(junos.load_junos_json("show route", capture(name)))
        assert any(len(v) >= 2 for v in found), name      # both copies kept, not the last one only


def test_junos_refuses_a_repeated_key_that_is_not_a_list():
    with pytest.raises(DriverError, match="repeated key"):
        junos.load_junos_json("show route", '{"a": [{"x": 1}], "b": {"y": 1}, "b": {"y": 2}}')
    with pytest.raises(DriverError, match="repeated key 'b'"):      # a list repeated as an object: not joined
        junos.load_junos_json("show route", '{"b": [{"y": 1}], "b": {"y": 2}}')
    with pytest.raises(DriverError, match="repeated key 'b'"):
        junos.load_junos_json("show route", '{"b": {"y": 1}, "b": [{"y": 2}]}')


def _route_entry(*hops):
    return {"protocol-nh": [{"to": [{"data": to}], **({"selected-next-hop": [{}]} if sel else {})}
                            for to, sel in hops]}


def test_a_path_with_two_different_unselected_protocol_next_hops_is_refused():
    with pytest.raises(DriverError, match="next hop"):
        junos._next_hop("show route", _route_entry(("10.60.0.1", False), ("10.60.0.9", False)))
    assert junos._next_hop("show route", _route_entry(("10.60.0.1", False), ("10.60.0.1", False))) == "10.60.0.1"
    assert junos._next_hop("show route", _route_entry(("10.60.0.1", False), ("10.60.0.9", True))) == "10.60.0.9"


def test_the_live_ibgp_capture_still_reads_its_one_next_hop():
    """The repeat in the real capture names one next hop twice (10.60.0.1): joined, it reads the same as before."""
    data = junos.load_junos_json("show route", capture("junos_route_ibgp.txt"))
    assert {t["data"] for v in protocol_nh(data) for h in v for t in h.get("to", [])} == {"10.60.0.1"}
    assert json.loads(capture("junos_route_ibgp.txt"))   # plain json accepts it: the hook is what changes
