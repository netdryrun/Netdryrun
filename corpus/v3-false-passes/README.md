# Corpus v3: the false passes

Every case here is a change, a lab or a pull request on which a version of Netdryrun (or of its `verify` code before release) **said yes when the answer was not yes**, or in two cases (03, 04) is a smoke test of a rule that has its own tests. Each is a small, self-contained, rerunnable case with the verdict recorded before anything was run, the release that fixed it, and the test that now holds it.

The [Verdict Corpus](../../website/docs/corpus.md) asks whether Netdryrun catches harmful network changes. This set asks the harder question about the tool itself: **where did it pass something it should not have, and does it still?** We publish our own failures because that is the evidence a change tester has to earn.

## The rules

- **The expected verdict is written first.** Each `case.yml` was committed before any case was run (`pre_registered`), and `MANIFEST.sha256` pins the file. A change to an expected verdict after that is listed in [AMENDMENTS.md](AMENDMENTS.md) with the reason; `check_cases.py` fails if the manifest and the files disagree.
- **Every expected verdict is a failure or an error.** Never a pass: a false-pass case that expects a pass proves nothing. `check_cases.py` enforces it.
- **A case says which versions it applies to.** `expected_from` is the first version that must give the recorded verdict. Older versions are the ones that got it wrong; `run_cases.py` skips a case on an older version instead of expecting the impossible. Several cases are marked from 0.4.0: 0.4 is not released yet, and they do not apply to 0.3.3.
- **Honest provenance.** Cases 01, 02 and 08 are false passes in **released** versions (0.3.2, 0.3.3): 01 and 02 have an advisory each; 08 was a limit we had already disclosed for 0.3.3. Cases 03 to 07 were found by our own review of the **unreleased** `verify` code before it shipped; they never reached a user, and the write-up says so.
- **Written and checked offline; not yet run in a lab.** `live_verified: false` in every `case.yml` until a lab run confirms the verdict. The offline check proves the files are well-formed and consistent with the write-up. It does not prove the verdict. Where a lab run shows the pre-registered expectation to be wrong, that is a published correction, not a quiet edit.

| # | Case | Mode | Passed wrongly in | Fixed in | Expected |
|---|---|---|---|---|---|
| 01 | [A config line FRR rejects at boot](cases/01-rejected-config-line/WRITEUP.md) | run | 0.3.2 and earlier | 0.3.3 | error (2) |
| 02 | [A topology `exec:` command that fails](cases/02-failed-topology-exec/WRITEUP.md) | run | 0.3.3 and earlier | 0.4.0 | error (2) |
| 03 | [A link-local next hop that is a typo](cases/03-link-local-next-hop-typo/WRITEUP.md) | verify | 0.4 development build | 0.4.0 | failed (1) |
| 04 | [A changed FRR `daemons` file](cases/04-changed-daemons-file/WRITEUP.md) | verify | 0.4 development build | 0.4.0 | error (2) |
| 05 | [The change edits a file the lab never loads](cases/05-no-bound-file-differs/WRITEUP.md) | verify | 0.4 development build | 0.4.0 | error (2) |
| 06 | [A declared route that is only a blackhole](cases/06-appears-on-a-blackhole/WRITEUP.md) | verify | 0.4 development build | 0.4.0 | failed (1) |
| 07 | [A pull request edits the workflow that judges it](cases/07-pr-edits-its-own-workflow/WRITEUP.md) | Action | 0.4 development build | 0.4.0 | step fails (1) |
| 08 | [An SR Linux startup config the router rejects](cases/08-sr-linux-startup-config-rejected/WRITEUP.md) | run | 0.3.3 and earlier | 0.4.0 | error (2) |

The 0.3.0 advisory's seven config-shape cases are in [advisories/0.3.0-false-pass](../../advisories/0.3.0-false-pass/README.md) and need no lab.

## Rerun

```bash
python corpus/v3-false-passes/check_cases.py             # offline: no lab, no Docker
python corpus/v3-false-passes/run_cases.py --dry-run     # what would run
python corpus/v3-false-passes/run_cases.py               # needs Docker and containerlab; one lab at a time
```

Each case folder has `case.yml` (the verdict), `WRITEUP.md` (what passed wrongly, why, what now holds it) and the files to run: `lab/` for a `netdryrun run` case; `lab/`, `before/`, `after/` and `intent.yml` for a `verify` case (run from inside the case folder); `base/` and `head/` for the Action case.

## Found another one?

[Open a corpus case](https://github.com/netdryrun/netdryrun/issues/new?template=corpus-case.yml): it becomes a permanent must-fail test, credited to you.
