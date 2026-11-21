"""Kill tests for the surviving runner mutants of the 0.4.2 mutation run on 83478f2 (group `runner`:
runner._link_sessions, runner._link_end, runner.run_scenario, runner._names_iface).

Device output: derived, not captured. The labs here are small duck-typed fakes built in this file (no `nodes` or
`links` where the test says so, to pin the getattr defaults), except the SONiC run test, which reuses the
FP-042-LINKDOWNBRIDGE oracle's fake kernel lab.
"""
import importlib.util
import ipaddress
from pathlib import Path
from types import SimpleNamespace

import pytest

from netdryrun import runner
from netdryrun.config import Fault, Scenario, _validate_check
from netdryrun.drivers.base import BgpNeighbor, DriverError, Observation
from netdryrun.lab import LabError, LinkDev

_PATH = Path(__file__).resolve().parent / "oracles" / "FP-042-LINKDOWNBRIDGE" / "test_oracle_fp_042_linkdownbridge.py"
_SPEC = importlib.util.spec_from_file_location("oracle_fp_042_linkdownbridge_kill_runner", _PATH)
o = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(o)

PLAIN = LinkDev(None, None, "veth", None, True)


class Speaker:
    """A BGP speaker with fixed established sessions (derived)."""
    name = "frr"

    def __init__(self, *keys):
        self.keys = keys

    def bgp_neighbors(self, vrf="default"):
        return Observation({k: BgpNeighbor(k, "established", {"ipv4-unicast": 1}) for k in self.keys}, [])


def driver_for(speakers):
    def get(node):
        if node not in speakers:
            raise DriverError(f"{node} runs no routing daemon")
        return speakers[node]
    return get


class DuckLab:
    """A Lab-like object (derived): only what _link_sessions reads. `nodes`/`links` are set only when given, so a lab
    without them exercises the getattr defaults."""

    def __init__(self, trees, addrs, peers, nodes=None, links=None, port_device=None):
        self._trees, self._addrs, self._peers = trees, addrs, peers
        if nodes is not None:
            self.nodes = {n: SimpleNamespace(kind=k) for n, k in nodes.items()}
        if links is not None:
            self.links = links
        if port_device is not None:
            self.sonic_port_device = port_device

    def link_tree(self, node):
        return self._trees[node]

    def interface_addresses(self, node, iface):
        return [ipaddress.ip_interface(a) for a in self._addrs.get((node, iface), [])]

    def peers_of(self, node, iface):
        return list(self._peers.get((node, iface), []))


def _bridge_lab(peers, nodes=None, links=None):
    """r1's eth1 and eth2 are ports of br0 (10.0.100.1/24); the far ends hold 10.0.100.n/24 on eth1."""
    trees = {"r1": {"eth1": LinkDev(None, "br0", "veth", "bridge_slave", True),
                    "eth2": LinkDev(None, "br0", "veth", "bridge_slave", True),
                    "br0": LinkDev(None, None, "bridge", None, True)},
             "r2": {"eth1": PLAIN}, "r3": {"eth1": PLAIN}}
    addrs = {("r1", "br0"): ["10.0.100.1/24"], ("r2", "eth1"): ["10.0.100.2/24"], ("r3", "eth1"): ["10.0.100.3/24"]}
    return DuckLab(trees, addrs, {("r1", "eth1"): peers}, nodes=nodes, links=links)


# --- _link_sessions -------------------------------------------------------------------------------------------------

def test_bridge_port_with_two_far_ends_watches_both(tmp_path):
    """x__link_sessions__mutmut_135: `far_ips |=` became `=`, so only the last far end's addresses counted and the
    session to the first far end over the bridge was not watched."""
    lab = _bridge_lab([("r2", "eth1"), ("r3", "eth1")], nodes={"r1": "linux", "r2": "linux", "r3": "linux"})
    watch, every = runner._link_sessions(lab, [("r1", "eth1")], ["default"],
                                         driver_for({"r1": Speaker("10.0.100.2", "10.0.100.3")}))
    want = [("r1", "default", "10.0.100.2"), ("r1", "default", "10.0.100.3")]
    assert watch == want and every == want


def test_bridge_port_on_a_lab_without_nodes_stops_with_a_lab_error():
    """x__link_sessions__mutmut_98, _102, _105: a far end the lab's `nodes` doesn't list has kind "" and stops the
    scenario with a LabError (exit 2), not a KeyError/TypeError/AttributeError crash."""
    lab = _bridge_lab([("r2", "eth1")])           # no `nodes`, no `links`
    with pytest.raises(LabError, match="the far end r2 is a"):
        runner._link_sessions(lab, [("r1", "eth1")], ["default"], driver_for({"r1": Speaker("10.0.100.2")}))
    lab = _bridge_lab([("r2", "eth1")], nodes={"r1": "linux"})   # `nodes` without the far end
    with pytest.raises(LabError, match="the far end r2 is a"):
        runner._link_sessions(lab, [("r1", "eth1")], ["default"], driver_for({"r1": Speaker("10.0.100.2")}))


def test_unnumbered_sonic_session_named_by_its_port_is_watched():
    """x__link_sessions__mutmut_150, _151: the near end's unnumbered key `Ethernet0` is matched with the node's own
    port map (SONiC: Ethernet0 on eth1); with the lab or the node dropped it was read as `eth0` and not watched."""
    lab = DuckLab({"r1": {"eth1": PLAIN}, "r2": {"eth1": PLAIN}}, {}, {("r1", "eth1"): [("r2", "eth1")]},
                  nodes={"r1": "sonic-vs", "r2": "linux"}, links=[(("r1", "eth1"), ("r2", "eth1"))],
                  port_device=lambda node, port: {"Ethernet0": "eth1", "Ethernet4": "eth2"}[port])
    watch, every = runner._link_sessions(lab, [("r1", "eth1")], ["default"],
                                         driver_for({"r1": Speaker("Ethernet0", "Ethernet4")}))
    assert watch == every == [("r1", "default", "Ethernet0")]


def test_link_sessions_uses_the_port_map_the_caller_confirmed():
    """x__link_sessions__mutmut_77, _81: `ports` (read from the node by run_scenario) decides the far end; dropping it
    re-read the port map, and a second read naming another link (eth2, to r3) watched the wrong far end."""
    reads = []

    def port_device(node, port):
        reads.append((node, port))
        return "eth2"
    links = [(("r1", "eth1"), ("r2", "eth1")), (("r1", "eth2"), ("r3", "eth1"))]
    lab = DuckLab({"r1": {"Ethernet0": PLAIN}, "r2": {"eth1": PLAIN}, "r3": {"eth1": PLAIN}},
                  {("r1", "Ethernet0"): ["10.0.100.1/24"]},
                  {("r1", "eth1"): [("r2", "eth1")], ("r1", "eth2"): [("r3", "eth1")]},
                  nodes={"r1": "sonic-vs", "r2": "linux", "r3": "linux"}, links=links, port_device=port_device)
    speakers = {"r1": Speaker("10.0.100.2"), "r2": Speaker("10.0.100.1"), "r3": Speaker("10.0.100.1")}
    watch, _ = runner._link_sessions(lab, [("r1", "Ethernet0")], ["default"], driver_for(speakers),
                                     ports={("r1", "Ethernet0"): "eth1"})
    assert watch == [("r1", "default", "10.0.100.2"), ("r2", "default", "10.0.100.1")]
    assert reads == []


# --- _link_end -------------------------------------------------------------------------------------------------------

def test_link_end_on_a_lab_without_nodes_or_links():
    """x__link_end__mutmut_3, _7, _10 (nodes default), _17, _20 (links default): a lab without them names the
    interface itself."""
    lab = SimpleNamespace()
    assert runner._link_end(lab, "r1", "Ethernet1") == "Ethernet1"
    assert runner._link_end(SimpleNamespace(links=[(("r1", "eth1"), ("r2", "eth1"))]), "r1", "Ethernet1") == "eth1"
    assert runner._link_end(SimpleNamespace(nodes={}), "r1", "eth1") == "eth1"


def test_link_end_sonic_without_a_port_reader_uses_the_lane_rule():
    """x__link_end__mutmut_31, _39, _45, _46, _47, _48: a SONiC node on a lab with no sonic_port_device falls back to
    the four-lanes rule (Ethernet0 on eth1, Ethernet4 on eth2)."""
    lab = SimpleNamespace(nodes={"r1": SimpleNamespace(kind="sonic-vs")},
                          links=[(("r1", "eth1"), ("r2", "eth1")), (("r1", "eth2"), ("r3", "eth1"))])
    assert runner._link_end(lab, "r1", "Ethernet0") == "eth1"
    assert runner._link_end(lab, "r1", "Ethernet4") == "eth2"


def test_link_end_keeps_a_name_no_link_names():
    """x__link_end__mutmut_59: a cEOS-style name whose container interface no link names is returned as it is, not
    as the unlinked container name."""
    lab = SimpleNamespace(nodes={"r2": SimpleNamespace(kind="ceos")}, links=[(("r2", "eth1"), ("r1", "eth1"))])
    assert runner._link_end(lab, "r2", "Ethernet7") == "Ethernet7"
    assert runner._link_end(lab, "r2", "Ethernet1") == "eth1"


# --- _names_iface ----------------------------------------------------------------------------------------------------

def test_names_iface_on_a_lab_without_nodes():
    """x__names_iface__mutmut_5, _9, _12."""
    assert runner._names_iface(SimpleNamespace(), "r1", "Ethernet1", {"eth1"})
    assert runner._names_iface(SimpleNamespace(nodes={}), "r1", "Ethernet1", {"eth1"})


def test_names_iface_sonic_without_a_port_reader_uses_the_lane_rule():
    """x__names_iface__mutmut_22, _25, _40, _42: a SONiC node on a lab with no sonic_port_device: Ethernet4 is on
    eth2 by the four-lanes rule (not eth4)."""
    lab = SimpleNamespace(nodes={"r1": SimpleNamespace(kind="sonic-vs")})
    assert runner._names_iface(lab, "r1", "Ethernet4", {"eth2"})
    assert not runner._names_iface(lab, "r1", "Ethernet4", {"eth4"})


# --- run_scenario: the plan of links to take down --------------------------------------------------------------------

class PlanLab:
    """A Lab-like object (derived) for run_scenario's planning: admin state per interface, set_link recorded."""

    def __init__(self, ifaces, admin_down=()):
        self.ifaces = ifaces
        self.up = {(n, i): (n, i) not in set(admin_down) for n, lst in ifaces.items() for i in lst}
        self.nodes = {n: SimpleNamespace(kind="linux") for n in ifaces}
        self.set_down = []

    def _require_linux_links(self, node):
        pass

    def data_interfaces(self, node):
        return list(self.ifaces[node])

    def admin_up(self, node, iface):
        return self.up[(node, iface)]

    def set_link(self, node, iface, up):
        self.up[(node, iface)] = up
        if not up:
            self.set_down.append((node, iface))


def _plan(monkeypatch, lab, faults):
    """Run the scenario with the observation and check steps stubbed: (the links planned, the links set down, logs)."""
    seen = {}

    def link_sessions(lab_, links, vrfs, driver_for, log=None, ports=None):
        seen["links"] = list(links)
        return [], []
    monkeypatch.setattr(runner, "_link_sessions", link_sessions)
    monkeypatch.setattr(runner, "_wait_fault_visible", lambda *a, **k: None)
    monkeypatch.setattr(runner, "_reach_then_hold", lambda *a, **k: [])
    monkeypatch.setattr(runner, "_sleep", lambda s: None)
    check = _validate_check(0, {"type": "route", "node": "r9", "prefix": "10.1.0.0/24", "protocol": "bgp"}, 30,
                            prefix="scenarios[0].checks")
    logs = []
    runner.run_scenario(lab, Scenario("s", faults, [check]), {}, settle=0, hold=0, log=logs.append,
                        driver_for=lambda n: None)
    return seen.get("links"), lab.set_down, logs


def test_node_isolated_after_a_link_down_on_the_same_node_takes_every_other_link_down(monkeypatch):
    """x_run_scenario__mutmut_36: `continue` became `break` on a link another fault plans already, so the rest of
    the node's links were never taken down (the node was not isolated)."""
    lab = PlanLab({"r1": ["eth1", "eth2", "eth3"]})
    links, down, _ = _plan(monkeypatch, lab, [Fault("link_down", "r1", "eth1"), Fault("node_isolated", "r1")])
    assert links == [("r1", "eth1"), ("r1", "eth2"), ("r1", "eth3")]
    assert down == links


def test_node_isolated_skips_only_the_link_already_down(monkeypatch):
    """x_run_scenario__mutmut_50, _53: a link the lab keeps down is logged and skipped, and the node's later links are
    still taken down (`break` left them up; `log(None)` lost the line)."""
    lab = PlanLab({"r1": ["eth1", "eth2", "eth3"]}, admin_down=[("r1", "eth2")])
    links, down, logs = _plan(monkeypatch, lab, [Fault("node_isolated", "r1")])
    assert links == down == [("r1", "eth1"), ("r1", "eth3")]
    assert any(isinstance(x, str) and "r1 eth2 is already administratively down" in x for x in logs), logs


def test_node_isolated_whose_links_another_fault_takes_down_is_not_refused(monkeypatch):
    """x_run_scenario__mutmut_77: `and not any(...)` became `or not any(...)`, refusing a node_isolated whose every
    link an earlier fault of the scenario takes down."""
    lab = PlanLab({"r1": ["eth1"]})
    links, down, _ = _plan(monkeypatch, lab, [Fault("link_down", "r1", "eth1"), Fault("node_isolated", "r1")])
    assert links == down == [("r1", "eth1")]


def test_node_isolated_that_changes_nothing_is_refused_even_with_another_nodes_fault(monkeypatch):
    """x_run_scenario__mutmut_85: `n == f.node` became `n != f.node`, so a node_isolated whose every link is already
    down ran (vacuously) when another node had a link planned."""
    lab = PlanLab({"r1": ["eth1", "eth2"], "r2": ["eth1"]}, admin_down=[("r1", "eth1"), ("r1", "eth2")])
    with pytest.raises(LabError, match="every lab link of r1 is already administratively down"):
        _plan(monkeypatch, lab, [Fault("link_down", "r2", "eth1"), Fault("node_isolated", "r1")])
    assert lab.set_down == []


def test_sonic_run_uses_the_port_map_read_before_the_fault(tmp_path, monkeypatch):
    """x_run_scenario__mutmut_112, _118: run_scenario reads each SONiC port's device once, before the fault, and hands
    it to _link_sessions (`ports`). Without it the port map was read again; a second read naming another link (eth2,
    to r3) left r2's end unwatched and the route check on r2 passed on the state from before the fault."""
    lab, drivers = o.sonic_routed_lab(tmp_path, monkeypatch)
    real = lab.sonic_port_device
    reads = []

    def port_device(node, port):
        reads.append((node, port))
        return real(node, port) if len(reads) == 1 else "eth2"
    lab.sonic_port_device = port_device
    results, logs, err = o.run(lab, drivers, o.scenario("Ethernet0"))
    assert err is None, err
    assert reads == [("r1", "Ethernet0")]
    o.assert_judged_after_the_fault(results, logs, "r2's end of the session runs over the downed port")
