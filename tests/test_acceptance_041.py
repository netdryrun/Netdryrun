"""False passes found by the 0.4.1 release gate's Layer 5b acceptance run (adversary angle), kept failing until fixed.
Each test reproduces one on fake state, with no lab; the red-team corpus lists them (tests/redteam)."""
from netdryrun.verify.engine import match
from netdryrun.verify.intent import parse_intent_text
from netdryrun.verify.snapshot import (AsPath, BgpAttrs, BgpPath, ItemKey, NextHop, NodeSnapshot, PathNextHop,
                                       RibEntry, Session, Snapshot)

P = "10.101.0.0/24"


def _attrs(as_path, nh):
    return BgpAttrs(origin="igp", as_path=AsPath.parse(as_path),
                    next_hops=(PathNextHop(nh, "global", True, True, 0, "eth1"),), local_pref=None, med=None,
                    weight=0, communities=(), ext_communities=(), large_communities=(), cluster_list=(),
                    originator_id=None, atomic_aggregate=False, aggregator=None)


def _rib(nh):
    hop = NextHop(nh, "eth1", None, True, True, True, False, False, False, "gateway", 1, (), None)
    return (RibEntry("bgp", None, True, True, 20, 0, None, 254, False, (hop,)),)


def _session(local):
    return Session(state="established", remote_as=65101, local_as=65000, afis=("ipv4-unicast",), local_address=local)


def test_with_from_pin_does_not_explain_a_path_from_an_undeclared_peer():
    """RT-0035. The intent approves the customer's block on edge1 learned *from the customer* (10.0.1.2, AS path
    65101). The change also opened the transit peer's inbound filter, so edge1 now holds a second path for the
    same prefix from 10.0.9.2 with a hijacker's origin AS 65666: not best today, best as soon as the customer
    session drops. The pin must explain only the path that matches it; 0.4.1 b61c325 explains both and says
    INTENT MATCHED."""
    base = {ItemKey("session", "edge1", "default", neighbor="10.0.1.2"): _session("10.0.1.1"),
            ItemKey("session", "edge1", "default", neighbor="10.0.9.2"): _session("10.0.9.1")}
    before = Snapshot({"edge1": NodeSnapshot("edge1", "frr", ("default",), dict(base), config=("router bgp 65000",))})
    after_items = dict(base)
    k = dict(kind="path", node="edge1", vrf="default", afi="ipv4", safi="unicast", prefix=P)
    after_items[ItemKey(**k, neighbor="10.0.1.2")] = BgpPath(_attrs("65101", "10.0.1.2"), True, False, True,
                                                             "external", "10.0.0.11")
    after_items[ItemKey(**k, neighbor="10.0.9.2")] = BgpPath(_attrs("65020 65666", "10.0.9.2"), False, False, True,
                                                             "external", "10.0.0.20")
    after_items[ItemKey("rib", "edge1", "default", "ipv4", "unicast", P, protocol="bgp")] = _rib("10.0.1.2")
    after = Snapshot({"edge1": NodeSnapshot("edge1", "frr", ("default",), after_items,
                                            config=("router bgp 65000", " neighbor 10.0.9.2 route-map ANY in"))})
    intent = parse_intent_text(f"""
intent:
  - prefix: {P}
    appears_on: [edge1]
    with: {{from: 10.0.1.2, as_path: "65101"}}
""")
    m = match(before, after, intent)
    assert m.status != "matched", "a path from an undeclared peer was explained by a pinned line"
    assert any(d.key.neighbor == "10.0.9.2" for d in m.undeclared)
