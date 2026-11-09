"""frr.parse_paths_available on FRR 10.2.1's real text answers (the FP-042-FRR102 capture, martimy/clab-bgp-frr).

FRR prints "BGP routing table entry for 192.168.21.0/24, version 5". The prefix was read with the comma, never
matched, and every route on FRR 10.2.1 became a named gap instead of a verdict: fail-safe, but the FRR102 fix did
nothing on the capture it was written for (its oracle accepts either). These pin the count on the captured text."""
from pathlib import Path

import pytest

from netdryrun.drivers.base import DriverError
from netdryrun.drivers.frr import parse_paths_available

FX = Path(__file__).resolve().parent / "fixtures"


def fx(name):
    return (FX / name).read_text(encoding="utf-8")


@pytest.mark.parametrize("name,prefix,count", [("frr1021_learned_prefix_text.txt", "192.168.21.0/24", 2),
                                               ("frr1021_own_prefix_text.txt", "192.168.11.0/24", 1)])
def test_the_captured_text_answer_gives_its_path_count(name, prefix, count):
    assert parse_paths_available(fx(name), prefix) == count


def test_another_prefixs_answer_gives_no_count():
    with pytest.raises(DriverError, match="no single path count"):
        parse_paths_available(fx("frr1021_learned_prefix_text.txt"), "192.168.11.0/24")


def test_the_strangers_learned_paths_read_with_the_text_count():
    from netdryrun.drivers.frr import needs_text_count, parse_bgp_paths
    js = fx("frr1021_learned_prefix_json.txt")
    assert needs_text_count(js)
    paths = parse_bgp_paths(js, "192.168.21.0/24", text_count=parse_paths_available(
        fx("frr1021_learned_prefix_text.txt"), "192.168.21.0/24"))
    assert [(x.best, x.as_path) for x in paths] == [(True, "65000 65002"), (False, "65000 65002")]
