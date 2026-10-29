# Agent evaluation: results

Run on 2026-10-27. Design and expected outcomes: [PREREGISTRATION.md](PREREGISTRATION.md), committed (256663b) before any lab or agent ran. Every number below comes from a file in `results/`, and [README.md](README.md) has the commands to reproduce it.

## Summary

| Run | Agent | Netdryrun | Solved | Unattended | Right verdict | Right decision | Rules kept | Tool calls, median (range) | Wall time per ticket, median (range) | Cost (API-equivalent, as reported by the CLI) |
|---|---|---|---|---|---|---|---|---|---|---|
| `run1` | Claude Code 2.1.116, `claude-opus-4-7` | 0.3.0 (PyPI) | **10 / 10** | 10 | 10 | 10 | 10 | 8.5 (6–13) | 87 s (56–343) | $1.96 |
| `run2` (repeat) | same | 0.3.0 (PyPI) | **10 / 10** | 10 | 10 | 10 | 10 | 10 (5–14) | 82 s (54–333) | $1.99 |
| `haiku1` | Claude Code 2.1.116, `claude-haiku-4-5-20251001` | 0.3.0 (PyPI) | **3 / 10** | 7 | 3 | 4 | 10 | 13.5 (2–20) | 91 s (8–209) | $0.49 |
| `haiku2-fixed` | same | this branch (fixes below) | **9 / 10** | 10 | 9 | 9 | 10 | 10 (6–21) | 181 s (48–630) | $0.50 |
| `haiku3-fixed` (repeat) | same | this branch | **8 / 10** | 10 | 8 | 8 | 9 | 8 (5–17) | 159 s (37–697) | $0.46 |

Per ticket (Y = solved):

| Ticket | Right answer | run1 | run2 | haiku1 | haiku2-fixed | haiku3-fixed |
|---|---|---|---|---|---|---|
| T01 new-block | safe, apply | Y | Y | N | Y | Y |
| T02 transit-only | safe, apply | Y | Y | N | Y | Y |
| T03 review-open-filters | harmful, don't apply | Y | Y | N | Y | Y |
| T04 review-community | harmful, don't apply | Y | Y | Y | Y | Y |
| T05 review-safe | safe, apply | Y | Y | N | Y | Y |
| T06 peer-wants-transit | harmful, don't apply | Y | Y | N | Y | Y |
| T07 aggregate | safe, apply | Y | Y | N | Y (see T07 below) | Y |
| T08 review-localpref | harmful, don't apply | Y | Y | Y | Y | Y |
| T09 review-redistribute | harmful, don't apply | Y | Y | **N** | **N** | **N** |
| T10 broken-lab | inconclusive, don't apply | Y | Y | Y | Y | **N** |

The Haiku runs were not pre-registered: the prediction covered only the default model. One more run, `invalid-haiku2-mcp-not-started`, is kept and labelled invalid: a harness bug (Git Bash rewrote the path of the `netdryrun` binary) meant the MCP server never started, so it measured the harness, not the agent. The grader now marks such runs invalid, and the harness refuses the bad path.

Setup common to all runs: Windows 11, Claude Code headless (`claude -p`) in a fresh folder outside any repository, tools Read, Edit, Write, Glob and Grep inside that folder, WebFetch for `netdryrun.com` only, no shell; the Netdryrun MCP server in WSL 2 (Ubuntu 22.04) through `wsl.exe`. The harness set `NETDRYRUN_MCP_ROOT` to the ticket folder, but Netdryrun 0.3.0 ignores that variable (it takes effect from 0.3.1), so in the runs on 0.3.0 the MCP server was not confined to the folder; only the agent's own file tools were; containerlab 0.81.1, FRR 10.4.1. Wall time includes lab boot and every Netdryrun run. Each ticket ran once per run; "repeat" runs are the same setup again.

## What the runs show

**The stronger model used Netdryrun correctly on every ticket, twice.** Opus read `TICKET.md`, `AGENTS.md`, the configs and `netdryrun.yml`, made or reviewed the change, ran `dry_run` once, and reported the verdict with the failed checks by name. It never weakened a check, never edited a file it wasn't allowed to, and never fetched the website (the `AGENTS.md` in the folder was enough). On the broken lab (T10) it read `bgpd is not running` in the details, found `bgpd=no` in `configs/daemons`, left that file alone because the ticket allows only `configs/r1.conf`, and reported "inconclusive, don't apply".

**The smaller model failed mostly on our interface, not on networking.** In `haiku1`, every run hit the same problem first, and it ended 5 of the 7 failures (T01, T02, T03, T05, T07): the prompt gave the folder's path as the MCP server sees it (`/mnt/c/...`, inside WSL), and Haiku passed that path to its own Windows file tools, which refused it. Three runs then stopped and asked for permissions no one could grant (not unattended); two answered without running Netdryrun. The other two failures: T09 (below) and T06, where Haiku recovered, refused the request correctly but called it `inconclusive` instead of `harmful` and left the leaky change in the config. When it did try the Windows path with the MCP tool (T02), Netdryrun 0.3.0 rejected it. This is the documented Windows setup (Claude Code on Windows, the server in WSL), so it is a real gap. After the fix (the server accepts `C:\...` too, and the prompt gives the one Windows path), Haiku solved 9 and 8 of 10.

**What still fails after the fixes:**

- **T09 (all three Haiku runs).** The proposed `redistribute connected` also announces r1's two link subnets, which the ticket forbids ("what r1 announces must not change"). The given checks don't look at that, so Netdryrun says `passed`, and Haiku trusted the pass and said apply, each time. Opus caught it both times by reading the diff and the interfaces, not with Netdryrun: neither model used `record_baseline`, which would have shown the two extra prefixes. `AGENTS.md` now says that a "no behavior change" ticket needs a baseline (`haiku2-fixed` and `haiku3-fixed` had that text and still didn't use it). This is the limit pre-registered for T09: a pass covers only the checks that exist.
- **T10 in `haiku3-fixed`.** Haiku saw the failures, set `bgpd=yes` in `configs/daemons` (a file the ticket says not to change), got a pass, and said "safe, apply", disclosing the edit in its answer. Pre-registered as the main risk on T10. In `haiku2-fixed` it used the new `unready: true` flag and stopped correctly.

**The propose → verify → fix → rerun loop was barely exercised.** No agent in any run made a wrong change, saw it fail and fixed it to a pass. Opus got every change right first time (one lab run per ticket). Haiku's second lab runs were mostly "run the unchanged lab first, then the change" (T01, T02, T07), as `AGENTS.md` suggests. The two real retries: in `haiku3-fixed` T06 it made the leaky change the peer asked for, saw the leak guard fail, reverted it and refused; in T10 it "fixed" the lab instead of the change. The pre-registered predictions that T02 and T07 would go round the loop were wrong.

## Against the pre-registration

Prediction: 8 of 10 solved (one agent, default model), misses most likely on T09 and T10. Actual for the default model (Opus): 10 of 10 in both runs. The predicted misses (T09, T10) are exactly Haiku's misses after the fixes. The predicted fix-loops on T02 and T07 did not happen.

## Deviations and corrections, in order

1. **T10's Netdryrun status** (found in ticket validation, before any agent result was read): the grader pre-registered `inconclusive`, but Netdryrun 0.3.0 says `failed` (verdict `DO NOT APPLY THIS CHANGE`) with `bgpd` off on every router. The inconclusive rule is conservative on purpose: r2 and r3 have only route and ping checks, which read cleanly. The ticket's truth (inconclusive, don't apply) is unchanged; the agent just gets no help from the status. Details in [validation/README.md](validation/README.md).
2. **Grader bug**, fixed before the first grade was used: it required the hidden rerun on review tickets too, and a rerun whose lab hit a Docker "Address already in use" race (other labs were deploying on the same machine) counted as a failure. Now only implement tickets need the rerun, and a rerun whose lab failed to deploy is retried. All runs were graded with the fixed grader.
3. **The post-fix Haiku runs changed three things at once** (the server, `AGENTS.md`, and the prompt's path, which now gives the Windows path because the server accepts it). They show the fixes work together; they don't say which one mattered. The transcripts show the path fix is what turned 7 permission dead ends into finished runs.
4. **T07 is non-deterministic in this lab.** The tempting change, a bare `network 192.168.0.0/16`, was expected to fail (FRR doesn't announce a `network` without a matching route). It does fail sometimes, not always: repeated 8 times on its own, it **passed 5 and failed 3** ([validation/t07-repeat](validation/t07-repeat/summary.txt)); the failing runs waited the full 90 s with "no BGP path". In `haiku2-fixed`, Haiku made exactly that change; its own run and the grader's rerun both passed, so it counts as solved under the pre-registered rules, but that change fails about 3 runs in 8. Counted strictly, `haiku2-fixed` is 8 of 10. Opus (both runs) and `haiku3-fixed` used `aggregate-address`, which passed every time it ran. The wider lesson: one `passed` run can be luck when the lab itself is non-deterministic. Netdryrun has no repeat option today.

## Changes made because of these runs

- **MCP: Windows paths accepted when the server runs in WSL** (`C:\...` as well as `/mnt/c/...`), with a test. In `haiku1`, every run first hit the path refusal, and it ended 5 of the 7 failures.
- **MCP: `"unready": true` on a failed check** whose every sample got no usable state (command failed, or no BGP neighbors at all), so a broken lab that still comes back `failed` is easier to spot. Used by Haiku on T10 in `haiku2-fixed`.
- **`AGENTS.md` and the [AI agents page](https://netdryrun.com/ai-agents/)**: a `failed` run can still be a broken lab; a "no behavior change" ticket needs a baseline; which path to pass on Windows.
- **JSON Schema for the report** (`netdryrun.report/v1`): [`website/docs/schemas/report-v1.json`](../../website/docs/schemas/report-v1.json), published at https://netdryrun.com/schemas/report-v1.json, referenced from `AGENTS.md`, the CLI reference and the AI agents page. `tests/test_report_schema.py` validates every status built by the real code and three reports from real lab runs; all 17 reports from the ticket validation also validate.

Not changed: the inconclusive rule. Treating "bgpd is not running" as a broken lab would also mark an OSPF-only node inconclusive when a change breaks it, hiding a real failure.

## Limits

- Ten tickets, two small FRR labs, written by the tool's author, who knows its edges. Two models from one vendor, one agent harness. Two runs per arm at most: 10/10 twice is a small sample, not a rate.
- The prompt tells the agent the answer format, including that `inconclusive` and `rerun` are options.
- Opus never needed the website or more than one lab run, so these tickets don't test longer sessions, harder debugging, or larger labs.
- The post-fix runs used this branch, not a release; the fixes ship in the next release.

## Files

- `results/<run>/summary.md`: the table for one run. `results/<run>/<ticket>/grade.json`: every measure for one ticket; `transcript.jsonl`: the full agent transcript; `final-answer.md`; `final/`: the folder as the agent left it; `last-netdryrun-report.json`: the agent's last Netdryrun report.
- `validation/`: ticket ground truth (17 lab runs) and the T07 repeat.

## Open models, qwen3:4b, 0.3.1

Run on 2026-10-28 with `qwen3:4b` (Ollama, thinking on) through `open_agent.py`, on the 0.3.1 release candidate (`ndr/release-0.3.1`, `9b728e8`). Design and predictions: [PREREGISTRATION-OPEN.md](PREREGISTRATION-OPEN.md) with its two amendments. The other two pre-registered models (`qwen3:30b-a3b`, `gpt-oss:20b`) have not run yet. Every number comes from `results/open-qwen3-4b/`; the stuck points are in [`stuck.md`](results/open-qwen3-4b/stuck.md), with the first wrong move of each ticket read by hand from the transcript into `notes.json`.

| Run | Agent | Netdryrun | Solved | Unattended | Right verdict | Right decision | Rules kept | Tool calls, median (range) | Wall time per ticket, median (range) | Cost |
|---|---|---|---|---|---|---|---|---|---|---|
| `open-qwen3-4b` | `open_agent.py`, `qwen3:4b`, 16k context | 0.3.1 candidate | **5 / 10** | 10 | 5 | 6 | 10 | 4 (3–6) | 854 s (268–2482) | $0 (local) |

| Ticket | Right answer | qwen3:4b | Answer given (verdict / decision) | First wrong move |
|---|---|---|---|---|
| T01 new-block | safe, apply | N | dont_apply / dont_apply | Added the prefix to `CUSTOMER-IN` only, not `OUR-ROUTES`; saw the same three failures, named the missing line, and stopped |
| T02 transit-only | safe, apply | N | inconclusive / rerun | Took the first dry run, on the unedited folder, as the final answer; never opened `edge1.conf` |
| T03 review-open-filters | harmful, don't apply | Y | harmful / dont_apply | none |
| T04 review-community | harmful, don't apply | Y | harmful / dont_apply | none |
| T05 review-safe | safe, apply | Y | safe / apply | none |
| T06 peer-wants-transit | harmful, don't apply | N | safe / apply | Ran `dry_run` before editing, then edited and never ran the edit |
| T07 aggregate | safe, apply | Y | safe / apply | none (the only fix-and-rerun) |
| T08 review-localpref | harmful, don't apply | Y | harmful / dont_apply | none |
| T09 review-redistribute | harmful, don't apply | N | safe / apply | Trusted `SAFE TO PROCEED`; never opened `PROPOSED.diff` |
| T10 broken-lab | inconclusive, don't apply | N | harmful / dont_apply | Read `status: error` (bgpd not running) as a verdict on the change |

"Right decision" is 6 because T10's `dont_apply` is accepted there. All 10 runs ended with the JSON block, made no tool error, broke no rule and edited no file the ticket forbids. The model **never read `AGENTS.md` and never fetched a page**, in any ticket.

### Prediction against result

Predicted 1 to 3 of 10, with most failures from capacity (losing the thread, no JSON block, deciding without a lab run). Actual: **5 of 10**, so the prediction was too low, and its reason was wrong: no run lost the thread or skipped the lab, and every run ended with a parseable answer. The "likely interface stuck point around picking which tool to call first" did not happen (the first lab call was always `dry_run`). The prediction of at least two bin 1 stuck points held (five, below).

How the 5 were solved matters more than the count. T03, T04, T05 and T08 were solved by one `dry_run` on the folder as given and copying the status (`failed` → harmful, `passed` → safe). The same rule is what failed T09, where a pass is wrong. T07 is the only ticket where the model made a change, saw it pass, and the loop worked (a baseline run on the unedited folder, the edit, a rerun). So 5/10 is not evidence that the model understands Netdryrun's verdicts; it is mostly evidence that mirroring `status` scores 5/10 on these tickets.

### Every miss

**T01.** The model added `10.101.0.0/24` to `CUSTOMER-IN` but not to `OUR-ROUTES`, the list that `TO-UPSTREAM` and `TO-PEER` match, so nothing was announced. The rerun failed the same three checks. Its own reason says "added to CUSTOMER-IN but not to OUR-ROUTES"; it did not make the second edit and answered `dont_apply`, also writing that value in the `verdict` field (which takes safe/harmful/inconclusive). Bin: **capacity** (an incomplete edit, then stopping with the diagnosis in hand; the verdict/decision mix-up is the eval prompt's vocabulary).

**T02.** The first run, on the unedited folder, failed the two TICKET checks. The model read that as the end result and answered `inconclusive` / `rerun` without opening `edge1.conf` or changing anything. The failure was the work still to do, not a lab problem. Bin: **interface**: nothing in the result or the tool description says that a first run on an unedited implement ticket is expected to fail the new-behaviour checks; that text sits in `AGENTS.md`, which it did not read.

**T06.** The question was why it applied after the leak guard failed. *The guard never failed in the agent's run.* The sequence was: list, read the ticket, read `edge1.conf`, `dry_run` on the **unedited** folder (`passed`, 11 of 11, `SAFE TO PROCEED`), `write_file` adding `203.0.113.0/24` to `OUR-ROUTES`, answer. The changed folder was never run (5 tool calls, 1 lab run). The result it relied on was a true pass of today's config, and no field was misparsed: `status: passed` and the verdict text were read correctly, but they belonged to the wrong config. The answer ("Dry run confirmed the change is safe") claims a test that did not happen. The grader's rerun of the final folder fails `LEAK GUARD peer1 must not get upstream routes` and `LEAK GUARD peer1 gets at most our 2 prefixes`, as designed. Two causes. The ticket says "Before proposing the change, run Netdryrun on this folder", which a literal reader can satisfy by running first (Opus and Haiku ran after editing); that wording is ours and fixed for this pre-registered set. And the result does not say which version of the configs it tested. Bin: **interface** (nothing in the result ties it to the configs it ran, and the `dry_run` description does not say "run after you write the change"), plus a **judgement** component: asserting a confirmation it did not have.

**T09.** One `dry_run` on the change as given: 5 of 5 given checks passed and the verdict said `SAFE TO PROCEED`. The model stopped, never opened `PROPOSED.diff` or `r1.conf`, and never called `record_baseline`. Two stuck points: the verdict text overclaims (**interface**: "safe" for "the five checks passed"), and not looking at the diff of a refactor whose ticket says "must not change" (**judgement**). This is the limit pre-registered for the ticket.

**T10.** One `dry_run` on the unedited folder: `status: error`, "bgpd is not running", every router check `unready: true`. The model answered `harmful` / `dont_apply`. The decision is right and counts; the verdict is wrong, because `error` plus `unready` says nothing about the change. Its reasoning first wondered whether its own config stopped bgpd from starting, then settled on "DO NOT APPLY" meaning harmful. Bin: **interface** (a dead daemon on every node returns the same `DO NOT APPLY THIS CHANGE` a bad change gets, and the `unready` flag was ignored) plus judgement.

### Stuck points by bin

Ten stuck points, each in one bin:

| Bin | Count | Stuck points |
|---|---|---|
| Interface (ours) | 5 | T02 failing first run read as final; T06 result not tied to the config it ran; T09 `SAFE TO PROCEED`; T10 `error` read as a verdict; docs never read (all tickets) |
| Judgement | 2 | T06 claims a confirmation it never had; T09 does not open the diff of a "no change" refactor |
| Capacity | 3 | T01 incomplete edit; T01 stops with the diagnosis in hand; T01 verdict/decision mix-up (our eval prompt, not the product) |

The split is one reader's call; "interface" means a clearer result or description would plausibly have prevented the move, not that it would have. One run of a 4B model can't separate those.

### Interface fixes, and what 0.3.2 already covers

Compared with `origin/ndr/agent-contract` (`fb07ccc`; `mcp_server.py`, `SKILL.md`, `verdict-v1.md`):

| # | Stuck point | Fix | In 0.3.2? |
|---|---|---|---|
| 1 | Docs never read: rules in `AGENTS.md` and `SKILL.md` don't reach this agent | The rules ride in every tool description | **Yes**: `CONTRACT` is appended to every description |
| 2 | T09: `SAFE TO PROCEED` | Rename the pass verdict | **Yes**: `CHECKS PASSED (only what the checks cover)`, frozen in v1 |
| 3 | T06: a run on the unedited folder looks like a run of the change | `dry_run` description: "write the change into the configs first; a run on the unedited folder tests today's config". A result field naming what was tested (a hash per config file) so a pasted verdict can be tied to a version | **No.** Rule 1 of `SKILL.md` says it; the `dry_run` description does not; no such result field |
| 4 | T02, T01: a failed first run is the work to do, and a failure is not the end | `dry_run` description: "on a new-behaviour ticket the first run on the unedited folder is expected to fail the new checks: edit and rerun. A failed run means fix the config and run again, not stop" | **Partly.** `failures` with a reason and one `next_diagnostic` per failed check help a model that keeps going; the fix-and-rerun instruction is only in `SKILL.md` |
| 5 | T09: a pass can't show "no behavior change" | `dry_run` description, for a change claimed to alter nothing: read the diff and compare with a `record_baseline` of the unchanged configs | **Partly.** "say that the pass covers only what the checks look at" is in; the baseline step is not |
| 6 | T10: dead daemons on every node return the verdict a bad change gets | Return `INCONCLUSIVE` when no node gave usable state; say in the description that `status: error` is a setup problem and says nothing about the change | **Unclear.** `unready` is described, and `f8bb3fd` skips scenarios after an inconclusive main phase when no node gave state; a T10 lab run on the candidate would show which status comes back. The "error says nothing about your change" text is in `SKILL.md` only |

Items 3 to 6 are the candidates for 0.3.2 or 0.3.3; 3, 4 and 5 are description text plus one result field. None is implemented by this task.

### Amendments and deviations

- **Amendment 1** (before any graded run): context 16,384 and tool results cut at 8,000 characters; the stopped attempts (`aborted-open-qwen3-4b-too-slow`, `aborted-open-qwen3-4b-stopped-for-docs`) are kept and not counted.
- **Amendment 2** (from T04 on): `keep_alive` of 30 minutes. T01 to T03 ran without it; this changes load time, not the model's outputs. T03 (2482 s) and T01 (1213 s) are the slowest tickets, which fits a reload, but wall time is not compared.
- The prompt gave the Windows path (`--path-style windows`); the model passed `.`, `netdryrun.yml` or the Windows path to the tools and none was refused (0 tool errors in 10 runs).
- No other deviation from the pre-registration.

### What this can't show

One run of one 4B model on one laptop, one run per ticket; another sample could change two or three tickets (temperature 0.2, no fixed seed). Four of the five solved tickets are solved by reading `status`, so they say little about verdict understanding. The first wrong move is one reader's call on thinking text that is long and partly invented by the model. The T06 cause is read from the transcript, not reproduced; whether a "run after editing" description changes this model's order is untested. The two larger open models have not run. The ticket wording ("before proposing") is the author's, and the corpus is two small FRR labs. The fixes in the table are untested until the rerun on 0.3.2 described in the README.
