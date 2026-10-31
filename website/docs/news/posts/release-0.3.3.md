---
date: 2026-10-30
slug: release-0.3.3
title: "Netdryrun 0.3.3: the agent runtime"
description: "An agent with no local Docker gets a verdict through a pull request, MCP calls answer within seconds, and record writes baselines that survive normal growth."
categories:
  - Releases
---

# Netdryrun 0.3.3: the agent runtime

An agent with no local Docker gets a verdict through a pull request, MCP calls answer within seconds, and `record` writes baselines that survive normal growth.

<!-- more -->

- **The pull-request path for agents without Docker.** `netdryrun run --verdict FILE` writes the same result object the MCP tools return, and the GitHub Action's PR comment starts with a fixed, machine-readable header. Guide: [AI agents without Docker](../../guides/agent-pr.md).
- **An asynchronous MCP shape.** `start_run` returns at once with a `run_id`, and `get_result` polls it, for clients that wait less time than a dry run takes.
- **`record` writes prefix-count ranges and standard guards by default**: no default route via BGP and no link subnet via BGP on every BGP node.
- **A run on an FRR lab that skipped a config line is an error, never a pass** ([advisory](https://github.com/netdryrun/Netdryrun/tree/main/advisories/0.3.2-rejected-config)).
- **Corpus v2 correction:** case 18 gives different verdicts on the same build in this lab, so it is left out of the score, which is now 16 of 17 deterministic cases. The earlier note is kept, struck through, with the correction.

Known limit: keep routing config out of topology `exec:` lines ([advisory](https://github.com/netdryrun/Netdryrun/blob/main/advisories/0.3.3-exec-not-checked/README.md)).

[Full changelog](https://github.com/netdryrun/Netdryrun/blob/main/CHANGELOG.md) · [Release on GitHub](https://github.com/netdryrun/Netdryrun/releases/tag/v0.3.3)
