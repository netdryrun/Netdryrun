# Layer 6: independent review, Netdryrun 0.4.0 (verify_change)

## Live runs before the review (branch `ndr/verify-change`)
The FRR parser had only been tested on synthetic output. Live captures from FRR 10.4.1 (`tests/fixtures/verify-lab`) and live `netdryrun verify` runs found that received routes were read after inbound policy, that a `default-originate` route was outside the listing verify read, four unknown path keys, and boot facts (management addresses, link-local next hops, zebra's `fe80::/64` choice, a graceful-restart stale path) that made a comment-only change fail. All fixed test-first; the fixtures are live captures now. The corpus v1 acceptance (cases 18 and 23 fail with an empty intent, 06 passes with its prefix declared) ran live too. Details: `design/verify_change.md`, revisions after the first live runs and for the 0.4 acceptance scope.

## Cold code review (fresh agent, no context: the diff `origin/main...ndr/verify-change -- src/ tests/` and the design)
| # | Finding | Severity | Decision | Commit |
|---|---|---|---|---|
| 1 | A PR adds a folder named like the base commit's hash: in the Action (hashes, the PR's checkout) the folder became the before side, the base's guards were dropped, and the change compared against itself: NO BEHAVIOR CHANGE | False pass (critical) | A side that is both a directory and a git ref is exit 2 | `run.py` `_is_ref`, test `test_cold_1_*` |
| 2 | Far ends of a session matched by address only (the last match won): a link /30 reused in another VRF let `appears_on b` explain a leak from c to d | False pass (high) | A candidate in the same VRF wins; an ambiguous pairing pairs nothing (stays undeclared) | `engine.far_ends`, tests `test_cold_2_*` |
| 3 | `advertisement ... goes: added` never compared the next hop (an outbound next-hop rewrite passed), nor aggregator and atomic-aggregate | False pass (medium) | The next hop must be the best path's or the node's own (0.0.0.0, ::, its session addresses) unless pinned; aggregator and atomic-aggregate join the compared attributes | `engine._advertisement`, test `test_cold_3_*` |
| 4 | The Action booted the PR head, never what lands (the PR merged into a base branch that moved on) | False pass (medium) | Before = the merge commit's first parent (the base branch tip), after = GitHub's merge commit (`github.sha`), whose second parent must be the PR head; refused otherwise | `action.yml`, test `test_cold_4_*` |
| 5 | Only the after side was rebooted for an approval: a before boot stably missing an item hides a change that removes it | False pass (medium) | An approval boots each side twice; the first difference is INCONCLUSIVE naming it (four boots per approval) | `run.confirm_by_rerun`, test `test_cold_5_*` |
| 6 | Two samples `settle` (15 s) apart can't see a timer that fires later (hold time, update-delay, delayed max-metric); nothing checks `settle` against the lab's timers | Possible false pass (medium-low) | **Rejected as a code change in 0.4:** a documented limit (design, cold review revision 7: `settle` must exceed the slowest timer in the lab); verify can't read every daemon's timers reliably. The doc keeps the rule; a timer-aware settle is a 0.4.1 candidate | — |
| 7 | `{}` from advertised-routes was read as "advertises nothing" with no cross-check | Possible false pass (low) | An empty listing for a session whose neighbor output counts sent prefixes is a failed read (retried, then exit 2) | `frr.sent_counters`, test `test_cold_7_*` |
| 8 | `goes: down` explained the whole session item on both ends, so a remote-AS, address-family or soft-reconfiguration change on that session rode along | False pass (low) | `goes: down` explains the session only when nothing but its state (established, local address) changed | `engine._session`, test `test_cold_8_*` |

Each fix was test-first: the reviewer's reproductions (1, 2, 3) became the failing tests, and tests for 4, 5, 7 and 8 fail on the code before the fix (4 proved against the previous `action.yml`).

## Advertisement intervals (0.3.2 multi-vendor audit)
| # | Finding | Severity | Decision | Commit |
|---|---|---|---|---|
| 9 | A peer's advertisement interval (MRAI) longer than `--settle`/`--hold` lets a leak arrive after a negative check sampled a prefix count stable at 0 | False pass | Fixed for FRR, SONiC and SR Linux: each driver reads the interval, and run's settle and hold, and verify's settle, stretch to the longest one plus 2 s (red tests: a 60 s peer, a leak at 45 s) | `runner._stretch_for_advertisement_intervals`, `converge.stable_snapshot` |
| 10 | Arista EOS: the advertisement delay (`neighbor ... out-delay`) is not in the captured `show` output, so it is not read (EOS's default, 0, is used) | False pass / **accepted documented limit** | Public in the config reference (convergence semantics) and the advisory's "Limits that remain": raise `--settle` and `--hold` above a configured out-delay on EOS. **Fix target: 0.4.1**, with the compatibility work (capture `show ip bgp neighbors` from a live cEOS lab, read the delay, test-first) | — |

## Merge with main (quality defences, 00d9cf7)
Main's new rule "the Action is green only on exit 0 AND status passed" made every verify approval red (status `matched`). Fixed: the result step computes `ok` per mode (run: passed; verify: matched or no_change), and the surfaces-agree test now covers verify mode (CLI, MCP and Action give the same verdict for the same run). The driver must-fail matrix gained its verify form: on the live FRR capture, every kind of item removed or changed fails an empty intent.

## Mutation layer
`verify.engine` and `verify.intent`: every survivor killed by a test (each kill proved with mutmut's per-mutant switch) or accepted in `accepted.json` with a reason and its diff fingerprint; acceptances are message wording or proven equivalent, never a mutant that can change a verdict. The engine changes from this review add mutants: the mutation layer runs again in the full gate.

## Merge with main (0.3.3, a38addc)

0.3.3's rejected-config reader (boot log since the container started, the "Failure to communicate" comparison with each daemon's running config, no sign of a load is an error) is the one reader for `run` and both sides of `verify` (`runner.config_load_by_node`); 0.4's duplicate parser, `Lab.logs` and `Driver.config_load_errors` were removed. `record` keeps 0.3.3's prefix ranges and guards with 0.4's per-VRF recording (guards in the default VRF only). In `mode: verify` the PR comment's header is read from the verify report.

## Expert gauntlet (fixed roster, 2026-10-30)

Batfish and Forward pointed at `verify_change`, plus Cisco, Juniper, NVIDIA, NTT Data/CDW, Starlink/Google Fiber and AWS/OpenAI/Anthropic, played by ChatGPT and Grok, and a code-reading agent. Eight false approvals and one timing gap, each fixed test-first and pinned in `tests/test_verify_gauntlet.py`:

| # | False approval | Fix |
|---|---|---|
| R1 | A link-local next hop set in config was compared as `fe80::`, so a typo was invisible | Named by the lab interface that owns it; one the node's config names keeps its address |
| R2 | A changed `daemons`, `vtysh.conf` or script could rewrite what FRR runs | Only an observed node's `/etc/frr/*.conf` may differ (exit 2 otherwise) |
| R3 | No bound file differed, and verify approved after four boots | "nothing to verify" (exit 2) |
| R4 | Config acting only on routes or events the lab never produces left no trace | The running config is in the snapshot; a change with no observable effect fails unless `config_change_on` declares it; approvals list untested lines |
| R5 | `appears_on` accepted a discard route | `state: discard`; installed needs a next hop that forwards |
| R6 | `send-community` / `local-as` toward an unobserved peer | Caught by R4 |
| R7 | A PR could edit the workflow that judged it | The Action refuses workflow edits (see the cold review) |
| R8 | `--unobserved` took an FRR router | Refused |
| S2 | A conditional-advertisement scan could land after both snapshots | `--settle` covers the timer |

Also from the coordinator: startup config a NOS rejects is detected on cEOS (`show startup-config errors`, live captures), relied on for SR Linux (containerlab's deploy fails), and a config bound into SONiC is an error.

## Cold review of the gauntlet fixes (fresh agent, 2026-10-30)

| # | Severity | Finding | Fix |
|---|---|---|---|
| 1 | BLOCKER | A BGP route whose next hop resolves over Null0, or an inactive gateway next to an active blackhole, still read "installed" | A next hop forwards only if active, in the FIB, and (recursive) resolved by one that forwards |
| 2 | BLOCKER | In `mode: run` the workflow guard was keyed on `path`, which the PR's workflow sets | Any change to `.github/workflows` or `.github/actions` together with anything else is refused; `mode: verify` also guards `.github/actions` |
| 3 | MAJOR | A node that only advertised the declared route counted as "behaving", so its config change was only listed | Only nodes a happened line names may carry untested config |
| 4 | MAJOR | The untested listing was cut silently in Markdown and MCP | "… and N more"; `added_total`/`removed_total` in the MCP result |
| 5 | MAJOR | `kinds:`/`groups:` binds were treated as reaching every node (a linux kind bind made a SONiC node an error) | `bind_reach` resolves containerlab's inheritance per node |
| 6 | MAJOR | A neighbour's random link-local (an unobserved SR Linux) kept its per-boot address | Kept only when the node's config names it; otherwise `fe80::` as in 0.3.3; one address on two interfaces is not named |
| 7 | MINOR | A bridge made a changed `defaults` bind an error | Bridges are left out of the reach |
| 8 | MINOR | An order-only config change listed nothing | Listed as an order change |
| 9 | MINOR | Untested lines were reported with a failed or inconclusive verdict | Only with an approval |

Not changed: `is_router_config` accepts any `/etc/frr/*.conf` (a `bgpd.conf` FRR ignores under an integrated `frr.conf` changes nothing in the lab or in production); rated MINOR by the reviewer.

## Multi-vendor audit (fresh agent, 2026-10-30)

| # | Severity | Finding | Fix |
|---|---|---|---|
| F1 | BLOCKER | A topology `exec:` command that fails is only logged; containerlab exits 0 (live: a `vtysh` line FRR rejected) | `Lab.deploy` fails on containerlab's "Failed to execute command" lines, naming node, command and output |
| F2 | BLOCKER | Under `check` (a lab Netdryrun didn't deploy), SR Linux and SONiC read "clean" with no evidence | `not verified on <driver>` there |
| F3 | BLOCKER | A JSON startup config SR Linux rejects deploys with rc 0 and runs without it (live) | SR Linux's log "Load of startup configuration failed" is read; unreadable is an error |
| F4 | MAJOR | verify passed `""` for unobserved nodes, so their load was never read | Read by detected driver, else by FRR's log |
| F5 | MAJOR | SONiC "setup checked" is exit code only | Stated; `vtysh -c` recommended for routing |
| F6 | MAJOR | SONiC bind scan missed `/etc`, `/usr`, `/var/lib` parents and inline startup configs | All flagged |
| F7 | MINOR | A node without a driver wrote no `config_load` | `not verified (no routing driver)` |
| F8 | MAJOR | A stale "Fix scheduled: 0.4" (file change time) | Moved to 0.4.1, in the CHANGELOG list |
| F9 | MAJOR | CHANGELOG contradicted itself on which platforms are verified | Fixed |
| F10 | MAJOR | The Juniper caveat was missing from the config reference, compatibility limits, junos.md and the advisories | Added (fix scheduled: 0.4.1) |
| F11 | MINOR | "Fixed in 0.4" text didn't carry F1–F3's scope | Rewritten |
| F12 | MINOR | cEOS errors are read at the end of the run, not at a known moment | Not changed: read after the checks, when the load has long finished |

## Repeated JSON keys (next-NOS session, offline scan, 2026-10-30)

**Finding (BLOCKER candidate):** Junos's live route captures (`junos_route_ibgp*.txt`) repeat `protocol-nh` inside one object. `base.load_json` was plain `json.loads`, so the last value silently won, and `junos._next_hop` reads that key: with two different next hops, a path check would judge one as if it were the only one. In the captures both copies name the same address, so no wrong verdict was observed; the path existed.

**Decision and fix (test-first, `tests/test_json_duplicate_keys.py`):** `base.load_json` refuses any repeated key (FRR, EOS, SONiC, SR Linux and verify's FRR collector; a scan of 91 fixtures and 59 research captures found none, so nothing changes today). Junos reads with its own hook, which joins repeated list elements in order and refuses any other repeat; `_next_hop` takes the selected next hop, or the one address all candidates name, and refuses several different addresses with none selected (never "the first listed").

## Adversarial review of the mutation acceptances (fresh agent, 2026-10-30)

The 255 `accepted.json` entries new or changed since 0.3.3, each read against its function and its current diff, doubtful ones run in WSL. **Rejected 2, reclassed 6, reasons corrected 4, upheld 243.**

- **Rejected: `engine._pins_ok` #59** (`len(cands) == 1` to `!= 1`, accepted as message text). With `state: received`, a BGP pin and no candidate path (the route's only BGP path is the best one, not installed: FRR `table-map`), the mutant indexes an empty list and `verify` exits 2 with an internal error instead of refusing the line. Not a false pass. **Decision:** killed by a test (`test_a_received_pin_with_no_candidate_path_is_refused_never_a_crash`), entry removed.
- **Rejected: `intent.load_intent` #4** (`encoding="utf-8"` to the locale's encoding, accepted as safety). Under a latin-1 locale, UTF-8 byte 0x85 decodes to NEL, which YAML reads as a line break: a commented-out `allow_anywhere` entry becomes live and widens what may change, so an undeclared change could be approved. Reproduced in WSL. The shipped code reads UTF-8; the mutant only showed that no test pinned it. **Decision:** killed by a test (`test_the_intent_file_is_read_as_utf8_whatever_the_locale`), entry removed. The same pin was added for the topology (`bind_reach`) in this round.
- **Reclassed equivalent to message text:** `intent._glob` #43, #100, #102, #104, #105 and `intent._allow` #36. The entry is still refused with an `IntentError`, only by a later check with a different message.
- **Reasons corrected (still equivalent):** `engine._flat` #17, #18, #23, #24. Config one-tuples and multi-entry RIB tuples do reach the line, but config fields are never read and multi-entry RIB output is filtered to `entries`.

## Mutation layer, final (81a49b3, 2026-10-30)

Every module passes on the gate commit. Fully gated, no survivor left unaccepted: `checks` 82, `config` 248, `runner` 161, `drivers` 230 (Junos included), `verify.engine` 71, `verify.intent` 122 accepted, each with a class, a reason and its diff fingerprint. Scoped (coordinator decision for 0.4): in `verify.frr`, `verify.snapshot`, `verify.converge`, `verify.run` and `verify.report` every survivor in the gated functions is killed or accepted (11 equivalent), and no mutant sits in code no test runs. The survivors outside the gated functions, **parsers that fail closed and rendering**, are named per function in `GATE.md`: `verify.frr` 872, `verify.report` 307, `verify.snapshot` 284, `verify.run` 231, `verify.converge` 12. Their full zero is the 0.4.1 gate item in RELEASES.md.

From the run on 1bf8693 to the gate commit: `snapshot.community_label`, never called, was removed (its 4 mutants were in code no test ran); new tests pin that a snapshotted node is read by its own driver, that the topology and the intent file are read as UTF-8, that a Junos key repeated as a list and as an object is refused, and that a received pin with no candidate path is refused.

**Accepted MAJOR:** `live/chaos-docker-restart` (optional by RELEASING.md; the lab machine is shared, and a Docker restart stops every container on it). `live/pack` and `live/scale` as in 0.3.3.

## Interop stress test, L1 (interop agent, 2026-10-31)

A mixed lab (cJunosEvolved 26.2R1.7-EVO, cEOS 4.36.3M, SR Linux 26.7.2, FRR 10.4.1) with the same checks run against every receiver of one advertisement. Report: HQ `research/interop/REPORT.md`; regression tests from live captures: `tests/test_interop_04.py` (from `ndr/interop` 4c7f510).

- **IOP-1, BLOCKER (Junos): a missing MED read as 0.** Junos omits `metric` when no MED was received; the driver defaulted it to 0, so `med: 0` passed on a route sent without a MED. **Fix:** absent is "not set", as on FRR and SR Linux.
- **IOP-2, BLOCKER (EOS): cEOS prints `"med": 0` for a path received with no MED.** **Decision (coordinator): fail closed.** No cEOS field separating the two cases was found in the capture, so a `med: 0` check on EOS is refused before the lab boots (`ambiguous_bgp_values`, exit 2, "EOS output cannot tell MED 0 from no MED"), and a MED that reads 0 is parsed as not set, so a `med: 0` check that reached a check could only fail. Non-zero MEDs unchanged. Documented in `config.md` and the EOS limits (`compat_verified.json`).
- **IOP-3, MAJOR (EOS): AS sets printed with spaces.** `{65004 65006}` is now `{65004,65006}`, as on every other driver (confederation sets `[a,b]` too).
- **Deferred to 0.4.1 (coordinator):** IOP-4, one SR Linux sample that answered rc=1 and did not recur (the test is in `test_interop_04.py` as a strict xfail: today it fails closed); IOP-5, a hold window that gets one sample when one pass over the checks is longer than the hold.

Gate rerun on the fix commit: static, unit, mutation on `drivers` (Junos and EOS included), live for the Junos and EOS cases.

**Gate after the interop fixes (coordinator: every layer on one commit).** Since 81a49b3 only `src/netdryrun/drivers/` changed (`__init__.py`, `base.py`, `eos.py`, `junos.py`); the tests were only added to (interop regressions, their edge cases, the gate's own tests), so a carried record can only understate what the tests kill. The gate gains `--carry-mutation`: mutation reruns `drivers` at the new commit, and every other verdict module keeps its 81a49b3 record only if its source is byte-identical (GATE.md says "carried over from 81a49b3" on each); a module whose source changed, or that is neither mutated nor carried, fails the layer. Unit, the full live matrix (corpus included) and static run in full on the new commit, static last.

Carried-over mutation records, each byte-identical to 81a49b3 (`git diff 81a49b3 3ca6145` is empty for its source): `checks` (src/netdryrun/checks.py), `config` (src/netdryrun/config.py), `runner` (src/netdryrun/runner.py), `verify.engine`, `verify.intent`, `verify.frr`, `verify.snapshot`, `verify.converge`, `verify.run` and `verify.report` (src/netdryrun/verify/). `drivers` was mutated fresh at 3ca6145, and it is the only module holding the EOS `med: 0` refusal (`check_supported` in drivers/__init__.py, its table in drivers/eos.py). That run left one survivor whose acceptance no longer matched: `drivers.x_check_supported__mutmut_47`, the same `', '` to `'XX, XX'` change in the unsupported-key message. Its diff context moved because the refusal lines follow it. It is still message text only, so its fingerprint is re-recorded (180f0dd… to b0f4a07…). This changes only `releases/`, not code or tests.

**Live layer (coordinator: keep live).** Live on 3ca6145; b4130ad differs only in releases/0.4.0/accepted.json and review.md. Unit, mutation (drivers fresh, the ten modules above carried over) and static ran on b4130ad. The interop L1 rerun runs on 3ca6145 too, and src/ and tests/ are byte-identical between the two commits.

**Repository rename (coordinator, 2026-10-31).** The repository is now github.com/netdryrun/Netdryrun. a46138b moves every current surface to the new name: docs, site, templates, examples, scripts, workflows, pyproject URLs and server.json `repository.url`. Some places keep the old spelling: the MCP Registry name `io.github.netdryrun/netdryrun`, the history (releases/0.3.x, advisories, older CHANGELOG sections) and the two `src/` links (cli.py FEEDBACK_URL, comment.py), which change in 0.4.1. The gate's Action-ref patterns accept either case, and a lowercase repo link in a public page is a stale phrase (fail-closed, tested). d180ece adds the Glama listing (prose only). `src/` is byte-identical to 3ca6145 at both commits. So the mutation record carries over: drivers was mutated fresh at a46138b and the ten other modules are carried from 81a49b3, each byte-identical. Unit and static ran on d180ece. Live stays on 3ca6145, which has the same `src/`, and so does the interop rerun.

## Interop run 2: IOP-6 and IOP-7 (2026-10-31)

Interop run 2 (the same mixed lab, rerun on 3ca6145) found two false passes; the owner pre-approved "BLOCKER fixed and re-checked, then publish". IOP-8 stays a strict xfail and moves to 0.4.1 (CHANGELOG, RELEASES.md). Tests from `ndr/interop` (652ee31..0f5ea24): `tests/test_interop_04_run2.py`; the fix's own edge cases: `tests/test_interop_04_fixes.py`.

- **IOP-6, false pass (SR Linux): a route rejected by import policy counted as received.** SR Linux keeps it in the BGP local RIB with `invalid-reason {rejected-route: true}`; the driver read it as a path, so `active: false` passed ("present via bgp (not selected)") and `present: false` failed, and a failure blamed an unreachable next hop. **Fix (9ea8b34):** `srlinux._received` leaves a rejected path out, as every other driver does; a path invalid for any other reason, or an `invalid-reason` that is not a map of booleans, is an error (`DriverError`), never a verdict.
- **IOP-7, false pass (Junos): the prefix count was Junos's accepted count**, which also leaves out a received route hidden for an unusable next hop (206 received, 205 accepted: `max: 205` and `exact: 205` passed; the reference count, received minus import-policy rejects as FRR, SR Linux and EOS count, is 206). **Fix (9ea8b34):** when received exceeds accepted, the driver reads the peer's hidden routes (`show route receive-protocol bgp <peer> table <table> hidden extensive`, output captured live from cJunosEvolved 26.2R1.7-EVO) and subtracts only those rejected by import policy. A received count lower than accepted is unexpected output. Must-fail tests: the 205 case and the live 3-received/1-accepted capture.

**Cold review of the fix (fresh agent, no context; fixes in 94a6cd4, each test-first):**

| # | Finding | Severity | Fix |
|---|---|---|---|
| 1 | Any hidden reason other than "rejected by import policy" was counted as received: a looped or martian route hidden by Junos made `min: 3` pass where the reference count is 2 | BLOCKER (false pass) | Only the two reasons seen live are classified (`REJECTED`, `NEXT_HOP_UNUSABLE`); any other, missing or empty reason keeps the count a range from accepted to received (`BgpNeighbor.prefixes_upto`), and a bound is judged only when the whole range agrees, otherwise the check fails with "can't tell whether the bound holds" |
| 2 | A failed hidden-route read was swallowed and the accepted count used | MAJOR | The error is kept (`BgpNeighbor.prefixes_unread`); a bound the range can't settle is `Unready` ("error: ...", no usable state), not a verdict |
| 3 | `record` wrote the lower end of a range as an exact count | MAJOR | A range is not recorded: an INCOMPLETE BASELINE warning asks for a check by hand |

Minor items for 0.4.1 (sent to the coordinator): the runner's convergence stability uses accepted counts only; an SR Linux release that omits `invalid-reason` is not covered; the neighbor and hidden-route reads are two commands (a route can change between them).

**Live repro on a real lab** (labs `ndr-iop6`, `ndr-iop7`, the failing interop cells and their neighbours, under the lab lock): run on 9ea8b34 and again on 8e9a376, with the same results. **Junos (`ndr-iop7`), 7 of 7 cells correct:** the count is 2 (received 3, 1 rejected by import policy); `max: 1` and `exact: 1` (the accepted count only) fail; the route hidden for its next hop is in the BGP table. **SR Linux (`ndr-iop6`):** the rejected route is absent (`present: false` passes) and `active: false` fails ("not active via bgp; seen: nothing"), the old false pass. One extra cell, `bgp_prefixes` expected 1, read 3. The expectation was wrong, not the driver: SR Linux counts 4 received, a looped route among them, and 1 rejected. That is SR Linux's documented loop-detection limit (`received-routes` counts looped routes, `compat_verified.json`). It is out of IOP-6's scope, and the cell is not a gate check.

**Mutation.** `drivers` and `checks` ran fresh at 8e9a376 (`drivers` 3077 mutants, 247 accepted; `checks` 1246, 82 accepted; none unaccepted). New acceptances, each with a class, a reason and its diff fingerprint: `junos._count_hidden` #4 (message text of the unread reason; the check is still `Unready`) and #16 (equivalent: `_table` tests `family == 6` only), `srlinux._received` #11-16 and #23-31 (message text), `srlinux._rib_rows` #26 (the command name passed for error messages only). Nine `_rib_rows` acceptances whose diff context moved were re-fingerprinted (#4, 11, 13, 19-24), unchanged in meaning. `checks._bgp_prefixes` #83 and #84 (the range detail text) are not accepted: a test pins the full message and kills both.

Carried-over mutation records, each byte-identical to 81a49b3 (`git diff 81a49b3 8e9a376` is empty for its source): `config`, `runner`, `verify.engine`, `verify.intent`, `verify.frr`, `verify.snapshot`, `verify.converge`, `verify.run`, `verify.report`. `checks` and `drivers` changed and were mutated fresh.

**Gate on one commit, 8e9a376:** unit (3723 passed, 2 strict xfails: IOP-4, IOP-8), mutation as above, the full live matrix (FRR, SR Linux, Junos, EOS, SONiC examples, corpus v1 and v2, signals, failure modes), the IOP-6/7 repro above, and static last.

## After publishing (2026-10-31)

Tag `v0.4.0` (annotated) on c236045, the READY TO PUBLISH commit. The release workflow published to PyPI through Trusted Publishing and created the GitHub release with signed provenance (run 41192110428); the MCP Registry workflow published `server.json` 0.4.0 (run 41192110427). The release branch was merged into main as c615ea8 (with `published-action.yml` at 0.4.0 and the CHANGELOG dated), and the site deployed from it. after-publish ran on 8e9a376, the commit every other layer ran on; the tagged c236045 differs from it only in `releases/0.4.0/`, so the published package is the same. All its BLOCKERs pass: pip and uvx on Python 3.10 to 3.14, frr-bgp from PyPI, and release consistency on every surface (PyPI, the GitHub release with the pasted notes, main, netdryrun.com and llms.txt, the MCP Registry).

**The Action by its tag (`after-publish/published-action`).** The gate reads the last `published-action.yml` run with the gh CLI, which the release machine doesn't use, so the check is a SKIP. The run was read instead through the public GitHub API: Published release run 68 on c615ea8 (main, the 0.4.0 merge, RELEASE 0.4.0, `uses: netdryrun/Netdryrun@v0.4.0`) completed with conclusion success, every job green: action-passes, action-catches-bad-change, and install on Python 3.10 to 3.15. https://github.com/netdryrun/Netdryrun/actions/runs/41192619813 Recorded with this evidence in `accepted.json`.
