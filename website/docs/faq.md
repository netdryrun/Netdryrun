---
title: FAQ
description: Frequently asked questions about Netdryrun. What it is, how to test a BGP change before production, containerlab in CI, the MCP server for AI agents, whether it touches production, what a pass proves, how it differs from Batfish and pyATS, supported network operating systems, Windows, memory needs, CI time and cost, privacy and license.
---

# FAQ

## What is Netdryrun?

Netdryrun™ is an open-source (Apache-2.0) tool that dry-runs a network change in a real containerlab virtual lab before it reaches production. It boots your topology with the changed configs, waits for routing to converge, checks BGP sessions, prefix counts, routes, BGP best-path attributes and ping reachability against a `netdryrun.yml` file, and returns a pass/fail verdict with the commands and raw output as evidence. Supported network operating systems: <!-- facts:faq_platforms -->FRR, Nokia SR Linux, SONiC (docker-sonic-vs) and Arista EOS (cEOS, bring your own image)<!-- /facts:faq_platforms -->. It runs as a CLI, a GitHub Action and an MCP server for AI agents. See [Getting started](getting-started.md).

## How do I test a BGP change before it reaches production?

Build a containerlab lab of the affected part of the network, apply the change to its configs, and check how the network behaves, not only whether sessions come up. With Netdryrun: keep the topology and configs in Git, run `netdryrun record` once to write down the lab's current BGP sessions, prefix counts and routes as checks, add negative checks for what must never happen (for example `route 0.0.0.0/0` `present: false` on a router that must not learn a default), then run `netdryrun run` on every change. Exit code `0` means every check passed, `1` means the change broke a check, and the JSON report shows the evidence. The [tutorial](tutorial.md) walks through it on your own lab, and [Add Netdryrun to your lab](guides/your-lab.md) does it in ten minutes. A pass covers only what the checks describe, in a lab; see [What does a pass prove?](#what-does-a-pass-prove).

## How do I run containerlab in CI?

On GitHub, add the Netdryrun action to a workflow on `pull_request`: `uses: netdryrun/netdryrun@v0.3.2` with `path:` pointing at the folder that holds `netdryrun.yml`. It installs containerlab on the GitHub-hosted `ubuntu-latest` runner, deploys the lab, runs the checks, destroys the lab, uploads JSON and JUnit reports and fails the job on any failed check. A small FRR lab takes about 1 to 2 minutes per job ([measured times](#how-long-does-a-run-take-and-what-does-ci-cost)). Other CI systems can run the same `netdryrun run` command on a Linux runner with Docker and containerlab installed. See [GitHub Action](github-action.md), and the [FRR](guides/frr-ci.md) and [SONiC](guides/sonic-ci.md) CI guides.

## Is there an MCP server for testing network changes?

Yes. `netdryrun mcp` starts Netdryrun's built-in MCP server over stdio (`uvx netdryrun mcp` runs it without installing; in Claude Code, `claude mcp add netdryrun -- netdryrun mcp`). An AI agent calls `dry_run` with the path to a lab folder; Netdryrun deploys the lab, runs every check, destroys the lab and returns a `verdict` field: `CHECKS PASSED (only what the checks cover)`, `DO NOT APPLY THIS CHANGE` or `INCONCLUSIVE` (decide on `status`, not on the text). The tools are <!-- facts:mcp_tools -->`dry_run`, `run_checks`, `record_baseline`, `validate` and `check_types`<!-- /facts:mcp_tools -->. It only builds labs on the machine where it runs and cannot connect to real devices. It is listed in the official MCP Registry as `io.github.netdryrun/netdryrun`. See [AI agents (MCP)](ai-agents.md).

## Does Netdryrun touch my production network?

No. Netdryrun™ only builds labs with containerlab on the machine where it runs, runs commands only inside the lab containers (with `docker exec`), and destroys the lab. Most are read-only show commands; the others take links down and up for failure scenarios, add and remove routes for `inject_routes` scenarios, and run any `setup` commands you write. It has no command, option or MCP tool that connects to a real device or pushes config anywhere. You apply the change to production yourself, with your normal process, after the test passes.

## What does a pass prove?

A pass means every check in your `netdryrun.yml` held in a lab running real routing software: positive checks reached the expected state within the timeout, and negative checks held for the hold time after convergence. It is strong evidence that the change does what you intended at the protocol and policy level.

It does not prove:

- **anything you did not check.** A pass covers the checks that exist. A leak with no negative check for it passes.
- **vendor or version behavior.** FRR, SR Linux, SONiC VS and cEOS are not your production routers or images.
- **scale, hardware or timing.** A lab has a few nodes and small tables, no ASICs, and different convergence times.

See [what a lab cannot prove](trust.md#what-a-lab-cannot-prove). The [verdict corpus](corpus.md) shows where Netdryrun was right and wrong on 30 realistic changes.

## What does "inconclusive" mean?

A run is `inconclusive` (exit code `3`) when checks failed but the lab never reached a state where they mean anything, for example a node whose BGP daemon never started. It says nothing about the change, good or bad: rerun, raise `timeout`, or check that the lab boots. Don't change the network change because of it, and don't apply it either: only `passed` means go.

The rules are conservative. A configured session that is down, a missing route or a failed ping is always `failed`, because an ASN typo looks exactly like a slow lab from the outside. See [when a run is inconclusive](reference/cli.md#when-a-run-is-inconclusive) and [troubleshooting](troubleshooting.md#inconclusive-the-lab-never-came-up).

## Is Netdryrun an alternative to Batfish or pyATS?

It complements them more than it replaces them. Netdryrun boots the real routing software in a lab and checks its behavior; Batfish models the network from its configs without booting anything; pyATS is a general test framework for labs and production devices. Many teams run Batfish first and boot the lab only when it passes ([Batfish, then Netdryrun](batfish.md) measures that pipeline).

- **Batfish** models routing and forwarding from the configs, without booting anything. It covers many vendors and large networks, and answers questions about every flow or route, including what changes between two snapshots or under failures. Netdryrun runs the real routing software, so it sees what the implementation actually does, on fewer nodes.
- **pyATS / Genie** is a full Python test framework with many parsers, for labs and production devices. Netdryrun is a YAML file of checks and a CLI, aimed at one job: a pass/fail gate in CI.

They work together. See [When to use what](when-to-use-what.md) for a longer, neutral comparison.

## Which network operating systems are supported?

<!-- facts:faq_platforms -->FRR, Nokia SR Linux, SONiC (docker-sonic-vs) and Arista EOS (cEOS, bring your own image)<!-- /facts:faq_platforms -->. Labs can mix them: the examples pair each one with FRR. See [drivers](reference/config.md#drivers) for what each driver supports.

## Why not Cisco or Juniper?

Not in a release yet. Their lab images need a vendor account and can't be redistributed. Netdryrun's CI and examples must run for anyone, so every image they use has to be free to pull: FRR, SR Linux and SONiC VS are. Arista cEOS is free to download with an account but can't be redistributed, so its example needs you to import your own image.

Cisco and Juniper images (for example IOS XRd, Cisco 8000 emulator, cRPD, vJunos) need an account, a license or both, and several are virtual machines that containerlab runs through vrnetlab. Drivers for them follow the same bring-your-own-image model as cEOS: Juniper (cJunosEvolved) and Cisco NX-OS (Nexus 9000v) come first, as beta, and IOS XE and IOS XR later. If you need one, say so in an [issue](https://github.com/netdryrun/netdryrun/issues).

## Does it work on Windows?

Yes, through WSL2. containerlab needs Linux, so install Docker and containerlab inside a WSL2 distribution (Ubuntu 22.04 is what we test on) and run Netdryrun there. Keep labs on the Linux filesystem (`~/...`) rather than under `/mnt/c`: it is faster, and SR Linux cannot save its config on a Windows drive. Netdryrun works around the second problem; see [troubleshooting](troubleshooting.md#sr-linux-fails-on-a-windows-drive-mntc). All the outputs in this documentation were produced on WSL2.

## How much memory and CPU does it need?

Memory used per node once the lab is up, measured with `docker stats` on WSL2 (20 cores, 16 GB):

| Node | Image | Memory |
|---|---|---|
| FRR | `quay.io/frrouting/frr:10.4.1` | 23 to 25 MiB |
| SONiC VS | `docker-sonic-vs:latest` | 302 MiB |
| Arista cEOS | `ceos:4.36.3M` | 903 MiB |
| Nokia SR Linux | `ghcr.io/nokia/srlinux:26.7.2` | 1.9 GB (1,947,377,664 bytes, read from the container's cgroup `memory.current`, because `docker stats` shows 0 for SR Linux) |

CPU is busy only while nodes boot. Once up, FRR and SONiC used about 1% of one core or less; cEOS was using about one full core when measured, shortly after boot.

Plan for the sum of your nodes plus a few hundred MB for Docker and containerlab. A small FRR lab runs on any laptop. A lab with several SR Linux or cEOS nodes needs a machine with 8 GB or more. GitHub-hosted `ubuntu-latest` runners have enough memory for every example.

### A 20-node lab

These numbers come from one-off runs on the maintainer's machine. The topology, the recorded checks and the reports are not published yet, so treat them as a rough guide rather than evidence you can check.

Measured on 2026-10-27 on the same WSL2 machine, images already pulled: a leaf-spine fabric of 4 spines and 16 leaves, all FRR 10.4.1, 64 links, eBGP on every link with ECMP. `netdryrun record` turned the running lab into 560 checks (128 sessions, 128 prefix counts, 304 routes) in 11 seconds. Then `netdryrun run` on those 560 checks:

| Phase | Time |
|---|---|
| Deploy (containerlab, 20 nodes) | 9 s |
| BGP converged everywhere (polled once a second) | 9 s after deploy |
| 432 convergence checks done | 25 s after deploy |
| Settle, then 128 prefix counts held 10 s | 27 s |
| Destroy | 3 s |
| **Total, `netdryrun run`** | **65 s, all 560 passed** |

Two more runs on the same lab:

- **With a failure scenario** (spine1 isolated: 16 links down, 4 checks on leaf1): 128 s, all 564 passed. The scenario took 32 s (its checks, restoring the links, settling 10 s). Proving that all 432 convergence checks recovered afterwards took another 32 s.
- **With a broken change** (leaf16 stops announcing its LAN): 193 s, 83 failed, exactly the expected ones: the 19 routes to that LAN, the 60 leaf prefix counts that dropped from 15 to 14, and the 4 spine prefix counts that dropped from 1 to 0. The prefix counts failed within 31 s. The missing routes failed at 120 s, the `timeout` that `record` writes, so most of a failing run is that wait. Lower `timeout` if your lab converges faster.

Memory: 532 MiB for the 20 nodes at the peak (25 MiB per leaf, up to 58 MiB per spine with 16 BGP sessions), about 1 GB more host memory in use during the run, and 72 MB for Netdryrun itself. Netdryrun used a bit more than one core while polling.

At this size each polling round takes 9 to 12 seconds instead of the nominal 3, because every check is its own `docker exec` and Netdryrun runs 8 at a time. A check therefore needs about 20 seconds to collect its two passing samples even when the network converged sooner, and failure detection is coarser. Timeouts still work as documented: a check is only failed on a failing sample after its timeout. If a big lab's runs are too slow, trim the recorded file to the checks that matter.

## How long does a run take, and what does CI cost?

On GitHub-hosted `ubuntu-latest` runners, measured from three CI runs on `main` on 2026-10-27, before 0.3.0 added a few checks per example:

| CI job | What it does | Time |
|---|---|---|
| `e2e (frr-bgp)` | Install containerlab and Netdryrun, pull FRR, run the checks and a link-failure scenario | 100 to 107 s |
| `e2e (srl-frr)` | The same with SR Linux and FRR (the SR Linux image is 3.2 GB) | 88 to 107 s |
| `catches-bad-change` | Run `frr-bgp-broken` and expect it to fail | 54 to 66 s |
| `agent-demo` | Replay the agent demo: two full runs | 82 to 94 s |

The whole CI workflow, with these jobs in parallel, took 2 minutes 10 seconds to 2 minutes 38 seconds in the last ten successful runs.

GitHub Actions minutes are free on public repositories with standard GitHub-hosted runners. On private repositories, each job uses minutes from your plan, rounded up to the whole minute, so a job like `e2e (frr-bgp)` uses 2 minutes. See [GitHub's billing page](https://docs.github.com/en/billing/managing-billing-for-your-products/managing-billing-for-github-actions/about-billing-for-github-actions) for current prices. Netdryrun itself is free.

Local runs are faster once images are pulled; see the times on the [examples page](examples.md).

## Does it collect any data?

No. The CLI, the GitHub Action and the MCP server have no telemetry and don't phone home. Reports are written only to the files you ask for. The GitHub Action's `cloud` input is reserved for Netdryrun Cloud, a hosted service that is not available yet; setting it today uploads nothing. See [privacy](trust.md#privacy) and the [privacy notice](privacy.md).

## What is the license?

Apache-2.0, for the code. "Netdryrun" and the logo are trademarks: forks are welcome under a different name. See [Trust and security](trust.md#license).

## Where do I get help?

Read [Troubleshooting](troubleshooting.md) first. Then [open an issue](https://github.com/netdryrun/netdryrun/issues) with the JSON report attached. See [Support](support.md).
