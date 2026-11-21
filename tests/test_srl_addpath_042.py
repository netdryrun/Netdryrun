"""The edges of the RT-0068 fix beyond its oracle (tests/oracles/FP-042-SRLADDPATH).

With add-path receive, SR Linux's received-routes counts paths. Where the peer may send add-path (the family's
`add-paths.receive` isn't a clear false and the peer's received-capabilities name ADD_PATH or aren't listed), the
driver counts the distinct prefixes of the neighbor's paths in the local RIB it already reads for AS-loop paths, and a
RIB whose usable paths don't add up to the counter is an error, never a count."""
import json
from pathlib import Path

import pytest

from netdryrun.checks import _counted
from netdryrun.drivers import srlinux
from netdryrun.drivers.base import DriverError
from netdryrun.drivers.srlinux import SrlDriver, parse_rib_neighbor_paths, srl_add_path_rx
from test_verdict_drivers import Lab

FX = Path(__file__).parent / "fixtures"
PEER = "10.0.0.2"


def nbr(received=4, rejected=0, receive=True, caps=("ADD_PATH",), state="established", fam="ipv4-unicast"):
    af = {"afi-safi-name": fam, "oper-state": "up", "received-routes": received, "rejected-routes": rejected}
    if receive is not None:
        af["add-paths"] = {"receive": receive, "send": False}
    n = {"peer-address": PEER, "session-state": state, "afi-safi": [af]}
    if caps is not None:
        n["received-capabilities"] = ["ROUTE_REFRESH", "MP_BGP", *caps]
    return json.dumps({"neighbor": [n]})


def rib(*rows):
    """rows: (prefix, invalid-reason or None, neighbor)."""
    out = []
    for i, (pfx, reason, peer) in enumerate(rows):
        r = {"prefix": pfx, "neighbor": peer, "origin-protocol": "bgp", "path-id": i, "valid-route": reason is None}
        if reason is not None:
            r["invalid-reason"] = reason
        out.append(r)
    return json.dumps({"local-rib": {"route": out}})


def two_by_two(*extra):
    return rib(("10.40.0.0/24", None, PEER), ("10.40.0.0/24", None, PEER), ("10.41.0.0/24", None, PEER),
               ("10.41.0.0/24", None, PEER), *extra)


def read(neighbors, rib_text, vrf="default", fam="ipv4-unicast"):
    lab = Lab([("protocols bgp neighbor", neighbors), (f"bgp-rib afi-safi {fam}", rib_text)])
    n = SrlDriver(lab, "srl1").bgp_neighbors(vrf).value[PEER]
    return n, lab


def test_the_capture_counts_two_prefixes():
    lab = Lab([("protocols bgp neighbor", (FX / "srl2672_rt0068_srl1_bgp_neighbors.json").read_text(encoding="utf-8")),
               ("bgp-rib afi-safi ipv4-unicast", (FX / "srl2672_rt0068_srl1_bgp_rib_ipv4.json").read_text(encoding="utf-8"))])
    n = SrlDriver(lab, "srl1").bgp_neighbors().value["10.0.100.2"]
    assert n.prefixes == {"ipv4-unicast": 2} and n.prefixes_upto == {}


def test_add_path_counts_distinct_prefixes():
    n, _ = read(nbr(4), two_by_two())
    assert n.prefixes == {"ipv4-unicast": 2} and "ipv4-unicast" not in n.prefixes_upto


def test_add_path_off_reads_the_counter():
    for kw in ({"receive": False}, {"caps": ()}):   # not asked for, or the peer didn't offer it
        n, _ = read(nbr(4, **kw), two_by_two())
        assert n.prefixes == {"ipv4-unicast": 4}
        assert srl_add_path_rx(nbr(4, **kw)) == set()


@pytest.mark.parametrize("kw", [{"receive": None}, {"receive": "false"}, {"caps": None}, {"receive": True}])
def test_unknown_add_path_is_read_as_may_send(kw):
    assert srl_add_path_rx(nbr(**kw)) == {(PEER, "ipv4-unicast")}
    n, _ = read(nbr(4, **kw), two_by_two())
    assert n.prefixes == {"ipv4-unicast": 2}


def test_a_session_that_is_not_up_is_not_flagged():
    assert srl_add_path_rx(nbr(state="active")) == set()
    assert srl_add_path_rx(json.dumps({"neighbor": [{"peer-address": PEER, "session-state": 1}]})) == set()


def test_families_not_counted_are_not_flagged():
    assert srl_add_path_rx(nbr(fam="evpn")) == set()


def test_ipv6_reads_the_ipv6_rib_and_a_vrf_reads_its_own():
    text = rib(("2001:db8:40::/48", None, PEER), ("2001:db8:40::/48", None, PEER))
    n, lab = read(nbr(2, fam="ipv6-unicast"), text, vrf="red", fam="ipv6-unicast")
    assert n.prefixes == {"ipv6-unicast": 1}
    assert lab.lines()[-1].endswith("network-instance red bgp-rib afi-safi ipv6-unicast ipv6-unicast")


def test_a_rib_that_disagrees_with_the_counter_is_an_error():
    for count, text in ((5, two_by_two()), (3, two_by_two()), (4, "{}"),
                        (4, two_by_two(("10.42.0.0/24", None, PEER)))):   # 5 usable paths against 4
        with pytest.raises(DriverError, match="prefix count can't be read"):
            read(nbr(count), text)


def test_other_neighbors_paths_and_local_rows_are_not_counted():
    n, _ = read(nbr(4), two_by_two(("10.42.0.0/24", None, "10.0.0.9"), ("10.43.0.0/24", None, "0.0.0.0")))
    assert n.prefixes == {"ipv4-unicast": 2}


def test_looped_and_rejected_paths_come_off_and_stay_exact():
    extra = (("10.50.0.0/24", {"as-loop": True}, PEER), ("10.51.0.0/24", {"rejected-route": True}, PEER))
    n, _ = read(nbr(6, rejected=1), two_by_two(*extra))   # 6 - 1 rejected - 1 looped = 4 paths, 2 prefixes
    assert n.prefixes == {"ipv4-unicast": 2} and "ipv4-unicast" not in n.prefixes_upto


def test_an_unsure_path_makes_a_range_of_prefixes():
    extra = (("10.60.0.0/24", {"next-hop-unresolved": True}, PEER),)
    n, _ = read(nbr(5), two_by_two(*extra))   # 4 or 5 paths; 2 prefixes, or 3 if the unsure one counts
    assert (n.prefixes["ipv4-unicast"], n.prefixes_upto["ipv4-unicast"]) == (2, 3)
    ok, _, _ = _counted(n, "ipv4-unicast", n.prefixes["ipv4-unicast"], 3, None, [])
    assert ok is False                        # min 3: no verdict, never a pass
    extra = (("10.40.0.0/24", {"next-hop-unresolved": True}, PEER),)
    n, _ = read(nbr(5), two_by_two(*extra))   # the unsure path's prefix is already counted
    assert (n.prefixes["ipv4-unicast"], n.prefixes_upto["ipv4-unicast"]) == (2, 2)


def test_one_path_or_none_needs_no_rib_count():
    for count in (0, 1):
        n, _ = read(nbr(count), "{}")
        assert n.prefixes == {"ipv4-unicast": count}


def test_min_checks_on_the_capture():
    from netdryrun.checks import run_check
    from netdryrun.config import _validate_check
    lab = Lab([("protocols bgp neighbor", (FX / "srl2672_rt0068_srl1_bgp_neighbors.json").read_text(encoding="utf-8")),
               ("bgp-rib afi-safi ipv4-unicast", (FX / "srl2672_rt0068_srl1_bgp_rib_ipv4.json").read_text(encoding="utf-8"))])

    def run(**raw):
        t = [0.0]
        check = _validate_check(0, {"node": "srl1", "type": "bgp_prefixes", "neighbor": "10.0.100.2", **raw}, 20)
        return run_check(check, SrlDriver(lab, "srl1"), clock=lambda: t[0],
                         sleep=lambda s: t.__setitem__(0, t[0] + max(s, 0.5)))
    assert run(min=2).passed is True
    assert run(min=3).passed is False
    assert run(exact=2).passed is True


def test_rib_paths_per_neighbor():
    got = parse_rib_neighbor_paths(two_by_two(("10.50.0.0/24", {"as-loop": True}, PEER),
                                              ("10.60.0.0/24", {"as-loop": True, "rejected-route": True}, PEER),
                                              ("10.70.0.0/24", {"as-loop": False}, "10.0.0.9")))
    assert got == {PEER: (["10.40.0.0/24"] * 2 + ["10.41.0.0/24"] * 2, ["10.60.0.0/24"]),
                   "10.0.0.9": (["10.70.0.0/24"], [])}
    assert parse_rib_neighbor_paths("{\n}") == {}


@pytest.mark.parametrize("text", ['{"local-rib": {"routes": []}}', '{"rib-in-out": {}}', '{"local-rib": {"route": [5]}}',
                                  rib(("not a prefix", None, PEER)), "[]"])
def test_rib_paths_errors(text):
    with pytest.raises(DriverError):
        parse_rib_neighbor_paths(text)


def test_the_error_names_the_range_when_there_is_one():
    extra = (("10.60.0.0/24", {"next-hop-unresolved": True}, PEER),)
    with pytest.raises(DriverError, match="is 6 to 7"):
        read(nbr(7), two_by_two(*extra))
    assert srlinux.RIB_TREE_CMD in str(pytest.raises(DriverError, read, nbr(5), two_by_two()).value)
