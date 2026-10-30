# Release gate: Netdryrun 0.4.0

Written by `scripts/release_gate.py` (see [RELEASING.md](../../RELEASING.md)). Do not edit by hand: rerun a layer, or record a decision in `accepted.json` or `review.md`.

**READY TO PUBLISH**: every layer before publishing ran on the same clean commit; no BLOCKER failed or was skipped; every MAJOR passed or was accepted. Tag it, then run `after-publish` to clear it.

**Layers not run yet:**

- Layer 7: after-publish proof

| Layer | Commit | Ran | Time | Result |
|---|---|---|---|---|
| [Layer 1: static](#layer-1-static) | `c952312cc9` | 2026-10-30 17:29:19 UTC | 1.1 s | 11 PASS |
| [Layer 2: unit tests on every supported Python](#layer-2-unit-tests-on-every-supported-python) | `81a49b3ce9` | 2026-10-30 13:25:41 UTC | 6.2 min | 7 PASS |
| [Layer 4: mutation testing](#layer-4-mutation-testing) | `81a49b3ce9` | 2026-10-30 13:31:53 UTC | 72.3 min | 11 PASS |
| [Layer 5: live matrix on the built package](#layer-5-live-matrix-on-the-built-package) | `81a49b3ce9` | 2026-10-30 14:44:08 UTC | 163.7 min | 3 ACCEPTED, 52 PASS |
| Layer 7: after-publish proof | | not run | | |

## Layer 1: static

Commit `c952312cc91b4ea954f2c3454afd6c8d74632b98` on `HEAD`; 2026-10-30 17:29:19 UTC; 1.1 s; Linux 6.18.54.1-microsoft-standard-WSL2 (x86_64); Python 3.10.12; --strict.

Tools: actionlint 1.7.7; ruff 0.17.3; shellcheck 0.8.0.

| Check | Severity | Result | Time | Notes |
|---|---|---|---|---|
| ruff (config in pyproject.toml) | BLOCKER | **PASS** | 0.0 s | All checks passed! |
| actionlint on every workflow (with shellcheck) | BLOCKER | **PASS** | 0.2 s | clean |
| shellcheck, error level, 18 scripts | BLOCKER | **PASS** | 0.2 s | clean |
| shellcheck, warning level, 18 scripts | MAJOR | **PASS** | 0.2 s | clean |
| no empty ${{ }} in action.yml or workflows | BLOCKER | **PASS** | 0.0 s | none |
| public facts match the source (sync_facts.py --check) | BLOCKER | **PASS** | 0.4 s | facts: in sync (version 0.4.0, 0 problem(s)) |
| every version reference says 0.4.0 | BLOCKER | **PASS** | 0.0 s | 43 references agree |
| pyproject.toml declares Python 3.10 to 3.14, the versions tested | MAJOR | **PASS** | 0.0 s | requires-python and classifiers agree |
| every example has a documented expected result and exit code | MAJOR | **PASS** | 0.0 s | 10 examples |
| every topology we ship is named ndr-* | BLOCKER | **PASS** | 0.0 s | 94 topologies |
| no retired public string outside the history (CHANGELOG, advisories, records) | BLOCKER | **PASS** | 0.0 s | none |

## Layer 2: unit tests on every supported Python

Commit `81a49b3ce951b117288ef1e3d08811cc443ac046` on `HEAD`; 2026-10-30 13:25:41 UTC; 6.2 min; Linux 6.18.54.1-microsoft-standard-WSL2 (x86_64); Python 3.10.12; --strict.

Tools: docker 29.9.2; uv 0.13.6 (x86_64-unknown-linux-gnu).

| Check | Severity | Result | Time | Notes |
|---|---|---|---|---|
| unit tests on Python 3.10.12 | BLOCKER | **PASS** | 64.0 s | 3644 passed, 61 skipped |
| unit tests on Python 3.11.18 | BLOCKER | **PASS** | 51.7 s | 3644 passed, 61 skipped |
| unit tests on Python 3.12.16 (with coverage) | BLOCKER | **PASS** | 89.9 s | 3644 passed, 61 skipped, 23 warnings |
| coverage of the verdict modules at or above the floors | MAJOR | **PASS** | 0.0 s | all at or above their floors |
| unit tests on Python 3.13.18 | BLOCKER | **PASS** | 47.4 s | 3644 passed, 61 skipped, 23 warnings |
| unit tests on Python 3.14.10 | BLOCKER | **PASS** | 47.0 s | 3644 passed, 61 skipped |
| unit tests in a plain python:3.12-slim container (no containerlab, no Docker) | BLOCKER | **PASS** | 72.2 s | 3604 passed, 101 skipped |

**Coverage of the verdict modules** (lines and branches, Python 3.12):

| Module | Lines | Branches | Covered | Floor |
|---|---|---|---|---|
| `src/netdryrun/checks.py` | 292/293 | 125/126 | 99.5% | 99% |
| `src/netdryrun/config.py` | 446/449 | 263/266 | 99.2% | 99% |
| `src/netdryrun/runner.py` | 662/669 | 274/278 | 98.8% | 98% |
| `src/netdryrun/drivers/` | 1196/1196 | 422/424 | 99.9% | 99% |
| `src/netdryrun/verify/engine.py` | 466/468 | 224/226 | 99.4% | 98% |
| `src/netdryrun/verify/intent.py` | 349/352 | 169/172 | 98.9% | 97% |
| `src/netdryrun/verify/frr.py` | 547/596 | 261/306 | 89.6% | 88% |
| `src/netdryrun/verify/snapshot.py` | 399/423 | 133/156 | 91.9% | 90% |
| `src/netdryrun/verify/converge.py` | 71/73 | 29/30 | 97.1% | 96% |
| `src/netdryrun/verify/run.py` | 483/542 | 177/212 | 87.5% | 83% |
| `src/netdryrun/verify/report.py` | 203/224 | 86/102 | 88.7% | 88% |

## Layer 4: mutation testing

Commit `81a49b3ce951b117288ef1e3d08811cc443ac046` on `HEAD`; 2026-10-30 13:31:53 UTC; 72.3 min; Linux 6.18.54.1-microsoft-standard-WSL2 (x86_64); Python 3.10.12; --strict.

Tools: mutmut python -m mutmut, version 3.8.0.

| Check | Severity | Result | Time | Notes |
|---|---|---|---|---|
| no surviving mutants in src/netdryrun/checks.py | BLOCKER | **PASS** | 68.7 min | 1220 generated, 1138/1220 caught (93.3%); not caught: 82 survived the tests, 0 in code no test runs, 82 accepted (33 equivalent, 49 message-text) |
| no surviving mutants in src/netdryrun/config.py | BLOCKER | **PASS** | 0.0 s | 1480 generated, 1232/1480 caught (83.2%); not caught: 248 survived the tests, 0 in code no test runs, 248 accepted (25 equivalent, 223 message-text) |
| no surviving mutants in src/netdryrun/runner.py | BLOCKER | **PASS** | 0.0 s | 1674 generated, 1513/1674 caught (90.4%); not caught: 161 survived the tests, 0 in code no test runs, 161 accepted (31 equivalent, 11 logging, 118 message-text, 1 timing-only) |
| no surviving mutants in src/netdryrun/drivers/ | BLOCKER | **PASS** | 0.0 s | 2965 generated, 2735/2965 caught (92.2%); not caught: 230 survived the tests, 0 in code no test runs, 230 accepted (48 equivalent, 182 message-text) |
| no surviving mutants in src/netdryrun/verify/engine.py | BLOCKER | **PASS** | 0.0 s | 1521 generated, 1450/1521 caught (95.3%); not caught: 71 survived the tests, 0 in code no test runs, 71 accepted (27 equivalent, 44 message-text) |
| no surviving mutants in src/netdryrun/verify/intent.py | BLOCKER | **PASS** | 0.0 s | 1146 generated, 1024/1146 caught (89.4%); not caught: 122 survived the tests, 0 in code no test runs, 122 accepted (13 equivalent, 109 message-text) |
| no surviving mutants in src/netdryrun/verify/frr.py | BLOCKER | **PASS** | 0.0 s | 2646 generated, 1772/2646 caught (67.0%); not caught: 874 survived the tests, 0 in code no test runs, 2 accepted (2 equivalent); 872 outside the gated functions (parsers that fail closed and rendering; their full zero is a 0.4.1 gate item) |
| no surviving mutants in src/netdryrun/verify/snapshot.py | BLOCKER | **PASS** | 0.0 s | 1100 generated, 816/1100 caught (74.2%); not caught: 284 survived the tests, 0 in code no test runs; 284 outside the gated functions (parsers that fail closed and rendering; their full zero is a 0.4.1 gate item) |
| no surviving mutants in src/netdryrun/verify/converge.py | BLOCKER | **PASS** | 0.0 s | 148 generated, 134/148 caught (90.5%); not caught: 14 survived the tests, 0 in code no test runs, 2 accepted (2 equivalent); 12 outside the gated functions (parsers that fail closed and rendering; their full zero is a 0.4.1 gate item) |
| no surviving mutants in src/netdryrun/verify/run.py | BLOCKER | **PASS** | 0.0 s | 1436 generated, 1198/1436 caught (83.4%); not caught: 238 survived the tests, 0 in code no test runs, 7 accepted (7 equivalent); 231 outside the gated functions (parsers that fail closed and rendering; their full zero is a 0.4.1 gate item) |
| no surviving mutants in src/netdryrun/verify/report.py | BLOCKER | **PASS** | 0.0 s | 842 generated, 535/842 caught (63.5%); not caught: 307 survived the tests, 0 in code no test runs; 307 outside the gated functions (parsers that fail closed and rendering; their full zero is a 0.4.1 gate item) |

**src/netdryrun/verify/frr.py: 872 survivors outside the gated functions** (parsers that fail closed and rendering; their full zero is a 0.4.1 gate item): `verify.frr._nexthop` 148, `verify.frr.parse_attrs` 146, `verify.frr.parse_routes` 81, `verify.frr.parse_adj` 72, `verify.frr.parse_neighbors` 70, `verify.frr._parse_received` 58, `verify.frr.parse_bgp_table` 53, `verify.frr.show_command` 38, `verify.frr.parse_path` 33, `verify.frr._dest_paths` 23, `verify.frr._nexthops` 23, `verify.frr.FrrCollector._collect_items` 22, `verify.frr.FrrCollector._vtysh` 14, `verify.frr._obj` 12, `verify.frr._add_path_rx` 11, `verify.frr.FrrCollector._collect` 10, `verify.frr._vrf` 8, `verify.frr._check_total` 7, `verify.frr._json` 7, `verify.frr._str` 7, `verify.frr._communities` 6, `verify.frr.sent_counters` 5, `verify.frr._bad` 4, `verify.frr._flag` 4, `verify.frr._int` 4, `verify.frr._opt_int` 2, `verify.frr.adv_intervals` 2, `verify.frr.FrrCollector.__init__` 1, `verify.frr.FrrCollector.collect` 1

**src/netdryrun/verify/snapshot.py: 284 survivors outside the gated functions** (parsers that fail closed and rendering; their full zero is a 0.4.1 gate item): `verify.snapshot.Snapshot.from_json` 41, `verify.snapshot.AsPath.build` 32, `verify.snapshot.decode` 30, `verify.snapshot.BgpAttrs.__post_init__` 27, `verify.snapshot.AsPath.parse` 22, `verify.snapshot.AsPath.__post_init__` 20, `verify.snapshot.AsPath.render` 20, `verify.snapshot.parse_asn` 13, `verify.snapshot.ItemKey.where` 12, `verify.snapshot.canon_prefix` 10, `verify.snapshot.NextHop.__post_init__` 8, `verify.snapshot.canon_ext_communities` 7, `verify.snapshot.canon_ip` 7, `verify.snapshot.BgpPath.__post_init__` 6, `verify.snapshot.canon_community` 5, `verify.snapshot.Session.__post_init__` 5, `verify.snapshot._typed` 4, `verify.snapshot.canon_large_community` 4, `verify.snapshot.RibEntry.__post_init__` 4, `verify.snapshot.canon_ext_community` 3, `verify.snapshot.Snapshot.to_json` 3, `verify.snapshot.PathNextHop.__post_init__` 1

**src/netdryrun/verify/converge.py: 12 survivors outside the gated functions** (parsers that fail closed and rendering; their full zero is a 0.4.1 gate item): `verify.converge._moving` 12

**src/netdryrun/verify/run.py: 231 survivors outside the gated functions** (parsers that fail closed and rendering; their full zero is a 0.4.1 gate item): `verify.run.verify` 64, `verify.run.materialize` 37, `verify.run.bind_sources` 24, `verify.run._git` 20, `verify.run.expand_bind` 16, `verify.run._hash_binds` 14, `verify.run._extract` 11, `verify.run.load_guards` 11, `verify.run._cat_files` 9, `verify.run._is_ref` 5, `verify.run.intent_edited` 5, `verify.run._files` 4, `verify.run.resolve_bind` 4, `verify.run._hint` 3, `verify.run._now` 1, `verify.run.confirm_by_rerun` 1, `verify.run.expects_bgp` 1, `verify.run.Side.locate` 1

**src/netdryrun/verify/report.py: 307 survivors outside the gated functions** (parsers that fail closed and rendering; their full zero is a 0.4.1 gate item): `verify.report.markdown` 142, `verify.report.console` 92, `verify.report._summary` 25, `verify.report.item_json` 25, `verify.report._intent_json` 6, `verify.report._plain_yaml` 6, `verify.report.to_json` 6, `verify.report._diag` 5

**Accepted entries that no longer survive** (4; remove them from accepted.json): `netdryrun.drivers.base.xǁRepeatedKeyǁ__init____mutmut_2`, `netdryrun.drivers.junos.x__join_repeats__mutmut_7`, `netdryrun.verify.engine.x__pins_ok__mutmut_78`, `netdryrun.verify.engine.x__pins_ok__mutmut_79`

**Surviving mutants by function** (2631 in all; every diff is in [mutants.md](mutants.md)):

| Function | Survivors |
|---|---|
| `verify.frr._nexthop` | 148 |
| `verify.frr.parse_attrs` | 146 |
| `verify.report.markdown` | 142 |
| `verify.report.console` | 92 |
| `config._describe` | 91 |
| `verify.frr.parse_routes` | 81 |
| `runner._bgp_convergence_gate` | 73 |
| `verify.frr.parse_adj` | 72 |
| `verify.frr.parse_neighbors` | 70 |
| `verify.run.verify` | 64 |
| `verify.frr._parse_received` | 58 |
| `verify.frr.parse_bgp_table` | 53 |
| `config._validate_check` | 50 |
| `verify.snapshot.Snapshot.from_json` | 41 |
| `verify.frr.show_command` | 38 |
| `verify.run.materialize` | 37 |
| `verify.frr.parse_path` | 33 |
| `verify.snapshot.AsPath.build` | 32 |
| `config._validate_scenario` | 30 |
| `verify.snapshot.decode` | 30 |
| `verify.intent._line` | 27 |
| `verify.snapshot.BgpAttrs.__post_init__` | 27 |
| `drivers.frr._bgp_paths_raw` | 26 |
| `verify.intent._glob` | 25 |
| `verify.report._summary` | 25 |
| `verify.report.item_json` | 25 |
| `verify.run.bind_sources` | 24 |
| `checks._ping` | 23 |
| `verify.frr._dest_paths` | 23 |
| `verify.frr._nexthops` | 23 |
| `verify.frr.FrrCollector._collect_items` | 22 |
| `verify.snapshot.AsPath.parse` | 22 |
| `verify.intent._attr` | 21 |
| `checks._route` | 20 |
| `verify.run._git` | 20 |
| `verify.snapshot.AsPath.__post_init__` | 20 |
| `verify.snapshot.AsPath.render` | 20 |
| `drivers.frr._route_table` | 18 |
| `config.load` | 17 |
| `drivers.eos._summary` | 16 |
| `verify.engine._pins_ok` | 16 |
| `verify.run.expand_bind` | 16 |
| `config.load_yaml` | 15 |
| `drivers.eos._bgp_entries` | 15 |
| `runner._yaml_problem` | 15 |
| `verify.frr.FrrCollector._vtysh` | 14 |
| `verify.run._hash_binds` | 14 |
| `config._StrictLoader.construct_mapping` | 13 |
| `verify.snapshot.parse_asn` | 13 |
| `drivers.eos._vrf` | 12 |
| `runner.run` | 12 |
| `verify.converge._moving` | 12 |
| `verify.frr._obj` | 12 |
| `verify.intent.parse_intent` | 12 |
| `verify.snapshot.ItemKey.where` | 12 |
| `checks._describe_path` | 11 |
| `config._validate_bgp_route` | 11 |
| `verify.engine._session` | 11 |
| `verify.frr._add_path_rx` | 11 |
| `verify.run._extract` | 11 |
| `verify.run.load_guards` | 11 |
| `drivers.srlinux._rib_rows` | 10 |
| `runner._link_sessions` | 10 |
| `runner._wait_fault_visible` | 10 |
| `runner.run_scenario` | 10 |
| `verify.frr.FrrCollector._collect` | 10 |
| `verify.snapshot.canon_prefix` | 10 |
| `checks._bgp_route` | 9 |
| `drivers.srlinux.SrlDriver._read_path` | 9 |
| `runner._shape_problem` | 9 |
| `verify.intent._allow` | 9 |
| `verify.run._cat_files` | 9 |
| `runner.load_config` | 8 |
| `verify.engine.match` | 8 |
| `verify.frr._vrf` | 8 |
| `verify.snapshot.NextHop.__post_init__` | 8 |
| `config._reject_unknown` | 7 |
| `drivers.frr._bgp_json` | 7 |
| `verify.engine._best_path` | 7 |
| `verify.frr._check_total` | 7 |
| `verify.frr._json` | 7 |
| `verify.frr._str` | 7 |
| `verify.intent.check_nodes` | 7 |
| `verify.snapshot.canon_ext_communities` | 7 |
| `verify.snapshot.canon_ip` | 7 |
| `checks.is_post_convergence` | 6 |
| `drivers.base.Driver._exec` | 6 |
| `drivers.base.load_json` | 6 |
| `drivers.eos._learned` | 6 |
| `drivers.frr._learned` | 6 |
| `drivers.junos._as_path` | 6 |
| `drivers.srlinux._list` | 6 |
| `verify.engine._advertisement` | 6 |
| `verify.engine.baseline_problems` | 6 |
| `verify.frr._communities` | 6 |
| `verify.report._intent_json` | 6 |
| `verify.report._plain_yaml` | 6 |
| `verify.report.to_json` | 6 |
| `verify.snapshot.BgpPath.__post_init__` | 6 |
| `config._suggest` | 5 |
| `drivers.base.network` | 5 |
| `drivers.srlinux._json` | 5 |
| `runner._reach_then_hold` | 5 |
| `runner.preflight` | 5 |
| `verify.frr.sent_counters` | 5 |
| `verify.report._diag` | 5 |
| `verify.run._is_ref` | 5 |
| `verify.run.intent_edited` | 5 |
| `verify.snapshot.Session.__post_init__` | 5 |
| `verify.snapshot.canon_community` | 5 |
| `checks._evaluate_all` | 4 |
| `drivers.eos._json` | 4 |
| `drivers.eos._table` | 4 |
| `drivers.frr.FrrDriver._confirm_vrf` | 4 |
| `drivers.junos._next_hop` | 4 |
| `verify.engine._flat` | 4 |
| `verify.engine.path_view` | 4 |
| `verify.frr._bad` | 4 |
| `verify.frr._flag` | 4 |
| `verify.frr._int` | 4 |
| `verify.intent.Allow.matches` | 4 |
| `verify.intent._attrs` | 4 |
| `verify.intent.parse_intent_text` | 4 |
| `verify.run._files` | 4 |
| `verify.run.resolve_bind` | 4 |
| `verify.snapshot.RibEntry.__post_init__` | 4 |
| `verify.snapshot._typed` | 4 |
| `verify.snapshot.canon_large_community` | 4 |
| `checks.run_round_robin` | 3 |
| `config.Fault.describe` | 3 |
| `config.normalize_as_path` | 3 |
| `drivers.base.Driver.all_routes` | 3 |
| `drivers.base.as_int` | 3 |
| `drivers.base.unexpected` | 3 |
| `drivers.check_supported` | 3 |
| `drivers.eos.parse_startup_config_errors` | 3 |
| `drivers.for_node` | 3 |
| `drivers.junos._adv_interval` | 3 |
| `verify.engine.config_lines_changed` | 3 |
| `verify.intent._prefix` | 3 |
| `verify.run._hint` | 3 |
| `verify.run.bind_reach` | 3 |
| `verify.snapshot.Snapshot.to_json` | 3 |
| `verify.snapshot.canon_ext_community` | 3 |
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
| `drivers.junos._afi` | 2 |
| `drivers.junos._destination` | 2 |
| `drivers.junos._hidden` | 2 |
| `drivers.junos._strip_port` | 2 |
| `drivers.srlinux.parse_instance_state` | 2 |
| `runner._sonic_config_bind` | 2 |
| `verify.converge.stable_snapshot` | 2 |
| `verify.engine.RouteView.best` | 2 |
| `verify.engine.attrs_view` | 2 |
| `verify.frr._opt_int` | 2 |
| `verify.frr.adv_intervals` | 2 |
| `verify.intent._ip` | 2 |
| `verify.intent.load_intent` | 2 |
| `verify.run.check_changed_binds` | 2 |
| `checks._not_configured` | 1 |
| `checks.converge_then_hold` | 1 |
| `config.parse_community` | 1 |
| `drivers.base.RepeatedKey.__init__` | 1 |
| `drivers.base.no_repeated_keys` | 1 |
| `drivers.eos.EosDriver.all_routes` | 1 |
| `drivers.frr.FrrDriver.all_routes` | 1 |
| `drivers.junos.JunosDriver.all_routes` | 1 |
| `drivers.junos._active` | 1 |
| `drivers.junos._filtered` | 1 |
| `drivers.junos._protocol` | 1 |
| `drivers.srlinux.SrlDriver.all_routes` | 1 |
| `drivers.srlinux._bgp_learned` | 1 |
| `runner._sessions_over_links` | 1 |
| `runner._stretch_for_advertisement_intervals` | 1 |
| `verify.engine._propagated` | 1 |
| `verify.engine.changed_fields` | 1 |
| `verify.frr.FrrCollector.__init__` | 1 |
| `verify.frr.FrrCollector.collect` | 1 |
| `verify.frr.configured_link_locals` | 1 |
| `verify.frr.parse_link_local` | 1 |
| `verify.intent._int_or_null` | 1 |
| `verify.intent._nodes` | 1 |
| `verify.run.Side.locate` | 1 |
| `verify.run._now` | 1 |
| `verify.run.classify_nodes` | 1 |
| `verify.run.confirm_by_rerun` | 1 |
| `verify.run.expects_bgp` | 1 |
| `verify.run.unobserved_reasons` | 1 |
| `verify.snapshot.PathNextHop.__post_init__` | 1 |

## Layer 5: live matrix on the built package

Commit `81a49b3ce951b117288ef1e3d08811cc443ac046` on `HEAD`; 2026-10-30 14:44:08 UTC; 163.7 min; Linux 6.18.54.1-microsoft-standard-WSL2 (x86_64); Python 3.10.12; --strict.

Tools: containerlab ⣴⡾⠛⠛⠖ ⢠⣶⠟⠛⢷⣦ ⢸⣿⣧ ⣿ ⠘⠛⢻⡟⠛⠛ ⣾⣿⡀ ⣿⡇ ⣿⣿⡄ ⢸⡇ ⣿⡟⠛⠛⠃⢸⣿⠛⠛⣷⡄ [38;2;0;201;255m⣿⡇[0m ; docker 29.9.2.

| Check | Severity | Result | Time | Notes |
|---|---|---|---|---|
| build the wheel | BLOCKER | **PASS** | 0.7 s | netdryrun-0.4.0-py3-none-any.whl |
| install netdryrun-0.4.0-py3-none-any.whl in a fresh venv | BLOCKER | **PASS** | 0.7 s |  |
| runs the installed package, not the source tree | BLOCKER | **PASS** | 0.0 s | /tmp/ndr-gate-live-8se2xmjn/venv/lib/python3.12/site-packages/netdryrun/__init__.py |
| netdryrun --version says 0.4.0 | BLOCKER | **PASS** | 0.0 s | netdryrun 0.4.0 |
| example agent-demo: `Demo OK`, exit 0 | BLOCKER | **PASS** | 81.2 s | exit 0: Demo OK: attempt 1 rejected by 5 leak guards with every other check passing; attempt 2 passed every check. |
| example agent-demo: no lab left running | BLOCKER | **PASS** | 0.0 s | none left |
| example arista-frr: `PASSED: 10 passed, 0 failed`, exit 0 | BLOCKER | **PASS** | 1.8 min | exit 0: PASSED: 10 passed, 0 failed (10 checks) |
| example arista-frr: no lab left running | BLOCKER | **PASS** | 0.0 s | none left |
| example batfish-pipeline: `PASSED: 10 passed, 0 failed`, exit 0 | BLOCKER | **PASS** | 1.7 min | exit 0: PASSED: 10 passed, 0 failed (10 checks) |
| example batfish-pipeline: no lab left running | BLOCKER | **PASS** | 0.0 s | none left |
| example frr-bgp: `PASSED: 11 passed, 0 failed`, exit 0 | BLOCKER | **PASS** | 1.7 min | exit 0: PASSED: 11 passed, 0 failed (11 checks) |
| example frr-bgp: no lab left running | BLOCKER | **PASS** | 0.0 s | none left |
| example frr-bgp-broken: `FAILED: 5 passed, 1 failed`, exit 1 | BLOCKER | **PASS** | 41.0 s | exit 1: FAILED: 5 passed, 1 failed (6 checks) |
| example frr-bgp-broken: no lab left running | BLOCKER | **PASS** | 0.0 s | none left |
| example junos-frr: `PASSED: 13 passed, 0 failed`, exit 0 | BLOCKER | **PASS** | 5.4 min | exit 0: PASSED: 13 passed, 0 failed (13 checks) |
| example junos-frr: no lab left running | BLOCKER | **PASS** | 0.0 s | none left |
| example leak-pattern: `PASSED: 8 passed, 0 failed`, exit 0 | BLOCKER | **PASS** | 44.5 s | exit 0: PASSED: 8 passed, 0 failed (8 checks) |
| example leak-pattern: no lab left running | BLOCKER | **PASS** | 0.0 s | none left |
| example sonic-frr: `PASSED: 8 passed, 0 failed`, exit 0 | BLOCKER | **PASS** | 1.6 min | exit 0: PASSED: 8 passed, 0 failed (8 checks) |
| example sonic-frr: no lab left running | BLOCKER | **PASS** | 0.0 s | none left |
| example srl-frr: `PASSED: 7 passed, 0 failed`, exit 0 | BLOCKER | **PASS** | 69.1 s | exit 0: PASSED: 7 passed, 0 failed (7 checks) |
| example srl-frr: no lab left running | BLOCKER | **PASS** | 0.0 s | none left |
| example srl-hidden-leak: `PASSED: 9 passed, 0 failed`, exit 0 | BLOCKER | **PASS** | 60.2 s | exit 0: PASSED: 9 passed, 0 failed (9 checks) |
| example srl-hidden-leak: no lab left running | BLOCKER | **PASS** | 0.0 s | none left |
| example srl-hidden-leak with leaks/frr1.conf: `FAILED: 8 passed, 1 failed`, exit 1 | BLOCKER | **PASS** | 63.6 s | exit 1: FAILED: 8 passed, 1 failed (9 checks) |
| example srl-hidden-leak with leaks/frr1.conf: no lab left running | BLOCKER | **PASS** | 0.0 s | none left |
| example srl-hidden-leak with leaks/srl1.cli: `FAILED: 8 passed, 1 failed`, exit 1 | BLOCKER | **PASS** | 80.8 s | exit 1: FAILED: 8 passed, 1 failed (9 checks) |
| example srl-hidden-leak with leaks/srl1.cli: no lab left running | BLOCKER | **PASS** | 0.0 s | none left |
| example times match the docs (within 2x) | MAJOR | **PASS** | 0.0 s | all within 2x |
| Verdict Corpus v1: every verdict matches the committed results.json | BLOCKER | **PASS** | 69.5 min | all verdicts match |
| Verdict Corpus v1: no harmful change approved beyond the published known misses | BLOCKER | **PASS** | 0.0 s | harmful changes approved: 5 (12-ibgp-send-community-dropped, 18-redistribute-connected, 21-customer-max-prefix-removed, 23-fat-finger-third-party-origin, 30-peer-import-filter-removed); published known misses: 12-ibgp-send-community-dropped, 18-redistribute-connected, 21-customer-max-prefix-removed, 23-fat-finger-third-party-origin, 30-peer-import-filter-removed |
| Verdict Corpus v1: no lab left running | BLOCKER | **PASS** | 0.0 s | none left |
| Verdict Corpus v2: every verdict matches the committed results.json | BLOCKER | **PASS** | 71.9 min | all verdicts match |
| Verdict Corpus v2: the nondeterministic exemption holds (pinned list, repeats ran, no error) | BLOCKER | **PASS** | 0.0 s | 18-aggregate-discard-route-removed |
| Verdict Corpus v2: nondeterministic cases recorded (known, not scored, never a blocker) | INFO | **PASS** | 0.0 s | Netdryrun verdicts per run: 18-aggregate-discard-route-removed: safe, unsafe, unsafe |
| Verdict Corpus v2: no harmful change approved beyond the published known misses | BLOCKER | **PASS** | 0.0 s | harmful changes approved: 1 (04-redundant-aggregate-typo); published known misses: 04-redundant-aggregate-typo |
| Verdict Corpus v2: no lab left running | BLOCKER | **PASS** | 0.0 s | none left |
| MCP handshake against the installed wheel | BLOCKER | **PASS** | 1.2 s | MCP handshake OK |
| check pack verification | MAJOR | **ACCEPTED** | 0.0 s | no --pack script given (accepted: No check pack is sold yet: pack verification is paused by the roadmap until the 45-day demand test; it runs with --pack before any pack ships.) |
| 20-node scale test | MAJOR | **ACCEPTED** | 0.0 s | not scripted in the repository yet: run it by hand (accepted: Not scripted yet. A 20-node lab was run by hand in pre-launch testing (it found the PR-comment size limit, fixed in 0.3.1); scripting it is a 0.4.1 item.) |
| SIGINT during deploy: exit 130, a clear message | BLOCKER | **PASS** | 4.8 s | exit 130 |
| SIGINT during deploy: no lab left running | BLOCKER | **PASS** | 0.0 s | none left |
| SIGINT during checks: exit 130, a clear message | BLOCKER | **PASS** | 17.1 s | exit 130 |
| SIGINT during checks: no lab left running | BLOCKER | **PASS** | 0.0 s | none left |
| SIGTERM during deploy: exit 143, a clear message | BLOCKER | **PASS** | 5.5 s | exit 143 |
| SIGTERM during deploy: no lab left running | BLOCKER | **PASS** | 0.0 s | none left |
| SIGTERM during checks: exit 143, a clear message | BLOCKER | **PASS** | 17.0 s | exit 143 |
| SIGTERM during checks: no lab left running | BLOCKER | **PASS** | 0.0 s | none left |
| a node's image does not exist: exit 2 with a clear error | BLOCKER | **PASS** | 0.4 s | exit 2:   wrote json report: /tmp/ndr-gate-live-8se2xmjn/reports/frr-bgp-missing-image.json |
| a node's image does not exist: no lab left running | BLOCKER | **PASS** | 0.0 s | none left |
| a node cannot be created (a bind source does not exist): exit 2 with a clear error | BLOCKER | **PASS** | 0.3 s | exit 2:   wrote json report: /tmp/ndr-gate-live-8se2xmjn/reports/frr-bgp-deploy-fails.json |
| a node cannot be created (a bind source does not exist): no lab left running | BLOCKER | **PASS** | 0.0 s | none left |
| two runs of the same lab at once: no false verdict, no crash | BLOCKER | **PASS** | 1.7 min | exit codes 0 and 2 |
| two runs at once: no lab left running | BLOCKER | **PASS** | 0.0 s | none left |
| Docker restarts mid-run | MAJOR | **ACCEPTED** | 0.0 s | off by default (restarts every container on the machine): pass --chaos-docker-restart (accepted: Optional by RELEASING.md (Layer 5, Chaos): it restarts Docker, which stops every container on the machine, and the lab machine is shared with other sessions' labs. The other chaos cases (SIGINT and SIGTERM in the deploy and the checks, a missing image, a node that can't be created, two runs of one lab) ran and passed on 81a49b3. Coordinator, 2026-10-31: kept for 0.4.0 (the interop stress test holds the lab, and a Docker restart would kill its labs); the restart case runs in the next quiet lab window or, at the latest, in the 0.4.1 gate.) |

## Layer 6: independent review

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
