"""NX-OS and RouterOS are unreleased beta drivers: used only when a node names them (`nodes.<node>.driver`), never
detected from a kind or image, and a run that uses one says so (Layer 6 on b03cb7a: they were registered and
auto-detected like the released drivers)."""
import pytest

from netdryrun import runner
from netdryrun.drivers import BETA_DRIVERS, DriverError, detect
from netdryrun.lab import Node


@pytest.mark.parametrize("node,name,label", [
    (Node("n1", "clab-t-n1", "cisco_n9kv", "vrnetlab/cisco_n9kv:10.5.3"), "nxos", "Cisco NX-OS"),
    (Node("m1", "clab-t-m1", "mikrotik_ros", "vrnetlab/mikrotik_routeros:7.23.8"), "routeros", "MikroTik RouterOS"),
    (Node("m2", "clab-t-m2", "linux", "mikrotik/routeros:7.23"), "routeros", "MikroTik RouterOS"),
])
def test_a_beta_driver_is_never_detected(node, name, label):
    with pytest.raises(DriverError) as e:
        detect(node)
    assert str(e.value) == (f"node {node.name} (kind={node.kind!r}, image={node.image!r}) runs {label}, whose driver "
                            f"is an unreleased beta: it is used only when chosen, with nodes.{node.name}.driver: "
                            f"{name} in netdryrun.yml")


def test_the_beta_drivers_are_nxos_and_routeros():
    assert BETA_DRIVERS == frozenset({"nxos", "routeros"})


def test_a_run_that_uses_one_says_so():
    from types import SimpleNamespace
    lines = []
    runner._warn_beta(SimpleNamespace(drivers={"n1": "nxos", "r1": "frr"}), lines.append)
    assert lines == ["Warning: n1 uses the nxos driver, an unreleased beta: its verdicts are not covered by a "
                     "released gate yet"]


def test_run_warns_for_a_beta_driver_after_preflight(monkeypatch):
    from test_verdict_runner import make, route
    e = make(monkeypatch, kinds={"r1": ("cisco_n9kv", "vrnetlab/vr-n9kv:10.4")})
    e.run([route("a")], drivers_cfg={"r1": "nxos"})
    assert ("Warning: r1 uses the nxos driver, an unreleased beta: its verdicts are not covered by a released gate "
            "yet") in e.logs


@pytest.mark.parametrize("override", ["eos", "frr"])
def test_a_node_detected_as_a_beta_nos_refuses_another_driver(override):
    """Mutation on b88adef (drivers.resolve_6, BetaDriver.__init___2, _beta_2): the beta NOS detection names is what a
    set driver is checked against; an image with no NOS mark leaves nothing else to catch the mismatch."""
    from netdryrun.drivers import BetaDriver, _detect, resolve
    node = Node("n1", "clab-t-n1", "cisco_n9kv", "registry.local/switch:1")
    with pytest.raises(BetaDriver) as e:
        _detect(node)
    assert e.value.driver == "nxos"
    with pytest.raises(DriverError, match=f"is set to driver {override}, but its kind and image say nxos"):
        resolve(node, override)
    assert resolve(node, "nxos") == "nxos"
