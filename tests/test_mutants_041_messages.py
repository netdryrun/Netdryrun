"""Mutation on b88adef: error texts that reach a user or an agent unchanged. Each test kills survivors that changed
only a message, where that message is documented (troubleshooting.md, the inject_routes reference) or carried in the
`error` field of the JSON report."""
import pytest

from netdryrun import runner
from netdryrun.drivers import DriverError, for_node, resolve
from netdryrun.lab import LabError, Node
from test_verdict_runner import Clock, Fault, FakeLab, Scenario, _cfg, _scenario, make, route


def test_preflight_names_every_unknown_node_and_the_topology():
    """preflight_13, preflight_15: the text troubleshooting.md shows."""
    with pytest.raises(LabError) as e:
        runner.preflight(_cfg([route("a", node="r8"), route("b", node="r9")]), FakeLab(Clock()))
    assert str(e.value) == "unknown node(s) r8, r9; the topology has r1, r2, r3"


def test_preflight_refuses_inject_routes_off_frr_in_the_documented_words():
    """preflight_50, preflight_51, preflight_52."""
    lab = FakeLab(Clock(), kinds={"r2": ("nokia_srlinux", "ghcr.io/nokia/srlinux:24.10")})
    sc = Scenario("s", [Fault("inject_routes", "r2", prefixes=["10.66.0.0/16"])], [route("x")])
    with pytest.raises(LabError) as e:
        runner.preflight(_cfg([route("a")], [sc]), lab)
    assert str(e.value) == ("inject_routes on r2 (srlinux) is not supported yet: it needs an FRR node; inject the "
                            "routes from an FRR neighbor instead")


def test_a_failed_restore_names_every_link_left_down(monkeypatch):
    """run_scenario_188, run_scenario_191."""
    e = make(monkeypatch)
    e.lab.set_link_error[("r1", "eth1", True)] = LabError("stuck")
    e.lab.set_link_error[("r2", "eth1", True)] = LabError("jammed")
    sc = Scenario("s", [Fault("link_down", "r1", "eth1"), Fault("link_down", "r2", "eth1")], [route("x", node="r3")])
    with pytest.raises(LabError) as err:
        runner.run_scenario(e.lab, sc, e.drivers, settle=1, hold=1, driver_for=lambda n: e.drivers[n])
    assert str(err.value) == "could not restore after scenario: r1 eth1: stuck; r2 eth1: jammed"


def test_a_failed_route_restore_carries_its_reason(monkeypatch):
    """run_scenario_177."""
    e = make(monkeypatch)
    orig = runner.RouteInjection

    class Failing(orig):
        def restore(self):
            raise LabError("routes still in r1's table")

    monkeypatch.setattr(runner, "RouteInjection", Failing)
    with pytest.raises(LabError) as err:
        runner.run_scenario(e.lab, _scenario(route("x", node="r3")), e.drivers, settle=1, hold=1,
                            driver_for=lambda n: e.drivers[n])
    assert str(err.value) == "could not restore after scenario: routes still in r1's table"


def test_for_node_errors_name_the_node_and_the_choices():
    """for_node_2, for_node_4, for_node_11."""
    lab = FakeLab(Clock())
    with pytest.raises(DriverError) as e:
        for_node(lab, "r9")
    assert str(e.value) == "node 'r9' is not in the topology (nodes: r1, r2, r3)"
    with pytest.raises(DriverError) as e:
        for_node(lab, "r1", "bogus")
    assert str(e.value).startswith("unknown driver 'bogus' for node r1; expected one of ['eos', ")


def test_an_image_with_several_other_marks_names_them_all():
    """_check_marks_14."""
    node = Node("r1", "clab-t-r1", "linux", "registry.local/ceos-junos-peer:1")
    with pytest.raises(DriverError) as e:
        resolve(node, "frr")
    assert str(e.value) == ("node r1 (kind='linux', image='registry.local/ceos-junos-peer:1'): the image name looks "
                            "like eos, junos, not frr; set nodes.r1.driver in netdryrun.yml")


def test_verify_carries_the_driver_mismatch_text_into_its_error():
    """classify_nodes_45, classify_nodes_46: the text becomes the JSON report's `error` field."""
    from netdryrun.verify import run as vrun

    class L:
        nodes = {"r2": Node("r2", "c2", "linux", "quay.io/frrouting/frr:10.4.1")}
    with pytest.raises(vrun.VerifyInputError) as e:
        vrun.classify_nodes(L(), {"r2": "srlinux"}, [])
    assert str(e.value) == ("node r2 (kind='linux', image='quay.io/frrouting/frr:10.4.1') is set to driver srlinux, "
                            "but its kind and image say frr; fix nodes.r2.driver in netdryrun.yml")


# --- run_scenario's progress lines: run_scenario decides verdicts, so its log calls are pinned, not accepted ---------

def test_a_scenario_logs_a_node_without_a_driver_over_its_links(monkeypatch):
    """run_scenario_58: _link_sessions gets the scenario's log."""
    e = make(monkeypatch)

    def driver_for(n):
        if n != "r3":
            raise DriverError("no driver here")
        return e.drivers[n]
    logs = []
    runner.run_scenario(e.lab, Scenario("s", [Fault("link_down", "r1", "eth1")], [route("x", node="r3")]), e.drivers,
                        settle=1, hold=1, driver_for=driver_for, log=logs.append)
    assert "  r1: no driver (no driver here); no BGP session to observe there" in logs


def test_a_scenario_logs_the_bgp_gate_warning(monkeypatch):
    """run_scenario_128: _bgp_convergence_gate gets the scenario's log."""
    e = make(monkeypatch, r3={"neighbors": {"default": {}}, "routes": {"default": lambda t, p: False},
                              "neighbors_error": DriverError("down")})
    logs = []
    runner.run_scenario(e.lab, _scenario(route("x", node="r3", present=False, timeout=6)), e.drivers, settle=1,
                        hold=1, driver_for=lambda n: e.drivers[n], log=logs.append)
    assert ("warning: convergence: r3's BGP state could not be read by the cap (6s); the check was evaluated without "
            "the BGP gate" in logs)


def test_a_failed_restore_logs_why_the_held_results_are_inconclusive(monkeypatch):
    """run_scenario_184: the restore-failed path hands _never_left the scenario's log."""
    e = make(monkeypatch)
    orig = runner.RouteInjection

    class Failing(orig):
        def restore(self):
            raise LabError("stuck")

    monkeypatch.setattr(runner, "RouteInjection", Failing)
    logs = []
    with pytest.raises(LabError):
        runner.run_scenario(e.lab, _scenario(route("x", node="r3")), e.drivers, settle=1, hold=1,
                            on_result=lambda r: None, driver_for=lambda n: e.drivers[n], log=logs.append)
    assert any(line.startswith("  inconclusive: the injected routes") for line in logs)
