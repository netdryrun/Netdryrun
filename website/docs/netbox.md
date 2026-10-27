---
title: Test changes on a replica built from NetBox
description: Build a containerlab replica of your network from NetBox with nrx, record a baseline with Netdryrun, and catch a bad NetBox change before it reaches the network. Exact steps, what nrx exports, caveats and measured times.
---

# Test changes on a replica built from NetBox

If NetBox is your source of truth, it already describes the network you want to test: devices, cables, addresses and, with config templates, the configs. [nrx](https://github.com/netreplica/nrx) (Apache-2.0, by netreplica) exports that as a containerlab topology. Netdryrun™ boots it, checks it against a baseline, and returns a verdict with evidence.

```text
NetBox  ──nrx──▶  topology.clab.yaml + one config per device  ──netdryrun run──▶  PASSED / FAILED + evidence
```

The worked example is [`examples/netbox-nrx`](https://github.com/netdryrun/netdryrun/tree/main/examples/netbox-nrx): four FRR routers in a ring, loaded into a local NetBox by a script, exported by nrx, recorded, and then broken by a one-character typo in NetBox. Its [README](https://github.com/netdryrun/netdryrun/blob/main/examples/netbox-nrx/README.md) has every command.

## What nrx exports

| From NetBox | Becomes | Notes |
|---|---|---|
| Devices (filtered by site, tags and role) | containerlab nodes | Roles to export are set in the nrx config. |
| Platform | node kind and image | Through a platform map. The example maps platform `frr` to a `linux` node running FRR. |
| Cables | links | Interfaces are renamed `eth1`, `eth2`, ... in the order of their NetBox names, sorted as text. |
| Config template, if the device has one | `<device>.config` | nrx asks NetBox to render it. Without one you get wiring only, and the configs are yours to write. |

The example's NetBox config template renders the whole FRR config from NetBox data: interface addresses, the ASN from the device's config context, and a BGP neighbor for the far end of each cable. So a change in NetBox, such as an address, a cable or an ASN, flows into the replica's configs on the next export.

## The workflow

1. **Export:** `nrx -o clab -s <site> ...` writes the topology and the configs.
2. **Record once:** `netdryrun record <topology> --deploy` writes a `netdryrun.yml` baseline of the sessions, prefix counts and routes it sees. Review it: remove what may change, and add what must never happen.
3. **For every NetBox change:** export again and run `netdryrun run`. The exit code is `0` if the replica still behaves like the baseline, `1` if not.

## What the example measured

On WSL2 (20 cores, 16 GB) on 2026-10-27, with NetBox 4.7, nrx 0.9.0, containerlab 0.81.1, FRR 10.4.1 and Netdryrun 0.3.0:

| Step | Result | Time |
|---|---|---|
| nrx export | 4 nodes, 4 links, 4 rendered configs | 1.4 s |
| `netdryrun record --deploy` | 28 checks recorded | 51 s |
| `netdryrun run`, reviewed baseline | `PASSED: 33 passed, 0 failed` | 73 s, 71 s |
| `netdryrun run`, after the typo in NetBox | `FAILED: 27 passed, 6 failed`, exit `1` | 205 s |

The bad change is r3's address on the r2-r3 link mistyped as `10.0.23.6/30` instead of `10.0.23.2/30`. Every LAN route and the ping still pass, because traffic goes the other way round the ring. The BGP session checks fail on both ends of the r2-r3 link, and the link-failure scenario shows the consequence: with r1-r2 also down, r2's LAN can't be reached from r1. A ping test alone would have passed this change.

## Caveats

- **Review the recording.** In this ring, the exact prefix counts that `record` saved changed from boot to boot (two neighbors offer equal-length paths), so the first unreviewed run failed 2 of 28 checks. The committed baseline uses a range of 1 to 10 instead.
- **Interface names must match.** Configs have to use the emulated names (`eth1`, ...). The example names its NetBox interfaces that way. With names like `Ethernet1/1`, make the config template emit the emulated name, or use a network OS kind that nrx can give an interface map.
- **FRR on a `linux` node needs its own node template.** nrx's stock `linux` template drops the rendered config. The example's template binds it to `/etc/frr/frr.conf`.
- **NetBox 4.7 rejects a role filter naming a role it doesn't have.** nrx's default role list does, so the example's nrx config lists only `router`.
- **A replica runs the images you give it.** The example uses FRR everywhere. For your network, map each NetBox platform to the containerlab kind and image you run (nrx ships templates for SR Linux, cEOS and SONiC, among others); see [Examples](examples.md) for the network OSes Netdryrun has been tested with.

## Next

- Run the committed export without NetBox: `netdryrun run examples/netbox-nrx/lab`.
- Run it in CI with the [GitHub Action](github-action.md), after the step that exports from NetBox.
- Write checks by hand: [netdryrun.yml reference](reference/config.md).
