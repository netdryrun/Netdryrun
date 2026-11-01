---
date: 2026-10-28T09:00:00
slug: release-0.3.1
title: "Netdryrun 0.3.1: false-pass and injection fixes"
description: "0.3.0 could report passed without testing what a file said. 0.3.1 fixes those paths, allowlists names that reach device commands and makes PR comments inert."
categories:
  - Releases
---

# Netdryrun 0.3.1: false-pass and injection fixes

0.3.0 could report `passed` without testing what a file said. 0.3.1 fixes those paths; the rerunnable cases are in [the advisory](https://github.com/netdryrun/Netdryrun/blob/main/advisories/0.3.0-false-pass/README.md). Upgrade, then run `netdryrun validate`: files that 0.3.0 accepted can now exit 2, and each of those was a check that didn't test what it said.

<!-- more -->

- **Security:** `vrf` and `link_down` interface names are allowlisted before they reach a device command, the Markdown summary and PR comment are inert, and a new `NETDRYRUN_MCP_ROOT` confines the MCP server to the folders you list.
- **Some verdicts change with no config edit**, for example a received path now counts as present even when it is not selected.
- **Exit codes:** 0 passed, 1 checks failed, 2 not tested, 3 inconclusive.

[Full changelog](https://github.com/netdryrun/Netdryrun/blob/main/CHANGELOG.md) · [Release on GitHub](https://github.com/netdryrun/Netdryrun/releases/tag/v0.3.1)
