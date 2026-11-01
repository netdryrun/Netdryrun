# Design note: the `captured-only` driver status

Status: design only. No driver has this status, and no code reads it yet. Written 2026-11-01 for the capture kit.

## Problem

The capture kit lets someone with a licensed image (IOS XE, IOS XR, SR OS, NX-OS) send us the output of a driver's
commands from their own lab node. That is enough to write and test a **parser**: we can prove the driver reads that
output correctly. It is not enough to prove **behaviour**: we have never seen how the NOS reacts to a change, what it
prints for a state no one captured, or how it fails. A driver whose only evidence is captures must not be able to
approve a change on the strength of output nobody has seen.

## The status

Drivers have a status today (supported, beta). A third one, below beta:

| Status | Evidence | May return `passed` |
|---|---|---|
| supported | live runs in our CI on every change | on every check type it implements |
| beta | at least one live run by someone who holds the image, plus every must-fail cell | on every check type it implements, labelled beta |
| **captured-only** | contributed captures only | **only on a check whose every must-fail cell has a capture** |

A **must-fail cell** is a (check type, state) pair that has to make a check fail: `bgp_session` with a session not
established, `route` with the prefix absent, `bgp_route` with `med` on a path without a MED, and so on. The capture
scenarios (`established`, `no-neighbor`, `route-absent`, `no-med`, ...) are named after these cells on purpose: each
contributed bundle is evidence for the cells its scenario shows.

## Rules

1. **No pass without coverage.** For a check on a captured-only node, the runner looks up the check's must-fail cells
   in the driver's coverage table. If any cell has no capture behind it, the check is `inconclusive` with the reason
   "captured-only driver: no capture of <cell> yet", never `passed`. The run's status follows the existing rules, so
   one such check makes a run inconclusive at best. A check can still `fail` on a captured-only node: a failure needs
   no coverage to be believed.
2. **Unknown shape is never a pass.** As for every driver today, output the parser doesn't recognise is an error. On a
   captured-only driver it is reported as "shape not covered by captures", with the command and the NOS version, so a
   capture request can be filed.
3. **Two independent captures before an approving path.** A parser path that can lead to `passed` (for example
   reading a session as established) needs captures from two contributors or two NOS versions. One capture can only
   enable paths that lead to `failed`. This limits what a wrong or poisoned capture can do to producing failures.
4. **Coverage comes from bundles, not from code.** The coverage table is generated from `captures/**/manifest.json`
   (NOS, version, scenario, the sanitiser's self-check, replay passed), not written by hand. A bundle removed or
   invalidated removes its coverage.
5. **Versions are explicit.** Coverage counts only for the NOS versions captured. A node reporting another version
   gets `inconclusive` on every check until that version is captured, or the owner accepts a version range in the
   driver with a written reason.
6. **Promotion is a human decision on live evidence.** A captured-only driver becomes beta only after a live run by
   someone who holds the image and every must-fail cell passing live. Agents may
   prepare the promotion; the owner approves it.

## What it needs before any driver uses it

- A coverage table format and its generator (from bundles), with a test that a missing cell gives `inconclusive`.
- The runner hook: a check on a node whose driver is captured-only consults the table before `passed`.
- Must-fail tests for the status itself: every cell missing in turn must turn a would-be pass into `inconclusive`;
  an unknown version must; a single capture must not enable an approving path.
- Capture scenarios for the cells not in the menu yet (rejected config, VRF state, IPv6 sessions).
- A command table for NOSes with no driver yet. `netdryrun capture` runs a driver's own read methods, so a NOS needs
  at least a driver that knows its commands (with parsers that may raise) before it can be captured.
- The status in `capabilities.json`, the compatibility matrix and the docs, worded so a captured-only driver is never
  presented as supported.

## Rejected alternatives

- **Pass on captured shapes, warn otherwise.** A warning next to a `passed` is still a pass to a pipeline or an agent.
- **Let contributors' captures change existing fixtures.** Captures add evidence; changing a live-captured fixture
  needs CODEOWNERS review as today.
- **Majority vote between captures.** Disagreement between two captures of the same scenario is a bug report, not a
  vote: the cell stays uncovered until a human looks.
