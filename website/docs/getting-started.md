---
title: Getting started
description: Try Netdryrun in your browser with GitHub Codespaces, or install it, check the requirements (Linux or WSL2, Docker, containerlab, Python 3.10+), and run the three bundled examples with their expected results.
---

# Getting started

## Try it in your browser

No install: [open Netdryrun in GitHub Codespaces](https://codespaces.new/netdryrun/Netdryrun?quickstart=1) and click **Create codespace**.

GitHub starts a Linux machine with Docker, containerlab 0.81.1 and Netdryrun installed from the repository, and pulls the FRR image the examples use. This takes a few minutes the first time. When the creation log shows `Ready`, run this in the terminal:

```bash
bash examples/agent-demo/demo.sh
```

The [agent demo](https://github.com/netdryrun/Netdryrun/tree/main/examples/agent-demo) boots four FRR routers twice, which takes about 65 s. The first change opens the filters to make a ticket work and is rejected by the leak guards; the second adds two prefix-list lines and passes all 14 checks. The run ends with `Demo OK`. The other FRR examples (`netdryrun run examples/frr-bgp`, `examples/frr-bgp-broken`) work the same way.

The codespace runs on the 2-core machine and uses your GitHub account's free Codespaces allowance (GitHub Free includes 120 core-hours and 15 GB of storage a month, so about 60 hours on this machine; Pro includes 180 core-hours). Stop or delete the codespace when you're done ([github.com/codespaces](https://github.com/codespaces)) so it doesn't use more. VM-based nodes (vrnetlab) don't work in Codespaces, which has no nested virtualization.

## Requirements

| Requirement | Notes |
|---|---|
| Linux or WSL2 | containerlab runs on Linux. On Windows, use WSL2. |
| Docker | The lab nodes are containers. |
| [containerlab](https://containerlab.dev/install/) | Netdryrun™ drives the `containerlab` CLI; it must be on `PATH`. |
| Python 3.10+ | |

containerlab needs root (or a user in the right groups) to create the lab. Run Netdryrun the same way you run containerlab on that machine.

!!! warning "0.3.3 and earlier: keep routing config out of topology `exec:` lines"
    containerlab only logs a failed `exec:` command, and the lab runs without what it configured, so a run can pass. Put routing config in `setup:` in `netdryrun.yml` (or, on FRR, in `frr.conf`). Fixed in 0.4. [Advisory](https://github.com/netdryrun/Netdryrun/blob/main/advisories/0.3.3-exec-not-checked/README.md).

!!! note "WSL2 and /mnt/c"
    If your topology lives under `/mnt/...` (a Windows drive), Netdryrun keeps containerlab's lab directory on the Linux filesystem (`~/.cache/netdryrun/labs`) unless you set `CLAB_LABDIR_BASE` yourself. SR Linux cannot save its config on a Windows drive.

## Install

```bash
pipx install netdryrun
netdryrun --version
```

On Ubuntu 24.04 and Debian 12 a plain `pip install` outside a virtualenv is refused ("externally managed environment"), so use pipx: `sudo apt install pipx && pipx ensurepath`, then open a new terminal. `uv tool install netdryrun`, or `pip install netdryrun` inside an activated virtualenv, work too.

The MCP server for AI agents is included: run `netdryrun mcp`. See [AI agents](ai-agents.md).

## Run the examples

The repository ships these example labs. The FRR and SR Linux images are pulled automatically on first use.

```bash
git clone https://github.com/netdryrun/Netdryrun && cd netdryrun
netdryrun run examples/frr-bgp          # 3 FRR routers, should pass
netdryrun run examples/srl-frr          # SR Linux + FRR, should pass
netdryrun run examples/frr-bgp-broken   # a bad change, should fail
examples/agent-demo/demo.sh             # replay: a leaky change rejected, the fix accepted
```

`examples/sonic-frr` needs the `docker-sonic-vs` image, which is on no container registry: download it from the SONiC build server and `docker load` it first ([how](guides/sonic-ci.md#1-get-the-image)). The example pins the build it is verified on, `docker-sonic-vs:master.1258173-c10162df4`; the build server keeps only recent builds, so tag yours with its own build id and put that tag on the image line of `examples/sonic-frr/topology.clab.yml` (`scripts/get_sonic_vs.sh` does both). Then:

```bash
netdryrun run examples/sonic-frr        # SONiC + FRR, should pass
```

`examples/arista-frr` needs a cEOS image you download from Arista and import yourself; see the [examples page](examples.md#arista-frr).

Each run deploys the lab, runs the checks, prints one line per check and destroys the lab. The first run of an example takes longer while its images are pulled.

### Expected results

The [examples page](examples.md) has every example, what it shows and how long it takes.


| Example | Topology | Checks | Expected | Exit code |
|---|---|---|---|---|
| `examples/frr-bgp` | Triangle of three FRR routers (r1, r2, r3), eBGP | 2 sessions, prefix count 1 to 10, route present via BGP, ping, best-path AS path and next hop, default route absent, and a link-failure scenario (reroute via r3) | `PASSED: 11 passed, 0 failed` | `0` |
| `examples/srl-frr` | Nokia SR Linux (`srl1`) peering eBGP with FRR (`frr1`) | 2 sessions, a BGP route on each side, a ping in each direction, best-path attributes on `srl1` | `PASSED: 7 passed, 0 failed` | `0` |
| `examples/sonic-frr` | SONiC VS (`sonic1`, configured by `setup` commands) peering eBGP with FRR (`frr1`) | a session, a BGP route on each side, a ping, a prefix count, best-path attributes, a port-down scenario | `PASSED` | `0` |
| `examples/frr-bgp-broken` | Same triangle, but r2 adds `default-originate` toward r1 | The first 6 checks of `frr-bgp`, without the scenario | `FAILED: 5 passed, 1 failed`; the default route check fails | `1` |

The broken example is the one shown on the [home page](index.md#a-failing-run). r1 receives the leaked default route but does not select it, so the ping still works. The route check catches it because a received-but-not-selected route counts as present.

SR Linux takes longer to boot, so `examples/srl-frr` sets `timeout: 120`.

## Record a baseline of your own lab (fastest start)

Point `record` at any containerlab topology you already have:

```bash
netdryrun record my-lab/topology.clab.yml --deploy
```

It deploys the lab, waits for BGP to converge, and writes `my-lab/netdryrun.yml` with a check for every established BGP session, every prefix count and every BGP route (up to 50 per node). Then make your change and run:

```bash
netdryrun run my-lab
```

Anything that changed fails, with evidence. Before committing the baseline, remove what is allowed to change and add negative checks for what must never happen (for example `present: false` for a default route at a peer). See the [`record` reference](reference/cli.md#record) and the [tutorial](tutorial.md).

## Write checks for your own lab

Put a `netdryrun.yml` next to your containerlab topology:

```yaml title="netdryrun.yml"
lab: topology.clab.yml      # your containerlab topology
timeout: 90                 # seconds a positive check may wait for convergence

checks:
  - type: bgp_session
    node: r1
    neighbor: 10.0.12.2
  - type: route
    node: r1
    prefix: 192.168.3.0/24
    protocol: bgp
  - type: ping
    node: r1
    source: 192.168.1.1
    target: 192.168.3.1
```

Check the file without starting anything, then run it:

```bash
netdryrun validate .
netdryrun run .
```

To debug a failing run, keep the lab up with `--keep` (or `--keep-on-failure`), inspect the routers, and rerun the checks against the running lab with `netdryrun check .`. Destroy it afterwards with `containerlab destroy -t topology.clab.yml --cleanup`.

Next: the [tutorial](tutorial.md) walks through all of this on a real lab, step by step. Then see the [netdryrun.yml reference](reference/config.md), the [CLI reference](reference/cli.md) and [Troubleshooting](troubleshooting.md).
