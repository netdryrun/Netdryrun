"""IOP-8 (0.4 interop run 2): FRR lists every multipath path in `advertised-routes detail json`, without an
addpathTxId when the session has no add-path. The neighbor is sent one path, the best; anything that can't name
that one path stays unreadable (verify exit 2), never a guess."""
import copy
import json
from pathlib import Path

import pytest

from netdryrun.verify import frr as vfrr
from netdryrun.verify.snapshot import SnapshotError
from test_verify_snapshot import FakeNode
from verify_helpers import fixture

FIX = Path(__file__).parent / "fixtures"
CMD = "show bgp ipv4 unicast neighbors 10.9.3.2 advertised-routes detail json"
PFX = "192.168.3.1/32"


def _doc(edit=None) -> str:
    doc = json.loads((FIX / "frr_adj_out_multipath.txt").read_text(encoding="utf-8"))
    if edit:
        edit(doc["advertisedRoutes"][PFX]["paths"])
    return json.dumps(doc)


def _edited(name, fn) -> str:
    d = json.loads(fixture(name))
    fn(d)
    return json.dumps(d)


def _make_second_best(paths):
    # the non-best path differs, so reading the wrong one would show
    other = next(p for p in paths if "bestpath" not in p)
    other["metric"] = 77


def test_the_best_path_is_the_one_read_even_when_the_other_differs():
    out = vfrr.parse_adj(_doc(_make_second_best), CMD, "ipv4", "out", add_path_tx=False)
    assert out[(PFX, 0)].med is None


def test_the_best_path_is_read_wherever_it_is_listed():
    def swap(paths):
        _make_second_best(paths)
        paths.reverse()
    out = vfrr.parse_adj(_doc(swap), CMD, "ipv4", "out", add_path_tx=False)
    assert list(out) == [(PFX, 0)] and out[(PFX, 0)].med is None


@pytest.mark.parametrize("edit, why", [
    (None, "several paths without addpathTxId"),                                       # add-path TX: ids needed
], ids=["add-path-session"])
def test_must_fail_a_session_with_add_path_still_needs_path_ids(edit, why):
    with pytest.raises(SnapshotError, match=why):
        vfrr.parse_adj(_doc(edit), CMD, "ipv4", "out")          # default: add-path assumed (fail closed)
    with pytest.raises(SnapshotError, match=why):
        vfrr.parse_adj(_doc(edit), CMD, "ipv4", "out", add_path_tx=True)


@pytest.mark.parametrize("edit, why", [
    (lambda ps: ps[0].pop("bestpath"), "2 paths listed without add-path and 0 flagged best"),
    (lambda ps: ps[1].update(bestpath=copy.deepcopy(ps[0]["bestpath"])), "and 2 flagged best"),
    (lambda ps: ps[0]["bestpath"].update(overall=False), "and 0 flagged best"),
    (lambda ps: ps[0]["bestpath"].update(overall="yes"), "overall"),
    (lambda ps: ps[0].update(bestpath=["overall"]), "bestpath"),
    (lambda ps: ps[0]["bestpath"].update(newKey=1), "newKey"),
    (lambda ps: ps.__setitem__(1, "path"), "not an object"),
], ids=["no-best", "two-best", "best-false", "best-not-bool", "bestpath-not-object", "unknown-key", "not-object"])
def test_must_fail_without_add_path_the_sent_path_must_be_named_exactly_once(edit, why):
    with pytest.raises(SnapshotError, match=why):
        vfrr.parse_adj(_doc(edit), CMD, "ipv4", "out", add_path_tx=False)


def test_paths_that_carry_ids_are_read_by_id_whatever_the_session():
    def ids(paths):
        for i, p in enumerate(paths):
            p["addpathTxId"] = i + 1
    for tx in (True, False):
        out = vfrr.parse_adj(_doc(ids), CMD, "ipv4", "out", add_path_tx=tx)
        assert sorted(out) == [(PFX, 1), (PFX, 2)]


def test_some_paths_with_an_id_and_some_without_is_unreadable():
    with pytest.raises(SnapshotError, match="several paths without addpathTxId"):
        vfrr.parse_adj(_doc(lambda ps: ps[0].update(addpathTxId=1)), CMD, "ipv4", "out", add_path_tx=False)


def _neighbors(addpath) -> str:
    # the live `show bgp vrf all neighbors json` capture of edge1 (tests/fixtures/verify)
    doc = json.loads(fixture("neighbors.txt"))
    for inst in doc.values():
        for nb in inst.values():
            if isinstance(nb, dict) and "neighborCapabilities" in nb:
                if addpath is None:
                    nb["neighborCapabilities"].pop("addPath", None)
                else:
                    nb["neighborCapabilities"]["addPath"] = copy.deepcopy(addpath)
    return json.dumps(doc)


def test_add_path_tx_is_read_from_the_neighbor_capabilities():
    # the live capture: receive only (FRR's default), so one path per prefix is sent
    text = fixture("neighbors.txt")
    assert vfrr.add_path_tx(text) == set()
    assert vfrr.add_path_tx(_neighbors(None)) == set()
    for flag in ("txAdvertised", "txReceived", "txAdvertisedAndReceived"):
        tx = vfrr.add_path_tx(_neighbors({"ipv4Unicast": {flag: True}}))
        assert ("default", "10.0.2.2", "ipv4-unicast") in tx, flag
    assert vfrr.add_path_tx(_neighbors({"ipv4Unicast": {"txAdvertised": False, "rxReceived": True}})) == set()


@pytest.mark.parametrize("addpath", [
    {"ipv4Unicast": {"txAdvertised": "yes"}},       # not a clear false
    {"ipv4Unicast": {"txAdvertised": None}},
    {"ipv4Unicast": "both"},                          # not an object
    "on",                                             # addPath not an object
], ids=["value", "null", "family", "addpath"])
def test_must_fail_add_path_tx_that_is_not_a_clear_no_counts_as_add_path(addpath):
    assert ("default", "10.0.2.2", "ipv4-unicast") in vfrr.add_path_tx(_neighbors(addpath))


# --- end to end, the collector on the live edge1 capture -------------------------------------------------

ADJ_OUT = vfrr.adj_command("default", "ipv4", "10.0.2.2", "out")


def _multipath_adj_out(d):
    # 192.0.2.0/24 listed twice, as FRR lists a multipath prefix: the copy is not best and has another MED
    dest = d["advertisedRoutes"]["192.0.2.0/24"]
    other = copy.deepcopy(dest["paths"][0])
    other.pop("bestpath")
    other["metric"] = 77
    dest["paths"].append(other)
    dest["pathCount"] = 2


def _collect(neighbors=None):
    over = {ADJ_OUT: _edited("adj_out_default_ipv4_10.0.2.2.txt", _multipath_adj_out)}
    if neighbors is not None:
        over[vfrr.NEIGHBORS_CMD] = neighbors
    return vfrr.FrrCollector("edge1", FakeNode(over)).collect()


def test_collector_reads_the_best_path_sent_on_a_session_without_add_path():
    snap = _collect()
    keys = [k for k in snap.items if k.kind == "adj_out" and k.neighbor == "10.0.2.2" and k.prefix == "192.0.2.0/24"]
    assert [k.path_id for k in keys] == [0]
    assert snap.items[keys[0]].med == vfrr.parse_attrs(ADJ_OUT, json.loads(fixture(
        "adj_out_default_ipv4_10.0.2.2.txt"))["advertisedRoutes"]["192.0.2.0/24"]["paths"][0], "best")[2].med != 77


def test_must_fail_collector_refuses_multipath_without_ids_on_an_add_path_session():
    with pytest.raises(SnapshotError, match="several paths without addpathTxId"):
        _collect(_neighbors({"ipv4Unicast": {"txAdvertised": True}}))   # this node may send add-path
