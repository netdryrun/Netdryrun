"""Driver behaviour pinned for the 0.4 mutation gate (EOS, FRR, base): what a parser returns and the error a
user reads when the output is not what the driver knows."""
import json
from pathlib import Path

import pytest

from netdryrun.drivers import eos
from netdryrun.drivers.base import Driver, DriverError
from netdryrun.drivers.frr import FrrDriver, parse_version
from netdryrun.lab import ExecResult

FIXTURES = Path(__file__).parent / "fixtures"
CMD = "show startup-config errors"
SUMMARY = "show ip bgp summary | json"


def fixture(name):
    return (FIXTURES / name).read_text(encoding="utf-8")


class RecordingLab:
    def __init__(self, text, rc=0):
        self.text, self.rc, self.cmds = text, rc, []

    def exec(self, node, cmd, timeout=60, input=None):
        self.cmds.append(cmd)
        return ExecResult(cmd, self.rc, self.text, "")


def snippet(text):
    return " ".join(text.split())[:200]


# --- eos.parse_startup_config_errors

def test_startup_errors_tolerate_trailing_whitespace():
    """Trailing blanks (a terminal pads lines) don't turn a clean or listed answer into unreadable output."""
    assert eos.parse_startup_config_errors("No errors were found in startup-config.   \n") == []
    padded = "\n".join(ln + "  " for ln in fixture("eos_startup_config_errors_one.txt").splitlines())
    assert eos.parse_startup_config_errors(padded) == eos.parse_startup_config_errors(
        fixture("eos_startup_config_errors_one.txt"))


def test_startup_errors_unknown_header_quotes_the_output():
    """Output without the known header and footer raises with the output, whitespace collapsed, capped at 200."""
    text = "% Invalid   input\n  at  foo\n"
    with pytest.raises(DriverError) as e:
        eos.parse_startup_config_errors(text)
    assert str(e.value) == f"{CMD}: unexpected output: '% Invalid input at foo'"
    long = "word " * 80
    with pytest.raises(DriverError) as e:
        eos.parse_startup_config_errors(long)
    assert str(e.value) == f"{CMD}: unexpected output: {snippet(long)!r}"


def test_startup_errors_odd_body_raises_a_driver_error_quoting_the_output():
    """A rejected line without its reason line is unreadable output: a DriverError quoting it, never a crash."""
    text = "Total 1 errors found in startup-config.\n>   x\nerrors in startup-config: 1\n"
    with pytest.raises(DriverError) as e:
        eos.parse_startup_config_errors(text)
    assert str(e.value) == f"{CMD}: unexpected output: 'Total 1 errors found in startup-config. > x errors in startup-config: 1'"
    long = "Total 1 errors found in startup-config.\n> " + "y " * 120 + "\nerrors in startup-config: 1\n"
    with pytest.raises(DriverError) as e:
        eos.parse_startup_config_errors(long)
    assert str(e.value) == f"{CMD}: unexpected output: {snippet(long)!r}"


@pytest.mark.parametrize("cmd, why", [
    ("neighbor 10.0.12.2 defualt-originate", "% Invalid input at line 3"),     # no '>' marker
    (">   neighbor 10.0.12.2 defualt-originate", "Invalid input on line 3"),   # reason EOS doesn't print
])
def test_startup_errors_unknown_pair_raises(cmd, why):
    """Either half of a pair not in EOS's form raises a DriverError: never listed, never a crash."""
    text = f"Total 1 errors found in startup-config.\n{cmd}\n{why}\nerrors in startup-config: 1\n"
    with pytest.raises(DriverError) as e:
        eos.parse_startup_config_errors(text)
    assert str(e.value) == f"{CMD}: unexpected output: {cmd!r} {why!r}"


def test_startup_errors_unknown_pair_message_caps_each_half_at_80():
    """The quoted pair is capped at 80 characters per line."""
    cmd, why = "x" * 100, "y" * 100
    text = f"Total 1 errors found in startup-config.\n{cmd}\n{why}\nerrors in startup-config: 1\n"
    with pytest.raises(DriverError) as e:
        eos.parse_startup_config_errors(text)
    assert str(e.value) == f"{CMD}: unexpected output: {'x' * 80!r} {'y' * 80!r}"


def test_startup_errors_marker_without_space_keeps_the_whole_line():
    """Only the '>' marker is removed from a rejected line: its first character is part of the line."""
    text = "Total 1 errors found in startup-config.\n>ip routing\n% Invalid input at line 3\nerrors in startup-config: 1\n"
    assert eos.parse_startup_config_errors(text) == ["line 3: ip routing (Invalid input)"]


def test_startup_errors_count_mismatch_says_both_counts():
    """A count that disagrees with the lines listed raises, saying both counts and what was listed."""
    text = "Total 2 errors found in startup-config.\n> a\n% Invalid input at line 3\nerrors in startup-config: 2\n"
    with pytest.raises(DriverError) as e:
        eos.parse_startup_config_errors(text)
    assert str(e.value) == f"{CMD}: says 2 and 2 errors, lists 1"


# --- eos._summary (via parse_bgp_summary)

def summary(peer):
    return json.dumps({"vrfs": {"default": {"peers": {"10.0.0.1": peer}}}})


def test_eos_established_without_count_names_the_command_and_peer():
    """An established peer with no prefixAccepted raises, naming the command and the peer."""
    with pytest.raises(DriverError) as e:
        eos.parse_bgp_summary(summary({"peerState": "Established"}))
    assert str(e.value) == f"unexpected output from `{SUMMARY}`: 10.0.0.1: established without prefixAccepted"


def test_eos_bad_prefix_count_names_the_command():
    """A prefixAccepted that isn't a number raises, naming the command it came from."""
    with pytest.raises(DriverError) as e:
        eos.parse_bgp_summary(summary({"peerState": "Established", "prefixAccepted": "many"}))
    assert str(e.value) == f"unexpected output from `{SUMMARY}`: not a number: 'many'"


# --- frr / base

def test_frr_vrfs_never_lists_default_and_keeps_evidence():
    """`default` is never a VRF to record even if zebra lists it; the `show vrf` call is kept as evidence."""
    lab = RecordingLab("vrf default id 0 table 254\nvrf red id 5 table 1001 (configured)\n")
    obs = FrrDriver(lab, "r1").vrfs()
    assert obs.value == ["red"]
    assert [e["cmd"] for e in obs.evidence] == ["vtysh -c show vrf"]


def test_frr_nos_version_asks_show_version():
    """The version comes from `show version`, the command FRR answers."""
    lab = RecordingLab("FRRouting 10.4.1_git (r1) on Linux.\n")
    assert FrrDriver(lab, "r1").nos_version() == "FRRouting 10.4.1_git"
    assert lab.cmds == [["vtysh", "-c", "show version"]]


def test_frr_version_found_after_a_banner_line():
    """The version line is found on any line, not only the first."""
    assert parse_version("Hello, this is FRRouting (version 10.4.1_git).\nFRRouting 10.4.1_git (r1) on Linux.\n") \
        == "FRRouting 10.4.1_git"


def test_base_driver_vrfs_says_listing_is_unsupported():
    """A driver without VRF listing says so by name (record turns it into a warning)."""
    with pytest.raises(DriverError) as e:
        Driver(None, "x1").vrfs()
    assert str(e.value) == "listing VRFs is not supported on base yet"
