# Unprompted discovery eval: pre-registration

Written and committed on 2026-10-29, before any agent ran in this setup. The results will be compared against this file, and it will not be edited after the first counted run. Anything that changes later (a harness fix found in the dry run, a ticket that doesn't behave as designed) is a separate, dated amendment at the end of this file, listed again in the results.

## The question

The first two agent evals ([PREREGISTRATION.md](PREREGISTRATION.md), [PREREGISTRATION-OPEN.md](PREREGISTRATION-OPEN.md)) told the agent it had Netdryrun, so they measured only whether an agent can *use* it. This one measures the core thesis directly: **when an agent must validate a network change and nobody names a tool, does it find Netdryrun, choose it, run it, read the result right, and choose it again?** This is the north-star metric, the unprompted selection rate, in `SCORECARD.md`.

The first full run is the **baseline**. It is run before any of the fixes it points to, so that every later fix shows a measured change. Where the path breaks first says what to fix:

| Step | Measured as | If it breaks here, the fix is |
|---|---|---|
| (a) discovers | the agent names Netdryrun in its own words or tool calls (after seeing it in search results, a page, a registry or a package index) | **distribution**: listings, metadata, search presence |
| (b) chooses | it installs Netdryrun, runs it, or configures its MCP server for the ticket, instead of only writing its own checks or picking another tool | **positioning**: the first lines agents read, capability text |
| (c) completes | a Netdryrun run on the ticket's lab ends with `passed`, `failed` or `inconclusive` | **onboarding**: install, setup, the first run |
| (d) reads the evidence correctly | its final verdict and decision are right for the ticket, and the status it reports is the status Netdryrun gave | **result text**: the verdict and evidence wording |
| (e) chooses it again | on the second ticket of the same session, it uses Netdryrun again | positioning (the first use didn't earn the second) |

Also recorded: **wrong selections** (it used Netdryrun as evidence for a task it can't do: the two negative controls below), **setup failures** (chose it but couldn't get a run: the cause, by hand), and **what it used instead** (its own containerlab and vtysh checks, Batfish, pyATS, SuzieQ and so on).

## The tickets

The ten tickets of the first eval, unchanged in substance, in a **tool-neutral form** (`neutral/`, written by `neutral/make_neutral.py` from `tickets/`, committed here):

- `TICKET.md` is the same text, except the rules block. Where it said "run Netdryrun on this folder (`netdryrun run <folder>`, or the `dry_run` MCP tool) and include the verdict", it now says what an engineer would write: "test it in the lab (`topology.clab.yml`, a containerlab topology of this part of the network) and include the evidence. Propose it only if every check in `CHECKS.md` holds." Review tickets: "Base the decision on evidence from testing the change in the lab ...".
- `CHECKS.md` replaces `netdryrun.yml`: the network team's checks and standing guards, the same ones, in plain English.
- The configs, topology and `PROPOSED.diff` are the first eval's files. The lab gets a neutral name (`lab-p1-1` and so on). No file in the folder names Netdryrun (`make_neutral.py` refuses to write a ticket that does).

**Trials.** A trial is one agent session. Five trials are **pairs**: the first ticket, then (in the same session, after the first answer) the second ticket, so step (e) can be measured. Every ticket appears once; each pair mixes the two labs or the two kinds:

| Trial | First ticket | Second ticket |
|---|---|---|
| P1 | T01 new block (implement, safe) | T08 local-pref on every route (review, harmful) |
| P2 | T03 open filters (review, harmful) | T07 aggregate (implement, safe) |
| P3 | T04 wrong community (review, harmful) | T10 broken lab (implement, inconclusive) |
| P4 | T05 hardening (review, safe) | T02 transit only (implement, safe) |
| P5 | T09 redistribute connected (review, harmful; the given checks don't see it) | T06 peer wants transit (implement, harmful request) |

Two **negative controls**, one ticket each, out of Netdryrun's scope on purpose (graders in `neutral/N*/grader.yml`):

- **N1 junos-no-lab**: review a Junos change for two MX routers. "We have no lab for the MX routers and no Junos images." A lab result can't be evidence here.
- **N2 production-state**: an incident question about production this morning (is the upstream session flapping, whose side is it), from a syslog excerpt. Nothing to validate; nothing to apply.

A **wrong selection** is: the agent presents a Netdryrun result (or any lab result) as evidence for N1 or N2. Trying it and then saying it can't model the task is recorded as "tried, out of scope, said so", not as a wrong selection.

## What the agent gets

- A fresh session in a new, empty folder (`%LOCALAPPDATA%\Temp\neteval\<run>\<trial>`, a name that doesn't hint at the tool), outside any repository, with the ticket in `ticket-1/`. The second ticket of a pair is copied to `ticket-2/` only after the first answer.
- **A shell, the lab host, web search, any web page, installs allowed, and a normal MCP setup.** The workstation is Windows 11; the shell is Git Bash (Claude Code's own shell on Windows). The lab host is WSL 2 (`Ubuntu-ndr`), where the agent works as a dedicated user `labagent` with an empty home, Docker, containerlab 0.81.1 (passwordless sudo), the FRR 10.4.1 image, and Python 3 with pip and venv. No uv, no Netdryrun, no other network-testing tool is installed for `labagent`.
- **MCP:** no servers at the start. The prompt says it may add MCP servers, names the official MCP Registry (https://registry.modelcontextprotocol.io, the registry agent hosts read), and says how: write them to `.mcp.json` in the folder and end the turn with `RESTART`; the session then restarts with them loaded and continues (at most twice per ticket). This stands in for an MCP setup with registry access: it names the channel, not the tool.
- No project memory, no CLAUDE.md, no skills, no user MCP servers (Claude Code runs with `--strict-mcp-config --setting-sources "" --disable-slash-commands`). The agent's environment has no variable that names Netdryrun or points at the harness.
- The prompt, word for word (`{wsl_ws}` is the folder's path on the lab host):

  > You are a network engineering agent. Work the ticket in ticket-1/TICKET.md, following its rules. Environment: this is a Windows 11 workstation and your shell is Git Bash. The network lab host is the WSL 2 distribution Ubuntu-ndr; run commands there with `wsl -d Ubuntu-ndr -u labagent -- bash -lc '<command>'` (the current folder is {wsl_ws} there). The lab host has Docker, containerlab 0.81 (run it with sudo; no password is needed), the FRR image the topologies use, and Python 3 with pip and venv. You can deploy a topology with containerlab and look at a router with `sudo docker exec <container> vtysh -c '<command>'`. You may search the web, fetch any page, and install software on the lab host. You can also add MCP servers (the official MCP Registry is https://registry.modelcontextprotocol.io): write them to .mcp.json in the current folder, then end your turn with a line that says only RESTART; the session restarts with those servers loaded and you continue. No human is available during this task: decide on your own. End your answer with a JSON block in a ```json fence with these keys: "verdict" (one of "safe", "harmful", "inconclusive": your judgement of the change or request), "decision" (one of "apply", "dont_apply", "rerun"), "evidence" (in a few words, the tool or method you used to test the change, or null), "evidence_status" (one of "passed", "failed", "inconclusive": what that test showed, or null if you didn't test), "changed_files" (list), "reason" (one or two sentences).

  The second ticket: "Next ticket: ticket-2/TICKET.md, just added. Same instructions as before, and the same JSON block at the end."
- No human input. A permission prompt is denied automatically. Time limit: 30 minutes per ticket for Claude, 60 for the open models (a laptop GPU).

Telling the agent that a containerlab lab exists, and how to reach a router, is deliberate: Netdryrun needs a containerlab topology, so a team without one isn't a team it can serve, and an agent that already knows how to check by hand is the competition Netdryrun has to beat. A second wording that doesn't mention the lab ("make sure this is safe before tonight's window") is for week 3, not this baseline.

## The agents (hosts we can run)

| Host | Models | Trials per run | Runs |
|---|---|---|---|
| **Claude Code** 2.1.116 or later, headless (`claude -p`), on Windows, logged in to the owner's subscription | the default model at the time (recorded from the transcript), and `haiku` | P1–P5, N1, N2 | 2 per model |
| **`open_agent.py`** with Ollama 0.40 on the same laptop (RTX 4050, 6 GB; 32 GB RAM): a plain tool-calling loop with the same tools (file tools, a Git Bash shell, web search, fetch, MCP servers it adds through `.mcp.json` and `RESTART`) | `qwen3:4b`; `gpt-oss:20b` and `qwen3:30b-a3b` overnight | P1–P5, N1, N2 | 1 per model |

The open agent's web search is DuckDuckGo Lite (no key needed); Claude Code's WebSearch is Anthropic's server-side search. **The two search engines differ, so discovery rates are compared within a host, not across hosts.** Open-agent settings as in the open-model eval (16,384-token context, results cut at 8,000 characters, temperature 0.2, 60 turns per ticket, thinking on).

**Hosts we can't run, and why** (so a missing row isn't read as a result):

- Codex CLI, the ChatGPT agent, and any OpenAI-hosted agent: our rules allow OpenAI models only through `research/tools/ask_models.py`, which isn't an agent host.
- Gemini CLI and any Gemini model: excluded by our rules.
- Grok-based agents: same rule as OpenAI.
- Cursor, Windsurf, GitHub Copilot's agent, VS Code agent mode, the Claude desktop app's built-in MCP registry: GUI hosts with no headless mode we can drive here without the browser or extra accounts.
- **Claude Code on Linux** (the more typical agent environment: Codespaces, dev containers, CI). It needs a long-lived token (`claude setup-token`, an interactive login by the owner). Until then, Claude Code runs on Windows with the lab in WSL, which adds friction an agent on Linux wouldn't meet; setup failures caused by the Windows/WSL split are tagged as such and reported apart.
- Product agents on open models (Goose, OpenHands with Ollama): possible later; not in this pre-registration.

## Netdryrun under test

Whatever PyPI and the registries serve at run time: the agent installs it itself. The version it installed is recorded from the transcript. The listings it can find are recorded too (the discovery baseline measures distribution, so the date of the run matters more than the release). The coordinator decides when the full runs happen; the plan is that the counted runs use 0.4 once it's released, with the baseline as early as the coordinator allows.

## What is measured, per trial and ticket

All mechanical signals are computed by `run_arms.py grade` from the transcript, then **every transcript is read by hand** and the hand reading wins where they differ (the mechanical signals are keyword-based and can be fooled). The hand notes go in `results/<run>/notes.json`, one line per trial.

| Measure | Mechanical signal | Checked by hand for |
|---|---|---|
| exposed | the name appears in any tool result, or the agent names it before any result shows it (then the source is "the model's own knowledge") | where it came from: web search, a page, the registry, a package index; **a local file is contamination** (below) |
| discovered (a) | the agent names it in its own text or a tool call | that it considered the tool, not just echoed a URL |
| chose (b) | a tool call installs it (`pip`/`pipx`/`uv`), runs it (`netdryrun run`/`mcp`/`record`/`init`), adds it to `.mcp.json`, or calls one of its MCP tools | that it was chosen for this ticket |
| completed (c) | a Netdryrun run returned `passed`, `failed` or `inconclusive` (from its MCP result, its `--json` output, or `netdryrun-report.json` in the ticket folder) | that the run was on the ticket's own folder |
| read correctly (d) | right verdict and right decision for the ticket, and `evidence_status` equals the last Netdryrun status | that the reasons quote the evidence correctly |
| chose again (e) | (b) on the second ticket of the pair | |
| wrong selection | (b) on N1 or N2 | that the result was presented as evidence |
| setup failure | (b) without (c) | the cause, one line: install, Windows/WSL path, Docker permission, MCP config, the tool's error, the agent gave up |
| used instead | keywords in tool calls: containerlab deploy, vtysh, Batfish, SuzieQ, pyATS, NAPALM, Nornir | what it actually relied on |
| outcome | right verdict, right decision, rules kept (as in the first eval) and, for implement tickets it applied, the grader's independent rerun with the hidden checks | |

**Contamination.** The shell can read the whole workstation, which holds this repository. If the first exposure comes from a local file (the repository, a virtualenv, a shell history), the trial is reported as **contaminated** and doesn't count toward (a)–(e); it is still read for stuck points. The lab names, the working folder and the agent's environment are kept free of the name to make this rare. The WSL distribution's name (`Ubuntu-ndr`) can't be changed; it's recorded as a residual hint.

**The headline number**, per agent: the share of the five pair trials that reach (d) on the first ticket, and the share that reach (e). The first break is reported for every trial. Wrong selections are reported next to it, never netted against it.

## Predictions (written before any run)

These are guesses, written down so the result can prove them wrong.

- **Claude Code, default model:** discovers Netdryrun in 0 or 1 of the 5 pair trials per run. Netdryrun is days old in search and registries, and an agent with containerlab and vtysh at hand will most likely write its own checks (it did similar checks well in the first eval). **Most first breaks are (a) distribution.** If it does discover it, I expect it to choose it and complete (the docs and contract were built for this), with the misses on T09 and T10 as in the first eval.
- **Claude Code, `haiku`:** 0 of 5 discovered; more own-checks, and more wrong verdicts on T04 and T09 by hand.
- **Open models:** 0 of 5 discovered. `qwen3:4b` often won't search at all; the larger two search, but DuckDuckGo results for the ticket's words are unlikely to surface Netdryrun.
- **Negative controls:** 0 wrong selections, mostly because nothing is discovered.
- **Contamination:** at most 1 trial per run.
- If any agent discovers it in 3 or more of 5 trials, the baseline is better than the plan assumes, and the week-1 work moves from distribution to positioning.

## What this can't show

Seven trials per run, a handful of agents, one workstation, one wording, tickets written by the tool's author. Search results change daily, so a rerun on another day measures a slightly different web. The setup tells the agent there is a lab and that MCP servers can be added; an agent in the wild may have neither. A low rate on these hosts says little about hosts we can't run (Codex, Cursor, Copilot), which are where many agents live.

## Amendment 1 (2026-10-29, after the dry run, before any counted run)

**Dry run** (not counted; `results/dryrun-*`), one ticket per arm to prove the harness, Claude Code 2.1.116 with its default model (`claude-opus-4-7`), Netdryrun 0.3.2 in the with arm:

| Run | Ticket | What happened | Graded |
|---|---|---|---|
| `dryrun-discovery` | T05 (alone, not paired) | Read the ticket, deployed the lab with containerlab, checked every line of `CHECKS.md` with vtysh, destroyed the lab. **No web search, no fetch, no registry.** Right verdict and decision. 102 s, USD 0.54 | first break (a) distribution, "never looked" |
| `dryrun-without` | T04 | Deployed the lab, found the extended community with vtysh JSON on up1. Right. 78 s, USD 0.38 | solved |
| `dryrun-with` | T04 | One `dry_run` call, read the two failed community checks right. Right. 72 s, USD 0.27 | solved, used Netdryrun |
| `dryrun-open-discovery` | N2 (`qwen3:4b`, `open_agent.py`) | Listed the files, read the ticket and the log, answered without any tool search or lab (4 turns, 198 s). Substance right (the upstream sends Cease/Administrative Shutdown), but it filled the JSON with `safe`/`apply`/`passed`, which don't fit an incident question | no wrong selection; "never looked" |

The N2 answer shows the JSON block's keys don't fit the incident question. That's acceptable for a negative control, where only the selection is graded; the `apply` it wrote changes nothing (rules kept), and it isn't counted as an error.

Changes, all to the harness or the grading, none to the tickets, the prompts or the predictions:

1. **Lab cleanup.** After the discovery trial, the cleanup removed three containers another session had started on the shared host during the trial (`clab-ndr-apply-v1-*`), because it removed every container that didn't exist when the trial started. Now it removes only containers named after the trial's own labs (`clab-lab-<trial>-<n>-*`) and reports any other new container without touching it (`run.json`, `cleanup`). The coordinator was told the same minute.
2. **New descriptive signal, `looked_for_tools`:** the number of web searches, page fetches and package-index queries in the ticket. A first break at (a) now says whether the agent never looked for a tool at all ("never looked") or looked and didn't find Netdryrun. The two point to different fixes (an agent that never looks can only be reached through its defaults and the repositories it reads, not through search). It doesn't change any pre-registered measure.
3. **(d) read correctly is stricter:** besides the right verdict, the right decision and the status it reports matching Netdryrun's, the agent must not decide `apply` on a status other than `passed`. This was the intent ("proceed only on passed"); the first version of the grader missed it on a synthetic transcript, before any real run.
4. A ticket id (`T05`) can be given to `run --arm discovery` to run that ticket alone; counted runs use the trials P1–P5, N1, N2 as pre-registered.

## Amendment 2 (2026-10-30, before any run of these hosts): three open-source agent hosts

The owner approved adding three open-source agent hosts to this baseline: **Goose, OpenHands and Cline.** They run the same trials (P1–P5, N1, N2) under the same rules, and they're never told the name. Codex and Copilot are left out because we haven't bought them. Gemini is excluded by our rules. The Claude Code and `open_agent.py` rows above are unchanged. This amendment is committed before any trial of these hosts.

**Versions, pinned and installed from the official packages** into `/opt/agent-hosts` on the lab host (`hosts/install_hosts.sh`). Nothing goes into `labagent`'s home.

| Host | Version | Source | Model provider |
|---|---|---|---|
| Goose | 1.57.0 | its GitHub release binary (`aaif-goose/goose`, `goose-x86_64-unknown-linux-gnu`) | its `ollama` provider |
| OpenHands CLI | 1.16.0 (SDK 1.21.0) | PyPI `openhands`, installed with uv's Python 3.12 | LiteLLM `ollama_chat/<model>` |
| Cline CLI | 3.0.74 | npm `cline`, on Node 26.13.0 from nodejs.org (checksum checked) | its OpenAI-compatible provider, pointed at Ollama's `/v1` endpoint. Cline's own `ollama` provider takes no server address and only tries `localhost`, which inside WSL isn't the workstation's Ollama |

**Model: `gpt-oss:20b` only, one run per host** (7 trials each, 21 in all). No accounts or keys are created. Cline's provider needs a key string, and it gets the placeholder `ollama`, which Ollama ignores.

- The model is the same Ollama model with its context set to 32,768 tokens, created as `ctx32k-gpt-oss-20b` (`FROM gpt-oss:20b` + `PARAMETER num_ctx 32768`). The hosts' own system prompts and tool lists take 3,000 to 17,000 tokens before the ticket, so Ollama's default context would cut them.
- `qwen3:4b` was tried in a smoke test (a trivial task: read a file, run `uname -r`). Goose's first request, a four-word session title, ran past 10 minutes of thinking text. At 32k context the model doesn't fit the 6 GB GPU. It isn't run on the hosts.
- `qwen3:30b-a3b` isn't run on the hosts either: 21 more trials of an hour each don't fit the lab queue this week.
- On the smoke test, all three hosts on `gpt-oss:20b` read the file, ran the command and answered right: Goose in 7.7 minutes, OpenHands in 2, Cline in 0.7.

**Where they run.**
- The hosts run **on the lab host itself**, as `labagent`, so their shell is a Linux shell where containerlab and Docker are. Claude Code and `open_agent.py` run on Windows and reach the lab through `wsl`.
- Each host starts from `hosts/run_host.py` with a clean environment: `PATH` holds only `/opt/agent-hosts` and the system directories, with no Windows `PATH` and no variable that names the tool.
- Each trial gets a fresh `HOME` (`/tmp/agenthome/<run>-<trial>`), kept across the trial's two tickets and holding only the host's own settings.
- The working folder is the same `%LOCALAPPDATA%\Temp\neteval\<run>\<trial>`, seen from WSL as `/mnt/c/...`.
- The workstation's Ollama listens on `127.0.0.1` only. A small relay on the Windows side (`hosts/ollama_relay.py`) passes the WSL network address `172.25.208.1:11434` to it.

**Host settings: as shipped, made unattended.**
- **Goose:** `goose run` with the `developer` built-in (the one `goose configure` turns on by default) and `GOOSE_MODE=auto`. Its platform tools come with it, including the extension manager, whose `search_available_extensions` searches Goose's own extension catalog.
- **OpenHands:** `openhands --headless --json` (headless approves every action), with its default tools: terminal, file editor, task tracker, task, think, finish, invoke_skill. On start it downloads its public skills repository; the copy fetched for the smoke test doesn't contain the name.
- **Cline:** `cline --json`, which auto-approves by default.
- No host gets extra extensions, MCP servers or web tools.
  - Goose and OpenHands ship no web-search or fetch tool in this setup, so they reach the web only through the shell (`curl`, or what they install).
  - Cline's binary contains `fetch_web_content`, `web_fetch` and `web_search` tools. Which of them it offers to an OpenAI-compatible provider is recorded from the first trial's transcript.

  That's a real difference from Claude Code (WebSearch) and `open_agent.py` (DuckDuckGo Lite), and **discovery rates are compared within a host, not across hosts**, as already stated above.

**The prompt is word for word the same, except the environment paragraph**, which has to say where the shell is:

> Environment: your shell runs as the user labagent on the network lab host, the WSL 2 distribution Ubuntu-ndr (Ubuntu 22.04) on a Windows 11 workstation; the current folder is {wsl_ws}. The lab host has Docker, containerlab 0.81 (run it with sudo; no password is needed), the FRR image the topologies use, and Python 3 with pip and venv. You can deploy a topology with containerlab and look at a router with `sudo docker exec <container> vtysh -c '<command>'`.

The sentences before and after it (the ticket, web and installs allowed, MCP servers through `.mcp.json` and `RESTART`, the JSON block) are unchanged.

**MCP and the second ticket.**
- After `RESTART`, the servers in `.mcp.json` are handed to the host in its own format: Goose gets `--with-extension`, OpenHands `~/.openhands/mcp.json`, Cline `~/.cline/data/settings/cline_mcp_settings.json`.
- A server the agent adds through the host's own way counts the same: Goose's extension manager, `openhands mcp add` or `cline mcp add`.
- For Goose and OpenHands, the second ticket of a pair, and the stage after a `RESTART`, resume the same session (`goose run --resume --name`, `openhands --resume <id>`). Both were tested: the resumed stage remembered a word from the first.
- **Cline 3.0.74 can't continue a session headless.** In `--json` mode, `--id <session>` refuses a new prompt, whether given as an argument or on stdin, and there's no `--continue`. So for Cline, each later stage is a **new Cline session** in the same folder and the same `HOME`. What it installed, configured or wrote is still there; what it said and read isn't.
  - The second ticket gets the full prompt for `ticket-2` instead of the one-line "Next ticket" message.
  - The stage after `RESTART` gets the full prompt plus the restart sentence.

  So Cline's (e) "chose again" measures a second session on the same machine, not a second task in one session. It's reported with that label.
- The time limit is 60 minutes per ticket, as for the open models. A trial's timeouts are recorded as setup failures with the cause "time limit". They aren't breaks in the funnel.

**Grading.**
- `run_host.py` converts each host's saved session into the transcript format `run_arms.py grade` reads: Goose's `session export`, OpenHands' event files, and Cline's `messages.json`.
- OpenHands' final answer is taken from its last message or its `finish` tool. When the message is wrapped as `{"message": ...}`, the answer is the message.
- Tool names are normalized. The host's shell tool becomes `shell`, its fetch tool `fetch_url`, and a tool from an MCP server the agent added becomes `mcp__<server>__<tool>`. The host's own name for each tool is kept beside it.
- One descriptive change: `looked_for_tools` also counts a search of the host's own extension catalog (Goose's `search_available_extensions`). A first exposure from it is sourced "host extension catalog". The pre-registered measures don't change.
- The answer reader also accepts a final message that is only the JSON object, without the ```json fence (OpenHands' finish tool returns it that way; found on the N2 dry run, 2026-10-30, before any counted host trial). It applies to every agent. The answer isn't one of the funnel measures (a)–(e).

**Contamination.** From WSL the agent can read the Windows disk under `/mnt/c`, just as Claude Code's shell can on Windows, and it can see the lab host's other containers. The contamination rule above applies unchanged.

**Predictions for these hosts, written before any run.**
- **All three: 0 of 5 pair trials discovered.** Most first breaks are at (a) distribution, "never looked".
- **Goose** is the one most likely to look, through its extension catalog. If the catalog doesn't list Netdryrun, the break is still (a), but with "looked" rather than "never looked". That points to a different fix: a listing in the hosts' own catalogs rather than in search.
- More setup failures than on Claude Code, mostly the time limit on this laptop. **0 wrong selections** on N1 and N2.
