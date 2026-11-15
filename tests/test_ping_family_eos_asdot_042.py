"""Unit tests for the 0.4.2 fixes FP-042-PINGSRCFAMILY and FP-042-EOSASDOT (session ndr-fix-042-n7b).

- config._ping_target refuses a ping `source` of the other address family than its `target`, in both directions,
  for every check list config loading reads (top-level checks and scenario checks), whatever `expect` says.
- eos._as_path reads every ASN as asplain digits and refuses any other token (a dotted asdot ASN included) as
  unexpected output, in bgp_route and in record --attributes.

The device output is tests/fixtures/eos_bgp_paths.txt (cEOS 4.36.3M, live) with the best path's asPath replaced.
"""
import json
from pathlib import Path

import pytest

from netdryrun import config
from netdryrun import record as rec
from netdryrun.checks import run_check
from netdryrun.config import ConfigError, _validate_check
from netdryrun.drivers import eos
from netdryrun.drivers.base import DriverError
from netdryrun.drivers.eos import EosDriver
from netdryrun.lab import ExecResult

FX = Path(__file__).resolve().parent / "fixtures"
PREFIX = "192.168.20.0/24"
BGP = f"show ip bgp {PREFIX} vrf default | json"


# ---- ping source family -------------------------------------------------------------------------------------------

def ping(**kw) -> dict:
    return {"type": "ping", "node": "r1", **kw}


@pytest.mark.parametrize("source,target,sv,tv", [
    ("192.0.2.1", "2001:db8:3::1", 4, 6),
    ("2001:db8:1::1", "10.0.3.1", 6, 4),
    ("fe80::1%eth1", "10.0.3.1", 6, 4),          # a scoped IPv6 source, IPv4 target
    ("10.0.12.1", "fe80::2%eth1", 4, 6),          # an IPv4 source, scoped IPv6 target
])
def test_source_of_the_other_family_is_refused(source, target, sv, tv):
    with pytest.raises(ConfigError) as e:
        _validate_check(0, ping(source=source, target=target), 20)
    msg = str(e.value)
    assert f"source {source} is an IPv{sv} address" in msg and f"target {target} an IPv{tv} address" in msg
    assert "of the target's family" in msg and msg.startswith("checks[0]")


@pytest.mark.parametrize("expect", ["success", "failure"])
def test_refused_whatever_expect_says(expect):
    # a dropped source makes expect: failure pass on the wrong source as easily as success
    with pytest.raises(ConfigError, match="IPv4 address and target"):
        _validate_check(0, ping(source="192.0.2.1", target="2001:db8:3::1", expect=expect), 20)


@pytest.mark.parametrize("source,target", [
    ("192.0.2.1", "10.0.3.1"),
    ("2001:db8:1::1", "2001:db8:3::1"),
    ("fe80::1%eth1", "2001:db8:3::1"),
    ("2001:db8:1::1", "fe80::2%eth1"),
])
def test_source_of_the_same_family_loads(source, target):
    c = _validate_check(0, ping(source=source, target=target), 20)
    assert c.params["source"] == source and c.params["target"] == target


def test_no_source_loads_in_both_families():
    assert _validate_check(0, ping(target="10.0.3.1"), 20).params["target"] == "10.0.3.1"
    assert _validate_check(0, ping(target="2001:db8:3::1"), 20).params["target"] == "2001:db8:3::1"


def test_source_equal_to_target_keeps_its_own_message():
    with pytest.raises(ConfigError, match="is the source address: the node pings itself"):
        _validate_check(0, ping(source="10.0.3.1", target="10.0.3.1"), 20)


def test_ipv4_mapped_target_keeps_its_own_message():
    # checked before the family comparison: an IPv4 source with ::ffff:10.0.3.1 names the mapped form
    with pytest.raises(ConfigError, match="IPv4-mapped IPv6 address: write the IPv4 address 10.0.3.1"):
        _validate_check(0, ping(source="192.0.2.1", target="::ffff:10.0.3.1"), 20)


def _write(tmp_path: Path, doc: dict) -> Path:
    (tmp_path / "lab.clab.yml").write_text("name: t\ntopology:\n  nodes:\n    r1: {kind: linux}\n", encoding="utf-8")
    p = tmp_path / "netdryrun.yml"
    p.write_text(json.dumps({"lab": "lab.clab.yml", **doc}), encoding="utf-8")
    return p


def test_load_refuses_it_in_checks(tmp_path):
    p = _write(tmp_path, {"checks": [ping(source="192.0.2.1", target="2001:db8:3::1")]})
    with pytest.raises(ConfigError, match=r"checks\[0\]: source 192.0.2.1 is an IPv4 address"):
        config.load(p)


def test_load_refuses_it_in_a_scenario(tmp_path):
    p = _write(tmp_path, {"checks": [ping(target="10.0.3.1")],
                          "scenarios": [{"name": "s", "link_down": {"node": "r1", "interface": "eth1"},
                                         "checks": [ping(source="2001:db8:1::1", target="10.0.3.1")]}]})
    with pytest.raises(ConfigError, match=r"scenarios\[0\]\.checks\[0\]: source 2001:db8:1::1 is an IPv6 address"):
        config.load(p)


def test_load_accepts_same_family_sources(tmp_path):
    p = _write(tmp_path, {"checks": [ping(source="192.0.2.1", target="10.0.3.1"),
                                     ping(source="2001:db8:1::1", target="2001:db8:3::1")]})
    assert [c.params["source"] for c in config.load(p).checks] == ["192.0.2.1", "2001:db8:1::1"]


# ---- EOS AS path -------------------------------------------------------------------------------------------------

def paths_with(as_path) -> str:
    """eos_bgp_paths.txt (live) with the best path's asPath replaced (any JSON value)."""
    text = (FX / "eos_bgp_paths.txt").read_text(encoding="utf-8")
    old = '"asPath": "65020"\n'
    assert text.count(old) == 1
    return text.replace(old, f'"asPath": {json.dumps(as_path)}\n')


def best(as_path) -> str:
    return next(p for p in eos.parse_bgp_paths(paths_with(as_path), PREFIX) if p.best).as_path


@pytest.mark.parametrize("printed,expected", [
    ("65020", "65020"),
    ("", ""),                                         # a locally originated path
    ("65002  65003", "65002 65003"),
    (" 65002 65003 ", "65002 65003"),
    ("4200000001 65020", "4200000001 65020"),
    ("65005 {65004 65006}", "65005 {65004,65006}"),
    ("65005 {65004,65006}", "65005 {65004,65006}"),
    ("65005 {65004, 65006}", "65005 {65004,65006}"),
    ("(65010 65011) 65020", "(65010 65011) 65020"),
    ("[65010 65011] 65020", "[65010,65011] 65020"),
    ("65020 {65001}", "65020 {65001}"),
    ("4294967295", "4294967295"),
])
def test_asplain_paths(printed, expected):
    assert best(printed) == expected


@pytest.mark.parametrize("printed", [
    "64086.59905 65020",          # asdot (4200000001)
    "65020 64086.59905",
    "1.0",
    "65005 {64086.59905 65006}",  # asdot inside a set
    "(64086.59905) 65020",        # ... in a confederation sequence
    "[1.2 65011]",                # ... in a confederation set
    "65020 i",                    # an origin letter
    "65020 ?",
    "{} 65020",                   # an empty set
    "() 65020",
    "65020 {65004",               # an unclosed set
    "AS65020",
    "-65020",
    "+65020",
    "６５０２０",                  # fullwidth digits: str.isdigit says yes, asplain says no
    "65020 x",
    "4294967296",                 # above the 4-byte range
    "65020 {4294967296}",
])
def test_anything_but_asplain_numbers_is_unexpected(printed):
    with pytest.raises(DriverError, match=r"^unexpected output from .*asPath"):
        best(printed)


@pytest.mark.parametrize("value", [65020, None, ["65020"], {"asPath": "65020"}, True])
def test_an_as_path_that_is_not_a_string_is_unexpected(value):
    with pytest.raises(DriverError, match="asPath"):
        best(value)


def test_the_error_names_the_printed_path():
    with pytest.raises(DriverError) as e:
        best("64086.59905 65020")
    assert "64086.59905 65020" in str(e.value)


class Lab:
    def __init__(self, text: str):
        self.text = text

    def exec(self, node, cmd, timeout=60, input=None):
        if list(cmd) == ["Cli", "-p", "15", "-c", BGP]:
            return ExecResult(cmd, 0, self.text, "")
        return ExecResult(cmd, 1, "", "% Invalid input")


class Clock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t

    def sleep(self, s):
        self.t += max(s, 0.5)


def run(text: str, **attrs):
    c = Clock()
    check = _validate_check(0, {"type": "bgp_route", "node": "r1", "prefix": PREFIX, **attrs}, 20)
    return run_check(check, EosDriver(Lab(text), "r1"), clock=c, sleep=c.sleep)


GUARD = r"^(?!.*\b42[0-9]{8}\b)"


def test_negative_guard_never_passes_on_asdot():
    r = run(paths_with("64086.59905 65020"), as_path_regex=GUARD)
    assert not r.passed and "64086.59905" in r.detail


def test_negative_guard_still_passes_on_plain_and_fails_on_asplain():
    assert run(paths_with("65020"), as_path_regex=GUARD).passed
    assert not run(paths_with("4200000001 65020"), as_path_regex=GUARD).passed


def test_bgp_route_without_attributes_on_asdot_does_not_pass():
    # the paths can't be read at all: not even "a best path exists" is judged on an answer the parser refuses
    assert not run(paths_with("64086.59905 65020")).passed


def test_record_attributes_raises_so_record_names_the_gap():
    drv = EosDriver(Lab(paths_with("64086.59905 65020")), "r1")
    with pytest.raises(DriverError, match="64086.59905"):
        rec._attribute_check(drv, "r1", PREFIX, "default", [])


def test_record_attributes_writes_the_asplain_path():
    drv = EosDriver(Lab(paths_with("4200000001 65020")), "r1")
    c = rec._attribute_check(drv, "r1", PREFIX, "default", [])
    assert c["as_path"] == "4200000001 65020"
