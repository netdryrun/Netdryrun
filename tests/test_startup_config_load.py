"""Startup config the NOS rejected, on Arista cEOS, Nokia SR Linux and SONiC (0.4; scheduled in 0.3.3's limits).

Captured live on 2026-10-30 (cEOS 4.36.3M, SR Linux 26.7.2, docker-sonic-vs master.1258173):
- cEOS loads its startup config line by line and skips a line it rejects, like FRR; `show startup-config errors`
  lists each one ("% Invalid input at line N") or says "No errors were found in startup-config.".
- SR Linux: containerlab applies the startup config as one commit; a line that doesn't parse, or a commit that
  fails, fails containerlab's deploy (rc 1), so the lab never runs a partial config.
- SONiC (docker-sonic-vs) has no startup config: Netdryrun configures it with setup commands, each checked. A
  config file bound into it is not checked, so it is an error, never a silent pass.
Anything that can't be read is an error (fail closed), as on FRR."""
from pathlib import Path

import pytest

from netdryrun import runner
from netdryrun.drivers import eos
from netdryrun.drivers.base import DriverError
from netdryrun.lab import ExecResult, Node

FIX = Path(__file__).parent / "fixtures"


def text(name):
    return (FIX / name).read_text(encoding="utf-8")


def test_eos_lists_each_rejected_startup_line():
    assert eos.parse_startup_config_errors(text("eos_startup_config_errors_clean.txt")) == []
    assert eos.parse_startup_config_errors(text("eos_startup_config_errors_one.txt")) == [
        "line 10: neighbor 10.0.12.2 defualt-originate (Invalid input)"]
    assert eos.parse_startup_config_errors(text("eos_startup_config_errors_two.txt")) == [
        "line 5: neighbor 10.0.12.2 defualt-originate (Invalid input)",
        "line 6: neighbor 10.0.12.2 maximum-routes twelve (Invalid input)"]


@pytest.mark.parametrize("out", ["", "% Invalid input at line 1\n", "Total 2 errors found in startup-config.\n\n\n"
                                 ">    x\n\n% Invalid input at line 5\nerrors in startup-config: 2\n",
                                 "some other text\n"])
def test_eos_output_it_can_not_account_for_is_an_error(out):
    """A count that doesn't match the lines found, or text it doesn't know, is never read as clean."""
    with pytest.raises(DriverError):
        eos.parse_startup_config_errors(out)


class Lab:
    def __init__(self, nodes: dict, outputs: dict | None = None, binds: str = ""):
        self.nodes = {n: Node(n, f"clab-t-{n}", kind, image) for n, (kind, image) in nodes.items()}
        self.outputs = outputs or {}
        self.topology = None
        self.binds = binds
        self.ran = []

    def exec(self, node, cmd, timeout=60, input=None):
        self.ran.append((node, cmd))
        rc, out = self.outputs.get(node, (0, text("eos_startup_config_errors_clean.txt")))
        return ExecResult(cmd, rc, out, "" if rc == 0 else "Cli: not ready")

    def boot_log(self, node):
        return ExecResult([], 0, "[45|bgpd] sending configuration\n", "")


CEOS = ("arista_ceos", "ceos:4.36.3M")
SRL = ("nokia_srlinux", "ghcr.io/nokia/srlinux:26.7.2")
SONIC = ("sonic-vs", "docker-sonic-vs:master.1258173-c10162df4")


def by_node(lab, sonic_binds=()):
    return runner.config_load_by_node(lab, runner._driver_of(runner.Config(path=Path("t.yml"), lab=Path("t.clab.yml"), timeout=60, checks=[])),
                                      bound=lambda name: list(sonic_binds))


def test_a_ceos_line_rejected_at_boot_makes_the_run_an_error():
    lab = Lab({"ceos1": CEOS}, {"ceos1": (0, text("eos_startup_config_errors_one.txt"))})
    found = by_node(lab)
    assert found == {"ceos1": ["line 10: neighbor 10.0.12.2 defualt-originate (Invalid input)"]}
    msg = runner.rejected_config_message(found)
    assert "ceos1: line 10" in msg and "NOS rejected configuration lines" in msg
    assert lab.ran == [("ceos1", ["Cli", "-p", "15", "-c", "show startup-config errors"])]


def test_a_clean_ceos_boot_is_clean():
    assert by_node(Lab({"ceos1": CEOS})) == {"ceos1": []}


def test_a_ceos_whose_errors_can_not_be_read_is_an_error():
    found = by_node(Lab({"ceos1": CEOS}, {"ceos1": (1, "")}))
    assert "could not be read" in found["ceos1"][0]


def test_sr_linux_is_checked_by_containerlabs_deploy():
    """Its startup config is one commit containerlab applies at deploy: a rejected line fails the deploy, so a
    running SR Linux node ran its whole config. Nothing to read after the run."""
    lab = Lab({"srl1": SRL}, {"srl1": (1, "")})
    assert by_node(lab) == {"srl1": []}


def test_sonic_without_bound_config_is_clean_and_with_it_is_an_error():
    assert by_node(Lab({"sonic1": SONIC})) == {"sonic1": []}
    found = by_node(Lab({"sonic1": SONIC}), sonic_binds=["configs/frr.conf:/etc/frr/frr.conf"])
    assert "not checked" in found["sonic1"][0] and "setup" in found["sonic1"][0]


def test_the_report_records_each_platforms_load():
    rep = runner.RunReport(config=runner.Config(path=Path("t.yml"), lab=Path("t.clab.yml"), timeout=60, checks=[]))
    lab = Lab({"ceos1": CEOS, "srl1": SRL}, {"srl1": (1, "")})
    lab.image_digest = lambda image: None

    class Drv:
        def __init__(self, name):
            self.name = name

        def nos_version(self):
            return None
    runner._config_load(lab, lambda n: Drv({"ceos1": "eos", "srl1": "srlinux"}[n]), rep, by_node(lab))
    assert rep.environment["nodes"]["ceos1"]["config_load"] == "clean"
    assert rep.environment["nodes"]["srl1"]["config_load"] == "clean"


def test_ceos_output_it_can_not_read_is_named():
    found = by_node(Lab({"ceos1": CEOS}, {"ceos1": (0, "% Invalid input\n")}))
    assert "unexpected output" in found["ceos1"][0] and "unknown" in found["ceos1"][0]


def test_the_binds_a_sonic_node_gets_are_read_from_the_topology(tmp_path):
    topo = tmp_path / "t.clab.yml"
    topo.write_text("name: t\ntopology:\n  defaults: {binds: [shared/a:/opt/x]}\n  nodes:\n"
                    "    sonic1: {kind: sonic-vs, binds: [configs/frr.conf:/etc/frr/frr.conf]}\n"
                    "    sonic2: {kind: sonic-vs}\n")
    lab = Lab({"sonic1": SONIC, "sonic2": SONIC})
    lab.topology = topo
    assert runner._bound_files(lab, "sonic1") == ["shared/a:/opt/x", "configs/frr.conf:/etc/frr/frr.conf"]
    found = runner.config_load_by_node(lab, runner._driver_of(runner.Config(path=Path("t.yml"), lab=topo, timeout=60,
                                                                            checks=[])))
    assert found["sonic2"] == [] and "not checked" in found["sonic1"][0]
    lab.topology = tmp_path / "missing.clab.yml"           # unreadable: an error, never clean
    assert "could not be read" in runner._bound_files(lab, "sonic1")[0]


# ===================================== Layer 6 multi-vendor audit (2026-10-30) ==================================

def test_audit_f2_under_check_sr_linux_and_sonic_are_not_verified():
    """`netdryrun check` runs on a lab it didn't deploy: SR Linux's deploy may have failed (the container keeps
    running with an empty config), and no setup command ran on SONiC. Neither can be called clean."""
    lab = Lab({"srl1": SRL, "sonic1": SONIC, "ceos1": CEOS})
    found = runner.config_load_by_node(lab, runner._driver_of(runner.Config(path=Path("t.yml"), lab=Path("t.clab.yml"),
                                                                            timeout=60, checks=[])),
                                       bound=lambda name: [], deployed=False)
    assert "srl1" not in found and "sonic1" not in found          # recorded as "not verified on <driver>"
    assert found["ceos1"] == []                                    # cEOS lists its own errors either way


@pytest.mark.parametrize("bind", ["./etc:/etc", "./root:/", "t:/usr/share/sonic/device/x", "s:/etc/supervisor/conf.d/b.conf",
                                  "c:/var/lib/frr/frr.conf"])
def test_audit_f6_any_bind_into_a_sonic_config_place_is_an_error(bind):
    found = by_node(Lab({"sonic1": SONIC}), sonic_binds=[bind])
    assert "not checked" in found["sonic1"][0], bind


def test_audit_f6_an_inline_startup_config_reaches_its_node(tmp_path):
    from netdryrun.verify import run as vrun
    topo = tmp_path / "t.clab.yml"
    topo.write_text("name: t\ntopology:\n  nodes:\n    s1:\n      kind: sonic-vs\n      startup-config: |\n"
                    "        hostname s1\n        router bgp 1\n")
    assert vrun.bind_reach(topo) == {"(inline startup-config)": [("s1", "startup-config")]}


def test_audit_f7_a_node_without_a_driver_is_recorded_as_not_verified():
    rep = runner.RunReport(config=runner.Config(path=Path("t.yml"), lab=Path("t.clab.yml"), timeout=60, checks=[]))
    lab = Lab({"h1": ("linux", "alpine:3")})
    lab.image_digest = lambda image: None

    def driver_for(n):
        raise DriverError("no driver")
    runner._config_load(lab, driver_for, rep, {})
    assert rep.environment["nodes"]["h1"]["config_load"] == "not verified (no routing driver)"


def test_audit_f4_verify_reads_the_config_load_of_an_unobserved_node():
    """--unobserved (and hosts) map to "" in verify's node table; the config load of such a node is still read the
    way `run` reads it (by its detected driver, or its log when the driver is unknown)."""
    from netdryrun.lab import LabError
    from netdryrun.verify import run as vrun
    lab = Lab({"ceos1": CEOS}, {"ceos1": (0, text("eos_startup_config_errors_one.txt"))})
    with pytest.raises(LabError, match="ceos1: line 10"):
        vrun.check_config_loaded(lab, {"ceos1": ""}, "after")



# F1 (live, containerlab 0.81.1): a topology `exec:` command that fails is logged, and the deploy still exits 0.
# FRR then runs without the line (`vtysh -c ... defualt-originate`: rc=1, "% Unknown command"). Any platform.
EXEC_FAILED = """15:20:49 INFO Executed command node=r1 command="sleep 8" stdout=""
15:20:49 ERRO Failed to execute command command="vtysh -c conf t -c router bgp 65001 -c neighbor 10.0.12.2 defualt-originate" node=r1 rc=1
  stdout=
  │ % Unknown command: neighbor 10.0.12.2 defualt-originate
15:20:49 INFO Executed command node=r1 command="ip link set lo up" stdout=""
"""


def test_audit_f1_an_exec_command_that_failed_fails_the_deploy(monkeypatch, tmp_path):
    from netdryrun import lab as lab_mod
    topo = tmp_path / "t.clab.yml"
    topo.write_text("name: t\ntopology:\n  nodes:\n    r1: {kind: linux, image: quay.io/frrouting/frr:10.4.1}\n")
    lab = lab_mod.Lab(topo)
    monkeypatch.setattr(lab_mod, "_run", lambda cmd, **kw: ExecResult(cmd, 0, "", EXEC_FAILED))
    with pytest.raises(lab_mod.LabError) as e:
        lab.deploy()
    assert "r1" in str(e.value) and "defualt-originate" in str(e.value) and "exec" in str(e.value)
    monkeypatch.setattr(lab_mod, "_run", lambda cmd, **kw: ExecResult(cmd, 0, "", EXEC_FAILED.split("\n")[0]))
    lab.deploy()                                                    # every exec command ran: fine


# F3 (live, SR Linux 26.7.2): a JSON startup config SR Linux rejects is not a deploy failure (rc 0). SR Linux falls
# back and runs without it; /var/log/messages says so.
SRL_JSON_REJECTED = ("Oct 30 08:21:04 n1 sr_mgmt_server: debug|2808|2808|00023|TR||E: common    "
                     "db_configuration_checkpoint.cc:1192 InitialLoadAndCommitWithFallbacks  Load of startup "
                     "configuration failed: Error 'Schema '/network-instance/protocols/bgp' has no field 'peer-groop''\n")


def test_audit_f3_an_sr_linux_startup_config_it_failed_to_load_is_an_error():
    lab = Lab({"srl1": SRL}, {"srl1": (0, SRL_JSON_REJECTED)})
    found = by_node(lab)
    assert "failed to load its startup config" in found["srl1"][0] and "peer-groop" in found["srl1"][0]
    assert lab.ran[0][1][:2] == ["grep", "-h"]


def test_audit_f3_sr_linux_with_no_load_failure_is_clean_and_an_unreadable_log_is_not():
    assert by_node(Lab({"srl1": SRL}, {"srl1": (1, "")})) == {"srl1": []}            # grep: no such line
    found = by_node(Lab({"srl1": SRL}, {"srl1": (2, "")}))                           # grep: no such file
    assert "could not be read" in found["srl1"][0]
