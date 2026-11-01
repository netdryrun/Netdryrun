"""`netdryrun capture`: only a running containerlab lab node is a target, the commands are the driver's own, and a
bundle is accepted only when it replays through the driver, matches its hashes and is sanitised."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from netdryrun import cli
from netdryrun.capture import CaptureError, bundle, collect, guard
from netdryrun.lab import ExecResult, Lab

FIXTURES = Path(__file__).resolve().parent / "fixtures"
TOPO = """name: cap
topology:
  nodes:
    r1: {kind: linux, image: quay.io/frrouting/frr:10.4.1}
    r2: {kind: linux, image: quay.io/frrouting/frr:10.4.1}
    h1: {kind: host}
    x1: {kind: ext-container}
"""
LABELS = {"containerlab": "cap", "clab-node-name": "r1", "clab-node-kind": "linux"}

# What r1 answers: FRR 10.4.1 output captured live (tests/fixtures)
ANSWERS = {
    "show bgp neighbors json": "frr_bgp_neighbors.txt",
    "show ip route 192.168.20.0/24 json": "frr_route.txt",
    "show bgp ipv4 unicast 192.168.20.0/24 json": "frr_bgp_paths.txt",
    "show bgp ipv4 unicast 255.255.255.255/32 longer-prefixes json": "frr_bgp_table_header.txt",
}


@pytest.fixture
def topo(tmp_path):
    p = tmp_path / "lab" / "topology.clab.yml"
    p.parent.mkdir()
    p.write_text(TOPO, encoding="utf-8")
    return p


class Docker:
    """docker as seen by the guard and the lab: inspect answers with `labels`, exec answers from ANSWERS."""

    def __init__(self, labels=LABELS, running=True, exists=True):
        self.labels, self.running, self.exists = labels, running, exists
        self.calls: list[list[str]] = []

    def __call__(self, cmd, timeout=600, env=None, input=None, errors=None):
        self.calls.append(list(cmd))
        if cmd[:2] == ["docker", "inspect"]:
            if not self.exists:
                return ExecResult(cmd, 1, "", "Error: No such object: clab-cap-r1")
            return ExecResult(cmd, 0, f"{json.dumps(self.labels)} {'true' if self.running else 'false'}\n", "")
        if cmd[:3] == ["docker", "image", "inspect"]:
            return ExecResult(cmd, 0, '["quay.io/frrouting/frr@sha256:' + "ab" * 32 + '"]\n', "")
        if cmd[:2] == ["docker", "exec"]:
            assert cmd[2] == "clab-cap-r1", f"a command ran on {cmd[2]}"
            if cmd[3:5] == ["vtysh", "-c"] and cmd[5] in ANSWERS:
                return ExecResult(cmd, 0, (FIXTURES / ANSWERS[cmd[5]]).read_text(encoding="utf-8"), "")
            return ExecResult(cmd, 1, "% Unknown command", "")
        raise AssertionError(f"unexpected command {cmd}")

    def device_commands(self):
        return [c for c in self.calls if c[:2] == ["docker", "exec"]]


@pytest.fixture
def docker(monkeypatch):
    d = Docker()
    monkeypatch.setattr("netdryrun.capture.guard._run", d)
    monkeypatch.setattr("netdryrun.lab._run", d)
    return d


# ---- the guard: nothing but a running containerlab node of this lab ------------------------------------------------
def test_a_running_lab_node_is_accepted(topo, docker):
    lab, node = guard.lab_node(topo, "r1")
    assert node.container == "clab-cap-r1" and docker.device_commands() == []


@pytest.mark.parametrize("labels,why", [
    ({}, "not node 'r1' of containerlab lab 'cap'"),                                         # a container someone started
    ({"containerlab": "other", "clab-node-name": "r1"}, "not node 'r1'"),                    # another lab's container
    ({"containerlab": "cap", "clab-node-name": "r2"}, "not node 'r1'"),                      # another node
])
def test_a_container_that_is_not_this_lab_node_is_refused(topo, monkeypatch, labels, why):
    d = Docker(labels=labels)
    monkeypatch.setattr("netdryrun.capture.guard._run", d)
    with pytest.raises(CaptureError, match=why):
        guard.lab_node(topo, "r1")
    assert d.device_commands() == []


def test_a_missing_or_stopped_container_is_refused(topo, monkeypatch):
    for d, why in ((Docker(exists=False), "deploy the lab first"), (Docker(running=False), "is not running")):
        monkeypatch.setattr("netdryrun.capture.guard._run", d)
        with pytest.raises(CaptureError, match=why):
            guard.lab_node(topo, "r1")


@pytest.mark.parametrize("node", ["h1", "x1"])
def test_nodes_containerlab_does_not_run_are_refused_before_docker_is_asked(topo, docker, node):
    with pytest.raises(CaptureError, match="capture only runs on lab nodes"):
        guard.lab_node(topo, node)
    assert docker.calls == []


@pytest.mark.parametrize("node", ["192.0.2.1", "core1.example.net", "r9"])
def test_an_address_or_hostname_is_not_a_target(topo, docker, node):
    with pytest.raises(CaptureError, match="is not in"):
        guard.lab_node(topo, node)
    assert docker.calls == []


def test_a_file_that_is_not_a_topology_is_refused(tmp_path, docker):
    p = tmp_path / "inventory.yml"
    p.write_text("hosts:\n  core1: {ansible_host: 192.0.2.1}\n", encoding="utf-8")
    with pytest.raises(CaptureError, match="not a containerlab topology"):
        guard.lab_node(p, "core1")
    assert docker.calls == []


def test_the_recording_lab_runs_commands_only_on_the_captured_node(topo, docker):
    lab = Lab(topo)
    rec = collect.RecordingLab(lab, "r1")
    with pytest.raises(CaptureError, match="runs only on 'r1'"):
        rec.exec("r2", ["vtysh", "-c", "show bgp neighbors json"])
    with pytest.raises(CaptureError, match="read commands only"):
        rec.exec("r1", ["vtysh"], input="configure terminal\n")
    assert docker.device_commands() == []


@pytest.mark.parametrize("argv,why", [
    (["--node", "192.0.2.1"], "is not in"),
    (["--node", "h1"], "lab nodes"),
])
def test_the_cli_refuses_and_runs_nothing(topo, docker, tmp_path, capsys, argv, why):
    code = cli.main(["capture", str(topo), "--scenario", "established", "--out", str(tmp_path / "b"), *argv])
    assert code == 2 and why in capsys.readouterr().err
    assert docker.device_commands() == [] and not (tmp_path / "b").exists()


def test_the_cli_refuses_a_container_with_the_name_but_not_the_labels(topo, monkeypatch, tmp_path, capsys):
    d = Docker(labels={"maintainer": "someone"})
    monkeypatch.setattr("netdryrun.capture.guard._run", d)
    monkeypatch.setattr("netdryrun.lab._run", d)
    code = cli.main(["capture", str(topo), "--node", "r1", "--scenario", "established", "--out", str(tmp_path / "b")])
    assert code == 2 and "not node 'r1' of containerlab lab 'cap'" in capsys.readouterr().err
    assert d.device_commands() == []


# ---- the capture and its bundle ------------------------------------------------------------------------------------
def _capture(topo, tmp_path, *extra, scenario="established"):
    out = tmp_path / "bundle"
    code = cli.main(["capture", str(topo), "--node", "r1", "--scenario", scenario, "--out", str(out), *extra])
    return code, out


def test_capture_records_exactly_the_driver_commands(topo, docker, tmp_path):
    code, out = _capture(topo, tmp_path, "--nos-version", "10.4.1")
    assert code == 0
    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    argvs = [c["argv"] for c in manifest["commands"]]
    assert argvs == [c[3:] for c in docker.device_commands()]          # every command the driver sent, nothing else
    assert ["vtysh", "-c", "show bgp neighbors json"] in argvs
    assert manifest["nos"] == "frr" and manifest["scenario"] == "established" and manifest["shows_scenario"] is True
    assert manifest["image_digest"].startswith("quay.io/frrouting/frr@sha256:")
    assert manifest["nos_version_reported"] == "10.4.1" and manifest["sanitizer"] is None
    problems = bundle.validate(out)[0]
    assert "not sanitised by this version's `netdryrun sanitize`, or its self-check failed" in problems
    assert any("IPv4 address 1.1.1.1" in p for p in problems)       # router IDs from public space: not shareable


def test_a_scenario_the_lab_does_not_show_is_flagged(topo, docker, tmp_path, capsys):
    code, out = _capture(topo, tmp_path, scenario="no-neighbor")       # every session in the capture is up
    assert code == 1 and "don't show" in capsys.readouterr().err
    assert json.loads((out / "manifest.json").read_text(encoding="utf-8"))["shows_scenario"] is False


@pytest.mark.parametrize("argv,why", [
    (["--scenario", "route-present"], "needs --prefix"),
    (["--scenario", "route-present", "--prefix", "192.168.20.1/24"], "host bits zero"),
    (["--scenario", "ping-reply"], "needs --target"),
    (["--scenario", "ping-reply", "--target", "core1"], "not an IP address"),
])
def test_scenario_options_are_checked_before_docker_is_asked(topo, docker, tmp_path, capsys, argv, why):
    code = cli.main(["capture", str(topo), "--node", "r1", "--out", str(tmp_path / "b"), *argv])
    assert code == 2 and why in capsys.readouterr().err and docker.calls == []


def test_an_existing_folder_is_never_overwritten(topo, docker, tmp_path, capsys):
    (tmp_path / "bundle").mkdir()
    (tmp_path / "bundle" / "keep.txt").write_text("mine")
    code, _ = _capture(topo, tmp_path)
    assert code == 2 and "not empty" in capsys.readouterr().err
    assert (tmp_path / "bundle" / "keep.txt").read_text() == "mine"


def _sanitised(topo, docker, tmp_path, scenario="established", extra=()):
    code, out = _capture(topo, tmp_path, *extra, scenario=scenario)
    assert code == 0
    assert cli.main(["sanitize", str(out), "--hostname", "r2", "--confirm"]) == 0
    return out, tmp_path / "bundle-sanitized", tmp_path / "bundle.sanitize-map.json"


def test_sanitise_without_confirm_writes_nothing(topo, docker, tmp_path, capsys):
    _, out = _capture(topo, tmp_path)
    assert cli.main(["sanitize", str(out)]) == 0
    assert "--confirm" in capsys.readouterr().out
    assert not (tmp_path / "bundle-sanitized").exists() and not (tmp_path / "bundle.sanitize-map.json").exists()


def test_a_sanitised_bundle_validates_and_the_mapping_stays_outside_it(topo, docker, tmp_path):
    raw, out, mapping = _sanitised(topo, docker, tmp_path, "as-path", ("--prefix", "192.168.20.0/24"))
    assert bundle.validate(out) == ([], [])
    m = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    assert m["sanitizer"]["self_check"] == "passed" and m["node"] == "host-1" and m["shows_scenario"] is True
    assert mapping.exists() and not list(out.rglob("*map*"))
    text = "".join(p.read_text(encoding="utf-8") for p in out.rglob("*") if p.is_file())
    for original in ("192.168.20.0", "2.2.2.2", '"remoteAs":65002', '"hostname":"r2"'):
        assert original not in text
    assert all("192-168" not in c["file"] for c in m["commands"])     # file names spell the mapped prefix only


def test_sanitising_twice_is_refused(topo, docker, tmp_path, capsys):
    _, out, _ = _sanitised(topo, docker, tmp_path)
    assert cli.main(["sanitize", str(out), "--out", str(tmp_path / "again")]) == 2
    assert "already sanitised" in capsys.readouterr().err


# ---- a tampered bundle is rejected --------------------------------------------------------------------------------
def _manifest(out):
    return json.loads((out / "manifest.json").read_text(encoding="utf-8"))


def _neighbors(m):
    return next(c for c in m["commands"] if "neighbors" in " ".join(c["argv"]))


def _save(out, m):
    (out / "manifest.json").write_text(json.dumps(m, indent=2), encoding="utf-8")


def test_an_output_edited_after_the_capture_is_rejected(topo, docker, tmp_path):
    _, out, _ = _sanitised(topo, docker, tmp_path)
    f = out / _neighbors(_manifest(out))["file"]
    f.write_text(f.read_text(encoding="utf-8").replace("Established", "Idle"), encoding="utf-8")
    assert "sha256 doesn't match" in bundle.validate(out)[0][0]


def test_an_edited_output_with_a_fixed_hash_fails_replay(topo, docker, tmp_path):
    _, out, _ = _sanitised(topo, docker, tmp_path)
    m = _manifest(out)
    f = out / _neighbors(m)["file"]
    f.write_text(f.read_text(encoding="utf-8").replace("Established", "Idle"), encoding="utf-8")
    _neighbors(m)["sha256"] = bundle._sha(f.read_text(encoding="utf-8"))
    _save(out, m)
    problems = bundle.validate(out)[0]
    assert any("reads the outputs differently" in p for p in problems)


def test_a_hand_edited_reading_fails_replay(topo, docker, tmp_path):
    _, out, _ = _sanitised(topo, docker, tmp_path)
    m = _manifest(out)
    first = next(iter(m["reading"]["neighbors"].values()))
    first["prefixes"] = {"ipv4-unicast": 999}
    _save(out, m)
    assert any("reads the outputs differently" in p for p in bundle.validate(out)[0])


def test_an_extra_file_or_a_reordered_command_list_is_rejected(topo, docker, tmp_path):
    _, out, _ = _sanitised(topo, docker, tmp_path)
    (out / "outputs" / "99-extra.txt").write_text("{}")
    assert "doesn't list" in bundle.validate(out)[0][0]
    (out / "outputs" / "99-extra.txt").unlink()
    m = _manifest(out)
    m["commands"].reverse()
    _save(out, m)
    assert "command_list_sha256" in bundle.validate(out)[0][0]


def test_a_public_address_added_after_sanitising_is_rejected(topo, docker, tmp_path):
    _, out, _ = _sanitised(topo, docker, tmp_path)
    m = _manifest(out)
    m["commands"][0]["stderr"] = "peer 81.2.3.4 is down"
    _save(out, m)
    assert any("IPv4 address 81.2.3.4" in p for p in bundle.validate(out)[0])


def test_a_mislabelled_scenario_is_rejected(topo, docker, tmp_path):
    _, out, _ = _sanitised(topo, docker, tmp_path)
    m = _manifest(out)
    m["scenario"] = "no-neighbor"
    _save(out, m)
    assert any("don't show scenario no-neighbor" in p for p in bundle.validate(out)[0])


def test_a_file_outside_the_bundle_is_never_read(topo, docker, tmp_path):
    _, out, _ = _sanitised(topo, docker, tmp_path)
    m = _manifest(out)
    m["commands"][0]["file"] = "../bundle/manifest.json"
    _save(out, m)
    assert "outside the bundle" in bundle.validate(out)[0][0]


def test_every_scenario_says_what_it_shows():
    assert set(collect.SCENARIOS) >= {"established", "no-neighbor", "route-present", "route-absent",
                                      "received-not-selected", "community", "med", "no-med"}
    for name, sc in collect.SCENARIOS.items():
        assert sc.reads and sc.shows, name
