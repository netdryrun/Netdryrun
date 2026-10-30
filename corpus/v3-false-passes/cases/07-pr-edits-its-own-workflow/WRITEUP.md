# A pull request edits the workflow that judges it

Case 07 of the [false-passes corpus](../../README.md). Expected: the **Action step fails** with the message above, before any lab boots. This case is checked in CI, not by `netdryrun run`.
Found by: 0.4 expert gauntlet, finding R7. Fixed in **0.4.0**.

## What was tested

`base/` is the repository's base branch: a verify workflow with `allow-intent-edit: false`. `head/` is the pull request: it sets `allow-intent-edit: true` and edits `intent.yml` to declare its own change.

## What passed wrongly

The 0.4 development build before the expert gauntlet (verify is new in 0.4; this was never released) answered: **the PR's edited intent was accepted**.

Under `pull_request`, the workflow that runs is the one in the pull request. A PR that edits the workflow sets its own inputs, so it could grant itself the right to write its own intent.

## What happens now

In `mode: verify` the Action refuses when `.github/workflows` or `.github/actions` differ between the base and the PR merge: "Change the workflow in a separate reviewed PR". The step fails (exit 1) before any lab boots. (The Action's own fail step is a plain job failure, not Netdryrun's exit-2 error.)

## The tests that hold it

- `tests/test_action_verify.py::test_a_pr_that_changes_a_workflow_is_refused_in_mode_verify`
- `tests/test_action_verify.py::test_a_workflow_change_alone_is_refused_too`

## Rerun it

Needs netdryrun 0.4.0 or later. On an older version this case is not expected to give the verdict above (the point of the case is that the older version did not).

```bash
git diff --no-index --name-only base/.github head/.github   # the workflow differs
```
The Action's own refusal runs in CI on a pull request.

Compare the exit code and message with [case.yml](case.yml). This case has been written and checked offline only; it has not yet been run in a lab (`live_verified: false` in case.yml).
