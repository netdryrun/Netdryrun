---
title: Network Change Verdict Corpus
description: 30 realistic BGP changes with expected verdicts committed before any run, tested with ping-only checks, session-only checks and Netdryrun intent checks in a real containerlab lab. Losses published.
---

# Network Change Verdict Corpus

How much does a typical "ping after the change" test miss? This corpus answers that with data anyone can rerun.

!!! info "How to read these numbers"
    This is a small benchmark the Netdryrun maintainers wrote: one FRR provider topology, 30 changes in v1 and 18 in v2, each labelled harmful or safe before any run. It compares testing methods on the same changes. It is **not** an independent benchmark and **not** a reliability estimate for production networks: "24/30" does not mean Netdryrun is right 80% of the time on your network. Both runs below are the rerun on the released 0.3.1 (commit `08059de`, code identical to the v0.3.1 tag), done by the release gate on 2026-10-27. The first published runs used pre-release builds (v1: commit `ec23379`, which called itself 0.2.0; v2: a development build that recorded no commit). On 0.3.1 every v1 verdict is unchanged, and v2 changed on one case: 18, now rejected as its expected verdict says. The [changes since](how-its-built.md#every-miss-and-what-it-changed) are listed per miss.

There are two runs. v1's cases and expected verdicts are frozen as first published; its results below are the 0.3.1 rerun, with the same verdicts as the first run. [Corpus v2](#corpus-v2) is a second, separately pre-registered run that makes v1's misses testable, including scenarios where a customer or peer misbehaves.

## Method

- **The network:** a small provider (AS65000, two routers) with a customer, an upstream transit and a settlement-free peer, running FRR in containerlab. Its written intent is in [INTENT.md](https://github.com/netdryrun/Netdryrun/blob/main/corpus/INTENT.md).
- **The changes:** 30 realistic edits ([cases](https://github.com/netdryrun/Netdryrun/tree/main/corpus/cases)): route leaks, filter typos, mass withdrawals, fat-fingered ASNs, latent risks, and safe changes that must not be blocked.
- **Pre-registered verdicts:** each case's expected verdict (would an experienced operator reject it?) was **committed to git before any run**. Verdicts are never edited afterwards; findings after the run are listed separately below.
- **Three strategies, same running lab per case:**
    1. **Ping only:** the customer pings the upstream and the peer.
    2. **All BGP sessions up:** every session established.
    3. **Netdryrun™ intent checks:** one [intent spec](https://github.com/netdryrun/Netdryrun/blob/main/corpus/specs/intent.yml), written once and used unchanged for every case, so it can't be tuned to win.
- **Rerun it:** `python corpus/run.py` on any Linux or WSL2 machine with Docker and containerlab. It uses the Netdryrun code in your checkout.
- **Rerun it on GitHub's machines:** fork the repository, then run the [Reproduce corpus](https://github.com/netdryrun/Netdryrun/blob/main/.github/workflows/reproduce-corpus.yml) workflow from your fork's Actions tab. It has not been run on GitHub yet, and it covers v1 only. It installs containerlab 0.81.1 and Netdryrun from your checkout (not the build that produced the committed results, so a verdict that differs can come from a code change) on a GitHub-hosted runner, runs every v1 case, uploads `results.json`, `RESULTS.md` and the run log as artifacts, and lists every verdict that differs from the committed [`results.json`](https://github.com/netdryrun/Netdryrun/blob/main/corpus/results/results.json) in the run summary.

## Results

<!-- RESULTS -->

Generated 2026-10-27T18:00:53+00:00 with netdryrun 0.3.1, containerlab 0.81.1, FRR quay.io/frrouting/frr:10.4.1, commit `08059de`. Rerun everything with `python corpus/run.py`.

**Conflict of interest:** the Netdryrun maintainers wrote this corpus and the runner. Expected verdicts were committed before any run (see the git history of [`corpus/cases/`](https://github.com/netdryrun/Netdryrun/tree/main/corpus/cases)). Losses are kept and shown at the same size as the catches.

## Summary (30 cases: 19 harmful, 11 safe)

| Strategy | Correct | Harmful changes caught | Approved a bad change | Blocked a good change | Errors |
|---|---|---|---|---|---|
| Ping only | **20/30** | 9/19 | 10 | 0 | 0 |
| All BGP sessions up | **15/30** | 4/19 | 15 | 0 | 0 |
| Netdryrun intent checks | **24/30** | 14/19 | 5 | 1 | 0 |

## Every case

| Case | Category | Expected | Ping only | Sessions up | Netdryrun | What Netdryrun flagged |
|---|---|---|---|---|---|---|
| `01-no-change` [No change (control)](corpus/01-no-change.md) | control | safe | ✅ | ✅ | ✅ | nothing |
| `02-med-to-upstream` [Set MED on routes sent to the upstream](corpus/02-med-to-upstream.md) | traffic-engineering | safe | ✅ | ✅ | ✅ | nothing |
| `03-prepend-to-peer` [Prepend our AS twice toward the peer](corpus/03-prepend-to-peer.md) | traffic-engineering | safe | ✅ | ✅ | ✅ | nothing |
| `04-tag-community-upstream` [Tag our aggregate with an informational community toward the upstream](corpus/04-tag-community-upstream.md) | hygiene | safe | ✅ | ✅ | ✅ | nothing |
| `05-description-only` [Change an interface description](corpus/05-description-only.md) | hygiene | safe | ✅ | ✅ | ✅ | nothing |
| `06-customer-adds-prefix` [Customer announces a second allowed /24](corpus/06-customer-adds-prefix.md) | customer-growth | safe | ✅ | ✅ | ⚠️ blocked a good change | I5 upstream receives exactly our 2 prefixes; I5 peer receives exactly our 2 prefixes |
| `07-tighten-max-prefix` [Lower the customer maximum-prefix from 100 to 50](corpus/07-tighten-max-prefix.md) | hygiene | safe | ✅ | ✅ | ✅ | nothing |
| `08-upstream-timers` [Shorten BGP timers toward the upstream](corpus/08-upstream-timers.md) | hygiene | safe | ✅ | ✅ | ✅ | nothing |
| `09-customer-localpref` [Lower customer local-preference from 300 to 250](corpus/09-customer-localpref.md) | traffic-engineering | safe | ✅ | ✅ | ✅ | nothing |
| `10-transit-export-filter-removed` [Upstream export filter replaced with permit-all](corpus/10-transit-export-filter-removed.md) | route-leak | unsafe | ❌ approved a bad change | ❌ approved a bad change | ✅ | I4 no peer route leaked to upstream; I5 upstream receives exactly our 2 prefixes |
| `11-peer-export-filter-removed` [Peer export filter replaced with permit-all](corpus/11-peer-export-filter-removed.md) | route-leak | unsafe | ❌ approved a bad change | ❌ approved a bad change | ✅ | I4 no upstream route leaked to peer; I4 no default leaked to peer; I5 peer receives exactly our 2 prefixes |
| `12-ibgp-send-community-dropped` [send-community removed on the pe1 to pe2 iBGP session](corpus/12-ibgp-send-community-dropped.md) | policy-bug | unsafe | ❌ approved a bad change | ❌ approved a bad change | ❌ approved a bad change | nothing |
| `13-upstream-asn-typo` [Typo in the upstream's ASN (65020 instead of 65200)](corpus/13-upstream-asn-typo.md) | fat-finger | unsafe | ✅ | ✅ | ✅ | I1 pe1-up1 session up; I2 upstream has customer route; I2 upstream has our aggregate; I3 customer has upstream route; I3 customer has default; I3 customer reaches upstream; I4 no peer route leaked to upstream; I5 upstream receives exactly our 2 prefixes |
| `14-peer-session-shutdown` [Peer session administratively shut down](corpus/14-peer-session-shutdown.md) | fat-finger | unsafe | ✅ | ✅ | ✅ | I1 pe2-peer1 session up; I2 peer has customer route; I2 peer has our aggregate; I3 customer has peer route; I3 customer reaches peer; I4 no upstream route leaked to peer; I4 no default leaked to peer; I5 peer receives exactly our 2 prefixes |
| `15-customer-filter-too-strict` [Customer prefix-list typo rejects the customer's /24](corpus/15-customer-filter-too-strict.md) | policy-bug | unsafe | ✅ | ❌ approved a bad change | ✅ | I2 upstream has customer route; I2 peer has customer route; I3 customer reaches upstream; I3 customer reaches peer; I5 upstream receives exactly our 2 prefixes; I5 peer receives exactly our 2 prefixes |
| `16-mass-withdrawal` [Upstream export policy denies everything](corpus/16-mass-withdrawal.md) | withdrawal | unsafe | ✅ | ❌ approved a bad change | ✅ | I2 upstream has customer route; I2 upstream has our aggregate; I3 customer reaches upstream; I5 upstream receives exactly our 2 prefixes |
| `17-default-leaked-to-peer` [default-originate configured toward the peer](corpus/17-default-leaked-to-peer.md) | route-leak | unsafe | ❌ approved a bad change | ❌ approved a bad change | ✅ | I4 no default leaked to peer; I5 peer receives exactly our 2 prefixes |
| `18-redistribute-connected` [redistribute connected added on pe1](corpus/18-redistribute-connected.md) | hygiene | unsafe | ❌ approved a bad change | ❌ approved a bad change | ❌ approved a bad change | nothing |
| `19-nexthop-self-removed` [next-hop-self removed on pe2 toward pe1](corpus/19-nexthop-self-removed.md) | policy-bug | unsafe | ✅ | ❌ approved a bad change | ✅ | I3 customer reaches peer |
| `20-ibgp-shutdown` [iBGP session between pe1 and pe2 shut down](corpus/20-ibgp-shutdown.md) | fat-finger | unsafe | ✅ | ✅ | ✅ | I1 pe1-pe2 iBGP up; I2 peer has customer route; I2 peer has our aggregate; I3 customer has peer route; I3 customer reaches peer; I5 peer receives exactly our 2 prefixes |
| `21-customer-max-prefix-removed` [Customer maximum-prefix safety limit removed](corpus/21-customer-max-prefix-removed.md) | latent-risk | unsafe | ❌ approved a bad change | ❌ approved a bad change | ❌ approved a bad change | nothing |
| `22-customer-leaks-third-party` [Customer announces someone else's prefix; our filter blocks it](corpus/22-customer-leaks-third-party.md) | filter-works | safe | ✅ | ✅ | ✅ | nothing |
| `23-fat-finger-third-party-origin` [pe1 accidentally originates 8.8.8.0/24](corpus/23-fat-finger-third-party-origin.md) | hijack | unsafe | ❌ approved a bad change | ❌ approved a bad change | ❌ approved a bad change | nothing |
| `24-customer-blackholed` [Static discard route for the customer prefix on pe1](corpus/24-customer-blackholed.md) | fat-finger | unsafe | ✅ | ❌ approved a bad change | ✅ | I3 customer reaches upstream; I3 customer reaches peer |
| `25-aggregate-typo` [Aggregate network statement typo (192.0.3.0/24)](corpus/25-aggregate-typo.md) | fat-finger | unsafe | ❌ approved a bad change | ❌ approved a bad change | ✅ | I2 upstream has our aggregate; I2 peer has our aggregate; I5 upstream receives exactly our 2 prefixes; I5 peer receives exactly our 2 prefixes |
| `26-route-map-order-bug` [A permit-everything clause inserted before the peer export filter](corpus/26-route-map-order-bug.md) | route-leak | unsafe | ❌ approved a bad change | ❌ approved a bad change | ✅ | I4 no upstream route leaked to peer; I4 no default leaked to peer; I5 peer receives exactly our 2 prefixes |
| `27-local-asn-typo` [pe2 configured with the wrong local ASN](corpus/27-local-asn-typo.md) | fat-finger | unsafe | ✅ | ✅ | ✅ | I1 pe1-pe2 iBGP up; I1 pe2-peer1 session up; I2 peer has customer route; I2 peer has our aggregate; I3 customer has peer route; I3 customer reaches peer; I4 no upstream route leaked to peer; I4 no default leaked to peer; I5 peer receives exactly our 2 prefixes |
| `28-customer-import-policy-removed` [Customer inbound route-map removed](corpus/28-customer-import-policy-removed.md) | policy-bug | unsafe | ✅ | ❌ approved a bad change | ✅ | I2 upstream has customer route; I2 peer has customer route; I3 customer reaches upstream; I3 customer reaches peer; I5 upstream receives exactly our 2 prefixes; I5 peer receives exactly our 2 prefixes |
| `29-graceful-restart` [Enable BGP graceful restart on pe1](corpus/29-graceful-restart.md) | hygiene | safe | ✅ | ✅ | ✅ | nothing |
| `30-peer-import-filter-removed` [Peer inbound filter replaced with permit-all](corpus/30-peer-import-filter-removed.md) | latent-risk | unsafe | ❌ approved a bad change | ❌ approved a bad change | ❌ approved a bad change | nothing |

## Netdryrun's losses

- **`06-customer-adds-prefix` Customer announces a second allowed /24** (false block). Normal customer growth inside the registered range.
- **`12-ibgp-send-community-dropped` send-community removed on the pe1 to pe2 iBGP session** (false pass). A common mistake when rebuilding iBGP sessions.
- **`18-redistribute-connected` redistribute connected added on pe1** (false pass). Not covered by the intent spec, which has no check for infrastructure routes at the customer.
- **`21-customer-max-prefix-removed` Customer maximum-prefix safety limit removed** (false pass). Latent risk: no steady-state check can see it until the customer actually leaks. Catching it needs a failure-injection scenario (the customer sends many prefixes), planned for a later release.
- **`23-fat-finger-third-party-origin` pe1 accidentally originates 8.8.8.0/24** (false pass). Not covered by the intent spec, which has no check for unexpected routes at the customer.
- **`30-peer-import-filter-removed` Peer inbound filter replaced with permit-all** (false pass). Latent risk: invisible in steady state until the peer misbehaves. Needs a failure-injection scenario.

## Findings after the run

These findings came after the run. The table above is left exactly as pre-registered; nothing in [`corpus/cases/`](https://github.com/netdryrun/Netdryrun/tree/main/corpus/cases) was edited.

**Case 12 was labeled wrong.** The case expected that removing `neighbor 10.0.3.2 send-community` on pe1 stops pe2 from seeing the customer community. In FRR (verified on 10.4.1) communities are sent to every neighbor by default, so deleting the explicit line is a no-op: `show running-config` no longer shows it, but pe1 still advertises `10.100.0.0/24` to pe2 with community `65000:100`, and pe2 still matches it (`show bgp ipv4 unicast community 65000:100` lists the route). Reproduce with `scripts/corpus_case12_verify.sh`. The change is actually safe, so all three strategies answered case 12 correctly. With that one label corrected the scores would be: ping only 21/30, sessions up 16/30, Netdryrun 25/30. The headline numbers stay at the pre-registered values. The mistake would have been real on platforms that do not send communities by default (Cisco IOS, for example); a vendor-specific version of this case belongs in a future corpus.

**Cases 18, 23, 21 and 30 are real misses.** 18 and 23 are gaps in the intent spec (no check for unexpected routes reaching the customer or the upstream). 21 and 30 are latent risks that no steady-state check can see; they need a failure-injection scenario where the customer or peer actually misbehaves. These stay as losses.

<!-- CORPUS-V2 -->

## Corpus v2

The v1 results above are frozen. Corpus v2 is a separate, second run with its own pre-registered cases. It turns v1's misses into things a test can see:

- **Unexpected routes** (v1 cases 18 and 23): the v2 intent spec says infrastructure prefixes and a sentinel list of well-known third-party prefixes must never be BGP routes at the customer, the upstream or the peer. These are `route` checks with `present: false`; no new check type is needed.
- **Latent risks** (v1 cases 21 and 30): two failure scenarios use the [`inject_routes`](reference/config.md#injecting-routes) fault, which ships in Netdryrun 0.3.1, to make a neighbor misbehave. The customer floods 200 more-specifics from its own /16, and the peer announces a more-specific of our customer's space and a third-party /24. The checks then verify that the max-prefix limit and the import filter actually hold.
- **Rigid counts** (v1 case 06): announced-prefix counts are a range (2 to 51), so customer growth inside its block is not blocked.
- **Vendor defaults** (v1 case 12): the FRR no-op is labeled safe, and the genuinely harmful variant is a separate case.

v2 changes two lines in the base lab so the customer's max-prefix limit can actually trip: in v1 the customer filter allowed at most 7 prefixes, so a limit of 100 could never be reached. The differences, the written intent (I1 to I9) and the disclosures are in [v2/INTENT.md](https://github.com/netdryrun/Netdryrun/blob/main/corpus/v2/INTENT.md). The spec is [v2/specs/intent.yml](https://github.com/netdryrun/Netdryrun/blob/main/corpus/v2/specs/intent.yml).

**Pre-registration:** all 18 cases and their expected verdicts were committed and pushed in [`322cc4e`](https://github.com/netdryrun/Netdryrun/commit/322cc4ede21492c3914a0a53b67268bea7abf7d6) (2026-10-27 04:02 UTC), before any v2 case was deployed. Rerun it with `python corpus/run.py --corpus v2`.

Generated 2026-10-27T19:05:43+00:00 with netdryrun 0.3.1, containerlab 0.81.1, FRR quay.io/frrouting/frr:10.4.1, commit `08059de`. Rerun everything with `python corpus/run.py --corpus v2`.

**Conflict of interest:** the Netdryrun maintainers wrote this corpus and the runner. Expected verdicts were committed before any run (see the git history of [`corpus/v2/cases/`](https://github.com/netdryrun/Netdryrun/tree/main/corpus/v2/cases)). Losses are kept and shown at the same size as the catches.

### Summary (17 deterministic cases: 10 harmful, 7 safe; 1 nondeterministic, not scored)

| Strategy | Correct | Harmful changes caught | Approved a bad change | Blocked a good change | Errors |
|---|---|---|---|---|---|
| Ping only | **9/17** | 2/10 | 8 | 0 | 0 |
| All BGP sessions up | **7/17** | 0/10 | 10 | 0 | 0 |
| Netdryrun intent checks | **16/17** | 9/10 | 1 | 0 | 0 |

### Every case

| Case | Category | Expected | Ping only | Sessions up | Netdryrun | What Netdryrun flagged |
|---|---|---|---|---|---|---|
| `01-no-change` [No change (control)](https://github.com/netdryrun/Netdryrun/blob/main/corpus/v2/cases/01-no-change.yml) | control | safe | ✅ | ✅ | ✅ | nothing |
| `02-redistribute-connected-pe2` [redistribute connected added on pe2](https://github.com/netdryrun/Netdryrun/blob/main/corpus/v2/cases/02-redistribute-connected-pe2.yml) | hygiene | unsafe | ❌ approved a bad change | ❌ approved a bad change | ✅ | I6 customer has no BGP route for link 10.0.3.0/30; I6 customer has no BGP route for link 10.0.4.0/30; I6 customer has no BGP route for pe2 loopback |
| `03-test-prefix-left-in-config` [pe1 originates 1.1.1.0/24 left over from a lab test](https://github.com/netdryrun/Netdryrun/blob/main/corpus/v2/cases/03-test-prefix-left-in-config.yml) | hijack | unsafe | ❌ approved a bad change | ❌ approved a bad change | ✅ | I7 customer has no route for 1.1.1.0/24 |
| `04-redundant-aggregate-typo` [Aggregate added on pe2 for redundancy, mistyped as 192.0.12.0/24](https://github.com/netdryrun/Netdryrun/blob/main/corpus/v2/cases/04-redundant-aggregate-typo.yml) | hijack | unsafe | ❌ approved a bad change | ❌ approved a bad change | ❌ approved a bad change | nothing |
| `05-customer-max-prefix-removed` [Customer maximum-prefix safety limit removed](https://github.com/netdryrun/Netdryrun/blob/main/corpus/v2/cases/05-customer-max-prefix-removed.yml) | latent-risk | unsafe | ❌ approved a bad change | ❌ approved a bad change | ✅ | [customer floods 200 prefixes] I8 upstream still receives at most 51 prefixes; [customer floods 200 prefixes] I8 peer still receives at most 51 prefixes |
| `06-peer-import-filter-permit-all` [Peer inbound filter replaced with permit-all](https://github.com/netdryrun/Netdryrun/blob/main/corpus/v2/cases/06-peer-import-filter-permit-all.yml) | latent-risk | unsafe | ❌ approved a bad change | ❌ approved a bad change | ✅ | [peer announces routes it does not own] I9 pe2 accepts only the peer's own prefix; [peer announces routes it does not own] I9 customer gets no hijacking more-specific; [peer announces routes it does not own] I9 pe1 has no third-party route from the peer |
| `07-customer-adds-prefixes` [Customer announces two more /24s from its /16](https://github.com/netdryrun/Netdryrun/blob/main/corpus/v2/cases/07-customer-adds-prefixes.yml) | customer-growth | safe | ✅ | ✅ | ✅ | nothing |
| `08-customer-announces-aggregate` [Customer also announces its covering /16](https://github.com/netdryrun/Netdryrun/blob/main/corpus/v2/cases/08-customer-announces-aggregate.yml) | customer-growth | safe | ✅ | ✅ | ✅ | nothing |
| `09-ibgp-send-community-line-removed` [Explicit send-community line removed on the pe1 to pe2 iBGP session](https://github.com/netdryrun/Netdryrun/blob/main/corpus/v2/cases/09-ibgp-send-community-line-removed.yml) | vendor-default | safe | ✅ | ✅ | ✅ | nothing |
| `10-ibgp-standard-communities-disabled` [Standard communities explicitly disabled on the pe1 to pe2 iBGP session](https://github.com/netdryrun/Netdryrun/blob/main/corpus/v2/cases/10-ibgp-standard-communities-disabled.yml) | policy-bug | unsafe | ✅ | ❌ approved a bad change | ✅ | I2 peer has customer route; I3 customer reaches peer; I5 peer receives 2 to 51 prefixes from us |
| `11-customer-max-prefix-warning-only` [Customer maximum-prefix changed to warning-only](https://github.com/netdryrun/Netdryrun/blob/main/corpus/v2/cases/11-customer-max-prefix-warning-only.yml) | latent-risk | unsafe | ❌ approved a bad change | ❌ approved a bad change | ✅ | [customer floods 200 prefixes] I8 upstream still receives at most 51 prefixes; [customer floods 200 prefixes] I8 peer still receives at most 51 prefixes |
| `12-customer-max-prefix-raised` [Customer maximum-prefix raised from 50 to 100](https://github.com/netdryrun/Netdryrun/blob/main/corpus/v2/cases/12-customer-max-prefix-raised.yml) | hygiene | safe | ✅ | ✅ | ✅ | nothing |
| `13-upstream-routes-tagged-as-customer` [Upstream import policy tags routes with the customer community (copy-paste error)](https://github.com/netdryrun/Netdryrun/blob/main/corpus/v2/cases/13-upstream-routes-tagged-as-customer.yml) | route-leak | unsafe | ❌ approved a bad change | ❌ approved a bad change | ✅ | I4 no upstream route leaked to peer; I4 no default leaked to peer |
| `14-customer-gets-default-only` [Customer export policy restricted to the default route](https://github.com/netdryrun/Netdryrun/blob/main/corpus/v2/cases/14-customer-gets-default-only.yml) | policy-bug | unsafe | ✅ | ❌ approved a bad change | ✅ | I3 customer has upstream route; I3 customer has peer route; I3 customer reaches upstream; I3 customer reaches peer |
| `15-upstream-default-filtered` [Default route from the upstream filtered on import](https://github.com/netdryrun/Netdryrun/blob/main/corpus/v2/cases/15-upstream-default-filtered.yml) | policy-bug | unsafe | ❌ approved a bad change | ❌ approved a bad change | ✅ | I3 customer has default |
| `16-customer-session-peer-group` [Customer session moved into a CUSTOMERS peer-group](https://github.com/netdryrun/Netdryrun/blob/main/corpus/v2/cases/16-customer-session-peer-group.yml) | refactor | safe | ✅ | ✅ | ✅ | nothing |
| `17-customer-region-community` [Add an informational region community to customer routes](https://github.com/netdryrun/Netdryrun/blob/main/corpus/v2/cases/17-customer-region-community.yml) | hygiene | safe | ✅ | ✅ | ✅ | nothing |
| `18-aggregate-discard-route-removed` [Discard route for our aggregate deleted as unused](https://github.com/netdryrun/Netdryrun/blob/main/corpus/v2/cases/18-aggregate-discard-route-removed.yml) | hygiene | unsafe | 🎲 not scored | 🎲 not scored | 🎲 not scored | nondeterministic in this lab: see below |

### Nondeterministic cases (not scored)

Same build, same machine, same case, different verdicts: the verdict follows a race in the lab, not the change. These cases are left out of every score above and listed here with every Netdryrun verdict seen. The case files and expected verdicts are unchanged; the list is in `corpus/v2/NONDETERMINISTIC.yml`.

- **`18-aggregate-discard-route-removed` Discard route for our aggregate deleted as unused** (expected unsafe). With the discard route for 192.0.2.0/24 deleted, FRR's BGP import check (enabled: the path shows "inaccessible, import-check enabled") sometimes withholds the aggregate and sometimes announces it. Withheld, the upstream and the peer lose it and the intent checks (I2, I5) fail; announced, they pass, and the harm left is the routing loop for unused addresses in the aggregate, which no check probes. Same build, same machine, same case: different verdicts. Netdryrun verdicts: 2026-10-27, first v2 run, development build before 0.3.1: **safe**; 2026-10-27, 0.3.1 release gate rerun (the committed results.json): **unsafe**; 2026-10-29, 0.3.3 release gate, build ada4dd0: **safe**; 2026-10-29, rerun 1 of 3, build ada4dd0: **unsafe**; 2026-10-29, rerun 2 of 3, build ada4dd0: **unsafe**; 2026-10-29, rerun 3 of 3, build ada4dd0: **safe**.

### Netdryrun's losses

- **`04-redundant-aggregate-typo` Aggregate added on pe2 for redundancy, mistyped as 192.0.12.0/24** (false pass). Expected to be missed. I7 only spot-checks a few well-known prefixes, and nothing bounds what the customer receives.

### Findings after the run

These findings came after the v2 run. The table above is left exactly as pre-registered in commit `322cc4e`; nothing in [`corpus/v2/cases/`](https://github.com/netdryrun/Netdryrun/tree/main/corpus/v2/cases) was edited.

**Run provenance.** `results.json` records the commit as `unknown`: the run used git inside WSL on a Windows git worktree, and that git could not read the worktree. The run started at 04:02:42 UTC, 16 seconds after the pre-registration commit `322cc4e`. `src/` and `corpus/run.py` were not changed during the run. The renderer, the docs and the unit tests were edited during the run, and none of them affect verdicts.

**Case 04 is a real miss, as predicted.** pe2 announced the mistyped 192.0.12.0/24 to pe1 and on to the customer, and no check looked for it. I7 only spot-checks a few well-known prefixes, and nothing bounds what the customer receives. Catching this class needs a check that the customer receives only routes from known origins, or only expected prefixes from our own AS. No such check type exists yet.

**Case 18 is a real miss.** ~~With the discard route deleted, FRR (traditional defaults, no `bgp network import-check`) kept announcing 192.0.2.0/24, so I2 passed.~~ *Corrected 2026-10-29: in this run FRR kept announcing 192.0.2.0/24, so I2 passed. But FRR's import check is enabled in this lab, and whether it withholds the aggregate is a race: see the last paragraph.* The harm is the routing loop for unused addresses inside the aggregate, which no check probes. A `ping` with `expect: failure` to an unused address in 192.0.2.0/24 from the upstream would not show the loop either, because ping fails both with and without it. Catching it needs a path or traceroute check (TTL exceeded versus a clean discard).

**Ping only's catch of case 14 is partly a lab artifact.** In the lab, the customer's BGP default is not active, because containerlab's management default route outranks it (the spec checks the default with `active: false` for this reason). Once the customer lost its specific routes, its pings had no path at all. A real customer with a working default would still ping, and the ping baseline would pass the change. The result stays as measured.

**Rerun on the released 0.3.1 (2026-10-27, by the release gate):** every verdict matches the first run except case 18 (`18-aggregate-discard-route-removed`). The development build approved it; 0.3.1 rejects it, which is the pre-registered expected verdict, because the upstream and the peer no longer receive the aggregate (checks I2 and I5 fail). ~~0.3.1 changed how routes are read (received paths count, errors are never read as "no routes"), and this case was one of v2's two misses. Netdryrun is now 17/18 on v2.~~ *Corrected 2026-10-29: 0.3.1 did not cause the flip, and 17/18 overstated the result: see the next paragraph.* The cases and the expected verdicts are unchanged.

**Case 18 is nondeterministic in this lab (found 2026-10-29 by the 0.3.3 release gate).** The 0.3.3 gate's rerun approved it again. Three more runs of the same build on the same machine gave unsafe, unsafe, safe. FRR's BGP import check is enabled (the path reads "inaccessible, import-check enabled"), and with the discard route gone it sometimes withholds the aggregate and sometimes announces it. The verdict follows that race, not Netdryrun's code. From 0.3.3 the case is listed in `NONDETERMINISTIC.yml` with every verdict seen. It is left out of the score: v2 is **16 of 17 deterministic cases correct**. The release gate runs it three times, records the verdicts and never blocks on them; a verdict change on any other case still blocks a release. A replacement with the same intent and the race removed goes into a later corpus version, its expected verdict committed before it runs. This case file and its expected verdict are not edited.
