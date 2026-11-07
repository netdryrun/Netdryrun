"""Exact tests for the mutation survivors of c5c1391 (2026-11-07)."""
from __future__ import annotations

from pathlib import Path

import pytest

from netdryrun import config, mgmt, runner
from netdryrun.config import ConfigError, Scenario
from netdryrun.lab import ExecResult, LabError

from test_mgmt import RouteLab, m_of
from test_verdict_runner import chk, leak, make, route


def _cfg(tmp_path, text):
    (tmp_path / "t.clab.yml").write_text("name: ndr-x\ntopology:\n  nodes:\n    r1: {kind: linux}\n", encoding="utf-8")
    p = tmp_path / "netdryrun.yml"
    p.write_text(text, encoding="utf-8")
    return p


def test_config_load_messages_name_the_file(tmp_path):
    p = _cfg(tmp_path, "checks: []\n")
    with pytest.raises(ConfigError) as e:
        config.load(p)
    assert str(e.value) == f"{p}: missing 'lab' (path to the containerlab topology file)"
    p = _cfg(tmp_path, "lab: 5\nchecks: []\n")
    with pytest.raises(ConfigError) as e:
        config.load(p)
    assert str(e.value).startswith(f"{p}: ")
    p = _cfg(tmp_path, "lab: t.clab.yml\ntimeout: abc\nchecks: [{type: bgp_session, node: r1, neighbor: 10.0.0.2}]\n")
    with pytest.raises(ConfigError) as e:
        config.load(p)
    assert str(e.value).startswith(f"{p}: ")
    p = _cfg(tmp_path, "lab: t.clab.yml\nchecks: []\n")
    with pytest.raises(ConfigError) as e:
        config.load(p)
    assert str(e.value) == f"{p}: no checks defined"


def test_b1_duration_is_rounded_to_a_tenth(monkeypatch):
    e = make(monkeypatch)
    calls = [0]

    def clk():   # fractional readings, as a real clock gives
        calls[0] += 1
        return e.clock.now + 0.123 * calls[0]
    monkeypatch.setattr(runner, "_clock", clk)
    e.drivers["r1"].neighbors_error = RuntimeError("cli timeout")
    neg = leak("n", timeout=6)
    sess = chk("bgp_session", "s", neighbor="10.0.12.2", state="established", timeout=6)
    r = runner._bgp_convergence_gate([neg], [neg, sess], e.drivers, log=e.logs.append, warnings={})[id(neg)]
    assert isinstance(r.duration, float) and r.duration == round(r.duration, 1) and r.duration != round(r.duration)


def test_preflight_refuses_a_scenario_check_on_an_unknown_node(monkeypatch):
    e = make(monkeypatch)
    cfg = runner.Config(path=Path("netdryrun.yml"), lab=Path("t.clab.yml"), timeout=60, checks=[route("a")],
                        scenarios=[Scenario("s", [], [route("[s] x", node="r9")])])
    with pytest.raises(LabError, match="unknown node.*r9"):
        runner.preflight(cfg, e.lab)


def test_unreadable_addresses_with_no_output_say_so():
    lab = RouteLab(v4="", v6="")
    real = lab.exec_root
    lab.exec_root = lambda node, cmd, timeout=60: (ExecResult(cmd, 1, "", "") if cmd[1:3] == ["addr", "show"]
                                                   else real(node, cmd, timeout))
    with pytest.raises(LabError) as e:
        mgmt.prepare(lab, [])
    assert str(e.value) == "r1: its addresses can't be read (`ip addr show` rc=1: no output)"


def test_the_ipv6_multicast_route_doesnt_stop_the_scan():
    rs = mgmt.parse_ip_route("ff00::/8 dev eth0 metric 256\n::/0 via 3fff:172:31:99::1 dev eth0 metric 1024", 6)
    docker, other = mgmt.classify_linux(rs, m_of())
    assert [r.line for r in docker] == ["::/0 via 3fff:172:31:99::1 dev eth0 metric 1024"] and other == []


def test_pairs_encap_after_two_pairs():
    assert mgmt._pairs(["dev", "e", "proto", "p", "encap", "mpls", "1", "via", "10.0.0.1"]) == \
        {"dev": "e", "proto": "p", "via": "10.0.0.1"}


def test_a_ping_without_a_target_still_has_its_source_checked():
    """Config always gives a ping a target, but refuse_checks must not rely on it (reviewer, c5c1391 triage)."""
    from netdryrun.config import Check
    c = Check(type="ping", params={"node": "r1", "source": "172.31.99.2"}, name="p", timeout=30)
    with pytest.raises(LabError, match="source 172.31.99.2 is in the lab's management network"):
        mgmt.refuse_checks(RouteLab(), {"r1": m_of()}, [c])
