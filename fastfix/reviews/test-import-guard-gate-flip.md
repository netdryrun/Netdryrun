# Gate-file review: ndr/test-import-guard-v2 (scripts/fastfix_gate.py@0d608ee7b1c0, scripts/release_gate.py@645070a65e8f)

- Reviewer session: adv-import-guard. It wrote no code, test, fixture, record, evidence or allowlist in this change;
  this file is its only commit.
- Reviewed: f84526a (dffc022, 1a9a007, f84526a on top of main 6df498a), judged against main 6df498a, in fresh
  clones, shared venv, `PYTHONPATH=src`. Third round: rounds 1 (ccbea44, 3900e8a) and 2 (1a9a007) were
  do-not-merge; every blocker they found is fixed in f84526a.
- Verdict: both gate-file flips are acceptable:
  - `gate :: scripts/fastfix_gate.py@0d608ee7b1c0: FAIL -> PASS`
  - `gate :: scripts/release_gate.py@645070a65e8f: FAIL -> PASS`
  Every change to the two gate files makes the judged test run read only the checked-out source and prove it did.
  No change removes a check, and no change narrows the set of tests that runs.

`reproduce --range 6df498a..f84526a`: clean (4 commits, 0 fix commits, 31 oracles held). `loosening --base 6df498a
--candidate f84526a` shows exactly 5 flips: the two above, and the 3 command-log noise flips
(`test_startup_config_load::test_audit_f1_*` and two `test_verdict_keys_041::test_action_verify_*`). Those 3 are the
known noise that ndr/gate-cmdlog-noise removes. This record does not cover them, and this change does not touch the
code they exercise.

## What changed in the gate files, and which way it points

| Change | Direction | Why that's safe |
|---|---|---|
| fastfix `run_pytest`: each judged run gets its own empty `PYTHONPYCACHEPREFIX` | stricter | a `.pyc` planted in the tree, or a stale one, is never read; the source is compiled again |
| fastfix: child runs drop the `NDR_*` guard variables from the inherited environment (`CHILD_ENV_DROP`) and require the guard's proof | stricter | an outer `NDR_TEST_SRC`/`NDR_TEST_INSTALLED` can't point a judged run at other code; a run with no proof, or one that tested other code, fails |
| release unit layer: a fresh `PYTHONPYCACHEPREFIX` per Python, the proof file removed first and checked after (`guard_proof_problem`) | stricter | the layer fails unless the guard ran and tested this checkout's `src/` |
| release container layer: `NDR_TEST_INSTALLED=1`, the proof must say `"mode": "installed"` | stricter | the wheel's installed code is compared byte for byte with the checkout before any test runs |
| release mutation layer: `clean_test_env()`, a fresh `PYTHONPYCACHEPREFIX`; the command moved into `mutmut_run_command` | stricter / neutral | same command as before (the same `mutmut run --max-children N <globs>`); the environment can no longer redirect imports, and old rewritten test `.pyc` files are not read |

## Is the mutation layer's result the same?

A guard that changed which tests run under mutmut would be a loosening, so real mutmut 3.8 ran on
`netdryrun.faults.*` with the same script on main and on the candidate (`src/` and `pyproject.toml` are identical).

- Main 6df498a: the stats run stops at `tests/test_plants_registry.py::test_every_oracle_here_has_a_valid_plant_entry`
  (git pathspecs read from the untracked `mutants/` folder), "failed to collect stats", rc 1. Main's mutation layer
  cannot complete there today. That is a failure, not a pass. f84526a fixes the test by reading git from the top
  level; the oracle ids still come from the copied tree.
- Candidate f84526a: rc 0; 8471 tests in mutmut's stats, the whole suite; 735 killed, 8 timeouts, 88 survived.
  (Main's stats run stopped at 5570 tests, because mutmut's stats run uses `-x`.)
- In `mutants/`, main collects 8357 tests and the candidate collects 8471. Every test main collects is also collected
  by the candidate; the 114 extra are the new tests in `tests/test_import_guard.py` (102) and
  `tests/test_contrib_gate.py` (12).
- All 13 `faults` entries in `releases/0.4.2/accepted.json` still survive; none is killed or not checked. Every
  survivor in the gated functions is an accepted entry. The 5 gated non-survivors are timeouts (caught). So the layer
  would report what 0.4.2's accepted list expects, over the full suite.

## Probes

- Mutants re-targeted to the new code: G13b (`.pyc` not refused), N7 (top-level only), N8 (no extension suffix),
  N9a-e (bare `.so`, `.abi3.so`, tagged only, extension suffixes only, everything not `.py`), R7 and R7b (mutation
  layer env not scrubbed / no fresh cache), R10, F6, C6 (no fresh cache in the unit layer, fastfix, contrib), N20,
  N21, N23 (proof-file handling): all killed. Round 2's 55 mutants: 54 killed; N18 is equivalent.
- A loadable-suffix bypass: a module file with a suffix that isn't in `EXTENSION_SUFFIXES` (`checks.sox`), loaded
  through a path hook added by a plugin. It is not refused as a file, but the loaded-module check catches it (exit 4,
  no proof). The same file with no hook is never imported (pass, correct).
- `checks.so`, `checks.abi3.so`, the cpython-tagged `.so` and `checks.pyc` in `src/netdryrun/`: refused (exit 4, no
  proof). A `.so` with another Python's tag is refused too. That is stricter than needed, but harmless.
- The proof-file raise (the M2 fix) can't block a correct run: an identical existing proof passes (rc 0); a
  differing one fails closed (rc 4). The gates delete the proof before each run, and the env var is popped at
  configure, so nested pytest runs never see it. Run with a proof path, `test_import_guard`, `test_contrib_gate` and
  `test_fastfix_gate` gave 328 passed and 1 skipped, and a correct proof.

## Mutant survivors

- N22 (`write_proof`: an existing proof that can't be read counts as "same"). No test makes the existing proof
  unreadable. The gates read the proof themselves afterwards and fail on a file they can't read, so the survivor
  can't turn into a pass. A test for it would be cheap.
- N18 (round 2): equivalent.

## Limits (not fixed here, outside this flip)

- A custom loader installed in-process (a hostile plugin or `.pth`) can report `checks.py` as its origin while it
  runs other code. The guard trusts `__spec__.origin`. Code that already runs inside pytest is out of the guard's
  reach.
- `monkeypatch.setitem(sys.modules, ...)` inside a test is not seen (round 2's M4, documented).
