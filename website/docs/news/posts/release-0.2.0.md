---
date: 2026-10-27T14:00:00
slug: release-0.2.0
title: "Netdryrun 0.2.0: SONiC, Arista EOS, record and the verdict corpus"
description: "SONiC and Arista EOS drivers, netdryrun record for baselines, failure scenarios, PR comments, and the first pre-registered verdict corpus with its losses published."
categories:
  - Releases
---

# Netdryrun 0.2.0: SONiC, Arista EOS, record and the verdict corpus

Two more network operating systems, baselines without writing checks by hand, and the first published corpus.

<!-- more -->

- **SONiC** (docker-sonic-vs) and **Arista EOS** (cEOS-lab, bring your own image) drivers.
- **`netdryrun record`** snapshots a known-good lab into a `netdryrun.yml` baseline, so you don't write checks by hand.
- **Failure scenarios:** `link_down` and `node_isolated`, with links always restored.
- **GitHub Action `pr-comment: true`**: one PR comment with the verdict and the evidence for each failed check.
- **The [verdict corpus](../../corpus.md):** 30 pre-registered cases comparing ping-only, session-only and Netdryrun checks, losses published.

[Full changelog](https://github.com/netdryrun/Netdryrun/blob/main/CHANGELOG.md) · [Release on GitHub](https://github.com/netdryrun/Netdryrun/releases/tag/v0.2.0)
