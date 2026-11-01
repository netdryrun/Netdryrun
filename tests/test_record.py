from pathlib import Path

from netdryrun.record import render


def test_render_has_review_header_and_warnings():
    text = render({"lab": "topology.clab.yml", "timeout": 120, "checks": [{"type": "bgp_session", "node": "r1", "neighbor": "10.0.0.2"}]},
                  ["r2: BGP neighbor 10.0.0.9 is active; not recorded"])
    assert text.startswith("# Recorded by netdryrun")
    assert "# warning: r2" in text
    assert "neighbor: 10.0.0.2" in text


def test_attribute_check_pins_best_path():
    from netdryrun.drivers.base import BgpPath, Observation
    from netdryrun.record import _attribute_check

    class Drv:
        def bgp_paths(self, prefix, vrf="default"):
            return Observation([
                BgpPath(best=False, as_path="65020 65020", next_hop="10.0.0.6", local_pref=100, med=10),
                BgpPath(best=True, as_path="65020", next_hop="10.0.0.2", local_pref=200, med=50,
                        communities=["65020:100", "65535:65281"], large_communities=["65020:1:1"]),
            ], [])

    c = _attribute_check(Drv(), "r1", "192.168.20.0/24")
    assert c == {"type": "bgp_route", "node": "r1", "prefix": "192.168.20.0/24", "as_path": "65020",
                 "local_pref": 200, "communities": ["65020:100", "no-export", "65020:1:1"]}


# ------------------------------------------------------------------------- 0.3.3 (c): ranges, truncation, guards

import ipaddress  # noqa: E402

import pytest  # noqa: E402

from netdryrun import record as rec  # noqa: E402
from netdryrun.drivers.base import BgpNeighbor, Observation, Route  # noqa: E402
from netdryrun.lab import Node  # noqa: E402


class FakeLab:
    def __init__(self, topology, addresses=None, links=None):
        self.nodes = {n: Node(n, f"clab-t-{n}", "linux", "frr") for n in ("r1", "r2")}
        self.links = links if links is not None else [(("r1", "eth1"), ("r2", "eth1"))]
        self.addresses = addresses or {("r1", "eth1"): ["10.0.12.1/30"], ("r2", "eth1"): ["10.0.12.2/30"]}

    def interface_addresses(self, node, iface):
        return [ipaddress.ip_interface(a) for a in self.addresses.get((node, iface), [])]


class FakeDrv:
    name = "frr"

    def __init__(self, counts, routes4=(), routes6=(), received=()):
        self.counts, self.table, self.received = counts, {4: list(routes4), 6: list(routes6)}, set(received)

    def vrfs(self):   # the default VRF only (VRFs: tests/test_record_vrfs.py)
        return Observation([], [])

    def bgp_neighbors(self, vrf="default"):
        return Observation({a: BgpNeighbor(a, "established", pfx) for a, pfx in self.counts.items()}, [])

    def all_routes(self, vrf="default", family=4):
        return Observation([Route(p, "bgp", True) for p in self.table[family]], [])

    def routes(self, prefix, vrf="default"):
        table = self.table[6 if ":" in prefix else 4]
        return Observation([Route(prefix, "bgp", prefix in table)] if prefix in table or prefix in self.received
                           else [], [{"cmd": "show route"}])


def run_record(monkeypatch, drivers, lab=None, **kw):
    lab = lab or FakeLab(None)
    monkeypatch.setattr(rec, "Lab", lambda topology: lab)
    monkeypatch.setattr(rec, "detect", lambda node: "frr")
    monkeypatch.setattr(rec, "for_node", lambda lab_, name: drivers[name])
    return rec.record(Path("t.clab.yml"), **kw)


def prefixes(data, node="r1"):
    return [c for c in data["checks"] if c["type"] == "bgp_prefixes" and c["node"] == node]


def test_prefix_counts_are_ranges_by_default(monkeypatch):
    drivers = {"r1": FakeDrv({"10.0.12.2": {"ipv4-unicast": 4}, "10.0.13.2": {"ipv4-unicast": 20, "ipv6-unicast": 0}}),
               "r2": FakeDrv({})}
    data, _ = run_record(monkeypatch, drivers)
    got = {(c["neighbor"], c["afi"]): {k: c[k] for k in ("min", "max", "exact") if k in c} for c in prefixes(data)}
    assert got == {("10.0.12.2", "ipv4-unicast"): {"min": 4, "max": 6},     # +max(2, 20%)
                   ("10.0.13.2", "ipv4-unicast"): {"min": 20, "max": 24},
                   ("10.0.13.2", "ipv6-unicast"): {"exact": 0}}               # min: 0 is refused; nothing stays nothing


@pytest.mark.parametrize("mode,want", [("exact", {"exact": 4}), ("min", {"min": 4})])
def test_exact_and_min_prefixes_stay_available(monkeypatch, mode, want):
    drivers = {"r1": FakeDrv({"10.0.12.2": {"ipv4-unicast": 4}}), "r2": FakeDrv({})}
    data, _ = run_record(monkeypatch, drivers, prefix_mode=mode)
    c = prefixes(data)[0]
    assert {k: c[k] for k in ("min", "max", "exact") if k in c} == want


def test_every_recorded_range_loads(monkeypatch, tmp_path):
    from netdryrun.config import load
    drivers = {"r1": FakeDrv({"10.0.12.2": {"ipv4-unicast": 0}, "10.0.13.2": {"ipv4-unicast": 7}}),
               "r2": FakeDrv({})}
    data, warnings = run_record(monkeypatch, drivers, guards=True)
    (tmp_path / "topology.clab.yml").write_text("name: t\ntopology:\n  nodes:\n    r1: {kind: linux, image: frr}\n    r2: {kind: linux, image: frr}\n")
    data["lab"] = "topology.clab.yml"
    (tmp_path / "netdryrun.yml").write_text(rec.render(data, warnings))
    assert load(tmp_path / "netdryrun.yml").checks


def test_truncation_is_loud(monkeypatch):
    many = [f"10.{i // 250}.{i % 250}.0/24" for i in range(rec.MAX_ROUTES_PER_NODE + 10)]
    drivers = {"r1": FakeDrv({"10.0.12.2": {"ipv4-unicast": 60}}, routes4=many), "r2": FakeDrv({})}
    data, warnings = run_record(monkeypatch, drivers)
    assert any(w.startswith("INCOMPLETE BASELINE") and "r1" in w and "60" in w for w in warnings)
    text = rec.render(data, warnings)
    head = text.splitlines()
    assert head[0].startswith("# INCOMPLETE BASELINE"), head[:3]   # first line of the file, before anything else


def guards(data, node="r1"):
    return sorted(c["prefix"] for c in data["checks"]
                  if c["type"] == "route" and c["node"] == node and c.get("present") is False)


def test_guards_add_no_default_route_and_no_link_subnets(monkeypatch):
    drivers = {"r1": FakeDrv({"10.0.12.2": {"ipv4-unicast": 2}}, routes4=["192.168.2.0/24"]),
               "r2": FakeDrv({"10.0.12.1": {"ipv4-unicast": 1}, "fd00::1": {"ipv6-unicast": 1}},
                             routes4=["192.168.1.0/24"], routes6=["fd01::/64"])}
    data, _ = run_record(monkeypatch, drivers, guards=True)
    assert guards(data, "r1") == ["0.0.0.0/0", "10.0.12.0/30"]
    assert guards(data, "r2") == ["0.0.0.0/0", "10.0.12.0/30", "::/0"]   # IPv6 BGP on r2: ::/0 too
    for c in data["checks"]:
        if c.get("present") is False:
            assert c["protocol"] == "bgp"


def test_no_guard_against_what_the_network_does_today(monkeypatch):
    # r1 learns a default and the link subnet via BGP today: a guard against them would fail the baseline
    drivers = {"r1": FakeDrv({"10.0.12.2": {"ipv4-unicast": 2}}, routes4=["0.0.0.0/0", "10.0.12.0/30"]),
               "r2": FakeDrv({})}
    data, warnings = run_record(monkeypatch, drivers, guards=True)
    assert guards(data, "r1") == []
    assert any("r1" in w and "0.0.0.0/0" in w for w in warnings)


def test_an_unreadable_interface_is_a_warning_not_a_missing_guard(monkeypatch):
    # 0.3.3 cold review 5: interface_addresses raises LabError when it can't read them; that was swallowed
    from netdryrun.lab import LabError

    class Unreadable(FakeLab):
        def interface_addresses(self, node, iface):
            if node == "r2":
                raise LabError("could not read the addresses of r2 eth1")
            return super().interface_addresses(node, iface)
    drivers = {"r1": FakeDrv({"10.0.12.2": {"ipv4-unicast": 2}}), "r2": FakeDrv({})}
    data, warnings = run_record(monkeypatch, drivers, lab=Unreadable(None), guards=True)
    assert "10.0.12.0/30" in guards(data, "r1")        # r1's end was read
    assert any("r2" in w and "eth1" in w and "guard" in w for w in warnings)


def test_ipv6_over_ipv4_sessions_gets_the_ipv6_default_guard(monkeypatch):
    # 0.3.3 cold review 6: IPv6 unicast carried over IPv4 neighbors, no IPv6 BGP route today
    drivers = {"r1": FakeDrv({"10.0.12.2": {"ipv4-unicast": 2, "ipv6-unicast": 0}}), "r2": FakeDrv({})}
    data, _ = run_record(monkeypatch, drivers, guards=True)
    assert "::/0" in guards(data, "r1")


def test_guards_are_on_by_default_and_can_be_turned_off(monkeypatch):
    # 0.3.3 audit (Grok): with ranges by default, one leaked default route fits inside the prefix range;
    # the no-default-route guard is what catches it, so record writes the guards unless asked not to
    drivers = {"r1": FakeDrv({"10.0.12.2": {"ipv4-unicast": 2}}), "r2": FakeDrv({})}
    data, _ = run_record(monkeypatch, drivers)
    assert "0.0.0.0/0" in guards(data)
    data, _ = run_record(monkeypatch, drivers, guards=False)
    assert guards(data) == []


def test_a_failed_route_read_says_its_link_guards_are_missing(monkeypatch):
    from netdryrun.drivers import DriverError

    class NoRoutes(FakeDrv):
        def all_routes(self, vrf="default", family=4):
            raise DriverError("vtysh timed out")
    drivers = {"r1": NoRoutes({"10.0.12.2": {"ipv4-unicast": 2}}), "r2": FakeDrv({})}
    _, warnings = run_record(monkeypatch, drivers)
    assert any(w.startswith("INCOMPLETE BASELINE") and "r1" in w and "guard" in w for w in warnings)


def test_the_link_guard_cap_is_loud(monkeypatch):
    links = [((("r1", f"eth{i}")), ("r2", f"eth{i}")) for i in range(1, rec.MAX_LINK_GUARDS_PER_NODE + 3)]
    addrs = {(n, f"eth{i}"): [f"10.{i}.0.{1 if n == 'r1' else 2}/30"] for i in range(1, 30) for n in ("r1", "r2")}
    drivers = {"r1": FakeDrv({"10.0.12.2": {"ipv4-unicast": 2}}), "r2": FakeDrv({})}
    _, warnings = run_record(monkeypatch, drivers, lab=FakeLab(None, addresses=addrs, links=links))
    assert any(w.startswith("INCOMPLETE BASELINE") and "link subnets" in w for w in warnings)



def test_never_a_guard_the_recording_lab_already_fails(monkeypatch):
    # an edge router that receives a default from upstream without selecting it: the routing table doesn't
    # list it, but the guard (route present: false via bgp) fails on a received route too. No guard for it,
    # and the file says why in a comment.
    drivers = {"r1": FakeDrv({"10.0.12.2": {"ipv4-unicast": 3}}, routes4=["192.168.2.0/24"], received=["0.0.0.0/0"]),
               "r2": FakeDrv({})}
    data, warnings = run_record(monkeypatch, drivers)
    assert "0.0.0.0/0" not in guards(data, "r1") and "10.0.12.0/30" in guards(data, "r1")
    text = rec.render(data, warnings)
    assert any(line.startswith("# warning: r1") and "0.0.0.0/0" in line and "baseline" in line
               for line in text.splitlines())


def test_every_guard_written_passes_on_the_recording_lab(monkeypatch):
    from netdryrun.checks import _evaluate
    from netdryrun.config import Check
    drivers = {"r1": FakeDrv({"10.0.12.2": {"ipv4-unicast": 2}, "fd00::2": {"ipv6-unicast": 1}}, routes6=["fd01::/64"],
                             received=["::/0"]),
               "r2": FakeDrv({"10.0.12.1": {"ipv4-unicast": 1}})}
    data, _ = run_record(monkeypatch, drivers)
    for c in (c for c in data["checks"] if c.get("present") is False):
        params = {k: v for k, v in c.items() if k != "type"}
        ok, detail, _ = _evaluate(Check("route", params, "g", 30), drivers[c["node"]])
        assert ok, (c, detail)


def test_a_link_with_no_global_address_where_it_is_read_is_loud(monkeypatch):
    # 0.3.3 cross-platform review (Grok) #1, #2: SONiC keeps the link's address on EthernetN and SR Linux on e1-Y.0
    # in srbase-default; the topology's ethN answers with no global address. That was read as "unnumbered",
    # with no guard and no warning.
    addrs = {("r1", "eth1"): ["fe80::1/64"], ("r2", "eth1"): []}
    drivers = {"r1": FakeDrv({"10.0.12.2": {"ipv4-unicast": 2}}), "r2": FakeDrv({})}
    data, warnings = run_record(monkeypatch, drivers, lab=FakeLab(None, addresses=addrs))
    assert [g for g in guards(data, "r1") if g != "0.0.0.0/0"] == []
    assert any(w.startswith("INCOMPLETE BASELINE") and "eth1" in w and "address" in w for w in warnings)


def test_a_prefix_count_known_only_as_a_range_is_not_recorded():
    # Junos hid routes for a reason Netdryrun can't classify: the count is 1 to 3, so no exact or min is written
    from netdryrun.drivers.base import BgpNeighbor
    from netdryrun.record import _session_checks
    warnings: list[str] = []
    n = BgpNeighbor("10.0.100.2", "established", {"ipv4-unicast": 1}, {"ipv4-unicast": 3})
    checks = _session_checks("j1", {"10.0.100.2": n}, "exact", warnings)
    assert [c["type"] for c in checks] == ["bgp_session"]
    assert any("INCOMPLETE BASELINE" in w and "1 to 3" in w for w in warnings)
