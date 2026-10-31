"""0.3.3 (a) and cold review 1-3: the Action's PR comment step is a thin call to netdryrun.comment, wired to the
lab path, the PR head commit and the expected author. Runs the step's own script, taken from action.yml."""
import http.server
import json
import re
import subprocess
import sys
import threading
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
ACTION = yaml.safe_load((ROOT / "action.yml").read_text(encoding="utf-8"))
STEP = next(s for s in ACTION["runs"]["steps"] if s.get("name") == "Comment on the pull request")


def step_script() -> str:
    m = re.search(r"<<'EOF'\n(.*?)\n\s*EOF\n", STEP["run"], re.S)
    assert m, "the comment step no longer runs an inline Python heredoc: update this test"
    lines = m.group(1).splitlines()
    indent = min(len(x) - len(x.lstrip()) for x in lines if x.strip())
    return "\n".join(x[indent:] for x in lines)


def test_the_step_is_wired_to_the_lab_the_head_commit_and_the_author():
    env = STEP["env"]
    # the lab: the checks file in mode run, the topology in mode verify (0.4)
    assert env["NDR_LABEL"] == "${{ inputs.mode == 'verify' && inputs.topology || inputs.path }}"
    assert env["NDR_MODE"] == "${{ inputs.mode }}" and env["NDR_JSON"] == "${{ inputs.json-report }}"
    assert env["NDR_COMMIT"] == "${{ github.event.pull_request.head.sha }}"
    assert env["NDR_AUTHOR"] == "${{ inputs.comment-author }}"
    assert env["NDR_STATUS"] == "${{ steps.result.outputs.status }}"
    assert ACTION["inputs"]["comment-author"]["default"] == "github-actions[bot]"
    assert "exit 0" not in STEP["run"].split("<<'EOF'")[0]   # no early exit: a run with no report still posts


class Fake(http.server.BaseHTTPRequestHandler):
    calls: list = []

    def _reply(self, code, data):
        raw = json.dumps(data).encode()
        self.send_response(code)
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):  # noqa: N802
        self._reply(200, [])

    def do_POST(self):  # noqa: N802
        Fake.calls.append((self.path, json.loads(self.rfile.read(int(self.headers["Content-Length"])))["body"]))
        self._reply(201, {"id": 1})

    def log_message(self, *a):
        pass


def test_a_run_with_no_report_posts_an_error_header_for_the_head_commit(tmp_path):
    Fake.calls = []
    srv = http.server.HTTPServer(("127.0.0.1", 0), Fake)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    sha = "ab" * 20
    env = {"PATH": "", "PYTHONPATH": str(ROOT / "src"), "GH_TOKEN": "t", "NDR_COMMENT_API": f"http://127.0.0.1:{srv.server_port}",
           "NDR_REPO": "o/r", "NDR_PR": "3", "NDR_COMMIT": sha, "NDR_LABEL": "examples/frr-bgp",
           "NDR_AUTHOR": "github-actions[bot]", "NDR_VERDICT": "nope.json", "NDR_SUMMARY": "nope.md", "NDR_STATUS": ""}
    p = subprocess.run([sys.executable, "-c", step_script()], cwd=tmp_path, env=env, capture_output=True, text=True)
    srv.shutdown()
    assert p.returncode == 0, p.stderr
    (path, text), = Fake.calls
    assert path == "/repos/o/r/issues/3/comments"
    lines = text.split("\n")
    assert lines[0] == "<!-- netdryrun-comment examples/frr-bgp -->"
    head = json.loads(re.search(r"\{.*\}", lines[1]).group(0))
    assert head["status"] == "error" and head["commit"] == sha


def test_a_verify_job_posts_the_verify_header_from_its_report(tmp_path):
    """mode: verify writes no agent result (verdict-report): the header comes from the verify report, so an
    approved change never reads as error, and a run-mode verdict never appears."""
    from netdryrun.verify import report as vr
    Fake.calls = []
    srv = http.server.HTTPServer(("127.0.0.1", 0), Fake)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    (tmp_path / "netdryrun-report.json").write_text(json.dumps(
        {"schema": vr.SCHEMA, "status": "matched", "verdict": vr.VERDICTS["matched"], "undeclared": [],
         "not_happened": [], "guards": {"passed": 3, "failed": 0}}), encoding="utf-8")
    env = {"PATH": "", "PYTHONPATH": str(ROOT / "src"), "GH_TOKEN": "t", "NDR_COMMENT_API": f"http://127.0.0.1:{srv.server_port}",
           "NDR_REPO": "o/r", "NDR_PR": "3", "NDR_COMMIT": "cd" * 20, "NDR_LABEL": "lab/topology.clab.yml",
           "NDR_AUTHOR": "github-actions[bot]", "NDR_VERDICT": "netdryrun-verdict.json", "NDR_SUMMARY": "nope.md",
           "NDR_STATUS": "matched", "NDR_MODE": "verify", "NDR_JSON": "netdryrun-report.json"}
    p = subprocess.run([sys.executable, "-c", step_script()], cwd=tmp_path, env=env, capture_output=True, text=True)
    srv.shutdown()
    assert p.returncode == 0, p.stderr
    (_, text), = Fake.calls
    head = json.loads(re.search(r"\{.*\}", text.split("\n")[1]).group(0))
    assert head["schema"] == "netdryrun.verify/v1" and head["status"] == "matched"
    assert head["verdict"] == "INTENT MATCHED" and "CHECKS PASSED" not in text


def test_without_netdryrun_installed_the_step_only_warns(tmp_path):
    # -S: no site-packages, so the package can't be imported (an install step that failed)
    p = subprocess.run([sys.executable, "-S", "-c", step_script()], cwd=tmp_path, env={"PATH": ""},
                       capture_output=True, text=True)
    assert p.returncode == 0 and "::warning" in p.stdout


# ------------------------------------------- 0.3.3 audit (Grok): a directory committed at a report path

RUN = next(s for s in ACTION["runs"]["steps"] if s.get("name") == "Run Netdryrun")


def removal_loop() -> str:
    run = RUN["run"]
    start = run.index("for f in ")
    end = run.index("done", start) + len("done")
    return run[start:end].replace("sudo ", "")


def test_a_committed_directory_at_a_report_path_is_removed_but_never_the_workspace(tmp_path):
    ws = tmp_path / "ws"
    (ws / "netdryrun-report.json").mkdir(parents=True)     # planted by a PR: the report write would fail
    (ws / "netdryrun-report.json" / "x").write_text("x")
    (ws / "keep.txt").write_text("keep")
    env = {"PATH": "/usr/bin:/bin", "NDR_JSON": "netdryrun-report.json", "NDR_JUNIT": ".", "NDR_VERDICT": ".."}
    subprocess.run(["bash", "-c", removal_loop()], cwd=ws, env=env, check=True)
    assert not (ws / "netdryrun-report.json").exists()
    assert (ws / "keep.txt").exists() and ws.exists() and tmp_path.exists()   # "." and ".." untouched
