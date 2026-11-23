"""0.4.3 mutation gate: config refusals, driver support refusals, EOS own-aggregate and RIB reads, FRR received
prefixes, the management settle and the runner's import-check and config-load steps.

Each error is pinned in full (who it names and what it says), and each runner step through a whole run on the fakes of
tests/test_runner_robustness.py.
"""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from netdryrun import mgmt, runner
from netdryrun.config import ConfigError, _validate_check
from netdryrun.drivers import check_supported, eos
from netdryrun.drivers.base import DriverError
from netdryrun.drivers.frr import FrrDriver
from netdryrun.lab import ExecResult, Node

from test_mgmt_settle_043 import replay, run as settle_run
from test_oracle_guards_fp_043_mgmtnh import DOCKER4, ROUTE_OUT, ReplayLab, load, pe1_before, samples, without
from test_runner_robustness import ALWAYS, FakeDriver, FakeLab, World, cfg, install

FX = Path(__file__).parent / "fixtures"


def U(command: str, text: str) -> str:
    """The driver's error for an answer it can't read (drivers.base.unexpected), as the user sees it."""
    return f"unexpected output from `{command}`: {' '.join(text.split())[:200]}"


def refused(**raw) -> str:
    with pytest.raises(ConfigError) as e:
        _validate_check(0, raw, 30.0)
    return str(e.value)


# ------------------------------------------------------------------------------------------- config

def test_an_interface_named_bgp_prefixes_neighbor_without_afi_says_so_in_full():
    assert refused(type="bgp_prefixes", node="r1", neighbor="eth1", max=3) == (
        "checks[0]: neighbor eth1 is an interface-named (BGP unnumbered) session, so afi has no default: set afi: "
        "ipv4-unicast or afi: ipv6-unicast")


@pytest.mark.parametrize("ctype,extra", [("bgp_session", {}), ("bgp_prefixes", {"max": 3})])
def test_a_neighbor_that_is_neither_an_address_nor_an_interface_says_so_in_full(ctype, extra):
    assert refused(type=ctype, node="r1", neighbor="10.0.0.256", **extra) == (
        "checks[0]: neighbor '10.0.0.256' is neither an IP address nor an interface name (letters, digits and . _ @ -, "
        "at most 15 characters)")


def test_an_attribute_above_32_bits_says_so_in_full():
    assert refused(type="bgp_route", node="r1", prefix="10.0.0.0/24", local_pref=2 ** 32) == (
        "checks[0]: local_pref must be at most 4294967295")


def test_a_vrf_that_is_not_a_name_says_so_in_full():
    assert refused(type="route", node="r1", prefix="10.0.0.0/24", vrf=True) == "checks[0]: vrf must be a VRF name, got True"


# ------------------------------------------------------------------------------------------- check_supported

def _lab():
    return SimpleNamespace(nodes={"r1": Node("r1", "clab-t-r1", "linux", "quay.io/frrouting/frr:10.4.1")})


def _unnumbered(ctype="bgp_session"):
    return _validate_check(0, {"type": ctype, "node": "r1", "neighbor": "eth1",
                               **({"afi": "ipv4-unicast", "max": 3} if ctype == "bgp_prefixes" else {})}, 30.0)


@pytest.mark.parametrize("ctype", ["bgp_session", "bgp_prefixes"])
def test_an_interface_named_session_on_an_address_keyed_driver_says_so_in_full(ctype):
    c = _unnumbered(ctype)
    with pytest.raises(DriverError) as e:
        check_supported(_lab(), c, "eos")
    assert str(e.value) == (f"{c.name}: neighbor eth1 is an interface name (a BGP unnumbered session), which the eos "
                            "driver can't check: it names BGP sessions by address. Name the neighbor's address, or use "
                            "route and ping checks")


def test_a_driver_name_with_no_driver_never_reads_an_interface_named_session():
    """Fail closed: a name DRIVERS doesn't hold has no interface_peers, so the check is refused, never let through."""
    c = _unnumbered()
    with pytest.raises(DriverError, match="which the nosuch driver can't check"):
        check_supported(_lab(), c, "nosuch")
    check_supported(_lab(), c, "frr")   # the one driver that keys sessions by interface


# ------------------------------------------------------------------------------------------- EOS

def _own_path() -> dict:
    """The node's own aggregate path, live (ceos4363m_advagg_advonly_ip_bgp.json, localAgg true)."""
    data = json.loads((FX / "ceos4363m_advagg_advonly_ip_bgp.json").read_text(encoding="utf-8"))
    [entry] = data["vrfs"]["default"]["bgpRouteEntries"].values()
    return entry["bgpRoutePaths"][0]


def _eos_error(p: dict) -> str:
    with pytest.raises(DriverError) as e:
        eos._own_aggregate(p)
    return str(e.value)


def test_the_live_own_aggregate_path_is_read_as_one():
    p = _own_path()
    assert p["routeType"]["localAgg"] is True and eos._own_aggregate(p) is True
    assert len(str(p)) > 151


@pytest.mark.parametrize("route_type", ["aggregate", None, 1])
def test_a_route_type_that_is_not_an_object_names_the_bgp_command(route_type):
    """DERIVED: the live path with routeType not an object: unknown, an error, never a crash."""
    p = dict(_own_path(), routeType=route_type)
    assert _eos_error(p) == U(eos.BGP_CMD, f"routeType.localAgg is None, not a boolean: {str(p)[:150]}")


def test_a_local_agg_flag_that_is_not_a_boolean_names_the_bgp_command():
    p = _own_path()
    p["routeType"] = dict(p["routeType"], localAgg="true")
    assert _eos_error(p) == U(eos.BGP_CMD, f"routeType.localAgg is 'true', not a boolean: {str(p)[:150]}")


def test_a_neighbors_path_marked_local_agg_names_the_bgp_command():
    """DERIVED: the live own path with a peer address: a neighbor's path can't be the node's own aggregate."""
    p = _own_path()
    p["peerEntry"] = dict(p["peerEntry"], peerAddr="10.0.0.2")
    assert _eos_error(p) == U(eos.BGP_CMD, f"a path from neighbor 10.0.0.2 marked localAgg: {str(p)[:150]}")


def test_a_rib_protocol_key_it_cannot_map_names_the_rib_command():
    """`routeInput` (a plain cEOS lists 0.0.0.0/8 under it, live) on the asked prefix: an error naming `show rib`."""
    text = json.dumps({"vrfs": {"default": {"ribRoutesByProtocol": {
        "routeInput": {"ribRoutes": {"10.9.9.0/24": {"bestRoute": True}}}}}}})
    with pytest.raises(DriverError) as e:
        eos.parse_rib_candidates(text, "10.9.9.0/24")
    assert str(e.value) == U(eos.RIB_CMD, "routeType 'routeInput' (read as 'routeinput') is not one this driver maps "
                                          "to a protocol")


# ------------------------------------------------------------------------------------------- FRR

def test_received_prefixes_from_a_neighbor_that_is_no_address_say_so_in_full():
    with pytest.raises(DriverError) as e:
        FrrDriver(SimpleNamespace(), "r1").bgp_received("10.0.0.256")
    assert str(e.value) == "the prefixes received from '10.0.0.256' can't be listed: not an address or an interface name"


# ------------------------------------------------------------------------------------------- management settle

def test_a_static_that_appears_during_the_wait_names_the_node():
    static = "10.77.0.0/16 via 172.20.20.1 dev eth0 proto static"
    rows = [(t, v4 + "\n" + static) for t, v4, _ in samples("t5")]
    b = pe1_before("t5")
    lab = ReplayLab("pe1", load("t5", "inspect_pe1.json"), b["ip -4 route show table all"],
                    b["ip -6 route show table all"], after=replay(rows))
    _, _, err = settle_run(lab)
    assert err is not None and err.startswith(
        "pe1 has a route out over the management network (after deleting Docker's default route): "), err


def test_two_routes_that_left_are_each_logged_and_recorded():
    """DERIVED from t1: a second BGP route via Docker's gateway beside the live one; both leave 1 s after the delete."""
    second = ROUTE_OUT.replace("198.51.100.0/24", "198.51.101.0/24")
    b = pe1_before("t1")
    v4 = b["ip -4 route show table all"].replace(ROUTE_OUT, ROUTE_OUT + "\n" + second)
    gone = without(without(without(v4, DOCKER4), ROUTE_OUT), second)
    lab = ReplayLab("pe1", load("t1", "inspect_pe1.json"), v4, b["ip -6 route show table all"],
                    after=lambda s: gone if s >= 1.0 else without(v4, DOCKER4))
    m, logs, err = settle_run(lab)
    assert err is None, err
    assert m.left == [ROUTE_OUT, second]
    assert [x for x in logs if "left the management network" in x] == [
        f"pe1: left the management network once Docker's default route was removed: {ROUTE_OUT}; {second} "
        f"(after {lab.slept:g}s)"]
    assert mgmt.describe(m, "linux").endswith(f"; left the management network once it was removed: {ROUTE_OUT}; {second}")


# ------------------------------------------------------------------------------------------- runner

def test_the_import_check_gap_reason_in_full():
    assert runner.import_check_gap_reason({"h1": "not checked: no vtysh answer", "h2": "not checked: rc 125"}) == (
        "FRR's import check could not be checked on h1, h2, so a route there may be announced with nothing behind it "
        "and the checks' results say nothing about the change: h1: no vtysh answer; h2: rc 125. Set "
        "`nodes.<node>.driver` for the node, or make it answer `vtysh`.")


class SrlLab(FakeLab):
    """r1-r3 (FRR) and an SR Linux node, srl1, whose log says it failed to load its startup config."""

    def __init__(self, world):
        super().__init__(world)
        self.nodes["srl1"] = Node("srl1", "clab-t-srl1", "nokia_srlinux", "ghcr.io/nokia/srlinux:26.7.2")
        self.asked: list = []

    def boot_log(self, node):
        return ExecResult([], 0, "[45|bgpd] done", "")

    def exec(self, node, cmd, timeout=60, input=None):
        self.asked.append((node, list(cmd)))
        if node == "srl1" and cmd[:1] == ["grep"]:
            return ExecResult(cmd, 0, f"Nov 21 11:50:01 srl1 sr_mgmt: {runner.SRL_LOAD_FAILED}: bad line\n", "")
        return super().exec(node, cmd, timeout, input)


def test_a_lab_the_run_did_not_deploy_leaves_sr_linux_load_unverified(tmp_path, monkeypatch):
    """`check` (deploy=False) on a lab it didn't deploy: SR Linux's startup-config load is not read (its deploy may
    have failed with the container still running), so it is neither clean nor an error."""
    w = World()
    lab = SrlLab(w)
    install(monkeypatch, w, lab, {n: FakeDriver(w) for n in ("r1", "r2", "r3")})
    rep = runner.run(cfg(tmp_path, [ALWAYS]), deploy=False, settle=0, hold=3)
    assert not rep.error and rep.status == "passed", rep.error
    assert not [c for n, c in lab.asked if n == "srl1"]


class UnclaimedFrrLab(FakeLab):
    """r1-r3 (FRR) and h1, an image no driver claims that answers vtysh as FRR does: found by probing."""

    def __init__(self, world):
        super().__init__(world)
        self.nodes["h1"] = Node("h1", "clab-t-h1", "linux", "registry.local/edge:1")

    def boot_log(self, node):
        return ExecResult([], 0, "[45|bgpd] done", "")


def test_the_import_check_guard_logs_into_the_run_log_both_times(tmp_path, monkeypatch):
    w = World()
    lab = UnclaimedFrrLab(w)
    install(monkeypatch, w, lab, {n: FakeDriver(w) for n in ("r1", "r2", "r3")})
    logs: list[str] = []
    runner.run(cfg(tmp_path, [ALWAYS]), deploy=False, settle=0, hold=3, log=logs.append)
    said = ("h1: no driver claims it, but vtysh answers with bgpd's running config: its import check is guarded as "
            "FRR's")
    assert logs.count(said) == 1 and logs.count(f"[before the verdict] {said}") == 1, logs
