import json, sys
sys.path.insert(0, "tests")
from netdryrun.checks import EVALUATORS
from netdryrun.drivers import srlinux, junos
from test_interop_04_run2 import _SrlRejectedLab, read
d = srlinux.SrlDriver(_SrlRejectedLab(), "s1")
for params in ({"prefix": "192.168.6.0/24", "protocol": "bgp"},
               {"prefix": "192.168.6.0/24", "protocol": "bgp", "active": False},
               {"prefix": "192.168.6.0/24"}):
    ok, detail, _ = EVALUATORS["route"](d, {"node": "s1", **params})
    print("IOP-6 route", params, "->", ok, detail)
ok, detail, _ = EVALUATORS["bgp_route"](d, {"node": "s1", "prefix": "192.168.6.0/24"})
print("IOP-6 bgp_route best exists ->", ok, detail)
ok, detail, _ = EVALUATORS["bgp_route"](d, {"node": "s1", "prefix": "192.168.6.0/24", "as_path": "65005 65006"})
print("IOP-6 bgp_route as_path ->", ok, detail)
n = junos.parse_bgp_neighbors(read("junos_bgp_neighbor_hidden_nexthop.txt"))["10.1.1.2"]
print("IOP-7 junos count", n.prefixes["ipv4-unicast"], "(Junos received 206: reference count 206)")
class L:
    def exec(self, node, cmd, timeout=60, input=None):
        from netdryrun.lab import ExecResult
        return ExecResult(cmd, 0, read("junos_bgp_neighbor_hidden_nexthop.txt"), "")
jd = junos.JunosDriver(L(), "j1")
for p in ({"max": 205}, {"exact": 205}):
    ok, detail, _ = EVALUATORS["bgp_prefixes"](jd, {"node": "j1", "neighbor": "10.1.1.2", **p})
    print("IOP-7 bgp_prefixes", p, "->", ok, detail)
