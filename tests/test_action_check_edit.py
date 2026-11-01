"""The Action in mode: run, on a pull request that changes the checks and the configs together (0.4; expert war
game): the PR would grade its own change. It fails before any lab boots unless `allow-check-edit: true`, which a
workflow sets only where branch protection requires a code-owner review of netdryrun.yml, as the intent rule does
in mode: verify. A PR that changes only configs, or only checks, runs as before; a push (no PR) is not checked."""
import os
import subprocess
import sys
from pathlib import Path

import pytest

from test_action_verify import ACTION, git, merged, python_of, step

EDITED = "checks and configs changed in the same PR"


@pytest.fixture
def repo(tmp_path):
    r = tmp_path / "repo"
    (r / "lab" / "configs").mkdir(parents=True)
    git(r, "init", "-q")
    (r / "lab" / "netdryrun.yml").write_text("lab: topology.clab.yml\nchecks: []\n")
    (r / "lab" / "topology.clab.yml").write_text("name: t\n")
    (r / "lab" / "configs" / "r1.conf").write_text("! r1\n")
    (r / "README.md").write_text("readme\n")
    git(r, "add", ".")
    git(r, "commit", "-q", "-m", "base")
    return r


def change(r: Path, files: dict[str, str]) -> str:
    for name, text in files.items():
        (r / name).write_text(text)
    git(r, "add", ".")
    git(r, "commit", "-q", "-m", "change")
    return git(r, "rev-parse", "HEAD").strip()


def check(r: Path, base: str, head: str, path="lab", allow="false", merge=None):
    out = r / "gh-output.txt"
    out.write_text("")
    merge = merged(r, base, head) if merge is None else merge
    env = {**os.environ, "NDR_PATH": path, "NDR_BASE": base, "NDR_HEAD": head, "NDR_MERGE": merge,
           "NDR_ALLOW_CHECK_EDIT": allow, "GITHUB_OUTPUT": str(out)}
    p = subprocess.run([sys.executable, "-c", python_of("Check the checks file")], cwd=r, env=env,
                       capture_output=True, text=True)
    summary = r / "netdryrun-summary.md"
    return p.returncode, p.stdout + p.stderr, summary.read_text(encoding="utf-8") if summary.exists() else None


def test_the_step_runs_in_mode_run_on_pull_requests_only_before_any_lab_boots():
    s = step("Check the checks file")
    assert s["if"] == "inputs.mode == 'run' && github.event_name == 'pull_request'"
    assert s["env"]["NDR_MERGE"] == "${{ github.sha }}" and s["env"]["NDR_ALLOW_CHECK_EDIT"] == "${{ inputs.allow-check-edit }}"
    assert ACTION["inputs"]["allow-check-edit"]["default"] == "false"
    names = [x.get("name") for x in ACTION["runs"]["steps"]]
    assert names.index("Check the checks file") < names.index("Install containerlab") < names.index("Run Netdryrun")


def test_checks_and_configs_changed_together_fail(repo):
    b = git(repo, "rev-parse", "HEAD").strip()
    h = change(repo, {"lab/netdryrun.yml": "lab: topology.clab.yml\nchecks: []\n# weakened\n",
                      "lab/configs/r1.conf": "! r1 leaks\n"})
    code, log, summary = check(repo, b, h)
    assert code == 1 and EDITED in log and summary.startswith("### ⚠️ Netdryrun: ERROR: NO VERDICT")
    for allow in ("True", "yes", ""):
        assert check(repo, b, h, allow=allow)[0] == 1
    code, log, _ = check(repo, b, h, allow="true")
    assert code == 0 and "::warning" in log and EDITED in log
    # path given as the file itself
    assert check(repo, b, h, path="lab/netdryrun.yml")[0] == 1


@pytest.mark.parametrize("files", [{"lab/configs/r1.conf": "! r1 changed\n"},
                                   {"lab/netdryrun.yml": "lab: topology.clab.yml\nchecks: []\n# more\n"},
                                   {"README.md": "docs\n", "lab/netdryrun.yml": "lab: topology.clab.yml\nchecks: []\n#\n"}])
def test_configs_alone_or_checks_alone_run(repo, files):
    b = git(repo, "rev-parse", "HEAD").strip()
    h = change(repo, files)
    code, log, _ = check(repo, b, h)
    assert code == 0, log


def test_a_merge_commit_that_is_not_this_prs_is_refused(repo):
    b = git(repo, "rev-parse", "HEAD").strip()
    h = change(repo, {"lab/configs/r1.conf": "! r1 changed\n"})
    code, log, _ = check(repo, b, h, merge=b)
    assert code == 1 and "merge commit" in log


def test_a_workflow_changed_with_the_configs_is_refused(repo):
    """Gauntlet 0.4, R7: the workflow sets `path:` and allow-check-edit, so a PR that changes it with the configs
    controls which checks grade it."""
    base = git(repo, "rev-parse", "HEAD").strip()
    (repo / ".github" / "workflows").mkdir(parents=True)
    head = change(repo, {".github/workflows/ci.yml": "allow-check-edit: true\n", "lab/configs/r1.conf": "! leak\n"})
    rc, out, summary = check(repo, base, head, allow="true")
    assert rc == 1 and ".github/workflows/ci.yml" in out and "workflow" in summary
    for left in ("netdryrun-summary.md", "gh-output.txt"):   # the first check's outputs: not part of the next PR
        (repo / left).unlink(missing_ok=True)
    head = change(repo, {".github/workflows/ci.yml": "only the workflow\n"})
    assert check(repo, git(repo, "rev-parse", "HEAD~1").strip(), head)[0] == 0   # no lab change: runs as before


def test_cold_2_a_workflow_that_moves_path_away_from_the_changed_lab_is_refused(repo):
    """The PR repoints `path:` to an untouched lab and changes the real one: the guard keyed on `path` saw no lab
    change. Any workflow change together with a change outside .github/workflows is refused."""
    base = git(repo, "rev-parse", "HEAD").strip()
    (repo / ".github" / "workflows").mkdir(parents=True)
    (repo / "demo").mkdir()
    head = change(repo, {".github/workflows/ci.yml": "path: demo\n", "lab/configs/r1.conf": "! leak\n"})
    rc, out, _ = check(repo, base, head, path="demo")
    assert rc == 1 and "workflow" in out


def test_cold_2_a_local_composite_action_counts_as_the_workflow(repo):
    base = git(repo, "rev-parse", "HEAD").strip()
    (repo / ".github" / "actions" / "ndr").mkdir(parents=True)
    head = change(repo, {".github/actions/ndr/action.yml": "allow-check-edit: true\n", "lab/configs/r1.conf": "! x\n"})
    assert check(repo, base, head)[0] == 1
