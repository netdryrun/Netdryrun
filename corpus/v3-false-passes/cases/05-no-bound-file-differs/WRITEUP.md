# The change edits a file the lab never loads

Case 05 of the [false-passes corpus](../../README.md). Expected: **error**, exit code 2, before any lab boots.
Found by: 0.4 expert gauntlet, finding R3. Fixed in **0.4.0**.

## What was tested

The pull request adds `r1.conf.new` with a default-route announcement. The topology binds `r1.conf`, not `r1.conf.new`, so the lab boots the same files on both sides. The intent declares a new default route at r2.

## What passed wrongly

The 0.4 development build before the expert gauntlet (verify is new in 0.4; this was never released) answered: **NO BEHAVIOR CHANGE after four boots**.

verify logged "no bound file differs" and approved after four boots: two identical labs compared equal, which says nothing about the change. (An agent passing its own *after* as *before* had the same effect.)

## What happens now

If no file the lab boots differs between the sides, verify stops before any boot: **error (exit 2)**, "nothing to verify".

## The tests that hold it

- `tests/test_verify_gauntlet.py::test_no_bound_file_differing_is_an_error_before_any_boot`

## Rerun it

Needs netdryrun 0.4.0 or later. On an older version this case is not expected to give the verdict above (the point of the case is that the older version did not).

```bash
cd corpus/v3-false-passes/cases/05-no-bound-file-differs
netdryrun verify lab/topology.clab.yml --before before --after after --config-dir configs --intent intent.yml --json report.json
```

Compare the exit code and message with [case.yml](case.yml). This case has been written and checked offline only; it has not yet been run in a lab (`live_verified: false` in case.yml).
