---
title: Examples
description: Every Netdryrun example lab. What each one shows, its topology and checks, the expected result and exit code, and how long it takes to run.
---

# Examples

The repository's [`examples/`](https://github.com/netdryrun/netdryrun/tree/main/examples) folder has one lab per supported network OS, a deliberately broken change, a replica exported from NetBox, and the AI agent demo. Each folder holds a containerlab topology, the router configs and a `netdryrun.yml`.

```bash
git clone https://github.com/netdryrun/netdryrun && cd netdryrun
netdryrun run examples/frr-bgp
```

## At a glance

Times are wall-clock for `netdryrun run` on WSL2 (20 cores, 16 GB) with images already pulled, measured on 2026-10-27 with containerlab 0.81.1 and Netdryrun™ 0.3.0 (`frr-bgp-broken` and `agent-demo`: 0.2.0; their checks did not change in 0.3.0). They include deploying and destroying the lab. The first run of each example also pulls its images.

| Example | Network OS | Shows | Expected | Exit | Time |
|---|---|---|---|---|---|
| [frr-bgp](#frr-bgp) | FRR | Basic checks, best-path attributes, a leak guard, a link-failure scenario | `PASSED: 11 passed, 0 failed` | `0` | 84 s |
| [frr-bgp-broken](#frr-bgp-broken) | FRR | A leaked default route caught | `FAILED: 5 passed, 1 failed` | `1` | 45 s |
| [srl-frr](#srl-frr) | Nokia SR Linux + FRR | Mixed vendors | `PASSED: 7 passed, 0 failed` | `0` | 60 s |
| [sonic-frr](#sonic-frr) | SONiC VS + FRR | Configuring a NOS after boot, a port-down scenario | `PASSED: 8 passed, 0 failed` | `0` | 90 s |
| [arista-frr](#arista-frr) | Arista cEOS + FRR (your image) | A bring-your-own vendor image | `PASSED: 10 passed, 0 failed` | `0` | 92 s |
| [netbox-nrx](#netbox-nrx) | FRR, exported from NetBox by nrx | A replica built from NetBox, a ring, a link-failure scenario | `PASSED: 33 passed, 0 failed` | `0` | 73 s |
| [agent-demo](#agent-demo) `demo.sh` | FRR | An agent's leaky change rejected, the fix accepted | `Demo OK` | `0` | 65 s |

## frr-bgp

[`examples/frr-bgp`](https://github.com/netdryrun/netdryrun/tree/main/examples/frr-bgp): three FRR routers (r1, r2, r3) in a triangle, each in its own AS, each announcing one LAN over eBGP.

**Shows:** the basic check types, a negative check and a failure scenario. r1 checks both BGP sessions, a prefix count between 1 and 10 (a leak guard), a route to r3's LAN, a ping to it, the AS path and next hop of the best path to r2's LAN (a `bgp_route` check), and that no default route arrives. The scenario takes the r1-r2 link down and checks that r2's LAN is still reachable through r3, that the best path now goes through r3 (AS path `65003 65002`), and that the session over the failed link is down.

**Expected:** `PASSED: 11 passed, 0 failed (11 checks)`, exit code `0`.

This is the lab the [tutorial](tutorial.md) uses as "your lab".

## frr-bgp-broken

[`examples/frr-bgp-broken`](https://github.com/netdryrun/netdryrun/tree/main/examples/frr-bgp-broken): the same triangle, but r2's config (`r2-bad.conf`) adds `default-originate` toward r1.

**Shows:** a bad change being caught. Sessions are up and the ping still works, because r1 receives the leaked default route but does not select it. The negative route check fails anyway: a received-but-not-selected route counts as present.

**Expected:** `FAILED: 5 passed, 1 failed (6 checks)`, exit code `1`. The failing check:

```text
  [FAIL] r1: route 0.0.0.0/0 via bgp is absent -- unexpectedly present via bgp (not selected) (0.1s)
```

CI runs this example on every push and expects it to fail.

## srl-frr

[`examples/srl-frr`](https://github.com/netdryrun/netdryrun/tree/main/examples/srl-frr): a Nokia SR Linux router (`srl1`) peering eBGP with FRR (`frr1`).

**Shows:** a mixed-vendor lab. Both sessions, a BGP route on each side, a ping in each direction, and the best path's AS path, local preference and next hop on `srl1`. SR Linux boots slower, so the file sets `timeout: 120`.

**Expected:** `PASSED: 7 passed, 0 failed (7 checks)`, exit code `0`. The SR Linux image is about 3.2 GB.

## sonic-frr

[`examples/sonic-frr`](https://github.com/netdryrun/netdryrun/tree/main/examples/sonic-frr): SONiC VS (`sonic1`, the `docker-sonic-vs` image) peering eBGP with FRR (`frr1`).

**Shows:** a NOS that is configured after boot. SONiC VS has no startup config here; `setup` commands in `netdryrun.yml` wait for its services, set the interface addresses and configure BGP. Checks: the session, a route on each side, a ping, a prefix count, best-path attributes on `sonic1`, and a scenario that takes the SONiC port `Ethernet0` down and checks that the session drops and the route is withdrawn.

**Expected:** `PASSED: 8 passed, 0 failed (8 checks)`, exit code `0`. `setup` waits for SONiC's services before any check runs.

## arista-frr

[`examples/arista-frr`](https://github.com/netdryrun/netdryrun/tree/main/examples/arista-frr): an Arista cEOS router (`ceos1`) peering eBGP with FRR (`frr1`).

**Shows:** a vendor image you bring yourself. cEOS-lab is free from arista.com with an account but can't be redistributed, so import it as `ceos:4.36.3M` first (the comment in `topology.clab.yml` shows how). Checks: both sessions, a prefix count, a route on each side, a ping, best-path attributes on `ceos1`, no default route at the Arista, and a scenario that takes the link down from the FRR side.

**Expected:** `PASSED: 10 passed, 0 failed (10 checks)`, exit code `0`. Without the image, the run stops with exit code `2`; see [the cEOS image is missing](troubleshooting.md#the-ceos-image-is-missing).

## netbox-nrx

[`examples/netbox-nrx`](https://github.com/netdryrun/netdryrun/tree/main/examples/netbox-nrx): four FRR routers (r1 to r4) in a ring, each in its own AS, described in NetBox and exported to containerlab by [nrx](https://github.com/netreplica/nrx). The configs come from a NetBox config template, so `lab/` is exactly what nrx wrote. Run `netdryrun run examples/netbox-nrx/lab`; the README has the steps from an empty NetBox.

**Shows:** a replica built from a source of truth. The baseline started from `netdryrun record` and was reviewed: all 8 sessions, 12 LAN routes, prefix counts as ranges, a ping, a best path, no default route, and a scenario that takes the r1-r2 link down and checks that r2's LAN is reached the long way round. A typo in NetBox (r3's address on the r2-r3 link) fails 6 checks while every route and the ping still pass. See [Replica from NetBox](netbox.md).

**Expected:** `PASSED: 33 passed, 0 failed (33 checks)`, exit code `0`.

## agent-demo

[`examples/agent-demo`](https://github.com/netdryrun/netdryrun/tree/main/examples/agent-demo): an edge router (`edge1`, AS 65000) with a customer, an upstream and a peer, a ticket ([`TICKET.md`](https://github.com/netdryrun/netdryrun/blob/main/examples/agent-demo/TICKET.md)) and the network team's 14 checks, including route-leak guards.

**Shows:** how an AI agent's change is judged. `demo.sh` replays two hand-written attempts: removing the prefix-list filters (passes the ticket checks, fails the leak guards) and adding the new block to two prefix lists (passes everything). See [AI agents](ai-agents.md#demo-a-ticket-a-tempting-change-a-verdict) and the [real agent run](ai-agents.md#a-real-agent-run).

**Expected:**

- `examples/agent-demo/demo.sh` exits `0` and ends with:

    ```text
    Demo OK: attempt 1 rejected by 5 leak guards with every other check passing; attempt 2 passed every check.
    ```

    Attempt 1 ends `FAILED: 9 passed, 5 failed (14 checks)`, attempt 2 `PASSED: 14 passed, 0 failed (14 checks)`. The two runs together took 65 seconds.

- `netdryrun run examples/agent-demo` shows the starting point, before anyone has worked the ticket: the guards pass and the 3 ticket checks fail, `FAILED: 11 passed, 3 failed (14 checks)`, exit code `1`. It took 119 seconds, because the failing ticket checks wait for their timeout.

## Use an example as a template

Copy a folder, change `name:` in `topology.clab.yml` (lab names must be unique on the machine), replace the configs with yours, and edit the checks. Or start from your own topology with `netdryrun record`, as in the [tutorial](tutorial.md).
