---
title: Capture kit (next release)
description: netdryrun capture and netdryrun sanitize record a driver's read-only commands on your own containerlab lab node and sanitise the output, so you can contribute coverage for your NOS version without sharing an image. Part of the next release, not 0.4.0.
---

# Capture kit

!!! note "Next release"
    `netdryrun capture` and `netdryrun sanitize` are on the main branch and ship in the next release. They are not in 0.4.0. To try them before that, install from a clone (`pip install -e .`).

Your team has a licensed image Netdryrun can't get: IOS XE, IOS XR, SR OS, or a newer version of a NOS it already supports. You can still help cover it. Capture what a driver reads on your own lab node, sanitise it, and send the bundle. We never ask for the image, a licence or a config: only the command output you choose to share.

## What a capture can and can't do

- **It can** give a driver real output to parse: parser tests for your NOS version, and new shapes the driver must handle.
- **It can't** prove how the NOS behaves. A driver built only from contributed captures would ship as *captured-only*: a status that never passes a check its captures don't cover (see the [design note](https://github.com/netdryrun/Netdryrun/blob/main/docs/captured-only.md); no driver has it yet). A live run by someone who holds the image is still what makes a driver beta.

## 1. Capture, on a lab node only

Deploy your lab with containerlab and bring it to the state you want to capture (the *scenario*). Then:

```bash
netdryrun capture lab/topology.clab.yml --node r1 --scenario established --out r1-established
```

`capture` takes a containerlab topology and a node name from it, never an address or a hostname. Before it runs anything, it asks Docker for the node's container and checks the labels containerlab gives every container it creates (`containerlab=<lab>`, `clab-node-name=<node>`). It refuses:

- a node that isn't in the topology;
- a `host`, `ext-container` or bridge node (containerlab doesn't run those as lab nodes);
- a container that is missing, stopped, or whose labels name another lab or node: one someone started with `docker run`, for example.

It then runs the driver's own read methods, through a lab object that records every command the driver sends and refuses a command for any other node. So the bundle holds exactly the commands Netdryrun runs, and nothing else.

| Scenario | The lab must show | Needs |
|---|---|---|
| `established` | at least one BGP session established | |
| `no-neighbor` | at least one configured session that is not established | |
| `route-present` | the prefix in the routing table | `--prefix` |
| `route-absent` | the prefix in neither the routing table nor BGP | `--prefix` |
| `received-not-selected` | two or more BGP paths for the prefix, one best | `--prefix` |
| `community`, `med`, `no-med`, `local-pref`, `as-path` | a BGP path for the prefix with that attribute (`no-med`: without a MED) | `--prefix` |
| `ping-reply`, `ping-no-reply` | every ping answered, or none | `--target` |

If the driver's reading doesn't show the scenario, `capture` says so and exits `1`: fix the lab, or capture the scenario it does show.

| Option | Meaning |
|---|---|
| `--node NAME` | The node, by its name in the topology (required) |
| `--scenario NAME` | What the lab shows now, from the table above (required) |
| `--out DIR` | A new, empty folder for the bundle (required) |
| `--prefix PREFIX` | The prefix the route scenarios read |
| `--target ADDRESS` | The address the ping scenarios ping |
| `--source ADDRESS` | The ping's source address |
| `--vrf NAME` | The VRF to read (default `default`) |
| `--driver NAME` | The driver, when it can't be detected from the node's kind or image |
| `--nos-version TEXT` | The NOS version as you know it, kept next to the one the node reports |

## 2. Sanitise

```bash
netdryrun sanitize r1-established --hostname core-ams-1
```

The bundle `capture` wrote is not sanitised: keep it to yourself. `sanitize` rewrites, the same way in every file of the bundle:

- **IPv4 addresses** into 10.0.0.0/8, one /16 at a time. The last two octets stay, /16s keep their order, and a shorter prefix (/8 to /15) gets an aligned block, so prefix lengths and containment survive.
- **IPv6 addresses** into the documentation range 3fff::/20, one /32 at a time, the same way.
- **AS numbers**, where the output says they are AS numbers (keys such as `remoteAs` and `peer-as`, AS paths, the AS half of a community, `remote-as 65001` and `AS 65001` in text): 2-byte ones to 64512 and up, 4-byte ones to 4200000000 and up, in order.
- **Hostnames and domain names**: the node's name, every `--hostname`, and the values of hostname-like keys, to `host-1`, `host-2`, ...
- **Secrets** (passwords and keys) to `<removed>`.

It keeps every key, every other value, list lengths and order, numbers as printed, and addresses that identify nobody: loopback, link-local, multicast, masks, 0.0.0.0/8, the documentation and benchmarking ranges, and prefixes shorter than /8. Unknown fields stay: removing them would hide the shape changes we need to see.

Without `--confirm`, it shows what it would change and writes nothing. With `--confirm`, it writes the sanitised bundle, but only if its self-check passes. The self-check runs on the result and doesn't trust the rewrite:

- no public address and no AS number outside the private ranges is left, and none of the replaced names;
- every output has the same structure as before;
- the driver, run again against the sanitised outputs, asks for exactly the bundle's commands and reads the sanitised version of what it read from the originals.

The mapping (which original became which) is written next to the bundle, never inside it. Don't share it.

| Option | Meaning |
|---|---|
| `--out DIR` | Where to write the sanitised bundle (default `BUNDLE-sanitized`) |
| `--map FILE` | Where to keep the mapping (default `BUNDLE.sanitize-map.json`); it must be outside the bundle |
| `--hostname NAME` | A name to replace; repeat for several |
| `--confirm` | Write the sanitised bundle (without it, show only) |

Exit codes: `0` done (or shown), `1` the self-check failed and nothing was written, `2` the bundle can't be read, was edited after the capture, or is already sanitised.

Known limits: a four-part version number such as a Linux kernel's `6.6.87.2` reads as an address and is rewritten too; AS numbers in asdot form (`1.10`) are not recognised yet; MAC addresses are kept.

## 3. Submit

Read the sanitised bundle before you share it: the sanitiser rewrites what it recognises, and you know your network better than it does. Then either:

- open a pull request that adds it under `captures/<nos>/<version>/<scenario>/`. The contributor CI validates it within minutes: the manifest, every file's sha256, the sanitiser's self-check, a fresh leak scan, and a replay through the driver; or
- attach it as a zip to a [capture submission](https://github.com/netdryrun/Netdryrun/issues/new?template=capture-submission.yml) issue.

## The bundle

```text
r1-established-sanitized/
  manifest.json
  outputs/01-vtysh-c-show-version.txt
  outputs/02-vtysh-c-show-bgp-neighbors-json.txt
```

`manifest.json` (`netdryrun.capture/v1`) records the Netdryrun version, the capture date, the NOS (driver) name, the version the node reports and the one you gave, the containerlab kind, the image and its digest when Docker has one (a private registry host is replaced), the scenario and its options, every command with its exit code, stderr, output file and sha256, a sha256 of the command list, what the driver read, whether that shows the scenario, and the sanitiser's version, self-check result and counts.
