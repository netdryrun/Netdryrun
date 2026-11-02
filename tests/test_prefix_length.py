"""Every prefix in netdryrun.yml carries its length (acceptance round B-1, 2026-11-02).

Without one, ipaddress reads `0.0.0.0` as 0.0.0.0/32: `route prefix: 0.0.0.0, protocol: bgp, present: false`, written
to mean "no default route via BGP", checked a single host and passed with a leaked 0.0.0.0/0 installed.
"""
import textwrap

import pytest

from netdryrun.checks import _route
from netdryrun.config import ConfigError, load
from netdryrun.drivers.base import Observation, Route

TOPO = "name: t\ntopology:\n  nodes:\n    r1: {image: quay.io/frrouting/frr:10.4.1}\n"
V4 = "write it with one (0.0.0.0/0 for a default route, 192.0.2.1/32 for one host)"
V6 = "write it with one (::/0 for a default route, 2001:db8::1/128 for one host)"


def write(tmp_path, body):
    (tmp_path / "topo.clab.yml").write_text(TOPO)
    p = tmp_path / "netdryrun.yml"
    p.write_text(textwrap.dedent(body))
    return p


def one_check(tmp_path, check):
    return write(tmp_path, f"lab: topo.clab.yml\nchecks:\n  - {check}\n")


class Leaked:
    """A node with 0.0.0.0/0 installed via BGP."""

    def routes(self, prefix, vrf="default"):
        return Observation([Route(prefix, "bgp", True)] if prefix == "0.0.0.0/0" else [], [])


def test_the_false_pass_it_closes():
    """Read as 0.0.0.0/32, the default-route guard passed with the default leaked; read as 0.0.0.0/0 it fails."""
    p = {"node": "r1", "protocol": "bgp", "present": False}
    assert _route(Leaked(), {**p, "prefix": "0.0.0.0/32"})[0] is True
    assert _route(Leaked(), {**p, "prefix": "0.0.0.0/0"})[0] is False


@pytest.mark.parametrize("ctype", ["route", "bgp_route"])
@pytest.mark.parametrize("value,hint", [("0.0.0.0", V4), ("10.20.0.0", V4), ("192.0.2.1", V4), ("::", V6),
                                        ("2001:db8::", V6)])
def test_a_check_prefix_without_a_length_is_refused(tmp_path, ctype, value, hint):
    with pytest.raises(ConfigError) as e:
        load(one_check(tmp_path, f"{{type: {ctype}, node: r1, prefix: '{value}', present: false, name: guard}}"))
    assert str(e.value) == f"checks[0] ('guard'): prefix {value!r} has no length: {hint}"


def test_the_message_names_the_scenario_check(tmp_path):
    body = """\
        lab: topo.clab.yml
        checks:
          - {type: route, node: r1, prefix: 10.0.0.0/8}
        scenarios:
          - name: s
            node_isolated: r1
            checks:
              - {type: route, node: r1, prefix: '0.0.0.0', present: false}
        """
    with pytest.raises(ConfigError) as e:
        load(write(tmp_path, body))
    assert str(e.value) == f"scenarios[0].checks[0]: prefix '0.0.0.0' has no length: {V4}"


def test_an_only_entry_without_a_length_is_refused(tmp_path):
    check = ("{type: bgp_prefixes, node: r1, neighbor: 10.0.0.2, min: 1, max: 3, "
             "only: ['10.1.0.0/24', '10.2.0.0']}")
    with pytest.raises(ConfigError) as e:
        load(one_check(tmp_path, check))
    assert str(e.value) == f"checks[0]: only: prefix '10.2.0.0' has no length: {V4}"


@pytest.mark.parametrize("fault,shown", [("{node: r1, prefixes: ['10.9.0.0/24', '10.8.0.0']}", "prefixes: prefix '10.8.0.0'"),
                                         ("{node: r1, prefixes: '10.8.0.0'}", "prefixes: prefix '10.8.0.0'"),
                                         ("{node: r1, count: 3, from: '100.64.0.0'}", "from: prefix '100.64.0.0'")])
def test_inject_routes_prefixes_without_a_length_are_refused(tmp_path, fault, shown):
    body = f"""\
        lab: topo.clab.yml
        checks:
          - {{type: route, node: r1, prefix: 10.0.0.0/8}}
        scenarios:
          - name: s
            inject_routes: {fault}
            checks:
              - {{type: route, node: r1, prefix: 10.9.0.0/24}}
        """
    with pytest.raises(ConfigError) as e:
        load(write(tmp_path, body))
    assert str(e.value) == f"scenarios[0] ('s'): inject_routes: {shown} has no length: {V4}"


def test_prefixes_with_a_length_still_load(tmp_path):
    body = """\
        lab: topo.clab.yml
        checks:
          - {type: route, node: r1, prefix: 0.0.0.0/0, protocol: bgp, present: false}
          - {type: route, node: r1, prefix: '2001:db8::/32'}
          - {type: bgp_route, node: r1, prefix: 192.0.2.1/32}
          - {type: bgp_prefixes, node: r1, neighbor: 10.0.0.2, min: 1, max: 3, only: [10.1.0.0/24]}
        scenarios:
          - name: s
            inject_routes: [{node: r1, prefixes: [10.8.0.0/24]}, {node: r1, count: 2, from: 100.64.0.0/24}]
            checks:
              - {type: route, node: r1, prefix: 10.8.0.0/24}
        """
    cfg = load(write(tmp_path, body))
    assert [c.params["prefix"] for c in cfg.checks if "prefix" in c.params] == ["0.0.0.0/0", "2001:db8::/32",
                                                                                 "192.0.2.1/32"]


def test_text_that_is_not_a_prefix_keeps_its_own_error(tmp_path):
    with pytest.raises(ConfigError, match="does not appear to be an IPv4 or IPv6 network"):
        load(one_check(tmp_path, "{type: route, node: r1, prefix: 'nope'}"))
