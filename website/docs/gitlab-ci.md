---
title: GitLab CI
description: Run Netdryrun in GitLab CI/CD with the Netdryrun CI/CD component. Inputs, job outputs, runner requirements for privileged containerlab labs, and security notes.
---

# GitLab CI

The Netdryrun™ CI/CD component is the GitLab counterpart of the [GitHub Action](github-action.md). It adds one job that installs containerlab if the runner has none, installs Netdryrun, runs your checks, prints the Markdown summary in the job log, publishes the JUnit report as the pipeline's test report, keeps the JSON, JUnit and Markdown reports as artifacts, and exits with Netdryrun's [exit code](reference/cli.md): `0` passed, `1` a check failed, `2` config or lab error, `3` inconclusive.

**Test status:** tested locally with [gitlab-ci-local](https://github.com/firecow/gitlab-ci-local) 4.76.1 on Docker 29.9.2, with both a privileged docker executor and a shell executor. Both exit `0` on `examples/frr-bgp` and `1` on `examples/frr-bgp-broken`. It has not yet run on GitLab.com or on a self-managed GitLab instance.

## Usage

The component is the file [`templates/netdryrun.yml`](https://github.com/netdryrun/netdryrun/blob/main/templates/netdryrun.yml) in the Netdryrun repository. It is not listed in the GitLab CI/CD Catalog yet, so include it as a remote file. Replace `main` with a commit SHA or a release tag so a change upstream can't change your pipeline:

```yaml title=".gitlab-ci.yml"
include:
  - remote: https://raw.githubusercontent.com/netdryrun/netdryrun/main/templates/netdryrun.yml
    inputs:
      path: network/        # folder containing netdryrun.yml
```

On a self-managed GitLab without internet access, copy the file into your project and use `include: local:` with the same `inputs:`.

### Only run when network files change

The included job is an ordinary job named `netdryrun` (or the `job-name` input). Add keys to it by defining a job with the same name; GitLab merges the two:

```yaml
include:
  - remote: https://raw.githubusercontent.com/netdryrun/netdryrun/main/templates/netdryrun.yml
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
  - remote: https://raw.githubusercontent.com/netdryrun/netdryrun/main/templates/netdryrun.yml
    inputs: {job-name: netdryrun-core, path: network/core}
  - remote: https://raw.githubusercontent.com/netdryrun/netdryrun/main/templates/netdryrun.yml
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
| `netdryrun-package` | `netdryrun==0.3.0` | What `pip` installs: a pinned release by default; a path or a git URL also work |
| `json-report` | `netdryrun-report.json` | Path for the JSON evidence report |
| `junit-report` | `netdryrun-junit.xml` | Path for the JUnit XML report, published as the pipeline's test report |
| `markdown-report` | `netdryrun-summary.md` | Path for the Markdown summary, also printed in the job log |
| `settle` | `10` | Seconds to wait before post-convergence checks |
| `hold` | `10` | Seconds a post-convergence check must hold |
| `artifacts-expire-in` | `14 days` | How long GitLab keeps the reports |

The GitHub Action's `pr-comment` and `cloud` inputs have no GitLab counterpart yet: the component doesn't comment on merge requests and doesn't upload to Netdryrun Cloud.

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
