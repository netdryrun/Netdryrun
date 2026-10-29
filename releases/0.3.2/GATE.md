# Release gate: Netdryrun 0.3.2

Written by `scripts/release_gate.py` (see [RELEASING.md](../../RELEASING.md)). Do not edit by hand: rerun a layer, or record a decision in `accepted.json` or `review.md`.

**CLEARED**: every layer ran on the same clean commit; no BLOCKER failed or was skipped; every MAJOR passed or was accepted.

| Layer | Commit | Ran | Time | Result |
|---|---|---|---|---|
| [Layer 1: static](#layer-1-static) | `e3f5163ea9` | 2026-10-28 10:36:27 UTC | 1.2 s | 13 PASS |
| [Layer 2: unit tests on every supported Python](#layer-2-unit-tests-on-every-supported-python) | `e3f5163ea9` | 2026-10-28 10:36:29 UTC | 3.3 min | 7 PASS |
| [Layer 4: mutation testing](#layer-4-mutation-testing) | `e3f5163ea9` | 2026-10-28 10:39:59 UTC | 20.8 min | 4 PASS |
| [Layer 5: live matrix on the built package](#layer-5-live-matrix-on-the-built-package) | `e3f5163ea9` | 2026-10-28 11:03:28 UTC | 144.7 min | 2 ACCEPTED, 46 PASS |
| [Layer 7: after-publish proof](#layer-7-after-publish-proof) | `e3f5163ea9` | 2026-10-28 13:57:54 UTC | 2.8 min | 1 ACCEPTED, 13 PASS |

## Layer 1: static

Commit `e3f5163ea97e3f90172df6937a1b35bfbb7d341c` on `ndr/agent-contract`; 2026-10-28 10:36:27 UTC; 1.2 s; Linux 6.18.54.1-microsoft-standard-WSL2 (x86_64); Python 3.10.12; --strict.

Tools: actionlint 1.7.7; ruff 0.17.3; shellcheck 0.8.0.

| Check | Severity | Result | Time | Notes |
|---|---|---|---|---|
| ruff (config in pyproject.toml) | BLOCKER | **PASS** | 0.0 s | All checks passed! |
| actionlint on every workflow (with shellcheck) | BLOCKER | **PASS** | 0.1 s | clean |
| shellcheck, error level, 18 scripts | BLOCKER | **PASS** | 0.1 s | clean |
| shellcheck, warning level, 18 scripts | MAJOR | **PASS** | 0.1 s | clean |
| no empty ${{ }} in action.yml or workflows | BLOCKER | **PASS** | 0.0 s | none |
| public facts match the source (sync_facts.py --check) | BLOCKER | **PASS** | 0.1 s | facts: in sync (version 0.3.2, 0 problem(s)) |
| every version reference says 0.3.2 | BLOCKER | **PASS** | 0.0 s | 36 references agree |
| pyproject.toml declares Python 3.10 to 3.14, the versions tested | MAJOR | **PASS** | 0.0 s | requires-python and classifiers agree |
| every example has a documented expected result and exit code | MAJOR | **PASS** | 0.0 s | 8 examples |
| every topology we ship is named ndr-* | BLOCKER | **PASS** | 0.0 s | 80 topologies |
| CHANGELOG has no Unreleased entries left (all under 0.3.2) | BLOCKER | **PASS** | 0.0 s | cut |
| tag v0.3.2 does not exist yet | BLOCKER | **PASS** | 0.0 s | unused |
| PyPI has no netdryrun 0.3.2 yet | BLOCKER | **PASS** | 0.0 s | HTTP 404 |

## Layer 2: unit tests on every supported Python

Commit `e3f5163ea97e3f90172df6937a1b35bfbb7d341c` on `ndr/agent-contract`; 2026-10-28 10:36:29 UTC; 3.3 min; Linux 6.18.54.1-microsoft-standard-WSL2 (x86_64); Python 3.10.12; --strict.

Tools: docker 29.9.2; uv 0.13.6 (x86_64-unknown-linux-gnu).

| Check | Severity | Result | Time | Notes |
|---|---|---|---|---|
| unit tests on Python 3.10.12 | BLOCKER | **PASS** | 35.0 s | 2131 passed, 39 skipped, 1 xfailed |
| unit tests on Python 3.11.18 | BLOCKER | **PASS** | 26.5 s | 2131 passed, 39 skipped, 1 xfailed |
| unit tests on Python 3.12.16 (with coverage) | BLOCKER | **PASS** | 43.9 s | 2131 passed, 39 skipped, 1 xfailed |
| coverage of the verdict modules at or above the floors | MAJOR | **PASS** | 0.0 s | all at or above their floors |
| unit tests on Python 3.13.18 | BLOCKER | **PASS** | 24.9 s | 2131 passed, 39 skipped, 1 xfailed |
| unit tests on Python 3.14.10 | BLOCKER | **PASS** | 24.2 s | 2131 passed, 39 skipped, 1 xfailed |
| unit tests in a plain python:3.12-slim container (no containerlab, no Docker) | BLOCKER | **PASS** | 43.8 s | 2131 passed, 39 skipped, 1 xfailed |

**Coverage of the verdict modules** (lines and branches, Python 3.12):

| Module | Lines | Branches | Covered | Floor |
|---|---|---|---|---|
| `src/netdryrun/checks.py` | 286/287 | 121/122 | 99.5% | 99% |
| `src/netdryrun/config.py` | 444/447 | 261/264 | 99.2% | 99% |
| `src/netdryrun/runner.py` | 528/535 | 209/214 | 98.4% | 98% |
| `src/netdryrun/drivers/` | 687/687 | 240/240 | 100.0% | 99% |

## Layer 4: mutation testing

Commit `e3f5163ea97e3f90172df6937a1b35bfbb7d341c` on `ndr/agent-contract`; 2026-10-28 10:39:59 UTC; 20.8 min; Linux 6.18.54.1-microsoft-standard-WSL2 (x86_64); Python 3.10.12; --strict.

Tools: mutmut python -m mutmut, version 3.8.0.

| Check | Severity | Result | Time | Notes |
|---|---|---|---|---|
| no surviving mutants in src/netdryrun/checks.py | BLOCKER | **PASS** | 20.0 min | 1112/1201 mutants caught (92.6%); not caught: 89 survived the tests, 0 in code no test runs, 89 accepted |
| no surviving mutants in src/netdryrun/config.py | BLOCKER | **PASS** | 0.0 s | 1215/1461 mutants caught (83.2%); not caught: 246 survived the tests, 0 in code no test runs, 246 accepted |
| no surviving mutants in src/netdryrun/runner.py | BLOCKER | **PASS** | 0.0 s | 1091/1278 mutants caught (85.4%); not caught: 187 survived the tests, 0 in code no test runs, 187 accepted |
| no surviving mutants in src/netdryrun/drivers/ | BLOCKER | **PASS** | 0.0 s | 1430/1626 mutants caught (87.9%); not caught: 196 survived the tests, 0 in code no test runs, 196 accepted |

**Accepted entries that no longer survive** (109; remove them from accepted.json): `netdryrun.checks.x_inconclusive_reason__mutmut_35`, `netdryrun.checks.x_inconclusive_reason__mutmut_37`, `netdryrun.config.x__validate_check__mutmut_106`, `netdryrun.config.x__validate_check__mutmut_150`, `netdryrun.config.x__validate_check__mutmut_178`, `netdryrun.config.x__validate_check__mutmut_199`, `netdryrun.config.x__validate_check__mutmut_229`, `netdryrun.config.x__validate_check__mutmut_236`, `netdryrun.config.x__validate_check__mutmut_237`, `netdryrun.config.x__validate_check__mutmut_280`, `netdryrun.config.x__validate_check__mutmut_305`, `netdryrun.config.x__validate_check__mutmut_306`, `netdryrun.config.x__validate_check__mutmut_307`, `netdryrun.config.x__validate_check__mutmut_308`, `netdryrun.config.x__validate_check__mutmut_309`, `netdryrun.config.x__validate_check__mutmut_311`, `netdryrun.config.x__validate_check__mutmut_312`, `netdryrun.config.x__validate_check__mutmut_313`, `netdryrun.config.x__validate_check__mutmut_314`, `netdryrun.config.x__validate_check__mutmut_315`, `netdryrun.config.x__validate_check__mutmut_316`, `netdryrun.config.x__validate_check__mutmut_317`, `netdryrun.config.x__validate_check__mutmut_326`, `netdryrun.config.x__validate_check__mutmut_345`, `netdryrun.config.x__validate_check__mutmut_346`, `netdryrun.config.x__validate_check__mutmut_358`, `netdryrun.config.x__validate_check__mutmut_368`, `netdryrun.config.x__validate_check__mutmut_372`, `netdryrun.config.x__validate_check__mutmut_373`, `netdryrun.config.x__validate_check__mutmut_374`, `netdryrun.config.x__validate_check__mutmut_375`, `netdryrun.config.x__validate_check__mutmut_407`, `netdryrun.config.x__validate_check__mutmut_408`, `netdryrun.config.x__validate_check__mutmut_434`, `netdryrun.config.x__validate_check__mutmut_441`, `netdryrun.config.x__validate_check__mutmut_457`, `netdryrun.config.x__validate_check__mutmut_493`, `netdryrun.config.x__validate_check__mutmut_494`, `netdryrun.config.x__validate_check__mutmut_495`, `netdryrun.config.x__validate_check__mutmut_496` ...

**Surviving mutants by function** (718 in all; every diff is in [mutants.md](mutants.md)):

| Function | Survivors |
|---|---|
| `config._describe` | 91 |
| `runner._bgp_convergence_gate` | 73 |
| `config._validate_check` | 48 |
| `runner.run` | 37 |
| `config._validate_scenario` | 30 |
| `checks._ping` | 23 |
| `drivers.eos._summary` | 21 |
| `checks._route` | 20 |
| `drivers.frr._route_table` | 18 |
| `config.load` | 17 |
| `config.load_yaml` | 15 |
| `drivers.eos._bgp_entries` | 15 |
| `runner._yaml_problem` | 15 |
| `config._StrictLoader.construct_mapping` | 13 |
| `drivers.eos._vrf` | 12 |
| `drivers.frr._bgp_paths_raw` | 12 |
| `runner._wait_fault_visible` | 12 |
| `runner.run_scenario` | 12 |
| `checks._describe_path` | 11 |
| `config._validate_bgp_route` | 11 |
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
| `checks._opt` | 3 |
| `checks.run_round_robin` | 3 |
| `config.Fault.describe` | 3 |
| `config.normalize_as_path` | 3 |
| `drivers.base.Driver.all_routes` | 3 |
| `drivers.check_supported` | 3 |
| `drivers.for_node` | 3 |
| `checks._not_configured` | 2 |
| `checks._reach_view` | 2 |
| `checks.inconclusive_reason` | 2 |
| `config._validate_nodes` | 2 |
| `drivers.base.Driver.bgp_neighbors` | 2 |
| `drivers.base.Driver.bgp_paths` | 2 |
| `drivers.base.Driver.ping` | 2 |
| `drivers.base.Driver.routes` | 2 |
| `drivers.base.check_vrf_name` | 2 |
| `drivers.frr._bgp_paths_for_route_check` | 2 |
| `drivers.srlinux.parse_instance_state` | 2 |
| `checks._bgp_prefixes` | 1 |
| `checks._bgp_session` | 1 |
| `checks._evaluate` | 1 |
| `checks.converge_then_hold` | 1 |
| `config.parse_community` | 1 |
| `drivers.eos.EosDriver.all_routes` | 1 |
| `drivers.frr.FrrDriver.all_routes` | 1 |
| `drivers.srlinux.SrlDriver.all_routes` | 1 |
| `drivers.srlinux._bgp_learned` | 1 |
| `runner._sessions_over_links` | 1 |

## Layer 5: live matrix on the built package

Commit `e3f5163ea97e3f90172df6937a1b35bfbb7d341c` on `ndr/agent-contract`; 2026-10-28 11:03:28 UTC; 144.7 min; Linux 6.18.54.1-microsoft-standard-WSL2 (x86_64); Python 3.10.12; --strict.

Tools: containerlab ⣴⡾⠛⠛⠖ ⢠⣶⠟⠛⢷⣦ ⢸⣿⣧ ⣿ ⠘⠛⢻⡟⠛⠛ ⣾⣿⡀ ⣿⡇ ⣿⣿⡄ ⢸⡇ ⣿⡟⠛⠛⠃⢸⣿⠛⠛⣷⡄ [38;2;0;201;255m⣿⡇[0m ; docker 29.9.2.

| Check | Severity | Result | Time | Notes |
|---|---|---|---|---|
| build the wheel | BLOCKER | **PASS** | 0.7 s | netdryrun-0.3.2-py3-none-any.whl |
| install netdryrun-0.3.2-py3-none-any.whl in a fresh venv | BLOCKER | **PASS** | 0.6 s |  |
| runs the installed package, not the source tree | BLOCKER | **PASS** | 0.0 s | /tmp/ndr-gate-live-hrln_m17/venv/lib/python3.12/site-packages/netdryrun/__init__.py |
| netdryrun --version says 0.3.2 | BLOCKER | **PASS** | 0.0 s | netdryrun 0.3.2 |
| example agent-demo: `Demo OK`, exit 0 | BLOCKER | **PASS** | 70.6 s | exit 0: Demo OK: attempt 1 rejected by 5 leak guards with every other check passing; attempt 2 passed every check. |
| example agent-demo: no lab left running | BLOCKER | **PASS** | 0.0 s | none left |
| example arista-frr: `PASSED: 10 passed, 0 failed`, exit 0 | BLOCKER | **PASS** | 1.7 min | exit 0: PASSED: 10 passed, 0 failed (10 checks) |
| example arista-frr: no lab left running | BLOCKER | **PASS** | 0.0 s | none left |
| example batfish-pipeline: `PASSED: 10 passed, 0 failed`, exit 0 | BLOCKER | **PASS** | 1.7 min | exit 0: PASSED: 10 passed, 0 failed (10 checks) |
| example batfish-pipeline: no lab left running | BLOCKER | **PASS** | 0.0 s | none left |
| example frr-bgp: `PASSED: 11 passed, 0 failed`, exit 0 | BLOCKER | **PASS** | 1.7 min | exit 0: PASSED: 11 passed, 0 failed (11 checks) |
| example frr-bgp: no lab left running | BLOCKER | **PASS** | 0.0 s | none left |
| example frr-bgp-broken: `FAILED: 5 passed, 1 failed`, exit 1 | BLOCKER | **PASS** | 39.3 s | exit 1: FAILED: 5 passed, 1 failed (6 checks) |
| example frr-bgp-broken: no lab left running | BLOCKER | **PASS** | 0.0 s | none left |
| example sonic-frr: `PASSED: 8 passed, 0 failed`, exit 0 | BLOCKER | **PASS** | 1.6 min | exit 0: PASSED: 8 passed, 0 failed (8 checks) |
| example sonic-frr: no lab left running | BLOCKER | **PASS** | 0.0 s | none left |
| example srl-frr: `PASSED: 7 passed, 0 failed`, exit 0 | BLOCKER | **PASS** | 78.7 s | exit 0: PASSED: 7 passed, 0 failed (7 checks) |
| example srl-frr: no lab left running | BLOCKER | **PASS** | 0.0 s | none left |
| example srl-hidden-leak: `PASSED: 9 passed, 0 failed`, exit 0 | BLOCKER | **PASS** | 82.0 s | exit 0: PASSED: 9 passed, 0 failed (9 checks) |
| example srl-hidden-leak: no lab left running | BLOCKER | **PASS** | 0.0 s | none left |
| example srl-hidden-leak with leaks/frr1.conf: `FAILED: 8 passed, 1 failed`, exit 1 | BLOCKER | **PASS** | 82.9 s | exit 1: FAILED: 8 passed, 1 failed (9 checks) |
| example srl-hidden-leak with leaks/frr1.conf: no lab left running | BLOCKER | **PASS** | 0.0 s | none left |
| example srl-hidden-leak with leaks/srl1.cli: `FAILED: 8 passed, 1 failed`, exit 1 | BLOCKER | **PASS** | 85.3 s | exit 1: FAILED: 8 passed, 1 failed (9 checks) |
| example srl-hidden-leak with leaks/srl1.cli: no lab left running | BLOCKER | **PASS** | 0.0 s | none left |
| example times match the docs (within 2x) | MAJOR | **PASS** | 0.0 s | all within 2x |
| Verdict Corpus v1: every verdict matches the committed results.json | BLOCKER | **PASS** | 64.1 min | all verdicts match |
| Verdict Corpus v1: no lab left running | BLOCKER | **PASS** | 0.0 s | none left |
| Verdict Corpus v2: every verdict matches the committed results.json | BLOCKER | **PASS** | 60.2 min | all verdicts match |
| Verdict Corpus v2: no lab left running | BLOCKER | **PASS** | 0.0 s | none left |
| MCP handshake against the installed wheel | BLOCKER | **PASS** | 1.2 s | MCP handshake OK |
| check pack verification | MAJOR | **ACCEPTED** | 0.0 s | no --pack script given (accepted: No check pack is sold yet: pack verification is paused by the roadmap until the 45-day demand test; it runs with --pack before any pack ships.) |
| 20-node scale test | MAJOR | **ACCEPTED** | 0.0 s | not scripted in the repository yet: run it by hand (accepted: Not scripted yet. A 20-node lab was run by hand in pre-launch testing (it found the PR-comment size limit, fixed in 0.3.1); scripting it is a 0.4.1 item.) |
| SIGINT during deploy: exit 130, a clear message | BLOCKER | **PASS** | 4.7 s | exit 130 |
| SIGINT during deploy: no lab left running | BLOCKER | **PASS** | 0.0 s | none left |
| SIGINT during checks: exit 130, a clear message | BLOCKER | **PASS** | 17.3 s | exit 130 |
| SIGINT during checks: no lab left running | BLOCKER | **PASS** | 0.0 s | none left |
| SIGTERM during deploy: exit 143, a clear message | BLOCKER | **PASS** | 5.9 s | exit 143 |
| SIGTERM during deploy: no lab left running | BLOCKER | **PASS** | 0.0 s | none left |
| SIGTERM during checks: exit 143, a clear message | BLOCKER | **PASS** | 17.8 s | exit 143 |
| SIGTERM during checks: no lab left running | BLOCKER | **PASS** | 0.0 s | none left |
| a node's image does not exist: exit 2 with a clear error | BLOCKER | **PASS** | 1.1 s | exit 2:   wrote json report: /tmp/ndr-gate-live-hrln_m17/reports/frr-bgp-missing-image.json |
| a node's image does not exist: no lab left running | BLOCKER | **PASS** | 0.0 s | none left |
| a node cannot be created (a bind source does not exist): exit 2 with a clear error | BLOCKER | **PASS** | 0.3 s | exit 2:   wrote json report: /tmp/ndr-gate-live-hrln_m17/reports/frr-bgp-deploy-fails.json |
| a node cannot be created (a bind source does not exist): no lab left running | BLOCKER | **PASS** | 0.0 s | none left |
| two runs of the same lab at once: no false verdict, no crash | BLOCKER | **PASS** | 1.7 min | exit codes 2 and 0 |
| two runs at once: no lab left running | BLOCKER | **PASS** | 0.0 s | none left |
| Docker restarts mid-run: never passed, a clear message | BLOCKER | **PASS** | 3.9 min | exit 2 |
| Docker restart: no lab left running | BLOCKER | **PASS** | 0.0 s | none left |

## Layer 7: after-publish proof

Commit `e3f5163ea97e3f90172df6937a1b35bfbb7d341c` on `ndr/agent-contract`; 2026-10-28 13:57:54 UTC; 2.8 min; Linux 6.18.54.1-microsoft-standard-WSL2 (x86_64); Python 3.10.12.

Tools: uv 0.13.6 (x86_64-unknown-linux-gnu).

| Check | Severity | Result | Time | Notes |
|---|---|---|---|---|
| PyPI serves netdryrun 0.3.2 | BLOCKER | **PASS** | 0.0 s | HTTP 200 |
| pip install netdryrun==0.3.2 on Python 3.10: --version, validate, MCP handshake | BLOCKER | **PASS** | 12.0 s | MCP handshake OK |
| uvx netdryrun@0.3.2 on Python 3.10: --version, MCP handshake | BLOCKER | **PASS** | 4.1 s | MCP handshake OK |
| pip install netdryrun==0.3.2 on Python 3.11: --version, validate, MCP handshake | BLOCKER | **PASS** | 10.0 s | MCP handshake OK |
| uvx netdryrun@0.3.2 on Python 3.11: --version, MCP handshake | BLOCKER | **PASS** | 3.1 s | MCP handshake OK |
| pip install netdryrun==0.3.2 on Python 3.12: --version, validate, MCP handshake | BLOCKER | **PASS** | 10.4 s | MCP handshake OK |
| uvx netdryrun@0.3.2 on Python 3.12: --version, MCP handshake | BLOCKER | **PASS** | 2.7 s | MCP handshake OK |
| pip install netdryrun==0.3.2 on Python 3.13: --version, validate, MCP handshake | BLOCKER | **PASS** | 9.3 s | MCP handshake OK |
| uvx netdryrun@0.3.2 on Python 3.13: --version, MCP handshake | BLOCKER | **PASS** | 2.9 s | MCP handshake OK |
| pip install netdryrun==0.3.2 on Python 3.14: --version, validate, MCP handshake | BLOCKER | **PASS** | 10.3 s | MCP handshake OK |
| uvx netdryrun@0.3.2 on Python 3.14: --version, MCP handshake | BLOCKER | **PASS** | 3.0 s | MCP handshake OK |
| frr-bgp from PyPI: `PASSED: 11 passed, 0 failed`, exit 0, no lab left | BLOCKER | **PASS** | 1.7 min | exit 0 |
| the MCP Registry lists io.github.netdryrun/netdryrun 0.3.2 | MAJOR | **PASS** | 0.0 s | listed versions: 0.3.0, 0.3.1, 0.3.2 |
| latest published-action.yml run | MAJOR | **ACCEPTED** | 0.0 s | gh is not installed (accepted: Checked by hand on the public Actions page, because the gate reads it with the gh CLI, which the release machine doesn't use: Run 41 of Published release (commit 311c8c6 on main, RELEASE 0.3.2) completed successfully. Run 40, on the merge commit 2db4ae1, failed as designed: it still pinned 0.3.1 while PyPI already served 0.3.2.) |

## Layer 6: independent review

# Layer 6: independent review, Netdryrun 0.3.2

## Cold code review (fresh agent, no context, the diff v0.3.1..ndr/agent-contract, src/ and tests/)
The question: any way the change can report `passed` or SAFE TO PROCEED without testing what the file or the agent's request says; any way the MCP path handling can be steered outside `NETDRYRUN_MCP_ROOT`; any exit-code change that turns a failure into a non-failure. The reviewer found no false pass on a run with a failed check and no escape from the root (`..`, symlinks, `~`, drive-relative, UNC and unmounted Windows paths all checked after `resolve()`).

| # | Finding | Severity | Decision | Commit |
|---|---|---|---|---|
| 1 | A relative MCP path resolved against the root could pick the main checkout's copy when the agent edited a worktree copy inside the root: SAFE TO PROCEED for a file the agent never changed | Possible false pass | Refused when the working directory holds a different file at that path (a folder counts when it holds `netdryrun.yml`); the working-directory file is used when only it exists, as before; the root check still follows | `319e989` |
| 2 | Skipping scenarios after an inconclusive main phase looked only at the main checks' nodes: a scenario on readable nodes that would have failed (exit 1) became inconclusive (exit 3) | Wrong exit (still non-passing) | Skip only when every node a scenario faults or checks never gave state (`checks.never_ready_nodes`, the same rule as `inconclusive_reason`) | `f8bb3fd` |
| 3 | An IPv6 scope ID (`fe80::1%…`) accepts any text, newlines included; it reached device CLI commands and the MCP `next_diagnostic` (EOS `Cli -c` runs each line) | Injection | The scope must be an interface name; anything else is a config error (exit 2) | `6175c2f` |
| 4 | A crash while building `failures` would lose the verdict (MCP error) | Low | Rejected: `evidence` entries are built by the drivers as dicts, never from lab or file input; a crash there is an MCP error with no verdict, which fails closed | — |
| 5 | `run_checks` returns SAFE TO PROCEED for a kept lab whose configs may be older than the agent's edits | Design, not new | Rejected for 0.3.2: the verdict strings are frozen for v1 and the description already says edited configs don't reach a running lab; backlog item: a `tested_change: false` field for `run_checks` | — |

Each fix was test-first: the tests failed on the branch before the fix (`test_relative_path_that_names_two_files_is_refused`, `test_scenarios_on_nodes_that_gave_state_still_run_after_an_unready_main_phase`, `test_ipv6_scope_id_must_be_an_interface_name`).

**Note on finding 3:** the same addresses already reached the lab's own commands in 0.3.1 (`drivers/eos.py`); the config check closes both.

## Multi-vendor AI audit (verdict path)

Three model families, each given the same brief (`research/briefs/ndr-0.3.2-verdict-audit.md` in HQ): the full MCP server module at the candidate and the v0.3.1 diff of config loading, the runner, the checks, the drivers and `action.yml`, with the questions "how can this report a pass, or CHECKS PASSED, without testing what the file or the agent asked; how can the MCP path handling escape NETDRYRUN_MCP_ROOT; what turns a failure into a non-failure", and none of our conclusions. Grok and ChatGPT (Codex) ran through `research/tools/ask_models.py` (privacy gate; one example path in a string literal was shown as `<HOME>/...` to pass it); the open model ran locally through Ollama. Answers: HQ `research/model-reviews/release-0.3.2/`.

Neither Grok nor ChatGPT found a way for a run with a failed check to report `passed`, or for a path the agent passes to escape the root (`..`, symlinks, multi-root relative paths, `/allowed-evil` against `/allowed`).

Class: **false-pass** means the finding, if real, could make Netdryrun report a pass without testing what it says; under the Layer 6 rule each one is a BLOCKER until it has a failing test and a fix, or is an explicitly accepted, publicly documented limit with a tracked fix target. **other** is everything else.

| # | Finding | Found by | Class | Decision | Commit |
|---|---|---|---|---|---|
| A1 | `tested.complete` said true while containerlab read files the list missed: topology `groups`, `license`, `env-files`, and paths given with `~`, `${VAR}` or a URL | Grok, ChatGPT | other (wrong evidence) | Fixed: groups, licences and env files listed; a `~`, `${VAR}` or URL reference is not read and makes `complete` false (`test_tested_is_not_complete_when_the_topology_uses_files_it_cannot_list`) | `9230a5c` |
| A2 | With a relative path, the result didn't say which `netdryrun.yml` the server chose (working-directory copy or root copy) | Grok, ChatGPT | other (traceability) | Fixed: `tested.config` is the resolved path that ran (`test_tested_names_the_config_that_ran`); the choice rule itself stays (cold review finding 1) | `9230a5c` |
| A3 | The report write truncated a hard link at `netdryrun-report.json` (the symlink check doesn't see hard links) | Grok | other (write outside the folder) | Fixed: written to a new file and renamed into place (`test_the_report_write_never_follows_a_hardlink`) | `9230a5c` |
| A4 | A topology inside the root can mount host paths, download configs, and run host commands (`stages` with `target: host`), as root | Grok, ChatGPT | other (security scope) | Documented limit, not a path escape: the safety model already said the root "does not make an untrusted lab inside the folder safe"; it now names host commands and URL downloads, and says an agent that can write a topology there can run code on the host | `9230a5c` (docs) |
| A5 | `run_checks` returns CHECKS PASSED for a kept lab while the files on disk were edited | Grok, ChatGPT | other (the checks in the file were tested, against the lab that runs) | Rejected for 0.3.2, as in the cold review (finding 5): verdict strings are frozen; `tested.lab_deployed_by_this_run: false` now says the files may not be what the lab runs | — |
| A6 | A node that answers BGP with no neighbors at all was released at the gate cap with a warning, so leak guards and prefix maxima could pass on a router whose BGP config never loaded (the 0.3.1 "remaining limit") | Grok | **false-pass** | **Fixed** (owner decision): when the file has a BGP check on that node (`bgp_session`, `bgp_prefixes`, `bgp_route`, or a `route` with `protocol: bgp`), its post-convergence checks fail at the cap as "not evaluated", every sample unready, so the inconclusive rule applies when nothing anywhere gave state; a node with no BGP check anywhere keeps the warning. Failing test first: `test_a_bgp_node_with_no_neighbors_beside_a_working_node_is_a_failure` returned `passed` before the fix. Advisory, config reference, troubleshooting and CHANGELOG updated | `054158c` |
| A6b | Prefix counts stable before routes arrive: a peer with a long advertisement interval can deliver a route after a negative check was released and held | Grok | **false-pass / accepted documented limit** | Accepted for 0.3.2 (owner decision). Public statement: the 0.3.0 advisory's remaining limits and the config reference (the convergence steps) say to raise `--settle` and `--hold` above the slowest advertisement interval. Tracked fix: 0.4 reads each peer's configured advertisement interval and extends the settle window automatically | — |
| A7 | Scenario skip and the T10 readiness rule move some runs from exit 1 or 2 to 3 | Grok, ChatGPT | other (never a pass) | Rejected: deliberate 0.3.2 decisions (cold review finding 2 and the agent eval T10 fix), documented with their known limit | — |
| A8 | An all-unready session check plus a `present: false` route that failed readably would go inconclusive | Grok | other (claimed exit change) | Rejected, not reproducible: condition 3 of the inconclusive rule keeps it `failed` (`test_failed_post_convergence_check_with_state_is_a_finding`) | — |
| A9 | Check-then-open races (swap a symlink after the root check; edit a file between hashing and deploy) | ChatGPT | other (local writer) | Rejected: needs a concurrent writer inside the root, who can already change the configs that run | — |
| A10 | `_summary` maps `passed` without checking results | ChatGPT | false-pass (claimed) | Rejected, not real: `RunReport.status` is `passed` only with no error, at least one result and no failure, and config loading refuses a file with no checks | — |
| A11 | The agent's intended checks are never compared with the file | ChatGPT | other (scope) | Rejected: the server tests the file; the descriptions say never to invent or weaken checks and to use `record_baseline` | — |
| A12 | `record_baseline` and `validate` return no verdict; `passed` in the result is a count | ChatGPT, Grok | other | Rejected: documented; agents decide on `status` | — |
| A13 | A Windows path whose drive isn't mounted could be joined to the root | ChatGPT | other (claimed misdirection) | Rejected: `_tool_path` treats a `C:\...` path as absolute and never joins it to the root | — |
| Q1 | A `netdryrun.yml` with no checks reports `passed` | Qwen3 30B-A3B (local) | false-pass (claimed) | Rejected, not real: loading refuses it, exit 2 "no checks defined" (checked on the candidate; `tests/test_verdict_config.py`); the answer quoted status code that doesn't exist | — |
| Q2 | A Windows path translated to `/mnt/c/...` escapes the root | Qwen3 30B-A3B | other (claimed escape) | Rejected, not real: the translated path is held to the root like any other (`test_windows_paths_stay_inside_netdryrun_mcp_root`); the answer's own example is refused | — |
| Q3 | Skipped scenarios leave the status `passed` | Qwen3 30B-A3B | false-pass (claimed) | Rejected, not real: the main results hold failed checks, so the status is `inconclusive`, exit 3 (`test_a_lab_that_never_reached_a_testable_state_is_inconclusive_with_scenarios_too`); the answer quoted status code that doesn't exist | — |

The open model (local Ollama, qwen3:30b-a3b, 55 minutes) found nothing real: all three findings rest on code it invented. Open false-pass findings after this audit: none (A6 fixed; A6b accepted as a documented limit with a 0.4 fix target).
