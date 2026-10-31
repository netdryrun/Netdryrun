"""The intent file: every form parses to its canonical line, and every malformed file is an IntentError."""
import pytest

from netdryrun.verify.intent import IntentError, check_nodes, load_intent, parse_intent
from netdryrun.verify.snapshot import AsPath


def parse(lines=(), allow=None):
    data = {"intent": list(lines)}
    if allow is not None:
        data["allow_anywhere"] = allow
    return parse_intent(data, "t")


def test_every_form_parses():
    it = parse([
        {"prefix": "10.101.0.0/24", "appears_on": ["up1", "peer1"], "with": {"from": "10.0.2.1", "as_path": "65000 65101",
                                                                           "communities": ["no-export", "65000:1"]}},
        {"prefix": "203.0.113.0/24", "best_path_on": "edge1", "to": {"local_pref": 200, "med": None}},
        {"session": {"node": "edge1", "neighbor": "10.0.9.2", "afi": "ipv4-unicast"}, "goes": "down"},
        {"prefix": "192.0.2.128/25", "disappears_from": "cust1", "including_received_only": True},
        {"prefix": "198.51.100.0/24", "advertisement": {"node": "edge1", "neighbor": "192.0.2.9"}, "goes": "added"},
        {"prefix": "2001:db8::/32", "vrf": "cust", "advertisement": {"node": "edge1", "neighbor": "2001:db8::9"},
         "to": {"as_path": "65000 65000"}},
    ], allow=["10.200.*.0/24", {"prefix": "10.9.0.0/16", "vrf": "cust"}])
    a, b, s, d, adv, adv6 = it.lines
    assert a.form == "appears_on" and a.nodes == ("up1", "peer1") and a.state == "installed"
    assert a.pins["as_path"] == AsPath.parse("65000 65101") and a.pins["communities"] == ("65000:1", "65535:65281")
    assert b.to == {"local_pref": 200, "med": None} and b.vrf == "default"
    assert s.form == "session" and s.neighbor == "10.0.9.2" and s.goes == "down" and s.afi == "ipv4-unicast"
    assert d.nodes == ("cust1",) and d.including_received_only
    assert adv.goes == "added" and adv.neighbor == "192.0.2.9"
    assert adv6.vrf == "cust" and adv6.to["as_path"].render() == "65000 65000"
    assert [x.pattern for x in it.allow] == ["10.200.*.0/24", "10.9.0.0/16"] and it.allow[0].glob
    assert it.nodes() == {"up1", "peer1", "edge1", "cust1"}


def test_empty_intent():
    it = parse()
    assert it.empty and it.lines == []


@pytest.mark.parametrize("data", [
    None, [], "intent", {}, {"intent": None}, {"intent": {}}, {"intent": [], "extra": 1},
    {"intent": [{"prefix": "10.0.0.0/24"}]},                                                  # no form
    {"intent": [{"prefix": "10.0.0.0/24", "appears_on": ["a"], "disappears_from": ["b"]}]},  # two forms
    {"intent": [{"prefix": "10.0.0.1/24", "appears_on": ["a"]}]},                             # host bits
    {"intent": [{"prefix": "10.0.0.0", "appears_on": ["a"]}]},                                # no length
    {"intent": [{"prefix": "nope", "appears_on": ["a"]}]},
    {"intent": [{"appears_on": ["a"]}]},
    {"intent": [{"prefix": "10.0.0.0/24", "appears_on": []}]},
    {"intent": [{"prefix": "10.0.0.0/24", "appears_on": ["a", "a"]}]},
    {"intent": [{"prefix": "10.0.0.0/24", "appears_on": ["a"], "state": "fib"}]},
    {"intent": [{"prefix": "10.0.0.0/24", "appears_on": ["a"], "with": {"colour": 1}}]},
    {"intent": [{"prefix": "10.0.0.0/24", "appears_on": ["a"], "with": {"local_pref": "200"}}]},
    {"intent": [{"prefix": "10.0.0.0/24", "appears_on": ["a"], "with": {"communities": "65000:1"}}]},
    {"intent": [{"prefix": "10.0.0.0/24", "appears_on": ["a"], "with": {"as_path": "65000 x"}}]},
    {"intent": [{"prefix": "10.0.0.0/24", "appears_on": ["a"], "with": {"protocol": "ebgp"}}]},
    {"intent": [{"prefix": "10.0.0.0/24", "appears_on": ["a"], "state": "received", "with": {"protocol": "bgp"}}]},
    {"intent": [{"prefix": "10.0.0.0/24", "appears_on": ["a"], "vrf": "all"}]},
    {"intent": [{"prefix": "10.0.0.0/24", "appears_on": ["a"], "goes": "down"}]},            # key of another form
    {"intent": [{"prefix": "10.0.0.0/24", "best_path_on": "a"}]},                             # no to:
    {"intent": [{"prefix": "10.0.0.0/24", "best_path_on": ["a", "b"], "to": {"med": 1}}]},
    {"intent": [{"prefix": "10.0.0.0/24", "best_path_on": "a", "to": {}}]},
    {"intent": [{"prefix": "10.0.0.0/24", "best_path_on": "a", "to": {"protocol": "bgp"}}]},
    {"intent": [{"prefix": "10.0.0.0/24", "disappears_from": ["a"], "including_received_only": "yes"}]},
    {"intent": [{"session": {"node": "a", "neighbor": "10.0.0.1"}}]},                          # no goes
    {"intent": [{"session": {"node": "a", "neighbor": "10.0.0.1"}, "goes": "up"}]},
    {"intent": [{"session": {"node": "a", "neighbor": "eth1"}, "goes": "down"}]},
    {"intent": [{"session": {"node": "a"}, "goes": "down"}]},
    {"intent": [{"session": {"node": "a", "neighbor": "10.0.0.1", "afi": "evpn"}, "goes": "down"}]},
    {"intent": [{"prefix": "10.0.0.0/24", "advertisement": {"node": "a", "neighbor": "10.0.0.1"}}]},
    {"intent": [{"prefix": "10.0.0.0/24", "advertisement": {"node": "a", "neighbor": "10.0.0.1"}, "goes": "down"}]},
    {"intent": [{"prefix": "10.0.0.0/24", "advertisement": {"node": "a", "neighbor": "10.0.0.1"}, "goes": "added",
                 "to": {"med": 1}}]},
    {"intent": [{"prefix": "10.0.0.0/24", "advertisement": {"node": "a", "neighbor": "10.0.0.1"},
                 "to": {"from": "10.0.0.1"}}]},
    # two lines about the same route on the same node
    {"intent": [{"prefix": "10.0.0.0/24", "appears_on": ["a"]}, {"prefix": "10.0.0.0/24", "best_path_on": "a",
                                                                "to": {"med": 1}}]},
    {"intent": [{"session": {"node": "a", "neighbor": "10.0.0.1"}, "goes": "down"},
                {"session": {"node": "a", "neighbor": "10.0.0.1"}, "goes": "down"}]},
    {"intent": [], "allow_anywhere": "10.0.0.0/8"},
    {"intent": [], "allow_anywhere": ["*"]},
    {"intent": [], "allow_anywhere": ["*/*"]},
    {"intent": [], "allow_anywhere": ["10.*"]},
    {"intent": [], "allow_anywhere": ["1*.0.0.0/8"]},
    {"intent": [], "allow_anywhere": ["10.0.[0-9.0/24"]},
    {"intent": [], "allow_anywhere": ["10.0.0.1/24"]},
    {"intent": [], "allow_anywhere": ["10.0.0.0/24", "10.0.0.0/24"]},
    {"intent": [], "allow_anywhere": [{"prefix": "10.0.0.0/24", "node": "a"}]},
])
def test_malformed_intents_are_errors(data):
    with pytest.raises(IntentError):
        parse_intent(data, "t")


def test_allow_anywhere_matches_exactly_or_by_explicit_glob_never_by_containment():
    it = parse(allow=["10.200.*.0/24", "10.0.0.0/8", "2001:db8:1:*::/64"])
    glob, exact, v6 = it.allow
    assert glob.matches("10.200.7.0/24", "default") and not glob.matches("10.200.7.0/25", "default")
    assert not glob.matches("10.200.7.0/24", "cust")                      # default VRF only
    assert exact.matches("10.0.0.0/8", "default")
    assert not exact.matches("10.1.0.0/16", "default")                     # no supernet containment
    assert v6.matches("2001:db8:1:2::/64", "default") and not v6.matches("2001:db8:4::/64", "default")


def test_load_intent_reads_yaml_strictly(tmp_path):
    p = tmp_path / "intent.yml"
    p.write_text("intent:\n  - prefix: 10.0.0.0/24\n    appears_on: [r1]\n")
    assert load_intent(p).lines[0].nodes == ("r1",)
    p.write_text("intent: []\nintent: []\n")                                # duplicate key
    with pytest.raises(IntentError):
        load_intent(p)
    p.write_text("intent: [\n")
    with pytest.raises(IntentError):
        load_intent(p)
    with pytest.raises(IntentError):
        load_intent(tmp_path / "missing.yml")


def test_check_nodes_refuses_unknown_and_unobserved_nodes():
    it = parse([{"prefix": "10.0.0.0/24", "appears_on": ["r1", "r2"]}])
    check_nodes(it, {"r1": "frr", "r2": "frr"})
    with pytest.raises(IntentError):
        check_nodes(it, {"r1": "frr"})
    with pytest.raises(IntentError):
        check_nodes(it, {"r1": "frr", "r2": ""})


# --- allow_anywhere breadth (review finding 3) ---------------------------------------------------------------

@pytest.mark.parametrize("entry", [
    "10.*/*", "10.*.0.0/16", "10.*.*.0/24", "*.0.0.0/8", "10.*.0.0/24",        # wider than /16 of reach
    "10.200.*.0/*", "10.200.*.0/2?", "10.200.*.0",                            # the length is always explicit
    "10.2*.0.0/24", "10.200.1*.0/24", "10.200.*1.0/24",                        # `*` is one whole octet
    "10.20?.1.0/24", "10.200.[0-3].0/24",                                      # no other wildcards
    "10.200.0.*/24",                                                          # a wildcard past the length
    "10.200.*.1/24",                                                          # host bits
    "2001:db8:*::/48", "2001:*::/32", "2001:db8:1:*::/*", "2001:db8:1:5*::/64", "2001:db8:1:*::/48",
])
def test_allow_anywhere_globs_are_bounded(entry):
    with pytest.raises(IntentError):
        parse(allow=[entry])


def test_allow_anywhere_glob_reach_and_matching():
    v4, v4b, v6 = parse(allow=["10.200.*.0/24", "10.200.*.*/32", "2001:db8:1:*::/64"]).allow
    assert v4.matches("10.200.7.0/24", "default") and v4.matches("10.200.255.0/24", "default")
    assert not v4.matches("10.200.7.0/25", "default") and not v4.matches("10.201.7.0/24", "default")
    assert not v4.matches("10.200.7.128/25", "default")
    assert v4b.matches("10.200.1.9/32", "default") and not v4b.matches("10.200.1.0/24", "default")
    assert v6.matches("2001:db8:1:5::/64", "default") and v6.matches("2001:0db8:0001:ffff::/64", "default")
    assert not v6.matches("2001:db8:2:5::/64", "default") and not v6.matches("2001:db8:1:5::/80", "default")
    assert not v6.matches("10.200.7.0/24", "default") and not v4.matches("2001:db8:1:5::/64", "default")


def test_advertisement_with_is_only_for_goes_added():
    adv = {"prefix": "10.0.0.0/24", "advertisement": {"node": "a", "neighbor": "10.0.0.1"}}
    ln = parse([{**adv, "goes": "added", "with": {"as_path": "65000 65000", "med": 5}}]).lines[0]
    assert ln.pins == {"as_path": AsPath.parse("65000 65000"), "med": 5}
    for bad in ({**adv, "goes": "removed", "with": {"med": 5}}, {**adv, "to": {"med": 5}, "with": {"med": 5}},
                {**adv, "goes": "added", "with": {"from": "10.0.0.1"}}, {**adv, "goes": "added", "with": {"protocol": "bgp"}}):
        with pytest.raises(IntentError):
            parse([bad])


# --- the whole intent is validated before anything boots (review finding 10) ---------------------------------

def test_a_session_line_names_its_address_family():
    with pytest.raises(IntentError, match="afi"):
        parse([{"session": {"node": "edge1", "neighbor": "10.0.9.2"}, "goes": "down"}])
    ln = parse([{"session": {"node": "edge1", "neighbor": "10.0.9.2", "afi": "ipv4-unicast"}, "goes": "down"}]).lines[0]
    assert ln.afi == "ipv4-unicast"


# --- the echoed text: what a human reviews at the top of every report (found by mutation testing) -----------

ADV = {"prefix": "198.51.100.0/24", "advertisement": {"node": "edge1", "neighbor": "192.0.2.9"}}
SESSION = {"session": {"node": "edge1", "neighbor": "10.0.9.2", "afi": "ipv4-unicast"}, "goes": "down"}


@pytest.mark.parametrize("line,text", [
    ({"prefix": "10.0.0.0/24", "appears_on": ["a", "b"]}, "10.0.0.0/24 appears on a, b"),
    ({"prefix": "10.0.0.0/24", "vrf": "cust", "appears_on": "a", "state": "selected"},
     "10.0.0.0/24 (vrf cust) appears on a (selected)"),
    ({"prefix": "10.0.0.0/24", "appears_on": "a", "state": "received"}, "10.0.0.0/24 appears on a (received)"),
    ({"prefix": "10.0.0.0/24", "appears_on": "a", "state": "installed"}, "10.0.0.0/24 appears on a"),
    ({"prefix": "10.0.0.0/24", "disappears_from": ["a", "b"]}, "10.0.0.0/24 disappears from a, b"),
    ({"prefix": "10.0.0.0/24", "vrf": "cust", "disappears_from": "a", "including_received_only": True},
     "10.0.0.0/24 (vrf cust) disappears from a (including received-only)"),
    ({"prefix": "10.0.0.0/24", "disappears_from": "a", "including_received_only": False}, "10.0.0.0/24 disappears from a"),
    ({"prefix": "203.0.113.0/24", "best_path_on": "edge1",
      "to": {"local_pref": 200, "med": None, "as_path": "65000 65000", "communities": ["no-export", "65000:1"]}},
     "203.0.113.0/24 best path on edge1 changes to local_pref=200, med=null, as_path='65000 65000', "
     "communities=[65000:1, 65535:65281]"),
    ({"prefix": "203.0.113.0/24", "vrf": "cust", "best_path_on": "edge1", "to": {"from": "10.0.0.1"}},
     "203.0.113.0/24 (vrf cust) best path on edge1 changes to from=10.0.0.1"),
    (SESSION, "session edge1 -> 10.0.9.2 ipv4-unicast goes down"),
    ({**SESSION, "session": {**SESSION["session"], "vrf": "cust", "afi": "ipv6-unicast"}},
     "session edge1 -> 10.0.9.2 (vrf cust) ipv6-unicast goes down"),
    ({**ADV, "goes": "added"}, "198.51.100.0/24 advertised by edge1 to 192.0.2.9: added"),
    ({**ADV, "goes": "removed"}, "198.51.100.0/24 advertised by edge1 to 192.0.2.9: removed"),
    ({**ADV, "goes": "added", "with": {"as_path": "65000 65000", "med": 5, "communities": []}},
     "198.51.100.0/24 advertised by edge1 to 192.0.2.9: added with as_path='65000 65000', med=5, communities=[]"),
    ({**ADV, "vrf": "cust", "to": {"med": 50, "local_pref": None}},
     "198.51.100.0/24 (vrf cust) advertised by edge1 to 192.0.2.9: changes to med=50, local_pref=null"),
])
def test_every_line_echoes_exactly_what_it_declares(line, text):
    ln = parse([line]).lines[0]
    assert ln.text == text


def test_a_session_line_keeps_its_vrf():
    ln = parse([{**SESSION, "session": {**SESSION["session"], "vrf": "cust"}}]).lines[0]
    assert ln.vrf == "cust" and ln.nodes == ("edge1",) and ln.neighbor == "10.0.9.2"
    assert parse([SESSION]).lines[0].vrf == "default"


def test_the_echo_is_the_file_as_given():
    lines, allow = [{"prefix": "10.0.0.0/24", "appears_on": "a"}], ["10.200.*.0/24"]
    assert parse(lines, allow).echo == {"intent": lines, "allow_anywhere": allow}
    assert parse(lines).echo == {"intent": lines, "allow_anywhere": []}


def test_the_default_source_names_an_inline_intent():
    from netdryrun.verify.intent import parse_intent_text

    assert parse_intent({"intent": []}).source == "<intent>"
    assert parse_intent_text("intent: []\n").source == "<intent>"


# --- every attribute `to:` and `with:` take, in its canonical form ---------------------------------------------

@pytest.mark.parametrize("key,value,canonical", [
    ("from", "local", "local"),
    ("from", "10.0.0.1", "10.0.0.1"),
    ("next_hop", "10.0.0.2", ("10.0.0.2",)),
    ("next_hop", ["10.0.0.2", "10.0.0.1", "10.0.0.2"], ("10.0.0.1", "10.0.0.2")),
    ("origin", "incomplete", "incomplete"),
    ("local_pref", 4294967295, 4294967295),
    ("med", 0, 0),
    ("weight", None, None),
    ("communities", ["no-export", "65000:1"], ("65000:1", "65535:65281")),
    ("large_communities", ["65000:001:2", "65000:1:1"], ("65000:1:1", "65000:1:2")),
    ("ext_communities", ["RT:65002:100"], ("rt:65002:100",)),
    ("ext_communities", [], ()),
    ("cluster_list", ["10.0.0.9", "10.0.0.1"], ("10.0.0.9", "10.0.0.1")),     # order kept
    ("cluster_list", [], ()),
    ("originator_id", "10.0.0.9", "10.0.0.9"),
    ("originator_id", None, None),
])
def test_every_attribute_parses_to_its_canonical_form(key, value, canonical):
    ln = parse([{"prefix": "10.0.0.0/24", "best_path_on": "a", "to": {key: value}}]).lines[0]
    assert ln.to == {key: canonical}
    ln = parse([{"prefix": "10.0.0.0/24", "appears_on": "a", "with": {key: value}}]).lines[0]
    assert ln.pins == {key: canonical}


@pytest.mark.parametrize("key,value", [
    ("local_pref", 4294967296), ("med", -1), ("weight", True), ("next_hop", []), ("next_hop", "nope"),
    ("from", "LOCAL"), ("origin", "IGP"), ("cluster_list", "10.0.0.1"), ("cluster_list", ["x"]),
    ("originator_id", "x"), ("large_communities", ["65000:1"]), ("ext_communities", ["garbage!"]),
])
def test_an_attribute_out_of_its_range_is_an_error(key, value):
    with pytest.raises(IntentError):
        parse([{"prefix": "10.0.0.0/24", "best_path_on": "a", "to": {key: value}}])


def test_with_pins_of_the_selected_route():
    ln = parse([{"prefix": "10.0.0.0/24", "appears_on": "a", "with": {"protocol": "static", "distance": 1, "metric": 0}}]).lines[0]
    assert ln.pins == {"protocol": "static", "distance": 1, "metric": 0}
    for pins in ({"distance": None}, {"metric": None}, {"protocol": "STATIC"}):
        with pytest.raises(IntentError):
            parse([{"prefix": "10.0.0.0/24", "appears_on": "a", "with": pins}])


# --- what is accepted and what is refused, at the edges --------------------------------------------------------

@pytest.mark.parametrize("data", [
    {"intent": [{"prefix": "10.0.0.0/24", "appears_on": ["a"], "state": "received", "with": {"distance": 20}}]},
    {"intent": [{"prefix": "10.0.0.0/24", "appears_on": ["a"], "state": "received", "with": {"metric": 0}}]},
    {"intent": [{"prefix": "10.0.0.0/24", "appears_on": [5]}]},
    {"intent": [{"prefix": "10.0.0.0/24", "appears_on": ["a"], "vrf": 5}]},
    {"intent": [{"prefix": "10.0.0.0/24", "appears_on": ["a"], "vrf": "bad vrf!"}]},
    {"intent": [{"prefix": "10.0.0.0/24", "advertisement": {"node": "a", "neighbor": "10.0.0.1", "vrf": "x"},
                 "goes": "added"}]},
    {"intent": [{"prefix": "10.0.0.0/24", "advertisement": {"node": 1, "neighbor": "10.0.0.1"}, "goes": "added"}]},
    {"intent": [{"session": {"node": "a", "afi": "ipv4-unicast"}, "goes": "down"}]},
    {"intent": [{"session": {"node": "a", "neighbor": "10.0.0.1", "afi": "ipv4-unicast", "x": 1}, "goes": "down"}]},
    {"intent": [{"session": {"node": "", "neighbor": "10.0.0.1", "afi": "ipv4-unicast"}, "goes": "down"}]},
    {"intent": [{"session": {"node": 5, "neighbor": "10.0.0.1", "afi": "ipv4-unicast"}, "goes": "down"}]},
    # the same session twice (with its address family), and two lines about one route on a node named "session"
    {"intent": [SESSION, SESSION]},
    {"intent": [{"prefix": "10.0.0.0/24", "appears_on": ["session"]},
                {"prefix": "10.0.0.0/24", "disappears_from": ["session"]}]},
    {"intent": [], "allow_anywhere": [5]},
    {"intent": [], "allow_anywhere": ["2001:db8::1:*::/64"]},                    # `::` twice
    {"intent": [], "allow_anywhere": ["2001:db8:1:*::5:6:7:8/128"]},            # `::` standing for nothing
    {"intent": [], "allow_anywhere": ["10.200.*.256/32"]},
])
def test_more_malformed_intents_are_errors(data):
    with pytest.raises(IntentError):
        parse_intent(data, "t")


def test_lines_about_different_things_on_one_node_are_accepted():
    it = parse([{"prefix": "10.0.0.0/24", "appears_on": "a"}, {"prefix": "10.1.0.0/24", "best_path_on": "a", "to": {"med": 1}},
                SESSION, {**SESSION, "session": {**SESSION["session"], "afi": "ipv6-unicast"}},
                {**ADV, "goes": "added"}, {**ADV, "advertisement": {"node": "edge1", "neighbor": "192.0.2.10"}, "goes": "added"}])
    assert len(it.lines) == 6


def test_allow_anywhere_mapping_entries():
    plain, cust = parse(allow=[{"prefix": "10.9.0.0/16"}, {"prefix": "10.200.*.0/24", "vrf": "cust"}]).allow
    assert plain.matches("10.9.0.0/16", "default") and not plain.matches("10.9.0.0/16", "cust")
    assert cust.matches("10.200.3.0/24", "cust") and not cust.matches("10.200.3.0/24", "default")
    exact = parse(allow=[{"prefix": "10.9.0.0/16", "vrf": "cust"}]).allow[0]
    assert exact.matches("10.9.0.0/16", "cust") and not exact.matches("10.9.0.0/16", "default")


@pytest.mark.parametrize("entry,inside,outside", [
    ("10.200.255.*/32", ["10.200.255.7/32"], ["10.200.254.7/32"]),
    ("10.200.*.0/17", ["10.200.0.0/17", "10.200.128.0/17"], ["10.200.0.0/16"]),       # a `*` inside the length
    ("2001:DB8:1:*::/64", ["2001:db8:1:ab::/64"], ["2001:db8:2:ab::/64"]),              # upper-case hex
    ("2001:db8:1:*::/50", ["2001:db8:1:4000::/50"], ["2001:db8:2::/50"]),
    ("2001:db8:1:*:0:0:0:0/64", ["2001:db8:1:7::/64"], ["2001:db8:2:7::/64"]),          # written in full
    ("2001:db8:1:*::5/128", ["2001:db8:1:7::5/128"], ["2001:db8:1:7::/128", "2001:db8:1:7::6/128"]),
    ("2001:db8:1:*::5:6/128", ["2001:db8:1:7::5:6/128"], ["2001:db8:1:7::6/128"]),
    ("::1:2:3:*:0:0/96", ["::1:2:3:9:0:0/96"], ["::1:2:4:9:0:0/96"]),                  # a leading `::`
])
def test_allow_anywhere_glob_forms(entry, inside, outside):
    (glob,) = parse(allow=[entry]).allow
    assert all(glob.matches(p, "default") for p in inside), inside
    assert not any(glob.matches(p, "default") for p in outside), outside


def test_a_glob_never_matches_a_prefix_with_host_bits():
    glob = parse(allow=["10.200.*.0/24"]).allow[0]
    assert not glob.matches("10.200.7.1/24", "default") and not glob.matches("not a prefix", "default")
