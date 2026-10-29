---
title: Trust and security
description: Netdryrun license (Apache-2.0), how releases are published with PyPI Trusted Publishing, security contact, what a lab cannot prove, and privacy (no telemetry, a website without cookies or third-party requests).
---

# Trust and security

## License

Netdryrun™ is open source under the [Apache License 2.0](https://github.com/netdryrun/netdryrun/blob/main/LICENSE). The source is at [github.com/netdryrun/netdryrun](https://github.com/netdryrun/netdryrun).

## How releases are published

- Releases are built and published by a GitHub Actions workflow when a version tag (`v*`) is pushed. The workflow checks that the tag matches the package version before building.
- Packages are uploaded to [PyPI](https://pypi.org/project/netdryrun/) with **Trusted Publishing** (OpenID Connect). No PyPI token or password is stored in the repository or its secrets; PyPI accepts the upload because it comes from that workflow in that repository.
- The same workflow creates a GitHub release with the built files attached.
- The GitHub Action (`netdryrun/netdryrun@v0.3.2`) installs Netdryrun from the action's own source at the tag you reference. Pin a tag or a commit SHA.

## Reporting a security issue

Email **[security@netdryrun.com](mailto:security@netdryrun.com)**. Please do not open a public issue for a vulnerability. Include the version, what you found, and how to reproduce it.

Past advisories: [0.3.0 could pass a check without testing what the file said](https://github.com/netdryrun/netdryrun/blob/main/advisories/0.3.0-false-pass/README.md), found by our own audit and fixed in 0.3.1, with a rerunnable test for each path. 0.3.0 is yanked on PyPI.

## What a lab cannot prove

A Netdryrun pass means the change behaved correctly in a lab. The lab runs real routing software, so a pass is strong evidence for protocol logic and policy intent: sessions come up, the intended prefixes are accepted, routes land in the routing table, traffic gets through, and unwanted routes stay out. It does not prove:

- **Vendor-specific behavior.** Open-source and container routers (FRR, SR Linux, SONiC VS) are not your vendor's routers, and even Arista cEOS is not the same as EOS on hardware. Defaults, policy evaluation and bugs differ between implementations and versions. For Arista you can bring your own licensed cEOS image.
- **Scale.** A lab has a handful of nodes and small tables, not full Internet tables or hundreds of peers.
- **Hardware and ASIC behavior.** Containers have no forwarding hardware, so TCAM limits, hardware programming and line-rate effects are not tested.
- **Timing at scale.** Convergence time in a small lab says little about convergence time in a large production network.

<!-- facts:trust_scope -->
Version 0.3.2 also covers only BGP (IPv4/IPv6 unicast), routes, BGP best-path attributes and ping, plus link-down, node-isolation and route-injection (FRR only) failure scenarios. OSPF/IS-IS adjacencies and path checks are not covered yet.
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

**AI in how we build it.** Development is done with Anthropic's Claude. Releases 0.1.0 and 0.2.0 were also reviewed by OpenAI and xAI models ([how it's built](how-its-built.md)). If you are a [design partner](design-partners.md), the sanitized configs you send us are processed with Anthropic's Claude to build your lab, under terms that don't allow training on them, and with no other AI service. They are deleted within 30 days after delivery unless you ask us to keep them. There are no paid products yet. See the [privacy notice](privacy.md#configs-you-send-us).

**This website** is static documentation hosted on GitHub Pages. It sets no cookies, has no analytics and no forms, and serves its fonts itself, so your browser contacts no third party. GitHub, as the host, receives your IP address and request details to serve the pages.

## Trademarks

"Netdryrun" and the Netdryrun logos are trademarks of the Netdryrun project. The Apache-2.0 license covers the code, not the name: forks are welcome under a different name. See the [trademark policy](https://github.com/netdryrun/netdryrun/blob/main/TRADEMARKS.md).
