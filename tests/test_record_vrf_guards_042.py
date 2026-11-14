"""RT-0076 (oracle FP-042-RECORDVRF): `record` writes the guards in every VRF with BGP sessions, each with its `vrf:`.

On the oracle's fake PE (default VRF: upstream 10.0.12.2; VRF cust: customer 10.1.0.2), these tests kill: guards in the
default VRF only, a VRF guard written without `vrf:` (it would judge the default VRF), a VRF guard evaluated on the
default VRF's state before it is written, the VRF's guards built from the default VRF's routes, and a gap message that
doesn't name the VRF.
"""
import importlib.util
from pathlib import Path

from netdryrun.drivers.base import DriverError, Observation, Route

_PATH = Path(__file__).resolve().parent / "oracles" / "FP-042-RECORDVRF" / "test_oracle_fp_042_recordvrf.py"
_SPEC = importlib.util.spec_from_file_location("oracle_fp_042_recordvrf_unit", _PATH)
o = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(o)


def guards(checks, vrf):
    return sorted(c["prefix"] for c in checks if c.get("present") is False and c.get("vrf", "default") == vrf)


def test_each_vrf_gets_the_default_and_link_subnet_guards_with_its_vrf(monkeypatch):
    # ::/0 too: an eBGP session where IPv6 routes can be read gets the IPv6 default guard (acceptance round B-3)
    data, warnings = o.record(monkeypatch)
    assert guards(data["checks"], "default") == ["0.0.0.0/0", "10.0.12.0/24", "10.1.0.0/24", "::/0"]
    assert guards(data["checks"], "cust") == ["0.0.0.0/0", "10.0.12.0/24", "10.1.0.0/24", "::/0"]
    assert not [w for w in warnings if "INCOMPLETE" in w]


def test_the_leak_into_the_vrf_fails_its_guard_only(monkeypatch):
    data, _ = o.record(monkeypatch)
    leaked = o.PeDrv(leaked=True)
    verdicts = {(c.get("vrf", "default"), c["prefix"]): o.judge(i, c, leaked).passed
                for i, c in enumerate(data["checks"]) if c.get("present") is False and c["prefix"] == "0.0.0.0/0"}
    assert verdicts == {("default", "0.0.0.0/0"): True, ("cust", "0.0.0.0/0"): False}


class DefaultInCustToday(o.PeDrv):
    """VRF cust learns a default from the customer today (the service itself): no guard against it there."""

    def _table(self, vrf):
        return super()._table(vrf) + ([Route("0.0.0.0/0", "bgp", True)] if vrf == "cust" else [])


def test_a_vrf_is_guarded_against_what_it_does_not_learn_today_only(monkeypatch):
    data, warnings = o.record(monkeypatch, DefaultInCustToday())
    assert guards(data["checks"], "cust") == ["10.0.12.0/24", "10.1.0.0/24", "::/0"]
    assert "0.0.0.0/0" in guards(data["checks"], "default")   # judged on the default VRF's own routes
    assert any(w.startswith("pe1 (vrf cust): learns 0.0.0.0/0 via BGP today") for w in warnings)


class CustRoutesUnreadable(o.PeDrv):
    def routes(self, prefix, vrf="default"):
        if vrf == "cust":
            raise DriverError("vtysh: timed out")
        return super().routes(prefix, vrf)


def test_a_vrf_guard_that_cannot_be_evaluated_is_a_named_gap(monkeypatch):
    data, warnings = o.record(monkeypatch, CustRoutesUnreadable())
    assert guards(data["checks"], "cust") == []
    gaps = [w for w in warnings if w.startswith("INCOMPLETE BASELINE: pe1 (vrf cust): the guard against")]
    assert len(gaps) == 4, warnings
    assert guards(data["checks"], "default") == ["0.0.0.0/0", "10.0.12.0/24", "10.1.0.0/24", "::/0"]


class CustRoutesListUnreadable(o.PeDrv):
    def all_routes(self, vrf="default", family=4):
        if vrf == "cust":
            raise DriverError("vtysh: timed out")
        return Observation(self._table(vrf) if family == 4 else [], [])


def test_a_vrf_whose_routes_cannot_be_read_gets_no_guard_and_says_so(monkeypatch):
    data, warnings = o.record(monkeypatch, CustRoutesListUnreadable())
    assert guards(data["checks"], "cust") == []
    assert any(w.startswith("INCOMPLETE BASELINE: pe1 (vrf cust): IPv4 routes could not be read, so no IPv4 guards")
               for w in warnings), warnings
