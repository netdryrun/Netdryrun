"""FRR 10.2.1 path count (0.4.2, oracle FP-042-FRR102): the gaps the mutation run on be62293 left in its tests.

bgpd 10.2.1 lists a prefix's paths without pathCount; the count then comes from the text answer's "Paths: (N
available". These pin what a user depends on there: a path dropped from the JSON listing is an error, never one path
less (a false `present: false` or a wrong AS-path pass); a text answer that names no readable prefix gives no count;
an answer that isn't JSON is reported as what it is, not as a missing count; and every such error is a DriverError
that names the prefix the check asked about and the counts that disagree.
"""
import importlib.util
import json
from pathlib import Path

import pytest

from netdryrun.drivers.base import DriverError
from netdryrun.drivers.frr import (BGP_PATHS_CMD, FrrDriver, _path_count, needs_text_count, parse_bgp_paths,
                                   parse_paths_available, parse_routes)

_PATH = Path(__file__).resolve().parent / "oracles" / "FP-042-FRR102" / "test_oracle_fp_042_frr102.py"
_SPEC = importlib.util.spec_from_file_location("oracle_fp_042_frr102_pathcount", _PATH)
o = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(o)

LEARNED = o.LEARNED   # 192.168.21.0/24: two eBGP paths, "Paths: (2 available"


def learned_json(paths: int | None = None, prefix: str | None = None) -> str:
    """The captured 10.2.1 answer for the learned prefix (no pathCount), cut to `paths` paths and/or renamed."""
    data = json.loads(o.fx("frr1021_learned_prefix_json.txt"))
    assert "pathCount" not in data
    if paths is not None:
        data["paths"] = data["paths"][:paths]
    if prefix is not None:
        data["prefix"] = prefix
    return json.dumps(data)


LEARNED_TEXT = o.fx("frr1021_learned_prefix_text.txt")


# ------------------------------------------------------------------ a dropped path is an error, a DriverError

def test_a_path_dropped_under_the_text_count_is_a_driver_error():
    """The text answer says 2 available, the JSON lists 1: never read as one path. The error is a DriverError (a
    TypeError would be an internal error, not a named read failure), and it gives the command and both counts."""
    count = parse_paths_available(LEARNED_TEXT, LEARNED)
    assert count == 2
    with pytest.raises(DriverError) as e:
        parse_bgp_paths(learned_json(paths=1), LEARNED, default_local_pref=100, text_count=count)
    msg = str(e.value)
    assert BGP_PATHS_CMD in msg
    assert "2 paths available" in msg and "1 listed" in msg


def test_all_paths_dropped_under_the_text_count_is_not_absent():
    """Text: 2 available; JSON: the prefix with an empty paths list. Never "no BGP path"."""
    with pytest.raises(DriverError):
        parse_bgp_paths(learned_json(paths=0), LEARNED, default_local_pref=100, text_count=2)


def test_route_check_side_also_rejects_a_dropped_path():
    """parse_routes reads the BGP side with the same count (bgp_count): a dropped path is an error there too."""
    zebra = o.fx("frr1021_learned_route_json.txt")
    with pytest.raises(DriverError):
        parse_routes(zebra, LEARNED, learned_json(paths=1), bgp_count=2)


def test_driver_with_a_dropped_path_gives_no_bgp_paths():
    """Through the real driver on the captured lab, with one path cut from the JSON answer."""
    lab = o.CapturedLab({f"show bgp ipv4 unicast {LEARNED} json": learned_json(paths=1)})
    with pytest.raises(DriverError, match="2 paths available"):
        FrrDriver(lab, "leaf01").bgp_paths(LEARNED)


# ------------------------------------------------------------------ a text answer naming no readable prefix: no count

@pytest.mark.parametrize("entry", [
    "[2]:[0]:[48]:[aa:bb:cc:dd:ee:ff]",      # an EVPN-style entry: no IP prefix
    "192.168.21.0/33",                      # no valid prefix length
    "not-a-prefix",
])
def test_an_entry_line_naming_no_readable_prefix_gives_no_count(entry):
    """An entry line the parser can't read as a prefix is not "this prefix": its "2 available" must not be taken as
    the count for the prefix asked (a count from another entry could match a cut listing)."""
    text = LEARNED_TEXT.replace("192.168.21.0/24", entry, 1)
    assert f"BGP routing table entry for {entry}," in text
    with pytest.raises(DriverError, match="no single path count"):
        parse_paths_available(text, LEARNED)


def test_driver_with_an_unreadable_entry_line_gives_no_verdict():
    lab = o.CapturedLab({f"show bgp ipv4 unicast {LEARNED}": LEARNED_TEXT.replace("192.168.21.0/24", "garbage", 1)})
    with pytest.raises(DriverError, match="no single path count"):
        FrrDriver(lab, "leaf01").bgp_paths(LEARNED)


# ------------------------------------------------------------------ not JSON: reported as such, no text read

def test_a_non_json_answer_needs_no_text_count():
    assert needs_text_count("% Unknown command: show bgp ipv4 unicast 10.0.0.0/24 json\n") is False
    assert needs_text_count("") is False
    assert needs_text_count(learned_json()) is True


def test_driver_reports_a_non_json_answer_as_unexpected_output():
    """bgpd printing text instead of JSON is unexpected output, named with what it printed. It is not a missing
    pathCount, and the driver doesn't go on to read the text answer (which would only hide the real fault)."""
    prefix = "10.0.0.0/24"
    junk = "% BGP is not running in this instance\n"
    calls = []

    class Lab(o.CapturedLab):
        def exec(self, node, cmd, timeout=60, input=None):
            calls.append(cmd)
            return super().exec(node, cmd, timeout, input)
    lab = Lab({f"show bgp ipv4 unicast {prefix} json": junk})
    with pytest.raises(DriverError) as e:
        FrrDriver(lab, "leaf01").bgp_paths(prefix)
    assert "unexpected output" in str(e.value) and "BGP is not running" in str(e.value)
    assert ["vtysh", "-c", f"show bgp ipv4 unicast {prefix}"] not in calls, calls


# ------------------------------------------------------------------ the no-count error names the prefix

def test_no_count_error_names_the_prefix_asked():
    """No pathCount and no text count: no verdict, naming the prefix the check asked about, even when bgpd's answer
    names another one (that answer is wrong twice; the user must see which check had no verdict)."""
    with pytest.raises(DriverError) as e:
        parse_bgp_paths(learned_json(prefix="10.9.9.0/24"), LEARNED, default_local_pref=100)
    assert LEARNED in str(e.value) and "without pathCount" in str(e.value)


def test_no_count_error_without_a_prefix_names_bgpds_prefix():
    """_path_count called without the prefix asked (its default) falls back to the prefix bgpd answered for."""
    with pytest.raises(DriverError) as e:
        _path_count(BGP_PATHS_CMD, json.loads(learned_json()))
    assert LEARNED in str(e.value) and "without pathCount" in str(e.value)
