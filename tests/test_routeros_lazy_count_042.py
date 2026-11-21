"""RouterOS brings a session's prefix-count up to date only when its routing table is read (live CHR 7.23.8,
2026-11-18: 0 over four reads ten minutes after boot, right just after `/routing/route`). bgp_neighbors reads the
sessions once more after the table; a count that still differs stays an error. Derived from the driver captures."""
import pytest
from test_routeros_driver import SESSIONS, STATE, body
from test_verdict_drivers import Lab

from netdryrun.drivers import DriverError
from netdryrun.drivers.routeros import RouterosDriver


def _stale(rows):
    out = [dict(r) for r in rows]
    for r in out:
        if "prefix-count" in r:
            r["prefix-count"] = "0"
    return out


class LazyLab(Lab):
    """Session rows read `before` until a `/routing/route` read, then `after`."""

    def __init__(self, before, after):
        super().__init__(STATE)
        self.before, self.after, self.table_read = before, after, False

    def exec(self, node, cmd, timeout=60, input=None):
        line = " ".join(cmd)
        if "/routing/route" in line:
            self.table_read = True
        if "/routing/bgp/session" in line:
            self.rules = [("/routing/bgp/session", body(self.after if self.table_read else self.before))] + STATE[1:]
        return super().exec(node, cmd, timeout, input)


def _session_reads(lab):
    return sum("/routing/bgp/session" in ln for ln in lab.lines())


def test_a_stale_count_read_before_the_table_is_read_again():
    lab = LazyLab(_stale(SESSIONS), SESSIONS)
    n = RouterosDriver(lab, "r1").bgp_neighbors().value
    assert n["192.0.2.2"].prefixes == {"ipv4-unicast": 3} and n["198.51.100.2"].prefixes == {"ipv4-unicast": 1}
    assert _session_reads(lab) == 2


def _paths_read(lab):
    return [c[1][4] for c in lab.calls]       # python3 -c HELPER GET <path> ...


def test_the_second_read_asks_for_the_sessions_again_exactly():
    lab = LazyLab(_stale(SESSIONS), SESSIONS)
    RouterosDriver(lab, "r1").bgp_neighbors()
    assert _paths_read(lab) == ["/routing/bgp/session", "/routing/bgp/connection", "/routing/route?routing-table=main",
                                "/routing/bgp/session"]


def test_a_count_still_off_after_the_second_read_is_an_error():
    lab = LazyLab(_stale(SESSIONS), _stale(SESSIONS))
    with pytest.raises(DriverError, match=r"received 0 prefixes \(prefix-count\) but the table lists 4 of its paths"):
        RouterosDriver(lab, "r1").bgp_neighbors()
    assert _session_reads(lab) == 2


def test_a_count_that_matches_is_read_once():
    lab = LazyLab(SESSIONS, SESSIONS)
    RouterosDriver(lab, "r1").bgp_neighbors()
    assert _session_reads(lab) == 1


def test_the_second_read_still_refuses_an_ipv6_session():
    after = [dict(r) for r in SESSIONS]
    for r in after:
        r["remote.afi"] = "ipv6"
    lab = LazyLab(_stale(SESSIONS), after)
    with pytest.raises(DriverError, match="IPv6 sessions are not supported on routeros yet"):
        RouterosDriver(lab, "r1").bgp_neighbors()
