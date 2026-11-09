# Layer 6: independent review, Netdryrun 0.4.1

Compiled 2026-11-05 from the git history, `CHANGELOG.md`, `reports/quality/YIELD.md`, the model outputs and the design records. Every test named below was found by grep in `tests/` of the worktree at `8ce7dde`; "TEST NOT FOUND" marks a claimed fix with no test to cite. Severities for rounds 3-9 are labels inferred from the effect the CHANGELOG states (the fresh reviewers' own ratings were not recorded); GPT, Grok and the adversaries' ratings are quoted where they gave one.

## Provenance

The reviews ran against these commits; the fix commit is the one that follows. Each fix commit holds the failing tests (several round-2 to round-6 tests were replaced when a later round rewrote the same rule; the table then names the test that covers the finding at `8ce7dde` and says so).

| Review | Reviewed | Reviewer | Fix commits |
|---|---|---|---|
| Review minors | 0.4.1 candidate, 2026-10-31 | not named in `b74166e` | `b74166e` |
| Cold review | 0.4.1 candidate, 2026-11-01 | fresh agent | `16775ad` |
| Round 1 | `b03cb7a` (11-03 05:14) | cold review (fresh agent, ~205k tokens) and adversarial reviewer (accepted mutants) | `4861c17`, `3c9a119`, `97839ca`, `fdef8fd` (kill tests `288b32b`, `eaa323c`) |
| Local model pass | about `fdef8fd` (brief 11-03 08:22, "subset brief"; commit not recorded in the file) | Ollama qwen3-30b-a3b | none needed |
| Round 2 | `eaa323c` (11-03 10:24) | cross-platform reviewer (~176k tokens), GPT and Grok (brief sha256 3efe93d0bb84, 11-03 15:22) | `e1c287f`, `c239e74` (`ddfdf4a` syncs llms-full.txt) |
| Round 3 | `5e65852` | fresh reviewer (~190k tokens) | `bf29e89` |
| Round 4 | `bf29e89` | fresh reviewer (~168k) | `45f63df` |
| Round 5 | `45f63df` | fresh reviewer (~125k) | `1a597d7` |
| Round 6 | `1a597d7` | fresh reviewer (~132k) | `f994222` (`99fe33e` adds a test) |
| Round 7 | `99fe33e` | fresh reviewer (~138k) | `ba4095d` |
| Round 8 | `ba4095d` | fresh reviewer (~149k), no BLOCKER | `02a96a2` |
| Round 9 | `02a96a2` | not recorded in YIELD (CHANGELOG does not say "fresh reviewer") | `b88adef` |
| Limit-proof code review | `0563e93` | GPT, Grok, fresh adversary (`research/model-reviews/release-0.4.1/limit-proof/`) | none: not shipped |
| Limit-proof design rounds 1-3 | design only (`design/attributable-limit-proof.md`) | the same adversary, a fresh one in round 3, two design reads | none: not shipped |
| Case-18 rule | design text, then code (11-05) | fresh adversary, fresh code check, fresh exception adversary | `35bf618`, `7da759b`, `94f5174`, `43ecdf8`, `22ea4b9` |

Each round's fixes also have an entry in `tests/known_false_passes.yml` (`layer6-review-0.4.1`, `layer6-review-2-0.4.1` to `layer6-review-9-0.4.1`).

**Shipped source.** The 0.4.1 `src/` is byte-identical from `b88adef` to `6e0a027`: `git diff --name-only b88adef 6e0a027 -- src` prints nothing (checked; also empty to `8ce7dde`). `0563e93` changed `src/` for the limit proof and `c5326a1` put `faults.py` and `runner.py` back to `b88adef`, so 0.4.1 ships the strict delivery rule. Everything after `b88adef` is tests, gate scripts, corpus files, docs and records.

**Attribution of fixes 1-8.** The brief for this draft said "Layer 6 fixes 1-8" (`4861c17`, `3c9a119`, `97839ca`, `fdef8fd`) came from the GPT/Grok/Ollama audit of 2026-11-03. The record says otherwise: those commits are dated 11-03 05:14 to 07:19, before the GPT and Grok outputs (15:22), which reviewed `eaa323c` and were fixed in round 2. YIELD and the CHANGELOG ("Layer 6 review of the 0.4.1 candidate (b03cb7a)") credit fixes 1-8 to the cold review and the adversarial reviewer. This record follows the commits. The numbers 1-8 in the commit subjects are shared by several fixes and cannot be mapped one to one; rows are ordered by CHANGELOG bullet.

## Review minors, 2026-10-31 (`b74166e`)
| # | Finding | Severity | Decision | Commit / test |
|---|---|---|---|---|
| 1 | The BGP gate before negative checks compared accepted counts only; a route still arriving where a driver knows more was received (Junos hidden routes) was not waited for | False pass (medium) | Fixed: received counts reset the wait too | `b74166e`, `tests/test_verdict_runner.py::test_gate_waits_for_received_counts_too` |
| 2 | SR Linux path marked `valid-route: false` with no `invalid-reason` was read as received or absent | False pass (medium) | Fixed: an error, never a verdict | `b74166e`, `tests/test_interop_04_fixes.py::test_srl_a_path_marked_invalid_with_no_reason_is_an_error_never_a_verdict` |
| 3 | Junos neighbor counts and hidden routes are two commands; a count could be used when they disagreed | False pass (medium) | Fixed: read again after the hidden routes, a second disagreement is an error | `b74166e`, `tests/test_interop_04_fixes.py::test_junos_hidden_routes_that_dont_add_up_are_read_again_and_then_an_error` |

## Cold review, 2026-11-01 (`16775ad`)
| # | Finding | Severity | Decision | Commit / test |
|---|---|---|---|---|
| 1 | The gate cleared a release on a stranger status whose `record` step failed (no must-fail change ran, `false_pass` false) or that named no tested version; 0.3.3 and 0.4.0 shipped while it reported the record false pass | Gate false clear (high) | Fixed: CLEARED needs a green status with a must-fail result that failed as it must and a tested version | `16775ad`, `tests/test_release_gate_render.py::test_the_stranger_keeps_the_release_from_clearing` |
| 2 | A `protocol` of the other address family than the check's prefix matched nothing, so `present: false` passed | False pass (medium) | Fixed: refused | `16775ad`, `tests/test_false_passes_041.py::test_a_protocol_of_the_other_address_family_is_refused` |
| 3 | A community printed as one number was read as absent (`without_communities` passed); Junos extended communities were mixed with standard ones | False pass (medium) | Fixed: tokens read strictly, extended kept out | `16775ad`, `tests/test_false_passes_041.py::test_a_community_printed_as_one_number_is_never_read_as_absent`, `::test_junos_extended_communities_are_not_standard_ones` |
| 4 | SR Linux and EOS did not say which neighbors are eBGP | False pass (low) | Fixed: both report it | `16775ad`, `tests/test_false_passes_041.py::test_srlinux_and_eos_say_which_neighbors_are_ebgp` |

## Round 1 on `b03cb7a` (cold review and adversarial reviewer)
| # | Finding | Severity | Decision | Commit / test |
|---|---|---|---|---|
| 1 | `with:` on `appears_on` with `state: received`: a route received before inbound policy can't show `originator_id`, `cluster_list` or communities, so a `null` pin on one was met; with `allow_anywhere` the line gave INTENT MATCHED (adversarial reviewer; mutants `_pins_ok` 53/55 had been accepted as a test gap) | False pass (high), confirmed by probe | Fixed: the pin is unknown there, never met; the two survivors are no longer accepted | `4861c17`, `tests/test_verify_pins_041.py::test_a_received_route_alone_cannot_meet_a_pin_it_cannot_show` |
| 2 | `inject_routes` counted the routes as left when they reached any one peer; a check behind another peer whose outbound filter held them back passed on nothing (BLOCKER) | False pass (high) | Fixed: every peer established when they went in (rule rewritten in rounds 2-9) | `3c9a119`, `tests/test_inject_sent_counts.py::test_routes_that_reached_one_peer_but_not_another_did_not_leave` |
| 3 | A never-left scenario made real failures exit 3 instead of 1 | Wrong exit code (medium) | Fixed: only passed checks turn inconclusive, a failed check stays failed (exit 1) | `4861c17`, `tests/test_verdict_runner.py::test_a_check_that_failed_in_a_never_left_scenario_stays_failed_exit_1` |
| 4 | `only` on `bgp_prefixes` errored only when the listing was empty; a prefix missing from a non-empty listing was one `only` never saw | False pass (medium) | Fixed: any count/list mismatch is an error | `4861c17`, `tests/test_mutants_041_checks.py::test_only_with_a_list_that_disagrees_with_the_count_is_an_error` |
| 5 | SR Linux: a path flagged both `as-loop` and `rejected-route` was subtracted twice (`max` could pass); any other invalid reason raised and broke every BGP read on the node (adversarial and cold) | False pass (medium) | Fixed: other flag combinations make the count a range judged only where the whole range agrees | `4861c17`, `tests/test_srl_loop_count.py::test_a_path_both_looped_and_rejected_is_not_subtracted_twice`, `::test_an_invalid_reason_the_driver_does_not_know_makes_a_range_not_an_error` |
| 6 | `record` treated unreadable BGP state, routes, attributes or a node with no driver as a plain warning | False pass (medium) | Fixed: INCOMPLETE BASELINE | `4861c17`, `tests/test_record_incomplete_041.py::test_a_read_that_failed_is_an_incomplete_baseline`, `::test_a_node_without_a_driver_is_an_incomplete_baseline` |
| 7 | A route type the driver doesn't map passed through under its raw name on NX-OS, Junos, SR Linux and FRR/SONiC, so `present: false` passed | False pass (high) | Fixed: an error (Juniper `INET6` ff02::2/128 reads as `local`) | `4861c17`, `tests/test_unmapped_route_types_041.py::test_an_unmapped_route_type_is_an_error` |
| 8 | Arista EOS: a route without both programmed flags counted as forwarding (YIELD lists this row as "NX-OS FIB"; the commit and CHANGELOG say EOS) | False pass (medium) | Fixed: first "not forwarding" (`97839ca`), then unknown = error (`e1c287f`) | `97839ca`, `e1c287f`, `tests/test_unmapped_route_types_041.py::test_eos_a_route_without_both_programmed_flags_is_unknown` (the `97839ca` test `..._is_not_forwarding` was renamed) |
| 9 | RouterOS: the received count was not checked against the listed paths; `without_communities` read a key RouterOS leaves out | False pass (medium) | Fixed: count must equal accepted plus filtered; `without_communities` refused before deploying | `97839ca`, `tests/test_routeros_driver.py::test_the_received_count_must_match_the_listed_paths`, `::test_without_communities_is_refused_before_deploying` |
| 10 | NX-OS `present` reads the RIB best flag (`ubest`), not whether the route is in the FIB | False pass (medium) | Accepted documented limit, CONDITIONS NOT ALL MET IN THE RECORD: public statement only in the CHANGELOG (not config.md or the compatibility page); mitigation is that NX-OS is an unreleased beta driver used only when chosen, with a warning; NO FIX RELEASE NAMED | `97839ca`; CHANGELOG 0.4.1 "Cisco NX-OS and MikroTik RouterOS are unreleased beta drivers" |
| 11 | NX-OS and RouterOS were auto-detected from the image name although unreleased (reviewer not recorded) | Policy (medium) | Fixed: beta drivers only when chosen with `nodes.<node>.driver`, and the run warns | `97839ca`, `288b32b`, `tests/test_beta_drivers_041.py::test_a_beta_driver_is_never_detected`, `::test_run_warns_for_a_beta_driver_after_preflight` |
| 12 | Six doc drifts: `only` is post-convergence, Juniper reads the stale mark, SR Linux count ranges, the another-prefix exit code, and the EOS out-delay and FRR boot-log fixes promised for 0.4.1 | Doc (low) | Fixed in the docs | `fdef8fd`, TEST NOT FOUND (docs-only commit; `tests/known_false_passes.yml` entry `layer6-review-0.4.1` records the false passes, not the drifts) |
| 13 | EOS `neighbor ... out-delay` is not read (carried from the 0.4.0 review, finding 10, whose target was 0.4.1) | False pass | Accepted documented limit, all three conditions met: public in `website/docs/reference/config.md` (convergence semantics and the known-limit paragraph); mitigation: raise `--settle` and `--hold` above a configured out-delay; fix scheduled 0.4.2 (moved from 0.4.1) | `fdef8fd` (docs only) |
| 14 | FRR boot-log comparison: a line FRR warned about but applied can make the run an error (fail closed), and a lab hook that rewrites `frr.conf` before the run ends leaves only a line-number check (carried from 0.4.0) | Fail-closed error; possible false pass for the rewrite case | Accepted documented limit: public in config.md; mitigation stated for the first (rewrite the line), NONE STATED FOR THE REWRITE CASE; fix scheduled 0.4.2 for both (moved from 0.4.1) | `fdef8fd` (docs only) |

## Local model pass (Ollama qwen3-30b-a3b, brief of 2026-11-03 08:22)
`research/model-reviews/release-0.4.1/ollama-qwen3-30b-a3b.md`: 32 KB of reasoning with terminal escape codes, cut off mid-sentence. It names no reproduction. Its stated conclusion: no critical issue that reports a real failure as a pass.

| # | Finding | Severity | Decision | Commit / test |
|---|---|---|---|---|
| 1 | `RouteInjection.restore`: a peer whose session reset over the prefix limit might be marked quiet though the routes were sent (a false block) | Not rated | Rejected: the model's own trace (lines 571-650) concludes the logic is correct; the whole rule was replaced in round 5 | none needed |
| 2 | `x.best` might be a string such as "True" and read as true | Not rated | Rejected: the model says it would be a driver bug, not a Netdryrun one; drivers parse booleans and the closure test (round 3 on) flags unchecked reads | none needed |

## Round 2a: cross-platform reviewer on `eaa323c`
YIELD counts "8 missing-key defaults on EOS, SR Linux, NX-OS and the shared AS-path regex"; the CHANGELOG lists more instances than that, so they are grouped by driver here.

| # | Finding | Severity | Decision | Commit / test |
|---|---|---|---|---|
| 1 | `inject_routes` counted a peer as reached when its sent-prefix count rose at all: 3 injected and a filter letting 1 through read as sent (BLOCKER) | False pass (high) | Fixed: every injected prefix of a family per peer; round 3 replaced the count with per-prefix reads | `e1c287f`, `tests/test_inject_sent_counts.py::test_a_filter_that_lets_one_of_three_through_names_the_two_held_back` (the `e1c287f` test `..._has_not_sent_them` was replaced in `bf29e89`) |
| 2 | Arista EOS verdict keys defaulted to empty/false: `communityList`, `largeCommunityList`, `asPathEntry`, `routeType.stale`, `.active`, both programmed flags | False pass (medium) | Fixed: present or the read fails | `e1c287f`, `c239e74`, `tests/test_verdict_keys_041.py::test_eos_a_missing_path_key_is_an_error` |
| 3 | SR Linux defaulted keys: `rejected-routes`, family `oper-state`, local-RIB `stale-route`, route `active` and FIB fields, attr-set `as-path` | False pass (medium) | Fixed: error, or unknown for an absent `as-path` | `e1c287f`, `c239e74`, `tests/test_verdict_keys_041.py::test_srl_a_missing_family_counter_or_state_is_an_error`, `::test_srl_a_local_rib_row_without_its_stale_mark_is_an_error`, `::test_srl_a_route_without_its_forwarding_state_is_an_error`, `::test_srl_an_attr_set_without_as_path_is_unknown_and_an_as_path_check_errors` |
| 4 | NX-OS `pathstaled` and `aspath` defaulted | False pass (medium) | Fixed: `pathstaled` required, `aspath` unknown when absent | `c239e74`, `tests/test_verdict_keys_041.py::test_nxos_a_path_without_its_stale_mark_is_an_error`, `::test_nxos_a_path_without_aspath_is_unknown` |
| 5 | The shared AS-path matching: `as_path: ""` / `^$` matched an AS path that could not be read | False pass (medium) | Fixed: `as_path` checks on an unreadable path are an error | `c239e74`, `tests/test_verdict_checks.py::test_bgp_route_on_an_unreadable_as_path_is_an_error` |
| 6 | No test stopped the next defaulted read | Process | Fixed: an AST closure test over every driver and the check evaluator, with a reasoned allowlist | `c239e74`, `tests/test_verdict_keys_041.py::test_no_verdict_key_is_read_with_a_default`, `::test_every_allowlist_entry_gives_a_reason` |

## Round 2b: GPT on `eaa323c`
`research/model-reviews/release-0.4.1/20261103-152223-gpt.md` (6 findings: 3 High, 3 Medium).

| # | Finding | Severity | Decision | Commit / test |
|---|---|---|---|---|
| 1 | Action: a run report with status `inconclusive` and a nonzero failed count and exit 3 was accepted and summarised as inconclusive beside failed checks | High | Fixed: counts must match the checks for `inconclusive` too, and it must say why; any contradiction is status `error` | `c239e74`, `tests/test_verdict_keys_041.py::test_action_run_inconclusive_counts_must_match_its_checks` |
| 2 | `frr.parse_received` checked the listed count against `totalRoutes` but not each path's shape, so `only` could pass on a malformed entry | High | Fixed: each path must name its prefix | `c239e74`, `tests/test_verdict_keys_041.py::test_frr_a_received_path_that_names_no_prefix_is_an_error` |
| 3 | SR Linux `_protocol` folded every `bgp*` type into `bgp`, so `protocol: bgp-evpn present: false` missed an unknown `bgp-evpn-*` | High | Fixed: an unknown `bgp-*` subtype is an error | `e1c287f`, `tests/test_verdict_keys_041.py::test_srl_a_bgp_route_type_it_does_not_know_is_an_error` |
| 4 | Action: a verify report with status `matched` but no declared line, or counts that disagree with the line results, could publish INTENT MATCHED | Medium | Fixed: `matched` needs a declared line, an inconclusive verdict a reason, an error its error | `c239e74`, `tests/test_verdict_keys_041.py::test_action_verify_match_without_a_declared_line_or_inconclusive_without_reason_is_no_verdict` |
| 5 | `_max_prefix_reset` took any new 0601 reset as proof of delivery, whatever family or cause | Medium | Fixed in `e1c287f` (only after the injection, on a session carrying that family alone); the shortcut was removed in round 5 and 0.4.1 treats every reset as quiet | `e1c287f`, `1a597d7`, `tests/test_inject_sent_counts.py::test_a_prefix_limit_reset_during_the_injection_is_inconclusive_never_passed` (the `e1c287f` tests were removed in `1a597d7`) |
| 6 | `_never_left` could turn a real failure into inconclusive | Medium | Rejected: GPT found no route that does it ("I found no route here"); a check that failed stays failed (round 1 finding 3) | pinned by `tests/test_verdict_runner.py::test_a_check_that_failed_in_a_never_left_scenario_stays_failed_exit_1` |

## Round 2c: Grok on `eaa323c`
`research/model-reviews/release-0.4.1/20261103-152223-grok.md` (225 KB, mostly the model reading its own prompt back; the 7 findings in its final "Findings" section are counted, not its working notes).

| # | Finding | Severity | Decision | Commit / test |
|---|---|---|---|---|
| 1 | `_bgp_prefixes` `exact: 0` on an established family missing from `n.prefixes` passes; SR Linux fills `prefixes` only when `received-routes` is present | High | Fixed before the audit: an up IPv4/IPv6 family with no counters is an error (acceptance A-7); Grok could not see `_counted_if_up`; a family a session doesn't carry is `exact: 0` only, by design | `fbc52fc`, `tests/test_drivers_harden_041.py::test_srl_up_family_without_counters_is_an_error_not_zero` |
| 2 | FRR `parse_adj`: `totalPrefixCounter` checked only when present, so a truncated adj-rib-out gives INTENT MATCHED | High | Fixed: a listing without its total is an error | `c239e74`, `tests/test_verdict_keys_041.py::test_verify_a_listing_without_its_total_is_an_error` |
| 3 | A neighbor with no add-path capability key left the session out of the add-path set, hiding extra advertised paths | Medium | Fixed: an established session with no add-path state for a carried family is read as add-path | `c239e74`, `tests/test_verify_adj_multipath.py::test_add_path_tx_is_read_from_the_neighbor_capabilities` |
| 4 | Action `unobserved` comes from the PR; a PR can list every router as unobserved and get a green job | High | Rejected as a new hole: a node whose config the change touches can't be named unobserved (refused since gauntlet 0.4); the Action path now has a test | `c239e74`, `tests/test_verdict_keys_041.py::test_verify_a_changed_config_of_an_unobserved_node_is_refused` |
| 5 | `inject_routes` that miss a peer end inconclusive (exit 3), not failed | Medium | Rejected: by design, inconclusive is never a pass and CI stays non-zero | none needed |
| 6 | `only` with no `min` or `exact` passes on an empty listing | Low | Rejected: `only` is an allow-list; `record` writes the floor; Grok rates it low | none needed |
| 7 | `parse_received` returns `set()` on `{}` before `totalRoutes` | Low | Rejected: Grok's own analysis says a false pass needs the counter and the listing both empty while prefixes exist; the count/list cross-check errors otherwise | none needed |

## Round 2d: other round-2 fixes (reviewer not recorded)
| # | Finding | Severity | Decision | Commit / test |
|---|---|---|---|---|
| 1 | `without_communities` on Junos and NX-OS: output leaves the communities out of a path with none, so a missing key can't be told from an unprinted one | False pass (medium) | Fixed: refused before deploying, as on RouterOS | `c239e74`, `tests/test_verdict_keys_041.py::test_without_communities_is_refused_where_a_path_without_them_omits_the_key` |
| 2 | An image name carrying another NOS's mark than its kind (`generic_vm` with an `n9kv` image detected as FRR) | False pass (medium) | Fixed: an error; set `nodes.<node>.driver` | `c239e74`, `tests/test_verdict_keys_041.py::test_an_image_name_of_another_nos_than_its_kind_is_an_error`, guard `::test_detection_of_plain_images_is_unchanged` |

## Round 3 on `5e65852` (fresh reviewer)
| # | Finding | Severity | Decision | Commit / test |
|---|---|---|---|---|
| 1 | `inject_routes` judged delivery on bgpd's aggregate sent count: two injections on one node, one filtered, read as both sent | False pass (high) | Fixed: per prefix and per peer from the node's advertised routes | `bf29e89`, `tests/test_inject_sent_counts.py::test_two_injections_on_one_node_are_each_proven_by_their_own_prefixes` |
| 2 | An IPv6 prefix on a node without IPv6 sessions read as delivered beside an IPv4 one that left | False pass (high) | Fixed: a family with no established session never left | `bf29e89`, `tests/test_inject_sent_counts.py::test_a_family_no_established_session_carries_never_left_though_the_other_did` |
| 3 | SR Linux `origin-protocol` and `best-route` defaulted (the router's own static read as a BGP best path, RT-0026 regression) | False pass (high) | Fixed: error | `bf29e89`, `tests/test_verdict_keys_041.py::test_srl_a_local_rib_row_without_origin_protocol_is_an_error_not_a_bgp_path`, `::test_srl_a_local_rib_row_without_best_route_is_an_error_not_a_non_best_path` |
| 4 | verify: add-path receive capability and a missing sent count under an empty advertised listing defaulted | False pass (medium) | Fixed: error | `bf29e89`, `tests/test_verdict_keys_041.py::test_verify_an_established_session_without_its_add_path_rx_capability_is_an_error`, `::test_verify_an_empty_advertised_listing_without_a_sent_count_is_an_error` |
| 5 | The rest of the defaulted-read sweep: NX-OS `configuredpeers`, Junos `active-tag` and `rt-entry-state`, RouterOS `active` vs contribution, EOS `peerEntry`, FRR `stale` type | False pass (medium) | Fixed: error | `bf29e89`, `tests/test_verdict_keys_041.py::test_nxos_a_family_row_without_configuredpeers_is_an_error_unless_it_is_the_empty_shape`, `::test_junos_an_extensive_entry_without_its_state_is_an_error`, `::test_routeros_an_active_flag_that_disagrees_with_the_contribution_is_an_error`, `::test_frr_a_stale_flag_that_is_not_a_boolean_is_an_error`; `tests/test_mutants_041_drivers.py::test_eos_stale_path_without_peer_entry_is_an_error_for_the_missing_key` |
| 6 | The closure scan caught 2 of 9 defaulted-read forms | Process | Fixed: scans `verify/`, `faults.py`, `runner.py`, more forms, checked against a red fixture with one of each | `bf29e89`, `tests/test_verdict_keys_041.py::test_the_scan_flags_every_defaulted_form_in_the_red_fixture` |
| 7 | `verify --unobserved` swallowed the detect error (an image naming another NOS read as "not FRR") | False pass (medium) | Fixed | `bf29e89`, `tests/test_verdict_keys_041.py::test_verify_unobserved_does_not_swallow_an_image_mark_mismatch` |
| 8 | A driver set in `nodes.<node>.driver` was trusted without checking kind and image | False pass (medium) | Fixed: checked, an error on mismatch | `bf29e89`, `tests/test_verdict_keys_041.py::test_verify_a_set_driver_is_checked_against_the_node` |
| 9 | Action: verify `no_change` accepted with a non-empty diff or an intent that declares something | False pass (medium) | Fixed | `bf29e89`, `tests/test_verdict_keys_041.py::test_action_verify_no_change_needs_an_empty_diff_and_nothing_declared` |

## Round 4 on `bf29e89` (fresh reviewer)
| # | Finding | Severity | Decision | Commit / test |
|---|---|---|---|---|
| 1 | A peer that came up while the routes were in was never read, so a peer sent nothing passed | False pass (high) | Fixed in `45f63df`; the rule changed again in round 5 | `45f63df`, `1a597d7`, `tests/test_inject_sent_counts.py::test_a_peer_that_came_up_while_the_routes_were_in_is_quiet` (the round-4 test was replaced) |
| 2 | A session that reset while the routes were in, for any reason but a prefix limit, still counted as reached once they were sent again | False pass (high) | Fixed | `45f63df`, `tests/test_inject_sent_counts.py::test_a_session_that_reset_while_the_routes_were_in_did_not_get_them` |
| 3 | A peer whose resets can't be read counted as reached | False pass (medium) | Fixed: quiet | `45f63df`, `tests/test_inject_sent_counts.py::test_a_peer_whose_resets_cant_be_read_did_not_get_them` |
| 4 | The prefix-limit shortcut proved delivery when another `inject_routes` shared the node | False pass (high) | Fixed in `45f63df`; removed with the shortcut in round 5 | `45f63df`, `1a597d7`, `tests/test_inject_sent_counts.py::test_a_prefix_limit_reset_during_the_injection_is_inconclusive_never_passed` (round-4 test removed) |
| 5 | FRR community object without `string` read as no communities | False pass (medium) | Fixed: error | `45f63df`, `tests/test_verdict_keys_041.py::test_frr_a_community_object_without_its_string_is_an_error` |
| 6 | FRR AS-path segment without `list` read as no ASNs (`as_path: ""` passed); `aspath.length` unchecked | False pass (medium) | Fixed: error, length must match the hop count | `45f63df`, `tests/test_verdict_keys_041.py::test_frr_an_aspath_segment_without_its_list_or_a_wrong_length_is_an_error` |
| 7 | SR Linux as-path container without a segment list, or a segment without type or members, read as the empty path | False pass (medium) | Fixed: error | `45f63df`, `tests/test_verdict_keys_041.py::test_srl_a_malformed_as_path_is_an_error` (round-4 test renamed in `1a597d7`) |
| 8 | The closure scan missed 14 of 14 extra forms (`.get(K) is True`, `K in x and x[K]`, `pop`, bare except, `str(x.get(K))`) and the Python in `action.yml` | Process | Fixed: forms and the embedded Python scanned | `45f63df`, `tests/test_verdict_keys_041.py::test_the_scan_reads_the_python_in_action_yml`, `::test_the_scan_flags_every_defaulted_form_in_the_red_fixture` |
| 9 | What a syntactic scan can't see (a key in a variable or parameter, a value defaulted later) | Detector gap (test tooling, not a product false pass) | Normal triage: public in the CHANGELOG (round 4 entry); covered meanwhile by the per-round fresh review; fix scheduled 0.4.2 (every verdict key behind one strict accessor) | `45f63df` |

## Round 5 on `45f63df` (fresh reviewer)
| # | Finding | Severity | Decision | Commit / test |
|---|---|---|---|---|
| 1 | A peer that came up after apply was read at restore and counted as reached though the checks ran without a session (regression from round 4) | False pass (high) | Fixed: quiet; one strict rule for the whole delivery | `1a597d7`, `tests/test_inject_sent_counts.py::test_a_peer_that_came_up_while_the_routes_were_in_is_quiet`, `::test_a_family_with_no_session_at_apply_never_left_even_if_one_came_up` |
| 2 | The prefix-limit proof held across nodes: another node's injection or a rerouted link trips the limit too | False pass (high) | Fixed: the shortcut is gone; any reset while the routes were in makes the peer quiet | `1a597d7`, `tests/test_inject_sent_counts.py::test_any_reset_while_the_routes_were_in_means_the_peer_did_not_get_them` |
| 3 | SR Linux communities container without a `community` or `large-community` list read as no communities | False pass (medium) | Fixed: error | `1a597d7`, `tests/test_verdict_keys_041.py::test_srl_a_communities_container_without_a_known_list_is_an_error` |
| 4 | SR Linux segment with an empty member list; an AS path without segments read as the empty path | False pass (medium) | Fixed: error / unknown | `1a597d7`, `tests/test_verdict_keys_041.py::test_srl_an_as_path_without_segments_is_unknown_and_an_as_path_check_errors` |

## Round 6 on `1a597d7` (fresh reviewer)
| # | Finding | Severity | Decision | Commit / test |
|---|---|---|---|---|
| 1 | "The attack had no effect" checks (best path stays, session stays up, ping works, `min` holds) passed on routes that never arrived: a regression from round 5's narrowing | False pass (high) | Fixed: every passed check in such a scenario is inconclusive again | `f994222`, `tests/test_verdict_runner.py::test_an_attack_had_no_effect_check_is_inconclusive_too`, `::test_a_scenario_whose_injected_routes_never_left_is_inconclusive` |
| 2 | A dynamic (`listen range`) peer's drop count reads 0 across a flap; a count that went down; an uptime shorter than the time since apply: resets the count can't show | False pass (medium) | Fixed: each is a reset | `f994222`, `tests/test_inject_sent_counts.py::test_a_dynamic_peer_is_never_counted_as_reached`, `::test_a_drop_count_that_went_down_is_a_reset`, `::test_a_session_up_for_less_than_the_injection_reset_while_the_routes_were_in` |
| 3 | Advertisement timing: checks ran before the routes were advertised to every peer | False pass (medium) | Fixed: wait, bounded by twice the longest interval plus settle; a late peer is quiet | `f994222`, `tests/test_inject_sent_counts.py::test_the_checks_wait_until_every_peer_is_sent_the_routes`, `::test_a_peer_not_sent_the_routes_within_the_bound_is_quiet_even_if_they_arrive_later`, `tests/test_verdict_runner.py::test_the_checks_wait_for_the_routes_to_leave` |
| 4 | SR Linux attr-set answer: a wrapped answer or another attr-set read as a path without attributes | False pass (medium) | Fixed: must be the one asked for | `f994222`, `tests/test_verdict_drivers.py::test_srl_parse_attr_set` (the `wrong` loop, "round 6 on 1a597d7") |

## Round 7 on `99fe33e` (fresh reviewer)
| # | Finding | Severity | Decision | Commit / test |
|---|---|---|---|---|
| 1 | Delivery matched by prefix, not by the injected path: a prefix already advertised from a learned path (the hijack case) counted as delivered | False pass (high) | Fixed: a path the node originates by a network statement with the injection's AS path | `ba4095d`, `tests/test_inject_sent_counts.py::test_a_prefix_advertised_from_a_learned_path_did_not_carry_the_injection`, `::test_an_advertised_path_with_another_as_path_did_not_carry_the_injection`, `::test_the_injection_waits_for_its_own_path_not_a_learned_one_for_the_prefix` |
| 2 | The console streamed PASS for checks that restore then turned inconclusive (verdict and exit code were right) | Output only (low) | Fixed: results held until the delivery verdict | `ba4095d`, `tests/test_verdict_runner.py::test_the_console_never_streams_a_pass_that_turns_inconclusive` |

## Round 8 on `ba4095d` (fresh reviewer, no BLOCKER)
| # | Finding | Severity | Decision | Commit / test |
|---|---|---|---|---|
| 1 | Latent: an add-path peer's listing shows paths denied to it, so delivery could read as proven | False pass (medium) | Fixed: an add-path peer is quiet | `02a96a2`, `tests/test_inject_sent_counts.py::test_an_add_path_peer_proves_nothing_and_is_quiet` |
| 2 | Regression: a redistributed static, connected, kernel or aggregate path beside the network route made `inject_routes` error | False block | Fixed: several local paths are read | `02a96a2`, `tests/test_inject_sent_counts.py::test_other_local_paths_for_the_prefix_are_read_not_refused` |
| 3 | A prefix the node already originates with the injection's AS path read as injected before the config went in; restore then timed out | Verdict loss (medium) | Fixed: refused at apply; restore always removes the config | `02a96a2`, `tests/test_inject_sent_counts.py::test_a_prefix_the_node_already_originates_with_the_same_as_path_is_refused`, `::test_restore_removes_the_injected_config_whatever_goes_wrong_reading` |
| 4 | A destination listed as a bare path list crashed the delivery read | Crash (low) | Fixed | `02a96a2`, `tests/test_inject_sent_counts.py::test_a_destination_listed_as_a_bare_path_list_is_read` |
| 5 | Held results were lost when restore failed | Output (low) | Fixed: shown as never-left before the run stops | `02a96a2`, `tests/test_verdict_runner.py::test_held_results_are_shown_before_a_failed_restore_stops_the_run` |

## Round 9 on `02a96a2` (reviewer not recorded in YIELD)
| # | Finding | Severity | Decision | Commit / test |
|---|---|---|---|---|
| 1 | FRR's advertised-routes detail view shows the node's current path under an existing adj-out entry, so in the hijack setup the injected path read as advertised before any UPDATE left; with a long interval the checks ran while the peer still held the old path | False pass (high) | Fixed: each established peer's listing is read before the config goes in; a prefix it already had is never read as delivered | `b88adef`, `tests/test_inject_sent_counts.py::test_a_prefix_the_peer_already_had_an_entry_for_is_never_read_as_delivered`, `::test_a_listing_that_cant_be_read_before_the_injection_counts_as_having_them_all`, `::test_the_wait_does_not_wait_for_a_peer_that_already_had_the_prefix` |
| 2 | What round 9 leaves: a hijack test of a prefix the injector already advertises ends inconclusive | False block (not a pass) | Fail-closed limit, not a false pass (the three-condition rule is for false passes): public in config.md (`inject_routes` paragraph); the result is inconclusive, exit 3, never a pass | `b88adef` |
| 3 | What round 9 leaves: on a node where FRR prints add-path IDs on every path, every inject scenario reads inconclusive | False block (not a pass) | Fail-closed limit, not a false pass: public in config.md; inconclusive, exit 3 | `b88adef` |

## Prefix-limit scenarios: a documented consequence of rounds 5-9 and the limit-proof stop
| # | Finding | Severity | Decision | Commit / test |
|---|---|---|---|---|
| 1 | A prefix-limit reset proves nothing, so the 8 flood-scenario cases of corpus v2 read inconclusive (9 of 17 deterministic cases correct, 0 harmful changes approved) | False block (not a pass) | Accepted documented limit, all three conditions met: public in the CHANGELOG known limitation, `corpus/v2/AMENDMENTS.md` and the trust page; mitigation: inconclusive (exit 3), documented way to test a limit through the receiver's session state; fix scheduled 0.4.2 (attributable proof) | `306564a`, `e1f9205`, `tests/test_inject_sent_counts.py::test_a_prefix_limit_reset_during_the_injection_is_inconclusive_never_passed` |

## Mutation and gate reviews after `b88adef` (`b88adef..8ce7dde`)
| # | Finding | Severity | Decision | Commit / test |
|---|---|---|---|---|
| 1 | `faults.py`, the inject delivery rule reworked in rounds 2-9, was never in the mutation set (found when the limit proof changed it; LESSONS Releasing 12) | Gate gap (high) | Fixed: G1 mutation-closure guard; `faults` a scoped verdict module; kill tests for 75 survivors and 6 restore survivors | `194c9ac`, `845f8e3`, `fdbd4a2`, `tests/test_quality_guards.py::test_faults_outside_the_mutation_set_turns_g1_red`, `tests/test_release_gate_mutants.py::test_every_verdict_module_is_mutated_and_has_a_coverage_floor` |
| 2 | Adversarial review of 15 equivalent `faults.py` mutants: all 15 confirmed, but 13 hold only because `parse_adj` or `parse_attrs` reads the same data first | Gate gap (medium) | Fixed: tests pin the statement order | `a4597d1`, `tests/test_mutants_041_faults.py::test_advertised_validates_the_whole_listing_before_its_own_loop`, `::test_is_injected_parses_the_path_before_reading_its_flags`, `::test_a_listing_record_listed_cant_read_counts_as_having_every_prefix` |
| 3 | The unit and live layers started under an ignored SIGINT (a background job of a non-interactive shell) (class E9, from the limit-proof rounds' lessons) | Gate gap (medium) | Fixed: G2 harness preflight | `194c9ac`, `tests/test_quality_guards.py::test_an_ignored_sigint_fails_the_preflight` |
| 4 | Both corpora were stale on `7532310` (results from older verdict code; class E8) | Gate gap (medium) | Fixed: G3 reference freshness (`verdict_tree` in results.json) | `194c9ac`, `tests/test_quality_guards.py::test_results_without_a_verdict_tree_are_stale_the_7532310_shape` |

## Limit-proof code review on `0563e93` (GPT, Grok, fresh adversary). NOT SHIPPED
0.4.1 ships the strict rule (`c5326a1`): `faults.py` and `runner.py` are back to `b88adef` and the proof's tests were removed. The CHANGELOG, trust page and `corpus/v2/AMENDMENTS.md` state the deferral (proof planned for 0.4.2). Findings below are against the rejected design; the failing tests existed only in the removed `tests/test_inject_limit_proof.py` (and `design/attributable-limit-proof-wip.patch`).

| # | Finding | Severity | Decision | Commit / test |
|---|---|---|---|---|
| F1 | The arithmetic proves capacity, not causality: late convergence or outbound filtering lets other routes trip the limit while the injection is credited (all three reviewers) | False pass (high) | Deferred design finding (limit proof not shipped) | `c5326a1` removed it |
| F2 | The proof is credited to every passed check and to every prefix: `missing = []` marks all injected prefixes delivered; "attack had no effect" checks pass on a down session (all three) | False pass (high) | Deferred design finding (limit proof not shipped) | `c5326a1` |
| F3 | A record that already read max-prefix at apply, plus a later drop that doesn't rewrite it (adversary) | False pass (medium) | Deferred design finding (limit proof not shipped) | `c5326a1` |
| F4 | Session identity: `hostLocal` not compared with the peer (a VRF, a second session to the same address) (adversary) | False pass (medium) | Deferred design finding (limit proof not shipped) | `c5326a1` |
| F5 | `force` and `warning-only` read only at apply, from the JSON flag, not the running config in any rendering | False pass (medium) | Deferred design finding (limit proof not shipped) | `c5326a1` |
| F6 | Ownership check skipped the injector | False pass (low) | Deferred design finding (limit proof not shipped) | `c5326a1` |
| F7 | An unreadable log was "no disagreement" (fail-open); the log is the only place naming family and count (GPT Q-c, Grok Q-c, adversary) | False pass (low) | Deferred design finding (limit proof not shipped) | `c5326a1` |
| F8 | The config-time caller `peer_maximum_prefix_set()` (`always=1`) can send the same Cease with no UPDATE; a soft-reconfig replay can trip it (GPT Q1, Grok, adversary) | False pass (medium) | Deferred design finding (limit proof not shipped) | `c5326a1` |

## Limit-proof design round 1: "the limit fired" (design only, rule 9)
| # | Finding | Severity | Decision | Commit / test |
|---|---|---|---|---|
| D1 | The limit is not compared with the check's bound (E5/E3) | False pass | Deferred design finding (limit proof not shipped) | design only |
| D2 | The check is not tied to the tripped session (E4/E5) | False pass | Deferred design finding (limit proof not shipped) | design only |
| D3 | A check with no neighbor gets credit (E2/E5) | False pass | Deferred design finding (limit proof not shipped) | design only |
| D4 | Another route source on the injector (E1/E3) | False pass | Deferred design finding (limit proof not shipped) | design only |
| D5 | The reset rule contradicts re-trips (E3) | False pass | Deferred design finding (limit proof not shipped) | design only |
| D6 | A warning flag read by presence (E2) | False pass | Deferred design finding (limit proof not shipped) | design only |

## Limit-proof design round 2: the bound (design only; zero-slack I8: 2 + 49 = 51 <= 51)
| # | Finding | Severity | Decision | Commit / test |
|---|---|---|---|---|
| B1 | L - B undercounts after a re-trip: pe1 can accept 50 injected routes before the trip, so up1 gains 50 (52 > 51) (E1/E4) | False pass | Deferred design finding (limit proof not shipped) | design only |
| B2 | C is read once; the change's own routes still reaching up1 raise it after the read (E3) | False pass | Deferred design finding (limit proof not shipped) | design only |
| B3 | Path closure sees only default-VRF sessions up at apply; a VRF, idle or dynamic neighbor is an unbounded way out (E2/E4) | False pass | Deferred design finding (limit proof not shipped) | design only |
| B4 | Another AFI/SAFI on the same session carries no limit (E4) | False pass | Deferred design finding (limit proof not shipped) | design only |
| B5 | Route creation beyond pe1: aggregate without summary-only, advertise-map, redistribution, VRF leaking, an IGP (E5) | False pass | Deferred design finding (limit proof not shipped) | design only |
| B6 | Is the ceiling L or L+1: the source shows the Cease at pcount > pmax but not that the overflowing path is never advertised before teardown (E6/E3) | False pass | Deferred design finding (limit proof not shipped) | design only |
| B7 | Smaller points: compare the check's effective afi after its default; a check on a remote that can never receive pe1's routes passes vacuously | False pass (low) | Deferred design finding (limit proof not shipped) | design only |

## Limit-proof design round 3 (2026-11-05, two independent design reads; R = the standing adversary, F = the fresh one)
The same adversary and a fresh one both said every finding is fixable fail-closed and both said round 3 was not complete. The pre-agreed stop rule applied and 0.4.1 ships strict (option A).

| # | Finding | Severity | Decision | Commit / test |
|---|---|---|---|---|
| R1 = F1 | A baseline prefix with a second path survives the drop and the re-trip refills 50 (52 > 51) (E4/E1) | False pass | Deferred design finding (limit proof not shipped) | design only |
| R2 = F3 | Add-path TX downstream counts paths: up to 2 x (L - B) (E1) | False pass | Deferred design finding (limit proof not shipped) | design only |
| R3 = F2 | Route creation P9 doesn't list: default-originate route-map, aggregate with suppress-map or unsuppress-map, a static resolving through an injected prefix (E5) | False pass | Deferred design finding (limit proof not shipped) | design only |
| R4 | P9 parses FRR syntax only (E2/E4) | False pass | Deferred design finding (limit proof not shipped) | design only |
| R5 | A REMOVED path is restored and re-counted with no overflow check (confirmed in `bgp_route.c` 5394-5406); dampening is another way in (E6) | False pass | Deferred design finding (limit proof not shipped) | design only |
| R6 | A dynamic `listen range` neighbor that comes and goes inside the window (E3) | False pass | Deferred design finding (limit proof not shipped) | design only |
| F4 | Graceful restart with the N-bit keeps stale routes and may reset pcount (unverified): up to about 98 (E3/E1) | False pass | Deferred design finding (limit proof not shipped) | design only |
| F5 | Stale routes over a second path across re-trips, with a slow MRAI elsewhere (E3) | False pass | Deferred design finding (limit proof not shipped) | design only |
| F6 | The read points are ambiguous (before the change settles, or after rollback) (E3) | False pass | Deferred design finding (limit proof not shipped) | design only |
| W | C sampled at three moments only | False pass | Deferred design finding (limit proof not shipped) | design only |

## Case-18 exemption rule, design adversary round 1 (fresh adversary, 2026-11-05)
Rule 9 design (`design/case18-exemption-rule.md`). The code is in `35bf618`; all tests are in `tests/test_case18_exemption.py` unless stated.

| # | Finding | Severity | Decision | Commit / test |
|---|---|---|---|---|
| A1 | `unsafe` isn't bound to the case's cause: lab noise (a session that never came up, an unrelated check) satisfies "at least one unsafe" | MAJOR | Fixed: per-case pins; a catch must fail the aggregate checks and nothing outside the case | `35bf618`, `::test_red_unsafe_without_the_checks_for_this_cases_cause`, `::test_red_inconclusive_because_the_lab_never_came_up` |
| A2 | Obligation 10 was wrong: the rule reads only fresh results, so committed files without `status` block nothing | MAJOR | Fixed in the design text only | TEST NOT FOUND (design text) |
| A3 | Verdict equality can't tell inconclusive from error on deterministic cases | MAJOR | Fixed: status compared when both sides have it | `35bf618`, `::test_a_slide_from_inconclusive_to_crash_is_a_diff_when_both_record_status`, `::test_expect_compares_status_when_both_sides_have_it` |
| A4 | `runs` is read by several consumers; nesting `status` there breaks them | MAJOR | Fixed: a parallel `run_details` list | `35bf618`, `::test_red_a_run_missing_a_strategy_or_its_status`, `::test_evaluate_records_status_checks_and_never_left_from_the_real_report` |
| A5 | Assertions imported by `run.py` are skipped in the live copy; a refresh compares against the file it replaces | MAJOR | Fixed: `release_gate.py corpus-check`; the refresh-script wiring is in HQ, outside this repo and not verified here | `35bf618`, `::test_corpus_check_passes_a_refresh_the_live_layer_would_pass`, `::test_corpus_check_fails_the_88cf6bb_shape` |
| A6 | `expected` comes from the case YAML; editing it flips the rule's branch; the expected-safe branch had no rule | MAJOR | Fixed: `NONDETERMINISTIC_PINNED` pins expected and run count; an expected-safe pin is red | `35bf618`, `::test_red_expected_flipped_in_the_case_file`, `::test_an_expected_safe_pinned_case_has_no_rule_and_is_red` |
| A7 | An exception in a repeat isn't recorded (the corpus run dies) | MINOR | Fixed: recorded as `status: error`, the other runs finish | `35bf618`, `::test_run_py_records_run_details_and_a_crash_without_losing_the_other_runs` |
| A8 | The run count is a floor (`< 2`) | MINOR | Fixed: exactly N = 5 | `35bf618`, `::test_the_run_count_is_exact` |
| A9 | "Ping and sessions have no inconclusive state" was unverified | MINOR | Fixed: they may be safe, unsafe or inconclusive, never error | `35bf618`, `::test_ping_and_sessions_may_be_inconclusive_but_never_error` |
| A10 | Keep the INFO line as redundancy | MINOR | Accepted: kept | `35bf618` (no test of its own) |
| A11 | Check consumers for a strict schema before adding fields | MINOR | Fixed: the contributor gate compares status too | `35bf618`, `::test_the_contributor_gate_compares_status_too` |

## Case-18 rule code check (fresh code check, diff and A1-A11 only)
Closed on first read: A2, A4, A8, A9, A10, A11. Partly closed: A1, A3, A5, A6, A7 (above). New defects, fixed in `35bf618` and `7da759b`:

| # | Finding | Severity | Decision | Commit / test |
|---|---|---|---|---|
| D1 | The per-run crash capture applied to every case: a deterministic crash became `error`, matched a legacy committed `error`, and the gate went green | MAJOR | Fixed: capture only for nondeterministic runs; any case's status `error` is a BLOCKER | `35bf618`, `::test_a_deterministic_case_crash_still_stops_the_run`, `::test_an_error_status_is_red_in_any_case_whatever_the_committed_file_says`, `::test_corpus_check_fails_a_deterministic_crash_against_a_legacy_committed_error` |
| D2 | With D1, a leaked lab cascaded through later cases unseen | MAJOR | Fixed: gone with D1 | `35bf618` (same tests as D1) |
| D3 | A null run or detail raised a traceback | MINOR | Fixed: "malformed run record" finding | `35bf618`, `::test_a_malformed_run_record_is_a_finding_not_a_traceback` |
| D4 | `live_corpora` ignored the exemption and harmful-approved BLOCKERs in its return | MINOR | Fixed | `35bf618`, `::test_the_live_layer_applies_the_same_rules_and_returns_false_on_them` |
| D5 | Only corpus-check required a status on every case | MINOR | Fixed: one `status_problems` for both | `35bf618`, `::test_corpus_check_fails_a_result_without_status` |
| D6 | Tests didn't exercise the real capture, interrupts, a legacy committed error, or expected-safe | MINOR | Fixed: tests for each | `35bf618`, `::test_an_interrupt_is_never_recorded_as_a_run`, `::test_evaluate_run_records_a_crash_as_error_for_every_strategy` |

## Case-18 rule verification pass (`94f5174`)
| # | Finding | Severity | Decision | Commit / test |
|---|---|---|---|---|
| N1 | A crash against a legacy committed `error` (no status) was not a problem on the contributor path | MAJOR | Fixed | `94f5174`, `tests/test_case18_exemption.py::test_the_contributor_gate_compares_status_too` |
| N2 | The live status BLOCKER was untested with a crash; the return value must say so | MAJOR | Fixed: tested with a crash in a deterministic case | `94f5174`, `tests/test_case18_exemption.py::test_the_live_layer_applies_the_same_rules_and_returns_false_on_them` |
| N3 | A list as a status or a number as a check list gave a traceback | MINOR | Fixed: a finding | `94f5174`, `tests/test_case18_exemption.py::test_a_wrong_typed_status_or_check_list_is_a_finding` |

## Case-18 exception: adversary check of `43ecdf8` (fresh adversary; no input widened the exception to another version, clause or case, or let `accepted.json` turn a BLOCKER into ACCEPTED)
| # | Finding | Severity | Decision | Commit / test |
|---|---|---|---|---|
| 1 | Hole: nothing tied the exception to the case as it ran; an edited case file, intent (I2 removed) or lab was still excepted | High | Fixed: `CATCH_EXCEPTIONS` pins a sha256 of the case file, `corpus/v2/specs/intent.yml` and `corpus/v2/base/`; any difference or a missing file is a BLOCKER | `22ea4b9`, `tests/test_case18_exemption.py::test_an_edited_case_file_intent_or_lab_voids_the_exception`, `::test_the_committed_case_still_matches_its_pin` |
| 2 | `nondeterministic_uncaught` derived case ids from message text (fragile parser) | Medium | Fixed: reads them from the runs | `22ea4b9`, `tests/test_case18_exemption.py::test_uncaught_is_read_from_the_runs_not_from_message_text` |
| 3 | `catch_severity` accepted a non-string version | Medium | Fixed: a BLOCKER | `22ea4b9`, `tests/test_case18_exemption.py::test_the_catch_exception_is_major_only_for_its_pinned_version` |
| 4 | A malformed run crashed the INFO line and `nd_always_approved` | Low | Fixed in `scripts/release_gate.py`; the malformed-run variant is only tested through `nondeterministic_problems` | `22ea4b9`, `tests/test_case18_exemption.py::test_the_catch_exception_never_covers_another_clause` (variant "malformed run"); TEST NOT FOUND that feeds a malformed run to `nd_always_approved` or the INFO line |
| 5 | Several guards had no test (other clauses, other case, a failed BLOCKER with an accepted entry, expiry, end to end) | Medium | Fixed: red fixtures for every widening | `22ea4b9`, `tests/test_case18_exemption.py::test_the_catch_exception_never_covers_another_case`, `::test_the_catch_exception_expires_with_the_version`, `::test_end_to_end_the_report_shows_accepted_on_0_4_1_and_blocks_otherwise`, `tests/test_release_gate_render.py::test_a_failed_blocker_cannot_be_accepted` |
| 6 | The exception itself: on `94f5174` 0 of 5 case-18 runs caught the change (all 5 not proven: I2 and I5 passed, only the I8 flood checks failed) | False block (not a pass) | Accepted exception for 0.4.1 only (owner decision (b)), all three conditions met: public in `corpus/v2/AMENDMENTS.md` and `website/docs/trust.md`; mitigation: the I2 checks catch a missing aggregate deterministically in v1 case 25, every other clause held; fix: removing the race is a 0.4.2 blocker. On the release run at `6e0a027` 3 of 5 runs caught it, so the "caught in at least one run" check PASSES in `GATE.md` and the exception was not used | `43ecdf8`, `tests/test_case18_exemption.py::test_only_the_catch_clause_is_excepted`, `::test_corpus_check_accepts_the_94f5174_shape_on_0_4_1_only` |

## Open items
- **Round 1 #10 (NX-OS `present` reads the RIB best flag, not the FIB):** now an accepted documented limit with all three conditions: stated where users of the driver look (`website/docs/examples.md`, nxos-frr, "Known beta limit", beside the CHANGELOG); mitigation: pair the `route` check with a `ping` across the path; fix scheduled: 0.4.2 (read the FIB state from a live Nexus 9000v capture), the driver stays beta and opt-in until then.
- **Round 1 #14, the rewrite case (a lab hook rewrites `frr.conf` before the run ends):** now all three conditions: public in `website/docs/reference/config.md`; mitigation stated there (no `write memory` over the bound `frr.conf` during a run; bind the final config); fix scheduled 0.4.2.
- **TEST NOT FOUND:** Round 1 #12 (six doc drifts, docs-only `fdef8fd`: no test applies); case-18 A2 (a design-text correction: no test applies); case-18 exception #4 (a malformed run through `nd_always_approved` and the INFO line: covered only through `nondeterministic_problems`; see also F1 below).
- **Not recorded:** who reviewed round 9, `b74166e` and round 2d; the exact commit the Ollama pass of 2026-11-03 read.
- **Final audit:** F1, F2, F3, F5, F12 fixed; F4, F11 for 0.4.2; the local-model leg pending (below).
- **Doc drift spotted in passing:** `website/docs/reference/compatibility.md` lists two contradicting Juniper graceful-restart limits (one says the stale mark isn't read, the next that it stops the read); generated from `tests/compat_verified.json`, to fix in 0.4.2.

## Multi-vendor AI audit, final round on `b88adef..6e0a027` (the gate, corpus runner and contributor gate)

**Last commit whose verdict path was fully audited: `b88adef`** (Layer 6 round 9). `src/` is byte-identical from there to `6e0a027`, the release candidate. Everything after it is the release gate (G1-G3, the corpus status and `run_details`, the case-18 rule and its 0.4.1 exception, `corpus-check`), `corpus/run.py`, `scripts/contrib_gate.py`, `scripts/sync_facts.py` and `pyproject.toml`. That diff, with the README, went to GPT and Grok through `research/tools/ask_models.py` (brief `research/model-reviews/release-0.4.1/final-gate/brief.md`, sha256 ec3924495839…, 2026-11-05 18:13; the standard question "how can this report a pass without testing what the file says?", applied to the gate clearing a release; none of our conclusions). Answers: `20261105-181310-gpt.md`, `20261105-181310-grok.md` in the same folder.

**Local open model (Ollama): PENDING.** The useful models need 13-18 GB; the hub declined the window while the owner works on the machine. It runs when the hub allows (gpt-oss:20b on the same brief), and this section gets its findings.

**Evidence check against every finding (read-only, 2026-11-05):** on the release run's own results (`releases/0.4.1/corpus-v1-results.json`, `corpus-v2-results.json`, live layer on `6e0a027`): no malformed or non-string record, no status/verdict disagreement in any case or run, no `error` status, the 8 v2 `inconclusive` cases are the published ones (01, 04, 07, 08, 09, 12, 16, 17); no corpus case file changed since v0.4.0; the committed results did not change after the live run; the case-18 exception was not used (3 of 5 runs caught it; the check passed). So none of the findings below changed what this release's gate run measured. They are gate defects: each could let a *forged or edited* results file, or an edit between layers, clear a later run.

| # | Model | Finding | Severity (theirs / ours) | Decision |
|---|---|---|---|---|
| F1 | Grok 1 | `nondeterministic_problems`: a check-name list that holds a non-string (`passed_checks: [1]`) passes the first shape guard, and the second guard `continue`s without reporting it, skipping the approval, caught and not-proven clauses; on 0.4.1 with the case-18 pin the only outcome is "no run caught", which the exception makes MAJOR/ACCEPTED. Confirmed in the code (introduced by the N3 fix in `94f5174`) | Critical / BLOCKER for the gate (a forged file only: `run.py` always writes strings; not present in this release's results) | **Fixed** (this commit): both guards check element types and report the record, never skip it. Red on `6e0a027`: `tests/test_case18_exemption.py::test_audit_f1_a_non_string_check_name_is_reported_not_skipped`, `::test_audit_f1_corpus_check_rejects_it_on_0_4_1` |
| F2 | Grok 2, GPT 7 | The case-18 exception pins the case file, intent and lab, not the code under test (`src/` verdict tree, `corpus/run.py`); `corpus_check` never reads `environment.verdict_tree`, so a hand-built results file of the right shape can be ACCEPTED | High / MAJOR | **Fixed:** `CATCH_EXCEPTIONS` also pins the verdict tree (`3e62b50e`) and `corpus/run.py`; `corpus_check` requires the results' `verdict_tree` to equal this code's. Red on `6e0a027`: `tests/test_case18_exemption.py::test_audit_f2_the_exception_needs_this_verdict_code`, `::test_audit_f2_corpus_check_rejects_results_from_other_code`. Limit: a hand-built file can copy the hash string; the live layer generates its own results, so this only bounds the advisory pre-commit `corpus-check` |
| F3 | GPT 2, Grok 3 | The live layer hands `run.py` the *source* tree's verdict hash (`NDR_VERDICT_TREE`), while the lab runs the installed wheel: an edit to `src/` after the wheel was built would be recorded as the code that ran | Critical, High / MAJOR | **Fixed:** `live_install` hashes the installed wheel's verdict modules (`verdict_tree(package_dir=...)`, `installed_package_dir`) and requires them to equal the source's (BLOCKER `installed-verdict-tree`; a mismatch stops the live layer); `live_corpora` hands `run.py` the installed tree and refuses the corpus without one. Red on `6e0a027`: `tests/test_case18_exemption.py::test_audit_f3_the_installed_wheels_tree_is_read_from_the_package`, `::test_audit_f3_no_installed_tree_means_no_corpus_run`, `::test_audit_f3_results_recording_another_tree_are_a_diff`; `::test_audit_check_the_installed_package_path_is_read_strictly` |
| F4 | Grok 4 | `contrib_gate.corpus_results` reads run 1 only for nondeterministic cases and never `run_details`, so a pull request whose case-18 runs 2-5 approve the change is not a contributor-CI failure | High / MAJOR (contributor path, not the release gate) | **OPEN, 0.4.2:** the contributor gate calls `nondeterministic_problems` and `status_problems` like the release gate |
| F5 | Grok 5 | `status_problems` doesn't require `status` to agree with `verdict` in deterministic cases; a forged record (verdict `unsafe`, status `passed`) passes | Medium / MAJOR | **Fixed:** `status_problems` requires status and verdict to agree in every case. Red on `6e0a027`: `tests/test_case18_exemption.py::test_audit_f5_a_status_that_contradicts_the_verdict_is_red` |
| F6 | GPT 1 | A committed harmful case relabeled `safe` or deleted could clear | Critical / rejected for this release | **Rejected:** a removed case shows as a verdict diff (`strategy_diffs` takes the union of ids); a relabel needs a case-file edit, which the contributor gate's `corpus --base` refuses and which no 0.4.1 commit made (no case file changed since v0.4.0); the case-18 expected verdict is pinned in the gate. 0.4.2: the release gate also compares each case's `expected` with the committed results |
| F7 | GPT 3 | Deterministic `inconclusive` runs clear | High / rejected | **Rejected:** inconclusive is fail-closed for users (exit 3, never a pass); the 8 v2 inconclusive cases are published as not proven; a slide from inconclusive to crash is caught by `status_problems` (no `error` anywhere) |
| F8 | GPT 4 | Malformed records crash the gate | High / rejected | **Rejected:** a crash is a non-zero exit, so the layer is red (fail-closed); shape findings are reported since `94f5174`/`22ea4b9`; F1 covers the one shape that was skipped instead of reported |
| F9 | GPT 5 | `run.py`: a crash mid-case or a malformed `--expect` file | High / rejected | **Rejected:** `write_results` runs only after every case; a crash exits non-zero and writes nothing; a malformed `--expect` raises (non-zero) |
| F10 | GPT 6 | The scratch corpus copy is reused if it exists | High / rejected | **Rejected:** `live.work` is a fresh `tempfile.mkdtemp` per run (`release_gate.py` `layer_live`), so the copy never pre-exists |
| F11 | Grok 6 | `sync_facts` counts every verdict `error` as inconclusive, even a crash | Medium / MINOR | **0.4.2:** count from `status`. Not reachable through a clean gate: `status_problems` blocks an `error` status |
| F12 | Grok 7 | `code_differs` treats `corpus/*/results/` as records, so a results edit after the live layer isn't re-checked | Medium / MAJOR | **Fixed:** a `corpus/*/results/` change between layers is code for the live and unit layers (they read it), not for mutation and static. Red on `6e0a027`: `tests/test_case18_exemption.py::test_audit_f12_a_results_change_between_layers_is_code`, `::test_audit_check_results_changes_are_code_only_for_the_layers_that_read_them` |

**Decision (coordinator, 2026-11-05): fix before the release.** F1, F2, F3, F5 and F12 are fixed, each with a red fixture that fails on `6e0a027`'s code and passes on the fix (proved by running the new tests against a `git archive` of `6e0a027`: 9 failed there, 9 pass here). F4 (contributor gate) and F11 (`sync_facts`) are 0.4.2. The fixes change `scripts/`, so unit, mutation, live and acceptance run again on the fixed commit.

**Fresh adversary check of the fixes (rule 9, diff and the findings only, 2026-11-05):** F1, F2, F3, F5, F12 CLOSED, no BLOCKER or MAJOR regression; F3's edge cases (a module missing from the wheel, an extra driver file, a namespace or editable install, `__pycache__`) all fail closed. Its minors: (1) a tree mismatch now stops the live layer at once (fixed); (2) the package-path parsing is now one tested function (fixed); (3) results changes are code only for the layers that read them (fixed); (4) the F2 hash check can't prove who produced a file (stated above); (5) the recorded-tree check after the corpus run echoes what the gate handed in (harmless; the real guard is `installed-verdict-tree`); (6) the tree covers `VERDICT_MODULES` only, as G3 defines it; (7) a nondeterministic case's row-level strategies (run 1) aren't checked against `runs[0]` (forged files only; 0.4.2).

## Angle-5 red team on `d87aa3e` (2026-11-08) and the batch that fixes it

Two isolated attackers (drivers; checks, config, record, verify) and a fresh verifier on an export of `d87aa3e`: 9
candidates, all reproduced offline (`tests/redteam/RT-0044` to `RT-0050`). Design `design/redteam-041-angle5-fixes.md`
(QUALITY-SYSTEM rule 9): three passes by a fresh adversary; pass 1 added a RouterOS case from a live fixture
(`RT-0051`). Code: two fresh adversaries on the diff (one BLOCKER each, fixed and re-checked: FRR aliases compared before
canonicalisation; `record` skipping routing nodes no driver recognises).

| Case | Confirmed | How |
|---|---|---|
| OSPFv3 carrying IPv4 (RT-0044/45, EOS cousin) | EOS live; Junos and SR Linux from crafted output | cEOS 4.36.3M prints `OSPFv3` (`eos_route_ospfv3_ipv4.txt`); the SR Linux lab formed no OSPF route; the Junos lab stopped at the memory guard |
| Own BGP paths (RT-0051 RouterOS fixed; RT-0048 SR Linux and Junos: **false pass / accepted documented limit**) | RouterOS from a live capture; SR Linux live (lab A: the exported static reads "not checked") | `routeros_routes_main.txt`; the fail-closed rule for SR Linux and Junos failed the shipped leak guards in the rule-10 rehearsal on `5183a6d` and was reverted (owner: "Ship, publish as limits"); published in config.md, junos.md, trust.md and the advisory with the neighbor-side mitigation; 0.4.2 reads the adj-rib-out (SR Linux `rib-out-post` captured live) |
| Repeated merge keys (RT-0050), record communities (RT-0052) | no device needed | `validate`; unit tests |
| zebra flags (RT-0046), SONiC offload (RT-0047) | SONiC live: BGP and static carry `offloaded`, even with orchagent stopped; `offloadFailed` never seen | lab B; RT-0047 kept as a fail-closed guard |
| FRR community alias (RT-0049) | live | lab C, `frr_running_config_bgpd_alias.txt` |

Acceptance on `d87aa3e` (Job-2 reader): one new BLOCKER, SR Linux paths both looped and rejected broke the BGP read and
`record` left the node out with exit 0 (fixed: the count range clips at 0; `record` exits 1 on any read gap). Live on
cEOS: a `route` check on a node without BGP was an error (fixed: the exact `BGP inactive` answer). The other failures
were harness problems, fixed in `scripts/acceptance.py`.

## Angle-5 red team on `26380cb` (2026-11-09): published as limits

Two isolated attackers (A: drivers, 6 candidates, 6 refused; B: checks, config, record, verify, 4 candidates, 7 refused)
and a fresh verifier on an export of `26380cb`; records in `wt/redteam-26380cb/` (VERDICTS.md). Decision (coordinator,
under the owner's rule): no source change in 0.4.1; the real ones are accepted documented limits with a mitigation each
(config.md, cli.md, compatibility.md, trust.md, the verdict spec, CHANGELOG), fixed in 0.4.2 as the first cases of the
reproduce-first fast-fix path.

**Registry pinning deferred to the 0.4.2 branch.** RT-0048 was published with a `tests/known_false_passes.yml` entry and
an `accepted_limit` red-team case pinning each published sentence. These four are published in prose only for 0.4.1:
the gate's `code_differs` counts every file under `tests/` as code, so adding the entries and case files after the
mutation (`8bc84c3`) and live (`26380cb`) runs would force both to rerun (about 8 to 9 hours, VM labs included) for no
change in behaviour. The entries, the case files (written red before each fix) and the widened accepted-limit pin land
as the first commit on the 0.4.2 branch, with the fixes. This also departs from ACCEPTANCE-PROMPT.md's step "file each
confirmed case as the next `tests/redteam/RT-NNNN-*.yml` ... on the acceptance branch"; the departure is recorded here
and in `acceptance-adversary.md`.

| Case | Verdict | Confirmed | Outcome |
|---|---|---|---|
| RT-0053 FRR/SONiC ping to an address on the VRF device | real, MAJOR | kernel and iproute2 in the pinned FRR 10.4.1 image (`cap-vrfdev.txt`: `show vrf red` omits `red`; 2/2 replies) | limit, fix 0.4.2 |
| RT-0056, RT-0063 EOS non-BGP route not selected | real, MAJOR | live fixtures `eos_leak_route.txt` / `eos_leak_bgp.txt` (selected route only); not yet in a lab | limit, fix 0.4.2 |
| RT-0058 SR Linux EVPN type-5 in an ip-vrf without BGP | real, MAJOR | offline; not yet in a lab | limit, fix 0.4.2 |
| RT-S01 SR Linux `record --attributes` drops an unread AS path | real, MAJOR | offline (no capture of an empty AS path) | limit, fix 0.4.2 (warn) |
| RT-0054, RT-0057, RT-0064 SR Linux route-table losers | unproven | one srl-frr test pending | limit if real |
| RT-0055 FRR VRF-imported default | not producible (zebra lists the unselected entry) | | none |
| RT-0065 `bgp_prefixes` default `afi` on a dual-stack session | documented | | doc line |
