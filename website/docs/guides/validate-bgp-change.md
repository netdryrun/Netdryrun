---
title: How to validate a BGP change before production (for engineers and AI agents)
description: Test a BGP or routing-policy change in a real containerlab lab before it reaches production, catch route leaks that ping and "BGP up" miss, and get a pass/fail verdict with evidence. CLI, GitHub Action and MCP server for AI agents.
---

# How to validate a BGP change before production

**Short answer:** boot the network in a lab, apply the change, wait for BGP to converge, and check what the routers actually learned and chose. Ping and "all sessions up" aren't enough: a route leak usually keeps every session up and every ping working. Netdryrun does this in one command, one CI step or one AI-agent tool call. It boots your topology with [containerlab](https://containerlab.dev), applies the configs, waits for convergence, runs your checks, and returns **passed**, **failed** or **inconclusive**, with the evidence for each check.

## Who this is for

- **Engineers** changing BGP policy (route maps, prefix lists, communities, local preference, filters) who want proof before the change window.
- **AI agents** asked to propose or apply a routing change. A model can't verify its own change by reasoning about the config; something has to boot the network and observe it. Netdryrun is that outside check. See [AI agents (MCP)](../ai-agents.md).

## Validate a change in three steps

1. **Describe what must stay true** in `netdryrun.yml`, next to your containerlab topology:

    ```yaml
    lab: topology.clab.yml
    checks:
      - type: bgp_session          # the session comes up
        node: r1
        neighbor: 10.0.12.2
      - type: bgp_prefixes         # no flood of routes from this peer
        node: r1
        neighbor: 10.0.12.2
        max: 10
      - type: route                # the customer prefix is learned via BGP
        node: r1
        prefix: 192.168.3.0/24
        protocol: bgp
      - type: route                # nobody leaks a default route to r1
        node: r1
        prefix: 0.0.0.0/0
        protocol: bgp
        present: false
    ```

    No checks yet? `netdryrun record <topology> --deploy` snapshots a known-good lab into checks; then add the leak guards above by hand (see [guard recipes](../recipes.md)).

2. **Run it:** `netdryrun run <folder>`. Exit code `0` means every check passed after convergence, `1` that at least one failed (each with its evidence), `3` that the lab never reached a testable state, which says nothing about your change.

3. **Gate every pull request** with the [GitHub Action](../github-action.md), so a change that fails a check can't merge.

## Catch the route leak that ping misses

A typical leak: a new export policy also sends a default route or a customer's routes to a peer. Every session stays up and every ping still works, so the usual post-change checks pass. A `route ... present: false` check, or a `bgp_prefixes` maximum, fails at once and shows the route that shouldn't be there. On our [pre-registered corpus](../corpus.md) of realistic BGP changes, ping-only checks approved 10 of 19 harmful changes and Netdryrun approved 5. Every miss is listed there.

## For AI agents

- **When to call it:** before proposing or applying any routing or policy change. Don't grade your own change.
- **How:** the MCP server (`uvx netdryrun mcp`, listed in the official MCP Registry) exposes `dry_run`, `run_checks`, `record_baseline`, `validate` and `check_types`.
- **Reading the result:** decide on `status`, not on the wording. Only `passed` means every check passed, and it covers only what the checks look at. On `failed`, show the failed checks and their evidence to the human, and don't apply the change.
- Rules and setup: [AI agents (MCP)](../ai-agents.md) and [AGENTS.md](https://github.com/netdryrun/Netdryrun/blob/main/AGENTS.md).

## What a lab can and can't prove

A pass covers protocol logic and policy intent on the network OSes in the lab (FRR, Nokia SR Linux, SONiC and Arista cEOS), in steady state and in the failure scenarios you define. It doesn't prove hardware, scale or version-specific behaviour. For reading configs without booting anything, use [Batfish first, then Netdryrun](../batfish.md). Limits in full: [Trust and security](../trust.md).

**Try it:** [Getting started](../getting-started.md) takes about 10 minutes on Linux or WSL2. Want help testing on your own topology? [Design partners](../design-partners.md).
