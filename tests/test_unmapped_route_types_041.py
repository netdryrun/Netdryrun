"""A route type a driver doesn't map is an error on every driver, never its raw name (Layer 6 on b03cb7a, closing the
class of the EOS acceptance finding): no `protocol` names a raw type, so `present: false` on it passed. Checked: EOS
(already an error), NX-OS, Junos, SR Linux and FRR (the four that passed the raw name through), RouterOS (maps
`belongs-to` flags, no raw names)."""
from pathlib import Path

import pytest

from netdryrun.drivers import frr, junos, nxos, srlinux
from netdryrun.drivers.base import DriverError

FIX = Path(__file__).parent / "fixtures"


def read(name):
    return (FIX / name).read_text(encoding="utf-8")


CASES = [
    ("nxos", lambda: nxos.parse_all_routes(read("nxos_all_routes.txt").replace('"bgp-65001"', '"mystery-1"', 1)),
     "clientname 'mystery-1' is not one this driver maps to a protocol"),
    ("junos", lambda: junos.parse_routes(read("junos_route_paths.txt").replace('"BGP"', '"Mystery"', 1), "10.20.0.0/24"),
     "protocol-name 'Mystery' is not one this driver maps to a protocol"),
    ("srlinux", lambda: srlinux.parse_all_routes(read("srl_route.txt").replace('"route-type": "bgp"',
                                                                              '"route-type": "mystery"', 1)),
     "route-type 'mystery' is not one this driver maps to a protocol"),
    ("frr", lambda: frr.parse_all_routes(read("frr_route.txt").replace('"protocol":"bgp"', '"protocol":"mystery"', 1)),
     "protocol 'mystery' is not one this driver maps to a protocol"),
]


@pytest.mark.parametrize("name,parse,detail", CASES, ids=[c[0] for c in CASES])
def test_an_unmapped_route_type_is_an_error(name, parse, detail):
    with pytest.raises(DriverError) as e:
        parse()
    assert str(e.value).endswith(detail)


def test_the_known_types_still_read():
    assert {r.protocol for r in nxos.parse_all_routes(read("nxos_all_routes.txt"))} == {"bgp", "connected", "local",
                                                                                      "static"}
    assert {r.protocol for r in srlinux.parse_all_routes(read("srl_route.txt"))} >= {"bgp"}
