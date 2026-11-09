"""Oracle FP-042-CAPMSG: `record.baseline_gaps` drops any INCOMPLETE BASELINE line containing "only the first".

`baseline_gaps` decides `record`'s exit code: every INCOMPLETE BASELINE line is a gap (exit 1), except the two size caps
of the format (MAX_ROUTES_PER_NODE routes, MAX_LINK_GUARDS_PER_NODE link guards: "... only the first N ..."). 0.4.2
(e6522db) tells them apart by the substring "only the first" anywhere in the line. Many gap lines quote the device's
own text (a read that failed carries its last output line), so device text that happens to contain those words erases
a real gap: `record` exits 0 on a node whose BGP state it couldn't read.

The rule: only the two cap messages `record` itself writes are not gaps. Every other INCOMPLETE BASELINE line is one,
whatever text it quotes.

The test goes through `record.record` with the real FRR driver on one node whose `show bgp neighbors json` read
fails, rc 1, with a line of text containing "only the first". That answer is constructed: no capture has FRR print
those words. The failure path it takes (the driver's error carries the device's last line, and record quotes it in its
gap line) is the real one.

The tests here fail on the parent. The guards, which pass before and after the fix, are in
tests/test_oracle_guards_fp_042_capmsg.py (listed in ORACLE.yml `evidence:`).
"""
from pathlib import Path

from netdryrun import record as rec
from netdryrun.drivers.base import Observation
from netdryrun.drivers.frr import FrrDriver
from netdryrun.lab import ExecResult, Node

FX = Path(__file__).resolve().parents[2] / "fixtures"
DEVICE_TEXT = "% Unknown command: only the first 3 words were read"


class OneNodeLab:
    """r1 (FRR) and, when asked, `links` point-to-point links to bridges, each with its own /24 on r1."""

    def __init__(self, answers: dict, links: int = 0):
        self.answers = answers
        self.nodes = {"r1": Node("r1", "clab-x-r1", "linux", "quay.io/frrouting/frr:10.4.1")}
        self.links = []
        for i in range(1, links + 1):
            self.nodes[f"br{i}"] = Node(f"br{i}", f"clab-x-br{i}", "bridge", "")
            self.links.append((("r1", f"eth{i}"), (f"br{i}", "p1")))
            self.answers[f"ip -o addr show dev eth{i}"] = ExecResult(
                [], 0, f"{i + 1}: eth{i}    inet 10.{i}.0.1/24 scope global eth{i}\\       valid_lft forever\n", "")

    def exec(self, node, cmd, timeout=60, input=None):
        a = self.answers.get(" ".join(cmd))
        return ExecResult(list(cmd), a.rc, a.stdout, a.stderr) if a else ExecResult(list(cmd), 1, "", "not captured")

    def interface_addresses(self, node, interface):
        from netdryrun.lab import Lab
        return Lab.interface_addresses(self, node, interface)


class Driver(FrrDriver):
    def __init__(self, lab, node, routes=()):
        super().__init__(lab, node)
        self._routes = list(routes)

    def vrfs(self):
        return Observation([], [])

    def all_routes(self, vrf="default", family=4):
        return Observation(self._routes if family == 4 else [], [])

    def routes(self, prefix, vrf="default"):
        return Observation([], [])


def record(monkeypatch, lab, guards=False, routes=()):
    drv = Driver(lab, "r1", routes)
    monkeypatch.setattr(rec, "Lab", lambda topology: lab)
    monkeypatch.setattr(rec, "detect", lambda node: "frr")
    monkeypatch.setattr(rec, "for_node", lambda lab_, name, *a: drv)
    return rec.record(Path("topology.clab.yml"), guards=guards, sleep=lambda s: None)


# ------------------------------------------------------------------ red on 0.4.2 (e6522db)

def test_device_text_never_erases_a_gap(monkeypatch):
    lab = OneNodeLab({"vtysh -c show bgp neighbors json": ExecResult([], 1, DEVICE_TEXT + "\n", "")})
    _, warnings = record(monkeypatch, lab)
    failed = [w for w in warnings if w.startswith("INCOMPLETE BASELINE") and DEVICE_TEXT in w]
    assert failed, f"no gap line quotes the failed read: {warnings}"
    gaps = rec.baseline_gaps(warnings)
    assert all(w in gaps for w in failed), f"a gap line was dropped for the device's words: {failed}; gaps {gaps}"
