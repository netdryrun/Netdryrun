"""MCP server: tools are registered and the no-lab tools work."""
import asyncio
import json
import os
import sys
from pathlib import Path

import pytest

pytest.importorskip("mcp")

from mcp import ClientSession, StdioServerParameters  # noqa: E402
from mcp.client.stdio import stdio_client  # noqa: E402

EXAMPLE = str(Path(__file__).parents[1] / "examples" / "frr-bgp")


async def _call(tool: str, args: dict) -> tuple[list[str], str]:
    # the same environment as the tests (the MCP client otherwise passes only a minimal one)
    params = StdioServerParameters(command=sys.executable, args=["-m", "netdryrun", "mcp"], env=dict(os.environ))
    async with stdio_client(params) as (r, w):
        async with ClientSession(r, w) as s:
            await s.initialize()
            tools = [t.name for t in (await s.list_tools()).tools]
            res = await s.call_tool(tool, args)
            return tools, res.content[0].text


def test_tools_and_validate_over_stdio():
    tools, text = asyncio.run(_call("validate", {"path": EXAMPLE}))
    assert {"dry_run", "run_checks", "validate", "check_types", "record_baseline"} <= set(tools)
    data = json.loads(text)
    assert data["valid"] and len(data["checks"]) == 7


def test_validate_reports_errors():
    _, text = asyncio.run(_call("validate", {"path": "/nonexistent"}))
    assert json.loads(text)["valid"] is False


@pytest.mark.skipif(os.name != "posix", reason="the server runs on Linux")
def test_windows_paths_reach_the_server_in_wsl(tmp_path, monkeypatch):
    # Claude Code on Windows with the server in WSL: the agent's file tools know C:\lab, the server needs /mnt/c/lab
    from netdryrun import mcp_server
    (tmp_path / "c").mkdir()
    monkeypatch.setattr(mcp_server, "WSL_MOUNTS", tmp_path)
    assert mcp_server._host_path(r"C:\Users\me\lab") == f"{tmp_path}/c/Users/me/lab"
    assert mcp_server._host_path("c:/Users/me/lab/netdryrun.yml") == f"{tmp_path}/c/Users/me/lab/netdryrun.yml"
    assert mcp_server._host_path("/home/me/lab") == "/home/me/lab"
    assert mcp_server._host_path("lab") == "lab"
    assert mcp_server._host_path(r"Q:\lab") == r"Q:\lab"  # no such drive mounted: left as it is
    lab = tmp_path / "c" / "lab"
    lab.mkdir()
    (lab / "topology.clab.yml").write_text("name: t\ntopology:\n  nodes:\n    r1: {kind: linux, image: frr}\n")
    (lab / "netdryrun.yml").write_text("lab: topology.clab.yml\nchecks:\n  - {type: route, node: r1, prefix: 10.0.0.0/24}\n")
    assert json.loads(mcp_server.validate(r"C:\lab"))["valid"] is True


@pytest.mark.skipif(os.name != "posix", reason="the server runs on Linux")
def test_windows_paths_stay_inside_netdryrun_mcp_root(tmp_path, monkeypatch):
    # a Windows path is translated first, then held to NETDRYRUN_MCP_ROOT like any other: .. can't step outside
    from netdryrun import mcp_server
    monkeypatch.setattr(mcp_server, "WSL_MOUNTS", tmp_path)
    for name in ("lab", "other"):
        d = tmp_path / "c" / name
        d.mkdir(parents=True)
        (d / "topology.clab.yml").write_text("name: t\ntopology:\n  nodes:\n    r1: {kind: linux, image: frr}\n")
        (d / "netdryrun.yml").write_text("lab: topology.clab.yml\nchecks:\n  - {type: route, node: r1, prefix: 10.0.0.0/24}\n")
    monkeypatch.setenv("NETDRYRUN_MCP_ROOT", str(tmp_path / "c" / "lab"))
    assert json.loads(mcp_server.validate(r"C:\lab"))["valid"] is True
    out = json.loads(mcp_server.validate(r"C:\lab\..\other"))
    assert out["valid"] is False and "outside NETDRYRUN_MCP_ROOT" in out["error"]


def _two_labs(tmp_path):
    for name in ("lab", "other"):
        d = tmp_path / name
        d.mkdir()
        (d / "topology.clab.yml").write_text("name: t\ntopology:\n  nodes:\n    r1: {kind: linux, image: frr}\n")
        (d / "netdryrun.yml").write_text("lab: topology.clab.yml\nchecks:\n  - {type: route, node: r1, prefix: 10.0.0.0/24}\n")
        (d / "netdryrun-report.json").write_text(f'{{"lab": "{name}"}}')
    elsewhere = tmp_path / "server-cwd"
    elsewhere.mkdir()
    return elsewhere


class _Ran(Exception):
    pass


def test_relative_paths_resolve_against_a_single_mcp_root(tmp_path, monkeypatch):
    # an agent passes netdryrun.yml relative to its project; the server's own working directory is elsewhere
    from netdryrun import mcp_server
    monkeypatch.chdir(_two_labs(tmp_path))
    monkeypatch.setenv("NETDRYRUN_MCP_ROOT", str(tmp_path / "lab"))
    for path in ("netdryrun.yml", ".", "./netdryrun.yml"):
        out = json.loads(mcp_server.validate(path))
        assert out["valid"] is True, out
        assert out["lab"] == str((tmp_path / "lab" / "topology.clab.yml").resolve())
    assert json.loads(mcp_server.last_report("."))["lab"] == "lab"
    # the topology is read from the root too (the server's cwd has none)
    err = json.loads(mcp_server.record_baseline("missing.clab.yml", deploy=False))["error"]
    assert str(tmp_path / "lab" / "missing.clab.yml") in err

    seen = []

    def fake_run(cfg, **_):
        seen.append(cfg.path)
        raise _Ran
    monkeypatch.setattr(mcp_server, "run", fake_run)
    for tool in (mcp_server.dry_run, mcp_server.run_checks):
        with pytest.raises(_Ran):
            tool("netdryrun.yml")
    assert seen == [(tmp_path / "lab" / "netdryrun.yml").resolve()] * 2


def test_relative_paths_cannot_escape_a_single_mcp_root(tmp_path, monkeypatch):
    from netdryrun import mcp_server
    monkeypatch.chdir(_two_labs(tmp_path))
    monkeypatch.setenv("NETDRYRUN_MCP_ROOT", str(tmp_path / "lab"))
    out = json.loads(mcp_server.validate("../other"))
    assert out["valid"] is False and "outside NETDRYRUN_MCP_ROOT" in out["error"]
    assert "outside NETDRYRUN_MCP_ROOT" in json.loads(mcp_server.record_baseline("../other/topology.clab.yml"))["error"]
    assert mcp_server.last_report("../other") == "{}"
    out = json.loads(mcp_server.dry_run("../other/netdryrun.yml"))
    assert out["status"] == "error" and "outside NETDRYRUN_MCP_ROOT" in out["error"]


@pytest.mark.parametrize("roots", ["", "lab+other"])
def test_relative_paths_without_a_single_root_ask_for_an_absolute_path(tmp_path, monkeypatch, roots):
    # no root, or several: there is no one folder to resolve against, so say what to pass instead of guessing
    from netdryrun import mcp_server
    _two_labs(tmp_path)
    monkeypatch.chdir(tmp_path / "lab")   # even a cwd that holds the file is not a guess we make
    monkeypatch.setattr(mcp_server, "run", lambda *a, **k: (_ for _ in ()).throw(_Ran()))   # never a real lab
    if roots:
        monkeypatch.setenv("NETDRYRUN_MCP_ROOT", os.pathsep.join(str(tmp_path / r) for r in roots.split("+")))
    else:
        monkeypatch.delenv("NETDRYRUN_MCP_ROOT", raising=False)
    for err in (json.loads(mcp_server.validate("netdryrun.yml"))["error"],
                json.loads(mcp_server.dry_run("netdryrun.yml"))["error"],
                json.loads(mcp_server.run_checks("netdryrun.yml"))["error"],
                json.loads(mcp_server.record_baseline("topology.clab.yml", deploy=False))["error"]):
        assert "relative path" in err and "absolute path" in err and "such as /" in err
        assert "outside NETDRYRUN_MCP_ROOT" not in err
    assert mcp_server.last_report(".") == "{}"


def test_relative_path_that_names_two_files_is_refused(tmp_path, monkeypatch):
    # 0.3.2 cold review, finding 1: the agent works in a worktree inside the root; the same relative path also
    # names the main checkout's copy under the root. Picking either one silently could test the unedited file.
    from netdryrun import mcp_server
    for d in (tmp_path / "a", tmp_path / "wt" / "a"):
        d.mkdir(parents=True)
        (d / "topology.clab.yml").write_text("name: t\ntopology:\n  nodes:\n    r1: {kind: linux, image: frr}\n")
        (d / "netdryrun.yml").write_text("lab: topology.clab.yml\nchecks:\n  - {type: route, node: r1, prefix: 10.0.0.0/24}\n")
    monkeypatch.setenv("NETDRYRUN_MCP_ROOT", str(tmp_path))
    monkeypatch.chdir(tmp_path / "wt")
    monkeypatch.setattr(mcp_server, "run", lambda *a, **k: (_ for _ in ()).throw(_Ran()))   # never a real lab
    for err in (json.loads(mcp_server.validate("a/netdryrun.yml"))["error"],
                json.loads(mcp_server.dry_run("a"))["error"],
                json.loads(mcp_server.record_baseline("a/topology.clab.yml", deploy=False))["error"]):
        assert "absolute path" in err and str(tmp_path / "wt" / "a") in err
    assert mcp_server.last_report("a") == "{}"
    # only the working-directory copy exists inside the root: that one, as before 0.3.2
    import shutil
    shutil.rmtree(tmp_path / "a")
    assert json.loads(mcp_server.validate("a"))["lab"] == str((tmp_path / "wt" / "a" / "topology.clab.yml").resolve())


def _hash(p):
    import hashlib
    return hashlib.sha256(p.read_bytes()).hexdigest()


def test_the_result_names_the_files_it_tested(tmp_path, monkeypatch):
    # agent eval T06: a run on the unedited folder looked like a run of the change. The result now carries a
    # sha256 of netdryrun.yml, the topology and every config file the topology binds or loads, so a pasted
    # verdict can be tied to the exact files it ran.
    from netdryrun import mcp_server
    from netdryrun.runner import RunReport
    lab = tmp_path / "lab"
    (lab / "configs").mkdir(parents=True)
    (lab / "configs" / "r1.conf").write_text("router bgp 65001\n")
    (lab / "configs" / "daemons").write_text("bgpd=yes\n")
    (lab / "startup").mkdir()
    (lab / "startup" / "r2.cfg").write_text("set / system name r2\n")
    outside = tmp_path / "elsewhere.conf"
    outside.write_text("secret\n")
    (lab / "topology.clab.yml").write_text(
        "name: t\ntopology:\n  defaults:\n    binds: [configs/daemons:/etc/frr/daemons]\n  nodes:\n"
        "    r1: {kind: linux, image: frr, binds: ['configs/r1.conf:/etc/frr/frr.conf:ro', '" + str(outside) + ":/x']}\n"
        "    r2: {kind: nokia_srlinux, image: srl, startup-config: startup/r2.cfg}\n")
    (lab / "netdryrun.yml").write_text("lab: topology.clab.yml\nchecks:\n  - {type: route, node: r1, prefix: 10.0.0.0/24}\n")
    seen = {}

    def fake_run(cfg, deploy, keep, **_):
        seen["deploy"] = deploy
        return RunReport(config=cfg, results=[])
    monkeypatch.setattr(mcp_server, "run", fake_run)
    out = json.loads(mcp_server.dry_run(str(lab)))
    assert out["tested"] == {"config": str((lab / "netdryrun.yml").resolve()), "lab_deployed_by_this_run": True, "files": {
        "netdryrun.yml": _hash(lab / "netdryrun.yml"), "topology.clab.yml": _hash(lab / "topology.clab.yml"),
        "configs/daemons": _hash(lab / "configs" / "daemons"), "configs/r1.conf": _hash(lab / "configs" / "r1.conf"),
        "startup/r2.cfg": _hash(lab / "startup" / "r2.cfg"),
        "../elsewhere.conf": _hash(outside)}, "complete": True}   # a file outside the folder is used too (a shared config)
    # NETDRYRUN_MCP_ROOT still confines what is read: a file outside it is not hashed, and the list says it is partial
    monkeypatch.setenv("NETDRYRUN_MCP_ROOT", str(lab))
    confined = json.loads(mcp_server.dry_run(str(lab)))["tested"]
    assert "../elsewhere.conf" not in confined["files"] and confined["complete"] is False
    monkeypatch.delenv("NETDRYRUN_MCP_ROOT")
    # run_checks tests a lab that is already running: the files on disk may not be what it runs
    assert json.loads(mcp_server.run_checks(str(lab)))["tested"]["lab_deployed_by_this_run"] is False
    # an edit changes the hash
    (lab / "configs" / "r1.conf").write_text("router bgp 65009\n")
    assert json.loads(mcp_server.dry_run(str(lab)))["tested"]["files"]["configs/r1.conf"] != out["tested"]["files"]["configs/r1.conf"]


def test_tested_is_not_complete_when_the_topology_uses_files_it_cannot_list(tmp_path, monkeypatch):
    # 0.3.2 multi-vendor audit: containerlab also reads files from topology groups, license and env-files, expands
    # ~ and ${VAR}, and downloads URLs. A list that can't follow those must not claim to be complete.
    from netdryrun import mcp_server
    from netdryrun.runner import RunReport
    monkeypatch.setattr(mcp_server, "run", lambda cfg, **_: RunReport(config=cfg, results=[]))
    lab = tmp_path / "lab"
    lab.mkdir()
    (lab / "netdryrun.yml").write_text("lab: topology.clab.yml\nchecks:\n  - {type: route, node: r1, prefix: 10.0.0.0/24}\n")
    (lab / "g.cfg").write_text("group config\n")
    (lab / "lic.txt").write_text("licence\n")

    def tested(nodes_extra="", top=""):
        (lab / "topology.clab.yml").write_text(
            f"name: t\ntopology:\n{top}  nodes:\n    r1: {{kind: linux, image: frr{nodes_extra}}}\n")
        return json.loads(mcp_server.dry_run(str(lab)))["tested"]

    assert tested()["complete"] is True
    t = tested(top="  groups:\n    edge: {startup-config: g.cfg}\n")              # group-level files are listed
    assert t["complete"] is True and "g.cfg" in t["files"]
    t = tested(nodes_extra=", license: lic.txt")
    assert "lic.txt" in t["files"]
    for extra in (", startup-config: 'https://example.invalid/r1.cfg'", ", startup-config: '${HOME}/r1.cfg'",
                  ", binds: ['~/.ssh/id_rsa:/tmp/k:ro']", ", env-files: [vars.env]"):
        assert tested(nodes_extra=extra)["complete"] is False, extra


def test_tested_names_the_config_that_ran(tmp_path, monkeypatch):
    # with a relative path, the agent can see which netdryrun.yml the server picked
    from netdryrun import mcp_server
    from netdryrun.runner import RunReport
    monkeypatch.setattr(mcp_server, "run", lambda cfg, **_: RunReport(config=cfg, results=[]))
    _two_labs(tmp_path)
    monkeypatch.setenv("NETDRYRUN_MCP_ROOT", str(tmp_path / "lab"))
    monkeypatch.chdir(tmp_path / "server-cwd")
    assert json.loads(mcp_server.dry_run("netdryrun.yml"))["tested"]["config"] == str((tmp_path / "lab" / "netdryrun.yml").resolve())


def test_the_report_write_never_follows_a_hardlink(tmp_path, monkeypatch):
    # 0.3.2 multi-vendor audit: write_text on a hardlinked netdryrun-report.json would rewrite the other file
    from netdryrun import mcp_server
    from netdryrun.runner import RunReport
    monkeypatch.setattr(mcp_server, "run", lambda cfg, **_: RunReport(config=cfg, results=[]))
    _two_labs(tmp_path)
    outside = tmp_path / "outside.txt"
    outside.write_text("keep me\n")
    report = tmp_path / "lab" / "netdryrun-report.json"
    report.unlink()
    os.link(outside, report)
    out = json.loads(mcp_server.dry_run(str(tmp_path / "lab")))
    assert outside.read_text() == "keep me\n" and out["evidence_file"] == str(report)
    assert json.loads(report.read_text())["status"] == "failed"
