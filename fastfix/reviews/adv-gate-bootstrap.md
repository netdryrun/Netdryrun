# Gate review: the release gate's command log at a log-less base, and the kind bridge for 0.4.3

- Reviewed in two rounds by two fresh sessions. Neither wrote code, tests, records or allowlists in this change.
  - Round 1, session adv-gatelog: c52d623 and 7968d9e (now 9db75db and 187da86, the same changes).
  - Round 2, session rev2-gatelog: the fixes 8743ed2 and d90cbb6. This file is round 2's only commit.
- Base: main 4388bb5, judged against the published v0.4.2 (61cd95de8b54). Work was done in fresh clones in WSL
  Ubuntu-ndr, with the shared venv and `PYTHONPATH=src`.
- Final verdict: **APPROVE** (round 1: approve with fixes; round 2: every fix verified).

What the change does:
- (A) When the published base's fixtures keep no fake-lab command log, the gate loads its own pytest plugin
  (`scripts/fastfix_cmdlog.py`, with the judge's `tests/fakes.py`) into both dominance runs, base and mixed.
- (B) A keyed, expiring kind bridge, for 0.4.3 against v0.4.2 only. It drops the frozen v0.4.2 judge's lines for
  allowlist entries that are rejected only for their `kind` key, and only when HEAD's dominance run matched the same
  entry to the same new-read flip.

## Round 1 (adv-gatelog): approve with fixes

1. **HIGH: a gate-kept log turned off the changed-driver live routing.**
   - What happened: `release_gate.new_read_problems` sends every network OS whose driver changed since the release to
     live when the base keeps no command log. The plugin's log set `command_log_at_base`, so that routing was dropped.
   - Why it matters: the v0.4.2 fixture world was never under `tests/test_fakes.py`'s unseen-fake guard. HEAD's shape
     scan over it finds two stand-ins the profiler can't see: `inj._apply_config = removed.append` in
     `tests/test_inject_sent_counts.py`, and `exits.append` in `tests/test_runner_robustness.py`. The real v0.4.2 log
     has 0 lines for `_apply_config`.
   - Impact on 0.4.3: `drivers/base.py` changed since v0.4.2, so before the change every OS needed live. After it,
     only the OSes named by new-read flips or entries did.
   - Red tests:
     - `test_a_gate_kept_log_at_an_unaudited_base_still_routes_changed_drivers_to_live[junos|*]`
     - the v0.4.2 fixture-world scan
2. **MEDIUM: the bridge's evidence comes from code the candidate can change.** In the bootstrap, HEAD's judge
   validates the entries the bridge lets through. This is acceptable because the run is a fingerprinted MAJOR and
   HEAD's `allow_entries` is strictly stronger than v0.4.2's. Ask: say so in the MAJOR's text.
3. **LOW: `tests/fakes.py` runs on the plugin path but was not gate code** (not in GATE_FILES).
4. **LOW: the raw log was not byte-stable at a log-less base.** A thread-pool test in v0.4.2 logged its rows in a
   different order on each run. The per-test sets the gate compares were identical.
5. **LOW: two internal record ids were added to product files.**

Held in round 1:
- The kind bridge, across 31 red cases plus a cross-check against the real v0.4.2 judge.
- Symmetry: the same plugin and fakes run on both sides, and the candidate's `tests/` never enters the base world.
- The tamper paths: a deleted log or a removed env var still blocks.
- The plugin is not loaded when the base logs by itself.

## Round 2 (rev2-gatelog): APPROVE

**Each fix, reverted alone, turns its test red.** Each case below is a fresh clone at d90cbb6 with one edit.

| Revert | Result |
|---|---|
| Routing back to `if not logged` | 8 failed: both unaudited-base cases, all 5 sources of `test_only_the_bases_own_fixture_log_lifts_the_changed_driver_routing`, and the v0.4.2 world test |
| Routing kept only for source "gate", so an unknown source lifts it | 4 failed (sources missing, "fixture", "", 1) |
| The bridge caveat removed from the MAJOR | `test_the_frozen_judges_kind_lines_are_dropped_by_name_and_the_run_is_a_major` fails |
| `tests/fakes.py` removed from both GATE_FILES | 2 failed (the gate-script flip case and the plugin test) |
| `tests/fakes.py` removed from one GATE_FILES list | 3 failed (adds `test_the_gate_lists_of_both_gates_agree`) |
| No sort, or sort by test only | `test_the_gates_log_is_byte_stable_when_threads_reach_the_fakes_in_any_order` fails |

The diff 4388bb5..d90cbb6 adds no internal record id.

**Live routing.** The routing is lifted only when `command_log_at_base` is exactly true and `command_log_source` is
exactly "fixtures". Every other case keeps it: "gate", a missing source, an unknown source, a non-string, or
"fixtures" without a log. A missing `changed_drivers` reads as every driver.

Only the judge sets "fixtures", and only when `logs_by_itself` reads it from the published base tree, which the
candidate cannot change. In the 0.4.3 bootstrap, both the judge and the router are HEAD code. Editing either is a
v0.4.2-judge gate flip that clears only through a blob-keyed allowlist entry from an independent session, plus the
bootstrap MAJOR.

**`tests/fakes.py` in GATE_FILES.**
- Both lists agree. v0.4.2's frozen list lacks the file, so the v0.4.2 judge prints no line for it.
- The commits touching `tests/fakes.py` since v0.4.2 all carry Session trailers.
- None of their sessions wrote or reviewed an allowlist entry, so the separation check gains no new problem.

**Sorting.** The gate reads the log only as a set of commands per test, so neither order nor counts are compared.
- The sort keeps duplicate lines.
- Temp-path labels are already in the rows (log format 2) before the sort, so it can't renumber them.
- A row that doesn't parse raises before the proof is written, so the run fails closed.

**No new loosening** in the full diff 187da86..d90cbb6.

**Tests.** `tests/test_fastfix_gate.py`, `tests/test_release_gate*.py` and `tests/test_fakes.py`: 630 passed,
1 skipped.

Low notes (not blocking, none introduced here):
- A. Every later fix that edits `tests/fakes.py` is now a gate flip. It needs its own blob-keyed allowlist entry
  from a separate session, and so does any further edit before 0.4.3.
- B. The changed-driver routing covers files under the drivers directory only. The stand-in that motivated finding
  1 is on the inject restore path, which is not a driver: a change there alone routes nothing to live. This is moot
  for 0.4.3, where every OS goes to live. The gap predates this change; source files the command log can't see
  should get their own live routing.
- C. For 0.4.3, the acceptor of the bootstrap MAJOR should check two things: that `gate/dominance.json` says
  `command_log_source: "gate"`, and that the report routes every network OS to live.
