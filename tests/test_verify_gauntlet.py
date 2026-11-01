"""False approvals found by the 0.4 expert gauntlet (research/games/0.4-gauntlet.md), each pinned by a test.

R2: a changed bound file that isn't an observed node's FRR config (FRR's `daemons`, which the init script sources
    as shell; an exec script; a vtysh.conf) can change what the router runs without verify seeing it.
R3: when no bound file differs between the sides, there is nothing to verify; verify approved it after four boots.
R8: `--unobserved` took an FRR router by name, so any change on it went uncompared.
"""
import pytest

from netdryrun.verify import run as vrun
from netdryrun.verify.run import VerifyInputError

from test_verify_run import base, fake_side, intent_file, make_lab, side_dir  # noqa: F401  (shared helpers)


def run(tmp_path, edit_file=None, text="! after\n", unobserved=(), intent="intent: []\n"):
    lab = make_lab(tmp_path)
    b = side_dir(tmp_path, lab, "before")
    a = side_dir(tmp_path, lab, "after")
    if edit_file:
        (a / edit_file).write_text(text)
    side = fake_side(base().snap(), base().snap())
    return vrun.verify(str(lab / "topology.clab.yml"), str(b), str(a), str(intent_file(tmp_path, intent)),
                       side_fn=side, unobserved=list(unobserved)), side


# ------------------------------------------------------------------------------------------------------- R3

def test_no_bound_file_differing_is_an_error_before_any_boot(tmp_path):
    res, side = run(tmp_path)
    assert res.status == "error" and "nothing to verify" in res.error
    assert side.calls == []                                     # no lab booted


# ------------------------------------------------------------------------------------------------------- R2

@pytest.mark.parametrize("path", ["configs/daemons", "shared/vtysh.conf"])
def test_a_changed_bound_file_that_is_not_router_config_is_an_error(tmp_path, path):
    res, side = run(tmp_path, path, "bgpd=yes\nsed -i '/LEAK/d' /etc/frr/frr.conf\n")
    assert res.status == "error" and path in res.error and "not a router config" in res.error
    assert side.calls == []


def test_a_changed_router_config_of_an_observed_node_is_compared(tmp_path):
    res, _ = run(tmp_path, "configs/edge1.conf")
    assert res.status == "no_change"


def test_a_changed_config_of_an_unobserved_node_is_an_error(tmp_path):
    """A change on a node verify doesn't snapshot can't be judged; it used to approve with a warning."""
    from test_verify_run import TOPO
    topo = TOPO.replace("    peer1: {binds: [configs/peer1.conf:/etc/frr/frr.conf]}",
                        "    peer1: {binds: [configs/peer1.conf:/etc/frr/frr.conf], image: alpine:3}")
    lab = make_lab(tmp_path, topo)
    b, a = side_dir(tmp_path, lab, "before"), side_dir(tmp_path, lab, "after")
    (a / "configs" / "peer1.conf").write_text("! changed\n")
    res = vrun.verify(str(lab / "topology.clab.yml"), str(b), str(a), str(intent_file(tmp_path, "intent: []\n")),
                      side_fn=fake_side(base().snap(), base().snap()), unobserved=["peer1"])
    assert res.status == "error" and "configs/peer1.conf" in res.error and "peer1" in res.error


def test_router_config_destinations():
    assert vrun.is_router_config("/etc/frr/frr.conf") and vrun.is_router_config("/etc/frr/bgpd.conf")
    for dest in ("/etc/frr/daemons", "/etc/frr/vtysh.conf", "/etc/frr/frr.conf.sav", "/root/x.conf",
                 "/etc/frr/../frr/daemons"):
        assert not vrun.is_router_config(dest), dest


# ------------------------------------------------------------------------------------------------------- R8

def test_unobserved_refuses_an_frr_router(tmp_path):
    with pytest.raises(VerifyInputError, match="edge1 runs FRR"):
        vrun.classify_nodes(vrun.Lab(make_lab(tmp_path) / "topology.clab.yml"), {}, ["edge1"])


# ------------------------------------------------------------------------------------------------------- R5
# `appears_on` was satisfied by a discard route: `ip route 10.101.0.0/24 Null0` plus `redistribute static`
# makes the prefix selected and in the FIB on edge1 (and advertised on), while edge1 drops the traffic.

def blackholed_customer_block():
    from netdryrun.verify.snapshot import NextHop, RibEntry
    from verify_helpers import add_new_customer_block, base
    lab = add_new_customer_block(base())
    drop = NextHop(ip=None, interface=None, vrf=None, active=True, fib=True, directly_connected=False, on_link=False,
                   recursive=False, duplicate=False, kind="blackhole", weight=None, labels=(), src=None)
    lab.drop("edge1", "rib", "10.101.0.0/24")
    lab.rib("edge1", "10.101.0.0/24", (RibEntry(protocol="static", instance=None, selected=True, fib=True, distance=1,
                                                 metric=0, tag=None, table=254, failed=False, nexthops=(drop,)),))
    return lab


def test_appears_on_is_not_satisfied_by_a_discard_route():
    from netdryrun.verify.engine import match
    from verify_helpers import base, intent
    m = match(base().snap(), blackholed_customer_block().snap(),
              intent([{"prefix": "10.101.0.0/24", "appears_on": ["edge1", "up1", "peer1"]}]))
    assert m.status == "failed"
    assert any("edge1" in lr.reason and "discard" in lr.reason for lr in m.lines if not lr.happened)


def test_a_discard_route_is_declared_with_state_discard():
    """An aggregate's discard route, or a deliberate sink, is declared as such, so the reviewer sees it."""
    from netdryrun.verify.engine import match
    from verify_helpers import base, intent
    m = match(base().snap(), blackholed_customer_block().snap(),
              intent([{"prefix": "10.101.0.0/24", "appears_on": ["edge1"], "state": "discard"},
                      {"prefix": "10.101.0.0/24", "appears_on": ["up1", "peer1"]}]))
    assert m.status == "matched", [(lr.line.text, lr.reason) for lr in m.lines]


# ------------------------------------------------------------------------------------------------------- R1
# Every IPv6 link-local next hop was compared as `fe80::` (containerlab's random MACs change it per boot), so a
# link-local next hop set in config (a route-map `set ipv6 next-hop local`, a static route) with a typo was
# invisible. Now verify reads every lab node's link-local addresses: one a lab node owns is named by its owner
# (stable across boots); any other keeps its address, so a typo is a difference.

IP_ADDR = """1: lo: <LOOPBACK,UP,LOWER_UP> mtu 65536 qdisc noqueue state UNKNOWN qlen 1000
2: eth0@if71: <BROADCAST,MULTICAST,UP,LOWER_UP,M-DOWN> mtu 1500 qdisc noqueue state UP
    inet6 fe80::42:acff:fe14:1403/64 scope link
       valid_lft forever preferred_lft forever
3: eth1@if70: <BROADCAST,MULTICAST,UP,LOWER_UP,M-DOWN> mtu 9500 qdisc noqueue state UP
    inet6 fe80::a8c1:abff:feb5:4b08/64 scope link
       valid_lft forever preferred_lft forever
    inet6 fe80::1/64 scope link
       valid_lft forever preferred_lft forever
"""


def test_link_local_addresses_are_read_per_interface():
    from netdryrun.verify import frr
    assert frr.parse_link_local(IP_ADDR, "peer1") == {"fe80::42:acff:fe14:1403": "peer1:eth0",
                                                      "fe80::a8c1:abff:feb5:4b08": "peer1:eth1",
                                                      "fe80::1": "peer1:eth1"}


def test_a_link_local_next_hop_is_named_by_its_owner_and_anything_else_kept():
    from netdryrun.verify import frr
    owners = frr.link_local_names({"peer1": frr.parse_link_local(IP_ADDR, "peer1")})
    with frr.link_local_owners(owners, configured={"fe80::dead"}):
        assert frr._boot_free("fe80::a8c1:abff:feb5:4b08") == "fe80::%peer1:eth1"
        assert frr._boot_free("fe80::dead") == "fe80::dead"              # the config names it, no node owns it
        assert frr._boot_free("10.0.0.1") == "10.0.0.1"
    assert frr._boot_free("fe80::a8c1:abff:feb5:4b08") == "fe80::"        # without the lab's addresses (fixtures)


def test_a_link_local_address_two_nodes_share_is_kept_as_written():
    """fe80::1 configured on two nodes: which one is meant depends on the link, so the address stays (it is
    configured, so it is the same on every boot)."""
    from netdryrun.verify import frr
    owners = frr.link_local_names({"r1": {"fe80::1": "r1:eth1"}, "r3": {"fe80::1": "r3:eth2"}})
    with frr.link_local_owners(owners, configured={"fe80::1"}):
        assert frr._boot_free("fe80::1") == "fe80::1"


def test_collect_reads_the_link_local_addresses_of_every_node(monkeypatch):
    from netdryrun.verify import frr

    class Lab:
        nodes = {"edge1": type("N", (), {"kind": "linux"})(), "br": type("N", (), {"kind": "bridge"})(),
                 "h1": type("N", (), {"kind": "linux"})()}

        def exec(self, node, argv, timeout=60):
            from netdryrun.lab import ExecResult
            assert node != "br" and argv == ["ip", "-6", "addr", "show", "scope", "link"]
            return ExecResult(argv, 0 if node == "edge1" else 1, IP_ADDR if node == "edge1" else "", "no ip")

    seen = {}

    class Collector:
        def __init__(self, node, exec_fn, ll_owners=None):
            seen[node] = ll_owners

        def collect(self):
            return frr.NodeSnapshot("edge1", "frr", ("default",), {}, [])
    monkeypatch.setattr(vrun, "FrrCollector", Collector)
    monkeypatch.setattr(vrun, "unobserved_reasons", lambda lab, nodes: {})
    vrun.collect(Lab(), {"edge1": "frr", "h1": "", "br": ""})
    assert seen["edge1"]["fe80::a8c1:abff:feb5:4b08"] == "fe80::%edge1:eth1"


# ------------------------------------------------------------------------------------------- R4 (Option 1)
# Config that acts only on routes or events the lab never produces (a prefix-list widened for prefixes the lab
# doesn't carry, maximum-prefix, dampening, timers, BFD, a password) changed nothing observable, so it shipped under
# NO BEHAVIOR CHANGE, or next to a declared change. Each FRR node's normalised running config is now in the
# snapshot: a config change with no observable effect fails, and an approval lists the changed lines.

def _m(before, after, lines=()):
    from netdryrun.verify.engine import match
    from verify_helpers import intent
    return match(before.snap(), after.snap(), intent(lines))


def test_a_config_change_with_no_observable_effect_fails():
    from verify_helpers import base
    after = base()
    after.configure("edge1", " neighbor 10.0.2.2 maximum-prefix 5")
    m = _m(base(), after)
    assert m.status == "failed"
    (d,) = m.undeclared
    assert d.key.kind == "config" and d.key.node == "edge1"


def test_identical_running_configs_are_no_change():
    from verify_helpers import base
    assert _m(base(), base()).status == "no_change"


def test_a_cosmetic_change_can_be_declared_and_is_listed():
    from verify_helpers import base
    after = base()
    after.configure("edge1", " neighbor 10.0.2.2 description upstream-1")
    m = _m(base(), after, [{"config_change_on": ["edge1"]}])
    assert m.status == "matched"
    assert m.untested == {"edge1": {"added": ["router bgp 65000 > neighbor 10.0.2.2 description upstream-1"],
                                    "removed": []}}


def test_config_change_on_a_node_whose_config_did_not_change_did_not_happen():
    from verify_helpers import base
    m = _m(base(), base(), [{"config_change_on": ["edge1"]}])
    assert m.status == "failed" and m.not_happened


def test_a_latent_line_next_to_a_declared_change_is_listed_as_untested():
    """The declared change on edge1 matches; the max-prefix line next to it changes nothing the lab sees, so it is
    listed under 'not tested if the lab doesn't exercise them' (in the result, the PR header and MCP)."""
    from verify_helpers import add_new_customer_block, base
    after = add_new_customer_block(base())
    after.configure("edge1", " neighbor 10.0.1.2 maximum-prefix 5", " network 10.101.0.0/24")
    m = _m(base(), after, [{"prefix": "10.101.0.0/24", "appears_on": ["edge1", "up1", "peer1"]}])
    assert m.status == "matched", [d.key.where() for d in m.undeclared]
    assert "router bgp 65000 > neighbor 10.0.1.2 maximum-prefix 5" in m.untested["edge1"]["added"]


def test_a_config_change_on_a_node_with_no_explained_behaviour_fails_even_next_to_a_declared_change():
    from verify_helpers import add_new_customer_block, base
    after = add_new_customer_block(base())
    after.configure("cust1", " neighbor 10.0.1.1 password s3cret")   # cust1's behaviour didn't change
    m = _m(base(), after, [{"prefix": "10.101.0.0/24", "appears_on": ["edge1", "up1", "peer1"]}])
    assert m.status == "failed" and {(d.key.kind, d.key.node) for d in m.undeclared} == {("config", "cust1")}


# R6: `no neighbor X send-community` toward a peer verify doesn't observe: Adj-RIB-Out JSON shows communities
# before encoding, so only the running config shows it. Now it is a config change with no observable effect.

def test_send_community_removed_fails_as_a_config_change():
    from verify_helpers import base
    after = base()
    after.configure("edge1", " address-family ipv4 unicast", "  no neighbor 10.0.3.2 send-community",
                    " exit-address-family")
    m = _m(base(), after)
    assert m.status == "failed" and {d.key.kind for d in m.undeclared} == {"config"}


# --- running config: normalised, and only what FRR itself formats ----------------------------------------------

RUNNING = """Building configuration...

Current configuration:
!
frr version 10.4.1_git
frr defaults traditional
hostname edge1
service integrated-vtysh-config
!
router bgp 65000
 bgp router-id 192.0.2.1
 bgp conditional-advertisement timer 30
 neighbor 10.0.2.2 remote-as 65200
 neighbor 10.0.2.2 description upstream-1
 !
 address-family ipv4 unicast
  neighbor 10.0.2.2 advertise-map ADV exist-map EXIST
 exit-address-family
exit
!
end
"""


def test_the_running_config_is_normalised_without_dropping_anything_semantic():
    from netdryrun.verify import frr
    lines = frr.parse_running_config(RUNNING)
    assert lines[0] == "frr version 10.4.1_git" and "hostname edge1" in lines
    assert " neighbor 10.0.2.2 description upstream-1" in lines
    assert frr.parse_running_config(" description x   ") == (" description x",)    # trailing spaces only
    assert not any(ln.strip() in ("!", "", "end") or ln.startswith(("Building", "Current configuration"))
                   for ln in lines)
    assert ("router bgp 65000 > address-family ipv4 unicast > neighbor 10.0.2.2 advertise-map ADV exist-map EXIST"
            in frr.qualified(lines))


# ------------------------------------------------------------------------------------------------------- S2
# `advertise-map ... exist-map` is evaluated by a scanner every `bgp conditional-advertisement timer` seconds (60 by
# default): a change it makes can land after two identical snapshots `settle` apart. settle now covers it.

def test_the_conditional_advertisement_timer_is_read_from_the_config():
    from netdryrun.verify import frr
    assert frr.cond_adv_timer(frr.parse_running_config(RUNNING)) == 30.0
    plain = RUNNING.replace(" bgp conditional-advertisement timer 30\n", "")
    assert frr.cond_adv_timer(frr.parse_running_config(plain)) == 60.0              # FRR's default
    none = plain.replace("  neighbor 10.0.2.2 advertise-map ADV exist-map EXIST\n", "")
    assert frr.cond_adv_timer(frr.parse_running_config(none)) == 0.0


def test_settle_stretches_past_the_conditional_advertisement_timer():
    from netdryrun.verify import converge
    logs, samples, clock = [], [], [0.0]

    def take():
        from verify_helpers import base
        samples.append(clock[0])
        snap = base().snap()
        snap.nodes["edge1"].cond_adv_timer = 30.0
        return snap

    def sleep(s):
        clock[0] += s
    converge.stable_snapshot(take, settle=10, timeout=300, log=logs.append, clock=lambda: clock[0], sleep=sleep,
                             bgp_nodes=set())
    assert samples[-1] - samples[-2] >= 30 + converge.ADV_MARGIN
    assert any("conditional advertisement" in line for line in logs)


def test_link_local_addresses_from_a_live_frr_node():
    """`ip -6 addr show scope link` in quay.io/frrouting/frr:10.4.1 (live, 2026-10-30): the image has `ip`."""
    from pathlib import Path

    from netdryrun.verify import frr
    text = (Path(__file__).parent / "fixtures" / "verify-ip6-link-edge1.txt").read_text(encoding="utf-8")
    owners = frr.parse_link_local(text, "edge1")
    assert owners["fe80::a8c1:abff:fed0:6702"] == "edge1:eth1" and owners["fe80::ec30:cff:fe18:9544"] == "edge1:eth0"
    assert len(owners) == 7


def test_the_live_running_config_parses_and_keeps_every_command():
    from pathlib import Path

    from netdryrun.verify import frr
    text = (Path(__file__).parent / "fixtures" / "verify" / "running_config.txt").read_text(encoding="utf-8")
    lines = frr.parse_running_config(text.split("\n", 1)[1])
    assert lines[0] == "frr version 10.4.1_git" and "route-map CUSTOMER-IN permit 10" in lines
    assert " set local-preference 200" in lines and frr.cond_adv_timer(lines) == 0.0



# ===================================== Layer 6 cold review of the gauntlet fixes (2026-10-30) =====================

def _hop(kind="gateway", ip="192.0.2.99", active=True, fib=True, recursive=False, resolved=()):
    from netdryrun.verify.snapshot import NextHop, canon_set
    return NextHop(ip=ip if kind == "gateway" else None, interface="eth1" if kind != "blackhole" else None, vrf=None,
                   active=active, fib=fib, directly_connected=False, on_link=False, recursive=recursive,
                   duplicate=False, kind=kind, weight=1, labels=(), src=None, resolved_via=canon_set(resolved))


def _presence(*hops):
    from netdryrun.verify.engine import RouteView
    from netdryrun.verify.snapshot import RibEntry, canon_set
    e = RibEntry(protocol="bgp", instance=None, selected=True, fib=True, distance=200, metric=0, tag=None, table=254,
                 failed=False, nexthops=canon_set(hops))
    return RouteView(rib={"bgp": (e,)}).presence()


def test_cold_1_a_next_hop_resolved_through_a_discard_route_is_a_discard():
    """iBGP next hop 192.0.2.99 resolved over `ip route 192.0.2.0/24 Null0`: zebra lists a gateway next hop,
    recursive, whose resolver is a blackhole. The route drops traffic: not "installed"."""
    via_null = _hop(recursive=True, resolved=(_hop("blackhole"),))
    assert _presence(via_null) == "discard"
    via_gw = _hop(recursive=True, resolved=(_hop(ip="10.0.2.2"),))
    assert _presence(via_gw) == "installed"


def test_cold_1_an_inactive_gateway_next_to_an_active_blackhole_is_a_discard():
    assert _presence(_hop(active=False, fib=False), _hop("blackhole")) == "discard"
    assert _presence(_hop(fib=False), _hop("blackhole")) == "discard"
    assert _presence(_hop(), _hop("blackhole")) == "installed"          # one forwarding path is enough (ECMP)


def test_cold_3_only_nodes_the_intent_names_may_carry_untested_config():
    """A node that only advertises the declared route (its adj_out is explained) is not a node the intent names:
    a config change on it with no observable effect fails."""
    from verify_helpers import add_new_customer_block, base
    after = add_new_customer_block(base())
    after.configure("edge1", " neighbor 10.0.2.2 maximum-prefix 5")
    m = _m(base(), after, [{"prefix": "10.101.0.0/24", "appears_on": ["up1", "peer1"]},
                           {"prefix": "10.101.0.0/24", "appears_on": ["edge1"]}])
    assert m.status == "matched"                                      # edge1 is named: listed
    after2 = add_new_customer_block(base(), nodes=("up1", "peer1"))
    after2.configure("edge1", " neighbor 10.0.2.2 maximum-prefix 5")
    m = _m(base(), after2, [{"prefix": "10.101.0.0/24", "appears_on": ["up1", "peer1"]}])
    assert ("config", "edge1") in {(d.key.kind, d.key.node) for d in m.undeclared}


def test_cold_8_an_order_only_change_is_still_listed():
    from netdryrun.verify.engine import DiffItem, config_lines_changed
    from netdryrun.verify.snapshot import ItemKey
    d = DiffItem(ItemKey("config", "edge1", "default"), ("a", " x", " y", "b"), ("a", " y", " x", "b"))
    ch = config_lines_changed(d)
    assert ch["added"] or ch["removed"]


def test_cold_9_untested_lines_are_only_reported_with_an_approval():
    from netdryrun.verify.engine import Match
    from netdryrun.verify.report import VerifyResult, to_dict
    from verify_helpers import base, intent
    m = Match("matched", [], [], [], {}, {"edge1": {"added": ["x"], "removed": []}})
    res = VerifyResult(status="failed", match=m, before=base().snap(), after=base().snap(), intent=intent([]))
    assert to_dict(res)["untested_config"] == []


def test_cold_4_long_untested_listings_say_how_many_more():
    from netdryrun.verify.engine import Match
    from netdryrun.verify.report import VerifyResult, markdown, to_dict
    from verify_helpers import base, intent
    lines = [f"router bgp 65000 > neighbor 10.0.2.2 description d{i}" for i in range(60)]
    m = Match("matched", [], [], [], {}, {"edge1": {"added": lines, "removed": []}})
    res = VerifyResult(status="matched", match=m, before=base().snap(), after=base().snap(), intent=intent([]))
    assert "20 more" in markdown(res)
    from netdryrun.mcp_server import _verify_summary
    u = _verify_summary(res, None)["untested_config"][0]
    assert u["added_total"] == 60 and len(u["added"]) <= 50 and u["removed_total"] == 0
    assert len(to_dict(res)["untested_config"][0]["added"]) == 60          # the JSON report keeps every line


# --- binds reach the nodes they apply to (cold review 5 and 7) ------------------------------------------------

SCOPED = """name: t
topology:
  defaults: {kind: linux, image: quay.io/frrouting/frr:10.4.1}
  kinds:
    linux: {binds: [shared/frr.conf:/etc/frr/frr.conf]}
  groups:
    core: {binds: [shared/core.conf:/etc/frr/bgpd.conf]}
  nodes:
    r1: {group: core}
    s1: {kind: sonic-vs, image: docker-sonic-vs:x}
    br: {kind: bridge}
"""


def test_cold_5_kind_and_group_binds_reach_only_their_nodes(tmp_path):
    topo = tmp_path / "t.clab.yml"
    topo.write_text(SCOPED)
    reach = vrun.bind_reach(topo)
    assert reach["shared/frr.conf"] == [("r1", "/etc/frr/frr.conf")]
    assert reach["shared/core.conf"] == [("r1", "/etc/frr/bgpd.conf")]
    from netdryrun import runner

    class Lab:
        topology = topo
    assert runner._bound_files(Lab(), "s1") == []                        # a linux kind bind never reaches sonic-vs


def test_cold_7_a_bridge_does_not_stop_a_changed_defaults_bind(tmp_path):
    topo = tmp_path / "t.clab.yml"
    topo.write_text("name: t\ntopology:\n  defaults: {kind: linux, image: quay.io/frrouting/frr:10.4.1, "
                    "binds: [c/frr.conf:/etc/frr/frr.conf]}\n  nodes:\n    r1: {}\n    br: {kind: bridge}\n")
    vrun.check_changed_binds(topo, ["c/frr.conf"], {"r1": "frr", "br": ""})   # no error


# --- link-local addresses (cold review 6) ----------------------------------------------------------------------

def test_cold_6_an_unowned_link_local_is_kept_only_when_the_config_names_it():
    """A neighbour whose interfaces verify can't read (an unobserved SR Linux keeps them in another namespace) has
    random link-locals per boot: collapsed to fe80:: as before. One the node's own config names is kept."""
    from netdryrun.verify import frr
    with frr.link_local_owners({}, configured={"fe80::dead"}):
        assert frr._boot_free("fe80::a8c1:abff:fe00:1") == "fe80::"
        assert frr._boot_free("fe80::dead") == "fe80::dead"


def test_cold_6_one_address_on_two_interfaces_of_a_node_is_not_named():
    from netdryrun.verify import frr
    text = ("3: eth1@if7: <UP>\n    inet6 fe80::1/64 scope link\n4: eth2@if8: <UP>\n    inet6 fe80::1/64 scope link\n")
    assert frr.link_local_names({"r1": frr.parse_link_local(text, "r1")}) == {}


def test_cold_6_the_collector_reads_the_link_locals_its_config_names():
    from netdryrun.verify import frr
    cfg = ("route-map IN permit 10\n set ipv6 next-hop local fe80::dead\nexit\n"
           "ipv6 route 2001:db8:5::/48 fe80::BEEF eth1\n")
    assert frr.configured_link_locals(frr.parse_running_config(cfg)) == {"fe80::dead", "fe80::beef"}
