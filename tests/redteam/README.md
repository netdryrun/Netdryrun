# Red-team corpus: every false pass we have ever found, kept failing forever

A verdict tool's one unforgivable bug is a pass that didn't check. Every time one is found (by our audit,
a cold review, the weekly adversarial agent, a test, or a user), it becomes a file here **before** the fix,
and `tests/test_redteam.py` runs every file on every commit. A case is never deleted.

## Kinds

| `kind` | What the file holds | What must happen |
|---|---|---|
| `config` | `file:` (a path in the repo) or `config:` with an optional `topology:` (inline YAML) | `netdryrun validate` exits 2 |
| `check` | `checks:` and `state:` per node, in the drivers' normalized form (`neighbors`, `routes`, `paths`, `pings`) | no check passes, through the real validator and scheduler |
| `driver` | `driver:`, one `check:` and `outputs:` (raw device output per command: `output:` text or `fixture:` from `tests/fixtures/`, optional `rc` and `stderr`) | the check doesn't pass, through the real driver and parser |
| `pinned` | `tests:` pytest node IDs of tests that reproduce it (for findings that need a whole run on a fake lab and clock) | each test still exists |

Every file has `id` (`RT-0001`, ...), `title` (what passed and why it shouldn't have), `found` (date and by
whom) and `fixed_in`.

## Adding a case

1. Take the next number. The numbers must stay contiguous: a missing one fails the suite, so a case can't
   disappear quietly.
2. Write the smallest file that reproduces the false pass. Prefer `driver` with real captured output, then
   `check`, then `config`; use `pinned` only when the reproduction needs a whole run.
3. Run `pytest tests/test_redteam.py`: the new case must **fail** (the false pass is real) before the fix
   and pass after it. From 0.4.2 the case is committed **before** the fix, by another session, as an oracle
   (`tests/oracles/README.md`); the fix commit names it with `Fixes-Oracle:` and may not edit it.
4. Add a line to the advisory or the CHANGELOG if a released version was affected.

## Retiring a case

Never delete one. If a feature is removed and a case can no longer run, set `retired: "<why>, <date>"`; the
file stays and still counts.
The same field holds a candidate that a verifier or a live test showed isn't a false pass (the reason names the
evidence; an unconfirmed one says which live test is queued and is filed again under a new number if it proves real),
and a number that was never used, so the numbering stays contiguous.

## Running it against an old release

`tests/test_redteam.py` imports no other test file and only long-standing package APIs, so it runs against
any release's source. Every case that fails there is a false pass that release had:

```bash
git archive v0.3.0 src | tar -x -C /tmp/old
NDR_TEST_SRC=/tmp/old/src PYTHONPATH=/tmp/old/src:tests pytest tests/test_redteam.py
```

`NDR_TEST_SRC` declares that the old source is the one under test; without it the import guard in
`tests/import_guard.py` aborts the run (exit 4), because the tests belong to a different checkout than the code. An
abort or a collection error is not a clean run: only a finished run with its failures counted tells you anything.

On 0.3.0 this fails RT-0001 to RT-0011 (eleven false passes). RT-0012, RT-0013, RT-0016 and RT-0017 are guards
that 0.3.0 already passed, and say so in `fixed_in`.
