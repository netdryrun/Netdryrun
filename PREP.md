# 0.4.1 preparation branch (`ndr/release-0.4.1`): what it holds, what will conflict with 0.4

Internal note for the release session; delete it when 0.4.1 ships. Written 2026-10-30.

## What is on this branch
`origin/main` (0.3.3, cafcfe5) plus:
- **`ndr/nxos`** (826d245): the Cisco NX-OS driver (beta, bring your own image).
- **`ndr/mikrotik`** (1bb74b9): the MikroTik RouterOS 7 driver (beta, bring your own image, one CHR node per lab until MikroTik answers a terms question) with `examples/mikrotik`.

Both drivers are in `sync_facts.UNRELEASED = {"nxos", "routeros"}`: registered and tested, not on the public compatibility page, not in the public docs, no matrix rows switched on. Registration conflicts between the two were resolved by listing both drivers everywhere (`config.DRIVER_NAMES`, `drivers.DRIVERS`, `detect`, `lab.py` kinds, `sync_facts.PLATFORMS`, `compat_matrix` EXAMPLES/NOS/BETA, `compat_verified.json`, `capture_fixtures.sh`, the matrix/fuzz/verdict/docs-claims tests).

Checks run on this branch (Windows, no lab, no mutation run): ruff clean; `sync_facts.py --check` and `compat_matrix.py --check` in sync; `pytest tests --ignore=tests/redteam`: 2892 passed, 10 failed, 49 skipped. The same 10 fail on plain main on this Windows machine (signal.SIGHUP, UTF-8 reads, path and quoting differences in the Action/GitLab/MCP tests): they are environment failures, not from this branch.

## What is NOT on this branch, and why
**`ndr/v041-prep` (2dc60f5) is not merged.** It sits on the 0.4 line (it is based on 3c00213, which predates the 0.3.3 merge), so merging it into main-based work drags in the 0.4.0 commits and conflicts in 18 files (AGENTS.md, CHANGELOG.md, action.yml, the 0.3.0 advisory, `drivers/{base,eos,frr,srlinux}.py`, `mcp_server.py`, `record.py`, MCP schema tests, the release-gate mutants test, five website pages and the MCP result schema). That conflict set is the 0.4.0-versus-main one and belongs to the 0.4 merge, not to 0.4.1. Its five prep commits (versioning policy, EOS out-delay reader, compact MCP results, the warm re-verify planner) apply cleanly on top of 0.4 (`git merge ndr/v041-prep` after 0.4 is on main, or `git cherry-pick 3c00213..2dc60f5`).

## Order once 0.4 ships
1. Merge main (with 0.4) into this branch, or rebase it. Expect the conflicts below.
2. Merge `ndr/v041-prep` (clean on top of 0.4).
3. Re-run the checks above and the 0.4.1 gate.

## Files that conflict with `ndr/release-0.4.0` (13cae78), measured with `git merge-tree`
Registration (0.4.0 registers the Junos driver on the same lines): resolve by keeping every driver, in this order `frr srlinux eos sonic junos nxos routeros`:
- `src/netdryrun/config.py` (`DRIVER_NAMES`), `src/netdryrun/drivers/__init__.py` (imports, `DRIVERS`, `detect`), `src/netdryrun/lab.py` (the `*_KINDS` constants, and `_require_linux_links` if Junos adds one)
- `scripts/sync_facts.py` (`PLATFORMS`, and `UNRELEASED` becomes `{"junos"?, "nxos", "routeros"}`: remove `junos` from it only if 0.4 ships it public)
- `scripts/compat_matrix.py` (`EXAMPLES`, `NOS`, `BETA`), `tests/compat_verified.json` (auto-merges; check the JSON stays valid)
- `scripts/capture_fixtures.sh` (usage line, `DRIVERS_HERE`, the driver table rows, the capture functions)
- tests: `test_docs_claims.py` (`DISPLAY`), `test_driver_false_pass.py`, `test_driver_fuzz.py` (imports, the Case list, `DRIVER_PARSER_MODULES`), `test_driver_matrix.py` (cells: keep every driver's block), `test_verdict_drivers.py` (detect rows, `for_node`)
Docs (pages 0.4 edits): `website/docs/llms-full.txt` (generated: re-run `python scripts/sync_facts.py` after the merge instead of resolving by hand), `website/docs/trust.md`.
Not conflicting but needing a look: `CHANGELOG.md` (neither side edits the 0.4.1 section yet), the public facts blocks (`sync_facts.py`), `website/docs/reference/config.md` (driver list and the evpn row: the docs-claims tests demand exactly the released drivers).

Rule of thumb when a conflict is only a list of drivers: keep all of them. When a hunk is a driver's own function or test cells: keep both blocks, then run `pytest tests/test_driver_matrix.py tests/test_driver_fuzz.py tests/test_verdict_drivers.py tests/test_docs_claims.py tests/test_compat_matrix.py`.

## Release switch per driver (when 0.4.1 ships it publicly)
Remove the driver from `sync_facts.UNRELEASED`; run `python scripts/sync_facts.py` and `python scripts/compat_matrix.py`; add the platform to `website/docs/reference/config.md` (driver list, the evpn row, the drivers table); add its examples page; fill the changelog entry; the docs-claims tests then demand exactly that. Per driver:
- **NX-OS**: image from Cisco (a free Cisco account was enough for 10.4(8)); keep the "bring your own image" wording.
- **MikroTik RouterOS**: only after MikroTik answers the terms question (free CHR for a maintainer who runs a business, a CI download, more than one CHR per lab); until then one CHR node per lab and no CI download. Keep "beta, bring your own image". Spectrum is not a matrix row for any driver (one docs/FAQ statement only).
- A beta lands only when its image boots in a lab we can run. NX-OS and RouterOS both have a green live run (`examples/nxos-frr`, `examples/mikrotik`).

## 0.4.1 items started offline on this branch (no lab, no mutation run)
- **Compatibility page draft** (`docs/compat-draft-0.4.1.md`, regenerate with `python scripts/compat_draft.py`): the page as it reads with nxos and routeros released. Unpublished; the public page is unchanged. Junos is not here (it is 0.4).
- **Graceful-restart stale paths** (`src/netdryrun/drivers/stale.py`, `tests/test_gr_stale.py`): EOS (`routeType.stale`), NX-OS (`pathstaled`) and SR Linux (`stale-route`) now refuse a stale path the way FRR already did (a `DriverError`, "not settled"), and a stale field of an unexpected type is an error, never "not stale". Red first: 19 of 20 tests failed before the drivers read the fields (the 20th is the control). Built from flipping the explicit stale field in the real captures we already have. The route readers now read the BGP paths even when the route is installed, so a stale path cannot hide behind an installed route. **Still needs a live graceful-restart capture** to confirm the field flips as assumed during a real restart on each NOS (compat_verified limits and the 0.4.1 changelog keep saying so until then). When 0.4 lands, `eos.py` and `srlinux.py` are files 0.4.0 may also touch: expect a small conflict near `_bgp_entries` and `_rib_rows`.
- **SR Linux AS-loop prefix count**: not started as code. The 2026-10-28 live capture it came from was not kept and the fixtures we have contain no looped route, so a red test would codify a guess. `tests/test_srl_loop_count.py` is a skipped placeholder whose docstring lists exactly what to capture (one lab run under the lock) and what to assert.

## Not verified yet (nothing here counts as done until the 0.4.1 release gate passes on one commit)
- **The release gate has not run on this branch.** Not run: mutation testing with fingerprinted acceptances, the live labs on the merged commit, the outside-model review, the after-publish proof. Only static checks (ruff, `sync_facts --check`, `compat_matrix --check`) and a normal `pytest` run were done.
- **Tests ran on Windows with Python 3.14 only.** Python 3.10 to 3.13 were not run, and the 10 Windows-only failures (signal.SIGHUP, UTF-8 reads, path and quoting in the Action, GitLab and MCP tests) were compared only with plain main on the same machine, not run on Linux.
- **Live runs are older than this commit.** NX-OS: green live run on its own branch (2026-10-28 to 30). RouterOS: one good and one leak run each on `ndr/mikrotik` (2026-10-30). Neither was rerun on the merged commit, `scripts/capture_fixtures.sh routeros` and `nxos` have never been run live from this tree, and the examples' timings come from one run each.
- **Graceful-restart stale paths:** the stale fields on EOS (`routeType.stale`), NX-OS (`pathstaled`) and SR Linux (`stale-route`) were read from existing captures where they are always false; no live graceful restart was captured, so that the fields turn true during a real restart is assumed. FRR (and SONiC through it) was already covered.
- **SR Linux AS-loop prefix count:** not fixed; needs one live capture (see `tests/test_srl_loop_count.py`).
- **RouterOS:** IPv6, add-path, multipath, max-prefix and graceful-restart behaviour not captured (they refuse or raise); MikroTik has not answered the terms question (commercial use of free CHR, a CI download, more than one CHR per lab); one CHR node per lab until then.
- **Interaction with 0.4.0 and Junos is untested:** the registration conflicts will be resolved again at the rebase, and nothing here has run next to the Junos driver or the 0.4 `verify_change` code.
- **Docs and release surfaces:** no changelog entry, no public docs, no examples page, no website or registry change; both drivers stay UNRELEASED. The compatibility page is only a draft (`docs/compat-draft-0.4.1.md`).
- **`ndr/v041-prep`** (versioning policy, EOS out-delay reader, compact MCP results, the warm re-verify planner) is not merged; it goes in after 0.4 ships.

## Cold review of this branch (fresh agent, 2026-10-30) and what was done
A reviewer who knew nothing of the work read `git diff origin/main...ndr/release-0.4.1` for false approvals, registration mistakes and tests that cannot fail. Findings and handling:
1. **RouterOS: a policy-rejected path was detected only by the separate `filtered` key** (confirmed by editing a fixture: a row with `contribution: filtered` and no `filtered` key was counted as accepted, so `bgp_prefixes exact` and `route present` could pass on a rejected prefix). Fixed test-first on `ndr/mikrotik` (83a7686): the two signals must agree, a disagreement raises, and `filtered` follows the contribution.
2. **Compatibility limit text contradicted the code** (EOS, SONiC, SR Linux, NX-OS limits said a stale path "counts as present and best; no stale marker is read yet", while this branch refuses stale paths). Rewritten in `tests/compat_verified.json` and the generated page (`website/docs/reference/compatibility.md`, `llms-full.txt`) and the draft regenerated: the mark is read from the NOS's own field, and the text says plainly that no live graceful restart has been captured. The NX-OS line is not on the public page (unreleased). These public-page edits ship only with the release.
3. **RouterOS VRF sessions were assumed to carry an `@VRF` suffix** (a VRF session without it would have been read as the default VRF). Fixed test-first (83a7686): the address suffix and the `routing-table` key must agree for sessions, and `vrf` and `routing-table` for connections; a disagreement raises. The `@VRF` naming itself is still only in the hand-written fixture (no live VRF capture), listed above as unverified.
Checked and found clean by the reviewer: driver detection order, the RouterOS REST layer (non-2xx, empty body, non-JSON, status 0), IPv6 and ping-in-VRF refusals, exact-prefix matching, NX-OS null-versus-empty handling, stale handling, registration consistency (DRIVER_NAMES, DRIVERS, PLATFORMS, UNRELEASED, EXAMPLES, compat data, capture script), no public mention of the unreleased drivers, and that no must-fail cell can pass on unreadable output. Not covered by the reviewer: `test_nxos*`, `test_routeros_rest`, `test_driver_fuzz` were not run by it (run here: green). A reviewer's pass is not the gate.
