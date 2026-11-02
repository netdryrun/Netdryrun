"""What `record` writes, `validate` and `run` accept, on every driver (acceptance round, 2026-11-02): B-3 wrote
`afi: ipv6-unicast, exact: 0` on every eBGP session, and RouterOS, which can't count IPv6 prefixes, refused the
baseline before deploying (exit 2). Each driver's own declarations (unsupported_afis, route_protocols,
reads_received) are put on the recording fake, and every recorded check goes through the config validation and the
driver's pre-deploy refusals."""
from types import SimpleNamespace

import pytest
from test_record import FakeDrv, run_record

from netdryrun import record as rec
from netdryrun.config import _validate_check
from netdryrun.drivers import DRIVERS, DriverError, check_supported


@pytest.mark.parametrize("name", sorted(DRIVERS))
def test_every_recorded_check_is_one_the_driver_runs(monkeypatch, name):
    cls = DRIVERS[name]
    fake = type(f"{name}Like", (FakeDrv,), {"name": name, "unsupported_afis": cls.unsupported_afis,
                                             "route_protocols": cls.route_protocols,
                                             "reads_received": getattr(cls, "reads_received", False)})
    drivers = {"r1": fake({"10.0.12.2": {"ipv4-unicast": 3}}, routes4=["192.168.2.0/24"]), "r2": fake({})}
    data, _ = run_record(monkeypatch, drivers, guards=True)
    monkeypatch.setattr(rec, "detect", lambda node: name)
    lab = SimpleNamespace(nodes={"r1": None, "r2": None})
    checks = [_validate_check(i, dict(c), 30) for i, c in enumerate(data["checks"])]
    assert checks
    for c in checks:
        check_supported(lab, c, override=name)   # raises DriverError for anything the driver refuses


def test_routeros_gets_no_ipv6_family_check():
    from netdryrun.drivers.base import BgpNeighbor
    drv = SimpleNamespace(unsupported_afis=DRIVERS["routeros"].unsupported_afis)
    checks = rec._session_checks("m1", {"10.0.12.2": BgpNeighbor("10.0.12.2", "established", {"ipv4-unicast": 1},
                                                                 external=True)}, "exact", [], drv=drv)
    assert [(c["type"], c.get("afi")) for c in checks] == [("bgp_session", None), ("bgp_prefixes", "ipv4-unicast")]


def test_the_refusal_says_what_is_true():
    from netdryrun.config import Check
    c = Check("bgp_prefixes", {"node": "m1", "neighbor": "10.0.12.2", "afi": "ipv6-unicast", "exact": 0}, "v6", 30)
    with pytest.raises(DriverError) as e:
        check_supported(SimpleNamespace(nodes={"m1": None}), c, override="routeros")
    assert str(e.value) == ("v6: afi ipv6-unicast is not supported on routeros (the routeros driver can't count "
                            "prefixes in that family)")
