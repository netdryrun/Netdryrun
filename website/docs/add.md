---
title: Add Netdryrun where your agent works
description: "Two-minute setup: put Netdryrun where coding agents already work, as a pull-request check, an AGENTS.md rule, or an MCP server in Claude Code, Cursor or VS Code with Copilot. Coding agents don't go looking for a verifier; this page is how a human puts one in their path."
---

# Add Netdryrun where your agent works

**Coding agents don't search for a network verifier.** In our own test, Claude Code worked 28 network tickets (20 paired trials, two models) with no mention of Netdryrun. It never searched the web, fetched a page or added an MCP server; it used containerlab and the router's CLI (our agent evaluation, 2026-10-30; the transcripts are published with 0.4). So an agent uses Netdryrun when a human puts it in its path. Pick one of the options below; each takes about two minutes.

A pass means every check in `netdryrun.yml` passed in the lab. It doesn't mean the change is safe to ship. The lab needs Linux or WSL2, Docker and containerlab; a small FRR lab takes about a minute once images are pulled.

## Option 1: a required check on every pull request (no Docker on the agent's machine)

Works for any agent that opens pull requests, and for humans. Add this workflow to the repository with your network configs:

```yaml
# .github/workflows/netdryrun.yml
name: Netdryrun
on: pull_request
permissions:
  contents: read
  pull-requests: write      # for the comment
jobs:
  verdict:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          persist-credentials: false   # the lab runs privileged containers: leave no token in .git/config
      - uses: netdryrun/Netdryrun@v0.4.0
        with:
          path: network/        # the folder with netdryrun.yml
          pr-comment: true
```

Then make the `Netdryrun` check required in branch protection, and keep the checks with the network team:

```text
# CODEOWNERS
network/netdryrun.yml @your-org/network-team
```

How an agent reads the result: [AI agents without Docker](guides/agent-pr.md).

## Option 2: a rule in AGENTS.md

Coding agents read `AGENTS.md` at the repository root. Paste this into the one for your network configs:

```markdown
Before proposing or applying any routing or policy change in this repository, dry-run it: `netdryrun run <lab>` or the `dry_run` MCP tool. Propose the change only if `status` is `passed` (verdict CHECKS PASSED), and say the pass covers only what the checks look at. Ping is not a test. Never edit `netdryrun.yml` to make a change pass.
```

Replace `<lab>` with the folder that holds `netdryrun.yml`. With Option 1 in place, use the [pull-request version](guides/agent-pr.md#paste-this-into-the-repositorys-agentsmd) instead.

## Option 3: an MCP server in the agent's client

The agent's machine needs Linux or WSL2, Docker and containerlab. Install once:

```bash
pipx install netdryrun   # or uv tool install netdryrun
```

**Claude Code** (writes `.mcp.json`, so everyone in the repository gets it):

```bash
claude mcp add -s project netdryrun -- netdryrun mcp
MCP_TOOL_TIMEOUT=600000 claude      # a dry run can take minutes
```

Claude Code on Windows with Netdryrun in WSL: `claude mcp add -s project netdryrun -- wsl.exe -d <distribution> -- <path from "which netdryrun" in WSL> mcp`.

**Cursor**: `.cursor/mcp.json` in the project.

```json
{
  "mcpServers": {
    "netdryrun": { "type": "stdio", "command": "netdryrun", "args": ["mcp"] }
  }
}
```

**VS Code with GitHub Copilot**: `.vscode/mcp.json` in the workspace. The top-level key is `servers`, not `mcpServers`.

```json
{
  "servers": {
    "netdryrun": { "type": "stdio", "command": "netdryrun", "args": ["mcp"] }
  }
}
```

Windsurf, Codex CLI, timeouts and the safety model: [AI agents (MCP)](ai-agents.md#set-up-the-mcp-server).

## Optional: the agent skill

The rules in one file, for clients that read skills. Copy [`skills/netdryrun/`](https://github.com/netdryrun/Netdryrun/tree/main/skills/netdryrun) to `.claude/skills/netdryrun/` (or `.agents/skills/netdryrun/`) in the repository and commit it. A skill alone runs nothing: it needs Option 1 or Option 3.

## The smallest netdryrun.yml

No checks yet? Record today's behaviour from your running lab with `netdryrun record <topology> --deploy` ([guide](guides/your-lab.md)), or start from this:

```yaml
lab: topology.clab.yml
checks:
  - type: bgp_session
    node: r1
    neighbor: 10.0.12.2
  - type: bgp_prefixes
    node: r1
    neighbor: 10.0.12.2
    min: 1
    max: 10            # guards against a leak flooding r1
  - type: route        # nothing should send r1 a default route
    node: r1
    prefix: 0.0.0.0/0
    protocol: bgp
    present: false
```

Full syntax: [netdryrun.yml reference](reference/config.md).

## Done when

- **Option 1:** a pull request shows the `Netdryrun` check, and a comment by `github-actions[bot]` whose `commit` is the head commit.
- **Option 3:** `claude mcp get netdryrun` says `Connected`, or your client lists the `dry_run` tool.

!!! warning "0.3.3 and earlier: keep routing config out of topology `exec:` lines"
    A topology `exec:` command that fails is only logged by containerlab, and the lab runs without it, so a run can pass. Put routing config in `setup:` (or, on FRR, in `frr.conf`). Fixed in 0.4. [Advisory](https://github.com/netdryrun/Netdryrun/blob/main/advisories/0.3.3-exec-not-checked/README.md).
