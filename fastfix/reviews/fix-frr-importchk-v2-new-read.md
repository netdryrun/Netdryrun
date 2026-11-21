# New-read review: ndr/fix-frr-importchk-v2 (FP-043-FRRIMPORTCHK, RT-0084)

- Reviewer session: recheck-frr. It wrote no code, test, record, evidence or allowlist in this change; this file is
  its only commit.
- Reviewed: 83576ad03fdee1b8e72976f21241db9fe96ee0bb (oracle 4a9fca8, fix c260a0c, follow-ups 975fe30, fc9aee3,
  75a1bd9, the fixes a333c28 for this session's review of 5a36902, plant 83576ad), judged against main
  6df498add4799838aaaba55dcd9462bd6191feb6's tests, as the gate runs them.
- Verdict: merge after the MINORs below. No false pass found on 83576ad.
- Network OS the new reads touch: FRR (and SONiC, which runs FRR's bgpd), plus one probe on every node no driver
  claims. Live runs of every FRR and SONiC example on the candidate commit are still owed to the release gate.

## The new device reads

On every FRR or SONiC router in the lab, after setup (run), before the snapshot (verify) and before recording
(`record --deploy`, MCP `record_baseline`), and again after the evidence is taken:
- `vtysh -d bgpd -c 'show running-config'`, the per-instance import-check table in text and JSON, and
  `show bgp vrfs json`;
- on an FRR router whose config has a `network` with a route-map and no import-check entry: the boot log,
  `show bgp [vrf V] <afi> unicast <prefix> json`, and `vtysh -d bgpd -c 'show route-map NAME json'`;
- when vtysh can't reach bgpd: `/etc/frr/daemons` and `cat /proc/[0-9]*/comm`;
- on a node no driver claims: `vtysh -d bgpd -c 'show running-config'` once, to tell whether it runs FRR.

## Gate results on 83576ad

- `reproduce --range origin/main..HEAD`: clean (32 oracles held at the candidate; the fix commit carries
  `Fixes-Oracle: FP-043-FRRIMPORTCHK`, the plant is a port).
- `plants --base origin/main`: clean, 19 of 19 caught.
- `loosening --base origin/main`: 102 flips, the same 102 test names as on 5a36902. Three are noise and are not
  covered here (below). The other 99 are judged genuine, listed at the end.
- Full suite on 83576ad, `PYTHONPATH=src`: see the commit message.

## The flips (99 judged genuine, no assertion weakened)

| Group | Count | Kind | What changed | Verdict |
|---|---|---|---|---|
| `tests.test_verdict_runner` | 59 | verdict | main's FakeLab has no `exec`, so the guard's first read raises and every run ends in error. The candidate's fakes answer bgpd's running config with a live FRR 10.4.1 capture (BGP, no `network`). The `lab.dead` nodes (made with `neighbors_error`) answer with the bgpd-off captures in `tests/fixtures/frr_fp043ic_followup/`, the state their scenario describes (vtysh can't reach bgpd, daemons says `bgpd=no`, no bgpd process). | genuine (new read answered, assertions unchanged) |
| `tests.test_frr_config_load` | 19 | new-read (frr; one eos,frr) | main's fakes refuse the guard's reads; the candidate's answer them with live FRR 10.4.1 captures. The config-load assertions are unchanged. | genuine |
| `tests.test_runner_mutants` | 11 | verdict / new-read on * | same FakeLab `exec` gap; the mutant tests' assertions are unchanged and pass with the candidate's fakes | genuine |
| `tests.test_mgmt` | 4 | verdict / new-read on * | same FakeLab `exec` gap; management-route assertions unchanged | genuine |
| `tests.test_runner_robustness` | 4 | verdict | same FakeLab `exec` gap; robustness assertions unchanged | genuine |
| `tests.test_acceptance_041` | 2 | verdict (was new-read on 5a36902) | node r1 runs `vrnetlab/cisco_n9kv`; NX-OS is a beta driver, so no driver claims it and the new probe calls `exec`, which main's FakeLab lacks. Checked: main's two tests on the candidate's src, with main's FakeLab given an `exec` that answers as a real vrnetlab container does (rc 127, Docker's `exec: "vtysh": executable file not found in $PATH`), both pass (`failed` with no error; `error` naming `clab-t-r1` and "requires KVM" within 120 s). The probe was called once on r1 and classed it as not a router. | genuine |

Noise, not covered by this review: `tests.test_startup_config_load::test_audit_f1_an_exec_command_that_failed_fails_the_deploy`
and the two `tests.test_verdict_keys_041::test_action_verify_*` tests. On 5a36902 instrumented runs showed the guard
is never called in them.

## What was checked

- Round-1 findings, live on 83576ad (FRR 10.4.1, Docker, Ubuntu-ndr):
  - MAJOR-A (delay-timer 0, permit map defined after `router bgp`): exit 2, "bgpd never applied the route-map's last
    change to it (`processedChange`)... No verdict". It was a PASS on 5a36902.
  - MAJOR-B (pe1 on a retagged FRR image, no driver override): pe1 probed ("vtysh answers with bgpd's running
    config"), found stuck, remedied, verdict FAIL, exit 1. The report names pe1 as found by probing. It was a PASS
    with pe1 unguarded on 5a36902.
  - MINOR-1 (MCP `record_baseline` unguarded): guarded before and after recording, and gap lines are added (code
    and the new tests; mutants N21 to N23 killed).
  - The other MINORs (daemons-file spellings, a delay above the budget, no sampling with no routers) are fixed and
    covered.
- Abuse of the route-map rule (code and FRR 10.4.1 behaviour):
  - A map applied, then redefined: with a non-zero timer bgpd re-applies it to the network, and `processedChange` stays
    true until then. With timer 0 the change is never processed, so this is an error.
  - A map defined in the running config but not in bgpd, and the reverse: both Unknown.
  - A route-map answer about another map or another daemon: Unknown.
  - An exemption on a node found by probing: it needs the same boot-log, BGP-table and route-map evidence as a
    detected FRR router.
- The driverless probe: only rc 127 with Docker's own no-such-executable line counts as "not a router". A stopped
  container, a timeout or any other answer is a gap (console WARNING, `not checked` in the report, a warning
  `import-check-not-checked` on every check, INCOMPLETE BASELINE and exit 1 for `record`).
- 28 new mutants of the a333c28 logic. 25 were killed. Three survived:
  - N07 (a route-map answer listing extra maps besides NAME is accepted): near-equivalent, since bgpd answers
    `show route-map NAME` for that name only.
  - N10 (a route-map name that fails `_NAME` is accepted): near-equivalent, since FRR never prints one.
  - N11 (rc 127 without Docker's line counts as "not a router"): a test gap, MINOR-3 below.

## MINORs (none blocks the merge)

1. **The timer-0 error advises a fix that does not work (live).** With `bgp route-map delay-timer 0`, bgpd never
   clears `processedChange` for any route-map, including one defined before the `network` (lab rm0e: `EARLYDENY`
   defined before `router bgp`, `invoked: 1`, `processedChange: true`, prefix correctly not in the table). The run
   ends with no verdict (fail-closed, not a false pass). But the message says "or define the route-map before the
   `network`", and that does not help. Fix: advise only removing the timer, and add this capture as a fixture.
2. **A gap can still end in PASS, exit 0.** The warning shows on every check in the text, JSON and markdown output.
   But the summary counts it as "N with a convergence warning", which is the wrong label. Opinion: an FRR import
   check that couldn't be told is the exact false-pass class this fix closes, and the probe only reaches a gap on an
   unexpected answer. So `run` should make a gap inconclusive (as `record` already exits 1), or at least label it
   correctly in the summary.
3. **The rc-127 branch has no negative test (mutant N11).** Add a probe case with rc 127 and other text (for example
   `sh: vtysh: not found`) that must be Unknown.
4. Nit: the probe's "not a router" result is silent. An image that runs bgpd with no vtysh on PATH would stay
   unguarded with no log line. Checking `/proc/*/comm` for bgpd before returning None would close it.
5. Nit: the candidate's FakeLab answers FRR's running config for every node, including the n9kv-image node in
   `test_acceptance_041`. Answering by image (rc 127 for the n9kv node) would keep the fakes consistent.
6. Nit: in `verify` a gap is logged on the console only. The node is already listed as unobserved in every output,
   because verify refuses a driverless node unless `--unobserved` names it.

## The 99 flips judged genuine

- `tests.test_acceptance_041::test_a_healthy_lab_is_not_stopped_by_the_watch` (verdict)
- `tests.test_acceptance_041::test_a_node_container_that_dies_ends_the_run_at_once` (verdict)
- `tests.test_frr_config_load::test_a_bridge_a_ceos_node_or_an_unreadable_host_before_an_frr_node_never_ends_the_scan` (new-read on eos,frr)
- `tests.test_frr_config_load::test_a_bridge_has_no_boot_log_to_read` (new-read on frr)
- `tests.test_frr_config_load::test_a_clean_boot_still_passes` (new-read on frr)
- `tests.test_frr_config_load::test_a_driver_set_in_the_file_decides_that_a_node_is_frr` (new-read on frr)
- `tests.test_frr_config_load::test_a_node_whose_driver_is_unknown_is_read_too` (new-read on frr)
- `tests.test_frr_config_load::test_a_plain_host_with_an_unknown_driver_is_not_an_error` (new-read on frr)
- `tests.test_frr_config_load::test_a_rejected_line_on_any_frr_node_makes_the_run_an_error[False]` (new-read on frr)
- `tests.test_frr_config_load::test_a_rejected_line_on_any_frr_node_makes_the_run_an_error[True]` (new-read on frr)
- `tests.test_frr_config_load::test_an_applied_line_passes_the_run` (new-read on frr)
- `tests.test_frr_config_load::test_an_frr_log_with_no_sign_of_a_config_load_is_an_error` (new-read on frr)
- `tests.test_frr_config_load::test_an_unreadable_boot_log_is_an_error` (new-read on frr)
- `tests.test_frr_config_load::test_an_unreadable_running_config_or_file_keeps_the_error_and_says_why[conf]` (new-read on frr)
- `tests.test_frr_config_load::test_an_unreadable_running_config_or_file_keeps_the_error_and_says_why[running]` (new-read on frr)
- `tests.test_frr_config_load::test_an_unreadable_running_config_without_a_reason_says_so` (new-read on frr)
- `tests.test_frr_config_load::test_no_running_config_is_read_without_a_failure_to_communicate` (new-read on frr)
- `tests.test_frr_config_load::test_only_frr_nodes_are_read` (new-read on frr)
- `tests.test_frr_config_load::test_only_the_daemons_that_answered_failure_to_communicate_are_read` (new-read on frr)
- `tests.test_frr_config_load::test_the_error_names_every_node_and_every_line_exactly` (new-read on frr)
- `tests.test_frr_config_load::test_the_reason_keeps_the_last_200_characters` (new-read on frr)
- `tests.test_mgmt::test_run_ends_with_an_error_when_a_route_out_appears` (verdict)
- `tests.test_mgmt::test_run_records_a_route_deleted_again` (verdict)
- `tests.test_mgmt::test_run_refuses_a_routing_node_whose_route_isnt_handled` (new-read on *)
- `tests.test_mgmt::test_run_removes_the_route_after_setup_and_before_the_first_check` (verdict)
- `tests.test_runner_mutants::test_a_clean_cleanup_says_it_destroys_and_warns_of_nothing` (verdict)
- `tests.test_runner_mutants::test_a_cleanup_that_raises_is_warned` (verdict)
- `tests.test_runner_mutants::test_a_failed_cleanup_is_warned_with_its_output[1--xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyy-yyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyy]` (verdict)
- `tests.test_runner_mutants::test_a_failed_cleanup_is_warned_with_its_output[1-out-err-err]` (verdict)
- `tests.test_runner_mutants::test_a_failed_cleanup_is_warned_with_its_output[2-out--out]` (verdict)
- `tests.test_runner_mutants::test_a_kept_lab_says_how_to_destroy_it` (verdict)
- `tests.test_runner_mutants::test_a_scenario_that_does_not_recover_says_later_ones_are_skipped` (verdict)
- `tests.test_runner_mutants::test_a_signal_during_cleanup_is_honoured_and_named` (verdict)
- `tests.test_runner_mutants::test_run_hands_its_driver_overrides_to_the_scenarios` (verdict)
- `tests.test_runner_mutants::test_run_reads_the_sr_linux_load_on_a_lab_it_deployed` (new-read on *)
- `tests.test_runner_mutants::test_the_last_scenario_not_recovering_skips_nothing` (verdict)
- `tests.test_runner_robustness::test_negative_check_waits_for_every_bgp_session_on_its_node` (verdict)
- `tests.test_runner_robustness::test_scenario_positive_cannot_pass_on_pre_fault_state[0.0]` (verdict)
- `tests.test_runner_robustness::test_scenario_positive_cannot_pass_on_pre_fault_state[10.0]` (verdict)
- `tests.test_runner_robustness::test_scenario_waits_for_the_fault_to_show_in_bgp` (verdict)
- `tests.test_verdict_runner::test_a_bgp_node_with_no_neighbors_at_the_cap_fails_its_post_convergence_checks` (verdict)
- `tests.test_verdict_runner::test_a_bgp_node_with_no_neighbors_beside_a_working_node_is_a_failure` (verdict)
- `tests.test_verdict_runner::test_a_check_that_failed_in_a_never_left_scenario_stays_failed_exit_1` (verdict)
- `tests.test_verdict_runner::test_a_driver_that_cannot_verify_the_load_says_so` (verdict)
- `tests.test_verdict_runner::test_a_lab_that_never_reached_a_testable_state_is_inconclusive_with_scenarios_too` (verdict)
- `tests.test_verdict_runner::test_a_leak_slowed_by_a_peers_advertisement_interval_is_still_seen` (verdict)
- `tests.test_verdict_runner::test_a_node_without_bgp_checks_is_still_released_at_the_cap` (verdict)
- `tests.test_verdict_runner::test_a_real_failure_beside_a_never_left_scenario_stays_failed` (verdict)
- `tests.test_verdict_runner::test_a_rejected_config_line_makes_the_run_an_error_never_a_pass` (verdict)
- `tests.test_verdict_runner::test_a_run_whose_only_failures_never_left_is_inconclusive_exit_3` (verdict)
- `tests.test_verdict_runner::test_a_scenario_without_injected_routes_still_streams_as_it_goes` (verdict)
- `tests.test_verdict_runner::test_agent_eval_t10_bgpd_off_everywhere_is_inconclusive_not_an_error` (verdict)
- `tests.test_verdict_runner::test_bgp_route_attribute_is_not_judged_on_a_temporary_best_path` (verdict)
- `tests.test_verdict_runner::test_checks_wait_on_the_runner_clock` (verdict)
- `tests.test_verdict_runner::test_cleanup_trouble_never_hides_the_results` (verdict)
- `tests.test_verdict_runner::test_deploy_setup_and_destroy` (verdict)
- `tests.test_verdict_runner::test_drivers_get_the_configured_override` (verdict)
- `tests.test_verdict_runner::test_each_kind_of_bgp_check_marks_its_node_as_running_bgp[bgp_prefixes]` (verdict)
- `tests.test_verdict_runner::test_each_kind_of_bgp_check_marks_its_node_as_running_bgp[bgp_route]` (verdict)
- `tests.test_verdict_runner::test_each_kind_of_bgp_check_marks_its_node_as_running_bgp[bgp_session]` (verdict)
- `tests.test_verdict_runner::test_each_kind_of_bgp_check_marks_its_node_as_running_bgp[route-protocol-bgp]` (verdict)
- `tests.test_verdict_runner::test_gate_uses_positive_results_to_skip_dead_nodes` (verdict)
- `tests.test_verdict_runner::test_gate_warning_when_a_node_never_answers` (verdict)
- `tests.test_verdict_runner::test_good_settle_and_hold[0.0]` (verdict)
- `tests.test_verdict_runner::test_good_settle_and_hold[0]` (verdict)
- `tests.test_verdict_runner::test_good_settle_and_hold[1000000000.0]` (verdict)
- `tests.test_verdict_runner::test_hold_is_passed_to_the_post_convergence_checks` (verdict)
- `tests.test_verdict_runner::test_inject_routes_needs_an_frr_node` (verdict)
- `tests.test_verdict_runner::test_interrupted_by_sigterm` (verdict)
- `tests.test_verdict_runner::test_keep_leaves_the_lab_and_never_registers_it` (verdict)
- `tests.test_verdict_runner::test_keep_on_failure[False-0]` (verdict)
- `tests.test_verdict_runner::test_keep_on_failure[True-1]` (verdict)
- `tests.test_verdict_runner::test_keep_on_failure_does_not_apply_to_an_interrupted_run` (verdict)
- `tests.test_verdict_runner::test_later_scenarios_are_skipped_when_the_network_does_not_recover` (verdict)
- `tests.test_verdict_runner::test_negative_checks_run_after_convergence_and_hold` (verdict)
- `tests.test_verdict_runner::test_no_deploy_means_no_setup_and_no_destroy` (verdict)
- `tests.test_verdict_runner::test_no_signal_during_cleanup_after_an_interrupt` (verdict)
- `tests.test_verdict_runner::test_node_that_never_reports_bgp_neighbors_is_released_at_the_cap_with_a_warning` (verdict)
- `tests.test_verdict_runner::test_node_without_bgp_neighbors_yet_is_not_converged` (verdict)
- `tests.test_verdict_runner::test_not_converged_checks_are_reported_once_and_not_held` (verdict)
- `tests.test_verdict_runner::test_only_passing_positive_checks_must_recover` (verdict)
- `tests.test_verdict_runner::test_positive_check_passes_on_two_samples_and_is_not_held` (verdict)
- `tests.test_verdict_runner::test_post_convergence_check_is_not_judged_on_two_early_samples` (verdict)
- `tests.test_verdict_runner::test_recovered_network_adds_nothing` (verdict)
- `tests.test_verdict_runner::test_report_started` (verdict)
- `tests.test_verdict_runner::test_results_of_every_phase_are_kept` (verdict)
- `tests.test_verdict_runner::test_run_defaults_settle_and_hold_10s` (verdict)
- `tests.test_verdict_runner::test_run_scenario_gate_ignores_sessions_a_top_level_check_expects_down` (verdict)
- `tests.test_verdict_runner::test_scenario_drivers_built_mid_scenario_get_their_override` (verdict)
- `tests.test_verdict_runner::test_scenario_recovery_is_checked` (verdict)
- `tests.test_verdict_runner::test_scenario_results_are_reported` (verdict)
- `tests.test_verdict_runner::test_scenarios_on_nodes_that_gave_state_still_run_after_an_unready_main_phase` (verdict)
- `tests.test_verdict_runner::test_settle_waits_at_least_30s_when_nothing_proved_convergence` (verdict)
- `tests.test_verdict_runner::test_short_advertisement_intervals_leave_the_windows_alone` (verdict)
- `tests.test_verdict_runner::test_signal_during_cleanup_is_raised_after_it` (verdict)
- `tests.test_verdict_runner::test_the_console_never_streams_a_pass_that_turns_inconclusive` (verdict)
- `tests.test_verdict_runner::test_the_no_neighbors_result_is_a_complete_failed_result` (verdict)
- `tests.test_verdict_runner::test_the_report_names_each_nodes_image_digest_and_nos_version` (verdict)
- `tests.test_verdict_runner::test_unreadable_snapshot_after_a_readable_failure_is_still_an_error` (verdict)
