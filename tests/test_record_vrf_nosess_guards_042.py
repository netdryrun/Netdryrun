"""Oracle FP-042-RECORDVRFNOSESS (adversary n4c on cf460d6, B1): `record` writes the guards in every VRF with a BGP
instance, sessions or not, each with its `vrf:`.

On the oracle's fake PE (shape "vrf": the default VRF has an eBGP upstream, VRF svc has a BGP instance, no session and
an imported 10.10.0.0/24; shape "default": VRF cust has the customer session, the default VRF has a BGP instance, no
session and an imported route; VRF mgmt has no BGP instance), these tests kill: guards only where the VRF has
sessions, a sessionless VRF's guard without `vrf:`, a sessionless VRF's guards judged on another VRF's routes, no
::/0 guard where the sessionless VRF holds IPv6 BGP routes, a guard in a VRF without a BGP instance, guards written
with --no-guards, an unnamed gap message, and the guards of a sessionless VRF counted as state of the node (which
would hide a node the baseline misses).
"""
import importlib.util
from pathlib import Path

from netdryrun import record as rec
from netdryrun.drivers.base import DriverError, Observation, Route

_PATH = (Path(__file__).resolve().parent / "oracles" / "FP-042-RECORDVRFNOSESS"
         / "test_oracle_fp_042_recordvrfnosess.py")
_SPEC = importlib.util.spec_from_file_location("oracle_fp_042_recordvrfnosess_unit", _PATH)
o = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(o)

LINKS = ["10.0.12.0/24", "10.1.0.0/24"]


def guards(checks, vrf):
    return sorted(c["prefix"] for c in checks if c.get("present") is False and c.get("vrf", "default") == vrf)


def run(monkeypatch, drv, guards_on=True):
    monkeypatch.setattr(rec, "Lab", o.PeLab)
    monkeypatch.setattr(rec, "detect", lambda node: "frr")
    monkeypatch.setattr(rec, "for_node", lambda lab, name, *a: drv)
    return rec.record(Path("t.clab.yml"), guards=guards_on, sleep=lambda s: None)


def test_a_sessionless_vrf_gets_the_default_and_link_subnet_guards_with_its_vrf(monkeypatch):
    data, warnings = run(monkeypatch, o.PeDrv("vrf"))
    svc = [c for c in data["checks"] if c.get("vrf") == "svc" and c.get("present") is False]
    assert sorted(c["prefix"] for c in svc) == ["0.0.0.0/0", *LINKS]
    assert all(c == {"type": "route", "node": "pe1", "prefix": c["prefix"], "protocol": "bgp", "present": False,
                     "vrf": "svc"} for c in svc)
    assert guards(data["checks"], "default") == ["0.0.0.0/0", *LINKS, "::/0"]   # eBGP upstream: ::/0 too (B-3)
    assert not [w for w in warnings if "INCOMPLETE" in w or rec.MISSING_NODE in w], warnings


def test_a_default_vrf_without_sessions_gets_its_guards_without_vrf(monkeypatch):
    data, warnings = run(monkeypatch, o.PeDrv("default"))
    assert guards(data["checks"], "default") == ["0.0.0.0/0", *LINKS]
    assert guards(data["checks"], "cust") == ["0.0.0.0/0", *LINKS, "::/0"]
    assert not [w for w in warnings if "INCOMPLETE" in w], warnings


def test_the_leak_into_the_sessionless_vrf_fails_its_guard_only(monkeypatch):
    for shape, vrf in o.SESSIONLESS.items():
        data, _ = run(monkeypatch, o.PeDrv(shape))
        leaked = o.PeDrv(shape, leaked=True)
        verdicts = {c.get("vrf", "default"): o.judge(i, c, leaked).passed
                    for i, c in enumerate(data["checks"]) if c.get("present") is False and c["prefix"] == "0.0.0.0/0"}
        assert verdicts[vrf] is False, (shape, verdicts)
        assert len(verdicts) == 2 and all(v for k, v in verdicts.items() if k != vrf), (shape, verdicts)


class SvcLearnsADefault(o.PeDrv):
    """VRF svc imports a default today (its service): no default guard there, the link guards stay."""

    def _table(self, vrf):
        return super()._table(vrf) + ([Route("0.0.0.0/0", "bgp", True)] if vrf == "svc" else [])


def test_a_sessionless_vrf_is_judged_on_its_own_routes(monkeypatch):
    data, warnings = run(monkeypatch, SvcLearnsADefault("vrf"))
    assert guards(data["checks"], "svc") == LINKS
    assert "0.0.0.0/0" in guards(data["checks"], "default")
    assert any(w.startswith("pe1 (vrf svc): learns 0.0.0.0/0 via BGP today") for w in warnings), warnings


class SvcHasIpv6(o.PeDrv):
    """VRF svc also imports an IPv6 route: IPv6 is carried there, so ::/0 is guarded too."""

    def all_routes(self, vrf="default", family=4):
        if family == 6 and vrf == "svc":
            return Observation([Route("2001:db8:10::/48", "bgp", True)], [])
        return super().all_routes(vrf, family)

    def routes(self, prefix, vrf="default"):
        if ":" in prefix:
            want = [Route("2001:db8:10::/48", "bgp", True)] if vrf == "svc" else []
            return Observation([r for r in want if r.prefix == prefix], [])
        return super().routes(prefix, vrf)


def test_a_sessionless_vrf_with_ipv6_bgp_routes_gets_the_ipv6_default_guard(monkeypatch):
    data, _ = run(monkeypatch, SvcHasIpv6("vrf"))
    assert guards(data["checks"], "svc") == ["0.0.0.0/0", *LINKS, "::/0"]


def test_no_guard_in_a_vrf_without_a_bgp_instance_or_with_no_guards(monkeypatch):
    data, warnings = run(monkeypatch, o.PeDrv("vrf"))
    assert not [c for c in data["checks"] if c.get("vrf") == "mgmt"]
    assert not [w for w in warnings if "mgmt" in w]
    data, _ = run(monkeypatch, o.PeDrv("vrf"), guards_on=False)
    assert not [c for c in data["checks"] if c.get("present") is False]


class SvcGuardUnreadable(o.PeDrv):
    def routes(self, prefix, vrf="default"):
        if vrf == "svc":
            raise DriverError("vtysh: timed out")
        return super().routes(prefix, vrf)


def test_a_sessionless_vrf_guard_that_cannot_be_evaluated_is_a_named_gap(monkeypatch):
    data, warnings = run(monkeypatch, SvcGuardUnreadable("vrf"))
    assert guards(data["checks"], "svc") == []
    gaps = [w for w in warnings if w.startswith("INCOMPLETE BASELINE: pe1 (vrf svc): the guard against")]
    assert len(gaps) == 3, warnings


class NothingYet(o.PeDrv):
    """A BGP instance with no session and no BGP route anywhere (BGP still starting, or no BGP on a driver that
    answers an empty table for that): only guards could be written."""

    def vrfs(self):
        return Observation([], [])

    def _sessions(self, vrf):
        return {}

    def _table(self, vrf):
        return []


def test_guards_alone_are_no_state_a_node_with_nothing_else_is_still_missed(monkeypatch):
    data, warnings = run(monkeypatch, NothingYet("vrf"))
    assert guards(data["checks"], "default") == ["0.0.0.0/0", *LINKS]
    assert [w for w in warnings if w.startswith(f"{rec.MISSING_NODE}: pe1:")], warnings


def test_a_sessionless_node_with_bgp_routes_is_not_missed(monkeypatch):
    class RoutesOnly(NothingYet):
        def _table(self, vrf):
            return [Route("10.10.0.0/24", "bgp", True)]

    data, warnings = run(monkeypatch, RoutesOnly("vrf"))
    assert {"type": "route", "node": "pe1", "prefix": "10.10.0.0/24", "protocol": "bgp"} in data["checks"]
    assert not [w for w in warnings if rec.MISSING_NODE in w], warnings
