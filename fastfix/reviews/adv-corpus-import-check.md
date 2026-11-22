# Corpus harness review: remedy FRR's stuck import check on the lab the harness deploys (d2a1b3a, 724a996)

- Reviewer session: adv-corpus-ic. It wrote no code, test, fixture, record, evidence or allowlist in this change;
  this file is its only commit.
- Reviewed: d2a1b3a and 724a996 on top of main 4388bb5, in a fresh clone, shared venv, `PYTHONPATH=src`, no lab
  started.
- Verdict: approve. 724a996 fixes the one medium finding (round 1, on d2a1b3a). The low findings below are accepted
  or left for the corpus refresh. None leads to a verdict the product would not give, and every failure path ends in
  status error or a case error.

## What the change does

`corpus/run.py` deploys each case's lab itself and runs every strategy with `run(deploy=False)`. On a lab it didn't
deploy the runner only detects a stuck FRR import check, so before this change the harness never remedied one and a
stuck boot ended every strategy in an error. The harness now calls the product's own guard with `remedy=True` right
after its deploy, records the result in `import_check` (in the row and in each run's `run_details`), and turns every
strategy into an error when the remedy fails or a router can't be checked.

## Does the harness still measure the product?

| Question | Finding |
|---|---|
| Same routers as `netdryrun run` with deploy | yes: `frr_import_check.candidates(lab, driver_resolver(config.drivers))`, the runner's own resolver; strategies with different driver overrides are a case error |
| Same remedy | yes: `frr_import_check.guard(..., remedy=True)`, the call `run`, `record --deploy`, the MCP record tool and verify already make on a lab they deploy |
| Same point in time | yes: after the deploy, before the management default route is removed and before any check; each strategy's run still checks again (detection only) before its checks and before its verdict |
| Can the remedy change the state a case depends on | no: the case's edits are in the startup configs, applied at deploy, before the remedy; the guard requires bgpd's running config byte-identical across the toggle and no BGP session dropped or reset; the flood scenario runs inside the netdryrun strategy, after the remedy; no corpus case edits `bgp network import-check` |
| Other harnesses that deploy labs | `scripts/acceptance.py` deploys through `netdryrun run` and `record --deploy`, which remedy themselves |

## Error paths (each ends in status error for every strategy, or a case error)

- still stuck after the remedy; a router not checked; the guard's ImportCheckError: every strategy error, no strategy
  runs.
- mixed driver overrides across the strategies: case error, exit 2.
- a crash inside the remedy (probed: a `LabError` from `lab.exec`): a deterministic case stops the corpus run, as
  before; a nondeterministic run is recorded as error for every strategy, which the gate turns red.

## Findings

1. MEDIUM, fixed in 724a996: a crash inside the remedy left a nondeterministic run's row and `run_details` with no
   `import_check` record (reproduced with a fake lab whose `exec` raises on pe1). Now `evaluate` hands the record to
   `evaluate_run` as soon as it is known: "not reached" before the remedy, the crash if the remedy crashes, the
   remedy's findings if a strategy crashes later. Three new tests cover the three points. With 724a996's
   `corpus/run.py` alone reverted to d2a1b3a, those 3 and 2 tests in `tests/test_case18_exemption.py` fail (5 failed,
   250 passed); with it, 255 passed.
2. LOW, accepted: a router the harness can't check is status error, where the product's runner says inconclusive.
   The verdict is error either way. The harness keeps error on purpose (comment in `corpus/run.py`): the gate turns any
   error red, while a deterministic inconclusive is only compared with the committed result. Can't happen in the
   all-FRR v2 lab.
3. LOW: the harness runs the guard straight after `lab.deploy()`, without the runner's running-container check and
   node watch. A dead node costs up to the guard's 120 s budget before the error, instead of failing at once. Same
   outcome: error.
4. LOW, for the corpus refresh: the fix author's live run of v2 case 18 gave netdryrun unsafe in 5 of 5 runs. The
   remedy log shows pe1's aggregate stuck and remedied in 2 of the 5 boots and registered in the other 3, so both
   boot states were exercised. But that split is read from log order: `--case` prints only the first 4000 characters
   of the rows and writes no results.json, so runs 2 to 5's records aren't in the log. Leave `NONDETERMINISTIC.yml`
   and the gate's pin unchanged in this change. Revisit after the full refresh, from its results.json, with every run
   decisive and a larger sample of remedied boots; the case's history stays listed.
5. LOW: `test_without_the_harness_remedy_every_strategy_is_the_reported_error` monkeypatches `remedy_import_check`, so
   on a reverted `run.py` it fails with an AttributeError, not by showing the stuck error. The other new tests do go
   red on a revert.
6. NIT: when the guard raises, `routers` is `{}`; the partial findings are only in the error text. The mixed-driver
   case error could be raised before the deploy instead of after it.

## What was run

- d2a1b3a: `tests/test_corpus_import_check.py`, `tests/test_case18_exemption.py`, `tests/test_frr_import_check.py`:
  249 passed. With `corpus/run.py` alone reverted to 4388bb5: 10 failed (all 9 new tests and the amended case-18
  test).
- 724a996: the same files plus `tests/test_corpus_nondeterministic.py`: 255 passed; the revert of 724a996's
  `corpus/run.py` alone: 5 failed, as in finding 1.
- The subprocess test runs `run.py` from a copy of `corpus/` alone, as the release gate's live layer runs it: passes.
