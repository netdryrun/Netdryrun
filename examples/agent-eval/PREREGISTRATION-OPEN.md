# Agent evaluation, open models: pre-registration

Written and committed on 2026-10-28, before any open model ran a ticket. Same tickets, graders, prompt and rules as [PREREGISTRATION.md](PREREGISTRATION.md); this file lists only what differs. It will not be edited after the runs; anything that changes is a separate commit listed in `RESULTS.md`.

## The question

The first eval measured Claude models, which are among the strongest tool-using models. Most agents that will reach Netdryrun in the wild run on other models, often small local ones. **Where does an agent that isn't Claude get stuck with Netdryrun's docs and tools?** The aim is to find the stuck points and fix them in the product, not to rank models.

## The agents

- `open_agent.py`: a plain tool-calling loop, written for this eval, that talks to Ollama (or any OpenAI-compatible API). It gives the model what the Claude Code agent got: file tools (list, read, write, exact-text edit) confined to the ticket folder, fetches limited to `https://netdryrun.com`, the Netdryrun MCP server's tools, no shell, no human, the same prompt word for word.
- Differences from Claude Code, on purpose: a one-line system message saying it works alone with tools; tool results longer than 12,000 characters are cut (with a note saying so); a turn limit of 60; context 32,768 tokens; temperature 0.2. The time limit is 60 minutes per ticket instead of 30, because the models run on a laptop (RTX 4050, 6 GB; 32 GB RAM) and a slow machine shouldn't count as a stuck agent. Wall times are reported but not compared with the Claude runs.
- Models, through Ollama 0.40 on the same machine: `qwen3:4b` (a small model many people run locally) `qwen3:30b-a3b` (the largest open model this machine runs at a usable speed), and `gpt-oss:20b` (OpenAI's open-weight model, common in local agent setups; added before any run, in a separate commit). Thinking on, the Ollama default for these models.
- Netdryrun: the 0.3.1 release candidate (`ndr/release-0.3.1`, commit `9b728e8`), installed from source in its own virtualenv. `AGENTS.md` from the same commit. The prompt gives the folder's Windows path (`--path-style windows`), which 0.3.1 accepts.
- Lab: WSL 2 (Ubuntu 22.04, distribution `Ubuntu-ndr`), containerlab 0.81.1, FRR 10.4.1. One ticket at a time (`--parallel 1`).

## What is measured

Everything in the first pre-registration, graded by the same `run_eval.py grade`, plus `stuck.py`: for each ticket, how the run ended, tool calls and lab runs, which docs it read, tool errors, loops (the same call three or more times), the last tool called, and rule breaks. After each run every transcript is read by hand and the **first wrong move** is written down in one line (`results/<run>/notes.json`).

Each stuck point is then sorted into one of three bins, which decides what happens next:

1. **Our interface** (a tool description, an error message, a doc, a schema, a default): fix it in Netdryrun.
2. **Networking judgement** (misreads a verdict, applies a harmful change): note it; see whether a clearer result or verdict text would have prevented it.
3. **Model capacity** (can't follow a tool-call format, loses the task): note it; not ours to fix.

## Predictions (written before any run)

- `qwen3:4b`: 1 to 3 of 10. Most failures from capacity: losing the thread over many turns, ending without the JSON block, or deciding from the configs without running a lab. Likely at least one interface stuck point around picking which tool to call first.
- `qwen3:30b-a3b`: 4 to 6 of 10. It will run labs; misses most likely on T09 (the given checks pass), T10 (the broken lab) and the implement tickets that need a fix-and-rerun round (T02, T07).
- `gpt-oss:20b`: 4 to 6 of 10, with the same likely misses as `qwen3:30b-a3b`.
- At least two stuck points in bin 1 (our interface) across both models. If there are none, the eval was too easy or too forgiving, and that gets said.

## Then

The same tickets and models run again on the 0.3.2 agent contract (`ndr/agent-contract`: tool descriptions that carry the rules, a typed result with `failures` and `next_diagnostic`), plus any bin-1 fixes from this run. The difference between the two is the measured effect of the contract.

## What this can't show

Three open models on one laptop, one run per ticket, ten tickets on two small FRR labs, tickets written by the tool's author. The agent loop is ours, not a product agent's; a product agent (Codex, Cursor, a vendor copilot) adds its own system prompt and tools.

## Amendment 1 (2026-10-28, before any graded run)

The first attempt was stopped during T01: `qwen3:4b` with a 32,768-token context ran 47% on CPU on this laptop and took about 8 minutes per turn, so ten tickets would have taken more than a day and measured the machine, not the agent. Changed before any ticket was graded: context **16,384** tokens and tool results cut at **8,000** characters (both still note the cut to the model). The stopped attempts are kept as `results/aborted-*`, not counted. `qwen3:30b-a3b` and `gpt-oss:20b` don't fit this GPU at any useful context; they run overnight, one model per night, when nothing else uses the machine.

## Amendment 2 (2026-10-28, during the qwen3:4b run, from T04 on)

Ollama unloaded the model after its default 5-minute idle time while the agent waited on a lab run, then reloaded it on the next turn. From T04 on, requests ask Ollama to keep the model loaded for 30 minutes (`keep_alive`). This changes load time only, not the model, its settings or its outputs; T01–T03 ran without it.
