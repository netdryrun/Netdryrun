"""A link fault watches the BGP sessions a bridge reached only through the downed port, and the far end of a SONiC port
(oracle FP-042-LINKDOWNBRIDGE, adversary n5d on 5f0b7d7, RT-0078 and RT-0079).

Since FP-042-LINKDOWNSTACKED, runner._link_sessions counted a bond, bridge or VRF master as down only once every
member went down. A bridge that keeps another port stays up, yet every peer it reached only through the downed port is
cut off: nothing was watched and the far end's route check passed on the state from before the fault.
runner._fault_reach now tells the master kinds apart (Lab.link_tree reads one `ip -d -j link show`): a bond keeps
today's all-members rule, a VRF device never goes down, a tunnel bound to the downed device keeps its carrier, and a
bridge that keeps another port (with what is stacked on it, SONiC's Vlan100@Bridge) is "bridged": the near end's
sessions with the far end's addresses and the far end's sessions with the bridge's addresses are watched. Where the
far end's addresses can't be read from its kernel (a NOS or VM kind) or it bridges further, the scenario stops
(LabError, exit 2). A SONiC port (`Ethernet0`) is mapped to the container interface the topology names (its lanes in
lanemap.ini) so the far end is found; an unreadable map stops the scenario.
"""
import importlib.util
from pathlib import Path

import pytest

from netdryrun import runner
from netdryrun.lab import ExecResult, LabError, LinkDev
from netdryrun.drivers.base import BgpNeighbor, Observation

_PATH = Path(__file__).resolve().parent / "oracles" / "FP-042-LINKDOWNBRIDGE" / "test_oracle_fp_042_linkdownbridge.py"
_SPEC = importlib.util.spec_from_file_location("oracle_fp_042_linkdownbridge_unit", _PATH)
o = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(o)

BOTH_ENDS = o.BOTH_ENDS


def sessions(lab, drivers, links=(("r1", "eth1"),), log=None):
    return runner._link_sessions(lab, list(links), ["default"], o.driver_for(drivers),
                                 **({"log": log} if log else {}))


class Many:
    """A BGP speaker with fixed established sessions."""
    name = "frr"

    def __init__(self, *keys):
        self.keys = keys

    def bgp_neighbors(self, vrf="default"):
        return Observation({k: BgpNeighbor(k, "established", {"ipv4-unicast": 1}) for k in self.keys}, [])


# --- a Linux bridge that keeps another port ---------------------------------------------------------------------

def test_the_bridge_session_is_watched_on_both_ends_and_named_in_the_log(tmp_path, monkeypatch):
    lab, drivers = o.bridge_lab(tmp_path, monkeypatch)
    logs = []
    assert sessions(lab, drivers, log=logs.append) == (BOTH_ENDS, BOTH_ENDS)
    assert ("  r1 eth1: a port of a bridge that keeps another port; also looking at the sessions between br0 and the "
            "far end of the link") in logs


def test_the_bridge_scenario_waits_for_the_far_end_and_the_route_check_fails(tmp_path, monkeypatch):
    lab, drivers = o.bridge_lab(tmp_path, monkeypatch)
    results, logs, err = o.run(lab, drivers, o.scenario())
    assert err is None, err
    assert any("the fault took effect after 180s" in x for x in logs), logs
    assert [r.passed for r in results] == [False]
    assert lab.devs["r1"]["eth1"].up and lab.devs["r1"]["br0"].up


def test_a_session_through_the_bridges_other_port_is_not_watched(tmp_path, monkeypatch):
    """r1 (br0 with eth1 to r2 and eth2 to r3) also peers with r3 at 10.0.100.3: that one stays up, so it is not
    waited for; r2's and r3's ends: only r2's session to br0's address is."""
    lab, _ = o.bridge_lab(tmp_path, monkeypatch)
    drivers = {"r1": Many("10.0.100.2", "10.0.100.3"), "r2": Many("10.0.100.1", "10.0.100.9"),
               "r3": Many("10.0.100.1")}
    assert sessions(lab, drivers) == (BOTH_ENDS, BOTH_ENDS)
    want = [("r1", "default", "10.0.100.3"), ("r3", "default", "10.0.100.1")]
    assert sessions(lab, drivers, links=(("r1", "eth2"),)) == (want, want)


def test_link_local_and_unnumbered_sessions_on_the_bridge(tmp_path, monkeypatch):
    lab, _ = o.bridge_lab(tmp_path, monkeypatch)
    drivers = {"r1": Many("fe80::a8c1:abff:fe02:1", "br0", "fe80::a8c1:abff:fe03:1"),
               "r2": Many("fe80::a8c1:abff:fe01:1", "eth1")}
    watch, _ = sessions(lab, drivers)
    assert watch == [("r1", "default", "br0"), ("r1", "default", "fe80::a8c1:abff:fe02:1"),
                     ("r2", "default", "eth1"), ("r2", "default", "fe80::a8c1:abff:fe01:1")]


def _far_end_kind(tmp_path, monkeypatch, kind):
    text = o.topology("rt0078k").replace("r2: {kind: linux", f"r2: {{kind: {kind}")
    return o.make_lab(tmp_path, monkeypatch, text, {"r1": o.bridge_r1(), "r2": o.far_end(2), "r3": o.far_end(3)},
                      r1_dev="br0")


@pytest.mark.parametrize("kind", ["ceos", "sonic-vs", "nokia_srlinux", "vr-sros"])
def test_a_bridge_port_whose_far_end_is_no_linux_node_stops_the_scenario(tmp_path, monkeypatch, kind):
    lab, drivers = _far_end_kind(tmp_path, monkeypatch, kind)
    with pytest.raises(LabError, match=f"far end r2 is a {kind} node"):
        sessions(lab, drivers)
    lab, drivers = _far_end_kind(tmp_path, monkeypatch, kind)
    results, logs, err = o.run(lab, drivers, o.scenario())
    assert isinstance(err, LabError) and results is None
    assert lab.devs["r1"]["eth1"].up and not lab.down_at   # stopped before the link went down


def test_a_bridge_port_whose_far_end_bridges_further_stops_the_scenario(tmp_path, monkeypatch):
    r2 = o.base(2) + [o.Dev("eth1", 5, o.mac(2, 1), [], master="br0", peer_index=42),
                      o.Dev("eth2", 6, o.mac(2, 2), [], master="br0", peer_index=52),
                      o.Dev("br0", 7, o.mac(2, 1), ["10.0.100.2/24"], kind="bridge")]
    lab, drivers = o.make_lab(tmp_path, monkeypatch, o.topology("rt0078f"),
                              {"r1": o.bridge_r1(), "r2": r2, "r3": o.far_end(3)}, r1_dev="br0", r2_dev="br0")
    with pytest.raises(LabError, match=r"r2 eth1 is a port of a bridge too \(br0\)"):
        sessions(lab, drivers)


def test_the_far_ends_vlan_subinterface_addresses_count_on_the_near_end(tmp_path, monkeypatch):
    """r1's br0.100@br0 (bridged with br0) peers with r2's eth1.100@eth1."""
    r1 = o.bridge_r1()[:-1] + [o.Dev("br0", 7, o.mac(1, 1), [], kind="bridge"),
                               o.Dev("br0.100", 8, o.mac(1, 1), ["10.0.100.1/24"], kind="vlan", lower="br0", vlan=100)]
    r2 = o.base(2) + [o.Dev("eth1", 5, o.mac(2, 1), [], peer_index=42),
                      o.Dev("eth1.100", 6, o.mac(2, 1), ["10.0.100.2/24"], kind="vlan", lower="eth1", vlan=100)]
    lab, drivers = o.make_lab(tmp_path, monkeypatch, o.topology("rt0078q"), {"r1": r1, "r2": r2, "r3": o.far_end(3)},
                              r1_dev="br0.100", r2_dev="eth1.100")
    assert sessions(lab, drivers) == (BOTH_ENDS, BOTH_ENDS)


def test_a_bridge_with_every_port_down_is_stacked_down(tmp_path, monkeypatch):
    lab, drivers = o.make_lab(tmp_path, monkeypatch, o.topology("rt0078a"),
                              {"r1": o.bridge_r1(), "r2": o.far_end(2), "r3": o.far_end(3)}, r1_dev="br0",
                              cut=o.cut_when_down("eth1", "eth2"))
    logs = []
    watch, _ = sessions(lab, drivers, links=(("r1", "eth1"), ("r1", "eth2")), log=logs.append)
    assert watch == BOTH_ENDS
    assert "  r1 eth1: also looking at the devices stacked on it (br0)" in logs
    assert not any("a port of a bridge" in x for x in logs)


# --- SONiC ---------------------------------------------------------------------------------------------------------

def test_sonic_svi_session_is_watched_on_both_ends(tmp_path, monkeypatch):
    lab, drivers = o.sonic_lab(tmp_path, monkeypatch)
    assert sessions(lab, drivers, links=(("r1", "Ethernet0"),)) == (BOTH_ENDS, BOTH_ENDS)
    assert ("r1", "sonic-db-cli CONFIG_DB hget PORT|Ethernet0 lanes") in lab.commands


def test_sonic_routed_port_far_end_is_watched(tmp_path, monkeypatch):
    lab, drivers = o.sonic_routed_lab(tmp_path, monkeypatch)
    assert sessions(lab, drivers, links=(("r1", "Ethernet0"),)) == (BOTH_ENDS, BOTH_ENDS)
    results, logs, err = o.run(*o.sonic_routed_lab(tmp_path, monkeypatch), o.scenario("Ethernet0"))
    assert err is None, err
    assert any("the fault took effect after 180s" in x for x in logs), logs
    assert [r.passed for r in results] == [False]


@pytest.mark.parametrize("lanes,match", [
    ("", "the port map for Ethernet0 can't be read"),
    ("29,30,31,32", "r1 Ethernet0 is on eth2"),       # eth2 is r1:eth2 in the topology: found, but see below
    ("1,2,3,4", "maps to 0 devices in lanemap.ini"),
])
def test_sonic_port_map_unreadable_or_off_the_topology_stops_the_scenario(tmp_path, monkeypatch, lanes, match):
    lab, drivers = o.sonic_routed_lab(tmp_path, monkeypatch)
    monkeypatch.setitem(o.PORT_LANES, "Ethernet0", lanes)
    if lanes == "29,30,31,32":
        # on eth2 (a topology link to r3): the far end is r3, and the run's own port check refuses the fault
        assert runner._link_end(lab, "r1", "Ethernet0") == "eth2"
        results, logs, err = o.run(lab, drivers, o.scenario("Ethernet0"))
        assert isinstance(err, LabError) and match in str(err), err
        return
    with pytest.raises(LabError, match=match):
        sessions(lab, drivers, links=(("r1", "Ethernet0"),))


def test_link_end(tmp_path, monkeypatch):
    lab, _ = o.sonic_routed_lab(tmp_path, monkeypatch)
    assert runner._link_end(lab, "r1", "eth1") == "eth1"                 # the topology's own name
    assert runner._link_end(lab, "r1", "Ethernet0") == "eth1"            # read from the node
    assert runner._link_end(lab, "r2", "Ethernet1") == "eth1"            # a cEOS-style name on a topology link
    assert runner._link_end(lab, "r2", "eth7") == "eth7"                 # no link: itself
    monkeypatch.setitem(o.PORT_LANES, "Ethernet8", "33,34,35,36")
    with pytest.raises(LabError):
        runner._link_end(lab, "r1", "Ethernet8")                          # no lanemap line
    lab.sonic_port_device = lambda node, port: "eth7"
    with pytest.raises(LabError, match="r1 Ethernet0 is on eth7, which no link of the topology names"):
        runner._link_end(lab, "r1", "Ethernet0")
    assert runner._link_end(lab, "r1", "Ethernet0", {("r1", "Ethernet0"): "eth1"}) == "eth1"   # confirmed already


def test_names_iface(tmp_path, monkeypatch):
    lab, _ = o.sonic_routed_lab(tmp_path, monkeypatch)
    assert runner._names_iface(lab, "r1", "Ethernet0", {"eth1"})        # SONiC port read from the node: on eth1
    assert not runner._names_iface(lab, "r1", "Ethernet4", {"eth1"})    # on eth2
    assert runner._names_iface(lab, "r2", "Ethernet1", {"eth1"})        # cEOS name of eth1
    assert runner._names_iface(lab, "r2", "eth1", {"eth1"})
    assert not runner._names_iface(lab, "r2", "eth2", {"eth1"})
    monkeypatch.setitem(o.PORT_LANES, "Ethernet0", "")
    with pytest.raises(LabError):
        runner._names_iface(lab, "r1", "Ethernet0", {"eth1"})


def test_an_unnumbered_session_on_a_sonic_far_end_is_watched(tmp_path, monkeypatch):
    """r2 (Linux) eth1 to SONiC r1's Ethernet0 (on eth1), unnumbered: r1's session is keyed Ethernet0."""
    lab, _ = o.sonic_routed_lab(tmp_path, monkeypatch)
    drivers = {"r1": Many("Ethernet0", "Ethernet4"), "r2": Many("eth1")}
    want = [("r1", "default", "Ethernet0"), ("r2", "default", "eth1")]
    assert sessions(lab, drivers, links=(("r2", "eth1"),)) == (want, want)
    assert sessions(lab, drivers, links=(("r1", "Ethernet0"),)) == (want, want)


# --- bonding_masters ------------------------------------------------------------------------------------------------

def test_bonding_masters_is_no_interface(tmp_path, monkeypatch):
    lab, drivers = o.make_lab(tmp_path, monkeypatch, o.topology("rt0078m"),
                              {"r1": o.plain_r1(), "r2": o.far_end(2), "r3": o.far_end(3)}, r1_dev="eth1",
                              bonding_masters=True)
    assert "bonding_masters" not in lab.link_tree("r1")
    assert lab.data_interfaces("r1") == ["eth1", "eth2"]
    assert sessions(lab, drivers) == (BOTH_ENDS, BOTH_ENDS)


# --- Lab.link_tree ------------------------------------------------------------------------------------------------

def test_link_tree_reads_kinds_masters_and_carrier(tmp_path, monkeypatch):
    lab, _ = o.sonic_lab(tmp_path, monkeypatch)
    tree = lab.link_tree("r1")
    assert tree["Ethernet0"] == LinkDev(None, "Bridge", "tun", "bridge_slave", True)
    assert tree["dummy"] == LinkDev(None, "Bridge", "dummy", "bridge_slave", True)
    assert tree["Vlan100"] == LinkDev("Bridge", None, "vlan", None, True)
    assert tree["eth1"] == LinkDev(None, None, "veth", None, True)
    lab.devs["r1"]["Ethernet0"].up = False
    assert lab.link_tree("r1")["Ethernet0"].carrier is False
    lab, _ = o.bridge_lab(tmp_path, monkeypatch)
    lab.devs["r1"]["eth1"].up = lab.devs["r1"]["eth2"].up = False
    tree = lab.link_tree("r1")
    assert tree["br0"].carrier is False and "UP" in lab._flags("r1", lab.devs["r1"]["br0"])   # admin-up, no carrier


def test_link_tree_falls_back_to_the_per_device_read(tmp_path, monkeypatch):
    """busybox `ip` has no -d or -j: `ls /sys/class/net` and `ip -o link show dev X`, kinds unknown but a bond's MASTER
    flag; lo and management are skipped, and so is bonding_masters."""
    lab, _ = o.bridge_lab(tmp_path, monkeypatch)
    real = lab.exec

    def exec_(node, cmd, timeout=60, input=None):
        if list(cmd) == ["ip", "-d", "-j", "link", "show"]:
            return ExecResult(cmd, 1, "", 'Option "-d" is unknown, try "ip -help".\n')
        return real(node, cmd, timeout, input)
    lab.exec = exec_
    tree = lab.link_tree("r1")
    assert tree["eth1"] == LinkDev(None, "br0", None, None, True)
    assert tree["br0"] == LinkDev(None, None, None, None, True)
    assert set(tree) == {"eth1", "eth2", "br0"}
    # a master whose kind isn't shown counts as a bridge: the session is still watched
    drivers = {"r1": Many("10.0.100.2"), "r2": Many("10.0.100.1")}
    assert sessions(lab, drivers) == (BOTH_ENDS, BOTH_ENDS)

    lab, _ = o.make_lab(tmp_path, monkeypatch, o.topology("rt0078b2"),
                        {"r1": o.base(1) + [o.Dev("eth1", 5, o.mac(1, 1), [], master="bond0", peer_index=41),
                                            o.Dev("bond0", 7, o.mac(1, 1), ["10.0.100.1/24"], kind="bond"),
                                            o.Dev("eth1.5", 8, o.mac(1, 1), [], kind="vlan", lower="eth1", vlan=5)],
                         "r2": o.far_end(2), "r3": o.far_end(3)}, r1_dev="bond0", bonding_masters=True)
    real2 = lab.exec

    def exec2(node, cmd, timeout=60, input=None):
        if list(cmd) == ["ip", "-d", "-j", "link", "show"]:
            return ExecResult(cmd, 255, "", "unknown option\n")
        return real2(node, cmd, timeout, input)
    lab.exec = exec2
    tree = lab.link_tree("r1")
    assert tree["bond0"].kind == "bond" and tree["eth1"].master == "bond0" and tree["eth1.5"].lower == "eth1"
    assert tree["eth1"].lower is None   # eth1@if41
    assert "bonding_masters" not in tree


# --- _fault_reach --------------------------------------------------------------------------------------------------

TREE = {
    "eth1": LinkDev(None, "br0", "veth", "bridge_slave"), "eth2": LinkDev(None, "br0", "veth", "bridge_slave"),
    "br0": LinkDev(None, None, "bridge"), "br0.10": LinkDev("br0", None, "vlan"),
    "eth3": LinkDev(None, "bond0", "veth", "bond_slave"), "eth4": LinkDev(None, "bond0", "veth", "bond_slave"),
    "bond0": LinkDev(None, None, "bond"), "bond0.20": LinkDev("bond0", "br9", "vlan", "bridge_slave"),
    "br9": LinkDev(None, None, "bridge"),
    "eth5": LinkDev(None, "red", "veth", "vrf_slave"), "red": LinkDev(None, None, "vrf"),
    "eth6": LinkDev(None, None, "veth"), "gre1": LinkDev("eth6", None, "gre"), "vx1": LinkDev("eth6", None, "vxlan"),
    "mv6": LinkDev("eth6", None, "macvlan"), "gre1.7": LinkDev("gre1", None, "vlan"),
    "eth7": LinkDev(None, "sw", None, "bridge_slave"), "eth8": LinkDev(None, "sw", None, None),
    "eth9": LinkDev(None, "tm", None, "team_slave"), "eth10": LinkDev(None, "tm", None, "team_slave"),
    "eth11": LinkDev(None, "odd", None, None), "eth12": LinkDev(None, "odd", None, None),
    "eth13": LinkDev(None, "bond1", "veth", "bond_slave"), "eth14": LinkDev(None, "bond1", "veth", "bond_slave", False),
    "bond1": LinkDev(None, None, "bond"),
    "eth15": LinkDev(None, "br2", "veth", "bridge_slave"), "eth16": LinkDev(None, "br2", "veth", "bridge_slave", False),
    "br2": LinkDev(None, None, "bridge"), "eth17": LinkDev(None, "mgmtbr", "veth", "bridge_slave"),
    "eth0": LinkDev(None, "mgmtbr", "veth", "bridge_slave"), "mgmtbr": LinkDev(None, None, "bridge"),
    "eth18": LinkDev(None, "bondx", None, "bond_slave"), "eth19": LinkDev(None, "bondx", None, "bond_slave"),
    "eth20": LinkDev(None, "vrfx", None, "vrf_slave"),
}


@pytest.mark.parametrize("iface,downed,stacked,bridged", [
    ("eth1", {"eth1"}, set(), {"br0", "br0.10"}),                 # a bridge that keeps eth2: bridged, with its VLAN
    ("eth1", {"eth1", "eth2"}, {"br0", "br0.10"}, set()),         # every port down: down
    ("eth3", {"eth3"}, set(), set()),                             # a bond that keeps eth4: neither
    ("eth3", {"eth3", "eth4"}, {"bond0", "bond0.20", "br9"}, set()),   # the bond down, its VLAN, and br9 (its only port)
    ("eth5", {"eth5"}, set(), set()),                             # a VRF device keeps its carrier
    ("eth6", {"eth6"}, {"mv6"}, set()),                           # tunnels (and what is on them) keep theirs
    ("eth7", {"eth7"}, set(), {"sw"}),                            # master kind from the slave kind: a bridge
    ("eth9", {"eth9"}, set(), set()),                             # a team is a bond
    ("eth11", {"eth11"}, set(), {"odd"}),                         # kind not shown: counted as a bridge
    ("eth13", {"eth13"}, {"bond1"}, set()),                       # the other member has no carrier: the bond goes
    ("eth15", {"eth15"}, {"br2"}, set()),                         # the other port has no carrier: the bridge goes
    ("eth17", {"eth17"}, set(), {"mgmtbr"}),                      # eth0 counts as a port too
    ("eth18", {"eth18"}, set(), set()),                           # master not listed: its kind from the slave kind
    ("eth20", {"eth20"}, set(), set()),
    ("eth99", {"eth99"}, set(), set()),
])
def test_fault_reach(iface, downed, stacked, bridged):
    assert runner._fault_reach(TREE, iface, downed) == (stacked, bridged)
    assert runner._stacked_on(TREE, iface, downed) == stacked
