---
title: Trust and security
description: Netdryrun license (Apache-2.0), how releases are published with PyPI Trusted Publishing, security contact, what a lab cannot prove, and privacy (no telemetry, a website without cookies or third-party requests).
---

# Trust and security

## License

Netdryrun™ is open source under the [Apache License 2.0](https://github.com/netdryrun/Netdryrun/blob/main/LICENSE). The source is at [github.com/netdryrun/Netdryrun](https://github.com/netdryrun/Netdryrun).

## How releases are published

- Releases are built and published by a GitHub Actions workflow when a version tag (`v*`) is pushed. The workflow checks that the tag matches the package version before building.
- Packages are uploaded to [PyPI](https://pypi.org/project/netdryrun/) with **Trusted Publishing** (OpenID Connect). No PyPI token or password is stored in the repository or its secrets; PyPI accepts the upload because it comes from that workflow in that repository.
- The same workflow creates a GitHub release with the built files attached.
- The GitHub Action (`netdryrun/Netdryrun@v0.4.0`) installs Netdryrun from the action's own source at the tag you reference. Pin a tag or a commit SHA.

## Reporting a security issue

Email **[security@netdryrun.com](mailto:security@netdryrun.com)**. Please do not open a public issue for a vulnerability. Include the version, what you found, and how to reproduce it.

Advisories: every false pass we have found, in our own audits and games before any outside user reported it:

| Version | What could pass wrongly | Status |
|---|---|---|
| 0.3.0 | A check could pass without testing what the file said | Fixed in 0.3.1; 0.3.0 is yanked on PyPI. [Advisory](https://github.com/netdryrun/Netdryrun/blob/main/advisories/0.3.0-false-pass/README.md) |
| 0.3.2 and earlier | An FRR config line the router rejected at boot was skipped silently | Fixed in 0.3.3. [Advisory](https://github.com/netdryrun/Netdryrun/blob/main/advisories/0.3.2-rejected-config/README.md) |
| 0.3.3 and earlier | A failed topology `exec:` command left the lab without that config | Fixed in 0.4.0. [Advisory](https://github.com/netdryrun/Netdryrun/blob/main/advisories/0.3.3-exec-not-checked/README.md) |
| 0.3.3 and earlier | On Arista EOS, `med: 0` passed on a path received with no MED (cEOS prints MED 0 for both) | Fixed in 0.4.0: a `med: 0` check on EOS is refused. [Changelog](https://github.com/netdryrun/Netdryrun/blob/main/CHANGELOG.md) |

## What a lab cannot prove

A Netdryrun pass means the change behaved correctly in a lab. The lab runs real routing software, so a pass is strong evidence for protocol logic and policy intent: sessions come up, the intended prefixes are accepted, routes land in the routing table, traffic gets through, and unwanted routes stay out. It does not prove:

- **Vendor-specific behavior.** Open-source and container routers (FRR, SR Linux, SONiC VS) are not your vendor's routers, and even Arista cEOS is not the same as EOS on hardware. Defaults, policy evaluation and bugs differ between implementations and versions. For Arista you can bring your own licensed cEOS image.
- **Scale.** A lab has a handful of nodes and small tables, not full Internet tables or hundreds of peers.
- **Hardware and ASIC behavior.** Containers have no forwarding hardware, so TCAM limits, hardware programming and line-rate effects are not tested.
- **Config the NOS skipped.** A config line rejected at boot makes the run an error on FRR and Arista cEOS (each lists what it skipped), SR Linux fails containerlab's deploy on one, and SONiC is configured by checked `setup:` commands (a config bound into it is an error). On Juniper (beta) the load is not verified yet, and the report says so: add a positive check for what each changed line creates.
- **Timing at scale.** Convergence time in a small lab says little about convergence time in a large production network.

<!-- facts:trust_scope -->
Version 0.4.0 also covers only BGP (IPv4/IPv6 unicast), routes, BGP best-path attributes and ping, plus link-down, node-isolation and route-injection (FRR only) failure scenarios. OSPF/IS-IS adjacencies and path checks are not covered yet.
<!-- /facts:trust_scope -->

## Running untrusted labs

containerlab runs privileged containers, so a topology and its configs are code that runs with root on the host. Only run labs you trust. In CI, see the [GitHub Action security notes](github-action.md#security-notes). For AI agents, see the [MCP safety model](ai-agents.md#safety-model).

What follows from that, by design:

- **`netdryrun.yml` is code too.** `nodes.<node>.setup` commands are shell commands run inside the node, and a `netdryrun.yml` can point at a topology in any folder. Review a `netdryrun.yml` the way you review a topology.
- **Everything else in `netdryrun.yml` is data.** From 0.3.1, VRF and interface names are restricted to letters, digits and a few punctuation marks before they reach a device CLI, and addresses and prefixes must parse as IP. A check can't run a device command it doesn't name.
- **`as_path_regex` runs with no time limit.** A pathological pattern can stall a run until your CI job's timeout; it can't do anything else. Set `timeout-minutes` on the job.
- **Text from a lab is treated as untrusted** wherever it ends up (0.3.1 and later): escaped in PR comments and step summaries, kept to one comment line in a recorded baseline, and flattened and capped in MCP results.

## Privacy

**The tool has no telemetry.** The CLI, the GitHub Action and the MCP server do not phone home or send usage data anywhere. Reports are written only to the files you ask for (and to the GitHub Actions step summary when running in Actions). containerlab and Docker may pull images from registries named in your topology, as they normally would.

The GitHub Action has a `cloud` input reserved for a future hosted service, Netdryrun Cloud. **Netdryrun Cloud is not available yet**: its address doesn't exist, so setting `cloud: true` today uploads nothing and only adds an "evidence upload failed" warning. If it launches, uploading will stay opt-in, and its privacy terms will be published first. Leave `cloud` off.

**No AI inside the tool.** The CLI, the GitHub Action and the MCP server contain no AI model and call no AI service; verdicts come from checks run against your lab. When an AI agent uses the MCP server, the agent sends whatever it chooses to the model provider *you* picked; Netdryrun is not part of that path.

**Configs you send us.** Design partners keep their configs on their side by default; the lab runs on their machine or CI runner. If a [design partner](design-partners.md) opts in to sending us sanitized configs, they are processed with Anthropic's Claude to build their lab, under terms that don't allow training on them, and with no other AI service. They are deleted within 30 days after delivery unless the partner asks us to keep them. There are no paid products yet. See the [privacy notice](privacy.md#configs-you-send-us).

**This website** is static documentation hosted on GitHub Pages. It sets no cookies, has no analytics and no forms, and serves its fonts itself, so your browser contacts no third party. GitHub, as the host, receives your IP address and request details to serve the pages.

## Trademarks

"Netdryrun" and the Netdryrun logos are trademarks of the Netdryrun project. The Apache-2.0 license covers the code, not the name: forks are welcome under a different name. See the [trademark policy](https://github.com/netdryrun/Netdryrun/blob/main/TRADEMARKS.md).
