---
date: 2026-10-27T20:00:00
slug: release-0.3.0
title: "Netdryrun 0.3.0: BGP attribute checks and inconclusive runs"
description: "A new bgp_route check for best-path attributes, a new inconclusive status for labs that never reached a testable state, and a browser trial in GitHub Codespaces."
categories:
  - Releases
---

# Netdryrun 0.3.0: BGP attribute checks and inconclusive runs

A new check for BGP best-path attributes, a status for labs that never reached a testable state, and a browser trial.

<!-- more -->

- **New check type `bgp_route`**: communities, AS path, local preference, MED and next hop of the BGP best path, on FRR, SR Linux, Arista EOS and SONiC.
- **New status `inconclusive` (exit code 3)**: the lab never reached a testable state, so the run says nothing about the change.
- **Try it in your browser:** a devcontainer and a GitHub Codespaces badge run the agent demo with nothing installed.
- **Agent demo:** a tempting change that passes the ticket checks but leaks routes is rejected; the proper fix is accepted.

[Full changelog](https://github.com/netdryrun/Netdryrun/blob/main/CHANGELOG.md) · [Release on GitHub](https://github.com/netdryrun/Netdryrun/releases/tag/v0.3.0)
