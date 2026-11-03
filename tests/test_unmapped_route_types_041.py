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


# --- a missing forwarding flag is unknown: an error, never "not forwarding" (Layer 6 round 2 on eaa323c) ------------

@pytest.mark.parametrize("route", [{"kernelProgrammed": True}, {"hardwareProgrammed": True}, {},
                                   {"kernelProgrammed": True, "hardwareProgrammed": None}])
def test_eos_a_route_without_both_programmed_flags_is_unknown(route):
    """cEOS 4.36.3M prints both flags on every route-table entry (every capture in tests/fixtures): one missing is
    unknown. Read as not forwarding (Layer 6 on b03cb7a), it passed `present: false`; now the read fails."""
    from netdryrun.drivers import eos
    with pytest.raises(DriverError):
        eos._programmed("cmd", route)


def test_eos_flags_read_as_given():
    from netdryrun.drivers import eos
    assert eos._programmed("cmd", {"kernelProgrammed": True, "hardwareProgrammed": True}) is True
    assert eos._programmed("cmd", {"kernelProgrammed": True, "hardwareProgrammed": False}) is False
