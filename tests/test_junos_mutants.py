"""Juniper cJunosEvolved driver: the behaviour the 0.4 mutation run showed unpinned. Error messages are
pinned whole (they name the command and the element, and an operator reads them as the reason a check
failed), along with the shapes Junos may print that a weaker parser would read as something else."""
import json

import pytest
from test_driver_junos import Lab, read

from netdryrun.drivers import DriverError, junos
from netdryrun.drivers.base import NoSuchInstance
from netdryrun.drivers.junos import JunosDriver

NB = f"unexpected output from `{junos.NEIGHBORS_CMD}`: "
RC = f"unexpected output from `{junos.ROUTE_CMD}`: "
AR = f"unexpected output from `{junos.ALL_ROUTES_CMD}`: "
PC = f"unexpected output from `{junos.PING_CMD}`: "


def _obj(d) -> str:
    return json.dumps(d)


def raises(fn, message: str) -> DriverError:
    with pytest.raises(DriverError) as e:
        fn()
    assert str(e.value) == message
    return e.value


# ---------------------------------------------------------------- BGP neighbors

def peer(**over) -> dict:
    p = {"peer-address": [{"data": "10.0.1.2+179"}], "peer-state": [{"data": "Established"}],
         "peer-cfg-rti": [{"data": "master"}],
         "bgp-rib": [{"name": [{"data": "inet.0"}], "accepted-prefix-count": [{"data": "3"}],
                     "received-prefix-count": [{"data": "3"}]}]}
    p.update(over)
    return p


def nb(*peers, instance: str = "master"):
    return junos.parse_bgp_neighbors(_obj({"bgp-information": [{"bgp-peer": list(peers)}]}), instance)


def with_options(options: dict, **over) -> dict:
    return peer(**{"bgp-option-information": [options]}, **over)


def test_adv_interval_zero_and_empty_flags_read_as_no_delay():
    """`out-delay 0` is no delay, not a negative one; an empty option-flag list carries no delay flag."""
    assert nb(with_options({"outbound-timer": [{"data": "0"}]}))["10.0.1.2"].adv_interval == 0.0
    assert nb(with_options({"bgp-options": []}))["10.0.1.2"].adv_interval == 0.0
    assert nb(with_options({"bgp-options": [{"data": "Preference"}], "outbound-timer": [{"data": "7"}]})
              )["10.0.1.2"].adv_interval == 7.0


def test_adv_interval_shape_errors_name_the_command():
    raises(lambda: nb(peer(**{"bgp-option-information": [{}, {}]})),
           NB + "bgp-option-information more than once: [{}, {}]")
    raises(lambda: nb(with_options({"outbound-timer": [{"data": "10"}, {"data": "20"}]})),
           NB + "outbound-timer more than once: [{'data': '10'}, {'data': '20'}]")
    raises(lambda: nb(with_options({"bgp-options": [{"data": "A"}, {"data": "B"}]})),
           NB + "bgp-options more than once: [{'data': 'A'}, {'data': 'B'}]")
    raises(lambda: nb(with_options({"outbound-timer": [{"data": "ten"}]})), NB + "not a number: 'ten'")
    raises(lambda: nb(with_options({"outbound-timer": [{"data": "-1"}]})), NB + "10.0.1.2: outbound-timer '-1'")


def test_unknown_delay_message_names_what_was_found():
    """The refusal names the delay elements found (peer first, then options), or the option flag."""
    tail = "; unexpected output, never read as no delay"
    raises(lambda: nb(with_options({"out-delay": [{"data": "30"}]}, **{"route-delay": [{"data": "1"}]})),
           "peer 10.0.1.2: an advertisement delay in a form this driver doesn't read (route-delay, out-delay)" + tail)
    raises(lambda: nb(with_options({"bgp-options": [{"data": "Preference OutDelay"}]})),
           "peer 10.0.1.2: an advertisement delay in a form this driver doesn't read (an option flag)" + tail)


def test_peer_address_port_is_cut_at_the_first_plus():
    assert junos._strip_port("10.0.1.2+179+1") == "10.0.1.2"


def test_foreign_unicast_ribs_are_refused():
    """A unicast RIB of another instance (any depth of dotted name, v4 or v6) never counts as this one's."""
    raises(lambda: nb(peer(**{"bgp-rib": [{"name": [{"data": "red.blue.inet.0"}]}]})),
           NB + "RIB 'red.blue.inet.0' is not in instance 'master'")
    raises(lambda: nb(peer(**{"bgp-rib": [{"name": [{"data": "RED.inet6.0"}]}]})),
           NB + "RIB 'RED.inet6.0' is not in instance 'master'")
    raises(lambda: nb(peer(**{"peer-cfg-rti": [{"data": "RED"}], "bgp-rib": [{"name": [{"data": "XYZ.inet.0"}]}]}),
                      instance="RED"),
           NB + "RIB 'XYZ.inet.0' is not in instance 'RED'")


# ---------------------------------------------------------------- the shared element readers

def test_root_errors_name_the_command():
    def parse(doc):
        return lambda: junos.parse_bgp_neighbors(_obj(doc), "master")
    raises(parse({"bgp-information": [{}, {}]}), NB + "bgp-information more than once: [{}, {}]")
    raises(parse({"bgp-information": []}), NB + "{'bgp-information': []}")
    raises(parse({"bgp-information": [{"bogus": []}]}), NB + "unknown element 'bogus'")
    raises(parse({"bgp-information": [{"zz": [], "aa": []}]}), NB + "unknown element 'aa'")
    doc = {"bgp-information": [{}], "x" + "y" * 200: 1}
    raises(parse(doc), NB + f"expected only 'bgp-information': {str(doc)[:150]}")


def test_leaf_errors_name_the_command_and_the_leaf():
    p = {"pad": "p" * 200, **peer()}
    del p["peer-state"]
    raises(lambda: nb(p), NB + f"no 'peer-state': {str(p)[:150]}")
    value = ["v" * 100]
    raises(lambda: nb(peer(**{"peer-state": [{"data": value}]})), NB + f"peer-state: {str(value)[:80]}")
    twice = [{"data": "a" * 100}, {"data": "b" * 100}]
    raises(lambda: nb(peer(**{"peer-state": twice})), NB + f"peer-state more than once: {str(twice)[:150]}")
    raises(lambda: nb(peer(**{"peer-state": "Established"})), NB + "peer-state: Established")


def test_items_error_names_the_command():
    raises(lambda: junos.parse_bgp_neighbors(_obj({"bgp-information": [{"bgp-peer": "z" * 200}]}), "master"),
           NB + "bgp-peer: " + "z" * 150)


def test_json_errors_name_the_command_and_the_message():
    long = "error: " + "word " * 60
    raises(lambda: junos.parse_ping(long), f"Junos error from `{junos.PING_CMD}`: {' '.join(long.split())[:200]}")
    two = _obj({"xnm:error": [{"message": [{"data": "first"}]}, {"message": [{"data": "second"}]}]})
    raises(lambda: junos.parse_ping(two), f"Junos error from `{junos.PING_CMD}`: first; second")
    raises(lambda: junos.parse_ping(_obj({"xnm:error": []})), f"Junos error from `{junos.PING_CMD}`: xnm:error")
    longer = _obj({"xnm:error": [{"message": [{"data": "m" * 300}]}]})
    raises(lambda: junos.parse_ping(longer), f"Junos error from `{junos.PING_CMD}`: " + "m" * 200)
    raises(lambda: junos.parse_ping("not json"), PC + "not json")
    raises(lambda: junos.parse_ping("[]"), PC + "[]")
    raises(lambda: junos.parse_ping(_obj({"rpc-error": [{"x": 1}]})),
           f"Junos error from `{junos.PING_CMD}`: [{{'x': 1}}]")
    raises(lambda: junos.parse_ping(_obj({"rpc-error": "e" * 300})), f"Junos error from `{junos.PING_CMD}`: " + "e" * 200)


# ---------------------------------------------------------------- routes

def entry(**over) -> dict:
    e = {"protocol-name": [{"data": "BGP"}], "active-tag": [{"data": "*"}], "as-path": [{"data": "AS path: 65002 I"}]}
    e.update(over)
    return e


def rt(*entries, dest="10.20.0.0", length="24", **over) -> dict:
    r = {"rt-destination": [{"data": dest}], "rt-entry": list(entries)}
    if length is not None:
        r["rt-prefix-length"] = [{"data": length}]
    r.update(over)
    return r


def answer(*rts, table="inet.0") -> str:
    return _obj({"route-information": [{"route-table": [{"table-name": [{"data": table}], "rt": list(rts)}]}]})


def routes(text, prefix="10.20.0.0/24"):
    return [(r.protocol, r.active) for r in junos.parse_routes(text, prefix)]


def test_hidden_by_state_or_by_reason_is_never_active():
    """Either sign of a hidden route (the `Hidden` state word, or a hidden-reason) keeps it from being active."""
    assert routes(answer(rt(entry(**{"rt-entry-state": [{"data": "Int Ext Hidden"}]})))) == [("bgp", False)]
    assert routes(answer(rt(entry(**{"hidden-reason": [{"data": "Unusable path"}]})))) == [("bgp", False)]
    assert routes(answer(rt(entry()))) == [("bgp", True)]


def test_entry_without_active_tag_is_inactive_not_an_error():
    e = entry()
    del e["active-tag"]
    assert routes(answer(rt(e))) == [("bgp", False)]


def test_unknown_protocol_keeps_its_junos_name():
    assert routes(answer(rt(entry(**{"protocol-name": [{"data": "Mystery"}]})))) == [("mystery", True)]


def test_entry_errors_name_the_command():
    twice = [{"data": "Hidden"}, {"data": "Hidden"}]
    raises(lambda: routes(answer(rt(entry(**{"rt-entry-state": twice})))),
           RC + f"rt-entry-state more than once: {twice}")
    raises(lambda: junos.parse_all_routes(answer(rt(entry(**{"rt-entry-state": twice}), dest="10.20.0.0/24",
                                                    length=None))),
           AR + f"rt-entry-state more than once: {twice}")
    raises(lambda: routes(answer(rt(entry(**{"hidden-reason": [{"data": "a"}, {"data": "b"}]})))),
           RC + "hidden-reason more than once: [{'data': 'a'}, {'data': 'b'}]")
    raises(lambda: routes(answer(rt(entry(**{"active-tag": [{"data": "*"}, {"data": "*"}]})))),
           RC + "active-tag more than once: [{'data': '*'}, {'data': '*'}]")
    raises(lambda: routes(answer(rt(entry(**{"protocol-name": [{"data": "BGP"}, {"data": "BGP"}]})))),
           RC + "protocol-name more than once: [{'data': 'BGP'}, {'data': 'BGP'}]")


def test_flag_protocol_name_is_no_protocol():
    """An empty flag element reads as "" (never some placeholder text), so it is an entry without a protocol."""
    e = entry(**{"protocol-name": [{}]})
    raises(lambda: routes(answer(rt(e))), RC + f"rt-entry without protocol-name: {e}")


def test_rt_entry_errors_name_the_command():
    r = rt(pad="r" * 200)
    del r["rt-entry"]
    raises(lambda: routes(answer(r)), RC + f"route without rt-entry: {str(r)[:150]}")
    raises(lambda: routes(answer(rt(**{"rt-entry": {"protocol-name": "BGP"}}))),
           RC + "rt-entry: {'protocol-name': 'BGP'}")
    e = entry(**{"protocol-name": [{"data": ""}]}, pad="e" * 200)
    raises(lambda: routes(answer(rt(e))), RC + f"rt-entry without protocol-name: {str(e)[:150]}")


def test_destination_errors_name_the_command():
    r = rt(entry(), length=None, pad="d" * 10)
    del r["rt-destination"]
    raises(lambda: junos.parse_all_routes(answer(r)), AR + f"no 'rt-destination': {r}")
    raises(lambda: routes(answer(rt(entry(), **{"rt-prefix-length": [{"data": "24"}, {"data": "24"}]}))),
           RC + "rt-prefix-length more than once: [{'data': '24'}, {'data': '24'}]")
    no_slash = "a" * 100
    raises(lambda: junos.parse_all_routes(answer(rt(entry(), dest=no_slash, length=None))),
           AR + f"not a prefix: {no_slash[:80]!r}")
    bad = "x" * 100 + "/24"
    raises(lambda: junos.parse_all_routes(answer(rt(entry(), dest=bad, length=None))),
           AR + f"not a prefix: {bad[:80]!r}")
    raises(lambda: routes(answer(rt(entry(), dest="not-an-ip"))), RC + "not a prefix: 'not-an-ip/24'")


def test_destination_with_host_bits_is_its_network():
    (r,) = junos.parse_all_routes(answer(rt(entry(), dest="10.0.1.1/30", length=None)))
    assert r.prefix == "10.0.1.0/30"


def test_table_errors_name_the_command():
    syntax = "error: syntax error"
    raises(lambda: routes(syntax), f"Junos error from `{junos.ROUTE_CMD}`: error: syntax error")
    two = {"route-table-error": [{"route-table-error-str": [{"data": "a"}, {"data": "b"}]}]}
    raises(lambda: routes(_obj(two)), RC + "route-table-error-str more than once: [{'data': 'a'}, {'data': 'b'}]")
    extra = {"route-table-error": [{}], "extra": 1}
    raises(lambda: routes(_obj(extra)), RC + f"expected only 'route-table-error': {extra}")
    extra = {"route-information": [{}], "extra": 1}
    raises(lambda: routes(_obj(extra)), RC + f"expected only 'route-information': {extra}")
    raises(lambda: routes(_obj({"route-information": [{"route-table": "x"}]})), RC + "route-table: x")
    raises(lambda: routes(_obj({"route-information": [{"route-table": [{"bogus": []}]}]})),
           RC + "unknown element 'bogus'")
    raises(lambda: routes(_obj({"route-information": [{"route-table": [{"rt": []}]}]})),
           RC + "no 'table-name': {'rt': []}")
    raises(lambda: routes(answer(rt(entry()), table="RED.inet.0")), RC + "table 'RED.inet.0' in the answer for 'inet.0'")
    raises(lambda: routes(_obj({"route-information": [{"route-table": [{"table-name": [{"data": "inet.0"}],
                                                                        "rt": "x"}]}]})), RC + "rt: x")


def test_route_table_error_message_is_shown_or_else_the_answer():
    def err(s):
        return {"route-table-error": [{"route-table-error-str": [s]}]}
    head = f"Junos error from `{junos.ROUTE_CMD}`: "
    raises(lambda: routes(_obj(err({"data": "rpd is busy"}))), head + "rpd is busy")
    raises(lambda: routes(_obj(err({"data": "b" * 300}))), head + "b" * 200)
    raises(lambda: routes(_obj(err({}))), head + str(err({})))
    e = raises(lambda: junos.parse_routes(read("junos_route_no_table.txt"), "10.88.0.0/24", "NOPE.inet.0"),
               f"no routing table NOPE.inet.0 (`{junos.ROUTE_CMD}`)")
    assert isinstance(e, junos.NoSuchTable)


def test_every_route_table_element_is_read():
    """Two route-table elements for the same table: the routes of both, never only the last one's."""
    t = {"table-name": [{"data": "inet.0"}], "rt": [rt(entry())]}
    text = _obj({"route-information": [{"route-table": [t, t]}]})
    assert routes(text) == [("bgp", True), ("bgp", True)]


# ---------------------------------------------------------------- BGP paths

def paths(*entries):
    return junos.parse_bgp_paths(answer(rt(*entries)), "10.20.0.0/24")


def test_selected_next_hop_wins_over_the_first_listed():
    nh = [{"to": [{"data": "10.0.1.1"}]}, {"to": [{"data": "10.0.2.2"}], "selected-next-hop": [{}]}]
    (p,) = paths(entry(nh=nh))
    assert p.next_hop == "10.0.2.2"


def test_next_hop_errors_name_the_command():
    raises(lambda: paths(entry(nh=[{"to": [{"data": "10.0.1.1"}, {"data": "10.0.1.2"}]}])),
           RC + "to more than once: [{'data': '10.0.1.1'}, {'data': '10.0.1.2'}]")
    raises(lambda: paths(entry(nh="x")), RC + "nh: x")


def test_as_path_set_with_commas():
    assert junos._as_path("c", "AS path: 65002 {65010,65011} I") == "65002 {65010,65011}"


def test_as_path_errors():
    raises(lambda: junos._as_path("c", "x" * 100), "unexpected output from `c`: as-path '" + "x" * 80 + "'")
    with pytest.raises(DriverError, match="as-path"):
        junos._as_path("c", "   ")
    line = "AS path: " + "1" * 90 + " x I"
    raises(lambda: junos._as_path("c", line), f"unexpected output from `c`: as-path token 'x' in {line[:80]!r}")
    line = "AS path: " + "1" * 100
    raises(lambda: junos._as_path("c", line), f"unexpected output from `c`: as-path without origin: {line[:80]!r}")


def test_community_errors_name_the_command():
    raises(lambda: paths(entry(communities=[{}, {}])), RC + "communities more than once: [{}, {}]")
    raises(lambda: paths(entry(communities=[{"community": "x"}])), RC + "community: x")
    c = {"data": 7, "pad": "q" * 100}
    raises(lambda: paths(entry(communities=[{"community": [c]}])), RC + f"community {str(c)[:80]}")


# ---------------------------------------------------------------- the driver

class TimedLab(Lab):
    """The fake cJunosEvolved node of test_driver_junos, also keeping each command's timeout."""

    def __init__(self, rules):
        super().__init__(rules)
        self.timeouts = []

    def exec(self, node, cmd, timeout=60, input=None):
        self.timeouts.append(timeout)
        return super().exec(node, cmd, timeout=timeout, input=input)


def cli(command: str) -> str:
    return f"cli -c '{command} | display json | no-more'"


def test_table_names():
    assert (junos._table("default", 4), junos._table("default", 6)) == ("inet.0", "inet6.0")
    assert junos._table("RED", 6) == "RED.inet6.0"


def test_ping_in_the_default_vrf_and_its_timeout():
    """A ping gets two seconds a probe plus 30; every other command the default 60."""
    lab = TimedLab([("ping", read("junos_ping.txt"))])
    obs = JunosDriver(lab, "j1").ping("10.20.0.1", None, 3)
    assert obs.value == (3, 3) and len(obs.evidence) == 1
    assert lab.calls == [cli("ping 10.20.0.1 count 3 rapid wait 1")] and lab.timeouts == [36]
    lab = TimedLab([("show route instance", read("junos_instances.txt"))])
    obs = JunosDriver(lab, "j1").vrfs()
    assert lab.timeouts == [60] and len(obs.evidence) == 1


def test_quote_refusal_message():
    command = "show route 'x" + "y" * 100
    raises(lambda: JunosDriver(TimedLab([]), "j1")._cli(command, []),
           f"refusing a Junos command with a quote: {command[:80]!r}")


def test_vrf_master_refusal_message():
    raises(lambda: JunosDriver(TimedLab([]), "j1").routes("10.0.0.0/24", "master"),
           "VRF 'master' is the Junos name for the default instance; use vrf: default")


def test_driver_reads_the_vrf_table_and_trusts_found_routes():
    """A VRF answer is parsed against that VRF's table; routes found need no instance confirmation."""
    lab = TimedLab([("RED.inet.0", read("junos_route_red.txt"))])
    obs = JunosDriver(lab, "j1").routes("10.40.0.0/24", "RED")
    assert [(r.protocol, r.active) for r in obs.value] == [("bgp", True)] and len(lab.calls) == 1
    assert len(obs.evidence) == 1
    lab = TimedLab([("show route table RED.inet.0", read("junos_route_table_red.txt"))])
    obs = JunosDriver(lab, "j1").all_routes("RED")
    assert obs.value and len(lab.calls) == 1 and len(obs.evidence) == 1
    lab = TimedLab([("show bgp neighbor instance RED", read("junos_bgp_neighbor_red.txt"))])
    obs = JunosDriver(lab, "j1").bgp_neighbors("RED")
    assert set(obs.value) == {"10.0.3.2"} and len(obs.evidence) == 1


def test_empty_vrf_answer_confirms_the_instance():
    lab = TimedLab([("show route instance NOPE", read("junos_instance_none.txt")),
                    ("NOPE.inet.0", read("junos_route_empty.txt"))])
    with pytest.raises(NoSuchInstance):
        JunosDriver(lab, "j1").routes("10.88.0.0/24", "NOPE")


def test_default_vrf_queries():
    """The default VRF reads master's tables (inet6.0 for IPv6) and an empty answer there is trusted."""
    lab = TimedLab([("show route table inet.0", read("junos_route_empty.txt"))])
    obs = JunosDriver(lab, "j1").all_routes()
    assert obs.value == [] and lab.calls == [cli("show route table inet.0")] and len(obs.evidence) == 1
    lab = TimedLab([("show route table inet6.0", read("junos_route_table_v6.txt"))])
    assert JunosDriver(lab, "j1").all_routes(family=6).value
    lab = TimedLab([("inet6.0", read("junos_route_v6.txt"))])
    assert JunosDriver(lab, "j1").routes("2001:db8:20::/48").value
    assert lab.calls == [cli("show route 2001:db8:20::/48 exact table inet6.0 all extensive")]
    lab = TimedLab([("inet.0", read("junos_route_paths.txt"))])
    obs = JunosDriver(lab, "j1").bgp_paths("10.20.0.0/24")
    assert len(obs.value) == 2 and len(obs.evidence) == 1
    assert lab.calls == [cli("show route 10.20.0.0/24 exact table inet.0 all extensive")]


def test_missing_table_paths_keep_their_evidence_and_name_the_instance():
    lab = TimedLab([("show route instance RED", read("junos_instance_red.txt")),
                    ("RED.inet6.0", read("junos_route_no_table.txt"))])
    obs = JunosDriver(lab, "j1").all_routes("RED", family=6)
    assert obs.value == [] and len(obs.evidence) == 2
    lab = TimedLab([("show route instance RED", read("junos_instance_red.txt")),
                    ("RED.inet.0", read("junos_route_no_table.txt"))])
    raises(lambda: JunosDriver(lab, "j1").routes("10.88.0.0/24", "RED"),
           "`show route` says table RED.inet.0 doesn't exist, but routing-instance 'RED' lists it")
