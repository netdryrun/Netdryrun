# Release gate: Netdryrun 0.4.1

Written by `scripts/release_gate.py` (see [RELEASING.md](../../RELEASING.md)). Do not edit by hand: rerun a layer, or record a decision in `accepted.json` or `review.md`.

**INCOMPLETE**: no BLOCKER failed, but the gate is not complete (see below).

**Layers not run yet:**

- Layer 5b: acceptance from five angles
- Layer 7: after-publish proof

**Other gaps:**

- no independent review recorded (review.md, layer 6)

| Layer | Commit | Ran | Time | Result |
|---|---|---|---|---|
| [Layer 1: static](#layer-1-static) | `6e0a0277ea` | 2026-11-05 07:06:39 UTC | 2.1 s | 18 PASS |
| [Layer 2: unit tests on every supported Python](#layer-2-unit-tests-on-every-supported-python) | `6e0a0277ea` | 2026-11-05 07:06:41 UTC | 7.4 min | 7 PASS |
| [Layer 4: mutation testing](#layer-4-mutation-testing) | `6e0a0277ea` | 2026-11-05 07:14:23 UTC | 9.3 min | 12 PASS |
| [Layer 5: live matrix on the built package](#layer-5-live-matrix-on-the-built-package) | `6e0a0277ea` | 2026-11-05 07:25:15 UTC | 180.7 min | 3 ACCEPTED, 62 PASS |
| Layer 5b: acceptance from five angles | | not run | | |
| Layer 7: after-publish proof | | not run | | |

## Layer 1: static

Commit `6e0a0277eada081407828d4577dd9bc539628c1e` on `HEAD`; 2026-11-05 07:06:39 UTC; 2.1 s; Linux 6.18.54.1-microsoft-standard-WSL2 (x86_64); Python 3.12.16; --strict.

Tools: actionlint 1.7.7; ruff 0.17.3; shellcheck 0.8.0.

| Check | Severity | Result | Time | Notes |
|---|---|---|---|---|
| every src/netdryrun module is mutated or exempt with a reason (G1) | BLOCKER | **PASS** | 0.0 s | 12 mutated, 15 exempt |
| the committed corpus results ran on this verdict code (G3; stale ones run first in live) | MAJOR | **PASS** | 0.0 s | every corpus is fresh |
| ruff (config in pyproject.toml) | BLOCKER | **PASS** | 0.1 s | All checks passed! |
| actionlint on every workflow (with shellcheck) | BLOCKER | **PASS** | 0.2 s | clean |
| shellcheck, error level, 22 scripts | BLOCKER | **PASS** | 0.2 s | clean |
| shellcheck, warning level, 22 scripts | MAJOR | **PASS** | 0.2 s | clean |
| no empty ${{ }} in action.yml or workflows | BLOCKER | **PASS** | 0.0 s | none |
| public facts match the source (sync_facts.py --check) | BLOCKER | **PASS** | 0.6 s | facts: in sync (version 0.4.1, 0 problem(s)) |
| every version reference says 0.4.1 | BLOCKER | **PASS** | 0.1 s | 47 references agree |
| pyproject.toml declares Python 3.10 to 3.14, the versions tested | MAJOR | **PASS** | 0.0 s | requires-python and classifiers agree |
| every example has a documented expected result and exit code | MAJOR | **PASS** | 0.0 s | 13 examples |
| every topology we ship is named ndr-* | BLOCKER | **PASS** | 0.0 s | 97 topologies |
| no retired public string outside the history (CHANGELOG, advisories, records) | BLOCKER | **PASS** | 0.0 s | none |
| CHANGELOG has no Unreleased entries left (all under 0.4.1) | BLOCKER | **PASS** | 0.0 s | cut |
| corpus v1: the committed results ran on this verdict code (G3) | BLOCKER | **PASS** | 0.0 s | fresh |
| corpus v2: the committed results ran on this verdict code (G3) | BLOCKER | **PASS** | 0.0 s | fresh |
| tag v0.4.1 does not exist yet | BLOCKER | **PASS** | 0.0 s | unused |
| PyPI has no netdryrun 0.4.1 yet | BLOCKER | **PASS** | 0.0 s | HTTP 404 |

## Layer 2: unit tests on every supported Python

Commit `6e0a0277eada081407828d4577dd9bc539628c1e` on `HEAD`; 2026-11-05 07:06:41 UTC; 7.4 min; Linux 6.18.54.1-microsoft-standard-WSL2 (x86_64); Python 3.12.16; --strict.

Tools: docker 29.9.2; uv 0.13.6 (x86_64-unknown-linux-gnu).

| Check | Severity | Result | Time | Notes |
|---|---|---|---|---|
| unit tests on Python 3.10.12 | BLOCKER | **PASS** | 78.9 s | 5612 passed, 65 skipped, 1 xfailed |
| unit tests on Python 3.11.18 | BLOCKER | **PASS** | 65.1 s | 5612 passed, 65 skipped, 1 xfailed |
| unit tests on Python 3.12.16 (with coverage) | BLOCKER | **PASS** | 1.8 min | 5612 passed, 65 skipped, 1 xfailed, 23 warnings |
| coverage of the verdict modules at or above the floors | MAJOR | **PASS** | 0.0 s | all at or above their floors |
| unit tests on Python 3.13.18 | BLOCKER | **PASS** | 58.0 s | 5612 passed, 65 skipped, 1 xfailed, 23 warnings |
| unit tests on Python 3.14.10 | BLOCKER | **PASS** | 58.1 s | 5612 passed, 65 skipped, 1 xfailed |
| unit tests in a plain python:3.12-slim container (no containerlab, no Docker) | BLOCKER | **PASS** | 74.8 s | 5563 passed, 114 skipped, 1 xfailed |

**Coverage of the verdict modules** (lines and branches, Python 3.12):

| Module | Lines | Branches | Covered | Floor |
|---|---|---|---|---|
| `src/netdryrun/checks.py` | 330/332 | 148/150 | 99.2% | 99% |
| `src/netdryrun/config.py` | 490/492 | 288/290 | 99.5% | 99% |
| `src/netdryrun/runner.py` | 746/753 | 325/330 | 98.9% | 98% |
| `src/netdryrun/drivers/` | 2324/2329 | 907/914 | 99.6% | 99% |
| `src/netdryrun/verify/engine.py` | 477/479 | 226/228 | 99.4% | 98% |
| `src/netdryrun/verify/intent.py` | 349/352 | 169/172 | 98.9% | 97% |
| `src/netdryrun/verify/frr.py` | 591/636 | 299/340 | 91.2% | 88% |
| `src/netdryrun/verify/snapshot.py` | 399/423 | 133/156 | 91.9% | 90% |
| `src/netdryrun/verify/converge.py` | 71/73 | 29/30 | 97.1% | 96% |
| `src/netdryrun/verify/run.py` | 485/544 | 175/210 | 87.5% | 83% |
| `src/netdryrun/verify/report.py` | 203/224 | 86/102 | 88.7% | 88% |
| `src/netdryrun/faults.py` | 276/283 | 108/112 | 97.2% | 96% |

## Layer 4: mutation testing

Commit `6e0a0277eada081407828d4577dd9bc539628c1e` on `HEAD`; 2026-11-05 07:14:23 UTC; 9.3 min; Linux 6.18.54.1-microsoft-standard-WSL2 (x86_64); Python 3.12.16; --strict.

Tools: mutmut python -m mutmut, version 3.8.1.

| Check | Severity | Result | Time | Notes |
|---|---|---|---|---|
| no surviving mutants in src/netdryrun/faults.py | BLOCKER | **PASS** | 9.0 min | 831 generated, 743/831 caught (89.4%); not caught: 88 survived the tests, 0 in code no test runs, 13 accepted (13 equivalent); 75 outside the gated functions (parsers that fail closed and rendering; their full zero is a 0.4.1 gate item) |
| no surviving mutants in src/netdryrun/runner.py | BLOCKER | **PASS** | 0.0 s | carried over from 7532310: src/netdryrun/runner.py is byte-identical at this commit. 1848 generated, 1693/1848 caught (91.6%); not caught: 155 survived the tests, 0 in code no test runs, 155 accepted (32 equivalent, 5 logging, 111 message-text, 1 safety, 6 timing-only) |
| no surviving mutants in src/netdryrun/drivers/ | BLOCKER | **PASS** | 0.0 s | carried over from 7532310: src/netdryrun/drivers/ is byte-identical at this commit. 5761 generated, 5508/5761 caught (95.6%); not caught: 253 survived the tests, 0 in code no test runs, 253 accepted (78 equivalent, 175 message-text) |
| no surviving mutants in src/netdryrun/verify/run.py | BLOCKER | **PASS** | 0.0 s | carried over from 7532310: src/netdryrun/verify/run.py is byte-identical at this commit. 1442 generated, 1205/1442 caught (83.6%); not caught: 237 survived the tests, 0 in code no test runs, 7 accepted (7 equivalent); 230 outside the gated functions (parsers that fail closed and rendering; their full zero is a 0.4.1 gate item) |
| no surviving mutants in src/netdryrun/checks.py | BLOCKER | **PASS** | 0.0 s | carried over from 7532310: src/netdryrun/checks.py is byte-identical at this commit. carried over from b88adef: src/netdryrun/checks.py is byte-identical at this commit. 1352 generated, 1325/1352 caught (98.0%); not caught: 27 survived the tests, 0 in code no test runs, 27 accepted (21 equivalent, 6 message-text) |
| no surviving mutants in src/netdryrun/config.py | BLOCKER | **PASS** | 0.0 s | carried over from 7532310: src/netdryrun/config.py is byte-identical at this commit. carried over from b88adef: src/netdryrun/config.py is byte-identical at this commit. 1635 generated, 1506/1635 caught (92.1%); not caught: 129 survived the tests, 0 in code no test runs, 129 accepted (30 equivalent, 99 message-text) |
| no surviving mutants in src/netdryrun/verify/engine.py | BLOCKER | **PASS** | 0.0 s | carried over from 7532310: src/netdryrun/verify/engine.py is byte-identical at this commit. carried over from b88adef: src/netdryrun/verify/engine.py is byte-identical at this commit. 1576 generated, 1512/1576 caught (95.9%); not caught: 64 survived the tests, 0 in code no test runs, 64 accepted (27 equivalent, 37 message-text) |
| no surviving mutants in src/netdryrun/verify/intent.py | BLOCKER | **PASS** | 0.0 s | carried over from 7532310: src/netdryrun/verify/intent.py is byte-identical at this commit. carried over from b88adef: src/netdryrun/verify/intent.py is byte-identical at this commit. 1146 generated, 1023/1146 caught (89.3%); not caught: 123 survived the tests, 0 in code no test runs, 123 accepted (14 equivalent, 109 message-text) |
| no surviving mutants in src/netdryrun/verify/frr.py | BLOCKER | **PASS** | 0.0 s | carried over from 7532310: src/netdryrun/verify/frr.py is byte-identical at this commit. carried over from b88adef: src/netdryrun/verify/frr.py is byte-identical at this commit. 2802 generated, 1949/2802 caught (69.6%); not caught: 853 survived the tests, 0 in code no test runs, 2 accepted (2 equivalent); 851 outside the gated functions (parsers that fail closed and rendering; their full zero is a 0.4.1 gate item) |
| no surviving mutants in src/netdryrun/verify/snapshot.py | BLOCKER | **PASS** | 0.0 s | carried over from 7532310: src/netdryrun/verify/snapshot.py is byte-identical at this commit. carried over from b88adef: src/netdryrun/verify/snapshot.py is byte-identical at this commit. 1100 generated, 822/1100 caught (74.7%); not caught: 278 survived the tests, 0 in code no test runs; 278 outside the gated functions (parsers that fail closed and rendering; their full zero is a 0.4.1 gate item) |
| no surviving mutants in src/netdryrun/verify/converge.py | BLOCKER | **PASS** | 0.0 s | carried over from 7532310: src/netdryrun/verify/converge.py is byte-identical at this commit. carried over from b88adef: src/netdryrun/verify/converge.py is byte-identical at this commit. 148 generated, 134/148 caught (90.5%); not caught: 14 survived the tests, 0 in code no test runs, 2 accepted (2 equivalent); 12 outside the gated functions (parsers that fail closed and rendering; their full zero is a 0.4.1 gate item) |
| no surviving mutants in src/netdryrun/verify/report.py | BLOCKER | **PASS** | 0.0 s | carried over from 7532310: src/netdryrun/verify/report.py is byte-identical at this commit. carried over from b88adef: src/netdryrun/verify/report.py is byte-identical at this commit. 842 generated, 535/842 caught (63.5%); not caught: 307 survived the tests, 0 in code no test runs; 307 outside the gated functions (parsers that fail closed and rendering; their full zero is a 0.4.1 gate item) |

**src/netdryrun/faults.py: 75 survivors outside the gated functions** (parsers that fail closed and rendering; their full zero is a 0.4.1 gate item): `faults.conflicts` 17, `faults.RouteInjection._apply_config` 13, `faults.parse_inject` 11, `faults.RouteInjection._vtysh` 11, `faults.RouteInjection.__init__` 10, `faults.RouteInjection._wait` 8, `faults.config_lines` 4, `faults.RouteInjection._as_path` 1

**src/netdryrun/verify/run.py: 230 survivors outside the gated functions** (parsers that fail closed and rendering; their full zero is a 0.4.1 gate item): `verify.run.verify` 63, `verify.run.materialize` 37, `verify.run.bind_sources` 24, `verify.run._git` 20, `verify.run.expand_bind` 16, `verify.run._hash_binds` 14, `verify.run._extract` 11, `verify.run.load_guards` 11, `verify.run._cat_files` 9, `verify.run._is_ref` 5, `verify.run.intent_edited` 5, `verify.run._files` 4, `verify.run.resolve_bind` 4, `verify.run._hint` 3, `verify.run._now` 1, `verify.run.confirm_by_rerun` 1, `verify.run.expects_bgp` 1, `verify.run.Side.locate` 1

**src/netdryrun/verify/frr.py: 851 survivors outside the gated functions** (parsers that fail closed and rendering; their full zero is a 0.4.1 gate item): `verify.frr._nexthop` 148, `verify.frr.parse_attrs` 146, `verify.frr.parse_routes` 81, `verify.frr.parse_neighbors` 72, `verify.frr._parse_received` 58, `verify.frr.parse_adj` 57, `verify.frr.parse_bgp_table` 53, `verify.frr.show_command` 38, `verify.frr.parse_path` 33, `verify.frr._dest_paths` 23, `verify.frr._nexthops` 23, `verify.frr.FrrCollector._collect_items` 22, `verify.frr.FrrCollector._vtysh` 14, `verify.frr.FrrCollector._collect` 10, `verify.frr._check_total` 8, `verify.frr._obj` 8, `verify.frr._vrf` 8, `verify.frr._best_sent` 7, `verify.frr._json` 7, `verify.frr._str` 7, `verify.frr._communities` 6, `verify.frr._add_path_rx` 5, `verify.frr._int` 4, `verify.frr._flag` 3, `verify.frr.sent_counters` 3, `verify.frr._opt_int` 2, `verify.frr.adv_intervals` 2, `verify.frr._bad` 1, `verify.frr.add_path_tx` 1, `verify.frr.FrrCollector.__init__` 1

**src/netdryrun/verify/snapshot.py: 278 survivors outside the gated functions** (parsers that fail closed and rendering; their full zero is a 0.4.1 gate item): `verify.snapshot.Snapshot.from_json` 41, `verify.snapshot.AsPath.build` 32, `verify.snapshot.decode` 30, `verify.snapshot.BgpAttrs.__post_init__` 27, `verify.snapshot.AsPath.parse` 22, `verify.snapshot.AsPath.__post_init__` 20, `verify.snapshot.AsPath.render` 20, `verify.snapshot.parse_asn` 13, `verify.snapshot.canon_prefix` 10, `verify.snapshot.NextHop.__post_init__` 8, `verify.snapshot.canon_ext_communities` 7, `verify.snapshot.canon_ip` 7, `verify.snapshot.BgpPath.__post_init__` 6, `verify.snapshot.ItemKey.where` 6, `verify.snapshot.canon_community` 5, `verify.snapshot.Session.__post_init__` 5, `verify.snapshot._typed` 4, `verify.snapshot.canon_large_community` 4, `verify.snapshot.RibEntry.__post_init__` 4, `verify.snapshot.canon_ext_community` 3, `verify.snapshot.Snapshot.to_json` 3, `verify.snapshot.PathNextHop.__post_init__` 1

**src/netdryrun/verify/converge.py: 12 survivors outside the gated functions** (parsers that fail closed and rendering; their full zero is a 0.4.1 gate item): `verify.converge._moving` 12

**src/netdryrun/verify/report.py: 307 survivors outside the gated functions** (parsers that fail closed and rendering; their full zero is a 0.4.1 gate item): `verify.report.markdown` 142, `verify.report.console` 92, `verify.report._summary` 25, `verify.report.item_json` 25, `verify.report._intent_json` 6, `verify.report._plain_yaml` 6, `verify.report.to_json` 6, `verify.report._diag` 5

**Surviving mutants by function** (88 in all; every diff is in [mutants.md](mutants.md)):

| Function | Survivors |
|---|---|
| `faults.conflicts` | 17 |
| `faults.RouteInjection._apply_config` | 13 |
| `faults.RouteInjection._vtysh` | 11 |
| `faults.parse_inject` | 11 |
| `faults.RouteInjection.__init__` | 10 |
| `faults.RouteInjection._wait` | 8 |
| `faults.RouteInjection.advertised` | 7 |
| `faults.config_lines` | 4 |
| `faults.RouteInjection._is_injected` | 2 |
| `faults.RouteInjection.record_listed` | 2 |
| `faults.RouteInjection._as_path` | 1 |
| `faults.RouteInjection.established` | 1 |
| `faults.RouteInjection.sessions` | 1 |

## Layer 5: live matrix on the built package

Commit `6e0a0277eada081407828d4577dd9bc539628c1e` on `HEAD`; 2026-11-05 07:25:15 UTC; 180.7 min; Linux 6.18.54.1-microsoft-standard-WSL2 (x86_64); Python 3.12.16; --strict.

Tools: containerlab ⣴⡾⠛⠛⠖ ⢠⣶⠟⠛⢷⣦ ⢸⣿⣧ ⣿ ⠘⠛⢻⡟⠛⠛ ⣾⣿⡀ ⣿⡇ ⣿⣿⡄ ⢸⡇ ⣿⡟⠛⠛⠃⢸⣿⠛⠛⣷⡄ [38;2;0;201;255m⣿⡇[0m ; docker 29.9.2.

| Check | Severity | Result | Time | Notes |
|---|---|---|---|---|
| build the wheel and the sdist | BLOCKER | **PASS** | 1.4 s | netdryrun-0.4.1-py3-none-any.whl |
| the wheel and the sdist carry NOTICE (Apache-2.0 section 4(d)) | BLOCKER | **PASS** | 0.0 s | both carry it |
| install netdryrun-0.4.1-py3-none-any.whl in a fresh venv | BLOCKER | **PASS** | 0.4 s |  |
| runs the installed package, not the source tree | BLOCKER | **PASS** | 0.0 s | /tmp/ndr-gate-live-06c10_5y/venv/lib/python3.12/site-packages/netdryrun/__init__.py |
| netdryrun --version says 0.4.1 | BLOCKER | **PASS** | 0.0 s | netdryrun 0.4.1 |
| example agent-demo: `Demo OK`, exit 0 | BLOCKER | **PASS** | 76.2 s | exit 0: Demo OK: attempt 1 rejected by 5 leak guards with every other check passing; attempt 2 passed every check. |
| example agent-demo: no lab left running | BLOCKER | **PASS** | 0.0 s | none left |
| example arista-frr: `PASSED: 10 passed, 0 failed`, exit 0 | BLOCKER | **PASS** | 1.6 min | exit 0: PASSED: 10 passed, 0 failed (10 checks) |
| example arista-frr: no lab left running | BLOCKER | **PASS** | 0.0 s | none left |
| example batfish-pipeline: `PASSED: 10 passed, 0 failed`, exit 0 | BLOCKER | **PASS** | 1.7 min | exit 0: PASSED: 10 passed, 0 failed (10 checks) |
| example batfish-pipeline: no lab left running | BLOCKER | **PASS** | 0.0 s | none left |
| example frr-bgp: `PASSED: 11 passed, 0 failed`, exit 0 | BLOCKER | **PASS** | 1.7 min | exit 0: PASSED: 11 passed, 0 failed (11 checks) |
| example frr-bgp: no lab left running | BLOCKER | **PASS** | 0.0 s | none left |
| example frr-bgp-broken: `FAILED: 5 passed, 1 failed`, exit 1 | BLOCKER | **PASS** | 40.4 s | exit 1: FAILED: 5 passed, 1 failed (6 checks) |
| example frr-bgp-broken: no lab left running | BLOCKER | **PASS** | 0.0 s | none left |
| example frr-customer-leak: `FAILED: 19 passed, 2 failed`, exit 1 | BLOCKER | **PASS** | 68.4 s | exit 1: FAILED: 19 passed, 2 failed (21 checks) |
| example frr-customer-leak: no lab left running | BLOCKER | **PASS** | 0.0 s | none left |
| example junos-frr: `PASSED: 13 passed, 0 failed`, exit 0 | BLOCKER | **PASS** | 4.7 min | exit 0: PASSED: 13 passed, 0 failed (13 checks) |
| example junos-frr: no lab left running | BLOCKER | **PASS** | 0.0 s | none left |
| example leak-pattern: `PASSED: 8 passed, 0 failed`, exit 0 | BLOCKER | **PASS** | 42.2 s | exit 0: PASSED: 8 passed, 0 failed (8 checks) |
| example leak-pattern: no lab left running | BLOCKER | **PASS** | 0.0 s | none left |
| example mikrotik: `PASSED: 10 passed, 0 failed`, exit 0 | BLOCKER | **PASS** | 83.6 s | exit 0: PASSED: 10 passed, 0 failed (10 checks) |
| example mikrotik: no lab left running | BLOCKER | **PASS** | 0.0 s | none left |
| example nxos-frr: `PASSED: 10 passed, 0 failed`, exit 0 | BLOCKER | **PASS** | 6.4 min | exit 0: PASSED: 10 passed, 0 failed (10 checks) |
| example nxos-frr: no lab left running | BLOCKER | **PASS** | 0.0 s | none left |
| example sonic-frr: `PASSED: 8 passed, 0 failed`, exit 0 | BLOCKER | **PASS** | 1.6 min | exit 0: PASSED: 8 passed, 0 failed (8 checks) |
| example sonic-frr: no lab left running | BLOCKER | **PASS** | 0.0 s | none left |
| example srl-frr: `PASSED: 7 passed, 0 failed`, exit 0 | BLOCKER | **PASS** | 86.2 s | exit 0: PASSED: 7 passed, 0 failed (7 checks) |
| example srl-frr: no lab left running | BLOCKER | **PASS** | 0.0 s | none left |
| example srl-hidden-leak: `PASSED: 9 passed, 0 failed`, exit 0 | BLOCKER | **PASS** | 58.5 s | exit 0: PASSED: 9 passed, 0 failed (9 checks) |
| example srl-hidden-leak: no lab left running | BLOCKER | **PASS** | 0.0 s | none left |
| example srl-hidden-leak with leaks/frr1.conf: `FAILED: 8 passed, 1 failed`, exit 1 | BLOCKER | **PASS** | 63.6 s | exit 1: FAILED: 8 passed, 1 failed (9 checks) |
| example srl-hidden-leak with leaks/frr1.conf: no lab left running | BLOCKER | **PASS** | 0.0 s | none left |
| example srl-hidden-leak with leaks/srl1.cli: `FAILED: 8 passed, 1 failed`, exit 1 | BLOCKER | **PASS** | 64.6 s | exit 1: FAILED: 8 passed, 1 failed (9 checks) |
| example srl-hidden-leak with leaks/srl1.cli: no lab left running | BLOCKER | **PASS** | 0.0 s | none left |
| example times match the docs (within 2x) | MAJOR | **PASS** | 0.0 s | all within 2x |
| Verdict Corpus v1: every verdict matches the committed results.json | BLOCKER | **PASS** | 68.1 min | all verdicts match |
| Verdict Corpus v1: every case records a status, none an error | BLOCKER | **PASS** | 0.0 s | all recorded, no error |
| Verdict Corpus v1: no harmful change approved beyond the published known misses | BLOCKER | **PASS** | 0.0 s | harmful changes approved: 5 (12-ibgp-send-community-dropped, 18-redistribute-connected, 21-customer-max-prefix-removed, 23-fat-finger-third-party-origin, 30-peer-import-filter-removed); published known misses: 12-ibgp-send-community-dropped, 18-redistribute-connected, 21-customer-max-prefix-removed, 23-fat-finger-third-party-origin, 30-peer-import-filter-removed |
| Verdict Corpus v1: no lab left running | BLOCKER | **PASS** | 0.0 s | none left |
| Verdict Corpus v2: every verdict matches the committed results.json | BLOCKER | **PASS** | 82.5 min | all verdicts match |
| Verdict Corpus v2: every case records a status, none an error | BLOCKER | **PASS** | 0.0 s | all recorded, no error |
| Verdict Corpus v2: the nondeterministic exemption holds (pinned, exact runs bound to the case's checks, no crash, no approval) | BLOCKER | **PASS** | 0.0 s | 18-aggregate-discard-route-removed |
| Verdict Corpus v2: every nondeterministic case was caught in at least one run | BLOCKER | **PASS** | 0.0 s | every case caught in at least one run |
| Verdict Corpus v2: nondeterministic cases recorded (known, not scored, never a blocker) | INFO | **PASS** | 0.0 s | Netdryrun verdicts per run: 18-aggregate-discard-route-removed: unsafe, error, error, unsafe, unsafe |
| Verdict Corpus v2: no harmful change approved beyond the published known misses | BLOCKER | **PASS** | 0.0 s | harmful changes approved: 0 (none); published known misses: none |
| Verdict Corpus v2: no lab left running | BLOCKER | **PASS** | 0.0 s | none left |
| MCP handshake against the installed wheel | BLOCKER | **PASS** | 1.1 s | MCP handshake OK |
| check pack verification | MAJOR | **ACCEPTED** | 0.0 s | no --pack script given (accepted: No check pack is sold yet: pack verification is paused by the roadmap until the 45-day demand test; it runs with --pack before any pack ships.) |
| 20-node scale test | MAJOR | **ACCEPTED** | 0.0 s | not scripted in the repository yet: run it by hand (accepted: Not scripted yet. A 20-node lab was run by hand in pre-launch testing (it found the PR-comment size limit, fixed in 0.3.1); scripting it is a 0.4.1 item.) |
| SIGINT during deploy: exit 130, a clear message | BLOCKER | **PASS** | 4.8 s | exit 130 |
| SIGINT during deploy: no lab left running | BLOCKER | **PASS** | 0.0 s | none left |
| SIGINT during checks: exit 130, a clear message | BLOCKER | **PASS** | 17.2 s | exit 130 |
| SIGINT during checks: no lab left running | BLOCKER | **PASS** | 0.0 s | none left |
| SIGTERM during deploy: exit 143, a clear message | BLOCKER | **PASS** | 5.6 s | exit 143 |
| SIGTERM during deploy: no lab left running | BLOCKER | **PASS** | 0.0 s | none left |
| SIGTERM during checks: exit 143, a clear message | BLOCKER | **PASS** | 18.0 s | exit 143 |
| SIGTERM during checks: no lab left running | BLOCKER | **PASS** | 0.0 s | none left |
| a node's image does not exist: exit 2 with a clear error | BLOCKER | **PASS** | 0.4 s | exit 2:   wrote json report: /tmp/ndr-gate-live-06c10_5y/reports/frr-bgp-missing-image.json |
| a node's image does not exist: no lab left running | BLOCKER | **PASS** | 0.0 s | none left |
| a node cannot be created (a bind source does not exist): exit 2 with a clear error | BLOCKER | **PASS** | 0.3 s | exit 2:   wrote json report: /tmp/ndr-gate-live-06c10_5y/reports/frr-bgp-deploy-fails.json |
| a node cannot be created (a bind source does not exist): no lab left running | BLOCKER | **PASS** | 0.0 s | none left |
| two runs of the same lab at once: no false verdict, no crash | BLOCKER | **PASS** | 1.7 min | exit codes 0 and 2 |
| two runs at once: no lab left running | BLOCKER | **PASS** | 0.0 s | none left |
| Docker restarts mid-run | MAJOR | **ACCEPTED** | 0.0 s | off by default (restarts every container on the machine): pass --chaos-docker-restart (accepted: Optional by RELEASING.md (Layer 5, Chaos): it restarts Docker, which stops every container on the machine, and the lab machine is shared with other sessions' labs. The other chaos cases (SIGINT and SIGTERM in the deploy and the checks, a missing image, a node that can't be created, two runs of one lab) ran and passed on 81a49b3. Coordinator, 2026-10-31: kept for 0.4.0 (the interop stress test holds the lab, and a Docker restart would kill its labs); the restart case runs in the next quiet lab window or, at the latest, in the 0.4.1 gate.) |

## Layer 6: independent review

Not recorded yet. Put the cold review, outside-model review, claims audit and fresh-user replay findings, and the decision on each, in `review.md` beside this file.
