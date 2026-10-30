"""The RouterOS driver itself: what each method returns for a router's answers, and every way it refuses to guess.

Answers are the hand-written fixtures in tests/fixtures/routeros_*.txt (the structure of a live CHR 7.23.8 capture).
The matrix (test_driver_matrix.py) proves verdicts; this file proves the facts under them.
"""
from __future__ import annotations

import http.server
import json
import subprocess
import sys
import threading
from pathlib import Path

import pytest
from test_verdict_drivers import Lab

from netdryrun.drivers import DriverError
from netdryrun.drivers.base import NoSuchInstance
from netdryrun.drivers.routeros import RouterosDriver
from netdryrun.drivers.routeros_rest import HELPER

FX = Path(__file__).parent / "fixtures"


def load(name):
    return json.loads((FX / name).read_text(encoding="utf-8"))


SESSIONS, CONNS, MAIN, RED, TABLES = (load("routeros_bgp_session.txt"), load("routeros_bgp_connection.txt"),
                                      load("routeros_routes_main.txt"), load("routeros_routes_red.txt"), load("routeros_rtable.txt"))


def body(rows, status=200):
    return f"{status}\n{json.dumps(rows)}"


def exact(rows, prefix):
    return [r for r in rows if r.get("dst-address") == prefix]


def driver(rules):
    lab = Lab(rules)
    return RouterosDriver(lab, "r1"), lab


STATE = [("/routing/bgp/session", body(SESSIONS)), ("/routing/bgp/connection", body(CONNS)), ("/routing/table", body(TABLES)),
         ("/routing/route?routing-table=main", body(MAIN)), ("/routing/route?routing-table=RED", body(RED))]


# ---- neighbors ------------------------------------------------------------------------------------------------
def test_neighbors_have_states_and_accepted_counts():
    d, _ = driver(STATE)
    n = d.bgp_neighbors().value
    assert n["192.0.2.2"].state == "established" and n["192.0.2.2"].prefixes == {"ipv4-unicast": 3}
    assert n["198.51.100.2"].prefixes == {"ipv4-unicast": 1}


def test_a_connection_that_cannot_start_is_idle_not_absent():
    d, _ = driver(STATE)
    n = d.bgp_neighbors().value
    assert n["192.0.2.99"].state == "idle" and n["192.0.2.99"].prefixes == {}


def test_a_connection_without_a_session_that_is_not_inactive_is_active():
    conns = [{**CONNS[0]}, {**CONNS[1]}]
    d, _ = driver([("/routing/bgp/session", body([])), ("/routing/bgp/connection", body(conns)), ("/routing/table", body(TABLES))])
    assert {a: n.state for a, n in d.bgp_neighbors().value.items()} == {"192.0.2.2": "active", "198.51.100.2": "active"}


def test_vrf_neighbors_are_scoped_to_the_vrf():
    d, _ = driver(STATE)
    n = d.bgp_neighbors("RED").value
    assert list(n) == ["203.0.113.2"] and n["203.0.113.2"].state == "established"


def test_unknown_vrf_is_a_no_such_instance_error():
    d, _ = driver(STATE)
    with pytest.raises(NoSuchInstance):
        d.bgp_neighbors("NOPE")


def test_invalid_routing_table_is_not_usable():
    tables = [{**TABLES[0]}, {**TABLES[1], "invalid": "true"}]
    d, _ = driver([("/routing/table", body(tables))])
    with pytest.raises(NoSuchInstance):
        d.bgp_neighbors("RED")


def test_ipv6_session_is_refused_not_skipped():
    v6 = {**SESSIONS[2], "name": "v6-1", "remote.address": "2001:db8::2", "remote.afi": "ipv6"}
    d, _ = driver([*STATE[:1][:0], ("/routing/bgp/session", body([*SESSIONS, v6])), *STATE[1:]])
    with pytest.raises(DriverError, match="IPv6"):
        d.bgp_neighbors()


# ---- routes ---------------------------------------------------------------------------------------------------
def routes_rules(prefix, rows, table="main"):
    return [("/routing/route?dst-address=" + prefix, body(exact(rows, prefix))), ("/routing/table", body(TABLES))]


def test_routes_report_protocol_and_installed_state():
    d, _ = driver(routes_rules("10.20.0.0/24", MAIN))
    got = {(r.protocol, r.active) for r in d.routes("10.20.0.0/24").value}
    assert got == {("bgp", True), ("bgp", False)}


def test_received_but_outranked_bgp_path_is_present_and_not_installed():
    d, _ = driver(routes_rules("0.0.0.0/0", MAIN))
    got = sorted((r.protocol, r.active) for r in d.routes("0.0.0.0/0").value)
    assert got == [("bgp", False), ("static", True)]


def test_policy_filtered_path_is_not_a_route():
    d, _ = driver(routes_rules("10.66.0.0/24", MAIN))
    assert d.routes("10.66.0.0/24").value == []


def test_empty_list_in_the_default_table_is_an_observed_absence():
    d, _ = driver(routes_rules("10.99.0.0/24", MAIN))
    assert d.routes("10.99.0.0/24").value == []


def test_empty_list_in_an_unknown_table_is_an_error_not_an_absence():
    d, _ = driver([("/routing/route?dst-address=10.99.0.0/24", body([])), ("/routing/table", body(TABLES))])
    with pytest.raises(NoSuchInstance):
        d.routes("10.99.0.0/24", "NOPE")


def test_ipv6_prefix_and_family_are_refused():
    d, _ = driver([])
    with pytest.raises(DriverError, match="IPv6"):
        d.routes("2001:db8::/32")
    with pytest.raises(DriverError, match="IPv6"):
        d.bgp_paths("2001:db8::/32")
    with pytest.raises(DriverError, match="IPv6"):
        d.all_routes("default", 6)


def test_all_routes_skip_pseudo_rows_link_locals_outputs_and_filtered_paths():
    d, _ = driver([("/routing/route?routing-table=main", body(MAIN)), ("/routing/table", body(TABLES))])
    got = {(r.prefix, r.protocol, r.active) for r in d.all_routes().value}
    assert ("10.66.0.0/24", "bgp", False) not in got and ("10.66.0.0/24", "bgp", True) not in got
    assert not any(p.startswith("fe80") for p, _, _ in got)
    assert ("0.0.0.0/0", "static", True) in got and ("0.0.0.0/0", "bgp", False) in got
    assert ("192.0.2.0/30", "connected", True) in got
    assert all(proto in ("bgp", "static", "connected") for _, proto, _ in got)


# ---- bgp paths ------------------------------------------------------------------------------------------------
def test_paths_carry_attributes_and_the_neighbor_address():
    d, _ = driver([*routes_rules("10.20.0.0/24", MAIN), ("/routing/bgp/session", body(SESSIONS))])
    paths = d.bgp_paths("10.20.0.0/24").value
    best = next(p for p in paths if p.best)
    assert (best.as_path, best.local_pref, best.med, best.neighbor, best.next_hop) == ("65002", 200, 50, "192.0.2.2", "192.0.2.2")
    assert best.communities == ["65002:100", "65002:200"] and best.large_communities == ["65002:1:1"]
    other = next(p for p in paths if not p.best)
    assert other.as_path == "65004 65004 65004" and other.neighbor == "198.51.100.2" and other.local_pref is None


def test_a_missing_local_pref_stays_unknown_never_a_default():
    d, _ = driver([*routes_rules("10.21.0.0/24", MAIN), ("/routing/bgp/session", body(SESSIONS))])
    assert d.bgp_paths("10.21.0.0/24").value[0].local_pref is None


def test_filtered_paths_are_not_bgp_paths():
    d, _ = driver([*routes_rules("10.66.0.0/24", MAIN), ("/routing/bgp/session", body(SESSIONS))])
    assert d.bgp_paths("10.66.0.0/24").value == []


def test_best_candidate_counts_as_the_best_path():
    d, _ = driver([*routes_rules("0.0.0.0/0", MAIN), ("/routing/bgp/session", body(SESSIONS))])
    paths = d.bgp_paths("0.0.0.0/0").value
    assert len(paths) == 1 and paths[0].best


def test_a_bgp_path_in_a_vrf_is_read_from_that_table():
    d, lab = driver([("/routing/route?dst-address=198.18.2.0/24&routing-table=RED", body(exact(RED, "198.18.2.0/24"))),
                     ("/routing/table", body(TABLES)), ("/routing/bgp/session", body(SESSIONS))])
    p = d.bgp_paths("198.18.2.0/24", "RED").value
    assert len(p) == 1 and p[0].neighbor == "203.0.113.2"
    assert any("routing-table=RED" in line for line in lab.lines())


# ---- ping -----------------------------------------------------------------------------------------------------
def test_ping_counts_and_request_body():
    d, lab = driver([("/ping", body(load("routeros_ping.txt")))])
    assert d.ping("10.20.0.1", "10.10.10.1", 3).value == (3, 3)
    line = lab.lines()[0]
    assert '"address":"10.20.0.1"' in line and '"count":"3"' in line and '"src-address":"10.10.10.1"' in line


def test_ping_loss_and_vrf_refusal():
    d, _ = driver([("/ping", body(load("routeros_ping_fail.txt")))])
    assert d.ping("192.0.2.1", None, 2).value == (2, 0)
    with pytest.raises(DriverError, match="VRF"):
        d.ping("192.0.2.1", None, 2, "RED")


# ---- transport and errors -------------------------------------------------------------------------------------
def test_credentials_never_appear_in_evidence():
    d, _ = driver(STATE)
    obs = d.bgp_neighbors()
    assert obs.evidence and all("admin:admin" not in json.dumps(e) for e in obs.evidence)
    assert all(e["cmd"].startswith("REST GET ") for e in obs.evidence)


def test_every_request_runs_inside_the_container_with_the_helper():
    d, lab = driver(STATE)
    d.bgp_neighbors()
    assert all(c[1][:2] == ["python3", "-c"] and c[1][2] == HELPER for c in lab.calls)


@pytest.mark.parametrize("answer", [
    (0, "401\n" + json.dumps({"error": 401, "message": "Unauthorized"})),
    (0, "400\n" + json.dumps({"error": 400, "message": "Bad Request", "detail": "no such command prefix"})),
    (0, "500\n{}"),
    (0, "000\n"),                                  # the helper got no HTTP answer
    (0, ""),                                       # the helper printed nothing
    (0, "200\n"),                                  # 2xx with no body
    (0, "200\n<html>proxy</html>"),                # not JSON
    (0, "200\n" + json.dumps({"a": "b"})),         # an object where rows are expected
    (3, "boom"),                                   # the helper itself failed
])
def test_every_failed_answer_is_an_error_never_an_empty_result(answer):
    d, _ = driver([("/routing/bgp/session", answer)])
    with pytest.raises(DriverError):
        d.bgp_neighbors()
    d, _ = driver([("/routing/route?dst-address=10.20.0.0/24", answer), ("/routing/table", body(TABLES))])
    with pytest.raises(DriverError):
        d.routes("10.20.0.0/24")


def test_unknown_route_key_stops_a_route_read():
    rows = [{**MAIN[0], "stale": "true"}]
    d, _ = driver([("/routing/route?dst-address=10.20.0.0/24", body(rows)), ("/routing/table", body(TABLES))])
    with pytest.raises(DriverError, match="unknown key"):
        d.routes("10.20.0.0/24")


# ---- the helper that runs inside the container ------------------------------------------------------------------
class _Handler(http.server.BaseHTTPRequestHandler):
    seen: list = []

    def log_message(self, *a):
        pass

    def _do(self):
        n = int(self.headers.get("Content-Length") or 0)
        _Handler.seen.append((self.command, self.path, self.headers.get("Authorization"), self.rfile.read(n).decode()))
        code, payload = (404, b'{"error":404}') if self.path.endswith("/missing") else (200, b'[{"a":"1"}]')
        self.send_response(code)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    do_GET = do_POST = _do


def _run_helper(port, *args):
    env = {"MT_TARGET": f"http://127.0.0.1:{port}", "SYSTEMROOT": "C:\\Windows", "PATH": ""}
    return subprocess.run([sys.executable, "-I", "-c", HELPER, *args], capture_output=True, text=True, env=env, timeout=30)


def test_the_helper_prints_status_then_body_and_sends_auth_and_body():
    srv = http.server.HTTPServer(("127.0.0.1", 0), _Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        r = _run_helper(srv.server_port, "GET", "/ip/route", "admin:admin", "")
        assert r.stdout == '200\n[{"a":"1"}]'
        r = _run_helper(srv.server_port, "POST", "/ping", "admin:admin", '{"address":"1.1.1.1"}')
        assert r.stdout.startswith("200\n")
        assert _Handler.seen[-1][0] == "POST" and _Handler.seen[-1][1] == "/rest/ping" and _Handler.seen[-1][3] == '{"address":"1.1.1.1"}'
        assert _Handler.seen[-1][2].startswith("Basic ")
        r = _run_helper(srv.server_port, "GET", "/missing", "admin:admin", "")
        assert r.stdout.split("\n", 1)[0] == "404"
    finally:
        srv.shutdown()


def test_the_helper_reports_000_when_nothing_answers():
    r = _run_helper(1, "GET", "/x", "admin:admin", "")
    assert r.stdout.split("\n", 1)[0] == "000"
