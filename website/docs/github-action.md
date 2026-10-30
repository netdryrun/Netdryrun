---
title: GitHub Action
description: Run Netdryrun in GitHub Actions with netdryrun/netdryrun@v0.3.3. Inputs, outputs, example workflows, and security notes for running privileged containerlab labs in CI.
---

# GitHub Action

The action installs containerlab, installs Netdryrun™, runs your checks, writes a summary to the job page, uploads the JSON and JUnit reports as an artifact, and fails the job if any check fails.

```yaml title=".github/workflows/network-dryrun.yml"
name: Network dry run
on: pull_request
jobs:
  dryrun:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: netdryrun/netdryrun@v0.3.3
        with:
          path: network/        # folder containing netdryrun.yml
```

It needs a Linux runner with Docker. GitHub-hosted `ubuntu-latest` runners work.

## Inputs

| Input | Default | Meaning |
|---|---|---|
| `path` | `.` | `netdryrun.yml` or the folder containing it |
| `containerlab-version` | `0.81.1` | containerlab version to install, pinned for reproducible runs. Empty means latest. If containerlab is already installed, it is used as is, with a warning if the version differs. |
| `json-report` | `netdryrun-report.json` | Path for the JSON evidence report |
| `junit-report` | `netdryrun-junit.xml` | Path for the JUnit XML report |
| `verdict-report` | `netdryrun-verdict.json` | Path for the agent result: status, verdict, failures and the sha256 of every file tested, in the shape the MCP tools return ([schema](https://netdryrun.com/schemas/mcp-result-v1.json)). Uploaded with the reports (from 0.3.3) |
| `upload-artifact` | `true` | Upload the reports as a workflow artifact |
| `artifact-name` | `netdryrun-report` | Name of the uploaded artifact |
| `settle` | `10` | Seconds to wait before post-convergence checks |
| `hold` | `10` | Seconds a post-convergence check must hold |
| `pr-comment` | `false` | On pull requests, post one comment with the verdict, failures first, and the evidence for each failed check. Updated in place on every push. Needs `permissions: pull-requests: write` |
| `comment-author` | `github-actions[bot]` | The account that writes the PR comment: only its comment is updated. Set it when `github-token` is another account's token (from 0.3.3) |
| `github-token` | `${{ github.token }}` | Token used for the PR comment |
| `cloud` | `false` | Reserved for Netdryrun Cloud, which is **not available yet**. With `true`, the action tries to POST the JSON report to `cloud-url` with a GitHub OIDC token; that address doesn't resolve today, so nothing is uploaded and you only get a warning ("evidence upload failed", or "needs 'permissions: id-token: write'" without that permission). Leave it off |
| `cloud-url` | `https://cloud.netdryrun.com` | Reserved for Netdryrun Cloud (this address does not exist yet) |

## Outputs

| Output | Meaning |
|---|---|
| `status` | `passed`, `failed`, `error` or `inconclusive` (the lab never reached a testable state, so the run says nothing about the change; the job still fails) |
| `inconclusive-reason` | Why the run was inconclusive; empty otherwise |
| `passed` | Number of passed checks |
| `failed` | Number of failed checks |
| `evidence-url` | Reserved for Netdryrun Cloud; always empty today |

## Examples

### Only run when network files change

```yaml
name: Network dry run
on:
  pull_request:
    paths:
      - "network/**"
jobs:
  dryrun:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: netdryrun/netdryrun@v0.3.3
        with:
          path: network/
```

### Use the outputs in a later step

```yaml
      - uses: netdryrun/netdryrun@v0.3.3
        id: ndr
        with:
          path: network/
      - if: always()
        env:
          NDR_STATUS: ${{ steps.ndr.outputs.status }}
          NDR_PASSED: ${{ steps.ndr.outputs.passed }}
          NDR_FAILED: ${{ steps.ndr.outputs.failed }}
        run: echo "Netdryrun $NDR_STATUS: $NDR_PASSED passed, $NDR_FAILED failed"
```

### Several labs

```yaml
jobs:
  dryrun:
    runs-on: ubuntu-latest
    strategy:
      fail-fast: false
      matrix:
        lab: [network/core, network/edge]
    steps:
      - uses: actions/checkout@v4
      - uses: netdryrun/netdryrun@v0.3.3
        with:
          path: ${{ matrix.lab }}
          artifact-name: netdryrun-${{ strategy.job-index }}
```

Give each matrix job its own `artifact-name`; artifact names must be unique within a workflow run.

### Comment the verdict on every pull request

```yaml
name: Network dry run
on: pull_request
permissions:
  contents: read
  pull-requests: write
jobs:
  dryrun:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: netdryrun/netdryrun@v0.3.3
        with:
          path: network/
          pr-comment: true
```

## Security notes

- **A lab is code that runs as root on the runner.** containerlab starts privileged containers with access to the host. Netdryrun passes the lab process a minimal environment (no job tokens, not the runner user's home directory), but that only narrows exposure; it is not a security boundary.
- **Run labs from untrusted pull requests (forks) only in jobs with no secrets**, a read-only `GITHUB_TOKEN`, and without `id-token: write`. Never run them under `pull_request_target`.
- **Check out with `persist-credentials: false`.** `actions/checkout` otherwise leaves the job token in `.git/config`, where a privileged lab container can read it during the run (the PR comment step gets its own token from `github-token`).
- **The comment starts with a fixed header** (from 0.3.3), so a coding agent reads the verdict without parsing the rest. After the update marker, which names the lab (`<!-- netdryrun-comment <path> -->`, so each lab has its own comment), come two lines:

    ```text
    <!-- netdryrun-verdict: {"schema": "netdryrun.mcp-result/v1", "status": "failed", "verdict": "DO NOT APPLY THIS CHANGE", "passed": 5, "failed": 1, "commit": "4f2a9c1e0b7d3a5f6e8c9b1a2d3e4f5a6b7c8d9e"} -->
    **Netdryrun: DO NOT APPLY THIS CHANGE** · status `failed` · 5 passed, 1 failed · commit `4f2a9c1e0b7d`
    ```

    The JSON holds only the status, the frozen verdict string, the counts and the pull request's head commit, and it is held to the run's checked exit code: a missing or contradicting result, or a run that wrote no report, reads `error` and `DO NOT APPLY THIS CHANGE`. Only a comment by `comment-author` (default `github-actions[bot]`) is updated; a comment someone else posts with the same marker is ignored, so read only the bot's comments. See [agents without Docker](guides/agent-pr.md).
- `pr-comment` needs `pull-requests: write`. Grant it only when you use it. Don't grant `id-token: write` for the `cloud` input: Netdryrun Cloud is not available yet.
- Uploaded report artifacts contain raw command output from the lab and are kept for 14 days. Don't put real secrets in lab configs.
- **The PR comment cannot be steered by lab text** (0.3.1 and later; 0.3.0 did not escape it). Check names, details, errors and device output are escaped before they are posted: no HTML, links, images, `@mentions` or `#123` references, and device output stays inside its code block. Report files already in the workspace (committed in the PR, or left by an earlier run on a self-hosted runner) are deleted before the run, and the `status` output is `error` unless the report matches the run's own exit code.
- **Pass outputs to a shell through `env:`**, not by pasting `${{ steps.<id>.outputs.inconclusive-reason }}` into a `run:` script. The reason can quote lab output; from 0.3.1 Netdryrun strips quotes, backslashes, `$` and backticks from it, but `env:` is the safe pattern for any action output.
