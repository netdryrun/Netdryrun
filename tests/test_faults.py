import json
import textwrap

import pytest

from netdryrun import runner
from netdryrun.config import ConfigError, load
from netdryrun.faults import RouteInjection, bgp_asn, config_lines, conflicts, parse_inject
from netdryrun.lab import ExecResult, Lab, LabError


def test_count_generates_consecutive_prefixes():
    inj = parse_inject("s", {"node": "ce1", "count": 3, "from": "10.100.16.0/24"})
    assert inj == {"node": "ce1", "prefixes": ["10.100.16.0/24", "10.100.17.0/24", "10.100.18.0/24"], "as_path": []}
    assert parse_inject("s", {"node": "r1", "count": 2})["prefixes"] == ["100.64.0.0/24", "100.64.1.0/24"]


def test_prefixes_are_canonical_and_as_path_kept():
    inj = parse_inject("s", {"node": "p", "prefixes": ["8.8.8.1/24", "2001:db8:0::/48"], "as_path": [65400, 15169]})
    assert inj["prefixes"] == ["8.8.8.0/24", "2001:db8::/48"]
    assert inj["as_path"] == [65400, 15169]


@pytest.mark.parametrize("item,msg", [
    ({"count": 3}, "needs a node"),
    ({"node": "r1"}, "either prefixes or count"),
    ({"node": "r1", "count": 2, "prefixes": ["10.0.0.0/24"]}, "either prefixes or count"),
    ({"node": "r1", "count": 0}, "count must be"),
    ({"node": "r1", "count": True}, "count must be"),
    ({"node": "r1", "count": 20000}, "count must be"),
    ({"node": "r1", "prefixes": ["10.0.0.0/24"], "from": "10.1.0.0/24"}, "from only goes with count"),
    ({"node": "r1", "prefixes": ["not-a-prefix"]}, "inject_routes"),
    ({"node": "r1", "count": 2, "from": "255.255.255.0/24"}, "inject_routes"),
    ({"node": "r1", "count": 2, "as_path": ["x"]}, "as_path"),
    ({"node": "r1", "count": 2, "colour": "red"}, "unknown inject_routes keys"),
])
def test_rejects_bad_injections(item, msg):
    with pytest.raises(ValueError, match=msg):
        parse_inject("scenarios[0]", item)


def test_config_lines_add_and_remove():
    add = config_lines("65100", ["10.1.0.0/24", "2001:db8::/48"], [65400])
    assert "ip route 10.1.0.0/24 blackhole" in add and "ipv6 route 2001:db8::/48 blackhole" in add
    assert " set as-path prepend 65400" in add
    assert "  network 10.1.0.0/24 route-map NDR-INJECT" in add
    assert add.index(" address-family ipv6 unicast") < add.index("  network 2001:db8::/48 route-map NDR-INJECT")
    rm = config_lines("65100", ["10.1.0.0/24"], [65400], remove=True)
    assert rm == ["no ip route 10.1.0.0/24 blackhole", "router bgp 65100", " address-family ipv4 unicast",
                  "  no network 10.1.0.0/24", " exit-address-family", "exit", "no route-map NDR-INJECT"]
    assert not any("route-map" in line for line in config_lines("1", ["10.1.0.0/24"], []))


RUNNING = textwrap.dedent("""\
    ip route 192.0.2.0/24 blackhole
    router bgp 65000
     address-family ipv4 unicast
      network 192.0.2.0/24
      network 10.9.0.0/24 route-map X
     exit-address-family
    """)


def test_asn_and_conflicts():
    assert bgp_asn(RUNNING) == "65000"
    with pytest.raises(LabError, match="no 'router bgp'"):
        bgp_asn("router bgp 65000 vrf blue\n")
    assert conflicts(RUNNING, ["192.0.2.0/24", "10.9.0.0/24", "10.9.0.0/2", "8.8.8.0/24"]) == ["192.0.2.0/24", "10.9.0.0/24"]


class FakeLab:
    """Pretends to be an FRR node: applies the injected config to an in-memory BGP table."""

    def __init__(self, running=RUNNING):
        self.running, self.table, self.calls, self.files = running, set(), [], []

    def exec(self, node, cmd, timeout=60, input=None):
        self.calls.append(cmd)
        if cmd[:2] == ["sh", "-c"]:
            self.files.append(input)
            return ExecResult(cmd, 0, "", "")
        if cmd[1:3] == ["-c", "show running-config"]:
            return ExecResult(cmd, 0, self.running, "")
        if cmd[1] == "-f":
            for line in self.files[-1].splitlines():
                w = line.split()
                if w[:1] == ["network"]:
                    self.table.add(w[1])
                elif w[:2] == ["no", "network"]:
                    self.table.discard(w[2])
            return ExecResult(cmd, 0, "", "")
        if cmd[1] == "-c" and cmd[2].endswith("unicast summary json"):   # one peer, sent everything in the table
            return ExecResult(cmd, 0, json.dumps({"peers": {"10.0.0.2": {"pfxSnt": len(self.table) + 1, "state": "Established"}}}), "")
        if cmd[1:3] == ["-c", "show bgp neighbors json"]:
            return ExecResult(cmd, 0, json.dumps({"10.0.0.2": {"connectionsDropped": 0}}), "")
        if cmd[1] == "-c" and cmd[2].startswith("show bgp"):
            return ExecResult(cmd, 0, json.dumps({"routes": {p: [] for p in self.table}}), "")
        raise AssertionError(cmd)


def test_apply_waits_for_routes_and_restore_removes_them():
    lab = FakeLab()
    inj = RouteInjection(lab, "ce1", ["10.100.16.0/24", "10.100.17.0/24"], [65400])
    inj.apply()
    assert lab.table == {"10.100.16.0/24", "10.100.17.0/24"}
    assert "router bgp 65000" in lab.files[0]
    inj.restore()
    assert lab.table == set()
    assert "no route-map NDR-INJECT" in lab.files[1]


def test_conflict_refuses_and_restore_touches_nothing():
    lab = FakeLab()
    inj = RouteInjection(lab, "pe1", ["192.0.2.0/24"], [])
    with pytest.raises(LabError, match="already configured"):
        inj.apply()
    inj.restore()
    assert lab.files == []


def test_routes_that_never_appear_fail_loudly(monkeypatch):
    monkeypatch.setattr("netdryrun.faults.time.sleep", lambda s: None)
    lab = FakeLab()
    lab.exec_orig = lab.exec
    lab.exec = lambda node, cmd, timeout=60, input=None: (
        ExecResult(cmd, 0, "", "") if cmd[1:2] == ["-f"] else lab.exec_orig(node, cmd, timeout, input))
    inj = RouteInjection(lab, "ce1", ["10.100.16.0/24"], [], budget=0)
    with pytest.raises(LabError, match="did not appear"):
        inj.apply()
    assert inj.applied   # so the runner still tries to restore


def write_cfg(tmp_path, kind_line=""):
    (tmp_path / "topo.clab.yml").write_text(textwrap.dedent(f"""\
        name: t
        topology:
          nodes:
            r1: {{image: quay.io/frrouting/frr:10.4.1}}
            r2: {{kind: nokia_srlinux{kind_line}}}
        """))
    p = tmp_path / "netdryrun.yml"
    p.write_text(textwrap.dedent("""\
        lab: topo.clab.yml
        checks:
          - {type: ping, node: r1, target: 10.0.0.1}
        scenarios:
          - inject_routes: {node: r2, count: 5}
            checks:
              - {type: bgp_prefixes, node: r1, neighbor: 10.0.0.2, max: 1}
          - name: r1 leaks
            inject_routes: [{node: r1, prefixes: [8.8.8.0/24]}]
            link_down: {node: r1, interface: eth1}
            checks:
              - {type: route, node: r1, prefix: 8.8.8.0/24}
        """))
    return p


def test_config_loads_inject_routes(tmp_path):
    cfg = load(write_cfg(tmp_path))
    sc = cfg.scenarios
    assert sc[0].name == "r2 injects 5 route(s)"
    assert sc[0].faults[0].kind == "inject_routes" and len(sc[0].faults[0].prefixes) == 5
    assert {f.kind for f in sc[1].faults} == {"inject_routes", "link_down"}


def test_config_error_names_the_scenario(tmp_path):
    p = write_cfg(tmp_path)
    p.write_text(p.read_text().replace("count: 5", "count: -1"))
    with pytest.raises(ConfigError, match=r"scenarios\[0\]: inject_routes: count must be"):
        load(p)


def test_runner_refuses_non_frr_nodes_before_deploying(tmp_path, monkeypatch):
    monkeypatch.setattr(Lab, "check_tools", lambda self: None)
    monkeypatch.setattr(Lab, "version", lambda self: "test")
    deployed = []
    monkeypatch.setattr(Lab, "deploy", lambda self: deployed.append(1))
    monkeypatch.setattr(Lab, "destroy", lambda self: ExecResult([], 0, "", ""))
    rep = runner.run(load(write_cfg(tmp_path)))
    assert rep.status == "error"
    assert "inject_routes on r2 (srlinux) is not supported" in rep.error
    assert not deployed
