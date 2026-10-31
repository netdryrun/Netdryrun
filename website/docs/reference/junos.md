---
title: Juniper cJunosEvolved driver (beta)
description: How Netdryrun reads Juniper cJunosEvolved (Junos Evolved) state, what each check type reads, what it refuses, and what to expect from a lab that boots a VM.
---

# Juniper cJunosEvolved driver (beta)

!!! note "Beta"
    The `junos` driver is beta. It is built and tested against output captured from a live `cjunosevolved:26.2R1.7-EVO` lab, and `examples/junos-frr` runs on it live, but it hasn't been run on a hosted CI runner. Other cJunosEvolved releases, vJunos and physical Junos devices are untested.

## Getting the image

cJunosEvolved is free for non-production labs, with no time limit, from Juniper's cJunosEvolved download page (accept the licence agreement, then `docker load -i` the tarball). Juniper's licence doesn't allow redistributing it, so Netdryrun never ships, mirrors or caches it: download it yourself.

Use containerlab's `juniper_cjunosevolved` kind (or `cjunosevolved`). Netdryrun detects the driver from the kind; `nodes.<node>.driver: junos` forces it.

```yaml
j1:
  kind: juniper_cjunosevolved
  image: cjunosevolved:26.2R1.7-EVO
  startup-config: configs/j1.cfg
  env:
    CPTX_NUM_IF: "1"   # the number of data links you connect (eth4 and up)
```

## Host and timing

- **KVM is required.** The container runs Junos in a QEMU VM, so the host needs `/dev/kvm` (on WSL2, nested virtualization). GitHub's standard hosted runners are not a tested target.
- **Memory:** about 8 GB for one node (measured: 8.2 GiB). 4 vCPUs minimum.
- **Boot time:** every deploy installs Junos inside the VM and reboots it. Set `CPTX_NUM_IF` to the number of data links you connect: without it the container waits 5 minutes for 36 interfaces before it starts the VM. Measured on WSL2 (20 threads, 16 GB) with `CPTX_NUM_IF` set and nothing else running: Junos answered about 4 minutes after deploy, BGP was up after about 6, and the whole `netdryrun run` of `examples/junos-frr` took 398 s. Without `CPTX_NUM_IF`, and on a busy host, it took about 22 minutes to BGP.
- **One VM at a time on a 16 GB host.** With a second vendor VM booting next to it, the Junos VM logged CPU soft lockups and the host stopped answering for minutes.
- Set `timeout` high enough for the boot (the example uses `1800`). While the VM boots, every read is an error on that sample (the check keeps waiting); it is never read as "no sessions".
- **Netdryrun doesn't verify the Junos config load yet** (the report says `not verified on junos`): add a positive check for what each changed line creates.
- **A startup config Junos rejects fails quietly:** the hostname stays `re0`, the VM's console logs "Failed to start MGD initialization of schema and database", and the routing daemon never starts. We hit this with a config that had a `/* */` comment, no `## SECRET-DATA` marker and a mixed IPv4/IPv6 route filter (which of the three Junos rejected wasn't isolated). The example's `configs/j1.cfg` follows containerlab's sample format and loads.

## How state is read

The container's own `cli -c` ignores its argument and opens an interactive CLI. Netdryrun uses the container's internal SSH hop to the VM instead, as the container's `cli` wrapper does, and asks for JSON:

```text
docker exec <node> ssh -i /root/.ssh/sshkey root@176.1.1.1 "cli -c '<command> | display json | no-more'"
```

Netdryrun's `default` VRF is the Junos `master` instance (tables `inet.0`, `inet6.0`); `vrf: X` is routing-instance `X` (tables `X.inet.0`, `X.inet6.0`). `vrf: master` is refused: use `default`.

| Check | Command | Reads |
|---|---|---|
| `bgp_session` | `show bgp neighbor instance <master\|X>` | `peer-state` per peer; a peer of another instance in the answer is an error |
| `bgp_prefixes` | the same, and `show route receive-protocol bgp <peer> table <table> hidden extensive` when the peer has hidden routes | received minus routes rejected by import policy, from `received-prefix-count` of the peer's `inet.0` (IPv4) or `inet6.0` (IPv6) RIB and the hidden routes' `hidden-reason` (see below) |
| `route` | `show route <prefix> exact table <table> all extensive` | every route for the prefix, hidden ones included |
| `bgp_route` | the same | the BGP routes for the prefix and their attributes |
| `ping` | `ping <target> count <n> rapid wait 1 [source <ip>] [routing-instance X]` | `probe-results-summary` (probes sent, responses received) |
| `netdryrun record` | `show route table <table>` | every route in the table |

## Received, hidden and filtered routes

- **Present means received.** A BGP route that loses to a static or local route (a leaked default behind your own static) is listed by Junos as inactive. It counts as present, not selected, so `present: false` fails, as on every driver.
- **Hidden for an unusable next hop counts as received.** Junos hides a route whose next hop it can't use (`hidden-reason`: for example "Protocol nexthop is not on the interface"). It was received, so it counts as present but not selected, like an invalid path on FRR, SR Linux and Arista EOS.
- **Rejected by import policy is filtered.** Junos keeps a route its import policy rejected as hidden, `hidden-reason` "Rejected by import policy". It can never be used, and FRR and EOS don't keep such a route at all, so it doesn't count: an import filter that drops a leak makes `present: false` pass. A hidden route with any other reason, or none, counts as present.
- **Prefix counts:** Junos's `accepted-prefix-count` leaves out every hidden route, for an unusable next hop as well as for import policy, so it is not used alone. When `received-prefix-count` is higher, Netdryrun reads the peer's hidden routes and subtracts only those with `hidden-reason` "Rejected by import policy", the count FRR, SR Linux and Arista EOS give (0.4 interop test, IOP-7). Only two reasons are known: "Rejected by import policy" (not received) and "Protocol nexthop is not on the interface" (received). When a hidden route gives any other reason, or none, the count is known only as a range, from accepted to received: a bound passes or fails only when every value in the range gives the same answer, and otherwise fails with "can't tell whether the bound holds". When the hidden routes can't be read at all, such a check fails as an error (the node gave no usable state). It never passes on a guess, and `netdryrun record` writes no count for such a neighbor.
- **BGP's best path:** the active BGP route. When a route of another protocol is active (a static default beats the leaked BGP one), the best BGP path is the first BGP route whose only reason to lose is route preference, as FRR reports it.
- **The router's own routes:** Junos doesn't list its own static, direct or aggregate routes as BGP routes, even when an export policy advertises them. `bgp_route` on Junos reads routes received over BGP only; check what a router advertises on the neighbor that receives it.
- **Attributes:** AS path from `as-path` (sets `{a,b}`, confederation sequences `(a b)`; a bracketed local AS or any unknown token is an error), MED from `metric` ("not set" when absent: Junos omits `metric` when no MED was received, so `med: 0` fails on such a path), local preference from `local-preference` ("not set" when absent), communities from `communities` (`large:a:b:c` entries are large communities), next hop from the protocol next hop when shown (iBGP) or the selected forwarding next hop.

## Errors are never "nothing"

Junos exits 0 for everything, errors included. The driver reads every answer as the JSON document it expects:

- `error: ...` text (a syntax error, a command Junos refuses) is an error on that sample.
- An unknown routing table is an explicit `route-table-error`. The driver then reads `show route instance <X>`: an instance that exists without the table (no IPv6 in that VRF) has no routes there; one that doesn't exist is an error.
- An unknown BGP instance answers exactly like one without peers, so an empty neighbor list in a VRF is trusted only after `show route instance <X>` confirms the instance.
- An unknown element where Junos lists routes or peers (a renamed list) is an error, never an empty table.
- `ping-failure` is ignored (Junos sets it even when every probe is answered); only `probe-results-summary` counts. No summary means ping didn't run (a bad source address, an unknown instance) or the destination is unreachable ("No route to host").

## Refused before deploying

- `afi: evpn` on `bgp_prefixes` (the driver reads IPv4 and IPv6 unicast counts only; an EVPN count would read 0).
- `link_down` and `node_isolated` faults on a cJunosEvolved node: fail the FRR or Linux side of the link instead.
- `inject_routes` from a cJunosEvolved node: inject from an FRR neighbor.

## Example

[`examples/junos-frr`](https://github.com/netdryrun/Netdryrun/tree/main/examples/junos-frr): cJunosEvolved and FRR peering eBGP, the good configs passing and a one-line leak failing exactly the leak guard. Its README has the real output of both runs.
