"""The reason an add-path prefix range gives (review NIT on the 0.4.2 add-path fixes, RT-0068 and RT-0069).

Where a count is a range because the counter counts add-path paths (EOS, an FRR EVPN family) or because a path the SR
Linux RIB flags invalid may or may not be counted with add-path, the check's detail and record's warning name that
reason, not hidden routes "rejected by import policy". Wording only: every verdict is the same as before."""
import json
from pathlib import Path

import pytest

from netdryrun.checks import Unready, _counted
from netdryrun.drivers.base import BgpNeighbor
from netdryrun.drivers.eos import EosDriver
from netdryrun.drivers.srlinux import SrlDriver
from netdryrun.record import _session_checks
from test_verdict_drivers import Lab, eos_summary

FX = Path(__file__).parent / "fixtures"
AFI = "ipv4-unicast"
HIDDEN = "rejected by import policy"
BOUNDS = [(0, 5), (0, 4), (0, 2), (0, 0), (1, None), (2, None), (4, None), (5, None), (1, 1)]


def eos_neighbor() -> BgpNeighbor:
    """The RT-0069 capture: 4 paths accepted, add-path receive on, so 1 to 4 prefixes."""
    peer = "10.0.200.2"
    lab = Lab([("ipv6 bgp summary", eos_summary("default", **{peer: {"peerState": "Established", "prefixAccepted": 0}})),
               ("ip bgp summary", eos_summary("default", **{peer: {"peerState": "Established", "prefixAccepted": 4}})),
               ("bgp neighbors", (FX / "ceos4363m_rt0069_ceos1_ip_bgp_neighbor.json").read_text(encoding="utf-8"))])
    return EosDriver(lab, "ceos1").bgp_neighbors().value[peer]


def srl_neighbor() -> BgpNeighbor:
    """Add-path: 2 prefixes with 2 paths each, and a fifth path the RIB flags next-hop-unresolved: 2 or 3 prefixes."""
    peer = "10.0.0.2"
    af = {"afi-safi-name": AFI, "oper-state": "up", "received-routes": 5, "rejected-routes": 0,
          "add-paths": {"receive": True, "send": False}}
    neighbors = json.dumps({"neighbor": [{"peer-address": peer, "session-state": "established", "afi-safi": [af],
                                          "received-capabilities": ["ROUTE_REFRESH", "MP_BGP", "ADD_PATH"]}]})
    rows = [("10.40.0.0/24", None), ("10.40.0.0/24", None), ("10.41.0.0/24", None), ("10.41.0.0/24", None),
            ("10.60.0.0/24", {"next-hop-unresolved": True})]
    rib = {"local-rib": {"route": [{"prefix": p, "neighbor": peer, "origin-protocol": "bgp", "path-id": i,
                                    "valid-route": r is None, **({"invalid-reason": r} if r else {})}
                                   for i, (p, r) in enumerate(rows)]}}
    lab = Lab([("protocols bgp neighbor", neighbors), (f"bgp-rib afi-safi {AFI}", json.dumps(rib))])
    return SrlDriver(lab, "srl1").bgp_neighbors().value[peer]


@pytest.mark.parametrize("read, span", [(eos_neighbor, (1, 4)), (srl_neighbor, (2, 3))])
def test_an_add_path_range_names_add_path_not_hidden_routes(read, span):
    n = read()
    assert (n.prefixes[AFI], n.prefixes_upto[AFI]) == span
    assert "add-path" in n.prefixes_upto_why[AFI]
    for low, high in BOUNDS:
        _, detail, _ = _counted(n, AFI, n.prefixes[AFI], low, high, [])
        if f"{span[0]} to {span[1]}" in str(detail):
            assert "add-path" in str(detail) and HIDDEN not in str(detail), (low, high, detail)


@pytest.mark.parametrize("read", [eos_neighbor, srl_neighbor])
def test_the_reason_changes_no_verdict(read):
    """The same neighbor without the reason (the hidden-routes wording) gets the same verdicts, ready or not."""
    n = read()
    plain = BgpNeighbor(n.address, n.state, dict(n.prefixes), dict(n.prefixes_upto), dict(n.prefixes_unread))
    for low, high in BOUNDS:
        ok, detail, _ = _counted(n, AFI, n.prefixes[AFI], low, high, [])
        ok0, detail0, _ = _counted(plain, AFI, plain.prefixes[AFI], low, high, [])
        assert (ok, isinstance(detail, Unready)) == (ok0, isinstance(detail0, Unready)), (low, high)
        if f"{n.prefixes[AFI]} to " in str(detail0):
            assert HIDDEN in str(detail0)


def test_hidden_routes_keep_their_reason():
    """A range from hidden routes (Junos, interop IOP-7) still says so."""
    n = BgpNeighbor("10.0.0.2", "established", {AFI: 205}, {AFI: 206})
    _, detail, _ = _counted(n, AFI, 205, 0, 300, [])
    assert "1 received route(s) hidden: " + HIDDEN in str(detail)
    warnings: list[str] = []
    _session_checks("r1", {"10.0.0.2": n}, "range", warnings, "default", None)
    assert any("205 to 206 (hidden routes Netdryrun can't classify)" in w for w in warnings), warnings


def test_record_names_the_add_path_reason():
    n = eos_neighbor()
    warnings: list[str] = []
    _session_checks("ceos1", {n.address: n}, "range", warnings, "default", None)
    [w] = [w for w in warnings if f"{AFI}: the prefix count is 1 to 4" in w]
    assert "add-path" in w and "hidden routes" not in w, w
