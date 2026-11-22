# Gate review: a new read may cite its oracle or unchanged test beside a live capture

- Reviewer session: adv-newread. It wrote no code, test, fixture, record, evidence or allowlist in this change;
  this file is its only commit.
- Reviewed: 6919692 on 2d22952, in a fresh clone in WSL Ubuntu-ndr, shared venv, `PYTHONPATH=src`, no lab.
- Verdict: **APPROVE**. No finding blocks; findings 1 to 3 are hardening for a follow-up change.

What the change does: for a `kind: new-read` fixture entry only, the flipped test's own file may be cited even when
it sits under `tests/oracles/` or is unchanged since the base. In that case the entry must also cite a changed,
non-.py file under `tests/fixtures/` that `tests/fixtures/SOURCES.yml` files as `kind: live-capture`, by name or by
a pattern with a literal stem.

## Findings, ranked

1. **MEDIUM-LOW (reproduced): the SOURCES.yml line that makes a file a capture is not under the separation rule.**
   - The cited capture is guarded, so the session that committed it can't write the allowlist or the review. The
     register line is a different matter.
   - Probe, a dominance run end to end:
     - the fix session adds a fixture with arbitrary text;
     - the allowlist session, in a commit of its own, files that fixture as `live-capture` in SOURCES.yml;
     - a fresh reviewer then commits.

     Result: the gate reports clean.
   - Fix: when an entry uses this exception, add SOURCES.yml to the cited files, so its commits need a Session apart
     from the allowlist writer and the reviewer.
2. **MEDIUM, theoretical: nothing ties the capture to the new command, the network OS or the test.**
   - Any qualifying file satisfies the rule.
   - "Real output only" is checked by review, not by code, here as elsewhere (fixture provenance checks coverage and
     kind; ORACLE.yml evidence is checked for existence).
   - Live routing still sends the release to a real device on every OS the read touches.
   - Hardening: print each case's candidate-only commands next to its new-read entry, and have the review record
     name the capture and the command it answers.
3. **LOW (reproduced): pattern and file-type edges.**
   - A pattern needs only a non-empty literal stem. With `f*` filed as live-capture, each of these counts as a
     capture:
     - `f/x/deep.txt` (`*` crosses `/`);
     - `frog.bin`;
     - `f.PY` and `f.pyc` (the code test is case-sensitive and suffix-exact).
   - Existing live-capture patterns (`junos_instance_*.txt`, `verify/*.txt`, `verify-corpus/*.json`, the
     `srl2672_fp043_*leaf1*` families) pre-label any new file whose name fits them.
   - A symlink under `tests/fixtures/` filed as live-capture counts, because `is_file()` follows links.
   - Refused correctly:
     - `../` traversal and `./` paths;
     - backslash paths;
     - a mis-cased `kind`;
     - a blank `source`.
   - Fix: refuse symlinks, compare code suffixes case-insensitively, and consider literal names only for captures
     cited this way.
4. **LOW, design note: the exception also covers a base test that really fails, as long as the test sent a new
   command.**
   - Examples: FP-042-UNNSESS's unconditional gap assertion, and the strict refusals in the commit's own end-to-end
     case.
   - Bounded by:
     - the candidate's own suite running an unchanged test (a real failure is red CI);
     - oracle edits needing oracle commits;
     - the fresh reviewer;
     - live routing.
   - Already looser before this change (reproduced): a verdict entry for an oracle flip is accepted when it cites
     any one changed non-code file, with no reviewer. So this change asks for more than that existing path. That
     floor deserves its own look.
   - Hardening: show the candidate's outcome and failure text next to each new-read flip.
5. **INFO.**
   - For 0.4.3 the dominance judge is HEAD's own fastfix_gate.py (the bootstrap), so this rule judges the release
     that ships it; that run is already a MAJOR to accept.
   - This commit edits a gate file and needs its own blob-keyed allowlist entry from a separate session.

## What was checked

- **Scope.** The exception needs all of:
  - kind new-read;
  - source `fixtures`;
  - the flip's own test cited;
  - at least one other cited file that passes `live_capture`.

  Blocked, by probe:
  - a new-read entry citing an oracle file that is not its own test;
  - a non-fixture source citing an oracle;
  - a wildcard case (literal-key rule);
  - a verdict entry citing an oracle or an unchanged test.

  An entry must still match a flip of the same key and kind.
- **Rules kept.** Reviewer separation (the fix session or the allowlist writer as reviewer still blocks) and live
  routing (`new_read_entries`) are unchanged. The stale-entry, literal-key and dead-entry paths are untouched.
- **Historic waiver.** release_gate.py waives in the dominance run.
  - efae4fd touches `scripts/surfaces_agree.py`, a gate file, so the judge prints its missing-Session line exactly
    once, equal to the recorded line.
  - The line is not of a never-waivable shape.
  - The run turns into a MAJOR only when every other BLOCKED line is waived or bridged.
  - So the record applies once the other dominance lines clear.
- **Red tests.** With scripts/fastfix_gate.py reverted to 2d22952, 14 of the 20 new tests fail:
  - every allowed shape;
  - the end-to-end allow;
  - the unreadable-register test;
  - the block cases.

  The block cases fail only on the new hint text. A separate run against the reverted gate shows every blocked
  shape still returns no entry, or exit 1. Blocked before, blocked now.
- **Full suite** at 6919692 (xdist, 10 workers): 9537 passed, 66 skipped, 1 xfailed. `ruff check .`: clean.
