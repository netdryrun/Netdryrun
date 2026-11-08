"""bgp_route: config validation and the best-path attribute evaluation (fake driver, no lab)."""
import textwrap

import pytest

from netdryrun.checks import _bgp_route, is_post_convergence
from netdryrun.config import Check, ConfigError, load, normalize_as_path, parse_community
from netdryrun.drivers import DRIVERS, DriverError, check_supported
from netdryrun.drivers.base import BgpPath, Observation, render_as_path


def write(tmp_path, checks):
    (tmp_path / "topo.clab.yml").write_text(
        "name: t\ntopology:\n  nodes:\n    r1: {image: quay.io/frrouting/frr:10.4.1}\n")
    p = tmp_path / "netdryrun.yml"
    p.write_text("lab: topo.clab.yml\nchecks:\n" + textwrap.indent(textwrap.dedent(checks), "  "))
    return p


def test_loads_and_normalizes(tmp_path):
    cfg = load(write(tmp_path, """
        - type: bgp_route
          node: r1
          prefix: 192.168.20.1/24
          communities: ["65020:0100", no-export, "65020:1:1"]
          without_communities: "65020:666"
          as_path: "65020   65030"
          local_pref: 200
          med: 0
          next_hop: 10.1.1.2
        - {type: bgp_route, node: r1, prefix: 10.0.0.0/8, present: false}
        - {type: bgp_route, node: r1, prefix: 10.0.0.0/8, as_path: 65020, as_path_regex: "^65020( |$)"}
    """))
    p = cfg.checks[0].params
    assert p["prefix"] == "192.168.20.0/24"
    assert p["communities"] == ["65020:100", "65535:65281", "65020:1:1"]
    assert p["without_communities"] == ["65020:666"]
    assert p["as_path"] == "65020 65030"
    assert cfg.checks[0].name.startswith("r1: BGP best path for 192.168.20.0/24 has communities 65020:100 no-export")
    assert cfg.checks[1].name == "r1: no BGP path for 10.0.0.0/8"
    assert cfg.checks[2].params["as_path"] == "65020"


@pytest.mark.parametrize("body,msg", [
    ("{type: bgp_route, node: r1, prefix: 10.0.0.0/8, communities: [65020:10]}", "quoted strings"),
    ("{type: bgp_route, node: r1, prefix: 10.0.0.0/8, communities: ['65020:70000']}", "bad community"),
    ("{type: bgp_route, node: r1, prefix: 10.0.0.0/8, communities: [no-such-name]}", "bad community"),
    ("{type: bgp_route, node: r1, prefix: 10.0.0.0/8, communities: []}", "at least one"),
    ("{type: bgp_route, node: r1, prefix: 10.0.0.0/8, present: false, med: 0}", "can't be combined"),
    ("{type: bgp_route, node: r1, prefix: 10.0.0.0/8, present: 'no'}", "true or false"),
    ("{type: bgp_route, node: r1, prefix: 10.0.0.0/8, local_pref: -1}", "non-negative"),
    ("{type: bgp_route, node: r1, prefix: 10.0.0.0/8, next_hop: nope}", "does not appear"),
    ("{type: bgp_route, node: r1, prefix: 10.0.0.0/8, as_path: '65020 x'}", "bad as_path"),
    ("{type: bgp_route, node: r1, prefix: 10.0.0.0/8, as_path_regex: '('}", "not a valid regular"),
    ("{type: bgp_route, node: r1, prefix: 10.0.0.0/8, protocol: bgp}", "unknown keys"),
    ("{type: bgp_route, node: r1, prefix: 10.0.0.0/8, communities: ['1:1'], without_communities: ['1:1']}", "both"),
])
def test_rejects_bad_bgp_route(tmp_path, body, msg):
    with pytest.raises(ConfigError, match=msg):
        load(write(tmp_path, f"- {body}\n"))


def test_community_and_as_path_forms():
    assert parse_community("NO_EXPORT") == "65535:65281"
    assert parse_community("4200000000:1:2") == "4200000000:1:2"
    assert normalize_as_path([65001, 65002]) == "65001 65002"
    assert normalize_as_path("") == ""
    assert normalize_as_path("65001 {65002, 65003}") == "65001 {65002,65003}"
    assert render_as_path([("as-sequence", [65001]), ("as-set", [65003, 65002])]) == "65001 {65003,65002}"


def path(**kw):
    base = dict(best=True, as_path="65020", next_hop="10.1.1.2", local_pref=200, med=50,
                communities=["65020:100", "65535:65281"], large_communities=["65020:1:1"])
    base.update(kw)
    return BgpPath(**base)


class Paths:
    def __init__(self, paths):
        self.paths = paths

    def bgp_paths(self, prefix, vrf="default"):
        return Observation(self.paths, [])


def ev(paths, **params):
    return _bgp_route(Paths(paths), {"node": "r1", "prefix": "192.168.20.0/24", **params})


def test_best_path_attributes_pass():
    ok, detail, _ = ev([path(best=False, local_pref=100), path()], communities=["65020:100", "65020:1:1"],
                       without_communities=["65020:666"], as_path="65020", local_pref=200, med=50,
                       next_hop="10.1.1.2", as_path_regex="^65020$")
    assert ok and "local-pref 200" in detail and "no-export" in detail


@pytest.mark.parametrize("params,needle", [
    ({"communities": ["65020:200"]}, "missing communities 65020:200"),
    ({"without_communities": ["65535:65281"]}, "carries communities no-export"),
    ({"as_path": "65020 65030"}, "as-path is '65020', expected '65020 65030'"),
    ({"as_path_regex": "65030$"}, "does not match"),
    ({"local_pref": 100}, "local-pref is 200, expected 100"),
    ({"med": 0}, "MED is 50, expected 0"),
    ({"next_hop": "10.9.9.9"}, "next hop is 10.1.1.2, expected 10.9.9.9"),
])
def test_best_path_attribute_mismatch(params, needle):
    ok, detail, _ = ev([path()], **params)
    assert not ok and needle in detail


def test_no_path_and_no_best_path():
    ok, detail, _ = ev([], local_pref=100)
    assert not ok and detail == "no BGP path"
    ok, detail, _ = ev([path(best=False)])
    assert not ok and "none is best" in detail


def test_present_false_means_no_path_at_all():
    assert ev([], present=False)[0]
    ok, detail, _ = ev([path(best=False)], present=False)  # not best, still in the table: still a leak
    assert not ok and "unexpectedly in the BGP table" in detail
    # the router's own static listed in the BGP table (SR Linux, whether exported or not) is not a received path:
    # present: false passes and says what it didn't check (accepted documented limit RT-0048, owner 2026-11-08: a
    # fail-closed rule failed the shipped leak guards on a node with its own static default)...
    local = path(as_path="", next_hop="0.0.0.0", local_candidate=True)
    ok, detail, _ = ev([local], present=False)
    assert ok and "a prefix this node originates itself isn't checked" in detail
    ok, _, _ = ev([local, path(best=False)], present=False)
    assert not ok
    # ...nor for a best-path check: SR Linux lists it, best, whether it is advertised or not (red team RT-0026)
    ok, detail, _ = ev([local], as_path="", next_hop="0.0.0.0")
    assert not ok and "only the router's own route" in detail
    assert not ev([local])[0]
    # a received path beside it is read, the router's own one never chosen as best
    assert ev([local, path(as_path="65002")], as_path="65002")[0]


def test_post_convergence_rules():
    def c(**p):
        return Check(type="bgp_route", params={"node": "r1", "prefix": "10.0.0.0/8", **p}, name="x", timeout=1)
    assert is_post_convergence(c(present=False))
    assert is_post_convergence(c(without_communities=["1:1"]))
    assert is_post_convergence(c(communities=["1:1"], local_pref=200))
    assert not is_post_convergence(c())   # presence only


def test_unsupported_attribute_is_refused(monkeypatch):
    from netdryrun.lab import Node

    class FakeLab:
        nodes = {"r1": Node("r1", "clab-t-r1", "linux", "quay.io/frrouting/frr:10.4.1")}

    c = Check(type="bgp_route", params={"node": "r1", "prefix": "10.0.0.0/8", "med": 0}, name="r1 med", timeout=1)
    check_supported(FakeLab(), c)  # every driver reads every attribute today
    monkeypatch.setattr(DRIVERS["frr"], "unsupported_bgp_attributes", frozenset({"med"}))
    with pytest.raises(DriverError, match="med is not supported on frr"):
        check_supported(FakeLab(), c)


def test_evpn_prefix_counts_are_refused_on_eos():
    from netdryrun.lab import Node

    class FakeLab:
        nodes = {"r1": Node("r1", "clab-t-r1", "arista_ceos", "ceos:4.33"),
                 "r2": Node("r2", "clab-t-r2", "linux", "quay.io/frrouting/frr:10.4.1")}

    def c(node, afi):
        return Check(type="bgp_prefixes", params={"node": node, "neighbor": "10.0.0.1", "max": 0, "afi": afi},
                     name=f"{node} {afi}", timeout=1)

    # the EOS driver has no EVPN counts: the count would read 0 and pass max: 0
    with pytest.raises(DriverError, match="afi evpn is not supported on eos"):
        check_supported(FakeLab(), c("r1", "evpn"))
    with pytest.raises(DriverError, match="afi evpn is not supported on eos"):
        check_supported(FakeLab(), c("r2", "evpn"), override="eos")
    check_supported(FakeLab(), c("r1", "ipv6-unicast"))
    check_supported(FakeLab(), c("r2", "evpn"))   # FRR reads EVPN counts
