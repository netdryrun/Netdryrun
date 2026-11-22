---
date: 2026-11-23
slug: release-0.4.3
title: "Netdryrun 0.4.3: false-pass fixes for Arista EOS, SR Linux EVPN and FRR"
description: "0.4.3 fixes the two open cases of the 0.4.1 advisory, the node's own BGP aggregate on Arista EOS and FRR's import check at boot, and checks BGP-unnumbered sessions on FRR."
categories:
  - Releases
---

# Netdryrun 0.4.3: false-pass fixes for Arista EOS, SR Linux EVPN and FRR

0.4.3 is a fix release. It closes the two cases of the 0.4.1 advisory that 0.4.2 left open, fixes two false passes found since, and lets checks on FRR name a BGP-unnumbered session by its interface.

<!-- more -->

- **Arista EOS: a route that lost route selection is seen** (case 1 of the [0.4.1 advisory](https://github.com/netdryrun/Netdryrun/blob/main/advisories/0.4.1-known-false-passes/README.md), RT-0056, RT-0063). EOS's routing table lists only the route it selected, so a floating static behind an eBGP default, or an OSPF default behind a static route, wasn't seen and `route ... protocol: static` (or `ospf`) `present: false` passed. The driver now also reads the RIB, which lists every candidate. Confirmed live on cEOS 4.36.3M.
- **Arista EOS: the node's own BGP aggregate is `bgp`, selected or not** (RT-0085, RT-0086). 0.4.2 read it as `aggregate` while it was selected and didn't see it while a static route for the same prefix won, so `present: false` checks passed on it. It is now `bgp` in every read, as on FRR and NX-OS, and `protocol: aggregate` is refused on EOS before the lab deploys.
- **SR Linux EVPN: type-5 routes imported into an ip-vrf are seen** (case 2 of the same advisory, RT-0058). `bgp_route present: false` in an ip-vrf passed while an EVPN route was imported into it, with or without BGP in the ip-vrf. The driver now reads the EVPN routes imported into that ip-vrf as received paths. Both designs were reproduced live on SR Linux 26.7.2.
- **FRR's import check at boot** (RT-0084). On some lab boots FRR's bgpd applies its `network` statements before its connection to zebra is up, then announces each prefix for the life of the lab whatever the routes say. A change that deleted the route behind a `network` could pass, and `verify` could approve it. This was the cause of the corpus v2 case 18 race. Netdryrun now reads every FRR and SONiC router's import-check table before judging. On a lab the run deployed, a stuck router gets one reset command and is read again; otherwise the run is an error, never a pass. [Details](../../reference/config.md#frrs-import-check-at-boot).
- **Checks on BGP-unnumbered sessions (FRR).** `bgp_session` and `bgp_prefixes` can name a session by its interface (`neighbor: eth1`), and `record` writes those checks where 0.4.2 named each such session as a gap. `bgp_prefixes` on an interface name needs `afi`. Other drivers refuse an interface name before the lab deploys (exit `2`).
- **PyYAML 6.0.4 is excluded.** It changed how YAML merge keys are expanded. No verdict was found to change, and the tests now check the installed PyYAML's merge behaviour.

**Stricter on replay:** a 0.4.2 baseline with `route ... protocol: bgp present: false` on an EOS node's own aggregate prefix now fails, where 0.4.2 passed it. Record that baseline again, or change the check to `present: true`.

Known limits in 0.4.3, each with a workaround on the [trust page](../../trust.md):

- **SR Linux EVPN ip-vrfs without PE-CE BGP:** `bgp_route` checks there come out not evaluated (a failure, never a pass), because the convergence gate can't read SR Linux's EVPN BGP state yet. Use a `route` check with `protocol: bgp` in the ip-vrf.
- **The import-check reset** can briefly announce an unbacked prefix to a peer. It wasn't seen in 3 live tries, but the timing isn't guaranteed. SONiC gets the same check, but it hasn't been run against a live SONiC lab yet.
- **An unresolved static route on Arista EOS** is in no EOS read, so `protocol: static present: false` passes on EOS where FRR fails it.
- The limits 0.4.2 listed as not fixed are still open, among them the node's own exported prefix on SR Linux and Junos, the EOS `out-delay`, the NX-OS FIB state, and a route that takes one advertisement interval per hop. The [roadmap](../../roadmap.md) lists them all.

Each false-pass fix, and the unnumbered session checks, has an oracle test built from live router output. Upgrade with `pipx upgrade netdryrun` and pin `netdryrun/Netdryrun@v0.4.3`.

Think you can make it say "passed" when it shouldn't? [Open a corpus case](https://github.com/netdryrun/Netdryrun/issues/new?template=corpus-case.yml) and it becomes a permanent must-fail test.

[Full changelog](https://github.com/netdryrun/Netdryrun/blob/main/CHANGELOG.md) · [Release on GitHub](https://github.com/netdryrun/Netdryrun/releases/tag/v0.4.3)
