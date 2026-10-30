# Agent speed in 0.4.1: compact results and warm re-verify

RELEASES.md, "Agent-speed and hub track" (2026-10-30). Two items: compact results ship in 0.4.1; warm re-verify is a spike in 0.4.1 and ships in 0.4.x only once it is proven equivalent to a cold run.

## 1. Compact agent results (built, in 0.4.1)

**Problem.** An agent pays for every token of a tool result, and a long result pushes the verdict out of its attention. Before 0.4.1 a `dry_run` result listed every check, every failure and up to 200 file hashes, pretty-printed, with no bound: a 300-check file produced tens of thousands of characters.

**Rule.** Every MCP tool result is compact JSON within `RESULT_BUDGET_CHARS` = 8,000 characters (JSON runs about 3–4 characters per token: roughly 2,000–2,700 tokens). A bigger result is cut in a fixed order, least deciding first:

| Tool | Cut order |
|---|---|
| `dry_run`, `run_checks` | passing checks in `checks` (their count is in `passed`), then `tested.files`, then failures beyond the first |
| `verify_change` | `declared`, `allowed`, `baseline.problems`, `warnings`, `inconclusive.moving`, then beyond the first: `guards.failures`, `undeclared`, `not_happened`, `intent.lines` |

If the kept items still don't fit, their lab text is shortened (`omitted.text`).

**Never cut:** `schema`, `status`, `verdict`, `passed`, `failed`, `error`, `inconclusive_reason`, `evidence_file`, `undeclared_total`, `failed_because`. At least one failure (or undeclared item) always stays. A test asserts no cut list names one of these.

**By reference.** `truncated` (new, add-only within `netdryrun.mcp-result/v1`) is null when nothing was cut; otherwise `{"omitted": {field: count}, "full_result": evidence_file}`. The evidence file now also carries `tested` with every file hash, so nothing a cut result leaves out is lost. Every tool description says results are bounded and where the rest is.

**Tests** (`tests/test_mcp_compact.py`): the budget's range; small results unchanged except compact whitespace and `truncated: null`; a 450-check, 200-file run and a 50-item verify result fit and keep what decides; passing checks go before any failure; inconclusive and error results keep their reason; a Hypothesis property that every run result of up to 900 checks fits with the counts intact; the schema documents `truncated`; the evidence file holds every hash.

**Contract.** Fields only added; the verdict strings are unchanged. Whitespace in the JSON changes (no indentation), which no contract covers. Changelog: 0.4.1 "Added".

## 2. Warm-lab re-verify (spike, off until proven)

**Problem.** An agent iterating on a change pays a full lab boot per attempt (about 60–120 s on FRR, 5–7 minutes on a Nexus 9000v). Most attempts change one router's config.

**Idea.** Keep the lab booted between attempts, apply only the diff, reconverge, recheck.

**The risk is a false pass.** A warm lab carries history a cold one doesn't. The known case: FRR applies a changed inbound route-map only to updates received after it. A warm run that reloads the config but doesn't make BGP re-read what it already received keeps routes the new policy would reject, and a leak guard passes where a cold boot fails. So warm is off until the corpus proves it gives the same verdicts as cold, case by case.

**The plan** (`src/netdryrun/warm.py`, `plan(before, after, topology)`, pure, tested in `tests/test_warm.py`):

- Warm only when the only changed files are the bound `/etc/frr/frr.conf` of FRR nodes. For each such node: `frr-reload.py --reload /etc/frr/frr.conf`, then `vtysh -c "clear bgp * soft"` (re-read received routes, re-send advertisements), then `frr-reload.py --test /etc/frr/frr.conf`, which must print no difference (the change landed).
- Cold, with the reason named: the topology changed; `daemons` or `vtysh.conf` changed; a changed file on a node that isn't FRR (no warm path proven); any other bound file; a file added or removed under a bind, or changed inside a bound folder.
- A changed file no node uses changes nothing (`ignored`).
- After the steps, the run continues exactly as a cold run does after deploy: the same convergence gate, settle and hold windows (stretched for advertisement intervals), then every check.

**The gate** (`equivalence(cold, warm)`): on corpus v1 and v2, each case is run cold (as today) and warm (base lab booted once; for each case, apply its edits warm, run the three strategies, then apply the base back warm and check the base still gives the base verdicts). Any case where a strategy's verdict differs, its failed checks differ, either side errors, or a case is missing from one run is a mismatch. Warm ships only with zero mismatches on both corpora, on the release build, recorded with the version; then once more on every release (a gate layer).

**Spike work left (needs lab time, through the lab lock):** `corpus/run.py --warm` (the runner side above), the "apply base back" step and its own check, timing per case (the success criterion is the RELEASES line: the median agent retry costs one boot), and the first equivalence run. Out of scope for the spike: non-FRR drivers, topology changes, link faults, `verify` (two sides).
