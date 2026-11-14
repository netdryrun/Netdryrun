"""Oracle FP-042-NXOSHIST (angle-5 red team on 82fb052, A-RT-0073, with A-RT-0077): a withdrawn NX-OS BGP path read as
received.

NX-OS lists every BGP path with `pathhistory` and `pathdeleted` flags. With `dampening`, a path the peer withdrew stays
in `show bgp ipv4 unicast <prefix> vrf <vrf>` as a history entry ("h" in the text view): `pathhistory: "true"`, not
valid, not best. The 0.4.2 NX-OS driver reads only `pathstaled`; `_learned` ignores `pathvalid`, `pathhistory` and
`pathdeleted`, and `parse_routes` adds `Route(prefix, "bgp", False)` for any learned path the routing table doesn't
use. So `route 0.0.0.0/0 protocol bgp active: false` passes ("present via bgp (not selected)") with nothing received.
The FRR form of the same bug was confirmed live (oracle FP-042-FRRDAMP, RT-0070); config.md's "a dampening history
entry, or a path being removed, is no path, from 0.4.2" names FRR and SONiC only, and no NX-OS limit is documented.

Device output. Nothing here was captured for this exact case: both answers are DERIVED in this file (`derived`) from
live NX-OS 10.4(8) captures (vrnetlab/cisco_n9kv:9300-10.4.8.M, 2026-10-28, tests/fixtures/nxos_captures.tsv), because
SOURCES.yml has no kind for a derived file:
- `show bgp ipv4 unicast 0.0.0.0/0 vrf default` is tests/fixtures/nxos_bgp_default.txt (n1's default from 10.0.1.2,
  AS 65002, valid and best) with the one path's flags set to the withdrawn state: `pathhistory: "true"` (A-RT-0073)
  or `pathdeleted: "true"` (A-RT-0077), `pathvalid` and `pathbest` "false", the prefix's `bestpathnr` "0" and nothing
  advertised (`on-xmitlist` "false", no TABLE_advertisedto), as the red team's candidates have it;
- `show ip route 0.0.0.0/0 vrf default` is tests/fixtures/nxos_route_default.txt with its bgp-65001 path removed (the
  peer withdrew the route, so BGP no longer offers it to the URIB): only n1's static Null0 default is left.
The A-RT-0077 state (`pathdeleted`) is transient on NX-OS and was judged "not proven" as a false pass under the
two-sample rule; it is here because the same fix covers it and a deleted path is no received path either.

The rule: a history or deleted path is a withdrawn route, not a received one. On the derived answers `route 0.0.0.0/0
protocol bgp active: false` must not pass (failing, or refused as unreadable, both satisfy the oracle).
"""
import copy
import json
from pathlib import Path

from netdryrun.checks import run_check
from netdryrun.config import _validate_check
from netdryrun.drivers.nxos import NxosDriver
from netdryrun.lab import ExecResult

FX = Path(__file__).resolve().parents[2] / "fixtures"
PREFIX = "0.0.0.0/0"
ROUTE_CMD = f"show ip route {PREFIX} vrf default"
BGP_CMD = f"show bgp ipv4 unicast {PREFIX} vrf default"


def fx(name: str) -> str:
    return (FX / name).read_text(encoding="utf-8")


def _prefix_row(bgp: dict) -> dict:
    return (bgp["result"]["body"]["TABLE_vrf"]["ROW_vrf"]["TABLE_afi"]["ROW_afi"]["TABLE_safi"]["ROW_safi"]
            ["TABLE_rd"]["ROW_rd"]["TABLE_prefix"]["ROW_prefix"])


def derived(flag: str) -> dict[str, str]:
    """n1's answers after 10.0.1.2 withdrew the default, with the path kept under `flag` (pathhistory or pathdeleted)."""
    bgp = json.loads(fx("nxos_bgp_default.txt"))
    row = _prefix_row(bgp)
    path = row["TABLE_path"]["ROW_path"]
    assert path["pathvalid"] == "true" and path["pathbest"] == "true" and path[flag] == "false"   # as captured
    path.update({flag: "true", "pathvalid": "false", "pathbest": "false"})
    row.update({"bestpathnr": "0", "on-xmitlist": "false"})
    del row["TABLE_advertisedto"]
    rib = json.loads(fx("nxos_route_default.txt"))
    rows = (rib["result"]["body"]["TABLE_vrf"]["ROW_vrf"]["TABLE_addrf"]["ROW_addrf"]["TABLE_prefix"]["ROW_prefix"]
            ["TABLE_path"])
    assert [p["clientname"] for p in rows["ROW_path"]] == ["static", "bgp-65001"]   # as captured
    rows["ROW_path"] = copy.deepcopy(rows["ROW_path"][0])   # NX-OS prints a single row as an object
    return {ROUTE_CMD: json.dumps(rib, indent="\t"), BGP_CMD: json.dumps(bgp, indent="\t")}


def captured() -> dict[str, str]:
    return {ROUTE_CMD: fx("nxos_route_default.txt"), BGP_CMD: fx("nxos_bgp_default.txt")}


class NxapiLab:
    """n1 answering NX-API requests (the command is the 5th argument of the driver's docker exec) from `answers`.
    A command not in it fails (rc 1): the oracle knows nothing else n1 would have said."""

    def __init__(self, answers: dict[str, str]):
        self.answers = answers

    def exec(self, node, cmd, timeout=60, input=None):
        if node == "n1" and len(cmd) == 6 and cmd[:2] == ["python3", "-c"] and cmd[4] in self.answers:
            return ExecResult(cmd, 0, self.answers[cmd[4]], "")
        return ExecResult(cmd, 1, "", f"not captured: {' '.join(cmd[3:5])}")


class Clock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t

    def sleep(self, s):
        self.t += max(s, 0.5)


def route_check(answers: dict[str, str], **raw):
    c = Clock()
    check = _validate_check(0, {"node": "n1", "type": "route", "prefix": PREFIX, **raw}, 20)
    return run_check(check, NxosDriver(NxapiLab(answers), "n1"), clock=c, sleep=c.sleep)


def test_active_false_does_not_pass_on_a_history_path():
    r = route_check(derived("pathhistory"), protocol="bgp", active=False)
    assert not r.passed, (f"`route {PREFIX} protocol bgp active: false` passed on a dampening history path "
                          f"(pathhistory true, not valid, not best: a route 10.0.1.2 withdrew): {r.detail}")


def test_active_false_does_not_pass_on_a_deleted_path():
    r = route_check(derived("pathdeleted"), protocol="bgp", active=False)
    assert not r.passed, (f"`route {PREFIX} protocol bgp active: false` passed on a path NX-OS is deleting "
                          f"(pathdeleted true, not valid, not best): {r.detail}")
