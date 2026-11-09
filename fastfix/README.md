# Loosening allowlist (0.4.2)

`scripts/fastfix_gate.py loosening` compares a change's verdicts with its base, case by case, and blocks any case that
passes more than before: FAIL or UNKNOWN to PASS, or a nondeterministic case going from some runs passing (MIXED) to
all of them. It compares:
- every committed corpus `results.json` (records only: it re-runs no lab);
- the must-not-pass fixtures **as the base has them**: `tests/test_redteam.py` with the tests its pinned cases name,
  the tests `tests/known_false_passes.yml` names, and every committed oracle in `tests/oracles/`. They run on the
  base's whole tree with only the candidate's `src/` packages swapped in, so editing a fixture, its data or the test
  harness changes nothing.

A flip that is genuinely right (a false alarm fixed, a lab re-captured) passes only through a file
`fastfix/allow/<change>.yml` added or changed in this change:

```yaml
flips:
  - source: corpus/v2/results/results.json     # as the gate prints it
    case: 06-peer-import-filter-permit-all
    from: FAIL                                   # FAIL, UNKNOWN or MIXED
    to: PASS                                     # MIXED or PASS
    evidence: [research/captures/case06-rerun.txt]
    why: What changed in the evidence, in a sentence a reviewer can check (40+ characters).
    reviewed_by: who reviewed it
```

Rules (each one blocks when broken):
- Exactly these keys, and no wildcards. An entry that matches no flip in this change blocks, so stale or pre-loaded
  entries can't wait for a future loosening.
- `evidence` must name files that exist at the candidate and changed in this change. They can't be code
  (`src/`, `scripts/`, `.github/`, `fastfix/`, `*.py`) or the flipped source itself. A `fixtures` entry may also cite
  the flipped test's own file, updated.
- Once the base has `scripts/fastfix_gate.py`, a change to the gate's own files (`scripts/fastfix_gate.py`,
  `scripts/release_gate.py`, `.github/workflows/release-gate.yml`) is a flip (`source: gate`, `case: <path>`), and
  the release gate always runs the base's copy of the checker.
- The commit that adds the allowlist changes nothing else. Its `Session:` trailer must differ from the `Session:` of
  every commit in the change that touches shipped code, the gate, a flipped record or the cited evidence, and those
  commits must carry one.
- Allowlists from earlier changes don't count: only files changed between the merge-base and the candidate are read.

Exit codes: 0 clean, 1 blocked, 2 couldn't run (missing git, unreadable input). The release gate treats anything but
0 as a failed BLOCKER.

## Oracle specs

`fastfix/oracle-specs/<ID>.md` says what an oracle must capture and prove before the capture exists (a lab that waits
for a night window). The oracle itself goes to `tests/oracles/<ID>/`, written by a session that isn't the fixer. A
spec lives here, not under `releases/`, because the slim-container unit run copies no release records and the
registry test reads it (`tests/known_false_passes.yml`, `oracle_spec:`).
