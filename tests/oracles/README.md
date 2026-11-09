# Oracles: reproduce first, from another session (0.4.2)

An oracle is a test that reproduces one confirmed bug from real evidence. It is written and committed **before** the
fix, by a different session (person or agent) from the one that fixes it. The fixer can't edit it. It must fail on
the commit before the fix and pass on the fix. Afterwards it stays here and runs forever.

`scripts/fastfix_gate.py reproduce` enforces this. The release gate's static layer and the release-gate workflow run
it on every pull request (`release_gate.py static`, checks `reproduce-first` and `loosening`).

## Layout

```
tests/oracles/<ID>/
  ORACLE.yml                 id: <ID>, bug: one line, evidence: [repo paths of the real capture, trace or perturbation]
  test_oracle_<id>*.py       the tests; <id> is the ID in lower case with every other character as "_"
```

- `<ID>` looks like `RT-0036` or `FP-042-01` (`^[A-Z][A-Z0-9]*-[0-9][0-9A-Za-z.-]*$`).
- Evidence lives under `tests/` (for example `tests/fixtures/`), added in the oracle commit or already committed.

## Commits

| Commit | Trailers | May change |
|---|---|---|
| Oracle | `Oracle: <ID>` and `Session: <marker>` | `tests/` only |
| Fix | `Fixes-Oracle: <ID>` (one line per ID) and `Session: <another marker>` | anything except `tests/oracles/` and the oracle's evidence |
| Any other commit that changes `src/` | `No-Oracle: <why it needs none, 20+ characters>` | |

Example fix message:

```
Driver X: an empty table no longer reads as "no routes"

Fixes-Oracle: FP-042-01
Session: ndr-fix-042-01
```

## What the check proves, and what it doesn't

For each `Fixes-Oracle` commit F:
- the oracle was committed before F, by commits carrying `Oracle: <ID>` and a `Session:` different from every session
  that fixes it;
- F changes nothing under `tests/oracles/` and none of the oracle's evidence files;
- every oracle test **fails with an assertion** on F's parent, and every one passes on F. Both runs use the tree of the
  last commit that wrote the oracle (its tests, conftest, fixtures and pytest config), with only the `src/` packages
  swapped in. So a fix can't make the oracle pass by changing the shared test harness.

For the candidate as a whole: every oracle present still passes, so a later commit can't bring the bug back.

Not proven:
- `Session:` markers are commit trailers, so whoever writes a commit can forge one. They make independence auditable
  in `git log`, not impossible to fake.
- Code under test that detects it is being tested can still cheat.
- Keep the oracle and fix commits when merging (no squash). A squash makes the fix and its oracle one commit, and the
  check then blocks it.

One fix commit per ID: if the bug is fixed across several commits, put the trailer on the last one and make sure the
oracle still fails on its parent.

The loosening gate is the other half: `fastfix_gate.py loosening` blocks any FAIL→PASS or UNKNOWN→PASS that
re-judging shows (corpus results, the red team, known false passes, every committed oracle). The only exception is a
reviewed entry in `fastfix/allow/*.yml`, added by another session in a commit of its own. See `fastfix/README.md`.
