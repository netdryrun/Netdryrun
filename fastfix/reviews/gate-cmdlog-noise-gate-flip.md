# Gate-file review: ndr/gate-cmdlog-noise (scripts/fastfix_gate.py@a8cfb442fc95)

- Reviewer session: recheck-cmdlog2. It wrote no code, test, fixture, record, evidence or allowlist in this change;
  this file is its only commit.
- Reviewed: 0694995 (697aa2f, 921e5c5, 0694995 on top of 47f8688), judged against main 6df498a, in a fresh clone,
  shared venv, `PYTHONPATH=src`.
- Verdict: the gate-file flip `gate :: scripts/fastfix_gate.py@a8cfb442fc95: FAIL -> PASS` is acceptable. Every
  change to the gate either refuses more, or removes run-to-run noise with a red fixture showing a real change still
  shows. One documented limit stays (old-format logs, below).

`loosening --base origin/main` on 0694995 shows only this flip, with 0 command-log flips. The 3 noise flips earlier
reviews listed (`test_startup_config_load::test_audit_f1_*` and two `test_verdict_keys_041::test_action_verify_*`) are
gone. With 921e5c5 as the base, a no-op commit and a comment-only `src` commit each showed 0 flips.

## What changed in scripts/fastfix_gate.py, and which way it points

| Change | Direction | Why that's safe |
|---|---|---|
| A log row with a `log` value other than 2 is refused (exit 2) | stricter | an unknown format can't be read as "nothing new" |
| `compose` refuses a candidate `src/` package the base doesn't have; `preflight` refuses a stdlib or gate-tool name under `src/` | stricter | before this, a candidate `src/json/` shadowed the standard library inside the judged run: a new command was rewritten into an old one and `loosening` came back clean (probe `src_extra_pkg_json`, exit 0 on 921e5c5, refused with exit 2 on 0694995) |
| Base and candidate write one log path, deleted before each run | neutral | the path is in the environment the code may pass on; two paths logged two commands for the same code |
| The trees under test are `<root>` (whole path names) | removes noise | a tree path differs per run; fixture `test_a_new_command_next_to_a_temp_path_is_still_a_new_read` keeps a new argument next to it visible |
| Rows with no `log` key (a base older than this change) lose the 8 random characters of `netdryrun-<what>-` scratch directories, numbered per `<what>` | removes noise, with one limit | applies only while the base's fakes predate format 2; the folder name and kind are kept (`test_an_older_logs_scratch_directory_keeps_its_kind`), a location change still shows. Limit: two directories of one `<what>` that trade places between two commands of one test read the same. It is written in the gate's comment and ends once main logs format 2 |

The scrubbing itself lives in `tests/fakes.py`, which the gate always takes from the base's tree. Those changes were
reviewed as well: only the random last name of a temporary path is replaced (the parent stays), and the environment is
logged by its difference from the session's start for every environment-like mapping and, on each call, for the live
process environment, including `os.putenv`/`os.unsetenv`.

## Probes (real `loosening`, base vs candidate)

Toy repository with the branch's `fakes.py` and gate, 25 probes:
- New command; environment set at import through a copy, `os.environ` itself, `.copy()`, a `MappingProxyType`, the
  inherited environment (`env=None`), or `os.putenv`: all flagged.
- Scratch directory moved with `mkdtemp(dir=)`, `tempfile.tempdir` or `TMPDIR`: flagged (each one was missed on
  921e5c5).
- `os.mkdir` under `gettempdir` with a new command, a swap between two product temp dirs, a sibling directory: all
  flagged.
- `src/json/` refused. `src/json.py`, a namespace directory, a `.pth` file, a nested `src/netdryrun/json` package and
  a `sys.path` insert from inside the product: not copied, or no effect; the new command is still flagged.
- Comment-only: 0 flips.
- Noise, safe direction: a `putenv` the command never receives adds a flip.

Real repository, candidate = 0694995 plus one edit:

| Edit | Flips |
|---|---|
| comment only in `lab.py`, `frr.py` and `verify/run.py` | 0 |
| `verify/run.py` scratch directory moved with `mkdtemp(dir="/dev/shm")` | 2; it was 0 on 921e5c5 |
| `TMPDIR` set at import | 1329 |
| `DOCKER_HOST` set at import | 1328 |

Other checks:
- The fixture targets were run twice with the log on: 2867 passed, and 0 of 1329 tests logged a different command
  set. Only 10 rows carry `<environment now>`: `NETDRYRUN_DEBUG=1`, which the CLI sets in-process, the same in both
  runs.
- `tests/test_fakes.py` and `tests/test_fastfix_gate.py`: 310 passed, 1 skipped.
- A change inside the real `Lab.exec` shows nothing, because no fixture test runs it (no `docker exec` row in the
  log). That is the fixtures' coverage, not the log's scrubbing.

## Mutant survivors

- K4 (`value is os.environ` shortcut removed): `os.environ` is still recognised by its shared keys. The mutant
  differs only when the environment has fewer than 4 variables or has lost half of them. Then `os.environ` is logged
  in full, which is louder, never quieter. No practical difference.
- K12 (putenv record not reset in `begin_session`): the record starts empty when the module loads, and the wrappers
  that fill it are installed only by `begin_session`, which runs once. Equivalent.
- G5 (work dir as a root): no observable effect, as reported in the earlier rounds.

## Still open (outside this flip)

- FX-0.4.3-gate-cmdlog-set-and-tamper stays suspected and is not fixed here. Product code runs in the same process
  as the log writer and can still change it: a product `__init__` that swaps `fakes.json` for a rewriting one hides
  a new command (exit 0). The log is also still a set per test, so the order and count of commands are not compared.
