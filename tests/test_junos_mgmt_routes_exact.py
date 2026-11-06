"""Exact-output tests for the Junos management-route reader (parse_management_routes, JunosDriver.management_routes).

Each test pins one thing a mutant of those functions would change: the command named in an error, the table
names asked for, the protocol and destination text of a result line, which entries are skipped."""

import json
import re
from pathlib import Path

import pytest

from netdryrun.drivers import DriverError, junos
from netdryrun.drivers.base import NoSuchInstance
from netdryrun.drivers.junos import JunosDriver
from netdryrun.lab import ExecResult

FIX = Path(__file__).parent / "fixtures"
CMD = "show route table <table>"
PFX = f"unexpected output from `{CMD}`: "


def read(name: str) -> str:
    return (FIX / name).read_text(encoding="utf-8")


def leaf(value) -> list:
    return [{"data": value}]


def nh(via=None, to=None) -> dict:
    out = {}
    if to is not None:
        out["to"] = leaf(to)
    if via is not None:
        out["via"] = leaf(via)
    return out


def entry(proto="Static", active=True, nhs=None, **extra) -> dict:
    e = {"active-tag": leaf("*" if active else ""), "protocol-name": leaf(proto)}
    if nhs is not None:
        e["nh"] = nhs
    e.update(extra)
    return e


def rt(dest="10.0.1.0/30", entries=None, **extra) -> dict:
    r = {"rt-destination": leaf(dest), "rt-entry": entries if entries is not None else [entry()]}
    r.update(extra)
    return r


def table(rts, name="inet.0", total=None, hidden=0, **extra) -> str:
    shown = sum(len(r.get("rt-entry", [])) for r in rts if isinstance(r.get("rt-entry"), list))
    t = {"table-name": leaf(name), "total-route-count": leaf(str(shown + hidden if total is None else total)),
         "hidden-route-count": leaf(str(hidden)), "rt": rts}
    t.update(extra)
    return json.dumps({"route-information": [{"route-table": [t]}]})


def snippet(text: str) -> str:
    return " ".join(text.split())[:200]


MGMT = nh(via="re0:mgmt-0", to="10.0.0.1")


# ------------------------------------------------------------------------------ parse_management_routes: results

def test_fixture_with_lab_interfaces_only_has_no_management_routes():
    assert junos.parse_management_routes(read("junos_route_table.txt")) == []


def test_skipped_entries_do_not_hide_a_later_active_static_route():
    # inactive static, connected and local entries on re0:mgmt-0 are skipped (continue, not break); the
    # active static entry after them in the same rt is found, with its protocol and destination in the line
    skipped = [entry("Static", active=False, nhs=[MGMT]),
               entry("Direct", nhs=[MGMT]),
               entry("Local", nhs=[MGMT]),
               entry("Static", nhs=[MGMT])]
    text = table([rt("10.0.1.0/30", skipped), rt("10.0.2.0/24", [entry("Direct", nhs=[MGMT])])])
    assert junos.parse_management_routes(text) == ["10.0.1.0/30 (inet.0, static) via re0:mgmt-0"]


def test_inactive_route_alone_is_not_reported():
    text = table([rt("10.0.1.0/30", [entry("Static", active=False, nhs=[MGMT])])])
    assert junos.parse_management_routes(text) == []


def test_local_route_alone_is_not_reported():
    text = table([rt("10.0.1.1/32", [entry("Local", nhs=[MGMT])])])
    assert junos.parse_management_routes(text) == []


def test_connected_route_alone_is_not_reported():
    text = table([rt("10.0.1.0/30", [entry("Direct", nhs=[MGMT])])])
    assert junos.parse_management_routes(text) == []


def test_other_protocols_are_named_in_the_line():
    text = table([rt("10.9.0.0/16", [entry("BGP", nhs=[nh(via="fxp0.0")])]),
                  rt("10.8.0.0/16", [entry("Static", nhs=[nh(via="em0")])])])
    assert junos.parse_management_routes(text, table="inet.0") == [
        "10.9.0.0/16 (inet.0, bgp) via fxp0.0", "10.8.0.0/16 (inet.0, static) via em0"]


def test_table_name_is_in_the_line():
    text = table([rt("2001:db8::/32", [entry(nhs=[MGMT])])], name="RED.inet6.0")
    assert junos.parse_management_routes(text, "RED.inet6.0") == [
        "2001:db8::/32 (RED.inet6.0, static) via re0:mgmt-0"]


def test_next_hop_without_via_is_not_an_error_and_does_not_count():
    text = table([rt("10.0.1.0/30", [entry(nhs=[nh(to="10.0.0.1")])]),
                  rt("10.0.2.0/30", [entry(nhs=[nh(to="10.0.0.1"), nh(via="re0:mgmt-0")])])])
    assert junos.parse_management_routes(text) == ["10.0.2.0/30 (inet.0, static) via re0:mgmt-0"]


def test_entry_without_next_hops_is_not_reported():
    assert junos.parse_management_routes(table([rt("10.0.1.0/30", [entry()])])) == []


def test_several_management_next_hops_are_joined_with_comma_space():
    text = table([rt("10.0.1.0/30", [entry(nhs=[nh(via="re0:mgmt-0"), nh(via="et-0/0/0.0"), nh(via="fxp0.0")])])])
    assert junos.parse_management_routes(text) == ["10.0.1.0/30 (inet.0, static) via re0:mgmt-0, fxp0.0"]


def test_custom_pattern_is_used():
    text = table([rt("10.0.1.0/30", [entry(nhs=[nh(via="et-0/0/0.0")])])])
    assert junos.parse_management_routes(text, mgmt=re.compile(r"et-")) == [
        "10.0.1.0/30 (inet.0, static) via et-0/0/0.0"]
    assert junos.parse_management_routes(text) == []


def test_destination_without_length_is_not_a_prefix_with_exact_message():
    text = table([rt("10.0.1.0", [entry(nhs=[MGMT])])])
    with pytest.raises(DriverError) as e:
        junos.parse_management_routes(text)
    assert str(e.value) == PFX + "not a prefix: '10.0.1.0'"


def test_missing_destination_names_the_command():
    r = {"rt-entry": [entry(nhs=[MGMT])]}
    with pytest.raises(DriverError) as e:
        junos.parse_management_routes(table([r]))
    assert str(e.value) == PFX + snippet(f"no 'rt-destination': {str(r)[:150]}")


# ------------------------------------------------------------------------------ parse_management_routes: errors

def test_count_that_disagrees_with_the_listing_raises_with_the_command():
    data = json.loads(read("junos_route_table.txt"))
    data["route-information"][0]["route-table"][0]["total-route-count"][0]["data"] = "14"
    with pytest.raises(DriverError) as e:
        junos.parse_management_routes(json.dumps(data))
    assert str(e.value) == PFX + "table inet.0: 14 routes, 2 hidden, but 11 listed"


def test_hidden_count_that_disagrees_raises():
    data = json.loads(read("junos_route_table.txt"))
    data["route-information"][0]["route-table"][0]["hidden-route-count"][0]["data"] = "0"
    with pytest.raises(DriverError) as e:
        junos.parse_management_routes(json.dumps(data))
    assert str(e.value) == PFX + "table inet.0: 13 routes, 0 hidden, but 11 listed"


def test_answer_for_another_table_raises_with_the_command():
    with pytest.raises(DriverError) as e:
        junos.parse_management_routes(table([rt()], name="inet6.0"), "inet.0")
    assert str(e.value) == PFX + "table 'inet6.0' in the answer for 'inet.0'"


def test_route_table_not_a_list_raises_with_the_command():
    text = json.dumps({"route-information": [{"route-table": "inet.0"}]})
    with pytest.raises(DriverError) as e:
        junos.parse_management_routes(text)
    assert str(e.value) == PFX + "route-table: inet.0"


def test_table_missing_its_name_raises_with_the_command():
    t = {"total-route-count": leaf("0"), "hidden-route-count": leaf("0")}
    text = json.dumps({"route-information": [{"route-table": [t]}]})
    with pytest.raises(DriverError) as e:
        junos.parse_management_routes(text)
    assert str(e.value) == PFX + snippet(f"no 'table-name': {str(t)[:150]}")


def test_route_without_entries_raises_with_the_command():
    r = {"rt-destination": leaf("10.0.1.0/30")}
    with pytest.raises(DriverError) as e:
        junos.parse_management_routes(table([r], total=0))
    assert str(e.value) == PFX + snippet(f"route without rt-entry: {str(r)[:150]}")


def test_entry_without_protocol_name_raises_with_the_command():
    bad = {"active-tag": leaf("*"), "nh": [MGMT]}
    with pytest.raises(DriverError) as e:
        junos.parse_management_routes(table([rt("10.0.1.0/30", [bad])]))
    assert str(e.value) == PFX + snippet(f"no 'protocol-name': {str(bad)[:150]}")


def test_unmapped_protocol_raises_with_the_command():
    with pytest.raises(DriverError) as e:
        junos.parse_management_routes(table([rt("10.0.1.0/30", [entry("Weird", nhs=[MGMT])])]))
    assert str(e.value) == PFX + "protocol-name 'Weird' is not one this driver maps to a protocol"


def test_entry_without_active_tag_raises_with_the_command():
    bad = {"protocol-name": leaf("Static"), "nh": [MGMT]}
    with pytest.raises(DriverError) as e:
        junos.parse_management_routes(table([rt("10.0.1.0/30", [bad])]))
    assert str(e.value) == PFX + snippet(f"no 'active-tag': {str(bad)[:150]}")


def test_next_hops_not_a_list_raise_with_the_command():
    with pytest.raises(DriverError) as e:
        junos.parse_management_routes(table([rt("10.0.1.0/30", [entry(nhs="re0:mgmt-0")])]))
    assert str(e.value) == PFX + "nh: re0:mgmt-0"


def test_next_hop_item_not_an_object_raises_with_the_command():
    with pytest.raises(DriverError) as e:
        junos.parse_management_routes(table([rt("10.0.1.0/30", [entry(nhs=["x"])])]))
    assert str(e.value) == PFX + "nh: ['x']"


def test_via_not_a_leaf_list_raises_with_the_command():
    bad = {"via": "re0:mgmt-0"}
    with pytest.raises(DriverError) as e:
        junos.parse_management_routes(table([rt("10.0.1.0/30", [entry(nhs=[bad])])]))
    assert str(e.value) == PFX + "via: re0:mgmt-0"


def test_via_with_non_text_data_raises_with_the_command():
    with pytest.raises(DriverError) as e:
        junos.parse_management_routes(table([rt("10.0.1.0/30", [entry(nhs=[{"via": [{"data": 5}]}])])]))
    assert str(e.value) == PFX + "via: 5"


def test_via_given_twice_raises_with_the_command():
    bad = {"via": leaf("fxp0.0") + leaf("em0")}
    with pytest.raises(DriverError) as e:
        junos.parse_management_routes(table([rt("10.0.1.0/30", [entry(nhs=[bad])])]))
    assert str(e.value) == PFX + snippet(f"via more than once: {str(bad['via'])[:150]}")


# ------------------------------------------------------------------------------ JunosDriver.management_routes

class Lab:
    """Answers each Junos command by its exact text and records the commands in order."""

    def __init__(self, answers):
        self.answers, self.calls = answers, []

    def exec(self, node, cmd, timeout=60, input=None):
        line = cmd[-1]
        head, tail = "cli -c '", " | display json | no-more'"
        assert line.startswith(head) and line.endswith(tail), line
        command = line[len(head):-len(tail)]
        self.calls.append(command)
        if command not in self.answers:
            raise AssertionError(f"unexpected command: {command}")
        return ExecResult(cmd, 0, self.answers[command], "")


NO_TABLE = read("junos_route_no_table.txt")


def instance(name: str, ribs: list) -> str:
    core = {"instance-name": leaf(name), "instance-type": leaf("virtual-router"),
            "instance-rib": [{"irib-name": leaf(r)} for r in ribs]}
    return json.dumps({"instance-information": [{"instance-core": [core]}]})


EMPTY_INSTANCES = json.dumps({"instance-information": [{}]})


def test_default_arguments_read_master_inet_and_inet6_in_that_order():
    lab = Lab({"show route table inet.0": table([rt("10.0.1.0/30", [entry(nhs=[MGMT])])]),
               "show route table inet6.0": table([rt("2001:db8::/32", [entry("BGP", nhs=[nh(via="fxp0.0")])])],
                                                  name="inet6.0")})
    assert JunosDriver(lab, "j1").management_routes() == [
        "10.0.1.0/30 (inet.0, static) via re0:mgmt-0", "2001:db8::/32 (inet6.0, bgp) via fxp0.0"]
    assert lab.calls == ["show route table inet.0", "show route table inet6.0"]


def test_default_vrf_with_real_captures_has_none():
    lab = Lab({"show route table inet.0": read("junos_route_table.txt"),
               "show route table inet6.0": read("junos_route_table_v6.txt")})
    assert JunosDriver(lab, "j1").management_routes("default") == []
    assert lab.calls == ["show route table inet.0", "show route table inet6.0"]


def test_vrf_reads_its_own_tables_and_names_them_in_the_lines():
    lab = Lab({"show route table RED.inet.0": table([rt("10.1.0.0/16", [entry(nhs=[MGMT])])], name="RED.inet.0"),
               "show route table RED.inet6.0": table([rt("2001:db8:1::/48", [entry(nhs=[nh(via="em0.0")])])],
                                                      name="RED.inet6.0")})
    assert JunosDriver(lab, "j1").management_routes("RED") == [
        "10.1.0.0/16 (RED.inet.0, static) via re0:mgmt-0", "2001:db8:1::/48 (RED.inet6.0, static) via em0.0"]
    assert lab.calls == ["show route table RED.inet.0", "show route table RED.inet6.0"]


def test_missing_table_of_an_existing_instance_is_no_routes_and_asks_the_instance():
    lab = Lab({"show route table RED.inet.0": table([rt("10.1.0.0/16", [entry(nhs=[MGMT])])], name="RED.inet.0"),
               "show route table RED.inet6.0": NO_TABLE,
               "show route instance RED": instance("RED", ["RED.inet.0"])})
    assert JunosDriver(lab, "j1").management_routes("RED") == ["10.1.0.0/16 (RED.inet.0, static) via re0:mgmt-0"]
    assert lab.calls == ["show route table RED.inet.0", "show route table RED.inet6.0", "show route instance RED"]


def test_missing_table_of_two_families_confirms_the_instance_twice():
    lab = Lab({"show route table RED.inet.0": NO_TABLE, "show route table RED.inet6.0": NO_TABLE,
               "show route instance RED": instance("RED", ["RED.other"])})
    assert JunosDriver(lab, "j1").management_routes("RED") == []
    assert lab.calls == ["show route table RED.inet.0", "show route instance RED",
                         "show route table RED.inet6.0", "show route instance RED"]


def test_missing_table_in_the_default_vrf_asks_for_master():
    lab = Lab({"show route table inet.0": table([], total=0), "show route table inet6.0": NO_TABLE,
               "show route instance master": instance("master", ["inet.0"])})
    assert JunosDriver(lab, "j1").management_routes() == []
    assert lab.calls == ["show route table inet.0", "show route table inet6.0", "show route instance master"]


def test_missing_table_that_the_instance_lists_raises_with_the_exact_message():
    lab = Lab({"show route table RED.inet.0": NO_TABLE,
               "show route instance RED": instance("RED", ["RED.inet.0"])})
    with pytest.raises(DriverError) as e:
        JunosDriver(lab, "j1").management_routes("RED")
    assert str(e.value) == "`show route` says table RED.inet.0 doesn't exist, but routing-instance 'RED' lists it"
    assert lab.calls == ["show route table RED.inet.0", "show route instance RED"]


def test_missing_inet6_table_that_the_instance_lists_raises_naming_inet6():
    lab = Lab({"show route table RED.inet.0": table([], name="RED.inet.0", total=0),
               "show route table RED.inet6.0": NO_TABLE,
               "show route instance RED": instance("RED", ["RED.inet.0", "RED.inet6.0"])})
    with pytest.raises(DriverError) as e:
        JunosDriver(lab, "j1").management_routes("RED")
    assert str(e.value) == "`show route` says table RED.inet6.0 doesn't exist, but routing-instance 'RED' lists it"


def test_missing_table_in_a_missing_instance_is_no_such_instance():
    lab = Lab({"show route table NOPE.inet.0": NO_TABLE, "show route instance NOPE": EMPTY_INSTANCES})
    with pytest.raises(NoSuchInstance) as e:
        JunosDriver(lab, "j1").management_routes("NOPE")
    assert str(e.value) == "routing-instance 'NOPE' does not exist on j1"
    assert lab.calls == ["show route table NOPE.inet.0", "show route instance NOPE"]


def test_master_is_refused_as_a_vrf_name_without_any_command():
    lab = Lab({})
    with pytest.raises(DriverError, match="VRF 'master' is the Junos name for the default instance"):
        JunosDriver(lab, "j1").management_routes("master")
    assert lab.calls == []
