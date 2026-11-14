"""RT-0075 (oracle FP-042-NXOSHIST): an NX-OS BGP path flagged pathhistory or pathdeleted is no path.

Answers are derived from the live NX-OS 10.4(8) captures (tests/fixtures/nxos_bgp_default.txt, nxos_route_default.txt)
by the oracle's own `derived`; the two-path answer adds a copy of the captured path from a second neighbor. These tests
kill: ignoring pathhistory, ignoring pathdeleted, reading a missing or non-boolean flag as "not withdrawn", filtering in
`routes` only (bgp_route reads parse_bgp_paths), and dropping a prefix's live path along with a withdrawn one.
"""
import copy
import importlib.util
import json
from pathlib import Path

import pytest

from netdryrun.drivers.base import DriverError
from netdryrun.drivers.nxos import parse_bgp_paths, parse_routes

_PATH = Path(__file__).resolve().parent / "oracles" / "FP-042-NXOSHIST" / "test_oracle_fp_042_nxoshist.py"
_SPEC = importlib.util.spec_from_file_location("oracle_fp_042_nxoshist_unit", _PATH)
o = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(o)

FLAGS = ["pathhistory", "pathdeleted"]


def answers(flag):
    a = o.derived(flag)
    return a[o.ROUTE_CMD], a[o.BGP_CMD]


def edit_path(bgp_text, fn):
    bgp = json.loads(bgp_text)
    fn(o._prefix_row(bgp))
    return json.dumps(bgp)


@pytest.mark.parametrize("flag", FLAGS)
def test_a_withdrawn_path_is_no_bgp_route(flag):
    rt, bgp = answers(flag)
    assert [r.protocol for r in parse_routes(rt, bgp, o.PREFIX)] == ["static"]


@pytest.mark.parametrize("flag", FLAGS)
def test_a_withdrawn_path_is_no_bgp_path(flag):
    # bgp_route and record read parse_bgp_paths, not parse_routes: the same filter applies there
    _, bgp = answers(flag)
    assert parse_bgp_paths(bgp, o.PREFIX) == []


@pytest.mark.parametrize("flag", FLAGS)
def test_a_live_path_beside_a_withdrawn_one_stays(flag):
    rt, bgp = answers(flag)

    def add_live(row):
        withdrawn = row["TABLE_path"]["ROW_path"]
        live = copy.deepcopy(withdrawn)
        live.update({flag: "false", "pathvalid": "true", "pathbest": "true", "neighbor": "10.0.1.6"})
        row["TABLE_path"]["ROW_path"] = [withdrawn, live]
        row["totalpaths"] = "2"

    bgp = edit_path(bgp, add_live)
    assert [p.neighbor for p in parse_bgp_paths(bgp, o.PREFIX)] == ["10.0.1.6"]
    assert sorted(r.protocol for r in parse_routes(rt, bgp, o.PREFIX)) == ["bgp", "static"]


@pytest.mark.parametrize("flag", FLAGS)
@pytest.mark.parametrize("value", [None, "maybe", 1])
def test_a_missing_or_odd_flag_is_unexpected_output(flag, value):
    bgp = o.captured()[o.BGP_CMD]

    def set_flag(row):
        if value is None:
            del row["TABLE_path"]["ROW_path"][flag]
        else:
            row["TABLE_path"]["ROW_path"][flag] = value

    with pytest.raises(DriverError, match=flag if value is None else "not a boolean"):
        parse_bgp_paths(edit_path(bgp, set_flag), o.PREFIX)


def test_the_captured_valid_path_is_still_read():
    rt, bgp = o.captured()[o.ROUTE_CMD], o.captured()[o.BGP_CMD]
    assert [p.neighbor for p in parse_bgp_paths(bgp, o.PREFIX)] == ["10.0.1.2"]
    assert sorted(r.protocol for r in parse_routes(rt, bgp, o.PREFIX)) == ["bgp", "static"]
