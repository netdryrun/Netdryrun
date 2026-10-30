# A topology exec: command that fails

Case 02 of the [false-passes corpus](../../README.md). Expected: **error**, exit code 2.
Found by: Advisory 0.3.3-exec-not-checked; 0.4 multi-vendor audit finding F1. Fixed in **0.4.0**.

## What was tested

r1 applies one routing line through the topology's `exec:` list: `neighbor 10.0.12.2 defualt-originate` (misspelled). containerlab runs it after the node starts, FRR rejects it, containerlab logs the error and exits 0.

## What passed wrongly

Netdryrun 0.3.3 and earlier answered: **passed (exit 0)**.

0.3.3 checked containerlab's exit code, not its log of `exec:` commands. The router ran without the line, the checks ran on the network without it, and the run passed.

## What happens now

After `containerlab deploy`, Netdryrun reads its output. Any `Failed to execute command` line is an **error (exit 2)** naming the node, the command, its exit code and its output.

## The tests that hold it

- `tests/test_startup_config_load.py::test_audit_f1_an_exec_command_that_failed_fails_the_deploy`

## Rerun it

Needs netdryrun 0.4.0 or later. On an older version this case is not expected to give the verdict above (the point of the case is that the older version did not).

```bash
cd corpus/v3-false-passes/cases/02-failed-topology-exec
netdryrun run lab --json report.json
```

Compare the exit code and message with [case.yml](case.yml). This case has been written and checked offline only; it has not yet been run in a lab (`live_verified: false` in case.yml).
