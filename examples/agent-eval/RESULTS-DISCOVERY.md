# Unprompted discovery eval: results (Claude Code baseline)

Run 2026-10-29 to 2026-10-30, on Netdryrun 0.3.2 as released. The protocol is [PREREGISTRATION-DISCOVERY.md](PREREGISTRATION-DISCOVERY.md), committed before any counted run. Per-trial tables are in `results/<run>/summary.md`, and the transcripts sit beside them.

## Headline

**0 of 20 pair trials discovered Netdryrun. 0 chose it, 0 completed a run, 0 chose again, and 0 wrong selections.** Across all 28 trials, Claude Code never searched the web, never fetched a page, and never added an MCP server. It did that even though the prompt said it may search, install, and add servers from the MCP Registry. The name `netdryrun` occurs 0 times in all 28 transcripts.

| Run | Model | Pair trials | Found | Chose | Completed | Explained correctly | Chose again | Wrong selections (N1, N2) | First break |
|---|---|---|---|---|---|---|---|---|---|
| disc-claude-default-1 | claude-opus-4-7 | 5 | 0 | 0 | 0 | 0 | 0 | 0 | 5 × (a) distribution, "never looked" |
| disc-claude-default-2 | claude-opus-4-7 | 5 | 0 | 0 | 0 | 0 | 0 | 0 | 5 × (a) distribution, "never looked" |
| disc-claude-haiku-1 | claude-haiku-4-5 | 5 | 0 | 0 | 0 | 0 | 0 | 0 | 5 × (a) distribution, "never looked" |
| disc-claude-haiku-2 | claude-haiku-4-5 | 5 | 0 | 0 | 0 | 0 | 0 | 0 | 5 × (a) distribution, "never looked" |

- **Contamination:** none. No local file exposed the name.
- **Setup failures:** none. There were no timeouts and no crashes.
- **Cleanup:** each trial removed only its own `clab-lab-*` labs. One container another session started during N2 (`vibrant_einstein`) was there before and after, and was left alone.

## What the agent did instead

In every pair trial it worked the ticket with the lab directly. It deployed the topology with containerlab, read routes with `vtysh` and pinged, then answered.

| Run | Bash calls | Read | Edit | WebSearch | WebFetch |
|---|---|---|---|---|---|
| default-1 | 78 | 77 | 8 | 0 | 0 |
| default-2 | 85 | 73 | 5 | 0 | 0 |
| haiku-1 | 200 | 82 | 10 | 0 | 0 |
| haiku-2 | 184 | 78 | 11 | 0 | 0 |

So the first break isn't "searched and didn't find it" or "found it and didn't trust it". **The agent never looks.** It already has a method it trusts (containerlab plus show commands), and nothing in the tickets makes that method look insufficient.

A separate unprompted selection test on 2026-10-30 found the same thing, 0 of 3. It used an even barer prompt ("this BGP change looks wrong; verify it", no lab, tool or MCP hints) on a repo that never named the tool.

## Predictions vs result

- **Claude Code, default model.** Predicted: 0 or 1 of 5 discovered, with most first breaks at (a). Result: **0 of 5, twice. All breaks at (a).**
- **haiku.** Predicted: 0 of 5. Result: **0 of 5, twice.**
- **Wrong selections.** Predicted: 0. Result: **0.**
- **Contamination.** Predicted: at most 1 per run. Result: **0.**

The prediction that open models would sometimes search couldn't be tested (see "Not run").

## The break, and the fix it points to

**Break: (a) distribution, "never looked", in 20 of 20 pair trials.** Search ranking doesn't explain it, because no search was made. Better listings or SEO would not have changed these trials. What would:

1. **Placement by humans:** the tool is already in front of the agent before it starts. That means a line in the repo's `AGENTS.md` or `CLAUDE.md`, a CI check whose output the agent reads, or a configured MCP server. The with/without eval for 0.4 (arm "with") measures it.
2. **A task where the agent's own method visibly falls short.** That's a candidate second selection test, a before/after across hundreds of prefixes. It's written but not run.

## Corrections made after the runs (none change the funnel)

- **Stage markers.** The marker between a pair's two tickets went through Python's file buffer, while Claude Code wrote straight to the same file. So it landed at the end of each transcript, and the grader gave ticket 2's events and answer to ticket 1.
  - The harness now flushes the marker before the agent's next stage.
  - The 20 pair transcripts were repaired by moving the marker to just before the first session init that opens `ticket-2`. The originals are kept as `transcript.orig.jsonl`.
  - The discovery signals were 0 in both versions, so the funnel is the same either way.
- **Answer reader.** It takes a stage's last result that carries a JSON block. In haiku-2 P3, a background command finishing woke the agent after its answer, and the wake-up reply had no JSON.
- **Regrading.** All four runs were regraded with `--no-rerun`. The grader's hidden reruns of applied changes weren't redone, so correctness of the agents' answers ("solved") isn't reported here. It isn't a funnel measure.
- **Run order.** `disc-claude-default-2` was stopped after P3 for a WSL restart. P4 and P5, then N1 and N2, ran after it, on the same harness version apart from the flush fix.

## Not run

- **Goose, OpenHands, Cline (Amendment 2) and `open_agent.py`.** Held on 2026-10-30 until the with/without eval for 0.4, under the project plan. Their N2 dry runs worked (`results/dryrun-*`, not counted).
- **Claude Code on Linux.** It needs a long-lived login token; see the pre-registration.

## What this can't show

Twenty pair trials, one host and two models, on one laptop with the lab in WSL, over two days. Tickets that tell the agent a lab is available may make its own method look sufficient, which works against looking. An agent in the wild with no lab might search more. This run doesn't show it.
