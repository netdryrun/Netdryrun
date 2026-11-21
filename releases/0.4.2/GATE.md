# Release gate: Netdryrun 0.4.2

Written by `scripts/release_gate.py` (see [RELEASING.md](../../RELEASING.md)). Do not edit by hand: rerun a layer, or record a decision in `accepted.json` or `review.md`.

**READY TO PUBLISH**: every layer before publishing ran on the same clean commit; no BLOCKER failed or was skipped; every MAJOR passed or was accepted. Tag it, then run `after-publish` to clear it.

**Layers not run yet:**

- Layer 7: after-publish proof

| Layer | Commit | Ran | Time | Result |
|---|---|---|---|---|
| [Layer 1: static](#layer-1-static) | `79de759842` | 2026-11-20 21:51:41 UTC | 2.6 min | 22 PASS |
| [Layer 2: unit tests on every supported Python](#layer-2-unit-tests-on-every-supported-python) | `79de759842` | 2026-11-20 21:54:22 UTC | 14.3 min | 7 PASS |
| [Layer 4: mutation testing](#layer-4-mutation-testing) | `79de759842` | 2026-11-21 06:19:32 UTC | 206.1 min | 13 PASS |
| [Layer 5: live matrix on the built package](#layer-5-live-matrix-on-the-built-package) | `79de759842` | 2026-11-20 22:09:05 UTC | 239.0 min | 3 ACCEPTED, 63 PASS |
| [Layer 5b: acceptance from five angles](#layer-5b-acceptance-from-five-angles) | `79de759842` | 2026-11-21 03:18:59 UTC | 171.6 min | 46 PASS |
| Layer 7: after-publish proof | | not run | | |

## Layer 1: static

Commit `79de75984253ec3727bb35fc2aec14bc957ea103` on `HEAD`; 2026-11-20 21:51:41 UTC; 2.6 min; Linux 6.18.58.1-microsoft-standard-WSL2 (x86_64); Python 3.12.16; --strict.

Tools: actionlint 1.7.7; ruff 0.17.6; shellcheck 0.8.0.

| Check | Severity | Result | Time | Notes |
|---|---|---|---|---|
| every src/netdryrun module is mutated or exempt with a reason (G1) | BLOCKER | **PASS** | 0.0 s | 13 mutated, 15 exempt |
| the committed corpus results ran on this verdict code (G3; stale ones run first in live) | MAJOR | **PASS** | 0.0 s | every corpus is fresh |
| ruff (config in pyproject.toml) | BLOCKER | **PASS** | 0.1 s | All checks passed! |
| actionlint on every workflow (with shellcheck) | BLOCKER | **PASS** | 0.2 s | clean |
| shellcheck, error level, 23 scripts | BLOCKER | **PASS** | 0.2 s | clean |
| shellcheck, warning level, 23 scripts | MAJOR | **PASS** | 0.2 s | clean |
| no empty ${{ }} in action.yml or workflows | BLOCKER | **PASS** | 0.0 s | none |
| public facts match the source (sync_facts.py --check) | BLOCKER | **PASS** | 0.6 s | facts: in sync (version 0.4.2, 0 problem(s)) |
| every surface names the platforms that shipped (surfaces_agree.py static) | BLOCKER | **PASS** | 0.1 s | surfaces static: agree (version 0.4.2, platforms eos, frr, junos, nxos, routeros, sonic, srlinux) |
| every version reference says 0.4.2 | BLOCKER | **PASS** | 0.1 s | 48 references agree |
| pyproject.toml declares Python 3.10 to 3.14, the versions tested | MAJOR | **PASS** | 0.0 s | requires-python and classifiers agree |
| every example has a documented expected result and exit code | MAJOR | **PASS** | 0.0 s | 13 examples |
| every shipped example passes `netdryrun validate` (preflight, no deploy) | BLOCKER | **PASS** | 1.0 s | 13 examples |
| every topology we ship is named ndr-* | BLOCKER | **PASS** | 0.0 s | 97 topologies |
| no retired public string outside the history (CHANGELOG, advisories, records) | BLOCKER | **PASS** | 0.0 s | none |
| no unexplained FAIL/UNKNOWN -> PASS against the base (fastfix_gate.py loosening) | BLOCKER | **PASS** | 38.2 s | clean since 7db9bce2a5, by this checkout's fastfix_gate.py (the base predates it) |
| every src/ commit names an independent oracle that failed before it, or says why not (fastfix_gate.py reproduce) | BLOCKER | **PASS** | 1.9 min | clean since 7db9bce2a5, by this checkout's fastfix_gate.py (the base predates it) |
| CHANGELOG has no Unreleased entries left (all under 0.4.2) | BLOCKER | **PASS** | 0.0 s | cut |
| corpus v1: the committed results ran on this verdict code (G3) | BLOCKER | **PASS** | 0.0 s | fresh |
| corpus v2: the committed results ran on this verdict code (G3) | BLOCKER | **PASS** | 0.0 s | fresh |
| tag v0.4.2 does not exist yet | BLOCKER | **PASS** | 0.0 s | unused |
| PyPI has no netdryrun 0.4.2 yet | BLOCKER | **PASS** | 0.0 s | HTTP 404 |

## Layer 2: unit tests on every supported Python

Commit `79de75984253ec3727bb35fc2aec14bc957ea103` on `HEAD`; 2026-11-20 21:54:22 UTC; 14.3 min; Linux 6.18.58.1-microsoft-standard-WSL2 (x86_64); Python 3.12.16; --strict.

Tools: docker 29.9.2; uv 0.13.6 (x86_64-unknown-linux-gnu).

| Check | Severity | Result | Time | Notes |
|---|---|---|---|---|
| unit tests on Python 3.10.12 | BLOCKER | **PASS** | 2.6 min | 7958 passed, 66 skipped, 1 xfailed |
| unit tests on Python 3.11.18 | BLOCKER | **PASS** | 2.2 min | 7958 passed, 66 skipped, 1 xfailed |
| unit tests on Python 3.12.16 (with coverage) | BLOCKER | **PASS** | 3.1 min | 7958 passed, 66 skipped, 1 xfailed, 23 warnings |
| coverage of the verdict modules at or above the floors | MAJOR | **PASS** | 0.0 s | all at or above their floors |
| unit tests on Python 3.13.18 | BLOCKER | **PASS** | 2.2 min | 7958 passed, 66 skipped, 1 xfailed, 23 warnings |
| unit tests on Python 3.14.10 | BLOCKER | **PASS** | 2.2 min | 7958 passed, 66 skipped, 1 xfailed |
| unit tests in a plain python:3.12-slim container (no containerlab, no Docker) | BLOCKER | **PASS** | 1.9 min | 7836 passed, 188 skipped, 1 xfailed |

**Coverage of the verdict modules** (lines and branches, Python 3.12):

| Module | Lines | Branches | Covered | Floor |
|---|---|---|---|---|
| `src/netdryrun/checks.py` | 370/372 | 172/174 | 99.3% | 99% |
| `src/netdryrun/config.py` | 588/592 | 341/344 | 99.3% | 99% |
| `src/netdryrun/runner.py` | 1141/1148 | 554/560 | 99.2% | 98% |
| `src/netdryrun/drivers/` | 3204/3214 | 1318/1330 | 99.5% | 99% |
| `src/netdryrun/verify/engine.py` | 487/488 | 229/230 | 99.7% | 98% |
| `src/netdryrun/verify/intent.py` | 349/352 | 169/172 | 98.9% | 97% |
| `src/netdryrun/verify/frr.py` | 596/641 | 299/340 | 91.2% | 88% |
| `src/netdryrun/verify/snapshot.py` | 402/426 | 133/156 | 91.9% | 90% |
| `src/netdryrun/verify/converge.py` | 73/75 | 29/30 | 97.1% | 96% |
| `src/netdryrun/verify/run.py` | 488/547 | 175/210 | 87.6% | 83% |
| `src/netdryrun/verify/report.py` | 203/224 | 86/102 | 88.7% | 88% |
| `src/netdryrun/faults.py` | 276/283 | 108/112 | 97.2% | 96% |
| `src/netdryrun/mgmt.py` | 490/492 | 220/220 | 99.7% | 98% |

## Layer 4: mutation testing

Commit `79de75984253ec3727bb35fc2aec14bc957ea103` on `HEAD`; 2026-11-21 06:19:32 UTC; 206.1 min; Linux 6.18.58.1-microsoft-standard-WSL2 (x86_64); Python 3.12.16; --strict.

Tools: mutmut python -m mutmut, version 3.8.1.

| Check | Severity | Result | Time | Notes |
|---|---|---|---|---|
| no surviving mutants in src/netdryrun/checks.py | BLOCKER | **PASS** | 197.9 min | 1582 generated, 1542/1582 caught (97.5%); not caught: 40 survived the tests, 0 in code no test runs, 40 accepted (32 equivalent, 8 message-text) |
| no surviving mutants in src/netdryrun/config.py | BLOCKER | **PASS** | 0.0 s | 1882 generated, 1779/1882 caught (94.5%); not caught: 103 survived the tests, 0 in code no test runs, 103 accepted (31 equivalent, 72 message-text) |
| no surviving mutants in src/netdryrun/runner.py | BLOCKER | **PASS** | 0.0 s | 3323 generated, 3177/3323 caught (95.6%); not caught: 146 survived the tests, 0 in code no test runs, 146 accepted (63 equivalent, 5 logging, 68 message-text, 5 safety, 5 timing-only) |
| no surviving mutants in src/netdryrun/drivers/ | BLOCKER | **PASS** | 0.0 s | 7988 generated, 7635/7988 caught (95.6%); not caught: 353 survived the tests, 0 in code no test runs, 353 accepted (140 equivalent, 211 message-text, 2 safety) |
| no surviving mutants in src/netdryrun/verify/engine.py | BLOCKER | **PASS** | 0.0 s | 1597 generated, 1534/1597 caught (96.1%); not caught: 63 survived the tests, 0 in code no test runs, 63 accepted (27 equivalent, 36 message-text) |
| no surviving mutants in src/netdryrun/verify/intent.py | BLOCKER | **PASS** | 0.0 s | 1146 generated, 1023/1146 caught (89.3%); not caught: 123 survived the tests, 0 in code no test runs, 123 accepted (14 equivalent, 109 message-text) |
| no surviving mutants in src/netdryrun/verify/frr.py | BLOCKER | **PASS** | 0.0 s | 2816 generated, 1983/2816 caught (70.4%); not caught: 833 survived the tests, 0 in code no test runs, 2 accepted (2 equivalent); 831 outside the gated functions (parsers that fail closed and rendering; their full zero is a 0.4.1 gate item) |
| no surviving mutants in src/netdryrun/verify/snapshot.py | BLOCKER | **PASS** | 0.0 s | 1108 generated, 828/1108 caught (74.7%); not caught: 280 survived the tests, 0 in code no test runs; 280 outside the gated functions (parsers that fail closed and rendering; their full zero is a 0.4.1 gate item) |
| no surviving mutants in src/netdryrun/verify/converge.py | BLOCKER | **PASS** | 0.0 s | 157 generated, 143/157 caught (91.1%); not caught: 14 survived the tests, 0 in code no test runs, 2 accepted (2 equivalent); 12 outside the gated functions (parsers that fail closed and rendering; their full zero is a 0.4.1 gate item) |
| no surviving mutants in src/netdryrun/verify/run.py | BLOCKER | **PASS** | 0.0 s | 1444 generated, 1206/1444 caught (83.5%); not caught: 238 survived the tests, 0 in code no test runs, 7 accepted (7 equivalent); 231 outside the gated functions (parsers that fail closed and rendering; their full zero is a 0.4.1 gate item) |
| no surviving mutants in src/netdryrun/verify/report.py | BLOCKER | **PASS** | 0.0 s | 842 generated, 535/842 caught (63.5%); not caught: 307 survived the tests, 0 in code no test runs; 307 outside the gated functions (parsers that fail closed and rendering; their full zero is a 0.4.1 gate item) |
| no surviving mutants in src/netdryrun/faults.py | BLOCKER | **PASS** | 0.0 s | 831 generated, 743/831 caught (89.4%); not caught: 88 survived the tests, 0 in code no test runs, 13 accepted (13 equivalent); 75 outside the gated functions (parsers that fail closed and rendering; their full zero is a 0.4.1 gate item) |
| no surviving mutants in src/netdryrun/mgmt.py | BLOCKER | **PASS** | 0.0 s | 1715 generated, 1690/1715 caught (98.5%); not caught: 25 survived the tests, 0 in code no test runs, 25 accepted (25 equivalent) |

**src/netdryrun/verify/frr.py: 831 survivors outside the gated functions** (parsers that fail closed and rendering; their full zero is a 0.4.1 gate item): `verify.frr._nexthop` 142, `verify.frr.parse_attrs` 142, `verify.frr.parse_routes` 88, `verify.frr.parse_neighbors` 72, `verify.frr._parse_received` 58, `verify.frr.parse_bgp_table` 53, `verify.frr.parse_adj` 52, `verify.frr.show_command` 38, `verify.frr.parse_path` 33, `verify.frr._nexthops` 23, `verify.frr.FrrCollector._collect_items` 22, `verify.frr._dest_paths` 21, `verify.frr.FrrCollector._vtysh` 13, `verify.frr.FrrCollector._collect` 10, `verify.frr._check_total` 8, `verify.frr._obj` 8, `verify.frr._vrf` 8, `verify.frr._best_sent` 7, `verify.frr._str` 7, `verify.frr._communities` 6, `verify.frr._add_path_rx` 5, `verify.frr._int` 4, `verify.frr.sent_counters` 3, `verify.frr._opt_int` 2, `verify.frr.adv_intervals` 2, `verify.frr._bad` 1, `verify.frr._flag` 1, `verify.frr.add_path_tx` 1, `verify.frr.FrrCollector.__init__` 1

**src/netdryrun/verify/snapshot.py: 280 survivors outside the gated functions** (parsers that fail closed and rendering; their full zero is a 0.4.1 gate item): `verify.snapshot.Snapshot.from_json` 41, `verify.snapshot.AsPath.build` 32, `verify.snapshot.decode` 31, `verify.snapshot.BgpAttrs.__post_init__` 27, `verify.snapshot.AsPath.parse` 22, `verify.snapshot.AsPath.__post_init__` 20, `verify.snapshot.AsPath.render` 20, `verify.snapshot.parse_asn` 13, `verify.snapshot.canon_ext_communities` 9, `verify.snapshot.canon_prefix` 9, `verify.snapshot.NextHop.__post_init__` 8, `verify.snapshot.canon_ip` 7, `verify.snapshot.BgpPath.__post_init__` 6, `verify.snapshot.ItemKey.where` 6, `verify.snapshot.canon_community` 5, `verify.snapshot.Session.__post_init__` 5, `verify.snapshot._typed` 4, `verify.snapshot.canon_large_community` 4, `verify.snapshot.RibEntry.__post_init__` 4, `verify.snapshot.canon_ext_community` 3, `verify.snapshot.Snapshot.to_json` 3, `verify.snapshot.PathNextHop.__post_init__` 1

**src/netdryrun/verify/converge.py: 12 survivors outside the gated functions** (parsers that fail closed and rendering; their full zero is a 0.4.1 gate item): `verify.converge._moving` 12

**src/netdryrun/verify/run.py: 231 survivors outside the gated functions** (parsers that fail closed and rendering; their full zero is a 0.4.1 gate item): `verify.run.verify` 63, `verify.run.materialize` 37, `verify.run.bind_sources` 24, `verify.run._git` 20, `verify.run.expand_bind` 16, `verify.run._hash_binds` 14, `verify.run._extract` 11, `verify.run.load_guards` 11, `verify.run._cat_files` 9, `verify.run._is_ref` 5, `verify.run.intent_edited` 5, `verify.run._files` 4, `verify.run.resolve_bind` 4, `verify.run._hint` 3, `verify.run._now` 1, `verify.run._real` 1, `verify.run.confirm_by_rerun` 1, `verify.run.expects_bgp` 1, `verify.run.Side.locate` 1

**src/netdryrun/verify/report.py: 307 survivors outside the gated functions** (parsers that fail closed and rendering; their full zero is a 0.4.1 gate item): `verify.report.markdown` 142, `verify.report.console` 92, `verify.report._summary` 25, `verify.report.item_json` 25, `verify.report._intent_json` 6, `verify.report._plain_yaml` 6, `verify.report.to_json` 6, `verify.report._diag` 5

**src/netdryrun/faults.py: 75 survivors outside the gated functions** (parsers that fail closed and rendering; their full zero is a 0.4.1 gate item): `faults.conflicts` 17, `faults.RouteInjection._apply_config` 13, `faults.parse_inject` 11, `faults.RouteInjection._vtysh` 11, `faults.RouteInjection.__init__` 10, `faults.RouteInjection._wait` 8, `faults.config_lines` 4, `faults.RouteInjection._as_path` 1

**Accepted entries that no longer survive** (496; remove them from accepted.json): `netdryrun.checks.x__bgp_route__mutmut_129`, `netdryrun.checks.x__bgp_route__mutmut_134`, `netdryrun.checks.x__bgp_route__mutmut_18`, `netdryrun.checks.x__bgp_route__mutmut_20`, `netdryrun.checks.x__bgp_route__mutmut_32`, `netdryrun.checks.x__bgp_route__mutmut_33`, `netdryrun.checks.x__bgp_route__mutmut_59`, `netdryrun.checks.x__describe_path__mutmut_10`, `netdryrun.checks.x__describe_path__mutmut_12`, `netdryrun.checks.x__describe_path__mutmut_13`, `netdryrun.checks.x__describe_path__mutmut_14`, `netdryrun.checks.x__describe_path__mutmut_16`, `netdryrun.checks.x__describe_path__mutmut_4`, `netdryrun.checks.x__describe_path__mutmut_6`, `netdryrun.checks.x__describe_path__mutmut_7`, `netdryrun.checks.x__describe_path__mutmut_8`, `netdryrun.checks.x__ping__mutmut_37`, `netdryrun.checks.x__ping__mutmut_39`, `netdryrun.checks.x__ping__mutmut_41`, `netdryrun.checks.x__ping__mutmut_44`, `netdryrun.checks.x__ping__mutmut_46`, `netdryrun.checks.x__ping__mutmut_48`, `netdryrun.checks.x__ping__mutmut_51`, `netdryrun.checks.x__ping__mutmut_56`, `netdryrun.checks.x__ping__mutmut_58`, `netdryrun.checks.x__ping__mutmut_60`, `netdryrun.checks.x__ping__mutmut_63`, `netdryrun.checks.x__ping__mutmut_64`, `netdryrun.checks.x__ping__mutmut_65`, `netdryrun.checks.x__ping__mutmut_67`, `netdryrun.checks.x__ping__mutmut_69`, `netdryrun.checks.x__ping__mutmut_72`, `netdryrun.checks.x__ping__mutmut_73`, `netdryrun.checks.x__ping__mutmut_74`, `netdryrun.checks.x__ping__mutmut_75`, `netdryrun.checks.x__ping__mutmut_76`, `netdryrun.checks.x__ping__mutmut_79`, `netdryrun.checks.x__ping__mutmut_81`, `netdryrun.checks.x__ping__mutmut_82`, `netdryrun.checks.x__ping__mutmut_83` ...

**Surviving mutants by function** (2613 in all; every diff is in [mutants.md](mutants.md)):

| Function | Survivors |
|---|---|
| `verify.frr._nexthop` | 142 |
| `verify.frr.parse_attrs` | 142 |
| `verify.report.markdown` | 142 |
| `verify.report.console` | 92 |
| `verify.frr.parse_routes` | 88 |
| `verify.frr.parse_neighbors` | 72 |
| `verify.run.verify` | 63 |
| `verify.frr._parse_received` | 58 |
| `verify.frr.parse_bgp_table` | 53 |
| `verify.frr.parse_adj` | 52 |
| `verify.snapshot.Snapshot.from_json` | 41 |
| `verify.frr.show_command` | 38 |
| `verify.run.materialize` | 37 |
| `verify.frr.parse_path` | 33 |
| `verify.snapshot.AsPath.build` | 32 |
| `verify.snapshot.decode` | 31 |
| `config._validate_scenario` | 30 |
| `runner._bgp_convergence_gate` | 29 |
| `verify.intent._line` | 27 |
| `verify.snapshot.BgpAttrs.__post_init__` | 27 |
| `verify.intent._glob` | 25 |
| `verify.report._summary` | 25 |
| `verify.report.item_json` | 25 |
| `drivers.srlinux._received` | 24 |
| `verify.run.bind_sources` | 24 |
| `verify.frr._nexthops` | 23 |
| `runner._link_sessions` | 22 |
| `verify.frr.FrrCollector._collect_items` | 22 |
| `verify.snapshot.AsPath.parse` | 22 |
| `verify.frr._dest_paths` | 21 |
| `verify.intent._attr` | 21 |
| `checks._ping` | 20 |
| `verify.run._git` | 20 |
| `verify.snapshot.AsPath.__post_init__` | 20 |
| `verify.snapshot.AsPath.render` | 20 |
| `faults.conflicts` | 17 |
| `drivers.eos._summary` | 16 |
| `verify.run.expand_bind` | 16 |
| `config._validate_check` | 15 |
| `runner._yaml_problem` | 15 |
| `verify.run._hash_binds` | 14 |
| `faults.RouteInjection._apply_config` | 13 |
| `verify.frr.FrrCollector._vtysh` | 13 |
| `verify.snapshot.parse_asn` | 13 |
| `drivers.eos._as_path` | 12 |
| `verify.converge._moving` | 12 |
| `verify.intent.parse_intent` | 12 |
| `faults.RouteInjection._vtysh` | 11 |
| `faults.parse_inject` | 11 |
| `verify.engine._session` | 11 |
| `verify.run._extract` | 11 |
| `verify.run.load_guards` | 11 |
| `config._validate_bgp_route` | 10 |
| `drivers.frr.gr_stale_window` | 10 |
| `faults.RouteInjection.__init__` | 10 |
| `runner.run_scenario` | 10 |
| `verify.frr.FrrCollector._collect` | 10 |
| `config.load` | 9 |
| `drivers.nxos._as_path` | 9 |
| `drivers.srlinux.SrlDriver._read_path` | 9 |
| `runner._shape_problem` | 9 |
| `verify.intent._allow` | 9 |
| `verify.run._cat_files` | 9 |
| `verify.snapshot.canon_ext_communities` | 9 |
| `verify.snapshot.canon_prefix` | 9 |
| `config._describe` | 8 |
| `drivers.eos.EosDriver._add_path_ranges` | 8 |
| `drivers.eos._vrf` | 8 |
| `drivers.frr.count_neighbor_prefixes` | 8 |
| `drivers.frr.frr_eor` | 8 |
| `faults.RouteInjection._wait` | 8 |
| `runner._wait_fault_visible` | 8 |
| `runner.load_config` | 8 |
| `runner.run` | 8 |
| `verify.engine._pins_ok` | 8 |
| `verify.engine.match` | 8 |
| `verify.frr._check_total` | 8 |
| `verify.frr._obj` | 8 |
| `verify.frr._vrf` | 8 |
| `verify.snapshot.NextHop.__post_init__` | 8 |
| `config._reject_unknown` | 7 |
| `drivers.nxos._bgp_prefix_rows` | 7 |
| `faults.RouteInjection.advertised` | 7 |
| `runner._NodeWatch.__call__` | 7 |
| `verify.engine._best_path` | 7 |
| `verify.frr._best_sent` | 7 |
| `verify.frr._str` | 7 |
| `verify.intent.check_nodes` | 7 |
| `verify.snapshot.canon_ip` | 7 |
| `drivers.base.load_json` | 6 |
| `drivers.frr._bgp_json` | 6 |
| `drivers.frr._learned` | 6 |
| `drivers.frr.parse_paths_available` | 6 |
| `drivers.junos._as_path` | 6 |
| `drivers.srlinux._list` | 6 |
| `verify.engine._advertisement` | 6 |
| `verify.engine.baseline_problems` | 6 |
| `verify.frr._communities` | 6 |
| `verify.report._intent_json` | 6 |
| `verify.report._plain_yaml` | 6 |
| `verify.report.to_json` | 6 |
| `verify.snapshot.BgpPath.__post_init__` | 6 |
| `verify.snapshot.ItemKey.where` | 6 |
| `config.load_yaml` | 5 |
| `drivers.nxos._prefix_rows` | 5 |
| `drivers.srlinux._json` | 5 |
| `drivers.srlinux.srl_eor` | 5 |
| `runner._link_end` | 5 |
| `runner._reach_then_hold` | 5 |
| `verify.frr._add_path_rx` | 5 |
| `verify.report._diag` | 5 |
| `verify.run._is_ref` | 5 |
| `verify.run.intent_edited` | 5 |
| `verify.snapshot.Session.__post_init__` | 5 |
| `verify.snapshot.canon_community` | 5 |
| `checks._evaluate_all` | 4 |
| `config._StrictLoader._check_keys` | 4 |
| `drivers.base.Driver.bgp_received` | 4 |
| `drivers.eos._bgp_entries` | 4 |
| `drivers.eos._json` | 4 |
| `drivers.eos._table` | 4 |
| `drivers.frr.FrrDriver._confirm_vrf` | 4 |
| `drivers.frr.FrrDriver.bgp_neighbors` | 4 |
| `drivers.frr.FrrDriver.local_addresses` | 4 |
| `drivers.frr._withdrawn` | 4 |
| `drivers.frr.add_path_rx` | 4 |
| `drivers.frr.listed_stale` | 4 |
| `drivers.junos._next_hop` | 4 |
| `drivers.nxos._withdrawn` | 4 |
| `drivers.routeros.RouterosDriver._v4_prefix` | 4 |
| `drivers.srlinux._count_add_path_prefixes` | 4 |
| `drivers.srlinux._in_fib` | 4 |
| `drivers.srlinux._rib_rows` | 4 |
| `faults.config_lines` | 4 |
| `mgmt._eos_only_kernel_defaults` | 4 |
| `mgmt.parse_ip_route` | 4 |
| `runner._far_ends` | 4 |
| `verify.engine._flat` | 4 |
| `verify.engine.path_view` | 4 |
| `verify.frr._int` | 4 |
| `verify.intent.Allow.matches` | 4 |
| `verify.intent._attrs` | 4 |
| `verify.intent.parse_intent_text` | 4 |
| `verify.run._files` | 4 |
| `verify.run.resolve_bind` | 4 |
| `verify.snapshot.RibEntry.__post_init__` | 4 |
| `verify.snapshot._typed` | 4 |
| `verify.snapshot.canon_large_community` | 4 |
| `checks._bgp_prefixes` | 3 |
| `checks.run_round_robin` | 3 |
| `config.Fault.describe` | 3 |
| `config._suggest` | 3 |
| `config.normalize_as_path` | 3 |
| `drivers.base.Driver._exec` | 3 |
| `drivers.base.Driver.all_routes` | 3 |
| `drivers.base.unexpected` | 3 |
| `drivers.eos.parse_startup_config_errors` | 3 |
| `drivers.junos._adv_interval` | 3 |
| `drivers.nxos.parse_startup_log` | 3 |
| `drivers.routeros.RouterosDriver.bgp_paths` | 3 |
| `drivers.srlinux._protocol` | 3 |
| `drivers.srlinux.srl_add_path_rx` | 3 |
| `mgmt.classify_eos` | 3 |
| `runner._routeros_peer` | 3 |
| `runner.preflight` | 3 |
| `verify.engine.config_lines_changed` | 3 |
| `verify.frr.sent_counters` | 3 |
| `verify.intent._prefix` | 3 |
| `verify.run._hint` | 3 |
| `verify.run.bind_reach` | 3 |
| `verify.snapshot.Snapshot.to_json` | 3 |
| `verify.snapshot.canon_ext_community` | 3 |
| `checks._describe_path` | 2 |
| `checks._reach_view` | 2 |
| `checks.inconclusive_reason` | 2 |
| `config._StrictLoader.construct_mapping` | 2 |
| `drivers.base.Driver.bgp_neighbors` | 2 |
| `drivers.base.Driver.bgp_paths` | 2 |
| `drivers.base.Driver.local_addresses` | 2 |
| `drivers.base.Driver.ping` | 2 |
| `drivers.base.Driver.routes` | 2 |
| `drivers.base.check_vrf_name` | 2 |
| `drivers.base.network` | 2 |
| `drivers.eos.EosDriver._bgp_cli` | 2 |
| `drivers.eos.EosDriver.bgp_paths` | 2 |
| `drivers.eos._programmed` | 2 |
| `drivers.frr.FrrDriver.bgp_paths` | 2 |
| `drivers.frr.parse_config_load_errors` | 2 |
| `drivers.junos.JunosDriver.bgp_paths` | 2 |
| `drivers.junos.JunosDriver.local_addresses` | 2 |
| `drivers.junos._afi` | 2 |
| `drivers.junos._destination` | 2 |
| `drivers.junos._filtered` | 2 |
| `drivers.junos._refuse_stale` | 2 |
| `drivers.junos._state` | 2 |
| `drivers.junos._strip_port` | 2 |
| `drivers.junos.parse_management_routes` | 2 |
| `drivers.nxos.NxosDriver.bgp_paths` | 2 |
| `drivers.nxos._communities` | 2 |
| `drivers.nxos._reply` | 2 |
| `drivers.nxos._rib_routes` | 2 |
| `drivers.nxos._rows` | 2 |
| `drivers.nxos.nxos_eor_text` | 2 |
| `drivers.srlinux.SrlDriver.bgp_paths` | 2 |
| `drivers.srlinux.SrlDriver.local_addresses` | 2 |
| `drivers.srlinux.parse_instance_state` | 2 |
| `faults.RouteInjection._is_injected` | 2 |
| `faults.RouteInjection.record_listed` | 2 |
| `mgmt._scan_eos` | 2 |
| `mgmt.prepare_linux` | 2 |
| `runner._check_declared_peers` | 2 |
| `runner._sonic_config_bind` | 2 |
| `verify.converge.stable_snapshot` | 2 |
| `verify.engine.RouteView.best` | 2 |
| `verify.engine.attrs_view` | 2 |
| `verify.frr._opt_int` | 2 |
| `verify.frr.adv_intervals` | 2 |
| `verify.intent._ip` | 2 |
| `verify.intent.load_intent` | 2 |
| `verify.run.check_changed_binds` | 2 |
| `checks._bgp_route` | 1 |
| `checks._not_configured` | 1 |
| `checks._via` | 1 |
| `checks.converge_then_hold` | 1 |
| `config._is_network` | 1 |
| `config._only` | 1 |
| `config._validate_peers` | 1 |
| `config.parse_community` | 1 |
| `drivers.base.Driver.__init_subclass__` | 1 |
| `drivers.base.RepeatedKey.__init__` | 1 |
| `drivers.base.Route.__post_init__` | 1 |
| `drivers.base.as_int` | 1 |
| `drivers.base.must_bool` | 1 |
| `drivers.base.no_repeated_keys` | 1 |
| `drivers.check_supported` | 1 |
| `drivers.eos.EosDriver.all_routes` | 1 |
| `drivers.frr.FrrDriver.all_routes` | 1 |
| `drivers.frr._bgp_paths_for_route_check` | 1 |
| `drivers.frr._bgp_paths_raw` | 1 |
| `drivers.junos.JunosDriver._count_hidden` | 1 |
| `drivers.junos.JunosDriver.all_routes` | 1 |
| `drivers.junos.JunosDriver.management_routes` | 1 |
| `drivers.junos._protocol` | 1 |
| `drivers.junos._tables` | 1 |
| `drivers.nxos.NxosDriver.all_routes` | 1 |
| `drivers.nxos._bgp_paths_raw` | 1 |
| `drivers.nxos._body` | 1 |
| `drivers.nxos._flag` | 1 |
| `drivers.nxos._learned` | 1 |
| `drivers.nxos._peer` | 1 |
| `drivers.nxos._vrf_rows` | 1 |
| `drivers.nxos.parse_ping_reply` | 1 |
| `drivers.routeros.RouterosDriver.all_routes` | 1 |
| `drivers.routeros.RouterosDriver.nos_version` | 1 |
| `drivers.routeros_rest.classify_reply` | 1 |
| `drivers.routeros_state.best_paths` | 1 |
| `drivers.srlinux.SrlDriver._drop_looped` | 1 |
| `drivers.srlinux.SrlDriver.all_routes` | 1 |
| `drivers.srlinux._counted_if_up` | 1 |
| `drivers.stale.refuse_llgr_stale` | 1 |
| `faults.RouteInjection._as_path` | 1 |
| `faults.RouteInjection.established` | 1 |
| `faults.RouteInjection.sessions` | 1 |
| `mgmt._await_answer` | 1 |
| `mgmt._eos` | 1 |
| `mgmt._eos_key` | 1 |
| `mgmt._in_mgmt_subnet` | 1 |
| `mgmt._scan_linux` | 1 |
| `mgmt.check_eos` | 1 |
| `mgmt.check_linux` | 1 |
| `mgmt.check_node` | 1 |
| `mgmt.prepare` | 1 |
| `mgmt.prepare_eos` | 1 |
| `runner._NodeWatch.__init__` | 1 |
| `runner._container_iface` | 1 |
| `runner._names_iface` | 1 |
| `runner._routing_nodes` | 1 |
| `runner._sessions_over_links` | 1 |
| `runner._stretch_for_advertisement_intervals` | 1 |
| `verify.engine._propagated` | 1 |
| `verify.engine.changed_fields` | 1 |
| `verify.frr.FrrCollector.__init__` | 1 |
| `verify.frr._bad` | 1 |
| `verify.frr._flag` | 1 |
| `verify.frr.add_path_tx` | 1 |
| `verify.frr.configured_link_locals` | 1 |
| `verify.frr.parse_link_local` | 1 |
| `verify.intent._groups` | 1 |
| `verify.intent._int_or_null` | 1 |
| `verify.intent._nodes` | 1 |
| `verify.run.Side.locate` | 1 |
| `verify.run._now` | 1 |
| `verify.run._real` | 1 |
| `verify.run.classify_nodes` | 1 |
| `verify.run.confirm_by_rerun` | 1 |
| `verify.run.expects_bgp` | 1 |
| `verify.run.unobserved_reasons` | 1 |
| `verify.snapshot.PathNextHop.__post_init__` | 1 |

## Layer 5: live matrix on the built package

Commit `79de75984253ec3727bb35fc2aec14bc957ea103` on `HEAD`; 2026-11-20 22:09:05 UTC; 239.0 min; Linux 6.18.58.1-microsoft-standard-WSL2 (x86_64); Python 3.12.16; --strict.

Tools: containerlab ⣴⡾⠛⠛⠖ ⢠⣶⠟⠛⢷⣦ ⢸⣿⣧ ⣿ ⠘⠛⢻⡟⠛⠛ ⣾⣿⡀ ⣿⡇ ⣿⣿⡄ ⢸⡇ ⣿⡟⠛⠛⠃⢸⣿⠛⠛⣷⡄ [38;2;0;201;255m⣿⡇[0m ; docker 29.9.2.

| Check | Severity | Result | Time | Notes |
|---|---|---|---|---|
| build the wheel and the sdist | BLOCKER | **PASS** | 1.3 s | netdryrun-0.4.2-py3-none-any.whl |
| the wheel and the sdist carry NOTICE (Apache-2.0 section 4(d)) | BLOCKER | **PASS** | 0.0 s | both carry it |
| install netdryrun-0.4.2-py3-none-any.whl in a fresh venv | BLOCKER | **PASS** | 0.1 s |  |
| runs the installed package, not the source tree | BLOCKER | **PASS** | 0.0 s | /tmp/ndr-gate-live-dv5xmnhm/venv/lib/python3.12/site-packages/netdryrun/__init__.py |
| the installed wheel's verdict modules are the source's | BLOCKER | **PASS** | 0.0 s | installed 690f560574f1, source 690f560574f1 |
| netdryrun --version says 0.4.2 | BLOCKER | **PASS** | 0.0 s | netdryrun 0.4.2 |
| example agent-demo: `Demo OK`, exit 0 | BLOCKER | **PASS** | 1.6 min | exit 0: Demo OK: attempt 1 rejected by 5 leak guards with every other check passing; attempt 2 passed every check. |
| example agent-demo: no lab left running | BLOCKER | **PASS** | 0.0 s | none left |
| example arista-frr: `PASSED: 10 passed, 0 failed`, exit 0 | BLOCKER | **PASS** | 2.0 min | exit 0: PASSED: 10 passed, 0 failed (10 checks) |
| example arista-frr: no lab left running | BLOCKER | **PASS** | 0.0 s | none left |
| example batfish-pipeline: `PASSED: 10 passed, 0 failed`, exit 0 | BLOCKER | **PASS** | 1.9 min | exit 0: PASSED: 10 passed, 0 failed (10 checks) |
| example batfish-pipeline: no lab left running | BLOCKER | **PASS** | 0.0 s | none left |
| example frr-bgp: `PASSED: 11 passed, 0 failed`, exit 0 | BLOCKER | **PASS** | 1.9 min | exit 0: PASSED: 11 passed, 0 failed (11 checks) |
| example frr-bgp: no lab left running | BLOCKER | **PASS** | 0.0 s | none left |
| example frr-bgp-broken: `FAILED: 5 passed, 1 failed`, exit 1 | BLOCKER | **PASS** | 50.2 s | exit 1: FAILED: 5 passed, 1 failed (6 checks) |
| example frr-bgp-broken: no lab left running | BLOCKER | **PASS** | 0.0 s | none left |
| example frr-customer-leak: `FAILED: 19 passed, 2 failed`, exit 1 | BLOCKER | **PASS** | 76.2 s | exit 1: FAILED: 19 passed, 2 failed (21 checks) |
| example frr-customer-leak: no lab left running | BLOCKER | **PASS** | 0.0 s | none left |
| example junos-frr: `PASSED: 13 passed, 0 failed`, exit 0 | BLOCKER | **PASS** | 5.1 min | exit 0: PASSED: 13 passed, 0 failed (13 checks) |
| example junos-frr: no lab left running | BLOCKER | **PASS** | 0.0 s | none left |
| example leak-pattern: `PASSED: 8 passed, 0 failed`, exit 0 | BLOCKER | **PASS** | 62.7 s | exit 0: PASSED: 8 passed, 0 failed (8 checks) |
| example leak-pattern: no lab left running | BLOCKER | **PASS** | 0.0 s | none left |
| example mikrotik: `PASSED: 10 passed, 0 failed`, exit 0 | BLOCKER | **PASS** | 1.6 min | exit 0: PASSED: 10 passed, 0 failed (10 checks; 1 with a convergence warning) |
| example mikrotik: no lab left running | BLOCKER | **PASS** | 0.0 s | none left |
| example nxos-frr: `PASSED: 10 passed, 0 failed`, exit 0 | BLOCKER | **PASS** | 5.7 min | exit 0: PASSED: 10 passed, 0 failed (10 checks; 1 with a convergence warning) |
| example nxos-frr: no lab left running | BLOCKER | **PASS** | 0.0 s | none left |
| example sonic-frr: `PASSED: 8 passed, 0 failed`, exit 0 | BLOCKER | **PASS** | 2.0 min | exit 0: PASSED: 8 passed, 0 failed (8 checks) |
| example sonic-frr: no lab left running | BLOCKER | **PASS** | 0.0 s | none left |
| example srl-frr: `PASSED: 7 passed, 0 failed`, exit 0 | BLOCKER | **PASS** | 66.6 s | exit 0: PASSED: 7 passed, 0 failed (7 checks) |
| example srl-frr: no lab left running | BLOCKER | **PASS** | 0.0 s | none left |
| example srl-hidden-leak: `PASSED: 9 passed, 0 failed`, exit 0 | BLOCKER | **PASS** | 66.0 s | exit 0: PASSED: 9 passed, 0 failed (9 checks) |
| example srl-hidden-leak: no lab left running | BLOCKER | **PASS** | 0.0 s | none left |
| example srl-hidden-leak with leaks/frr1.conf: `FAILED: 8 passed, 1 failed`, exit 1 | BLOCKER | **PASS** | 65.3 s | exit 1: FAILED: 8 passed, 1 failed (9 checks) |
| example srl-hidden-leak with leaks/frr1.conf: no lab left running | BLOCKER | **PASS** | 0.0 s | none left |
| example srl-hidden-leak with leaks/srl1.cli: `FAILED: 8 passed, 1 failed`, exit 1 | BLOCKER | **PASS** | 66.3 s | exit 1: FAILED: 8 passed, 1 failed (9 checks) |
| example srl-hidden-leak with leaks/srl1.cli: no lab left running | BLOCKER | **PASS** | 0.0 s | none left |
| example times match the docs (within 2x) | MAJOR | **PASS** | 0.0 s | all within 2x |
| Verdict Corpus v1: every verdict matches the committed results.json | BLOCKER | **PASS** | 80.8 min | all verdicts match |
| Verdict Corpus v1: every case records a status, none an error | BLOCKER | **PASS** | 0.0 s | all recorded, no error |
| Verdict Corpus v1: no harmful change approved beyond the published known misses | BLOCKER | **PASS** | 0.0 s | harmful changes approved: 5 (12-ibgp-send-community-dropped, 18-redistribute-connected, 21-customer-max-prefix-removed, 23-fat-finger-third-party-origin, 30-peer-import-filter-removed); published known misses: 12-ibgp-send-community-dropped, 18-redistribute-connected, 21-customer-max-prefix-removed, 23-fat-finger-third-party-origin, 30-peer-import-filter-removed |
| Verdict Corpus v1: no lab left running | BLOCKER | **PASS** | 0.0 s | none left |
| Verdict Corpus v2: every verdict matches the committed results.json | BLOCKER | **PASS** | 125.9 min | all verdicts match |
| Verdict Corpus v2: every case records a status, none an error | BLOCKER | **PASS** | 0.0 s | all recorded, no error |
| Verdict Corpus v2: the nondeterministic exemption holds (pinned, exact runs bound to the case's checks, no crash, no approval) | BLOCKER | **PASS** | 0.0 s | 18-aggregate-discard-route-removed |
| Verdict Corpus v2: every nondeterministic case was caught in at least one run | BLOCKER | **PASS** | 0.0 s | every case caught in at least one run |
| Verdict Corpus v2: nondeterministic cases recorded (known, not scored, never a blocker) | INFO | **PASS** | 0.0 s | Netdryrun verdicts per run: 18-aggregate-discard-route-removed: error, error, error, unsafe, unsafe |
| Verdict Corpus v2: no harmful change approved beyond the published known misses | BLOCKER | **PASS** | 0.0 s | harmful changes approved: 0 (none); published known misses: none |
| Verdict Corpus v2: no lab left running | BLOCKER | **PASS** | 0.0 s | none left |
| MCP handshake against the installed wheel | BLOCKER | **PASS** | 1.0 s | MCP handshake OK |
| check pack verification | MAJOR | **ACCEPTED** | 0.0 s | no --pack script given (accepted: No check pack is sold yet: pack verification is paused by the roadmap until the demand test; it runs with --pack before any pack ships. Same as 0.4.1.) |
| 20-node scale test | MAJOR | **ACCEPTED** | 0.0 s | not scripted in the repository yet: run it by hand (accepted: Still not scripted (planned since 0.4.1, not done; carried to the 0.4.3 list). A 20-node lab was run by hand in pre-launch testing (it found the PR-comment size limit, fixed in 0.3.1). 0.4.2 is a fix release and changes no report-size path.) |
| SIGINT during deploy: exit 130, a clear message | BLOCKER | **PASS** | 4.8 s | exit 130 |
| SIGINT during deploy: no lab left running | BLOCKER | **PASS** | 0.0 s | none left |
| SIGINT during checks: exit 130, a clear message | BLOCKER | **PASS** | 24.7 s | exit 130 |
| SIGINT during checks: no lab left running | BLOCKER | **PASS** | 0.0 s | none left |
| SIGTERM during deploy: exit 143, a clear message | BLOCKER | **PASS** | 4.8 s | exit 143 |
| SIGTERM during deploy: no lab left running | BLOCKER | **PASS** | 0.0 s | none left |
| SIGTERM during checks: exit 143, a clear message | BLOCKER | **PASS** | 24.9 s | exit 143 |
| SIGTERM during checks: no lab left running | BLOCKER | **PASS** | 0.0 s | none left |
| a node's image does not exist: exit 2 with a clear error | BLOCKER | **PASS** | 0.4 s | exit 2:   wrote json report: /tmp/ndr-gate-live-dv5xmnhm/reports/frr-bgp-missing-image.json |
| a node's image does not exist: no lab left running | BLOCKER | **PASS** | 0.0 s | none left |
| a node cannot be created (a bind source does not exist): exit 2 with a clear error | BLOCKER | **PASS** | 0.4 s | exit 2:   wrote json report: /tmp/ndr-gate-live-dv5xmnhm/reports/frr-bgp-deploy-fails.json |
| a node cannot be created (a bind source does not exist): no lab left running | BLOCKER | **PASS** | 0.0 s | none left |
| two runs of the same lab at once: no false verdict, no crash | BLOCKER | **PASS** | 1.9 min | exit codes 2 and 0 |
| two runs at once: no lab left running | BLOCKER | **PASS** | 0.0 s | none left |
| Docker restarts mid-run | MAJOR | **ACCEPTED** | 0.0 s | off by default (restarts every container on the machine): pass --chaos-docker-restart (accepted: Optional by RELEASING.md (Layer 5, Chaos): it restarts Docker, which stops every container on the machine, and the release runs on the one shared laptop (no separate lab machine since 2026-11-09). The other chaos cases in this live layer on f4b5e6a (SIGINT and SIGTERM in the deploy and in the checks, two runs of one lab at once, each with no lab left running) passed. Same decision as 0.4.1.) |

## Layer 5b: acceptance from five angles

Commit `79de75984253ec3727bb35fc2aec14bc957ea103` on `HEAD`; 2026-11-21 03:18:59 UTC; 171.6 min; Linux 6.18.58.1-microsoft-standard-WSL2 (x86_64); Python 3.12.16; --strict.

| Check | Severity | Result | Time | Notes |
|---|---|---|---|---|
| example frr-bgp (angle1/frr/example/frr-bgp) | BLOCKER | **PASS** | 1.9 min | exit 0, `PASSED: 11 passed, 0 failed (11 checks)` |
| example frr-bgp-broken (angle1/frr/example/frr-bgp-broken) | BLOCKER | **PASS** | 49.9 s | exit 1, `FAILED: 5 passed, 1 failed (6 checks)` |
| example frr-customer-leak (angle1/frr/example/frr-customer-leak) | BLOCKER | **PASS** | 76.2 s | exit 1, `FAILED: 19 passed, 2 failed (21 checks)` |
| example leak-pattern (angle1/frr/example/leak-pattern) | BLOCKER | **PASS** | 52.4 s | exit 0, `PASSED: 8 passed, 0 failed (8 checks)` |
| example leak-pattern, netdryrun-leaky.yml (angle1/frr/example/leak-pattern/netdryrun-leaky.yml) | BLOCKER | **PASS** | 52.3 s | exit 1, `FAILED: 6 passed, 2 failed (8 checks)` |
| example leak-pattern, netdryrun-roles.yml (angle1/frr/example/leak-pattern/netdryrun-roles.yml) | BLOCKER | **PASS** | 58.2 s | exit 0, `PASSED: 8 passed, 0 failed (8 checks)` |
| example batfish-pipeline (angle1/frr/example/batfish-pipeline) | BLOCKER | **PASS** | 1.9 min | exit 0, `PASSED: 10 passed, 0 failed (10 checks)` |
| example agent-demo (angle1/frr/example/agent-demo) | BLOCKER | **PASS** | 1.6 min | exit 0, `['Demo OK: attempt 1 rejected by 5 leak guards with every other check passing; attempt 2 passed every check.']` |
| ported must-fail change with a record baseline, and the vendor traps (angle1/frr/mustfail) | BLOCKER | **PASS** | 2.9 min | record: 28 checks; 14 traps failed as they must |
| example srl-frr (angle1/srlinux/example/srl-frr) | BLOCKER | **PASS** | 65.6 s | exit 0, `PASSED: 7 passed, 0 failed (7 checks)` |
| example srl-hidden-leak (angle1/srlinux/example/srl-hidden-leak) | BLOCKER | **PASS** | 65.1 s | exit 0, `PASSED: 9 passed, 0 failed (9 checks)` |
| example srl-hidden-leak, leaks/frr1.conf (angle1/srlinux/example/srl-hidden-leak/leak-frr1.conf) | BLOCKER | **PASS** | 64.8 s | exit 1, `FAILED: 8 passed, 1 failed (9 checks)` |
| example srl-hidden-leak, leaks/srl1.cli (angle1/srlinux/example/srl-hidden-leak/leak-srl1.cli) | BLOCKER | **PASS** | 65.8 s | exit 1, `FAILED: 8 passed, 1 failed (9 checks)` |
| ported must-fail change with a record baseline, and the vendor traps (angle1/srlinux/mustfail) | BLOCKER | **PASS** | 3.3 min | record: 11 checks + 1 by hand; record exit 1 on 3 known driver gap(s): INCOMPLETE BASELINE: srl1: BGP neighbor 10.0.100.2 ipv4-unicast: the prefix count is 0 to 1 (hidden routes Netdryrun can't classify); not recorded: add a check by hand \| INCOMPLETE BASELINE: srl1: no global address on e1-1 where Netdryrun reads it (unnumbered, or kept on another interface by the NOS); its link subnet has no guard \| INCOMPLETE BASELINE: srl1: the guard against 10.0.100.0/30 via BGP could not be evaluated on the lab (error: 10.0.100.0/30: the path from 10.0.100.2 is invalid for as-loop, rejected-route, a reason the srlinux driver doesn't read yet); not recorded: add it by hand once the node answers; 14 traps failed as they must |
| example sonic-frr (angle1/sonic/example/sonic-frr) | BLOCKER | **PASS** | 1.7 min | exit 0, `PASSED: 8 passed, 0 failed (8 checks)` |
| ported must-fail change with a record baseline, and the vendor traps (angle1/sonic/mustfail) | BLOCKER | **PASS** | 3.2 min | record: 14 checks; record exit 1 on 1 known driver gap(s): INCOMPLETE BASELINE: sonic1: no global address on eth1 where Netdryrun reads it (unnumbered, or kept on another interface by the NOS); its link subnet has no guard; 14 traps failed as they must |
| example arista-frr (angle1/eos/example/arista-frr) | BLOCKER | **PASS** | 1.9 min | exit 0, `PASSED: 10 passed, 0 failed (10 checks)` |
| ported must-fail change with a record baseline, and the vendor traps (angle1/eos/mustfail) | BLOCKER | **PASS** | 3.6 min | record: 13 checks; record exit 1 on 1 known driver gap(s): INCOMPLETE BASELINE: ceos1: could not read IPv6 routes (VRF 'default' has routing disabled (`show ip route \| json`): nothing routes there, so no route check means anything in it), so none is recorded as a check: fix the read and record again, or add checks by hand; 14 traps failed as they must |
| example junos-frr (angle1/junos/example/junos-frr) | BLOCKER | **PASS** | 4.6 min | exit 0, `PASSED: 13 passed, 0 failed (13 checks)` |
| example junos-frr, leaks/frr1.conf (angle1/junos/example/junos-frr/leak-frr1.conf) | BLOCKER | **PASS** | 4.8 min | exit 1, `FAILED: 12 passed, 1 failed (13 checks)` |
| example junos-frr, leaks/j1.cfg (angle1/junos/example/junos-frr/leak-j1.cfg) | BLOCKER | **PASS** | 4.9 min | exit 1, `FAILED: 12 passed, 1 failed (13 checks)` |
| ported must-fail change with a record baseline, and the vendor traps (angle1/junos/mustfail) | BLOCKER | **PASS** | 20.9 min | record: 24 checks; record exit 1 on 1 known driver gap(s): INCOMPLETE BASELINE: j1: no global address on eth4 where Netdryrun reads it (unnumbered, or kept on another interface by the NOS); its link subnet has no guard; 13 traps failed as they must |
| example nxos-frr (angle1/nxos/example/nxos-frr) | BLOCKER | **PASS** | 6.1 min | exit 0, `PASSED: 10 passed, 0 failed (10 checks; 1 with a convergence warning)` |
| example nxos-frr, leaks/frr1.conf (angle1/nxos/example/nxos-frr/leak-frr1.conf) | BLOCKER | **PASS** | 5.6 min | exit 1, `FAILED: 8 passed, 2 failed (10 checks; 1 with a convergence warning)` |
| ported must-fail change with a record baseline, and the vendor traps (angle1/nxos/mustfail) | BLOCKER | **PASS** | 23.8 min | record: 14 checks; record exit 1 on 1 known driver gap(s): INCOMPLETE BASELINE: n1: no global address on eth1 where Netdryrun reads it (unnumbered, or kept on another interface by the NOS); its link subnet has no guard; 14 traps failed as they must |
| example mikrotik (angle1/routeros/example/mikrotik) | BLOCKER | **PASS** | 1.6 min | exit 0, `PASSED: 10 passed, 0 failed (10 checks; 1 with a convergence warning)` |
| example mikrotik, leaks/frr1.conf (angle1/routeros/example/mikrotik/leak-frr1.conf) | BLOCKER | **PASS** | 1.6 min | exit 1, `FAILED: 8 passed, 2 failed (10 checks; 1 with a convergence warning)` |
| ported must-fail change with a record baseline, and the vendor traps (angle1/routeros/mustfail) | BLOCKER | **PASS** | 13.8 min | record: 12 checks + 2 by hand; record exit 1 on 2 known driver gap(s): INCOMPLETE BASELINE: r1: could not read IPv6 routes (IPv6 routes are not supported on routeros yet), so none is recorded as a check: fix the read and record again, or add checks by hand \| INCOMPLETE BASELINE: r1: no global address on eth1 where Netdryrun reads it (unnumbered, or kept on another interface by the NOS); its link subnet has no guard; 13 traps failed as they must |
| README quick start and own topology, word for word in a fresh container (angle2/readme) | BLOCKER | **PASS** | 7.4 min | 0 0 0 0 1 1 0 1 |
| common mistake: missing-image (angle2/mistake/missing-image) | BLOCKER | **PASS** | 1.4 s | exit 2:   quay.io/frrouting/frr:0.0.0-does-not-exist: not found. |
| common mistake: typo-in-netdryrun-yml (angle2/mistake/typo-in-netdryrun-yml) | BLOCKER | **PASS** | 0.1 s | exit 2: config error: /home/ndr/ndr-acceptance/0.4.2/labs/frr-bgp-mistake-typo-in-netdryrun-yml/netdryrun.yml: unknown top-level keys ['chekcs']; did you mean 'checks'? |
| common mistake: wrong-path (angle2/mistake/wrong-path) | BLOCKER | **PASS** | 0.1 s | exit 2: config error: /nonexistent/lab: not found |
| common mistake: no-docker-permission (angle2/mistake/no-docker-permission) | BLOCKER | **PASS** | 0.1 s | exit 2: ERROR: could not list Docker containers: permission denied while trying to connect to the docker API at unix:///var/run/docker.sock |
| common mistake: no-kvm (angle2/mistake/no-kvm) | BLOCKER | **PASS** | 0.1 s | exit 2: ERROR: node(s) n1 run their NOS as a VM, which needs KVM, and this host has no /dev/kvm: the VM would never start. Run on a Linux host (or a VM with nested virt |
| the same lab twice at once: the second exits 2, the first keeps its verdict (angle3/concurrency/same-lab) | BLOCKER | **PASS** | 2.0 min | exits (0, 2) |
| two different labs at once, started 20 s apart (angle3/concurrency/different-labs) | BLOCKER | **PASS** | 1.9 min | exits (0, 1) |
| brownfield FRR policy, good (angle3/brownfield/good) | BLOCKER | **PASS** | 1.7 min | record 51 s |
| brownfield FRR policy, leak (angle3/brownfield/leak) | BLOCKER | **PASS** | 54.3 s | exit 1, `FAILED: 123 passed, 1 failed (124 checks)` |
| brownfield FRR policy, swap (angle3/brownfield/swap) | BLOCKER | **PASS** | 84.3 s | exit 1, `FAILED: 123 passed, 1 failed (124 checks)` |
| brownfield FRR policy, cosmetic (angle3/brownfield/cosmetic) | BLOCKER | **PASS** | 54.2 s | exit 0, `PASSED: 124 passed, 0 failed (124 checks)` |
| 30-node multi-vendor lab, good (also angle 1's mixed lab) (angle3/big30/good) | BLOCKER | **PASS** | 6.7 min | deploy+boot 131 s, record 315 s, destroy 4 s, record exit 1 on 13 known gap(s) |
| 30-node multi-vendor lab, bad (also angle 1's mixed lab) (angle3/big30/bad) | BLOCKER | **PASS** | 7.1 min | exit 1, `FAILED: 1971 passed, 56 failed (2027 checks)` |
| documented CI templates: YAML and actionlint (angle3/templates) | BLOCKER | **PASS** | 0.1 s | 16 workflows, 0 problem(s) |
| every JSON report read against the published schema, status against exit code (angle3/schema) | BLOCKER | **PASS** | 0.0 s | 53 reports, exit 0 |
| the MCP tools on a fresh lab, a leaky change rejected, result sizes (angle4/mcp) | BLOCKER | **PASS** | 7.4 min | tools/list 2885 tokens, dry_run 2575 tokens, start_run 49 tokens, get_result 49 tokens, get_result 49 tokens, get_result 49 tokens, get_result 49 tokens, get_result 49 tokens, get_result 49 tokens, get_result 49 tokens, get_result 49 tokens, get_result 49 tokens, get_result 49 tokens, get_result 49 tokens, get_result 1590 tokens, record_baseline 2097 tokens, verify_change 521 tokens; verify_change INCONCLUSIVE, known: M-8 (0.4.1): FRR 10.4.1 keeps a default-originate path stale after End-of-RIB; fail-safe INCONCLUSIVE, fix planned for 0.4.3 |
| angle 5: two isolated red-teamers on new cases, verified (releases/ACCEPTANCE-PROMPT.md) | BLOCKER | **PASS** | 0.0 s | Result: no open false pass |

Every item, with its evidence: [acceptance.md](acceptance.md).

## Layer 6: independent review

# Layer 6: independent review, Netdryrun 0.4.2

Reviewed: the whole diff `v0.4.1..f220469` (the first `ndr/release-0.4.2` push, 2026-11-10), then the docs delta
`f220469..e6522db`. Every finding below is checked against the code; the fix commits are on `ndr/release-0.4.2`.

## Provenance

| Review | Reviewer | Output |
|---|---|---|
| Cold review | a fresh agent with none of the author's context, read-only on the worktree (~161k tokens) | findings 1-7 below |
| Adversary (angle 5) | one fresh attacker on an export of code, user docs, fixtures and the red-team harness only (~228k tokens) | RT-0066 (a BLOCKER), one LOW, 7 attempts refused |
| GPT and Grok, shipped code | `research/tools/ask_models.py`, brief `research/model-reviews/release-0.4.2/brief-shipped.md` (sha256 cbb34ee4d73e) | `research/model-reviews/release-0.4.2/shipped/` |
| GPT and Grok, gate scripts | the same tool, brief `brief-gate.md` (sha256 ede220941e07; resent once, the privacy check refused a git `index` line) | `research/model-reviews/release-0.4.2/gate/` |
| Docs delta e6522db | the release session, against the code | findings 8-9 |

One attacker instead of two, and no separate verifier: the release session reproduced the attacker's BLOCKER itself
(the repro script on the committed captures). Token budget, owner rule.

## Shipped code

| # | Finding | From | Severity | Decision | Commit / test |
|---|---|---|---|---|---|
| A1 | `record` on a BGP-unnumbered FRR fabric left every interface-named session out with a plain warning and exited 0: a dropped session or a prefix flood passed the baseline (RT-0066) | adversary | BLOCKER | Fixed: an INCOMPLETE BASELINE line names each such session; `record` exits 1. Naming them in checks is 0.4.3 | `67745a5`, oracle `FP-042-UNNSESS` |
| A2 | A numbered 169.254.0.0/30 link with a session over it was called unnumbered and left unguarded | adversary | LOW | Fixed: only fe80::/10 is link-local for "unnumbered" | `67745a5`, `FP-042-UNNSESS` |
| G1 | `inet A peer B/31` read as A/32: the wrong subnet guarded, exit 0 (a regression from the UNNUMBERED fix) | Grok, confirmed | MAJOR | Fixed: A in the peer's subnet, else a gap; no prefix length is a gap | `67745a5`, `FP-042-UNNSESS` |
| 6 | A gap line quoting device text with "only the first" was taken for a size cap and dropped | cold review | MINOR | Fixed: only `record`'s own two cap lines are exempt | `1289ef1`, oracle `FP-042-CAPMSG` |
| 7, 8 | The advice to add `as_path: ""` by hand on SR Linux can't work: the driver reads the missing container as unknown, so that check never gets a verdict. It was in the CHANGELOG, trust.md, cli.md, the advisory and the record warning | cold review; docs delta | MINOR | Fixed: "check that path's AS path on the peer that sends it", until 0.4.3 | `9d155d7` (No-Oracle: message text) |
| 9 | The roadmap and the news post called unnumbered `record` fixed while A1 was open | docs delta | MINOR | Fixed with A1: they say the sessions are a named gap until 0.4.3 | `fad7bb5` |
| G2 | `parse_paths_available` takes the first entry header and one "Paths:" line anywhere | Grok | MINOR | 0.4.3: require exactly one entry header (FRR prints one for an exact prefix) | `fastfix/plan-0.4.3.md` |
| G3 | `needs_text_count` catches ValueError only; deep JSON raises RecursionError | GPT, Grok, cold review | MINOR | 0.4.3; every caller fails closed | `fastfix/plan-0.4.3.md` |
| R1 | `_load` accepts `null`, `0`, `false` or a string | Grok | none | Refuted: every reader raises DriverError on them (checked) | |
| R2 | `_attribute_check` with `warnings=None` drops the gap silently | Grok | none | Not reachable: `record` always passes a list | |
| R3 | local_pref None is a warning, not a gap | Grok | none | As designed: a path without LOCAL_PREF is a real answer on some drivers | |

The cold reviewer and the attacker found nothing in: the FRR text path count, `mgmt.own_holder`, `addresses._load`,
`lab.interface_addresses` (apart from G1), `_unnumbered` (apart from A1, A2) and `_attribute_check`.

## Release gate

| # | Finding | From | Severity | Decision | Commit / test |
|---|---|---|---|---|---|
| 1 | A `--case` or `--resume` live run with no full layer on the commit saved a partial `live.json` that could clear | cold review, Grok | MAJOR | Fixed: `live-partial` BLOCKER until a full run | `1a05ec7`, `tests/test_gate_records.py` |
| 2 | A FAIL and the rerun limit were keyed on the commit: an empty commit started again | cold review | MAJOR | Fixed: they follow the tree | `1a05ec7` |
| 3 | A FAIL in a labrun host gap was dropped and not counted (`--gap 0` tainted everything) | cold review, Grok | MAJOR | Fixed: a FAIL there fails, every tainted run counts; labrun records its limits | `1a05ec7` |
| 5 | An unreadable attempt record (it may have held a FAIL) was skipped | cold review, GPT, Grok | MINOR | Fixed: a BLOCKER | `1a05ec7` |
| 4 | `No-Oracle:` is free text nobody reviews | cold review, GPT, Grok | MAJOR | 0.4.3 design: a reviewed entry with narrow kinds. In 0.4.2 the reviewer read both `No-Oracle` reasons in the range (f220469 version bump, 9d155d7 warning text) against their diffs | `fastfix/plan-0.4.3.md` |
| G4 | An oracle deleted after its fix (then a No-Oracle revert) went unseen | GPT, Grok | MAJOR | Fixed: an oracle the base holds or a fix names must stay | `149f0d6`, `tests/test_fastfix_gate.py` |
| G5 | A symlink in an oracle folder let a fix change its oracle through `src/` | Grok | MAJOR | Fixed: refused | `149f0d6` |
| G6 | `GATE_FILES` lacked `gate_records.py`, `labrun.py`, `surfaces_agree.py` | GPT | MAJOR | Fixed | `149f0d6` |
| G7 | A guard skipped at the base and failing at the candidate was not compared | Grok | MINOR | Fixed: a red | `149f0d6` |
| G8 | A FAIL vanished from GATE.md when the latest record lacked that check | GPT | MAJOR | Fixed | `149f0d6` |
| G9 | The bootstrap judges itself; the candidate could forge its JUnit report; allowlist `reviewed_by` unchecked; Session markers self-declared; shipped paths narrow | GPT, Grok | MAJOR (design) | 0.4.3 plan. 0.4.2 is the bootstrap release: its static layer runs this checkout's gate, as RELEASING.md says | `fastfix/plan-0.4.3.md` |
| R4 | Pytest crashes or timeouts read as passes | GPT | none | Refuted: any exit but 0/1 is a problem in both callers, and 0/1 must agree with the report | |

## What this review did not cover

- No lab: the attacker worked offline, and nothing here ran in containerlab. A1's repro used the committed captures.
- The fresh-user walk-through (an agent following the getting-started guide and tutorial on the candidate) belongs to
  the acceptance layer run by the coordinator.
- The final candidate after these fixes was not reviewed again by a fresh agent; the reproduce check, the unit suite
  and the oracles are what hold it.
