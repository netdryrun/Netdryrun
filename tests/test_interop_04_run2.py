"""Regression tests from the 0.4 interop stress test, run 2 on 3ca6145 (interop/results/RUN2.md).

Shapes captured live on 2026-10-31 in the L1 mixed-5 lab (SR Linux 26.7.2), lab addresses only.
"""
import json
from pathlib import Path

from netdryrun.checks import EVALUATORS
from netdryrun.drivers import srlinux
from netdryrun.lab import ExecResult

FIX = Path(__file__).parent / "fixtures"


def read(name: str) -> str:
    return (FIX / name).read_text()


# ---- MAJOR IOP-6: SR Linux keeps a route rejected by import policy in its local RIB (`invalid-reason:
# {rejected-route: true}`, valid-route false, best-route false), and the srlinux driver counts it as a received path.
# Live (overlay M07: s1's import policy rejects 192.168.6.0/24): the prefix count dropped (207 received, 206 active)
# and the best path was gone, but `bgp_route ... present: false` failed "unexpectedly in the BGP table". FRR and EOS
# don't keep such a route, and the Junos driver drops it ("rejected by import policy"), so the same import filter
# makes the leak guard pass on every other platform. The reference: a route an import policy rejected can never be
# used and does not count as received.

class _SrlRejectedLab:
    def exec(self, node, cmd, timeout=60, input=None):
        if "local-rib" in cmd[-1]:
            return ExecResult(cmd, 0, read("srl_rib_rejected.txt"), "")
        if "attr-set" in cmd[-1]:
            return ExecResult(cmd, 0, read("srl_attr_set_rejected.txt"), "")
        if "route-table" in cmd[-1]:
            return ExecResult(cmd, 0, "{\n}", "")
        return ExecResult(cmd, 0, json.dumps({"peer-address": "10.1.2.2", "local-preference": 100}), "")


def test_srl_route_rejected_by_import_policy_is_not_a_received_path():
    d = srlinux.SrlDriver(_SrlRejectedLab(), "s1")
    ok, detail, _ = EVALUATORS["bgp_route"](d, {"node": "s1", "prefix": "192.168.6.0/24", "present": False})
    assert ok, detail


def test_srl_route_rejected_by_import_policy_is_absent_from_route_checks():
    assert srlinux.parse_routes("{\n}", "192.168.6.0/24", read("srl_rib_rejected.txt")) == []


# ---- MAJOR IOP-7: the Junos prefix count leaves out a received route whose next hop is unusable.
# Live (overlay M09: f1 sends 192.168.6.0/24 with third-party next hop 10.99.99.99): Junos hides it ("Protocol
# nexthop is not on the interface") and reports received 206, accepted 205; the junos driver reads
# accepted-prefix-count, so `bgp_prefixes exact: 206` fails on Junos while SR Linux, EOS and FRR keep the route in
# their counts. The reference: accepted = received minus rejected by import policy (nothing was rejected here).

def test_junos_count_keeps_a_received_route_with_an_unusable_next_hop():
    from netdryrun.drivers import junos
    n = junos.parse_bgp_neighbors(read("junos_bgp_neighbor_hidden_nexthop.txt"))["10.1.1.2"]
    assert n.prefixes["ipv4-unicast"] == 206


# IOP-6 false-pass path (coordinator's question, run 2): `route ... active: false` accepts "in the table but not
# selected". On the captured shape it passes on s1 for a route s1's import policy rejected; on FRR and EOS the same
# config leaves no path and the check fails. A route rejected by import policy is not received (reference).

def test_srl_route_rejected_by_import_policy_does_not_satisfy_active_false():
    d = srlinux.SrlDriver(_SrlRejectedLab(), "s1")
    ok, detail, _ = EVALUATORS["route"](d, {"node": "s1", "prefix": "192.168.6.0/24", "protocol": "bgp",
                                             "active": False})
    assert not ok, detail


# IOP-7 false-pass path: with the Junos undercount, an upper bound passes where the reference count fails it.

def test_junos_undercount_does_not_pass_an_upper_bound_the_reference_count_breaks():
    from netdryrun.drivers import junos
    from netdryrun.lab import ExecResult

    class Lab:
        def exec(self, node, cmd, timeout=60, input=None):
            return ExecResult(cmd, 0, read("junos_bgp_neighbor_hidden_nexthop.txt"), "")

    ok, detail, _ = EVALUATORS["bgp_prefixes"](junos.JunosDriver(Lab(), "j1"),
                                               {"node": "j1", "neighbor": "10.1.1.2", "max": 205})
    assert not ok, detail
