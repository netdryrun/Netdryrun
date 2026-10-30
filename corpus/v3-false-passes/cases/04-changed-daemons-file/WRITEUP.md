# A changed FRR daemons file

Case 04 of the [false-passes corpus](../../README.md). Expected: **error**, exit code 2, before any lab boots.
Found by: 0.4 expert gauntlet, finding R2. Fixed in **0.4.0**.

## What was tested

The only file that differs between *before* and *after* is FRR's `daemons`, a shell file that FRR's start script runs. The after version adds a line that removes the BGP neighbor 10 minutes after boot, long after verify has taken its snapshots. The intent declares that nothing changes.

## What passed wrongly

The 0.4 development build before the expert gauntlet (verify is new in 0.4; this was never released) answered: **NO BEHAVIOR CHANGE or INTENT MATCHED (the file was only logged)**.

verify reasoned only about the router config. Any other bound file that differed was only logged, and the effect arrives after the snapshots, so a file that rewrites the config at boot or runs vtysh passed under an empty intent.

## What happens now

A bound file other than the observed node's FRR config that differs between the sides is an **error (exit 2)** before any boot, naming the file: "change it in a separate PR".

## The tests that hold it

- `tests/test_verify_run_mutants.py::test_a_changed_daemons_file_on_the_demo_lab_is_refused`

## Rerun it

Needs netdryrun 0.4.0 or later. On an older version this case is not expected to give the verdict above (the point of the case is that the older version did not).

```bash
cd corpus/v3-false-passes/cases/04-changed-daemons-file
netdryrun verify lab/topology.clab.yml --before before --after after --config-dir configs --intent intent.yml --json report.json
```

Compare the exit code and message with [case.yml](case.yml). This case has been written and checked offline only; it has not yet been run in a lab (`live_verified: false` in case.yml).
