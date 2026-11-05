"""End-of-RIB in the convergence gate (0.4.1 red-team fixes, design round 3 "R3").

Red team: during a graceful restart (or any table still in flight) a session reads established with stable counts
while its routes are still arriving, so a leak guard passed before the leak was in. Each driver now reads End-of-RIB
per family ("received", "pending", "untracked", "unknown"), from live captures; the gate treats pending and unknown as
not settled: at the cap the own node's post-convergence checks are blocked, another node's carry a warning. A peer that
never sends End-of-RIB is declared with `nodes.<node>.peers.<address>.eor: not_sent`.

The gate tests are red on 1de8d70 (no End-of-RIB read: the check ran on a table still arriving).
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from netdryrun import runner
from netdryrun.config import ConfigError, load
from netdryrun.drivers import eos, frr, junos, nxos, routeros_state, srlinux
from netdryrun.drivers.base import BgpNeighbor

from test_verdict_runner import leak, make

FX = Path(__file__).parent / "fixtures"


def j(name):
    t = (FX / name).read_text(encoding="utf-8")
    return json.loads(t[min(i for i in (t.find("{"), t.find("[")) if i >= 0):])


# ------------------------------------------------------------------------------------------- driver readers

def test_frr_reads_pending_then_received_and_untracked_with_gr_off():
    assert frr.frr_eor(j("frr_eor_pending.json")["10.0.12.2"]) == {"ipv4-unicast": "pending"}
    assert frr.frr_eor(j("frr_eor_received.json")["10.0.12.2"]) == {"ipv4-unicast": "received"}
    assert frr.frr_eor(j("frr_eor_gr_off.json")["10.0.12.2"]) == {"*": "untracked"}


def test_frr_block_and_map_disagreeing_is_unknown():
    info = j("frr_eor_pending.json")["10.0.12.2"]
    info["gracefulRestartInfo"]["endOfRibRecv"] = {"ipv4Unicast": True}       # the map says received, the block not
    assert frr.frr_eor(info) == {"ipv4-unicast": "unknown"}
    assert frr.frr_eor({"bgpState": "Established"}) == {"*": "unknown"}


def test_frr_neighbor_parser_carries_it():
    text = (FX / "frr_eor_pending.json").read_text(encoding="utf-8")
    assert frr.parse_bgp_neighbors(text)["10.0.12.2"].eor == {"ipv4-unicast": "pending"}


def test_srlinux_reads_received_and_unknown_when_missing_with_gr():
    n = j("srl_eor_gr_baseline.txt")
    assert srlinux.srl_eor(n) == {"ipv4-unicast": "received"}
    n.pop("received-end-of-rib")
    assert srlinux.srl_eor(n) == {"ipv4-unicast": "unknown"}                  # never assumed received
    n["received-capabilities"] = [c for c in n["received-capabilities"] if c != "GRACEFUL_RESTART"]
    assert srlinux.srl_eor(n) == {"*": "untracked"}


def test_eos_reads_received_then_pending():
    assert eos.parse_eos_eor(json.dumps(j("eos_eor_received.txt")), "default") == {"10.0.200.2": {"ipv4-unicast": "received"}}
    assert eos.parse_eos_eor(json.dumps(j("eos_eor_pending.txt")), "default") == {"10.0.200.2": {"ipv4-unicast": "pending"}}
    p = j("eos_eor_gr_default.json")["vrfs"]["default"]["peerList"][0]
    p["endOfRibs"]["incoming"]["ipv4Unicast"]["status"] = "weird"
    assert eos.eos_eor(p) == {"ipv4-unicast": "unknown"}


def test_routeros_reads_empty_eor_as_pending_only_with_gr_both_ways():
    rows = {r["remote.address"]: r for r in j("routeros_eor_pending.txt")}
    assert routeros_state.ros_eor(rows["192.0.2.2"]) == {"ipv4-unicast": "pending"}
    assert routeros_state.ros_eor(rows["198.51.100.2"]) == {"ipv4-unicast": "received"}
    r = dict(rows["192.0.2.2"], **{"local.capabilities": "mp,rr,as4"})
    assert routeros_state.ros_eor(r) == {"*": "untracked"}
    assert routeros_state.ros_eor(dict(rows["192.0.2.2"], **{"remote.eor": "vpnv4"})) == {"*": "unknown"}
    received = {r["remote.address"]: r for r in j("routeros_eor_received.txt")}
    assert routeros_state.ros_eor(received["192.0.2.2"]) == {"ipv4-unicast": "received"}


def test_junos_reads_received_and_unknown_when_missing_with_gr():
    peer = j("junos_eor_received.txt")["bgp-information"][0]["bgp-peer"][0]
    assert junos.junos_eor(peer) == {"ipv4-unicast": "received"}
    peer.pop("peer-end-of-rib-received")
    assert junos.junos_eor(peer) == {"ipv4-unicast": "unknown"}
    peer.pop("peer-restart-nlri-negotiated")
    assert junos.junos_eor(peer) == {"ipv4-unicast": "untracked"}


def test_nxos_reads_the_text_line_only_while_established():
    msg = lambda name: nxos._ascii_msg((FX / name).read_text(encoding="utf-8"))   # noqa: E731
    assert nxos.nxos_eor_text(msg("nxos_eor_received.txt"), "ipv4-unicast") == "received"
    assert nxos.nxos_eor_text(msg("nxos_eor_pending.txt"), "ipv4-unicast") == "pending"
    assert nxos.nxos_eor_text(msg("nxos_eor_idle_sticky.txt"), "ipv4-unicast") == "unknown"   # sticky line ignored
    assert nxos.nxos_eor_text(msg("nxos_eor_received.txt"), "ipv6-unicast") == "unknown"      # no such block
    assert nxos.nxos_eor_text(None, "ipv4-unicast") == "unknown"


def test_readers_never_raise_on_junk():
    for junk in (None, 3, "x", [], {"gracefulRestartInfo": []}, {"endOfRibs": 5}, {"nlri-type-session": "x"}):
        frr.frr_eor(junk if isinstance(junk, dict) else {})
        srlinux.srl_eor(junk if isinstance(junk, dict) else {})
        eos.eos_eor(junk if isinstance(junk, dict) else {})
        junos.junos_eor(junk if isinstance(junk, dict) else {})
        routeros_state.ros_eor(junk if isinstance(junk, dict) else {})


# ------------------------------------------------------------------------------------------- the gate

class EorDrv:
    """Wraps a fake driver with an End-of-RIB answer per neighbor: fn(t) -> {addr: {fam: state}}."""

    def __init__(self, inner, eor):
        self.inner, self.eor = inner, eor

    def __getattr__(self, k):
        return getattr(self.inner, k)

    def end_of_rib(self, vrf, neighbors):
        return self.eor(self.inner.clock.now)


def gate(e, negatives, all_checks=None, warnings=None, not_sent=frozenset(), reported=None, extras=None):
    return runner._bgp_convergence_gate(negatives, all_checks or negatives, e.drivers, log=e.logs.append,
                                        warnings=warnings, extras=extras or {}, eor_not_sent=not_sent,
                                        eor_reported=reported)


def test_the_gate_waits_for_end_of_rib_on_the_own_node(monkeypatch):
    e = make(monkeypatch, r1={"neighbors": {"default": {"10.0.12.2": "established"}}})
    e.drivers["r1"] = EorDrv(e.drivers["r1"], lambda t: {"10.0.12.2": {"ipv4-unicast": "received" if t >= 15 else "pending"}})
    assert gate(e, [leak("n", timeout=60)], warnings={}) == {}
    assert e.clock.now >= 15


def test_end_of_rib_still_pending_at_the_cap_blocks_the_own_node(monkeypatch):
    e = make(monkeypatch, r1={"neighbors": {"default": {"10.0.12.2": "established"}}})
    e.drivers["r1"] = EorDrv(e.drivers["r1"], lambda t: {"10.0.12.2": {"ipv4-unicast": "pending"}})
    neg = leak("n", timeout=30)
    blocked = gate(e, [neg], warnings={})
    assert id(neg) in blocked and "End-of-RIB" in blocked[id(neg)].detail and "not_sent" in blocked[id(neg)].detail


def test_unknown_is_never_settled(monkeypatch):
    e = make(monkeypatch, r1={"neighbors": {"default": {"10.0.12.2": "established"}}})
    e.drivers["r1"] = EorDrv(e.drivers["r1"], lambda t: {"10.0.12.2": {"*": "unknown"}})
    neg = leak("n", timeout=30)
    assert id(neg) in gate(e, [neg], warnings={})


def test_a_peer_declared_not_sent_is_not_waited_for(monkeypatch):
    e = make(monkeypatch, r1={"neighbors": {"default": {"10.0.12.2": "established"}}})
    e.drivers["r1"] = EorDrv(e.drivers["r1"], lambda t: {"10.0.12.2": {"ipv4-unicast": "pending"}})
    assert gate(e, [leak("n", timeout=30)], warnings={}, not_sent={("r1", "default", "10.0.12.2")}) == {}
    assert e.clock.now < 30


def test_pending_on_another_node_is_a_warning(monkeypatch):
    e = make(monkeypatch, r1={"neighbors": {"default": {"10.0.12.2": "established"}}},
             r2={"neighbors": {"default": {"10.0.23.3": "established"}}})
    e.drivers["r2"] = EorDrv(e.drivers["r2"], lambda t: {"10.0.23.3": {"ipv4-unicast": "pending"}})
    neg = leak("n", timeout=30)
    w: dict = {}
    assert gate(e, [neg], warnings=w, extras={"r2": e.drivers["r2"]}) == {}
    assert [(x["code"], x["session"]) for x in w[id(neg)]] == [("gate-eor-pending", "10.0.23.3")]


def test_untracked_is_one_warning_per_run_and_session(monkeypatch):
    e = make(monkeypatch, r1={"neighbors": {"default": {"10.0.12.2": "established"}}})
    e.drivers["r1"] = EorDrv(e.drivers["r1"], lambda t: {"10.0.12.2": {"*": "untracked"}})
    a, b = leak("a", timeout=30), leak("b", timeout=30, prefix="10.77.0.0/16")
    w: dict = {}
    reported: set = set()
    assert gate(e, [a, b], warnings=w, reported=reported) == {}
    assert [x["code"] for x in w.get(id(a), [])] == ["eor-untracked"] and id(b) not in w
    w2: dict = {}
    gate(e, [a, b], warnings=w2, reported=reported)        # a scenario's gate later in the same run
    assert w2 == {}


# ------------------------------------------------------------------------------------------- the declaration

def _cfg(tmp_path, nodes):
    (tmp_path / "t.clab.yml").write_text("name: t\ntopology: {nodes: {r1: {kind: linux}}}\n")
    (tmp_path / "netdryrun.yml").write_text(json.dumps({
        "lab": "t.clab.yml", "nodes": nodes,
        "checks": [{"type": "route", "node": "r1", "prefix": "10.0.0.0/8", "present": False}]}))
    return load(tmp_path / "netdryrun.yml")


def test_the_declaration_is_normalised_per_vrf(tmp_path):
    cfg = _cfg(tmp_path, {"r1": {"peers": {"2001:DB8::0:1": {"eor": "not_sent"}, "red/10.0.0.1": {"eor": "not_sent"}}}})
    assert cfg.eor_not_sent == {("r1", "default", "2001:db8::1"), ("r1", "red", "10.0.0.1")}


@pytest.mark.parametrize("peers", [{"10.0.0.1": {"eor": "sent"}}, {"nope": {"eor": "not_sent"}},
                                   {"10.0.0.1": {"eor": "not_sent", "x": 1}}, {"10.0.0.1": "not_sent"}, []])
def test_a_bad_declaration_is_refused(tmp_path, peers):
    with pytest.raises(ConfigError):
        _cfg(tmp_path, {"r1": {"peers": peers}})


def test_a_declaration_that_matches_no_session_is_an_error(monkeypatch):
    e = make(monkeypatch, r1={"neighbors": {"default": {"10.0.12.2": "established"}}, "routes": {"default": lambda t, p: False}})
    cfg_checks = [leak("n", timeout=30)]
    from netdryrun.config import Config
    rep = runner.run(Config(path=Path("netdryrun.yml"), lab=Path("t.clab.yml"), timeout=30, checks=cfg_checks,
                            eor_not_sent=frozenset({("r1", "default", "10.0.12.9")})),
                     deploy=False, log=e.logs.append, settle=1, hold=3)
    assert rep.status == "error" and "10.0.12.9" in rep.error


def test_neighbor_equality_ignores_end_of_rib():
    assert BgpNeighbor("a", "established", eor={"*": "pending"}) == BgpNeighbor("a", "established")
