"""Regression tests for driver false passes: a failed, unexpected or ambiguous command must raise a
DriverError, never read as "no routes" / "no sessions" (which makes `present: false` pass).

Each test here fails on the drivers before the fix (audit C-code.md: B6, M4, S1, S2, the invalid-path
minor item) and passes after it."""
import json
from pathlib import Path

import pytest

from netdryrun.drivers import DriverError, eos, frr, srlinux
from netdryrun.drivers.eos import EosDriver
from netdryrun.drivers.frr import FrrDriver
from netdryrun.drivers.sonic import SonicDriver
from netdryrun.drivers.srlinux import SrlDriver
from netdryrun.lab import ExecResult

FIX = Path(__file__).parent / "fixtures"


def read(name: str) -> str:
    return (FIX / name).read_text()


class Lab:
    """A node whose commands are answered by the first rule whose substring is in the command."""

    def __init__(self, rules):
        self.rules, self.calls = rules, []

    def exec(self, node, cmd, timeout=60, input=None):
        line = " ".join(cmd)
        self.calls.append(line)
        for needle, answer in self.rules:
            if needle in line:
                rc, out = answer if isinstance(answer, tuple) else (0, answer)
                return ExecResult(cmd, rc, out, "" if rc == 0 else "% failed")
        raise AssertionError(f"unexpected command: {line}")


def _obj(d) -> str:
    return json.dumps(d, indent=2)


# ---------------------------------------------------------------- 1. unknown and special VRFs

SHOW_VRF = "netns-based vrfs\nvrf red id 5 table 1001 (configured)\nvrf blue inactive (configured)\n"


def _frr_lab():
    """zebra answers `{}` for a VRF that doesn't exist (FRR lib/vrf.h VRF_GET_ID with json), exactly as
    for an existing VRF without the route; bgpd says the instance is unknown."""
    return Lab([
        ("show vrf", SHOW_VRF),
        ("route", "{}"),
        ("neighbors json", _obj({"bgpNoSuchInstance": True})),
        ("show bgp", _obj({"warning": "View/Vrf is unknown"})),
    ])


@pytest.mark.parametrize("cls", [FrrDriver, SonicDriver])
def test_frr_unknown_vrf_raises_instead_of_no_routes(cls):
    d = cls(_frr_lab(), "r1")
    with pytest.raises(DriverError, match="VRF 'CUSTOMR' does not exist"):
        d.routes("10.0.0.0/24", vrf="CUSTOMR")
    with pytest.raises(DriverError, match="does not exist"):
        d.all_routes(vrf="CUSTOMR")
    with pytest.raises(DriverError):
        d.bgp_neighbors(vrf="CUSTOMR")
    with pytest.raises(DriverError):
        d.bgp_paths("10.0.0.0/24", vrf="CUSTOMR")
    with pytest.raises(DriverError, match="inactive"):
        d.routes("10.0.0.0/24", vrf="blue")


def test_frr_existing_vrf_without_the_route_is_a_real_absence():
    lab = Lab([("show vrf", SHOW_VRF), ("route", "{}"), ("show bgp", "{}")])
    assert FrrDriver(lab, "r1").routes("10.0.0.0/24", vrf="red").value == []
    # and a VRF without a BGP instance still answers the route check from zebra
    lab = Lab([("show vrf", SHOW_VRF), ("route", "{}"), ("show bgp", _obj({"warning": "View/Vrf is unknown"}))])
    assert FrrDriver(lab, "r1").routes("10.0.0.0/24", vrf="red").value == []
    lab = Lab([("route", "{}"), ("show bgp", _obj({"warning": "Default BGP instance not found"}))])
    assert FrrDriver(lab, "r1").routes("10.0.0.0/24").value == []


def test_frr_vrf_all_shaped_output_is_unexpected():
    """`show ip route vrf all json` is keyed by VRF name; the old parser skipped those keys: []."""
    vrf_all = _obj({"default": json.loads(read("frr_route.txt")), "red": {}})
    with pytest.raises(DriverError, match="unexpected output"):
        frr.parse_routes(vrf_all, "192.168.3.0/24")


@pytest.mark.parametrize("cls", [FrrDriver, SonicDriver, EosDriver, SrlDriver])
@pytest.mark.parametrize("vrf", ["all", "ALL", "All", "", "a b", "red|x", "*"])
def test_special_or_bad_vrf_names_raise_on_every_driver(cls, vrf):
    lab = Lab([("", "{}")])
    d = cls(lab, "r1")
    for call in (lambda: d.routes("10.0.0.0/24", vrf=vrf), lambda: d.bgp_paths("10.0.0.0/24", vrf=vrf),
                 lambda: d.bgp_neighbors(vrf=vrf), lambda: d.all_routes(vrf=vrf),
                 lambda: d.ping("10.0.0.1", None, 1, vrf=vrf)):
        with pytest.raises(DriverError, match="VRF"):
            call()
    assert lab.calls == []  # refused before anything ran on the device


def test_eos_vrf_missing_from_answer_raises():
    """EOS keys every answer by VRF; `_vrf` used to return {} when the VRF wasn't there."""
    no_vrf = _obj({"vrfs": {}})
    lab = Lab([("route", no_vrf), ("bgp", no_vrf)])
    d = EosDriver(lab, "ceos1")
    with pytest.raises(DriverError, match="VRF 'CUSTOMR' is not in the output"):
        d.routes("10.0.0.0/24", vrf="CUSTOMR")
    with pytest.raises(DriverError, match="not in the output"):
        d.bgp_paths("10.0.0.0/24", vrf="CUSTOMR")
    with pytest.raises(DriverError, match="not in the output"):
        d.bgp_neighbors(vrf="CUSTOMR")
    with pytest.raises(DriverError, match="not in the output"):
        d.all_routes(vrf="CUSTOMR")
    # `vrf all` shaped output (keyed by the real VRFs) never answers for a VRF called "all"
    with pytest.raises(DriverError):
        eos.parse_bgp_paths(read("eos_bgp_paths.txt"), "192.168.20.0/24", vrf="all")


def test_eos_existing_vrf_without_the_route_is_a_real_absence():
    route = _obj({"vrfs": {"red": {"routes": {}}}})
    bgp = _obj({"vrfs": {"red": {"bgpRouteEntries": {}}}})
    assert EosDriver(Lab([("route", route), ("bgp", bgp)]), "c").routes("10.0.0.0/24", vrf="red").value == []
    # a BGP answer without the VRF can't be told from unknown output: conservative, it raises
    with pytest.raises(DriverError, match="not in the output"):
        EosDriver(Lab([("route", route), ("bgp", _obj({"vrfs": {}}))]), "c").routes("10.0.0.0/24", vrf="red")


def _srl_lab(instance_state: str):
    return Lab([
        ("oper-state", instance_state),
        ("", "{\n}"),  # every state path under an instance that doesn't exist answers like an empty one
    ])


def test_srl_unknown_network_instance_raises_instead_of_no_routes():
    d = SrlDriver(_srl_lab("{\n}"), "srl1")
    with pytest.raises(DriverError, match="network-instance 'CUSTOMR' does not exist"):
        d.routes("10.0.0.0/24", vrf="CUSTOMR")
    with pytest.raises(DriverError, match="does not exist"):
        d.bgp_paths("10.0.0.0/24", vrf="CUSTOMR")
    with pytest.raises(DriverError, match="does not exist"):
        d.bgp_neighbors(vrf="CUSTOMR")
    with pytest.raises(DriverError, match="does not exist"):
        d.all_routes(vrf="CUSTOMR")


def test_srl_existing_network_instance_without_the_route_is_a_real_absence():
    d = SrlDriver(_srl_lab(_obj({"name": "red", "oper-state": "up"})), "srl1")
    assert d.routes("10.0.0.0/24", vrf="red").value == []
    assert d.bgp_paths("10.0.0.0/24", vrf="red").value == []


# ---------------------------------------------------------------- 2. swallowed command failures

@pytest.mark.parametrize("v6", [(1, "% BGP inactive"), (124, ""), (0, _obj({"errors": ["internal error"]})),
                                (0, "not json"), (0, "")])
def test_eos_failed_ipv6_summary_raises(v6):
    """M4: the IPv6 summary's failure was swallowed, so IPv6 prefix counts read 0 (passes max/exact: 0)."""
    lab = Lab([("show ipv6 bgp summary", v6), ("show ip bgp summary", read("eos_bgp_summary.txt"))])
    with pytest.raises(DriverError):
        EosDriver(lab, "ceos1").bgp_neighbors()


def test_eos_ipv6_summary_is_still_read():
    v6 = json.loads(read("eos_bgp_summary.txt"))
    v6["vrfs"]["default"]["peers"] = {"2001:db8::2": {"peerState": "Established", "prefixAccepted": 7}}
    lab = Lab([("show ipv6 bgp summary", _obj(v6)), ("show ip bgp summary", read("eos_bgp_summary.txt")),
               ("running-config", read("eos_bgp_config.txt"))])
    n = EosDriver(lab, "ceos1").bgp_neighbors().value
    assert n["10.0.200.2"].prefixes == {"ipv4-unicast": 1} and n["2001:db8::2"].prefixes == {"ipv6-unicast": 7}


def test_srl_failed_local_pref_lookup_raises():
    """The neighbor local-preference lookup's failure was swallowed (local-pref silently unknown)."""
    row = {"prefix": "10.0.0.0/24", "best-route": True, "neighbor": "10.0.0.2", "origin-protocol": "bgp",
           "attr-id": "7"}
    lab = Lab([("local-rib", _obj({"route": [row]})), ("attr-set", _obj({"as-path": {"segment": []}})),
               ("local-preference", (1, "Error: timeout"))])
    with pytest.raises(DriverError, match="failed"):
        SrlDriver(lab, "srl1").bgp_paths("10.0.0.0/24")


# ---------------------------------------------------------------- 3. output shape checks

@pytest.mark.parametrize("parse, text", [
    # a NOS release renames a container key: the old parsers read every one of these as "no routes"
    (lambda t: frr.parse_routes(t, "192.168.3.0/24"), _obj({"routes": json.loads(read("frr_route.txt"))})),
    (lambda t: frr.parse_routes(t, "192.168.3.0/24"), ""),
    (lambda t: frr.parse_routes(t, "192.168.3.0/24"), "[]"),
    (lambda t: frr.parse_all_routes(t), "[]"),
    (lambda t: frr.parse_all_routes(t), _obj({"192.168.3.0/24": {"protocol": "bgp"}})),
    (lambda t: frr.parse_bgp_paths(t, "192.168.20.0/24"),
     read("frr_bgp_paths.txt").replace('"paths"', '"pathList"')),
    (lambda t: frr.parse_bgp_paths(t, "192.168.20.0/24"), ""),
    (lambda t: frr.parse_bgp_neighbors(t), _obj({"10.0.0.2": {"state": "Established"}})),
    (lambda t: frr.parse_bgp_neighbors(t), read("frr_bgp_neighbors.txt").replace("acceptedPrefixCounter", "accepted")),
    (lambda t: frr.parse_bgp_neighbors(t), _obj({"bgpNoSuchInstance": True})),
    (lambda t: eos.parse_routes(t, read("eos_bgp_paths_empty.txt"), "192.168.20.0/24"),
     read("eos_route.txt").replace('"routes"', '"routeEntries"')),
    (lambda t: eos.parse_routes(read("eos_leak_route.txt").replace("0.0.0.0/0", "10.1.1.0/24"), t, "0.0.0.0/0"),
     read("eos_leak_bgp.txt").replace('"bgpRouteEntries"', '"routeEntries"')),
    (lambda t: eos.parse_routes(t, read("eos_bgp_paths_empty.txt"), "192.168.20.0/24"), "[]"),
    (lambda t: eos.parse_routes(t, read("eos_bgp_paths_empty.txt"), "192.168.20.0/24"), ""),
    (lambda t: eos.parse_bgp_paths(t, "192.168.20.0/24"), read("eos_bgp_paths.txt").replace('"vrfs"', '"vrf"')),
    (lambda t: eos.parse_bgp_paths(t, "192.168.20.0/24"),
     read("eos_bgp_paths.txt").replace('"bgpRoutePaths"', '"paths"')),
    (lambda t: eos.parse_bgp_summary(t), read("eos_bgp_summary.txt").replace('"peers"', '"neighbors"')),
    (lambda t: eos.parse_bgp_summary(t), read("eos_bgp_summary.txt").replace('"prefixAccepted"', '"accepted"')),
    (lambda t: srlinux.parse_routes(t, "192.168.20.0/24", "{}"), read("srl_route.txt").replace('"route"', '"routes"')),
    (lambda t: srlinux.parse_routes(t, "192.168.20.0/24", "{}"), "[]"),
    (lambda t: srlinux.parse_routes(t, "192.168.20.0/24", "{}"),
     read("srl_route.txt").replace('"ipv4-prefix"', '"prefix"')),
    (lambda t: srlinux.parse_routes("{}", "0.0.0.0/0", t), read("srl_leak_rib.txt").replace('"route"', '"routes"')),
    (lambda t: srlinux.parse_rib_paths(t, "0.0.0.0/0"), read("srl_leak_rib.txt").replace('"prefix"', '"pfx"')),
    (lambda t: srlinux.parse_bgp_neighbors(t), read("srl_bgp_neighbors.txt").replace('"neighbor"', '"peer"')),
], ids=[
    "frr-route-renamed-container", "frr-route-empty-output", "frr-route-list", "frr-all-routes-list", "frr-all-routes-entry-not-list", "frr-bgp-paths-renamed", "frr-bgp-paths-empty-output", "frr-neighbor-without-bgpState", "frr-neighbor-counter-renamed", "frr-neighbors-no-instance", "eos-routes-renamed", "eos-bgp-side-renamed", "eos-routes-list", "eos-routes-empty-output", "eos-bgp-paths-vrfs-renamed", "eos-bgp-paths-paths-renamed", "eos-summary-peers-renamed", "eos-summary-counter-renamed", "srl-route-renamed", "srl-route-list", "srl-route-prefix-key-renamed", "srl-rib-renamed", "srl-rib-prefix-renamed", "srl-neighbors-renamed"])
def test_unexpected_output_raises(parse, text):
    with pytest.raises(DriverError, match="unexpected output|vtysh|EOS error"):
        parse(text)


def test_real_empty_answers_still_read_as_empty():
    assert frr.parse_routes("{}", "10.0.0.0/24") == []
    assert frr.parse_all_routes("{}") == []
    assert frr.parse_bgp_paths(read("sonic_bgp_paths_empty.txt"), "10.0.0.0/24") == []
    assert frr.parse_bgp_neighbors("{}") == {}
    assert eos.parse_bgp_paths(read("eos_bgp_paths_empty.txt"), "10.99.0.0/16") == []
    assert eos.parse_routes(_obj({"vrfs": {"default": {"routes": {}}}}), read("eos_bgp_paths_empty.txt"),
                            "10.99.0.0/16") == []
    assert srlinux.parse_routes(read("srl_rib_empty.txt"), "10.0.0.0/24", read("srl_rib_empty.txt")) == []
    assert srlinux.parse_routes(_obj({"route": []}), "10.0.0.0/24", _obj({"route": []})) == []
    assert srlinux.parse_rib_paths(read("srl_rib_empty.txt"), "10.0.0.0/24") == []


# ---------------------------------------------------------------- 4. invalid / not-selected BGP paths

def _invalid(path: dict) -> dict:
    return {**path, "valid-route": False, "best-route": False, "used-route": False}


def test_srl_invalid_received_path_counts_as_present():
    """SR Linux skipped `valid-route: false`; EOS counted it. Received counts as present on every driver."""
    rib = json.loads(read("srl_leak_rib.txt"))
    rib["route"] = [_invalid(r) for r in rib["route"] if r["origin-protocol"] == "bgp"]
    routes = srlinux.parse_routes("{\n}", "0.0.0.0/0", _obj(rib))
    assert [(r.protocol, r.active) for r in routes] == [("bgp", False)]


def _frr_invalid_path_output() -> str:
    data = json.loads(read("frr_bgp_paths.txt"))
    for p in data["paths"]:
        p.pop("valid", None)
        p.pop("bestpath", None)
        for h in p.get("nexthops", []):
            h["accessible"] = False
    return _obj(data)


def test_frr_received_path_not_in_zebra_counts_as_present():
    """FRR read only zebra, so a received path with an unresolved next hop (never installed) read as
    absent and `route present: false` passed."""
    lab = Lab([("route", "{}"), ("show bgp", _frr_invalid_path_output())])
    routes = FrrDriver(lab, "r1").routes("192.168.20.0/24").value
    assert [(r.protocol, r.active) for r in routes] == [("bgp", False)]


def test_router_own_bgp_route_is_not_a_received_route_anywhere():
    """FRR, EOS and SR Linux agree: the router's own network/redistributed route in its BGP table is
    not a BGP route for the route check (it's still a path for bgp_route)."""
    lab = Lab([("route", "{}"), ("show bgp", read("frr_bgp_paths_local.txt"))])
    assert FrrDriver(lab, "r1").routes("192.168.21.0/24").value == []
    assert eos.parse_routes(_obj({"vrfs": {"default": {"routes": {}}}}), read("eos_bgp_paths_local.txt"),
                            "192.168.30.1/32") == []
    assert len(eos.parse_bgp_paths(read("eos_bgp_paths_local.txt"), "192.168.30.1/32")) == 1


def test_eos_invalid_received_path_counts_as_present():
    bgp = json.loads(read("eos_bgp_route.txt"))
    for e in bgp["vrfs"]["default"]["bgpRouteEntries"].values():
        for p in e["bgpRoutePaths"]:
            p["routeType"].update(valid=False, active=False)
    routes = eos.parse_routes(_obj({"vrfs": {"default": {"routes": {}}}}), _obj(bgp), "192.168.20.0/24")
    assert [(r.protocol, r.active) for r in routes] == [("bgp", False)]
