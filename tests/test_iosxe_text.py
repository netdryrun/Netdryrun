"""IOS XE text answers: what each one means, and the strict parsers for the ones we have captured.

The hand-written samples below have the structure of a real Catalyst 8000V (IOS XE 17.15) capture taken from a
Cisco DevNet always-on sandbox (the captures themselves are unpublished until DevNet answers); the content is
invented. Rules under test (research/iosxe-capture/devnet/CLASSIFICATION-iosxe-17.15.md):

- IOS prints every error as text; the answer text is the only signal. Anything starting with `%` is a failed
  collection unless it is one of the few answers that prove something.
- "% BGP not active" is not "no routes". Unknown VRF is not "absent". Only exact-prefix answers prove absence.
- A line a parser doesn't know raises; it is never skipped (the genieparser lesson).
"""
from __future__ import annotations

import dataclasses
import ipaddress
import os
from pathlib import Path

import pytest

from netdryrun.drivers.base import DriverError
from netdryrun.drivers.iosxe_text import (
    Answer,
    classify,
    find_routes,
    parse_route_table,
    parse_vrf_list,
)

LEGEND = """Codes: L - local, C - connected, S - static, R - RIP, M - mobile, B - BGP
       D - EIGRP, EX - EIGRP external, O - OSPF, IA - OSPF inter area
       N1 - OSPF NSSA external type 1, N2 - OSPF NSSA external type 2
       E1 - OSPF external type 1, E2 - OSPF external type 2, m - OMP
       n - NAT, Ni - NAT inside, No - NAT outside, Nd - NAT DIA
       i - IS-IS, su - IS-IS summary, L1 - IS-IS level-1, L2 - IS-IS level-2
       ia - IS-IS inter area, * - candidate default, U - per-user static route
       H - NHRP, G - NHRP registered, g - NHRP registration summary
       o - ODR, P - periodic downloaded static route, l - LISP
       a - application route
       + - replicated route, % - next hop override, p - overrides from PfR
       & - replicated local route overrides by connected
"""

TABLE = LEGEND + """
Gateway of last resort is 192.0.2.254 to network 0.0.0.0

S*    0.0.0.0/0 [1/0] via 192.0.2.254
      10.0.0.0/8 is variably subnetted, 4 subnets, 2 masks
C        10.1.1.0/24 is directly connected, Loopback12
L        10.1.1.12/32 is directly connected, Loopback12
B        10.8.0.0/16 [20/50] via 192.0.2.1, 00:10:00
                     [20/50] via 192.0.2.2, 00:10:00
O IA     10.9.0.0/24 [110/20] via 192.0.2.3, 00:00:09, GigabitEthernet2
      99.0.0.0/32 is subnetted, 2 subnets
C        99.99.99.91 is directly connected, Loopback90
C        99.99.99.99 is directly connected, Loopback99
"""

INVALID = """show bgp vrf NDRNOPE ipv4 unicast summary
                      ^
% Invalid input detected at '^' marker.
"""


# ---- classify -------------------------------------------------------------------------------------------------
def test_bgp_not_active_is_its_own_state_not_an_empty_table():
    a = classify("show bgp all summary", "% BGP not active\n")
    assert a.kind == "bgp_not_active"
    assert not a.ok


def test_exact_route_absence_needs_the_mask_form_answer():
    a = classify("show ip route 10.99.0.0 255.255.0.0", "% Subnet not in table\n")
    assert a.kind == "absent_route"


def test_cef_absence_has_no_space_after_the_percent():
    assert classify("show ip cef 10.99.0.0/16 detail", "%Prefix not found\n").kind == "absent_fib"


def test_no_such_vrf_proves_the_vrf_is_absent():
    a = classify("show vrf detail NDRNOPE", "% No VRF named NDRNOPE\n")
    assert a.kind == "absent_vrf" and a.detail == "NDRNOPE"


def test_unknown_vrf_in_a_route_command_is_a_failure_not_absence():
    a = classify("show ip route vrf NDRNOPE 10.0.0.0 255.0.0.0", "% IP routing table vrf NDRNOPE does not exist\n")
    assert a.kind == "unknown_vrf" and a.detail == "NDRNOPE" and not a.ok


def test_invalid_input_keeps_the_caret_and_is_ambiguous():
    a = classify("show bgp vrf NDRNOPE ipv4 unicast summary", INVALID)
    assert a.kind == "invalid_input"
    assert a.caret_column == 22


def test_unknown_percent_line_is_an_error_never_ignored():
    a = classify("show something", "% Some new message from a newer release\n")
    assert a.kind == "other_error" and not a.ok


def test_percent_in_a_legend_line_is_not_an_error():
    assert classify("show ip route", TABLE).kind == "ok"


def test_error_after_normal_output_is_still_an_error():
    a = classify("show x", "line one\n% Invalid input detected at '^' marker.\n")
    assert a.kind in ("invalid_input", "other_error")


def test_empty_answer_is_not_ok():
    a = classify("show vrf", "")
    assert a.kind == "empty" and not a.ok


def test_pager_prompt_means_truncated():
    a = classify("show ip route", TABLE + "--More--\n")
    assert a.kind == "truncated" and not a.ok


def test_every_non_ok_kind_has_ok_false():
    for text in ("% BGP not active\n", "% Subnet not in table\n", "%Prefix not found\n", "% No VRF named X\n",
                 "% IP routing table vrf X does not exist\n", INVALID, "% weird\n", "", "x\n--More--\n"):
        assert classify("cmd", text).ok is False


# ---- route table ----------------------------------------------------------------------------------------------
def test_table_parses_every_route_with_its_protocol():
    routes = parse_route_table(TABLE)
    by = {(r.prefix, r.protocol) for r in routes}
    assert ("0.0.0.0/0", "static") in by
    assert ("10.1.1.0/24", "connected") in by
    assert ("10.1.1.12/32", "local") in by
    assert ("10.8.0.0/16", "bgp") in by
    assert ("10.9.0.0/24", "ospf") in by


def test_children_of_a_subnetted_header_take_the_header_mask():
    # "99.99.99.91" is printed without a length under "99.0.0.0/32 is subnetted"; a parser that dropped the mask
    # would never find it as an exact /32 (a false "absent")
    routes = parse_route_table(TABLE)
    assert any(r.prefix == "99.99.99.91/32" for r in routes)
    assert not any(r.prefix == "99.99.99.91/24" for r in routes)


def test_ecmp_second_next_hop_line_belongs_to_the_route_above():
    routes = parse_route_table(TABLE)
    r = next(r for r in routes if r.prefix == "10.8.0.0/16")
    assert r.next_hops == ["192.0.2.1", "192.0.2.2"]


def test_exact_lookup_does_not_match_covering_or_longer_routes():
    routes = parse_route_table(TABLE)
    assert [r.prefix for r in find_routes(routes, "10.0.0.0/8")] == []          # only a header, not a route
    assert [r.prefix for r in find_routes(routes, "10.1.1.0/25")] == []         # longer than the connected /24
    assert [r.prefix for r in find_routes(routes, "10.8.0.0/16")] == ["10.8.0.0/16"]
    assert [r.prefix for r in find_routes(routes, "0.0.0.0/0")] == ["0.0.0.0/0"]


def test_a_table_with_no_routes_is_an_observed_empty_table_not_an_error():
    text = LEGEND + "\nGateway of last resort is not set\n"
    assert parse_route_table(text) == []


def test_unknown_line_in_a_table_raises():
    with pytest.raises(DriverError):
        parse_route_table(TABLE + "Z        10.5.0.0/24 something a newer release prints\n")


@pytest.mark.parametrize("junk", [
    "Something a newer release prints\n",                    # column 0, no address
    "      an indented line of unknown meaning\n",            # indented, not a header or continuation
    "B        10.8.0.0/16 [20/50] via\n",                      # a route whose next hop is cut
    "C        10.1.1.0/24 is directly connected,\n",           # a connected route whose interface is cut
])
def test_any_unrecognised_line_in_a_table_raises_not_skipped(junk):
    with pytest.raises(DriverError):
        parse_route_table(TABLE + junk)


def test_text_that_is_not_a_table_raises():
    for text in ("", "% BGP not active\n", "hello\n", "   \n"):
        with pytest.raises(DriverError):
            parse_route_table(text)


def test_truncated_table_raises():
    with pytest.raises(DriverError):
        parse_route_table(TABLE + "--More--\n")


def test_error_answer_given_to_the_table_parser_raises():
    with pytest.raises(DriverError):
        parse_route_table("% IP routing table vrf X does not exist\n")


def test_prefixes_are_canonical_networks():
    for r in parse_route_table(TABLE):
        ipaddress.ip_network(r.prefix)


# ---- vrf list -------------------------------------------------------------------------------------------------
VRFS = """  Name                             Default RD            Protocols   Interfaces
  Mgmt-vrf                         <not set>             ipv4,ipv6
  RED                              65001:1               ipv4        Gi4
                                                                     Gi5
"""


def test_vrf_list_gives_names_and_interfaces():
    v = parse_vrf_list(VRFS)
    assert set(v) == {"Mgmt-vrf", "RED"}
    assert v["RED"] == ["Gi4", "Gi5"]
    assert v["Mgmt-vrf"] == []


def test_vrf_list_with_an_unknown_header_raises():
    with pytest.raises(DriverError):
        parse_vrf_list("  Name   Something   Else\n  A  x  y  z\n")


def test_vrf_list_empty_or_error_raises():
    for text in ("", "% No VRF named X\n"):
        with pytest.raises(DriverError):
            parse_vrf_list(text)


def test_answer_dataclass_is_frozen():
    a = Answer("ok", "", None)
    with pytest.raises(dataclasses.FrozenInstanceError):
        a.kind = "x"  # type: ignore[misc]


# ---- local only: the real first capture (unpublished; skipped where it is not present) ---------------------------


def _real_dir():
    env = os.environ.get("NDR_IOSXE_CAPTURES")
    base = Path(env) if env else Path(__file__).resolve().parents[3] / "research" / "iosxe-capture" / "out" / "devnet" / "iosxe-always-on"
    runs = sorted(p for p in base.glob("*") if p.is_dir()) if base.is_dir() else []
    return runs[-1] if runs else None


REAL = _real_dir()
real_only = pytest.mark.skipif(REAL is None, reason="no real DevNet capture on this machine (unpublished)")


def _real(name):
    return (REAL / f"{name}.txt").read_text(encoding="utf-8")


@real_only
@pytest.mark.parametrize("name,command,kind", [
    ("summary_all", "show bgp all summary", "bgp_not_active"),
    ("bgp_table", "show bgp ipv4 unicast", "bgp_not_active"),
    ("nbr_unknown", "show bgp ipv4 unicast neighbors 10.255.255.254", "bgp_not_active"),
    ("summary_vrf_nope", "show bgp vrf NDRNOPE ipv4 unicast summary", "invalid_input"),
    ("bgp_invalid", "show bgp bogus", "invalid_input"),
    ("route_absent", "show ip route 10.99.0.0 255.255.0.0", "absent_route"),
    ("route_absent_slash", "show ip route 10.99.0.0/16", "invalid_input"),
    ("route_novrf", "show ip route vrf NDRNOPE 10.0.0.0 255.0.0.0", "unknown_vrf"),
    ("route_all_novrf", "show ip route vrf NDRNOPE", "unknown_vrf"),
    ("cef_absent", "show ip cef 10.99.0.0/16 detail", "absent_fib"),
    ("cef_novrf", "show ip cef vrf NDRNOPE 10.0.0.0/8 detail", "invalid_input"),
    ("vrf_nope", "show vrf detail NDRNOPE", "absent_vrf"),
    ("vrf_brief_nope", "show vrf NDRNOPE", "absent_vrf"),
    ("route_all", "show ip route", "ok"),
    ("vrf_list", "show vrf", "ok"),
])
def test_real_capture_classification(name, command, kind):
    assert classify(command, _real(name)).kind == kind


@real_only
def test_real_route_table_parses_and_finds_the_exact_32_under_a_subnetted_header():
    routes = parse_route_table(_real("route_all"))
    assert routes, "the sandbox router has connected routes"
    assert any(r.prefix == "0.0.0.0/0" and r.protocol == "static" for r in routes)
    # the /32 children printed without a mask must be found as /32
    no_mask = [ln for ln in _real("route_all").splitlines() if "directly connected" in ln and "/" not in ln.split()[1]]
    assert no_mask, "the capture has routes printed without a mask"
    for ln in no_mask:
        addr = ln.split()[1]
        assert find_routes(routes, f"{addr}/32"), addr


@real_only
def test_real_vrf_list_parses():
    assert "Mgmt-vrf" in parse_vrf_list(_real("vrf_list"))
