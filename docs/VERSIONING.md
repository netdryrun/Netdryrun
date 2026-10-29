# Versioning and deprecation policy (draft for 0.4.1)

**Status: draft, not published.** It becomes the page `website/docs/reference/versioning.md` in 0.4.1 (RELEASES.md: "a versioning and deprecation policy for the MCP contract, the Action and the result schema"). Until then nothing here is a public promise. Open questions for the owner are at the end.

## Why

Netdryrun is read by programs: CI jobs gate on its exit code, AI agents act on its MCP results, other tools may emit its verdict format. A silent change in any of those is worse than a crash, because the reader keeps going on a wrong assumption. Two things already happened that this policy would have shaped:

- 0.3.2, a patch release, renamed the pass verdict (`SAFE TO PROCEED` became `CHECKS PASSED (only what the checks cover)`). It was the right change: the old text overclaimed, and readers that matched the text now fail closed. But it was a breaking change in a patch release, announced only in the changelog.
- The verdict format (`netdryrun.report/v1`) already has add-only rules in its spec; the MCP result, the verify report, the Action and the CLI have none written down.

## What is a contract

Only these are covered. Everything else (the Python modules, log lines, the wording of `detail` strings, the order of checks run concurrently, the commands a driver sends) can change in any release.

| Contract | Where it is defined | What is stable |
|---|---|---|
| **Verdict strings** | `website/docs/spec/verdict-v1.md`, `skills/netdryrun/SKILL.md` | The three strings, exactly. **Frozen**: never changed or deprecated within a schema version |
| **Statuses and exit codes** | the spec; `website/docs/reference/cli.md` | `passed`/`failed`/`error`/`inconclusive` and exit codes `0` `1` `2` `3` with their meaning. **Frozen** within a schema version. New statuses may be added; readers already treat anything but `passed` as not applicable |
| **Result documents** | `website/docs/schemas/report-v1.json`, `mcp-result-v1.json`, `verify-v1.json` | Each identifier's fields: added, never removed, renamed or retyped (the spec's existing rule, extended to all three). A break gets a new identifier (`.../v2`) and a new schema file; the old one stays published |
| **MCP tools** | `src/netdryrun/mcp_server.py` | Tool names, parameter names and types, defaults, and the result fields above |
| **The GitHub Action** | `action.yml` | Input and output names, their meaning and defaults |
| **The CLI** | `website/docs/reference/cli.md` | Command names, option names and defaults, exit codes, the report files `--json`/`--junit`/`--markdown` write |
| **The check file** | `website/docs/reference/config.md` | Keys and accepted values of `netdryrun.yml` and the verify intent file. An unknown key stays an error (exit 2), never ignored |
| **Capability statement** | `website/docs/capabilities.json` | Its field names; its content follows each release |

## Version numbers

Netdryrun is `0.x` (PyPI classifier Alpha). Until 1.0:

- **A patch release (`0.x.y`) never breaks a contract.** It adds, fixes, and starts deprecations.
- **A minor release (`0.x`) may remove what was deprecated** under the rules below, and nothing else.
- **1.0** means: the contracts above have gone two minor releases without a breaking change, and an outside user depends on them. From 1.0 on, removals need a major release.

**The one exception: verdict safety.** A fix that makes a check fail where it used to pass on a broken network (a false pass) ships in any release, patch included, and is not a breaking change. It is listed under "Fixed" with what used to pass. The same holds for refusing an input that used to be silently accepted and could test nothing (0.3.1's strict parsing). Netdryrun never keeps a false pass for compatibility. A change in the other direction (something that failed now passes) is never a fix-only change: it needs the same justification and changelog entry as a new feature.

## Deprecation

A contract item is deprecated, not removed:

1. **Announced** in the changelog under "Deprecated", with the replacement and the release that will remove it.
2. **Warned at runtime** every time it is used: on the CLI as a line on stderr starting with `deprecated:`; in MCP results in `warnings` (already in the schema); in the Action as a `::warning::` annotation. A deprecated `netdryrun.yml` key is still accepted and warned, never silently ignored.
3. **Kept working** for at least **two minor releases and 90 days**, whichever is later.
4. **Removed** only in a minor release, under a "Breaking change" heading with who is affected and how to migrate (the 0.3.2 entry is the model).

Frozen items (verdict strings, statuses, exit codes) are never deprecated within a schema version. Changing them means a new schema identifier, published next to the old one for at least the same two minor releases and 90 days.

## Beta drivers

A driver marked beta (Cisco NX-OS from 0.4.1; Juniper if it ships as beta) is covered by the same verdict rules: fail closed, an error is never "nothing", must-fail coverage for every check type. What beta does not promise: that the platform's limits stay where they are, that the image versions on the compatibility matrix stay supported, and that the driver keeps its name. A beta driver leaves beta when outside users confirm it in use (the compatibility page already says so). Dropping a beta driver follows the deprecation rules.

## The Action and the package

- Release tags (`vX.Y.Z`) are immutable; the docs pin an exact tag (`netdryrun/netdryrun@v0.4.1`), and `sync_facts.py` keeps every pinned reference on the current release.
- The Action installs the Netdryrun version that matches its tag. A workflow pinned to an old tag keeps getting that version.
- A yanked PyPI release (0.3.0) stays yanked; its advisory names the release that replaces it.

## How it is enforced (0.4.1 work)

- **A contract snapshot test.** `tests/contract_snapshot.json`, generated from the code: MCP tool names, parameters and defaults; `action.yml` inputs and outputs; CLI commands, options and defaults; exit codes; the frozen strings; the field lists of the three schemas. A test regenerates it and compares. Any difference fails CI until the snapshot is regenerated **and** the changelog's unreleased section has an "Added", "Deprecated" or "Breaking change" line naming the item. A removal without a prior deprecation fails outright.
- **The schema test** already checks every result against its JSON Schema; it extends to check that each schema only adds properties relative to the previous release's file.
- **Deprecation warnings are tested** like any output: a deprecated input produces the warning on all three surfaces.

## Open questions for the owner

1. Is "two minor releases and 90 days" the right floor while there are few outside users? Shorter (one minor, 30 days) keeps 0.x nimble; longer reassures early adopters.
2. Should the Action get a floating major tag (`v0`) for users who want fixes automatically? It conflicts with "pin an exact tag", and a floating tag can change what a pinned workflow runs.
3. Does the Python API (`netdryrun.runner`, `netdryrun.drivers`) stay explicitly internal until 1.0? This draft says yes.
4. Should the 0.3.2 verdict-string rename get a retroactive note in the changelog, saying it would be a minor-release change under this policy?
