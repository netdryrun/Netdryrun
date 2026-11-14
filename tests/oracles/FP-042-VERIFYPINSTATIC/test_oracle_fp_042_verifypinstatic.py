"""Oracle FP-042-VERIFYPINSTATIC (red team 042-GV, B-RT-0077): an `appears_on` line with BGP pins explains a static.

`verify` intent: "10.101.0.0/24 appears on edge1, installed, learned from 10.0.1.2 with AS path 65100" (`with: {from:
10.0.1.2, as_path: "65100"}`). The engine docstring says BGP attributes in `with:` explain "only the paths and received
routes that match them" (acceptance B-6), and `_pins_ok` says why a line fails when "the selected route is not a BGP
route, so BGP attributes can't match": the pins describe the route the node selects and installs. In 0.4.2
`RouteView.presence()` reads "installed" from any selected FIB entry, `_pins_ok` compares the BGP pins with the BGP
best path only (bgpd keeps its best path when zebra prefers a distance-1 static), and `_pinned_items` explains every
non-path item, the static RIB entry included. A change that also adds `ip route 10.101.0.0/24 10.0.3.2` on edge1 gets
INTENT MATCHED while edge1 forwards the prefix to 10.0.3.2 (eth3, peer1), not to 10.0.1.2.

Device output: derived, not captured. The snapshots come from the real FRR collector (`verify.frr.FrrCollector`) on
the live FRR 10.4.1 captures of edge1 in tests/fixtures/verify (unchanged for "before"). "After" is built in this file
from those captures, and marked derived here:
- `show bgp vrf all ipv4 unicast detail json`: 10.101.0.0/24 gets a copy of the captured 10.100.0.0/24 path (from
  10.0.1.2 = cust1, AS path 65100, bestpath.overall true, as bgpd shows it with a static winning in zebra);
- `show ip route vrf all json`: 10.101.0.0/24 gets two entries, shaped as the capture shows a prefix with two
  protocols (192.0.2.0/24): the bgp entry (distance 20, via 10.0.1.2 eth1) without selected/destSelected/installed,
  and a static entry (distance 1, via 10.0.3.2 eth3) selected and installed;
- running config: `ip route 10.101.0.0/24 10.0.3.2` after the captured `ip route` lines.
No other command's output changes. A live capture of this shape (FRR 10.4.1 with a static over a BGP route) is the
red team's containerlab recipe in candidates/B/RT-0077; the engine path is the same.

The rule: when the route edge1 selects and installs is not BGP, BGP pins can't be met by it, so the line is not met
(or the static entry stays undeclared): never INTENT MATCHED.
"""
import copy
import json
import re
from pathlib import Path

from netdryrun.verify import frr
from netdryrun.verify.engine import match
from netdryrun.verify.intent import parse_intent_text
from netdryrun.verify.snapshot import Snapshot

FIX = Path(__file__).resolve().parents[2] / "fixtures" / "verify"
LIVE = re.compile(r"# live capture: FRRouting 10\.4\.1_git, node edge1 of tests/fixtures/verify-lab, `vtysh -c '(.+)'`, "
                  r"\d{4}-\d\d-\d\d")
NEW = "10.101.0.0/24"
TEMPLATE = "10.100.0.0/24"   # the captured route from cust1 (10.0.1.2, AS 65100) the derived path is copied from
ROUTE_CMD = "show ip route vrf all json"
BGP_CMD = "show bgp vrf all ipv4 unicast detail json"
CONFIG_CMD = "show running-config"


def captures() -> dict[str, str]:
    """command -> the live capture's output (its header line checked and removed)."""
    out = {}
    for f in sorted(FIX.iterdir()):
        head, body = f.read_text(encoding="utf-8").split("\n", 1)
        m = LIVE.fullmatch(head)
        assert m, f"{f.name}: not a live capture of edge1"
        out[m.group(1)] = body
    return out


class FakeEdge1:
    """`vtysh -c <command>` on edge1, answered from the outputs given."""

    def __init__(self, outputs: dict[str, str]):
        self.outputs = outputs

    def __call__(self, node, argv):
        assert node == "edge1" and argv[:2] == ["vtysh", "-c"], argv
        if argv[2] not in self.outputs:
            raise AssertionError(f"unexpected command {argv[2]!r}")
        return 0, self.outputs[argv[2]], ""


def _config_key(outputs) -> str:
    keys = [k for k in outputs if k.startswith(CONFIG_CMD)]
    assert len(keys) == 1, keys
    return keys[0]


def after_outputs(static_hop=("10.0.3.2", "eth3")) -> dict[str, str]:
    """DERIVED edge1 output after the change (see the module docstring). static_hop None: no static at all (the
    BGP route alone is installed, as captured for 10.100.0.0/24)."""
    out = captures()
    bgp = json.loads(out[BGP_CMD])
    paths = copy.deepcopy(bgp["default"]["routes"][TEMPLATE])
    bgp["default"]["routes"][NEW] = paths
    bgp["default"]["totalRoutes"] += 1
    bgp["default"]["totalPaths"] += len(paths)
    out[BGP_CMD] = json.dumps(bgp)

    routes = json.loads(out[ROUTE_CMD])
    bgp_entry = copy.deepcopy(routes["default"][TEMPLATE][0])
    assert bgp_entry["protocol"] == "bgp" and bgp_entry["nexthops"][0]["ip"] == "10.0.1.2"
    bgp_entry.update(prefix=NEW)
    entries = [bgp_entry]
    if static_hop is not None:
        ip, iface = static_hop
        # the shape of the captured static entry for 198.18.200.0/24 (distance 1, selected, installed)
        static = copy.deepcopy(routes["default"]["198.18.200.0/24"][0])
        hop = copy.deepcopy(static["nexthops"][0])
        hop.update(ip=ip, interfaceName=iface, interfaceIndex=14659)
        static.update(prefix=NEW, nexthops=[hop], internalNextHopNum=1, internalNextHopActiveNum=1)
        # the bgp entry loses, shaped as the captured losing static of 192.0.2.0/24 (no selected/installed keys)
        for k in ("selected", "destSelected", "installed", "installedNexthopGroupId"):
            bgp_entry.pop(k, None)
        bgp_entry["internalStatus"] = 0
        entries.append(static)
    routes["default"][NEW] = entries
    out[ROUTE_CMD] = json.dumps(routes)

    if static_hop is not None:
        key = _config_key(out)
        anchor = "ip route 198.18.200.0/24 10.0.6.2\n"
        assert anchor in out[key]
        out[key] = out[key].replace(anchor, anchor + f"ip route {NEW} {static_hop[0]}\n", 1)
    return out


def snap(outputs) -> Snapshot:
    return Snapshot({"edge1": frr.FrrCollector("edge1", FakeEdge1(outputs)).collect()})


INTENT = f"""
intent:
  - prefix: {NEW}
    appears_on: [edge1]
    with: {{from: 10.0.1.2, as_path: "65100"}}
"""


def verify(after, text=INTENT):
    return match(snap(captures()), snap(after), parse_intent_text(text))


def test_bgp_pins_never_explain_a_static_route_that_edge1_installs():
    after = snap(after_outputs())
    rib = {k.protocol: v for k, v in after.items().items() if k.kind == "rib" and k.prefix == NEW}
    # the derived output reads as intended: the static is selected and in the FIB, the BGP entry is neither
    assert set(rib) == {"bgp", "static"}
    assert all(e.selected and e.fib for e in rib["static"]) and not any(e.selected or e.fib for e in rib["bgp"])
    m = verify(after_outputs())
    assert m.status != "matched", (
        f"INTENT MATCHED for `appears_on: edge1 with from 10.0.1.2, as_path 65100` while the route edge1 selects and "
        f"installs for {NEW} is a static via 10.0.3.2 (eth3), not the pinned BGP path: undeclared "
        f"{[d.key.where() for d in m.undeclared]}, untested config {m.untested}")
