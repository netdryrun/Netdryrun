"""record._attribute_check on an attribute the driver couldn't read (RT-S01 fix, 0.4.2): never silently dropped.

An unknown AS path writes no bgp_route check (one without as_path would pass a changed path) and an INCOMPLETE
BASELINE line names the route, so `record` exits 1. An unknown local preference is named, without a gap: a path
without LOCAL_PREF is a real answer on some drivers."""
from netdryrun import record as rec
from netdryrun.drivers.base import BgpPath, Observation


class Drv:
    name = "fake"
    unsupported_bgp_attributes = frozenset()

    def __init__(self, path):
        self.path = path

    def bgp_paths(self, prefix, vrf="default"):
        return Observation([self.path], [])

    def community_aliases(self):
        return Observation(False, [])


def path(**kw):
    return BgpPath(**{"best": True, "as_path": "65020", "next_hop": "10.0.0.2", "local_pref": 100, "med": None, **kw})


def test_an_unknown_as_path_writes_no_check_and_names_the_gap():
    w: list = []
    assert rec._attribute_check(Drv(path(as_path=None)), "r1", "10.9.0.0/24", "red", w) is None
    gaps = rec.baseline_gaps(w)
    assert len(gaps) == 1 and gaps[0].startswith("INCOMPLETE BASELINE: r1 vrf red: 10.9.0.0/24: no bgp_route check")
    assert "AS path" in gaps[0]


def test_an_empty_as_path_is_pinned_as_empty():
    w: list = []
    c = rec._attribute_check(Drv(path(as_path="")), "r1", "10.9.0.0/24", "default", w)
    assert c["as_path"] == "" and not rec.baseline_gaps(w)


def test_an_unknown_local_pref_is_named_but_not_a_gap():
    w: list = []
    c = rec._attribute_check(Drv(path(local_pref=None)), "r1", "10.9.0.0/24", "default", w)
    assert c is not None and "local_pref" not in c and c["as_path"] == "65020"
    assert any("local_pref is not recorded" in x for x in w) and not rec.baseline_gaps(w)
