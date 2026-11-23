"""The FRR import-check guard (drivers/frr_import_check.py): every refusal says exactly what it refused, and the states
around the edges of each rule (the first sample after an unreadable one, a hold that ends at the limit, an instance
after one with nothing to check, a later entry of a VRF zebra doesn't know) are judged as the rule says.

Answers are the live FRR 10.4.1 captures of tests/test_frr_import_check.py; DERIVED answers change only what the test
names. A refusal's text is part of the result: the run prints it as the reason there is no verdict.
"""
from __future__ import annotations

import json

import pytest

from netdryrun.drivers import frr_import_check as ic
from netdryrun.lab import ExecResult, LabError
from test_frr_import_check import (BOOT_LOG, EMPTY_JSON, EMPTY_TEXT, JSON, REMEDIED_JSON, REMEDIED_TEXT, SESSIONS,
                                   STUCK_CONFIG, STUCK_JSON, STUCK_TEXT, TEXT, VALID_TEXT, Clock, Lab, _config,
                                   cap_answers, fu, node_answers, off_answers, r1_answers, run, run_cap, run_r1)

RMCAP_ALL = ["EARLYDENY", "LATEDENY", "NOSUCH", "LATEPERMIT"]
STUCK_WHY = "192.0.2.0/24 in 'router bgp 65000' is not registered with zebra"
ADVICE = ("bgpd applied these `network` statements before its zebra connection was up and never registered them, so "
          "it announces them whatever its routes say (production would not). Redeploy the lab, or on each router run "
          "`vtysh -c 'configure terminal' -c 'router bgp <asn>' -c 'no bgp network import-check' -c 'bgp network "
          "import-check' -c 'end'`. No verdict.")


@pytest.fixture(autouse=True)
def _sample_gap_two_seconds(monkeypatch):
    """conftest.py takes the two samples with no gap; these tests time the real gap."""
    monkeypatch.setattr(ic, "SAMPLE_GAP", 2.0)


def unreadable(budget: float, why: str) -> str:
    """The error once the time limit ends on reads that never came out complete."""
    return (f"could not read every FRR router's BGP import check within {budget:g}s, so whether the lab announces "
            f"only what its routes back is unknown: {why}. No verdict.")


def refused(call, *args) -> str:
    with pytest.raises(ic.Unknown) as e:
        call(*args)
    return str(e.value)


def error(fn, *args, **kw) -> str:
    with pytest.raises(ic.ImportCheckError) as e:
        fn(*args, **kw)
    assert isinstance(e.value, LabError)
    return str(e.value)


# ------------------------------------------------------------------------------------------------ small helpers

def test_cut_keeps_160_characters_on_one_line():
    assert ic._cut("a" * 160) == "a" * 160
    assert ic._cut("a" * 161) == "a" * 160 + "..."
    assert ic._cut("x\n  y\tz ") == "x y z"
    assert ic._cut("") == ic._cut(" \n") == "no output"
    assert ic._cut(None) == "None" and ic._cut("-", 0) == "..."


@pytest.mark.parametrize("value,read", [
    ('"no"', "no"), ("'no'", "no"), ('""', ""), ("no  # off", "no"), ('"no', '"no'), ("XnoX", "XnoX"),
    ("'no\"", "'no\""), ("n", "n"), ('"', '"'),
])
def test_a_daemons_value_is_read_as_the_shell_reads_it(value, read):
    assert ic._shell_value(value) == read


def test_small_formatters_say_exactly_what_they_list():
    inst = ic.Instance("router bgp 1", "", "default")
    assert ic._describe([(inst, "10.0.0.0/8", "is a"), (inst, "10.1.0.0/16", "is b")]) == (
        "10.0.0.0/8 in 'router bgp 1' is a; 10.1.0.0/16 in 'router bgp 1' is b")
    assert ic.gap_warnings({"a": "registered", "b": "not checked: why"}) == [
        "INCOMPLETE BASELINE: b: its FRR import check is not checked: why; a route bgpd announces without zebra "
        "backing it may be recorded"]
    c = ic.Candidates({"r1": "frr"}, r2="sonic")
    assert c == {"r1": "frr", "r2": "sonic"} and (c.found, c.gaps, c.not_frr) == ({}, {}, [])
    assert refused(ic._Obj([("a", 1), ("a", 2)]).single, "w") == "w: repeated key 'a' in one object"
    assert refused(ic._prefix, "10.0.0.1/8", "w") == "w: '10.0.0.1/8' is not a prefix"
    assert refused(ic.route_map_delay, "bgp route-map delay-timer 1\nbgp route-map delay-timer 2\n") == (
        "bgpd's running config sets the route-map delay timer more than once")
    assert refused(ic.table_commands, "all") == (
        "VRF name 'all' can't be put on a command line (`vrf all` is not one instance)")


# ------------------------------------------------------------------------------------------------ the parsers

def test_bgpd_config_refusals_say_what_they_refused():
    def cfg(body):
        return _config("router bgp 1\n" + body + "exit\n")
    fam = " address-family ipv4 unicast\n"
    cases = [
        ("", "bgpd's running config is not a complete answer (no output)"),
        ("Building configuration...\n!\nend\n",
         "bgpd's running config is not a complete answer (Building configuration... ! end)"),
        (_config("router bgp 1 vrf a b\nexit\n"),
         "bgpd's running config has a `router bgp` line this check doesn't know: 'router bgp 1 vrf a b'"),
        (_config(" network 10.0.0.0/24\n"),
         "bgpd's running config has a `network` line outside any `router bgp`: ' network 10.0.0.0/24'"),
        (_config("router bgp 1\n address-family ipv4 unicast\nexit\n"),
         "bgpd's running config leaves an address family open in 'router bgp 1'"),
        (_config("router bgp 1\nip route 1.1.1.0/24 lo\nexit\n"),
         "bgpd's running config has 'ip route 1.1.1.0/24 lo' inside 'router bgp 1' (no `exit` before it)"),
        (cfg(fam + " address-family ipv6 unicast\n exit-address-family\n"),
         "bgpd's running config opens 'address-family ipv6 unicast' inside another address family"),
        (cfg(" address-family ipv4 sr-te\n  network 10.0.0.0/24\n exit-address-family\n"),
         "bgpd's running config has a network in address family 'ipv4 sr-te', which this check doesn't know"),
        (cfg(" address-family ipv4\n  network 10.0.0.0/24\n exit-address-family\n"),
         "bgpd's running config has a network in address family 'ipv4 ', which this check doesn't know"),
        (cfg(fam + "  network 10.0.0.1/24\n exit-address-family\n"),
         "bgpd's running config has a network this check can't read: 'network 10.0.0.1/24'"),
        (cfg(fam + "  network 2001:db8::/32\n exit-address-family\n"),
         "bgpd's running config has 'network 2001:db8::/32' in address family ipv4 unicast"),
        (cfg(fam + "  network 10.0.0.0/24 route-map r;m\n exit-address-family\n"),
         "bgpd's running config has a route-map name this check can't read: 'network 10.0.0.0/24 route-map r;m'"),
    ]
    for text, why in cases:
        assert refused(ic.parse_bgpd_config, text) == why, text


@pytest.mark.parametrize("change", [
    lambda t: "% Warning: something\n" + t,                                     # a line before the answer
    lambda t: t.replace("Current configuration:\n", ""),                         # the answer's second marker gone
])
def test_bgpd_config_needs_both_markers_of_a_whole_answer(change):
    text = change(STUCK_CONFIG)
    assert text != STUCK_CONFIG
    assert refused(ic.parse_bgpd_config, text).startswith("bgpd's running config is not a complete answer (")


def test_bgpd_config_keeps_a_views_name_and_a_route_map_before_backdoor():
    """DERIVED: FRR prints `route-map NAME` before `backdoor` when a network has both (bgp_config_write_network)."""
    view, default = ic.parse_bgpd_config(_config(
        "router bgp 1 view v1\n address-family ipv4 unicast\n  network 10.2.0.0/16\n exit-address-family\nexit\n!\n"
        "router bgp 1\n address-family ipv4 unicast\n  network 10.0.0.0/24 route-map RM backdoor\n"
        " exit-address-family\nexit\n"))
    assert (view.kind, view.vrf) == ("view", "v1")
    (net,) = default.networks
    assert (net.route_map, net.backdoor) == ("RM", True) and default.checked == []


def test_table_json_refusals_say_what_they_refused():
    entry = STUCK_JSON.split('"192.0.2.0":', 1)[1].rsplit("\n},", 1)[0]
    path = entry.split('"paths":[', 1)[1].rsplit("]}", 1)[0]

    def table(e: str) -> str:
        return '{"ipv4":{"192.0.2.0":' + e + '},"ipv6":{}}'

    def with_path(p: str) -> str:
        return table(entry.replace(path, p))
    p0 = {"afi": "L2VPN", "safi": "unicast", "prefix": "192.0.2.0/24", "vrf": "default", "flags": [["valid", True]]}
    cases = [
        ("% Unknown command\n", "j: not JSON (% Unknown command)"),
        ("[1]", "j: not a JSON object ([1])"),
        ('{"ipv4":{},"ipv4":{}}', "j: repeated key 'ipv4' in one object"),
        ('{"ipv4":{}}', 'j: expected the ipv4 and ipv6 tables, got keys [\'ipv4\'] ({"ipv4":{}})'),
        ('{"ipv4":[],"ipv6":{}}', "j: ipv4 is not an object"),
        ('{"ipv4":{"x":{}},"ipv6":{}}', "j: entry 'x' is not an address"),
        ('{"ipv4":{},"ipv6":{"192.0.2.0":{}}}', "j: entry '192.0.2.0' is not an ipv6 entry object"),
        (table('{"valid":true,"valid":true}'), "j 192.0.2.0: repeated key 'valid' in one object"),
        (table('{"color":1}'), "j: entry 192.0.2.0 has key(s) this check doesn't know: ['color']"),
        (table('{"valid":true,"pathCount":1,"paths":"x"}'),
         'j: entry 192.0.2.0 lacks a readable valid flag, path count or path list, or its registration flag isn\'t '
         'false: {"valid": true, "pathCount": 1, "paths": "x"}'),
        (STUCK_JSON.replace('"isRegistered":false', '"isRegistered":true'),
         "j: entry 192.0.2.0 prints isRegistered true, which FRR never prints"),
        (with_path("1"), "j 192.0.2.0: a path is not an object"),
        (with_path('{"color":1}'), "j 192.0.2.0: a path has key(s) this check doesn't know (['color']) or no flags"),
        (with_path('{"afi":"IPv4","afi":"IPv4"}'), "j 192.0.2.0: repeated key 'afi' in one object"),
        (with_path('{"flags":{"valid":true,"valid":true}}'), "j 192.0.2.0 flags: repeated key 'valid' in one object"),
        (with_path(json.dumps({**p0, "flags": {"valid": True}})),
         "j 192.0.2.0: a path lacks a readable afi, safi, vrf or valid flag: " + json.dumps(p0)),
        (with_path(path.replace('"prefix":"192.0.2.0/24"', '"prefix":"192.0.2.1/24"')),
         "j 192.0.2.0: '192.0.2.1/24' is not a prefix"),
    ]
    for text, why in cases:
        assert refused(ic.parse_table_json, text, "j") == why, text


@pytest.mark.parametrize("old,new", [
    ('"isRegistered":false', '"isRegistered":"false"'),          # a flag that is not a boolean
    ('"pathCount":1', '"pathCount":true'),                        # a count that is a boolean
    ('"valid":false,"complete"', '"valid":0,"complete"'),        # a valid flag that is a number
    ('"safi":"unicast"', '"safi":1'),                            # a path family that is not a name
])
def test_table_json_fields_of_the_wrong_type_are_unknown(old, new):
    """DERIVED: one field of the live stuck entry, given a type FRR never prints there."""
    assert old in STUCK_JSON
    with pytest.raises(ic.Unknown):
        ic.parse_table_json(STUCK_JSON.replace(old, new), "j")


def test_table_text_refusals_say_what_they_refused():
    head = "Current BGP import check cache:\n"
    cases = [
        ("x", "t: the answer stops inside a line (x)"),
        ("% No such BGP instance exist\n", "t: not an import-check table (% No such BGP instance exist)"),
        (" " + head, "t: not an import-check table (Current BGP import check cache:)"),
        (STUCK_TEXT.replace("#paths 1", "#paths 2"), "t: entry 192.0.2.0 says 2 path(s) and lists 1"),
        (STUCK_TEXT.replace(" 192.0.2.0 invalid", " 192.0.2.x invalid"), "t: entry '192.0.2.x' is not an address"),
        (head + "  Paths:\n", "t: line '  Paths:' before any entry"),
        (VALID_TEXT.replace("  Resolved prefix", "  Is not Registered\n  Resolved prefix"),
         "t: a valid entry says it is not registered"),
        (STUCK_TEXT.replace("    1/1 ", "    9/1 "),
         "t: path line with an unknown address family: '    9/1 192.0.2.0/24 VRF default flags 0x18'"),
        (VALID_TEXT + "something else\n", "t: a line this check doesn't know: 'something else'"),
        (STUCK_TEXT.replace("192.0.2.0/24 VRF", "192.0.2.1/24 VRF"), "t: '192.0.2.1/24' is not a prefix"),
    ]
    for text, why in cases:
        assert refused(ic.parse_table_text, text, "t") == why, text


def test_table_text_reads_flags_as_hex_and_keeps_a_family_it_has_no_name_for():
    """DERIVED: the stuck entry's path with other flags (BGP_PATH_VALID is 0x10) and another SAFI number."""
    def path(flags="0x18", safi="1"):
        (e,) = ic.parse_table_text(STUCK_TEXT.replace("1/1 192.0.2.0/24 VRF default flags 0x18",
                                                      f"1/{safi} 192.0.2.0/24 VRF default flags {flags}"), "t")
        return e.paths[0]
    assert path("0x1f")[3] is True and path("0x2f")[3] is False and path("0x0")[3] is False
    assert path(safi="99")[2] == ("ipv4", "99") and path(safi="4")[2] == ("ipv4", "labeled-unicast")
    assert ic.parse_table_text("Current BGP import check cache: \n", "t") == []


def test_bgp_vrfs_refusals_say_what_they_refused():
    w = "show bgp vrfs json"
    cases = [
        ("x", f"`{w}`: not JSON (x)"),
        ("[]", f"`{w}`: not a JSON object ([])"),
        ('{"vrfs":{},"vrfs":{}}', f"{w}: repeated key 'vrfs' in one object"),
        ('{"vrfs":{}}', f'`{w}`: not the VRF list this check knows ({{"vrfs":{{}}}})'),
        ('{"vrfs":{"a":{"vrfId":1}},"totalVrfs":true}',
         f'`{w}`: not the VRF list this check knows ({{"vrfs":{{"a":{{"vrfId":1}}}},"totalVrfs":true}})'),
        ('{"vrfs":{"a":{"vrfId":1},"a":{"vrfId":2}},"totalVrfs":2}', f"{w}: repeated key 'a' in one object"),
        ('{"vrfs":{},"totalVrfs":1}', f"`{w}` counts 1 VRF(s) and lists 0"),
        ('{"vrfs":{"a":{"vrfId":1,"vrfId":2}},"totalVrfs":1}', f"{w} a: repeated key 'vrfId' in one object"),
        ('{"vrfs":{"a":{}},"totalVrfs":1}', f"`{w}`: VRF 'a' has no readable vrfId"),
        ('{"vrfs":{"a":1},"totalVrfs":1}', f"`{w}`: VRF 'a' has no readable vrfId"),
    ]
    for text, why in cases:
        assert refused(ic.parse_bgp_vrfs, text) == why, text


def test_route_map_refusals_say_what_they_refused():
    w = "`show route-map EARLYDENY json`"
    rm = '{"invoked":1,"processedChange":false}'
    cases = [
        ("x", f"{w}: not JSON (x)"),
        ("[]", f"{w}: not a JSON object ([])"),
        ('{"bgpd":{},"bgpd":{}}', f"{w}: repeated key 'bgpd' in one object"),
        ('{"zebra":{}}', f'{w}: not bgpd\'s answer alone ({{"zebra":{{}}}})'),
        ('{"bgpd":{"A":{},"A":{}}}', f"{w}: repeated key 'A' in one object"),
        ('{"bgpd":{"OTHER":{}}}', f'{w}: answers about another route-map ({{"bgpd":{{"OTHER":{{}}}}}})'),
        ('{"bgpd":{"EARLYDENY":' + rm + ',"OTHER":' + rm + '}}',
         f'{w}: answers about another route-map ({{"bgpd":{{"EARLYDENY":{rm},"OTHER":{rm}}}}})'),
        ('{"bgpd":{"EARLYDENY":{"invoked":1,"invoked":2}}}', f"{w}: repeated key 'invoked' in one object"),
        ('{"bgpd":{"EARLYDENY":{"invoked":1}}}',
         f'{w}: not the route-map state this check knows ({{"bgpd":{{"EARLYDENY":{{"invoked":1}}}}}})'),
    ]
    for text, why in cases:
        assert refused(ic.parse_route_map, text, "EARLYDENY") == why, text
    assert ic.parse_route_map('{"bgpd":{"EARLYDENY":' + rm + "}}", "EARLYDENY") == (1, False)


# ------------------------------------------------------------------------------------------------ probing nodes

def test_probe_reads_frr_past_leading_blank_lines_and_says_why_it_cant_tell():
    assert ic.probe(Lab({("x", tuple(ic.BGPD_CONFIG)): (0, "\n" + STUCK_CONFIG, "")}), "x") == (
        "vtysh answers with bgpd's running config")
    assert refused(ic.probe, Lab({("x", tuple(ic.BGPD_CONFIG)): (1, "OUT", "ERR")}), "x") == (
        "`vtysh -d bgpd -c show running-config` answered rc 1 (ERR)")


def test_bgpd_off_reads_whole_process_names():
    """DERIVED: the live process list of a router with bgpd off, plus a process whose name has a space and the word
    bgpd in it (a comm name may hold spaces): that is no bgpd process."""
    procs = fu("r1_comm_bgpd_off.txt") + "my bgpd\n"
    out, _, _ = run(Lab(off_answers(procs=(0, procs, ""))), nodes={"r1": "frr"})
    assert out == {"r1": ic.BGPD_DOWN}


def test_candidates_probe_every_node_no_driver_claims_and_skip_only_bridges():
    from types import SimpleNamespace as N

    from netdryrun.drivers.base import DriverError
    lab = Lab({("g", tuple(ic.BGPD_CONFIG)): (1, "OUT", "ERR"), ("f", tuple(ic.BGPD_CONFIG)): (0, STUCK_CONFIG, ""),
               ("d", tuple(ic.BGPD_CONFIG)): (0, STUCK_CONFIG, "")})
    lab.nodes = {"o": N(kind="ovs-bridge"), "g": N(kind="linux"), "f": N(kind="linux"), "d": N(kind="linux")}

    def driver_of(name, node):
        if name == "d":
            raise DriverError("no driver for this image")
        return {"o": "frr"}.get(name)
    got = ic.candidates(lab, driver_of)
    assert got == {"f": "frr", "d": "frr"}   # after a node that can't be told, and one whose driver lookup failed
    assert got.gaps == {"g": "no driver claims it and whether it runs FRR could not be told (`vtysh -d bgpd -c show "
                             "running-config` answered rc 1 (ERR)): its import check is not checked"}
    assert not any(a[0] == "o" for a in lab.asked)


# ------------------------------------------------------------------------------------------------ the guard's errors

def test_a_stuck_lab_not_deployed_by_this_run_is_named_in_full():
    assert error(run, Lab(node_answers()), remedy=False) == (
        f"FRR's import check is stuck on a lab this run didn't deploy: pe1: {STUCK_WHY}. {ADVICE}")


def test_a_stuck_lab_after_the_evidence_names_every_router_under_its_label():
    answers = {**node_answers(), **node_answers(node="pe9")}
    clock = Clock()
    with pytest.raises(ic.ImportCheckError) as e:
        ic.guard(Lab(answers), {"pe1": "frr", "pe9": "frr"}, remedy=False, clock=clock, sleep=clock.sleep,
                 label="after the snapshot")
    assert str(e.value) == (
        "[after the snapshot] FRR's import check is stuck once the evidence was taken (nothing is remedied then): "
        f"pe1: {STUCK_WHY} | pe9: {STUCK_WHY}. {ADVICE}")


def test_a_failed_remedy_says_what_bgpd_answered():
    lab = Lab(node_answers(), after=node_answers(j=REMEDIED_JSON, t=REMEDIED_TEXT), remedy=(1, "OUT", "ERR"))
    assert error(run, lab) == f"pe1: the import-check remedy failed (rc 1: ERR) while {STUCK_WHY}. No verdict."


def test_still_stuck_after_the_remedy_names_every_router():
    answers = {**node_answers(), **node_answers(node="pe9")}
    lab = Lab(answers, after=dict(answers))
    assert error(run, lab, nodes={"pe1": "frr", "pe9": "frr"}) == (
        f"FRR's import check is still stuck after the remedy: pe1: {STUCK_WHY} | pe9: {STUCK_WHY}. The lab would "
        "announce prefixes production withdraws. No verdict.")


def test_a_remedy_that_leaves_the_lab_unreadable_is_an_error_without_a_label():
    after = node_answers(j=REMEDIED_JSON, t=REMEDIED_TEXT)
    after[("pe1", tuple(JSON))] = (1, "OUT", "ERR")
    assert error(run, Lab(node_answers(), after=after)) == unreadable(
        20, "pe1: `show bgp import-check-table detail json` failed (ERR)")


def test_a_config_changed_by_the_remedy_is_named():
    after = node_answers(j=REMEDIED_JSON, t=REMEDIED_TEXT, config=STUCK_CONFIG.replace("hostname pe1", "hostname x"))
    assert error(run, Lab(node_answers(), after=after)) == (
        "pe1: bgpd's running config changed across the import-check remedy, so the lab no longer runs the config "
        "under test. No verdict.")


@pytest.mark.parametrize("after,now", [
    (SESSIONS.replace('"connectionsEstablished":1', '"connectionsEstablished":2', 1), "Established, 2 established, 0 dropped"),
    ('{"default":{"vrfId":0,"vrfName":"default"}}', "gone"),
])
def test_a_session_changed_by_the_remedy_is_named_with_both_states(after, now):
    lab = Lab(node_answers(), after=node_answers(j=REMEDIED_JSON, t=REMEDIED_TEXT, sessions=after))
    assert error(run, lab) == (
        f"pe1: BGP session 10.0.1.2 (vrf default) changed across the import-check remedy (Established, 1 established, "
        f"0 dropped -> {now}): the toggle may have announced a transient prefix (a maximum-prefix limit, dampening). "
        "No verdict.")


@pytest.mark.parametrize("sessions,why", [
    (SESSIONS.replace('"connectionsDropped":0', '"connectionsDropped":"0"', 1), SESSIONS.replace(
        '"connectionsDropped":0', '"connectionsDropped":"0"', 1)),
    (None, "ERR"),
])
def test_sessions_that_cant_be_read_are_named(sessions, why):
    answers = node_answers(sessions=sessions or SESSIONS)
    if sessions is None:
        answers[("pe1", tuple(ic.NEIGHBORS))] = (1, "OUT", "ERR")
    lab = Lab(answers, after=node_answers(j=REMEDIED_JSON, t=REMEDIED_TEXT))
    assert error(run, lab) == (f"pe1: its BGP sessions could not be read around the import-check remedy "
                               f"({ic._cut(why)}), so whether the remedy reset one is unknown. No verdict.")


# ------------------------------------------------------------------------------------------------ one router's read

@pytest.mark.parametrize("change,why", [
    ({tuple(JSON): (1, "OUT", "ERR")}, "`show bgp import-check-table detail json` failed (ERR)"),
    ({tuple(TEXT): (1, "OUT2", "ERR2")}, "`show bgp import-check-table detail` failed (ERR2)"),
    ({tuple(JSON): (0, "% Unknown command\n", "")}, "`show bgp import-check-table detail json`: not JSON (% Unknown command)"),
    ({tuple(TEXT): (0, "% Unknown command: x\n", "")},
     "`show bgp import-check-table detail`: not an import-check table (% Unknown command: x)"),
    ({tuple(ic.BGPD_CONFIG): (1, "OUT", "ERR"), ("cat", "/etc/frr/frr.conf"): (0, "router bgp 65000\n", "")},
     "bgpd's running config could not be read (ERR)"),
    ({tuple(ic.BGPD_CONFIG): (0, _config(""), ""), ("cat", "/etc/frr/frr.conf"): (0, "router bgp 65000\n", "")},
     "bgpd's running config has no `router bgp` yet (its startup config has one, or can't be read): bgpd hasn't "
     "loaded its config"),
    ({tuple(ic.BGPD_CONFIG): (0, STUCK_CONFIG.replace("  network 192.0.2.0/24\n",
                                               "  network 192.0.2.0/24\n  network 198.51.100.0/24\n"), ""),
      tuple(JSON): (0, EMPTY_JSON, ""), tuple(TEXT): (0, EMPTY_TEXT, "")},
     "'router bgp 65000' has no import-check entry for network(s) 192.0.2.0/24, 198.51.100.0/24 (bgpd hasn't applied "
     "them yet, or the table is not what it holds)"),
])
def test_a_read_that_cant_be_used_is_named_until_the_limit(change, why):
    answers = node_answers(j=REMEDIED_JSON, t=REMEDIED_TEXT)
    answers.update({("pe1", tuple(k)): v for k, v in change.items()})
    lab = Lab(answers)
    assert error(run, lab) == unreadable(20, f"pe1: {why}") and lab.remedied == []


def test_a_failed_read_with_no_command_echoed_is_still_named():
    class Bare(Lab):
        def exec(self, node, argv, timeout=60, input=None):
            r = super().exec(node, argv, timeout, input)
            return ExecResult([], 1, "OUT", "ERR") if list(argv) == JSON else r
    assert error(run, Bare(node_answers(j=REMEDIED_JSON, t=REMEDIED_TEXT))) == unreadable(20, "pe1: `` failed (ERR)")


def test_two_routers_that_cant_be_read_are_both_named():
    answers = {**node_answers(j=REMEDIED_JSON, t=REMEDIED_TEXT), **node_answers(node="pe9")}
    answers[("pe1", tuple(JSON))] = answers[("pe9", tuple(JSON))] = (1, "", "ERR")
    assert error(run, Lab(answers), nodes={"pe1": "frr", "pe9": "frr"}) == unreadable(
        20, "pe1: `show bgp import-check-table detail json` failed (ERR); pe9: `show bgp import-check-table detail "
            "json` failed (ERR)")


@pytest.mark.parametrize("log,why", [
    ((1, "OUT", "ERR"), "its boot log could not be read (ERR), so whether bgpd is still applying its config is unknown"),
    ((0, "[42|bgpd] sending configuration\n", ""), "its boot log shows bgpd still applying its config"),
])
def test_a_boot_log_that_doesnt_show_the_config_loaded_is_named(log, why):
    class Logged(Lab):
        def boot_log(self, node):
            return ExecResult([], *log)
    assert error(run, Logged(node_answers(j=REMEDIED_JSON, t=REMEDIED_TEXT))) == unreadable(20, f"pe1: {why}")


@pytest.mark.parametrize("driver,startup", [("frr", (0, "router ospf\n", "")), ("sonic", None)])
def test_a_router_without_router_bgp_is_skipped_on_its_drivers_evidence(driver, startup):
    """FRR: skipped once its startup config shows no `router bgp`. SONiC: its running config alone (it has no
    /etc/frr/frr.conf to read)."""
    answers = {("pe1", tuple(ic.BGPD_CONFIG)): (0, _config(""), "")}
    if startup:
        answers[("pe1", ("cat", "/etc/frr/frr.conf"))] = startup
    out, _, _ = run(Lab(answers), nodes={"pe1": driver})
    assert out == {"pe1": "no `router bgp` in bgpd's running config"}


def test_a_running_config_without_bgp_that_changes_is_read_again():
    answers = {("pe1", tuple(ic.BGPD_CONFIG)): [(0, _config(""), ""), (0, _config("ip forwarding\n"), "")],
               ("pe1", ("cat", "/etc/frr/frr.conf")): (0, "router ospf\n", "")}
    out, clock, _ = run(Lab(answers))
    assert out == {"pe1": "no `router bgp` in bgpd's running config"} and clock.sleeps == [2.0, 2.0]


def test_an_instance_after_one_with_nothing_to_check_is_still_read():
    """DERIVED: the stuck network moved to a VRF instance printed after a default instance with import check off."""
    cfg = STUCK_CONFIG.replace(" bgp router-id", " no bgp network import-check\n bgp router-id").replace(
        "bgp community-list", "router bgp 65000 vrf RED\n address-family ipv4 unicast\n  network 192.0.2.0/24\n"
        " exit-address-family\nexit\n!\nbgp community-list")
    answers = node_answers(config=cfg)
    answers[("pe1", tuple(ic.VRFS))] = (0, '{"vrfs":{"default":{"vrfId":0},"RED":{"vrfId":5}},"totalVrfs":2}', "")
    text, j = ic.table_commands("RED")
    answers[("pe1", tuple(j))] = (0, STUCK_JSON.replace('"vrf":"default"', '"vrf":"RED"'), "")
    answers[("pe1", tuple(text))] = (0, STUCK_TEXT.replace("VRF default", "VRF RED"), "")
    assert error(run, Lab(answers), remedy=False) == (
        "FRR's import check is stuck on a lab this run didn't deploy: pe1: 192.0.2.0/24 in 'router bgp 65000 vrf RED' "
        f"is not registered with zebra. {ADVICE}")


def test_an_unregistered_entry_in_the_default_instance_is_stuck_even_with_every_path_invalid():
    """DERIVED: the stuck entry with its path invalid too. Only a VRF zebra doesn't know (vrfId -1) excuses that:
    in the default instance it is a network the lab withholds while production, registered, may announce it."""
    j = STUCK_JSON.replace('"bestpath":true,"valid":true', '"bestpath":false,"valid":false')
    t = STUCK_TEXT.replace("flags 0x18", "flags 0x0")
    assert error(run, Lab(node_answers(j=j, t=t)), remedy=False) == (
        f"FRR's import check is stuck on a lab this run didn't deploy: pe1: {STUCK_WHY}. {ADVICE}")


def test_samples_that_keep_changing_never_settle():
    answers = node_answers()
    answers[("pe1", tuple(JSON))] = [(0, STUCK_JSON, ""), (0, REMEDIED_JSON, "")] * 20
    answers[("pe1", tuple(TEXT))] = [(0, STUCK_TEXT, ""), (0, REMEDIED_TEXT, "")] * 20
    assert error(run, Lab(answers), remedy=False) == unreadable(
        20, "the import-check tables kept changing between samples")


def test_an_entry_with_two_paths_names_both():
    """DERIVED: one network in ipv4 unicast and ipv4 labeled-unicast; bgpd keeps one import-check table per AFI, so
    both paths depend on one entry."""
    path = STUCK_JSON.split('"paths":[', 1)[1].rsplit("]}", 1)[0]
    j = STUCK_JSON.replace('"pathCount":1', '"pathCount":2').replace(
        path, path + "," + path.replace('"safi":"unicast"', '"safi":"labeled-unicast"'))
    t = STUCK_TEXT.replace("#paths 1", "#paths 2") + "    1/4 192.0.2.0/24 VRF default flags 0x18\n"
    assert error(run, Lab(node_answers(j=j, t=t)), remedy=False) == (
        "FRR's import check is stuck on a lab this run didn't deploy: pe1: 192.0.2.0/24, 192.0.2.0/24 in 'router bgp "
        f"65000' is not registered with zebra. {ADVICE}")


# ------------------------------------------------------------------------------- VRF instances zebra doesn't know

def test_every_entry_of_a_vrf_zebra_doesnt_know_is_judged_after_an_exempt_one():
    """DERIVED: r1's GHOST instance with a second network whose path is valid: announced, so stuck, though the entry
    before it is exempt."""
    cfg = fu("r1_bgpd_config.txt").replace("  network 100.64.0.0/24\n", "  network 100.64.0.0/24\n  network "
                                                                        "100.64.1.0/24\n")
    j = fu("r1_ghost_table.json")
    second = j.split('"100.64.0.0":', 1)[1].rsplit("\n},", 1)[0].replace("100.64.0.0", "100.64.1.0").replace(
        '"bestpath":false,"valid":false', '"bestpath":true,"valid":true')
    j = j.replace("\n},", ',"100.64.1.0":' + second + "\n},", 1)
    t = fu("r1_ghost_table.txt") + fu("r1_ghost_table.txt").split("\n", 1)[1].replace("100.64.0.0", "100.64.1.0") \
        .replace("flags 0x0", "flags 0x18")
    lab = Lab(r1_answers(config=(0, cfg, ""), ghost_json=(0, j, ""), ghost_text=(0, t, "")), boot_log=BOOT_LOG)
    assert error(run, lab, remedy=False, nodes={"r1": "frr"}, budget=60.0) == (
        "FRR's import check is stuck on a lab this run didn't deploy: r1: 100.64.1.0/24 in 'router bgp 65001 vrf "
        f"GHOST' is not registered with zebra. {ADVICE}")


def test_a_vrf_zebra_doesnt_know_renames_only_the_paths_bgpd_calls_unknown():
    """JSON names the VRF of such a path "Unknown" and the text by name (live). DERIVED: JSON naming it by name agrees
    with the text; JSON naming another VRF disagrees, never read as this one."""
    by_name = fu("r1_ghost_table.json").replace('"vrf":"Unknown"', '"vrf":"GHOST"')
    out, _, _ = run_r1(r1_answers(ghost_json=(0, by_name, "")))
    assert "100.64.0.0 (vrf GHOST) needs no entry" in out["r1"]
    other = fu("r1_ghost_table.json").replace('"vrf":"Unknown"', '"vrf":"default"')
    assert error(run_r1, r1_answers(ghost_json=(0, other, ""))) == unreadable(
        60, "r1: the import-check table's text and JSON answers disagree in 'router bgp 65001 vrf GHOST'")


@pytest.mark.parametrize("vrfs,why", [
    ((1, "OUT", "ERR"), "`show bgp vrfs json` failed (ERR)"),
    ((0, '{"vrfs":{"default":{"vrfId":0}},"totalVrfs":1}', ""),
     "`show bgp vrfs json` doesn't list the instance 'router bgp 65001 vrf GHOST'"),
])
def test_a_vrf_instance_bgpd_doesnt_list_is_named(vrfs, why):
    assert error(run_r1, r1_answers(vrfs=vrfs)) == unreadable(60, f"r1: {why}")


# ------------------------------------------------------------------------------- the route-map exemption

DENY_WHAT = "198.51.100.0/24 in 'router bgp 65001' has route-map DENYALL and no import-check entry"
DENIED = "no path of its own, no entry"


def test_every_healthy_state_is_named_in_full():
    out, clock, _ = run_r1(r1_answers())
    assert out == {"r1": "registered; 100.64.0.0 (vrf GHOST) needs no entry: its VRF is not active in zebra (bgpd vrfId "
                         "-1): the entry can't register, and every path that depends on it is invalid; 198.51.100.0/24 "
                         "(vrf default) needs no entry: denied by its route-map DENYALL: bgpd applied it with no change "
                         f"waiting, {DENIED}"}
    assert clock.sleeps == [2.0] * 4   # the route-map delay 5 s, the gap 2 s and 1 s: 8 s from the first sample
    out, _, _ = run_cap(cap_answers("rmcap", RMCAP_ALL, ["100", "101", "102"]))
    assert out == {"r1": "registered; 198.51.100.0/24 (vrf default) needs no entry: denied by its route-map EARLYDENY: "
                         f"bgpd applied it with no change waiting, {DENIED}; 198.51.101.0/24 (vrf default) needs no "
                         f"entry: denied by its route-map LATEDENY: bgpd applied it with no change waiting, {DENIED}; "
                         "198.51.102.0/24 (vrf default) needs no entry: its route-map NOSUCH is not defined, so bgpd "
                         f"denies it (as production running this config would): {DENIED}"}


@pytest.mark.parametrize("kw,why", [
    ({"denied": (1, "OUT", "ERR")}, f"{DENY_WHAT}, and `show bgp ipv4 unicast 198.51.100.0/24 json` failed (ERR)"),
    ({"rmap": (1, "OUT", "ERR")}, f"{DENY_WHAT}, and bgpd's route-map DENYALL could not be read (ERR)"),
    ({"denied": (0, "[]", "")}, f"{DENY_WHAT}, and `show bgp ipv4 unicast 198.51.100.0/24 json` gave no answer this "
                                "check can use (unexpected output from `show bgp <afi> unicast <prefix> json`: [])"),
])
def test_a_route_map_exemption_that_cant_be_proven_is_named(kw, why):
    assert error(run_r1, r1_answers(**kw)) == unreadable(60, f"r1: {why}")


def test_a_route_map_exemption_on_sonic_is_named():
    assert error(run_r1, r1_answers(), driver="sonic") == unreadable(
        60, f"r1: {DENY_WHAT}: on a sonic router a route-map deny can't be told from a network bgpd hasn't applied yet "
            "(its log doesn't show when bgpd finished loading its config)")


def test_a_route_map_bgpd_lacks_but_the_config_defines_is_named():
    a = cap_answers("rmcap", RMCAP_ALL, ["100", "101", "102"])
    a[("r1", tuple(ic.route_map_command("LATEDENY")))] = (0, fu("rmcap_rm_nosuch.json"), "")
    assert error(run_cap, a, budget=20.0) == unreadable(
        20, "r1: 198.51.101.0/24 in 'router bgp 65001' has route-map LATEDENY and no import-check entry: bgpd's running "
            "config defines route-map LATEDENY but bgpd says it has none")


def test_timer_0_error_is_named_in_full():
    assert error(run_cap, cap_answers("rm0", ["PERMIT"], ["100"])) == (
        "r1: 198.51.100.0/24 in 'router bgp 65001' has route-map PERMIT and no import-check entry, and bgpd never "
        "applied the route-map's last change (`processedChange`): with `bgp route-map delay-timer 0` bgpd never "
        "applies a route-map change, wherever the route-map is defined, so whether this network is denied by the "
        "route-map or only by the boot order can't be told, and the lab may withhold a prefix production announces. "
        "Remove `bgp route-map delay-timer 0` from the lab's config. No verdict.")


def test_a_route_map_network_in_a_vrf_is_read_in_that_vrf():
    """DERIVED: rmcap with an active VRF BLUE whose network EARLYDENY denies: bgpd's BGP table of BLUE, not the
    default one, must say it holds no path of its own."""
    cfg = fu("rmcap_bgpd_config.txt").replace("!\nend\n", "!\nrouter bgp 65001 vrf BLUE\n address-family ipv4 unicast\n"
                                              "  network 198.51.110.0/24 route-map EARLYDENY\n exit-address-family\n"
                                              "exit\n!\nend\n")
    a = cap_answers("rmcap", RMCAP_ALL, ["100", "101", "102"], config=cfg)
    a[("r1", tuple(ic.VRFS))] = (0, '{"vrfs":{"default":{"vrfId":0},"BLUE":{"vrfId":7}},"totalVrfs":2}', "")
    text, j = ic.table_commands("BLUE")
    a[("r1", tuple(j))], a[("r1", tuple(text))] = (0, EMPTY_JSON, ""), (0, EMPTY_TEXT, "")
    a[("r1", ("vtysh", "-c", "show bgp vrf BLUE ipv4 unicast 198.51.110.0/24 json"))] = (0, "{}", "")
    out, _, _ = run_cap(a)
    assert "198.51.110.0/24 (vrf BLUE) needs no entry: denied by its route-map EARLYDENY" in out["r1"]


# ------------------------------------------------------------------------------- holding samples within the limit

def test_a_hold_counts_from_the_first_complete_sample():
    """An unreadable first sample, then denies: the route-map delay counts from the first readable sample, so a path
    of its own read 6 s after it (within the 8 s hold) is never passed over."""
    cfg = fu("r1_bgpd_config.txt")
    own = fu("r1_own_prefix.json").replace("203.0.113.0/24", "198.51.100.0/24")
    seq = [(0, fu("r1_denied_prefix.json"), "")] * 3 + [(0, own, "")]
    a = r1_answers(config=[(1, "", "ERR"), (0, cfg, "")], denied=seq)
    with pytest.raises(ic.ImportCheckError, match="198.51.100.0/24 .* a path of its own"):
        run_r1(a)


def test_a_hold_that_ends_at_the_limit_is_waited_for():
    out, clock, _ = run_cap(cap_answers("rmcap", RMCAP_ALL, ["100", "101", "102"]), budget=8.0)
    assert out["r1"].startswith("registered; ") and sum(clock.sleeps) == 8.0


def test_a_route_map_delay_past_the_limit_is_named_in_full():
    cfg = fu("rmcap_bgpd_config.txt").replace("service integrated-vtysh-config\n",
                                              "bgp route-map delay-timer 100\nservice integrated-vtysh-config\n")
    assert error(run_cap, cap_answers("rmcap", RMCAP_ALL, ["100", "101", "102"], config=cfg)) == (
        "a route-map deny counts only once it has held past bgpd's route-map delay (103s with the sampling, from `bgp "
        "route-map delay-timer`), which ends after this check's 60s limit: whether the lab announces only what its "
        "routes back is unknown. Lower `bgp route-map delay-timer`. No verdict.")


class Bounded(Clock):
    """A clock that stops a guard that sleeps without end."""

    def sleep(self, s):
        assert len(self.sleeps) < 50, "the guard keeps sleeping"
        super().sleep(s)


@pytest.mark.parametrize("gap,sleeps", [(0.0, [0.0, 6.0]), (0.5, [0.5] * 13)])
def test_a_hold_is_read_again_every_sample_gap(monkeypatch, gap, sleeps):
    """With no gap (the runner's fakes) the hold is slept in one go; with a gap, the router is read again every gap
    while the hold runs, so a change within it is seen."""
    monkeypatch.setattr(ic, "SAMPLE_GAP", gap)
    clock = Bounded()
    out = ic.guard(Lab(cap_answers("rmcap", RMCAP_ALL, ["100", "101", "102"]), boot_log=fu("rmcap_bootlog_bgpd.txt")),
                   {"r1": "frr"}, remedy=True, clock=clock, sleep=clock.sleep, budget=60.0)
    assert out["r1"].startswith("registered; ") and clock.sleeps == sleeps


def test_after_an_unreadable_sample_the_next_waits_only_the_sample_gap(monkeypatch):
    monkeypatch.setattr(ic, "SAMPLE_GAP", 0.5)
    early = _config("")
    answers = node_answers(j=REMEDIED_JSON, t=REMEDIED_TEXT)
    answers[("pe1", tuple(ic.BGPD_CONFIG))] = [(0, early, ""), (0, early, ""), (0, STUCK_CONFIG, "")]
    answers[("pe1", ("cat", "/etc/frr/frr.conf"))] = (0, "router bgp 65000\n", "")
    out, clock, _ = run(Lab(answers))
    assert out == {"pe1": "registered"} and clock.sleeps == [2.0, 2.0, 0.5]


def test_reads_stop_at_the_limit_exactly():
    answers = node_answers(j=REMEDIED_JSON, t=REMEDIED_TEXT)
    answers[("pe1", tuple(JSON))] = (1, "", "ERR")
    clock = Clock()
    with pytest.raises(ic.ImportCheckError):
        ic.guard(Lab(answers), {"pe1": "frr"}, remedy=True, clock=clock, sleep=clock.sleep, budget=20.0)
    assert clock.sleeps == [ic.RETRY_GAP] * 10 and clock.t == 20.0
