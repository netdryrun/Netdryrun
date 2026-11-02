"""Findings of the 0.4.1 release gate's Layer 5b acceptance run, each a test written before its fix: false passes
from the adversary angle (on fake state, no lab; the red-team corpus lists them in tests/redteam), and broken
documented paths from the system-integrator angle (the GitHub Action and the docs' YAML)."""
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import yaml

from netdryrun.verify.engine import match
from netdryrun.verify.intent import parse_intent_text
from netdryrun.verify.snapshot import (AsPath, BgpAttrs, BgpPath, ItemKey, NextHop, NodeSnapshot, PathNextHop,
                                       RibEntry, Session, Snapshot)
from test_action_verify import git, merged, python_of

ROOT = Path(__file__).parents[1]
FENCE = "`" * 3
P = "10.101.0.0/24"


def _attrs(as_path, nh):
    return BgpAttrs(origin="igp", as_path=AsPath.parse(as_path),
                    next_hops=(PathNextHop(nh, "global", True, True, 0, "eth1"),), local_pref=None, med=None,
                    weight=0, communities=(), ext_communities=(), large_communities=(), cluster_list=(),
                    originator_id=None, atomic_aggregate=False, aggregator=None)


def _rib(nh):
    hop = NextHop(nh, "eth1", None, True, True, True, False, False, False, "gateway", 1, (), None)
    return (RibEntry("bgp", None, True, True, 20, 0, None, 254, False, (hop,)),)


def _session(local):
    return Session(state="established", remote_as=65101, local_as=65000, afis=("ipv4-unicast",), local_address=local)


def test_with_from_pin_does_not_explain_a_path_from_an_undeclared_peer():
    """RT-0035. The intent approves the customer's block on edge1 learned *from the customer* (10.0.1.2, AS path
    65101). The change also opened the transit peer's inbound filter, so edge1 now holds a second path for the
    same prefix from 10.0.9.2 with a hijacker's origin AS 65666: not best today, best as soon as the customer
    session drops. The pin must explain only the path that matches it; 0.4.1 b61c325 explains both and says
    INTENT MATCHED."""
    base = {ItemKey("session", "edge1", "default", neighbor="10.0.1.2"): _session("10.0.1.1"),
            ItemKey("session", "edge1", "default", neighbor="10.0.9.2"): _session("10.0.9.1")}
    before = Snapshot({"edge1": NodeSnapshot("edge1", "frr", ("default",), dict(base), config=("router bgp 65000",))})
    after_items = dict(base)
    k = dict(kind="path", node="edge1", vrf="default", afi="ipv4", safi="unicast", prefix=P)
    after_items[ItemKey(**k, neighbor="10.0.1.2")] = BgpPath(_attrs("65101", "10.0.1.2"), True, False, True,
                                                             "external", "10.0.0.11")
    after_items[ItemKey(**k, neighbor="10.0.9.2")] = BgpPath(_attrs("65020 65666", "10.0.9.2"), False, False, True,
                                                             "external", "10.0.0.20")
    after_items[ItemKey("rib", "edge1", "default", "ipv4", "unicast", P, protocol="bgp")] = _rib("10.0.1.2")
    after = Snapshot({"edge1": NodeSnapshot("edge1", "frr", ("default",), after_items,
                                            config=("router bgp 65000", " neighbor 10.0.9.2 route-map ANY in"))})
    intent = parse_intent_text(f"""
intent:
  - prefix: {P}
    appears_on: [edge1]
    with: {{from: 10.0.1.2, as_path: "65101"}}
""")
    m = match(before, after, intent)
    assert m.status != "matched", "a path from an undeclared peer was explained by a pinned line"
    assert any(d.key.neighbor == "10.0.9.2" for d in m.undeclared)


# --- angle 3 (system integrator): documented CI templates -------------------------------------------------------



def test_every_yaml_block_in_the_docs_parses():
    """T-B2. A user copies these into a workflow or a config file: each one must at least be YAML. 0.4.1 b61c325's
    "Use the outputs in a later step" (github-action.md) has an unquoted `run: echo "... $NDR_STATUS: ..."`,
    which GitHub refuses to load."""
    block = re.compile(FENCE + r"ya?ml[^\n]*\n(.*?)" + FENCE, re.DOTALL)
    bad = []
    for md in [ROOT / "README.md", ROOT / "website" / "docs" / "llms-full.txt",
               *sorted((ROOT / "website" / "docs").rglob("*.md"))]:
        text = md.read_text(encoding="utf-8")
        for m in block.finditer(text):
            body = re.sub(r"^ {0,4}(?=\S)", "", m.group(1), flags=re.MULTILINE) if m.group(1).startswith("    ") else m.group(1)
            try:
                yaml.safe_load(body)
            except yaml.YAMLError as e:
                line = text[:m.start()].count("\n") + 1
                bad.append(f"{md.relative_to(ROOT)}:{line}: {str(e).splitlines()[0]}")
    assert not bad, "\n".join(bad)


def test_the_check_step_works_after_a_shallow_checkout(tmp_path):
    """T-B1. actions/checkout fetches only github.sha (the merge commit) at depth 1, which every documented workflow
    uses. The merge commit is then present but has no parents in the clone, so "Check the checks file" refused
    every pull request ("github.sha is not this pull request's merge commit"): the product's own CI on pull
    requests has failed this way since 31 Oct (v0.4.0 has the same step). A PR that changes only a config must
    pass this step with the default checkout."""
    origin = tmp_path / "origin"
    (origin / "lab" / "configs").mkdir(parents=True)
    git(origin, "init", "-q")
    (origin / "lab" / "netdryrun.yml").write_text("lab: topology.clab.yml\nchecks: []\n")
    (origin / "lab" / "topology.clab.yml").write_text("name: t\n")
    (origin / "lab" / "configs" / "r1.conf").write_text("! r1\n")
    git(origin, "add", ".")
    git(origin, "commit", "-q", "-m", "base")
    base = git(origin, "rev-parse", "HEAD").strip()
    (origin / "lab" / "configs" / "r1.conf").write_text("! r1 changed\n")
    git(origin, "commit", "-q", "-am", "change")
    head = git(origin, "rev-parse", "HEAD").strip()
    merge = merged(origin, base, head)
    git(origin, "update-ref", "refs/pull/1/merge", merge)
    # what actions/checkout does on pull_request with its default fetch-depth: 1
    work = tmp_path / "work"
    work.mkdir()
    git(work, "init", "-q")
    git(work, "remote", "add", "origin", origin.as_uri())
    git(work, "fetch", "-q", "--no-tags", "--depth=1", "origin", "+refs/pull/1/merge:refs/remotes/pull/1/merge")
    git(work, "checkout", "-q", "--detach", merge)
    out = work / "gh-output.txt"
    env = {**os.environ, "NDR_PATH": "lab", "NDR_BASE": base, "NDR_HEAD": head, "NDR_MERGE": merge,
           "NDR_ALLOW_CHECK_EDIT": "false", "GITHUB_OUTPUT": str(out)}
    p = subprocess.run([sys.executable, "-c", python_of("Check the checks file")], cwd=work, env=env,
                       capture_output=True, text=True)
    assert p.returncode == 0, p.stdout + p.stderr


ACTION = yaml.safe_load((ROOT / "action.yml").read_text(encoding="utf-8"))


def _steps():
    return ACTION["runs"]["steps"]


def _fake_sudo(tmp_path) -> dict:
    bin_ = tmp_path / "bin"
    bin_.mkdir(exist_ok=True)
    (bin_ / "sudo").write_text('#!/bin/sh\nexec "$@"\n')
    (bin_ / "sudo").chmod(0o755)
    return {**os.environ, "PATH": f"{bin_}{os.pathsep}{os.environ['PATH']}"}


def test_a_committed_verdict_never_reaches_the_artifact(tmp_path):
    """M4 (raised to BLOCKER). A PR can commit netdryrun-verdict.json saying "passed". In b61c325 the reports were
    removed only by "Run Netdryrun", which is skipped when a check step before it fails, while "Upload reports"
    always runs: the artifact (which agent-pr.md tells agents to read) carried the PR's file. The very first step
    must remove every report path, whatever happens after."""
    first = _steps()[0]
    assert first.get("name") == "Remove old reports" and first.get("if", "always()") == "always()"
    env = {**_fake_sudo(tmp_path), "NDR_JSON": "netdryrun-report.json", "NDR_JUNIT": "netdryrun-junit.xml",
           "NDR_VERDICT": "netdryrun-verdict.json"}
    ws = tmp_path / "ws"
    ws.mkdir()
    for f in ("netdryrun-report.json", "netdryrun-junit.xml", "netdryrun-summary.md", "netdryrun-comment.json"):
        (ws / f).write_text('{"status": "passed"}')
    (ws / "netdryrun-verdict.json").mkdir()   # a directory planted at a report path
    (ws / "netdryrun-verdict.json" / "x").write_text("x")
    (ws / "keep.txt").write_text("not a report")
    for k, v in first.get("env", {}).items():
        env.setdefault(k, v)
    p = subprocess.run(["bash", "-c", first["run"]], cwd=ws, env=env, capture_output=True, text=True)
    assert p.returncode == 0, p.stdout + p.stderr
    assert sorted(x.name for x in ws.iterdir()) == ["keep.txt"]
    names = [s.get("name") for s in _steps()]
    assert names.index("Remove old reports") < names.index("Check the checks file") < names.index("Upload reports")


def _read_result(tmp_path, rep, exit_code, mode="run") -> dict:
    (tmp_path / "r.json").write_text(json.dumps(rep))
    out = tmp_path / "out.txt"
    out.write_text("")
    env = {**os.environ, "NDR_JSON": str(tmp_path / "r.json"), "NDR_EXIT": exit_code, "GITHUB_OUTPUT": str(out),
           "NDR_MODE": mode}
    subprocess.run([sys.executable, "-c", python_of("Read result")], env=env, check=True)
    return dict(line.split("=", 1) for line in out.read_text().splitlines())


def _check(name, passed):
    return {"name": name, "type": "route", "params": {}, "passed": passed, "detail": "", "attempts": 1,
            "duration_s": 1.0, "history": [], "evidence": ""}


def test_exit_code_and_report_that_disagree_never_go_green(tmp_path):
    """M1 (raised to BLOCKER). The job was green when the CLI exited 0 with a report saying "passed" whose own
    counts or checks say a check failed. Any internal contradiction is status error, never a pass."""
    ok = {"schema": "netdryrun.report/v1", "status": "passed", "summary": {"passed": 2, "failed": 0},
          "checks": [_check("a", True), _check("b", True)], "inconclusive_reason": None}
    assert _read_result(tmp_path, ok, "0")["ok"] == "true"
    for bad in ({**ok, "summary": {"passed": 2, "failed": 1}},
                {**ok, "checks": [_check("a", True), _check("b", False)]},
                {**ok, "summary": {"passed": 3, "failed": 0}},
                {**ok, "checks": []}):
        out = _read_result(tmp_path, bad, "0")
        assert out["status"] == "error" and out["ok"] == "false", bad
    # the other direction is never green either: a failed report whose counts don't match its checks is error
    failed = {**ok, "status": "failed", "summary": {"passed": 1, "failed": 0}}
    assert _read_result(tmp_path, failed, "1")["status"] == "error"


def test_verify_matched_with_undeclared_differences_never_goes_green(tmp_path):
    """M1, mode: verify: INTENT MATCHED with an undeclared difference, a declared line that didn't happen or a
    failed standing guard contradicts itself."""
    base = {"schema": "netdryrun.verify/v1", "status": "matched", "verdict": "INTENT MATCHED", "declared": [{}],
            "undeclared": [], "not_happened": [], "guards": {"passed": 1, "failed": 0}, "inconclusive": None}
    assert _read_result(tmp_path, base, "0", "verify")["ok"] == "true"
    for bad in ({**base, "undeclared": [{}]}, {**base, "not_happened": [{}]}, {**base, "guards": {"passed": 1, "failed": 1}}):
        out = _read_result(tmp_path, bad, "0", "verify")
        assert out["status"] == "error" and out["ok"] == "false", bad


def _check_inputs(tmp_path, **env):
    step = next(s for s in _steps() if s.get("name") == "Check the inputs")
    defaults = {k: str(v.get("default", "")) for k, v in ACTION["inputs"].items()}
    e = {**os.environ}
    for var, expr in step["env"].items():   # each NDR_X is ${{ inputs.x }}: fill it with the input's default
        name = re.fullmatch(r"\$\{\{ inputs\.([a-z-]+) \}\}", expr).group(1)
        e[var] = env.get(name, defaults[name])
    p = subprocess.run(["bash", "-c", step["run"]], cwd=tmp_path, env=e, capture_output=True, text=True)
    return p.returncode, p.stdout + p.stderr


def test_an_input_the_mode_does_not_use_is_refused_by_name(tmp_path):
    """M2. In b61c325 mode: verify ignored `settle` (and every run-only input) silently, and mode: run ignored the
    verify inputs. An input set for the other mode is now an error naming it, before anything is installed."""
    assert _check_inputs(tmp_path)[0] == 0
    assert _check_inputs(tmp_path, mode="verify", topology="lab/t.clab.yml")[0] == 0
    assert _check_inputs(tmp_path, mode="verify", topology="lab/t.clab.yml", settle="30")[0] == 0   # verify has --settle
    for mode, name, value in (("verify", "path", "lab/"), ("verify", "allow-check-edit", "true"),
                              ("verify", "junit-report", "x.xml"), ("verify", "verdict-report", "v.json"),
                              ("run", "topology", "lab/t.clab.yml"), ("run", "allow-intent-edit", "true"),
                              ("run", "timeout", "900"), ("run", "unobserved", "host1"),
                              ("run", "intent-file", "ticket.yml")):
        extra = {"topology": "lab/t.clab.yml"} if mode == "verify" and name != "topology" else {}
        code, log = _check_inputs(tmp_path, mode=mode, **{name: value}, **extra)
        assert code == 1 and f"`{name}`" in log, (mode, name, log)
    code, log = _check_inputs(tmp_path, mode="Verify")
    assert code == 1 and "run or verify" in log
    names = [s.get("name") for s in _steps()]
    assert names.index("Check the inputs") < names.index("Install containerlab")
    assert "unobserved" in ACTION["inputs"]


def test_verify_passes_settle_and_unobserved_to_the_cli():
    cmd = next(s for s in _steps() if s.get("name") == "Run Netdryrun")["run"]
    verify = cmd[cmd.index("verify)"):cmd.index("code=$?", cmd.index("netdryrun verify"))]
    assert "--settle" in verify and "--unobserved" in verify
    # an empty settle means each command's own default (run 10 s, verify 15 s), never 10 s for verify
    assert ACTION["inputs"]["settle"]["default"] == ""


# --- the GitLab component (unlisted): the same rules as the Action -------------------------------------------

TEMPLATE = ROOT / "templates" / "netdryrun.yml"


def _gitlab_script() -> str:
    _, body = TEMPLATE.read_text(encoding="utf-8").split("\n---\n", 1)
    (job,) = yaml.safe_load(body).values()
    (script,) = job["script"]
    return script


def _heredoc(script: str, tag: str) -> str:
    return script.split(f"<<'{tag}'\n", 1)[1].split(f"\n{tag}\n", 1)[0]


def test_gitlab_job_is_never_green_without_a_matching_report(tmp_path):
    """M6. The job exited with Netdryrun's exit code even when its own dotenv said NETDRYRUN_STATUS=error (a
    report that is missing, or doesn't match the exit code or its own checks): exit 0 must mean status passed."""
    script = _gitlab_script()
    code = _heredoc(script, "EOF")
    good = {"status": "passed", "summary": {"passed": 1, "failed": 0}, "checks": [{"name": "a", "passed": True}]}
    for rep, want in ((good, "passed"), ({**good, "checks": [{"name": "a", "passed": False}]}, "error"),
                      ({**good, "checks": []}, "error")):
        (tmp_path / "r.json").write_text(json.dumps(rep))
        subprocess.run([sys.executable, "-c", code], cwd=tmp_path, check=True,
                       env={**os.environ, "NDR_JSON": str(tmp_path / "r.json"), "NDR_EXIT": "0"})
        assert f"NETDRYRUN_STATUS={want}" in (tmp_path / "netdryrun.env").read_text(), rep
    # after the dotenv, exit 0 with any status but passed becomes exit 2
    tail = script[script.index("<<'EOF'"):]
    assert re.search(r'NETDRYRUN_STATUS=passed.*\n.*NDR_EXIT=2', tail) or "NDR_EXIT=2" in tail
    assert script.rstrip().endswith('exit "$NDR_EXIT"')


def test_gitlab_mr_that_changes_checks_and_configs_together_is_refused(tmp_path):
    """M7. The Action refuses a PR that edits netdryrun.yml and the lab's configs together (it would grade its own
    change); the GitLab component had no such guard."""
    r = tmp_path / "repo"
    (r / "lab" / "configs").mkdir(parents=True)
    git(r, "init", "-q")
    (r / "lab" / "netdryrun.yml").write_text("lab: topology.clab.yml\nchecks: []\n")
    (r / "lab" / "configs" / "r1.conf").write_text("! r1\n")
    git(r, "add", ".")
    git(r, "commit", "-q", "-m", "base")
    base = git(r, "rev-parse", "HEAD").strip()
    (r / "lab" / "netdryrun.yml").write_text("lab: topology.clab.yml\nchecks: []\n# weakened\n")
    (r / "lab" / "configs" / "r1.conf").write_text("! r1 leaks\n")
    git(r, "commit", "-q", "-am", "change")
    guard = _heredoc(_gitlab_script(), "GUARD")

    def run(allow="false", source="merge_request_event"):
        env = {**os.environ, "CI_PIPELINE_SOURCE": source, "CI_MERGE_REQUEST_DIFF_BASE_SHA": base,
               "CI_COMMIT_SHA": git(r, "rev-parse", "HEAD").strip(), "NDR_PATH": "lab", "NDR_ALLOW_CHECK_EDIT": allow,
               "CI_CONFIG_PATH": ".gitlab-ci.yml"}
        p = subprocess.run([sys.executable, "-c", guard], cwd=r, env=env, capture_output=True, text=True)
        return p.returncode, p.stdout + p.stderr

    code, log = run()
    assert code != 0 and "checks and configs changed in the same merge request" in log
    assert run(allow="true")[0] == 0
    assert run(source="push")[0] == 0   # only merge requests are checked, as the Action checks pull requests only
    inputs = yaml.safe_load(TEMPLATE.read_text(encoding="utf-8").split("\n---\n", 1)[0])["spec"]["inputs"]
    assert inputs["allow-check-edit"]["default"] == "false"


# --- angle 2 (end user): a lab lock left by another user -------------------------------------------------------

def test_a_lab_lock_file_left_by_another_user_is_no_internal_error(tmp_path, monkeypatch):
    """F2 (end-user angle). acquire_lock opened /tmp/netdryrun-lab-<name>.lock in a+ mode and never removes it, created
    0644: after one run as another user (or with sudo, which troubleshooting.md suggests), every later run of that lab
    as this user ended in "internal error: PermissionError ... This is a Netdryrun bug". A lock file this user can't
    write must still lock (flock needs no write access), never stop the run."""
    import tempfile

    import pytest

    from netdryrun.lab import Lab

    if os.name != "posix" or os.geteuid() == 0:
        pytest.skip("needs a non-root POSIX user (root can write any file)")
    monkeypatch.setattr(tempfile, "gettempdir", lambda: str(tmp_path))
    topo = tmp_path / "t.clab.yml"
    topo.write_text("name: ndr-lock-perm\ntopology:\n  nodes:\n    r1: {}\n")
    stale = tmp_path / "netdryrun-lab-ndr-lock-perm.lock"
    stale.write_text("")
    stale.chmod(0o444)            # what another user's run leaves behind, as far as this user can tell
    lab = Lab(topo)
    lab.acquire_lock()            # b61c325: PermissionError
    lab.release_lock()


# --- angle 2 (end user): a VM node without KVM -----------------------------------------------------------------

def _fake_run(monkeypatch, tmp_path, kind="linux", dies_at=None):
    """The runner on a fake clock, a fake lab and a fake driver whose route never appears (so only the timeout or
    the lab can end the run). With dies_at, node r1's container stops at that time, as a VM node's does when qemu
    can't start."""
    from test_runner_robustness import FakeDriver, FakeLab, World, cfg, chk

    from netdryrun import runner

    w = World()
    lab = FakeLab(w, nodes=("r1",))
    lab.nodes["r1"] = lab.nodes["r1"].__class__("r1", "clab-t-r1", kind, "vrnetlab/cisco_n9kv:9300-10.4.8.M")

    def stopped():
        if dies_at is not None and w.t >= dies_at:
            return {"clab-t-r1": "qemu-system-x86_64: CPU model 'host' requires KVM or HVF"}
        return {}
    lab.stopped_containers = stopped
    from netdryrun.lab import Lab
    lab.kvm_problem = Lab.kvm_problem.__get__(lab)   # the real check, on the fake lab's nodes
    monkeypatch.setattr(runner, "_clock", w, raising=False)
    monkeypatch.setattr(runner, "_sleep", w.sleep, raising=False)
    monkeypatch.setattr(runner, "Lab", lambda path: lab)
    monkeypatch.setattr(runner, "for_node", lambda lab_, node, override=None: FakeDriver(w, routes=lambda _w, p: False))
    rep = runner.run(cfg(tmp_path, [chk("route", "r1 route", timeout=900, node="r1", prefix="10.0.0.0/24")]))
    return rep, lab, w


def test_a_node_container_that_dies_ends_the_run_at_once(tmp_path, monkeypatch):
    """F3 (end-user angle). With no KVM, a VM node's container exits right after deploy (qemu refuses to start), and
    b61c325 polled it until every check's timeout: no verdict after 23 minutes. A node whose container stopped can
    never answer: the run must end quickly as an error (exit 2), naming the node and its last log line."""
    rep, lab, w = _fake_run(monkeypatch, tmp_path, dies_at=20)
    assert rep.status == "error", rep.status
    assert "clab-t-r1" in rep.error and "requires KVM" in rep.error
    assert w.t < 120, f"noticed only after {w.t:.0f} s"
    assert lab.destroyed == 1


def test_a_healthy_lab_is_not_stopped_by_the_watch(tmp_path, monkeypatch):
    rep, _, _ = _fake_run(monkeypatch, tmp_path)
    assert rep.status == "failed" and not rep.error


def test_a_vm_node_without_kvm_is_refused_before_deploy(tmp_path, monkeypatch):
    """F3: a VM-based node (vrnetlab: NX-OS, RouterOS, Junos) on a host without /dev/kvm can't boot. Refuse before
    deploying, with exit 2 and a message that says so, instead of deploying a lab that can't come up."""
    import os.path as osp

    from netdryrun import lab as lab_mod

    real = osp.exists
    monkeypatch.setattr(lab_mod.os.path, "exists", lambda p: False if str(p) == "/dev/kvm" else real(p))
    monkeypatch.delenv("DOCKER_HOST", raising=False)
    rep, lab, _ = _fake_run(monkeypatch, tmp_path, kind="cisco_n9kv")
    assert rep.status == "error" and "KVM" in rep.error and "r1" in rep.error, rep.error
    assert lab.deployed == 0
