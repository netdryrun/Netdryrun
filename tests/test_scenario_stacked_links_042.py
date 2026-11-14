"""A link fault watches the BGP sessions on devices stacked on the downed interface (oracle FP-042-LINKDOWNSTACKED, red
team 042-GV B-RT-0078, RT-0078).

0.3.1 to 0.4.1 found the sessions over a downed link from the addresses of that interface only, so a session on its
VLAN subinterface (eth1.100@eth1) was never watched: the run logged "no BGP session runs over the downed links" and
judged at once, while r2 behind a bridge kept the route for its hold time. Lab.link_tree reads each device's lower
device and master, runner._stacked_on finds what the fault takes down with the interface, and their addresses and
names count as the link's. A device that can't be read stops the scenario (LabError, exit 2).
"""
import importlib.util
from pathlib import Path

import pytest

from netdryrun import runner
from netdryrun.lab import ExecResult, LabError, LinkDev

_PATH = Path(__file__).resolve().parent / "oracles" / "FP-042-LINKDOWNSTACKED" / "test_oracle_fp_042_linkdownstacked.py"
_SPEC = importlib.util.spec_from_file_location("oracle_fp_042_linkdownstacked_unit", _PATH)
o = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(o)

BOTH_ENDS = [("r1", "default", "10.0.100.2"), ("r2", "default", "10.0.100.1")]


def sessions(lab, drivers, links=(("r1", "eth1"),), log=None):
    return runner._link_sessions(lab, list(links), ["default"], lambda n: drivers[n], **({"log": log} if log else {}))


# --- the fix on the oracle's lab -------------------------------------------------------------------------------

def test_the_vlan_subinterface_session_is_watched_on_both_ends_and_named_in_the_log(tmp_path, monkeypatch):
    lab, drivers = o.make_lab(tmp_path, monkeypatch)
    logs = []
    watch, every = sessions(lab, drivers, log=logs.append)
    assert watch == BOTH_ENDS and every == BOTH_ENDS
    assert "  r1 eth1: also looking at the devices stacked on it (eth1.100)" in logs


def test_the_scenario_waits_for_the_far_end_and_the_route_check_fails(tmp_path, monkeypatch):
    lab, drivers = o.make_lab(tmp_path, monkeypatch)
    results, logs, err = o.run(lab, drivers, o.scenario())
    assert err is None, err
    assert not any(o.NOTHING_WATCHED in x for x in logs), logs
    assert any("the fault took effect after 180s" in x for x in logs), logs
    assert [r.passed for r in results] == [False]
    assert lab.devs["r1"]["eth1"].up and lab.devs["r1"]["eth1.100"].up   # restored; the subinterface never touched
    assert not any("eth1.100" in c and "set" in c for _n, c in lab.commands)


def test_link_tree_reads_lower_devices_and_masters(tmp_path, monkeypatch):
    lab, _ = o.make_lab(tmp_path, monkeypatch)
    tree = lab.link_tree("r1")   # one `ip -d -j link show`: every device, lo and eth0 too
    assert tree == {"lo": LinkDev(None, None), "eth0": LinkDev(None, None), "eth1": LinkDev(None, None),
                    "eth1.100": LinkDev("eth1", None, "vlan")}
    assert [c for n, c in lab.commands if n == "r1"] == ["ip -d -j link show"]
    lab, _ = o.make_lab(tmp_path, monkeypatch, o.plain_devices)
    assert lab.link_tree("r1")["eth1"] == (None, None, None, None, True)   # @if41: a veth peer in another namespace


def test_link_tree_reads_a_master_and_a_bond_of_two_members_takes_its_vlan_down_only_with_both(tmp_path, monkeypatch):
    """r1: eth1 and eth2 enslaved to bond0, the session on bond0.100@bond0 (iproute2's `master bond0` on each member)."""
    def devices(node, n):
        devs = o.stacked_devices(node, n)
        if node == "r1":
            devs = devs[:3] + [o.Dev("eth2", 7, "aa:c1:ab:01:00:02", [], peer_index=50),
                               o.Dev("bond0", 8, "aa:c1:ab:01:00:01", ["fe80::1/64"]),
                               o.Dev("bond0.100", 9, "aa:c1:ab:01:00:01", ["10.0.100.1/30"], parent="bond0", vlan=100)]
        return devs

    lab, drivers = o.make_lab(tmp_path, monkeypatch, devices)
    real = lab._json

    def json_(node, d, obj, family):
        j = real(node, d, obj, family)
        if node == "r1" and d.name in ("eth1", "eth2"):
            j["master"] = "bond0"
            j["linkinfo"] = {"info_kind": "veth", "info_slave_kind": "bond_slave"}
        if node == "r1" and d.name == "bond0":
            j["linkinfo"] = {"info_kind": "bond"}
        return j
    lab._json = json_
    tree = lab.link_tree("r1")
    assert tree["eth1"] == (None, "bond0", "veth", "bond_slave", True) and tree["eth2"].master == "bond0"
    assert tree["bond0.100"] == ("bond0", None, "vlan", None, True) and tree["bond0"].kind == "bond"
    assert sessions(lab, drivers, links=(("r1", "eth1"), ("r1", "eth2")))[0] == BOTH_ENDS
    assert sessions(lab, drivers) == ([], [])   # the bond keeps eth2: its VLAN's session stays up


def _with_exec(lab, answer):
    real = lab.exec

    def exec_(node, cmd, timeout=60, input=None):
        got = answer(node, list(cmd))
        return ExecResult(cmd, *got) if got is not None else real(node, cmd, timeout, input)

    lab.exec = exec_


def _r1_links(out, fallback=None):
    """r1's `ip -d -j link show` answers `out`; without JSON, `fallback(argv)` answers the per-device read (None: the
    fake kernel)."""
    def answer(n, c):
        if n == "r1" and c == ["ip", "-d", "-j", "link", "show"]:
            return out
        if n == "r1" and fallback is not None:
            return fallback(c)
        return None
    return answer


NO_JSON = (1, "", 'Option "-j" is unknown, try "ip -help".\n')


def _dev(name, got):
    return lambda c: got if c == ["ip", "-o", "link", "show", "dev", name] else None


@pytest.mark.parametrize("answer,match", [
    (_r1_links((0, "garbage\n", "")), "could not read the links on r1"),              # not JSON
    (_r1_links((0, "[]\n", "")), "could not read the links on r1"),                   # no device
    (_r1_links((0, '{"ifname": "eth1"}\n', "")), "could not read the links on r1"),   # not a list
    (_r1_links((0, '[{"ifname": "eth1"}]\n', "")), "could not read the links on r1"),  # no flags
    (_r1_links((0, '[{"ifname": "eth1", "flags": [], "linkinfo": 3}]\n', "")), "could not read the links on r1"),
    (_r1_links((0, '[{"ifname": "eth1", "flags": [], "link": 5}]\n', "")), "could not read the links on r1"),
    (_r1_links((0, '[{"ifname": "eth1", "flags": []}, {"ifname": "eth1", "flags": []}]\n', "")),
     "could not read the links on r1"),                                                 # listed twice
    # no JSON: `ls /sys/class/net` and one `ip -o link show dev X` each
    (_r1_links(NO_JSON, lambda c: (1, "", "ls: no such dir\n") if c == ["ls", "/sys/class/net"] else None),
     "could not read the links on r1"),
    (_r1_links(NO_JSON, lambda c: (0, "lo eth0\n", "") if c == ["ls", "/sys/class/net"] else None),
     "could not read the links on r1 .*: no device listed"),
    (_r1_links(NO_JSON, _dev("eth1.100", (1, "", 'Device "eth1.100" does not exist.\n'))),
     "could not read the links on r1 .*: the link of eth1.100"),
    (_r1_links(NO_JSON, _dev("eth1.100", (0, "garbage\n", ""))), "the link of eth1.100"),
    (_r1_links(NO_JSON, _dev("eth1.100", (0, "6: eth1.200@eth1: <UP> mtu 1500\n", ""))), "the link of eth1.100"),
    (_r1_links(NO_JSON, _dev("eth1.100", (0, "6: eth1.100@eth1: <UP> mtu 1500\n6: eth1.100@eth1: <UP> mtu 1500\n",
                                          ""))), "the link of eth1.100"),
    (lambda n, c: (1, "", "boom\n") if c[-1] == "eth1.100" and c[2] == "addr" else None,
     "could not read the addresses of eth1.100 on r1"),
])
def test_a_stacked_device_that_cannot_be_read_stops_the_scenario(tmp_path, monkeypatch, answer, match):
    lab, drivers = o.make_lab(tmp_path, monkeypatch)
    _with_exec(lab, answer)
    with pytest.raises(LabError, match=match):
        sessions(lab, drivers)
    lab, drivers = o.make_lab(tmp_path, monkeypatch)
    _with_exec(lab, answer)
    results, logs, err = o.run(lab, drivers, o.scenario())
    assert isinstance(err, LabError) and results is None
    assert lab.devs["r1"]["eth1"].up and not lab.down_at   # stopped before the link went down


def test_without_json_the_per_device_read_still_finds_the_subinterface(tmp_path, monkeypatch):
    lab, drivers = o.make_lab(tmp_path, monkeypatch)
    _with_exec(lab, _r1_links(NO_JSON, lambda c: None))
    assert lab.link_tree("r1") == {"eth1": LinkDev(None, None), "eth1.100": LinkDev("eth1", None)}   # lo, eth0 skipped
    assert sessions(lab, drivers) == (BOTH_ENDS, BOTH_ENDS)


def test_a_plain_link_reads_nothing_on_the_far_end_kernel(tmp_path, monkeypatch):
    lab, drivers = o.make_lab(tmp_path, monkeypatch, o.plain_devices)
    assert sessions(lab, drivers) == (BOTH_ENDS, BOTH_ENDS)
    assert not any(n == "r2" for n, _c in lab.commands)


def test_the_far_end_vlan_subinterface_name_counts_for_an_unnumbered_session(tmp_path, monkeypatch):
    lab, drivers = o.make_lab(tmp_path, monkeypatch)

    class Unnumbered:
        name = "frr"

        def __init__(self, key):
            self.key = key

        def bgp_neighbors(self, vrf="default"):
            return o.Observation({self.key: o.BgpNeighbor(self.key, "established", {"ipv4-unicast": 1})}, [])

    drivers = {"r1": Unnumbered("eth1.100"), "r2": Unnumbered("eth1.100")}
    watch, _every = sessions(lab, drivers)
    assert watch == [("r1", "default", "eth1.100"), ("r2", "default", "eth1.100")]
    drivers = {"r1": Unnumbered("eth1.200"), "r2": Unnumbered("eth1.200")}
    assert sessions(lab, drivers) == ([], [])


# --- which devices a fault takes down ----------------------------------------------------------------------------

TREE = {
    "eth1": (None, "bond0"), "eth2": (None, "bond0"), "eth3": (None, "br0"), "eth4": (None, "red"),
    "bond0": LinkDev(None, None, "bond"), "bond0.10": ("bond0", None), "br0": (None, None), "eth3.20": ("eth3", "br1"),
    "br1": (None, None), "mv0": ("eth4", None), "red": LinkDev(None, None, "vrf"), "eth5": (None, None),
    "eth5.30": ("eth5", None),
    "eth5.30.40": ("eth5.30", None),
}


@pytest.mark.parametrize("iface,downed,want", [
    ("eth5", {"eth5"}, {"eth5.30", "eth5.30.40"}),                 # VLAN on VLAN (QinQ)
    ("eth1", {"eth1"}, set()),                                     # a bond keeps its other member
    ("eth1", {"eth1", "eth2"}, {"bond0", "bond0.10"}),             # every member down: the bond and its VLAN
    ("eth2", {"eth1", "eth2"}, {"bond0", "bond0.10"}),
    ("eth3", {"eth3"}, {"br0", "eth3.20", "br1"}),                 # sole bridge port; a VLAN enslaved to another bridge
    ("eth4", {"eth4"}, {"mv0"}),                                   # macvlan; a VRF device keeps its carrier
    ("bond0", {"bond0"}, {"bond0.10"}),
    ("eth9", {"eth9"}, set()),                                     # not in the tree: nothing stacked
])
def test_stacked_on(iface, downed, want):
    assert runner._stacked_on(TREE, iface, downed) == want


def test_a_master_counts_for_the_interface_that_reaches_it_only():
    tree = {"eth1": (None, None), "eth2": (None, None), "eth1.5": ("eth1", "br0"), "eth2.5": ("eth2", "br0"),
            "br0": (None, None)}
    assert runner._stacked_on(tree, "eth1", {"eth1"}) == {"eth1.5"}
    assert runner._stacked_on(tree, "eth1", {"eth1", "eth2"}) == {"eth1.5", "br0"}
    assert runner._stacked_on(tree, "eth2", {"eth1", "eth2"}) == {"eth2.5", "br0"}
