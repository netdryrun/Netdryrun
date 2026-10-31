"""Parsers against real device output captured from live labs (tests/fixtures)."""
import json
from pathlib import Path

import pytest

from netdryrun.drivers import DriverError, frr, srlinux
from netdryrun.lab import ExecResult

FIX = Path(__file__).parent / "fixtures"


def read(name: str) -> str:
    return (FIX / name).read_text()


def test_frr_bgp_neighbors():
    n = frr.parse_bgp_neighbors(read("frr_bgp_neighbors.txt"))
    assert n["10.0.12.2"].state == "established"
    assert n["10.0.12.2"].prefixes["ipv4-unicast"] >= 1


def test_frr_routes():
    routes = frr.parse_routes(read("frr_route.txt"), "192.168.3.0/24")
    assert any(r.protocol == "bgp" and r.active for r in routes)
    assert frr.parse_routes(read("frr_route.txt"), "10.99.0.0/16") == []


def test_ping_busybox_and_iputils():
    assert frr.parse_ping(read("frr_ping.txt")) == (3, 3)
    assert frr.parse_ping(read("srl_ping.txt")) == (3, 3)
    assert frr.parse_ping("garbage") == (0, 0)


def test_srl_bgp_neighbors():
    n = srlinux.parse_bgp_neighbors(read("srl_bgp_neighbors.txt"))
    nb = n["10.0.100.2"]
    assert nb.state == "established"
    assert nb.prefixes["ipv4-unicast"] >= 1
    assert "evpn" not in nb.prefixes  # families without counters are skipped


def test_srl_routes():
    routes = srlinux.parse_routes(read("srl_route.txt"), "192.168.20.0/24")
    assert routes and routes[0].protocol == "bgp" and routes[0].active


def test_srl_bad_output_is_an_error():
    with pytest.raises(DriverError):
        srlinux.parse_bgp_neighbors("Parsing error: nope")
    assert srlinux.parse_bgp_neighbors("{\n}") == {}  # sr_cli's answer when there are no neighbors
    with pytest.raises(DriverError, match="unexpected output"):
        srlinux.parse_bgp_neighbors("")  # no output at all is not "no neighbors"


def test_frr_all_routes():
    routes = frr.parse_all_routes(read("frr_route.txt"))
    assert any(r.prefix == "192.168.3.0/24" and r.protocol == "bgp" for r in routes)


# --- Arista EOS (real cEOS-lab 4.36.3M output) ---
from netdryrun.drivers import eos  # noqa: E402


def test_eos_bgp_summary():
    n = eos.parse_bgp_summary(read("eos_bgp_summary.txt"))
    assert n["10.0.200.2"].state == "established"
    assert n["10.0.200.2"].prefixes["ipv4-unicast"] == 1


def test_eos_routes_active_bgp():
    routes = eos.parse_routes(read("eos_route.txt"), read("eos_bgp_route.txt"), "192.168.20.0/24")
    assert [(r.protocol, r.active) for r in routes] == [("bgp", True)]


def test_eos_leak_received_but_not_installed():
    """Regression (live-found): BGP 'best' default losing to a static must still count as present."""
    routes = eos.parse_routes(read("eos_leak_route.txt"), read("eos_leak_bgp.txt"), "0.0.0.0/0")
    assert ("static", True) in [(r.protocol, r.active) for r in routes]
    assert ("bgp", False) in [(r.protocol, r.active) for r in routes]


def test_eos_ping():
    assert frr.parse_ping(read("eos_ping.txt")) == (3, 3)


def test_eos_error_output_is_an_error():
    with pytest.raises(DriverError):
        eos.parse_bgp_summary("% Invalid input")


def test_srl_leak_received_but_not_installed():
    """Regression (live-found): SR Linux's route table only shows the installed static; the leaked
    BGP default lives in the BGP RIB and must still count as present."""
    routes = srlinux.parse_routes(read("srl_leak_route.txt"), "0.0.0.0/0", read("srl_leak_rib.txt"))
    assert ("static", True) in [(r.protocol, r.active) for r in routes]
    assert ("bgp", False) in [(r.protocol, r.active) for r in routes]


def test_srl_local_static_in_rib_is_not_bgp():
    """Regression (live-found): SR Linux lists its own static default in the BGP local-RIB (neighbor
    0.0.0.0, origin-protocol static) even when no export policy advertises it. It is not a BGP route
    for the route check, and is marked so `present: false` ignores it; best-path checks still see it."""
    rib = srlinux._json(read("srl_leak_rib.txt"))
    static_only = json.dumps({"route": [r for r in rib["route"] if r["origin-protocol"] == "static"]})
    routes = srlinux.parse_routes(read("srl_leak_route.txt"), "0.0.0.0/0", static_only)
    assert [(r.protocol, r.active) for r in routes] == [("static", True)]
    rows = srlinux.parse_rib_paths(read("srl_leak_rib.txt"), "0.0.0.0/0")
    assert [(r["neighbor"], r["best-route"]) for r in rows] == [("0.0.0.0", True), ("10.0.100.2", False)]
    assert [srlinux.unread_path(r).local_candidate for r in rows] == [True, False]


def test_srl_empty_rib_adds_nothing():
    assert srlinux.parse_routes(read("srl_rib_empty.txt"), "10.99.0.0/16", read("srl_rib_empty.txt")) == []


def test_detect_sonic_and_others():
    from netdryrun.drivers import detect
    from netdryrun.lab import Node
    def n(kind, image):
        return Node(name="x", kind=kind, image=image, container="c")
    assert detect(n("sonic-vs", "docker-sonic-vs:latest")) == "sonic"
    assert detect(n("linux", "docker-sonic-vs:latest")) == "sonic"
    assert detect(n("arista_ceos", "ceos:4.36.3M")) == "eos"
    assert detect(n("linux", "quay.io/frrouting/frr:10.4.1")) == "frr"


def test_sonic_reads_frr_output():
    # docker-sonic-vs runs FRR 10.7 inside; output captured from examples/sonic-frr
    n = frr.parse_bgp_neighbors(read("sonic_bgp_neighbors.txt"))
    assert n["10.0.40.2"].state == "established"
    assert n["10.0.40.2"].prefixes["ipv4-unicast"] == 1
    routes = frr.parse_routes(read("sonic_route.txt"), "192.168.20.0/24")
    assert any(r.protocol == "bgp" and r.active for r in routes)


# --- BGP path attributes (bgp_route), captured from a live lab: an FRR source in AS 65020 sends each
# device 192.168.20.0/24 twice. Primary session: communities 65020:100 65020:200, large 65020:1:1 65020:2:2,
# MED 50, local-pref 200 set by the device's import policy. Backup: 65020:999, MED 10, path prepended twice.
# 192.168.22.0/24 carries 65020:300 and no-export.

def _best(paths):
    best = [p for p in paths if p.best]
    assert len(best) == 1
    return best[0]


@pytest.mark.parametrize("fixture", ["frr_bgp_paths.txt", "sonic_bgp_paths.txt"])
def test_frr_and_sonic_bgp_paths(fixture):
    # frr 10.4.1 and the FRR 10.7.1 inside docker-sonic-vs print the same shape
    paths = frr.parse_bgp_paths(read(fixture), "192.168.20.0/24", default_local_pref=100)
    assert len(paths) == 2
    b = _best(paths)
    assert b.as_path == "65020" and b.med == 50 and b.local_pref == 200
    assert b.communities == ["65020:100", "65020:200"]
    assert b.large_communities == ["65020:1:1", "65020:2:2"]
    backup = next(p for p in paths if not p.best)
    assert backup.as_path == "65020 65020 65020" and backup.med == 10
    assert backup.local_pref == 100  # no LOCAL_PREF attribute: the instance default applies
    assert backup.communities == ["65020:999"] and backup.large_communities == []


def test_frr_bgp_paths_details():
    assert frr.parse_bgp_paths(read("frr_bgp_paths.txt"), "192.168.20.0/24")[0].next_hop == "10.1.1.2"
    noexp = frr.parse_bgp_paths(read("frr_bgp_paths_noexport.txt"), "192.168.22.0/24")
    assert noexp[0].communities == ["65020:300", "65535:65281"]  # "no-export" by its value
    local = frr.parse_bgp_paths(read("frr_bgp_paths_local.txt"), "192.168.21.0/24")
    assert local[0].best and local[0].as_path == ""  # FRR prints "Local" as the string; segments are empty
    v6 = frr.parse_bgp_paths(read("frr_bgp_paths_v6.txt"), "2001:db8:20::/48")
    assert v6[0].med == 60 and v6[0].large_communities == ["65020:6:6"]
    assert v6[0].next_hop.startswith("fe80::")  # FRR lists only the link-local next hop here
    assert frr.parse_bgp_paths("{}", "10.99.0.0/16") == []
    assert frr.parse_bgp_paths("{\n}", "10.99.0.0/16") == []
    assert frr.parse_default_local_pref(read("frr_bgp_table_header.txt")) == 100
    with pytest.raises(DriverError):
        frr.parse_bgp_paths('{"warning":"View/Vrf is unknown"}', "10.0.0.0/8")


def test_eos_bgp_paths():
    paths = eos.parse_bgp_paths(read("eos_bgp_paths.txt"), "192.168.20.0/24")
    b = _best(paths)
    assert (b.as_path, b.med, b.local_pref, b.next_hop) == ("65020", 50, 200, "10.3.1.2")
    assert b.communities == ["65020:100", "65020:200"] and b.large_communities == ["65020:1:1", "65020:2:2"]
    backup = next(p for p in paths if not p.best)
    assert (backup.as_path, backup.med, backup.local_pref) == ("65020 65020 65020", 10, 100)
    noexp = eos.parse_bgp_paths(read("eos_bgp_paths_noexport.txt"), "192.168.22.0/24")
    assert noexp[0].communities == ["65020:300", "65535:65281"]
    local = eos.parse_bgp_paths(read("eos_bgp_paths_local.txt"), "192.168.30.1/32")
    assert local[0].best and local[0].as_path == "" and local[0].next_hop is None and local[0].local_pref is None
    assert eos.parse_bgp_paths(read("eos_bgp_paths_empty.txt"), "10.99.0.0/16") == []
    assert eos.parse_bgp_paths(read("eos_bgp_paths.txt"), "192.168.20.0/25") == []


def test_srl_bgp_paths():
    rows = srlinux.parse_rib_paths(read("srl_bgp_rib_paths.txt"), "192.168.20.0/24")
    assert [r["attr-id"] for r in rows] == ["7", "12"]  # best path first
    b = srlinux.parse_attr_set(read("srl_attr_set_best.txt"), rows[0])
    assert b.best and (b.as_path, b.med, b.local_pref, b.next_hop) == ("65020", 50, 200, "10.2.1.2")
    assert b.communities == ["65020:100", "65020:200"] and b.large_communities == ["65020:1:1", "65020:2:2"]
    # no local-pref in the attr-set: the neighbor's local-preference (state) applies
    lp = srlinux._json(read("srl_neighbor_local_pref.txt"))["local-preference"]
    backup = srlinux.parse_attr_set(read("srl_attr_set_backup.txt"), rows[1], lp)
    assert not backup.best and (backup.as_path, backup.med, backup.local_pref) == ("65020 65020 65020", 10, 100)
    noexp_row = srlinux.parse_rib_paths(read("srl_bgp_rib_paths_noexport.txt"), "192.168.22.0/24")[0]
    noexp = srlinux.parse_attr_set(read("srl_attr_set_noexport.txt"), noexp_row)
    assert noexp.communities == ["65020:300", "65535:65281"] and noexp.med == 0
    assert srlinux.parse_rib_paths(read("srl_rib_empty.txt"), "10.99.0.0/16") == []
    with pytest.raises(DriverError):
        srlinux.parse_attr_set("{\n}", rows[0])  # attr-set vanished between the two reads


class _SrlLeakLab:
    """srl1 with its own static default (best) and a leaked one from 10.0.100.2, from the live capture."""

    def __init__(self):
        self.calls = []

    def exec(self, node, cmd, timeout=60, input=None):
        self.calls.append(cmd[-1])
        if "local-rib" in cmd[-1]:
            return ExecResult(cmd, 0, read("srl_leak_rib.txt"), "")
        if cmd[-1].endswith("attr-set 6"):
            return ExecResult(cmd, 0, json.dumps({"as-path": {"segment": [{"type": "as-sequence", "member": [65020]}]},
                                                  "next-hop": "10.0.100.2"}), "")
        if "attr-set" in cmd[-1]:
            return ExecResult(cmd, 0, json.dumps({"as-path": {"segment": []}, "next-hop": "0.0.0.0"}), "")
        return ExecResult(cmd, 0, json.dumps({"local-preference": 100}), "")


def test_srl_leak_behind_own_static_is_described():
    """When the best path is the router's own route, the leaked path's attributes are read too, so a
    `present: false` failure says where the leak came from (live-found: it said 'as-path ?')."""
    paths = srlinux.SrlDriver(_SrlLeakLab(), "srl1").bgp_paths("0.0.0.0/0").value
    assert [(p.local_candidate, p.as_path, p.next_hop) for p in paths] == [
        (True, "", "0.0.0.0"), (False, "65020", "10.0.100.2")]
    assert paths[1].local_pref == 100


# --- advertisement intervals (MRAI): what each driver reads, or its platform's default --------------------------

def test_frr_and_sonic_read_the_advertisement_interval_each_neighbor_reports():
    text = read("frr_bgp_neighbors.txt")
    assert {n.adv_interval for n in frr.parse_bgp_neighbors(text).values()} == {0.0}
    slow = text.replace('"minBtwnAdvertisementRunsTimerMsecs":0', '"minBtwnAdvertisementRunsTimerMsecs":30000')
    assert {n.adv_interval for n in frr.parse_bgp_neighbors(slow).values()} == {30.0}
    assert {n.adv_interval for n in frr.parse_bgp_neighbors(read("sonic_bgp_neighbors.txt")).values()} == {0.0}


def test_srlinux_reads_its_minimum_advertisement_interval():
    text = read("srl_bgp_neighbors.txt")
    assert {n.adv_interval for n in srlinux.parse_bgp_neighbors(text).values()} == {5.0}
    assert {n.adv_interval for n in srlinux.parse_bgp_neighbors(
        text.replace('"minimum-advertisement-interval": 5', '"minimum-advertisement-interval": 60')).values()} == {60.0}


def test_eos_uses_its_platform_default_out_delay():
    """EOS's summary carries no interval; EOS sends without delay unless `out-delay` is configured (not read)."""
    assert {n.adv_interval for n in eos.parse_bgp_summary(read("eos_bgp_summary.txt")).values()} == {0.0}
