---
title: CLI and reports
description: Netdryrun command-line reference. The run, check and validate commands, every flag, exit codes, and the JSON (netdryrun.report/v1), Markdown and JUnit report formats.
---

# CLI and reports

```text
netdryrun run      [path] [options]   deploy the lab, run checks, destroy the lab
netdryrun check    [path] [options]   run checks against an already running lab
netdryrun validate [path]             validate netdryrun.yml without running anything
netdryrun record   topology.clab.yml  snapshot a known-good lab into a netdryrun.yml baseline
netdryrun mcp                         start the MCP server for AI agents (stdio)
netdryrun feedback                    open a short feedback form on GitHub
netdryrun --version
```

`--debug` (before or after the command: `netdryrun --debug run` or `netdryrun run --debug`) prints the Python traceback of an internal error. Setting `NETDRYRUN_DEBUG=1` does the same.

`path` is `netdryrun.yml` or the folder containing it. Default: the current folder.

## Commands

### run

Deploys the containerlab topology (`containerlab deploy --reconfigure`), runs every check, writes reports, and destroys the lab (`containerlab destroy --cleanup`). The lab is destroyed even when checks fail, unless you ask to keep it.

`run` refuses to start (exit code `2`) when a lab with the same name is already running: another Netdryrun run of the same lab, a lab deployed by hand, or one kept with `--keep`. Redeploying it would reconfigure the other lab's containers, and destroying it afterwards would pull them out from under whoever is using it. The error names a container and the command to remove the lab: `containerlab destroy -t <topology> --cleanup`. Two runs of the same lab started at the same moment on one host are also refused, by a lock (`another Netdryrun run is already using lab '<name>' on this host`). `check` doesn't deploy, so it runs against the existing lab.

### check

Runs the checks against a lab that is already up, for example one left running with `--keep`. It does not deploy or destroy anything. It fails with an error if any of the lab's containers are not running.

### validate

Loads and validates `netdryrun.yml` and prints the parsed checks. It does not need Docker or containerlab.

From 0.3.1 it also reads the topology (strictly: malformed YAML and duplicate keys are errors) and checks what `run` checks before deploying: every node a check, fault or `setup` names exists; the driver can read every key the checks use (for example no `afi: evpn` on SR Linux or Arista EOS); and `inject_routes` names an FRR node. It also checks two things `run` finds out only after deploying: every node a check reads has a driver (detected from its kind and image, or set with `nodes.<node>.driver`), and no `link_down` or `node_isolated` fault targets an SR Linux node. Any of these is an error with exit code `2`. What it can't check without containerlab: whether containerlab accepts the topology itself (a misspelled `kind:`, a missing image).

```text
$ netdryrun validate examples/frr-bgp
OK: examples/frr-bgp/netdryrun.yml (7 checks, lab .../examples/frr-bgp/topology.clab.yml, 3 nodes)
  - [bgp_session] r1: BGP session to 10.0.12.2 is established
  ...
```

### record

```bash
netdryrun record path/to/topology.clab.yml --deploy
```

Snapshots a known-good lab into a `netdryrun.yml` baseline: every established BGP session, every prefix count (exact, or minimums with `--min-prefixes`) and up to 50 BGP routes per node. Commit it, and every later change is tested against today's behavior. Review the file before committing: remove what is allowed to change, and add negative checks for what must never happen.

| Option | Meaning |
|---|---|
| `--out FILE` | Where to write (default: `netdryrun.yml` next to the topology) |
| `--deploy` | Deploy the lab first and destroy it afterwards (otherwise the lab must be running) |
| `--wait SECONDS` | With `--deploy`: time for BGP to converge before recording (default 45) |
| `--min-prefixes` | Record prefix counts as minimums instead of exact |
| `--no-routes` | Don't record individual routes |
| `--attributes` | Also record a `bgp_route` check per BGP route, pinning its best path's AS path, local preference and communities (not MED or next hop, which follow the topology) |
| `--force` | Overwrite an existing file |

### feedback

Opens a short feedback form on GitHub in your browser, prefilled with your Netdryrun version and platform. Nothing is sent until you submit the form.

| Option | Meaning |
|---|---|
| `--print-only` | Print the form's URL instead of opening a browser |

## Options

`run` and `check`:

| Option | Default | Meaning |
|---|---|---|
| `--json FILE` | | Write the full evidence report as JSON |
| `--markdown FILE` | | Write a Markdown summary (for PR comments) |
| `--junit FILE` | | Write JUnit XML (for CI test reporting) |
| `--settle SECONDS` | `10` | Wait before post-convergence checks, and in a scenario after the fault took effect |
| `--hold SECONDS` | `10` | How long a post-convergence check must hold (a check's own `hold` key overrides it). In a scenario, positive checks must hold this long too |
| `--debug` | | Print the traceback of an internal error |
| `--no-step-summary` | | Do not append the Markdown summary to `$GITHUB_STEP_SUMMARY` |

`run` only:

| Option | Meaning |
|---|---|
| `--keep` | Leave the lab running afterwards, for debugging |
| `--keep-on-failure` | Leave the lab running only if the run did not pass |

When a lab is kept, Netdryrun prints the command to destroy it. See [convergence semantics](config.md#convergence-semantics) for what `--settle` and `--hold` control.

## Exit codes

| Code | Status | Meaning |
|---|---|---|
| `0` | `passed` | Every check passed |
| `1` | `failed` | At least one check failed |
| `2` | `error` | No verdict: the run could not start or could not finish. See below |
| `3` | `inconclusive` | Checks failed, but the lab never reached a state where they mean anything: the result says nothing about the change. Rules below |
| `130` | `error` | Interrupted by SIGINT (Ctrl-C): no verdict |
| `143` | `error` | Interrupted by SIGTERM (for example a cancelled CI job or `docker stop`): no verdict |
| `129` | `error` | Interrupted by SIGHUP (the terminal closed): no verdict |

**Exit code 2** is used for every run that ends without a verdict (0.3.1 and later):

- a config error: bad YAML, an unknown or duplicate key, a bad value (see [validation](config.md));
- a bad topology, an unknown node, or a check a driver can't read;
- a bad option, for example a negative `--settle`;
- a lab problem: containerlab or Docker missing, deploy failed, containers not running, unknown driver, a lab with the same name already running;
- a scenario whose fault did not take effect within the checks' timeout, or whose BGP state or interface addresses could not be read before the fault, so Netdryrun can't tell when it took effect (see [scenario timing](config.md#scenario-timing));
- a link or injected route that could not be restored after a scenario;
- a report that could not be written (`--json`, `--markdown`, `--junit`, or the GitHub Actions step summary), for example a path in a folder that doesn't exist. The verdict line is still printed and every other report is still written, but the evidence you asked for is missing, so the run exits `2`, with one line per report on stderr: `could not write <path>: <reason>; the verdict was <status>` (0.3.1 and later; 0.3.0 reported an internal error). The status inside the reports that were written is the verdict;
- an internal error (a Netdryrun bug). It is reported on one line, never as a bare traceback, and never as exit code `1`, which would read as "the change broke something". Rerun with `--debug` or `NETDRYRUN_DEBUG=1` for the traceback, and please report it.

The message is one line on stderr. With `--json` on `run` or `check`, a report with `status: error` and the message in `error` is written, including for a config error before anything starts and for an interrupted run.

**Interrupted runs** (codes 129, 130, 143): SIGINT, SIGTERM and SIGHUP all clean up the same way. Netdryrun destroys the lab it deployed (unless `--keep` was set; `--keep-on-failure` doesn't apply, since an interrupted run has no verdict), writes the requested reports with `status: error`, and exits with 128 plus the signal number, the shell convention. A second signal during cleanup doesn't cut it short.

### When a run is inconclusive

A run is `inconclusive` instead of `failed` only when **all** of these hold. The rules are deliberately conservative: when in doubt, the run is `failed`.

1. At least one check failed, and there was no lab or config error (that is `error`).
2. No positive check passed on **any** sample, anywhere in the run, scenarios included. One passing sample anywhere shows a working network, so the failures are findings.
3. No post-convergence check failed with readable state. A leaked route, or a session that is up but must be down, proves a working control plane.
4. Every failed check is on a node that never gave usable state. That means every sample of every `bgp_session` and `bgp_prefixes` check on the node was *unready*: the state command failed or its output could not be read (a CLI that isn't up yet), or BGP had no neighbors at all on the node. A node with no session or prefix checks qualifies if every sample of every `route` and `bgp_route` check on it was unready (its routing table never answered; from 0.3.2, a ping on it that got no replies doesn't stop this, since a ping can't show that the node gave routing state). A node with only `ping` checks qualifies only if every sample of every check on it was unready.

A configured BGP session that is down (`idle`, `active`, `connect`, ...) is never unready. An ASN typo, a wrong neighbor address or a shutdown look exactly like a slow lab from the outside, so they stay `failed`. A routing table without the route, and a ping with no replies, are findings for the same reason. So a `timeout` that is merely too short for configured sessions to establish gives `failed`, not `inconclusive`; `inconclusive` is for a node whose CLI or BGP never came up at all.

Known limit: a change that deletes a node's entire BGP configuration looks like a NOS that never started BGP, so it is reported `inconclusive`. It is still never `passed`.

What to do: rerun, raise `timeout`, or check that the lab boots (`containerlab inspect`). Don't change the network change because of an inconclusive run.

The JSON report says why in `inconclusive_reason`, and each unready sample in `history` has `"unready": true`.

## GitHub Actions step summary

When the `GITHUB_STEP_SUMMARY` environment variable is set (it is in GitHub Actions), the Markdown summary is appended to the job page automatically. Use `--no-step-summary` to turn this off.

## Report formats

### Console

One line per check as it finishes, then a summary line:

```text
  [FAIL] r1: route 0.0.0.0/0 via bgp is absent -- unexpectedly present via bgp (not selected) (0.1s)
FAILED: 5 passed, 1 failed (6 checks)
```

### JSON

`--json FILE` writes the full evidence. Schema identifier: `netdryrun.report/v1`. Formal definition: [`report-v1.json`](https://netdryrun.com/schemas/report-v1.json), a JSON Schema (draft 2020-12) that the test suite checks real reports against. Within v1 fields are only added, so validate with extra properties allowed (the schema does).

| Field | Type | Meaning |
|---|---|---|
| `schema` | string | Always `netdryrun.report/v1` |
| `status` | string | `passed`, `failed`, `error` or `inconclusive` (new after 0.2.0; a reader should treat any status it does not know as not passed) |
| `lab` | string | containerlab lab name |
| `config` | string | Path of the `netdryrun.yml` that was run |
| `started`, `finished` | string | UTC timestamps (ISO 8601) |
| `error` | string or null | Why the run has no verdict (config, lab or driver error, interruption, internal error); null otherwise |
| `inconclusive_reason` | string or null | Why the run is `inconclusive` ([rules](#when-a-run-is-inconclusive)); null otherwise |
| `environment` | object | `netdryrun`, `containerlab` and `python` versions, `host` platform, and `nodes` (each with `kind` and `image`) |
| `summary` | object | `passed`, `failed`, `total` |
| `checks` | array | One object per check, in file order (below) |

Each entry in `checks`:

| Field | Type | Meaning |
|---|---|---|
| `name` | string | Check name |
| `type` | string | Check type |
| `params` | object | The check's parameters after normalization |
| `passed` | boolean | Result |
| `detail` | string | Human-readable result, for example `3 ipv4-unicast prefixes accepted` |
| `attempts` | integer | Number of samples taken |
| `duration_s` | number | Seconds spent on the check |
| `started` | string | UTC timestamp |
| `history` | array | Every sample (last 50): `t` (seconds since start), `passed`, `detail`, and `unready: true` on a failing sample where the node gave no usable state |
| `evidence` | array | Raw commands from the final sample: `node`, `cmd`, `rc`, `output`, `stderr` |

Long outputs are truncated (the last 20,000 characters of command output are kept).

### Markdown

`--markdown FILE` writes a short summary: a heading (passed, failed, inconclusive, or could not run), the reason when inconclusive, the pass/fail counts and lab name, a table of checks with failures first, and a footer with the Netdryrun and containerlab versions. This is the same text appended to the GitHub Actions step summary.

### JUnit XML

`--junit FILE` writes one `<testsuite name="netdryrun">` with one `<testcase>` per check:

- `classname` is `netdryrun.<type>`, for example `netdryrun.route`
- a failed check has a `<failure>` whose `message` is the detail and whose body is the evidence as JSON
- in an `inconclusive` run, failed checks have an `<error>` instead of a `<failure>` (they could not run meaningfully), and they count as `errors`, not `failures`
- a lab error adds a testcase named `lab` with an `<error>` element
