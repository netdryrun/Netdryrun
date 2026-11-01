---
date: 2026-10-28T18:00:00
slug: release-0.3.2
title: "Netdryrun 0.3.2: the agent contract"
description: "What an AI agent needs to choose Netdryrun, read its result and act on it safely: a typed MCP result, frozen verdict strings and failures that explain themselves."
categories:
  - Releases
---

# Netdryrun 0.3.2: the agent contract

What an AI agent needs to choose Netdryrun, read its result and act on it safely. Tool names and parameters are unchanged.

<!-- more -->

- **Breaking for agents: the pass verdict is renamed.** `SAFE TO PROCEED` is now `CHECKS PASSED (only what the checks cover)`, because a pass covers only what the checks look at. Decide on the `status` field, not the text.
- **A typed result**, defined by a published [JSON Schema](https://netdryrun.com/schemas/mcp-result-v1.json), with frozen verdict strings.
- **Failed results explain themselves:** one entry per failed check with its reason, an evidence excerpt and one read-only diagnostic command for the node.
- **Results name what they tested:** a sha256 of `netdryrun.yml`, the topology and every config file the run used.
- **Network Change Verdict v1**, an open [spec](../../spec/verdict-v1.md) so other tools can emit the same verdict document.

[Full changelog](https://github.com/netdryrun/Netdryrun/blob/main/CHANGELOG.md) · [Release on GitHub](https://github.com/netdryrun/Netdryrun/releases/tag/v0.3.2)
