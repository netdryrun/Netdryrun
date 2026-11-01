"""Pins for the RouterOS driver's exact behavior where the other tests only check the outcome: every Reply field, every
error message, the request each method sends (path, method, body, timeout) and the evidence it keeps. Written against
the mutation survivors of the 0.4.1 fit; the verdict tests stay in test_routeros_driver.py and test_driver_matrix.py.
"""
from __future__ import annotations

import json

import pytest
from test_routeros_driver import CONNS, MAIN, SESSIONS, STATE, TABLES, body, driver, exact, load

from netdryrun.drivers import DriverError
from netdryrun.drivers.base import NoSuchInstance
from netdryrun.drivers.routeros_rest import Reply, as_bool, as_int, classify_reply
from netdryrun.drivers.routeros_state import _addr, _need, _vrf, best_paths, parse_routing_routes


def msg(request, text):
    return f"unexpected output from `{request}`: {text}"


# ---- classify_reply: every field of every kind ------------------------------------------------------------------
@pytest.mark.parametrize("status,text,want", [
    (0, "", Reply("no_answer", 0, "no HTTP answer", request="R")),
    (0, "[]", Reply("no_answer", 0, "no HTTP answer", request="R")),
    (500, "{}", Reply("http_error", 500, "HTTP 500", request="R")),
    (500, "[]", Reply("http_error", 500, "HTTP 500", request="R")),
    (300, "[]", Reply("http_error", 300, "HTTP 300", request="R")),
    (400, json.dumps({"error": 400, "message": "Bad Request", "detail": "no such command"}),
     Reply("http_error", 400, "Bad Request no such command", request="R")),
    (401, json.dumps({"message": "Unauthorized"}), Reply("http_error", 401, "Unauthorized", request="R")),
    (404, json.dumps({"detail": "not found"}), Reply("http_error", 404, "not found", request="R")),
    (502, "<html>\n  bad   gateway</html>", Reply("http_error", 502, "<html> bad gateway</html>", request="R")),
    (502, "x" * 200, Reply("http_error", 502, "x" * 120, request="R")),
    (200, "  \n", Reply("no_body", 200, "2xx with an empty body", request="R")),
    (200, "<html>\n proxy</html>", Reply("not_json", 200, "<html> proxy</html>", request="R")),
    (200, "y" * 200, Reply("not_json", 200, "y" * 120, request="R")),
    (200, "[]", Reply("empty_list", 200, request="R")),
    (299, "[{\"a\": \"1\"}]", Reply("rows", 299, rows=({"a": "1"},), request="R")),
    (200, "[{\"a\": \"1\"}, 2]", Reply("unexpected_shape", 200, "list with non-object rows", request="R")),
    (201, "{\"a\": \"1\"}", Reply("object", 201, obj={"a": "1"}, request="R")),
    (200, "\"text\"", Reply("unexpected_shape", 200, "top-level str", request="R")),
    (200, "7", Reply("unexpected_shape", 200, "top-level int", request="R")),
])
def test_classify_reply_sets_every_field(status, text, want):
    assert classify_reply("R", status, text) == want


def test_a_body_that_is_not_text_is_no_body():
    assert classify_reply("R", 200, None) == Reply("no_body", 200, "2xx with an empty body", request="R")


def test_require_ok_names_the_request_kind_status_and_detail():
    with pytest.raises(DriverError) as e:
        Reply("http_error", 500, "boom", request="REST GET /x").require_ok()
    assert str(e.value) == msg("REST GET /x", "http_error (HTTP 500): boom")
    with pytest.raises(DriverError) as e:
        Reply("not_json", 200, "", request="REST GET /x").require_ok()
    assert str(e.value) == msg("REST GET /x", "not_json")
    r = Reply("rows", 200, rows=({"a": 1},), request="q")
    assert r.require_ok() is r


# ---- value conversions ------------------------------------------------------------------------------------------
def test_as_int_and_as_bool_messages():
    long = "9" * 30 + "z" * 40
    for fn, what, good in ((as_int, "not a number", ("17", 17)), (as_bool, "not a boolean", ("true", True))):
        assert fn("Q", good[0]) == good[1]
        with pytest.raises(DriverError) as e:
            fn("Q", long)
        assert str(e.value) == msg("Q", f"{what}: {long[:60]!r}")
        with pytest.raises(DriverError) as e:
            fn("Q", None)
        assert str(e.value) == msg("Q", f"{what}: 'None'")
    assert as_bool("Q", "false") is False


def test_address_and_row_messages():
    assert _addr("Q", "192.0.2.1@RED") == ("192.0.2.1", "RED") and _addr("Q", "192.0.2.1") == ("192.0.2.1", "default")
    with pytest.raises(DriverError) as e:
        _addr("Q", "a" * 70)
    assert str(e.value) == msg("Q", f"not an address: {'a' * 60!r}")
    with pytest.raises(DriverError) as e:
        _need("Q", {"x": 1}, "x", "name")
    assert str(e.value) == msg("Q", "row without 'name'")
    assert _vrf("") == "default" and _vrf(None) == "default" and _vrf("main") == "default" and _vrf("RED") == "RED"


def test_best_paths_and_route_reads_take_a_prefix_with_host_bits():
    paths = parse_routing_routes(MAIN)
    assert [p.prefix for p in best_paths(paths, "10.20.0.9/24", "main")] == ["10.20.0.0/24"]
    d, _ = driver([("/routing/route?dst-address=10.20.0.0/24", body(exact(MAIN, "10.20.0.0/24")))])
    assert {r.prefix for r in d.routes("10.20.0.9/24").value} == {"10.20.0.0/24"}


# ---- _rest: the request and its evidence ------------------------------------------------------------------------
def test_rest_sends_the_request_inside_the_node_and_keeps_full_evidence():
    out, err = "o" * 25000, "e" * 3000
    rows = json.dumps([{"name": "main", "invalid": "false", "pad": out}], indent=1)   # a body over several lines
    d, lab = driver([("/routing/table", (0, "200\n" + rows, err))])
    ev = []
    reply = d._rest("GET", "/routing/table", ev)
    assert reply.kind == "rows" and reply.request == "REST GET /routing/table"
    node, cmd, timeout = lab.calls[0]
    assert node == "r1" and cmd[3:] == ["GET", "/routing/table", "admin:admin", ""] and timeout == 90
    assert ev == [{"node": "r1", "cmd": "REST GET /routing/table", "rc": 0, "output": rows[-20000:], "stderr": err[-2000:]}]


@pytest.mark.parametrize("stdout", ["abc\n[]", "12345\n[]", "\n[]"])
def test_a_status_line_that_is_not_three_digits_is_no_answer(stdout):
    d, _ = driver([("/x", stdout)])
    with pytest.raises(DriverError) as e:
        d._rest("GET", "/x", [])
    assert str(e.value) == msg("REST GET /x", "no_answer (HTTP 0): no HTTP answer")


@pytest.mark.parametrize("answer,last", [((3, "out1\nout2", "err1\nerr2\n"), "err2"), ((3, "out1\nout2", ""), "out2"),
                                         ((3, "", ""), "no output")])
def test_a_failed_helper_names_the_request_and_its_last_line(answer, last):
    d, _ = driver([("/ping", answer)])
    with pytest.raises(DriverError) as e:
        d._rest("POST", "/ping", [], body="{}")
    assert str(e.value) == f"`REST POST /ping {{}}` failed on r1 (rc=3): {last}"


def test_rows_needs_a_list():
    d, _ = driver([("/routing/table", body({"a": "b"}))])
    with pytest.raises(DriverError) as e:
        d._rows("/routing/table", [])
    assert str(e.value) == "`GET /routing/table` on r1: expected a list of rows, got object"


# ---- what each method asks, and the evidence it returns ---------------------------------------------------------
def paths_asked(lab):
    return [c[1][3:5] for c in lab.calls]


def test_confirm_table_messages_and_request():
    d, lab = driver([("/routing/table", body(TABLES))])
    with pytest.raises(NoSuchInstance) as e:
        d.bgp_neighbors("NOPE")
    assert str(e.value) == "VRF 'NOPE' does not exist on r1 (`/routing/table` lists: RED, main)"
    assert paths_asked(lab) == [["GET", "/routing/table"]]
    d, _ = driver([("/routing/table", body([]))])
    with pytest.raises(NoSuchInstance) as e:
        d.bgp_neighbors("NOPE")
    assert str(e.value) == "VRF 'NOPE' does not exist on r1 (`/routing/table` lists: none)"
    d, _ = driver([("/routing/table", body([{**TABLES[0]}, {**TABLES[1], "invalid": "true"}]))])
    with pytest.raises(NoSuchInstance) as e:
        d.bgp_neighbors("RED")
    assert str(e.value) == "VRF 'RED' is configured on r1 but its routing table is invalid"


def test_neighbors_ask_sessions_connections_and_routes_and_name_each_neighbor():
    down = {**SESSIONS[2], "established": "false"}
    d, lab = driver([("/routing/bgp/session", body([*SESSIONS[:2], down])), *STATE[1:]])
    n = d.bgp_neighbors().value
    assert all(a == x.address for a, x in n.items())
    assert n[down["remote.address"]].state == "active"
    assert paths_asked(lab)[:2] == [["GET", "/routing/bgp/session"], ["GET", "/routing/bgp/connection"]]
    d, _ = driver([("/routing/bgp/session", body([])), ("/routing/bgp/connection", body(CONNS)), ("/routing/table", body(TABLES))])
    assert all(a == x.address for a, x in d.bgp_neighbors().value.items())


def test_routes_read_the_main_table_and_keep_evidence():
    d, lab = driver([("/routing/route?dst-address=10.20.0.0/24", body(exact(MAIN, "10.20.0.0/24")))])
    obs = d.routes("10.20.0.0/24")
    assert {r.prefix for r in obs.value} == {"10.20.0.0/24"} and len(obs.evidence) == 1
    assert paths_asked(lab) == [["GET", "/routing/route?dst-address=10.20.0.0/24&routing-table=main"]]


def test_all_routes_keep_evidence_skip_ipv6_and_refuse_family_6():
    v6 = {**MAIN[6], ".id": "*v6", "dst-address": "2001:db8::/64", "belongs-to": "static"}
    d, _ = driver([("/routing/route?routing-table=main", body([*MAIN, v6]))])
    obs = d.all_routes()
    assert obs.evidence and all(":" not in r.prefix for r in obs.value) and obs.value
    d, _ = driver(STATE)
    obs = d.all_routes("RED")
    assert [e["cmd"] for e in obs.evidence] == ["REST GET /routing/table", "REST GET /routing/route?routing-table=RED"]
    with pytest.raises(DriverError) as e:
        d.all_routes(family=6)
    assert str(e.value) == "IPv6 routes are not supported on routeros yet"


def test_bgp_paths_without_an_as_path_and_their_evidence():
    row = {k: v for k, v in exact(MAIN, "10.21.0.0/24")[0].items() if k != "bgp.as-path"}
    d, lab = driver([("/routing/route?dst-address=10.21.0.0/24", body([row])), ("/routing/bgp/session", body(SESSIONS))])
    obs = d.bgp_paths("10.21.0.0/24")
    assert [p.as_path for p in obs.value] == [None] and obs.value[0].neighbor == "192.0.2.2"
    assert [e["cmd"] for e in obs.evidence] == ["REST GET /routing/route?dst-address=10.21.0.0/24&routing-table=main",
                                                "REST GET /routing/bgp/session"]
    assert paths_asked(lab)[1] == ["GET", "/routing/bgp/session"]


def test_nos_version_asks_system_resource():
    d, lab = driver([("/system/resource", body(load("routeros_resource.txt")))])
    assert d.nos_version() == "RouterOS 7.23.8 (long-term)"
    assert paths_asked(lab) == [["GET", "/system/resource"]]


def test_ping_request_timeout_evidence_and_refusals():
    d, lab = driver([("/ping", body(load("routeros_ping.txt")))])
    obs = d.ping("10.20.0.1", "10.10.10.1", 3)
    want = '{"address":"10.20.0.1","count":"3","src-address":"10.10.10.1"}'
    assert lab.calls[0][1][3:] == ["POST", "/ping", "admin:admin", want] and lab.calls[0][2] == 39
    assert [e["cmd"] for e in obs.evidence] == ["REST POST /ping " + want]
    with pytest.raises(DriverError) as e:
        d.ping("192.0.2.1", None, 2, "RED")
    assert str(e.value) == "ping inside a VRF is not supported on routeros yet"
    d, _ = driver([("/ping", body({"a": "b"}))])
    with pytest.raises(DriverError) as e:
        d.ping("192.0.2.1", None, 2)
    assert str(e.value) == "`POST /ping` on r1: expected probe rows, got object"
