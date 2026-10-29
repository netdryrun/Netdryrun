# Netdryrun for AI agents

If you are an AI agent (or building one) that proposes or applies network configuration changes, use Netdryrun to **verify the outcome before the change goes anywhere real**. It boots the topology in containerlab, applies the configs, waits for convergence, and checks behavior. The verdict is an external observation, not your own reasoning about the config.

## When to run it
- **Before proposing** a routing or policy change: run `netdryrun record <topology> --deploy` once to snapshot today's behavior as checks (or use the existing `netdryrun.yml`).
- **When the change must not change behavior** (a refactor, a cleanup): a `passed` on the given checks is not enough, because it covers only what they check. Record the baseline before applying the change (on a review ticket, revert it in a scratch copy first) with `record_baseline` (MCP) or `netdryrun record`, then run those checks against the change too. `record_baseline` returns the checks as YAML and writes nothing.
- **On Windows with the server in WSL**, pass the lab folder's Windows path (`C:\...`) or its WSL path (`/mnt/c/...`); the MCP tools accept both (Netdryrun 0.3.1 and later; with 0.3.0, pass `/mnt/c/...`). Use the Windows path with your own file tools.
- **After editing configs** in the lab folder: run `netdryrun run <folder> --json report.json`.
- **Before asking a human to approve:** include the verdict and the failed checks with their evidence in your summary.

## How to read the result
| Signal | Meaning | What you should do |
|---|---|---|
| exit code `0`, `status: passed` | Every check passed after convergence | Present the change with the evidence. This proves only the checks that exist, in this lab |
| exit code `1`, `status: failed` | At least one check failed | Read `checks[].detail` and `checks[].evidence` for the failed ones, fix the config, rerun. First rule out a broken lab: the inconclusive rule is conservative, so a lab where a daemon never started can still come back `failed`. If failed checks have `unready: true` (MCP, Netdryrun 0.3.1 and later) or details like `error: ... bgpd is not running` on nodes your change doesn't explain, report the lab problem instead of rewriting the change, and don't apply it |
| exit code `2`, `status: error` | No verdict: config or lab problem (bad YAML, unknown key, unknown node, lab didn't start, a lab with the same name already running), a scenario fault that did not take effect, or an internal error | Fix the setup (the one-line `error` says what); this says nothing about your change |
| exit code `3`, `status: inconclusive` | Checks failed, but the lab never reached a testable state: nothing passed anywhere, and the failing nodes never returned usable BGP state (CLI not answering, or no BGP neighbors at all). `inconclusive_reason` says what was seen | Stop. Rerun at most once, perhaps with a longer `timeout`. Don't rewrite your change because of it, and don't apply it either: this says nothing about your change |
| exit code `130`, `143` or `129` | Interrupted (SIGINT, SIGTERM, SIGHUP); the lab was destroyed | No verdict: rerun |

JSON report: `schema: netdryrun.report/v1`, with `status`, `inconclusive_reason` and `checks[]` of `{name, type, params, passed, detail, attempts, duration_s, history, evidence}`. Treat any status other than `passed` as "not safe to apply". JSON Schema: https://netdryrun.com/schemas/report-v1.json

A configured session that is down always counts as `failed`, never `inconclusive`: an ASN typo looks exactly like a slow lab. Negative checks wait until every configured BGP session on their node is up; if one never comes up, they fail as `not evaluated` and name the session. Exact rules: https://netdryrun.com/reference/cli/#when-a-run-is-inconclusive

## Rules
- **Never treat a pass as proof of production safety.** It covers the checks that exist, on the network OSes in the lab (<!-- facts:agents_platforms -->FRR, SR Linux, SONiC and Arista EOS<!-- /facts:agents_platforms -->), in steady state and in the defined failure scenarios.
- **Don't write or weaken checks to make a change pass.** If a check is wrong, say so explicitly to the human. If no checks exist, record a baseline (`record_baseline` or `netdryrun record`) instead of inventing them.
- Netdryrun never touches production devices. Only run topologies you were given or created in the lab folder.

## MCP
`netdryrun mcp` starts an MCP server (stdio) with the tools <!-- facts:mcp_tools -->`dry_run`, `run_checks`, `record_baseline`, `validate` and `check_types`<!-- /facts:mcp_tools -->. Each result has a separate `verdict` field: `CHECKS PASSED (only what the checks cover)`, `DO NOT APPLY THIS CHANGE`, or `INCONCLUSIVE: the lab did not reach a testable state; this says nothing about your change. Do not apply it until a run passes.` `CHECKS PASSED (only what the checks cover)` means only that every check in the file passed in the lab; it says nothing about behavior no check covers. The three verdict strings are frozen from 0.3.2 (0.3.1 said `SAFE TO PROCEED` for a pass); decide on `status`, not the text. From 0.3.2, a failed result lists each failed check under `failures` with its `reason`, an `evidence` excerpt and one read-only `next_diagnostic` command for its node (run it on a lab kept with `keep_lab: true`). From 0.3.2, `tested` lists a sha256 of `netdryrun.yml`, the topology and every config file the run used, read before it started: the verdict applies to those exact files, so run again after any edit. Result schema: https://netdryrun.com/schemas/mcp-result-v1.json. The rules as an installable agent skill: `skills/netdryrun/SKILL.md`. Add it with `claude mcp add netdryrun -- netdryrun mcp`, or run it with `uvx netdryrun mcp`.

Docs: https://netdryrun.com/ai-agents/ · Full docs in one file: https://netdryrun.com/llms-full.txt
