"""0.4.3: a check names an FRR BGP-unnumbered session by its interface (`neighbor: eth1`), and `record` writes it.

The live behaviour is pinned by oracle FP-043-UNNSESSCHK (captures from FRR 10.2.1); these are the unit tests of the
pieces: the config accepts an interface name where it can't be a mistyped address and asks for afi, every driver but
FRR refuses it before deploying, the FRR driver lists what such a session sent, and `record` writes the checks only
where the driver can read them (the 0.4.2 gap elsewhere).
"""
import json

import pytest

from netdryrun import record as rec
from netdryrun.config import Check, ConfigError, _validate_check, interface_peer
from netdryrun.drivers import DRIVERS, DriverError, check_supported
from netdryrun.drivers.base import BgpNeighbor
from netdryrun.drivers.frr import FrrDriver
from netdryrun.lab import Node
from test_verdict_drivers import Lab


def validate(**raw):
    return _validate_check(0, raw, 60)


@pytest.mark.parametrize("name", ["eth1", "swp1", "e1-1.0", "Ethernet0", "bond0.100", "eth1@if7"])
def test_an_interface_name_is_an_interface_peer(name):
    assert interface_peer(name)
    assert validate(type="bgp_session", node="r1", neighbor=name).params["neighbor"] == name


@pytest.mark.parametrize("value", ["10.0.0.1", "2001:db8::1", "10.0.0.256", "1.2.3", "10", "fe80::1%eth1",
                                   "eth 1", "a" * 16, "eth1;reboot", "", None, 7])
def test_an_address_or_a_bad_name_is_no_interface_peer(value):
    assert not interface_peer(value)


@pytest.mark.parametrize("value", ["10.0.0.256", "1.2.3", "eth 1", "abcdefghijklmnop", "eth1|x"])
def test_a_neighbor_that_is_neither_is_refused(value):
    with pytest.raises(ConfigError):
        validate(type="bgp_session", node="r1", neighbor=value)


def test_an_interface_neighbor_needs_its_afi():
    with pytest.raises(ConfigError, match="afi has no default"):
        validate(type="bgp_prefixes", node="r1", neighbor="eth1", max=3)
    c = validate(type="bgp_prefixes", node="r1", neighbor="eth1", max=3, afi="ipv6-unicast")
    assert c.params["neighbor"] == "eth1" and c.params["afi"] == "ipv6-unicast"


class FakeLab:
    nodes = {"frr": Node("frr", "clab-t-frr", "linux", "quay.io/frrouting/frr:10.2.1"),
             "eos": Node("eos", "clab-t-eos", "arista_ceos", "ceos:4.36"),
             "sonic": Node("sonic", "clab-t-sonic", "sonic-vs", "docker-sonic-vs")}


def check(ctype, node, **p):
    return Check(type=ctype, params={"node": node, "neighbor": "eth1", **p}, name=f"{node} {ctype}", timeout=1)


@pytest.mark.parametrize("ctype,extra", [("bgp_session", {"state": "established"}),
                                         ("bgp_prefixes", {"afi": "ipv4-unicast", "max": 3})])
def test_only_frr_takes_an_interface_neighbor(ctype, extra):
    check_supported(FakeLab(), check(ctype, "frr", **extra))
    for node in ("eos", "sonic"):
        with pytest.raises(DriverError, match="is an interface name"):
            check_supported(FakeLab(), check(ctype, node, **extra))
    for name, cls in DRIVERS.items():   # set by hand (nodes.<node>.driver) too
        if not cls.interface_peers:
            with pytest.raises(DriverError, match=f"the {name} driver can't check"):
                check_supported(FakeLab(), check(ctype, "frr", **extra), override=name)
    assert {n for n, c in DRIVERS.items() if c.interface_peers} == {"frr"}


def test_an_address_neighbor_is_not_refused_anywhere():
    for node in ("frr", "eos", "sonic"):
        check_supported(FakeLab(), Check(type="bgp_session", params={"node": node, "neighbor": "10.0.0.1",
                                                                     "state": "established"}, name="x", timeout=1))


def test_frr_lists_what_an_interface_session_sent():
    routes = {"routes": {"10.1.1.0/24": [{"valid": True, "network": "10.1.1.0/24"}],
                         "10.1.2.0/24": [{"valid": True, "network": "10.1.2.0/24"}]}, "totalRoutes": 2,
              "totalPaths": 2}
    lab = Lab([("neighbors eth1 routes json", json.dumps(routes))])
    got = FrrDriver(lab, "r1").bgp_received("eth1", "ipv4-unicast").value
    assert got == {"10.1.1.0/24", "10.1.2.0/24"}
    assert lab.lines() == ["vtysh -c show bgp ipv4 unicast neighbors eth1 routes json"]


def test_frr_lists_what_an_interface_session_in_a_vrf_sent():
    routes = {"routes": {"10.1.1.0/24": [{"valid": True, "network": "10.1.1.0/24"}]}, "totalRoutes": 1,
              "totalPaths": 1}
    lab = Lab([("vrf red ipv4 unicast neighbors eth1 routes json", json.dumps(routes))])
    got = FrrDriver(lab, "r1").bgp_received("eth1", "ipv4-unicast", "red").value
    assert got == {"10.1.1.0/24"}
    assert lab.lines() == ["vtysh -c show bgp vrf red ipv4 unicast neighbors eth1 routes json"]


def test_record_writes_vrf_and_only_for_an_interface_session_in_a_vrf():
    routes = {"routes": {"10.1.1.0/24": [{"valid": True, "network": "10.1.1.0/24"}]}, "totalRoutes": 1,
              "totalPaths": 1}
    lab = Lab([("vrf red ipv4 unicast neighbors eth1 routes json", json.dumps(routes))])
    nbrs = {"eth1": BgpNeighbor("eth1", "established", {"ipv4-unicast": 1}, external=True)}
    checks = rec._session_checks("r2", nbrs, "range", [], vrf="red", drv=FrrDriver(lab, "r2"))
    assert {"type": "bgp_session", "node": "r2", "neighbor": "eth1", "vrf": "red"} in checks
    mine = [c for c in checks if c["type"] == "bgp_prefixes" and c["afi"] == "ipv4-unicast"]
    assert len(mine) == 1 and mine[0]["vrf"] == "red" and mine[0]["only"] == ["10.1.1.0/24"], mine
    assert "vtysh -c show bgp vrf red ipv4 unicast neighbors eth1 routes json" in lab.lines()


@pytest.mark.parametrize("bad", ["eth1;reboot", "eth 1", "10.0.0.256"])
def test_frr_never_puts_a_bad_name_in_a_command(bad):
    lab = Lab([])
    with pytest.raises(DriverError):
        FrrDriver(lab, "r1").bgp_received(bad, "ipv4-unicast")
    assert lab.lines() == []


class FakeDriver:
    reads_received = True

    def __init__(self, name, interface_peers):
        self.name, self.interface_peers = name, interface_peers

    def bgp_received(self, neighbor, afi, vrf="default"):
        from netdryrun.drivers.base import Observation
        return Observation({"10.1.1.0/24", "10.1.2.0/24"}, [])


def unnumbered():
    return {"eth1": BgpNeighbor("eth1", "established", {"ipv4-unicast": 2}, external=True),
            "eth2": BgpNeighbor("eth2", "active", {}, external=True)}


def test_record_writes_every_check_a_numbered_session_gets_on_frr():
    warnings = []
    checks = rec._session_checks("r2", unnumbered(), "range", warnings, drv=FakeDriver("frr", True))
    assert {"type": "bgp_session", "node": "r2", "neighbor": "eth1"} in checks
    assert {"type": "bgp_prefixes", "node": "r2", "neighbor": "eth1", "afi": "ipv4-unicast", "min": 2, "max": 4,
            "only": ["10.1.1.0/24", "10.1.2.0/24"]} in checks
    # eBGP: a family the session doesn't carry is exactly 0, as for a numbered session
    assert {"type": "bgp_prefixes", "node": "r2", "neighbor": "eth1", "afi": "ipv6-unicast", "exact": 0} in checks
    # the session that is down today is the usual gap, named
    assert [w for w in rec.baseline_gaps(warnings) if "eth2" in w and "active" in w]
    for c in checks:   # and every one loads back
        validate(**c)


def test_record_names_the_gap_where_the_driver_cannot_check_it():
    warnings = []
    checks = rec._session_checks("s1", unnumbered(), "range", warnings, drv=FakeDriver("sonic", False))
    assert not [c for c in checks if c["neighbor"] == "eth1"]
    gaps = rec.baseline_gaps(warnings)
    assert [w for w in gaps if "eth1" in w and "no check can name on the sonic driver" in w]
