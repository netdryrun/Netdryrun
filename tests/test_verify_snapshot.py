"""verify's snapshot model and its FRR collection: normalisation and strict validation.

The FRR outputs in tests/fixtures/verify are live captures from FRR 10.4.1 (node edge1 of
tests/fixtures/verify-lab, by scripts/capture_verify_fixtures.py); each starts with a line naming the version, the
command and the date. Rerun the capture after an FRR upgrade."""
import json

import pytest

from netdryrun.drivers.base import DriverError
from netdryrun.verify import frr
from netdryrun.verify.snapshot import (AsPath, ItemKey, NodeSnapshot, Snapshot, SnapshotError, canon_community,
                                       canon_ext_communities, canon_large_community, canon_set, parse_asn)
from verify_helpers import FIX, base, fixture, fixture_commands, fixture_header, nh, rib

OUTPUTS = fixture_commands()          # command -> fixture file
ADJ_OUT_UP1 = frr.adj_command("default", "ipv4", "10.0.2.2", "out")
ADJ_IN_UP1 = frr.adj_command("default", "ipv4", "10.0.2.2", "in")


class FakeNode:
    def __init__(self, overrides=None, fail=()):
        self.texts = {cmd: fixture(name) for cmd, name in OUTPUTS.items()}
        self.texts.update(overrides or {})
        self.fail = set(fail)
        self.calls = []

    def __call__(self, node, argv):
        assert argv[:2] == ["vtysh", "-c"]
        cmd = argv[2]
        self.calls.append(cmd)
        if cmd in self.fail:
            return 1, "", "Exiting: failed to connect to any daemons."
        if cmd not in self.texts:
            raise AssertionError(f"unexpected command {cmd!r}")
        return 0, self.texts[cmd], ""


def collect(**kw):
    return frr.FrrCollector("edge1", FakeNode(**kw)).collect()


def edited(cmd, fn):
    data = json.loads(fixture(OUTPUTS[cmd]))
    fn(data)
    return {cmd: json.dumps(data)}


def test_every_verify_fixture_is_a_live_capture_of_exactly_what_the_collector_runs():
    files = sorted(f.name for f in FIX.iterdir())
    assert len(files) >= 15
    for name in files:
        m = fixture_header(name)
        assert m.group(1) == "FRRouting 10.4.1_git" and m.group(2) == "edge1", name
    fake = FakeNode()
    frr.FrrCollector("edge1", fake).collect()
    assert sorted(fake.calls) == sorted(OUTPUTS)          # no fixture unused, no command without one


# --- normalisation ---------------------------------------------------------------------------------------

def test_as_set_is_a_sorted_set_and_sequence_order_is_kept():
    a = AsPath.build([("as-sequence", [65003, 65001]), ("as-set", [65021, 65020, 65021])])
    b = AsPath.parse("65003 65001 {65020,65021}")
    assert a == b and a.render() == "65003 65001 {65020,65021}"
    assert AsPath.parse("65001 65003") != AsPath.parse("65003 65001")
    assert AsPath.build([("as-sequence", [1]), ("as-sequence", [2])]) == AsPath.parse("1 2")   # merged
    assert AsPath.parse("") == AsPath(())
    with pytest.raises(SnapshotError):
        AsPath.build([("as-weird", [1])])
    with pytest.raises(SnapshotError):
        AsPath.parse("65001 foo")


def test_asns_are_asplain():
    assert parse_asn("1.10") == 65546 and parse_asn(65546) == 65546 and parse_asn("65546") == 65546
    for bad in (True, -1, 2 ** 32, "x", "1.70000"):
        with pytest.raises(SnapshotError):
            parse_asn(bad)


@pytest.mark.parametrize("token,canonical", [
    ("no-export", "65535:65281"), ("NO_EXPORT", "65535:65281"), ("65535:65281", "65535:65281"),
    ("local-AS", "65535:65283"), ("no-export-subconfed", "65535:65283"), ("internet", "0:0"),
    ("blackhole", "65535:666"), ("graceful-shutdown", "65535:0"), ("065000:0100", "65000:100"),
    ("4259840100", "65000:100"),
])
def test_standard_communities_have_one_form(token, canonical):
    assert canon_community(token) == canonical


def test_large_and_extended_communities():
    assert canon_large_community("65000:001:2") == "65000:1:2"
    assert canon_ext_communities("RT:65002:100 LB:65002:125000 (1.000 Mbps) SoO:65000:1") == \
        ("lb:65002:125000", "rt:65002:100", "soo:65000:1")
    for bad in ("65000:1", "1:2:4294967296"):
        with pytest.raises(SnapshotError):
            canon_large_community(bad)
    with pytest.raises(SnapshotError):
        canon_ext_communities("RT:65002:100 garbage!")
    with pytest.raises(SnapshotError):
        canon_community("65536:1")


def test_ecmp_next_hops_are_a_set():
    a = canon_set([nh("10.0.0.2"), nh("10.0.0.1")])
    b = canon_set([nh("10.0.0.1"), nh("10.0.0.2"), nh("10.0.0.1")])
    assert a == b and len(a) == 2


def test_ecmp_order_in_frr_output_does_not_matter():
    entries = frr.parse_routes(fixture("route_v4.txt"), "ipv4")["default"][("198.18.200.0/24", "static")]
    assert len(entries[0].nexthops) == 2                                   # an ECMP static over both links to up1
    data = json.loads(fixture("route_v4.txt"))
    data["default"]["198.18.200.0/24"][0]["nexthops"].reverse()
    data["default"]["198.18.200.0/24"][0]["uptime"] = "00:09:59"           # noise
    data["default"]["198.18.200.0/24"][0]["nexthops"][0]["interfaceIndex"] = 99   # ifindex varies across boots
    again = frr.parse_routes(json.dumps(data), "ipv4")["default"][("198.18.200.0/24", "static")]
    assert entries == again


def test_absent_med_and_local_pref_stay_absent():
    paths = frr.parse_bgp_table(fixture("bgp_v4_detail.txt"), "ipv4")
    ibgp = paths["default"][("198.18.0.0/24", "10.255.0.2", 0)]
    assert ibgp.attrs.med == 0 and ibgp.attrs.local_pref == 100
    local = paths["default"][("192.0.2.0/24", "local", 0)]
    assert local.attrs.local_pref is None and local.attrs.med == 0 and local.peer_type == "local"
    ebgp = paths["cust"][("10.201.0.0/24", "10.10.1.2", 0)]
    assert ebgp.attrs.local_pref is None and ebgp.attrs.weight is None
    received = frr.parse_adj(fixture(OUTPUTS[ADJ_IN_UP1]), ADJ_IN_UP1, "ipv4", "in")
    assert received[("10.100.0.0/23", 0)].med is None and received[("203.0.113.0/24", 0)].med == 50


# --- FRR collection --------------------------------------------------------------------------------------

def test_collect_reads_every_vrf_afi_protocol_and_session():
    ns = collect()
    assert ns.vrfs == ("cust", "default")
    kinds = {}
    for k in ns.items:
        kinds.setdefault(k.kind, set()).add((k.vrf, k.afi))
    assert kinds["session"] == {("default", ""), ("cust", "")}
    assert {("default", "ipv4"), ("default", "ipv6"), ("cust", "ipv4")} <= kinds["rib"]
    assert kinds["path"] == {("default", "ipv4"), ("default", "ipv6"), ("cust", "ipv4")}
    assert kinds["adj_out"] == {("default", "ipv4"), ("cust", "ipv4")}            # TO-PEER sends nothing over IPv6
    assert kinds["adj_in"] == {("default", "ipv4"), ("default", "ipv6")}
    protos = {k.protocol for k in ns.items if k.kind == "rib"}
    assert protos == {"bgp", "connected", "kernel", "local", "ospf", "static"}
    s = ns.items[ItemKey("session", "edge1", "default", neighbor="10.0.2.2")]
    assert s.established and s.local_address == "10.0.2.1" and s.afis == ("ipv4-unicast",)
    assert s.soft_reconfig_in == ("ipv4-unicast",) and dict(s.prefix_counts) == {"ipv4-unicast": 1}
    v6 = ns.items[ItemKey("session", "edge1", "default", neighbor="2001:db8:11::2")]
    assert v6.afis == ("ipv6-unicast",) and v6.local_address == "2001:db8:11::1"
    ibgp = ns.items[ItemKey("session", "edge1", "default", neighbor="10.255.0.2")]
    assert ibgp.local_address == "192.0.2.1" and ibgp.remote_as == ibgp.local_as == 65000
    down = ns.items[ItemKey("session", "edge1", "default", neighbor="10.0.9.2")]
    assert down.state in ("active", "connect", "idle") and not down.established and down.local_address is None
    # the management address (Docker's, on eth0) is not in the snapshot; the management subnet is
    mgmt = [k for k in ns.items if k.kind == "rib" and k.protocol == "local" and k.prefix.startswith(("172.20.", "3fff:"))]
    assert mgmt == []
    assert ItemKey("rib", "edge1", "default", "ipv4", "unicast", "172.20.20.0/24", protocol="connected") in ns.items


def test_no_route_ceiling_every_route_is_in_the_snapshot():
    """verify has no route ceiling (record keeps 50 per node; verify keeps everything): 20,000 extra routes are
    20,000 extra items, each compared."""
    data = json.loads(fixture("route_v4.txt"))
    template = data["default"]["192.0.2.0/24"][0]
    for i in range(20000):
        p = f"10.{128 + i // 256}.{i % 256}.0/24"
        data["default"][p] = [{**template, "prefix": p}]
    ns = collect(overrides={frr.ROUTE_CMDS["ipv4"]: json.dumps(data)})
    generated = {f"10.{128 + i // 256}.{i % 256}.0/24" for i in range(20000)}
    extra = [k for k in ns.items if k.kind == "rib" and k.vrf == "default" and k.prefix in generated]
    assert len(extra) == 20000


def test_collect_keeps_raw_output_for_every_command():
    fake = FakeNode()
    ns = frr.FrrCollector("edge1", fake).collect()
    assert [r["cmd"] for r in ns.raw] == [f"vtysh -c '{c}'" for c in fake.calls]
    assert all(r["rc"] == 0 and r["output"] for r in ns.raw)


def test_received_only_and_selected_routes():
    ns = collect()
    from_up1 = {k.prefix for k in ns.items if k.kind == "adj_in" and k.neighbor == "10.0.2.2"}
    # 0/0 is received only (filtered inbound); up1 also sends edge1's own routes back (dropped: AS loop)
    assert from_up1 == {"0.0.0.0/0", "10.100.0.0/23", "192.0.2.0/24", "203.0.113.0/24"}
    assert not any(k.prefix == "0.0.0.0/0" and (k.kind == "path" or k.protocol == "bgp") for k in ns.items)
    statics = ns.items[ItemKey("rib", "edge1", "default", "ipv4", "unicast", "192.0.2.0/24", protocol="static")]
    assert [(e.distance, e.selected, e.fib) for e in sorted(statics, key=lambda e: e.distance)] == \
        [(1, True, True), (250, False, False)]


def test_recursive_next_hop_keeps_its_resolver():
    entries = frr.parse_routes(fixture("route_v4.txt"), "ipv4")["default"][("198.18.0.0/24", "bgp")]
    (hop,) = entries[0].nexthops
    assert hop.recursive and hop.ip == "10.255.0.9" and [r.ip for r in hop.resolved_via] == ["10.0.4.2"]


def test_link_local_next_hop_keeps_its_interface():
    entries = frr.parse_routes(fixture("route_v6.txt"), "ipv6")["default"][("2001:db8:20::/48", "bgp")]
    (hop,) = entries[0].nexthops
    assert hop.ip == "fe80::" and hop.interface == "eth3"
    assert "fe80::a8c1:ab" in fixture("route_v6.txt")                     # the address itself stays in the evidence


def test_every_bgp_path_with_all_attributes():
    paths = frr.parse_bgp_table(fixture("bgp_v4_detail.txt"), "ipv4")["default"]
    up = paths[("203.0.113.0/24", "10.0.2.2", 0)]
    assert up.best and up.peer_type == "external" and up.attrs.med == 50 and up.attrs.local_pref == 100
    assert up.attrs.communities == ("65200:100", "65200:200")
    assert up.attrs.large_communities == ("65200:1:1", "65200:2:2")
    assert up.attrs.ext_communities == ("lb:65200:125000000", "rt:65200:100")
    peer = paths[("198.51.100.0/24", "10.0.3.2", 0)]
    assert peer.attrs.communities == ("65300:7", "65535:65281")             # no-export, canonical
    ibgp = paths[("198.18.0.0/24", "10.255.0.2", 0)]
    assert ibgp.attrs.cluster_list == ("10.255.0.2",) and ibgp.attrs.originator_id == "10.255.0.9"
    assert ibgp.peer_type == "internal" and ibgp.attrs.next_hops[0].igp_metric == 20
    agg = paths[("10.100.0.0/23", "local", 0)]
    assert agg.flags == ("aggregated",) and agg.attrs.aggregator == "65000:192.0.2.1"
    wide = paths[("192.0.0.0/2", "local", 0)]
    assert wide.attrs.as_path.render() == "{65200,65300}" and wide.flags == ("aggregated",)
    cust = frr.parse_bgp_table(fixture("bgp_v4_detail.txt"), "ipv4")["cust"]
    assert list(cust) == [("10.201.0.0/24", "10.10.1.2", 0)]
    v6 = frr.parse_bgp_table(fixture("bgp_v6_detail.txt"), "ipv6")["default"]
    (hop,) = v6[("2001:db8:20::/48", "2001:db8:11::2", 0)].attrs.next_hops
    assert (hop.ip, hop.scope) == ("fe80::", "link-local")


def test_an_aggregate_path_keeps_its_aggregated_flag():
    """Live FRR 10.4.1 marks a locally aggregated path `"aggregated": true` (found on the first live capture,
    where the strict parser refused it): a flag that is compared, so a route that becomes or stops being an
    aggregate is a difference."""
    path = {"aspath": {"string": "65100", "segments": [{"type": "as-sequence", "list": [65100]}], "length": 1},
            "aggregatorAs": 65000, "aggregatorId": "192.0.2.1", "origin": "IGP", "metric": 0, "weight": 32768,
            "valid": True, "aggregated": True, "local": True, "bestpath": {"overall": True},
            "nexthops": [{"ip": "0.0.0.0", "afi": "ipv4", "accessible": True, "used": True}],
            "peer": {"peerId": "0.0.0.0", "routerId": "192.0.2.1"}}
    text = json.dumps({"default": {"vrfName": "default", "routes": {"10.100.0.0/23": [path]}}})
    agg = frr.parse_bgp_table(text, "ipv4")["default"][("10.100.0.0/23", "local", 0)]
    assert agg.flags == ("aggregated",) and agg.attrs.aggregator == "65000:192.0.2.1"
    plain = frr.parse_bgp_table(text.replace('"aggregated": true, ', ""), "ipv4")["default"][("10.100.0.0/23", "local", 0)]
    assert plain.flags == () and plain != agg
    with pytest.raises(SnapshotError):
        frr.parse_bgp_table(text.replace('"aggregated": true', '"aggregated": "yes"'), "ipv4")


# Received routes come from the plain listing. Live FRR 10.4.1's `received-routes detail json` prints the path in
# the BGP table, after inbound policy (an inbound `set metric 10` showed MED 10 where the peer sent 50, and a
# route looped back from up1 showed edge1's own aggregate), so verify reads the plain listing, which is what the
# neighbor sent. Lines from a live capture (tests/fixtures/verify-lab, FRR 10.4.1).
RECEIVED_V4 = ('{"bgpTableVersion":8,"bgpLocalRouterId":"192.0.2.1","defaultLocPrf":100,"localAS":65000,"receivedRoutes": '
               '{"0.0.0.0/0":{"addrPrefix":"0.0.0.0","prefixLen":0,"network":"0.0.0.0/0","nextHop":"10.0.2.2","metric":0,'
               '"weight":0,"path":"65200","origin":"IGP","valid":true,"best":true},"10.100.0.0/23":{"addrPrefix":"10.100.0.0",'
               '"prefixLen":23,"network":"10.100.0.0/23","nextHop":"10.0.2.2","weight":0,"path":"65200 65000 65100",'
               '"origin":"IGP","valid":true,"best":true},"203.0.113.0/24":{"addrPrefix":"203.0.113.0","prefixLen":24,'
               '"network":"203.0.113.0/24","nextHop":"10.0.2.2","metric":50,"weight":0,"path":"65200","origin":"IGP",'
               '"valid":true,"best":true}}\n,"totalPrefixCounter":3,"filteredPrefixCounter":1}')
RECEIVED_V6 = ('{"bgpTableVersion":1,"bgpLocalRouterId":"192.0.2.1","defaultLocPrf":100,"localAS":65000,"receivedRoutes": '
               '{"2001:db8:20::/48":{"addrPrefix":"2001:db8:20::","prefixLen":48,"network":"2001:db8:20::/48",'
               '"nextHopGlobal":"fe80::a8c1:abff:fec0:c62b","metric":0,"weight":0,"path":"65300","origin":"IGP",'
               '"valid":true,"best":true}}\n,"totalPrefixCounter":1,"filteredPrefixCounter":0}')


# Two boots of the same lab with the same configs (a live `netdryrun verify` with a comment-only change,
# FRR 10.4.1) differed in 31 items: every node's management address (Docker assigns them per boot) and an IPv6
# link-local next hop (containerlab gives interfaces random MAC addresses). Neither is behavior.

def _route(prefix, protocol, hops, **kw):
    return {"prefix": prefix, "prefixLen": int(prefix.split("/")[1]), "protocol": protocol, "vrfId": 0,
            "vrfName": "default", "selected": True, "destSelected": True, "distance": 0, "metric": 0,
            "installed": True, "table": 254, "nexthops": hops, **kw}


def test_the_management_address_is_not_compared():
    eth = lambda name: {"flags": 3, "fib": True, "directlyConnected": True, "interfaceIndex": 2,   # noqa: E731
                        "interfaceName": name, "active": True}
    table = {"172.20.20.4/32": [_route("172.20.20.4/32", "local", [eth("eth0")])],
             "172.20.20.0/24": [_route("172.20.20.0/24", "connected", [eth("eth0")])],
             "10.0.1.1/32": [_route("10.0.1.1/32", "local", [eth("eth1")])]}
    got = frr.parse_routes(json.dumps({"default": table}), "ipv4")["default"]
    assert sorted(got) == [("10.0.1.1/32", "local"), ("172.20.20.0/24", "connected")]
    # only in the default VRF, where containerlab puts it
    got = frr.parse_routes(json.dumps({"default": {}, "mgmt": {"172.20.20.4/32": [
        {**_route("172.20.20.4/32", "local", [eth("eth0")]), "vrfName": "mgmt"}]}}), "ipv4")
    assert list(got["mgmt"]) == [("172.20.20.4/32", "local")]


def test_which_link_local_subnet_zebra_selects_is_not_compared():
    """Every interface has a connected fe80::/64; zebra marks one selected, in interface creation order (eth0 on
    one boot of peer1, eth1 on the next). Each entry is still compared by interface and FIB state."""
    def table(selected_iface, ifaces=("eth0", "eth1")):
        entries = [_route("fe80::/64", "connected", [{"flags": 3, "fib": True, "directlyConnected": True,
                                                      "interfaceIndex": 2, "interfaceName": i, "active": True}],
                          selected=i == selected_iface) for i in ifaces]
        return frr.parse_routes(json.dumps({"default": {"fe80::/64": entries}}), "ipv6")["default"]
    assert table("eth0") == table("eth1")
    assert table("eth0") != table("eth0", ifaces=("eth0", "eth2"))
    other = [_route("2001:db8::/64", "connected", [{"interfaceName": "eth1", "directlyConnected": True}], selected=s)
             for s in (True, False)]
    a = frr.parse_routes(json.dumps({"default": {"2001:db8::/64": other}}), "ipv6")
    b = frr.parse_routes(json.dumps({"default": {"2001:db8::/64": other[::-1]}}), "ipv6")
    assert a == b and [e.selected for e in a["default"][("2001:db8::/64", "connected")]].count(True) == 1


def test_ipv6_link_local_next_hops_compare_by_interface_and_source():
    def rib(ll, iface="eth3"):
        hop = {"flags": 3, "fib": True, "ip": ll, "afi": "ipv6", "interfaceIndex": 4, "interfaceName": iface,
               "active": True, "weight": 1}
        text = json.dumps({"default": {"2001:db8:20::/48": [_route("2001:db8:20::/48", "bgp", [hop], distance=20)]}})
        return frr.parse_routes(text, "ipv6")["default"][("2001:db8:20::/48", "bgp")]
    assert rib("fe80::a8c1:abff:feca:b96a") == rib("fe80::a8c1:abff:fe04:64fd")
    assert rib("fe80::a8c1:abff:feca:b96a") != rib("fe80::a8c1:abff:feca:b96a", iface="eth4")
    assert rib("2001:db8:11::2") != rib("2001:db8:11::3")                  # global next hops keep their address

    def path(ll):
        p = {"aspath": {"string": "65300", "segments": [{"type": "as-sequence", "list": [65300]}], "length": 1},
             "origin": "IGP", "valid": True, "bestpath": {"overall": True},
             "nexthops": [{"ip": ll, "afi": "ipv6", "scope": "link-local", "linkLocalOnly": True, "accessible": True,
                           "used": True}],
             "peer": {"peerId": "2001:db8:11::2", "routerId": "198.51.100.1", "type": "external"}}
        text = json.dumps({"default": {"routes": {"2001:db8:20::/48": [p]}}})
        return frr.parse_bgp_table(text, "ipv6")["default"][("2001:db8:20::/48", "2001:db8:11::2", 0)]
    assert path("fe80::a8c1:abff:feca:b96a") == path("fe80::a8c1:abff:fe04:64fd")
    received = RECEIVED_V6.replace("fe80::a8c1:abff:fec0:c62b", "fe80::1")
    cmd = frr.adj_command("default", "ipv6", "2001:db8:11::2", "in")
    assert frr.parse_adj(received, cmd, "ipv6", "in") == frr.parse_adj(RECEIVED_V6, cmd, "ipv6", "in")


def test_a_path_queued_for_processing_is_the_same_path():
    """Live FRR 10.4.1 (r9, during a verify run) printed `"processScheduled": true` on a path whose destination
    was queued for best-path selection: a transient state of bgpd, not an attribute (two snapshots taken
    `settle` apart must still be identical before verify trusts either)."""
    path = {"aspath": {"string": "65100", "segments": [{"type": "as-sequence", "list": [65100]}], "length": 1},
            "origin": "IGP", "metric": 0, "locPrf": 100, "valid": True, "bestpath": {"overall": True},
            "nexthops": [{"ip": "192.0.2.1", "afi": "ipv4", "metric": 20, "accessible": True, "used": True}],
            "peer": {"peerId": "10.255.0.2", "routerId": "10.255.0.2", "type": "internal"}}
    def parse(p):
        text = json.dumps({"default": {"routes": {"10.100.0.0/24": [p]}}})
        return frr.parse_bgp_table(text, "ipv4")["default"][("10.100.0.0/24", "10.255.0.2", 0)]
    assert parse({**path, "processScheduled": True}) == parse(path)


def test_a_next_hops_import_check_mode_is_not_compared():
    """Live FRR 10.4.1 (cust1, on one of two boots of the same configs) printed `"importCheckEnabled": true` on a
    path's next hop: how bgpd tracks that next hop, whose outcome is `accessible` (compared)."""
    def parse(extra, accessible=True):
        p = {"aspath": {"string": "65000", "segments": [{"type": "as-sequence", "list": [65000]}], "length": 1},
             "origin": "IGP", "valid": True, "bestpath": {"overall": True},
             "nexthops": [{"ip": "10.0.1.1", "afi": "ipv4", "accessible": accessible, "used": True, **extra}],
             "peer": {"peerId": "10.0.1.1", "routerId": "192.0.2.1", "type": "external"}}
        text = json.dumps({"default": {"routes": {"192.0.0.0/2": [p]}}})
        return frr.parse_bgp_table(text, "ipv4")["default"][("192.0.0.0/2", "10.0.1.1", 0)]
    assert parse({"importCheckEnabled": True}) == parse({})
    assert parse({"importCheckEnabled": True}, accessible=False) != parse({})


def test_a_redistributed_paths_fib_installed_flag_is_compared():
    """Live FRR 10.4.1 (corpus case 18, `redistribute connected` on pe1) printed `"fibInstalled": true` on the
    redistributed paths; the parser refused it."""
    def parse(extra):
        p = {"aspath": {"string": "Local", "segments": [], "length": 0}, "origin": "incomplete", "metric": 0,
             "weight": 32768, "valid": True, "sourced": True, "bestpath": {"overall": True},
             "nexthops": [{"ip": "0.0.0.0", "afi": "ipv4", "metric": 0, "accessible": True, "used": True}],
             "peer": {"peerId": "0.0.0.0", "routerId": "10.255.0.1"}, **extra}
        text = json.dumps({"default": {"routes": {"10.0.1.0/30": [p]}}})
        return frr.parse_bgp_table(text, "ipv4")["default"][("10.0.1.0/30", "local", 0)]
    assert parse({"fibInstalled": True}).flags == ("fibInstalled",) and parse({}).flags == ()


def test_a_path_from_a_route_reflector_client_keeps_its_flag():
    """Live FRR 10.4.1 marks a route reflector's paths from its clients `"rxedFromRrClient": true` (rr1 in the
    capture lab; the parser refused it, so verify could not run on a lab with a route reflector)."""
    path = {"aspath": {"string": "65100", "segments": [{"type": "as-sequence", "list": [65100]}], "length": 1},
            "rxedFromRrClient": True, "origin": "IGP", "metric": 0, "locPrf": 100, "valid": True,
            "bestpath": {"overall": True}, "nexthops": [{"ip": "192.0.2.1", "afi": "ipv4", "metric": 10,
                                                          "accessible": True, "used": True}],
            "peer": {"peerId": "192.0.2.1", "routerId": "192.0.2.1", "type": "internal"}}
    text = json.dumps({"default": {"vrfName": "default", "routes": {"10.100.0.0/24": [path]}}})
    p = frr.parse_bgp_table(text, "ipv4")["default"][("10.100.0.0/24", "192.0.2.1", 0)]
    assert p.flags == ("rxedFromRrClient",)


# A default route sent with `neighbor X default-originate` is not in advertisedRoutes: FRR 10.4.1 names it in
# "bgpOriginatingDefaultNetwork" and counts it in totalPrefixCounter (up1 in the capture lab). Dropping the key
# would hide a default route leaked to a neighbor outside the lab.
ORIGINATING_DEFAULT = ('{"bgpTableVersion":3,"bgpLocalRouterId":"203.0.113.1","defaultLocPrf":100,"localAS":65200,'
                       '"bgpOriginatingDefaultNetwork":"0.0.0.0/0","advertisedRoutes": {"192.0.2.0/24":{"prefix":'
                       '"192.0.2.0/24","version":2,"advertisedTo":{"10.0.2.1":{"hostname":"edge1"}},"pathCount":1,'
                       '"paths":[{"aspath":{"string":"65000","segments":[{"type":"as-sequence","list":[65000]}],'
                       '"length":1},"origin":"IGP","valid":true,"version":2,"bestpath":{"bestpathFromAs":65000,'
                       '"overall":true,"selectionReason":"First path received"},"nexthops":[{"ip":"0.0.0.0",'
                       '"hostname":"edge1","afi":"ipv4","metric":0,"accessible":true,"used":true}],"peer":{"peerId":'
                       '"10.0.2.1","routerId":"192.0.2.1","type":"external"}}]}}\n,"totalPrefixCounter":2,'
                       '"filteredPrefixCounter":0}')


def test_a_default_originated_to_a_neighbor_is_an_advertisement():
    cmd = frr.adj_command("default", "ipv4", "10.0.2.1", "out")
    got = frr.parse_adj(ORIGINATING_DEFAULT, cmd, "ipv4", "out")
    assert sorted(got) == [("0.0.0.0/0", 0), ("192.0.2.0/24", 0)]
    assert got[("0.0.0.0/0", 0)] == frr.DEFAULT_ORIGINATE
    without = json.loads(ORIGINATING_DEFAULT)
    without.pop("bgpOriginatingDefaultNetwork")
    without["totalPrefixCounter"] = 1
    assert sorted(frr.parse_adj(json.dumps(without), cmd, "ipv4", "out")) == [("192.0.2.0/24", 0)]
    for bad in ({"bgpOriginatingDefaultNetwork": "10.0.0.0/8"}, {"bgpOriginatingDefaultNetwork": "::/0"},
                {"totalPrefixCounter": 1}):
        data = {**json.loads(ORIGINATING_DEFAULT), **bad}
        with pytest.raises(SnapshotError):
            frr.parse_adj(json.dumps(data), cmd, "ipv4", "out")
    v6 = json.loads(ORIGINATING_DEFAULT)
    v6.update(bgpOriginatingDefaultNetwork="::/0", advertisedRoutes={}, totalPrefixCounter=1)
    assert sorted(frr.parse_adj(json.dumps(v6), frr.adj_command("default", "ipv6", "2001:db8:11::1", "out"),
                                "ipv6", "out")) == [("::/0", 0)]


def test_received_routes_are_read_from_the_plain_listing_before_inbound_policy():
    assert frr.adj_command("default", "ipv4", "10.0.2.2", "in") == \
        "show bgp ipv4 unicast neighbors 10.0.2.2 received-routes json"
    assert frr.adj_command("cust", "ipv4", "10.10.1.2", "out") == \
        "show bgp vrf cust ipv4 unicast neighbors 10.10.1.2 advertised-routes detail json"
    cmd = frr.adj_command("default", "ipv4", "10.0.2.2", "in")
    got = frr.parse_adj(RECEIVED_V4, cmd, "ipv4", "in")
    assert sorted(got) == [("0.0.0.0/0", 0), ("10.100.0.0/23", 0), ("203.0.113.0/24", 0)]
    up = got[("203.0.113.0/24", 0)]
    assert up.med == 50 and up.as_path.render() == "65200" and up.origin == "igp" and up.local_pref is None
    assert [h.ip for h in up.next_hops] == ["10.0.2.2"] and up.weight == 0
    assert got[("10.100.0.0/23", 0)].med is None                     # absent stays absent
    assert got[("10.100.0.0/23", 0)].as_path.render() == "65200 65000 65100"
    v6 = frr.parse_adj(RECEIVED_V6, frr.adj_command("default", "ipv6", "2001:db8:11::2", "in"), "ipv6", "in")
    (hop,) = v6[("2001:db8:20::/48", 0)].next_hops
    assert hop.ip == "fe80::" and hop.scope == "link-local"         # compared by source, not by address


@pytest.mark.parametrize("edit", [
    lambda d: d["receivedRoutes"]["203.0.113.0/24"].update(community="65000:1"),      # unknown field
    lambda d: d["receivedRoutes"]["203.0.113.0/24"].pop("path"),                      # missing field
    lambda d: d["receivedRoutes"]["203.0.113.0/24"].pop("nextHop"),
    lambda d: d["receivedRoutes"]["203.0.113.0/24"].update(network="203.0.114.0/24"),
    lambda d: d["receivedRoutes"]["203.0.113.0/24"].update(path="65200 foo"),
    lambda d: d["receivedRoutes"]["203.0.113.0/24"].update(origin="weird"),
    lambda d: d["receivedRoutes"]["203.0.113.0/24"].update(metric="50"),
    lambda d: d.update(totalPrefixCounter=7),
    lambda d: d.update(advertisedRoutes={}),
])
def test_the_plain_received_listing_is_validated_strictly(edit):
    data = json.loads(RECEIVED_V4)
    edit(data)
    with pytest.raises(SnapshotError):
        frr.parse_adj(json.dumps(data), frr.adj_command("default", "ipv4", "10.0.2.2", "in"), "ipv4", "in")


def test_a_soft_reconfiguration_session_that_may_receive_add_path_is_refused():
    """The plain listing has one path per prefix: a peer that may send several (add-path) can't be read."""
    def add_path_tx(d):
        caps = d["default"]["10.0.2.2"].setdefault("neighborCapabilities", {})
        caps.setdefault("addPath", {}).setdefault("ipv4Unicast", {})["txReceived"] = True
    with pytest.raises(SnapshotError):
        collect(overrides=edited(frr.NEIGHBORS_CMD, add_path_tx))


# --- strict validation: an unknown or missing field is an error, never a smaller snapshot ------------------

def _route_entry(d):
    return d["default"]["203.0.113.0/24"][0]


def _path(d):
    return d["default"]["routes"]["203.0.113.0/24"][0]


@pytest.mark.parametrize("cmd,mutate", [
    (frr.ROUTE_CMDS["ipv4"], lambda d: _route_entry(d).update(aigp=1)),                       # unknown field
    (frr.ROUTE_CMDS["ipv4"], lambda d: _route_entry(d).pop("distance")),                     # missing field
    (frr.ROUTE_CMDS["ipv4"], lambda d: _route_entry(d).update(protocol="ebgp")),             # unknown protocol
    (frr.ROUTE_CMDS["ipv4"], lambda d: _route_entry(d).update(selected="true")),             # wrong type
    (frr.ROUTE_CMDS["ipv4"], lambda d: _route_entry(d)["nexthops"][0].update(color=3)),
    (frr.ROUTE_CMDS["ipv4"], lambda d: d["default"].update({"not-a-prefix": []})),
    (frr.ROUTE_CMDS["ipv4"], lambda d: d.pop("cust")),                                       # a VRF missing
    (frr.ROUTE_CMDS["ipv6"], lambda d: d["default"].update({"10.9.9.0/24": d["default"]["2001:db8:11::/64"]})),
    (frr.BGP_CMDS["ipv4"], lambda d: _path(d).update(newAttribute=1)),
    (frr.BGP_CMDS["ipv4"], lambda d: _path(d).pop("origin")),
    (frr.BGP_CMDS["ipv4"], lambda d: _path(d).update(origin="weird")),
    (frr.BGP_CMDS["ipv4"], lambda d: _path(d)["aspath"]["segments"][0].update(type="as-strange")),
    (frr.BGP_CMDS["ipv4"], lambda d: _path(d)["community"].update(string="65000:1 bogus")),
    (frr.BGP_CMDS["ipv4"], lambda d: _path(d)["peer"].update(type="sideways")),
    (frr.BGP_CMDS["ipv4"], lambda d: d["default"]["routes"]["203.0.113.0/24"].append(_path(d))),  # two from one source
    (frr.BGP_CMDS["ipv4"], lambda d: d.pop("cust")),                                         # instance missing
    (frr.BGP_CMDS["ipv6"], lambda d: d["default"].update(extra=1)),
    (frr.NEIGHBORS_CMD, lambda d: d["default"]["10.0.2.2"].pop("bgpState")),
    (frr.NEIGHBORS_CMD, lambda d: d["default"]["10.0.2.2"]["addressFamilyInfo"].update(l2VpnEvpn={"acceptedPrefixCounter": 1})),
    (frr.NEIGHBORS_CMD, lambda d: d["default"]["10.0.2.2"]["addressFamilyInfo"].update(ipv9Magic={"acceptedPrefixCounter": 1})),
    (frr.NEIGHBORS_CMD, lambda d: d["default"]["10.0.2.2"]["addressFamilyInfo"]["ipv4Unicast"].pop("acceptedPrefixCounter")),
    (frr.NEIGHBORS_CMD, lambda d: d["default"].update(eth1=d["default"]["10.0.2.2"])),        # unnumbered
    (frr.NEIGHBORS_CMD, lambda d: d["default"]["10.0.2.2"].pop("hostLocal")),
    (ADJ_OUT_UP1, lambda d: d.update(totalPrefixCounter=5)),
    (ADJ_OUT_UP1, lambda d: d["advertisedRoutes"]["192.0.2.0/24"]["paths"][0].update(mystery=True)),
    (ADJ_OUT_UP1, lambda d: d["advertisedRoutes"]["192.0.2.0/24"].update(pathCount=3)),
    (ADJ_IN_UP1, lambda d: d.update(advertisedRoutes={})),
    (ADJ_IN_UP1, lambda d: d["receivedRoutes"]["203.0.113.0/24"].update(community="65200:100")),
])
def test_unknown_or_missing_fields_are_errors(cmd, mutate):
    with pytest.raises(SnapshotError):
        collect(overrides=edited(cmd, mutate))


@pytest.mark.parametrize("text", ["", "not json", "[]", '{"warning": "Unknown command"}', "null"])
def test_unreadable_output_is_an_error(text):
    with pytest.raises(DriverError):
        collect(overrides={frr.ROUTE_CMDS["ipv4"]: text})


def test_a_failed_command_is_a_command_failure():
    with pytest.raises(frr.CommandFailed):
        collect(fail={frr.NEIGHBORS_CMD})


def test_a_router_without_bgp_has_no_sessions_or_paths():
    empty = {frr.NEIGHBORS_CMD: "{}", frr.BGP_CMDS["ipv4"]: "{}", frr.BGP_CMDS["ipv6"]: "{}"}
    ns = collect(overrides=empty)
    assert not [k for k in ns.items if k.kind in ("session", "path", "adj_out", "adj_in")]
    assert [k for k in ns.items if k.kind == "rib"]


def test_bgp_instances_must_match_between_outputs():
    with pytest.raises(SnapshotError):
        collect(overrides={frr.BGP_CMDS["ipv4"]: "{}"})


# --- stored snapshots --------------------------------------------------------------------------------------

def test_snapshot_round_trips_through_json():
    snap = Snapshot({"edge1": collect()}, {"host1": "a host"})
    data = json.loads(json.dumps(snap.to_json()))
    again = Snapshot.from_json(data)
    assert again.items() == snap.items() and again.unobserved == snap.unobserved
    lab = base().snap()
    assert Snapshot.from_json(json.loads(json.dumps(lab.to_json()))).items() == lab.items()


@pytest.mark.parametrize("mutate", [
    lambda d: d.update(extra=1),
    lambda d: d.update(schema="netdryrun.snapshot/v0"),
    lambda d: d["nodes"]["edge1"]["items"][0]["value"].update(unknown=1),
    lambda d: d["nodes"]["edge1"]["items"][-1]["value"].pop(next(iter(d["nodes"]["edge1"]["items"][-1]["value"]))),
    lambda d: d["nodes"]["edge1"]["items"][0]["key"].update(kind="mystery"),
    lambda d: d["nodes"]["edge1"]["items"].append(d["nodes"]["edge1"]["items"][0]),
    lambda d: d["nodes"]["edge1"].pop("items"),
])
def test_stored_snapshot_is_validated_strictly(mutate):
    data = json.loads(json.dumps(Snapshot({"edge1": collect()}).to_json()))
    mutate(data)
    with pytest.raises(SnapshotError):
        Snapshot.from_json(data)


def test_values_validate_their_normal_form():
    with pytest.raises(SnapshotError):
        NodeSnapshot("r1", "frr", ("default",), {ItemKey("rib", "r2", "default", "ipv4", "unicast", "10.0.0.0/8",
                                                         protocol="bgp"): rib()})
    with pytest.raises(SnapshotError):
        ItemKey("rib", "r1", "default", "ipv6", "unicast", "10.0.0.0/8", protocol="bgp")
    with pytest.raises(SnapshotError):
        AsPath((("set", (3, 1)),))


# --- the must-fail matrix of verify on real output: every kind of item the live capture has, removed or
# changed, fails an empty intent (the driver x check matrix, applied to verify's snapshot) --------------------

def _one_of_each_kind(ns):
    seen = {}
    for k in sorted(ns.items):
        seen.setdefault((k.kind, k.vrf, k.afi), k)
    return sorted(seen.values())


@pytest.mark.parametrize("change", ["removed", "changed"])
def test_every_kind_of_item_in_the_live_capture_fails_an_empty_intent_when_it_changes(change):
    from dataclasses import replace as dc_replace

    from netdryrun.verify.engine import match
    from netdryrun.verify.intent import parse_intent_text

    ns = collect()
    empty = parse_intent_text("intent: []\n", "empty")
    keys = _one_of_each_kind(ns)
    assert {k.kind for k in keys} == {"session", "rib", "path", "adj_out", "adj_in"}
    for k in keys:
        items = dict(ns.items)
        v = items[k]
        if change == "removed":
            del items[k]
        elif k.kind == "session":
            items[k] = dc_replace(v, remote_as=(v.remote_as or 0) + 1)
        elif k.kind == "rib":
            items[k] = tuple(dc_replace(e, distance=e.distance + 1) for e in v)
        elif k.kind == "path":
            items[k] = dc_replace(v, attrs=dc_replace(v.attrs, med=(v.attrs.med or 0) + 1))
        else:
            items[k] = dc_replace(v, med=(v.med or 0) + 1)
        after = Snapshot({"edge1": NodeSnapshot("edge1", "frr", ns.vrfs, items, config=ns.config)})
        m = match(Snapshot({"edge1": ns}), after, empty)
        assert m.status == "failed" and [d.key for d in m.undeclared] == [k], (change, k)


def test_cold_7_an_empty_advertised_listing_for_a_session_that_sent_routes_is_not_nothing():
    """Cold review: `{}` from advertised-routes was read as "advertises nothing" even when the neighbor output
    says routes were sent. It is a failed read (retried, then exit 2), never an empty adj-RIB-out."""
    with pytest.raises(frr.CommandFailed):
        collect(overrides={ADJ_OUT_UP1: "{}"})                 # 10.0.2.2: sentPrefixCounter 2
    quiet = frr.adj_command("default", "ipv4", "10.0.3.2", "out")   # sentPrefixCounter 0: empty is fine
    ns = collect(overrides={quiet: "{}"})
    assert not [k for k in ns.items if k.kind == "adj_out" and k.neighbor == "10.0.3.2"]


def test_the_collector_reports_the_longest_advertisement_interval():
    assert collect().adv_interval == 0.0                     # FRR 10.4.1's default, as the live capture reports it
    slow = edited(frr.NEIGHBORS_CMD, lambda d: d["default"]["10.0.2.2"].update(minBtwnAdvertisementRunsTimerMsecs=45000))
    ns = collect(overrides=slow)
    assert ns.adv_interval == 45.0
    assert ns == collect()                                  # a timer, never compared
    assert "adv_interval" not in json.dumps(Snapshot({"edge1": ns}).to_json(raw=False))
