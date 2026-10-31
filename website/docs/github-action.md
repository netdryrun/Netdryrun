---
title: GitHub Action
description: Run Netdryrun in GitHub Actions with netdryrun/Netdryrun@v0.4.0. Inputs, outputs, example workflows, and security notes for running privileged containerlab labs in CI.
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
      - uses: netdryrun/Netdryrun@v0.4.0
        with:
          path: network/        # folder containing netdryrun.yml
```

It needs a Linux runner with Docker. GitHub-hosted `ubuntu-latest` runners work.

## Inputs

| Input | Default | Meaning |
|---|---|---|
| `mode` | `run` | `run`: deploy the lab of `netdryrun.yml` and run its checks. `verify` (0.4, FRR only): on a pull request, compare the lab with the base branch's configs and with the PR merged into it against an intent file. See [mode: verify](#verify-a-change-against-its-intent-mode-verify) |
| `path` | `.` | `netdryrun.yml` or the folder containing it (`mode: run`) |
| `topology` | | The containerlab topology file (`mode: verify`); it must be the same in the base and the head |
| `intent-file` | `netdryrun-intent.yml` | The intent file (`mode: verify`): what the change is meant to do |
| `allow-intent-edit` | `false` | `mode: verify`: let a PR that adds or edits the intent file run. Set it only when branch protection requires a code-owner review of that file |
| `allow-check-edit` | `false` | `mode: run` on a pull request: let a PR that changes `netdryrun.yml` and the lab's configs together run (with a warning). Without it such a PR fails before any lab boots: it would grade its own change. Set it only where branch protection requires a code-owner review of `netdryrun.yml` |
| `containerlab-version` | `0.81.1` | containerlab version to install, pinned for reproducible runs. Empty means latest. If containerlab is already installed, it is used as is, with a warning if the version differs. |
| `json-report` | `netdryrun-report.json` | Path for the JSON evidence report |
| `junit-report` | `netdryrun-junit.xml` | Path for the JUnit XML report |
| `verdict-report` | `netdryrun-verdict.json` | Path for the agent result: status, verdict, failures and the sha256 of every file tested, in the shape the MCP tools return ([schema](https://netdryrun.com/schemas/mcp-result-v1.json)). Uploaded with the reports (from 0.3.3) |
| `upload-artifact` | `true` | Upload the reports as a workflow artifact |
| `artifact-name` | `netdryrun-report` | Name of the uploaded artifact |
| `settle` | `10` | Seconds to wait before post-convergence checks |
| `hold` | `10` | Seconds a post-convergence check must hold |
| `timeout` | `300` | `mode: verify` only: seconds each lab may take to reach a stable snapshot. Raise it for a lab with a slow-booting node (see [verify](reference/verify.md#nodes-verify-does-not-snapshot-and-slow-boots)), and set the job's `timeout-minutes` to match |
| `pr-comment` | `false` | On pull requests, post one comment with the verdict, failures first, and the evidence for each failed check. Updated in place on every push. Needs `permissions: pull-requests: write` |
| `comment-author` | `github-actions[bot]` | The account that writes the PR comment: only its comment is updated. Set it when `github-token` is another account's token (from 0.3.3) |
| `github-token` | `${{ github.token }}` | Token used for the PR comment |
| `cloud` | `false` | Reserved for Netdryrun Cloud, which is **not available yet**. With `true`, the action tries to POST the JSON report to `cloud-url` with a GitHub OIDC token; that address doesn't resolve today, so nothing is uploaded and you only get a warning ("evidence upload failed", or "needs 'permissions: id-token: write'" without that permission). Leave it off |
| `cloud-url` | `https://cloud.netdryrun.com` | Reserved for Netdryrun Cloud (this address does not exist yet) |

## Outputs

| Output | Meaning |
|---|---|
| `status` | `passed`, `failed`, `error` or `inconclusive` (the lab never reached a testable state, so the run says nothing about the change; the job still fails). With `mode: verify`: `matched`, `no_change`, `failed`, `error`, `inconclusive` or `unhealthy_baseline` |
| `verdict` | `CHECKS PASSED (only what the checks cover)`, `DO NOT APPLY THIS CHANGE` or `INCONCLUSIVE` (decide on `status`, not on the text). With `mode: verify`: `INTENT MATCHED`, `NO BEHAVIOR CHANGE`, `UNDECLARED CHANGES: DO NOT APPLY`, `INCONCLUSIVE`, `INCONCLUSIVE: UNHEALTHY BASELINE` or `ERROR: NO VERDICT` (never a pass of checks) |
| `inconclusive-reason` | Why the run was inconclusive; empty otherwise |
| `passed` | Number of passed checks (`mode: verify`: declared intent lines observed, plus standing guards passed) |
| `failed` | Number of failed checks (`mode: verify`: undeclared differences, declared lines that didn't happen, plus standing guards failed) |
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
      - uses: netdryrun/Netdryrun@v0.4.0
        with:
          path: network/
```

### Use the outputs in a later step

```yaml
      - uses: netdryrun/Netdryrun@v0.4.0
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
      - uses: netdryrun/Netdryrun@v0.4.0
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
      - uses: netdryrun/Netdryrun@v0.4.0
        with:
          path: network/
          pr-comment: true
```

### Verify a change against its intent (mode: verify)

New in 0.4, FRR only. Instead of running checks, the Action boots the topology twice, with the base branch (the first parent of the PR's merge commit) and with the PR merged into it (the merge commit, `github.sha`: what lands, not the PR head alone), and fails on every difference in routing behavior that the intent file doesn't declare. It runs [`netdryrun verify`](reference/verify.md): the verdict is `INTENT MATCHED`, `NO BEHAVIOR CHANGE`, `UNDECLARED CHANGES: DO NOT APPLY` or `INCONCLUSIVE`, never a pass of checks. The standing guards are the `netdryrun.yml` next to the topology **in the base commit**, never the PR's copy, so a PR can't weaken them.

```yaml title=".github/workflows/network-verify.yml"
name: Network verify
on: pull_request
permissions:
  contents: read
  pull-requests: write
jobs:
  verify:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0          # verify reads the base and head commits
      - uses: netdryrun/Netdryrun@v0.4.0
        with:
          mode: verify
          topology: network/topology.clab.yml
          intent-file: network/netdryrun-intent.yml
          pr-comment: true
```

**The intent comes from outside the change.** It states what the ticket asks for, so the PR that makes the change must not also write its intent: a change that writes its own allowlist explains whatever it does. If the PR adds or edits the intent file, the job fails with "intent edited in this PR: requires a code-owner approval", before any lab boots. Two ways to work with that:

- Merge the intent from the ticket first, in its own reviewed PR, then open the change against it.
- Or let one PR carry both, with `allow-intent-edit: true`, **only if branch protection requires a code-owner review** on the intent file. Then a human from the network team approves every intent, and the job prints a warning that the intent was edited.

**The workflow itself is part of the verdict.** Under `pull_request` GitHub runs the workflow from the PR merged into its base, so a PR that edits it sets the inputs that judge it (`allow-intent-edit`, `intent-file`, `topology`, `path`, `allow-check-edit`). So `mode: verify` fails on a PR that changes anything under `.github/workflows/` or `.github/actions/` (a local action the workflow wraps), and `mode: run` fails on one that changes them together with anything else (it could point `path` at a lab it didn't touch), before any lab boots: change the workflow in its own reviewed PR.

Either way, list the intent file, `netdryrun.yml` and the workflows in `CODEOWNERS` and turn on "Require review from Code Owners" for the default branch:

```text title=".github/CODEOWNERS"
network/netdryrun-intent.yml  @your-org/network-team
network/netdryrun.yml         @your-org/network-team
.github/workflows/            @your-org/network-team
.github/actions/              @your-org/network-team
```

The PR comment (with `pr-comment: true`) and the job summary show the verdict, the declared intent echoed for the reviewer, every undeclared difference with the read-only command that shows it on its node, the declarations that didn't happen and the standing guards. The same protections as in `mode: run` apply: report files already in the workspace are deleted before the run, the `status` and `verdict` outputs come from this run's report only (and must match its exit code), and lab text in the comment and outputs is made inert.

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

    In `mode: verify` (0.4) the marker names the topology, and the header is read from the verify report, with verify's own schema, verdict and counts: `{"schema": "netdryrun.verify/v1", "status": "matched", "verdict": "INTENT MATCHED", "undeclared": 0, "not_happened": 0, "commit": "..."}`, then the same in words ("Netdryrun verify: INTENT MATCHED", the status, the counts and the commit). An approval that lists an undeclared difference, a missing declared change or a failed guard, a report that contradicts the run's exit code, or no report reads `error` and `ERROR: NO VERDICT`.
- `pr-comment` needs `pull-requests: write`. Grant it only when you use it. Don't grant `id-token: write` for the `cloud` input: Netdryrun Cloud is not available yet.
- Uploaded report artifacts contain raw command output from the lab and are kept for 14 days. Don't put real secrets in lab configs.
- **The PR comment cannot be steered by lab text** (0.3.1 and later; 0.3.0 did not escape it). Check names, details, errors and device output are escaped before they are posted: no HTML, links, images, `@mentions` or `#123` references, and device output stays inside its code block. Report files already in the workspace (committed in the PR, or left by an earlier run on a self-hosted runner) are deleted before the run, and the `status` output is `error` unless the report matches the run's own exit code.
- **Pass outputs to a shell through `env:`**, not by pasting `${{ steps.<id>.outputs.inconclusive-reason }}` into a `run:` script. The reason can quote lab output; from 0.3.1 Netdryrun strips quotes, backslashes, `$` and backticks from it, but `env:` is the safe pattern for any action output.
