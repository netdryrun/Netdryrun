"""A path count that disagrees with the paths listed is a parse error, never "no path" (0.4.1).

The Junos fuzz finding of 2026-11-01 (a route's entry dropped from under its count read as "no BGP path", so
`present: false` passed) has the same shape on three more drivers: FRR and SONiC print `pathCount`, Arista EOS
`totalPaths` and NX-OS `totalpaths` beside the paths they count, and the check drivers never compared them.
Each driver here: the live captures still parse, and a count that disagrees (a path dropped, a path added, the
count missing or not a number) errors with a message naming the command."""
import json
from pathlib import Path

import pytest

from netdryrun.drivers import DriverError, eos, frr, nxos

FIX = Path(__file__).parent / "fixtures"


def read(name: str) -> str:
    return (FIX / name).read_text(encoding="utf-8")


def _obj(d) -> str:
    return json.dumps(d, indent=1)


def _snip(detail: str) -> str:
    """What `unexpected()` keeps of a detail: whitespace collapsed, at most 200 characters."""
    return " ".join(detail.split())[:200]


def raises(fn, message: str):
    with pytest.raises(DriverError) as e:
        fn()
    assert str(e.value) == message


# ------------------------------------------------------------------------------------------------- FRR / SONiC

FRR = f"unexpected output from `{frr.BGP_PATHS_CMD}`: "


@pytest.mark.parametrize("name,prefix,paths", [
    ("frr_bgp_paths.txt", "192.168.20.0/24", 2), ("frr_bgp_paths_local.txt", "192.168.21.0/24", 1),
    ("frr_bgp_paths_noexport.txt", "192.168.22.0/24", 1), ("frr_bgp_paths_v6.txt", "2001:db8:20::/48", 1),
    ("sonic_bgp_paths.txt", "192.168.20.0/24", 2),
])
def test_frr_live_captures_still_parse(name, prefix, paths):
    assert len(frr.parse_bgp_paths(read(name), prefix)) == paths


def test_frr_path_dropped_under_its_count_is_an_error_not_one_path_less():
    d = json.loads(read("frr_bgp_paths.txt"))
    d["paths"] = d["paths"][1:]
    raises(lambda: frr.parse_bgp_paths(_obj(d), "192.168.20.0/24"), FRR + "pathCount 2, but 1 paths listed")
    d["paths"] = []
    raises(lambda: frr.parse_bgp_paths(_obj(d), "192.168.20.0/24"), FRR + "pathCount 2, but 0 paths listed")
    # the route check reads the same answer: a dropped path never makes the route absent
    raises(lambda: frr.parse_routes("{}", "192.168.20.0/24", _obj(d)), FRR + "pathCount 2, but 0 paths listed")


@pytest.mark.parametrize("edit,detail", [
    (lambda d: d.update(pathCount=3), "pathCount 3, but 2 paths listed"),
    (lambda d: d.pop("pathCount"), None),
    (lambda d: d.update(pathCount="two"), "not a number: 'two'"),
    (lambda d: d.update(pathCount=True), "not a number: True"),
], ids=["count-higher", "count-missing", "count-not-a-number", "count-bool"])
def test_frr_count_shapes(edit, detail):
    d = json.loads(read("frr_bgp_paths.txt"))
    edit(d)
    if detail is None:
        # no pathCount (FRR 10.2.1 prints none, oracle FP-042-FRR102): still an error without the text answer's count,
        # now named, and the paths are never read as fewer or none
        raises(lambda: frr.parse_bgp_paths(_obj(d), "192.168.20.0/24"), "bgpd listed the BGP paths for 192.168.20.0/24 without pathCount: the count comes from the text answer (`show bgp <afi> unicast <prefix>`), which wasn't read, so no verdict on them")
        return
    raises(lambda: frr.parse_bgp_paths(_obj(d), "192.168.20.0/24"), FRR + detail)


def test_frr_empty_answer_has_no_count_and_is_no_path():
    assert frr.parse_bgp_paths("{}", "10.0.0.0/24") == []


# ------------------------------------------------------------------------------------------------- Arista EOS

EOS = f"unexpected output from `{eos.BGP_CMD}`: "


@pytest.mark.parametrize("name,prefix,paths", [
    ("eos_bgp_paths.txt", "192.168.20.0/24", 2), ("eos_bgp_paths_as_set.txt", "172.16.0.0/16", 2),
    ("eos_bgp_paths_local.txt", "192.168.30.1/32", 1), ("eos_bgp_paths_no_med.txt", "192.168.1.1/32", 2),
    ("eos_bgp_paths_noexport.txt", "192.168.22.0/24", 1), ("eos_bgp_route.txt", "192.168.20.0/24", 1),
    ("eos_leak_bgp.txt", "0.0.0.0/0", 1),
])
def test_eos_live_captures_still_parse(name, prefix, paths):
    assert len(eos.parse_bgp_paths(read(name), prefix)) == paths


def _eos_entry(d, key="192.168.20.0/24"):
    return d["vrfs"]["default"]["bgpRouteEntries"][key]


def test_eos_path_dropped_under_its_count_is_an_error_not_one_path_less():
    d = json.loads(read("eos_leak_bgp.txt"))
    _eos_entry(d, "0.0.0.0/0")["bgpRoutePaths"] = []
    raises(lambda: eos.parse_bgp_paths(_obj(d), "0.0.0.0/0"), EOS + "0.0.0.0/0: totalPaths 1, but 0 paths listed")
    no_routes = _obj({"vrfs": {"default": {"routingDisabled": False, "routes": {}}}})
    raises(lambda: eos.parse_routes(no_routes, _obj(d), "0.0.0.0/0"), EOS + "0.0.0.0/0: totalPaths 1, but 0 paths listed")


@pytest.mark.parametrize("edit,detail", [
    (lambda e: e.update(totalPaths=3), "192.168.20.0/24: totalPaths 3, but 2 paths listed"),
    (lambda e: e["bgpRoutePaths"].pop(), "192.168.20.0/24: totalPaths 2, but 1 paths listed"),
    (lambda e: e.update(totalPaths="2x"), "not a number: '2x'"),
], ids=["count-higher", "path-dropped", "count-not-a-number"])
def test_eos_count_shapes(edit, detail):
    d = json.loads(read("eos_bgp_paths.txt"))
    edit(_eos_entry(d))
    raises(lambda: eos.parse_bgp_paths(_obj(d), "192.168.20.0/24"), EOS + detail)


def test_eos_count_missing_is_an_error():
    d = json.loads(read("eos_bgp_paths.txt"))
    e = _eos_entry(d)
    del e["totalPaths"]
    raises(lambda: eos.parse_bgp_paths(_obj(d), "192.168.20.0/24"),
           EOS + _snip(f"192.168.20.0/24: no totalPaths: {str({k: v for k, v in e.items() if k != 'bgpRoutePaths'})[:150]}"))


# ------------------------------------------------------------------------------------------------- NX-OS

NX = f"unexpected output from `{nxos.BGP_CMD}`: "


@pytest.mark.parametrize("name,prefix,vrf", [
    ("nxos_bgp_20.txt", "192.168.20.0/24", "default"), ("nxos_bgp_default.txt", "0.0.0.0/0", "default"),
    ("nxos_bgp_local.txt", "192.168.10.1/32", "default"), ("nxos_bgp_red.txt", "172.16.2.0/24", "RED"),
    ("nxos_bgp_v6.txt", "2001:db8:20::/48", "default"),
])
def test_nxos_live_captures_still_parse(name, prefix, vrf):
    assert len(nxos.parse_bgp_paths(read(name), prefix, vrf)) == 1


def _nx_prefix_row(d):
    """The one prefix row of an NX-OS BGP capture (the dict holding TABLE_path)."""
    found = []

    def walk(n):
        if isinstance(n, dict):
            if "TABLE_path" in n and ("ipprefix" in n or "ipv6prefix" in n):
                found.append(n)
            for v in n.values():
                walk(v)
        elif isinstance(n, list):
            for v in n:
                walk(v)
    walk(d)
    (row,) = found
    return row


def test_nxos_path_dropped_under_its_count_is_an_error_not_no_path():
    d = json.loads(read("nxos_bgp_default.txt"))
    row = _nx_prefix_row(d)
    path = row["TABLE_path"]["ROW_path"]
    row["TABLE_path"]["ROW_path"] = [path, path] if isinstance(path, dict) else path + path   # one path more
    raises(lambda: nxos.parse_bgp_paths(_obj(d), "0.0.0.0/0"), NX + "0.0.0.0/0: totalpaths 1, but 2 paths listed")
    row["totalpaths"] = "3"
    raises(lambda: nxos.parse_bgp_paths(_obj(d), "0.0.0.0/0"), NX + "0.0.0.0/0: totalpaths 3, but 2 paths listed")


@pytest.mark.parametrize("edit,detail", [
    (lambda r: r.update(totalpaths="2"), "0.0.0.0/0: totalpaths 2, but 1 paths listed"),
    (lambda r: r.update(totalpaths="one"), "not a number: 'one'"),
], ids=["count-higher", "count-not-a-number"])
def test_nxos_count_shapes(edit, detail):
    d = json.loads(read("nxos_bgp_default.txt"))
    edit(_nx_prefix_row(d))
    raises(lambda: nxos.parse_bgp_paths(_obj(d), "0.0.0.0/0"), NX + detail)


def test_nxos_count_missing_is_an_error():
    d = json.loads(read("nxos_bgp_default.txt"))
    row = _nx_prefix_row(d)
    del row["totalpaths"]
    raises(lambda: nxos.parse_bgp_paths(_obj(d), "0.0.0.0/0"),
           NX + _snip(f"0.0.0.0/0: no totalpaths: {str({k: v for k, v in row.items() if k != 'TABLE_path'})[:150]}"))


# ------------------------------------------------------------------------------------------------- exact messages

def test_missing_count_messages_cut_the_details_at_150_characters():
    long = "x" * 300
    d = json.loads(read("frr_bgp_paths.txt"))
    del d["pathCount"]
    d["zz"] = long
    # FRR: a missing pathCount is a named gap (FP-042-FRR102) that prints none of the answer's details
    raises(lambda: frr.parse_bgp_paths(_obj(d), "192.168.20.0/24"), "bgpd listed the BGP paths for 192.168.20.0/24 without pathCount: the count comes from the text answer (`show bgp <afi> unicast <prefix>`), which wasn't read, so no verdict on them")
    d = json.loads(read("eos_bgp_paths.txt"))
    e = _eos_entry(d)
    del e["totalPaths"]
    e["zz"] = long
    detail = str({k: v for k, v in e.items() if k != "bgpRoutePaths"})[:150]
    raises(lambda: eos.parse_bgp_paths(_obj(d), "192.168.20.0/24"), EOS + _snip(f"192.168.20.0/24: no totalPaths: {detail}"))
    row = {"ipprefix": "10.0.0.0/8", "zz": long, "TABLE_path": {"ROW_path": {"neighbor": "10.0.0.2"}}}
    raises(lambda: nxos._counted_paths(row), NX + _snip(f"10.0.0.0/8: no totalpaths: {str({'ipprefix': '10.0.0.0/8', 'zz': long})[:150]}"))


def test_nxos_missing_count_message_leaves_the_paths_out_and_names_an_ipv6_prefix():
    row = {"TABLE_path": {"ROW_path": {"neighbor": "10.0.0.2"}}, "ipprefix": "10.0.0.0/8"}
    raises(lambda: nxos._counted_paths(row), NX + "10.0.0.0/8: no totalpaths: {'ipprefix': '10.0.0.0/8'}")
    v6 = {"TABLE_path": {"ROW_path": {"neighbor": "2001:db8::2"}}, "ipv6prefix": "2001:db8::/32", "totalpaths": "2"}
    raises(lambda: nxos._counted_paths(v6), NX + "2001:db8::/32: totalpaths 2, but 1 paths listed")
