"""The capture sanitiser, tested on Netdryrun's own live captures (tests/fixtures) and on the cases they don't have.

Sanitising must change what identifies a network (addresses, AS numbers, names, secrets) and nothing else: the
same input gives the same output, the structure is the same, and a driver reads the sanitised output as the
sanitised version of what it read from the original.
"""
from __future__ import annotations

import ipaddress
import json
import re
from pathlib import Path

import pytest

from netdryrun.capture import sanitize as san
from netdryrun.capture.collect import _jsonable
from netdryrun.drivers import eos, frr, junos, srlinux

FIXTURES = Path(__file__).resolve().parent / "fixtures"
OUTPUTS = sorted(p for p in [*FIXTURES.glob("*.txt"), *(FIXTURES / "verify").glob("*.txt")])


def run(*texts: str, hostnames=()) -> tuple[san.Sanitizer, list[str]]:
    s = san.Sanitizer(hostnames)
    for t in texts:
        s.collect(t)
    s.build()
    return s, [s.text(t) for t in texts]


def test_there_are_captures_to_test_on():
    assert len(OUTPUTS) >= 80


@pytest.mark.parametrize("path", OUTPUTS, ids=lambda p: p.relative_to(FIXTURES).as_posix())
def test_our_captures_sanitise_with_the_same_structure_and_no_leak(path):
    text = path.read_text(encoding="utf-8")
    s, (out,) = run(text, hostnames=["r1", "r2", "r3", "j1", "pe1", "edge1"])
    assert not s.problems, s.problems
    assert san.leaks(out, s.mapping()) == []
    assert san.shape(s.names_only(text)) == san.shape(out)
    # deterministic: a second run on the same input gives the same bytes
    s2, (again,) = run(text, hostnames=["r1", "r2", "r3", "j1", "pe1", "edge1"])
    assert again == out and s2.mapping() == s.mapping()


def test_public_router_ids_in_our_captures_are_rewritten():
    text = (FIXTURES / "frr_bgp_neighbors.txt").read_text(encoding="utf-8")
    assert '"remoteRouterId":"2.2.2.2"' in text
    s, (out,) = run(text)
    assert "2.2.2.2" not in out and "1.1.1.1" not in out
    assert re.search(r'"remoteRouterId":"10\.\d+\.2\.2"', out)
    assert '"remoteAs":65002' not in out and re.search(r'"remoteAs":645\d\d', out)


def test_json_layout_and_numbers_are_kept():
    text = (FIXTURES / "frr_route.txt").read_text(encoding="utf-8")
    _, (out,) = run(text)
    assert out.splitlines()[1].startswith('  "') and '":' in out and '": ' not in out   # FRR's own layout
    assert '"prefixLen":24' in out and '"distance":20' in out
    assert len(out.splitlines()) == len(text.splitlines())


# ---- a driver reads the sanitised output as the sanitised reading -------------------------------------------------
def _prefix(text: str) -> str:
    return re.search(r'"prefix":\s*"([^"]+)"', text).group(1)


READS = [
    ("frr_bgp_neighbors.txt", lambda t: frr.parse_bgp_neighbors(t)),
    ("frr_bgp_paths.txt", lambda t: frr.parse_bgp_paths(t, _prefix(t))),
    ("frr_bgp_paths_v6.txt", lambda t: frr.parse_bgp_paths(t, _prefix(t))),
    ("frr_bgp_paths_noexport.txt", lambda t: frr.parse_bgp_paths(t, _prefix(t))),
    ("frr_route.txt", lambda t: frr.parse_routes(t, _prefix(t))),
    ("frr_ping.txt", lambda t: frr.parse_ping(t)),
    ("srl_bgp_neighbors.txt", lambda t: srlinux.parse_bgp_neighbors(t)),
    ("eos_bgp_summary.txt", lambda t: eos.parse_bgp_summary(t)),
    ("junos_bgp_neighbor.txt", lambda t: junos.parse_bgp_neighbors(t)),
    ("junos_bgp_neighbor_ibgp.txt", lambda t: junos.parse_bgp_neighbors(t)),
    ("junos_route_ibgp_noexport.txt", lambda t: junos.parse_bgp_paths(t, _junos_prefix(t))),
]


def _junos_prefix(text: str) -> str:
    return re.search(r'"rt-destination"\s*:\s*\[\s*\{\s*"data"\s*:\s*"([^"]+)"', text).group(1) + "/" + \
        re.search(r'"rt-prefix-length"\s*:\s*\[\s*\{\s*"data"\s*:\s*"(\d+)"', text).group(1)


@pytest.mark.parametrize("name,parse", READS, ids=[r[0] for r in READS])
def test_the_driver_reads_the_sanitised_output_as_the_sanitised_reading(name, parse):
    text = (FIXTURES / name).read_text(encoding="utf-8")
    before = json.dumps(_jsonable(parse(text)))
    s, (out,) = run(text)
    # the original reading, put through the same mapping, is what the driver reads from the sanitised output
    after = _jsonable(parse(out))
    assert json.loads(json.dumps(after)) == json.loads(s.text(before))


def test_junos_route_prefix_maps_like_the_output():
    # junos_route_paths is read for 10.20.0.0/24: the sanitised read uses the mapped prefix
    text = (FIXTURES / "junos_route_paths.txt").read_text(encoding="utf-8")
    s, (out, prefix) = run(text, "10.20.0.0/24")
    before = _jsonable(junos.parse_bgp_paths(text, "10.20.0.0/24"))
    after = _jsonable(junos.parse_bgp_paths(out, prefix))
    assert after == json.loads(s.text(json.dumps(before))) and before


# ---- what our captures don't contain -------------------------------------------------------------------------------
def test_public_v4_space_from_a_production_copy_is_rewritten_with_lengths_and_order_kept():
    text = "\n".join(["route 81.2.3.0/24 via 81.2.3.1", "route 81.2.4.0/24 via 81.2.4.1", "aggregate 81.0.0.0/12",
                      "route 62.1.0.0/16 via 62.1.0.1", "peer 100.64.0.1"])
    s, (out,) = run(text)
    assert not s.problems and san.leaks(out) == []
    nets = [ipaddress.ip_network(n) for n in re.findall(r"\d+\.\d+\.\d+\.\d+/\d+", out)]
    assert [n.prefixlen for n in nets] == [24, 24, 12, 16]
    assert all(n.subnet_of(ipaddress.ip_network("10.0.0.0/8")) for n in nets)
    agg = nets[2]
    assert nets[0].subnet_of(agg) and nets[1].subnet_of(agg) and not nets[3].subnet_of(agg)   # containment kept
    hosts = re.findall(r"via (\S+)", out)
    assert ipaddress.ip_address(hosts[0]) < ipaddress.ip_address(hosts[1])                     # order kept
    assert ipaddress.ip_address(hosts[0]) in nets[0]


def test_global_v6_goes_to_the_documentation_range_and_link_local_stays():
    text = '{"peers": {"2a01:4f8:1:2::1": {"nexthop": "fe80::a8c1:abff:fe00:1%e1-1", "prefix": "2a01:4f8::/32"}}}'
    s, (out,) = run(text)
    assert "2a01" not in out and "fe80::a8c1:abff:fe00:1%e1-1" in out
    assert "3fff:" in out and san.leaks(out) == []
    assert ipaddress.ip_network(re.search(r'"prefix": "([^"]+)"', out).group(1)).prefixlen == 32


def test_kept_ranges_stay():
    text = "lo 127.0.0.1 mask 255.255.255.0 wildcard 0.0.0.255 doc 192.0.2.1 198.51.100.7 203.0.113.9 bench 198.18.0.1 " \
           "mcast 224.0.0.5 v6 ::1 2001:db8::1 ff02::5"
    _, (out,) = run(text)
    assert out == text


def test_asns_change_only_where_the_output_says_they_are_asns():
    text = json.dumps({"localAs": 3356, "remoteAs": 4200001234, "peer-as": [{"data": "174"}],
                       "aspath": {"string": "174 {3356,1299} 64999", "segments": [{"list": [174, 3356]}], "length": 3},
                       "communities": {"list": ["174:100", "65535:65281", "3356:1:2"]},
                       "bgpVersion": 4, "metric": 174, "prefixCount": 3356})
    s, (out,) = run(text)
    d = json.loads(out)
    assert 64512 <= d["localAs"] <= 65534 and d["remoteAs"] >= 4200000000
    assert d["aspath"]["length"] == 3 and d["metric"] == 174 and d["prefixCount"] == 3356 and d["bgpVersion"] == 4
    a174, a3356 = str(s.asn_map[174]), str(s.asn_map[3356])
    assert d["peer-as"] == [{"data": a174}] and d["aspath"]["segments"] == [{"list": [int(a174), int(a3356)]}]
    assert d["aspath"]["string"] == f"{a174} {{{a3356},{s.asn_map[1299]}}} {s.asn_map[64999]}"
    assert d["communities"]["list"] == [f"{a174}:100", "65535:65281", f"{a3356}:1:2"]   # well-known kept
    assert san.leaks(out) == []


def test_asns_in_text():
    text = "router bgp 3356\n neighbor 192.0.2.1 remote-as 174\nBGP neighbor is 192.0.2.1, remote AS 174, local AS 3356\n" \
           "Sent as 3 packets"
    s, (out,) = run(text)
    assert "3356" not in out and "174" not in out and "Sent as 3 packets" in out
    assert san.leaks(out) == []


def test_hostnames_domains_and_secrets():
    text = json.dumps({"hostname": "core-sw-ams1", "domainname": "corp.example.net", "peer": "core-sw-ams1",
                       "auth-key": "s3cret", "password": "hunter2", "description": "to core-sw-ams1 uplink"})
    s, (out, cfg) = run(text, "hostname core-sw-ams1\n neighbor 192.0.2.1 password 7 0822455D0A16")
    d = json.loads(out)
    assert d["hostname"] == d["peer"] == "host-1" and d["domainname"] == "host-2"
    assert d["auth-key"] == d["password"] == "<removed>" and d["description"] == "to host-1 uplink"
    assert cfg == "hostname host-1\n neighbor 192.0.2.1 password 7 <removed>"
    assert "hunter2" not in out and "core-sw" not in out
    assert san.leaks(out, s.mapping()) == [] and san.leaks(cfg, s.mapping()) == []


@pytest.mark.parametrize("name", ["nxos_boot_log_clean.txt", "nxos_boot_log_rejected.txt"])
def test_secret_syntax_is_removed_and_english_about_passwords_is_kept(name):
    # NX-OS boot logs (live n9kv captures) ask for the admin password in prose, and vrnetlab prints the default one
    text = (FIXTURES / name).read_text(encoding="utf-8")
    _, (out,) = run(text)
    prose = [ln for ln in text.splitlines() if re.search(r"(?i)the password for|secure password standard", ln)]
    assert prose and all(ln in out.splitlines() for ln in prose)
    assert "<removed> \"admin\"" not in out and "password <removed>" not in out.lower()
    if "PASSWORD: admin" in text:
        assert "PASSWORD: admin" not in out and "PASSWORD: <removed>" in out


@pytest.mark.parametrize("line,secret", [
    ("neighbor 192.0.2.1 password 7 0822455D0A16", "0822455D0A16"),
    ("username admin password 5 $1$abc$xyz", "$1$abc$xyz"),
    ('authentication-key "$9$dkfj"; ## SECRET-DATA', '"$9$dkfj"'),
    ("snmp key-string s3cr3t", "s3cr3t"),
])
def test_config_secrets_are_removed(line, secret):
    _, (out,) = run(line)
    assert secret not in out and "<removed>" in out


@pytest.mark.parametrize("line", ["Enter the password for \"admin\":", "Please set a new password now",
                                  "Do you want to enforce secure password standard (yes/no) [y]:", "Password:"])
def test_prose_is_not_a_secret(line):
    _, (out,) = run(line)
    assert out == line


def test_versions_and_times_are_not_addresses():
    text = "FRRouting 10.4.1 uptime 00:00:03 mac aa:bb:cc:dd:ee:ff version 4.32.2F build 1.2.3.4a"
    _, (out,) = run(text)
    assert out == text


def test_a_prefix_shorter_than_8_identifies_nobody_and_is_kept():
    s, (out,) = run("aggregate-address 192.0.0.0/2 as-set\n2000::/3 81.2.3.4")
    assert out.startswith("aggregate-address 192.0.0.0/2 as-set\n2000::/3 10.") and not s.problems
    assert san.leaks(out) == []


def test_too_many_slash16s_is_a_problem():
    text = " ".join(f"81.{i}.0.1 82.{i}.0.1" for i in range(129))
    s, _ = run(text)
    assert any("pool has 256" in p for p in s.problems)


def test_the_leak_check_does_not_trust_the_rewrite():
    assert san.leaks("peer 81.2.3.4") == ["IPv4 address 81.2.3.4"]
    assert san.leaks('{"remoteAs": 3356}') == ["AS number 3356"]
    assert san.leaks("peer 2a01:4f8::1") == ["IPv6 address 2a01:4f8::1"]
    assert san.leaks("hello edge7", {"hostname": {"edge7": "host-1"}}) == ["name edge7"]
    assert san.leaks("peer 10.1.2.3 3fff:1::1 AS 64512") == []
