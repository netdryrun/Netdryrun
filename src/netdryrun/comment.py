"""The PR comment (GitHub Action) and MR note (GitLab component) an agent reads (0.3.3).

One comment per lab, marked `<!-- netdryrun-comment <lab path> -->`, updated in place on every run. It starts
with agent_result.pr_comment_header: status, verdict, counts and the commit tested, held to the run's checked
status. A run that wrote no report still rewrites it, as error, so a header from an older commit never stands
for a newer one. Only a comment by the expected author is updated: anyone else's comment with the marker is
ignored. Every problem here is a warning; a comment never changes a test result.
"""
from __future__ import annotations

import json
import re
import urllib.request

from .agent_result import pr_comment_header

MARK = "<!-- netdryrun-comment"
NO_REPORT = ("*Netdryrun wrote no report for this run: it did not start, or stopped before writing one. The job "
             "log says why. This says nothing about the change.*\n")
MAX_PAGES = 30   # 3,000 comments
MAX_BODY = 65000   # GitHub rejects a comment over 65,536 characters; the header must always fit
CUT = "\n\n*The summary was cut to fit the comment limit; the full report is in the job's artifact.*\n"


def marker(label: str) -> str:
    """The first line of this lab's comment. The label is the lab path, reduced to safe characters."""
    safe = re.sub(r"[^A-Za-z0-9._/-]", "_", str(label))[:200] or "."
    return f"{MARK} {safe} -->"


def body(verdict_path: str, status: str, summary_path: str, label: str, commit: str | None) -> str:
    """The comment for one run: marker, header, then the Markdown summary (or a no-report line). The agent
    result counts only when it agrees with the run's checked status; otherwise the header reads error."""
    try:
        result = json.load(open(verdict_path, encoding="utf-8"))
    except (OSError, ValueError):
        result = {}
    if not isinstance(result, dict) or result.get("status") != status:
        result = {}
    try:
        summary = open(summary_path, encoding="utf-8").read()
    except OSError:
        summary = NO_REPORT
    # The summary quotes device output (in failed checks' evidence): it must not carry a second marker or a
    # look-alike header that a reader could take for the real one, so no HTML comment opens in it
    summary = summary.replace("<!--", "&lt;!--")
    head = marker(label) + "\n" + pr_comment_header(result, commit=commit) + "\n"
    if len(head) + len(summary) > MAX_BODY:
        summary = summary[:MAX_BODY - len(head) - len(CUT)] + CUT
    return head + summary


def _call(method: str, url: str, headers: dict, data=None, timeout: float = 30):
    req = urllib.request.Request(url, method=method, headers={**headers, "Content-Type": "application/json"},
                                 data=json.dumps(data).encode() if data is not None else None)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def _pages(url: str, headers: dict):
    for page in range(1, MAX_PAGES + 1):
        items = _call("GET", f"{url}{'&' if '?' in url else '?'}per_page=100&page={page}", headers)
        yield from items
        if len(items) < 100:
            return


def upsert_github(api: str, repo: str, pr: str, token: str, author: str, mark: str, text: str) -> str:
    h = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"}
    own = next((c["id"] for c in _pages(f"{api}/repos/{repo}/issues/{pr}/comments", h)
                if str(c.get("body", "")).startswith(mark) and (c.get("user") or {}).get("login") == author), None)
    if own is None:
        _call("POST", f"{api}/repos/{repo}/issues/{pr}/comments", h, {"body": text})
        return "created"
    _call("PATCH", f"{api}/repos/{repo}/issues/comments/{own}", h, {"body": text})
    return "updated"


def upsert_gitlab(api: str, project: str, iid: str, token: str, mark: str, text: str) -> str:
    h = {"PRIVATE-TOKEN": token}
    me = _call("GET", f"{api}/user", h)["id"]   # the token's own user: only its notes are updated
    url = f"{api}/projects/{project}/merge_requests/{iid}/notes"
    own = next((n["id"] for n in _pages(url + "?sort=asc", h)
                if str(n.get("body", "")).startswith(mark) and (n.get("author") or {}).get("id") == me), None)
    if own is None:
        _call("POST", url, h, {"body": text})
        return "created"
    _call("PUT", f"{url}/{own}", h, {"body": text})
    return "updated"


def main_github(env) -> int:
    """The Action's comment step. Reads NDR_* variables (see action.yml); always exits 0."""
    try:
        text = body(env.get("NDR_VERDICT", ""), env.get("NDR_STATUS", ""), env.get("NDR_SUMMARY", ""),
                    env.get("NDR_LABEL", ""), env.get("NDR_COMMIT"))
        done = upsert_github(env.get("NDR_COMMENT_API", "https://api.github.com"), env["NDR_REPO"], env["NDR_PR"],
                             env.get("GH_TOKEN", ""), env.get("NDR_AUTHOR", "github-actions[bot]"),
                             marker(env.get("NDR_LABEL", "")), text)
        print(f"Netdryrun: PR comment {done}")
    except Exception as e:
        print(f"::warning title=Netdryrun::could not comment on the PR ({type(e).__name__}: {e}); needs permissions "
              "pull-requests: write, and fork PRs can't be commented on. An older Netdryrun comment may still "
              "be there: its header names the commit it describes")
    return 0


def main_gitlab(env) -> int:
    """The GitLab component's merge request note. Reads NDR_* and CI_* variables; always exits 0."""
    iid, var = env.get("CI_MERGE_REQUEST_IID", ""), env.get("NDR_TOKEN_VAR", "")
    if env.get("NDR_MR_COMMENT") != "true" or not iid:
        return 0
    token = env.get(var, "")
    if not token:
        print(f"WARNING: Netdryrun: no merge request note: set the masked CI/CD variable {var} to a project access "
              "token with the api scope (https://github.com/netdryrun/netdryrun/blob/main/templates/README.md"
              "#merge-request-note)")
        return 0
    try:
        status = ""
        try:
            lines = open("netdryrun.env", encoding="utf-8").read().splitlines()
            status = dict(x.split("=", 1) for x in lines if "=" in x).get("NETDRYRUN_STATUS", "")
        except OSError:
            pass
        commit = env.get("CI_MERGE_REQUEST_SOURCE_BRANCH_SHA") or env.get("CI_COMMIT_SHA")
        text = body(env.get("NDR_VERDICT", ""), status, env.get("NDR_MARKDOWN", ""), env.get("NDR_PATH", ""), commit)
        done = upsert_gitlab(env["CI_API_V4_URL"], env["CI_PROJECT_ID"], iid, token, marker(env.get("NDR_PATH", "")), text)
        print(f"Netdryrun: merge request note {done}")
    except Exception as e:
        print(f"WARNING: Netdryrun: could not write the merge request note ({type(e).__name__}); the result is unchanged. "
              "An older Netdryrun note may still be there: its header names the commit it describes")
    return 0
