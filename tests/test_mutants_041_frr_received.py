"""FrrDriver.bgp_received pinned for the 0.4.1 mutation gate: the command it sends for each family and VRF, the
family it reads the listing as, and what it refuses before asking. The listings are FRR 10.4.1 captures
(tests/fixtures/SOURCES.yml)."""
from pathlib import Path

import pytest

from netdryrun.drivers import frr
from netdryrun.drivers.base import DriverError
from netdryrun.drivers.frr import FrrDriver
from netdryrun.lab import ExecResult

FIXTURES = Path(__file__).parent / "fixtures"


def fixture(name):
    return (FIXTURES / name).read_text(encoding="utf-8")


class RecordingLab:
    def __init__(self, text):
        self.text, self.cmds = text, []

    def exec(self, node, cmd, timeout=60, input=None):
        self.cmds.append(cmd)
        return ExecResult(cmd, 0, self.text, "")


def vtysh(command):
    return ["vtysh", "-c", command]


def test_defaults_ask_ipv4_in_the_default_vrf_and_keep_evidence():
    """With no afi or vrf, the IPv4 listing of the default VRF is read (the capture's three routes), and the call is
    kept as evidence."""
    lab = RecordingLab(fixture("frr_received_routes.txt"))
    obs = FrrDriver(lab, "r1").bgp_received("10.1.1.2")
    assert obs.value == {"192.168.20.0/24", "192.168.21.0/24", "192.168.22.0/24"}
    assert lab.cmds == [vtysh("show bgp ipv4 unicast neighbors 10.1.1.2 routes json")]
    assert [e["cmd"] for e in obs.evidence] == ["vtysh -c show bgp ipv4 unicast neighbors 10.1.1.2 routes json"]


def test_a_named_vrf_is_in_the_command():
    lab = RecordingLab(fixture("frr_received_cust.txt"))
    FrrDriver(lab, "edge").bgp_received("10.0.0.2", "ipv4-unicast", "red")
    assert lab.cmds == [vtysh("show bgp vrf red ipv4 unicast neighbors 10.0.0.2 routes json")]


def test_ipv6_asks_the_ipv6_listing_and_reads_it_as_ipv6(monkeypatch):
    """ipv6-unicast sends the ipv6 command and parses the listing as family 6 (a family-4 read would let IPv4
    prefixes stand in for the IPv6 set)."""
    seen = []
    monkeypatch.setattr(frr, "parse_received", lambda text, family: seen.append(family) or set())
    lab = RecordingLab("{}")
    FrrDriver(lab, "r1").bgp_received("2001:db8::2", "ipv6-unicast")
    assert lab.cmds == [vtysh("show bgp ipv6 unicast neighbors 2001:db8::2 routes json")]
    FrrDriver(lab, "r1").bgp_received("10.1.1.2", "ipv4-unicast")
    assert seen == [6, 4]


def test_an_ipv4_listing_asked_as_ipv6_is_refused():
    """The real IPv4 capture answered for an ipv6-unicast question is unexpected output, never a set to compare."""
    with pytest.raises(DriverError):
        FrrDriver(RecordingLab(fixture("frr_received_routes.txt")), "r1").bgp_received("10.1.1.2", "ipv6-unicast")


def test_the_address_is_normalized_in_the_command():
    lab = RecordingLab("{}")
    FrrDriver(lab, "r1").bgp_received("2001:DB8:0::2", "ipv6-unicast")
    assert lab.cmds == [vtysh("show bgp ipv6 unicast neighbors 2001:db8::2 routes json")]


@pytest.mark.parametrize("afi", ["l2vpn-evpn", "ipv4-multicast"])
def test_another_afi_is_refused_before_asking(afi):
    lab = RecordingLab("{}")
    with pytest.raises(DriverError, match=f"the prefixes received in {afi} can't be listed"):
        FrrDriver(lab, "r1").bgp_received("10.1.1.2", afi)
    assert lab.cmds == []


def test_a_scoped_link_local_is_refused_before_asking():
    """fe80::1%eth1 parses as an address, but it can name several sessions: refused, not asked."""
    lab = RecordingLab("{}")
    with pytest.raises(DriverError, match="received from fe80::1%eth1 can't be listed: use a global address"):
        FrrDriver(lab, "r1").bgp_received("fe80::1%eth1", "ipv6-unicast")
    assert lab.cmds == []


def test_a_name_is_refused_before_asking():
    lab = RecordingLab("{}")
    with pytest.raises(DriverError, match="received from 'peer1' can't be listed: not an address"):
        FrrDriver(lab, "r1").bgp_received("peer1")
    assert lab.cmds == []
