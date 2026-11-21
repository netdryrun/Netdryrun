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
commit it names. Origin is the published repository asked by its URL (`https://github.com/netdryrun/Netdryrun.git`),
from outside the working copy with git's config files and `GIT_*` variables set aside, so neither a remote, a folder
named `origin/` nor a `url.*.insteadOf` rule can answer for it; no answer is a failure. The tag must be the commit
origin publishes under that name, origin may list no newer release, and if origin already lists the candidate's own
version it must name this very commit (the `tag-unused` check asks origin as well). Only release 0.4.3 against v0.4.2
(whose copy predates the two commands) is judged by its own committed copy, and the gate records that as a MAJOR to
accept once; from 0.4.4 the fallback can't be reached. That rests on origin's tag list: a 0.4.3 published without its
tag at origin would let a later commit claim 0.4.3 again until the tag exists (PyPI's check catches it when PyPI can
be reached).

## Historic records (0.4.3 only)

Two commits reached main before v0.4.3 could follow the rules the published v0.4.2 judge enforces, and that judge
can't change. `fastfix/historic/0.4.3.json`, committed, may waive the exact lines it prints about them:

```json
{"release": "0.4.3", "base": "61cd95de8b5446d6adf24deda43f9bfb6957ee20",
 "waivers": [{"sha": "<full commit id>", "patch_id": "<git patch-id --stable of that commit>",
              "lines": ["BLOCKED <first 10 digits of the sha> ... (copied from the judge's output)"],
              "why": "...", "reviewed_by": "<session>", "owner_decision": "..."}]}
```

The release gate subtracts only those lines, character for character, from the loosening, reproduce-first and
dominance runs; a run blocked by nothing else becomes a MAJOR that needs its own entry in `accepted.json`, never a
PASS. It blocks (`historic-record`) when the record names another release, or the run or the record is against any
base other than v0.4.2's commit (so it expires with 0.4.3), when a waiver's commit is not in the range or its patch-id
differs, when a line is not a `BLOCKED <that sha>` line or is a flip, an oracle failure or a plant, when a field is
missing, when any other file sits in `fastfix/historic/`, and when a waived line isn't printed by any judge in the run.

The published v0.4.2 judge names a gate-file flip by its bare path, while the judge after it names it
`<path>@<blob>`, so no allowlist can satisfy both: the entry one needs is a stale entry to the other. For release 0.4.3
against v0.4.2's commit only (the change's base and the published release both), the release gate drops two kinds of
line from v0.4.2's loosening run, the bare flip `gate :: <path>: FAIL -> PASS` and the stale-entry line for
`<path>@<blob>`, and only for a gate file whose exact `<path>@<blob>` entry, with the candidate's own blob, is in an
allowlist changed in the change and was allowed by the dominance run on this commit. Every dropped line is listed in
the check's output, and a run that needed it is a MAJOR to accept, never a PASS. Any other line still blocks.

Known limits (accepted for now):
- The checks run from the candidate's own `release_gate.py`. A candidate that edits it shows up as a gate-file flip
  (`scripts/release_gate.py@<blob>`) needing an allowlist entry, but only when an honest copy runs the comparison;
  running the published release's orchestrator, or CI pinned to main, would close this.
- `reviewed_by` and every `Session:` trailer are attestations, not proof: one author can write commits under two
  session names, and the review record's content isn't checked. Session names are compared by their words, in any
  order, case or separator (`fix-unnsess` is `unnsess-fix`), but two genuinely different names from one author still
  pass. A session ledger kept outside the repository would make them verifiable.
- Origin is asked over the network by URL, so the answer is only as good as that connection: a machine whose DNS or
  TLS trust has been tampered with can still be shown a copy that agrees with a moved tag.

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
