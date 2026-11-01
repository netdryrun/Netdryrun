"""A config line FRR rejects at boot is skipped: the lab runs without it, so a check can pass on a change that never
loaded (found in 0.3.2 by the 0.4 session: `default-orignate`). After the checks, each FRR node's boot log is read,
and any line vtysh rejected makes the run an error (exit 2), never a pass.

The fixtures are `docker logs` of quay.io/frrouting/frr:10.4.1 started privileged, as containerlab starts it, with
examples/frr-bgp/configs/r1.conf plus three bad lines (frr_boot_log_rejected.conf, lines 21-23), and with the clean
r1.conf: captured 2026-10-29."""
from pathlib import Path

import pytest

from netdryrun import runner
from netdryrun.drivers import frr
from netdryrun.lab import ExecResult, Node

from test_runner_robustness import ALWAYS, FakeDriver, FakeLab, World, cfg, install

FIX = Path(__file__).parent / "fixtures"
REJECTED = (FIX / "frr_boot_log_rejected.txt").read_text(encoding="utf-8")
CLEAN = (FIX / "frr_boot_log_clean.txt").read_text(encoding="utf-8")


def test_the_rejected_lines_are_read_from_a_real_boot_log():
    found = frr.parse_config_load_errors(REJECTED)
    assert found == [
        "line 21: neighbor 10.0.12.2 default-orignate (Unknown command)",
        "line 22: neighbor 10.0.12.2 maximum-prefix (Command incomplete)",
        "line 23: neighbor 10.9.9.9 route-map ALLOW-ALL in (rejected by bgpd)",
    ]
    assert frr.parse_config_load_errors(CLEAN) == []


@pytest.mark.parametrize("text, expected", [
    ("line 7: % Ambiguous command[4]: ip ro\n", ["line 7: ip ro (Ambiguous command)"]),
    ("line 7: % Unknown command: foo\n", ["line 7: foo (Unknown command)"]),   # FRR without the node number
    ("line 9: Warning[31]...:   neighbor 1.2.3.4 shutdown\n", ["line 9: neighbor 1.2.3.4 shutdown (warning)"]),
    ("line 3: Warning[4]...: early exit from config file\n", ["line 3: early exit from config file (warning)"]),
    ("[45|bgpd] Configuration file[/etc/frr/frr.conf] processing failure: 13\n",
     ["bgpd reported a configuration file processing failure (13)"]),
])
def test_every_vtysh_load_error_form_counts(text, expected):
    assert frr.parse_config_load_errors(text) == expected


class BootLogLab(FakeLab):
    def __init__(self, world, logs: dict, images: dict | None = None):
        super().__init__(world)
        self.logs, self.read, self.daemons_read = logs, [], []
        for n, image in (images or {}).items():
            self.nodes[n] = Node(n, f"clab-t-{n}", "linux" if "frr" in image else "ceos", image)

    def boot_log(self, node):
        self.read.append(node)
        log = self.logs.get(node, CLEAN)
        return log if isinstance(log, ExecResult) else ExecResult([], 0, log, "")

    running: dict = {}
    conf: dict = {}

    def exec(self, node, cmd, timeout=60, input=None):
        if cmd[:1] == ["Cli"]:   # a cEOS node's startup-config errors (tests/test_startup_config_load.py): none
            return ExecResult(cmd, 0, "No errors were found in startup-config.", "")
        if cmd == ["cat", "/etc/frr/frr.conf"]:
            r = self.conf.get(node, "")
        else:   # one daemon's own running config: vtysh -d <daemon>
            assert cmd[:2] == ["vtysh", "-d"] and cmd[3:] == ["-c", "show running-config"], cmd
            self.daemons_read.append(cmd[2])
            r = self.running.get(node, "")
            r = r.get(cmd[2], "") if isinstance(r, dict) else r
        return r if isinstance(r, ExecResult) else ExecResult(cmd, 0, r, "")


def _run(tmp_path, monkeypatch, lab, deploy=False):
    w = lab.world
    install(monkeypatch, w, lab, {n: FakeDriver(w) for n in ("r1", "r2", "r3")})
    return runner.run(cfg(tmp_path, [ALWAYS]), deploy=deploy, settle=0, hold=3)


def test_a_clean_boot_still_passes(tmp_path, monkeypatch):
    lab = BootLogLab(World(), {})
    rep = _run(tmp_path, monkeypatch, lab)
    assert rep.status == "passed" and sorted(lab.read) == ["r1", "r2", "r3"]


@pytest.mark.parametrize("deploy", [True, False])
def test_a_rejected_line_on_any_frr_node_makes_the_run_an_error(tmp_path, monkeypatch, deploy):
    # r2 has no check at all: the line it rejected can still change what r3 sees
    lab = BootLogLab(World(), {"r2": REJECTED})
    rep = _run(tmp_path, monkeypatch, lab, deploy=deploy)
    assert rep.status == "error" and rep.exit_code == 2
    assert all(r.passed for r in rep.results)   # the checks passed: on a lab without the change
    assert "r2" in rep.error and "line 21: neighbor 10.0.12.2 default-orignate (Unknown command)" in rep.error
    assert "line 23" in rep.error and "r1" not in rep.error.split("rejected")[0]


def test_an_unreadable_boot_log_is_an_error(tmp_path, monkeypatch):
    lab = BootLogLab(World(), {"r1": ExecResult([], 1, "", "Error response from daemon: configured logging driver does not support reading")})
    rep = _run(tmp_path, monkeypatch, lab)
    assert rep.status == "error" and "r1" in rep.error and "boot log" in rep.error


def test_only_frr_nodes_are_read(tmp_path, monkeypatch):
    lab = BootLogLab(World(), {"ce1": REJECTED}, images={"ce1": "ceos:4.32.0F"})
    rep = _run(tmp_path, monkeypatch, lab)
    assert rep.status == "passed" and "ce1" not in lab.read


# Config applied by `setup:` commands (SONiC, or FRR configured after boot) goes through `vtysh -c`, which exits 1
# on a rejected line (FRR 10.4.1, 2026-10-29: "% Unknown command: ...", "% Command incomplete: ...",
# "% Specify remote-as or peer-group commands first", each rc=1). A setup command that never succeeds stops the run.

def test_a_setup_command_vtysh_rejects_stops_the_run():
    from netdryrun.lab import Lab, LabError
    lab = object.__new__(Lab)
    lab.nodes = {"r1": Node("r1", "clab-t-r1", "linux", "quay.io/frrouting/frr:10.4.1")}
    calls = []

    def exec_(node, cmd, timeout=60, input=None):
        calls.append(cmd)
        if "default-orignate" in cmd[-1]:
            return ExecResult(cmd, 1, "% Unknown command: neighbor 10.0.12.2 default-orignate\n", "")
        return ExecResult(cmd, 0, "", "")

    lab.exec = exec_
    lab.run_setup("r1", ["vtysh -c 'conf t' -c 'router bgp 65001' -c 'neighbor 10.0.12.2 description ok'"], budget=0)
    with pytest.raises(LabError, match="setup on r1 failed.*Unknown command: neighbor 10.0.12.2 default-orignate"):
        lab.run_setup("r1", ["vtysh -c 'conf t' -c 'router bgp 65001' -c 'neighbor 10.0.12.2 default-orignate'"],
                      budget=0)


# --- Delta review round 2 (2026-10-29) --------------------------------------------------------------------------------

def test_a_node_whose_driver_is_unknown_is_read_too(tmp_path, monkeypatch):
    # R1: FRR in an image without "frr" in its name: its boot log still counts
    lab = BootLogLab(World(), {"edge": REJECTED}, images={"edge": "registry.local/edge-router:10.4"})
    lab.nodes["edge"] = Node("edge", "clab-t-edge", "linux", "registry.local/edge-router:10.4")
    rep = _run(tmp_path, monkeypatch, lab)
    assert rep.status == "error" and "edge" in lab.read and "default-orignate" in rep.error


def test_a_plain_host_with_an_unknown_driver_is_not_an_error(tmp_path, monkeypatch):
    lab = BootLogLab(World(), {"h1": "Starting nginx\nready\n"})
    lab.nodes["h1"] = Node("h1", "clab-t-h1", "linux", "alpine:3.20")
    rep = _run(tmp_path, monkeypatch, lab)
    assert rep.status == "passed" and "h1" in lab.read


def test_a_bridge_has_no_boot_log_to_read(tmp_path, monkeypatch):
    lab = BootLogLab(World(), {})
    lab.nodes["br1"] = Node("br1", "br1", "bridge", "")
    rep = _run(tmp_path, monkeypatch, lab)
    assert rep.status == "passed" and "br1" not in lab.read


def test_a_daemon_that_reads_its_own_config_file_reports_rejected_lines_too():
    # R2: per-daemon config (bgpd.conf, no integrated frr.conf): the daemon logs "... on config line N: ..."
    text = ("2026/10/29 16:25:51 BGP: [ZWCSR-M7FG9][EC 100663304] No such command on config line 21: "
            "neighbor 1.1.1.1 default-orignate\n")
    assert frr.parse_config_load_errors(text) == [
        "line 21: neighbor 1.1.1.1 default-orignate (No such command, bgp)"]


def test_an_frr_log_with_no_sign_of_a_config_load_is_an_error(tmp_path, monkeypatch):
    # R2: no vtysh boot output at all (a custom entrypoint, config read elsewhere): whether it loaded is unknown
    started_only = "\n".join(line for line in CLEAN.splitlines()
                             if "sending configuration" not in line and "] done" not in line)
    lab = BootLogLab(World(), {"r3": started_only})
    rep = _run(tmp_path, monkeypatch, lab)
    assert rep.status == "error" and "r3" in rep.error and "no sign" in rep.error


def test_the_boot_log_is_read_since_the_container_last_started(monkeypatch):
    # R4/R5: a log from before a restart (a config fixed since) must not count; invalid bytes don't crash
    from netdryrun import lab as lab_mod
    from netdryrun.lab import Lab
    calls = []

    def fake_run(cmd, timeout=600, env=None, input=None, errors=None):
        calls.append((cmd, errors))
        if cmd[:2] == ["docker", "inspect"]:
            return ExecResult(cmd, 0, "2026-10-29T16:25:51.123456789Z\n", "")
        return ExecResult(cmd, 0, "[45|bgpd] done", "")

    monkeypatch.setattr(lab_mod, "_run", fake_run)
    lab = object.__new__(Lab)
    lab.nodes = {"r1": Node("r1", "clab-t-r1", "linux", "quay.io/frrouting/frr:10.4.1")}
    r = lab.boot_log("r1")
    assert r.rc == 0 and "done" in r.stdout
    logs = [c for c, _ in calls if c[:2] == ["docker", "logs"]][0]
    assert logs == ["docker", "logs", "--since", "2026-10-29T16:25:51.123456789Z", "clab-t-r1"]
    assert all(e == "replace" for _, e in calls)


# --- Mutation follow-up (2026-10-30): every node is read in order, and the error says exactly what was found ------

def test_a_bridge_a_ceos_node_or_an_unreadable_host_before_an_frr_node_never_ends_the_scan(tmp_path, monkeypatch):
    # nodes that are skipped come first: the FRR node after them is still read
    w = World()
    lab = BootLogLab(w, {"h1": ExecResult([], 1, "", "no such container"), "r3": REJECTED})
    frr_nodes = dict(lab.nodes)
    lab.nodes = {"br1": Node("br1", "br1", "bridge", ""), "ovs1": Node("ovs1", "ovs1", "ovs-bridge", ""),
                 "ce1": Node("ce1", "clab-t-ce1", "ceos", "ceos:4.32.0F"),
                 "h1": Node("h1", "clab-t-h1", "linux", "alpine:3.20"), **frr_nodes}
    rep = _run(tmp_path, monkeypatch, lab)
    assert rep.status == "error" and "r3: line 21" in rep.error
    assert lab.read == ["h1", "r1", "r2", "r3"]


def test_a_driver_set_in_the_file_decides_that_a_node_is_frr(tmp_path, monkeypatch):
    # an image Netdryrun can't name, declared FRR in `drivers:`: an unreadable boot log is an error, as for any FRR
    lab = BootLogLab(World(), {"edge": ExecResult([], 1, "", "no such container")})
    lab.nodes["edge"] = Node("edge", "clab-t-edge", "linux", "registry.local/edge-router:10.4")
    install(monkeypatch, lab.world, lab, {n: FakeDriver(lab.world) for n in ("r1", "r2", "r3")})
    c = cfg(tmp_path, [ALWAYS])
    c.drivers = {"edge": "frr"}
    rep = runner.run(c, deploy=False, settle=0, hold=3)
    assert rep.status == "error" and "edge: its boot log could not be read" in rep.error


def test_the_error_names_every_node_and_every_line_exactly(tmp_path, monkeypatch):
    noise = "x" * 50 + "y" * 200
    no_load = "\n".join(line for line in CLEAN.splitlines() if "sending configuration" not in line and "] done" not in line)
    lab = BootLogLab(World(), {"r1": REJECTED, "r2": ExecResult([], 1, "", noise), "r3": no_load})
    rep = _run(tmp_path, monkeypatch, lab)
    assert rep.error == (
        "The NOS rejected configuration lines at boot, so the lab ran without them and the checks did not test the "
        "change as written: r1: line 21: neighbor 10.0.12.2 default-orignate (Unknown command); line 22: neighbor "
        "10.0.12.2 maximum-prefix (Command incomplete); line 23: neighbor 10.9.9.9 route-map ALLOW-ALL in (rejected "
        f"by bgpd) | r2: its boot log could not be read ({'y' * 200}), so whether its config loaded is unknown | r3: "
        "its boot log shows no sign of a config load (no vtysh boot output, no daemon config line), so whether its "
        "config loaded is unknown. Netdryrun reads the config load FRR's image runs at boot (frr.conf, vtysh -b). "
        "Fix the config and run again.")


def test_every_daemon_rejected_line_is_reported_in_line_order():
    text = ("2026/10/29 16:25:51 BGP: [ZWCSR-M7FG9] No such command on config line 30: neighbor 1.1.1.1 foo\n"
            "2026/10/29 16:25:51 BGP: [ZWCSR-M7FG9] No such command on config line 21: neighbor 1.1.1.1 bar\n"
            "line 25: % Unknown command[4]: baz\n")
    assert frr.parse_config_load_errors(text) == [
        "line 21: neighbor 1.1.1.1 bar (No such command, bgp)",
        "line 25: baz (Unknown command)",
        "line 30: neighbor 1.1.1.1 foo (No such command, bgp)"]


# --- Live gate on ada4dd0 (corpus v1 case 29, 2026-10-29): bgpd can answer a line with "Failure to communicate[13]"
# (CMD_WARNING_CONFIG_FAILED) and still apply it: `bgp graceful-restart` was in pe1's running config. Such a line
# doesn't count only if line N of frr.conf is that line and the running config has it in the same section. Every other
# kind always counts, and anything that can't be read keeps the error. (Delta review round 3: a section-blind match,
# per-daemon line numbers sharing a key, and a swallowed processing failure were false passes.)

GR_LOG = """[36|zebra] done
[35|mgmtd] done
line 64: Failure to communicate[13] to bgpd, line:  bgp graceful-restart
[42|bgpd] Configuration file[/etc/frr/frr.conf] processing failure: 13
"""
GR_CONF = "\n".join(["!"] * 62 + ["router bgp 65000", " bgp graceful-restart"]) + "\n"   # line 64
GR_RUNNING = """frr version 10.4.1
!
router bgp 65000
 bgp router-id 10.255.0.1
 bgp graceful-restart
 neighbor 10.0.1.2 remote-as 65100
 address-family ipv4 unicast
  neighbor 10.0.12.2 route-map ALLOW-ALL in
 exit-address-family
exit
!
end
"""


def test_a_line_the_daemon_complained_about_but_applied_is_not_rejected():
    assert frr.parse_config_load_errors(GR_LOG, running={"bgpd": GR_RUNNING}, config=GR_CONF) == []
    assert frr.parse_config_load_errors(GR_LOG) == ["line 64: bgp graceful-restart (rejected by bgpd)"]
    assert frr.parse_config_load_errors(GR_LOG, running={"bgpd": GR_RUNNING}) == [
        "line 64: bgp graceful-restart (rejected by bgpd)"]
    assert frr.parse_config_load_errors(GR_LOG, running={"zebra": GR_RUNNING}, config=GR_CONF) == [
        "line 64: bgp graceful-restart (rejected by bgpd)"]   # another daemon's running config proves nothing


def test_the_same_line_applied_in_another_section_does_not_count():
    # rejected under VRF RED (no such neighbor there); the default VRF has the very same line
    conf = "\n".join(["!"] * 77 + ["router bgp 65000 vrf RED", " address-family ipv4 unicast",
                                   "  neighbor 10.0.12.2 route-map ALLOW-ALL in"]) + "\n"   # line 80
    log = "line 80: Failure to communicate[13] to bgpd, line:   neighbor 10.0.12.2 route-map ALLOW-ALL in\n"
    assert frr.parse_config_load_errors(log, running={"bgpd": GR_RUNNING}, config=conf) == [
        "line 80: neighbor 10.0.12.2 route-map ALLOW-ALL in (rejected by bgpd)"]


def test_a_line_vtysh_could_not_parse_counts_even_if_the_text_is_applied():
    conf = "\n".join(["!"] * 62 + ["router bgp 65000", " bgp graceful-restart"]) + "\n"
    log = "line 64: % Unknown command[4]:  bgp graceful-restart\n"
    assert frr.parse_config_load_errors(log, running={"bgpd": GR_RUNNING}, config=conf) == [
        "line 64: bgp graceful-restart (Unknown command)"]


def test_a_line_that_is_not_the_files_line_n_counts():
    conf = "\n".join(["!"] * 62 + ["router bgp 65000", " bgp router-id 10.255.0.1"]) + "\n"
    assert frr.parse_config_load_errors(GR_LOG, running={"bgpd": GR_RUNNING}, config=conf) == [
        "line 64: bgp graceful-restart (rejected by bgpd)"]


def test_a_line_for_mgmtd_counts_even_if_the_running_config_has_it():
    conf = "\n".join(["!"] * 63 + ["ip route 10.9.0.0/24 blackhole"]) + "\n"
    log = "line 64: Failure to communicate[13] to mgmtd, line: ip route 10.9.0.0/24 blackhole\n"
    running = "frr version 10.4.1\nip route 10.9.0.0/24 blackhole\n"
    assert frr.parse_config_load_errors(log, running={"mgmtd": running}, config=conf) == [
        "line 64: ip route 10.9.0.0/24 blackhole (rejected by mgmtd)"]


def test_another_daemons_processing_failure_still_counts():
    log = GR_LOG + "[50|ospfd] Configuration file[/etc/frr/frr.conf] processing failure: 13\n"
    assert frr.parse_config_load_errors(log, running={"bgpd": GR_RUNNING}, config=GR_CONF) == [
        "ospfd reported a configuration file processing failure (13)"]


def test_two_daemon_files_with_the_same_line_number_are_both_kept():
    log = ("2026/10/29 16:25:51 BGP: [X] No such command on config line 5: bgp graceful-restart\n"
           "2026/10/29 16:25:51 OSPF: [Y] No such command on config line 5: router-info area\n")
    assert frr.parse_config_load_errors(log, running={"bgpd": GR_RUNNING}, config=GR_CONF) == [
        "line 5: bgp graceful-restart (No such command, bgp)", "line 5: router-info area (No such command, ospf)"]


def test_the_sections_of_a_config():
    text = ("router bgp 65000 vrf RED\n neighbor 1.1.1.1 remote-as 1\n address-family ipv4 unicast\n"
            "  network 10.0.0.0/8\n exit-address-family\nexit\n!\nip route 1.0.0.0/8 Null0\n")
    assert frr.config_sections(text) == [
        ((), "router bgp 65000 vrf RED"), (("router bgp 65000 vrf RED",), "neighbor 1.1.1.1 remote-as 1"),
        (("router bgp 65000 vrf RED",), "address-family ipv4 unicast"),
        (("router bgp 65000 vrf RED", "address-family ipv4 unicast"), "network 10.0.0.0/8"),
        (("router bgp 65000 vrf RED",), "exit-address-family"),
        ((), "exit"), ((), "!"), ((), "ip route 1.0.0.0/8 Null0")]


def test_every_depth_is_a_section():
    text = ("router bgp 65000\n address-family l2vpn evpn\n  vni 10\n   route-target import 65000:99\n  exit-vni\n"
            "  vni 20\n   route-target import 65000:99\n")
    evpn = ("router bgp 65000", "address-family l2vpn evpn")
    assert frr.config_sections(text)[3] == ((*evpn, "vni 10"), "route-target import 65000:99")
    assert frr.config_sections(text)[6] == ((*evpn, "vni 20"), "route-target import 65000:99")


def test_a_line_another_block_prints_the_same_does_not_clear_it():
    # delta review round 5: `route-target both` in vni 20 prints as import + export; vni 10's refused import must count
    conf = ("router bgp 65000\n address-family l2vpn evpn\n  vni 10\n   route-target import 65000:99\n  exit-vni\n"
            "  vni 20\n   route-target both 65000:99\n  exit-vni\n exit-address-family\nexit\n")   # line 4
    log = "line 4: Failure to communicate[13] to bgpd, line:    route-target import 65000:99\n"
    running = ("router bgp 65000\n address-family l2vpn evpn\n  vni 10\n  exit-vni\n  vni 20\n"
               "   route-target import 65000:99\n   route-target export 65000:99\n  exit-vni\n exit-address-family\nexit\n")
    assert frr.parse_config_load_errors(log, running={"bgpd": running}, config=conf) == [
        "line 4: route-target import 65000:99 (rejected by bgpd)"]


def test_a_flat_file_never_matches_an_indented_running_config():
    conf = "\n".join(["!"] * 62 + ["router bgp 65000", "bgp graceful-restart"]) + "\n"   # no indentation
    assert frr.parse_config_load_errors(GR_LOG, running={"bgpd": GR_RUNNING}, config=conf) == [
        "line 64: bgp graceful-restart (rejected by bgpd)"]


def test_a_line_missing_from_the_running_config_is_still_rejected():
    assert frr.parse_config_load_errors(REJECTED, running={"bgpd": GR_RUNNING}, config=GR_CONF) == [
        "line 21: neighbor 10.0.12.2 default-orignate (Unknown command)",
        "line 22: neighbor 10.0.12.2 maximum-prefix (Command incomplete)",
        "line 23: neighbor 10.9.9.9 route-map ALLOW-ALL in (rejected by bgpd)",
    ]


def test_a_processing_failure_with_no_line_is_still_an_error_whatever_the_running_config():
    text = "[45|bgpd] Configuration file[/etc/frr/frr.conf] processing failure: 13\n"
    assert frr.parse_config_load_errors(text, running={"bgpd": GR_RUNNING}, config=GR_CONF) == [
        "bgpd reported a configuration file processing failure (13)"]


def test_an_applied_line_passes_the_run(tmp_path, monkeypatch):
    lab = BootLogLab(World(), {"r1": GR_LOG})
    lab.running, lab.conf = {"r1": GR_RUNNING}, {"r1": GR_CONF}
    rep = _run(tmp_path, monkeypatch, lab)
    assert rep.status == "passed", rep.error


@pytest.mark.parametrize("which", ["running", "conf"])
def test_an_unreadable_running_config_or_file_keeps_the_error_and_says_why(tmp_path, monkeypatch, which):
    lab = BootLogLab(World(), {"r1": GR_LOG})
    lab.running, lab.conf = {"r1": GR_RUNNING}, {"r1": GR_CONF}
    setattr(lab, which, {"r1": ExecResult([], 1, "", "vtysh: not found")})
    rep = _run(tmp_path, monkeypatch, lab)
    assert rep.status == "error" and ("r1: line 64: bgp graceful-restart (rejected by bgpd); (not checked against "
                                      "the running config: vtysh: not found)") in rep.error


# Delta review round 4: the merged running config shows a line zebra took and bgpd refused, and two blocks one level
# below an address family (two `vni`) share a section. Each daemon's own running config is read, and the line must
# be there at least as often as in the file.

def test_a_line_another_daemon_took_does_not_clear_the_one_that_refused_it():
    conf = "\n".join(["!"] * 61 + ["route-map RM permit 10", " match ip address prefix-list X"]) + "\n"   # line 63
    log = "line 63: Failure to communicate[13] to bgpd, line:  match ip address prefix-list X\n"
    zebra = "route-map RM permit 10\n match ip address prefix-list X\nexit\n"
    bgpd = "route-map RM permit 10\nexit\n"
    assert frr.parse_config_load_errors(log, running={"bgpd": bgpd, "zebra": zebra}, config=conf) == [
        "line 63: match ip address prefix-list X (rejected by bgpd)"]
    assert frr.parse_config_load_errors(log, running={"bgpd": zebra}, config=conf) == []


def test_two_blocks_in_one_section_need_the_line_in_both():
    conf = ("router bgp 65000\n address-family l2vpn evpn\n  vni 100\n   route-target import 65000:100\n  exit-vni\n"
            "  vni 200\n   route-target import 65000:100\n  exit-vni\n exit-address-family\nexit\n")   # line 7
    log = "line 7: Failure to communicate[13] to bgpd, line:    route-target import 65000:100\n"
    once = ("router bgp 65000\n address-family l2vpn evpn\n  vni 100\n   route-target import 65000:100\n  exit-vni\n"
            "  vni 200\n  exit-vni\n exit-address-family\nexit\n")
    assert frr.parse_config_load_errors(log, running={"bgpd": once}, config=conf) == [
        "line 7: route-target import 65000:100 (rejected by bgpd)"]
    assert frr.parse_config_load_errors(log, running={"bgpd": conf}, config=conf) == []


def test_only_the_daemons_that_answered_failure_to_communicate_are_read(tmp_path, monkeypatch):
    lab = BootLogLab(World(), {"r1": GR_LOG, "r2": REJECTED})
    lab.running, lab.conf = {"r1": GR_RUNNING, "r2": GR_RUNNING}, {"r1": GR_CONF, "r2": GR_CONF}
    rep_ = _run(tmp_path, monkeypatch, lab)
    assert lab.daemons_read == ["bgpd", "bgpd"] and frr.communicate_daemons(REJECTED) == ["bgpd"]
    assert frr.communicate_daemons("line 4: Failure to communicate[13] to mgmtd, line: ip route 1.0.0.0/8 Null0\n") == []
    assert rep_.status == "error" and "r1" not in rep_.error.split("change as written:")[1] and "r2: line 21" in rep_.error



# Delta review round 6: vtysh places a line by the commands before it, not by indentation, so a misindented line can
# share a section with an applied one; a refused header can leave its block in the running config. The line's whole
# block must be in the daemon's running config as written, and a header always counts.

def test_a_misindented_refused_line_does_not_borrow_another_lines_section():
    conf = ("router bgp 65000 vrf RED\n address-family l2vpn evpn\n  route-target both 65000:99\n  vni 10\n"
            "  route-target import 65000:99\n exit-address-family\nexit\n")   # line 5, at vni 10's depth
    log = "line 5: Failure to communicate[13] to bgpd, line:   route-target import 65000:99\n"
    running = ("router bgp 65000 vrf RED\n address-family l2vpn evpn\n  route-target import 65000:99\n"
               "  route-target export 65000:99\n  vni 10\n  exit-vni\n exit-address-family\nexit\n")
    assert frr.parse_config_load_errors(log, running={"bgpd": running}, config=conf) == [
        "line 5: route-target import 65000:99 (rejected by bgpd)"]


def test_a_refused_header_counts_even_if_its_block_shows():
    conf = ("router bgp 65000\n address-family l2vpn evpn\n  vni 10\n   route-target import 65000:99\n  exit-vni\n"
            " exit-address-family\nexit\n")   # line 3: vni 10
    log = "line 3: Failure to communicate[13] to bgpd, line:   vni 10\n"
    assert frr.parse_config_load_errors(log, running={"bgpd": conf}, config=conf) == ["line 3: vni 10 (rejected by bgpd)"]


def test_a_line_under_a_comment_keeps_its_real_section():
    text = "router bgp 65000\n ! a note\n  bgp graceful-restart\n"
    assert frr.config_sections(text)[2] == (("router bgp 65000",), "bgp graceful-restart")


def test_the_block_must_be_in_the_running_config_as_written():
    # the GR case: the appended block is inside the running config's router bgp block, in order
    assert frr._block_applied(GR_CONF, 63, GR_RUNNING)
    assert not frr._block_applied(GR_CONF.replace("router bgp 65000", "router bgp 65001"), 63, GR_RUNNING)
    assert not frr._block_applied(GR_CONF, 63, GR_RUNNING.replace(" bgp graceful-restart\n", ""))



# Delta review round 7: vtysh numbers frr.conf by \n only; splitlines() also splits on \f, U+2028 and others, which
# moved line N onto an applied line elsewhere.

@pytest.mark.parametrize("sep", ["\u2028", "\x0c", "\x0b", "\r"])
def test_line_n_is_counted_the_way_vtysh_counts_it(sep):
    conf = (f"! note{sep}{sep}{sep}\ninterface eth1\n ip ospf passive\nexit\ninterface eth2\n ip ospf passive\nexit\n")
    log = "line 6: Failure to communicate[13] to ospfd, line:  ip ospf passive\n"
    running = "interface eth1\n ip ospf passive\nexit\ninterface eth2\nexit\n"
    assert frr.parse_config_load_errors(log, running={"ospfd": running}, config=conf) == [
        "line 6: ip ospf passive (rejected by ospfd)"]


def test_a_command_that_starts_like_end_is_still_a_header():
    text = "endpoint-group A\n member 1\n"
    assert frr.config_sections(text)[1] == (("endpoint-group A",), "member 1")


def test_a_line_longer_than_vtysh_reads_at_once_clears_nothing():
    # delta review round 8: vtysh's 4096-byte line buffer would count it as several lines
    conf = "! " + "x" * 5000 + "\n" + GR_CONF.split("\n", 1)[1]
    assert frr.parse_config_load_errors(GR_LOG, running={"bgpd": GR_RUNNING}, config=GR_CONF) == []
    assert frr.parse_config_load_errors(GR_LOG, running={"bgpd": GR_RUNNING}, config=conf) == [
        "line 64: bgp graceful-restart (rejected by bgpd)"]


# Mutation follow-up on f8bbb0a: the edges of the running-config match.

@pytest.mark.parametrize("size, kept", [(4094, False), (4095, True)])
def test_the_long_line_limit_is_exact(size, kept):
    conf = "! " + "x" * (size - 2) + "\n" + GR_CONF.split("\n", 1)[1]
    assert bool(frr.parse_config_load_errors(GR_LOG, running={"bgpd": GR_RUNNING}, config=conf)) is kept


def test_a_line_the_file_has_twice_needs_it_twice_in_the_running_config():
    conf = "router bgp 1\n a\nexit\nrouter bgp 1\n a\nexit\n"
    log = "line 5: Failure to communicate[13] to bgpd, line:  a\n"
    assert frr.parse_config_load_errors(log, running={"bgpd": "router bgp 1\n a\nexit\n"}, config=conf) == [
        "line 5: a (rejected by bgpd)"]


def test_line_1_can_be_cleared_and_a_line_past_the_file_cannot():
    log = "line {}: Failure to communicate[13] to bgpd, line: bgp x\n"
    assert frr.parse_config_load_errors(log.format(1), running={"bgpd": "bgp x\n"}, config="bgp x\n") == []
    assert frr.parse_config_load_errors(log.format(2), running={"bgpd": "bgp x\n"}, config="bgp x\n") == [
        "line 2: bgp x (rejected by bgpd)"]


def test_lines_end_at_crlf_too():
    assert frr._lines("a\r\nb\r\n") == ["a", "b"]


def test_a_blank_line_keeps_its_section():
    assert frr.config_sections("router bgp 1\n\n a\n") == [
        ((), "router bgp 1"), (("router bgp 1",), ""), (("router bgp 1",), "a")]


@pytest.mark.parametrize("close", ["exit", "end", "exit-vni", "! note"])
def test_a_closing_line_is_never_a_header(close):
    assert frr.config_sections(f"router bgp 1\n {close}\n  a\n")[2] == (("router bgp 1",), "a")


def test_significant_lines_drop_blanks_and_comments():
    assert frr._significant(["a", "", " ! c", " b"]) == ["a", "b"]


@pytest.mark.parametrize("conf, i, header", [
    ("router bgp 65000\n a\n", 0, True),   # deeper, though shorter
    ("router bgp 1\n\n a\n", 0, True),     # a blank line between
    ("router bgp 1\n! c\n a\n", 0, True),  # a comment between
    (" a\n b\n", 0, False),                # the same depth
])
def test_is_header(conf, i, header):
    assert frr._is_header(conf, i) is header


RB = "router bgp 1\n a\n"


@pytest.mark.parametrize("conf, i, running, applied", [
    ("router bgp 1\n\ta\n", 1, RB, True),                         # a tab-indented line is under its header
    ("router bgp 1\n a\n\tb\n", 1, RB, False),                    # a later tab-indented line is in the block
    ("router bgp 1\n a\n b\n", 1, RB, False),                     # so is a later space-indented one
    ("router bgp 1\n a\nrouter bgp 2\n", 1, RB, True),            # the next block is not
    ("router bgp 1\n a\n b\nrouter bgp 2\n", 1, RB + " b\n", True),
    ("router bgp 1\n x\n y\n a\n", 3, "router bgp 1\n x\n y\n a\n", True),
    ("router bgp 0\n z\nrouter bgp 1\n a\n", 3, RB, True),        # nor the block before
    (" a\n", 0, "a\n", True),
    (" a\n b\n", 0, "a\n b\n", True),                            # a file that starts indented
    (" a\n", 0, "router bgp 1\n\ta\n", False),                    # a running line under a tab is in its block
    ("router bgp 1\n a\n", 1, "router bgp 1\n\ta\n", True),
])
def test_block_applied_edges(conf, i, running, applied):
    assert frr._block_applied(conf, i, running) is applied


def _unreadable(tmp_path, monkeypatch, stderr):
    lab = BootLogLab(World(), {"r1": GR_LOG})
    lab.running, lab.conf = {"r1": ExecResult([], 1, "", stderr)}, {"r1": GR_CONF}
    return _run(tmp_path, monkeypatch, lab).error


def test_an_unreadable_running_config_without_a_reason_says_so(tmp_path, monkeypatch):
    assert "(not checked against the running config: it could not be read)" in _unreadable(tmp_path, monkeypatch, "")


def test_the_reason_keeps_the_last_200_characters(tmp_path, monkeypatch):
    err = _unreadable(tmp_path, monkeypatch, "y" + "x" * 200)
    assert "(not checked against the running config: " + "x" * 200 + ")" in err


def test_frr_conf_and_a_daemon_file_on_the_same_line_number_keep_their_order():
    log = ("line 5: % Unknown command: foo\n"
           "2026/10/30 10:00:00 1d: bad on config line 5: bar\n")
    assert frr.parse_config_load_errors(log) == ["line 5: foo (Unknown command)", "line 5: bar (bad, 1d)"]


def test_daemon_files_are_told_apart_by_their_lowercase_name():
    log = ("2026/10/30 10:00:00 ss: bad on config line 3: foo\n"
           "2026/10/30 10:00:00 ß: bad on config line 3: bar\n")
    assert frr.parse_config_load_errors(log) == ["line 3: foo (bad, ss)", "line 3: bar (bad, ß)"]


def test_no_running_config_is_read_without_a_failure_to_communicate(tmp_path, monkeypatch):
    lab = BootLogLab(World(), {"r2": "line 3: % Unknown command: foo\n"})
    lab.conf = {"r2": ExecResult([], 1, "", "No such file")}
    rep = _run(tmp_path, monkeypatch, lab)
    assert rep.status == "error" and "not checked" not in rep.error and lab.daemons_read == []
