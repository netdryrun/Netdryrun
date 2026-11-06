"""The management path out of the lab (red team round 4, B3; design "e, option A" and revision R1-R12).

B3: with the lab route gone, an FRR/SONiC ping left over Docker's default route on eth0, Docker masqueraded it, and an
address the Docker host reaches answered, so `expect: success` passed without the lab (every released version). The
route texts are live captures (tests/fixtures/mgmt_*_ip_route.txt; SOURCES.yml).
"""
from __future__ import annotations

import ipaddress
import re
import json
from pathlib import Path

import pytest

from netdryrun import checks, mgmt, runner
from netdryrun.config import Check
from netdryrun.drivers.frr import FrrDriver
from netdryrun.lab import ExecResult, Lab, LabError, Node
from netdryrun.mgmt import ManagementPathError

from test_verdict_runner import chk, make, route

FX = Path(__file__).parent / "fixtures"


def section(name, title):
    """One `--- title` section of a capture (the first section has no title: "")."""
    parts, cur, key = {}, [], ""
    for line in (FX / name).read_text(encoding="utf-8").splitlines():
        if line.startswith("--- "):
            parts[key], cur, key = "\n".join(cur), [], line[4:]
        elif line.startswith("rc="):
            continue
        else:
            cur.append(line)
    parts[key] = "\n".join(cur)
    return parts[title]


FRR_V4, FRR_V6 = section("mgmt_frr_ip_route.txt", ""), section("mgmt_frr_ip_route.txt", "v6")
FRR_V4_AFTER, FRR_V6_AFTER = section("mgmt_frr_ip_route.txt", "after v4"), section("mgmt_frr_ip_route.txt", "after v6")
FRR_MULTIPATH = section("mgmt_frr_ip_route.txt", "multipath")
BB_V4, BB_V6 = section("mgmt_busybox_ip_route.txt", ""), section("mgmt_busybox_ip_route.txt", "v6")

GW4, GW6 = "172.31.99.1", "3fff:172:31:99::1"
INSPECT = {"HostConfig": {"NetworkMode": "clab"},
           "NetworkSettings": {"Networks": {"clab": {
               "IPAddress": "172.31.99.2", "IPPrefixLen": 24, "Gateway": GW4,
               "GlobalIPv6Address": "3fff:172:31:99::2", "GlobalIPv6PrefixLen": 64, "IPv6Gateway": GW6}}}}


def m_of(devices=("eth0",)):
    m = mgmt.Mgmt("r1", "clab", [ipaddress.ip_network("172.31.99.0/24"), ipaddress.ip_network("3fff:172:31:99::/64")],
                  [ipaddress.ip_address(GW4), ipaddress.ip_address(GW6)])
    m.devices = set(devices)
    return m


class RouteLab:
    """A lab whose nodes answer `ip route` from a per-node table, as the captures print it; `del` removes the line."""

    def __init__(self, nodes=None, v4=FRR_V4, v6=FRR_V6, inspect=None, kinds=None, fail=None):
        kinds = kinds or {}
        self.nodes = {n: Node(n, f"clab-t-{n}", *kinds.get(n, ("linux", "quay.io/frrouting/frr:10.4.1")))
                      for n in (nodes or ["r1"])}
        self.tables = {n: {4: v4, 6: v6} for n in self.nodes}
        self.inspect = inspect or {}
        self.fail = fail or {}
        self.calls: list[tuple] = []
        self.events: list[tuple] = []

    def docker_inspect(self, node):
        return self.inspect.get(node, INSPECT)

    def exec_root(self, node, cmd, timeout=60):
        self.calls.append((node, tuple(cmd)))
        key = " ".join(cmd)
        for needle, rc in self.fail.items():
            if needle in key:
                return ExecResult(cmd, rc, "", "boom")
        if cmd[0] == "sysctl":
            return ExecResult(cmd, 1, "", "sysctl: error setting key: Read-only file system")
        fam = 6 if "-6" in cmd else 4
        if cmd[2:4] == ["route", "show"]:
            return ExecResult(cmd, 0, self.tables[node][fam], "")
        if cmd[2:4] == ["route", "del"]:
            via = cmd[cmd.index("via") + 1]
            lines = self.tables[node][fam].splitlines()
            keep = [ln for ln in lines if not ln.startswith(f"default via {via} dev")]
            self.events.append(("del", node, fam, via))
            self.tables[node][fam] = "\n".join(keep)
            return ExecResult(cmd, 0 if len(keep) < len(lines) else 2, "", "")
        raise AssertionError(key)


# ------------------------------------------------------------------------------------------- parsing (captures)

def test_parse_the_frr_capture():
    rs = mgmt.parse_ip_route(FRR_V4, 4)
    assert (rs[0].prefix, rs[0].via, rs[0].dev, rs[0].proto, rs[0].table) == ("default", GW4, "eth0", "", "main")
    assert [r.rtype for r in rs].count("local") == 3 and rs[1].proto == "kernel"
    v6 = mgmt.parse_ip_route(FRR_V6, 6)
    assert [(r.prefix, r.via) for r in v6 if r.via] == [("default", GW6)]


def test_parse_the_multipath_legs():
    legs = [r for r in mgmt.parse_ip_route(FRR_MULTIPATH, 4) if r.line.startswith("nexthop")]
    assert [(r.prefix, r.via, r.dev, r.proto) for r in legs] == [("default", "10.9.0.2", "dummy0", "static"),
                                                                ("default", GW4, "eth0", "static")]


def test_an_indented_line_that_is_no_nexthop_is_an_error():
    with pytest.raises(LabError, match="doesn't explain"):
        mgmt.parse_ip_route("default proto static\n\tsomething else", 4)


# ------------------------------------------------------------------------------------------- what is Docker's

@pytest.mark.parametrize("v4,v6", [(FRR_V4, FRR_V6), (BB_V4, BB_V6)], ids=["iproute2", "busybox"])
def test_only_dockers_defaults_are_deleted(v4, v6):
    m = m_of()
    docker, other = mgmt.classify_linux(mgmt.parse_ip_route(v4, 4) + mgmt.parse_ip_route(v6, 6), m)
    assert [(r.family, r.via) for r in docker] == [(4, GW4), (6, GW6)] and other == []


def test_after_the_delete_nothing_is_left():
    m = m_of()
    assert mgmt.classify_linux(mgmt.parse_ip_route(FRR_V4_AFTER, 4) + mgmt.parse_ip_route(FRR_V6_AFTER, 6), m) == ([], [])


def test_a_multipath_default_or_a_static_route_via_the_management_gateway_is_a_run_error():
    docker, other = mgmt.classify_linux(mgmt.parse_ip_route(FRR_MULTIPATH, 4), m_of())
    assert docker == []
    assert sorted(r.line for r in other) == ["10.77.0.0/16 via 172.31.99.1 dev eth0 proto static",
                                             "nexthop via 172.31.99.1 dev eth0 weight 1"]


@pytest.mark.parametrize("line", [
    "default via 172.31.99.1 dev eth0 proto static",     # configured by the lab: zebra would reinstall it
    "default via 172.31.99.254 dev eth0",                # another gateway on the management device
    "default via 172.31.99.1 dev eth0 table 10",         # another table
    "10.0.0.0/8 dev eth0 scope link",                    # a lab prefix on the management device
])
def test_any_other_route_on_the_management_device_is_a_run_error(line):
    docker, other = mgmt.classify_linux(mgmt.parse_ip_route(line, 4), m_of())
    assert docker == [] and [r.line for r in other] == [line]


def test_a_lab_default_via_a_lab_interface_is_never_touched():
    assert mgmt.classify_linux(mgmt.parse_ip_route("default via 10.0.12.2 dev eth1 proto bgp metric 20", 4),
                               m_of()) == ([], [])


# ------------------------------------------------------------------------------------------- prepare (Linux)

def test_docker_mgmt_reads_every_network():
    m = mgmt.docker_mgmt(RouteLab(), "r1")
    assert m.mode == "clab" and [str(s) for s in m.subnets] == ["172.31.99.0/24", "3fff:172:31:99::/64"]
    assert [str(g) for g in m.gateways] == [GW4, GW6]


def test_docker_inspect_without_network_settings_is_an_error():
    with pytest.raises(LabError, match="no network settings"):
        mgmt.docker_mgmt(RouteLab(inspect={"r1": {"HostConfig": {}}}), "r1")


def test_prepare_deletes_dockers_defaults_and_records_them():
    lab = RouteLab()
    logs: list[str] = []
    state = mgmt.prepare(lab, [], log=logs.append)
    m = state["r1"]
    assert m.devices == {"eth0"} and m.removed == ["default via 172.31.99.1 dev eth0", "default via "
                                                   "3fff:172:31:99::1 dev eth0 metric 1024 pref medium"]
    assert ("r1", ("ip", "-4", "route", "del", "default", "via", GW4, "dev", "eth0")) in lab.calls
    assert lab.management is state and mgmt.describe(m, "linux").startswith("removed: default via 172.31.99.1")
    assert any("accept_ra=0 on eth0 not set" in x for x in logs)    # read-only in an unprivileged container


def test_a_failed_delete_is_a_run_error():
    with pytest.raises(ManagementPathError, match="could not be deleted"):
        mgmt.prepare(RouteLab(fail={"route del": 2}), [])


def test_a_default_still_there_after_the_delete_is_a_run_error():
    lab = RouteLab()
    lab.exec_root = (lambda orig: lambda node, cmd, timeout=60: (
        ExecResult(cmd, 0, "", "") if cmd[2:4] == ["route", "del"] else orig(node, cmd, timeout)))(lab.exec_root)
    with pytest.raises(ManagementPathError, match="after deleting Docker's default route"):
        mgmt.prepare(lab, [])


def test_routes_that_cant_be_read_are_a_run_error():
    with pytest.raises(LabError, match="can't be read"):
        mgmt.prepare(RouteLab(fail={"-4 route show": 1}), [])


def test_routes_the_helper_cant_read_either_are_a_run_error():
    lab = NoIpLab()
    lab.netns_exec = lambda node, cmd, timeout=60: ExecResult(cmd, 1, "", "RTNETLINK answers: Operation not permitted")
    with pytest.raises(LabError, match="can't be read"):
        mgmt.prepare(lab, [])


def test_another_route_on_the_management_device_ends_the_run_before_the_checks():
    with pytest.raises(ManagementPathError, match="10.77.0.0/16 via 172.31.99.1"):
        mgmt.prepare(RouteLab(v4=FRR_MULTIPATH), [])


def test_a_node_without_ipv6_in_its_kernel_has_no_ipv6_route():
    lab = RouteLab()
    real = lab.exec_root
    lab.exec_root = lambda node, cmd, timeout=60: (ExecResult(cmd, 2, "", "Address family not supported by protocol")
                                                   if "-6" in cmd else real(node, cmd, timeout))
    assert mgmt.prepare(lab, [])["r1"].removed == ["default via 172.31.99.1 dev eth0"]


# ------------------------------------------------------------------------------------------- network modes, checks

def test_host_and_container_network_modes_are_not_touched():
    lab = RouteLab(nodes=["r1", "h1", "h2"],
                   inspect={"h1": {"HostConfig": {"NetworkMode": "host"}, "NetworkSettings": {"Networks": {}}},
                            "h2": {"HostConfig": {"NetworkMode": "container:clab-t-r1"},
                                   "NetworkSettings": {"Networks": {}}}})
    state = mgmt.prepare(lab, [])
    assert not any(n in ("h1", "h2") for n, _ in lab.calls)
    assert mgmt.describe(state["h1"], "linux").startswith("not touched (network-mode host")
    assert mgmt.describe(state["h2"], "linux") == "not touched (shares clab-t-r1's namespace)"


def test_a_check_on_a_host_network_node_is_refused():
    lab = RouteLab(nodes=["h1"], inspect={"h1": {"HostConfig": {"NetworkMode": "host"},
                                                 "NetworkSettings": {"Networks": {}}}})
    with pytest.raises(LabError, match="Docker host's network namespace"):
        mgmt.prepare(lab, [chk("ping", "p", node="h1", target="10.0.0.9")])


@pytest.mark.parametrize("params,match", [
    ({"target": "172.31.99.7"}, "target 172.31.99.7 is in the lab's management network"),
    ({"target": "10.0.0.9", "source": "172.31.99.2"}, "source 172.31.99.2 is in the lab's management network"),
    ({"target": "3fff:172:31:99::9"}, "management network 3fff:172:31:99::/64"),
    ({"target": "fe80::2%eth0"}, "scoped to the management interface eth0"),
])
def test_a_ping_over_the_management_network_is_refused(params, match):
    with pytest.raises(LabError, match=match):
        mgmt.prepare(RouteLab(), [chk("ping", "p", **params)])


def test_a_lab_without_docker_is_left_alone():
    class Fake:
        nodes = {"r1": Node("r1", "c", "linux", "frr")}
    lab = Fake()
    assert mgmt.prepare(lab, []) == {} and lab.management == {}


def test_the_real_lab_can_read_docker():
    assert callable(getattr(Lab, "docker_inspect")) and callable(getattr(Lab, "exec_root"))


# ------------------------------------------------------------------------------------------- re-checks

def test_a_default_back_before_a_ping_ends_the_run():
    lab = RouteLab()
    mgmt.prepare(lab, [])
    lab.tables["r1"][4] = FRR_V4                          # re-added (a DHCP client, a user exec)
    lab.exec = lambda node, cmd, timeout=60, input=None: pytest.fail("the ping must not run")
    with pytest.raises(ManagementPathError, match="before the ping to 10.0.0.9"):
        FrrDriver(lab, "r1").ping("10.0.0.9", None, 3)


def test_a_default_back_after_a_ping_ends_the_run():
    lab = RouteLab()
    mgmt.prepare(lab, [])

    def ping(node, cmd, timeout=60, input=None):
        lab.tables["r1"][6] = FRR_V6                      # a router advertisement during the ping
        return ExecResult(cmd, 0, "3 packets transmitted, 3 received, 0% packet loss", "")
    lab.exec = ping
    with pytest.raises(ManagementPathError, match="after the ping to 10.0.0.9"):
        FrrDriver(lab, "r1").ping("10.0.0.9", None, 3)


def test_the_error_is_never_an_unready_sample():
    class D:
        def ping(self, *a):
            raise ManagementPathError("back")
    with pytest.raises(ManagementPathError):
        checks._evaluate(Check(type="ping", params={"node": "r1", "target": "10.0.0.9"}, name="p", timeout=30), D())


def test_recheck_covers_every_touched_node():
    lab = RouteLab(nodes=["r1", "r2"])
    mgmt.prepare(lab, [])
    lab.tables["r2"][4] = FRR_V4
    with pytest.raises(ManagementPathError, match="r2 has a route out .*(before scenario 's')"):
        mgmt.recheck(lab, "before scenario 's'")


# ------------------------------------------------------------------------------------------- cEOS

def eos_json(default_via=None, other=None, vrf="default"):
    routes = {"172.31.99.0/24": {"routeType": "connected", "vias": [{"interface": "Management0"}]},
              "10.0.12.0/30": {"routeType": "connected", "vias": [{"interface": "Ethernet1"}]}}
    if default_via:
        routes["0.0.0.0/0"] = {"routeType": "static", "vias": [{"nexthopAddr": default_via, "interface": "Management0"}]}
    if other:
        routes.update(other)
    return json.dumps({"vrfs": {vrf: {"routes": routes}}})


def test_eos_containerlabs_default_is_ours_and_the_connected_subnet_is_fine():
    ours, other = mgmt.classify_eos(eos_json(GW4), 4, m_of())
    assert ours == [("default", "0.0.0.0/0", GW4)] and other == []


def test_eos_another_route_via_management_is_a_run_error():
    ours, other = mgmt.classify_eos(eos_json(other={"10.77.0.0/16": {"routeType": "static", "vias": [
        {"nexthopAddr": GW4, "interface": "Management0"}]}}), 4, m_of())
    assert ours == [] and other == ["10.77.0.0/16 (vrf default, static) via 172.31.99.1 Management0"]


CLAB_EOS = ("hostname e1\nip route 0.0.0.0/0 172.31.99.1\nipv6 route ::0/0 3fff:172:31:99::1\n"
            "interface Management0\n   ip address 172.31.99.2/24\n")


class EosLab(RouteLab):
    """A cEOS node: startup and running config text, and a routing table that follows the running config."""

    def __init__(self, running=CLAB_EOS, startup=CLAB_EOS, load_after=0, **kw):
        super().__init__(kinds={"r1": ("arista_ceos", "ceos:4.36.3M")}, **kw)
        self.running, self.startup, self.load_after, self.sent, self.reads = running, startup, load_after, [], 0

    def exec(self, node, cmd, timeout=60, input=None):
        c = cmd[-1]
        if c.startswith("configure"):
            self.sent.append(c)
            for ln in c.splitlines()[1:-1]:
                self.running = self.running.replace(ln[3:] + "\n", "")
            return ExecResult(cmd, 0, "", "")
        if c == "show startup-config":
            return ExecResult(cmd, 0, self.startup, "")
        if c == "show running-config":
            self.reads += 1
            return ExecResult(cmd, 0, self.running if self.reads > self.load_after else "hostname e1\n", "")
        if "route vrf all" in c:
            v6 = "ipv6" in c
            gw = GW6 if v6 else GW4
            has = (f"ipv6 route ::0/0 {gw}" if v6 else f"ip route 0.0.0.0/0 {gw}") in self.running
            routes = {"::/0" if v6 else "0.0.0.0/0": {"routeType": "static", "vias": [
                {"nexthopAddr": gw, "interface": "Management0"}]}} if has else {}
            return ExecResult(cmd, 0, json.dumps({"vrfs": {"default": {"routes": routes}}}), "")
        raise AssertionError(c)


def test_eos_prepare_removes_containerlabs_defaults_in_config():
    lab = EosLab()
    m = mgmt.prepare(lab, [])["r1"]
    assert lab.sent == ["configure\nno ip route 0.0.0.0/0 172.31.99.1\nno ipv6 route ::0/0 3fff:172:31:99::1\nend"]
    assert m.removed == ["ip route 0.0.0.0/0 172.31.99.1", "ipv6 route ::0/0 3fff:172:31:99::1"]
    assert lab.calls == []                                # nothing in the container's Linux namespace


def test_eos_waits_for_the_startup_config_to_load_before_removing():
    slept = []
    lab = EosLab(load_after=3)                           # the first three reads see a config not loaded yet
    mgmt.prepare(lab, [], sleep=slept.append)
    assert slept == [3.0, 3.0, 3.0] and len(lab.sent) == 1


def test_eos_a_startup_config_that_never_loads_is_a_run_error():
    lab = EosLab(load_after=10 ** 6)
    with pytest.raises(ManagementPathError, match="running config still doesn't after 180s"):
        mgmt.prepare(lab, [], sleep=lambda s: None)
    assert lab.sent == []


def test_eos_a_lab_without_containerlabs_route_is_left_alone():
    lab = EosLab(running="hostname e1\n", startup="hostname e1\n")
    assert mgmt.prepare(lab, [])["r1"].removed == [] and lab.sent == []


@pytest.mark.parametrize("line", ["ip route 10.77.0.0/16 172.31.99.1", "ip route 0.0.0.0/0 Management0",
                                  "ip route 0.0.0.0/0 172.31.99.1 200"])
def test_eos_another_static_over_management_in_the_config_is_a_run_error(line):
    lab = EosLab(running=f"hostname e1\n{line}\n", startup=f"hostname e1\n{line}\n")
    with pytest.raises(ManagementPathError, match="in its config"):
        mgmt.prepare(lab, [])


def test_eos_a_route_back_before_a_ping_ends_the_run():
    from netdryrun.drivers.eos import EosDriver
    lab = EosLab()
    mgmt.prepare(lab, [])
    lab.running = CLAB_EOS
    with pytest.raises(ManagementPathError, match="before the ping to 10.0.0.9"):
        EosDriver(lab, "r1").ping("10.0.0.9", None, 3)


def test_eos_unreadable_routes_are_a_run_error():
    with pytest.raises(LabError, match="can't be read"):
        mgmt.classify_eos("% Invalid input", 4, m_of())


# ------------------------------------------------------------------------------------------- the run

def _route_lab(e):
    """The runner tests' fake lab, with Docker and the capture's routes on every node."""
    rl = RouteLab(nodes=list(e.lab.nodes))
    e.lab.docker_inspect, e.lab.exec_root, e.lab.tables = rl.docker_inspect, rl.exec_root, rl.tables
    rl.events = e.lab.events
    return rl


def test_run_removes_the_route_after_setup_and_before_the_first_check(monkeypatch):
    e = make(monkeypatch)
    _route_lab(e)
    e.drivers["r1"].on_call = lambda: e.lab.events.append(("check",))
    rep = e.run([route("a")], setup={"r1": ["true"]}, deploy=True)
    kinds = [ev[0] for ev in e.lab.events if ev[0] in ("setup", "del", "check")]
    assert kinds.index("setup") < kinds.index("del") < kinds.index("check")
    assert rep.environment["nodes"]["r1"]["management_default"].startswith("removed: default via 172.31.99.1")
    assert any("settling" in x for x in e.logs)


def test_run_ends_with_an_error_when_the_route_comes_back(monkeypatch):
    e = make(monkeypatch)
    rl = _route_lab(e)
    e.drivers["r1"].on_call = lambda: rl.tables["r1"].__setitem__(4, FRR_V4)
    rep = e.run([route("a")])
    assert rep.status == "error" and "after the positive checks" in rep.error


# ------------------------------------------------------------------------------------------- Junos (probe only)

def _junos_table(via=None):
    """The whole-table capture (inet.0: BGP and static routes out of et-0/0/0.0 and et-0/0/1.0), et-0/0/0.0 moved to
    `via` when given."""
    t = (FX / "junos_route_table.txt").read_text(encoding="utf-8")
    return t.replace('"data" : "et-0/0/0.0"', f'"data" : "{via}"') if via else t


@pytest.mark.parametrize("via", ["re0:mgmt-0", "fxp0.0", "em0"])
def test_junos_any_active_route_out_of_a_management_interface_is_read(via):
    from netdryrun.drivers import junos
    found = junos.parse_management_routes(_junos_table(via))
    assert found and all(f.endswith(f"via {via}") for f in found)
    assert not any("(inet.0, connected)" in f or "(inet.0, local)" in f for f in found)


def test_junos_routes_out_of_lab_interfaces_are_not():
    from netdryrun.drivers import junos
    assert junos.parse_management_routes(_junos_table()) == []


def test_junos_a_management_route_ends_the_run_and_is_never_deleted():
    class JLab(RouteLab):
        def exec(self, node, cmd, timeout=60, input=None):
            text = " ".join(cmd)
            assert "show route table" in text, text
            if "inet6.0" in text:
                return ExecResult(cmd, 0, (FX / "junos_route_table_v6.txt").read_text(encoding="utf-8"), "")
            return ExecResult(cmd, 0, _junos_table("re0:mgmt-0"), "")
    lab = JLab(kinds={"r1": ("juniper_cjunosevolved", "cjunos:26.2")})
    with pytest.raises(ManagementPathError, match="re0:mgmt-0.*mgmt_junos"):
        mgmt.prepare(lab, [])
    assert lab.calls == []


# ------------------------------------------------------------------------------------------- option-A code adversary

def test_a_route_that_names_no_device_is_a_run_error():
    other = mgmt.classify_linux(mgmt.parse_ip_route("default nhid 12 proto static metric 20", 4), m_of())[1]
    assert [r.line for r in other] == ["default nhid 12 proto static metric 20"]


def test_a_multipath_head_without_a_device_is_judged_by_its_legs():
    docker, other = mgmt.classify_linux(mgmt.parse_ip_route(
        "default proto static\n\tnexthop via 10.9.0.2 dev dummy0 weight 1", 4), m_of())
    assert docker == [] and other == []


def test_an_encap_block_doesnt_shift_the_fields_after_it():
    rs = mgmt.parse_ip_route("10.0.0.0/8  encap mpls  100 via 172.31.99.1 dev eth0 proto static", 4)
    assert (rs[0].via, rs[0].dev, rs[0].proto) == (GW4, "eth0", "static")
    assert [r.line for r in mgmt.classify_linux(rs, m_of())[1]] == [rs[0].line]


def test_eos_config_lines_compare_normalised():
    lab = EosLab(running=CLAB_EOS.replace("::0/0", "::/0"))      # EOS prints containerlab's `::0/0` as `::/0`
    m = mgmt.prepare(lab, [], sleep=lambda s: pytest.fail("no wait: the route is loaded"))["r1"]
    assert m.removed == ["ip route 0.0.0.0/0 172.31.99.1", "ipv6 route ::/0 3fff:172:31:99::1"]


def test_an_unreadable_recheck_is_a_management_error_never_an_unready_sample():
    lab = RouteLab()
    mgmt.prepare(lab, [])
    lab.tables["r1"][4] = "default via 172.31.99.1 dev eth0\n  cache"          # a line the parser refuses
    with pytest.raises(ManagementPathError, match="could not be read before the ping"):
        mgmt.check_node(lab, "r1", "before the ping to 10.0.0.9")


@pytest.mark.parametrize("kind", ["ext-container", "k8s-kind", "cisco_xrd"])
def test_a_routing_driver_on_a_kind_whose_route_isnt_removed_is_refused(kind):
    lab = RouteLab(kinds={"r1": (kind, "quay.io/frrouting/frr:10.4.1")})
    state = mgmt.prepare(lab, [])
    with pytest.raises(LabError, match="read with the frr driver, but its kind"):
        mgmt.require_covered(lab, state, "r1", "frr")
    mgmt.require_covered(lab, state, "r1", "srlinux")           # a driver whose management is its own VRF


def test_a_node_sharing_a_namespace_is_covered_by_its_owner_by_name_or_id():
    shared = {"HostConfig": {"NetworkMode": "container:0123456789ab"}, "NetworkSettings": {"Networks": {}}}
    lab = RouteLab(nodes=["r1", "h1"], inspect={"r1": {**INSPECT, "Id": "0123456789abcdef"}, "h1": shared})
    state = mgmt.prepare(lab, [chk("ping", "p", node="h1", target="10.0.0.9")])
    mgmt.require_covered(lab, state, "h1", "frr")
    lab.tables["r1"][4] = FRR_V4
    with pytest.raises(ManagementPathError, match="r1 has a route out"):
        mgmt.check_node(lab, "h1", "before the ping to 10.0.0.9")


def test_run_refuses_a_routing_node_whose_route_isnt_handled(monkeypatch):
    e = make(monkeypatch, kinds={"r1": ("k8s-kind", "quay.io/frrouting/frr:10.4.1")})
    _route_lab(e)
    monkeypatch.setattr(runner, "resolve", lambda node, override=None: "frr")
    rep = e.run([route("a")])
    assert rep.status == "error" and "read with the frr driver" in rep.error


# ------------------------------------------------------------------------------------------- images without `ip`

def test_the_helper_image_is_a_sha256_pin():
    from netdryrun.lab import NETNS_HELPER_IMAGE
    assert re.fullmatch(r"alpine@sha256:[0-9a-f]{64}", NETNS_HELPER_IMAGE)


def test_the_helper_joins_only_the_nodes_netns_with_net_admin_only(monkeypatch):
    import netdryrun.lab as labmod
    seen = []
    monkeypatch.setattr(labmod, "_run", lambda cmd, **kw: seen.append(cmd) or ExecResult(cmd, 0, "", ""))
    lab = Lab.__new__(Lab)
    lab.nodes = {"h1": Node("h1", "clab-t-h1", "linux", "nginx")}
    lab.netns_exec("h1", ["ip", "-4", "route", "show"])
    assert seen == [["docker", "run", "--rm", "--network", "container:clab-t-h1", "--cap-drop", "ALL", "--cap-add",
                     "NET_ADMIN", "--read-only", "--security-opt", "no-new-privileges", labmod.NETNS_HELPER_IMAGE,
                     "ip", "-4", "route", "show"]]


class NoIpLab(RouteLab):
    """Nodes whose image has no `ip` (nginx, distroless): docker exec fails, the helper answers from the tables."""

    def __init__(self, helper_rc=0, **kw):
        super().__init__(v4=BB_V4, v6=BB_V6, **kw)
        self.helper_rc, self.helper_calls = helper_rc, []

    def exec_root(self, node, cmd, timeout=60):
        self.calls.append((node, tuple(cmd)))
        return ExecResult(cmd, 126, "", 'OCI runtime exec failed: exec: "ip": executable file not found in $PATH')

    def netns_exec(self, node, cmd, timeout=60):
        self.helper_calls.append((node, tuple(cmd)))
        if self.helper_rc:
            return ExecResult(cmd, self.helper_rc, "", "Unable to find image 'alpine@sha256:...' locally: dial tcp: "
                                                       "lookup registry-1.docker.io: no such host")
        return RouteLab.exec_root(self, node, ["ip", *cmd[1:]], timeout)


def test_a_node_without_ip_is_read_and_changed_through_the_helper():
    lab = NoIpLab()
    logs: list[str] = []
    m = mgmt.prepare(lab, [], log=logs.append)["r1"]
    assert m.via == "helper" and m.removed == ["default via 172.31.99.1 dev eth0", "default via 3fff:172:31:99::1 "
                                                                                  "dev eth0  metric 1024"]
    assert ("r1", ("ip", "-4", "route", "del", "default", "via", GW4, "dev", "eth0")) in lab.helper_calls
    assert mgmt.describe(m, "linux").endswith("(read from outside: no `ip` in the image)")
    assert any("no sysctl in the image" in x for x in logs)
    lab.tables["r1"][4] = BB_V4                           # and the re-check reads through the helper too
    with pytest.raises(ManagementPathError):
        mgmt.check_node(lab, "r1", "before the ping to 10.0.0.9")


def test_an_air_gapped_host_without_the_helper_image_gets_the_pull_hint():
    from netdryrun.lab import NETNS_HELPER_IMAGE
    with pytest.raises(LabError, match=re.escape(f"`docker pull {NETNS_HELPER_IMAGE}`")):
        mgmt.prepare(NoIpLab(helper_rc=125), [])


def test_a_node_whose_own_ip_works_never_uses_the_helper():
    lab = RouteLab()
    lab.netns_exec = lambda *a, **k: pytest.fail("the helper must not run")
    assert mgmt.prepare(lab, [])["r1"].via == "container"


# ------------------------------------------------------------------------------------------- edges (each line has its reason)

def test_a_docker_network_that_isnt_a_mapping_is_an_error():
    bad = {"HostConfig": {"NetworkMode": "clab"}, "NetworkSettings": {"Networks": {"clab": "x"}}}
    with pytest.raises(LabError, match="Docker network 'clab' reads x"):
        mgmt.docker_mgmt(RouteLab(inspect={"r1": bad}), "r1")


def test_parser_edges():
    rs = mgmt.parse_ip_route("\n10.0.0.0/8 via inet6 fe80::1 dev eth1 onlink proto bgp\n", 4)
    assert [(r.prefix, r.via, r.dev, r.proto) for r in rs] == [("10.0.0.0/8", "fe80::1", "eth1", "bgp")]
    with pytest.raises(LabError, match="without a destination"):
        mgmt.parse_ip_route("unicast", 4)


def test_an_unparseable_prefix_is_never_the_management_subnet():
    assert mgmt._in_mgmt_subnet("default", m_of()) is False


def test_a_multicast_prefix_without_its_type_is_not_a_route_out():
    assert mgmt.classify_linux(mgmt.parse_ip_route("ff00::/8 dev eth0 metric 256", 6), m_of()) == ([], [])


def test_an_ip_that_cant_list_every_table_reads_the_main_table():
    lab = RouteLab()
    real = lab.exec_root
    lab.exec_root = lambda node, cmd, timeout=60: (ExecResult(cmd, 1, "", "ip: invalid argument 'all'")
                                                   if cmd[-2:] == ["table", "all"] else real(node, cmd, timeout))
    m = mgmt.prepare(lab, [])["r1"]
    assert m.tables == "main" and len(m.removed) == 2


def test_no_interface_holding_the_management_subnet_is_an_error():
    with pytest.raises(LabError, match="no interface holds its management subnet"):
        mgmt.prepare(RouteLab(v4="10.0.12.0/30 dev eth1 proto kernel scope link", v6=""), [])


def test_eos_cli_failures_and_shapes_are_errors():
    class Fail(EosLab):
        def exec(self, node, cmd, timeout=60, input=None):
            return ExecResult(cmd, 1, "", "% Invalid input")
    with pytest.raises(LabError, match="failed .rc=1."):
        mgmt.prepare(Fail(), [])
    with pytest.raises(LabError, match="has no route table"):
        mgmt.classify_eos(json.dumps({"vrfs": {"default": {}}}), 4, m_of())
    with pytest.raises(LabError, match="reads"):
        mgmt.classify_eos(json.dumps({"vrfs": {"default": {"routes": {"0.0.0.0/0": {"routeType": "static"}}}}}), 4,
                          m_of())


def test_eos_a_lab_static_is_not_a_management_route():
    assert mgmt.eos_config_routes("ip route 10.0.0.0/8 10.0.12.2\nip route 10.1.0.0/16 Ethernet1\n", m_of()) == ([], [])


def test_network_mode_none_and_other_kinds_are_not_applicable():
    lab = RouteLab(nodes=["s1", "n1"], kinds={"s1": ("nokia_srlinux", "srl"), "n1": ("linux", "x")},
                   inspect={"n1": {"HostConfig": {"NetworkMode": "none"}, "NetworkSettings": {"Networks": {}}}})
    state = mgmt.prepare(lab, [chk("route", "r", node="s1", prefix="10.0.0.0/8")])
    assert mgmt.describe(state["s1"], "nokia_srlinux") == "not applicable (nokia_srlinux)"
    assert state["n1"].kind == "" and lab.calls == []


def test_recheck_reads_eos_and_junos_nodes_too():
    lab = EosLab()
    mgmt.prepare(lab, [])
    lab.running = CLAB_EOS
    with pytest.raises(ManagementPathError, match="before the hold"):
        mgmt.recheck(lab, "before the hold")
    called = []
    monkey = mgmt.Mgmt("j1", "clab", kind="junos")
    real = mgmt.check_junos
    try:
        mgmt.check_junos = lambda lab_, m, when: called.append((m.node, when))
        lab.management = {"j1": monkey}
        mgmt.recheck(lab, "after scenario 's'")
    finally:
        mgmt.check_junos = real
    assert called == [("j1", "after scenario 's'")]
