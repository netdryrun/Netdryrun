"""0.4.1 mutation survivors in runner._startup_load (RouterOS, NX-OS), drivers.check_supported and the EOS driver's
route-type and BGP-summary parsing: the exact messages a refusal carries, and the node each read is made on."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from netdryrun.config import _validate_check
from netdryrun.drivers import DRIVERS, check_supported, eos
from netdryrun.drivers.base import DriverError
from netdryrun.lab import ExecResult, Lab
from netdryrun.runner import _startup_load

FX = Path(__file__).parent / "fixtures"
VRNETLAB_OK = "Pushing config via FTP\nconfig pushed via FTP\nStartup complete in: 0:00:43\n"


def check(**raw):
    return _validate_check(0, raw, 30.0)


class NamedLab:
    """A lab with one node, `r2`: its boot log and REST answers are given; any other node name has no log and its
    commands fail, so a read made on the wrong node shows."""

    def __init__(self, boot="", boot_rc=0, boot_err="", log=None, exec_rc=0, exec_err=""):
        self.boot, self.boot_rc, self.boot_err = boot, boot_rc, boot_err
        self.log, self.exec_rc, self.exec_err = log, exec_rc, exec_err

    def boot_log(self, name):
        if name != "r2":
            return ExecResult(["docker", "logs"], 1, "", f"no such container: {name}")
        return ExecResult(["docker", "logs", name], self.boot_rc, self.boot, self.boot_err)

    def exec(self, node, cmd, timeout=60, input=None):
        if node != "r2":
            return ExecResult(cmd, 1, "", f"no such container: {node}")
        return ExecResult(cmd, self.exec_rc, "" if self.exec_rc else f"200\n{json.dumps(self.log)}", self.exec_err)


def load(node_lab, driver="routeros"):
    return _startup_load(node_lab, "r2", driver, lambda n: [])


# --- RouterOS ----------------------------------------------------------------------------------------------------

def test_routeros_reads_the_named_nodes_boot_log_and_router_log():
    errors = json.loads((FX / "routeros_log_import_error.txt").read_text(encoding="utf-8"))
    from netdryrun.drivers.routeros_state import parse_import_log
    expected = parse_import_log(errors)
    assert expected   # the capture has a rejected line
    assert load(NamedLab(VRNETLAB_OK, log=errors)) == expected


def test_routeros_exact_messages_for_no_startup_and_gave_up():
    assert load(NamedLab("")) == [
        "its vrnetlab log doesn't show a completed startup, so whether its config loaded is unknown"]
    gave_up = "Pushing config via FTP\nGiving up after 5\nconfig pushed via FTP\nStartup complete in: 0:01:43\n"
    assert load(NamedLab(gave_up)) == [
        "vrnetlab could not upload its startup config over FTP (it gave up), so the router runs without it"]


def test_routeros_driver_error_without_unknown_gets_the_suffix():
    found = load(NamedLab(VRNETLAB_OK, exec_rc=1, exec_err="connection refused"))
    assert found == ["`REST GET /log` failed on r2 (rc=1): connection refused; so whether its config loaded is unknown"]


def test_routeros_driver_error_that_already_says_unknown_is_kept_as_is():
    # a log without the FTP upload session: parse_import_log's own message already says "unknown"
    assert load(NamedLab(VRNETLAB_OK, log=[])) == [
        "RouterOS's log doesn't show the startup config upload (an FTP session that started and ended), "
        "so whether the config loaded is unknown"]


# --- NX-OS -------------------------------------------------------------------------------------------------------

def test_nxos_reads_the_named_nodes_boot_log():
    # the named node's log has no "Startup complete": parse_startup_log's own error, not the unreadable-log one
    found = load(NamedLab("booting\n"), "nxos")
    assert found == ["vrnetlab's log shows no completed startup (no \"Startup complete\" line), so whether the "
                     "startup config loaded is unknown"]


def test_nxos_unreadable_log_uses_stdout_when_stderr_is_empty():
    found = load(NamedLab("  docker: daemon gone  \n", boot_rc=1), "nxos")
    assert found == ["its vrnetlab log could not be read (docker: daemon gone), so whether its config loaded is unknown"]


def test_nxos_unreadable_log_prefers_stderr():
    found = load(NamedLab("partial", boot_rc=1, boot_err="permission denied"), "nxos")
    assert found == ["its vrnetlab log could not be read (permission denied), so whether its config loaded is unknown"]


def test_nxos_unreadable_log_keeps_the_last_200_characters():
    err = "A" * 50 + "".join(chr(ord("a") + i % 26) for i in range(200))
    found = load(NamedLab("", boot_rc=1, boot_err=err), "nxos")
    assert found == [f"its vrnetlab log could not be read ({err[-200:]}), so whether its config loaded is unknown"]
    assert err[-200:] != err[-201:] and err[-200:] != err[200:]


# --- check_supported ---------------------------------------------------------------------------------------------

def _lab(tmp_path, kind="ceos", image="ceos:4.36.3M"):
    (tmp_path / "t.clab.yml").write_text(f"name: t\ntopology:\n  nodes:\n    r1:\n      kind: {kind}\n      image: {image}\n")
    return Lab(tmp_path / "t.clab.yml")


def test_route_protocol_message_lists_every_known_name(tmp_path):
    c = check(type="route", node="r1", prefix="10.0.0.0/24", protocol="rip", present=False, name="c1")
    with pytest.raises(DriverError) as e:
        check_supported(_lab(tmp_path), c)
    assert str(e.value) == ("c1: protocol rip is never reported by eos, so the check could never match a route; use one "
                            "of aggregate, bgp, connected, isis, ospf, ospf6, static")


def test_route_protocol_on_a_driver_with_no_list_is_refused_with_none(tmp_path):
    c = check(type="route", node="r1", prefix="10.0.0.0/24", protocol="bgp", present=False, name="c1")
    with pytest.raises(DriverError) as e:
        check_supported(_lab(tmp_path), c, override="nosuch")
    assert str(e.value) == ("c1: protocol bgp is never reported by nosuch, so the check could never match a route; use "
                            "one of (none)")


def test_unsupported_afi_exact_message(tmp_path):
    c = check(type="bgp_prefixes", node="r1", neighbor="10.20.1.2", afi="evpn", max=0, name="c1")
    with pytest.raises(DriverError) as e:
        check_supported(_lab(tmp_path), c)
    assert str(e.value) == "c1: afi evpn is not supported on eos (the eos driver can't count prefixes in that family)"


@pytest.mark.parametrize("override", [None, "nosuch"])
def test_only_exact_message_and_refused_on_a_driver_with_no_flag(tmp_path, override):
    c = check(type="bgp_prefixes", node="r1", neighbor="10.20.1.2", only=["203.0.113.0/25"], name="c1")
    name = override or "eos"
    with pytest.raises(DriverError) as e:
        check_supported(_lab(tmp_path), c, override=override)
    assert str(e.value) == (f"c1: only is not supported on {name} yet (it can't list the prefixes a neighbor sent); use "
                            "exact, or route checks with present: false")


def test_unsupported_bgp_attributes_are_all_named(tmp_path, monkeypatch):
    monkeypatch.setattr(DRIVERS["eos"], "unsupported_bgp_attributes", frozenset({"med", "local_pref"}))
    c = check(type="bgp_route", node="r1", prefix="203.0.113.0/25", med=10, local_pref=200, name="c1")
    with pytest.raises(DriverError) as e:
        check_supported(_lab(tmp_path), c)
    assert str(e.value) == "c1: local_pref, med is not supported on eos"


# --- EOS route types ---------------------------------------------------------------------------------------------

@pytest.mark.parametrize("rtype", ["OSPF3", "ospf3 intra area", "OSPFv3 External Type 2"])
def test_eos_ospfv3_route_types_are_ospf6_even_in_an_ipv4_shaped_prefix(rtype):
    assert eos._protocol(rtype, "10.0.0.0/24") == "ospf6"


@pytest.mark.parametrize("rtype", ["ISIS Level 1 Leaked", "isisLevel2External"])
def test_eos_any_isis_route_type_is_isis(rtype):
    # not in the PROTOCOLS map: the isis prefix rule alone names them
    assert eos._protocol(rtype, "10.0.0.0/24") == "isis"
