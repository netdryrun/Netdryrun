---
title: When to use what
description: A neutral comparison of Batfish, pyATS/Genie, containerlab and Netdryrun for network change testing. What each tool is best at and how they combine.
---

# When to use what

Several good open-source tools help you test network changes. They answer different questions and work well together. This page tries to describe each one fairly; if something here is wrong or out of date, please [open an issue](https://github.com/netdryrun/Netdryrun/issues).

## The short version

| Tool | Best at | Runs routers? |
|---|---|---|
| [Batfish](https://batfish.org) | Modelling a network from the configs of many vendors, without booting anything: reachability and traceroute, ACLs and firewall rules, routes and routing policy, failure impact, differences between two snapshots | No, it models them |
| [pyATS / Genie](https://developer.cisco.com/pyats/) | A full Python test framework with a large library of device parsers, for testing labs and real (including production) devices, with state snapshots and diffs | Works against any reachable device |
| [containerlab](https://containerlab.dev) | Running container-based network labs from a YAML topology, for many network operating systems | Yes, it is the lab |
| Your own scripts | Exactly the checks your team needs, around a lab you already run, with no new dependency | Yes, through containerlab |
| Netdryrun™ | Declarative, convergence-aware checks on a containerlab lab, packaged for CI with a pass/fail verdict and evidence | Yes, through containerlab |

## Batfish

Batfish parses device configs and uses a model of the control plane (routing protocols such as BGP) to compute the data plane that the configs would produce, then answers questions about it ([Batfish team, SIGCOMM 2023](https://doi.org/10.1145/3603269.3604866)). It needs only the configs, not access to devices ([README](https://github.com/batfish/batfish)). Its authors report analysing networks with thousands of nodes within minutes, and it reads configs from many router, firewall and cloud vendors. Its [questions](https://batfish.readthedocs.io/en/latest/questions.html) cover traceroute and reachability over every matching flow, routing tables and BGP sessions, route-map and ACL behavior, and differences between two snapshots, including a copy of the network with chosen links or nodes failed ([failure analysis](https://batfish.readthedocs.io/en/latest/notebooks/linked/analyzing-the-impact-of-failures-and-letting-loose-a-chaos-monkey.html)). A question such as "can any host in this subnet reach that server?" covers every packet, which a ping cannot.

Use it on every commit, before a lab boots, especially for ACLs, firewall policy, failure impact and configs from vendors that cannot run in containers.

A model is not the running software. Batfish computes the converged result, not the path the routers take to it, and where the model and the implementation differ (an unmodelled default, a vendor bug), its answer follows the model. A [HotNets 2025 paper from Google and UC Berkeley](https://doi.org/10.1145/3772356.3772380) makes the same point and prototypes "model-free verification": boot real router images in an emulator, extract the converged data plane, and run Batfish's queries on it. That is where a lab helps; our [Batfish page](batfish.md) shows one FRR default the model missed.

## pyATS / Genie

pyATS is a mature Python test framework from Cisco, and Genie adds a large library of parsers and models that turn CLI output into structured data. It can learn the state of a device, take before and after snapshots, and diff them. It works against lab devices and real ones.

Use it when you need deep, programmable testing, broad parser coverage (especially for Cisco platforms), or pre- and post-change checks on production devices.

Netdryrun is narrower: a YAML file and a GitHub Action, with no test code to write, and it only runs against labs. If you already have pyATS tests, keep them.

## containerlab

containerlab runs network labs from a YAML topology: container-native network operating systems (such as Nokia SR Linux, Arista cEOS, Juniper cRPD, FRR) and, through vrnetlab, many VM-based ones. It handles wiring, management addresses and lifecycle.

Use it whenever you want a real lab on a laptop or a CI runner. Netdryrun does not replace it; Netdryrun drives it.

## Your own scripts around containerlab

Many teams already run containerlab in CI with a script that deploys the lab, sleeps, runs a few `show` commands or pings, and tears down. That is free, flexible, and needs no new tool. If your checks are few and your lab rarely changes, keep it.

Scripts tend to get harder in the same places, and those are what Netdryrun packages:

- **Timing.** A fixed `sleep` either wastes minutes or fails while BGP is still converging. Netdryrun polls until each check passes twice in a row, and runs "must never happen" checks only after convergence, for a hold window.
- **Routes that hide.** A leaked route that was received but not selected doesn't show in the main routing table output on every network OS. Netdryrun's drivers read where each one keeps it (FRR, SR Linux, SONiC, cEOS).
- **Evidence.** One verdict, an exit code, JUnit, a PR comment, and a JSON file with every command and its raw output, instead of a log to read.
- **Scenarios and agents.** Link-down and node-isolation scenarios with recovery checks, and an MCP server so an AI agent can run the same checks.

The two mix well: keep a script for anything Netdryrun doesn't check, and call `netdryrun check` from it for the rest.

## Netdryrun

Netdryrun adds a test layer on top of a containerlab lab:

- positive checks wait for convergence and must pass twice in a row
- negative checks (absent routes, failing pings, prefix upper bounds) run only after convergence and must hold
- a route that was received but not selected counts as present
- every run produces one pass/fail result, a CI-friendly exit code, and a JSON evidence file

<!-- facts:when_status -->
Version 0.4.0 has drivers for FRR, Nokia SR Linux, SONiC, Arista EOS (bring your own cEOS image) and Juniper cJunosEvolved (beta), and its checks cover BGP sessions, prefix counts, routes, BGP best-path attributes and ping, with link-down, node-isolation and route-injection (FRR only) failure scenarios.
<!-- /facts:when_status -->
It does not do static analysis, build labs for you, or test production devices.

## How they combine

A reasonable pipeline uses more than one:

1. **Batfish** on every commit, to analyse the configs before anything boots.
2. A **containerlab** topology that mirrors the change.
3. **Netdryrun** in CI to boot that lab, wait for convergence, and gate the merge on runtime behavior.
4. **pyATS / Genie** (or similar) for pre- and post-change checks on the production devices during the change window.

None of these steps proves the change is safe on its own. Each one removes a different class of mistakes.

[Batfish, then Netdryrun](batfish.md) shows steps 1 and 3 together on a small FRR network, with measured times. In that test, Batfish caught two of three bad changes in seconds, before any lab booted; the third depended on an FRR default that only the running routers showed.
