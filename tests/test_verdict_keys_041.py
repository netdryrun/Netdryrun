"""A key in device output that decides a verdict is present, proven absent, or unknown, and unknown is an error: never
read as empty, zero or false (Layer 6 round 2 on eaa323c, QUALITY-SYSTEM rule 1: the class closed mechanically, not
one instance at a time). The AST scan below fails on a defaulted read of a listed key in drivers/ and checks.py; every
entry of its allowlist says why that read is safe. The tests after it are the known instances, each failing on
eaa323c."""
import ast
import json
import textwrap
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
    "peerState", "session-state", "afi-safi", "addressFamilyInfo", "addPath", "best-route", "configuredpeers",
    "peerEntry", "neighborCapabilities", "sentPrefixCounter", "connectionsDropped", "lastResetDueTo",
    "lastErrorCodeSubcode", "lastResetTimerMsecs", "peerAddr", "filtered", "contribution", "segments", "list",
    "segment", "member", "string", "length", "valid-route", "invalid-reason", "local", "sourced", "overall", "scope"})
# every module that reads device output on the way to a verdict (Layer 6 round 3: verify/, faults.py and runner.py
# were never scanned)
SCANNED = sorted((SRC / "drivers").glob("*.py")) + sorted((SRC / "verify").glob("*.py")) + [
    SRC / "checks.py", SRC / "faults.py", SRC / "runner.py", SRC.parent.parent / "action.yml"]

# (file, key) -> why the read can't pass a check on a missing key. Each reason names what a reviewer checks: the
# capture that shows the device leaves the key out (and so what absence means), or that the value is netdryrun's own
# input, not device output.
PARAM = "a netdryrun.yml parameter of the check (p / c.params), validated by config, not device output"
ALLOWED = {
    ("checks.py", "communities"): PARAM,
    ("checks.py", "protocol"): PARAM,
    ("checks.py", "state"): PARAM,
    ("runner.py", "protocol"): PARAM,
    ("runner.py", "state"): PARAM,
    ("verify/intent.py", "state"): "an intent file parameter (`state:` of an appears_on line), validated by INTENT_KEYS "
                                   "before use, not device output",
    ("verify/report.py", "failed"): "netdryrun's own guards summary (r.guards, built by the guards run), rendered into "
                                    "the report; not device output",
    ("drivers/frr.py", "addressFamilyInfo"): "an established session without it is an error (default None); only a "
                                             "session that is down defaults to no families, and its counts are never "
                                             "judged (frr_v2_inject_linkdown_neighbors.txt, live: down, no families)",
    ("verify/frr.py", "addressFamilyInfo"): "parse_neighbors: as drivers/frr.py (an established session without it is "
                                            "an error). sent_counters: a family without a count is left out, and an "
                                            "empty advertised listing on it is then an error (FrrCollector). "
                                            "add_path_tx: no family list reads as every family carrying add-path",
    ("verify/frr.py", "neighborCapabilities"): "add_path_tx only: missing reads as add-path on every carried family "
                                               "(more paths assumed, never fewer); _add_path_rx refuses it on an "
                                               "established session",
    ("verify/frr.py", "addPath"): "add_path_tx only: as neighborCapabilities, missing is add-path, never 'one path'",
    ("drivers/frr.py", "bestpath"): "bgpd prints bestpath only on the best path (frr_bgp_paths captures): a path "
                                    "without it reads as not best, which only fails a best-path check",
    ("drivers/frr.py", "stale"): "bgpd prints `stale` only when set (json_object_boolean_true_add); present, it must be "
                                 "a boolean, so a malformed flag is an error, and absence is not stale",
    ("drivers/frr.py", "failed"): "zebra prints selected, installed and failed only when true (frr route captures); a "
                                  "route is present only when selected and installed are both true, so a missing "
                                  "failed flag can't make an uninstalled route present",
    ("checks.py", "active"): PARAM,
    ("action.yml", "failed"): "the Action reads netdryrun's own guards summary (rep['guards']), written by the guards "
                              "run, not device output",
    ("drivers/frr.py", "local"): "bgpd prints `local` and `sourced` only on the router's own paths (json boolean "
                                 "true); such a path also names peer 0.0.0.0, which is checked next, so a missing flag "
                                 "can't make an own path read as received",
    ("drivers/frr.py", "sourced"): "as `local`: printed only when true, and the peer address is checked as well",
    ("drivers/frr.py", "selected"): "zebra prints selected and installed only when true (frr route captures): a route "
                                    "without them is not forwarding, which only fails `present`",
    ("drivers/frr.py", "installed"): "as selected: zebra prints it only when true, so absent only fails `present`",
    ("drivers/frr.py", "overall"): "bgpd prints bestpath, with overall true inside it, only on the best path "
                                   "(frr_bgp_paths captures): absent reads as not best, which only fails a best-path "
                                   "check",
    ("drivers/frr.py", "scope"): "bgpd prints scope only on IPv6 next hops (global or link-local); an IPv4 next hop has "
                                 "none (frr_bgp_paths captures), so absent is global",
    ("verify/frr.py", "scope"): "as drivers/frr.py: absent on IPv4 next hops; any value but global or link-local is an "
                                "error",
    ("verify/frr.py", "bestpath"): "bgpd prints bestpath only on the best path; when present it is read strictly "
                                   "(_obj with its known keys, then _flag on overall)",
    ("drivers/srlinux.py", "oper-state"): "_counted_if_up raises on a counted family without oper-state the line "
                                          "before it reads it; families it doesn't count are skipped",
    ("drivers/srlinux.py", "as-path"): "an attr-set without as-path reads as None (unknown), never the empty path: "
                                       "as_path and as_path_regex on None are an error (checks.py); so does a "
                                       "container without segments (no capture shows an empty path); a malformed "
                                       "segment is an error",
    ("drivers/nxos.py", "ubest"): "NX-OS prints ubest only on the best path (nxos_route_default.txt, live): absent "
                                  "reads not active, which only fails `present`; `present: false` fails on any listed "
                                  "route",
    ("drivers/nxos.py", "configuredpeers"): "NX-OS leaves it out of a family without peers, printing only safi and "
                                            "af-name (nxos_summary_red_v6.txt, live); only that exact shape reads as "
                                            "0 peers, any other row without it is an error",
    ("drivers/nxos.py", "aspath"): "absent reads as None (unread), never the empty path: as_path and as_path_regex "
                                   "on None are an error (checks.py)",
    ("drivers/routeros_state.py", "active"): "RouterOS prints active only when true (routeros_routes_*.txt, live); the "
                                             "row's contribution must agree, so a missing flag on an active route is "
                                             "an error",
    ("drivers/routeros_state.py", "filtered"): "as active: printed only when true, and contribution must agree",
    ("drivers/routeros_state.py", "bgp.communities"): "RouterOS leaves it out of a path with none (live); "
                                                      "without_communities is refused on RouterOS for that reason",
    ("drivers/routeros_state.py", "bgp.large-communities"): "as bgp.communities: left out of a path with none, so "
                                                            "without_communities is refused on RouterOS",
    ("drivers/srlinux.py", "afi-safi"): "an established session without it is an error (default None); a down one has "
                                        "none",
    ("drivers/srlinux.py", "communities"): "YANG state leaves an empty container out: a path without communities has "
                                           "none (srl_attr_set_rejected.txt, live); a present container must hold a "
                                           "community or large-community list, else it is an error",
    ("drivers/junos.py", "rt-entry-state"): "only the brief `show route table` (ALL_ROUTES_CMD) reads it optionally: "
                                            "that listing never prints it (junos_route_table*.txt, live) and only "
                                            "record reads it, to propose checks; the extensive output requires it",
}


def _sources(f: Path) -> list[tuple[str, str]]:
    """(where, Python source) of a scanned file: a module, or each `python - <<'EOF'` block of action.yml."""
    text = f.read_text(encoding="utf-8")
    where = f.relative_to(SRC).as_posix() if SRC in f.parents else f.name
    if f.suffix != ".yml":
        return [(where, text)]
    out, lines = [], text.split("\n")
    for i, line in enumerate(lines):
        if line.strip() == "python - <<'EOF'":
            end = next(j for j in range(i + 1, len(lines)) if lines[j].strip() == "EOF")
            out.append((where, textwrap.dedent("\n".join(lines[i + 1:end]))))
    return out


def defaulted_reads(files=None) -> set[tuple[str, str]]:
    """(file, key) for every read of a verdict key that can stand in a value for a missing key: `x.get(K, default)`;
    `x.get(K)` in a truth test, followed by `or`, compared with True or False, or passed to str(); a `... if K in x
    else ...` ternary and `K in x and x[K]`; getattr(o, K, default); `dict.get(x, K, default)`; x.setdefault(K, ...)
    and x.pop(K, default); a subscript of K inside a try whose handler catches KeyError (or everything); and a helper
    called with K and required=False (Layer 6 rounds 3 and 4). K is a string literal or a module-level name bound to
    one. What it can't see (a key in a variable or a parameter, a value used later) is a known gap: the 0.4.2 router
    state contract moves every verdict key behind one strict accessor (QUALITY-SYSTEM.md, known gaps)."""
    out = set()
    for f in files if files is not None else SCANNED:
        for where, text in _sources(f):
            _scan(where, ast.parse(text), out)
    return out


def _scan(where: str, tree: ast.AST, out: set) -> None:
    names = {t.id: n.value.value for n in tree.body if isinstance(n, ast.Assign) and isinstance(n.value, ast.Constant)
             and isinstance(n.value.value, str) for t in n.targets if isinstance(t, ast.Name)}

    def key(node):
        v = node.value if isinstance(node, ast.Constant) else names.get(node.id) if isinstance(node, ast.Name) else None
        return v if isinstance(v, str) and v in VERDICT_KEYS else None

    def get_key(node, nargs):
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "get"
                and len(node.args) in nargs):
            return key(node.args[0])
        return None

    tests = []
    for n in ast.walk(tree):
        if isinstance(n, (ast.If, ast.While, ast.IfExp, ast.Assert)):
            tests.append(n.test)
        elif isinstance(n, ast.comprehension):
            tests += n.ifs
        elif isinstance(n, ast.UnaryOp) and isinstance(n.op, ast.Not):
            tests.append(n.operand)
        elif isinstance(n, ast.BoolOp):
            tests += n.values
        elif isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id in ("bool", "str") and n.args:
            tests.append(n.args[0])
        elif (isinstance(n, ast.Compare) and len(n.comparators) == 1 and isinstance(n.comparators[0], ast.Constant)
              and isinstance(n.comparators[0].value, bool)):
            tests.append(n.left)   # x.get(K) is True / == False
    for t in tests:
        k = get_key(t, (1,)) or (get_key(t, (2,)) if isinstance(t, ast.Call) and t.args and isinstance(t.args[-1], ast.Constant)
                                  and t.args[-1].value is None else None)
        if k:
            out.add((where, k))
    for n in ast.walk(tree):
        k = None
        if isinstance(n, ast.Call):
            k = get_key(n, (2,))
            if k and isinstance(n.args[1], ast.Constant) and n.args[1].value is None:
                k = None   # .get(K, None) is .get(K): flagged only where it stands in for a value (above)
            f_ = n.func
            if isinstance(f_, ast.Name) and f_.id == "getattr" and len(n.args) == 3:
                k = key(n.args[1])
            if isinstance(f_, ast.Attribute) and f_.attr == "setdefault" and n.args:
                k = key(n.args[0])
            if isinstance(f_, ast.Attribute) and f_.attr == "pop" and len(n.args) == 2:
                k = key(n.args[0])
            if (isinstance(f_, ast.Attribute) and f_.attr == "get" and isinstance(f_.value, ast.Name)
                    and f_.value.id == "dict" and len(n.args) == 3):
                k = key(n.args[1])
            if any(kw.arg == "required" and isinstance(kw.value, ast.Constant) and kw.value.value is False
                   for kw in n.keywords):
                k = next((key(a) for a in n.args if key(a)), None)
        elif isinstance(n, ast.IfExp) and isinstance(n.test, ast.Compare) and isinstance(n.test.ops[0], ast.In):
            k = key(n.test.left)
        elif isinstance(n, ast.BoolOp) and isinstance(n.op, ast.And):
            tested = {key(v.left) for v in n.values if isinstance(v, ast.Compare) and isinstance(v.ops[0], ast.In)}
            read = {key(s.slice) for v in n.values for s in ast.walk(v) if isinstance(s, ast.Subscript)}
            k = next(iter((tested & read) - {None}), None)   # K in x and x[K]
        elif isinstance(n, ast.Try) and any(_catches_keyerror(h) for h in n.handlers):
            for s in ast.walk(ast.Module(body=n.body, type_ignores=[])):
                if isinstance(s, ast.Subscript) and key(s.slice):
                    out.add((where, key(s.slice)))
        if k:
            out.add((where, k))


def _catches_keyerror(h: ast.ExceptHandler) -> bool:
    if h.type is None:
        return True   # a bare except
    types = h.type.elts if isinstance(h.type, ast.Tuple) else [h.type]
    return any(isinstance(t, ast.Name) and t.id in ("KeyError", "LookupError", "Exception", "BaseException")
               for t in types)


RED = {"stale", "active", "asPath", "communityList", "pfxRcd", "installed", "selected", "communities",
       "totalPrefixCounter", "rt-entry-state", "best-route", "suppressed", "pathstaled", "ubest", "pathbest",
       "valid-route", "pfxSnt", "largeCommunityList", "aspath", "session-state"}


def test_the_scan_flags_every_defaulted_form_in_the_red_fixture():
    """F7: one read per form; a form the scan stops seeing drops its key here."""
    assert {k for _f, k in defaulted_reads([Path(__file__).parent / "scan_red" / "defaulted_reads.txt"])} == RED


def test_every_allowlist_entry_gives_a_reason():
    assert all(isinstance(why, str) and len(why) > 40 for why in ALLOWED.values())


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
    with pytest.raises(DriverError, match="path without peerEntry|no peerAddr"):
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


def test_action_verify_no_change_needs_an_empty_diff_and_nothing_declared(tmp_path):
    """Layer 6 round 3 on 5e65852 (F8): no_change had no evidence rule; a report claiming it over a diff, or with an
    intent that declares lines, is no verdict."""
    from test_action_verify import read_result, verify_report
    from verify_helpers import base
    rep, _ = verify_report(tmp_path / "n", base().snap(), base().snap(), "intent: []\n")
    assert read_result(tmp_path, rep, "0")["status"] == "no_change"
    line = {"prefix": "10.101.0.0/24"}
    for bad in ({**rep, "diff_items": 3}, {**rep, "declared": [line]}, {**rep, "allowed": [line]},
                {**rep, "intent": {**rep["intent"], "lines": ["10.101.0.0/24 appears on edge1"]}}):
        assert read_result(tmp_path, bad, "0")["status"] == "error", bad


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


# --- Layer 6 round 3 on 5e65852: the reads the round-2 sweep missed, each failing on 5e65852 -----------------------

SRL_ATTR = json.dumps({"attr-id": 3, "as-path": {"segment": [{"type": "as-sequence", "member": [65020]}]},
                       "next-hop": "0.0.0.0", "origin": "igp"})


def test_srl_a_local_rib_row_without_origin_protocol_is_an_error_not_a_bgp_path():
    """F3: read as bgp, the router's own static became a BGP best path, and `as_path: ""` passed on it (RT-0026)."""
    with pytest.raises(DriverError, match="no origin-protocol"):
        srlinux.parse_attr_set(SRL_ATTR, {"prefix": "10.9.0.0/24", "best-route": True, "neighbor": "0.0.0.0"})
    with pytest.raises(DriverError, match="no origin-protocol"):
        srlinux.unread_path({"best-route": False, "neighbor": "10.0.0.2"})


def test_srl_a_local_rib_row_without_best_route_is_an_error_not_a_non_best_path():
    with pytest.raises(DriverError, match="no best-route"):
        srlinux.unread_path({"neighbor": "10.0.0.2", "origin-protocol": "bgp"})


def _nxos_summary(saf):
    return json.dumps({"result": {"body": {"TABLE_vrf": {"ROW_vrf": {"vrf-name-out": "default", "TABLE_af": {
        "ROW_af": {"af-id": 2, "TABLE_saf": {"ROW_saf": saf}}}}}}}})


def test_nxos_a_family_row_without_configuredpeers_is_an_error_unless_it_is_the_empty_shape():
    """F6: configuredpeers defaulted to 0, so the family's peers went unlisted and `exact: 0` passed. Only the live
    shape of a family without peers (safi and af-name, nxos_summary_red_v6.txt) reads as none."""
    peer = {"TABLE_neighbor": {"ROW_neighbor": {"neighborid": "10.0.1.2", "state": "Established", "prefixreceived": 3}}}
    for saf in ({"safi": 1, **peer}, {"safi": 1, "af-name": "IPv6 Unicast", "other": 1}):
        with pytest.raises(DriverError, match="no configuredpeers"):
            nxos.parse_bgp_summary(_nxos_summary(saf), afi="ipv6-unicast")
    assert nxos.parse_bgp_summary(_nxos_summary({"safi": 1, "af-name": "IPv6 Unicast"}), afi="ipv6-unicast") == {}


def test_junos_an_extensive_entry_without_its_state_is_an_error():
    """The BGP best-path read took a missing rt-entry-state as no state: a Hidden or NotInstall route read active."""
    d = json.loads((FX / "junos_route_paths.txt").read_text(encoding="utf-8"))
    _strip(d, "rt-entry-state")
    with pytest.raises(DriverError, match="no 'rt-entry-state'"):
        junos.parse_bgp_paths(json.dumps(d), "10.20.0.0/24")


def test_routeros_an_active_flag_that_disagrees_with_the_contribution_is_an_error():
    """RouterOS prints active only when true (live): a missing flag on an active route read as inactive."""
    from netdryrun.drivers import routeros_state
    rows = json.loads((FX / "routeros_routes_main.txt").read_text(encoding="utf-8"))
    row = next(r for r in rows if r.get("contribution") == "active")
    del row["active"]
    with pytest.raises(DriverError, match="active flag None and contribution 'active' disagree"):
        routeros_state.parse_routing_routes(rows)


def test_frr_a_stale_flag_that_is_not_a_boolean_is_an_error():
    d = json.loads((FX / "frr_bgp_paths.txt").read_text(encoding="utf-8"))
    d["paths"][0]["stale"] = "yes"
    with pytest.raises(DriverError, match="stale: 'yes'"):
        frr.parse_bgp_paths(json.dumps(d), "192.168.20.0/24")


def _verify_neighbors(drop):
    from verify_helpers import fixture
    doc = json.loads(fixture("neighbors.txt"))
    nb = doc["default"]["10.0.2.2"]
    drop(nb)
    return json.dumps(doc)


@pytest.mark.parametrize("drop", [lambda nb: nb.pop("neighborCapabilities"),
                                  lambda nb: nb["neighborCapabilities"].pop("addPath"),
                                  lambda nb: nb["neighborCapabilities"]["addPath"].pop("ipv4Unicast")],
                         ids=["capabilities", "addPath", "family"])
def test_verify_an_established_session_without_its_add_path_rx_capability_is_an_error(drop):
    """F4: _add_path_rx read a missing capability as "one path", the opposite of add_path_tx."""
    from netdryrun.verify import frr as vfrr
    from netdryrun.verify.snapshot import SnapshotError

    def soft_and_drop(nb):
        nb["addressFamilyInfo"]["ipv4Unicast"]["inboundSoftConfigPermit"] = True
        drop(nb)
    with pytest.raises(SnapshotError, match="no add-path capability"):
        vfrr.parse_neighbors(_verify_neighbors(soft_and_drop))


def test_verify_an_empty_advertised_listing_without_a_sent_count_is_an_error():
    """F4: `sent.get(..., 0)` read a missing count as 0 sent, so an empty listing passed as "advertises nothing"."""
    from netdryrun.verify import frr as vfrr
    from test_verify_snapshot import FakeNode
    over = {vfrr.NEIGHBORS_CMD: _verify_neighbors(lambda nb: nb["addressFamilyInfo"]["ipv4Unicast"].pop(
                "sentPrefixCounter")),
            vfrr.adj_command("default", "ipv4", "10.0.2.2", "out"): "{}"}
    with pytest.raises(vfrr.CommandFailed, match="gives no sent-prefix count"):
        vfrr.FrrCollector("edge1", FakeNode(over)).collect()


def test_verify_unobserved_does_not_swallow_an_image_mark_mismatch():
    """F5: --unobserved read detect()'s mismatch error as "not FRR", so an FRR node whose image names another NOS was
    accepted unobserved. A host detection can't place is still accepted."""
    from netdryrun.verify import run as vrun

    class L:
        def __init__(self, nodes):
            self.nodes = nodes
    lab = L({"r1": Node("r1", "c1", "linux", "quay.io/frrouting/frr:10.4.1"),
             "r2": Node("r2", "c2", "linux", "registry.local/frr-nexus-peer:10.4.1")})
    with pytest.raises(vrun.VerifyInputError, match="--unobserved r2: .*looks like nxos, not frr"):
        vrun.classify_nodes(lab, {}, ["r2"])
    host = L({"r1": Node("r1", "c1", "linux", "quay.io/frrouting/frr:10.4.1"), "h1": Node("h1", "c2", "linux", "alpine:3")})
    assert vrun.classify_nodes(host, {}, ["h1"]) == {"r1": "frr", "h1": ""}


def test_verify_a_set_driver_is_checked_against_the_node():
    """F5: an srlinux override on an FRR node was trusted, so --unobserved accepted an FRR node as SR Linux."""
    from netdryrun.verify import run as vrun

    class L:
        nodes = {"r2": Node("r2", "c2", "linux", "quay.io/frrouting/frr:10.4.1")}
    with pytest.raises(vrun.VerifyInputError, match="is set to driver srlinux, but its kind and image say frr"):
        vrun.classify_nodes(L(), {"r2": "srlinux"}, ["r2"])


# --- Layer 6 round 4 on bf29e89: parser instances of the missing-key class, each failing on bf29e89 ---------------

def _frr_best(change):
    d = json.loads((FX / "frr_bgp_paths_noexport.txt").read_text(encoding="utf-8"))
    change(next(p for p in d["paths"] if (p.get("bestpath") or {}).get("overall")))
    return json.dumps(d), d["prefix"]


@pytest.mark.parametrize("key", ["community", "largeCommunity"])
def test_frr_a_community_object_without_its_string_is_an_error(key):
    """F4: read as no communities, so `without_communities` passed."""
    text, prefix = _frr_best(lambda p: p.update({key: {"list": ["65020:300"]}}))
    with pytest.raises(DriverError, match=f"{key} without its string"):
        frr.parse_bgp_paths(text, prefix)


@pytest.mark.parametrize("change,detail", [
    (lambda p: p["aspath"].update(segments=[{"type": "as-sequence"}]), "aspath segment without its type or list"),
    (lambda p: p["aspath"].update(length=3), "aspath length 3, but its segments count 1 hops"),
    (lambda p: p["aspath"].pop("length"), "aspath length None"),
], ids=["no-list", "length", "no-length"])
def test_frr_an_aspath_segment_without_its_list_or_a_wrong_length_is_an_error(change, detail):
    """F5: a segment without its list read as no ASNs, so `as_path: ""` passed on a path that had some."""
    text, prefix = _frr_best(change)
    with pytest.raises(DriverError, match=detail):
        frr.parse_bgp_paths(text, prefix)


def _srl_attr(**change):
    a = json.loads((FX / "srl_attr_set_best.txt").read_text(encoding="utf-8"))
    a.update(change)
    return json.dumps(a)


SRL_ROW = {"best-route": True, "neighbor": "10.2.1.2", "origin-protocol": "bgp"}


@pytest.mark.parametrize("as_path,detail", [
    ({"segment": [{"type": "as-sequence"}]}, "as-path segment without its type or members"),
    ({"segment": [{"type": "as-sequence", "member": []}]}, "as-path segment without its type or members"),
    ({"segment": "65020"}, "as-path without its segment list"),
    ({"segments": []}, "as-path: "),
], ids=["no-member", "empty-member", "not-a-list", "unknown-key"])
def test_srl_a_malformed_as_path_is_an_error(as_path, detail):
    """Round 4 (F6) and round 5 (F4): a segment without members, or with an empty member list, read as the empty
    path, which `as_path: ""` matched."""
    with pytest.raises(DriverError, match=detail):
        srlinux.parse_attr_set(_srl_attr(**{"as-path": as_path}), SRL_ROW)


@pytest.mark.parametrize("as_path", [{}, {"segment": []}], ids=["no-segments", "empty-segment-list"])
def test_srl_an_as_path_without_segments_is_unknown_and_an_as_path_check_errors(as_path):
    """No capture shows how SR Linux prints an empty AS path: unknown, never the empty path, so `as_path: ""` and
    `as_path_regex: "^$"` are an error, while the path's other attributes stay readable."""
    bp = srlinux.parse_attr_set(_srl_attr(**{"as-path": as_path}), SRL_ROW)
    assert bp.as_path is None
    for p in ({"prefix": "192.168.22.0/24", "as_path": ""}, {"prefix": "192.168.22.0/24", "as_path_regex": "^$"}):
        passed, detail, _ = checks._bgp_route(_Paths([bp]), p)
        assert passed is False and isinstance(detail, Unready)


@pytest.mark.parametrize("comms", [{}, {"community": "65020:100"}, {"community-member": ["65020:100"]},
                                   {"community": ["65020:100"], "extended": ["target:1:1"]}],
                         ids=["empty", "string", "other-key", "extra-key"])
def test_srl_a_communities_container_without_a_known_list_is_an_error(comms):
    """Round 5 (F3): `a.get("communities") or {}` then `.get("community")` read these as no communities, so
    `without_communities` passed."""
    with pytest.raises(DriverError, match="communities without a community list"):
        srlinux.parse_attr_set(_srl_attr(communities=comms), SRL_ROW)


def test_the_scan_reads_the_python_in_action_yml():
    """F7: the Action's embedded Python reads report keys too; the scan sees each `python - <<'EOF'` block."""
    blocks = _sources(SRC.parent.parent / "action.yml")
    assert len(blocks) >= 4 and all(where == "action.yml" for where, _ in blocks)
    assert all(ast.parse(text) for _, text in blocks)
