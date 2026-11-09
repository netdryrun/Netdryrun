# Fast-fix gate: planned for 0.4.3

Items found by the 0.4.2 Layer 6 review that change the gate's design, not just its code. Each one lands with a test
that fails before the change.

## 1. `No-Oracle:` is a free-text escape nobody reviews (cold review of f220469, MAJOR 4)

**Today.** `fastfix_gate.py reproduce` accepts any commit that changes shipped code (`src/`, `action.yml`,
`templates/`) if it carries `No-Oracle: <reason>` of 20 characters or more. Nothing checks the reason. A commit that
loosens a parser and says `No-Oracle: refactor, no behaviour change` passes reproduce-first. The loosening check
then catches it only if a committed fixture or corpus record happens to flip.

**Planned: a reviewed entry, like the loosening allowlist** (`fastfix/README.md`).
- A `No-Oracle:` trailer names an entry, for example `No-Oracle: fastfix/no-oracle/<change>.yml#<n>`, instead of
  carrying free text.
- The entry gives the commit, the files it changes in shipped code, a reason (40+ characters), the kind (`version
  bump`, `message text only`, `generated facts`, `refactor` with the tests that pin the behaviour, ...), and
  `reviewed_by`.
- It is committed in a separate commit whose `Session:` differs from the fixing commit's, as allowlist entries are
  today. Entries from earlier changes don't count.
- **The kinds are narrow on purpose.** For `message text only` the gate checks that the diff touches string literals
  only. For `version bump` it checks that only the version lines change. A `refactor` entry must name the tests that
  pin the behaviour, and the gate runs those tests on the parent and the commit; both must pass.
- An entry that matches no commit in the range blocks, so no entry can be pre-loaded.

**Until then.** The Layer 6 reviewer reads every `No-Oracle:` reason in the release range
(`git log --format='%h %(trailers:key=No-Oracle,valueonly)' <base>..HEAD`) against its diff. In 0.4.2 there are two:
the version bump (f220469) and the record warning text (9d155d7).

## 2. Trust boundaries GPT and Grok named on the gate brief (Layer 6 on f220469)

Fixed in 0.4.2 (tests in `tests/test_fastfix_gate.py` and `tests/test_gate_records.py`): a deleted oracle, a symlink
in an oracle folder, the gate files missing from `GATE_FILES`, a guard skipped at the base and failing at the
candidate, and a FAIL missing from the latest layer record. These need a design:

- **The bootstrap judges itself.** While the base has no `fastfix_gate.py`, the static layer runs the candidate's copy
  (0.4.2 is that release). From 0.4.3 the base has it. Also: the call to `fastfix_checks` sits in the candidate's
  `release_gate.py`, so a candidate can remove it. Planned: the release-gate workflow runs the base's
  `fastfix_gate.py` itself, outside the candidate's `release_gate.py`.
- **The candidate's code runs inside the judging pytest.** A package that writes its own passing JUnit report on
  import and exits 0 would fool `run_pytest`. Planned: the judge collects outcomes through a plugin from the base's
  tree, compares the collected node ids with the base's, and treats a report it didn't write as a failure.
- **The allowlist trusts its author.** `reviewed_by` isn't checked and evidence is never run. Planned: as for
  `No-Oracle` above, a reviewed entry with narrow kinds, and evidence that is a test the gate runs.
- **`Session:` markers are self-declared.** They make independence auditable, not proven (tests/oracles/README.md says
  so). Planned: the oracle and the fix come from different commit authors in the same repository, where the commit
  identity is set by the session's host, not by the commit message.
- **Shipped code is `src/`, `action.yml` and `templates/` only.** A behaviour change in a build or dependency file
  needs no trailer. Planned: `pyproject.toml` dependency and entry-point lines count as shipped.

## 3. Smaller items from GPT and Grok on the 0.4.2 shipped diff

- `frr.parse_paths_available`: require exactly one "BGP routing table entry for" line, not only one "Paths:" line.
  FRR prints one entry for an exact-prefix query, so this is hardening.
- `frr.needs_text_count`: catch RecursionError and TypeError as well, so deeply nested JSON is a named error. Callers
  already fail closed.
