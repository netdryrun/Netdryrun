# GitLab CI (not listed yet)

> **Unlisted until it has run in a real GitLab pipeline.** This component is built and unit-tested, and was run locally with gitlab-ci-local, but it has not run on GitLab.com or a self-managed GitLab yet, so the website and the README don't mention it. The merge request note (0.3.3) has only been tested against a stub of the GitLab API.

The Netdryrun™ CI/CD component is the GitLab counterpart of the [GitHub Action](https://netdryrun.com/github-action/). It adds one job that installs containerlab if the runner has none, installs Netdryrun, runs your checks, prints the Markdown summary in the job log, publishes the JUnit report as the pipeline's test report, keeps the JSON, JUnit and Markdown reports as artifacts, and exits with Netdryrun's [exit code](https://netdryrun.com/reference/cli/): `0` passed, `1` a check failed, `2` config or lab error, `3` inconclusive.

**Test status:** tested locally with [gitlab-ci-local](https://github.com/firecow/gitlab-ci-local) 4.76.1 on Docker 29.9.2, with both a privileged docker executor and a shell executor. Both exit `0` on `examples/frr-bgp` and `1` on `examples/frr-bgp-broken`. It has not yet run on GitLab.com or on a self-managed GitLab instance.

## Usage

The component is the file [`templates/netdryrun.yml`](https://github.com/netdryrun/Netdryrun/blob/main/templates/netdryrun.yml) in the Netdryrun repository. It is not listed in the GitLab CI/CD Catalog yet, so include it as a remote file. Replace `main` with a commit SHA or a release tag so a change upstream can't change your pipeline:

```yaml title=".gitlab-ci.yml"
include:
  - remote: https://raw.githubusercontent.com/netdryrun/Netdryrun/main/templates/netdryrun.yml
    inputs:
      path: network/        # folder containing netdryrun.yml
```

On a self-managed GitLab without internet access, copy the file into your project and use `include: local:` with the same `inputs:`.

### Only run when network files change

The included job is an ordinary job named `netdryrun` (or the `job-name` input). Add keys to it by defining a job with the same name; GitLab merges the two:

```yaml
include:
  - remote: https://raw.githubusercontent.com/netdryrun/Netdryrun/main/templates/netdryrun.yml
    inputs:
      path: network/

netdryrun:
  tags: [privileged]           # pick a runner that allows privileged jobs
  rules:
    - if: $CI_PIPELINE_SOURCE == "merge_request_event"
      changes: ["network/**/*"]
```

### Several labs

Include the component once per lab, each with its own `job-name`:

```yaml
include:
  - remote: https://raw.githubusercontent.com/netdryrun/Netdryrun/main/templates/netdryrun.yml
    inputs: {job-name: netdryrun-core, path: network/core}
  - remote: https://raw.githubusercontent.com/netdryrun/Netdryrun/main/templates/netdryrun.yml
    inputs: {job-name: netdryrun-edge, path: network/edge}
```

### Use the result in a later job

The job writes a `dotenv` report, so jobs that `needs:` it get `NETDRYRUN_STATUS` (`passed`, `failed`, `error` or `inconclusive`), `NETDRYRUN_PASSED`, `NETDRYRUN_FAILED` and `NETDRYRUN_INCONCLUSIVE_REASON`. The status is `error` unless the report matches the run's own exit code.

```yaml
report:
  needs: [netdryrun]
  when: always
  script:
    - echo "Netdryrun $NETDRYRUN_STATUS: $NETDRYRUN_PASSED passed, $NETDRYRUN_FAILED failed"
```

## Inputs

| Input | Default | Meaning |
|---|---|---|
| `job-name` | `netdryrun` | Name of the job the component adds |
| `stage` | `test` | Stage the job runs in |
| `image` | `ghcr.io/srl-labs/containerlab/devcontainer-dind-slim:0.81.1` | Job image on docker executors: containerlab's own Docker-in-Docker image (Debian, Python 3.11, containerlab preinstalled). Shell runners ignore it |
| `path` | `.` | `netdryrun.yml` or the folder containing it |
| `containerlab-version` | `0.81.1` | containerlab version to install when the runner has none. Empty means latest. An installed containerlab is used as is, with a warning if the version differs |
| `netdryrun-package` | `netdryrun==0.4.0` | What `pip` installs: a pinned release by default; a path or a git URL also work |
| `json-report` | `netdryrun-report.json` | Path for the JSON evidence report |
| `junit-report` | `netdryrun-junit.xml` | Path for the JUnit XML report, published as the pipeline's test report |
| `markdown-report` | `netdryrun-summary.md` | Path for the Markdown summary, also printed in the job log |
| `verdict-report` | `netdryrun-verdict.json` | Path for the agent result: status, verdict, failures and the sha256 of every file tested, in the shape the MCP tools return ([schema](https://netdryrun.com/schemas/mcp-result-v1.json)). Kept with the reports (0.3.3) |
| `mr-comment` | `false` | On merge request pipelines, post and keep updating one note with the verdict (see below) |
| `mr-comment-token-variable` | `NETDRYRUN_GITLAB_TOKEN` | Name of the masked CI/CD variable holding the token for the note |
| `settle` | `10` | Seconds to wait before post-convergence checks |
| `hold` | `10` | Seconds a post-convergence check must hold |
| `artifacts-expire-in` | `14 days` | How long GitLab keeps the reports |

The GitHub Action's `pr-comment` and `cloud` inputs have no GitLab counterpart yet: the component doesn't comment on merge requests and doesn't upload to Netdryrun Cloud.

## Merge request note

With `mr-comment: true`, on a merge request pipeline the job posts one note on the merge request and updates it on every run. It starts the same way as the GitHub Action's PR comment, so a coding agent reads it the same way:

```text
<!-- netdryrun-comment network/ -->
<!-- netdryrun-verdict: {"schema": "netdryrun.mcp-result/v1", "status": "failed", "verdict": "DO NOT APPLY THIS CHANGE", "passed": 5, "failed": 1, "commit": "4f2a9c1e0b7d3a5f6e8c9b1a2d3e4f5a6b7c8d9e"} -->
**Netdryrun: DO NOT APPLY THIS CHANGE** · status `failed` · 5 passed, 1 failed · commit `4f2a9c1e0b7d`
```

There is one note per lab (the marker names the `path`). The JSON names the merge request's head commit and is held to the run's checked exit code: a missing or contradicting result reads `error`, and so does a job that stopped before Netdryrun wrote a report (the note is written however the script ends). Only notes by the token's own user are updated; read only those. Then comes the Markdown summary.

GitLab's job token can't write merge request notes, so the note needs a token:

1. In the project: **Settings > Access tokens**, add a project access token with the **Reporter** role and the **api** scope.
2. In **Settings > CI/CD > Variables**, add it as `NETDRYRUN_GITLAB_TOKEN`, **masked**. Merge request branches are usually not protected, so leave **Protected** off, or the job won't see it.
3. Set `mr-comment: true`, and run the job in merge request pipelines (for example `rules: [{if: $CI_PIPELINE_SOURCE == "merge_request_event"}]` on the job).

Anyone who can push a branch that edits `.gitlab-ci.yml` can read that variable in their own job (or point `CI_API_V4_URL` elsewhere). And the token is in the job's environment while the lab runs: the lab's containers are privileged, so an untrusted topology can read it from the host. Give the token only the Reporter role, and use `mr-comment` only where everyone who can open a merge request is trusted. Without the token, the job prints a warning naming the variable and the result is unchanged; a note that can't be written is also only a warning.

## Runner requirements

containerlab starts privileged containers and creates network namespaces and virtual links on the host, so the job needs a Linux runner where it can do that. Two setups work:

- **Docker executor with `privileged = true`** in the runner's `config.toml`. The default image starts its own Docker daemon inside the job container (Docker-in-Docker), so labs never touch the runner host's Docker and every job starts with an empty image cache (the FRR image is about 90 MB). A `docker:dind` *service* isn't supported: containerlab has to run in the same namespaces as the Docker daemon that starts the lab, and a service runs in its own.
- **Shell executor** on a Linux host with Docker and containerlab installed. The `gitlab-runner` user needs passwordless `sudo`, or membership of the `docker` and `clab_admins` groups. The lab then runs on the host's Docker, so give each lab a unique `name:` if jobs can run at the same time.

GitLab.com's hosted Linux runners (`saas-linux-*` tags, the default) run jobs in privileged mode, each in its own VM, so the component may work there without any setup; we haven't run it there yet. Runners tagged `gitlab-org` are not privileged and can't run it. Kubernetes runners need privileged pods.

## Security notes

- **A lab is code that runs as root on the runner.** containerlab starts privileged containers with access to the host. A privileged job can take over the runner host, so use a runner that runs nothing else, or ephemeral VMs. The component passes the lab process a minimal environment (no `CI_JOB_TOKEN` or other job variables, not the runner user's home directory), but that only narrows exposure; it is not a security boundary.
- **Run labs from untrusted merge requests only in jobs with no secrets.** Don't expose protected or masked variables to the job, and don't run fork merge requests in the parent project's pipeline on a privileged runner you also use for deployments.
- Report artifacts contain raw command output from the lab and are kept for 14 days by default. Don't put real secrets in lab configs.
- Report files already in the workspace (committed in the merge request, or left by an earlier run on a shell runner) are deleted before the run. The `NETDRYRUN_*` variables are one line each, and `NETDRYRUN_INCONCLUSIVE_REASON` has quotes, backslashes, `$` and backticks removed, because it can quote lab output.
