"""A key in device output that decides a verdict is present, proven absent, or unknown, and unknown is an error: never
read as empty, zero or false (Layer 6 round 2 on eaa323c, QUALITY-SYSTEM rule 1: the class closed mechanically, not
one instance at a time). The AST scan below fails on a defaulted read of a listed key in drivers/ and checks.py; every
entry of its allowlist says why that read is safe. The tests after it are the known instances, each failing on
eaa323c."""
import ast
import json
from pathlib import Path

import pytest

from netdryrun import checks
from netdryrun.checks import Unready
from netdryrun.drivers import DriverError, detect, eos, frr, junos, nxos, routeros, srlinux
from netdryrun.drivers.base import Observation
from netdryrun.lab import Node

SRC = Path(__file__).parent.parent / "src" / "netdryrun"
FX = Path(__file__).parent / "fixtures"

# keys whose value decides a verdict: counts, AS path, communities, stale, programmed/installed/best flags, family
# and session state, protocol or route type
VERDICT_KEYS = frozenset({
    "communityList", "largeCommunityList", "asPathEntry", "asPath", "routeType", "stale", "active", "kernelProgrammed",
    "hardwareProgrammed", "prefixAccepted", "as-path", "communities", "community", "large-community",
    "received-routes", "rejected-routes", "oper-state", "stale-route", "suppressed", "pending-operation-type",
    "last-failed-operation-type", "route-type", "origin-protocol", "aspath", "pathstaled", "ubest", "largecommunity",
    "pathbest", "totalPrefixCounter", "pfxRcd", "pfxSnt", "acceptedPrefixCounter", "bestpath", "largeCommunity",
    "protocol", "installed", "selected", "failed", "bgp.communities", "bgp.large-communities", "bgp.as-path",
    "rt-entry-state", "active-tag", "accepted-prefix-count", "received-prefix-count", "totalRoutes", "state",
    "peerState", "session-state", "afi-safi", "addressFamilyInfo", "addPath"})

# (file, key) -> why the defaulted read can't pass a check on a missing key
ALLOWED = {
    ("checks.py", "communities"): "a netdryrun.yml parameter of the check (p), validated by config, not device output",
    ("checks.py", "protocol"): "a netdryrun.yml parameter of the check (p), validated by config, not device output",
    ("checks.py", "state"): "a netdryrun.yml parameter of the check (p), validated by config, not device output",
    ("frr.py", "addressFamilyInfo"): "an established session without it is an error (default None); only a session "
                                     "that is down defaults to no families, and its counts are never judged",
    ("frr.py", "bestpath"): "a path without bestpath reads as not best, which only fails a best-path check",
    ("frr.py", "community"): "bgpd adds `community` to a path's JSON only when the path carries the attribute "
                             "(frr_bgp_paths captures with and without): absence is proven empty",
    ("frr.py", "largeCommunity"): "as `community`: bgpd prints it only for a path with large communities",
    ("nxos.py", "ubest"): "NX-OS prints ubest only on the best path (nxos_route_default.txt, live): absent reads not "
                          "active, which only fails `present`; `present: false` fails on any listed route",
    ("routeros_state.py", "bgp.communities"): "RouterOS leaves it out of a path with none (live); without_communities "
                                              "is refused on RouterOS for that reason",
    ("routeros_state.py", "bgp.large-communities"): "as bgp.communities",
    ("srlinux.py", "afi-safi"): "an established session without it is an error (default None); a down one has none",
    ("srlinux.py", "communities"): "YANG state leaves an empty container out: a path without communities has none "
                                   "(srl_attr_set_rejected.txt, live)",
    ("srlinux.py", "origin-protocol"): "defaults to bgp: a row without it counts as learned over BGP, which only "
                                       "makes `present: false` fail",
}


def defaulted_reads(root: Path = SRC) -> set[tuple[str, str]]:
    """(file, key) for every `x.get(KEY, default)` with a default other than None, and every `x.get(KEY) or ...`."""
    out = set()
    for f in sorted((root / "drivers").glob("*.py")) + [root / "checks.py"]:
        for n in ast.walk(ast.parse(f.read_text(encoding="utf-8"))):
            if isinstance(n, ast.BoolOp) and isinstance(n.op, ast.Or):
                n = n.values[0]
                if _get(n) and len(n.args) == 1:
                    out.add((f.name, n.args[0].value))
            elif _get(n) and len(n.args) == 2 and not (isinstance(n.args[1], ast.Constant) and n.args[1].value is None):
                out.add((f.name, n.args[0].value))
    return out


def _get(n) -> bool:
    return (isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == "get" and bool(n.args)
            and isinstance(n.args[0], ast.Constant) and n.args[0].value in VERDICT_KEYS)


def test_no_verdict_key_is_read_with_a_default():
    found = defaulted_reads()
    assert sorted(found - set(ALLOWED)) == []
    assert sorted(set(ALLOWED) - found) == []   # a stale allowlist entry is removed with the read it excused


# --- the known instances (Layer 6 round 2 on eaa323c: cross-platform review, GPT and Grok audits) ------------------

def _eos_paths():
    d = json.loads((FX / "eos_bgp_paths_noexport.txt").read_text(encoding="utf-8"))
    return d, d["vrfs"]["default"]["bgpRouteEntries"]["192.168.22.0/24"]["bgpRoutePaths"][0]


@pytest.mark.parametrize("drop", [lambda p: p["routeDetail"].pop("communityList"),
                                  lambda p: p["routeDetail"].pop("largeCommunityList"),
                                  lambda p: p.pop("asPathEntry"), lambda p: p["routeType"].pop("stale"),
                                  lambda p: p["routeType"].pop("active")],
                         ids=["communityList", "largeCommunityList", "asPathEntry", "stale", "active"])
def test_eos_a_missing_path_key_is_an_error(drop):
    """communityList missing read as no communities (`without_communities` passed), asPathEntry as the empty path
    (`as_path: ""` passed), routeType.stale as not stale."""
    d, path = _eos_paths()
    drop(path)
    with pytest.raises(DriverError):
        eos.parse_bgp_paths(json.dumps(d), "192.168.22.0/24")


class _Paths:
    def __init__(self, paths):
        self.paths = paths

    def bgp_paths(self, prefix, vrf="default"):
        return Observation(self.paths, [])


def test_srl_an_attr_set_without_as_path_is_unknown_and_an_as_path_check_errors():
    a = json.loads((FX / "srl_attr_set_best.txt").read_text(encoding="utf-8"))
    del a["as-path"]
    bp = srlinux.parse_attr_set(json.dumps(a), {"best-route": True, "neighbor": "10.2.1.2", "origin-protocol": "bgp"})
    assert bp.as_path is None
    passed, detail, _ = checks._bgp_route(_Paths([bp]), {"prefix": "192.168.22.0/24", "as_path": ""})
    assert passed is False and isinstance(detail, Unready)


def _srl_neighbors(af):
    return json.dumps({"neighbor": [{"peer-address": "10.0.0.2", "session-state": "established",
                                     "afi-safi": [{"afi-safi-name": "ipv4-unicast", **af}]}]})


@pytest.mark.parametrize("af,detail", [({"oper-state": "up", "received-routes": 5}, "no rejected-routes"),
                                       ({}, "10.0.0.2 ipv4-unicast: no oper-state")])
def test_srl_a_missing_family_counter_or_state_is_an_error(af, detail):
    """rejected-routes missing read as 0 (received alone over-counts); a family with neither oper-state nor counters
    read as not carried, which passes `exact: 0`."""
    with pytest.raises(DriverError, match=detail):
        srlinux.parse_bgp_neighbors(_srl_neighbors(af))


def test_srl_a_local_rib_row_without_its_stale_mark_is_an_error():
    rib = json.dumps({"route": [{"prefix": "10.9.0.0/24", "neighbor": "10.0.0.2", "origin-protocol": "bgp",
                                 "best-route": True, "valid-route": True}]})
    with pytest.raises(DriverError, match="no stale-route"):
        srlinux._rib_rows(rib, "10.9.0.0/24")


@pytest.mark.parametrize("route,detail", [({"active": True}, "no suppressed"), ({}, "no active")])
def test_srl_a_route_without_its_forwarding_state_is_an_error(route, detail):
    fib = {"suppressed": False, "pending-operation-type": "none", "last-failed-operation-type": "none"}
    if route.get("active"):
        fib.pop("suppressed")
    r = {"ipv4-prefix": "10.1.0.0/16", "route-type": "bgp", **route, "fib-programming": fib}
    with pytest.raises(DriverError, match=detail):
        srlinux.parse_routes(json.dumps({"route": [r]}), "10.1.0.0/16")


def test_srl_a_bgp_route_type_it_does_not_know_is_an_error():
    """Folded into bgp, a new subtype matched `protocol: bgp` but not `protocol: bgp-evpn`, so `present: false` on
    bgp-evpn missed it."""
    with pytest.raises(DriverError, match="route-type 'bgp-mystery' is not one this driver maps to a protocol"):
        srlinux._protocol("bgp-mystery")
    assert srlinux._protocol("bgp-evpn") == "bgp-evpn" and srlinux._protocol("bgp") == "bgp"


def _strip(o, key):
    if isinstance(o, dict):
        o.pop(key, None)
        for v in o.values():
            _strip(v, key)
    elif isinstance(o, list):
        for v in o:
            _strip(v, key)
    return o


def test_nxos_a_path_without_its_stale_mark_is_an_error():
    j = _strip(json.loads((FX / "nxos_bgp_20.txt").read_text(encoding="utf-8")), "pathstaled")
    with pytest.raises(DriverError, match="no pathstaled"):
        nxos.parse_bgp_paths(json.dumps(j), "192.168.20.0/24")


def test_nxos_a_path_without_aspath_is_unknown():
    j = _strip(json.loads((FX / "nxos_bgp_20.txt").read_text(encoding="utf-8")), "aspath")
    [p] = nxos.parse_bgp_paths(json.dumps(j), "192.168.20.0/24")
    assert p.as_path is None


@pytest.mark.parametrize("driver", [nxos.NxosDriver, junos.JunosDriver, routeros.RouterosDriver])
def test_without_communities_is_refused_where_a_path_without_them_omits_the_key(driver):
    assert "without_communities" in driver.unsupported_bgp_attributes


def test_frr_a_received_path_that_names_no_prefix_is_an_error():
    """`only` judged every listed prefix: a malformed element still counted as received."""
    text = json.dumps({"routes": {"10.10.0.0/24": [{"valid": True}]}, "totalRoutes": 1})
    with pytest.raises(DriverError, match="10.10.0.0/24 path"):
        frr.parse_received(text, 4)


def test_verify_a_listing_without_its_total_is_an_error():
    from netdryrun.verify import frr as vfrr
    from netdryrun.verify.snapshot import SnapshotError
    d = json.loads((FX / "frr_adj_out_multipath.txt").read_text(encoding="utf-8"))
    d.pop("totalPrefixCounter")
    with pytest.raises(SnapshotError, match="no totalPrefixCounter"):
        vfrr.parse_adj(json.dumps(d), "show bgp ipv4 unicast neighbors 10.0.0.2 advertised-routes detail json",
                       "ipv4", "out", add_path_tx=False)


@pytest.mark.parametrize("kind,image", [("generic_vm", "vrnetlab/cisco_n9kv-frr"), ("linux", "frrouting/frr-ceos"),
                                        ("srl", "vrnetlab/vr-n9kv:10.4")])
def test_an_image_name_of_another_nos_than_its_kind_is_an_error(kind, image):
    """kind generic_vm with an n9kv image was detected as frr ("frr" in the image name)."""
    with pytest.raises(DriverError, match="the image name looks like"):
        detect(Node("n1", "clab-t-n1", kind, image))


def test_detection_of_plain_images_is_unchanged():
    assert detect(Node("r1", "c", "linux", "quay.io/frrouting/frr:10.4.1")) == "frr"
    assert detect(Node("s1", "c", "srl", "ghcr.io/nokia/srlinux:26.7.2")) == "srlinux"
    assert detect(Node("e1", "c", "ceos", "ceos:4.36.3M")) == "eos"
    assert detect(Node("v1", "c", "sonic-vs", "docker-sonic-vs:latest")) == "sonic"


def test_only_sonic_may_carry_the_frr_mark():
    """SONiC runs FRR inside, so its image may name frr; any other NOS whose image names frr is a mismatch."""
    assert detect(Node("v1", "c", "sonic-vs", "docker-sonic-vs-frr:202505")) == "sonic"
    with pytest.raises(DriverError, match="looks like frr, not eos"):
        detect(Node("e1", "c", "ceos", "ceos-frr:4.36.3M"))
    with pytest.raises(DriverError, match="looks like frr, not srlinux"):
        detect(Node("s1", "c", "srl", "srlinux-frr:26.7.2"))


@pytest.mark.parametrize("peer", [{}, {"peerAddr": None}, {"peerAddr": 5}, "10.0.0.2", None])
def test_eos_path_whose_peer_address_is_not_a_string_is_an_error(peer):
    """A path whose peerEntry carries no string peerAddr can't be told learned from local: an error, never a guess."""
    with pytest.raises(DriverError, match="path without peerEntry"):
        eos._learned({"peerEntry": peer})


# --- the Action holds every status to its evidence ------------------------------------------------------------------

def test_action_verify_match_without_a_declared_line_or_inconclusive_without_reason_is_no_verdict(tmp_path):
    from test_action_verify import read_result, verify_report
    from verify_helpers import add_new_customer_block, base
    rep, _ = verify_report(tmp_path / "m", base().snap(), add_new_customer_block(base()).snap(),
                           "intent:\n  - prefix: 10.101.0.0/24\n    appears_on: [edge1, up1, peer1]\n")
    assert read_result(tmp_path, rep, "0")["status"] == "matched"
    assert read_result(tmp_path, {**rep, "declared": []}, "0")["status"] == "error"
    inc = {**rep, "status": "inconclusive", "verdict": "INCONCLUSIVE", "declared": [], "inconclusive": None}
    assert read_result(tmp_path, inc, "3")["status"] == "error"


def test_action_run_inconclusive_counts_must_match_its_checks(tmp_path):
    from test_acceptance_041 import _check, _read_result
    inc = {"schema": "netdryrun.report/v1", "status": "inconclusive", "summary": {"passed": 1, "failed": 1},
           "checks": [_check("a", True), _check("b", False)], "inconclusive_reason": "no BGP neighbors at all"}
    assert _read_result(tmp_path, inc, "3")["status"] == "inconclusive"
    for bad in ({**inc, "summary": {"passed": 1, "failed": 3}}, {**inc, "inconclusive_reason": ""}):
        assert _read_result(tmp_path, bad, "3")["status"] == "error", bad


def test_verify_a_changed_config_of_an_unobserved_node_is_refused(tmp_path):
    """The `unobserved` input is PR-controlled: marking the changed router unobserved can't hide its change (held
    since gauntlet 0.4 R2 by check_changed_binds; pinned here for the Action path)."""
    from netdryrun.verify import run as vrun
    t = tmp_path / "t.clab.yml"
    t.write_text("name: t\ntopology:\n  nodes:\n    r1: {kind: linux, image: quay.io/frrouting/frr:10.4.1, "
                 "binds: [r1/frr.conf:/etc/frr/frr.conf]}\n")
    with pytest.raises(vrun.VerifyInputError, match=r"r1/frr.conf \(/etc/frr/frr.conf on r1\)"):
        vrun.check_changed_binds(t, ["r1/frr.conf"], {"r1": ""})
