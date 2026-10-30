---
title: Fail CI on routing mistakes before they reach production
description: Test a network change in CI with a containerlab lab. Netdryrun boots the topology, waits for convergence, checks BGP, routes and reachability, and fails the job on mistakes.
---

# Fail CI on routing mistakes before they reach production

To test a network change in CI, keep the changed configs and a containerlab topology in Git, describe the expected behavior in a `netdryrun.yml` file, and run `netdryrun run` (or the GitHub Action) on every pull request. Netdryrun™ deploys the lab, waits for BGP to converge, checks sessions, prefix counts, routes and pings, then destroys the lab. Any failed check exits non-zero and fails the job, with a JSON evidence file showing every command and its raw output.

[Try it in your browser](https://codespaces.new/netdryrun/netdryrun?quickstart=1){ .md-button .md-button--primary } [View the source on GitHub](https://github.com/netdryrun/netdryrun){ .md-button }

The browser trial runs in GitHub Codespaces: it needs a free GitHub account, takes a few minutes to start, and then `bash examples/agent-demo/demo.sh` shows a bad change rejected and the fix accepted. Nothing to install.

!!! abstract "What Netdryrun is"
    Software teams don't ship code without running its tests. Network changes deserve the same step: run the change in a real lab, check how the network behaves, and ship only on a pass. Netdryrun is the open-source tool that makes that one command, one CI step, or one tool call for an AI agent. It tests network changes in a real virtual lab before they reach production. It boots the topology with containerlab, waits for convergence, checks BGP sessions, prefixes, routes and reachability, and returns a pass/fail verdict with evidence. It runs locally, in GitHub Actions, or as an MCP server for AI agents.

## Watch the demo

<figure class="ndr-video">
<video controls preload="none" playsinline width="1920" height="1080" poster="/assets/video/netdryrun-demo-poster.jpg" aria-label="Netdryrun demo video, about 90 seconds, captions burned in">
<source src="/assets/video/netdryrun-demo.mp4" type="video/mp4">
<track kind="captions" srclang="en" label="English (text)" src="/assets/video/netdryrun-demo.vtt">
<a href="/assets/video/netdryrun-demo.mp4">Download the video (MP4)</a>
</video>
<figcaption>About 90 seconds, captions on screen, no sound. A leaked default route that ping and session checks miss, an AI agent's tempting change rejected and the two-line fix passed (a scripted replay), a real agent run, and the verdict corpus with its losses. Every terminal line comes from a real run. <a href="/assets/video/netdryrun-demo.vtt">Captions as text</a>.</figcaption>
</figure>

## A failing run

This is the bundled `frr-bgp-broken` example. Router r2 has a bad change: it sends r1 a default route.

![Netdryrun catching a leaked default route that ping and session checks miss](assets/netdryrun-demo.gif)

```text
$ netdryrun run examples/frr-bgp-broken
Deploying lab ndr-frr-broken (3 nodes)...
  [PASS] r1: BGP session to 10.0.12.2 is established -- state is established (6.3s)
  [PASS] r1: ping 192.168.3.1 from 192.168.1.1 expects success -- 3/3 replies (2.3s)
  ... (3 more passing checks trimmed)
  [FAIL] r1: route 0.0.0.0/0 via bgp is absent -- unexpectedly present via bgp (not selected) (0.1s)
FAILED: 5 passed, 1 failed (6 checks)
```

The leaked default route was *received but not selected*: r1 kept its own default, so traffic still flowed and the ping passed. A ping test or a session check would have missed it. (A static analyzer such as Batfish also catches this particular leak; the [Batfish page](batfish.md) shows one that it misses and the lab catches.) Netdryrun counts a route that is in the routing table but not selected as present, so the "must be absent" check fails.

The check that caught it:

```yaml
- type: route        # nothing should send r1 a default route
  node: r1
  prefix: 0.0.0.0/0
  protocol: bgp
  present: false
```

Checks like this one run only after the network has converged (the positive checks passed and every configured BGP session on the node is up) and must hold for a time window, so they cannot pass just because BGP has not come up yet. See [convergence semantics](reference/config.md#convergence-semantics).

## Run it in GitHub Actions

```yaml title=".github/workflows/network-dryrun.yml"
name: Network dry run
on: pull_request
jobs:
  dryrun:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: netdryrun/netdryrun@v0.3.3
        with:
          path: network/        # folder containing netdryrun.yml
```

The action installs containerlab, runs the checks, writes a summary to the job page, uploads the JSON and JUnit reports as an artifact, and fails the job if any check fails. Details: [GitHub Action](github-action.md).

## Run it locally

Fastest start on your own topology: `netdryrun record my-lab/topology.clab.yml --deploy` snapshots today's behavior into checks, then `netdryrun run my-lab` tests every change against it.


```bash
pipx install netdryrun          # Ubuntu 24.04+: sudo apt install pipx && pipx ensurepath first
netdryrun run path/to/folder    # the folder containing netdryrun.yml
```

Requirements: Linux or WSL2, Docker, containerlab, Python 3.10+. Walkthrough: [Getting started](getting-started.md).

!!! warning "What a lab cannot prove"
    A pass means the change behaved correctly in a lab built from container router images (FRR, Nokia SR Linux, SONiC, Arista cEOS). That is strong evidence for protocol logic and policy intent. It is not proof of:

    - vendor-specific behavior on the routers you run in production
    - behavior at production scale (full tables, many peers)
    - hardware and ASIC limits
    - timing and convergence at scale

    More on this in [Trust and security](trust.md#what-a-lab-cannot-prove).

## Status

<!-- facts:site_status -->
Version 0.3.3. Works with FRR, Nokia SR Linux, SONiC and Arista EOS (bring your own cEOS image) on Linux and WSL2. Check types: `bgp_session`, `bgp_prefixes`, `route`, `bgp_route` and `ping` (IPv4/IPv6 unicast BGP sessions, prefix counts, routes, BGP best-path attributes and ping), plus link-down, node-isolation and route-injection (FRR only) failure scenarios. On the [verdict corpus](corpus.md) v1 (30 realistic BGP changes: 19 harmful, 11 safe), Netdryrun judged 24/30 correctly, ping-only checks 20/30 and all-sessions-up checks 15/30. Netdryrun approved 5 of the 19 harmful changes (ping-only checks: 10 of 19) and blocked 1 of the 11 safe ones. On v2 (18 cases written after v1 to target v1's misses): Netdryrun 16 of 17 deterministic cases correct, ping-only 9/17, all-sessions-up 7/17; case 18 is nondeterministic in this lab and excluded from the score (listed with its reruns). Expected verdicts were committed before any run, on one FRR topology: a comparison of testing methods, not a production reliability estimate. Method, every miss and a one-command rerun are on the corpus page. Provenance: both ran on Netdryrun 0.3.1. Issues and feedback: [github.com/netdryrun/netdryrun](https://github.com/netdryrun/netdryrun/issues).
<!-- /facts:site_status -->
