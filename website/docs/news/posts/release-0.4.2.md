---
date: 2026-11-21
slug: release-0.4.2
title: "Netdryrun 0.4.2: fixes from the new-user test and the red team"
description: "0.4.2 fixes the two problems the new-user test found on 0.4.1, cases 3 and 4 of the 0.4.1 advisory, and false passes found before release, among them BGP add-path paths counted as prefixes."
categories:
  - Releases
---

# Netdryrun 0.4.2: fixes from the new-user test and the red team

0.4.2 is a fix release. It fixes what our new-user test found on 0.4.1, two of the four known false passes in the 0.4.1 advisory, and further false passes our red team found before release.

*Posted on 23 November, with 0.4.3: 0.4.2 shipped on 21 November without a release post.*

<!-- more -->

- **Two problems the new-user test found on 0.4.1** (both failed safe: an error, never a wrong pass). SR Linux on containerlab 0.83 refused every check, and on FRR 10.2 `record` and route checks stopped on every BGP prefix answer.
- **`bgp_prefixes` counted add-path paths as prefixes** on FRR, SONiC, SR Linux and Arista EOS, so a `min` could pass on fewer prefixes than it asked for ([0.4.2 advisory](https://github.com/netdryrun/Netdryrun/blob/main/advisories/0.4.2-addpath-prefix-count/README.md), [GHSA-hcc6-p4rp-w376](https://github.com/netdryrun/Netdryrun/security/advisories/GHSA-hcc6-p4rp-w376)).
- **Further false passes found before release:** withdrawn and dampened paths read as received routes (FRR, SONiC, NX-OS), graceful-restart stale paths counted (FRR, SONiC), labeled-unicast sessions read as empty (FRR, SONiC), `record` guards missing in VRFs, a ping source of the other address family, an AS path in asdot kept as text on Arista EOS, and a duplicate key in a YAML merge.
- **Cases 3 and 4 of the [0.4.1 advisory](https://github.com/netdryrun/Netdryrun/blob/main/advisories/0.4.1-known-false-passes/README.md):** a `ping` in a VRF to the VRF device's own address (FRR, SONiC), and SR Linux `record --attributes` leaving out an AS path it couldn't read, which is now a named gap.
- **`record` on BGP-unnumbered links:** a link with link-local addresses only and a BGP session over it is no longer a gap. The sessions themselves, named by their interface, stayed a named gap in 0.4.2, so `record` exited 1 there; 0.4.3 records them on FRR.

Not fixed in 0.4.2, each with a workaround: cases 1 and 2 of the 0.4.1 advisory (Arista EOS routes that lost route selection, SR Linux EVPN routes in an ip-vrf), both fixed in 0.4.3. On Arista EOS, `route ... protocol: bgp present: false` passed on the node's own BGP aggregate; the 0.4.2 notes suggested `protocol: aggregate` instead, which doesn't hold while a static route for the same prefix wins. On 0.4.2, use `bgp_route ... present: false` on the prefix; 0.4.3 fixes both. The [CHANGELOG](https://github.com/netdryrun/Netdryrun/blob/main/CHANGELOG.md) lists every limit.

How it was tested: before publishing, static checks, the unit suite on every supported Python, mutation testing, live labs on the built package and the scripted acceptance round passed on the release commit. Three live items that are optional or not scripted yet were accepted, and the [gate report](https://github.com/netdryrun/Netdryrun/blob/main/releases/0.4.2/GATE.md) lists them. After publishing, one outside listing still named an older version; the gate report records that too.

[Full changelog](https://github.com/netdryrun/Netdryrun/blob/main/CHANGELOG.md) · [Release on GitHub](https://github.com/netdryrun/Netdryrun/releases/tag/v0.4.2)
