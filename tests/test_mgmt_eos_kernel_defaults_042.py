"""_eos_only_kernel_defaults: prepare_eos waits only while every route cEOS lists over Management (connected ones in
the management subnet aside) is a `kernel` default via a management gateway, and the running config has no static of
ours or another one over Management. Anything else ends the wait at once, and is then judged by check_eos. Inputs
shaped like `show ip[v6] route vrf all | json` (cEOS 4.36.3M) and containerlab's config lines."""
import json

import pytest

from netdryrun import mgmt
from netdryrun.lab import ExecResult, LabError
from netdryrun.mgmt import ManagementPathError
from test_mgmt import GW4, GW6, m_of
from test_mgmt_eos_kernel_042 import KernelLab
from fakes import UnexpectedCommand, seen

V4_CMD, V6_CMD = "show ip route vrf all | json", "show ipv6 route vrf all | json"


def _via(gw, intf="Management0"):
    v = {"interface": intf}
    if gw is not None:
        v["nexthopAddr"] = gw
    return v


def _r(rtype, *vias):
    return {"routeType": rtype, "vias": list(vias)}


KERNEL4 = _r("kernel", _via(GW4))
KERNEL6 = _r("kernel", _via(GW6))
CONNECTED4 = _r("connected", {"interface": "Management0"})          # 172.31.99.0/24, the management subnet
CONNECTED6 = _r("connected", {"interface": "Management0"})          # 3fff:172:31:99::/64
LAB_ROUTE = _r("static", _via("10.0.0.2", "Ethernet1"))             # a lab route, not over Management


def _table(*vrfs):
    return json.dumps({"vrfs": {name: {"routes": routes} for name, routes in vrfs}})


class TableLab:
    """A cEOS node answering `show running-config` and the two route tables; records every command it was sent."""

    def __init__(self, v4=None, v6=None, running="hostname e1\n"):
        self.running = running
        self.out = {V4_CMD: v4 if isinstance(v4, str) else _table(("default", v4 or {})),
                    V6_CMD: v6 if isinstance(v6, str) else _table(("default", v6 or {}))}
        self.sent: list[str] = []

    def exec(self, node, cmd, timeout=60, input=None):
        assert node == "r1" and cmd[:4] == ["Cli", "-p", "15", "-c"]
        c = cmd[-1]
        self.sent.append(c)
        seen(c)
        if c == "show running-config":
            return ExecResult(cmd, 0, self.running, "")
        if c in self.out:
            return ExecResult(cmd, 0, self.out[c], "")
        raise UnexpectedCommand(c)


def only(lab):
    return mgmt._eos_only_kernel_defaults(lab, m_of())


# ------------------------------------------------------------------- the running config decides first

@pytest.mark.parametrize("running", [
    "hostname e1\nip route 0.0.0.0/0 172.31.99.1\n",                 # containerlab's own default, still there
    "hostname e1\nipv6 route ::0/0 3fff:172:31:99::1\n",
    "hostname e1\nip route 10.77.0.0/16 172.31.99.1\n",              # another static over Management
    "hostname e1\nip route 0.0.0.0/0 Management0\n",
])
def test_a_static_over_management_in_the_running_config_is_not_waited_out(running):
    lab = TableLab(v4={"0.0.0.0/0": KERNEL4}, v6={"::/0": KERNEL6}, running=running)
    assert only(lab) is False
    assert lab.sent == ["show running-config"]                       # decided on the config, no table read


def test_a_lab_static_in_the_config_does_not_stop_the_wait():
    lab = TableLab(v4={"0.0.0.0/0": KERNEL4}, running="hostname e1\nip route 10.77.0.0/16 10.0.0.2\n")
    assert only(lab) is True


# ------------------------------------------------------------------- the tables

def test_exact_commands_in_order():
    lab = TableLab(v4={"0.0.0.0/0": KERNEL4}, v6={"::/0": KERNEL6})
    assert only(lab) is True
    assert lab.sent == ["show running-config", V4_CMD, V6_CMD]


def test_nothing_over_management_is_nothing_to_wait_for():
    for lab in (TableLab(), TableLab(v4={"10.1.0.0/16": LAB_ROUTE}),
                TableLab(v4={"172.31.99.0/24": CONNECTED4}, v6={"3fff:172:31:99::/64": CONNECTED6})):
        assert only(lab) is False


@pytest.mark.parametrize("v4,v6", [
    ({"0.0.0.0/0": KERNEL4}, {}),
    ({}, {"::/0": KERNEL6}),                                          # an IPv6 kernel default alone
    ({"0.0.0.0/0": KERNEL4}, {"::/0": KERNEL6}),
])
def test_kernel_defaults_via_the_gateway_are_waited_out(v4, v6):
    assert only(TableLab(v4=v4, v6=v6)) is True


def test_a_kernel_default_in_another_vrf_counts_too():
    lab = TableLab(v4=_table(("default", {}), ("MGMT", {"0.0.0.0/0": KERNEL4})))
    assert only(lab) is True


def test_lab_routes_beside_a_kernel_default_are_ignored():
    lab = TableLab(v4={"10.1.0.0/16": LAB_ROUTE, "0.0.0.0/0": KERNEL4,
                       "10.2.0.0/16": _r("static", _via("10.0.0.2", "Ethernet1"), "junk")})
    assert only(lab) is True


def test_the_connected_management_subnet_beside_a_kernel_default_is_ignored():
    lab = TableLab(v4={"172.31.99.0/24": CONNECTED4, "0.0.0.0/0": KERNEL4},
                   v6={"3fff:172:31:99::/64": CONNECTED6, "::/0": KERNEL6})
    assert only(lab) is True


def test_a_skipped_route_does_not_end_the_scan_of_its_table():
    # the kernel default is listed after the skipped ones: it is still seen
    lab = TableLab(v4={"172.31.99.0/24": CONNECTED4, "10.1.0.0/16": LAB_ROUTE, "0.0.0.0/0": KERNEL4})
    assert only(lab) is True
    # and a route out listed after a skipped one is still found, though the other table has a kernel default
    lab = TableLab(v4={"10.1.0.0/16": LAB_ROUTE, "172.31.99.0/24": CONNECTED4,
                       "10.77.0.0/16": _r("static", _via(GW4))}, v6={"::/0": KERNEL6})
    assert only(lab) is False


@pytest.mark.parametrize("prefix,route", [
    ("172.31.0.0/16", _r("connected", {"interface": "Management0"})),          # connected, not the mgmt subnet
    ("172.31.99.0/24", _r("static", _via(GW4))),                               # the mgmt subnet, not connected
    ("172.31.99.0/24", _r("kernel", _via(GW4))),
    ("10.77.0.0/16", _r("static", _via(GW4))),                                 # a route out
    ("10.77.0.0/16", _r("kernel", _via(GW4))),                                 # a kernel route, not a default
    ("0.0.0.0/0", _r("static", _via(GW4))),                                    # a default, not kernel
    ("0.0.0.0/0", _r("kernel", _via("172.31.99.77"))),                         # via a non-gateway
    ("0.0.0.0/0", _r("kernel", {"interface": "Management0"})),                 # no next hop at all
    ("0.0.0.0/0", _r("kernel", _via(GW4), _via("10.0.0.1", "Ethernet1"))),     # mixed via list
    ("0.0.0.0/0", _r("kernel", _via(GW4), _via("172.31.99.77"))),              # one gateway, one not
    ("0.0.0.0/0", _r("kernel", _via(GW4, "Management1/1"), "junk")),           # a via that isn't one
])
def test_anything_else_over_management_ends_the_wait(prefix, route):
    # beside a kernel default in each family, which alone would be waited out
    lab = TableLab(v4={"0.0.0.0/0": KERNEL4, **{prefix: route}} if prefix != "0.0.0.0/0" else {prefix: route},
                   v6={"::/0": KERNEL6})
    assert only(lab) is False


def test_another_route_in_the_ipv6_table_ends_the_wait():
    lab = TableLab(v4={"0.0.0.0/0": KERNEL4}, v6={"::/0": KERNEL6, "2001:db8::/32": _r("static", _via(GW6))})
    assert only(lab) is False


# ------------------------------------------------------------------- unreadable output

def test_an_unreadable_ipv4_table_is_a_run_error_naming_it():
    with pytest.raises(LabError) as e:
        only(TableLab(v4="% Invalid input", v6={"::/0": KERNEL6}))
    assert str(e.value) == ("r1: `show ip route vrf all | json` printed '% Invalid input', so its routes over "
                            "Management0 can't be read")


def test_an_unreadable_ipv6_table_is_a_run_error_naming_it():
    with pytest.raises(LabError) as e:
        only(TableLab(v4={"0.0.0.0/0": KERNEL4}, v6="% Invalid input"))
    assert str(e.value) == ("r1: `show ipv6 route vrf all | json` printed '% Invalid input', so its routes over "
                            "Management0 can't be read")


# ------------------------------------------------------------------- prepare_eos's wait

@pytest.mark.parametrize("limit,sleeps", [(0.0, 0), (1.0, 1), (2.0, 1), (3.0, 2), (4.0, 2), (5.0, 3)])
def test_prepare_eos_waits_in_2s_steps_from_zero_up_to_the_limit(monkeypatch, limit, sleeps):
    monkeypatch.setattr(mgmt, "EOS_KERNEL_WAIT", limit)
    slept: list = []
    with pytest.raises(ManagementPathError, match=r"0\.0\.0\.0/0 \(vrf default, kernel\) via 172\.31\.99\.1"):
        mgmt.prepare_eos(KernelLab(extra4={"0.0.0.0/0": KERNEL4}), m_of(), None, slept.append)
    assert slept == [2.0] * sleeps
