"""Oracle FP-042-FRRVRFPARSE (adversary n4i on 57eb8ca, D2): FRR's VRF list accepts any text.

FrrDriver.vrfs() runs `vtysh -c "show vrf"` and frr.parse_vrfs keeps every line matching `vrf NAME ...`; every other
line is skipped. When vtysh exits 0 with an answer that is not zebra's `show vrf` at all (a daemon-connection message,
a changed or JSON format, a wrapper's banner), parse_vrfs returns {} and vrfs() returns [] with no warning: `record`
then records the default VRF only, as on a node without VRFs, and a leak into any VRF passes (the gap
FP-042-RECORDVRFLISTFAIL closed for a failed read, open for an unrecognised one).

The rule: an answer vrfs() doesn't recognise raises DriverError (record turns it into an INCOMPLETE BASELINE line);
it never reads as "no VRFs". Each answer here is non-empty and holds no `vrf NAME` line of zebra's format. The
guards (the live capture tests/fixtures/verify/show_vrf.txt still lists VRF cust; an empty answer, zebra's for a node
without VRFs, is still no VRFs; inactive VRFs and the netns header still parse) are in
tests/test_oracle_guards_fp_042_frrvrfparse.py.
"""
import pytest

from netdryrun.drivers.base import DriverError
from netdryrun.drivers.frr import FrrDriver
from netdryrun.lab import ExecResult


class AnswerLab:
    """Every command exits 0 with `text`."""

    def __init__(self, text):
        self.text, self.cmds = text, []

    def exec(self, node, cmd, timeout=60, input=None):
        self.cmds.append(cmd)
        return ExecResult(cmd, 0, self.text, "")


UNRECOGNISED = {
    "daemon-message": "% Can't open configuration file /etc/frr/vtysh.conf due to 'No such file or directory'.\n"
                      "Exiting: failed to connect to any daemons.\n",
    "unknown-command": "% Unknown command: show vrf\n",
    "banner": "Hello, this is FRRouting (version 10.4.1_git).\nCopyright 1996-2005 Kunihiro Ishiguro, et al.\n",
    "json-object": '{"red": {"vrfId": 5, "table": 1001, "state": "active"}}\n',
    "json-list": '[{"name": "red", "id": 5, "table": 1001}]\n',
    "json-string": '"vrf red id 5 table 1001"\n',
    "json-null": "null\n",
    "json-number": "5\n",
}


@pytest.mark.parametrize("case", sorted(UNRECOGNISED))
def test_an_unrecognised_show_vrf_answer_fails_closed(case):
    drv = FrrDriver(AnswerLab(UNRECOGNISED[case]), "r1")
    try:
        got = drv.vrfs().value
    except DriverError:
        return
    raise AssertionError(f"FRR answered `show vrf` with text that is not zebra's VRF list ({case}: "
                         f"{UNRECOGNISED[case]!r}) and vrfs() read it as the VRF list {got!r} instead of raising "
                         "DriverError: record would record the default VRF only, without an INCOMPLETE BASELINE line")
