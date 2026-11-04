"""Mutation on 0563e93: faults.py joined the mutation gate (it was outside it through Layer 6 rounds 2-9), and the old
inject_routes delivery path had survivors. Each test kills mutants by name (netdryrun.faults.xǁRouteInjectionǁ<fn>__mutmut_N).

The device output is the live captures test_inject_sent_counts builds on; error texts are pinned because they reach a
scenario's error and the JSON report."""
import copy
import json
import time

import pytest

from netdryrun.faults import RouteInjection, Session
from netdryrun.lab import ExecResult, LabError
from netdryrun.verify.snapshot import SnapshotError
from test_inject_sent_counts import (_INJECTED, R1, ApplyLab, InjectLab, TableLab, _path, _table, adv, applied, listing,
                                     live, steady, summary)

ADJ = "show bgp ipv4 unicast neighbors 10.0.12.2 advertised-routes detail json"
TABLE = "show bgp vrf all ipv4 unicast detail json"


def _msg(cmd: str, what: str) -> str:
    return f"unexpected output from `{cmd}`: {what}"


class Recording(InjectLab):
    """InjectLab that keeps every exec's argv."""

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.argv = []

    def exec(self, node, cmd, timeout=60, input=None):
        self.argv.append(list(cmd))
        return super().exec(node, cmd, timeout, input)


# --- established, sessions ------------------------------------------------------------------------------------------

def test_a_family_with_no_session_before_another_family_is_still_read():
    """established_18 (`continue` -> `break`): ipv4 has no session configured (`{}`, live); ipv6's peer was dropped."""
    lab = InjectLab([], summaries6=[summary({"2001:db8::2": "Established"})])
    lab.summaries = ["{}"]
    inj = RouteInjection(lab, "r1", ["100.64.0.0/24", "2001:db8:66::/48"], [])
    assert inj.established() == {"ipv4": [], "ipv6": ["2001:db8::2"]}


def test_a_session_list_that_isnt_an_object_names_the_command():
    """sessions_14."""
    lab = InjectLab([summary({"10.0.12.2": "Established"})], neighbors=["[1, 2]"])
    with pytest.raises(LabError) as e:
        RouteInjection(lab, "r1", [R1], []).sessions()
    assert str(e.value) == "inject_routes on r1: unexpected output from `show bgp neighbors json`"


def test_a_peer_entry_that_isnt_an_object_is_a_lab_error_naming_it():
    """sessions_16 (`or` -> `and`: a list entry crashed with AttributeError), sessions_19 (the text)."""
    lab = InjectLab([summary({"10.0.12.2": "Established"})], neighbors=[json.dumps({"10.0.12.2": [1]})])
    with pytest.raises(LabError) as e:
        RouteInjection(lab, "r1", [R1], []).sessions()
    assert str(e.value) == ("inject_routes on r1: no dropped-session count for 10.0.12.2 "
                            "(`show bgp neighbors json`)")


# --- advertised -----------------------------------------------------------------------------------------------------

def test_the_advertised_listing_is_read_with_vtysh_dash_c():
    """advertised_15, _17, _19, _20: the exact argv."""
    lab = Recording([live("before"), live("after")], advertised={"10.0.12.2": adv(R1), "10.0.13.2": adv(R1)})
    inj = applied(lab, "r1", [R1])
    lab.argv.clear()
    assert inj.advertised("ipv4", "10.0.12.2") == {R1}
    assert lab.argv == [["vtysh", "-c", ADJ]]


def test_an_unreadable_advertised_listing_names_its_command():
    """advertised_22 (parse_adj's command)."""
    lab = InjectLab([live("before"), live("after")], advertised={"10.0.12.2": "[]"})
    inj = applied(lab, "r1", [R1])
    with pytest.raises(SnapshotError) as e:
        inj.advertised("ipv4", "10.0.12.2")
    assert str(e.value) == _msg(ADJ, "[]")


def test_a_single_advertised_path_needs_no_best_path_flag():
    """advertised_62 (`len(paths) > 1` -> `>= 1`): one path without add-path is the one sent, flagged best or not."""
    one = copy.deepcopy(_INJECTED)
    one.pop("bestpath", None)
    inj = applied(InjectLab([live("before"), live("after")], advertised={"10.0.12.2": listing({R1: [one]})}), "r1", [R1])
    assert inj.advertised("ipv4", "10.0.12.2") == {R1}


def _local_not_bool():
    """A network-statement path whose `local` flag isn't a boolean: parse_attrs reads `sourced` first and stops there,
    so only _is_injected's own `local` read sees it."""
    p = copy.deepcopy(_INJECTED)
    p["local"] = "yes"
    return p


def test_a_non_boolean_local_flag_on_an_advertised_path_names_command_and_path():
    """advertised_72, _74 (what advertised passes on), _is_injected_24, _27 (the local flag's command and path)."""
    inj = applied(InjectLab([live("before"), live("after")],
                            advertised={"10.0.12.2": listing({R1: [_local_not_bool()]})}), "r1", [R1])
    with pytest.raises(SnapshotError) as e:
        inj.advertised("ipv4", "10.0.12.2")
    assert str(e.value) == _msg(ADJ, f"{R1} path 0.local: not a boolean: 'yes'")


# --- record_listed --------------------------------------------------------------------------------------------------

def test_record_listed_reads_the_default_vrfs_advertised_listing_per_family():
    """record_listed_8, _15, _16: the exact command."""
    lab = Recording([live("before")], advertised_before={"10.0.12.2": adv()})
    applied(lab, "r1", [R1])
    assert ["vtysh", "-c", ADJ] in lab.argv


def test_a_listing_of_other_prefixes_means_the_peer_had_none_of_the_injected_ones():
    """record_listed_23, _24, _37, _38 (afi, direction): a wrong family or direction fails the read, and a failed read
    counts as having them all."""
    lab = InjectLab([live("before")], advertised_before={"10.0.12.2": adv("10.0.0.0/24"), "10.0.13.2": adv("10.0.0.0/24")})
    assert applied(lab, "r1", [R1]).listed_before == {}


def test_a_multipath_listing_without_add_path_is_read_by_its_best_path():
    """record_listed_30, _39 (add_path_tx True: several paths without TX ids fail the read and count as all)."""
    other = "10.0.0.0/24"
    two = listing({other: [_path(_INJECTED, other, bestpath={"overall": True}),
                           _path(_INJECTED, other, bestpath={"overall": False})]})
    lab = InjectLab([live("before")], advertised_before={"10.0.12.2": two, "10.0.13.2": adv()})
    assert applied(lab, "r1", [R1]).listed_before == {}


# --- _own_paths, _missing -------------------------------------------------------------------------------------------

def _own(text, prefixes=(R1,)):
    return RouteInjection(TableLab(text), "r1", list(prefixes), [])


def _own_err(text) -> str:
    with pytest.raises(LabError) as e:
        _own(text)._own_paths("ipv4")
    return str(e.value)


def test_a_table_without_the_default_instance_has_no_own_paths():
    """_own_paths_21 (`or True`: KeyError), _27, _28 (the empty default's key)."""
    assert _own(json.dumps({"red": {"routes": {}}}))._own_paths("ipv4") == {}


def test_own_path_errors_in_full():
    """_own_paths_7 (_json's command), _18, _29 (`or` -> `and` on a non-object), _32, _74 (the wrap)."""
    assert _own_err("not json").startswith(f"inject_routes on r1: unexpected output from `{TABLE}`")
    assert _own_err("[]") == f"inject_routes on r1: unexpected output from `{TABLE}`"
    assert _own_err(json.dumps({"default": []})) == f"inject_routes on r1: unexpected output from `{TABLE}`: default: no routes"


def test_a_table_key_that_isnt_a_prefix_names_the_command():
    """_own_paths_38, _40 (canon_prefix's where)."""
    doc = json.loads(_table())
    doc["default"]["routes"]["not-a-prefix"] = []
    assert _own_err(json.dumps(doc)) == f"inject_routes on r1: {TABLE}: not a prefix: 'not-a-prefix'"


def test_a_destination_object_is_read_and_checked_against_its_prefix():
    """_own_paths_44, _45, _47 (_dest_paths' command, prefix and where)."""
    doc = json.loads(_table(injected=(R1,)))
    paths = doc["default"]["routes"][R1]
    doc["default"]["routes"][R1] = {"prefix": R1, "paths": paths}
    assert _own(json.dumps(doc))._missing(want_present=True) == []
    doc["default"]["routes"][R1] = {"prefix": R1, "paths": paths, "pathCount": len(paths) + 1}
    assert _own_err(json.dumps(doc)) == ("inject_routes on r1: " + _msg(TABLE, f"{R1}: pathCount {len(paths) + 1} but "
                                                                         f"{len(paths)} paths listed"))


def test_an_own_path_that_cant_be_read_names_command_and_path():
    """_own_paths_52, _54, _56 (parse_attrs' command and path), _68, _70 (_is_injected's)."""
    doc = json.loads(_table(injected=(R1,)))
    p = doc["default"]["routes"][R1][0]
    bad = copy.deepcopy(doc)
    bad["default"]["routes"][R1][0]["origin"] = 7
    assert _own_err(json.dumps(bad)).startswith("inject_routes on r1: " + _msg(TABLE, f"{R1} path 0.origin"))
    p["local"] = "yes"
    assert _own_err(json.dumps(doc)) == "inject_routes on r1: " + _msg(TABLE, f"{R1} path 0.local: not a boolean: 'yes'")


class TwoFamilies(TableLab):
    def __init__(self, v4, v6):
        self.v4, self.v6 = v4, v6

    def exec(self, node, cmd, timeout=60, input=None):
        text = {TABLE: self.v4, "show bgp vrf all ipv6 unicast detail json": self.v6}.get(cmd[-1], "")
        return ExecResult(cmd, 0, text, "")


def test_injected_prefixes_of_both_families_are_all_found():
    """_missing_4 (`|=` -> `=`: only the last family's prefixes counted)."""
    v6 = "2001:db8:66::/48"
    doc = json.loads(_table(injected=(R1,)))
    six = {"default": {"routes": {v6: copy.deepcopy(doc["default"]["routes"][R1])}}}
    for p in six["default"]["routes"][v6]:
        for nh in p.get("nexthops", []):
            nh.update(ip="::", afi="ipv6")
    inj = RouteInjection(TwoFamilies(json.dumps(doc), json.dumps(six)), "r1", [R1, v6], [])
    assert inj._missing(want_present=True) == []


# --- await_delivery: the bound and the loop -------------------------------------------------------------------------

class Clock:
    def __init__(self, monkeypatch):
        self.now, self.sleeps = 0.0, []
        monkeypatch.setattr("netdryrun.faults.time.monotonic", lambda: self.now)
        monkeypatch.setattr("netdryrun.faults.time.sleep", self.sleep)

    def sleep(self, s):
        self.sleeps.append(s)
        self.now += s
        if len(self.sleeps) > 200:
            raise AssertionError("waited too long")


def _never(monkeypatch, sessions):
    clock = Clock(monkeypatch)
    lab = InjectLab([live("before")], advertised={"10.0.12.2": adv(), "10.0.13.2": adv()})
    inj = applied(lab, "r1", [R1])
    inj.sessions_before = sessions
    inj.await_delivery(settle=10)
    return clock, inj


@pytest.mark.parametrize("mrai_ms, sleeps", [(5000, 12), (None, 37), (0, 7)])
def test_the_wait_is_settle_plus_twice_the_longest_interval_plus_two(monkeypatch, mrai_ms, sleeps):
    """await_delivery_2 to _7, _9, _10, _13, _19, _38 (`>` -> `>=` at the edge), _40, _41 (2 s steps). Deadline = 10 +
    2 x interval + 2: 5 s -> 22 (checks at 0, 2 .. 22, then 24 > 22: 12 sleeps), unread -> 30 s -> 72 (37 sleeps),
    0 -> 12 (7 sleeps)."""
    clock, inj = _never(monkeypatch, {"10.0.12.2": Session(0, False, 60000, mrai_ms),
                                      "10.0.13.2": Session(0, False, 60000, 0)})
    assert clock.sleeps == [2] * sleeps and inj.late == {"10.0.12.2", "10.0.13.2"}


def test_the_two_seconds_on_top_of_the_bound(monkeypatch):
    """await_delivery_19 (+2 -> +3): settle 9 and a 5 s interval give 21, an odd deadline, so a second more shows (checks
    at 0, 2 .. 20, then 22 > 21: 11 sleeps; with 22 it takes 12)."""
    clock = Clock(monkeypatch)
    lab = InjectLab([live("before")], advertised={"10.0.12.2": adv(), "10.0.13.2": adv()})
    inj = applied(lab, "r1", [R1])
    inj.sessions_before = {"10.0.12.2": Session(0, False, 60000, 5000)}
    inj.await_delivery(settle=9)
    assert clock.sleeps == [2] * 11


def test_with_no_session_read_the_interval_counts_as_30_seconds(monkeypatch):
    """await_delivery_15, _17, _18 (max's default)."""
    clock, _ = _never(monkeypatch, {})
    assert clock.sleeps == [2] * 37


def test_an_unreadable_peer_doesnt_stop_the_others_being_checked(monkeypatch):
    """await_delivery_30 (`continue` -> `break`): 10.0.12.2's listing fails every time; 10.0.13.2 has the prefix."""
    Clock(monkeypatch)
    lab = InjectLab([live("before")], advertised={"10.0.12.2": "not json", "10.0.13.2": adv(R1)})
    inj = applied(lab, "r1", [R1])
    inj.await_delivery(settle=10)
    assert inj.late == {"10.0.12.2"}


# --- apply ----------------------------------------------------------------------------------------------------------

class Running(ApplyLab):
    def __init__(self, text, running="router bgp 65001\n"):
        super().__init__(text)
        self.running = running

    def exec(self, node, cmd, timeout=60, input=None):
        if cmd[-1] == "show running-config":
            return ExecResult(cmd, 0, self.running, "")
        if cmd[-1] == "show bgp ipv4 unicast summary json":
            return ExecResult(cmd, 0, summary({"10.0.12.2": "Established"}), "")
        if cmd[-1] == "show bgp neighbors json":
            return ExecResult(cmd, 0, steady(["10.0.12.2"]), "")
        if cmd[-1].endswith(" advertised-routes detail json"):
            return ExecResult(cmd, 0, adv(), "")
        return super().exec(node, cmd, timeout, input)


def _apply_err(lab, prefixes=(R1,), as_path=()) -> str:
    with pytest.raises(LabError) as e:
        RouteInjection(lab, "r1", list(prefixes), list(as_path)).apply()
    return str(e.value)


def test_apply_reads_the_sessions_and_stamps_the_time():
    """apply_50 (sessions_before), apply_55 (applied_at)."""
    inj = RouteInjection(Running(_table()), "r1", [R1], [])
    inj._apply_config = lambda lines: None
    inj._wait = lambda want_present: None
    t0 = time.monotonic()
    inj.apply()
    assert inj.sessions_before == {"10.0.12.2": Session(0, False, 600000, 0)}
    assert isinstance(inj.applied_at, float) and inj.applied_at >= t0


def test_a_node_without_bgp_names_itself():
    """apply_12."""
    assert _apply_err(Running(_table(), running="hostname r1\n")) == "inject_routes on r1: no 'router bgp' in the default VRF"


def test_six_conflicting_prefixes_name_the_first_five():
    """apply_20, _21, _22, _23."""
    six = [f"100.64.{i}.0/24" for i in range(6)]
    running = "router bgp 65001\n" + "".join(f" network {p}\n" for p in six)
    assert _apply_err(Running(_table(), running=running), six) == (
        "inject_routes on r1: 100.64.0.0/24, 100.64.1.0/24, 100.64.2.0/24, 100.64.3.0/24, 100.64.4.0/24 already "
        "configured there; inject prefixes the node does not announce yet")


def test_an_existing_injection_route_map_on_any_line_is_refused():
    """apply_30 (re.M: the route-map is not on the first line), _31."""
    running = "router bgp 65001\n!\nroute-map NDR-INJECT permit 10\n"
    assert _apply_err(Running(_table(), running=running), as_path=[65099]) == (
        "inject_routes on r1: route-map NDR-INJECT already exists")


def test_six_prefixes_the_node_already_originates_name_the_first_five():
    """apply_42 to _48."""
    six = [f"100.64.{i}.0/24" for i in range(6)]
    doc = json.loads(_table())
    own = copy.deepcopy(json.loads(_table(injected=("100.64.0.0/24",)))["default"]["routes"]["100.64.0.0/24"])
    for p in own:
        p.pop("local", None)   # a redistributed route: sourced, not local, empty AS path
    for p in six:
        doc["default"]["routes"][p] = copy.deepcopy(own)
    doc["default"].update(totalRoutes=len(doc["default"]["routes"]))
    assert _apply_err(Running(json.dumps(doc)), six) == (
        "inject_routes on r1: it already originates 100.64.0.0/24, 100.64.1.0/24, 100.64.2.0/24, 100.64.3.0/24, "
        "100.64.4.0/24 itself (a redistributed, aggregated or network route) with the AS path the injected routes "
        "would carry; inject prefixes it doesn't originate, or give the injection an as_path")
