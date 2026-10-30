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
