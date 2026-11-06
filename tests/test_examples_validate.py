"""Every shipped example passes `netdryrun validate` (preflight included, no deploy), and SONiC port names map to their
lab links (found 2026-11-07: examples/sonic-frr refused to run on every 0.4.1 candidate, because the 0.4.1 link_down
rule mapped SONiC's `Ethernet0` to `eth0`; nothing in the gate ran it)."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

from netdryrun import runner
from netdryrun.config import Fault, Scenario, load
from netdryrun.lab import LabError, sonic_device_for_lanes

from test_verdict_runner import make, route

ROOT = Path(__file__).resolve().parent.parent
FX = Path(__file__).parent / "fixtures"
sys.path.insert(0, str(ROOT / "scripts"))
import release_gate as gate  # noqa: E402

EXAMPLES = sorted(p.parent for p in (ROOT / "examples").glob("*/netdryrun.yml"))


def _section(title):
    text = (FX / "sonic_vs_port_map.txt").read_text(encoding="utf-8")
    part = text.split(f"--- {title}\n", 1)[1]
    return part.split("\n--- ", 1)[0]


@pytest.mark.parametrize("example", EXAMPLES, ids=lambda p: p.name)
def test_every_shipped_example_passes_preflight(example):
    runner.check_topology(load(example / "netdryrun.yml"))


def test_the_gate_check_passes_on_the_shipped_examples():
    assert gate.examples_validate() == []


def _old_container_iface(name, kind=""):
    """The pre-fix mapping (c6e99eb): every EthernetN is ethN, whatever the kind."""
    import re
    m = re.fullmatch(r"Ethernet(\d+)", name)
    if m:
        return f"eth{m.group(1)}"
    m = re.fullmatch(r"ethernet-(\d+)/(\d+)", name)
    return f"e{m.group(1)}-{m.group(2)}" if m else name


def test_red_fixture_sonic_frr_fails_preflight_on_the_pre_fix_mapping(monkeypatch):
    monkeypatch.setattr(runner, "_container_iface", _old_container_iface)
    with pytest.raises(LabError, match="link_down sonic1 Ethernet0: not an interface of a link in the topology"):
        runner.check_topology(load(ROOT / "examples" / "sonic-frr" / "netdryrun.yml"))


# ------------------------------------------------------------------------------------------- the SONiC map

def test_the_sonic_formula_matches_the_captured_port_map():
    """Each captured port's lanes name a lanemap device: the preflight mapping must agree with it."""
    lanemap = _section("lanemap.ini")
    ports = {}
    for line in _section("sonic-db-cli PORT lanes").splitlines():
        port, _, lanes = line.partition(": ")
        ports[port.strip()] = lanes.strip()
    checked = 0
    for port, lanes in ports.items():
        if any(ln.split(":")[1] == lanes for ln in lanemap.splitlines() if ":" in ln):
            assert runner._container_iface(port, "sonic-vs") == sonic_device_for_lanes(lanemap, lanes, "s1", port)
            checked += 1
    assert checked == 2      # Ethernet0 -> eth1, Ethernet4 -> eth2 (Ethernet8 has no lab link in the capture)


@pytest.mark.parametrize("name,kind,expected", [
    ("Ethernet0", "sonic-vs", "eth1"), ("Ethernet4", "sonic-vs", "eth2"), ("Ethernet124", "sonic_vs", "eth32"),
    ("Ethernet2", "sonic-vs", "Ethernet2"),             # not a port name of this HwSKU: no mapping, so refused
    ("Ethernet1", "arista_ceos", "eth1"), ("Ethernet1", "", "eth1"), ("ethernet-1/2", "nokia_srlinux", "e1-2"),
    ("eth3", "linux", "eth3"),
])
def test_container_iface_by_kind(name, kind, expected):
    assert runner._container_iface(name, kind) == expected


def test_sonic_device_for_lanes_exact():
    lanemap = "eth1:25,26,27,28\neth2:29,30,31,32\n\n"
    assert sonic_device_for_lanes(lanemap, "29,30,31,32\n") == "eth2"
    with pytest.raises(LabError) as e:
        sonic_device_for_lanes(lanemap, "33,34,35,36", "s1", "Ethernet8")
    assert str(e.value) == "s1: Ethernet8 (lanes 33,34,35,36) maps to 0 devices in lanemap.ini"
    with pytest.raises(LabError) as e:
        sonic_device_for_lanes("eth1:1,2\neth9:1,2", "1,2", "s1", "Ethernet0")
    assert str(e.value) == "s1: Ethernet0 (lanes 1,2) maps to 2 devices in lanemap.ini: eth1, eth9"
    with pytest.raises(LabError, match="isn't `device:lanes`"):
        sonic_device_for_lanes("eth1 25,26", "25,26")


def test_a_sonic_name_without_a_link_is_still_refused(monkeypatch):
    e = make(monkeypatch, kinds={"r1": ("sonic-vs", "docker-sonic-vs")})
    cfg = runner.Config(path=Path("netdryrun.yml"), lab=Path("t.clab.yml"), timeout=60, checks=[route("a")],
                        scenarios=[Scenario("s", [Fault("link_down", "r1", "Ethernet8")], [route("[s] x")])])
    with pytest.raises(LabError, match="link_down r1 Ethernet8: not an interface of a link"):
        runner.preflight(cfg, e.lab)
    cfg.scenarios = [Scenario("s", [Fault("link_down", "r1", "Ethernet0")], [route("[s] x")])]
    runner.preflight(cfg, e.lab)                        # r1's link is eth1: Ethernet0


# ------------------------------------------------------------------------------------------- confirmed on the node

def test_the_fault_confirms_the_sonic_port_on_the_node(monkeypatch):
    e = make(monkeypatch, kinds={"r1": ("sonic-vs", "docker-sonic-vs")})
    asked = []
    e.lab.sonic_port_device = lambda node, port: asked.append((node, port)) or "eth9"
    sc = Scenario("s", [Fault("link_down", "r1", "Ethernet0")], [route("[s] x", node="r3")])
    rep = e.run([route("a")], [sc])
    assert asked == [("r1", "Ethernet0")]
    assert rep.status == "error" and rep.error == ("scenario 's': r1 Ethernet0 is on eth9, not on the lab link eth1: "
                                                   "the fault would take another link down")
    assert not any(ev[0] == "link" and ev[2] == "Ethernet0" for ev in e.lab.events if len(ev) > 2)


def test_the_fault_goes_ahead_when_the_node_agrees(monkeypatch):
    e = make(monkeypatch, kinds={"r1": ("sonic-vs", "docker-sonic-vs")})
    e.lab.sonic_port_device = lambda node, port: "eth1"
    sc = Scenario("s", [Fault("link_down", "r1", "Ethernet0")], [route("[s] x", node="r3")])
    rep = e.run([route("a")], [sc])
    assert "is on eth" not in (rep.error or "")
