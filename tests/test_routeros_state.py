"""RouterOS 7 state: sessions, connections, routing tables and the routing route table, read strictly.

The synthetic rows below have the structure of a live CHR 7.23.8 capture (2026-10-30; the captures are unpublished
until MikroTik answers a terms question); the content is invented. Facts under test:

- `prefix-count` on a session is the RECEIVED count (it includes prefixes a filter rejected); accepted prefixes come from
  the routing route table: BGP paths of that session whose contribution is not `filtered`.
- A configured connection that cannot start has no session row: no row is not "established" and not "unconfigured".
- `/routing/route` lists pseudo rows (interfaces, link-locals); they are recognised by `belongs-to`, not guessed.
- Unknown values or keys raise: nothing is skipped quietly.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from netdryrun.drivers.base import DriverError
from netdryrun.drivers.routeros_state import (
    accepted_prefixes,
    best_paths,
    parse_connections,
    parse_ping,
    parse_routing_routes,
    parse_sessions,
    parse_tables,
)


def session(**kw):
    row = {".id": "*2800003", "ebgp": "", "established": "true", "hold-time": "9s", "input.filter": "FROM-F1", "instance": "bgp1",
           "local.address": "10.0.1.1", "local.afi": "ip", "local.as": "65001", "name": "f1-1", "prefix-count": "4",
           "remote.address": "10.0.1.2", "remote.afi": "ip", "remote.as": "65002", "uptime": "4m9s600ms"}
    row.update(kw)
    return row


def route(**kw):
    row = {".id": "*20193010", "afi": "ip", "belongs-to": "bgp-IP-10.0.1.2", "bgp": "true", "bgp.as-path": "65002", "bgp.med": "0",
           "bgp.origin": "igp", "bgp.session": "f1-1", "contribution": "active", "active": "true", "debug.fwp-ptr": "0x1",
           "distance": "20", "dst-address": "192.168.20.0/24", "gateway": "10.0.1.2", "immediate-gw": "10.0.1.2%ether2",
           "nexthop-id": "*1", "routing-table": "main", "scope": "40", "target-scope": "10"}
    row.update(kw)
    return row


# ---- sessions -------------------------------------------------------------------------------------------------
def test_session_fields_are_typed_from_strings():
    s = parse_sessions([session()])[0]
    assert (s.name, s.remote_address, s.remote_as, s.established, s.received_count, s.vrf) == ("f1-1", "10.0.1.2", 65002, True, 4, "default")


def test_vrf_session_address_carries_the_vrf_and_is_split():
    s = parse_sessions([session(name="red-f2-1", **{"remote.address": "10.0.2.2@RED", "routing-table": "RED"})])[0]
    assert s.remote_address == "10.0.2.2" and s.vrf == "RED"


def test_session_count_is_called_received_not_accepted():
    s = parse_sessions([session()])[0]
    assert not hasattr(s, "accepted_count")
    assert s.received_count == 4


def test_not_established_session_may_have_no_prefix_count():
    rows = [session(established="false")]
    del rows[0]["prefix-count"]
    s = parse_sessions(rows)[0]
    assert s.established is False and s.received_count is None


def test_established_session_without_a_count_raises():
    rows = [session()]
    del rows[0]["prefix-count"]
    with pytest.raises(DriverError):
        parse_sessions(rows)


@pytest.mark.parametrize("bad", [{"established": "yes"}, {"prefix-count": "four"}, {"remote.as": "AS65002"}, {"remote.address": "not-an-ip"}])
def test_bad_session_values_raise(bad):
    with pytest.raises(DriverError):
        parse_sessions([session(**bad)])


def test_session_missing_a_required_key_raises():
    for key in ("name", "remote.address", "remote.as", "established"):
        row = session()
        del row[key]
        with pytest.raises(DriverError):
            parse_sessions([row])


def test_no_sessions_is_an_empty_list_not_an_error_here():
    assert parse_sessions([]) == []


# ---- connections ----------------------------------------------------------------------------------------------
def test_inactive_connection_keeps_its_reason():
    rows = [{".id": "*3", "as": "65001", "inactive": "true", ".about": "cannot listen to incoming connections, missing 'local-address'",
             "instance": "bgp1", "local.role": "ebgp", "name": "idle", "remote.address": "10.0.9.9", "remote.as": "65009",
             "routing-table": "main", "templates": "default"}]
    c = parse_connections(rows)[0]
    assert c.inactive is True and "missing 'local-address'" in c.about and c.vrf == "default"


def test_connection_in_a_vrf():
    rows = [{".id": "*4", "inactive": "false", "name": "red-f2", "remote.address": "10.0.2.2", "remote.as": "65003",
             "routing-table": "RED", "vrf": "RED", "instance": "bgp1"}]
    assert parse_connections(rows)[0].vrf == "RED"


def test_connection_without_a_name_or_address_raises():
    with pytest.raises(DriverError):
        parse_connections([{"inactive": "false", "remote.address": "10.0.0.1"}])
    with pytest.raises(DriverError):
        parse_connections([{"inactive": "false", "name": "x"}])


# ---- tables ---------------------------------------------------------------------------------------------------
def test_tables_list_names_and_validity():
    t = parse_tables([{".id": "*0", "dynamic": "true", "fib": "", "invalid": "false", "name": "main"},
                      {".id": "*1", "dynamic": "true", "fib": "", "invalid": "false", "name": "RED"}])
    assert t == {"main": True, "RED": True}


def test_invalid_table_is_listed_as_not_usable():
    t = parse_tables([{".id": "*0", "dynamic": "false", "fib": "", "invalid": "true", "name": "X"}])
    assert t == {"X": False}


# ---- routing routes -------------------------------------------------------------------------------------------
def test_active_bgp_path_has_attributes():
    r = parse_routing_routes([route(**{"bgp.local-pref": "200", "bgp.med": "50", "bgp.communities": "65002:100,65002:200",
                                        "bgp.large-communities": "65002:1:1"})])[0]
    assert r.kind == "bgp" and r.active and r.contribution == "active" and r.session == "f1-1"
    assert (r.local_pref, r.med, r.as_path) == (200, 50, [65002])
    assert r.communities == ["65002:100", "65002:200"] and r.large_communities == ["65002:1:1"]


def test_missing_local_pref_stays_unknown_not_zero():
    r = parse_routing_routes([route()])[0]
    assert r.local_pref is None


def test_prepended_as_path_is_kept_in_order():
    r = parse_routing_routes([route(**{"bgp.as-path": "65004,65004,65004"})])[0]
    assert r.as_path == [65004, 65004, 65004]


def test_filtered_path_is_visible_and_not_accepted():
    rows = [route(), route(**{"dst-address": "192.168.66.0/24", "contribution": "filtered", "filtered": "true"})]
    rows[1].pop("active")
    paths = parse_routing_routes(rows)
    assert [p.filtered for p in paths] == [False, True]
    assert accepted_prefixes(paths, "f1-1") == {"192.168.20.0/24"}


def test_received_count_and_accepted_prefixes_differ_when_a_filter_rejects():
    rows = [route(), route(**{"dst-address": "192.168.21.0/24", "contribution": "candidate"}),
            route(**{"dst-address": "192.168.66.0/24", "contribution": "filtered", "filtered": "true"})]
    for r in rows[1:]:
        r.pop("active", None)
    paths = parse_routing_routes(rows)
    s = parse_sessions([session(**{"prefix-count": "3"})])[0]
    assert s.received_count == 3 and len(accepted_prefixes(paths, "f1-1")) == 2


def test_best_candidate_is_a_bgp_path_that_lost_to_another_protocol():
    # a BGP default under a static default: received, accepted by policy, not the active route
    static = {".id": "*8", "active": "true", "afi": "ip", "belongs-to": "static", "blackhole": "true", "contribution": "active",
              "distance": "1", "dst-address": "0.0.0.0/0", "immediate-gw": "", "routing-table": "main", "static": "true"}
    bgp = route(**{"dst-address": "0.0.0.0/0", "contribution": "best-candidate"})
    bgp.pop("active")
    paths = parse_routing_routes([static, bgp])
    assert [p.kind for p in paths] == ["static", "bgp"]
    assert [p.active for p in paths] == [True, False]
    assert best_paths(paths, "0.0.0.0/0", "main") == [paths[1]]            # BGP best, though not installed
    assert [p.contribution for p in paths if p.active] == ["active"]


def test_pseudo_rows_are_recognised_by_what_they_belong_to():
    rows = [{".id": "*1", "active": "true", "afi": "ip", "belongs-to": "interface", "contribution": "active", "distance": "0",
             "dst-address": "ether3", "routing-table": "RED"},
            {".id": "*2", "active": "true", "afi": "ip", "belongs-to": "interface", "contribution": "active", "distance": "0",
             "dst-address": "RED", "routing-table": "RED"},
            {".id": "*3", "active": "true", "afi": "ip", "belongs-to": "connected", "contribution": "active", "distance": "0",
             "dst-address": "fe80::%ether3/64", "gateway": "ether3@RED", "routing-table": "RED"}]
    paths = parse_routing_routes(rows)
    assert [p.kind for p in paths] == ["interface", "interface", "connected"]
    assert paths[0].prefix is None and paths[2].prefix is None and paths[2].link_local


def test_outgoing_network_rows_are_not_received_paths():
    row = {".id": "*5", "afi": "ip", "belongs-to": "bgp-output-10.0.2.2@*1", "contribution": "candidate", "distance": "255",
           "dst-address": "192.168.10.1/32", "routing-table": "RED"}
    p = parse_routing_routes([row])[0]
    assert p.kind == "bgp-output" and p.session is None
    assert accepted_prefixes([p], "red-f2-1") == set()


def test_exact_lookup_of_best_paths_ignores_covering_routes():
    rows = [route(**{"dst-address": "192.168.0.0/16"}), route()]
    paths = parse_routing_routes(rows)
    assert [p.prefix for p in best_paths(paths, "192.168.20.0/24", "main")] == ["192.168.20.0/24"]
    assert best_paths(paths, "192.168.20.0/25", "main") == []


def test_a_candidate_path_is_not_a_best_path():
    cand = route(**{"bgp.session": "f3-1", "belongs-to": "bgp-IP-10.0.3.2", "contribution": "candidate", "gateway": "10.0.3.2"})
    cand.pop("active")
    paths = parse_routing_routes([route(), cand])
    assert [p.session for p in best_paths(paths, "192.168.20.0/24", "main")] == ["f1-1"]


def test_best_paths_are_per_table():
    red = route(**{"routing-table": "RED", "bgp.session": "red-f2-1", "belongs-to": "bgp-IP-10.0.2.2@*1"})
    paths = parse_routing_routes([route(), red])
    assert [p.session for p in best_paths(paths, "192.168.20.0/24", "RED")] == ["red-f2-1"]
    assert [p.session for p in best_paths(paths, "192.168.20.0/24", "main")] == ["f1-1"]
    assert best_paths(paths, "192.168.20.0/24", "NOPE") == []


@pytest.mark.parametrize("bad", [
    {"contribution": "something-new"},
    {"belongs-to": "ospf-instance"},
    {"dst-address": "not-a-prefix"},
    {"bgp.med": "high"},
    {"distance": "far"},
    {"brand-new-flag": "true"},
])
def test_unknown_values_or_keys_raise(bad):
    with pytest.raises(DriverError):
        parse_routing_routes([route(**bad)])


def test_a_route_row_without_a_contribution_raises():
    row = route()
    del row["contribution"]
    with pytest.raises(DriverError):
        parse_routing_routes([row])


def test_debug_keys_are_ignored_by_name_only():
    parse_routing_routes([route(**{"debug.fwp-ptr": "0x1", "debug.other": "x"})])
    with pytest.raises(DriverError):
        parse_routing_routes([route(**{"degub.fwp-ptr": "0x1"})])


# ---- cold-review findings (0.4.1 merge review): one signal is never enough --------------------------------------
def test_a_filtered_contribution_without_the_filtered_flag_is_an_error_not_accepted():
    row = route(**{"dst-address": "192.168.66.0/24", "contribution": "filtered"})   # no "filtered" key
    row.pop("active")
    with pytest.raises(DriverError, match="filtered"):
        parse_routing_routes([row])


def test_the_filtered_flag_without_a_filtered_contribution_is_an_error():
    row = route(**{"filtered": "true"})
    with pytest.raises(DriverError, match="filtered"):
        parse_routing_routes([row])


def test_a_session_in_a_table_without_the_vrf_suffix_is_an_error_not_the_default_vrf():
    with pytest.raises(DriverError, match="routing table"):
        parse_sessions([session(**{"routing-table": "RED"})])


def test_a_session_whose_suffix_and_table_disagree_is_an_error():
    with pytest.raises(DriverError, match="routing table"):
        parse_sessions([session(**{"remote.address": "10.0.2.2@RED", "routing-table": "BLUE"})])


def test_a_session_in_the_main_table_may_carry_the_table_name():
    assert parse_sessions([session(**{"routing-table": "main"})])[0].vrf == "default"


def test_a_connection_takes_its_vrf_from_its_routing_table():
    rows = [{".id": "*4", "inactive": "false", "name": "red-f2", "remote.address": "10.0.2.2", "remote.as": "65003",
             "routing-table": "RED", "instance": "bgp1"}]
    assert parse_connections(rows)[0].vrf == "RED"


def test_a_connection_whose_vrf_and_table_disagree_is_an_error():
    rows = [{".id": "*4", "inactive": "false", "name": "x", "remote.address": "10.0.2.2", "remote.as": "65003",
             "routing-table": "main", "vrf": "RED", "instance": "bgp1"}]
    with pytest.raises(DriverError, match="routing table"):
        parse_connections(rows)


# ---- ping -----------------------------------------------------------------------------------------------------
def test_ping_uses_the_last_cumulative_row():
    rows = [{"host": "10.0.1.2", "packet-loss": "0", "received": "1", "sent": "1", "seq": "0", "size": "56", "time": "315us", "ttl": "64"},
            {"host": "10.0.1.2", "packet-loss": "0", "received": "2", "sent": "2", "seq": "1", "size": "56", "time": "358us", "ttl": "64"},
            {"host": "10.0.1.2", "packet-loss": "0", "received": "3", "sent": "3", "seq": "2", "size": "56", "time": "298us", "ttl": "64"}]
    assert parse_ping(rows) == (3, 3)


def test_failed_probes_count_as_sent_and_lost():
    rows = [{"packet-loss": "100", "received": "0", "sent": "1", "seq": "0", "status": "22 (Invalid argument)"},
            {"packet-loss": "100", "received": "0", "sent": "2", "seq": "1", "status": "22 (Invalid argument)"}]
    assert parse_ping(rows) == (2, 0)


def test_ping_without_counters_raises():
    for rows in ([], [{"seq": "0"}], [{"sent": "x", "received": "0"}], [{"sent": "1", "received": "2"}]):
        with pytest.raises(DriverError):
            parse_ping(rows)


# ---- local only: the real live capture (unpublished; skipped where it is not present) -------------------------
def _real_dir():
    env = os.environ.get("NDR_ROUTEROS_CAPTURES")
    p = Path(env) if env else Path(__file__).resolve().parents[3] / "research" / "mikrotik-capture" / "out" / "live-20261030"
    return p if p.is_dir() else None


REAL = _real_dir()
real_only = pytest.mark.skipif(REAL is None, reason="no real CHR capture on this machine (unpublished)")


def _rows(name):
    import json
    return json.loads((REAL / f"mikrotik_{name}.txt").read_text(encoding="utf-8"))


@real_only
def test_real_sessions_connections_tables():
    sessions = parse_sessions(_rows("bgp_session"))
    assert {s.name for s in sessions} == {"f1-1", "f3-1", "red-f2-1"} and all(s.established for s in sessions)
    conns = {c.name: c for c in parse_connections(_rows("bgp_connection"))}
    assert conns["idle"].inactive and conns["idle"].about and not any(s.remote_address == "10.0.9.9" for s in sessions)
    assert parse_tables(_rows("rtable_list")) == {"main": True, "RED": True}


@real_only
def test_real_received_count_includes_the_filtered_prefix_and_accepted_does_not():
    sessions = {s.name: s for s in parse_sessions(_rows("bgp_session"))}
    paths = parse_routing_routes(_rows("rrt_all"))
    acc = accepted_prefixes(paths, "f1-1")
    assert "192.168.66.0/24" not in acc and "192.168.20.0/24" in acc
    assert sessions["f1-1"].received_count == len(acc) + 1


@real_only
@pytest.mark.parametrize("name", ["rrt_all", "rrt_20", "rrt_66", "rrt_default", "rrt_red"])
def test_real_routing_routes_parse(name):
    assert parse_routing_routes(_rows(name))


@real_only
def test_real_default_is_best_candidate_under_the_static():
    paths = parse_routing_routes(_rows("rrt_default"))
    bgp = [p for p in paths if p.kind == "bgp"][0]
    assert bgp.contribution == "best-candidate" and not bgp.active
    assert [p for p in paths if p.active][0].kind == "static"


@real_only
def test_real_ping():
    assert parse_ping(_rows("ping_ok")) == (3, 3)
    assert parse_ping(_rows("ping_fail")) == (2, 0)
