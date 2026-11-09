"""Oracle FP-042-UNNUMBERED: a BGP-unnumbered link has no subnet to guard; `record` must say so by name, not exit 1.

What the routers showed (tests/fixtures/frr1021u_capture.txt, martimy/clab-bgp-frr @ ac5b96c, FRR 10.2.1):
- `ip -o addr show dev eth1` on leaf01 and on spine01 (the two ends of one fabric link) lists one address, an IPv6
  link-local (fe80::/64, scope link); leaf01 eth3, a LAN, lists 192.168.11.1/24 as well;
- `show bgp neighbors json` on each node has a session keyed by the interface name ("eth1"), Established, to the
  other end's link-local address: BGP unnumbered.

The rule (approved by the coordinator, 2026-11-09): "nothing to guard" only when the interface lists link-local
addresses only AND the node has a BGP session over that interface. Then `record` names it (the node, the interface
and "unnumbered") and it is no gap. Anything else stays an INCOMPLETE BASELINE gap that exits 1: an interface whose
addresses can't be read, one with no global address and no interface session, and one whose `ip` answer has an
address token that can't be read (a global address that exists must never read as "none").

Everything goes through `record.record` with the real `Lab.interface_addresses` and the real FRR driver's
`bgp_neighbors`, fed the captured answers; the reads the capture doesn't cover (routes, VRFs) answer "nothing".
"""
import json
import types
from pathlib import Path


from netdryrun import record as rec
from netdryrun.drivers import Undetectable
from netdryrun.drivers.base import Observation
from netdryrun.drivers.frr import FrrDriver
from netdryrun.lab import ExecResult, Lab, Node

FX = Path(__file__).resolve().parents[2] / "fixtures"


def fx(name: str) -> str:
    return (FX / name).read_text(encoding="utf-8")


def captured():
    out = {}
    for node in ("leaf01", "spine01"):
        for dev in ("eth1", "eth2", "eth3"):
            out[(node, f"ip -o addr show dev {dev}")] = fx(f"frr1021u_{node}_ip_o_addr_show_dev_{dev}.txt")
        out[(node, "vtysh -c show bgp neighbors json")] = fx(f"frr1021u_{node}_show_bgp_neighbors_json.txt")
    return out


class CapturedLab:
    """leaf01 and spine01 joined by their eth1 (the captured fabric link), and leaf01's LAN eth3 on a bridge."""

    def __init__(self, answers=None, links=None):
        self.answers = captured() if answers is None else answers
        self.nodes = {"leaf01": Node("leaf01", "clab-frr-leaf01", "linux", "quay.io/frrouting/frr:10.2.1"),
                      "spine01": Node("spine01", "clab-frr-spine01", "linux", "quay.io/frrouting/frr:10.2.1"),
                      "lan1": Node("lan1", "clab-frr-lan1", "bridge", "")}
        self.links = links if links is not None else [(("leaf01", "eth1"), ("spine01", "eth1")),
                                                      (("leaf01", "eth3"), ("lan1", "p1"))]
        self.interface_addresses = types.MethodType(Lab.interface_addresses, self)   # the real parser

    def exec(self, node, cmd, timeout=60, input=None):
        key = (node, " ".join(cmd))
        if key in self.answers:
            a = self.answers[key]
            return a if isinstance(a, ExecResult) else ExecResult(cmd, 0, a, "")
        return ExecResult(cmd, 1, "", f"not captured: {key}")


class Driver(FrrDriver):
    """The real FRR driver for the captured BGP neighbors; what wasn't captured answers "nothing"."""

    def vrfs(self):
        return Observation([], [])

    def all_routes(self, vrf="default", family=4):
        return Observation([], [])

    def routes(self, prefix, vrf="default"):
        return Observation([], [])


def run(monkeypatch, lab):
    def detect(node):
        if node.kind == "bridge":
            raise Undetectable("a bridge")
        return "frr"
    drivers = {n: Driver(lab, n) for n in ("leaf01", "spine01")}
    monkeypatch.setattr(rec, "Lab", lambda topology: lab)
    monkeypatch.setattr(rec, "detect", detect)
    monkeypatch.setattr(rec, "for_node", lambda lab_, name, *a: drivers[name])
    return rec.record(Path("topology.clab.yml"), guards=True)


def link_gaps(warnings, node, dev):
    return [w for w in rec.baseline_gaps(warnings) if node in w and dev in w]


def named(warnings):
    """The lines that say a link has nothing to guard: about a link's guard, calling it unnumbered, not a gap (the
    session line "BGP neighbor 'eth1' is not an IP address (unnumbered?)" is about the session, not the link)."""
    return [w for w in warnings if "unnumbered" in w.lower() and "guard" in w.lower()
            and not w.startswith("INCOMPLETE") and "BGP neighbor" not in w]


def guarded(data):
    return {(c["node"], c["prefix"]) for c in data["checks"] if c["type"] == "route" and c.get("present") is False}


# ------------------------------------------------------------------ red on 0.4.1

def test_unnumbered_fabric_link_is_named_not_a_gap(monkeypatch):
    data, warnings = run(monkeypatch, CapturedLab())
    for node in ("leaf01", "spine01"):
        assert link_gaps(warnings, node, "eth1") == [], warnings
        assert [w for w in named(warnings) if node in w and "eth1" in w], warnings
    assert rec.baseline_gaps(warnings) == [], warnings   # nothing else is missing: record exits 0


# ------------------------------------------------------------------ guards: pass before and after the fix

def test_the_numbered_lan_still_gets_its_guard(monkeypatch):
    data, _ = run(monkeypatch, CapturedLab())
    assert ("leaf01", "192.168.11.0/24") in guarded(data)
    assert ("spine01", "192.168.11.0/24") in guarded(data)


def test_link_local_only_without_an_interface_session_stays_a_gap(monkeypatch):
    """spine01 eth1 as captured (link-local only), but no BGP session over eth1: could be an address kept elsewhere
    (SONiC on EthernetN, SR Linux on e1-Y.0), so it stays a gap."""
    answers = captured()
    nbrs = json.loads(answers[("spine01", "vtysh -c show bgp neighbors json")])
    del nbrs["eth1"]
    answers[("spine01", "vtysh -c show bgp neighbors json")] = json.dumps(nbrs)
    _, warnings = run(monkeypatch, CapturedLab(answers))
    assert link_gaps(warnings, "spine01", "eth1"), warnings


def test_an_unreadable_interface_stays_a_gap(monkeypatch):
    answers = captured()
    answers[("leaf01", "ip -o addr show dev eth1")] = ExecResult([], 1, "", 'Device "eth1" does not exist.')
    _, warnings = run(monkeypatch, CapturedLab(answers))
    assert link_gaps(warnings, "leaf01", "eth1"), warnings


def test_an_unreadable_address_token_is_never_none(monkeypatch):
    """The captured eth1 answer plus a global address line whose address can't be read: a global address is there,
    so it must not read as "link-local only" (Lab.interface_addresses drops a token it can't parse)."""
    answers = captured()
    extra = "14: eth1    inet 192.168.300.1/31 scope global eth1\\       valid_lft forever preferred_lft forever\n"
    answers[("leaf01", "ip -o addr show dev eth1")] = answers[("leaf01", "ip -o addr show dev eth1")] + extra
    _, warnings = run(monkeypatch, CapturedLab(answers))
    assert link_gaps(warnings, "leaf01", "eth1"), warnings


def test_a_global_address_next_to_the_session_is_guarded(monkeypatch):
    """eth1 with its interface session and also a global /31: that subnet is guarded, not called unnumbered."""
    answers = captured()
    extra = "14: eth1    inet 10.0.0.0/31 scope global eth1\\       valid_lft forever preferred_lft forever\n"
    answers[("leaf01", "ip -o addr show dev eth1")] = answers[("leaf01", "ip -o addr show dev eth1")] + extra
    data, warnings = run(monkeypatch, CapturedLab(answers))
    assert ("leaf01", "10.0.0.0/31") in guarded(data)
    assert not [w for w in named(warnings) if "leaf01" in w and "eth1" in w], warnings
