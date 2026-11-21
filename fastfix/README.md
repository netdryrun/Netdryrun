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
  `scripts/release_gate.py`, `scripts/gate_records.py`, `scripts/labrun.py`, `scripts/surfaces_agree.py`,
  `.github/workflows/release-gate.yml`) is a flip (`source: gate`, `case: <path>@<blob>`, the first 12 hex digits of
  the file's blob at the candidate, so each later edit of the gate needs its own entry), and the release gate always
  runs the base's copy of the checker.
- A fixture that now passes only because the driver sends a device a command the base never sent (a fake refused
  it, or the command log shows it) is a new device read: its entry adds `kind: new-read`, cites the updated test, and
  names in `reviewed_by: "<session>: <what was checked>"` a session that has a commit of its own in the change,
  touching only `fastfix/reviews/`, and that wrote neither the allowlist nor any code, record or evidence. The release
  gate then needs live runs, on the candidate commit, of every example of each network OS the read touches.
- The commit that adds the allowlist changes nothing else. Its `Session:` trailer must differ from the `Session:` of
  every commit in the change that touches shipped code, the gate, a flipped record or the cited evidence, and those
  commits must carry one.
- Allowlists from earlier changes don't count: only files changed between the merge-base and the candidate are read.

Exit codes: 0 clean, 1 blocked, 2 couldn't run (missing git, unreadable input). The release gate treats anything but
0 as a failed BLOCKER.

## Against the published release

`release_gate.py static --candidate` also compares the candidate with the published release (`loosening
--dominance`) and re-plants every oracle's bug (`plants`). Both are judged by the published tag's own
`fastfix_gate.py`, never by a copy the caller picks. The tag is read only as `refs/tags/<tag>` and passed on as the
commit it names; it must be the commit origin publishes under that name, and origin may list no newer release. Only
release 0.4.3 against v0.4.2 (whose copy predates the two commands) is judged by its own committed copy, and the gate
records that as a MAJOR to accept once; from 0.4.4 the fallback can't be reached.

Known limits (accepted for now):
- The checks run from the candidate's own `release_gate.py`. A candidate that edits it shows up as a gate-file flip
  (`scripts/release_gate.py@<blob>`) needing an allowlist entry, but only when an honest copy runs the comparison;
  running the published release's orchestrator, or CI pinned to main, would close this.
- `reviewed_by` and every `Session:` trailer are attestations, not proof: one author can write commits under two
  session names, and the review record's content isn't checked. A session ledger kept outside the repository would
  make them verifiable.
- "origin" is whatever the local git config says. Pointing it (or a `url.*.insteadOf` rule) at a copy that agrees
  with a moved tag passes the check; it takes deliberate local tampering.

While the published release's tests keep no command log (v0.4.2 has no `tests/fakes.py`), a new read that a lenient
fake answers can't be seen; the report says so and asks for live runs on every network OS whose driver changed.

## Oracle specs

`fastfix/oracle-specs/<ID>.md` says what an oracle must capture and prove before the capture exists (a lab that waits
for a night window). The oracle itself goes to `tests/oracles/<ID>/`, written by a session that isn't the fixer. A
spec lives here, not under `releases/`, because the slim-container unit run copies no release records and the
registry test reads it (`tests/known_false_passes.yml`, `oracle_spec:`).

Start a spec from `fastfix/oracle-specs/TEMPLATE.md`. The reproduce check runs every test in `tests/oracles/<ID>/` on
the fix's parent and needs each one to fail with an assertion. So a spec puts only the red tests in the oracle folder,
and the guards (tests that pass before and after the fix) in `tests/test_oracle_guards_<id>.py`, listed in the
oracle's `evidence:`.
