"""Guards for oracle FP-042-RECORDV6READFAIL: they pass before and after its fix.

The fast-fix gate needs every test in tests/oracles/FP-042-RECORDV6READFAIL/ to fail on the fix's parent, so the
guards live here. This file is in the oracle's `evidence:`, so the fix can't change it. The fake PE lab and driver
come from the oracle's own module.

What must keep working:
- a driver that can't read IPv6 routes at all keeps today's output exactly, with routes recorded and with
  --no-routes: RouterOS ("IPv6 routes are not supported on routeros yet"), and cEOS whose IPv6 routing is off
  (`routingDisabled: true` in the IPv6 route answer, the live capture tests/fixtures/eos_route_red_v6_routing_disabled
  .json, read by the real EOS parser: NoSuchInstance): no IPv6 check, no INCOMPLETE BASELINE line, the same plain
  warnings;
- a failed IPv6 read on FRR doesn't change the IPv4 checks, and with routes recorded it is still a gap (exit 1);
- where the IPv6 routes read (empty), --no-routes keeps the ::/0 and IPv6 link guards in every VRF and no gap line;
- every check recorded passes on the recording state.
"""
import importlib.util
import json
from pathlib import Path

import pytest

from netdryrun.drivers import eos

_PATH = (Path(__file__).resolve().parent / "oracles" / "FP-042-RECORDV6READFAIL"
         / "test_oracle_fp_042_recordv6readfail.py")
_SPEC = importlib.util.spec_from_file_location("oracle_fp_042_recordv6readfail", _PATH)
o = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(o)

EOS_V6_OFF = json.loads((Path(__file__).resolve().parent / "fixtures" / "eos_route_red_v6_routing_disabled.json")
                        .read_text(encoding="utf-8"))


def eos_v6_off(vrf):
    """The live cEOS IPv6 route answer of a VRF whose IPv6 routing is off, for `vrf`."""
    return json.dumps({"vrfs": {vrf: EOS_V6_OFF["vrfs"]["RED"]}})


class EosV6Off(o.PeDrv):
    """The PE as cEOS with IPv6 routing off: the IPv6 route answers go through the real EOS parser."""
    name = "eos"

    def all_routes(self, vrf="default", family=4):
        if family == 6:
            return o.Observation(eos.parse_all_routes(eos_v6_off(vrf), vrf), [])
        return super().all_routes(vrf, family)

    def routes(self, prefix, vrf="default"):
        if ":" in prefix:
            eos.parse_all_routes(eos_v6_off(vrf), vrf)   # raises NoSuchInstance, as the driver's route read does
        return super().routes(prefix, vrf)


def eos_off_msg(vrf):
    try:
        eos.parse_all_routes(eos_v6_off(vrf), vrf)
    except o.DriverError as e:
        return str(e)
    raise AssertionError("the EOS parser read routes from a VRF with routing disabled")


def where(vrf):
    return o.PE if vrf == "default" else f"{o.PE} (vrf {vrf})"


CANT_READ = {"routeros": (o.PeDrv, "unsupported", lambda vrf: o.V6_UNSUPPORTED), "eos-v6-off": (EosV6Off, "ok", eos_off_msg)}


def v6_checks(checks):
    return [c for c in checks if ":" in str(c.get("prefix", ""))]


@pytest.mark.parametrize("kind", sorted(CANT_READ))
@pytest.mark.parametrize("shape", o.SHAPES)
def test_no_routes_where_ipv6_cannot_be_read_keeps_todays_output(monkeypatch, shape, kind):
    cls, v6, msg = CANT_READ[kind]
    data, warnings = o.record(monkeypatch, shape, v6=v6, drv_class=cls)
    assert not v6_checks(data["checks"]), data["checks"]
    assert not o.rec.baseline_gaps(warnings), warnings
    assert not o.gap_lines(data, warnings)
    assert [w for w in warnings if "IPv6" in w or "::" in w] == [
        f"{where(v)}: could not read IPv6 routes ({msg(v)})" for v in o.vrfs_of(shape)], warnings
    # the IPv4 checks are those of a node whose IPv6 routes read
    readable, _ = o.record(monkeypatch, shape, v6="ok")
    assert data["checks"] == [c for c in readable["checks"] if c not in v6_checks(readable["checks"])]


@pytest.mark.parametrize("kind", sorted(CANT_READ))
@pytest.mark.parametrize("shape", o.SHAPES)
def test_routes_mode_where_ipv6_cannot_be_read_keeps_todays_gap_lines(monkeypatch, shape, kind):
    cls, v6, msg = CANT_READ[kind]
    data, warnings = o.record(monkeypatch, shape, v6=v6, include_routes=True, drv_class=cls)
    assert not v6_checks(data["checks"]), data["checks"]
    assert sorted(o.rec.baseline_gaps(warnings)) == sorted(
        f"INCOMPLETE BASELINE: {where(v)}: could not read IPv6 routes ({msg(v)}), so none is recorded as a "
        "check: fix the read and record again, or add checks by hand" for v in o.vrfs_of(shape)), warnings


@pytest.mark.parametrize("shape", o.SHAPES)
def test_a_failed_ipv6_read_leaves_the_ipv4_checks_alone(monkeypatch, shape):
    data, _ = o.record(monkeypatch, shape, v6="fail")
    readable, _ = o.record(monkeypatch, shape, v6="ok")
    assert [c for c in data["checks"] if c not in v6_checks(data["checks"])] == \
        [c for c in readable["checks"] if c not in v6_checks(readable["checks"])]


@pytest.mark.parametrize("shape", o.SHAPES)
def test_a_failed_ipv6_read_with_routes_recorded_is_still_a_gap(monkeypatch, shape):
    data, warnings = o.record(monkeypatch, shape, v6="fail", include_routes=True)
    for v in o.vrfs_of(shape):
        assert f"INCOMPLETE BASELINE: {where(v)}: could not read IPv6 routes ({o.V6_TIMEOUT}), so none is recorded " \
               "as a check: fix the read and record again, or add checks by hand" in o.rec.baseline_gaps(warnings)


@pytest.mark.parametrize("shape", o.SHAPES)
def test_where_ipv6_reads_no_routes_keeps_every_v6_guard_and_no_gap(monkeypatch, shape):
    data, warnings = o.record(monkeypatch, shape, v6="ok")
    assert not o.rec.baseline_gaps(warnings), warnings
    for v in o.vrfs_of(shape):
        assert len(o.absent_guard(data["checks"], v, "::/0")) == 1, (v, data["checks"])
        assert len(o.absent_guard(data["checks"], v, o.V6_LINK)) == 1, (v, data["checks"])


@pytest.mark.parametrize("shape", o.SHAPES)
@pytest.mark.parametrize("v6", ["ok", "fail", "unsupported"])
def test_every_recorded_check_passes_on_the_recording_state(monkeypatch, shape, v6):
    data, _ = o.record(monkeypatch, shape, v6=v6)
    for i, raw in enumerate(data["checks"]):
        r = o.judge(i, raw, o.PeDrv(shape))
        assert r.passed, (raw, r.detail)
