# Release gate: Netdryrun 0.3.3

Written by `scripts/release_gate.py` (see [RELEASING.md](../../RELEASING.md)). Do not edit by hand: rerun a layer, or record a decision in `accepted.json` or `review.md`.

**CLEARED**: every layer ran on the same clean commit; no BLOCKER failed or was skipped; every MAJOR passed or was accepted.

| Layer | Commit | Ran | Time | Result |
|---|---|---|---|---|
| [Layer 1: static](#layer-1-static) | `91b4820a78` | 2026-10-30 03:53:02 UTC | 0.9 s | 14 PASS |
| [Layer 2: unit tests on every supported Python](#layer-2-unit-tests-on-every-supported-python) | `878ac81b42` | 2026-10-30 00:35:51 UTC | 4.0 min | 7 PASS |
| [Layer 4: mutation testing](#layer-4-mutation-testing) | `878ac81b42` | 2026-10-30 00:45:03 UTC | 22.8 min | 4 PASS |
| [Layer 5: live matrix on the built package](#layer-5-live-matrix-on-the-built-package) | `878ac81b42` | 2026-10-30 01:08:40 UTC | 156.9 min | 2 ACCEPTED, 50 PASS |
| [Layer 7: after-publish proof](#layer-7-after-publish-proof) | `91b4820a78` | 2026-10-30 06:06:12 UTC | 2.5 min | 1 ACCEPTED, 13 PASS |

## Layer 1: static

Commit `91b4820a7857e8b8af25a7be7e6ac66601011838` on `ndr/agent-runtime`; 2026-10-30 03:53:02 UTC; 0.9 s; Linux 6.18.54.1-microsoft-standard-WSL2 (x86_64); Python 3.10.12; --strict.

Tools: actionlint 1.7.7; ruff 0.17.3; shellcheck 0.8.0.

| Check | Severity | Result | Time | Notes |
|---|---|---|---|---|
| ruff (config in pyproject.toml) | BLOCKER | **PASS** | 0.0 s | All checks passed! |
| actionlint on every workflow (with shellcheck) | BLOCKER | **PASS** | 0.1 s | clean |
| shellcheck, error level, 18 scripts | BLOCKER | **PASS** | 0.2 s | clean |
| shellcheck, warning level, 18 scripts | MAJOR | **PASS** | 0.1 s | clean |
| no empty ${{ }} in action.yml or workflows | BLOCKER | **PASS** | 0.0 s | none |
| public facts match the source (sync_facts.py --check) | BLOCKER | **PASS** | 0.2 s | facts: in sync (version 0.3.3, 0 problem(s)) |
| every version reference says 0.3.3 | BLOCKER | **PASS** | 0.0 s | 39 references agree |
| pyproject.toml declares Python 3.10 to 3.14, the versions tested | MAJOR | **PASS** | 0.0 s | requires-python and classifiers agree |
| every example has a documented expected result and exit code | MAJOR | **PASS** | 0.0 s | 8 examples |
| every topology we ship is named ndr-* | BLOCKER | **PASS** | 0.0 s | 90 topologies |
| no retired public string outside the history (CHANGELOG, advisories, records) | BLOCKER | **PASS** | 0.0 s | none |
| CHANGELOG has no Unreleased entries left (all under 0.3.3) | BLOCKER | **PASS** | 0.0 s | cut |
| tag v0.3.3 does not exist yet | BLOCKER | **PASS** | 0.0 s | unused |
| PyPI has no netdryrun 0.3.3 yet | BLOCKER | **PASS** | 0.0 s | HTTP 404 |

## Layer 2: unit tests on every supported Python

Commit `878ac81b42c7822877b3f48b3c268d00ce4bdddd` on `ndr/agent-runtime`; 2026-10-30 00:35:51 UTC; 4.0 min; Linux 6.18.54.1-microsoft-standard-WSL2 (x86_64); Python 3.10.12; --strict.

Tools: docker 29.9.2; uv 0.13.6 (x86_64-unknown-linux-gnu).

| Check | Severity | Result | Time | Notes |
|---|---|---|---|---|
| unit tests on Python 3.10.12 | BLOCKER | **PASS** | 41.3 s | 2382 passed, 41 skipped |
| unit tests on Python 3.11.18 | BLOCKER | **PASS** | 33.8 s | 2382 passed, 41 skipped |
| unit tests on Python 3.12.16 (with coverage) | BLOCKER | **PASS** | 53.0 s | 2382 passed, 41 skipped |
| coverage of the verdict modules at or above the floors | MAJOR | **PASS** | 0.0 s | all at or above their floors |
| unit tests on Python 3.13.18 | BLOCKER | **PASS** | 31.2 s | 2382 passed, 41 skipped |
| unit tests on Python 3.14.10 | BLOCKER | **PASS** | 31.6 s | 2382 passed, 41 skipped |
| unit tests in a plain python:3.12-slim container (no containerlab, no Docker) | BLOCKER | **PASS** | 50.0 s | 2381 passed, 42 skipped |

**Coverage of the verdict modules** (lines and branches, Python 3.12):

| Module | Lines | Branches | Covered | Floor |
|---|---|---|---|---|
| `src/netdryrun/checks.py` | 292/293 | 125/126 | 99.5% | 99% |
| `src/netdryrun/config.py` | 446/449 | 263/266 | 99.2% | 99% |
| `src/netdryrun/runner.py` | 566/573 | 233/238 | 98.5% | 98% |
| `src/netdryrun/drivers/` | 792/792 | 278/280 | 99.8% | 99% |

## Layer 4: mutation testing

Commit `878ac81b42c7822877b3f48b3c268d00ce4bdddd` on `ndr/agent-runtime`; 2026-10-30 00:45:03 UTC; 22.8 min; Linux 6.18.54.1-microsoft-standard-WSL2 (x86_64); Python 3.10.12; --strict.

Tools: mutmut python -m mutmut, version 3.8.0.

| Check | Severity | Result | Time | Notes |
|---|---|---|---|---|
| no surviving mutants in src/netdryrun/checks.py | BLOCKER | **PASS** | 21.9 min | 1220 generated, 1138/1220 caught (93.3%); not caught: 82 survived the tests, 0 in code no test runs, 82 accepted (33 equivalent, 49 message-text) |
| no surviving mutants in src/netdryrun/config.py | BLOCKER | **PASS** | 0.0 s | 1480 generated, 1232/1480 caught (83.2%); not caught: 248 survived the tests, 0 in code no test runs, 248 accepted (25 equivalent, 223 message-text) |
| no surviving mutants in src/netdryrun/runner.py | BLOCKER | **PASS** | 0.0 s | 1389 generated, 1203/1389 caught (86.6%); not caught: 186 survived the tests, 0 in code no test runs, 186 accepted (28 equivalent, 30 logging, 127 message-text, 1 timing-only) |
| no surviving mutants in src/netdryrun/drivers/ | BLOCKER | **PASS** | 0.0 s | 1931 generated, 1716/1931 caught (88.9%); not caught: 215 survived the tests, 0 in code no test runs, 215 accepted (23 equivalent, 192 message-text) |

**Surviving mutants by function** (731 in all; every diff is in [mutants.md](mutants.md)):

| Function | Survivors |
|---|---|
| `config._describe` | 91 |
| `runner._bgp_convergence_gate` | 73 |
| `config._validate_check` | 50 |
| `runner.run` | 37 |
| `config._validate_scenario` | 30 |
| `drivers.frr._bgp_paths_raw` | 26 |
| `drivers.eos._summary` | 24 |
| `checks._ping` | 23 |
| `checks._route` | 20 |
| `drivers.frr._route_table` | 18 |
| `config.load` | 17 |
| `config.load_yaml` | 15 |
| `drivers.eos._bgp_entries` | 15 |
| `runner._yaml_problem` | 15 |
| `config._StrictLoader.construct_mapping` | 13 |
| `drivers.eos._vrf` | 12 |
| `runner.run_scenario` | 12 |
| `checks._describe_path` | 11 |
| `config._validate_bgp_route` | 11 |
| `runner._wait_fault_visible` | 11 |
| `drivers.srlinux._rib_rows` | 10 |
| `runner._link_sessions` | 10 |
| `checks._bgp_route` | 9 |
| `drivers.srlinux.SrlDriver._read_path` | 9 |
| `runner._shape_problem` | 9 |
| `runner.load_config` | 8 |
| `config._reject_unknown` | 7 |
| `drivers.base.unexpected` | 7 |
| `drivers.frr._bgp_json` | 7 |
| `checks.is_post_convergence` | 6 |
| `drivers.base.Driver._exec` | 6 |
| `drivers.base.as_int` | 6 |
| `drivers.base.load_json` | 6 |
| `drivers.eos._learned` | 6 |
| `drivers.frr._learned` | 6 |
| `drivers.srlinux._list` | 6 |
| `config._suggest` | 5 |
| `drivers.base.network` | 5 |
| `drivers.srlinux._json` | 5 |
| `runner._reach_then_hold` | 5 |
| `runner.preflight` | 5 |
| `checks._evaluate_all` | 4 |
| `drivers.eos._json` | 4 |
| `drivers.eos._table` | 4 |
| `drivers.frr.FrrDriver._confirm_vrf` | 4 |
| `checks.run_round_robin` | 3 |
| `config.Fault.describe` | 3 |
| `config.normalize_as_path` | 3 |
| `drivers.base.Driver.all_routes` | 3 |
| `drivers.check_supported` | 3 |
| `drivers.for_node` | 3 |
| `checks._reach_view` | 2 |
| `checks.inconclusive_reason` | 2 |
| `config._validate_nodes` | 2 |
| `drivers.base.Driver.bgp_neighbors` | 2 |
| `drivers.base.Driver.bgp_paths` | 2 |
| `drivers.base.Driver.ping` | 2 |
| `drivers.base.Driver.routes` | 2 |
| `drivers.base.check_vrf_name` | 2 |
| `drivers.frr._bgp_paths_for_route_check` | 2 |
| `drivers.frr.parse_config_load_errors` | 2 |
| `drivers.srlinux.parse_instance_state` | 2 |
| `checks._not_configured` | 1 |
| `checks.converge_then_hold` | 1 |
| `config.parse_community` | 1 |
| `drivers.eos.EosDriver.all_routes` | 1 |
| `drivers.frr.FrrDriver.all_routes` | 1 |
| `drivers.srlinux.SrlDriver.all_routes` | 1 |
| `drivers.srlinux._bgp_learned` | 1 |
| `runner._sessions_over_links` | 1 |

## Layer 5: live matrix on the built package

Commit `878ac81b42c7822877b3f48b3c268d00ce4bdddd` on `ndr/agent-runtime`; 2026-10-30 01:08:40 UTC; 156.9 min; Linux 6.18.54.1-microsoft-standard-WSL2 (x86_64); Python 3.10.12; --strict.

Tools: containerlab ⣴⡾⠛⠛⠖ ⢠⣶⠟⠛⢷⣦ ⢸⣿⣧ ⣿ ⠘⠛⢻⡟⠛⠛ ⣾⣿⡀ ⣿⡇ ⣿⣿⡄ ⢸⡇ ⣿⡟⠛⠛⠃⢸⣿⠛⠛⣷⡄ [38;2;0;201;255m⣿⡇[0m ; docker 29.9.2.

| Check | Severity | Result | Time | Notes |
|---|---|---|---|---|
| build the wheel | BLOCKER | **PASS** | 0.6 s | netdryrun-0.3.3-py3-none-any.whl |
| install netdryrun-0.3.3-py3-none-any.whl in a fresh venv | BLOCKER | **PASS** | 0.4 s |  |
| runs the installed package, not the source tree | BLOCKER | **PASS** | 0.0 s | /tmp/ndr-gate-live-vwhe7d3_/venv/lib/python3.12/site-packages/netdryrun/__init__.py |
| netdryrun --version says 0.3.3 | BLOCKER | **PASS** | 0.0 s | netdryrun 0.3.3 |
| example agent-demo: `Demo OK`, exit 0 | BLOCKER | **PASS** | 72.5 s | exit 0: Demo OK: attempt 1 rejected by 5 leak guards with every other check passing; attempt 2 passed every check. |
| example agent-demo: no lab left running | BLOCKER | **PASS** | 0.0 s | none left |
| example arista-frr: `PASSED: 10 passed, 0 failed`, exit 0 | BLOCKER | **PASS** | 1.7 min | exit 0: PASSED: 10 passed, 0 failed (10 checks) |
| example arista-frr: no lab left running | BLOCKER | **PASS** | 0.0 s | none left |
| example batfish-pipeline: `PASSED: 10 passed, 0 failed`, exit 0 | BLOCKER | **PASS** | 1.7 min | exit 0: PASSED: 10 passed, 0 failed (10 checks) |
| example batfish-pipeline: no lab left running | BLOCKER | **PASS** | 0.0 s | none left |
| example frr-bgp: `PASSED: 11 passed, 0 failed`, exit 0 | BLOCKER | **PASS** | 1.7 min | exit 0: PASSED: 11 passed, 0 failed (11 checks) |
| example frr-bgp: no lab left running | BLOCKER | **PASS** | 0.0 s | none left |
| example frr-bgp-broken: `FAILED: 5 passed, 1 failed`, exit 1 | BLOCKER | **PASS** | 39.9 s | exit 1: FAILED: 5 passed, 1 failed (6 checks) |
| example frr-bgp-broken: no lab left running | BLOCKER | **PASS** | 0.0 s | none left |
| example sonic-frr: `PASSED: 8 passed, 0 failed`, exit 0 | BLOCKER | **PASS** | 1.6 min | exit 0: PASSED: 8 passed, 0 failed (8 checks) |
| example sonic-frr: no lab left running | BLOCKER | **PASS** | 0.0 s | none left |
| example srl-frr: `PASSED: 7 passed, 0 failed`, exit 0 | BLOCKER | **PASS** | 62.6 s | exit 0: PASSED: 7 passed, 0 failed (7 checks) |
| example srl-frr: no lab left running | BLOCKER | **PASS** | 0.0 s | none left |
| example srl-hidden-leak: `PASSED: 9 passed, 0 failed`, exit 0 | BLOCKER | **PASS** | 61.1 s | exit 0: PASSED: 9 passed, 0 failed (9 checks) |
| example srl-hidden-leak: no lab left running | BLOCKER | **PASS** | 0.0 s | none left |
| example srl-hidden-leak with leaks/frr1.conf: `FAILED: 8 passed, 1 failed`, exit 1 | BLOCKER | **PASS** | 80.8 s | exit 1: FAILED: 8 passed, 1 failed (9 checks) |
| example srl-hidden-leak with leaks/frr1.conf: no lab left running | BLOCKER | **PASS** | 0.0 s | none left |
| example srl-hidden-leak with leaks/srl1.cli: `FAILED: 8 passed, 1 failed`, exit 1 | BLOCKER | **PASS** | 83.0 s | exit 1: FAILED: 8 passed, 1 failed (9 checks) |
| example srl-hidden-leak with leaks/srl1.cli: no lab left running | BLOCKER | **PASS** | 0.0 s | none left |
| example times match the docs (within 2x) | MAJOR | **PASS** | 0.0 s | all within 2x |
| Verdict Corpus v1: every verdict matches the committed results.json | BLOCKER | **PASS** | 67.1 min | all verdicts match |
| Verdict Corpus v1: no harmful change approved beyond the published known misses | BLOCKER | **PASS** | 0.0 s | harmful changes approved: 5 (12-ibgp-send-community-dropped, 18-redistribute-connected, 21-customer-max-prefix-removed, 23-fat-finger-third-party-origin, 30-peer-import-filter-removed); published known misses: 12-ibgp-send-community-dropped, 18-redistribute-connected, 21-customer-max-prefix-removed, 23-fat-finger-third-party-origin, 30-peer-import-filter-removed |
| Verdict Corpus v1: no lab left running | BLOCKER | **PASS** | 0.0 s | none left |
| Verdict Corpus v2: every verdict matches the committed results.json | BLOCKER | **PASS** | 70.1 min | all verdicts match |
| Verdict Corpus v2: the nondeterministic exemption holds (pinned list, repeats ran, no error) | BLOCKER | **PASS** | 0.0 s | 18-aggregate-discard-route-removed |
| Verdict Corpus v2: nondeterministic cases recorded (known, not scored, never a blocker) | INFO | **PASS** | 0.0 s | Netdryrun verdicts per run: 18-aggregate-discard-route-removed: unsafe, unsafe, safe |
| Verdict Corpus v2: no harmful change approved beyond the published known misses | BLOCKER | **PASS** | 0.0 s | harmful changes approved: 1 (04-redundant-aggregate-typo); published known misses: 04-redundant-aggregate-typo |
| Verdict Corpus v2: no lab left running | BLOCKER | **PASS** | 0.0 s | none left |
| MCP handshake against the installed wheel | BLOCKER | **PASS** | 1.2 s | MCP handshake OK |
| check pack verification | MAJOR | **ACCEPTED** | 0.0 s | no --pack script given (accepted: No check pack is sold yet: pack verification is paused by the roadmap until the 45-day demand test; it runs with --pack before any pack ships.) |
| 20-node scale test | MAJOR | **ACCEPTED** | 0.0 s | not scripted in the repository yet: run it by hand (accepted: Not scripted yet. A 20-node lab was run by hand in pre-launch testing (it found the PR-comment size limit, fixed in 0.3.1); scripting it is a 0.4.1 item.) |
| SIGINT during deploy: exit 130, a clear message | BLOCKER | **PASS** | 4.7 s | exit 130 |
| SIGINT during deploy: no lab left running | BLOCKER | **PASS** | 0.0 s | none left |
| SIGINT during checks: exit 130, a clear message | BLOCKER | **PASS** | 17.1 s | exit 130 |
| SIGINT during checks: no lab left running | BLOCKER | **PASS** | 0.0 s | none left |
| SIGTERM during deploy: exit 143, a clear message | BLOCKER | **PASS** | 6.0 s | exit 143 |
| SIGTERM during deploy: no lab left running | BLOCKER | **PASS** | 0.0 s | none left |
| SIGTERM during checks: exit 143, a clear message | BLOCKER | **PASS** | 18.0 s | exit 143 |
| SIGTERM during checks: no lab left running | BLOCKER | **PASS** | 0.0 s | none left |
| a node's image does not exist: exit 2 with a clear error | BLOCKER | **PASS** | 0.4 s | exit 2:   wrote json report: /tmp/ndr-gate-live-vwhe7d3_/reports/frr-bgp-missing-image.json |
| a node's image does not exist: no lab left running | BLOCKER | **PASS** | 0.0 s | none left |
| a node cannot be created (a bind source does not exist): exit 2 with a clear error | BLOCKER | **PASS** | 0.3 s | exit 2:   wrote json report: /tmp/ndr-gate-live-vwhe7d3_/reports/frr-bgp-deploy-fails.json |
| a node cannot be created (a bind source does not exist): no lab left running | BLOCKER | **PASS** | 0.0 s | none left |
| two runs of the same lab at once: no false verdict, no crash | BLOCKER | **PASS** | 1.7 min | exit codes 2 and 0 |
| two runs at once: no lab left running | BLOCKER | **PASS** | 0.0 s | none left |
| Docker restarts mid-run: never passed, a clear message | BLOCKER | **PASS** | 3.9 min | exit 2 |
| Docker restart: no lab left running | BLOCKER | **PASS** | 0.0 s | none left |

## Layer 7: after-publish proof

Commit `91b4820a7857e8b8af25a7be7e6ac66601011838` on `HEAD`; 2026-10-30 06:06:12 UTC; 2.5 min; Linux 6.18.54.1-microsoft-standard-WSL2 (x86_64); Python 3.10.12.

Tools: uv 0.13.6 (x86_64-unknown-linux-gnu).

| Check | Severity | Result | Time | Notes |
|---|---|---|---|---|
| PyPI serves netdryrun 0.3.3 | BLOCKER | **PASS** | 0.0 s | HTTP 200 |
| pip install netdryrun==0.3.3 on Python 3.10: --version, validate, MCP handshake | BLOCKER | **PASS** | 8.0 s | MCP handshake OK |
| uvx netdryrun@0.3.3 on Python 3.10: --version, MCP handshake | BLOCKER | **PASS** | 1.7 s | MCP handshake OK |
| pip install netdryrun==0.3.3 on Python 3.11: --version, validate, MCP handshake | BLOCKER | **PASS** | 7.6 s | MCP handshake OK |
| uvx netdryrun@0.3.3 on Python 3.11: --version, MCP handshake | BLOCKER | **PASS** | 1.6 s | MCP handshake OK |
| pip install netdryrun==0.3.3 on Python 3.12: --version, validate, MCP handshake | BLOCKER | **PASS** | 8.5 s | MCP handshake OK |
| uvx netdryrun@0.3.3 on Python 3.12: --version, MCP handshake | BLOCKER | **PASS** | 1.7 s | MCP handshake OK |
| pip install netdryrun==0.3.3 on Python 3.13: --version, validate, MCP handshake | BLOCKER | **PASS** | 7.8 s | MCP handshake OK |
| uvx netdryrun@0.3.3 on Python 3.13: --version, MCP handshake | BLOCKER | **PASS** | 1.6 s | MCP handshake OK |
| pip install netdryrun==0.3.3 on Python 3.14: --version, validate, MCP handshake | BLOCKER | **PASS** | 8.1 s | MCP handshake OK |
| uvx netdryrun@0.3.3 on Python 3.14: --version, MCP handshake | BLOCKER | **PASS** | 1.9 s | MCP handshake OK |
| frr-bgp from PyPI: `PASSED: 11 passed, 0 failed`, exit 0, no lab left | BLOCKER | **PASS** | 1.7 min | exit 0 |
| the MCP Registry lists io.github.netdryrun/netdryrun 0.3.3 | MAJOR | **PASS** | 0.0 s | listed versions: 0.3.0, 0.3.1, 0.3.2, 0.3.3 |
| latest published-action.yml run | MAJOR | **ACCEPTED** | 0.0 s | gh is not installed (accepted: Checked by hand on the public Actions page (the gate reads it with the gh CLI, which the release machine doesn't use): Run 54 of Published release (commit 298bcf6 on main, RELEASE 0.3.3) completed successfully; runs 55 and 56 on later main commits (8a046cc, 43acd5b) also succeeded.) |

## Layer 6: independent review

# Layer 6: independent review, Netdryrun 0.3.3

## Cold code review (fresh agent, no context, the saved prompt; the diff v0.3.2..ndr/agent-runtime, src/, action.yml and templates/netdryrun.yml)

Class: **false-pass** means the finding, if real, could make Netdryrun (or a surface an agent reads) report a pass without testing what it says; under the Layer 6 rule each one is a BLOCKER until it has a failing test and a fix. **other** is everything else. The reviewer found no false pass in the CLI exit code: the job result is still gated on the exit code and the JSON report. Its three false passes were all in the new PR comment / MR note header an agent reads.

| # | Finding | Class | Decision | Commit |
|---|---|---|---|---|
| 1 | A `passed` header from an earlier commit survived a later run that posted nothing (install failed, netdryrun crashed, GitLab's early `exit 2`), and the header named no commit | **false-pass** (agent-facing) | Fixed: the header names the head commit; a run that wrote no report rewrites it as `error`; GitLab writes the note from an EXIT trap, so however the script ends (`test_no_report_still_rewrites_the_header_as_error`, `test_a_job_that_stopped_before_any_report_still_rewrites_the_note_as_error`, `test_a_run_with_no_report_posts_an_error_header_for_the_head_commit`) | `c44a7af` |
| 2 | One marker for every invocation: two labs on one PR overwrote each other's header, the last one winning | **false-pass** (agent-facing) | Fixed: the marker names the lab's `path`, one comment per lab; the guide says every Netdryrun comment must say `passed` (`test_the_body_starts_with_the_lab_marker_then_the_header`, `test_github_updates_only_its_own_comment_for_this_lab`) | `c44a7af` |
| 3 | The comment to update was chosen by body text, not author, so a forged marker comment could stick; GitLab read only the first 100 notes | **false-pass** (agent-facing) | Fixed: only the expected author's comment is updated (Action: `comment-author`, default `github-actions[bot]`; GitLab: the token's own user), every page is read; the docs tell agents to read only the bot's comments (`test_github_creates_a_comment_when_only_others_match`, `test_gitlab_updates_only_the_tokens_own_note_on_any_page`) | `c44a7af` |
| 4 | `tested` is hashed before the deploy, but the agent is free right after `start_run`: a config edited before containerlab reads it was tested yet reported with the old hash | **false-pass** (agent-facing: a verdict tied to the wrong version) | Fixed: after a run that deployed from the files, they are hashed again; a change makes the result `status: error` with `tested.changed_during_run` (MCP and `--verdict`). `check`/`run_checks` don't deploy, which `lab_deployed_by_this_run: false` already says (that sub-point rejected) (`test_a_file_edited_while_the_run_is_in_progress_makes_it_an_error`, `test_a_file_edited_during_the_run_makes_the_agent_result_an_error`) | `35a2089` |
| 5 | `record --guards` swallowed an unreadable interface: no link-subnet guard and no warning | other (coverage dropped) | Fixed: a warning names the node and interface; bridge and host endpoints are skipped (`test_an_unreadable_interface_is_a_warning_not_a_missing_guard`) | `35a2089` |
| 6 | No `::/0` guard when IPv6 unicast runs over IPv4 sessions | other (coverage dropped) | Fixed: IPv6 is also read from the neighbors' address families (`test_ipv6_over_ipv4_sessions_gets_the_ipv6_default_guard`) | `35a2089` |
| 7 | `--verdict` crashed on a topology with a list where a mapping belongs, before any report was written; MCP gave a bare tool error | other (error for the wrong reason) | Fixed: reading the files a run uses never raises; a shape it can't read makes `complete` false (`test_a_malformed_topology_never_crashes_the_agent_result`) | `35a2089` |
| 8 | The client closing stdio during a `start_run` left the lab deployed | other | Fixed: `main()` destroys the active labs when the server stops (`test_the_server_destroys_its_labs_when_the_client_goes_away`) | `35a2089` |
| 9 | Docs and CHANGELOG disagreed with the code: the 50-route cap is per address family; `--min-prefixes` with a count of 0; the your-lab guide still described exact counts; the async result on an internal error; a header `passed` with 0 checks | other (docs) | Fixed, and the header now refuses a pass with no check (`test_a_pass_with_no_check_is_not_a_pass`) | `35a2089`, `c44a7af` |

Each fix was test-first: the tests named above failed on the branch before the fix.

## Multi-vendor AI audit (verdict path)

Three model families got the same brief (`research/briefs/ndr-0.3.3-verdict-audit.md` in HQ). It holds the v0.3.2 diff of src/, `action.yml` and the GitLab component, and none of our conclusions. It asks how this code can:

- report a pass, CHECKS PASSED or a passing PR/MR header without testing what the file or the agent asked;
- escape `NETDRYRUN_MCP_ROOT`;
- turn a failure into a non-failure;
- make a PR/MR's header or outputs lie, or leak the token.

Grok and ChatGPT ran through `research/tools/ask_models.py`. To pass its privacy gate, diff lines are marked `>`/`<`, `index` lines are dropped, and one home path reads `<HOME>`. The open model ran locally (Ollama, qwen3:30b-a3b, 45 minutes). Answers are in HQ `research/model-reviews/release-0.3.3/`. Both API reviews read the code before the cold-review fixes; findings those fixes had already closed are marked so.

| # | Finding | Found by | Class | Decision | Commit |
|---|---|---|---|---|---|
| M1 | Device output in a failed check's evidence can carry a look-alike `<!-- netdryrun-verdict ... passed -->` in the summary | Grok | **false-pass** (agent-facing) | Fixed: the summary can't open an HTML comment (`test_a_lookalike_header_in_the_summary_is_neutralised`) | `36e959b` |
| M2 | Header plus a full summary goes over GitHub's 65,536-character limit, so GitHub rejects the whole comment, header included | Grok | other (verdict lost) | Fixed: the summary is cut so the header stays (`test_the_body_fits_github_with_the_header_first`) | `36e959b` |
| M3 | `start_run`: the lab boots files swapped after the hash, or a topology rewritten to point outside the root | Grok, ChatGPT | **false-pass** | Already fixed by cold review 4: a changed file makes the result an error | `35a2089` |
| M4 | A worker that ends on a `BaseException` leaves the run `running` forever | ChatGPT, Grok | other | Fixed: any end of the worker is a result (`test_a_worker_that_dies_on_a_base_exception_ends_as_error`) | `36e959b` |
| M5 | Truncated run IDs can collide, and every `start_run` shared one evidence file | ChatGPT, Grok | other | Fixed: unique IDs, `netdryrun-report-<run_id>.json` (`test_run_ids_never_collide`, `test_each_async_run_has_its_own_evidence_file`) | `36e959b` |
| M6 | `_tested` listed and walked an outside folder before the root check | ChatGPT | other (confinement) | Fixed: the root check comes first (`test_tested_does_not_list_or_walk_a_folder_outside_the_root`) | `36e959b` |
| M7 | A PR that commits a directory at a report path makes the write fail, so a failed run is published as `error` | Grok | other (exit label) | Fixed: that directory is removed before the run, never the workspace (`test_a_committed_directory_at_a_report_path_is_removed_but_never_the_workspace`). Test-first was not followed: the fix (the removal had to become a loop) was written before its test | `36e959b` |
| M8 | Ranges are now the default, so one leaked default route fits inside a recorded prefix range | Grok | **false-pass** (recorded baselines) | Fixed (coordination decision): `record` writes the guards by default (`--no-guards` to opt out). It writes only guards the recording lab passes, each run with the real check first (`test_guards_are_on_by_default_and_can_be_turned_off`, `test_never_a_guard_the_recording_lab_already_fails`) | `36e959b`, `440f6be` |
| M9 | A failed route read silently dropped that family's link guards, and the link-guard cap was silent | ChatGPT, Grok | other (coverage) | Fixed: each is now an `INCOMPLETE BASELINE` line | `36e959b` |
| M10 | A privileged lab can read the checkout token in `.git/config` | Grok | other (security docs) | Documented: check out with `persist-credentials: false` | `36e959b` |
| M11 | GitLab: the note token is in the job while a privileged lab runs, and the YAML can override `CI_API_V4_URL` | Grok, ChatGPT | other (security scope) | Documented limit (the component is unlisted): anyone who can edit the CI config can read the variable anyway; use `mr-comment` only where MR authors are trusted | `36e959b` |
| M12 | A tampered or stale verdict file with the run's status and plausible counts (GitHub and GitLab), or a forged JSON report for the dotenv | ChatGPT, Qwen | false-pass (claimed) | Rejected: the run deletes these files before it starts and then writes them. Replacing them takes code running in the job after that. A status that disagrees with the checked exit code reads `error` (`test_a_verdict_file_that_disagrees_with_the_run_reads_as_error`) | — |
| M13 | Topology files outside the root (absolute paths, symlinks) are deployed | Grok, ChatGPT | other | Rejected: a documented limit since 0.3.2 (a topology inside the root can still mount host paths) | — |
| M14 | `complete: false` results can still pass; a colon in a bind's host path | ChatGPT | other | Rejected: `complete` is the signal by design, and containerlab's bind syntax splits on the colon too | — |
| M15 | The 50-route cap, and `record`'s headroom lets counts grow | ChatGPT, Grok | other | By design, and both are stated (`INCOMPLETE BASELINE`). The ranges are the documented trade-off; the guards cover the default route | — |
| Q1 | `pr_comment_header` would show a pass with `failed: 1` | Qwen3 30B-A3B | false-pass (claimed) | Rejected, not real: a pass with any failure, or with no check run, reads `error` (`test_the_comment_header_never_carries_lab_text_or_a_pass_it_did_not_get`) | — |
| Q2 | Without a root, files anywhere are hashed | Qwen3 30B-A3B | other | Rejected: an unset root means no confinement, by design and documented; the run deploys those files anyway | — |
| Q3 | A config error with `--verdict` exits 0 | Qwen3 30B-A3B | other (claimed) | Rejected, not real: it exits 2 (`test_a_config_error_writes_the_setup_error`) | — |

## Adversarial review (Layer 6 role 2): the mutant arguments in verdict-deciding functions

ChatGPT reviewed in three rounds (briefs `research/briefs/ndr-0.3.3-adversarial-mutants-{1,2}.md`, `-round2.md`, `-round3.md`). It covered the 184 survivors in `VERDICT_FUNCTIONS` (scripts/release_gate.py), each with its diff and a written argument that it can't turn a failure into a pass.

- **Round 1** checked all 184. Every survivor not listed below was agreed. Several lines marked "REJECT" in fact said the argument holds. The others asked how detail text is used, or gave a counterexample.
- **Round 2** rechecked 93, with the code it asked for: a check's verdict is its `ok` flag, and "unready" is `isinstance(detail, Unready)`, never text. Of the 93, 55 were confirmed and 14 were marked REJECT. Of those 14, 10 said in their own words that only a message changes and no verdict. The other four came with counterexamples.
- **Round 3** traced those four through the code, and all four were confirmed:
  - `_ping_37`: the unreachable pattern needs a literal space, so no match spans two entries (shown by running the regex).
  - `_bgp_convergence_gate_92`: `empty` is always set before it is read.
  - `run_round_robin_72/73`: the branch is unreachable, because a passing sample never ends a check below `confirm`. It is dead code, to remove in 0.4.
- **Killed instead of argued:** `_wait_fault_visible_20` (`continue` to `break` after an unreadable node), by `test_the_fault_wait_names_every_session_still_up_even_after_an_unreadable_node`.

Result: 183 survivors are accepted with a reviewed argument (`reviewed` on each entry in `accepted.json`) and 1 is killed. The review found none that can turn a failure into a pass.

## Cross-platform review (Layer 6 role 3): driver and NOS assumptions

Grok reviewed from `research/briefs/ndr-0.3.3-cross-platform.md`: the four drivers in full, `record`, the `next_diagnostic` commands, and how the lab reads interface addresses.

| # | Finding | Class | Decision | Commit |
|---|---|---|---|---|
| X1 | SONiC keeps a link's address on `EthernetN`, not the topology's `ethN`, so no link guard and no warning | **false-pass** (recorded baselines) | Fixed: a link end with no global address where Netdryrun reads it is an `INCOMPLETE BASELINE` line (`test_a_link_with_no_global_address_where_it_is_read_is_loud`) | `1f2cfb9` |
| X2 | SR Linux keeps it on `e1-Y.0` in `srbase-default` | **false-pass** (recorded baselines) | Fixed by the same rule | `1f2cfb9` |
| X3 | `record` snapshots the default VRF only | coverage | Accepted documented limit: stated in the `record` reference with the mitigation (add checks for other VRFs by hand); fix scheduled: 0.4 (a VRF-aware `record`) | this commit |
| X4 | Scoped link-local neighbors (`fe80::1%eth1`, `fe80::1%eth2`) collapse to one key, so an up session can hide a down one | **false-pass** | Fixed, then superseded by D1/D2 below: keeping the down session hid a false pass on negative checks; the key is now ambiguous and not evaluated | `1f2cfb9` |
| X5 | Graceful-restart stale paths count as present and best until the stale timer ends | **false-pass** | FRR: fixed (coordination decision: a cheap fail-closed fix beats a documented limit). FRR marks the path `"stale": true` (bgpd `route_vty_out_detail`), so a `route` or `bgp_route` check that sees one is not settled, never a pass, present or absent (`test_frr_route_with_a_stale_bgp_path_is_not_settled`, `test_frr_bgp_paths_with_a_stale_path_are_not_settled`, `test_a_route_check_never_passes_on_a_stale_frr_path_present_or_absent`). SR Linux, EOS, SONiC: no stale marker known without a live capture, so an accepted documented limit (advisory, config reference, compatibility matrix), mitigation no GR in labs or a `timeout` above the stale timer; fix scheduled: 0.4 (live GR capture) | this commit |
| X6 | The SR Linux prefix count includes routes dropped by BGP loop detection (seen on a live SR Linux 26.7.2) | **false-pass / accepted documented limit** | Stated publicly in the advisory, the config reference and the compatibility matrix. Mitigation: pair the count with `route` checks; fix scheduled: 0.4 (count usable routes only) | `1f2cfb9`, this commit |
| X7 | SR Linux `bgp-evpn` routes didn't match `protocol: bgp`, so a no-default guard passed on an EVPN-learned default | **false-pass** | Fixed: mapped to `bgp`; widened to every `bgp*` route type by D4 (`test_srl_bgp_evpn_route_type_is_bgp`) | `1f2cfb9` |
| X8 | The routing table doesn't list every BGP route, so a guard could fail on the recording lab | other (false fail) | Fixed by the baseline-guard rule: each guard is run on the lab first | `440f6be` |
| X9 | EOS `Idle(Admin)` was read as `idle(admin)`, so `state: idle` failed | other (false fail) | Fixed (`test_eos_admin_idle_reads_as_idle`) | `1f2cfb9` |
| X10 | A missing MED is read as 0 | **false-pass** | First rejected (BGP's default treats a missing MED as 0); reversed after the 2026-10-29 Grok review (G1 below): with `missing-as-worst` a missing MED is the worst, so `med: 0` passing on it is a false pass. Fixed | see G1 |
| X11 | The EOS `BGP Aggregate` route type wouldn't match `protocol: bgp` | other | Rejected: an aggregate is originated locally, not learned, and appears in no capture | — |
| X12 | FRR's local-pref probe errors on an IPv6-only box | other (false fail) | Backlog (0.4): it errors, never passes | — |

Open false-pass findings after Layer 6: none. X5 is fixed on FRR and, with X6, accepted as a documented limit with the mitigation stated and a fix scheduled for 0.4.

## Follow-up review (Grok, 2026-10-29): three items checked test-first before the freeze

| # | Item | Class | Decision | Tests |
|---|---|---|---|---|
| G1 | An omitted MED must be unknown, not 0 | **false-pass** | Fixed on FRR, EOS and SR Linux: their per-prefix output omits the MED field when the path has no MED attribute (seen in the EOS capture of a locally originated path), and the drivers read that as 0. Now `None`: any `med` check fails on it, `MED is not set`. Three older tests that pinned 0 updated | `test_a_missing_med_is_unknown_on_every_driver`, `test_med_zero_never_passes_on_a_path_without_med` (both failed before the fix) |
| G2 | Truncated or exit-0 error output must never become an empty RIB | **false-pass** (claimed) | Holds, now pinned: parsing is strict `json.loads` (a cut-off document, trailing text or error text raises), empty output raises, a non-zero exit or a timeout raises. Pinned for every route, path and session parser of every driver: each real capture cut at 17 points, and 8 exit-0 error texts | `test_cut_off_or_error_output_is_never_an_empty_answer` (13 parsers) |
| G3 | A covering or default route must never satisfy an exact-prefix check | **false-pass** (claimed) | Holds, now pinned: every driver compares the output's prefix with `==` (zebra's longest-match answer included). Pinned with each capture rewritten to `0.0.0.0/0`, a covering /16 and a more-specific /25 | `test_only_the_exact_prefix_counts_on_every_driver`, `test_a_route_check_fails_when_only_a_covering_route_exists` |

## Mutation follow-up after the cross-platform fixes

The driver fixes moved or added 37 surviving mutants in `frr._bgp_paths_raw` and `eos._summary`. One changed behaviour: `eos._summary_69` kept the *last* of two down sessions sharing a link-local key, where FRR and SR Linux keep the first. Killed by `test_eos_two_down_link_locals_keep_the_first_like_frr`. The other 36 are accepted with arguments in `accepted.json`: 27 change only an error message or the command label in one (a one-argument `unexpected` raises a TypeError, which the parser wrapper turns into the same DriverError), and 9 are equivalent (`maxsplit` when only field 0 is used; `established` written over `established`). Five acceptances that no longer survive were removed.

## Layer 6 delta review (fresh Opus agent, 2026-10-29): `git diff 35a2089..d9723aa -- src action.yml templates`

Every change since the cold review, read by a fresh agent with no context, focused on false passes, exit codes and security. It ran the parsers on the inputs it describes.

| # | Finding | Class | Decision | Tests |
|---|---|---|---|---|
| D1 | Two *up* sessions on one link-local key: the last one's count is kept, so `max: 100` passes while the other session accepts 5000 | **false-pass** | Fixed: a key that several sessions share is ambiguous (`BgpNeighbor.ambiguous`); a `bgp_session` or `bgp_prefixes` check on it is not evaluated (never a pass) and says to use a global address. One peer listed in several EOS per-family summaries is not ambiguous | `test_two_up_link_locals_on_one_key_never_pass_a_prefix_check`, `test_one_peer_in_several_eos_summaries_is_not_ambiguous` |
| D2 | One up, one down: keeping the down one (X4's fix) makes `state: down` pass while a session is up | **false-pass** | Fixed by D1 (FRR, SR Linux, EOS); the down state is still what the convergence gate reads | `test_one_up_one_down_on_one_key_never_pass_a_session_check` |
| D3 | `record`: a guard whose one sample errors (a vtysh timeout, a stale path) was dropped as "the baseline already fails it", without an `INCOMPLETE BASELINE` line | **false-pass** (recorded baselines) | Fixed: an erroring sample is retried (3 samples); a guard that never gets a real answer is left out with an `INCOMPLETE BASELINE` line; only a real failing sample means the lab fails it. An ambiguous neighbor is left out of the baseline the same way | `test_a_guard_sample_that_errors_is_retried_then_loud`, `test_an_ambiguous_neighbor_is_not_recorded_and_says_so` |
| D4 | SR Linux `bgp-vpn` and `bgp-label` routes still didn't match `protocol: bgp` | **false-pass** | Fixed: every `bgp*` route type is BGP | `test_srl_every_bgp_route_type_is_bgp` |
| D5 | `record --guards` was removed (scripts using it break) | other | Rejected: `--guards` never shipped (not in v0.3.2; added and replaced within 0.3.3) | — |

Areas checked with nothing found: the PR comment and MR note header (escaping, cut, status held to the exit code), the report-path removal loops (workspace and parents refused, symlinks unlinked), MED, FRR stale paths, `_tested`, run IDs and evidence files, exit codes, `run_id` in file names.

All four fixes were test-first: each test failed before its fix.

## Blocker from the 0.4 work (2026-10-29): FRR runs without a config line it rejected

Found by the 0.4 session on a live lab, in released 0.3.2: FRR skips a config line it rejects at boot (`default-orignate`), the lab runs without it, and the checks can pass on a change that never loaded. Class: **false-pass**. Coordination rule: a cheap fail-closed fix ships instead of a documented limit.

| Platform | Decision | Tests |
|---|---|---|
| FRR | Fixed: after the checks, every FRR node's boot log (`docker logs`) is read; any `line N: % Unknown command / Ambiguous command / Command incomplete / Warning / Failure to communicate` line, or a daemon's `Configuration file[...] processing failure`, makes the run `error` (exit 2), naming node, line and reason. An unreadable boot log is an error too. Fixtures are real `docker logs` of `quay.io/frrouting/frr:10.4.1` started privileged, with three bad lines (captured 2026-10-29); the running config confirmed none of the three loaded | `tests/test_frr_config_load.py` (all failed before the fix) |
| `setup:` commands (SONiC, FRR configured after boot) | Already fail-closed: `vtysh -c` exits 1 on each rejected form (verified on FRR 10.4.1: Unknown command, Command incomplete, "Specify remote-as"), and a setup command that never succeeds stops the run. Pinned | `test_a_setup_command_vtysh_rejects_stops_the_run` |
| Arista cEOS, SR Linux, SONiC startup config | **Accepted documented limit**, fix scheduled for 0.4 (the 0.4 session builds apply verification): stated in the config reference, the compatibility matrix, the Trust page and both advisories, with the mitigation (a positive check for what each changed line creates) | — |

Advisory: `advisories/0.3.2-rejected-config/README.md`. `runner.rejected_config` is added to the verdict-deciding functions for mutation review.

## The two games (Layer 6, before the freeze)

- **Expert gauntlet:** `research/expert-gauntlet-20261029.md` (HQ), played against this release's scope (Cisco, Juniper, a Batfish-style researcher, Forward/IP Fabric, NVIDIA, NTT Data/CDW, Starlink/Google Fiber, AWS/OpenAI/Anthropic). Its false-pass finding, a config line FRR rejected at boot, is the blocker above, fixed in this release.
- **War game delta:** `research/games/0.3.3-wargame.md` (HQ), Grok and ChatGPT, two new personas: a bank's network team with a change advisory board, and an AI-agent startup building a network copilot. No false-pass finding. Both models: serve the startup first. Both name the question 0.3.3 answers only on FRR ("did every node load the config?"); proposed for 0.4, not this release (it would change the frozen result contract during the freeze): a per-node "config load verified" field in the agent result and the PR header, and the rejected-config check on SR Linux, cEOS and SONiC as 0.4's first slice.

## Delta review, round 2 (fresh Opus agent, 2026-10-29): `git diff d9723aa..78d7649 -- src scripts/release_gate.py`

| # | Finding | Class | Decision | Tests |
|---|---|---|---|---|
| R1 | An FRR node in an image not named "frr" (no driver detected) was skipped by the boot-log check | **false-pass** | Fixed: a node whose driver can't be detected is read too; FRR's own error lines count there (a plain host prints none) | `test_a_node_whose_driver_is_unknown_is_read_too`, `test_a_plain_host_with_an_unknown_driver_is_not_an_error`, `test_a_bridge_has_no_boot_log_to_read` |
| R2 | A daemon reading its own file (bgpd.conf, no integrated frr.conf) reports a rejected line as `... on config line N: ...`, which wasn't read; and a log with no config load at all passed | **false-pass** | Fixed: the daemon form is read; an FRR node whose log shows no sign of a config load is an error ("whether its config loaded is unknown") | `test_a_daemon_that_reads_its_own_config_file_reports_rejected_lines_too`, `test_an_frr_log_with_no_sign_of_a_config_load_is_an_error` |
| R3 | `bgp_route next_hop: fe80::1`: the zone is stripped, so a path through another session sharing the link-local matched | **false-pass** | Fixed: a link-local `next_hop` is refused before deploying (the scoped form could never match anyway) | `test_a_link_local_next_hop_is_refused` |
| R4 | A line rejected before a restart, and fixed since, still made every later `check` an error | other | Fixed: only the log since the container's current start is read (`docker inspect` StartedAt, `docker logs --since`) | `test_the_boot_log_is_read_since_the_container_last_started` |
| R5 | No cap on the log; a non-UTF-8 byte made an internal error | other | Fixed by R4 (current boot only), lenient decoding, a 120 s timeout | same test |
| R6 | A host that can't read container logs (log driver `none`) always errors | other | Accepted: fail-closed, and the message carries Docker's reason | — |

Every fix was test-first. Checked live on 2026-10-29 with real FRR 10.4.1 containers (`Lab.boot_log` itself): the three rejected lines are found, a clean boot gives none, and after `docker restart` the config load is still seen.

## Mutation follow-up after the delta fixes (run on `4a4fbf0`, 2026-10-29)

The run left 129 survivors that `accepted.json` didn't accept. 63 were acceptances made before and only renumbered: the new link-local check in `config._validate_check` and the new code in `runner.run` and `eos._summary` moved mutmut's numbering. Each was matched to its old entry by diff body, and only an exact match moved (the fingerprint includes the mutant's ID, so it always changes on a renumber). The other 66 were new.

- **Three could hide a rejected config (false pass), now killed.** In `runner.rejected_config`, `continue` became `break` after a bridge, a non-FRR node or an unreadable non-FRR log, so an FRR node listed after one of them was never read. `test_a_bridge_a_ceos_node_or_an_unreadable_host_before_an_frr_node_never_ends_the_scan` kills all three, and the `ovs-bridge` spelling with them.
- **Killed:** a driver set in the file being ignored (`test_a_driver_set_in_the_file_decides_that_a_node_is_frr`).
- **Killed by exact-text tests:** every message mutant in `rejected_config`, `_ambiguous` and the `next_hop` refusal; the neighbor and node arguments in `_bgp_session` and `_bgp_prefixes`; the ambiguity lists in `eos._summary` and `frr._keep_down`; and a `break` and a lost line key in `parse_config_load_errors` (two daemon lines, out of order).
- **Accepted (19), each with its reason in `accepted.json`:**
  - equivalent: the `next_hop` split, since the address is already parsed with its scope; the FRR `Warning` replace, since the reason never holds that word; `maxsplit`; and `established` written over itself;
  - message or logging text in `runner.run`: the signal name and two log lines;
  - the command label in an `as_int` message.
- **Removed:** acceptances whose mutant no longer survives, under any number.

The rerun on `4ce4caa` left one survivor that wasn't accepted: `config._describe_47` (`'counted'` written as `'COUNTED'` in a default check name). The first run reported it caught, so its old acceptance had been removed with the others that no longer survived. That kill was not stable. The old entry pins this same diff, and it is back in `accepted.json` (message-text).

## Live gate on `ada4dd0` (2026-10-29): two corpus verdicts changed

Static, unit and mutation passed. Live failed on 4 corpus verdicts, both cases looked at again under the lab lock (`docker ps -a` empty before and after).

| # | Finding | Class | Decision | Commit |
|---|---|---|---|---|
| L1 | v1 case 29 (`bgp graceful-restart` appended to pe1): every strategy went from `safe` to `error`. The boot log has `line 64: Failure to communicate[13] to bgpd` and `processing failure: 13`, but pe1's running config has `bgp graceful-restart`: bgpd applied the line and returned CMD_WARNING_CONFIG_FAILED. A false error from the rejected-config check | other (false error) | Fixed: a reported line counts only if the node's `show running-config` doesn't have it; a running config that can't be read, or a processing-failure count with no line, still makes the run an error (`test_a_line_the_daemon_complained_about_but_applied_is_not_rejected`, `test_a_line_missing_from_the_running_config_is_still_rejected`, `test_an_applied_line_passes_the_run`, `test_an_unreadable_running_config_keeps_the_error`). New documented limit: a rejected line that is word for word another applied line is not reported; fix scheduled: 0.4 | this commit |
| L2 | v2 case 18 (aggregate discard route removed): `netdryrun` went from `unsafe` to `safe` | other (lab nondeterminism) | Not a code change: three identical reruns gave unsafe, unsafe, safe. FRR's import check sometimes withholds 192.0.2.0/24 ("inaccessible, import-check enabled") and sometimes announces it, so this case's verdict follows the lab. The v2 text that credits the 0.3.1 flip to a code change is wrong; the public wording and the gate rule for this case are the coordinator's decision | — |


## Delta review, round 3 (fresh Opus agent, 2026-10-29): `git diff ada4dd0..142dcf6 -- src tests`

The first fix for L1 compared each reported line's text with any line of the running config. The review found false passes in it, and the fix was redone before any of it was released:

| # | Finding | Class | Decision |
|---|---|---|---|
| R3-1 | The match ignored the section: a line rejected under `router bgp 65000 vrf RED` was dropped because the default VRF had the same line | **false-pass** | Fixed: the line is compared within its section (`router bgp ...`, address family), read from line N of the node's `frr.conf`; if line N isn't that line, it counts (`test_the_same_line_applied_in_another_section_does_not_count`, `test_a_line_that_is_not_the_files_line_n_counts`, `test_the_sections_of_a_config`) |
| R3-2 | Per-daemon line numbers shared one key: bgpd.conf line 5 hid ospfd.conf line 5, so a dropped first line hid a rejected second one | **false-pass** | Fixed: lines are keyed by line and source, and a line from a daemon's own file is never dropped (`test_two_daemon_files_with_the_same_line_number_are_both_kept`) |
| R3-3 | Once every line was dropped, a processing failure from another daemon was swallowed | **false-pass** | Fixed: only the failures of daemons whose own lines were dropped are explained away (`test_another_daemons_processing_failure_still_counts`) |
| R3-4 | Every kind of rejection could be dropped, though a line vtysh couldn't parse never reaches a daemon | **false-pass** | Fixed: only a "Failure to communicate" line can be dropped (`test_a_line_vtysh_could_not_parse_counts_even_if_the_text_is_applied`) |
| R3-5 | A line for mgmtd can be in the stored config yet fail in the daemon behind it | other | Fixed, fail closed: lines for mgmtd always count (`test_a_line_for_mgmtd_counts_even_if_the_running_config_has_it`); documented limit for warned-but-applied lines, fix scheduled: 0.4 |
| R3-6 | When the running config can't be read, the error still said the lines were rejected | other | Fixed: it adds "(not checked against the running config: ...)" (`test_an_unreadable_running_config_or_file_keeps_the_error_and_says_why`) |

## Corpus v2 case 18 and the harmful-approval line (coordinator decision, 2026-10-29)

- **L2 decision (a).** Case 18 is listed in `corpus/v2/NONDETERMINISTIC.yml` with every verdict seen and left out of every score. v2 is now 16 of 17 deterministic cases, changed everywhere through `sync_facts` (README, site, how-it's-built, llms). The wrong sentences in `corpus/v2/AMENDMENTS.md` are kept, struck through, with the correction. `corpus/run.py` runs the case 3 times. The gate records the verdicts as an INFO line and never blocks on them; a verdict change on any other case still blocks. The case file and its expected verdict are not edited. A replacement without the race goes into a later corpus version.
- **G4, found while doing this.** `harmful_approved` compared `expected` with `"harmful"`, a word no corpus case uses (`unsafe`), so the gate's "no harmful change approved" line could never fail. Its tests used the same made-up word. The line came in on 2026-10-28 and was never in a released gate. Fixed and pinned on the committed results (`test_the_published_known_misses_are_found_in_the_real_results`).

## Delta review, round 4 (fresh Opus agent, 2026-10-30): `git diff 142dcf6..2d63399`

| # | Finding | Class | Decision |
|---|---|---|---|
| R4-1 | `show running-config` merges every daemon: a route-map line zebra took and bgpd refused was cleared | **false-pass** | Fixed: each daemon that answered "Failure to communicate" has its own running config read (`vtysh -d <daemon>`); a daemon not read keeps its lines (`test_a_line_another_daemon_took_does_not_clear_the_one_that_refused_it`, `test_only_the_daemons_that_answered_failure_to_communicate_are_read`) |
| R4-2 | Sections stop at the address family: a line refused in `vni 200` was cleared by the same line in `vni 100` | **false-pass** | Fixed: the daemon's running config must have the line in that section at least as many times as `frr.conf` does (`test_two_blocks_in_one_section_need_the_line_in_both`) |
| R4-3 | `frr.conf` may have been rewritten after boot (`write memory` in a lab hook) | other | Documented limit; the line-N check still applies; fix scheduled: 0.4 (the file's change time against the boot) |
| R4-4 | The case-18 exemption had no limits: an error on the case, a missing case, or a case added to the yml went unnoticed | other (gate) | Fixed: a BLOCKER holds the exemption. The list is pinned in the gate (`NONDETERMINISTIC_PINNED`), the repeats must have run, and any run that ends in error blocks (`test_the_nondeterministic_exemption_holds_only_as_pinned`). The distribution itself stays INFO, as decided. A change that makes Netdryrun always approve case 18 shows only there, in the recorded verdicts |
| R4-5 | `--keep` kept run 1's lab, and run 2 deployed over it | other | Fixed: only the last run keeps its lab (`test_keep_reaches_only_the_last_run_of_a_nondeterministic_case`) |
| minor | `run.py`'s own RESULTS.md marked case 18; a yml key naming no case changed the v2 count | other | Fixed |

## Delta review, round 5 (fresh Opus agent, 2026-10-30): `git diff 2d63399..02ee953`

| # | Finding | Class | Decision |
|---|---|---|---|
| R5-1 | Sections stopped at the address family, so a line FRR prints in a sibling block cleared a refused one: `route-target both` in `vni 20` prints as `route-target import`, matching the line refused in `vni 10` | **false-pass** | Fixed: a section is every header above the line, from indentation, at any depth. A file indented differently from FRR's output never matches, which gives a false error, never a false pass (`test_every_depth_is_a_section`, `test_a_line_another_block_prints_the_same_does_not_clear_it`, `test_a_flat_file_never_matches_an_indented_running_config`) |
| R5-2 | A change that made Netdryrun approve case 18 in every run passes the gate silently | other (gate) | Shown, not blocking, as decided (it happens by chance, about 1 run in 8 from the history): the INFO line fails and names the case (`test_a_harmful_nondeterministic_case_approved_in_every_run_is_shown`). The deterministic replacement case is the real fix, in a later corpus version |
| — | Static on `02ee953`: ruff B905 (`zip` without `strict=`) in a new test | other | Fixed |

The reviewer checked clean:
- per-daemon reads: one unreadable daemon keeps only its own lines;
- partial or empty output fails closed;
- duplicate lines;
- mgmtd;
- the gate's exemption BLOCKER wiring, including v1 with an empty pin;
- `--keep`.

## Delta review, round 6 (fresh Opus agent, 2026-10-30): `git diff 02ee953..fdc5754`

| # | Finding | Class | Decision |
|---|---|---|---|
| R6-1 | vtysh places a line by the commands before it, not by its indentation. A misindented refused line therefore shares a section with an applied one; FRR printed the applied line's `route-target both` as `route-target import`, which matched the refused line | **false-pass** | Fixed: a second, independent condition. The line's whole left-margin block in `frr.conf` must be in that daemon's running config, line by line and in order, inside a block with the same first line. Any line FRR rewrote, dropped or moved breaks the match (`test_a_misindented_refused_line_does_not_borrow_another_lines_section`, `test_the_block_must_be_in_the_running_config_as_written`) |
| R6-2 | A refused header (`vni 10`) could be cleared because its block shows in the running config, while the lines under it went elsewhere | **false-pass** (probable) | Fixed: a line with deeper lines under it in the file always counts (`test_a_refused_header_counts_even_if_its_block_shows`) |
| R6-3 | Comment and `exit` lines became headers | other (false error) | Fixed (`test_a_line_under_a_comment_keeps_its_real_section`) |
| R6-4 | The every-run-approved flag read `expected` only from the published row, missing a case new in the release | other (gate) | Fixed |

What clearing a refused line now takes, all at once:
- the "Failure to communicate" kind, from a daemon other than mgmtd;
- that daemon's own running config was read;
- line N of `frr.conf` is the line;
- the line has no lines under it;
- that daemon's running config has it under the same headers at least as often as the file does;
- its whole block is there as written.

Anything else keeps the run an error.

## Delta review, round 7 (fresh Opus agent, 2026-10-30): `git diff fdc5754..cd7831d`

| # | Finding | Class | Decision |
|---|---|---|---|
| R7-1 | vtysh numbers `frr.conf` by `
` only (fgets), while `str.splitlines()` also splits on ``, ``, U+2028 and a lone `
`. One such character in a comment moved line N onto an applied line in another block, and the reviewer cleared a refused line that way | **false-pass** | Fixed: the file and the running config are cut only at `
`, as vtysh does (`test_line_n_is_counted_the_way_vtysh_counts_it`, four separators) |
| R7-2 | A command starting with "end" was treated as a block end | other | Fixed: only `!`, `exit`, `end` and `exit-...` close a block (`test_a_command_that_starts_like_end_is_still_a_header`) |

Checked clean: duplicate lines in a block, lines FRR prints by default, the same first line twice in the running config, index edges, CRLF, comments and `exit` after the line.

## Delta review, round 8 (fresh Opus agent, 2026-10-30): `git diff cd7831d..eb9b8b0`

The reviewer checked line numbering against vtysh's fgets loop on an empty file, a file with no final newline, `
` endings and a trailing blank line. It found no way to clear a refused line through this diff. One contrived residue: vtysh reads into a 4096-byte buffer, so a longer line would count as several lines and shift N. Closed: if any line of `frr.conf` is that long, nothing is cleared (`test_a_line_longer_than_vtysh_reads_at_once_clears_nothing`).

## Mutation follow-up on f8bbb0a (2026-10-30)

46 new survivors, all in the running-config match (41 in `drivers/frr.py`, 5 in `runner.rejected_config`). 32 old acceptances no longer survive and were dropped. 44 survivors are killed by new tests in `tests/test_frr_config_load.py`: the 4094/4095-byte limit, line 1 and a line past the file, CRLF, blank and comment lines, tab and space indentation at both ends of a block, closing lines, line order on a shared line number, daemon names that differ only in case folding, no running-config read without a "Failure to communicate", and the exact "unreadable" message. Each mutant was applied by hand and the tests were run against it.

A fresh Opus agent reviewed the 5 that the first round of tests missed. Three could differ (message order, a dropped line for non-ASCII daemon names, an extra "not checked" note), though none could change a run's status. All three are now killed. The other two (`parse_config_load_errors` `_mutmut_67` and `_mutmut_79`) are accepted as equivalent: the daemon they change is read only when every line was cleared, and those lines never are.
