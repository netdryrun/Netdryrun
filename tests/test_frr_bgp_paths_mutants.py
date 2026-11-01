"""frr._bgp_paths_raw pinned for the 0.4.1 mutation gate: the exact error a user reads for every answer the BGP
paths parser refuses (the command it names, what was wrong), and the stale-path message during graceful restart.
Every surviving mutant of the function changed one of these messages or the shape check's logic."""
import json

import pytest

from netdryrun.drivers import frr
from netdryrun.drivers.base import DriverError

CMD = frr.BGP_PATHS_CMD
U = f"unexpected output from `{CMD}`: "
P = "10.1.0.0/16"


def message(text: str, prefix: str = P) -> str:
    with pytest.raises(DriverError) as e:
        frr.parse_bgp_paths(text, prefix)
    return str(e.value)


def answer(paths, **extra) -> str:
    return json.dumps({"prefix": P, "pathCount": len(paths), "paths": paths, **extra})


def test_unreadable_answer_names_the_command():
    assert message("not json") == U + "not json"


@pytest.mark.parametrize("data", [
    {"pathCount": 0, "paths": []},              # no prefix
    {"prefix": P, "pathCount": 0},              # no paths
    {"prefix": P, "pathCount": 0, "paths": {}},  # paths not a list
])
def test_shape_errors_print_the_answer_and_name_the_command(data):
    """Either key missing is an error of its own (the shape check is an `or`), shown as the device printed it."""
    text = json.dumps(data)
    assert message(text) == U + " ".join(text.split())


def test_bad_prefix_names_the_command():
    assert message(json.dumps({"prefix": "bad", "pathCount": 0, "paths": []})) == U + "not a prefix: 'bad'"


def test_a_path_that_isnt_an_object_is_shown_cut_at_150_characters():
    long = "x" * 300
    assert message(answer([long])) == U + f"path: {long[:150]}"


def test_stale_path_names_the_prefix_and_the_peer():
    stale = {"stale": True, "peer": {"peerId": "10.0.0.2"}}
    assert message(answer([stale])) == \
        f"{P}: BGP path from 10.0.0.2 is stale (graceful restart in progress): not settled"


@pytest.mark.parametrize("path", [{"stale": True}, {"stale": True, "peer": None}, {"stale": True, "peer": {}}],
                         ids=["no-peer", "peer-null", "peer-empty"])
def test_stale_path_without_a_peer_address_says_question_mark(path):
    assert message(answer([path])) == f"{P}: BGP path from ? is stale (graceful restart in progress): not settled"
