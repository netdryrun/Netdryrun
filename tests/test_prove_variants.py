"""Variant generation for `netdryrun prove`: what is read from an FRR config, which variants a lab gets, in which
order the budget takes them, and that each variant's lines say exactly what it does."""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from netdryrun.prove import variants as V
from netdryrun.verify.frr import parse_running_config, qualified

import prove_helpers as h

CONFIGS = {n: h.file_config(n) for n in ("cust", "edge", "up")}

RICH = """frr defaults datacenter
hostname r1
!
interface eth1
 ip address 10.1.0.1/30
 ipv6 address 2001:db8:1::1/64
!
interface lo
 ip address 192.0.2.1/32
!
ip prefix-list FROM-A seq 5 deny 10.99.0.0/16 le 32
ip prefix-list FROM-A seq 10 permit 10.50.0.0/24
ip prefix-list BOGONS seq 5 permit 100.64.0.0/24
ip route 192.0.2.128/25 blackhole
!
route-map IN-A permit 10
 match ip address prefix-list FROM-A
 set local-preference 200
 set community 65000:1
exit
!
route-map OUT-A permit 10
 set local-preference 300
 set as-path prepend 65000 65000
exit
!
route-map IN-G permit 10
exit
!
router bgp 65000
 neighbor GRP peer-group
 neighbor GRP remote-as external
 neighbor 10.1.0.2 remote-as 65100
 neighbor 10.1.0.6 remote-as 65000
 neighbor 10.1.0.6 shutdown
 neighbor 10.1.0.10 peer-group GRP
 neighbor 2001:db8:1::2 remote-as 65200
 neighbor 10.1.0.14 remote-as internal
 !
 address-family ipv4 unicast
  network 192.0.2.128/25
  neighbor GRP route-map IN-G in
  neighbor 10.1.0.2 route-map IN-A in
  neighbor 10.1.0.2 route-map OUT-A out
  neighbor 10.1.0.2 maximum-prefix 100
  neighbor 10.1.0.14 prefix-list BOGONS in
 exit-address-family
 !
 address-family ipv6 unicast
  neighbor 2001:db8:1::2 route-map OUT-A out
 exit-address-family
exit
!
router bgp 65000 vrf RED
 neighbor 10.9.9.9 remote-as 65999
exit
"""


# ---------------------------------------------------------------------------------------------------------
# Reading the config
# ---------------------------------------------------------------------------------------------------------

def test_parse_reads_what_the_variants_need():
    c = V.parse(RICH)
    assert c.asn == "65000"
    assert c.ip_neighbors() == ["10.1.0.2", "10.1.0.6", "10.1.0.10", "10.1.0.14", "2001:db8:1::2"]
    assert c.groups == {"GRP"}
    assert c.neighbors["10.1.0.6"].shutdown and not c.neighbors["10.1.0.2"].shutdown
    assert c.maps_of("10.1.0.2") == {("ipv4", "in"): "IN-A", ("ipv4", "out"): "OUT-A"}
    assert c.maps_of("10.1.0.10") == {("ipv4", "in"): "IN-G"}            # inherited from its peer-group
    assert c.maps_of("2001:db8:1::2") == {("ipv6", "out"): "OUT-A"}
    assert c.lists_of("10.1.0.14") == {("ipv4", "in"): "BOGONS"}
    assert c.max_prefix("10.1.0.2") and not c.max_prefix("10.1.0.14") and not c.max_prefix("10.9.9.9")
    assert c.networks == {"192.0.2.128/25"} and c.statics == {"192.0.2.128/25"}
    assert [e.header for e in c.route_maps["IN-A"]] == ["route-map IN-A permit 10"]
    assert c.route_maps["IN-A"][0].lines == ["match ip address prefix-list FROM-A", "set local-preference 200",
                                            "set community 65000:1"]
    assert c.route_maps["IN-G"][0].lines == []
    assert c.prefix_lists["FROM-A"] == ["ip prefix-list FROM-A seq 5 deny 10.99.0.0/16 le 32",
                                        "ip prefix-list FROM-A seq 10 permit 10.50.0.0/24"]
    assert c.addresses() == {"10.1.0.1", "2001:db8:1::1", "192.0.2.1"}
    assert "10.9.9.9" not in c.neighbors        # another VRF's BGP instance is not read


def test_parse_takes_running_config_form_and_file_form_alike():
    assert V.parse(parse_running_config(RICH)).maps_of("10.1.0.2") == V.parse(RICH).maps_of("10.1.0.2")
    assert V.parse(RICH.splitlines()).asn == "65000"


def test_peer_group_settings_are_inherited():
    c = V.parse("router bgp 1\n neighbor G peer-group\n neighbor G remote-as 2\n neighbor G maximum-prefix 9\n"
                " neighbor 10.0.0.2 peer-group G\n address-family ipv4 unicast\n  neighbor G prefix-list P in\n")
    assert c.remote_as_of("10.0.0.2") == "2" and c.ebgp("10.0.0.2") and c.max_prefix("10.0.0.2")
    assert c.lists_of("10.0.0.2") == {("ipv4", "in"): "P"}
    c.neighbors["10.0.0.2"].remote_as = "1"
    assert c.remote_as_of("10.0.0.2") == "1" and not c.ebgp("10.0.0.2")


@pytest.mark.parametrize("ras, ebgp", [("65100", True), ("65000", False), ("external", True), ("internal", False),
                                       ("", False)])
def test_ebgp(ras, ebgp):
    c = V.parse(f"router bgp 65000\n neighbor 10.0.0.2 remote-as {ras}\n" if ras else
                "router bgp 65000\n neighbor 10.0.0.2 shutdown\n")
    assert c.ebgp("10.0.0.2") is ebgp


def test_parse_ignores_what_it_does_not_know():
    c = V.parse("! comment\n\ninterface eth9\n ip address not-an-address\n description x\n"
                "route-map BAD permit ten\n match x\nip prefix-list\nrouter bgp\n neighbor 1.2.3.4\n")
    assert c.asn == "" and c.route_maps == {} and c.prefix_lists == {} and c.interfaces == {"eth9": []}
    assert c.neighbors == {}


def test_address_family_ends_with_its_exit():
    c = V.parse("router bgp 1\n neighbor 10.0.0.2 remote-as 2\n address-family ipv6 unicast\n"
                "  neighbor 10.0.0.2 route-map X in\n exit-address-family\n neighbor 10.0.0.2 route-map Y in\n")
    assert c.maps_of("10.0.0.2") == {("ipv6", "in"): "X", ("ipv4", "in"): "Y"}


# ---------------------------------------------------------------------------------------------------------
# The customer-leak lab
# ---------------------------------------------------------------------------------------------------------

def ids(vs):
    return [v.id for v in vs]


def test_the_lab_gets_these_variants_in_this_order():
    assert ids(V.generate(CONFIGS, h.LINKS)) == [
        "customer_leak:cust:1", "customer_leak:cust:2", "customer_leak:edge:1", "customer_leak:edge:2",
        "customer_leak:up:1", "customer_leak:up:2",
        "import_filter:edge:CUST-IN permit 10:match ip address prefix-list CUST-IN:+leak:cust",
        "import_filter:edge:CUST-IN permit 10:match ip address prefix-list CUST-IN",
        "import_filter:edge:ip prefix-list CUST-IN seq 10 permit 10.10.0.0/24:+leak:cust",
        "import_filter:edge:ip prefix-list CUST-IN seq 10 permit 10.10.0.0/24",
        "session_down:cust:10.0.1.1", "session_down:edge:10.0.2.2",
        "link_down:cust:eth1--edge:eth1", "link_down:edge:eth2--up:eth1",
        "attribute_drift:cust:ALLOW-ALL permit 10:+set local-preference 50",
        "attribute_drift:edge:ALLOW-ALL permit 10:+set local-preference 50",
        "attribute_drift:edge:CUST-IN permit 10:+set local-preference 50",
        "attribute_drift:up:ALLOW-ALL permit 10:+set local-preference 50",
        "default_leak:cust:0.0.0.0/0", "default_leak:edge:0.0.0.0/0", "default_leak:up:0.0.0.0/0",
        "link_subnet_leak:cust:10.0.1.0/30", "link_subnet_leak:edge:10.0.1.0/30", "link_subnet_leak:edge:10.0.2.0/30",
        "link_subnet_leak:up:10.0.2.0/30",
    ]


def test_the_default_budget_takes_one_of_each_kind_first():
    run, rest = V.select(V.generate(CONFIGS, h.LINKS))
    assert [v.kind for v in run] == [*V.KINDS, "customer_leak"]
    assert run[1].id.endswith(":+leak:cust")   # the stranger's case, composed with a leak, is in the default run
    assert len(run) == V.DEFAULT_MAX and len(rest) == 25 - V.DEFAULT_MAX


def test_select_round_robin_and_filters():
    vs = V.generate(CONFIGS, h.LINKS)
    run, rest = V.select(vs, ["session_down", "link_down"], 3)
    assert ids(run) == ["session_down:cust:10.0.1.1", "link_down:cust:eth1--edge:eth1", "session_down:edge:10.0.2.2"]
    assert ids(rest) == ["link_down:edge:eth2--up:eth1"]
    run, rest = V.select(vs, ["link_down"], 100)
    assert len(run) == 2 and rest == []
    run, _ = V.select(vs, None, 1)
    assert ids(run) == ["customer_leak:cust:1"]
    assert V.select([], None, 8) == ([], [])


@pytest.mark.parametrize("kinds, maximum, msg", [(["nope"], 8, r"unknown variant kind\(s\) nope"), (None, 0, "at least 1"),
                                                 (None, True, "at least 1"), (None, 2.5, "at least 1"),
                                                 (None, -1, "at least 1")])
def test_select_refuses_bad_options(kinds, maximum, msg):
    with pytest.raises(V.VariantError, match=msg):
        V.select([], kinds, maximum)


def test_import_filter_lines():
    v = {x.id: x for x in V.generate(CONFIGS, h.LINKS)}
    m = v["import_filter:edge:CUST-IN permit 10:match ip address prefix-list CUST-IN"]
    assert m.apply == ("route-map CUST-IN permit 10", " no match ip address prefix-list CUST-IN", "exit")
    assert m.revert == ("route-map CUST-IN permit 10", " match ip address prefix-list CUST-IN", "exit")
    assert m.removes == ("route-map CUST-IN permit 10 > match ip address prefix-list CUST-IN",) and m.adds == ()
    assert m.soft_in == ("10.0.1.2",) and m.node == "edge" and m.companion is None
    p = v["import_filter:edge:ip prefix-list CUST-IN seq 10 permit 10.10.0.0/24"]
    assert p.apply == ("no ip prefix-list CUST-IN seq 10 permit 10.10.0.0/24",)
    assert p.revert == ("ip prefix-list CUST-IN seq 10 permit 10.10.0.0/24",)
    assert p.removes == ("ip prefix-list CUST-IN seq 10 permit 10.10.0.0/24",)
    c = v[m.id + ":+leak:cust"]
    assert c.companion.node == "cust" and c.companion.originates == ("100.64.0.0/24",)
    assert c.parts() == [c.companion, c] and m.parts() == [m]
    assert (c.apply, c.removes, c.node, c.kind) == (m.apply, m.removes, "edge", "import_filter")
    assert c.description.endswith("while cust announces 100.64.0.0/24")


def test_session_down_one_per_session():
    vs = [v for v in V.generate(CONFIGS, h.LINKS) if v.kind == "session_down"]
    s = vs[0]
    assert s.apply == ("router bgp 65010", " neighbor 10.0.1.1 shutdown", "exit")
    assert s.revert == ("router bgp 65010", " no neighbor 10.0.1.1 shutdown", "exit")
    assert s.adds == ("router bgp 65010 > neighbor 10.0.1.1 shutdown",)
    assert "(edge)" in s.description


def test_session_down_leaves_out_sessions_that_carry_nothing():
    counts = {("edge", "10.0.1.2", "ipv4-unicast"): 1, ("cust", "10.0.1.1", "ipv4-unicast"): 1,
              ("edge", "10.0.2.2", "ipv4-unicast"): 0, ("up", "10.0.2.1", "ipv4-unicast"): 0}
    vs = [v.id for v in V.generate(CONFIGS, h.LINKS, base_counts=counts) if v.kind == "session_down"]
    assert vs == ["session_down:cust:10.0.1.1"]
    counts[("up", "10.0.2.1", "ipv4-unicast")] = 3   # either end counts
    vs = [v.id for v in V.generate(CONFIGS, h.LINKS, base_counts=counts) if v.kind == "session_down"]
    assert vs == ["session_down:cust:10.0.1.1", "session_down:edge:10.0.2.2"]
    counts[("up", "10.0.2.1", "ipv6-unicast")] = 3
    counts[("up", "10.0.2.1", "ipv4-unicast")] = 0
    assert len([v for v in V.generate(CONFIGS, h.LINKS, base_counts=counts) if v.kind == "session_down"]) == 2


def test_rich_config_variants():
    vs = {v.id: v for v in V.generate({"r1": RICH}, [(("r1", "eth1"), ("x", "eth1"))])}
    # a shut neighbor is never shut again; one per configured IP neighbor otherwise
    assert sorted(i for i in vs if i.startswith("session_down")) == [
        "session_down:r1:10.1.0.10", "session_down:r1:10.1.0.14", "session_down:r1:10.1.0.2",
        "session_down:r1:2001:db8:1::2"]
    # inbound route-map match lines and the prefix-lists they (or `neighbor X prefix-list P in`) use
    assert sorted(i for i in vs if i.startswith("import_filter")) == [
        "import_filter:r1:IN-A permit 10:match ip address prefix-list FROM-A",
        "import_filter:r1:ip prefix-list BOGONS seq 5 permit 100.64.0.0/24",
        "import_filter:r1:ip prefix-list FROM-A seq 10 permit 10.50.0.0/24",
        "import_filter:r1:ip prefix-list FROM-A seq 5 deny 10.99.0.0/16 le 32"]
    # no lab FRR node owns the neighbors: no companion leak
    assert not any(v.companion for v in vs.values())
    drift = {i: v for i, v in vs.items() if i.startswith("attribute_drift")}
    assert sorted(drift) == [
        "attribute_drift:r1:IN-A permit 10:set community 65000:1",
        "attribute_drift:r1:IN-A permit 10:set local-preference 200",
        "attribute_drift:r1:IN-G permit 10:+set local-preference 50",
        "attribute_drift:r1:OUT-A permit 10:set as-path prepend 65000 65000"]   # no LP change on an outbound map
    lp = drift["attribute_drift:r1:IN-A permit 10:set local-preference 200"]
    assert lp.apply == ("route-map IN-A permit 10", " set local-preference 100", "exit")
    assert lp.revert == ("route-map IN-A permit 10", " set local-preference 200", "exit")
    assert lp.removes == ("route-map IN-A permit 10 > set local-preference 200",)
    assert lp.adds == ("route-map IN-A permit 10 > set local-preference 100",)
    assert lp.soft_in == ("10.1.0.2",)
    com = drift["attribute_drift:r1:IN-A permit 10:set community 65000:1"]
    assert com.apply == ("route-map IN-A permit 10", " no set community 65000:1", "exit") and com.adds == ()
    assert com.revert == ("route-map IN-A permit 10", " set community 65000:1", "exit")
    add = drift["attribute_drift:r1:IN-G permit 10:+set local-preference 50"]
    assert add.apply == ("route-map IN-G permit 10", " set local-preference 50", "exit")
    assert add.revert == ("route-map IN-G permit 10", " no set local-preference 50", "exit")
    assert add.removes == () and add.soft_in == ("10.1.0.10",)
    # an IPv6 neighbor: a ::/0 leak too; the node has eBGP: customer leaks
    assert "default_leak:r1:::/0" in vs and "default_leak:r1:0.0.0.0/0" in vs
    assert "customer_leak:r1:1" in vs
    # the link subnets of its links, IPv4 then IPv6; not the loopback (not on a link)
    assert [i for i in vs if i.startswith("link_subnet_leak")] == ["link_subnet_leak:r1:10.1.0.0/30",
                                                                    "link_subnet_leak:r1:2001:db8:1::/64"]
    assert vs["link_down:r1:eth1--x:eth1"].link == ("r1", "eth1")


def test_lp_drift_from_100():
    c = "route-map M permit 10\n set local-preference 100\nrouter bgp 1\n neighbor 10.0.0.2 remote-as 2\n" \
        " address-family ipv4 unicast\n  neighbor 10.0.0.2 route-map M in\n"
    v = next(v for v in V.generate({"r": c}) if v.kind == "attribute_drift")
    assert v.apply[1] == " set local-preference 200"


def test_a_deny_entry_gets_no_added_local_preference():
    c = "route-map M deny 10\nrouter bgp 1\n neighbor 10.0.0.2 remote-as 2\n address-family ipv4 unicast\n" \
        "  neighbor 10.0.0.2 route-map M in\n"
    assert not [v for v in V.generate({"r": c}) if v.kind == "attribute_drift"]


def test_originating_variants():
    v = {x.id: x for x in V.generate(CONFIGS, h.LINKS)}
    d = v["default_leak:edge:0.0.0.0/0"]
    assert d.originates == ("0.0.0.0/0",)
    assert d.apply == ("ip route 0.0.0.0/0 blackhole", "router bgp 65000", " address-family ipv4 unicast",
                       "  network 0.0.0.0/0", " exit-address-family", "exit")
    assert d.revert[0] == "no ip route 0.0.0.0/0 blackhole" and "  no network 0.0.0.0/0" in d.revert
    assert d.adds == ("ip route 0.0.0.0/0 blackhole", "router bgp 65000 > address-family ipv4 unicast > network 0.0.0.0/0")
    leak = v["customer_leak:cust:2"]
    assert leak.originates == ("100.64.0.0/24", "100.64.1.0/24") and len(leak.adds) == 4
    assert v["link_subnet_leak:up:10.0.2.0/30"].originates == ("10.0.2.0/30",)


def test_the_adds_are_what_the_running_config_shows():
    """Applied to the config, a variant's lines give exactly its removes and adds as the qualified diff."""
    for v in V.generate(CONFIGS, h.LINKS):
        for part in v.parts():
            if not (part.removes or part.adds):
                continue
            before = CONFIGS[part.node]
            after = h.edit_config(before, part.removes, part.adds)
            qb, qa = set(qualified(before)), set(qualified(after))
            assert sorted(qb - qa) == sorted(part.removes) and sorted(qa - qb) == sorted(part.adds), v.id


def test_nothing_already_configured_is_originated():
    c = "ip route 0.0.0.0/0 blackhole\ninterface eth1\n ip address 10.0.0.1/30\nrouter bgp 1\n" \
        " neighbor 10.0.0.2 remote-as 2\n address-family ipv4 unicast\n  network 10.0.0.0/30\n"
    vs = ids(V.generate({"r": c}, [(("r", "eth1"), ("x", "eth1"))]))
    assert not any(i.startswith(("default_leak", "link_subnet_leak")) for i in vs)


def test_no_bgp_no_bgp_variants():
    c = "interface eth1\n ip address 10.0.0.1/30\n"
    assert ids(V.generate({"r": c}, [(("r", "eth1"), ("x", "eth1"))])) == ["link_down:r:eth1--x:eth1"]
    c2 = "router bgp 1\n"   # BGP but no neighbor
    assert ids(V.generate({"r": c2})) == []
    c3 = "router bgp 1\n neighbor 10.0.0.2 remote-as 1\n"   # iBGP only: no customer to leak from
    assert not [i for i in ids(V.generate({"r": c3})) if i.startswith("customer_leak")]


def test_link_down_needs_an_frr_end():
    vs = V.generate({"a": "hostname a\n"}, [(("b", "eth1"), ("a", "eth2")), (("x", "eth1"), ("y", "eth1"))])
    assert [(v.id, v.link, v.node) for v in vs] == [("link_down:a:eth2--b:eth1", ("a", "eth2"), "a")]


def test_headroom_sizes_the_leak_inside_the_range():
    checks = [SimpleNamespace(type="bgp_prefixes", params={"node": "edge", "neighbor": "10.0.1.2", "min": 1, "max": 6}),
              SimpleNamespace(type="bgp_prefixes", params={"node": "edge", "neighbor": "10.0.2.2", "exact": 1}),
              SimpleNamespace(type="bgp_prefixes", params={"node": "edge", "neighbor": "10.0.2.2", "max": 9,
                                                           "vrf": "RED"}),
              SimpleNamespace(type="route", params={"node": "edge", "prefix": "10.0.0.0/8"})]
    counts = {("edge", "10.0.1.2", "ipv4-unicast"): 1, ("edge", "10.0.2.2", "ipv4-unicast"): 1}
    assert V.headroom(checks, counts) == {"edge": {"10.0.1.2": 5}}
    assert V.headroom(checks, {}) == {}
    assert V.headroom(checks, {("edge", "10.0.1.2", "ipv4-unicast"): 6}) == {}   # no room left
    vs = ids(V.generate(CONFIGS, h.LINKS, checks, counts))
    assert "customer_leak:cust:5" in vs and "customer_leak:up:5" not in vs     # cust owns 10.0.1.2
    v = next(v for v in V.generate(CONFIGS, h.LINKS, checks, counts) if v.id == "customer_leak:cust:5")
    assert "just inside the prefix-count range" in v.description and len(v.originates) == 5
    counts[("edge", "10.0.1.2", "ipv4-unicast")] = 4      # room for 2: the 1 and 2 variants already sit inside it
    assert not [i for i in ids(V.generate(CONFIGS, h.LINKS, checks, counts)) if i.startswith("customer_leak:cust:")
                and i not in ("customer_leak:cust:1", "customer_leak:cust:2")]
    big = [SimpleNamespace(type="bgp_prefixes", params={"node": "edge", "neighbor": "10.0.1.2", "min": 1,
                                                        "max": 1000})]
    assert f"customer_leak:cust:{V.MAX_LEAK}" in ids(V.generate(CONFIGS, h.LINKS, big, counts))


def test_leak_prefixes_step_around_what_the_lab_uses():
    import ipaddress as ip
    assert V.leak_prefixes(2) == ["100.64.0.0/24", "100.64.1.0/24"]
    used = [ip.ip_network("100.64.0.7/32"), ip.ip_network("100.64.0.0/10"), ip.ip_network("0.0.0.0/0"),
            ip.ip_network("2001:db8::/32"), ip.ip_network("100.64.2.0/24")]
    assert V.leak_prefixes(2, used) == ["100.64.1.0/24", "100.64.3.0/24"]
    assert V.leak_prefixes(0) == []
    every = [ip.ip_network("100.64.0.0/10").subnets(new_prefix=24)]
    assert V.leak_prefixes(1, list(every[0])) == []


def test_used_networks():
    checks = [SimpleNamespace(params={"node": "a", "prefix": "100.64.0.0/24"}),
              SimpleNamespace(params={"node": "a", "target": "100.64.1.9", "source": "bad source"})]
    nets = {str(n) for n in V.used_networks({"r": V.parse(RICH)}, checks)}
    assert {"100.64.0.0/24", "100.64.1.9/32", "10.1.0.0/30", "192.0.2.128/25", "100.64.0.0/24", "10.99.0.0/16",
            "2001:db8:1::/64"} <= nets
    assert "bad source" not in nets


def test_a_customer_leak_with_no_free_prefix_is_left_out():
    import ipaddress as ip
    checks = [SimpleNamespace(type="route", params={"prefix": str(n)}) for n in ip.ip_network("100.64.0.0/10").subnets(new_prefix=24)]
    vs = ids(V.generate(CONFIGS, h.LINKS, checks))
    assert not [i for i in vs if i.startswith("customer_leak")]
    assert not [i for i in vs if i.endswith(":+leak:cust")]


def test_owner_needs_exactly_one_node():
    a = V.parse("interface eth1\n ip address 10.0.0.1/30\n")
    b = V.parse("interface eth1\n ip address 10.0.0.1/30\n")
    assert V._owner("10.0.0.1", {"a": a}) == "a"
    assert V._owner("10.0.0.1", {"a": a, "b": b}) is None
    assert V._owner("10.0.0.9", {"a": a}) is None


def test_to_json():
    v = {x.id: x for x in V.generate(CONFIGS, h.LINKS)}
    j = v["import_filter:edge:CUST-IN permit 10:match ip address prefix-list CUST-IN:+leak:cust"].to_json()
    assert set(j) == {"id", "kind", "node", "description", "apply", "with"}
    assert j["with"]["originates"] == ["100.64.0.0/24"]
    assert v["link_down:cust:eth1--edge:eth1"].to_json() == {
        "id": "link_down:cust:eth1--edge:eth1", "kind": "link_down", "node": "cust",
        "description": "link cust:eth1 -- edge:eth1 down", "link": "cust:eth1"}
