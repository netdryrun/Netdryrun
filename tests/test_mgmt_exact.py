"""mgmt.py, exactly: every message, command, argument and boundary (mutation triage of bd76896, 2026-11-06).

test_mgmt.py proves the behaviour; this file pins what each path says and sends, so a changed word, timeout, slice or
sub-condition fails a test instead of surviving mutation.
"""
from __future__ import annotations

import ipaddress
import json

import pytest

from netdryrun import mgmt
from netdryrun.lab import NETNS_HELPER_IMAGE, ExecResult, LabError, Node
from netdryrun.mgmt import ManagementPathError

from test_mgmt import (BB_V4, FRR_V4, GW4, GW6, INSPECT, EosLab, NoIpLab, RouteLab, m_of)
from test_verdict_runner import chk

LONG = "E" * 400 + "TAIL"


class Rec(RouteLab):
    """RouteLab that records every exec_root call with its timeout."""

    def __init__(self, **kw):
        super().__init__(**kw)
        self.timeouts: list = []
        self.sysctl = ExecResult([], 1, "", "sysctl: error setting key: Read-only file system")

    def exec_root(self, node, cmd, timeout=60):
        self.timeouts.append((node, cmd[0], timeout))
        if cmd[0] == "sysctl":
            self.calls.append((node, tuple(cmd)))
            return self.sysctl
        return super().exec_root(node, cmd, timeout)


# ------------------------------------------------------------------------------------------- docker_mgmt

def test_docker_mgmt_exact():
    m = mgmt.docker_mgmt(RouteLab(inspect={"r1": {**INSPECT, "Id": "abc123"}}), "r1")
    assert (m.node, m.mode, m.cid) == ("r1", "clab", "abc123")
    assert m.subnets == [ipaddress.ip_network("172.31.99.0/24"), ipaddress.ip_network("3fff:172:31:99::/64")]
    assert m.gateways == [ipaddress.ip_address(GW4), ipaddress.ip_address(GW6)]
    assert mgmt.docker_mgmt(RouteLab(), "r1").cid == ""


def test_docker_mgmt_ipv4_only_network_and_null_networks():
    v4 = {"HostConfig": {"NetworkMode": "clab"}, "NetworkSettings": {"Networks": {"clab": {
        "IPAddress": "172.20.20.2", "IPPrefixLen": 24, "Gateway": "172.20.20.1", "GlobalIPv6Address": "",
        "IPv6Gateway": ""}}}}
    m = mgmt.docker_mgmt(RouteLab(inspect={"r1": v4}), "r1")
    assert m.subnets == [ipaddress.ip_network("172.20.20.0/24")] and m.gateways == [ipaddress.ip_address("172.20.20.1")]
    none = {"HostConfig": {"NetworkMode": "none"}, "NetworkSettings": {"Networks": None}}
    m = mgmt.docker_mgmt(RouteLab(inspect={"r1": none}), "r1")
    assert (m.mode, m.subnets, m.gateways) == ("none", [], [])


def test_docker_mgmt_errors_exact():
    with pytest.raises(LabError) as e:
        mgmt.docker_mgmt(RouteLab(inspect={"r1": {"HostConfig": {}}}), "r1")
    assert str(e.value) == "r1: `docker inspect` printed no network settings, so its management network can't be read"
    with pytest.raises(LabError) as e:
        mgmt.docker_mgmt(RouteLab(inspect={"r1": None}), "r1")
    assert "printed no network settings" in str(e.value)
    bad = {"HostConfig": {"NetworkMode": "clab"}, "NetworkSettings": {"Networks": {"clab": "x" * 100}}}
    with pytest.raises(LabError) as e:
        mgmt.docker_mgmt(RouteLab(inspect={"r1": bad}), "r1")
    assert str(e.value) == "r1: Docker network 'clab' reads " + "x" * 80


# ------------------------------------------------------------------------------------------- parse_ip_route, _pairs

def test_parse_ip_route_every_field():
    rs = mgmt.parse_ip_route("blackhole 10.0.0.0/8 proto static metric 20\n\n"
                             "10.1.0.0/16 via 10.0.0.2 dev eth1 proto bgp table 10 metric 20\n", 4)
    assert [(r.rtype, r.prefix, r.dev, r.via, r.proto, r.table, r.family, r.line) for r in rs] == [
        ("blackhole", "10.0.0.0/8", "", "", "static", "main", 4, "blackhole 10.0.0.0/8 proto static metric 20"),
        ("unicast", "10.1.0.0/16", "eth1", "10.0.0.2", "bgp", "10", 4,
         "10.1.0.0/16 via 10.0.0.2 dev eth1 proto bgp table 10 metric 20")]


def test_parse_ip_route_legs_take_the_heads_fields():
    rs = mgmt.parse_ip_route("default proto zebra table 7 metric 20\n\tnexthop via 10.9.0.2 dev d0 weight 1\n"
                             "  nexthop via 10.9.0.6 dev d1 weight 1", 6)
    assert [(r.rtype, r.prefix, r.dev, r.via, r.proto, r.table, r.family, r.line) for r in rs] == [
        ("unicast", "default", "", "", "zebra", "7", 6, "default proto zebra table 7 metric 20"),
        ("unicast", "default", "d0", "10.9.0.2", "zebra", "7", 6, "nexthop via 10.9.0.2 dev d0 weight 1"),
        ("unicast", "default", "d1", "10.9.0.6", "zebra", "7", 6, "nexthop via 10.9.0.6 dev d1 weight 1")]


def test_parse_ip_route_errors_exact():
    with pytest.raises(LabError) as e:
        mgmt.parse_ip_route("\tnexthop via 1.1.1.1 dev x", 4)
    assert str(e.value) == "`ip route` printed a line it doesn't explain: 'nexthop via 1.1.1.1 dev x'"
    with pytest.raises(LabError) as e:
        mgmt.parse_ip_route("default dev x\n    " + "c" * 200, 4)
    assert str(e.value) == "`ip route` printed a line it doesn't explain: '" + "c" * 120 + "'"
    with pytest.raises(LabError) as e:
        mgmt.parse_ip_route("unreachable" + " " * 0, 4)
    assert str(e.value) == "`ip route` printed a route without a destination: 'unreachable'"


@pytest.mark.parametrize("tokens,expected", [
    (["onlink", "dev", "eth0"], {"dev": "eth0"}),
    (["dev", "eth0", "dev", "eth9"], {"dev": "eth0"}),
    (["via", "inet6", "fe80::1", "dev", "eth1"], {"via": "fe80::1", "dev": "eth1"}),
    (["via", "inet", "10.0.0.1"], {"via": "10.0.0.1"}),
    (["via", "inet6"], {"via": ""}),
    (["via", "10.0.0.1", "via", "inet6", "fe80::1"], {"via": "10.0.0.1"}),
    (["encap", "mpls", "100/200", "via", "10.0.0.1", "dev", "eth0"], {"via": "10.0.0.1", "dev": "eth0"}),
    (["encap", "ip", "id", "5", "dst", "1.1.1.1", "ttl", "3", "dev", "eth0"], {"dev": "eth0"}),
    (["encap", "seg6"], {}),
    (["metric"], {"metric": ""}),
    (["linkdown", "dead", "pervasive", "offload", "trap", "rt_offload", "rt_trap", "notify", "cache", "lock",
      "rt_offload_failed", "unresolved", "dev", "e"], {"dev": "e"}),
])
def test_pairs_exact(tokens, expected):
    assert mgmt._pairs(tokens) == expected


def test_pairs_every_encap_terminator():
    for key in ("via", "dev", "proto", "table", "scope", "src", "metric", "pref", "weight", "nhid", "mtu", "expires",
                "realm", "error", "advmss", "hoplimit"):
        assert mgmt._pairs(["encap", "mpls", "1", "2", key, "v"]) == {key: "v"}, key


# ------------------------------------------------------------------------------------------- classify_linux

def test_in_mgmt_subnet_exact():
    m = m_of()
    assert mgmt._in_mgmt_subnet("172.31.99.0/24", m) is True
    assert mgmt._in_mgmt_subnet("172.31.99.5/24", m) is True          # host bits allowed (strict=False)
    assert mgmt._in_mgmt_subnet("172.31.0.0/16", m) is False          # a wider prefix is not the subnet
    assert mgmt._in_mgmt_subnet("172.31.99.0/25", m) is False
    assert mgmt._in_mgmt_subnet("junk", m) is False


@pytest.mark.parametrize("line,fam,where", [
    ("10.0.0.0/8 dev eth1 proto kernel", 4, "skip"),                       # not a management device
    ("local 172.31.99.2 dev eth0 table local proto kernel", 4, "skip"),
    ("broadcast 172.31.99.255 dev eth0 table local proto kernel", 4, "skip"),
    ("anycast 3fff:172:31:99:: dev eth0 table local proto kernel", 6, "skip"),
    ("multicast ff00::/8 dev eth0 table local proto kernel", 6, "skip"),
    ("fe80::/64 dev eth0 proto kernel metric 256", 6, "skip"),
    ("fe80::/64 via fe80::1 dev eth0", 6, "other"),                        # a gateway on the link-local prefix
    ("172.31.99.0/24 dev eth0 proto kernel scope link", 4, "skip"),
    ("172.31.99.0/24 dev eth0 scope link", 4, "skip"),                      # busybox: no proto
    ("172.31.99.0/24 dev eth0 proto static", 4, "other"),                   # the subnet, configured
    ("172.31.99.0/24 via 172.31.99.1 dev eth0 proto kernel", 4, "other"),
    ("172.31.0.0/16 dev eth0 proto kernel", 4, "other"),                    # not the subnet
    ("ff00::/8 dev eth0 metric 256", 6, "skip"),
    ("ff00::/8 via fe80::1 dev eth0", 6, "other"),
    ("ff00::/8 dev eth0", 4, "other"),                                      # an IPv4 table never has it
    ("default via 172.31.99.1 dev eth0", 4, "docker"),
    ("0.0.0.0/0 via 172.31.99.1 dev eth0", 4, "docker"),
    ("::/0 via 3fff:172:31:99::1 dev eth0 metric 1024", 6, "docker"),
    ("default via 172.31.99.1 dev eth0 proto boot", 4, "docker"),
    ("default via 172.31.99.1 dev eth0 proto static", 4, "other"),
    ("default via 172.31.99.1 dev eth0 table 5", 4, "other"),
    ("default via 172.31.99.9 dev eth0", 4, "other"),
    ("default dev eth0", 4, "other"),
    ("10.0.0.0/8 via 172.31.99.1 dev eth0", 4, "other"),
    ("default nhid 5 proto zebra", 4, "other"),                             # no device
    ("unreachable default proto kernel metric 4278198272", 4, "skip"),      # no device, not unicast
])
def test_classify_linux_every_rule(line, fam, where):
    docker, other = mgmt.classify_linux(mgmt.parse_ip_route(line, fam), m_of())
    got = "docker" if docker else "other" if other else "skip"
    assert got == where and len(docker) + len(other) <= 1


def test_classify_linux_a_multipath_leg_via_the_gateway_is_never_dockers():
    docker, other = mgmt.classify_linux(mgmt.parse_ip_route(
        "default proto boot\n\tnexthop via 172.31.99.1 dev eth0 weight 1", 4), m_of())
    assert docker == [] and [r.line for r in other] == ["nexthop via 172.31.99.1 dev eth0 weight 1"]


def test_classify_linux_a_multipath_key_is_per_family_prefix_and_table():
    # the leg's (family, prefix, table) is multipath; a single default in another table, family or prefix is not
    rs = mgmt.parse_ip_route("default proto static table 9\n\tnexthop via 10.9.0.2 dev d0", 4) + \
        mgmt.parse_ip_route("default via 172.31.99.1 dev eth0", 4) + \
        mgmt.parse_ip_route("default proto static\n\tnexthop via 10.9.0.2 dev d0", 6) + \
        mgmt.parse_ip_route("::/0 via 3fff:172:31:99::1 dev eth0", 6)
    docker, other = mgmt.classify_linux(rs, m_of())
    assert [r.line for r in docker] == ["default via 172.31.99.1 dev eth0", "::/0 via 3fff:172:31:99::1 dev eth0"]
    assert other == []


def test_classify_linux_keeps_order():
    rs = mgmt.parse_ip_route("default via 172.31.99.1 dev eth0\n10.1.0.0/16 via 172.31.99.1 dev eth0\n"
                             "10.2.0.0/16 dev eth0 proto static", 4)
    docker, other = mgmt.classify_linux(rs, m_of())
    assert [r.line for r in other] == ["10.1.0.0/16 via 172.31.99.1 dev eth0", "10.2.0.0/16 dev eth0 proto static"]


# ------------------------------------------------------------------------------------------- _ip, the helper

def test_ip_in_the_container_exact():
    lab = Rec()
    m = mgmt.Mgmt("r1", "clab")
    assert mgmt._ip(lab, m, ["-4", "route", "show"])[0] == 0
    assert lab.timeouts == [("r1", "ip", 30)] and m.via == "container"


@pytest.mark.parametrize("rc,err,helper", [
    (126, "", True), (127, "", True),
    (1, 'exec: "ip": executable file not found in $PATH', True),
    (1, "sh: ip: No such file or directory", True),
    (1, "ip: not found in $PATH", True),
    (0, "executable file not found", False),          # rc 0: whatever it printed, ip ran
    (2, "RTNETLINK answers: Invalid argument", False),
    (125, "", False),
])
def test_ip_falls_back_to_the_helper_only_when_ip_is_missing(rc, err, helper):
    seen = []

    class L(RouteLab):
        def exec_root(self, node, cmd, timeout=60):
            return ExecResult(cmd, rc, "", err)

        def netns_exec(self, node, cmd, timeout=60):
            seen.append((node, tuple(cmd), timeout))
            return ExecResult(cmd, 0, "from helper", "")
    m = mgmt.Mgmt("r1", "clab")
    out = mgmt._ip(L(), m, ["-4", "route", "show"])
    if helper:
        assert out == (0, "from helper", "") and m.via == "helper"
        assert seen == [("r1", ("ip", "-4", "route", "show"), 120)]
    else:
        assert out == (rc, "", err) and m.via == "container" and seen == []


def test_ip_stdout_counts_for_the_missing_ip_test():
    class L(RouteLab):
        def exec_root(self, node, cmd, timeout=60):
            return ExecResult(cmd, 1, "executable file not found", "")

        def netns_exec(self, node, cmd, timeout=60):
            return ExecResult(cmd, 0, "ok", "")
    m = mgmt.Mgmt("r1", "clab")
    assert mgmt._ip(L(), m, ["x"]) == (0, "ok", "") and m.via == "helper"


def test_the_helper_is_used_directly_once_chosen_and_its_answer_returned():
    lab = NoIpLab()
    m = mgmt.Mgmt("r1", "clab", via="helper")
    lab.netns_exec = lambda node, cmd, timeout=60: ExecResult(cmd, 3, "o", "e")
    assert mgmt._ip(lab, m, ["-4", "route", "show"]) == (3, "o", "e") and lab.calls == []


def test_a_helper_that_cant_start_exact():
    for err, out in ((LONG, "ignored"), ("", "  out-text  ")):
        lab = NoIpLab()
        lab.netns_exec = lambda node, cmd, timeout=60, e=err, o=out: ExecResult(cmd, 125, o, e)
        with pytest.raises(LabError) as e:
            mgmt._ip(lab, mgmt.Mgmt("r1", "clab"), ["-4"])
        shown = LONG[-300:] if err else "out-text"
        assert str(e.value) == (f"r1 has no `ip`, and the helper that reads its routes from outside couldn't start: "
                                f"{shown}. On a host without registry access, run `docker pull {NETNS_HELPER_IMAGE}` "
                                "first")


# ------------------------------------------------------------------------------------------- _scan_linux

def test_scan_linux_commands_exact():
    lab = RouteLab()
    m = m_of()
    rs = mgmt._scan_linux(lab, m)
    assert [c for _, c in lab.calls] == [("ip", "-4", "route", "show", "table", "all"),
                                          ("ip", "-6", "route", "show", "table", "all")]
    assert [r.family for r in rs] == [4] * 7 + [6] * 6


def test_scan_linux_main_table_mode_and_fallback_exact():
    lab = RouteLab()
    m = m_of()
    m.tables = "main"
    mgmt._scan_linux(lab, m)
    assert [c for _, c in lab.calls] == [("ip", "-4", "route", "show"), ("ip", "-6", "route", "show")]
    for msg in ("ip: invalid argument 'all'", "Unknown table", "Usage: ip route"):
        lab = RouteLab(fail={"-4 route show table all": 1})
        lab.fail_msg = msg
        real = lab.exec_root
        lab.exec_root = lambda node, cmd, timeout=60, msg=msg, real=real: (
            ExecResult(cmd, 1, "", msg) if cmd[1:] == ["-4", "route", "show", "table", "all"] else real(node, cmd, timeout))
        m = m_of()
        mgmt._scan_linux(lab, m)
        assert m.tables == "main"
        assert [c for _, c in lab.calls] == [("ip", "-4", "route", "show"), ("ip", "-6", "route", "show")]


def test_scan_linux_no_fallback_for_other_errors_or_ipv6():
    lab = RouteLab()
    real = lab.exec_root
    lab.exec_root = lambda node, cmd, timeout=60: (ExecResult(cmd, 1, "", "RTNETLINK answers: Operation not permitted")
                                                   if "table" in cmd else real(node, cmd, timeout))
    m = m_of()
    with pytest.raises(LabError) as e:
        mgmt._scan_linux(lab, m)
    assert m.tables == "all"
    assert str(e.value) == ("r1: its routes can't be read (`ip -4 route show` rc=1: RTNETLINK answers: Operation not "
                            "permitted), so its route out over the management network can't be removed. Give the node "
                            "iproute2 (or busybox `ip`)")
    lab = RouteLab()
    lab.exec_root = lambda node, cmd, timeout=60: (ExecResult(cmd, 1, "", "ip: invalid argument 'all'")
                                                   if cmd[1] == "-6" else real(node, cmd, timeout))
    with pytest.raises(LabError, match=r"`ip -6 route show` rc=1: ip: invalid argument 'all'"):
        mgmt._scan_linux(lab, m_of())


def test_scan_linux_a_failed_fallback_is_the_first_error():
    lab = RouteLab()
    lab.exec_root = lambda node, cmd, timeout=60: ExecResult(cmd, 1, "", "ip: invalid argument 'all'" if "table" in cmd
                                                             else "other failure")
    m = m_of()
    with pytest.raises(LabError, match=r"rc=1: ip: invalid argument 'all'\)"):
        mgmt._scan_linux(lab, m)
    assert m.tables == "all"


def test_scan_linux_error_text_from_stdout_long_or_empty():
    for out, shown in ((LONG, LONG[-200:]), ("", "no output")):
        lab = RouteLab()
        lab.exec_root = lambda node, cmd, timeout=60, o=out: ExecResult(cmd, 5, o, "")
        with pytest.raises(LabError) as e:
            mgmt._scan_linux(lab, m_of())
        assert f"(`ip -4 route show` rc=5: {shown}), so" in str(e.value)


def test_scan_linux_ipv6_absent_only_for_the_ipv6_read():
    lab = RouteLab()
    real = lab.exec_root
    lab.exec_root = lambda node, cmd, timeout=60: (ExecResult(cmd, 2, "Address family not supported by protocol", "")
                                                   if cmd[1] == "-6" else real(node, cmd, timeout))
    assert {r.family for r in mgmt._scan_linux(lab, m_of())} == {4}
    lab = RouteLab()
    lab.exec_root = lambda node, cmd, timeout=60: ExecResult(cmd, 2, "", "Address family not supported by protocol")
    with pytest.raises(LabError, match="`ip -4 route show` rc=2"):
        mgmt._scan_linux(lab, m_of())


# ------------------------------------------------------------------------------------------- devices, offending

def test_linux_devices_exact():
    m = m_of(devices=())
    mgmt._linux_devices(RouteLab(v4="172.31.99.0/24 dev mgmt9 proto kernel\n172.31.99.0/24 via 1.1.1.1 dev x\n"
                                    "10.0.0.0/8 dev eth1 proto kernel\n172.31.99.0/24 dev y proto static",
                                 v6="3fff:172:31:99::/64 dev eth0 metric 256"), m)
    assert m.devices == {"mgmt9", "eth0"}


def test_linux_devices_none_needed_without_subnets():
    m = mgmt.Mgmt("r1", "clab")
    mgmt._linux_devices(RouteLab(v4="", v6=""), m)
    assert m.devices == set()


def test_linux_devices_error_exact():
    m = m_of(devices=())
    with pytest.raises(LabError) as e:
        mgmt._linux_devices(RouteLab(v4="", v6=""), m)
    assert str(e.value) == ("r1: no interface holds its management subnet (172.31.99.0/24, 3fff:172:31:99::/64), so its "
                            "management device can't be told apart from a lab interface")


def test_offending_exact():
    rs = mgmt.parse_ip_route("\n".join(f"10.{i}.0.0/16 via 172.31.99.1 dev eth0" for i in range(7)), 4)
    assert mgmt._offending("r1", rs + ["text-route"], "when") == (
        "r1 has a route out over the management network (when): " + "; ".join(r.line for r in rs[:5])
        + ". A ping over it leaves the lab (Docker reaches beyond it), so the run can't show what the lab does. "
        "Remove it (a route via the management interface is not a lab path)")
    assert mgmt._offending("r1", ["a", "b"], "w").startswith("r1 has a route out over the management network (w): a; b.")


# ------------------------------------------------------------------------------------------- prepare_linux

def test_prepare_linux_exact():
    lab = Rec(nodes=["r1"])
    lab.tables["r1"][4] = FRR_V4 + "\n172.31.99.0/24 dev eth9 proto kernel"     # two management devices
    m = m_of(devices=())
    logs: list[str] = []
    mgmt.prepare_linux(lab, m, logs.append)
    assert m.kind == "linux" and m.devices == {"eth0", "eth9"}
    assert [c for _, c in lab.calls if c[0] == "sysctl"] == [
        ("sysctl", "-w", "net.ipv6.conf.eth0.accept_ra=0"), ("sysctl", "-w", "net.ipv6.conf.eth9.accept_ra=0")]
    assert [t for t in lab.timeouts if t[1] == "sysctl"] == [("r1", "sysctl", 30), ("r1", "sysctl", 30)]
    assert logs == [f"note: r1: accept_ra=0 on {d} not set (sysctl: error setting key: Read-only file system); a "
                    "re-added default is caught before every ping" for d in ("eth0", "eth9")]
    assert m.removed == ["default via 172.31.99.1 dev eth0", "default via 3fff:172:31:99::1 dev eth0 metric 1024 "
                                                              "pref medium"]
    assert ("r1", ("ip", "-6", "route", "del", "default", "via", GW6, "dev", "eth0")) in lab.calls


def test_prepare_linux_sysctl_messages():
    lab = Rec()
    lab.sysctl = ExecResult([], 0, "", "")
    logs: list[str] = []
    mgmt.prepare_linux(lab, m_of(devices=()), logs.append)
    assert logs == []
    lab = Rec()
    lab.sysctl = ExecResult([], 1, "  " + LONG + "  ", "")
    logs = []
    mgmt.prepare_linux(lab, m_of(devices=()), logs.append)
    assert logs == [f"note: r1: accept_ra=0 on eth0 not set ({LONG[-120:]}); a re-added default is caught before every "
                    "ping"]


def test_prepare_linux_helper_note_once():
    lab = NoIpLab()
    lab.tables["r1"][4] = BB_V4 + "\n172.31.99.0/24 dev eth9 scope link"
    logs: list[str] = []
    mgmt.prepare_linux(lab, m_of(devices=()), logs.append)
    assert logs == ["note: r1: accept_ra not set (no sysctl in the image); a re-added default is caught before every "
                    "ping and phase"]


def test_prepare_linux_other_route_exact():
    lab = RouteLab(v4=FRR_V4 + "\n10.77.0.0/16 via 172.31.99.1 dev eth0 proto static")
    with pytest.raises(ManagementPathError) as e:
        mgmt.prepare_linux(lab, m_of(devices=()), lambda _: None)
    assert str(e.value) == mgmt._offending("r1", mgmt.parse_ip_route("10.77.0.0/16 via 172.31.99.1 dev eth0 proto "
                                                                     "static", 4), "before the checks")
    assert not any("del" in c for _, c in lab.calls)


def test_prepare_linux_failed_delete_exact():
    for err, out, shown in ((LONG, "x", LONG[-200:]), ("", " o ", "o")):
        lab = RouteLab()
        real = lab.exec_root
        lab.exec_root = lambda node, cmd, timeout=60, e=err, o=out, real=real: (
            ExecResult(cmd, 2, o, e) if "del" in cmd else real(node, cmd, timeout))
        with pytest.raises(ManagementPathError) as e:
            mgmt.prepare_linux(lab, m_of(devices=()), lambda _: None)
        assert str(e.value) == (f"r1: Docker's default route (default via 172.31.99.1 dev eth0) could not be deleted "
                                f"(rc=2: {shown}); the run won't ping over it")


def test_prepare_linux_rechecks_after_the_delete_exact():
    lab = RouteLab()
    real = lab.exec_root
    lab.exec_root = lambda node, cmd, timeout=60: (ExecResult(cmd, 0, "", "") if "del" in cmd
                                                   else real(node, cmd, timeout))
    with pytest.raises(ManagementPathError) as e:
        mgmt.prepare_linux(lab, m_of(devices=()), lambda _: None)
    assert "(after deleting Docker's default route): default via 172.31.99.1 dev eth0; default via" in str(e.value)


def test_check_linux_exact():
    lab = RouteLab(v4="default via 172.31.99.1 dev eth0\n10.7.0.0/16 via 172.31.99.1 dev eth0", v6="")
    with pytest.raises(ManagementPathError) as e:
        mgmt.check_linux(lab, m_of(), "W")
    assert str(e.value).startswith("r1 has a route out over the management network (W): default via 172.31.99.1 dev "
                                   "eth0; 10.7.0.0/16 via 172.31.99.1 dev eth0.")
    mgmt.check_linux(RouteLab(v4="10.7.0.0/16 via 10.0.0.2 dev eth1", v6=""), m_of(), "W")


# ------------------------------------------------------------------------------------------- cEOS

def test_eos_cli_exact():
    sent = []

    class L(RouteLab):
        def exec(self, node, cmd, timeout=60, input=None):
            sent.append((node, cmd, timeout))
            return ExecResult(cmd, 0, "out", "")
    assert mgmt._eos(L(), "e1", "show x") == "out"
    assert sent == [("e1", ["Cli", "-p", "15", "-c", "show x"], 60)]
    for err, out, shown in ((LONG, "x", LONG[-200:]), ("", " o ", "o")):
        class F(RouteLab):
            def exec(self, node, cmd, timeout=60, input=None, e=err, o=out):
                return ExecResult(cmd, 3, o, e)
        with pytest.raises(LabError) as e:
            mgmt._eos(F(), "e1", "show x")
        assert str(e.value) == f"e1: `show x` failed (rc=3): {shown}"


def test_classify_eos_errors_exact():
    for fam, cmd in ((4, "show ip route"), (6, "show ipv6 route")):
        with pytest.raises(LabError) as e:
            mgmt.classify_eos("  " + "z" * 200 + "  ", fam, m_of())
        assert str(e.value) == f"r1: `{cmd} vrf all | json` printed {'z' * 150!r}, so its routes over Management0 can't be read"
    for bad in ('{"vrfs": []}', '{"x": 1}', "[]", "null"):
        with pytest.raises(LabError, match="can't be read"):
            mgmt.classify_eos(bad, 4, m_of())
    with pytest.raises(LabError) as e:
        mgmt.classify_eos(json.dumps({"vrfs": {"RED": None}}), 4, m_of())
    assert str(e.value) == "r1: VRF RED in `show ip route vrf all | json` has no route table"
    with pytest.raises(LabError) as e:
        mgmt.classify_eos(json.dumps({"vrfs": {"RED": {"routes": {"10.0.0.0/8": ["q" * 150]}}}}), 4, m_of())
    assert str(e.value) == "r1: route 10.0.0.0/8 (vrf RED) reads " + str(["q" * 150])[:100]
    with pytest.raises(LabError, match="reads"):
        mgmt.classify_eos(json.dumps({"vrfs": {"RED": {"routes": {"10.0.0.0/8": {"vias": "x"}}}}}), 4, m_of())


def _eos_routes(**routes):
    return json.dumps({"vrfs": {"default": {"routes": routes}}})


def test_classify_eos_every_rule():
    m = m_of()
    via = lambda gw, i="Management0": {"nexthopAddr": gw, "interface": i}   # noqa: E731
    text = _eos_routes(**{
        "0.0.0.0/0": {"routeType": "static", "vias": [via(GW4)]},
        "::/0": {"routeType": "static", "vias": [via(GW6)]},
        "172.31.99.0/24": {"routeType": "connected", "vias": [{"interface": "Management0"}]},
        "172.31.0.0/16": {"routeType": "connected", "vias": [{"interface": "Management0"}]},
        "10.0.0.0/8": {"routeType": "static", "vias": [via(GW4)]},
        "10.1.0.0/16": {"routeType": "static", "vias": [via("10.0.0.2", "Ethernet1"), "junk"]},
        "1.0.0.0/8": {"routeType": "static", "vias": [via(GW4, "Management1/1"), via("10.0.0.2", "Ethernet1")]},
        "2.0.0.0/8": {"routeType": "static", "vias": [{"interface": "Management0"}]},
    })
    ours, other = mgmt.classify_eos(text, 4, m)
    assert ours == [("default", "0.0.0.0/0", GW4), ("default", "::/0", GW6)]
    assert other == ["172.31.0.0/16 (vrf default, connected) via Management0",
                     "10.0.0.0/8 (vrf default, static) via 172.31.99.1 Management0",
                     "1.0.0.0/8 (vrf default, static) via 172.31.99.1 Management1/1",
                     "2.0.0.0/8 (vrf default, static) via Management0"]


@pytest.mark.parametrize("route", [
    {"routeType": "bgp", "vias": [{"nexthopAddr": GW4, "interface": "Management0"}]},                 # not static
    {"routeType": "static", "vias": [{"nexthopAddr": "172.31.99.9", "interface": "Management0"}]},    # other gateway
    {"routeType": "static", "vias": [{"interface": "Management0"}]},                                   # no gateway
    {"routeType": "static", "vias": [{"nexthopAddr": GW4, "interface": "Management0"},
                                     {"nexthopAddr": "10.0.0.2", "interface": "Ethernet1"}]},         # ECMP
    {"routeType": "static", "vias": [{"nexthopAddr": GW4, "interface": "Management0"},
                                     {"nexthopAddr": "172.31.99.9", "interface": "Management0"}]},    # two gateways
])
def test_classify_eos_a_default_that_isnt_containerlabs_is_other(route):
    ours, other = mgmt.classify_eos(_eos_routes(**{"0.0.0.0/0": route}), 4, m_of())
    assert ours == [] and len(other) == 1


def test_classify_eos_two_vrfs_and_gateways_sorted():
    text = json.dumps({"vrfs": {"default": {"routes": {"0.0.0.0/0": {"routeType": "static", "vias": [
        {"nexthopAddr": GW4, "interface": "Management0"}]}}},
                                "MGMT": {"routes": {"0.0.0.0/0": {"routeType": "static", "vias": [
        {"nexthopAddr": GW4, "interface": "Management0"}]}}}}})
    assert mgmt.classify_eos(text, 4, m_of())[0] == [("default", "0.0.0.0/0", GW4), ("MGMT", "0.0.0.0/0", GW4)]
    assert mgmt.classify_eos(_eos_routes(), 4, m_of()) == ([], [])


def test_scan_eos_commands_and_sums():
    sent = []
    v4 = _eos_routes(**{"0.0.0.0/0": {"routeType": "static", "vias": [{"nexthopAddr": GW4, "interface": "Management0"}]},
                        "9.0.0.0/8": {"routeType": "static", "vias": [{"nexthopAddr": GW4, "interface": "Management0"}]}})
    v6 = _eos_routes(**{"::/0": {"routeType": "static", "vias": [{"nexthopAddr": GW6, "interface": "Management0"}]},
                        "9::/16": {"routeType": "static", "vias": [{"nexthopAddr": GW6, "interface": "Management0"}]}})

    class L(RouteLab):
        def exec(self, node, cmd, timeout=60, input=None):
            sent.append(cmd[-1])
            return ExecResult(cmd, 0, v6 if "ipv6" in cmd[-1] else v4, "")
    ours, other = mgmt._scan_eos(L(), m_of())
    assert sent == ["show ip route vrf all | json", "show ipv6 route vrf all | json"]
    assert ours == [("default", "0.0.0.0/0", GW4), ("default", "::/0", GW6)]
    assert other == ["9.0.0.0/8 (vrf default, static) via 172.31.99.1 Management0",
                     "9::/16 (vrf default, static) via 3fff:172:31:99::1 Management0"]


def test_eos_config_routes_every_rule():
    m = m_of()
    text = "\n".join([
        "hostname e1", "ip route 0.0.0.0/0 172.31.99.1", "  ipv6 route ::0/0 3fff:172:31:99::1  ",
        "ipv6 route ::/0 3fff:172:31:99::1", "ip route vrf MGMT 0.0.0.0/0 172.31.99.1",
        "ip route 0.0.0.0/0 172.31.99.1 200", "ip route 0.0.0.0/0 Management0", "ip route 10.0.0.0/8 172.31.99.1",
        "ip route 0.0.0.0/0 10.0.12.2", "ip route 10.0.0.0/8 Ethernet1", "ip route 0.0.0.0/0 Management1/1 172.31.99.1",
        "ip routing", "ip route 1.0.0.0/8 172.31.99.9"])
    ours, other = mgmt.eos_config_routes(text, m)
    assert ours == ["ip route 0.0.0.0/0 172.31.99.1", "ipv6 route ::0/0 3fff:172:31:99::1",
                    "ipv6 route ::/0 3fff:172:31:99::1", "ip route vrf MGMT 0.0.0.0/0 172.31.99.1"]
    assert other == ["ip route 0.0.0.0/0 172.31.99.1 200", "ip route 0.0.0.0/0 Management0",
                     "ip route 10.0.0.0/8 172.31.99.1", "ip route 0.0.0.0/0 Management1/1 172.31.99.1"]


def test_eos_key_exact():
    assert mgmt._eos_key("ipv6 route ::0/0 3fff:172:31:99::1") == mgmt._eos_key("ipv6 route ::/0 3fff:172:31:99::1") == (
        "ipv6", "default", ipaddress.ip_network("::/0"), ipaddress.ip_address(GW6))
    assert mgmt._eos_key("ip route vrf M 0.0.0.0/0 172.31.99.1") == (
        "ip", "M", ipaddress.ip_network("0.0.0.0/0"), ipaddress.ip_address(GW4))
    assert mgmt._eos_key("ip route 10.0.0.5/8 172.31.99.1")[2] == ipaddress.ip_network("10.0.0.0/8")


def test_eos_config_reads_the_named_config():
    sent = []

    class L(RouteLab):
        def exec(self, node, cmd, timeout=60, input=None):
            sent.append((node, cmd[-1]))
            return ExecResult(cmd, 0, "cfg", "")
    assert mgmt._eos_config(L(), "e1", "startup") == "cfg"
    assert sent == [("e1", "show startup-config")]


def test_prepare_eos_exact_commands():
    lab = EosLab()
    m = mgmt.Mgmt("r1", "clab", [ipaddress.ip_network("172.31.99.0/24")], [ipaddress.ip_address(GW4),
                                                                           ipaddress.ip_address(GW6)])
    m.removed = ["earlier"]
    mgmt.prepare_eos(lab, m, None, lambda s: pytest.fail("no wait"))
    assert m.kind == "eos" and m.removed == ["earlier", "ip route 0.0.0.0/0 172.31.99.1",
                                             "ipv6 route ::0/0 3fff:172:31:99::1"]


@pytest.mark.parametrize("limit,sleeps", [(4.0, 2), (6.0, 2), (3.0, 1), (0.0, 0)])
def test_prepare_eos_waits_in_3s_steps_up_to_the_limit(monkeypatch, limit, sleeps):
    monkeypatch.setattr(mgmt, "EOS_LOAD_WAIT", limit)
    slept: list = []
    with pytest.raises(ManagementPathError) as e:
        mgmt.prepare_eos(EosLab(load_after=10 ** 6), m_of(), None, slept.append)
    assert slept == [3.0] * sleeps
    assert str(e.value) == (f"r1: its startup config has containerlab's management route (ip route 0.0.0.0/0 "
                            f"172.31.99.1; ipv6 route ::0/0 3fff:172:31:99::1) but the running config still doesn't "
                            f"after {limit:g}s, so it can't be removed before the checks")


def test_prepare_eos_reports_only_the_lines_still_missing():
    lab = EosLab(running="hostname e1\nip route 0.0.0.0/0 172.31.99.1\n")
    with pytest.raises(ManagementPathError) as e:
        mgmt.prepare_eos(lab, m_of(), None, lambda s: None)
    assert "management route (ipv6 route ::0/0 3fff:172:31:99::1) but" in str(e.value)


@pytest.mark.parametrize("running,startup,shown", [
    ("ip route 9.0.0.0/8 172.31.99.1\n", "", "9.0.0.0/8"),
    ("", "ip route 8.0.0.0/8 172.31.99.1\n", "8.0.0.0/8"),
])
def test_prepare_eos_another_static_in_either_config_exact(running, startup, shown):
    lab = EosLab(running=running, startup=startup)
    with pytest.raises(ManagementPathError) as e:
        mgmt.prepare_eos(lab, m_of(), None, lambda s: None)
    assert str(e.value) == mgmt._offending("r1", [f"ip route {shown} 172.31.99.1"], "in its config")
    assert lab.sent == []


def test_prepare_eos_lists_both_configs_static_routes_sorted_once():
    lab = EosLab(running="ip route 9.0.0.0/8 172.31.99.1\nip route 7.0.0.0/8 172.31.99.1\n",
                 startup="ip route 9.0.0.0/8 172.31.99.1\nip route 8.0.0.0/8 172.31.99.1\n")
    with pytest.raises(ManagementPathError) as e:
        mgmt.prepare_eos(lab, m_of(), None, lambda s: None)
    assert ": ip route 7.0.0.0/8 172.31.99.1; ip route 8.0.0.0/8 172.31.99.1; ip route 9.0.0.0/8 172.31.99.1." in \
        str(e.value)


def test_prepare_eos_rechecks_exact():
    class Stuck(EosLab):
        def exec(self, node, cmd, timeout=60, input=None):
            if cmd[-1].startswith("configure"):
                self.sent.append(cmd[-1])
                return ExecResult(cmd, 0, "", "")          # accepted, changed nothing
            return super().exec(node, cmd, timeout, input)
    with pytest.raises(ManagementPathError) as e:
        mgmt.prepare_eos(Stuck(), m_of(), None, lambda s: None)
    assert "(after deleting containerlab's default route): ip route 0.0.0.0/0 172.31.99.1; ipv6 route ::0/0" in \
        str(e.value)


def test_check_eos_lists_config_and_table_exact():
    lab = EosLab()
    with pytest.raises(ManagementPathError) as e:
        mgmt.check_eos(lab, m_of(), "W", repair=False)
    assert str(e.value).startswith(
        "r1 has a route out over the management network (W): ip route 0.0.0.0/0 172.31.99.1; ipv6 route ::0/0 "
        "3fff:172:31:99::1; 0.0.0.0/0 (vrf default) via 172.31.99.1; ::/0 (vrf default) via 3fff:172:31:99::1.")
    mgmt.check_eos(EosLab(running="hostname e1\n", startup=""), m_of(), "W")


# ------------------------------------------------------------------------------------------- Junos, prepare, describe

def test_check_junos_reads_every_vrf_sorted_and_says_so_exact(monkeypatch):
    seen = []

    class D:
        def __init__(self, lab, node):
            seen.append(("init", node))

        def management_routes(self, vrf):
            seen.append(vrf)
            return [f"r-{vrf}"] if vrf != "a" else []
    import netdryrun.drivers.junos as junos
    monkeypatch.setattr(junos, "JunosDriver", D)
    m = mgmt.Mgmt("j1", "clab", vrfs={"default", "a", "RED"})
    with pytest.raises(ManagementPathError) as e:
        mgmt.check_junos(RouteLab(), m, "W")
    assert seen == [("init", "j1"), "RED", "a", "default"]
    assert str(e.value) == mgmt._offending("j1", ["r-RED", "r-default"], "W") + (
        " (on Junos: delete it, or keep management in the mgmt_junos instance)")
    seen.clear()
    m.vrfs = {"a"}
    mgmt.check_junos(RouteLab(), m, "W")


def test_prepare_junos_vrfs_and_when_exact(monkeypatch):
    got = []
    monkeypatch.setattr(mgmt, "check_junos", lambda lab, m, when: got.append((m.kind, set(m.vrfs), when)))
    monkeypatch.setattr(mgmt, "_junos_answers", lambda lab, node: got.append(("probe", node)))
    lab = RouteLab(nodes=["j1", "r9"], kinds={"j1": ("juniper_cjunosevolved", "cj")})
    checks = [chk("route", "a", node="j1", prefix="10.0.0.0/8", vrf="RED"), chk("route", "b", node="j1", prefix="1.0.0.0/8"),
              chk("route", "c", node="r9", prefix="1.0.0.0/8", vrf="BLUE")]
    logs: list[str] = []
    mgmt.prepare(lab, checks, log=logs.append)
    assert got == [("probe", "j1"), ("junos", {"default", "RED"}, "before the checks")]
    assert logs[0] == "j1: management default route none"


def test_prepare_logs_exact_and_skips_only_non_containers():
    lab = RouteLab(nodes=["a-br", "r1", "s1"], kinds={"a-br": ("bridge", ""), "s1": ("nokia_srlinux", "srl")})
    logs: list[str] = []
    state = mgmt.prepare(lab, [], log=logs.append)
    assert sorted(state) == ["r1", "s1"]
    assert logs == ["note: r1: accept_ra=0 on eth0 not set (sysctl: error setting key: Read-only file system); a "
                    "re-added default is caught before every ping",
                    "r1: management default route removed (default via 172.31.99.1 dev eth0; default via "
                    "3fff:172:31:99::1 dev eth0 metric 1024 pref medium)",
                    "s1: management default route not applicable (nokia_srlinux)"]
    lab = RouteLab(v4="", v6="")
    lab.inspect = {"r1": {"HostConfig": {"NetworkMode": "clab"}, "NetworkSettings": {"Networks": {}}}}
    logs = []
    mgmt.prepare(lab, [], log=logs.append)
    assert logs == ["r1: management default route none"]


def test_prepare_skips_host_container_and_none_and_continues():
    shared = {"HostConfig": {"NetworkMode": "container:clab-t-z1"}, "NetworkSettings": {"Networks": {}}}
    host = {"HostConfig": {"NetworkMode": "host"}, "NetworkSettings": {"Networks": {}}}
    none = {"HostConfig": {"NetworkMode": "none"}, "NetworkSettings": {"Networks": {}}}
    lab = RouteLab(nodes=["a", "b", "c", "z1"], inspect={"a": host, "b": shared, "c": none})
    logs: list[str] = []
    state = mgmt.prepare(lab, [], log=logs.append)
    assert [n for n, _ in lab.calls if _[0] == "ip"] and {n for n, _ in lab.calls} == {"z1"}
    assert len(logs) == 2 and logs[0].startswith("note: z1:") and logs[1].startswith("z1: management default route "
                                                                                    "removed")
    assert state["z1"].kind == "linux" and lab.management is state


def test_prepare_passes_the_given_sleep(monkeypatch):
    got = []
    monkeypatch.setattr(mgmt, "prepare_eos", lambda lab, m, log, sleep: got.append(sleep))
    monkeypatch.setattr(mgmt, "_eos_config", lambda lab, node, which: "")   # the readiness read answers at once
    s = lambda x: None   # noqa: E731
    mgmt.prepare(RouteLab(kinds={"r1": ("ceos", "c")}), [], sleep=s)
    mgmt.prepare(RouteLab(kinds={"r1": ("arista_ceos", "c")}), [])
    import time
    assert got == [s, time.sleep]


def test_describe_exact():
    m = mgmt.Mgmt("r1", "clab", kind="linux")
    assert mgmt.describe(m, "linux") == "none"
    m.removed = ["a", "b"]
    assert mgmt.describe(m, "linux") == "removed: a; b"
    m.via = "helper"
    assert mgmt.describe(m, "linux") == "removed: a; b (read from outside: no `ip` in the image)"
    assert mgmt.describe(mgmt.Mgmt("r1", "clab", kind="eos", via="helper"), "x") == \
        "none (read from outside: no `ip` in the image)"
    assert mgmt.describe(mgmt.Mgmt("r1", "clab"), "srl") == "not applicable (srl)"
    assert mgmt.describe(mgmt.Mgmt("r1", "host", kind="linux"), "linux") == \
        "not touched (network-mode host: the Docker host's namespace)"
    assert mgmt.describe(mgmt.Mgmt("r1", "container:abc", kind="linux"), "linux") == "not touched (shares abc's namespace)"


# ------------------------------------------------------------------------------------------- owner, cover, refuse

def test_owner_by_name_container_or_id_prefix():
    lab = RouteLab(nodes=["r1", "r2"])
    state = {"r1": mgmt.Mgmt("r1", "clab", cid="0123456789"), "r2": mgmt.Mgmt("r2", "clab", cid="")}
    for target in ("r1", "clab-t-r1", "0123", "0123456789"):
        assert mgmt._owner(lab, state, mgmt.Mgmt("h", f"container:{target}")) is state["r1"], target
    assert mgmt._owner(lab, state, mgmt.Mgmt("h", "container:r2")) is state["r2"]
    for target in ("", "9999", "r3"):
        assert mgmt._owner(lab, state, mgmt.Mgmt("h", f"container:{target}")) is None, target


def test_covering_exact():
    lab = RouteLab(nodes=["r1", "h1"])
    r1 = mgmt.Mgmt("r1", "clab", kind="linux")
    h1 = mgmt.Mgmt("h1", "container:r1")
    state = {"r1": r1, "h1": h1}
    assert mgmt.covering(lab, state, "r1") is r1 and mgmt.covering(lab, state, "h1") is r1
    assert mgmt.covering(lab, state, "zz") is None


@pytest.mark.parametrize("driver,kind,ok", [
    ("frr", "linux", True), ("sonic", "linux", True), ("eos", "eos", True), ("junos", "junos", True),
    ("frr", "eos", False), ("eos", "linux", False), ("junos", "", False), ("sonic", "", False),
    ("srlinux", "", True), ("nxos", "", True), ("routeros", "", True),
])
def test_require_covered_by_driver(driver, kind, ok):
    lab = RouteLab(kinds={"r1": ("weird", "img")})
    state = {"r1": mgmt.Mgmt("r1", "clab", kind=kind)}
    if ok:
        mgmt.require_covered(lab, state, "r1", driver)
    else:
        with pytest.raises(LabError) as e:
            mgmt.require_covered(lab, state, "r1", driver)
        assert str(e.value) == (f"r1 is read with the {driver} driver, but its kind (weird) is not one whose management "
                                "default route Netdryrun removes, so a ping from it could leave the lab over Docker's "
                                "network. Use the kind containerlab documents for that image")


def test_require_covered_unknown_node_and_lab_without_docker():
    with pytest.raises(LabError, match=r"its kind \(\?\)"):
        mgmt.require_covered(RouteLab(), {}, "zz", "frr")

    class NoDocker:
        nodes = {}
    mgmt.require_covered(NoDocker(), {}, "zz", "frr")


def test_refuse_checks_namespace_messages_exact():
    lab = RouteLab(nodes=["h1", "h2"])
    state = {"h1": mgmt.Mgmt("h1", "host"), "h2": mgmt.Mgmt("h2", "container:nowhere")}
    with pytest.raises(LabError) as e:
        mgmt.refuse_checks(lab, state, [chk("route", "rc", node="h1", prefix="1.0.0.0/8")])
    assert str(e.value) == ("check 'rc' reads h1, which runs in the Docker host's network namespace (network-mode: "
                            "host): it would test the host, not the lab")
    with pytest.raises(LabError) as e:
        mgmt.refuse_checks(lab, state, [chk("route", "rc", node="h2", prefix="1.0.0.0/8")])
    assert str(e.value) == ("check 'rc' reads h2, which runs in the namespace of nowhere, which is not a lab node: it "
                            "would test the host, not the lab")


def test_refuse_checks_goes_through_every_check_and_key():
    lab = RouteLab()
    state = {"r1": m_of()}
    later = [chk("route", "r", prefix="1.0.0.0/8"), chk("ping", "p0", target="10.0.0.9"),
             chk("ping", "p1", target="10.0.0.9", source="172.31.99.2")]
    with pytest.raises(LabError) as e:
        mgmt.refuse_checks(lab, state, later)
    assert str(e.value) == ("check 'p1': source 172.31.99.2 is in the lab's management network 172.31.99.0/24: that "
                            "path is Docker's, not the lab's, so the ping says nothing about the network")
    with pytest.raises(LabError) as e:
        mgmt.refuse_checks(lab, state, [chk("ping", "p", target="10.0.0.9", source="fe80::1%eth0")])
    assert str(e.value) == "check 'p': source fe80::1%eth0 is scoped to the management interface eth0"


@pytest.mark.parametrize("scope,devices,refused", [
    ("eth0", (), True), ("mgmt0", (), True), ("Management0", (), True), ("Management1/1", (), True),
    ("eth9", ("eth9",), True), ("eth1", ("eth9",), False), ("Ethernet1", (), False), ("eth00", (), False),
])
def test_refuse_checks_scopes(scope, devices, refused):
    m = m_of(devices=devices)
    call = lambda: mgmt.refuse_checks(RouteLab(), {"r1": m}, [chk("ping", "p", target=f"fe80::2%{scope}")])  # noqa
    if refused:
        with pytest.raises(LabError, match=f"scoped to the management interface {scope}"):
            call()
    else:
        call()


def test_refuse_checks_a_scope_on_a_node_without_state_is_not_read():
    mgmt.refuse_checks(RouteLab(), {}, [chk("ping", "p", target="fe80::2%eth0")])


# ------------------------------------------------------------------------------------------- _check, recheck, node

def test_check_dispatches_by_kind(monkeypatch):
    got = []
    for k in ("linux", "eos", "junos"):
        monkeypatch.setattr(mgmt, f"check_{k}", lambda lab, m, when, k=k: got.append((k, m.node, when)))
    for k in ("linux", "eos", "junos", ""):
        mgmt._check(RouteLab(), mgmt.Mgmt("n", "clab", kind=k), "W")
    assert got == [("linux", "n", "W"), ("eos", "n", "W"), ("junos", "n", "W")]


def test_check_wraps_every_other_failure_exact(monkeypatch):
    monkeypatch.setattr(mgmt, "check_linux", lambda lab, m, when: (_ for _ in ()).throw(ValueError("bad via")))
    with pytest.raises(ManagementPathError) as e:
        mgmt._check(RouteLab(), mgmt.Mgmt("n", "clab", kind="linux"), "before X")
    assert str(e.value) == "n: its routes could not be read before X: bad via"
    assert isinstance(e.value.__cause__, ValueError)
    original = ManagementPathError("keep me")
    monkeypatch.setattr(mgmt, "check_linux", lambda lab, m, when: (_ for _ in ()).throw(original))
    with pytest.raises(ManagementPathError) as e:
        mgmt._check(RouteLab(), mgmt.Mgmt("n", "clab", kind="linux"), "W")
    assert e.value is original


def test_recheck_and_check_node_exact(monkeypatch):
    got = []
    monkeypatch.setattr(mgmt, "_check", lambda lab, m, when: got.append((m.node, when)))
    lab = RouteLab(nodes=["a", "b"])
    lab.management = {"a": mgmt.Mgmt("a", "clab"), "b": mgmt.Mgmt("b", "clab")}
    mgmt.recheck(lab, "W")
    mgmt.check_node(lab, "b", "P")
    mgmt.check_node(lab, "zz", "P")
    assert got == [("a", "W"), ("b", "W"), ("b", "P")]
    lab.management["h"] = mgmt.Mgmt("h", "container:nowhere")
    mgmt.check_node(lab, "h", "P")
    assert got[-1] == ("b", "P")
    mgmt.recheck(Node("x", "c", "linux", "i"), "W")        # an object without state: nothing to read



# ------------------------------------------------------------------------------------------- readiness (live 2026-11-08)

class Flaky:
    """A first read that fails `fails` times with a run error, then answers."""

    def __init__(self, fails, exc=None):
        self.n, self.fails = 0, fails
        self.exc = exc or LabError("j1: `show route` timed out")

    def __call__(self):
        self.n += 1
        if self.n <= self.fails:
            raise self.exc


def test_a_booting_node_is_waited_for_in_5s_steps(monkeypatch):
    monkeypatch.setattr(mgmt, "READY_BUDGET", 300.0)
    slept: list = []
    read = Flaky(3)
    mgmt._await_answer(read, "j1", slept.append)
    assert slept == [5.0, 5.0, 5.0] and read.n == 4


def test_a_driver_error_is_waited_for_too(monkeypatch):
    from netdryrun.drivers.base import DriverError
    monkeypatch.setattr(mgmt, "READY_BUDGET", 300.0)
    slept: list = []
    mgmt._await_answer(Flaky(1, DriverError("cli not up")), "j1", slept.append)
    assert slept == [5.0]


def test_a_node_that_never_answers_is_a_run_error_after_the_budget(monkeypatch):
    monkeypatch.setattr(mgmt, "READY_BUDGET", 12.0)
    slept: list = []
    read = Flaky(10 ** 6)
    with pytest.raises(LabError) as e:
        mgmt._await_answer(read, "j1", slept.append, clock=lambda: 0.0)
    assert slept == [5.0, 5.0, 5.0] and read.n == 4
    assert str(e.value) == ("j1: `show route` timed out (no answer in 15s after setup, a budget of 12s, so j1's route "
                            "out over the management network can't be checked before the checks)")


def test_the_budget_is_on_the_clock_when_each_read_takes_time(monkeypatch):
    """Adversary on the readiness diff: a `show route` that times out takes 60 s itself; 300 s is 300 s of clock."""
    monkeypatch.setattr(mgmt, "READY_BUDGET", 300.0)
    now = [0.0]
    slept: list = []

    def slow():
        now[0] += 60.0
        raise LabError("j1: `show route` timed out")
    with pytest.raises(LabError, match=r"no answer in 300s after setup, a budget of 300s"):
        mgmt._await_answer(slow, "j1", slept.append, clock=lambda: now[0])
    assert slept == [5.0] * 4                     # reads at 60, 120, 180, 240, 300 s of clock: four waits between


def test_a_missing_instance_is_never_waited_for(monkeypatch):
    from netdryrun.drivers.base import NoSuchInstance
    monkeypatch.setattr(mgmt, "READY_BUDGET", 300.0)
    with pytest.raises(NoSuchInstance):
        mgmt._await_answer(Flaky(1, NoSuchInstance("no RED")), "j1", lambda s: pytest.fail("must not wait"))


def test_an_explicit_budget_wins(monkeypatch):
    monkeypatch.setattr(mgmt, "READY_BUDGET", 300.0)
    slept: list = []
    with pytest.raises(LabError):
        mgmt._await_answer(Flaky(10 ** 6), "j1", slept.append, budget=5.0)
    assert slept == [5.0]


def test_a_route_out_is_never_retried(monkeypatch):
    monkeypatch.setattr(mgmt, "READY_BUDGET", 300.0)
    read = Flaky(1, ManagementPathError("route out"))
    with pytest.raises(ManagementPathError):
        mgmt._await_answer(read, "j1", lambda s: pytest.fail("must not wait"))
    assert read.n == 1


def test_any_other_exception_is_not_swallowed(monkeypatch):
    monkeypatch.setattr(mgmt, "READY_BUDGET", 300.0)
    with pytest.raises(KeyError):
        mgmt._await_answer(Flaky(1, KeyError("x")), "j1", lambda s: pytest.fail("must not wait"))


def test_junos_prepare_waits_for_its_default_instance_then_checks_once(monkeypatch):
    monkeypatch.setattr(mgmt, "READY_BUDGET", 300.0)
    probes, checks = [], []

    def probe(lab, node):
        probes.append(node)
        if len(probes) < 3:
            raise LabError("j1: `show route` timed out")
    monkeypatch.setattr(mgmt, "_junos_answers", probe)
    monkeypatch.setattr(mgmt, "check_junos", lambda lab, m, when: checks.append((m.node, set(m.vrfs), when)))
    slept: list = []
    lab = RouteLab(nodes=["j1"], kinds={"j1": ("juniper_cjunosevolved", "cj")})
    mgmt.prepare(lab, [chk("route", "a", node="j1", prefix="10.0.0.0/8", vrf="RED")], sleep=slept.append)
    assert slept == [5.0, 5.0] and probes == ["j1"] * 3
    assert checks == [("j1", {"default", "RED"}, "before the checks")]       # every instance read once, unretried


def test_a_default_instance_read_as_missing_is_not_ready_yet(monkeypatch):
    """Verifier on the readiness fixes: a booting rpd can make the default instance read as missing; it always
    exists, so the probe retries instead of failing at boot."""
    from netdryrun.drivers import junos
    from netdryrun.drivers.base import DriverError, NoSuchInstance

    def missing(self, vrf):
        raise NoSuchInstance("routing-instance 'default' does not exist on j1")
    monkeypatch.setattr(junos.JunosDriver, "management_routes", missing)
    with pytest.raises(DriverError, match="j1: its default instance reads as missing") as e:
        mgmt._junos_answers(RouteLab(nodes=["j1"], kinds={"j1": ("juniper_cjunosevolved", "cj")}), "j1")
    assert not isinstance(e.value, NoSuchInstance)


def test_the_junos_probe_reads_the_default_instance(monkeypatch):
    from netdryrun.drivers import junos
    seen = []
    monkeypatch.setattr(junos.JunosDriver, "management_routes", lambda self, vrf: seen.append((self.node, vrf)) or [])
    mgmt._junos_answers(RouteLab(nodes=["j1"], kinds={"j1": ("juniper_cjunosevolved", "cj")}), "j1")
    assert seen == [("j1", "default")]


def test_eos_prepare_waits_for_its_cli(monkeypatch):
    monkeypatch.setattr(mgmt, "READY_BUDGET", 300.0)
    lab = EosLab()
    real, n = lab.exec, [0]

    def exec_(node, cmd, timeout=60, input=None):
        n[0] += 1
        if n[0] <= 2:
            raise LabError("e1: Cli: not ready")
        return real(node, cmd, timeout, input)
    lab.exec = exec_
    slept: list = []
    m = mgmt.prepare(lab, [], sleep=slept.append)["r1"]
    assert slept == [5.0, 5.0] and len(lab.sent) == 1 and m.removed


def test_linux_kinds_are_not_waited_for(monkeypatch):
    monkeypatch.setattr(mgmt, "READY_BUDGET", 300.0)
    with pytest.raises(LabError, match="its routes can't be read"):
        mgmt.prepare(RouteLab(fail={"route show": 1}), [], sleep=lambda s: pytest.fail("must not wait"))
