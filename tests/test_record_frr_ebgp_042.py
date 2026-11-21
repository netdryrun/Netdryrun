"""The RT-S01 fix must not touch the stranger's README path on FRR: `record --attributes` on eBGP FRR paths still
writes a bgp_route check with the AS path and names no gap, so `record` exits 0 (exit 1 comes only from
record.baseline_gaps, cli.py). The paths are FRR's own captured answers: FRR 10.4.1 (frr_bgp_paths.txt) and FRR 10.2.1
from the stranger's martimy/clab-bgp-frr capture (frr1021_learned_prefix_*), both through the whole `record` flow."""
from pathlib import Path

import pytest
from test_record import FakeDrv, run_record

from netdryrun import record as rec
from netdryrun.drivers.base import Observation
from netdryrun.drivers.frr import parse_bgp_paths, parse_paths_available

FX = Path(__file__).resolve().parent / "fixtures"


def fx(name):
    return (FX / name).read_text(encoding="utf-8")


def frr_10_4(prefix):
    return parse_bgp_paths(fx("frr_bgp_paths.txt"), prefix)


def frr_10_2(prefix):
    return parse_bgp_paths(fx("frr1021_learned_prefix_json.txt"), prefix,
                           text_count=parse_paths_available(fx("frr1021_learned_prefix_text.txt"), prefix))


class FrrPaths(FakeDrv):
    unsupported_bgp_attributes = frozenset()

    def __init__(self, read, *a, **k):
        super().__init__(*a, **k)
        self.read = read

    def bgp_paths(self, prefix, vrf="default"):
        return Observation(self.read(prefix), [])


@pytest.mark.parametrize("read,prefix,as_path", [(frr_10_4, "192.168.20.0/24", "65020"),
                                                 (frr_10_2, "192.168.21.0/24", "65000 65002")],
                         ids=["frr-10.4.1", "frr-10.2.1-stranger"])
def test_record_attributes_on_ebgp_frr_writes_the_check_and_no_gap(monkeypatch, read, prefix, as_path):
    drivers = {"r1": FrrPaths(read, {"10.1.1.2": {"ipv4-unicast": 1}}, routes4=[prefix]),
               "r2": FakeDrv({"10.1.1.1": {"ipv4-unicast": 1}})}
    data, warnings = run_record(monkeypatch, drivers, include_routes=True, attributes=True)
    route = [c for c in data["checks"] if c["type"] == "bgp_route" and c["node"] == "r1"]
    assert len(route) == 1 and route[0]["as_path"] == as_path, route
    assert rec.baseline_gaps(warnings) == [], warnings
