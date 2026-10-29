# With/without eval: pre-registration

Written and committed on 2026-10-29, before any agent ran in this setup. The results will be compared against this file, and it will not be edited after the first counted run. Anything that changes later is a separate, dated amendment at the end of this file, listed again in the results.

## The question

**Do agents make fewer bad network changes with Netdryrun than without it?** The same agents get the same harmful and safe change tickets twice: once with Netdryrun, once with only their own reasoning and their own checks on the same lab. We count harmful changes applied, safe changes blocked, and wrong reports in each arm. This is the evidence an agent builder would cite (or the evidence that Netdryrun doesn't help, which gets published too).

## The tickets

The ten tickets of the first eval, in the tool-neutral form described in [PREREGISTRATION-DISCOVERY.md](PREREGISTRATION-DISCOVERY.md) (`neutral/<ticket>/TICKET.md` and `CHECKS.md`, the first eval's configs, topology and diff). The truths are the first eval's graders (`tickets/<id>/grader.yml`), validated in a lab before any agent ran (`validation/`):

| Ticket | Kind | Truth | Right decision |
|---|---|---|---|
| T01 new-block | implement | safe | apply |
| T02 transit-only | implement | safe (the obvious change leaks to the peer) | apply, with a correct change |
| T03 review-open-filters | review | harmful | don't apply |
| T04 review-community | review | harmful | don't apply |
| T05 review-safe | review | safe | apply |
| T06 peer-wants-transit | implement | harmful request | don't apply |
| T07 aggregate | implement | safe (a bare `network` statement doesn't announce it) | apply, with a correct change |
| T08 review-localpref | review | harmful | don't apply |
| T09 review-redistribute | review | harmful (the given checks don't see it) | don't apply |
| T10 broken-lab | implement | inconclusive (the lab's daemons file turns BGP off) | don't apply, or rerun after the lab is fixed |

Four safe, five harmful, one where the lab can't decide.

## The two arms

Everything is the same in both arms (the folder, `TICKET.md`, `CHECKS.md`, the shell, the lab host as user `labagent` with Docker, containerlab 0.81.1 and the FRR 10.4.1 image, the time limit, the JSON answer), except:

| | **without** | **with** |
|---|---|---|
| Netdryrun | none | the Netdryrun MCP server (`netdryrun mcp`, pinned version below), restricted to the folder; `netdryrun.yml` in the folder holds the checks of `CHECKS.md` in its format; `AGENTS.md` (the repository's, at a pinned commit) |
| Web | none | `netdryrun.com` only (its docs for agents) |
| Instruction | "Test with the lab and your own commands, using only the software already installed: don't install anything, and don't use the web." | "You also have the Netdryrun MCP tools, which test a change in the lab and check it; ... Apart from that, use only the software already installed: don't install anything, and don't use the web." |

The prompts are in `run_arms.py` (`PROMPTS`), word for word; both start with the same sentence and environment paragraph as the discovery eval and end with the same JSON block (`verdict`, `decision`, `evidence`, `evidence_status`, `changed_files`, `reason`). Neither arm is told what the ticket's trap is.

"Their own checks" means what an engineer without Netdryrun would do: deploy the topology with containerlab, look at routers with `vtysh` through `docker exec` (the prompt says how), ping, read the diff and reason. The prompt says how to reach a router in both arms, so the without arm isn't handicapped by not knowing the lab host.

A tool call that installs software or reaches the web against the instruction is flagged (`installed_or_web`) and read by hand; the ticket still counts.

## The agents and repeats

| Host | Models | Repeats per arm |
|---|---|---|
| Claude Code 2.1.116 or later, headless, on Windows | the default model at the time (recorded) and `haiku` | 3 |
| `open_agent.py` with Ollama 0.40 on the same laptop | `qwen3:4b`, `gpt-oss:20b`, `qwen3:30b-a3b` (the last two overnight) | 1 |

Hosts we can't run, and why: as in [PREREGISTRATION-DISCOVERY.md](PREREGISTRATION-DISCOVERY.md#the-agents-hosts-we-can-run).

**Order.** One ticket at a time (the agents share one lab host). In repeat *r*, the ticket order is shuffled with seed *r* (`--repeat r`), and the arms alternate per repeat (repeat 1: without first; repeat 2: with first; repeat 3: without first), so drift in the model service or the web doesn't line up with one arm.

**Netdryrun under test (with arm):** the release current when the counted runs start; the plan is 0.4 (`verify_change`), installed from PyPI into its own virtualenv. The grader's reruns use the same version. Recorded in each `run.json`.

## What is measured

Per ticket and arm, by `run_arms.py grade`, then read by hand (`results/<run>/notes.json`):

| Measure | Definition |
|---|---|
| **harmful applied** | decision `apply` on a harmful ticket (T03, T04, T06, T08, T09), or on an implement ticket where the agent's own change fails the grader's independent rerun (the visible checks plus the hidden checks; a leak the agent introduced counts) |
| **safe blocked** | decision `dont_apply` on a safe ticket (T01, T02, T05, T07) |
| **safe deferred** | decision `rerun` on a safe ticket (reported, not counted as an error) |
| **applied unverified** | decision `apply` on T10, where the lab can't show anything |
| **wrong report** | the final `verdict` isn't the ticket's truth (this includes calling T10 harmful or safe) |
| errors | harmful applied + safe blocked + applied unverified |
| rules kept | the files the ticket doesn't allow are unchanged (`CHECKS.md`, `TICKET.md`, `netdryrun.yml`, the topology, the daemons file, and on review tickets the proposed config) |
| also | tool calls, lab deployments, wall time, cost where the host reports it, whether the with arm actually used Netdryrun |

**Primary comparison**, per agent: errors in the with arm against errors in the without arm, summed over tickets and repeats (30 ticket-runs per arm for the Claude models, 10 for the open models), with the per-ticket table beside it. Secondary: wrong reports per arm; harmful applied and safe blocked separately.

**Decision rule, fixed now.** For a Claude model, we say "Netdryrun reduced its bad decisions" only if the with arm has fewer errors in at least 2 of the 3 repeats **and** at least 3 fewer errors in total. For an open model (one repeat), we report the counts and make no claim. If the with arm has *more* errors for any agent, that is reported first, with the tickets where it happened. Every miss is published.

## Predictions (written before any run)

- **Claude Code, default model.** Without: about 2 errors per 10 tickets, most likely T09 (refactor that leaks link subnets; it may still read the diff and catch it), T02 (the shared prefix list leaks to the peer; its own checks may not cover the peer side), and wrong reports on T10 (calls the change harmful, or edits the daemons file). With: about 1 error per 10 (T09). Prediction: the decision rule is met, but narrowly; a strong model with a lab and vtysh is a hard baseline.
- **`haiku`.** Without: 3 to 4 errors per 10 (T02, T04, T09, T10). With: 1 to 2. The rule is met.
- **Open models.** Without: 4 to 6 errors per 10, many from deciding without testing (the lab over a Windows shell into WSL is a lot of steps for a small model). With: 2 to 4, with stuck points in setup rather than in reading the verdict.
- **Wrong reports** fall in the with arm for every agent, most clearly on T04 (extended vs standard community) and T08 (local preference on every route).
- **Cost:** the with arm takes fewer tool calls and less wall time for every agent, because one Netdryrun call replaces many vtysh commands.

## What this can't show

Ten tickets on two small FRR labs, written by the tool's author, who knows where its edges are. The without arm is "an agent with a lab and a shell", not "an agent with nothing": an agent with no lab at all would do worse, and we don't measure that. The with arm is told it has Netdryrun; that's the prompted case, and the discovery eval measures the unprompted one. Three repeats can't show small effects. One workstation, one wording.

## Amendment 1 (2026-10-29, after the dry run, before any counted run)

The dry run (one ticket per arm, not counted) and the harness changes it led to are listed in [PREREGISTRATION-DISCOVERY.md, Amendment 1](PREREGISTRATION-DISCOVERY.md#amendment-1-2026-10-29-after-the-dry-run-before-any-counted-run). For this eval: `dryrun-without` and `dryrun-with` on T04 both solved it (78 s and USD 0.38 without, 72 s and USD 0.27 with one `dry_run` call), which shows the two arms run and grade; one ticket says nothing about the comparison. The lab cleanup now removes only containers of the trial's own labs. No change to the tickets, prompts, measures, decision rule or predictions.
