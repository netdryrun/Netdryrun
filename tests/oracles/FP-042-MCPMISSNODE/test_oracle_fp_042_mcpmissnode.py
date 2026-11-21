"""Oracle FP-042-MCPMISSNODE (angle-5 red team on 82fb052, B-RT-0075): the MCP record_baseline tool names one gap signal
of two.

The `record_baseline` tool returns the recorded YAML and nothing else (no exit code, no gaps field). Its description
gives the agent one signal for a partial baseline: 'A first line starting "# INCOMPLETE BASELINE" means routes were left
out: say so to the human.' But `record.render` puts every gap line first, and a routing node with no recorded check
(an OSPF-only or static router that answers "no BGP instance", a cEOS still answering "BGP inactive", a VM still
booting) produces `BASELINE MISSES A NODE: ...` (record.MISSING_NODE), on which the CLI exits 1. When that is the only
gap, the YAML's first line is "# BASELINE MISSES A NODE", which the description doesn't name, so an agent following
the contract reads the baseline as complete. (The line is still in the file, which the description says to show the
human; no check passes falsely. A contract defect, Low-Medium.)

No device output is involved. The gaps come from the real `record.record()` on a fake two-node lab (the shape of
tests/test_record_missing_node.py): r1 answers "no BGP instance" (NoSuchInstance, what an OSPF-only FRR or a cEOS
before its BGP starts answers), r2 has one established eBGP session. A second run has r2's session down instead, the
INCOMPLETE BASELINE case. The tool description is read from the MCP server's tool list, offline.

The rule: every first line `record` can put before the header to mark a gap is named in the tool's description, or
the markers are unified under the one the description names.
"""
import asyncio
from pathlib import Path

from netdryrun import mcp_server
from netdryrun import record as rec
from netdryrun.drivers.base import BgpNeighbor, NoSuchInstance, Observation
from netdryrun.lab import Node


class TwoNodeLab:
    links: list = []

    def __init__(self, topology):
        self.nodes = {n: Node(n, f"clab-t-{n}", "linux", "quay.io/frrouting/frr:10.4.1") for n in ("r1", "r2")}


class Drv:
    name = "frr"
    reads_received = False
    unsupported_afis = frozenset()

    def __init__(self, bgp: str | None):
        self.bgp = bgp   # None: "no BGP instance"; else the state of its one session

    def vrfs(self):
        return Observation([], [])

    def bgp_neighbors(self, vrf="default"):
        if self.bgp is None:
            raise NoSuchInstance("no BGP instance (`show bgp neighbors json`: {})")
        return Observation({"10.0.12.1": BgpNeighbor("10.0.12.1", self.bgp, {"ipv4-unicast": 1}, external=False)}, [])

    def all_routes(self, vrf="default", family=4):
        return Observation([], [])

    def routes(self, prefix, vrf="default"):
        return Observation([], [{"cmd": "show ip route"}])


def record(monkeypatch, drivers: dict):
    monkeypatch.setattr(rec, "Lab", TwoNodeLab)
    monkeypatch.setattr(rec, "detect", lambda node: "frr")
    monkeypatch.setattr(rec, "for_node", lambda lab, name, *a: drivers[name])
    data, warnings = rec.record(Path("t.clab.yml"), guards=False, sleep=lambda s: None)
    return rec.render(data, warnings), warnings


def gap_marker(text: str) -> str | None:
    """The marker of the YAML's first line when it is a gap line (before the "# Recorded by" header), else None."""
    first = text.splitlines()[0]
    if first.startswith("# Recorded by"):
        return None
    return first.removeprefix("# ").split(":")[0].strip()


def description() -> str:
    tools = {t.name: " ".join(t.description.split()) for t in asyncio.run(mcp_server.mcp.list_tools())}
    return tools["record_baseline"]


def test_the_missing_node_first_line_is_named_in_the_tool_description(monkeypatch):
    text, warnings = record(monkeypatch, {"r1": Drv(None), "r2": Drv("established")})
    assert rec.baseline_gaps(warnings), "the CLI would exit 0: the lab no longer produces a gap"
    marker = gap_marker(text)
    assert marker, f"the YAML starts with no gap line though `record` exits 1: {text.splitlines()[0]!r}"
    desc = description()
    assert marker in desc, (
        f"the first line of the YAML is {text.splitlines()[0]!r}, but the record_baseline description names only "
        f"another signal: {desc[desc.find('first line') - 3:][:120]!r}")
