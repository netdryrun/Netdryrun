# Oracle spec <ID>: <the bug in one line>

Status: **spec only**. A session that is not the fixer writes the oracle from the evidence below.

## The bug
- **Where it was found:** the run, job or report, with its date.
- **What happens:** the command, the input and the wrong result, quoted.
- **The code path:** the function that goes wrong, and why.
- **Severity:** whether it can cause a false pass, and on which checks.

## The guard must stay
- The behaviour that has to keep working, or keep being refused, once the bug is fixed.

## Evidence to capture
- The commands to run, the versions to record, and where the files go under `tests/` (with provenance entries).

## The oracle: two files, because the gate runs every test in the oracle folder
- **`tests/oracles/<ID>/test_oracle_<id>.py`: red tests only.** Every test there must fail **with an assertion** on
  the fix's parent and pass on the fix. `scripts/fastfix_gate.py reproduce` runs the whole folder on the parent and
  blocks if any test there passes or errors. Never put a guard in this folder, and never write "test N passes there
  too, as a guard".
  1. <what reproduces the bug: an assertion that fails today>
- **`tests/test_oracle_guards_<id>.py`: the guards.** They pass before and after the fix: the behaviour that must
  not change, and the refusals the fix must keep. The file is listed in `ORACLE.yml` `evidence:`, so the fix can't
  edit it. It runs in the unit suite, not in the reproduce check.
  1. <a guard>
- **`ORACLE.yml`:** `id`, `bug`, and `evidence:` listing every file the oracle reads that the base doesn't have, the
  guards file included.

## The fix (for the fixing session, after the oracle)
- What it may change, and what it must not loosen.
