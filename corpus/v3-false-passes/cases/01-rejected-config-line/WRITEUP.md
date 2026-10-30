# A config line FRR rejects at boot

Case 01 of the [false-passes corpus](../../README.md). Expected: **error**, exit code 2.
Found by: Advisory 0.3.2-rejected-config. Fixed in **0.3.3**.

## What was tested

r1.conf carries three lines FRR rejects when the container boots: `neighbor 10.0.12.2 default-orignate` (a typo), `neighbor 10.0.12.2 maximum-prefix` (incomplete) and `neighbor 10.9.9.9 route-map ALLOW-ALL in` (a neighbor that does not exist). FRR skips each rejected line and keeps running. The checks are the ordinary FRR triangle checks.

## What passed wrongly

Netdryrun 0.3.2 and earlier answered: **passed (exit 0)**.

0.3.2 did not read the boot log, so the checks ran on a router without the lines and passed. A check that "the change must not break something" passes trivially when the change is not there.

## What happens now

After the checks, Netdryrun reads the boot log of every FRR node. A rejected line makes the run an **error (exit 2)**, naming the node, the line number, the line and the reason. Never a pass.

## The tests that hold it

- `tests/test_frr_config_load.py`

## Rerun it

Needs netdryrun 0.3.3 or later. On an older version this case is not expected to give the verdict above (the point of the case is that the older version did not).

```bash
cd corpus/v3-false-passes/cases/01-rejected-config-line
netdryrun run lab --json report.json
```

Compare the exit code and message with [case.yml](case.yml). This case has been written and checked offline only; it has not yet been run in a lab (`live_verified: false` in case.yml).
