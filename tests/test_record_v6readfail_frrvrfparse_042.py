"""Unit tests of the fixes for FP-042-RECORDV6READFAIL and FP-042-FRRVRFPARSE (adversary n4i on 57eb8ca, B1, D1, D2).

- record: "IPv6 routes can't be read here" is the driver's own answer (cannot_read_ipv6: RouterOS's not-supported
  text, cEOS's routingDisabled), never a read that failed; a failed IPv6 read is an INCOMPLETE BASELINE line in both
  modes, so --no-routes can't drop ::/0 and the IPv6 link guards with exit 0.
- FRR/SONiC parse_vrfs: every non-blank line is zebra's `show vrf` format, or the answer raises; empty is no VRFs.
"""
import importlib.util
import json
from pathlib import Path

import pytest

from netdryrun import record as rec
from netdryrun.drivers import eos
from netdryrun.drivers.base import (IPV6_ROUTES_UNSUPPORTED, BgpNeighbor, DriverError, NoSuchInstance, Observation,
                                    RoutingDisabled, cannot_read_ipv6)
from netdryrun.drivers.frr import FrrDriver, parse_vrfs
from netdryrun.drivers.routeros import RouterosDriver
from netdryrun.drivers.sonic import SonicDriver
from netdryrun.lab import ExecResult

_PATH = (Path(__file__).resolve().parent / "oracles" / "FP-042-RECORDV6READFAIL"
         / "test_oracle_fp_042_recordv6readfail.py")
_SPEC = importlib.util.spec_from_file_location("oracle_fp_042_recordv6readfail_unit", _PATH)
o = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(o)

FIXTURES = Path(__file__).resolve().parent / "fixtures"
V6_GAP = ("INCOMPLETE BASELINE: {where}: IPv6 routes could not be read, so no IPv6 guards (no default route, no link "
          "subnet) were recorded for it")
READ_GAP = ("INCOMPLETE BASELINE: {where}: could not read IPv6 routes ({e}), so none is recorded as a check: fix the "
            "read and record again, or add checks by hand")


def where(vrf):
    return o.PE if vrf == "default" else f"{o.PE} (vrf {vrf})"


# --- cannot_read_ipv6: the driver's answer, not a failed read ---

def test_routeros_ipv6_route_answer_is_cannot_read():
    with pytest.raises(DriverError) as e:
        RouterosDriver(None, "r1").all_routes(family=6)
    assert str(e.value) == IPV6_ROUTES_UNSUPPORTED.format("routeros") == "IPv6 routes are not supported on routeros yet"
    assert cannot_read_ipv6(e.value)


def test_eos_ipv6_routing_off_is_routing_disabled_and_cannot_read():
    data = json.loads((FIXTURES / "eos_route_red_v6_routing_disabled.json").read_text(encoding="utf-8"))
    with pytest.raises(RoutingDisabled) as e:
        eos.parse_all_routes(json.dumps(data), "RED")
    assert isinstance(e.value, NoSuchInstance)   # everything that read it as NoSuchInstance still does
    assert cannot_read_ipv6(e.value)


@pytest.mark.parametrize("err", [
    DriverError(o.V6_TIMEOUT),
    DriverError("vtysh: timed out"),
    NoSuchInstance("VRF 'svc' does not exist on pe1 (`show vrf` lists: none)"),
    NoSuchInstance("VRF 'RED' is not in the output of `show ipv6 route vrf RED`"),
    DriverError("::/0: IPv6 routes are not supported on routeros yet"),   # routes(), not all_routes()
    DriverError("IPv6 routes are not supported on routeros yet, retry"),
    DriverError("% IPv6 routes are not supported on frr yet"),
    DriverError("unexpected output from `show vrf`: IPv6 routes are not supported on routeros yet"),
])
def test_a_failed_read_is_never_cannot_read(err):
    assert not cannot_read_ipv6(err)


# --- record: a failed IPv6 read is a gap in both modes ---

@pytest.mark.parametrize("shape", o.SHAPES)
@pytest.mark.parametrize("include_routes", [False, True])
def test_a_failed_ipv6_read_is_the_v6_guard_gap_line_in_every_vrf(monkeypatch, shape, include_routes):
    data, warnings = o.record(monkeypatch, shape, v6="fail", include_routes=include_routes)
    gaps = rec.baseline_gaps(warnings)
    want = [V6_GAP.format(where=where(v)) for v in o.vrfs_of(shape)]
    if include_routes:
        want += [READ_GAP.format(where=where(v), e=o.V6_TIMEOUT) for v in o.vrfs_of(shape)]
    else:   # the cause stays named in the plain line
        assert [w for w in warnings if w.startswith(f"{o.PE}") and "could not read IPv6" in w] == [
            f"{where(v)}: could not read IPv6 routes ({o.V6_TIMEOUT})" for v in o.vrfs_of(shape)]
    assert sorted(gaps) == sorted(want), warnings
    assert not [c for c in data["checks"] if ":" in str(c.get("prefix", ""))]   # no IPv6 guard built on nothing
    assert rec.render(data, warnings).splitlines()[0].startswith("# INCOMPLETE BASELINE")


class V6NoSuchInstance(o.PeDrv):
    """A VRF the IPv6 answer doesn't list (FRR's _confirm_vrf, EOS's _vrf): a read that failed, not "IPv6 off"."""

    def all_routes(self, vrf="default", family=4):
        if family == 6:
            raise NoSuchInstance(f"VRF {vrf!r} does not exist on pe1 (`show vrf` lists: none)")
        return super().all_routes(vrf, family)


class V6RoutingDisabled(o.PeDrv):
    def all_routes(self, vrf="default", family=4):
        if family == 6:
            raise RoutingDisabled(f"VRF {vrf!r} has routing disabled")
        return super().all_routes(vrf, family)


def test_a_no_such_instance_ipv6_answer_is_a_gap_but_routing_disabled_is_not(monkeypatch):
    _, warnings = o.record(monkeypatch, "svc", drv_class=V6NoSuchInstance)
    assert sorted(rec.baseline_gaps(warnings)) == sorted(V6_GAP.format(where=where(v)) for v in o.vrfs_of("svc"))
    data, warnings = o.record(monkeypatch, "svc", drv_class=V6RoutingDisabled)
    assert not rec.baseline_gaps(warnings), warnings
    assert not [c for c in data["checks"] if ":" in str(c.get("prefix", ""))]


# --- _guards: the skip needs both "nothing says IPv6" and the driver's can't-read answer ---

class Clean:
    name = "frr"

    def routes(self, prefix, vrf="default"):
        return Observation([], [])


V4_ONLY = {"10.0.0.2": BgpNeighbor("10.0.0.2", "established", {"ipv4-unicast": 1})}
V6_PEER = {"2001:db8::2": BgpNeighbor("2001:db8::2", "established", {"ipv6-unicast": 0})}
LINKS = ["10.0.12.0/30", "2001:db8:1::/64"]


def guards(neighbors, no_v6):
    warnings: list[str] = []
    out = rec._guards("r1", Clean(), neighbors, {4: set()}, LINKS, warnings, sleep=lambda s: None, no_v6=no_v6)
    return [g["prefix"] for g in out], warnings


def test_guards_skip_ipv6_silently_only_on_the_drivers_answer():
    assert guards(V4_ONLY, no_v6=True) == (["0.0.0.0/0", "10.0.12.0/30"], [])
    prefixes, warnings = guards(V4_ONLY, no_v6=False)
    assert prefixes == ["0.0.0.0/0", "10.0.12.0/30"]
    assert warnings == [V6_GAP.format(where="r1")]


def test_guards_keep_the_gap_where_the_vrf_carries_ipv6_even_if_the_driver_cannot_read_it():
    for no_v6 in (True, False):
        assert guards(V6_PEER, no_v6=no_v6) == (["0.0.0.0/0", "10.0.12.0/30"], [V6_GAP.format(where="r1")])


def test_guards_default_is_fail_closed():
    warnings: list[str] = []
    rec._guards("r1", Clean(), V4_ONLY, {4: set()}, [], warnings, sleep=lambda s: None)
    assert warnings == [V6_GAP.format(where="r1")]


# --- FRR parse_vrfs: zebra's format or an error ---

@pytest.mark.parametrize("text,want", [
    ("", {}),
    ("\n\n", {}),
    ("vrf cust id 3 table 1001\n", {"cust": True}),
    ("vrf red id 5 table 1001 (configured)\n", {"red": True}),
    ("vrf blue inactive\n", {"blue": False}),
    ("vrf blue inactive (configured)\n", {"blue": False}),
    ("netns-based vrfs\nvrf red id 5 netns /run/netns/red (configured)\n", {"red": True}),
    ("  vrf green id 7 table 7  \n", {"green": True}),
    ("vrf default id 0 table 254\nvrf red id 5 table 1001\n", {"default": True, "red": True}),
])
def test_parse_vrfs_reads_zebras_lines(text, want):
    assert parse_vrfs(text) == want


@pytest.mark.parametrize("text", [
    "% Unknown command: show vrf\n",
    "vrf red id 5 table 1001\n% Unknown command\n",   # one good line doesn't excuse the rest
    "vrf red id 5 table 1001\nvrf blue\n",
    "vrf red id 5 table 1001 extra\n",
    "vrf red id x table 1001\n",
    "vrf red\n",
    "vrf  \n",
    "vrfs red id 5 table 1001\n",
    '{"red": {"vrfId": 5}}\n',
    "netns-based vrfs extra\n",
])
def test_parse_vrfs_raises_on_anything_else(text):
    with pytest.raises(DriverError, match=r"unexpected output from `show vrf`"):
        parse_vrfs(text)


class AnswerLab:
    def __init__(self, text):
        self.text = text

    def exec(self, node, cmd, timeout=60, input=None):
        return ExecResult(cmd, 0, self.text, "")


@pytest.mark.parametrize("cls", [FrrDriver, SonicDriver])
def test_confirm_vrf_on_an_unrecognised_answer_is_a_failed_read_not_no_such_vrf(cls):
    with pytest.raises(DriverError) as e:
        cls(AnswerLab("Exiting: failed to connect to any daemons.\n"), "r1")._confirm_vrf("red", [])
    assert not isinstance(e.value, NoSuchInstance)


def test_record_writes_the_vrf_list_gap_for_an_unrecognised_show_vrf(monkeypatch):
    class FrrPe(FrrDriver):
        def __init__(self):
            super().__init__(AnswerLab("% Unknown command: show vrf\n"), o.PE)
            self.state = o.PeDrv("svc", v6="ok")

        def bgp_neighbors(self, vrf="default"):
            return self.state.bgp_neighbors(vrf)

        def bgp_received(self, neighbor, afi="ipv4-unicast", vrf="default"):
            return self.state.bgp_received(neighbor, afi, vrf)

        def all_routes(self, vrf="default", family=4):
            return self.state.all_routes(vrf, family)

        def routes(self, prefix, vrf="default"):
            return self.state.routes(prefix, vrf)

    monkeypatch.setattr(rec, "Lab", o.PeLab)
    monkeypatch.setattr(rec, "detect", lambda node: "frr")
    monkeypatch.setattr(rec, "for_node", lambda lab, name, *a: FrrPe())
    _, warnings = rec.record(Path("t.clab.yml"), include_routes=False, guards=True, sleep=lambda s: None)
    gaps = rec.baseline_gaps(warnings)
    assert len(gaps) == 1 and gaps[0].startswith(f"INCOMPLETE BASELINE: {o.PE}: could not list its VRFs (unexpected "
                                                 "output from `show vrf`: % Unknown command: show vrf)"), warnings
