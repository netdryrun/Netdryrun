"""Must-fail matrix per driver: every check type, through every driver's real parser, on real device output.

`test_invariants.py` proves the verdict logic on a driver-agnostic fake. That can't see a driver that reads
a violation as something else (0.3.1's cold review: SR Linux EVPN counts read as 0, a pass on `max`). Here
each cell is:

- device output captured from the real NOS (`tests/fixtures/`), as is or with one edit that puts the
  violation in it (a session no longer Established, zero replies);
- the real driver class, answering from that output through a fake `docker exec`;
- the check through the real validator and the real scheduler (positive checks through `run_check`,
  post-convergence checks through `converge_then_hold`), on a fake clock.

A MUST_FAIL cell must end `failed`. A MUST_PASS cell is the control: the same output without the violation
passes, so a cell can't fail only because the fixture no longer parses (that is what a NOS update would
do, and it must show up here as a red control, not as a quiet "fails anyway").

Meta-test: every registered driver × every check type needs at least one cell of each kind.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import pytest
from test_checks import FakeClock
from test_verdict_drivers import Lab

from netdryrun.checks import converge_then_hold, is_post_convergence, run_check
from netdryrun.config import AFIS, CHECK_TYPES, _validate_check
from netdryrun.drivers import DRIVERS, DriverError, check_supported
from netdryrun.lab import Node

FIXTURES = Path(__file__).parent / "fixtures"


def fx(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def session_down(text: str) -> str:
    """The same capture with every BGP session no longer Established (the NOS's own state field)."""
    out, n = re.subn(r'("(?:bgpState|peerState|session-state)"\s*:\s*")[Ee]stablished"', r'\1Active"', text)
    assert n, "no session state field to edit: has the capture's format changed?"
    return out


def frr_family(text: str, family: str) -> str:
    """The same FRR capture with each neighbor's IPv4 unicast family reported as another family (the
    counter fields are the same for every family in `show bgp neighbors json`)."""
    out, n = re.subn(r'("addressFamilyInfo"\s*:\s*\{\s*")ipv4Unicast"', rf'\1{family}"', text)
    assert n, "no addressFamilyInfo to edit"
    return out


def no_replies(text: str) -> str:
    out, n = re.subn(r"(\d+) packets transmitted, \d+ (packets )?received", r"\1 packets transmitted, 0 \2received", text)
    assert n, "no ping statistics line to edit"
    return re.sub(r"^\d+ bytes from .*\n", "", out, flags=re.M)


# Answers that are not captures, kept to the minimum and named so a reader sees them
EOS_NO_V6_PEERS = '{"vrfs": {"default": {"vrf": "default", "peers": {}}}}'   # `show ipv6 bgp summary` with no IPv6 peers
FRR_NO_BGP_PATH = "{}"                                                       # `show bgp ... <prefix> json` for an unknown prefix
FRR_NO_ROUTE = "{}"                                                          # `show ip route <prefix> json` with no route


def frr_like():
    """Command needles for FRR and SONiC (vtysh JSON)."""
    def neighbors(text):
        return [("neighbors json", text)]

    def routes(route_text, bgp_text):
        return [("show ip route", route_text), ("show bgp", bgp_text)]

    def paths(text):
        return [("longer-prefixes", fx("frr_bgp_table_header.txt")), ("show bgp", text)]

    def ping(text):
        return [("ping", text)]
    return neighbors, routes, paths, ping


def eos_rules():
    def neighbors(text):
        return [("show ipv6 bgp summary", EOS_NO_V6_PEERS), ("show ip bgp summary", text)]

    def routes(route_text, bgp_text):
        return [("show ip route", route_text), ("show ip bgp", bgp_text)]

    def paths(text):
        return [("show ip bgp", text)]

    def ping(text):
        return [("ping", text)]
    return neighbors, routes, paths, ping


def srl_rules():
    def neighbors(text):
        return [("protocols bgp neighbor *", text)]

    def routes(route_text, rib_text):
        return [("route-table", route_text), ("bgp-rib afi-safi", rib_text)]

    def paths(rib_text, attrs=()):
        return [*attrs, ("local-preference", fx("srl_neighbor_local_pref.txt")), ("local-rib", rib_text)]

    def ping(text):
        return [("ip netns list", "srbase-default\n"), ("ping", text)]
    return neighbors, routes, paths, ping


@dataclass
class Cell:
    driver: str
    label: str
    check: dict
    rules: list
    must: str   # "fail" or "pass"

    @property
    def ctype(self) -> str:
        return self.check["type"]


def _cells() -> list[Cell]:
    cells: list[Cell] = []

    def add(driver, must, label, check, rules):
        cells.append(Cell(driver, label, {"node": "r1", **check}, rules, must))

    # ---- FRR and SONiC: the same driver code, each on its own captures -------------------------------------
    for drv, nbr_fx, nbr, count, route_fx, route_pfx, paths_fx in (
        ("frr", "frr_bgp_neighbors.txt", "10.0.12.2", 2, "frr_route.txt", "192.168.3.0/24", "frr_bgp_paths.txt"),
        ("sonic", "sonic_bgp_neighbors.txt", "10.0.40.2", 1, "sonic_route.txt", "192.168.20.0/24", "sonic_bgp_paths.txt"),
    ):
        neighbors, routes, paths, ping = frr_like()
        s = {"type": "bgp_session", "neighbor": nbr}
        px = {"type": "bgp_prefixes", "neighbor": nbr}
        add(drv, "pass", "session established", s, neighbors(fx(nbr_fx)))
        add(drv, "fail", "session not established", s, neighbors(session_down(fx(nbr_fx))))
        add(drv, "fail", "session must be down but is up", {**s, "state": "down"}, neighbors(fx(nbr_fx)))
        add(drv, "pass", "prefixes within max", {**px, "max": count}, neighbors(fx(nbr_fx)))
        add(drv, "fail", "prefixes over max", {**px, "max": count - 1}, neighbors(fx(nbr_fx)))
        add(drv, "fail", "prefixes not exact", {**px, "exact": count + 1}, neighbors(fx(nbr_fx)))
        add(drv, "fail", "prefixes under min", {**px, "min": count + 1}, neighbors(fx(nbr_fx)))
        add(drv, "fail", "prefixes on a session that is down", {**px, "min": 1}, neighbors(session_down(fx(nbr_fx))))
        for afi, frr_name in (("ipv6-unicast", "ipv6Unicast"), ("evpn", "l2VpnEvpn")):
            add(drv, "fail", f"{afi} prefixes over max", {**px, "afi": afi, "max": count - 1},
                neighbors(frr_family(fx(nbr_fx), frr_name)))
            add(drv, "fail", f"{afi} counted from the ipv4 family", {**px, "afi": afi, "min": 1},
                neighbors(fx(nbr_fx)))
        r = {"type": "route", "prefix": route_pfx}
        add(drv, "pass", "route present", r, routes(fx(route_fx), FRR_NO_BGP_PATH))
        add(drv, "fail", "leaked route is installed", {**r, "present": False}, routes(fx(route_fx), FRR_NO_BGP_PATH))
        add(drv, "fail", "route missing", {**r, "prefix": "203.0.113.0/24"}, routes(FRR_NO_ROUTE, FRR_NO_BGP_PATH))
        add(drv, "fail", "route via the wrong protocol", {**r, "protocol": "static"}, routes(fx(route_fx), FRR_NO_BGP_PATH))
        # received over BGP but not in zebra: still a leak (0.3.0 runtime path R4)
        add(drv, "fail", "leak in the BGP table only", {**r, "prefix": "192.168.20.0/24", "present": False},
            routes(FRR_NO_ROUTE, fx(paths_fx)))
        br = {"type": "bgp_route", "prefix": "192.168.20.0/24"}
        add(drv, "pass", "bgp path present", br, paths(fx(paths_fx)))
        add(drv, "fail", "leaked bgp path", {**br, "present": False}, paths(fx(paths_fx)))
        add(drv, "fail", "wrong as_path", {**br, "as_path": "65999"}, paths(fx(paths_fx)))
        add(drv, "fail", "wrong local_pref", {**br, "local_pref": 999}, paths(fx(paths_fx)))
        add(drv, "fail", "community missing", {**br, "communities": ["65000:999"]}, paths(fx(paths_fx)))
        p = {"type": "ping", "target": "10.9.9.9"}
        add(drv, "pass", "ping replies", p, ping(fx("frr_ping.txt")))
        add(drv, "fail", "no replies", p, ping(no_replies(fx("frr_ping.txt"))))
        add(drv, "fail", "must fail but replies", {**p, "expect": "failure"}, ping(fx("frr_ping.txt")))
    neighbors, routes, paths, ping = frr_like()
    add("frr", "fail", "no-export present", {"type": "bgp_route", "prefix": "192.168.22.0/24",
                                             "without_communities": ["no-export"]}, paths(fx("frr_bgp_paths_noexport.txt")))

    # ---- Arista EOS ------------------------------------------------------------------------------------------
    neighbors, routes, paths, ping = eos_rules()
    nbr, count = "10.0.200.2", 1
    s = {"type": "bgp_session", "neighbor": nbr}
    px = {"type": "bgp_prefixes", "neighbor": nbr}
    add("eos", "pass", "session established", s, neighbors(fx("eos_bgp_summary.txt")))
    add("eos", "fail", "session not established", s, neighbors(session_down(fx("eos_bgp_summary.txt"))))
    add("eos", "fail", "session must be down but is up", {**s, "state": "down"}, neighbors(fx("eos_bgp_summary.txt")))
    add("eos", "pass", "prefixes within max", {**px, "max": count}, neighbors(fx("eos_bgp_summary.txt")))
    add("eos", "fail", "prefixes over max", {**px, "max": count - 1}, neighbors(fx("eos_bgp_summary.txt")))
    add("eos", "fail", "prefixes not exact", {**px, "exact": count + 1}, neighbors(fx("eos_bgp_summary.txt")))
    add("eos", "fail", "prefixes under min", {**px, "min": count + 1}, neighbors(fx("eos_bgp_summary.txt")))
    add("eos", "fail", "prefixes on a session that is down", {**px, "min": 1},
        neighbors(session_down(fx("eos_bgp_summary.txt"))))
    add("eos", "fail", "ipv6-unicast prefixes under min", {**px, "afi": "ipv6-unicast", "min": 1},
        neighbors(fx("eos_bgp_summary.txt")))
    r = {"type": "route", "prefix": "192.168.20.0/24"}
    add("eos", "pass", "route present", r, routes(fx("eos_route.txt"), fx("eos_bgp_route.txt")))
    add("eos", "fail", "leaked route is installed", {**r, "present": False},
        routes(fx("eos_route.txt"), fx("eos_bgp_route.txt")))
    # the leaked default loses to a local drop route, yet it was received: present (0.3.0 runtime path R4)
    add("eos", "fail", "leak received but not selected", {"type": "route", "prefix": "0.0.0.0/0", "present": False},
        routes(fx("eos_leak_route.txt"), fx("eos_leak_bgp.txt")))
    add("eos", "fail", "route via the wrong protocol", {**r, "protocol": "static"},
        routes(fx("eos_route.txt"), fx("eos_bgp_route.txt")))
    br = {"type": "bgp_route", "prefix": "192.168.20.0/24"}
    add("eos", "pass", "bgp path present", br, paths(fx("eos_bgp_paths.txt")))
    add("eos", "fail", "leaked bgp path", {**br, "present": False}, paths(fx("eos_bgp_paths.txt")))
    add("eos", "fail", "wrong as_path", {**br, "as_path": "65999"}, paths(fx("eos_bgp_paths.txt")))
    add("eos", "fail", "no-export present", {"type": "bgp_route", "prefix": "192.168.22.0/24",
                                             "without_communities": ["no-export"]}, paths(fx("eos_bgp_paths_noexport.txt")))
    add("eos", "fail", "leaked default in the BGP table", {"type": "bgp_route", "prefix": "0.0.0.0/0", "present": False},
        paths(fx("eos_leak_bgp.txt")))
    p = {"type": "ping", "target": "192.168.20.1"}
    add("eos", "pass", "ping replies", p, ping(fx("eos_ping.txt")))
    add("eos", "fail", "no replies", p, ping(no_replies(fx("eos_ping.txt"))))
    add("eos", "fail", "must fail but replies", {**p, "expect": "failure"}, ping(fx("eos_ping.txt")))

    # ---- Nokia SR Linux ------------------------------------------------------------------------------------
    neighbors, routes, paths, ping = srl_rules()
    nbr, count = "10.0.100.2", 1
    s = {"type": "bgp_session", "neighbor": nbr}
    px = {"type": "bgp_prefixes", "neighbor": nbr}
    add("srlinux", "pass", "session established", s, neighbors(fx("srl_bgp_neighbors.txt")))
    add("srlinux", "fail", "session not established", s, neighbors(session_down(fx("srl_bgp_neighbors.txt"))))
    add("srlinux", "fail", "session must be down but is up", {**s, "state": "down"}, neighbors(fx("srl_bgp_neighbors.txt")))
    add("srlinux", "pass", "prefixes within max", {**px, "max": count}, neighbors(fx("srl_bgp_neighbors.txt")))
    add("srlinux", "fail", "prefixes over max", {**px, "max": count - 1}, neighbors(fx("srl_bgp_neighbors.txt")))
    add("srlinux", "fail", "prefixes not exact", {**px, "exact": count + 1}, neighbors(fx("srl_bgp_neighbors.txt")))
    add("srlinux", "fail", "prefixes under min", {**px, "min": count + 1}, neighbors(fx("srl_bgp_neighbors.txt")))
    add("srlinux", "fail", "prefixes on a session that is down", {**px, "min": 1},
        neighbors(session_down(fx("srl_bgp_neighbors.txt"))))
    # the capture lists ipv6-unicast administratively disabled, with no received-routes counter
    add("srlinux", "fail", "ipv6-unicast prefixes under min", {**px, "afi": "ipv6-unicast", "min": 1},
        neighbors(fx("srl_bgp_neighbors.txt")))
    r = {"type": "route", "prefix": "192.168.20.0/24"}
    add("srlinux", "pass", "route present", r, routes(fx("srl_route.txt"), fx("srl_bgp_rib_paths.txt")))
    add("srlinux", "fail", "leaked route is installed", {**r, "present": False},
        routes(fx("srl_route.txt"), fx("srl_bgp_rib_paths.txt")))
    # the leaked default loses to a static route, yet BGP received it (examples/srl-hidden-leak)
    add("srlinux", "fail", "leak received but not selected", {"type": "route", "prefix": "0.0.0.0/0", "present": False},
        routes(fx("srl_leak_route.txt"), fx("srl_leak_rib.txt")))
    add("srlinux", "fail", "route via the wrong protocol", {**r, "protocol": "static"},
        routes(fx("srl_route.txt"), fx("srl_bgp_rib_paths.txt")))
    best = [("attr-set 7", fx("srl_attr_set_best.txt")), ("attr-set 12", fx("srl_attr_set_backup.txt"))]
    br = {"type": "bgp_route", "prefix": "192.168.20.0/24"}
    add("srlinux", "pass", "bgp path present", br, paths(fx("srl_bgp_rib_paths.txt"), best))
    add("srlinux", "fail", "leaked bgp path", {**br, "present": False}, paths(fx("srl_bgp_rib_paths.txt"), best))
    add("srlinux", "fail", "wrong as_path", {**br, "as_path": "65999"}, paths(fx("srl_bgp_rib_paths.txt"), best))
    add("srlinux", "fail", "wrong local_pref", {**br, "local_pref": 999}, paths(fx("srl_bgp_rib_paths.txt"), best))
    add("srlinux", "fail", "no-export present", {"type": "bgp_route", "prefix": "192.168.22.0/24",
                                                 "without_communities": ["no-export"]},
        paths(fx("srl_bgp_rib_paths_noexport.txt"), [("attr-set 11", fx("srl_attr_set_noexport.txt"))]))
    p = {"type": "ping", "target": "192.168.20.1"}
    add("srlinux", "pass", "ping replies", p, ping(fx("srl_ping.txt")))
    add("srlinux", "fail", "no replies", p, ping(no_replies(fx("srl_ping.txt"))))
    add("srlinux", "fail", "must fail but replies", {**p, "expect": "failure"}, ping(fx("srl_ping.txt")))
    return cells


CELLS = _cells()


def verdict(cell: Cell) -> tuple[bool, str]:
    check = _validate_check(0, dict(cell.check), 20)
    driver = DRIVERS[cell.driver](Lab(cell.rules), "r1")
    clock = FakeClock()
    if is_post_convergence(check):
        r = converge_then_hold(check, driver, hold=10, interval=3, clock=clock, sleep=clock.sleep)
    else:
        r = run_check(check, driver, interval=3, clock=clock, sleep=clock.sleep)
    return r.passed, r.detail


def _params(must: str):
    return [pytest.param(c, id=f"{c.driver}-{c.ctype}-{c.label}") for c in CELLS if c.must == must]


@pytest.mark.parametrize("cell", _params("fail"))
def test_must_fail_on_the_drivers_own_output(cell):
    passed, detail = verdict(cell)
    assert passed is False, f"{cell.driver}: {cell.label} PASSED: {detail}"


@pytest.mark.parametrize("cell", _params("pass"))
def test_control_passes_on_the_same_output(cell):
    """The capture still parses and the harness isn't rigged to fail."""
    passed, detail = verdict(cell)
    assert passed is True, f"{cell.driver}: {cell.label} failed: {detail}"


@pytest.mark.parametrize("driver", sorted(DRIVERS))
@pytest.mark.parametrize("ctype", sorted(CHECK_TYPES))
def test_meta_every_driver_and_check_type_has_cells(driver, ctype):
    """A new driver or a new check type turns CI red here until it has a must-fail cell and a control,
    both on that driver's real output."""
    kinds = {c.must for c in CELLS if c.driver == driver and c.ctype == ctype}
    assert kinds == {"fail", "pass"}, (f"{driver} × {ctype}: missing "
                                       f"{sorted({'fail', 'pass'} - kinds)} cells in tests/test_driver_matrix.py")


@pytest.mark.parametrize("driver", sorted(DRIVERS))
@pytest.mark.parametrize("afi", AFIS)
def test_meta_every_driver_and_address_family_is_refused_or_has_a_must_fail_cell(driver, afi):
    """0.3.1's cold review found SR Linux reading every EVPN count as 0 (a pass on `max`). A family a driver
    can't count must be refused before deploying; any other needs a must-fail cell on that family."""
    check = _validate_check(0, {"type": "bgp_prefixes", "node": "r1", "neighbor": "10.0.0.2", "max": 0, "afi": afi}, 20)
    lab = Lab([], nodes={"r1": Node("r1", "clab-t-r1", "linux", "any")})
    if afi in DRIVERS[driver].unsupported_afis:
        with pytest.raises(DriverError):
            check_supported(lab, check, override=driver)
        return
    check_supported(lab, check, override=driver)
    cells = [c for c in CELLS if c.driver == driver and c.ctype == "bgp_prefixes" and c.must == "fail"
             and c.check.get("afi", "ipv4-unicast") == afi]
    assert cells, f"{driver} reads {afi} prefix counts but has no must-fail cell for them in tests/test_driver_matrix.py"


def test_meta_cells_name_registered_drivers_and_types():
    assert {c.driver for c in CELLS} <= set(DRIVERS)
    assert {c.ctype for c in CELLS} <= set(CHECK_TYPES)
