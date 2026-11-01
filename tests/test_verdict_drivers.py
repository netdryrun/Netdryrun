"""Driver plumbing and parsing, pinned down so that mutation testing finds no surviving mutant.

Every driver method is driven against a recording fake node: the exact device commands (per VRF, per
address family), the timeouts, the evidence kept, and the parsed sessions, routes, prefix counts, BGP paths
and ping counts. A wrong command (the default VRF instead of the check's VRF, IPv4 instead of IPv6) reads
the wrong table, which is how a check passes on state it never looked at. No lab is needed.
"""
from __future__ import annotations

import json
from dataclasses import replace

import pytest

from netdryrun import drivers as drv
from netdryrun.drivers import base, eos, frr, srlinux
from netdryrun.drivers.base import BgpNeighbor, BgpPath, Driver, DriverError, NoSuchInstance, Route
from netdryrun.drivers.eos import EosDriver
from netdryrun.drivers.junos import JunosDriver
from netdryrun.drivers.frr import FrrDriver
from netdryrun.drivers.nxos import NxosDriver
from netdryrun.drivers.sonic import SonicDriver
from netdryrun.drivers.srlinux import SrlDriver
from netdryrun.lab import ExecResult, Node


class Lab:
    """A node that answers each command with the first rule whose needle is in the command line.
    An answer is stdout, or (rc, stdout) or (rc, stdout, stderr). Every call is recorded."""

    def __init__(self, rules, nodes=None):
        self.rules, self.calls = list(rules), []
        self.nodes = nodes or {}

    def exec(self, node, cmd, timeout=60, input=None):
        line = " ".join(cmd)
        self.calls.append((node, list(cmd), timeout))
        for needle, answer in self.rules:
            if needle in line:
                if isinstance(answer, tuple):
                    rc, out, err = (answer + ("",))[:3] if len(answer) == 2 else answer
                else:
                    rc, out, err = 0, answer, ""
                return ExecResult(list(cmd), rc, out, err)
        raise AssertionError(f"unexpected command: {line}")

    def lines(self):
        return [" ".join(c[1]) for c in self.calls]


def J(d) -> str:
    return json.dumps(d)


# ----------------------------------------------------------------------------------------------- base

def test_exec_keeps_evidence_and_raises_on_failure():
    lab = Lab([("ok", (0, "x" * 25000, "e" * 3000)), ("bad", (3, "out\nlast out line", "err1\nerr2\n"))])
    d = Driver(lab, "r1")
    assert d.lab is lab and d.node == "r1"
    ev = []
    assert d._exec(["show", "ok"], ev) == "x" * 25000
    assert ev == [{"node": "r1", "cmd": "show ok", "rc": 0, "output": "x" * 20000, "stderr": "e" * 2000}]
    with pytest.raises(DriverError):
        d._exec(["show", "bad"], ev, timeout=7)
    assert ev[1]["rc"] == 3 and ev[1]["cmd"] == "show bad" and ev[1]["output"] == "out\nlast out line"
    assert lab.calls[0] == ("r1", ["show", "ok"], 60) and lab.calls[1][2] == 7


@pytest.mark.parametrize("answer", [(1, "", ""), (1, "", "e"), (2, "o", ""), (255, "", "")])
def test_exec_any_nonzero_rc_raises(answer):
    with pytest.raises(DriverError):
        Driver(Lab([("x", answer)]), "r1")._exec(["x"], [])


def test_base_driver_methods_are_abstract():
    d = Driver(Lab([]), "r1")
    for call in (lambda: d.bgp_neighbors(), lambda: d.routes("10.0.0.0/8"), lambda: d.ping("1.1.1.1", None, 1),
                 lambda: d.bgp_paths("10.0.0.0/8"), lambda: d.all_routes()):
        with pytest.raises(NotImplementedError):
            call()
    assert Driver.unsupported_bgp_attributes == frozenset()


@pytest.mark.parametrize("vrf", ["default", "red", "a.b:c-d_1", "A" * 64])
def test_check_vrf_name_accepts(vrf):
    assert base.check_vrf_name(vrf) == vrf


@pytest.mark.parametrize("vrf", ["all", "ALL", "", "a b", "a;b", "-x", "A" * 65, None, 1, "a\nb"])
def test_check_vrf_name_refuses(vrf):
    with pytest.raises(DriverError):
        base.check_vrf_name(vrf)


@pytest.mark.parametrize("value,expected", [(3, 3), ("7", 7), (0, 0), ("-1", -1)])
def test_as_int(value, expected):
    assert base.as_int("c", value) == expected


@pytest.mark.parametrize("value", [True, False, None, "x", "1.5", [], {}])
def test_as_int_refuses(value):
    with pytest.raises(DriverError):
        base.as_int("c", value)


def test_load_json():
    assert base.load_json("c", '{"a": 1}') == {"a": 1}
    assert base.load_json("c", "[]") == []
    for bad in ("", "  \n", None, "{", "[" * 100000):
        with pytest.raises(DriverError):
            base.load_json("c", bad)


def test_network():
    import ipaddress
    assert base.network("c", "10.1.2.3/16") == ipaddress.ip_network("10.1.0.0/16")
    assert base.network("c", "2001:db8::1/32") == ipaddress.ip_network("2001:db8::/32")
    for bad in ("vrf1", "", None, "10.0.0.0/33"):
        with pytest.raises(DriverError):
            base.network("c", bad)


def test_unexpected_is_a_driver_error():
    e = base.unexpected("cmd", "  a\n  b  ")
    assert isinstance(e, DriverError)


def test_parser_wraps_structural_errors_only():
    @base.parser("cmd")
    def f(kind):
        if kind == "driver":
            raise DriverError("as is")
        raise {"type": TypeError, "value": ValueError, "attr": AttributeError, "key": KeyError,
               "index": IndexError, "rec": RecursionError, "zero": ZeroDivisionError}[kind]("x")

    for kind in ("type", "value", "attr", "key", "index", "rec", "driver"):
        with pytest.raises(DriverError):
            f(kind)
    with pytest.raises(ZeroDivisionError):
        f("zero")
    assert f.__name__ == "f"


def test_canon_communities():
    assert base.canon_communities(["65000:010", "NO_EXPORT", " Weird "]) == ["65000:10", "65535:65281", "weird"]
    assert base.canon_communities(None) == [] and base.canon_communities([]) == []


@pytest.mark.parametrize("segments,expected", [
    ([("as-sequence", [65001, "65002"])], "65001 65002"),
    ([("AS_SEQUENCE", [1])], "1"),
    ([("as-set", [3, 2])], "{3,2}"),
    ([("set", [3, 2])], "{3,2}"),
    ([("AS_SET", [5])], "{5}"),
    ([("as-confed-sequence", [1, 2])], "(1 2)"),
    ([("AS_CONFED_SEQUENCE", [1])], "(1)"),
    ([("as-confed-set", [1, 2])], "[1,2]"),
    ([("confed_set", [4])], "[4]"),
    ([("as-sequence", [1]), ("as-set", [2, 3]), ("as-sequence", [4])], "1 {2,3} 4"),
    ([("whatever", [9, 8])], "9 8"),
    ([], ""),
])
def test_render_as_path(segments, expected):
    assert base.render_as_path(segments) == expected


def test_bgp_path_all_communities():
    p = BgpPath(True, "1", None, None, None, communities=["1:1"], large_communities=["1:1:1"])
    assert p.all_communities() == ["1:1", "1:1:1"]
    assert BgpPath(True, "1", None, None, None).local_candidate is False


# ----------------------------------------------------------------------------------------------- detect / for_node

def N(name, kind="linux", image="x"):
    return Node(name, f"clab-t-{name}", kind, image)


@pytest.mark.parametrize("kind,image,expected", [
    ("nokia_srlinux", "ghcr.io/nokia/srlinux", "srlinux"), ("srl", "x", "srlinux"),
    ("arista_ceos", "ceos", "eos"), ("ceos", "x", "eos"),
    ("sonic-vs", "x", "sonic"), ("sonic_vs", "x", "sonic"), ("linux", "docker-SONiC-vs:latest", "sonic"),
    ("linux", "quay.io/frrouting/FRR:10.4", "frr"),
    ("cisco_n9kv", "vrnetlab/cisco_n9kv:9300-10.4.8.M", "nxos"), ("vr-n9kv", "x", "nxos"), ("vr-cisco_n9kv", "x", "nxos"),
    ("cisco_n9kv", "frr-lookalike", "nxos"),   # the kind decides before any image-name guess
    ("juniper_cjunosevolved", "cjunosevolved:26.2R1.7-EVO", "junos"), ("cjunosevolved", "x", "junos"),
])
def test_detect(kind, image, expected):
    assert drv.detect(N("r1", kind, image)) == expected


def test_detect_unknown_raises():
    with pytest.raises(DriverError):
        drv.detect(N("r1", "linux", "alpine"))


def test_for_node():
    lab = Lab([], nodes={"r1": N("r1", "srl", "x"), "r2": N("r2", "linux", "frr"), "r3": N("r3", "linux", "alpine")})
    d = drv.for_node(lab, "r1")
    assert type(d) is SrlDriver and d.lab is lab and d.node == "r1"
    assert type(drv.for_node(lab, "r2")) is FrrDriver
    assert type(drv.for_node(lab, "r2", "eos")) is EosDriver
    assert type(drv.for_node(lab, "r3", "sonic")) is SonicDriver
    with pytest.raises(DriverError):
        drv.for_node(lab, "r9")
    assert type(drv.for_node(lab, "r2", "junos")) is JunosDriver
    with pytest.raises(DriverError):
        drv.for_node(lab, "r2", "iosxr")
    with pytest.raises(DriverError):
        drv.for_node(lab, "r3")
    assert type(drv.for_node(lab, "r3", "nxos")) is NxosDriver
    assert drv.DRIVERS == {"frr": FrrDriver, "srlinux": SrlDriver, "eos": EosDriver, "sonic": SonicDriver,
                           "junos": JunosDriver, "nxos": NxosDriver}


def test_check_supported(monkeypatch):
    from netdryrun.config import Check
    lab = Lab([], nodes={"r1": N("r1", "linux", "frr"), "r3": N("r3", "linux", "alpine")})
    c = Check("bgp_route", {"node": "r1", "prefix": "10.0.0.0/8", "med": 5}, "c", 30)
    drv.check_supported(lab, c)                      # FRR reads every attribute
    monkeypatch.setattr(EosDriver, "unsupported_bgp_attributes", frozenset({"med"}))
    with pytest.raises(DriverError):
        drv.check_supported(lab, c, "eos")
    drv.check_supported(lab, Check("bgp_route", {"node": "r1", "prefix": "10.0.0.0/8"}, "c", 30), "eos")
    drv.check_supported(lab, Check("route", {"node": "r1", "prefix": "10.0.0.0/8", "med": 5}, "c", 30), "eos")
    drv.check_supported(lab, Check("bgp_route", {"node": "r9", "prefix": "1.0.0.0/8", "med": 1}, "c", 30), "eos")
    monkeypatch.setattr(FrrDriver, "unsupported_bgp_attributes", frozenset({"med"}))
    with pytest.raises(DriverError):
        drv.check_supported(lab, c)                  # detected as frr


def test_check_supported_refuses_evpn_counts_on_sr_linux():
    """The SR Linux driver has no EVPN prefix count (the family has no received-routes counter, so it is
    skipped): the count would read 0 and pass max or exact: 0. Refused before deploying, as on EOS."""
    from netdryrun.config import Check
    lab = Lab([], nodes={"r1": N("r1", "srl", "x"), "r2": N("r2", "linux", "frr")})
    evpn = Check("bgp_prefixes", {"node": "r1", "neighbor": "10.0.0.2", "max": 0, "afi": "evpn"}, "c", 30)
    with pytest.raises(DriverError):
        drv.check_supported(lab, evpn)
    with pytest.raises(DriverError):
        drv.check_supported(lab, replace(evpn, params={**evpn.params, "node": "r2"}), "srlinux")
    drv.check_supported(lab, replace(evpn, params={**evpn.params, "afi": "ipv6-unicast"}))
    drv.check_supported(lab, replace(evpn, params={**evpn.params, "node": "r2"}))   # FRR reads EVPN counts


def test_check_supported_prefix_counts(monkeypatch):
    """bgp_prefixes without an afi reads ipv4-unicast (as the check does), so a driver without IPv4 unicast
    counts refuses it; a driver name check_supported doesn't know is left to for_node to refuse."""
    from netdryrun.config import Check
    lab = Lab([], nodes={"r1": N("r1", "linux", "frr")})
    no_afi = Check("bgp_prefixes", {"node": "r1", "neighbor": "10.0.0.2", "max": 0}, "c", 30)
    v6 = Check("bgp_prefixes", {"node": "r1", "neighbor": "10.0.0.2", "max": 0, "afi": "ipv6-unicast"}, "c", 30)
    drv.check_supported(lab, no_afi)
    monkeypatch.setattr(FrrDriver, "unsupported_afis", frozenset({"ipv4-unicast"}))
    with pytest.raises(DriverError):
        drv.check_supported(lab, no_afi)
    drv.check_supported(lab, v6)
    # an unknown driver name: no attributes to refuse, no crash (for_node reports the unknown driver)
    drv.check_supported(lab, no_afi, "nosuch")
    drv.check_supported(lab, Check("bgp_route", {"node": "r1", "prefix": "10.0.0.0/8", "med": 5}, "c", 30), "nosuch")


# ----------------------------------------------------------------------------------------------- FRR

FRR_NBR = J({"10.0.0.2": {"bgpState": "Established",
                          "addressFamilyInfo": {"ipv4Unicast": {"acceptedPrefixCounter": 3},
                                                "ipv6Unicast": {"acceptedPrefixCounter": "4"},
                                                "l2VpnEvpn": {"acceptedPrefixCounter": 5},
                                                "ipv4Multicast": {"acceptedPrefixCounter": 6}}},
             "2001:db8:0::1": {"bgpState": "Idle (Admin)"},
             "eth1": {"bgpState": "Active", "addressFamilyInfo": {}}})
SHOW_VRF = "vrf red id 5 table 1001\nvrf blue inactive\n"


@pytest.mark.parametrize("cls", [FrrDriver, SonicDriver])
def test_frr_bgp_neighbors(cls):
    lab = Lab([("neighbors json", FRR_NBR)])
    obs = cls(lab, "r1").bgp_neighbors()
    assert lab.lines() == ["vtysh -c show bgp neighbors json"]
    n = obs.value
    assert set(n) == {"10.0.0.2", "2001:db8::1", "eth1"}
    assert n["10.0.0.2"] == BgpNeighbor("10.0.0.2", "established",
                                        {"ipv4-unicast": 3, "ipv6-unicast": 4, "evpn": 5, "ipv4Multicast": 6})
    assert n["2001:db8::1"].state == "idle" and n["2001:db8::1"].prefixes == {}
    assert n["eth1"].state == "active"
    assert obs.evidence[0]["cmd"] == "vtysh -c show bgp neighbors json" and obs.evidence[0]["node"] == "r1"


def test_frr_bgp_neighbors_in_a_vrf():
    lab = Lab([("neighbors json", FRR_NBR)])
    FrrDriver(lab, "r1").bgp_neighbors("red")
    assert lab.lines() == ["vtysh -c show bgp vrf red neighbors json"]   # neighbors found: VRF not re-checked
    lab = Lab([("neighbors json", "{}"), ("show vrf", SHOW_VRF)])
    obs = FrrDriver(lab, "r1").bgp_neighbors("red")
    assert obs.value == {} and lab.lines() == ["vtysh -c show bgp vrf red neighbors json", "vtysh -c show vrf"]
    assert len(obs.evidence) == 2
    lab = Lab([("neighbors json", "{}")])
    assert FrrDriver(lab, "r1").bgp_neighbors().value == {} and len(lab.calls) == 1   # default VRF always exists
    for vrf in ("green", "blue"):
        with pytest.raises(NoSuchInstance):     # the device says there is no such (active) VRF: "none here"
            FrrDriver(Lab([("neighbors json", "{}"), ("show vrf", SHOW_VRF)]), "r1").bgp_neighbors(vrf)
    with pytest.raises(DriverError):
        FrrDriver(Lab([]), "r1").bgp_neighbors("all")


def test_frr_no_such_instance_is_told_apart_from_unreadable_output():
    for text in (J({"warning": "View/Vrf is unknown"}), J({"bgpNoSuchInstance": True}),
                 J({"warning": "BGP instance not found"})):
        with pytest.raises(NoSuchInstance):
            frr._bgp_json("c", text)
    for text in (J({"warning": "something else"}), J({"warning": 3}), J([]), ""):
        with pytest.raises(DriverError) as exc:
            frr._bgp_json("c", text)
        assert not isinstance(exc.value, NoSuchInstance)


@pytest.mark.parametrize("text", [
    J([]), J({"warning": "View/Vrf is unknown"}), J({"bgpNoSuchInstance": True}),
    J({"10.0.0.2": "x"}), J({"10.0.0.2": {"bgpState": ""}}), J({"10.0.0.2": {"bgpState": 3}}),
    J({"10.0.0.2": {}}),
    J({"10.0.0.2": {"bgpState": "Established"}}),                                   # no families at all
    J({"10.0.0.2": {"bgpState": "Established", "addressFamilyInfo": []}}),
    J({"10.0.0.2": {"bgpState": "Idle", "addressFamilyInfo": None}}),
    J({"10.0.0.2": {"bgpState": "Established", "addressFamilyInfo": {"ipv4Unicast": {}}}}),
    J({"10.0.0.2": {"bgpState": "Established", "addressFamilyInfo": {"ipv4Unicast": 3}}}),
    J({"10.0.0.2": {"bgpState": "Established", "addressFamilyInfo": {"ipv4Unicast": {"acceptedPrefixCounter": "x"}}}}),
])
def test_frr_bgp_neighbors_unexpected_output(text):
    with pytest.raises(DriverError):
        frr.parse_bgp_neighbors(text)


def test_frr_bgp_json_accepts_a_false_no_such_instance():
    assert frr._bgp_json("c", J({"a": 1})) == {"a": 1}
    assert frr._bgp_json("c", J({"bgpNoSuchInstance": False})) == {"bgpNoSuchInstance": False}


def test_frr_canon_addr():
    assert frr._canon_addr("2001:db8:0::1") == "2001:db8::1"
    assert frr._canon_addr("fe80::1%eth1") == "fe80::1"
    assert frr._canon_addr("eth1") == "eth1"


def route_json(prefix, *entries):
    return J({prefix: list(entries)})


FRR_PATHS = J({"prefix": "10.1.0.0/16", "paths": [
    {"bestpath": {"overall": True}, "aspath": {"segments": [{"type": "as-sequence", "list": [65002, 65003]}]},
     "nexthops": [{"ip": "fe80::1", "scope": "link-local"}, {"ip": "10.0.0.2", "scope": "global"}],
     "locPrf": 200, "metric": 7, "community": {"string": "65000:1 no-export"},
     "largeCommunity": {"string": "65000:1:2"}, "peer": {"peerId": "10.0.0.2"}},
    {"aspath": {"segments": []}, "nexthops": [{"ip": "10.0.0.3"}], "peer": {"peerId": "10.0.0.3"}},
]})


def test_frr_routes_commands():
    lab = Lab([("route", route_json("10.1.0.0/16", {"protocol": "BGP", "selected": True, "installed": True})),
               ("show bgp", "{}")])
    obs = FrrDriver(lab, "r1").routes("10.1.0.0/16")
    assert lab.lines() == ["vtysh -c show ip route 10.1.0.0/16 json", "vtysh -c show bgp ipv4 unicast 10.1.0.0/16 json"]
    assert obs.value == [Route("10.1.0.0/16", "bgp", True)] and len(obs.evidence) == 2
    lab = Lab([("route", "{}"), ("show bgp", "{}"), ("show vrf", SHOW_VRF)])
    obs = FrrDriver(lab, "r1").routes("2001:db8::/32", "red")
    assert lab.lines() == ["vtysh -c show ipv6 route vrf red 2001:db8::/32 json",
                           "vtysh -c show bgp vrf red ipv6 unicast 2001:db8::/32 json", "vtysh -c show vrf"]
    assert obs.value == []
    lab = Lab([("route", "{}"), ("show bgp", "{}")])
    assert FrrDriver(lab, "r1").routes("10.1.0.0/16").value == [] and len(lab.calls) == 2
    with pytest.raises(DriverError):
        FrrDriver(Lab([("route", "{}"), ("show bgp", "{}"), ("show vrf", SHOW_VRF)]), "r1").routes("10.1.0.0/16", "nope")
    lab = Lab([("route", route_json("10.1.0.0/16", {"protocol": "static", "selected": True})), ("show bgp", "{}")])
    FrrDriver(lab, "r1").routes("10.1.0.0/16", "red")
    assert len(lab.calls) == 2                                  # a route was found: no VRF check


@pytest.mark.parametrize("entry,active", [
    ({"protocol": "bgp", "selected": True, "installed": True}, True),
    ({"protocol": "bgp", "selected": True}, True),               # installed defaults to true
    ({"protocol": "bgp", "selected": True, "installed": False}, False),
    ({"protocol": "bgp", "installed": True}, False),
    ({"protocol": "bgp", "selected": False, "installed": True}, False),
])
def test_frr_route_active(entry, active):
    assert frr.parse_routes(route_json("10.1.0.0/16", entry), "10.1.0.0/16") == [Route("10.1.0.0/16", "bgp", active)]


def test_frr_routes_ignore_a_covering_prefix_and_keep_every_entry():
    text = J({"10.0.0.0/8": [{"protocol": "static", "selected": True}],
              "10.1.0.0/16": [{"protocol": "Connected", "selected": True}, {"protocol": "bgp"}]})
    assert frr.parse_routes(text, "10.1.0.0/16") == [Route("10.1.0.0/16", "connected", True),
                                                     Route("10.1.0.0/16", "bgp", False)]
    assert frr.parse_routes(text, "10.2.0.0/16") == []
    assert frr.parse_routes(J({"10.1.0.0/16": [{"protocol": "bgp", "selected": True}]}), "10.1.0.0/24") == []


@pytest.mark.parametrize("text", [J([]), J({"vrf1": []}), J({"10.0.0.0/8": []}), J({"10.0.0.0/8": {}}),
                                  J({"10.0.0.0/8": ["x"]}), J({"10.0.0.0/8": [{"protocol": 1}]}),
                                  J({"10.0.0.0/8": [{}]})])
def test_frr_route_table_unexpected(text):
    with pytest.raises(DriverError):
        frr.parse_routes(text, "10.0.0.0/8")
    with pytest.raises(DriverError):
        frr.parse_all_routes(text)


def _path(**kw):
    base_ = {"peer": {"peerId": "10.0.0.2"}}
    base_.update(kw)
    return base_


def bgp_text(prefix, *paths):
    return J({"prefix": prefix, "paths": list(paths)})


@pytest.mark.parametrize("path,learned", [
    (_path(), True),
    (_path(peer={"peerId": "0.0.0.0"}), False),
    (_path(peer={"peerId": "::"}), False),
    (_path(peer={"peerId": ""}), False),
    (_path(local=True), False),
    (_path(sourced=True), False),
    (_path(local=False, sourced=False), True),
])
def test_frr_received_path_not_in_zebra(path, learned):
    """A path learned from a neighbor that zebra doesn't hold is present (not selected); the router's own isn't."""
    out = frr.parse_routes("{}", "10.1.0.0/16", bgp_text("10.1.0.0/16", path))
    assert out == ([Route("10.1.0.0/16", "bgp", False)] if learned else [])


def test_frr_received_path_rules():
    learned = bgp_text("10.1.0.0/16", _path())
    # zebra already has a BGP route (even not selected): nothing added
    zebra_bgp = route_json("10.1.0.0/16", {"protocol": "bgp"})
    assert frr.parse_routes(zebra_bgp, "10.1.0.0/16", learned) == [Route("10.1.0.0/16", "bgp", False)]
    # zebra has only a static: the learned BGP path is added
    zebra_static = route_json("10.1.0.0/16", {"protocol": "static", "selected": True})
    assert frr.parse_routes(zebra_static, "10.1.0.0/16", learned) == [Route("10.1.0.0/16", "static", True),
                                                                      Route("10.1.0.0/16", "bgp", False)]
    # one learned path among the router's own is enough
    mixed = bgp_text("10.1.0.0/16", _path(local=True), _path())
    assert frr.parse_routes("{}", "10.1.0.0/16", mixed) == [Route("10.1.0.0/16", "bgp", False)]
    # no BGP instance (or an unknown-instance warning): no BGP paths
    for t in (J({"bgpNoSuchInstance": True}), J({"warning": "BGP instance not found"}), J({"warning": "Unknown VRF"}), "{}"):
        assert frr.parse_routes("{}", "10.1.0.0/16", t) == []
    # any other warning is an error
    with pytest.raises(DriverError):
        frr.parse_routes("{}", "10.1.0.0/16", J({"warning": "something else"}))
    with pytest.raises(DriverError):
        frr.parse_routes("{}", "10.1.0.0/16", J({"warning": 3}))
    # a path without its peer is unexpected
    for bad in ({}, {"peer": {}}, {"peer": "x"}, {"peer": {"peerId": 3}}):
        with pytest.raises(DriverError):
            frr.parse_routes("{}", "10.1.0.0/16", bgp_text("10.1.0.0/16", bad))
    # the BGP side answering for a covering prefix: nothing for this one
    assert frr.parse_routes("{}", "10.1.0.0/16", bgp_text("10.0.0.0/8", _path())) == []
    assert frr.parse_routes("{}", "10.1.0.0/16", None) == []


@pytest.mark.parametrize("text", [J({"paths": []}), J({"prefix": "10.1.0.0/16"}), J({"prefix": "10.1.0.0/16", "paths": {}}),
                                  J({"prefix": "x", "paths": []}), J({"prefix": "10.1.0.0/16", "paths": ["x"]}), J([]),
                                  J({"warning": "x"})])
def test_frr_bgp_paths_unexpected(text):
    with pytest.raises(DriverError):
        frr.parse_bgp_paths(text, "10.1.0.0/16")


def test_frr_parse_bgp_paths():
    paths = frr.parse_bgp_paths(FRR_PATHS, "10.1.0.0/16")
    assert paths[0] == BgpPath(True, "65002 65003", "10.0.0.2", 200, 7, ["65000:1", "65535:65281"], ["65000:1:2"],
                               "10.0.0.2")
    assert paths[1] == BgpPath(False, "", "10.0.0.3", 100, None, [], [], "10.0.0.3")
    assert frr.parse_bgp_paths(FRR_PATHS, "10.1.0.0/16", default_local_pref=None)[1].local_pref is None
    assert frr.parse_bgp_paths(FRR_PATHS, "10.1.0.0/16", default_local_pref=150)[1].local_pref == 150
    assert frr.parse_bgp_paths(FRR_PATHS, "10.1.0.0/24") == [] and frr.parse_bgp_paths("{}", "10.1.0.0/16") == []
    one = bgp_text("10.1.0.0/16", {"bestpath": {"overall": False}, "aspath": None, "nexthops": None, "peer": None})
    assert frr.parse_bgp_paths(one, "10.1.0.0/16") == [BgpPath(False, "", None, 100, None, [], [], None)]


@pytest.mark.parametrize("hops,expected", [
    ([{"ip": "fe80::1", "scope": "link-local"}, {"ip": "2001:db8:0::2", "scope": "global"}], "2001:db8::2"),
    ([{"ip": "fe80::1", "scope": "link-local"}], "fe80::1"),
    ([{"ip": "10.0.0.2"}], "10.0.0.2"),
    ([{"scope": "global"}, {"ip": "10.0.0.3"}], "10.0.0.3"),
    (["x", {"ip": ""}, {"ip": "10.0.0.4"}], "10.0.0.4"),
    ([{"ip": "10.0.0.5", "scope": "link-local"}, {"ip": "10.0.0.6", "scope": "link-local"}], "10.0.0.5"),
    ([], None),
])
def test_frr_next_hop(hops, expected):
    assert frr._next_hop(hops) == expected


def test_frr_bgp_paths_commands_and_default_local_pref():
    lab = Lab([("longer-prefixes", J({"routes": {}, "defaultLocPrf": 150})), ("show bgp", FRR_PATHS)])
    obs = FrrDriver(lab, "r1").bgp_paths("10.1.0.0/16")
    assert lab.lines() == ["vtysh -c show bgp ipv4 unicast 10.1.0.0/16 json",
                           "vtysh -c show bgp ipv4 unicast 255.255.255.255/32 longer-prefixes json"]
    assert [p.local_pref for p in obs.value] == [200, 150] and len(obs.evidence) == 2
    v6 = J({"prefix": "2001:db8::/32", "paths": [_path(locPrf=100, bestpath={"overall": True})]})
    lab = Lab([("show bgp", v6)])
    obs = FrrDriver(lab, "r1").bgp_paths("2001:db8::/32", "red")
    assert lab.lines() == ["vtysh -c show bgp vrf red ipv6 unicast 2001:db8::/32 json"]   # every path has locPrf
    assert obs.value[0].local_pref == 100 and obs.value[0].best
    lab = Lab([("longer-prefixes", J({"routes": {}, "defaultLocPrf": 150})), ("show bgp", FRR_PATHS)])
    FrrDriver(lab, "r1").bgp_paths("10.1.0.0/16", "red")
    assert lab.lines()[1] == "vtysh -c show bgp vrf red ipv4 unicast 255.255.255.255/32 longer-prefixes json"
    lab = Lab([("show bgp", "{}"), ("show vrf", SHOW_VRF)])
    assert FrrDriver(lab, "r1").bgp_paths("10.1.0.0/16", "red").value == []
    assert lab.lines()[-1] == "vtysh -c show vrf"
    lab = Lab([("show bgp", "{}")])
    assert FrrDriver(lab, "r1").bgp_paths("10.1.0.0/16").value == [] and len(lab.calls) == 1
    with pytest.raises(DriverError):
        FrrDriver(Lab([("show bgp", "{}"), ("show vrf", SHOW_VRF)]), "r1").bgp_paths("10.1.0.0/16", "nope")


def test_frr_default_local_pref():
    assert frr.parse_default_local_pref(J({"routes": {}, "defaultLocPrf": 150})) == 150
    assert frr.parse_default_local_pref(J({"routes": {}})) is None
    for bad in (J({"defaultLocPrf": 150}), J({"routes": {}, "defaultLocPrf": "x"}), J({"warning": "x"})):
        with pytest.raises(DriverError):
            frr.parse_default_local_pref(bad)


def test_frr_parse_vrfs():
    assert frr.parse_vrfs(SHOW_VRF + "netns-based vrfs\n  vrf green id 7 table 7\n") == \
        {"red": True, "blue": False, "green": True}
    assert frr.parse_vrfs("") == {}


def test_frr_all_routes():
    text = J({"10.1.0.0/16": [{"protocol": "BGP", "selected": True}], "10.2.0.0/16": [{"protocol": "static"}]})
    lab = Lab([("route", text)])
    obs = FrrDriver(lab, "r1").all_routes()
    assert lab.lines() == ["vtysh -c show ip route json"]
    assert obs.value == [Route("10.1.0.0/16", "bgp", True), Route("10.2.0.0/16", "static", False)]
    lab = Lab([("route", text)])
    FrrDriver(lab, "r1").all_routes("red", 6)
    assert lab.lines() == ["vtysh -c show ipv6 route vrf red json"]
    lab = Lab([("route", "{}"), ("show vrf", SHOW_VRF)])
    assert FrrDriver(lab, "r1").all_routes("red").value == [] and lab.lines()[-1] == "vtysh -c show vrf"
    lab = Lab([("route", "{}")])
    assert FrrDriver(lab, "r1").all_routes().value == [] and len(lab.calls) == 1
    with pytest.raises(DriverError):
        FrrDriver(Lab([("route", "{}"), ("show vrf", SHOW_VRF)]), "r1").all_routes("nope")


PING_OK = "PING 10.9.9.9\n3 packets transmitted, 2 received, 33% packet loss\n"


def test_frr_ping():
    lab = Lab([("ping", (0, PING_OK + "x" * 6000, "e" * 1500))])
    obs = FrrDriver(lab, "r1").ping("10.9.9.9", None, 3)
    assert lab.calls == [("r1", ["ping", "-c", "3", "-W", "1", "10.9.9.9"], 16)]
    assert obs.value == (3, 2)
    ev = obs.evidence[0]
    assert ev["node"] == "r1" and ev["cmd"] == "ping -c 3 -W 1 10.9.9.9" and ev["rc"] == 0
    assert len(ev["output"]) == 5000 and ev["stderr"] == "e" * 1000
    lab = Lab([("ping", (1, PING_OK))])
    obs = FrrDriver(lab, "r1").ping("10.9.9.9", "10.0.0.1", 5, "red")
    assert lab.calls == [("r1", ["ip", "vrf", "exec", "red", "ping", "-c", "5", "-W", "1", "-I", "10.0.0.1", "10.9.9.9"],
                          20)]
    assert obs.value == (3, 2) and obs.evidence[0]["rc"] == 1 and obs.evidence[0]["output"] == PING_OK
    with pytest.raises(DriverError):
        FrrDriver(Lab([]), "r1").ping("10.9.9.9", None, 3, "all")


@pytest.mark.parametrize("text,expected", [
    ("3 packets transmitted, 3 received, 0% packet loss", (3, 3)),
    ("5 packets transmitted, 0 packets received, 100% packet loss", (5, 0)),
    ("10 packets transmitted, 10 received", (10, 10)),
    ("connect: Network is unreachable", (0, 0)),
    ("", (0, 0)),
])
def test_parse_ping(text, expected):
    assert frr.parse_ping(text) == expected


# ----------------------------------------------------------------------------------------------- SR Linux

SRL_NBR = J({"neighbor": [
    {"peer-address": "10.0.0.2", "session-state": "Established",
     "afi-safi": [{"afi-safi-name": "ipv4-unicast", "received-routes": 5, "rejected-routes": 1},
                  {"afi-safi-name": "ipv6-unicast", "received-routes": "4"},
                  {"afi-safi-name": "evpn"}]},
    {"peer-address": "2001:db8:0::1", "session-state": "idle"},
]})


def test_srl_bgp_neighbors():
    lab = Lab([("neighbor", SRL_NBR)])
    obs = SrlDriver(lab, "r1").bgp_neighbors()
    assert lab.lines() == ["sr_cli --output-format json info from state /network-instance default protocols bgp neighbor *"]
    # evpn has no received-routes counter: not in the counts, which is why check_supported refuses afi: evpn here
    assert obs.value["10.0.0.2"] == BgpNeighbor("10.0.0.2", "established", {"ipv4-unicast": 4, "ipv6-unicast": 4})
    assert "evpn" in SrlDriver.unsupported_afis
    assert obs.value["2001:db8::1"] == BgpNeighbor("2001:db8:0::1", "idle", {})
    lab = Lab([("neighbor", SRL_NBR)])
    SrlDriver(lab, "r1").bgp_neighbors("red")
    assert lab.lines() == ["sr_cli --output-format json info from state /network-instance red protocols bgp neighbor *"]
    lab = Lab([("neighbor", "{}"), ("oper-state", J({"oper-state": "up"}))])
    assert SrlDriver(lab, "r1").bgp_neighbors("red").value == {}
    assert lab.lines()[-1] == "sr_cli --output-format json info from state /network-instance red oper-state"
    lab = Lab([("neighbor", "{}")])
    assert SrlDriver(lab, "r1").bgp_neighbors().value == {} and len(lab.calls) == 1
    with pytest.raises(NoSuchInstance):
        SrlDriver(Lab([("neighbor", "{}"), ("oper-state", "{}")]), "r1").bgp_neighbors("nope")


@pytest.mark.parametrize("text", [
    J([]), J({"neighbor": {}}), J({"neighbor": ["x"]}), J({"neighbor": [{}]}), J({"other": []}),
    J({"neighbor": [{"peer-address": "", "session-state": "idle"}]}),
    J({"neighbor": [{"peer-address": "10.0.0.2", "session-state": ""}]}),
    J({"neighbor": [{"peer-address": 1, "session-state": "idle"}]}),
    J({"neighbor": [{"peer-address": "10.0.0.2", "session-state": 1}]}),
    J({"neighbor": [{"peer-address": "10.0.0.2", "session-state": "established"}]}),     # no afi-safi
    J({"neighbor": [{"peer-address": "10.0.0.2", "session-state": "idle", "afi-safi": {}}]}),
    J({"neighbor": [{"peer-address": "10.0.0.2", "session-state": "established",
                     "afi-safi": [{"afi-safi-name": "ipv4-unicast", "received-routes": "x"}]}]}),
])
def test_srl_neighbors_unexpected(text):
    with pytest.raises(DriverError):
        srlinux.parse_bgp_neighbors(text)


SRL_ROUTE = J({"route": [{"ipv4-prefix": "10.1.0.0/16", "route-type": "BGP", "active": True},
                         {"ipv4-prefix": "10.1.0.0/16", "route-type": "local", "active": False},
                         {"ipv4-prefix": "10.0.0.0/8", "route-type": "static", "active": True}]})
SRL_RIB = J({"route": [{"prefix": "10.1.0.0/16", "neighbor": "10.0.0.2", "origin-protocol": "bgp", "best-route": True,
                        "attr-id": 7}]})


def test_srl_routes():
    lab = Lab([("route-table", SRL_ROUTE), ("bgp-rib", SRL_RIB)])
    obs = SrlDriver(lab, "r1").routes("10.1.0.0/16")
    assert lab.lines() == [
        "sr_cli --output-format json info from state /network-instance default route-table ipv4-unicast route "
        "10.1.0.0/16 id * route-type * route-owner * origin-network-instance *",
        "sr_cli --output-format json info from state /network-instance default bgp-rib afi-safi ipv4-unicast "
        "ipv4-unicast local-rib route 10.1.0.0/16 neighbor * origin-protocol * path-id *"]
    assert obs.value == [Route("10.1.0.0/16", "bgp", True), Route("10.1.0.0/16", "connected", False)]
    lab = Lab([("route-table", "{}"), ("bgp-rib", "{}"), ("oper-state", J({"oper-state": "up"}))])
    assert SrlDriver(lab, "r1").routes("2001:db8::/32", "red").value == []
    assert lab.lines() == [
        "sr_cli --output-format json info from state /network-instance red route-table ipv6-unicast route "
        "2001:db8::/32 id * route-type * route-owner * origin-network-instance *",
        "sr_cli --output-format json info from state /network-instance red bgp-rib afi-safi ipv6-unicast "
        "ipv6-unicast local-rib route 2001:db8::/32 neighbor * origin-protocol * path-id *",
        "sr_cli --output-format json info from state /network-instance red oper-state"]
    lab = Lab([("route-table", "{}"), ("bgp-rib", "{}")])
    assert SrlDriver(lab, "r1").routes("10.1.0.0/16").value == [] and len(lab.calls) == 2
    with pytest.raises(DriverError):
        SrlDriver(Lab([("route-table", "{}"), ("bgp-rib", "{}"), ("oper-state", "{}")]), "r1").routes("10.1.0.0/16", "x")


def test_srl_parse_routes_rules():
    v6 = J({"route": [{"ipv6-prefix": "2001:db8:0::/32", "route-type": "ospfv3", "active": True}]})
    assert srlinux.parse_routes(v6, "2001:db8::/32") == [Route("2001:db8::/32", "ospf6", True)]
    assert srlinux.parse_routes(J({"route": [{"ipv4-prefix": "10.1.0.0/16"}]}), "10.1.0.0/16") == \
        [Route("10.1.0.0/16", "", False)]
    assert srlinux.parse_routes(J({"route": [{"ipv4-prefix": "10.1.0.0/16", "route-type": "host", "active": 1}]}),
                                "10.1.0.0/16") == [Route("10.1.0.0/16", "local", True)]
    with pytest.raises(DriverError):
        srlinux.parse_routes(J({"route": [{"ipv6-prefix": "10.1.0.0/16"}]}), "10.1.0.0/16")
    with pytest.raises(DriverError):
        srlinux.parse_routes(J({"route": [{"ipv4-prefix": "x"}]}), "10.1.0.0/16")


@pytest.mark.parametrize("table,rib,expected", [
    ("{}", SRL_RIB, [Route("10.1.0.0/16", "bgp", False)]),
    # an active BGP route in the table: the RIB adds nothing
    (J({"route": [{"ipv4-prefix": "10.1.0.0/16", "route-type": "bgp", "active": True}]}), SRL_RIB,
     [Route("10.1.0.0/16", "bgp", True)]),
    # an inactive BGP route in the table: the RIB path still counts
    (J({"route": [{"ipv4-prefix": "10.1.0.0/16", "route-type": "bgp", "active": False}]}), SRL_RIB,
     [Route("10.1.0.0/16", "bgp", False), Route("10.1.0.0/16", "bgp", False)]),
    # an active static wins the table: the received BGP path is still present
    (J({"route": [{"ipv4-prefix": "10.1.0.0/16", "route-type": "static", "active": True}]}), SRL_RIB,
     [Route("10.1.0.0/16", "static", True), Route("10.1.0.0/16", "bgp", False)]),
    # the router's own static in the RIB is not a BGP route
    ("{}", J({"route": [{"prefix": "10.1.0.0/16", "neighbor": "0.0.0.0", "origin-protocol": "Static"}]}), []),
    ("{}", J({"route": [{"prefix": "10.1.0.0/16", "neighbor": "0.0.0.0"}]}), [Route("10.1.0.0/16", "bgp", False)]),
    ("{}", J({"route": [{"prefix": "10.1.0.0/16", "origin-protocol": "BGP"}]}), [Route("10.1.0.0/16", "bgp", False)]),
    ("{}", J({"route": [{"prefix": "10.0.0.0/8", "origin-protocol": "bgp"}]}), []),
    ("{}", "{}", []),
])
def test_srl_bgp_rib_paths_count_as_present(table, rib, expected):
    assert srlinux.parse_routes(table, "10.1.0.0/16", rib) == expected


def test_srl_rib_rows():
    with pytest.raises(DriverError):
        srlinux.parse_rib_paths(J({"route": [{"neighbor": "x"}]}), "10.1.0.0/16")
    with pytest.raises(DriverError):
        srlinux.parse_rib_paths(J({"route": "x"}), "10.1.0.0/16")
    with pytest.raises(DriverError):
        srlinux.parse_rib_paths(J({"route": [1]}), "10.1.0.0/16")
    rows = J({"route": [{"prefix": "10.1.0.0/16", "neighbor": "a"}, {"prefix": "10.1.0.0/16", "neighbor": "b",
                                                                     "best-route": True},
                        {"prefix": "10.0.0.0/8", "neighbor": "c", "best-route": True}]})
    assert [r["neighbor"] for r in srlinux.parse_rib_paths(rows, "10.1.0.0/16")] == ["b", "a"]
    assert srlinux.parse_rib_paths("{}", "10.1.0.0/16") == []


def test_srl_list():
    assert srlinux._list("c", {}, "k") == []
    assert srlinux._list("c", {"k": []}, "k") == []
    assert srlinux._list("c", {"k": [{"a": 1}]}, "k") == [{"a": 1}]
    for bad in ({"k": {}}, {"j": []}, {"k": [1]}, {"k": None}):
        with pytest.raises(DriverError):
            srlinux._list("c", bad, "k")
    with pytest.raises(DriverError):
        srlinux._json("[]")
    assert srlinux._json("{}") == {}


ATTR = J({"as-path": {"segment": [{"type": "as_sequence", "member": [65002, 65003]}]}, "next-hop": "2001:db8:0::2",
          "local-pref": 200, "med": 9, "communities": {"community": ["65000:010"], "large-community": ["1:2:3"]}})


def test_srl_parse_attr_set():
    row = {"prefix": "10.1.0.0/16", "neighbor": "10.0.0.2", "best-route": True, "attr-id": 7}
    assert srlinux.parse_attr_set(ATTR, row) == BgpPath(True, "65002 65003", "2001:db8::2", 200, 9, ["65000:10"],
                                                        ["1:2:3"], "10.0.0.2", False)
    bare = srlinux.parse_attr_set(J({"x": 1}), {"neighbor": "0.0.0.0", "origin-protocol": "static"}, 150)
    assert bare == BgpPath(False, "", None, 150, None, [], [], "0.0.0.0", True)
    assert srlinux.parse_attr_set(J({"x": 1}), row).local_pref is None
    with pytest.raises(DriverError):
        srlinux.parse_attr_set("{}", row)
    with pytest.raises(DriverError):
        srlinux.parse_attr_set(J({"local-pref": "x"}), row)


def test_srl_unread_path():
    assert srlinux.unread_path({"best-route": True, "neighbor": "10.0.0.3"}) == \
        BgpPath(True, None, None, None, None, [], [], "10.0.0.3", False)
    assert srlinux.unread_path({"origin-protocol": "local"}) == BgpPath(False, None, None, None, None, [], [], None, True)


def test_srl_find_and_instance_state():
    assert srlinux._find({"a": {"b": [{"c": 1}, {"oper-state": "up"}]}}, "oper-state") == "up"
    assert srlinux._find({"oper-state": "down", "x": {"oper-state": "up"}}, "oper-state") == "down"
    assert srlinux._find([{"x": None}, {"k": 0}], "k") == 0
    assert srlinux._find({"a": {"k": None}, "b": {"k": 2}}, "k") == 2
    assert srlinux._find("x", "k") is None and srlinux._find({}, "k") is None
    assert srlinux.parse_instance_state(J({"network-instance": [{"name": "red", "oper-state": "up"}]})) == "up"
    assert srlinux.parse_instance_state("{}") is None
    assert srlinux.parse_instance_state(J({"oper-state": ""})) is None
    assert srlinux.parse_instance_state(J({"oper-state": 1})) is None
    with pytest.raises(DriverError):
        srlinux.parse_instance_state("[]")


def test_srl_ip_or_none():
    assert srlinux._ip_or_none("2001:db8:0::1") == "2001:db8::1"
    assert srlinux._ip_or_none("x") is None and srlinux._ip_or_none(None) is None


def _srl_paths_lab(rib, attrs, neighbor_lp=None):
    rules = [("bgp-rib afi-safi", rib), ("attr-set", attrs)]
    if neighbor_lp is not None:
        rules.append(("local-preference", neighbor_lp))
    rules.append(("oper-state", J({"oper-state": "up"})))
    return Lab(rules)


def test_srl_bgp_paths_commands():
    lab = _srl_paths_lab(SRL_RIB, ATTR)
    obs = SrlDriver(lab, "r1").bgp_paths("10.1.0.0/16")
    assert lab.lines() == [
        "sr_cli --output-format json info from state /network-instance default bgp-rib afi-safi ipv4-unicast "
        "ipv4-unicast local-rib route 10.1.0.0/16 neighbor * origin-protocol * path-id *",
        "sr_cli --output-format json info from state /network-instance default bgp-rib attr-sets attr-set 7"]
    assert obs.value == [BgpPath(True, "65002 65003", "2001:db8::2", 200, 9, ["65000:10"], ["1:2:3"], "10.0.0.2")]
    assert len(obs.evidence) == 2
    rib6 = J({"route": [{"prefix": "2001:db8::/32", "neighbor": "10.0.0.2", "best-route": True, "attr-id": 3}]})
    lab = _srl_paths_lab(rib6, ATTR)
    SrlDriver(lab, "r1").bgp_paths("2001:db8::/32", "red")
    assert lab.lines() == [
        "sr_cli --output-format json info from state /network-instance red bgp-rib afi-safi ipv6-unicast "
        "ipv6-unicast local-rib route 2001:db8::/32 neighbor * origin-protocol * path-id *",
        "sr_cli --output-format json info from state /network-instance red bgp-rib attr-sets attr-set 3"]
    lab = _srl_paths_lab("{}", ATTR)
    obs = SrlDriver(lab, "r1").bgp_paths("10.1.0.0/16", "red")
    assert obs.value == [] and lab.lines()[-1].endswith("/network-instance red oper-state")
    lab = _srl_paths_lab("{}", ATTR)
    assert SrlDriver(lab, "r1").bgp_paths("10.1.0.0/16").value == [] and len(lab.calls) == 1
    with pytest.raises(DriverError):
        SrlDriver(Lab([("bgp-rib", "{}"), ("oper-state", "{}")]), "r1").bgp_paths("10.1.0.0/16", "nope")


def test_srl_bgp_paths_reads_the_best_and_the_first_learned_path():
    rib = J({"route": [{"prefix": "10.1.0.0/16", "neighbor": "10.0.0.3", "attr-id": 2, "origin-protocol": "bgp"},
                       {"prefix": "10.1.0.0/16", "neighbor": "0.0.0.0", "best-route": True, "attr-id": 1,
                        "origin-protocol": "static"},
                       {"prefix": "10.1.0.0/16", "neighbor": "10.0.0.4", "attr-id": 3, "origin-protocol": "bgp"}]})
    lab = _srl_paths_lab(rib, J({"as-path": {}, "local-pref": 100}))
    paths = SrlDriver(lab, "r1").bgp_paths("10.1.0.0/16").value
    assert [p.neighbor for p in paths] == ["0.0.0.0", "10.0.0.3", "10.0.0.4"]
    assert [p.local_pref for p in paths] == [100, 100, None]          # the third path is not read
    assert paths[0].local_candidate and not paths[1].local_candidate and paths[2].as_path is None
    assert [ln.rsplit(" ", 1)[1] for ln in lab.lines() if "attr-set " in ln] == ["1", "2"]
    # the best path is learned: only it is read
    rib = J({"route": [{"prefix": "10.1.0.0/16", "neighbor": "10.0.0.3", "attr-id": 2, "best-route": True},
                       {"prefix": "10.1.0.0/16", "neighbor": "10.0.0.4", "attr-id": 3}]})
    lab = _srl_paths_lab(rib, J({"local-pref": 100}))
    paths = SrlDriver(lab, "r1").bgp_paths("10.1.0.0/16").value
    assert [p.local_pref for p in paths] == [100, None] and sum("attr-set " in ln for ln in lab.lines()) == 1
    # only the router's own paths: only the best is read
    rib = J({"route": [{"prefix": "10.1.0.0/16", "neighbor": "0.0.0.0", "attr-id": 2, "best-route": True,
                        "origin-protocol": "local"},
                       {"prefix": "10.1.0.0/16", "neighbor": "0.0.0.0", "attr-id": 3, "origin-protocol": "static"}]})
    lab = _srl_paths_lab(rib, J({"local-pref": 100}))
    assert [p.local_pref for p in SrlDriver(lab, "r1").bgp_paths("10.1.0.0/16").value] == [100, None]


def test_srl_local_pref_from_the_neighbor():
    rib = J({"route": [{"prefix": "10.1.0.0/16", "neighbor": "10.0.0.2", "attr-id": 7, "best-route": True}]})
    lab = _srl_paths_lab(rib, J({"med": 1}), neighbor_lp=J({"local-preference": 250}))
    [p] = SrlDriver(lab, "r1").bgp_paths("10.1.0.0/16", "red").value
    assert p.local_pref == 250
    assert lab.lines()[-1] == ("sr_cli --output-format json info from state /network-instance red protocols bgp "
                               "neighbor 10.0.0.2 local-preference")
    lab = _srl_paths_lab(rib, J({"med": 1}), neighbor_lp="{}")
    assert SrlDriver(lab, "r1").bgp_paths("10.1.0.0/16").value[0].local_pref is None
    with pytest.raises(DriverError):
        SrlDriver(_srl_paths_lab(rib, J({"med": 1}), neighbor_lp=J({"local-preference": "x"})), "r1").bgp_paths("10.1.0.0/16")
    with pytest.raises(DriverError):
        SrlDriver(_srl_paths_lab(rib, J({"med": 1}), neighbor_lp="[]"), "r1").bgp_paths("10.1.0.0/16")
    # no neighbor to ask: the router's own route, an unspecified address, or a non-IP neighbor
    for row in ({"neighbor": "0.0.0.0"}, {"neighbor": "::"}, {"neighbor": "x"}, {},
                {"neighbor": "10.0.0.2", "origin-protocol": "static"}):
        r = J({"route": [{"prefix": "10.1.0.0/16", "attr-id": 7, "best-route": True, **row}]})
        lab = _srl_paths_lab(r, J({"med": 1}))
        assert SrlDriver(lab, "r1").bgp_paths("10.1.0.0/16").value[0].local_pref is None
        assert not any("local-preference" in ln for ln in lab.lines())
    # the attr-set has local-pref: no neighbor lookup
    lab = _srl_paths_lab(rib, J({"local-pref": 5}))
    assert SrlDriver(lab, "r1").bgp_paths("10.1.0.0/16").value[0].local_pref == 5
    assert not any("local-preference" in ln for ln in lab.lines())


@pytest.mark.parametrize("attr_id", ["7; reboot", None, "x", "", "-1"])
def test_srl_bad_attr_id_raises(attr_id):
    rib = J({"route": [{"prefix": "10.1.0.0/16", "neighbor": "10.0.0.2", "attr-id": attr_id, "best-route": True}]})
    with pytest.raises(DriverError):
        SrlDriver(_srl_paths_lab(rib, ATTR), "r1").bgp_paths("10.1.0.0/16")


def test_srl_all_routes():
    text = J({"route": [{"ipv4-prefix": "10.1.2.0/16", "route-type": "local", "active": True}]})
    lab = Lab([("route-table", text)])
    obs = SrlDriver(lab, "r1").all_routes()
    assert lab.lines() == ["sr_cli --output-format json info from state /network-instance default route-table "
                           "ipv4-unicast route * id * route-type * route-owner * origin-network-instance *"]
    assert obs.value == [Route("10.1.0.0/16", "connected", True)]
    v6 = J({"route": [{"ipv6-prefix": "2001:db8::/32", "route-type": "bgp"}]})
    lab = Lab([("route-table", v6)])
    assert SrlDriver(lab, "r1").all_routes("red", 6).value == [Route("2001:db8::/32", "bgp", False)]
    assert lab.lines() == ["sr_cli --output-format json info from state /network-instance red route-table "
                           "ipv6-unicast route * id * route-type * route-owner * origin-network-instance *"]
    lab = Lab([("route-table", "{}"), ("oper-state", J({"oper-state": "up"}))])
    assert SrlDriver(lab, "r1").all_routes("red").value == [] and lab.lines()[-1].endswith("red oper-state")
    lab = Lab([("route-table", "{}")])
    assert SrlDriver(lab, "r1").all_routes().value == [] and len(lab.calls) == 1
    with pytest.raises(DriverError):
        SrlDriver(Lab([("route-table", "{}"), ("oper-state", "{}")]), "r1").all_routes("nope")
    with pytest.raises(DriverError):
        srlinux.parse_all_routes(J({"route": [{"ipv6-prefix": "2001:db8::/32"}]}))
    assert srlinux.parse_all_routes(J({"route": [{"ipv4-prefix": "10.0.0.0/8"}]})) == [Route("10.0.0.0/8", "", False)]


@pytest.mark.parametrize("netns,vrf,expected", [
    ("srbase-default (id: 1)\nsrbase-mgmt\n", "default", "srbase-default"),
    ("srbase (id: 0)\nsrbase-mgmt\n", "default", "srbase"),
    ("srbase-mgmt\n", "default", "srbase-default"),
    ("\n  \nsrbase\n", "default", "srbase"),
    ("srbase\nsrbase-red\n", "red", "srbase-red"),
    ("srbase\n", "red", "srbase-red"),
    ("", "default", "srbase-default"),
])
def test_srl_ping_namespace(netns, vrf, expected):
    lab = Lab([("netns list", netns), ("netns exec", (0, PING_OK + "x" * 6000, "e" * 1500))])
    obs = SrlDriver(lab, "r1").ping("10.9.9.9", None, 3, vrf)
    assert lab.calls[0] == ("r1", ["ip", "netns", "list"], 15)
    assert lab.calls[1] == ("r1", ["ip", "netns", "exec", expected, "ping", "-c", "3", "-W", "1", "10.9.9.9"], 16)
    assert obs.value == (3, 2)
    ev = obs.evidence[0]
    assert ev["node"] == "r1" and ev["rc"] == 0 and ev["cmd"] == " ".join(lab.calls[1][1])
    assert len(ev["output"]) == 5000 and ev["stderr"] == "e" * 1000


def test_srl_ping6_with_source():
    lab = Lab([("netns list", "srbase-red\n"), ("netns exec", (1, "x"))])
    obs = SrlDriver(lab, "r1").ping("2001:db8::9", "2001:db8::1", 4, "red")
    assert lab.calls[1] == ("r1", ["ip", "netns", "exec", "srbase-red", "ping6", "-c", "4", "-W", "1", "-I",
                                   "2001:db8::1", "2001:db8::9"], 18)
    assert obs.value == (0, 0) and obs.evidence[0]["rc"] == 1
    with pytest.raises(DriverError):
        SrlDriver(Lab([]), "r1").ping("10.9.9.9", None, 3, "all")


# ----------------------------------------------------------------------------------------------- EOS

def eos_summary(vrf="default", **peers):
    return J({"vrfs": {vrf: {"peers": peers}}})


def test_eos_bgp_neighbors_commands_and_counts():
    v4 = eos_summary(**{"10.0.0.2": {"peerState": "Established", "prefixAccepted": 3},
                        "10.0.0.3": {"peerState": "Idle (Admin)"}})
    v6 = eos_summary(**{"10.0.0.2": {"peerState": "Established", "prefixAccepted": "5"},
                        "2001:db8:0::1": {"peerState": "Active", "prefixAccepted": 0}})
    lab = Lab([("ipv6 bgp summary", v6), ("ip bgp summary", v4)])
    obs = EosDriver(lab, "r1").bgp_neighbors()
    assert lab.lines() == ["Cli -p 15 -c show ip bgp summary vrf default | json",
                           "Cli -p 15 -c show ipv6 bgp summary vrf default | json"]
    n = obs.value
    assert n["10.0.0.2"] == BgpNeighbor("10.0.0.2", "established", {"ipv4-unicast": 3, "ipv6-unicast": 5})
    assert n["10.0.0.3"] == BgpNeighbor("10.0.0.3", "idle", {})
    assert n["2001:db8::1"] == BgpNeighbor("2001:db8:0::1", "active", {"ipv6-unicast": 0})
    assert len(obs.evidence) == 2
    lab = Lab([("ipv6 bgp summary", eos_summary("red")), ("ip bgp summary", eos_summary("red"))])
    assert EosDriver(lab, "r1").bgp_neighbors("red").value == {}
    assert lab.lines() == ["Cli -p 15 -c show ip bgp summary vrf red | json",
                           "Cli -p 15 -c show ipv6 bgp summary vrf red | json"]
    with pytest.raises(DriverError):   # the VRF is not in the answer
        EosDriver(Lab([("bgp summary", eos_summary("red"))]), "r1").bgp_neighbors("blue")


def test_eos_summary_rules():
    assert eos.parse_bgp_summary(eos_summary(**{"10.0.0.2": {"peerState": "Established", "prefixAccepted": 1}}),
                                 afi="ipv6-unicast")["10.0.0.2"].prefixes == {"ipv6-unicast": 1}
    assert eos.parse_bgp_summary(eos_summary(**{"10.0.0.2": {"peerState": "Established", "prefixAccepted": 1}}),
                                 afi="evpn")["10.0.0.2"].prefixes == {"evpn": 1}
    into = {}
    out = eos.parse_bgp_summary(eos_summary(**{"10.0.0.2": {"peerState": "Connect"}}), into=into)
    assert out is into and into["10.0.0.2"].state == "connect"
    for bad in (eos_summary(**{"10.0.0.2": {"peerState": "Established"}}),          # established without a count
                eos_summary(**{"10.0.0.2": {"peerState": ""}}), eos_summary(**{"10.0.0.2": {"peerState": 1}}),
                eos_summary(**{"10.0.0.2": "x"}), eos_summary(**{"10.0.0.2": {}}),
                eos_summary(**{"10.0.0.2": {"peerState": "Established", "prefixAccepted": "x"}}),
                J({"vrfs": {"default": {}}}), J({"vrfs": {"default": {"peers": []}}}), J({"vrfs": {"default": 1}}),
                J({"vrfs": []}), J({}), J([]), J({"errors": ["% Not supported"]}), J({"errors": [], "vrfs": {}})):
        with pytest.raises(DriverError):
            eos.parse_bgp_summary(bad)
    with pytest.raises(DriverError):
        eos.parse_bgp_summary(eos_summary(), vrf="red")


def eos_routes(vrf="default", **routes):
    return J({"vrfs": {vrf: {"routes": routes}}})


def eos_bgp(vrf="default", entries=None):
    return J({"vrfs": {vrf: {"bgpRouteEntries": entries or {}}}})


def eos_path(peer="10.0.0.2", **kw):
    p = {"peerEntry": {"peerAddr": peer}}
    p.update(kw)
    return p


def test_eos_routes_commands():
    lab = Lab([("route", eos_routes(**{"10.1.0.0/16": {"routeType": "eBGP"}})), ("bgp", eos_bgp())])
    obs = EosDriver(lab, "r1").routes("10.1.0.0/16")
    assert lab.lines() == ["Cli -p 15 -c show ip route vrf default 10.1.0.0/16 | json",
                           "Cli -p 15 -c show ip bgp 10.1.0.0/16 vrf default | json"]
    assert obs.value == [Route("10.1.0.0/16", "bgp", True)] and len(obs.evidence) == 2
    lab = Lab([("route", eos_routes("red")), ("bgp", eos_bgp("red"))])
    assert EosDriver(lab, "r1").routes("2001:db8::/32", "red").value == []
    assert lab.lines() == ["Cli -p 15 -c show ipv6 route vrf red 2001:db8::/32 | json",
                           "Cli -p 15 -c show ipv6 bgp 2001:db8::/32 vrf red | json"]


@pytest.mark.parametrize("rtype,proto", [("eBGP", "bgp"), ("iBGP", "bgp"), ("connected", "connected"),
                                         ("static", "static"), ("OSPF Inter Area", "ospf"), ("isisLevel2", "isis"),
                                         ("Dropped", "static"), ("aggregate", "aggregate"), ("weird type", "weirdtype"),
                                         (None, "none")])
def test_eos_route_types(rtype, proto):
    r = {"routeType": rtype} if rtype is not None else {}
    out = eos.parse_routes(eos_routes(**{"10.1.0.0/16": r}), eos_bgp(), "10.1.0.0/16")
    assert out == [Route("10.1.0.0/16", proto if rtype is not None else "", True)]


def test_eos_routes_rules():
    pfx = "10.1.0.0/16"
    static = eos_routes(**{pfx: {"routeType": "static"}, "10.0.0.0/8": {"routeType": "eBGP"}})
    learned = eos_bgp(entries={pfx: {"bgpRoutePaths": [eos_path("")]}, "10.1.0.0/24": {"bgpRoutePaths": [eos_path()]}})
    assert eos.parse_routes(static, learned, pfx) == [Route(pfx, "static", True)]   # own path; other prefix ignored
    learned = eos_bgp(entries={pfx: {"bgpRoutePaths": [eos_path(""), eos_path()]}})
    assert eos.parse_routes(static, learned, pfx) == [Route(pfx, "static", True), Route(pfx, "bgp", False)]
    installed = eos_routes(**{pfx: {"routeType": "eBGP"}})
    assert eos.parse_routes(installed, learned, pfx) == [Route(pfx, "bgp", True)]
    two = J({"vrfs": {"default": {"bgpRouteEntries": {pfx: {"bgpRoutePaths": [eos_path()]},
                                                      "10.1.0.0/16 ": {"bgpRoutePaths": [eos_path()]}}}}})
    assert eos.parse_routes(eos_routes(), two, pfx) == [Route(pfx, "bgp", False)]   # added once
    assert eos.parse_routes(eos_routes("red"), eos_bgp("red"), pfx, "red") == []
    for rt, bgp in ((eos_routes(**{pfx: "x"}), eos_bgp()), (eos_routes(**{"x": {}}), eos_bgp()),
                    (eos_routes(), eos_bgp(entries={pfx: {"bgpRoutePaths": [{}]}})),
                    (eos_routes(), eos_bgp(entries={pfx: {"bgpRoutePaths": [{"peerEntry": {"peerAddr": 1}}]}})),
                    (eos_routes(), eos_bgp(entries={pfx: {"bgpRoutePaths": [{"peerEntry": "x"}]}})),
                    (eos_routes(), eos_bgp(entries={pfx: {"bgpRoutePaths": {}}})),
                    (eos_routes(), eos_bgp(entries={pfx: "x"})),
                    (eos_routes(), eos_bgp(entries={pfx: {"bgpRoutePaths": ["x"]}})),
                    (eos_routes(), J({"vrfs": {"default": {}}})), (J({"vrfs": {"default": {}}}), eos_bgp()),
                    (eos_routes(), eos_bgp("red")), (eos_routes("red"), eos_bgp())):
        with pytest.raises(DriverError):
            eos.parse_routes(rt, bgp, pfx)


def test_eos_bgp_paths():
    pfx = "10.1.0.0/16"
    text = eos_bgp(entries={pfx: {"bgpRoutePaths": [
        eos_path(routeType={"active": True}, asPathEntry={"asPath": "65002  65003"}, nextHop="2001:db8:0::2",
                 localPreference=200, med=5, routeDetail={"communityList": ["65000:010"],
                                                          "largeCommunityList": ["1:2:3"]}),
        eos_path("", routeType={"active": False}),
    ]}, "10.0.0.0/8": {"bgpRoutePaths": [eos_path(routeType={"active": True})]}})
    lab = Lab([("bgp", text)])
    obs = EosDriver(lab, "r1").bgp_paths(pfx)
    assert lab.lines() == ["Cli -p 15 -c show ip bgp 10.1.0.0/16 vrf default | json"] and len(obs.evidence) == 1
    assert obs.value == [BgpPath(True, "65002 65003", "2001:db8::2", 200, 5, ["65000:10"], ["1:2:3"], "10.0.0.2"),
                         BgpPath(False, "", None, None, None, [], [], None)]
    lab = Lab([("bgp", eos_bgp("red"))])
    assert EosDriver(lab, "r1").bgp_paths("2001:db8::/32", "red").value == []
    assert lab.lines() == ["Cli -p 15 -c show ipv6 bgp 2001:db8::/32 vrf red | json"]
    bare = eos_bgp(entries={pfx: {"bgpRoutePaths": [{"routeType": None, "asPathEntry": None, "routeDetail": None,
                                                     "peerEntry": None}]}})
    assert eos.parse_bgp_paths(bare, pfx) == [BgpPath(False, "", None, None, None, [], [], None)]
    with pytest.raises(DriverError):
        eos.parse_bgp_paths(eos_bgp(entries={pfx: {"bgpRoutePaths": [{"med": "x"}]}}), pfx)


def test_eos_all_routes():
    text = eos_routes(**{"10.1.2.0/16": {"routeType": "eBGP"}, "10.2.0.0/16": {"routeType": "connected"}})
    lab = Lab([("route", text)])
    obs = EosDriver(lab, "r1").all_routes()
    assert lab.lines() == ["Cli -p 15 -c show ip route vrf default | json"] and len(obs.evidence) == 1
    assert obs.value == [Route("10.1.0.0/16", "bgp", True), Route("10.2.0.0/16", "connected", True)]
    lab = Lab([("route", eos_routes("red"))])
    assert EosDriver(lab, "r1").all_routes("red", 6).value == []
    assert lab.lines() == ["Cli -p 15 -c show ipv6 route vrf red | json"]
    for bad in (eos_routes(**{"10.0.0.0/8": "x"}), eos_routes(**{"x": {}}), eos_routes("red")):
        with pytest.raises(DriverError):
            eos.parse_all_routes(bad)
    assert eos.parse_all_routes(eos_routes(**{"10.0.0.0/8": {}})) == [Route("10.0.0.0/8", "", True)]


EOS_PING = "PING 10.9.9.9\n3 packets transmitted, 3 received, 0% packet loss\n"


def test_eos_ping():
    lab = Lab([("ping", (0, EOS_PING + "x" * 6000, "e" * 1500))])
    obs = EosDriver(lab, "r1").ping("10.9.9.9", None, 3)
    assert lab.calls == [("r1", ["Cli", "-p", "15", "-c", "ping vrf default 10.9.9.9 repeat 3"], 21)]
    ev = obs.evidence[0]
    assert ev == {"node": "r1", "cmd": "Cli -c ping vrf default 10.9.9.9 repeat 3", "rc": 0,
                  "output": (EOS_PING + "x" * 6000)[-5000:], "stderr": "e" * 1000}
    lab = Lab([("ping", (1, EOS_PING))])
    obs = EosDriver(lab, "r1").ping("2001:db8::9", "2001:db8::1", 5, "red")
    assert lab.calls == [("r1", ["Cli", "-p", "15", "-c", "ping ipv6 vrf red 2001:db8::9 repeat 5 source 2001:db8::1"],
                          25)]
    assert obs.value == (3, 3) and obs.evidence[0]["rc"] == 1
    with pytest.raises(DriverError):
        EosDriver(Lab([]), "r1").ping("10.9.9.9", None, 3, "all")


def test_eos_json_and_vrf_helpers():
    assert eos._json("c", '{"vrfs": {}}') == {"vrfs": {}}
    for bad in ("[]", '{"errors": "x"}', ""):
        with pytest.raises(DriverError):
            eos._json("c", bad)
    assert eos._vrf("c", {"vrfs": {"red": {"a": 1}}}, "red") == {"a": 1}
    for data in ({"vrfs": {"red": 1}}, {"vrfs": {}}, {"vrfs": None}, {}):
        with pytest.raises(DriverError) as exc:
            eos._vrf("c", data, "red")
        # only "the VRF is not in a well-formed answer" means there is nothing there
        assert isinstance(exc.value, NoSuchInstance) is (data == {"vrfs": {}})
    # a well-formed answer that lists other VRFs (not only an empty one): the VRF isn't there
    with pytest.raises(NoSuchInstance):
        eos._vrf("c", {"vrfs": {"default": {}, "blue": {}}}, "red")
    with pytest.raises(NoSuchInstance):
        EosDriver(Lab([("bgp summary", eos_summary("red"))]), "r1").bgp_neighbors("blue")
    assert eos._table("c", {"k": {}}, "k") == {}
    for entry in ({}, {"k": []}, {"k": None}):
        with pytest.raises(DriverError):
            eos._table("c", entry, "k")


# ----------------------------------------------------------------------------------------------- more edges

def test_frr_malformed_entry_for_another_prefix_is_still_unexpected():
    text = J({"10.0.0.0/8": [{}], "10.1.0.0/16": [{"protocol": "bgp", "selected": True}]})
    with pytest.raises(DriverError):
        frr.parse_routes(text, "10.1.0.0/16")
    with pytest.raises(DriverError):
        frr.parse_routes(J({"10.0.0.0/8": ["x"], "10.1.0.0/16": [{"protocol": "bgp"}]}), "10.1.0.0/16")


def test_frr_next_hop_without_scope_is_global():
    assert frr._next_hop([{"ip": "fe80::1", "scope": "link-local"}, {"ip": "2001:db8::2"}]) == "2001:db8::2"


def test_srl_routes_read_the_bgp_rib():
    """A received BGP path that only shows in the RIB (lost to a static) is present: the RIB must be read."""
    lab = Lab([("route-table", J({"route": [{"ipv4-prefix": "10.1.0.0/16", "route-type": "static", "active": True}]})),
               ("bgp-rib", SRL_RIB)])
    obs = SrlDriver(lab, "r1").routes("10.1.0.0/16")
    assert obs.value == [Route("10.1.0.0/16", "static", True), Route("10.1.0.0/16", "bgp", False)]
    assert len(obs.evidence) == 2 and obs.evidence[1]["cmd"].startswith("sr_cli")


def test_srl_evidence_is_kept_everywhere():
    lab = Lab([("neighbor", "{}"), ("oper-state", J({"oper-state": "up"}))])
    assert len(SrlDriver(lab, "r1").bgp_neighbors("red").evidence) == 2
    lab = Lab([("neighbor", SRL_NBR)])
    assert len(SrlDriver(lab, "r1").bgp_neighbors().evidence) == 1
    lab = Lab([("bgp-rib", "{}"), ("oper-state", J({"oper-state": "up"}))])
    assert len(SrlDriver(lab, "r1").bgp_paths("10.1.0.0/16", "red").evidence) == 2
    lab = Lab([("route-table", "{}"), ("oper-state", J({"oper-state": "up"}))])
    assert len(SrlDriver(lab, "r1").all_routes("red").evidence) == 2
    lab = Lab([("route-table", J({"route": [{"ipv4-prefix": "10.0.0.0/8"}]}))])
    assert len(SrlDriver(lab, "r1").all_routes().evidence) == 1


def test_frr_all_routes_evidence():
    lab = Lab([("route", "{}"), ("show vrf", SHOW_VRF)])
    assert len(FrrDriver(lab, "r1").all_routes("red").evidence) == 2
    lab = Lab([("route", J({"10.0.0.0/8": [{"protocol": "static"}]}))])
    assert len(FrrDriver(lab, "r1").all_routes().evidence) == 1


def test_srl_ping_defaults_to_the_default_instance():
    lab = Lab([("netns list", "srbase-default\n"), ("netns exec", PING_OK)])
    assert SrlDriver(lab, "r1").ping("10.9.9.9", None, 3).value == (3, 2)
    assert lab.calls[1][1][3] == "srbase-default"
    lab = Lab([("ping", PING_OK)])
    FrrDriver(lab, "r1").ping("10.9.9.9", None, 3)
    assert lab.calls[0][1][0] == "ping"
    lab = Lab([("ping", EOS_PING)])
    EosDriver(lab, "r1").ping("10.9.9.9", None, 3)
    assert "vrf default " in lab.calls[0][1][-1]


def test_default_vrf_everywhere():
    lab = Lab([("route-table", "{}"), ("bgp-rib", "{}")])
    SrlDriver(lab, "r1").routes("10.1.0.0/16")
    assert all("network-instance default " in ln for ln in lab.lines())
    lab = Lab([("bgp-rib", "{}")])
    SrlDriver(lab, "r1").bgp_paths("10.1.0.0/16")
    assert all("network-instance default " in ln for ln in lab.lines())
    lab = Lab([("route", eos_routes()), ("bgp", eos_bgp())])
    EosDriver(lab, "r1").routes("10.1.0.0/16")
    EosDriver(lab, "r1").bgp_paths("10.1.0.0/16")
    EosDriver(lab, "r1").all_routes()
    assert all("vrf default " in ln for ln in lab.lines())
    lab = Lab([("bgp summary", eos_summary())])
    EosDriver(lab, "r1").bgp_neighbors()
    assert all("vrf default " in ln for ln in lab.lines())
    lab = Lab([("show bgp", "{}"), ("route", "{}")])
    FrrDriver(lab, "r1").routes("10.1.0.0/16")
    FrrDriver(lab, "r1").bgp_paths("10.1.0.0/16")
    FrrDriver(lab, "r1").all_routes()
    assert not any(" vrf " in ln for ln in lab.lines())
