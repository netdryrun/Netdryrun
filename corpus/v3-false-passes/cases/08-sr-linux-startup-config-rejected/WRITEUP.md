# An SR Linux startup config the router rejects

Case 08 of the [false-passes corpus](../../README.md). Expected: **error**, exit code 2. Needs the SR Linux image.
Found by: 0.4 multi-vendor audit, finding F3. Fixed in **0.4.0**.

## What was tested

srl1's JSON startup config has a misspelled key, `peer-groop`, in the BGP block that applies an export policy. SR Linux rejects the whole file and starts without it (deploy exit code 0). The only guard is that frr1 must not learn a default route.

## What passed wrongly

Netdryrun 0.3.3 and earlier answered: **passed (exit 0)**.

0.3.3 did not read SR Linux's log. Without the config nothing is announced at all, so the guard "no default route at frr1" passed on a network the change never reached.

## What happens now

After the checks, Netdryrun reads SR Linux's log; "Load of startup configuration failed" is an **error (exit 2)** naming the node and the reason. An unreadable log is an error too.

## The tests that hold it

- `tests/test_startup_config_load.py::test_audit_f3_an_sr_linux_startup_config_it_failed_to_load_is_an_error`

## Rerun it

Needs netdryrun 0.4.0 or later. On an older version this case is not expected to give the verdict above (the point of the case is that the older version did not).

Images needed: ghcr.io/nokia/srlinux:26.7.2.

```bash
cd corpus/v3-false-passes/cases/08-sr-linux-startup-config-rejected
netdryrun run lab --json report.json
```

Compare the exit code and message with [case.yml](case.yml). This case has been written and checked offline only; it has not yet been run in a lab (`live_verified: false` in case.yml).
