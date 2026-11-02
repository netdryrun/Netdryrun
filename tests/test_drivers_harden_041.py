"""0.4.1 driver hardening from the acceptance round's adversary: output a driver read as "nothing" or as a plain
value where the device was telling it something else. Each case fails closed (an error, or "not active"), with
the exact message a user reads, and the live captures still parse."""
import json
from pathlib import Path

import pytest

from netdryrun.drivers import eos, frr, srlinux
from netdryrun.drivers.base import DriverError, Route

FIX = Path(__file__).parent / "fixtures"


def read(name: str) -> str:
    return (FIX / name).read_text(encoding="utf-8")


def _obj(d) -> str:
    return json.dumps(d, indent=1)


def _snip(detail: str) -> str:
    """What `unexpected()` keeps of a detail: whitespace collapsed, at most 200 characters."""
    return " ".join(detail.split())[:200]


def raises(fn, message: str):
    with pytest.raises(DriverError) as e:
        fn()
    assert str(e.value) == message


# ---------------------------------------------------------------- EOS: an unmapped routeType is an error

EOS_RC = f"unexpected output from `{eos.ROUTE_CMD}`: "
EOS_AR = f"unexpected output from `{eos.ALL_ROUTES_CMD}`: "
NO_BGP = _obj({"vrfs": {"default": {"bgpRouteEntries": {}}}})


def _eos_routes(rtype: str, pfx: str = "10.1.0.0/16") -> str:
    return _obj({"vrfs": {"default": {"routes": {pfx: {"routeType": rtype, "kernelProgrammed": True,
                                                       "hardwareProgrammed": True}}}}})


@pytest.mark.parametrize("rtype", ["nexthopGroupStaticRoute", "VRF leaked", "dynamicPolicy", "somethingNew", ""])
def test_eos_unmapped_route_type_is_an_error_not_a_protocol_nothing_matches(rtype):
    """0.4.0 passed the raw name through: `protocol: static present: false` could never match a nexthop-group
    static, so it passed. A route type the driver doesn't map is now an error naming it."""
    key = rtype.lower().replace(" ", "")
    raises(lambda: eos.parse_routes(_eos_routes(rtype), NO_BGP, "10.1.0.0/16"),
           EOS_RC + f"routeType {rtype!r} (read as {key!r}) is not one this driver maps to a protocol")
    raises(lambda: eos.parse_all_routes(_eos_routes(rtype)),
           EOS_AR + f"routeType {rtype!r} (read as {key!r}) is not one this driver maps to a protocol")


@pytest.mark.parametrize("rtype,proto", [("eBGP", "bgp"), ("iBGP", "bgp"), ("static", "static"), ("connected", "connected"),
                                         ("dropRoute", "static"), ("ospfNssaExternalType2", "ospf"), ("isisLevel2", "isis"),
                                         ("bgpAggregate", "aggregate")])
def test_eos_mapped_route_types(rtype, proto):
    assert eos.parse_routes(_eos_routes(rtype), NO_BGP, "10.1.0.0/16") == [Route("10.1.0.0/16", proto, True)]


def test_eos_live_route_captures_still_parse():
    assert eos.parse_all_routes(read("eos_route.txt"))
    assert eos.parse_all_routes(read("eos_leak_route.txt"))


# ---------------------------------------------------------------- FRR: a path without AS-path segments

FRR = f"unexpected output from `{frr.BGP_PATHS_CMD}`: "


@pytest.mark.parametrize("edit", [lambda p: p.pop("aspath"), lambda p: p["aspath"].pop("segments"),
                                  lambda p: p.update(aspath="65002"), lambda p: p["aspath"].update(segments=None)],
                         ids=["no-aspath", "no-segments", "aspath-string", "segments-null"])
def test_frr_path_without_as_path_segments_is_an_error_not_a_local_route(edit):
    """An AS path read as empty is a locally originated route: `as_path: ""` would pass on a path whose AS path
    simply wasn't printed (acceptance A-6)."""
    d = json.loads(read("frr_bgp_paths.txt"))
    p = d["paths"][0]
    edit(p)
    raises(lambda: frr.parse_bgp_paths(_obj(d), "192.168.20.0/24"),
           FRR + _snip(f"path without aspath segments: {str(p)[:150]}"))


def test_frr_local_path_with_empty_segments_is_still_local():
    (p,) = frr.parse_bgp_paths(read("frr_bgp_paths_local.txt"), "192.168.21.0/24")
    assert p.as_path == ""


# ---------------------------------------------------------------- SR Linux: an up family without counters

SRL_NB = f"unexpected output from `{srlinux.NEIGHBORS_CMD}`: "


def test_srl_up_family_without_counters_is_an_error_not_zero():
    """An IPv4 or IPv6 family that is up but prints no received-routes read as no prefixes, which passes `max`
    and `exact: 0` (acceptance A-7). Families the driver doesn't count (evpn, route-target) stay skipped."""
    d = json.loads(read("srl_bgp_neighbors.txt"))
    af = next(a for a in d["neighbor"][0]["afi-safi"] if a["afi-safi-name"] == "ipv4-unicast")
    af.pop("received-routes")
    raises(lambda: srlinux.parse_bgp_neighbors(_obj(d)),
           SRL_NB + "10.0.100.2 ipv4-unicast: oper-state up but no received-routes counter")


def test_srl_down_and_uncounted_families_stay_skipped():
    n = srlinux.parse_bgp_neighbors(read("srl_bgp_neighbors.txt"))
    assert n["10.0.100.2"].prefixes == {"ipv4-unicast": 1}


# ---------------------------------------------------------------- SR Linux: FIB programming

SRL_RC = f"unexpected output from `{srlinux.ROUTE_CMD}`: "


def _srl_route(edit) -> str:
    d = json.loads(read("srl_route.txt"))
    edit(d["route"][0])
    return _obj(d)


@pytest.mark.parametrize("edit", [
    lambda r: r["fib-programming"].update({"pending-operation-type": "add"}),
    lambda r: r["fib-programming"].update({"last-failed-operation-type": "add"}),
    lambda r: r["fib-programming"].update({"suppressed": True}),
], ids=["fib-add-pending", "fib-add-failed", "suppressed"])
def test_srl_active_route_not_in_the_fib_is_not_active(edit):
    """SR Linux marks a route active before its FIB add completes, and keeps it active when the add fails
    (acceptance A-1/A-2). Present means forwarding, as on FRR and EOS: such a route is present but not active."""
    assert srlinux.parse_routes(_srl_route(edit), "192.168.20.0/24") == [Route("192.168.20.0/24", "bgp", False)]


def test_srl_active_route_without_fib_programming_is_an_error():
    text = _srl_route(lambda r: r.pop("fib-programming"))
    raises(lambda: srlinux.parse_routes(text, "192.168.20.0/24"),
           SRL_RC + "192.168.20.0/24: active route without fib-programming")


def test_srl_live_route_captures_still_parse_as_active():
    assert srlinux.parse_routes(read("srl_route.txt"), "192.168.20.0/24") == [Route("192.168.20.0/24", "bgp", True)]
    assert any(r.active for r in srlinux.parse_all_routes(read("srl_route.txt")))


# ---------------------------------------------------------------- Junos: no-install (A-3) and graceful-restart stale (A-4)

from netdryrun.drivers import junos  # noqa: E402

JRC = f"unexpected output from `{junos.ROUTE_CMD}`: "


def test_junos_no_install_static_is_not_active():
    """Captured live 2026-11-02: a static with `no-install` is `*` active in the routing table but never reaches the
    FIB (Junos marks it NotInstall); `netdryrun check` passed `route ... protocol static` on it while ping to it
    failed (acceptance A-3). Present means forwarding, as on FRR and EOS."""
    assert junos.parse_routes(read("junos_route_noinstall.txt"), "10.99.0.0/24") == [Route("10.99.0.0/24", "static", False)]


def _junos_entry_doc(edit, name="junos_route_paths.txt"):
    d = json.loads(read(name))
    edit(d["route-information"][0]["route-table"][0]["rt"][0]["rt-entry"][0])
    return _obj(d)


@pytest.mark.parametrize("state", ["Active Ext Stale", "Ext Stale Changed", "Active Ext LongLivedStale"])
def test_junos_stale_route_is_not_settled(state):
    """A graceful-restart stale route is neither present nor gone yet, as on FRR, EOS, NX-OS and SR Linux: the read
    stops with "not settled" and the check samples again (acceptance A-4). The token's spelling comes from Junos's
    documented route states; a live restart wasn't produced (the lab's FRR is a GR helper, not a restarter)."""
    text = _junos_entry_doc(lambda e: e.update({"rt-entry-state": [{"data": state}]}))
    for parse in (junos.parse_routes, junos.parse_bgp_paths):
        with pytest.raises(DriverError) as err:
            parse(text, "10.20.0.0/24")
        assert str(err.value) == "10.20.0.0/24: BGP path from 10.0.1.2 is stale (graceful restart in progress): not settled"


def test_junos_exact_answer_without_entry_state_is_an_error():
    """Every exact extensive answer prints rt-entry-state: without it, a stale or not-installed route couldn't be
    told from an active one."""
    text = _junos_entry_doc(lambda e: e.pop("rt-entry-state"))
    with pytest.raises(DriverError) as err:
        junos.parse_routes(text, "10.20.0.0/24")
    assert str(err.value).startswith(JRC + "no 'rt-entry-state':")


def test_junos_live_captures_still_parse():
    assert [r.active for r in junos.parse_routes(read("junos_route_paths.txt"), "10.20.0.0/24")] == [True, False]
    assert junos.parse_all_routes(read("junos_route_table.txt"))
