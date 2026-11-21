# Re-check: ndr/fix-srl-evpn after 5bc6459 (RT-0058 reason, live captures, generic red-team check)

- Reviewer session: recheck-srl2. It wrote no code, test, fixture, record, evidence or allowlist in this change; this
  file is its only commit.
- Reviewed: f47f9da (258da1e, 2dcdd28, 48b42f4, 4a6c621, fac1cdf, 14b5ce6, 2c5cc81, f47f9da on top of 5bc6459), judged
  against main 6e77ebb, in a fresh clone, shared venv, `PYTHONPATH=src`. No lab was run.
- Verdict: **merge-after-fixes**. The SR Linux fix and its tests are sound: RT-0058 and the oracle now fail for the
  reason they claim, on the plant and on main's driver, and every one of 16 driver mutants is killed by the suite. The
  one MAJOR is in the generic red-team check `f47f9da` added (a WRONG_REASON entry never has to come off). Fix that,
  refresh the stale allowlist texts (MINOR 1), then merge.

## 1. RT-0058 and the oracle fail for the reason they claim

| Driver | Oracle FP-043-SRLEVPNVRF (3 tests) | RT-0058 in `tests/test_redteam.py` |
|---|---|---|
| fix (f47f9da) | 3 pass, no unanswered read | `does_not_pass`, `ends_in_its_refusal`, `rt0058_fails_on_the_drivers_own_verdict` pass; detail `unexpectedly in the BGP table (1 path(s); as-path ?, next hop 2.2.2.2, local-pref 100, ...)` |
| plant (`plant.diff` applied, `git apply --check` clean) | 3 fail: design A `no BGP path`, design B `no BGP path (received); a prefix this node originates itself isn't checked` | `does_not_pass` and `rt0058_...` fail: `passed: no BGP path (held 10s, 5 samples)` |
| main 6e77ebb `srlinux.py` | 3 fail, same two false passes | the same two fail, same detail |

On the plant and on main the failures are the false pass itself, never an unanswered read: the strict labs and the
case's outputs answer every read those drivers send. `fastfix_gate.py plants --base 6e77ebb`: 19 caught of 19, clean.
`reproduce --range 6e77ebb..HEAD`: clean (FP-043-SRLEVPNVRF fails on d8fee26, the plant is a port).

The pin works: mutant M5 below (the EVPN RIB never read) makes RT-0058 end in the driver's cross-check refusal
(`installed from bgp-evpn, but the EVPN RIB has no IP-prefix route`). `test_driver_case_does_not_pass` would accept
that; `test_rt0058_fails_on_the_drivers_own_verdict` and the generic refusal test kill it.

## 2. Mutants of the fix (`src/netdryrun/drivers/srlinux.py`)

Each mutant was applied alone and these were run: the oracle, the three RT-0058 tests, all of `test_redteam.py`,
`test_srl_evpn_043.py` (153), `test_oracle_guards_fp_043_srlevpnvrf.py` (9), and the SR Linux tests in
`test_driver_false_pass.py` and `test_verdict_drivers.py`. "x" = killed.

| Mutant | Oracle | RT-0058 | evpn_043 | Guards | Other SRL |
|---|---|---|---|---|---|
| M1 first best EVPN path, the next-hop-group never read | | | x (72) | | |
| M2 next-hop-group read, but the first candidate taken | | | x (19) | | |
| M3 no active bgp-evpn route: no path chosen, never a refusal | | | x (6) | | |
| M3b empty next-hop-group answer = the path is not used | | | x (2) | | |
| M4 route-table cross-check dropped (bgp-evpn installed, no EVPN path) | | | x (1) | | |
| M5 the VRF's own tables only (EVPN RIB never read) | x | x (reason pin) | x | | x |
| M6 M5 plus M4 (the plant's behaviour without the plant's lines) | x | x | x | | x |
| M7 a received path imported nowhere = absent | | | x (1) | | |
| M8 route-target ignored (`if into:` for `if vrf in into:`) | | | x (3) | x (1) | |
| M9 design-B bgp-evpn row read as the node's own (`_imported` = None) | | | x (21) | | |
| M10 design-B local-pref cross-check dropped | | | x (3) | | |
| M11 the ip-vrf's bgp-evpn rows kept as own entries | | | x (9) | | |
| M12 ECMP accepted (one matching VTEP is enough) | | | x (8) | | |
| M13 stale EVPN path accepted | | | x (3) | | |
| M14 missing network-instance = absent (oper-state confirm skipped) | | | | | x (4) |
| plant.diff | x | x | x (87) | | x |
| main's driver | x | x | x (134) | | x |

No mutant survives the suite. RT-0058 and the oracle are single-PE captures, so they only see "the EVPN path is not
read at all"; selection (M1 to M3b, M12), route-target (M8) and design-B internals (M9 to M11) are held by the
two-PE live captures in `test_srl_evpn_043.py`, which is as designed (FX-0.4.3-srl-evpn-first-path).

## 3. The captures look like genuine single-run live captures

`srl2672_fp043_rt58_*` (design A) and `srl2672_fp043_pece2b_*` (design B):
- Ids agree across files. rt58: the route names next-hop-group 3530614221, the group's one next hop is 3530614219,
  the next hop is 2.2.2.2 on vni 99, the EVPN row's attr-id 6 is the attr-set read. pece2b: route group 3692599526,
  next hop 3692599523, EVPN attr-id 8, the ip-vrf row's attr-id 10 is the ip-vrf attr-set read, local-pref 100 on
  both. The next hop's `destination-mac` equals the attr-set's `mac-nh` in each run (1a:3d:01 in rt58, 1a:f6:02 in
  pece2b, 1a:5b:01 in the older present_* run): three deploys, three leaf2 MACs, each consistent inside its run.
- The clocks agree. rt58: leaf1 booted 21:38:51Z, every route programmed 21:39:12.9Z, read 19 to 23 s later
  (04:39+07:00, as SOURCES.yml says). pece2b: booted 22:05:51Z, the reads' "N seconds ago" climb 31, 32, 32, 33 in
  the driver's read order, then 36 to 39 for the after-reads (05:06:42 to 05:06:48+07:00, as SOURCES.yml says).
  Each commit came after its capture (04:53 and 05:07:41).
- Start and end route-table reads are the same route and group; only the "seconds ago" moves (21 to 23, 32 to 37).
- Shape: byte for byte the same layout as the older live captures (`present_*`, `twope_*`): same keys and order,
  2-space indent, LF, one trailing newline, the same sizes give or take the digits of the ids. The id spacing (next
  hop = group - 2 or 3, resolving tunnel = next hop + 4 or 5) matches the `twope_*` captures. Nothing looks
  hand-edited.
- SOURCES.yml has an entry for each set with image digest, version, lab inputs, the exact command per file and the
  time window. `pece2b_ce1_running.conf` is identical to `pece2_ce1_running.conf`, as its entry says.

I can't prove a capture is live from the files alone; nothing in them points the other way.

## 4. The generic check in test_redteam.py

- **The harness copy matches `origin/ndr/fix-eos-agg-v3` exactly.** `git diff origin/ndr/fix-eos-agg-v3 HEAD --
  tests/test_redteam.py` shows only the additions (REFUSALS, WRONG_REASON, the two new tests). In a scratch merge of
  the two branches `tests/test_redteam.py` merges without conflict.
- **A harness error can't count as caught.** An unanswered command fails the test from `_run_driver_case` whatever the
  driver does with the exception, a missing fixture is a collection error, and an answer of the wrong shape ends in an
  `error:` detail that fails the generic test unless the case is in REFUSALS (phrase must match) or WRONG_REASON.
- **REFUSALS entries are real driver refusals.** All 11 end in exactly their phrase on f47f9da (each detail checked).
  RT-0008, 0038, 0039, 0043, 0053, 0069 and 0072 match the driver's own refusal wording. See MINOR 2 for the other four.
- **WRONG_REASON is a loophole (MAJOR 1).**

### MAJOR 1: a WRONG_REASON entry skips any error and never has to come off

`test_driver_case_that_ends_in_an_error_ends_in_its_refusal` skips a WRONG_REASON case on any `error:` detail, and
nothing fails when the entry no longer describes what the case does. Shown in the scratch merge with
`origin/ndr/fix-eos-agg-v3`: RT-0037 no longer ends on the missing routingDisabled; it ends in its real refusal,
`error: unexpected output from show ip route <prefix> | json: routeType 'nexthopGroupStaticRoute' ... is not one this
driver maps to a protocol`. It is still skipped. The comment says such an entry "falls back to" the check, but it
never can, because a refusal is itself an `error:`. The same holds for RT-0021, 0022 and 0027: once their pathCount
answers are fixed, any other error they end in is skipped too.

Fix:
- Key each entry on a phrase of its known wrong error, for example `"without pathCount"` and `"routingDisabled is
  None"`. Skip only when the detail contains that phrase.
- Otherwise fail with "the case no longer ends in its known wrong reason: remove it from WRONG_REASON".
- On the merge with fix-eos-agg-v3, move RT-0037 to REFUSALS (`"is not one this driver maps to a protocol"`).

This does not open a product false pass, because `test_driver_case_does_not_pass` still holds every case. But it is
exactly the "each name must come off" rule (FX-0.4.3-redteam-fake-unanswered-command,
FX-0.4.3-frr-redteam-cases-wrong-reason), and it is cheap to fix before both branches land.

### MINOR 2: four REFUSALS phrases match echoed data, not the refusal's wording

- RT-0049 `bgp community alias 65020:777 65020:100` and RT-0083 `asPath: '64086.59905 65020'` match text the
  generic `unexpected output from ...` error echoes back.
- RT-0012 `View/Vrf is unknown` and RT-0009 `` show ipv6 bgp summary vrf default | json` failed `` match the
  device's stderr and the command-failed wording. For RT-0009 that is the refusal its fix is, so it is fine.

Another error that echoes the same data would match. Anchor them on the command, for example
`` unexpected output from `show ip bgp <prefix> | json`: asPath: ``. Low risk today, since each case has one such
read.

### MINOR 3: only `error:` details are checked

A harness-made unready verdict without that prefix (the shape of RT-0080's `... can't be read: ...`) passes the
generic test unchecked. Consider also checking `samples_unready` results.

Nit: the module docstring still says the file "imports nothing from other test files". It now imports `fakes`. The
same is true on fix-eos-agg-v3.

## 5. Scratch merge with origin/ndr/fix-eos-agg-v3 (2a0438b)

`git merge --no-commit` from f47f9da gives content conflicts in 6 files, none in code or in test_redteam.py:
- `CHANGELOG.md`
- `advisories/0.4.1-known-false-passes/README.md`
- `tests/fixtures/SOURCES.yml`
- `tests/known_false_passes.yml` (2 hunks)
- `tests/test_known_false_passes.py`
- `website/docs/trust.md`

Each branch removes a different accepted limit. The merged result must keep both removals:
- `test_known_false_passes.py`: `{"RT-0048"}`;
- `known_false_passes.yml`: `cases: []` for that group, with the rt-0058 entry and the rt-0056/0063, rt-0085 and
  rt-0086 entries all kept;
- SOURCES.yml: both new blocks.

With the conflicted files taken from this branch, the merged `test_redteam.py`, `test_srl_evpn_043.py`, the oracle and
its guards gave 280 passed, 4 skipped, 1 failed. The failure is `test_ids_are_contiguous` (RT-0084 missing). That
comes from fix-eos-agg-v3's renumbering, which waits for RT-0084 on `ndr/fix-frr-importchk-v2`, so it is not this
branch's problem.

## 6. Allowlist `fastfix/allow/0.4.3-srl-evpn.yml`: all 7 flips genuine

I ran `fastfix_gate.py loosening --base 6e77ebb --candidate f47f9da`: clean, the same 7 flips, all `new-read on
srlinux`, all allowed, nothing else. I also ran main's tests with the candidate's `src`:
- RT-0058: main's accepted-limit case answers only the bgp-rib and oper-state reads. The candidate's EVPN RIB read is
  unanswered (`unexpected command`), so "the documented limit no longer holds". On the branch the case is fixed,
  `fixed_in: 0.4.3`, and its outputs answer every read from the rt58 run.
- The four `test_verdict_drivers` tests: an unanswered route-table read, an EVPN read answered by a `bgp-rib` needle
  with a route answer, or the command list longer by the EVPN read. Each test's update on the branch adds exactly
  those reads.
- The two `test_driver_false_pass` tests: they pass on main's version with the candidate's src. Only the command log
  shows the new EVPN read. On the branch (2dcdd28) they also pin the full read sequence.

No assertion was weakened in any of them.

### MINOR 1: three entries describe the old state

- The RT-0058 entry's `evidence` cites `srl2672_fp043_present_*` captures and its `why` says the outputs gain those and
  that "tests/test_redteam.py is unchanged by this branch". Both are now false: the case answers from
  `srl2672_fp043_rt58_*` (next-hop-group 3530614221, next hop 3530614219), and f47f9da changed test_redteam.py.
- The two test_driver_false_pass entries say "The test file is unchanged by this branch". 2dcdd28 changed it.

The flips are still genuine. Refresh the evidence and texts before the allowlist commit.

### Sentences for `reviewed_by`

| Flip | Genuine | `reviewed_by` |
|---|---|---|
| `tests.test_redteam::test_accepted_limits_are_published_and_still_behave_as_documented[RT-0058-srl-evpn-bgp-route-absent]` FAIL->PASS | yes | `recheck-srl2: RT-0058 is fixed in 0.4.3 and leaves the accepted limits; it fails on the driver's own verdict (unexpectedly in the BGP table, next hop 2.2.2.2) with every read answered from the live rt58 run, next-hop-group and next hop included; fails on the plant and main's driver` |
| `tests.test_verdict_drivers::test_srl_bgp_paths_commands` FAIL->PASS | yes | `recheck-srl2: the expected command list gains exactly the EVPN RIB and route-table reads; the nope case still raises from oper-state` |
| `tests.test_verdict_drivers::test_srl_evidence_is_kept_everywhere` FAIL->PASS | yes | `recheck-srl2: the bgp_paths evidence count in a vrf goes from 2 to 4, the two new reads; other counts unchanged` |
| `tests.test_verdict_drivers::test_srl_local_pref_from_the_neighbor` FAIL->PASS | yes | `recheck-srl2: only the _srl_paths_lab helper answers the new reads with empty containers; every assertion unchanged` |
| `tests.test_verdict_drivers::test_srl_routes` FAIL->PASS | yes | `recheck-srl2: one more expected command, the EVPN RIB read in a named vrf; route values and call counts unchanged` |
| `tests.test_driver_false_pass::test_srl_existing_network_instance_without_the_route_is_a_real_absence` FAIL->PASS | yes | `recheck-srl2: passes on main's version with the candidate's src, flagged by the command log only; the branch's version pins the four reads in order and absence is still []` |
| `tests.test_driver_false_pass::test_srl_unknown_network_instance_raises_instead_of_no_routes` FAIL->PASS | yes | `recheck-srl2: passes on main's version with the candidate's src, flagged by the command log only; the branch's version pins the reads and the driver still raises NoSuchInstance from oper-state` |

## Other notes

- MINOR 4: `_read_evpn_path` checks the EVPN attr-id with `str.isdigit()`, not `_index`, which only takes ASCII
  digits. A `²` from the device would go into the command, where SR Linux would refuse it. That is not an injection,
  but use `_index` for consistency with the design-B attr-set read.
- `test_a_route_imported_into_another_ip_vrf_is_not_a_path_in_this_one` asserts only `not r.passed`, so a refusal
  would satisfy it. M8 still kills it through the path, so this is a nit.
- Full suite on f47f9da, fresh clone: 8656 passed, 70 skipped, 1 xfailed.
