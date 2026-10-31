"""A config the NOS rejected, wholly or in part, is never a pass (expert war game, 2026-10-29).

Reproduced live on FRR 10.4.1 (examples/frr-bgp, r2 adds `neighbor 10.0.12.1 default-orignate`, a typo): FRR's
boot apply skipped that line, logged `line 18: % Unknown command`, loaded the rest, and 0.3.2 said PASSED (exit
0) on a config whose changed line never ran. `run` reads the boot log from 0.3.3 (tests/test_frr_config_load.py);
0.4 reads it the same way on each side of `verify`, and records every node's load in the report (a driver that
can't tell says so, never silently)."""
import pytest

from netdryrun.drivers.frr import FrrDriver
from netdryrun.lab import ExecResult, LabError, Node
from netdryrun.verify import run as vrun

# the container log of r2 in the live repro (FRR's vtysh -b prints each rejected line once per daemon)
LIVE_LOG = """\
[38|mgmtd] sending configuration
[45|bgpd] sending configuration
line 18: % Unknown command[31]:   neighbor 10.0.12.1 default-orignate
line 18: % Unknown command[31]:   neighbor 10.0.12.1 default-orignate
line 18: % Unknown command[31]:   neighbor 10.0.12.1 default-orignate
[45|bgpd] Configuration file[/etc/frr/frr.conf] processing failure: 2
"""
CLEAN_LOG = "[38|mgmtd] sending configuration\n[45|bgpd] sending configuration\n"


class Lab:
    def __init__(self, logs: dict, kinds: dict | None = None):
        self.logs, self.read = logs, []
        kinds = kinds or {}
        self.nodes = {n: Node(n, f"clab-t-{n}", *kinds.get(n, ("linux", "quay.io/frrouting/frr:10.4.1")))
                      for n in logs}

    def boot_log(self, node):
        self.read.append(node)
        return ExecResult([], 0, self.logs[node], "")


def test_verify_stops_on_a_side_whose_config_did_not_load():
    """verify_change: a changed line FRR rejected on the after side would read as NO BEHAVIOR CHANGE. Each side's
    nodes are checked after the snapshot: any rejected line stops the run (exit 2), naming the side, the node and
    the line."""
    lab = Lab({"r1": CLEAN_LOG, "r2": LIVE_LOG, "h1": CLEAN_LOG}, {"h1": ("linux", "alpine:3")})
    with pytest.raises(LabError) as e:
        vrun.check_config_loaded(lab, {"r1": "frr", "r2": "frr"}, "after")
    assert "[after]" in str(e.value) and "r2: line 18: neighbor 10.0.12.1 default-orignate" in str(e.value)
    vrun.check_config_loaded(Lab({"r1": CLEAN_LOG, "h1": CLEAN_LOG}), {"r1": "frr"}, "before")   # clean: no error


def test_verify_reads_a_node_it_did_not_snapshot_when_its_log_shows_rejected_lines():
    """A node verify doesn't snapshot (a host, a node run as --unobserved) whose log shows FRR's rejected lines
    still stops the side: fail closed, as `run` does for a node whose driver it can't detect."""
    lab = Lab({"r1": CLEAN_LOG, "x1": LIVE_LOG}, {"x1": ("linux", "registry.local/edge:7")})
    with pytest.raises(LabError, match="x1: line 18"):
        vrun.check_config_loaded(lab, {"r1": "frr"}, "after")


def test_verify_stops_when_an_frr_nodes_load_is_unknown():
    """No sign of a config load in an FRR node's log is no proof it loaded: exit 2, as in `run`."""
    with pytest.raises(LabError, match="no sign of a config load"):
        vrun.check_config_loaded(Lab({"r1": "watchfrr: all daemons up\n"}), {"r1": "frr"}, "before")


def test_verify_reads_another_platform_by_its_own_rule_not_by_frrs_log():
    """An SR Linux node is read by SR Linux's rule (its startup-config load log), never by FRR's boot-log parser."""
    lab = Lab({"r1": CLEAN_LOG, "s1": LIVE_LOG}, {"s1": ("nokia_srlinux", "ghcr.io/nokia/srlinux:26.7.2")})
    lab.exec = lambda node, cmd, timeout=60, input=None: ExecResult(cmd, 1, "", "")   # grep: no load failure
    vrun.check_config_loaded(lab, {"r1": "frr", "s1": "srlinux"}, "after")
    assert lab.read == ["r1"]


def test_frr_reports_its_version():
    from netdryrun.drivers.frr import parse_version

    text = "FRRouting 10.4.1_git (edge1) on Linux(6.18.54.1-microsoft-standard-WSL2).\nCopyright 1996-2005 ...\n"
    assert parse_version(text) == "FRRouting 10.4.1_git"
    assert parse_version("% Unknown command\n") is None


def test_driver_defaults_never_claim_what_they_do_not_read():
    from netdryrun.drivers.base import Driver, DriverError
    d = Driver(None, "x1")
    assert d.nos_version() is None
    with pytest.raises(DriverError):
        d.vrfs()


def test_frr_reads_its_version_from_the_node_and_none_when_it_cannot():
    class ExecLab:
        def __init__(self, rc, out):
            self.rc, self.out = rc, out

        def exec(self, node, cmd, timeout=60, input=None):
            return ExecResult(cmd, self.rc, self.out, "")
    assert FrrDriver(ExecLab(0, "FRRouting 10.4.1_git (r1) on Linux.\n"), "r1").nos_version() == "FRRouting 10.4.1_git"
    assert FrrDriver(ExecLab(1, ""), "r1").nos_version() is None
