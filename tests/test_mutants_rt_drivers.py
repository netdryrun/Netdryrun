"""Focused tests for small driver helpers: exact messages and values, so a changed constant, command name or default
is caught. Router output comes from the live captures in tests/fixtures; edits to it are named in each test."""
from __future__ import annotations

import ipaddress
import json
import re
from pathlib import Path

import pytest

from netdryrun.drivers import addresses, eos, junos, nxos
from netdryrun.drivers.base import DriverError, NoSuchInstance
from netdryrun.drivers.eos import EosDriver
from netdryrun.drivers.frr import FrrDriver
from netdryrun.drivers.junos import JunosDriver
from netdryrun.drivers.nxos import NxosDriver
from netdryrun.drivers.routeros import RouterosDriver
from netdryrun.drivers.routeros_state import parse_sessions
from netdryrun.drivers.srlinux import SrlDriver

from test_verdict_drivers import Lab

FX = Path(__file__).parent / "fixtures"


def fx(name):
    return (FX / name).read_text(encoding="utf-8")


def exact(msg):
    return rf"^{re.escape(msg)}$"


# ------------------------------------------------------------------------------------------- addresses._load

def test_load_skips_text_before_the_json_and_reads_either_bracket():
    assert addresses._load("c", 'banner line\n{"a": 1}') == {"a": 1}
    assert addresses._load("c", "noise [1, 2]") == [1, 2]
    assert addresses._load("c", 'x {"a": [1]}') == {"a": [1]}  # the earlier bracket wins


def test_load_error_names_the_command_and_the_error_and_cuts_the_text_at_120():
    text = "n" * 200                                            # no bracket at all
    cut = "n" * 120
    # Python's own wording of the min() error differs between versions (3.12: "iterable argument is empty"): only
    # Netdryrun's part of the message is pinned
    with pytest.raises(DriverError, match=r"^unexpected output from `my cmd`: not JSON \(min\(\) [^)]+\): '"
                                          + cut + r"'$"):
        addresses._load("my cmd", text)
    with pytest.raises(DriverError, match=exact(
            "unexpected output from `my cmd`: not JSON (Expecting value: line 1 column 2 (char 1)): '[nope'")):
        addresses._load("my cmd", "[nope")


# ------------------------------------------------------------------------------------------- addresses._iface

def test_iface_drops_a_scope_id_and_keeps_an_explicit_length():
    assert str(addresses._iface("c", "fe80::1%eth0")) == "fe80::1/128"
    assert str(addresses._iface("c", "fe80::1%eth0", 64)) == "fe80::1/64"
    assert str(addresses._iface("c", "10.0.0.1/24", 32)) == "10.0.0.1/24"      # a length in the text wins
    assert str(addresses._iface("c", "10.0.0.1", 32)) == "10.0.0.1/32"
    assert str(addresses._iface("c", "10.0.0.1", 24)) == "10.0.0.1/24"


def test_iface_error_names_the_command_and_the_first_60_characters():
    with pytest.raises(DriverError, match=exact("unexpected output from `ip -j addr`: not an address: 'nope'")):
        addresses._iface("ip -j addr", "nope")
    long = "z" * 100
    with pytest.raises(DriverError, match=exact(f"unexpected output from `c2`: not an address: '{'z' * 60}'")):
        addresses._iface("c2", long)
    with pytest.raises(DriverError, match=exact("unexpected output from `c3`: not an address: '5'")):
        addresses._iface("c3", 5)


def test_local_prefix_keeps_its_interface():
    iface = ipaddress.ip_interface("10.9.0.1/24")
    lp = addresses.LocalPrefix(iface)
    assert lp.iface is iface
    assert (lp.ip, lp.network, lp.version) == (iface.ip, iface.network, 4)
    assert str(lp) == "10.9.0.1/24 (lo: the whole prefix is local)"


# ------------------------------------------------------------------------------------------- eos

def test_eor_key_is_the_canonical_address_without_a_scope():
    assert eos._eor_key("fe80::1%Ethernet1") == "fe80::1"
    assert eos._eor_key("FE80:0:0:0:0:0:0:1") == "fe80::1"
    assert eos._eor_key("10.0.0.2") == "10.0.0.2"
    assert eos._eor_key("not-an-address") == "not-an-address"


def test_routing_vrf_names_the_command_in_every_refusal():
    cmd = "show ip route | json"
    with pytest.raises(NoSuchInstance, match=exact(
            f"VRF 'BLUE' is not in the output of `{cmd}` (VRFs listed: RED, default): it does not exist, or this "
            "command has nothing configured in it")):
        eos._routing_vrf(cmd, {"vrfs": {"default": {}, "RED": {}}}, "BLUE")
    with pytest.raises(DriverError, match=exact(
            f"unexpected output from `{cmd}`: vrf RED: routingDisabled is None, not a boolean")):
        eos._routing_vrf(cmd, {"vrfs": {"RED": {"routes": {}}}}, "RED")
    with pytest.raises(DriverError, match=exact(
            f"unexpected output from `{cmd}`: vrf RED: routingDisabled is 'yes', not a boolean")):
        eos._routing_vrf(cmd, {"vrfs": {"RED": {"routingDisabled": "yes"}}}, "RED")
    ok = {"routingDisabled": False, "routes": {}}
    assert eos._routing_vrf(cmd, {"vrfs": {"RED": ok}}, "RED") is ok


@pytest.mark.parametrize("name,vrf", [("eos_route_default_routing_disabled.json", "default"),
                                      ("eos_route_red_routing_disabled.json", "RED"),
                                      ("eos_route_red_v6_routing_disabled.json", "RED")])
def test_routing_disabled_message_is_exact(name, vrf):
    cmd = "show ip route | json"
    with pytest.raises(NoSuchInstance, match=exact(
            f"VRF {vrf!r} has routing disabled (`{cmd}`): nothing routes there, so no route check means anything "
            "in it")):
        eos._routing_vrf(cmd, json.loads(fx(name)), vrf)


# ------------------------------------------------------------------------------------------- junos._tables

def _leak_with(extra: str) -> str:
    text = fx("junos_route_leak.txt")
    i = text.index('"table-name"')
    return text[:i] + extra + text[i:]


def test_junos_tables_restart_state_refusals_are_exact():
    table = json.loads(fx("junos_route_leak.txt"))["route-information"][0]["route-table"][0]["table-name"][0]["data"]
    with pytest.raises(DriverError, match=exact(
            f"routing table {table} is in graceful-restart state 'Pending' (`CMD`): not settled")):
        junos._tables("CMD", _leak_with('"restart-state" : [{"data" : " Pending "}], '), table)
    # a state that is not text names the command
    with pytest.raises(DriverError, match=exact("unexpected output from `CMD2`: restart-state: 5")):
        junos._tables("CMD2", _leak_with('"restart-state" : [{"data" : 5}], '), table)
    # two restart-state leaves: the same
    with pytest.raises(DriverError, match=r"^unexpected output from `CMD3`: restart-state more than once"):
        junos._tables("CMD3", _leak_with('"restart-state" : [{"data" : "Complete"}, {"data" : "Complete"}], '), table)
    # "Complete" (with its padding) is settled
    assert junos._tables("CMD", _leak_with('"restart-state" : [{"data" : " Complete "}], '), table)


# ------------------------------------------------------------------------------------------- nxos._ascii_msg

def test_ascii_msg_reads_the_message_of_a_dict_result_only():
    f = nxos._ascii_msg
    assert f(json.dumps({"result": {"msg": "hello"}})) == "hello"
    assert f(json.dumps({"result": [{"msg": "one"}]})) == "one"
    assert f("not json") is None
    assert f(json.dumps([{"result": {"msg": "x"}}])) is None        # a list answer has no result
    assert f(json.dumps("text")) is None
    assert f(json.dumps({"result": "text"})) is None                # a result that is no map has no msg
    assert f(json.dumps({"result": [{"msg": "a"}, {"msg": "b"}]})) is None
    assert f(json.dumps({"result": [1]})) is None
    assert f(json.dumps({"result": {"msg": 5}})) is None
    assert f(json.dumps({})) is None


# ------------------------------------------------------------------------------------------- routeros neighbors

def test_routeros_neighbors_carry_the_end_of_rib_of_each_session():
    sessions = json.loads(fx("routeros_eor_pending.txt")[4:])
    for r in sessions:
        r["prefix-count"] = "0"                      # edit: no routes listed in the (empty) table below
    expected = {s.remote_address: dict(s.eor) for s in parse_sessions(sessions) if s.vrf == "default"}
    assert any(expected.values())
    d = RouterosDriver(Lab([("/routing/bgp/session", f"200\n{json.dumps(sessions)}"),
                            ("/routing/bgp/connection", "200\n[]"),
                            ("/routing/table", f"200\n{fx('routeros_rtable.txt')}"),
                            ("/routing/route", "200\n[]")]), "r1")
    got = d.bgp_neighbors().value
    assert {a: n.eor for a, n in got.items()} == expected


# ------------------------------------------------------------------------------------------- bgp_paths wrapper

DRIVERS = [EosDriver, FrrDriver, JunosDriver, NxosDriver, RouterosDriver, SrlDriver]


def _run(fn, cls, args):
    lab = Lab([("", (0, "{}", ""))])
    d = cls(lab, "n1")
    try:
        out = ("ok", fn(d, *args))
    except Exception as e:                                             # noqa: BLE001 - compared, not swallowed
        out = (type(e).__name__, str(e))
    return out, lab.lines()


@pytest.mark.parametrize("cls", DRIVERS, ids=lambda c: c.__name__)
def test_each_drivers_bgp_paths_is_the_llgr_checked_wrapper_and_defaults_to_the_default_vrf(cls):
    # The wrapper always passes the VRF on, so a driver's own default VRF is never used (its mutants are accepted as
    # equivalent). Only the wrapper is checked here: mutation testing replaces each method with a trampoline, so the
    # driver's own function can't be introspected portably.
    wrapper = cls.__dict__["bgp_paths"]
    assert wrapper._llgr_checked is True
    assert wrapper.__name__ == "bgp_paths"
    assert wrapper.__defaults__[0] == "default"
    via, lines_via = _run(cls.bgp_paths, cls, ("10.0.0.0/24",))
    explicit, lines_explicit = _run(cls.bgp_paths, cls, ("10.0.0.0/24", "default"))
    assert lines_via and (via, lines_via) == (explicit, lines_explicit)
    assert not any("XX" in ln or "DEFAULT" in ln for ln in lines_via)
