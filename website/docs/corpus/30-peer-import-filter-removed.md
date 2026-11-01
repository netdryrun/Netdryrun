---
title: "Peer inbound filter replaced with permit-all: BGP change test (case 30)"
description: "Peer inbound filter replaced with permit-all. Expected unsafe: Nothing changes today because the peer only sends its /24, but the peer could now send a..."
---

# Peer inbound filter replaced with permit-all

Case 30 of the [Network Change Verdict Corpus](../corpus.md). Category: **latent-risk**. Expected verdict: **unsafe** (an experienced operator would reject it).

## Why it is expected unsafe

Nothing changes today because the peer only sends its /24, but the peer could now send a default or bogons. Reviewers reject removing an import filter.

Note: Latent risk: invisible in steady state until the peer misbehaves. Needs a failure-injection scenario.

## The config change

Against the FRR configs of the [base lab](https://github.com/netdryrun/Netdryrun/tree/main/corpus/base/configs):

```diff
--- a/pe2.conf
+++ b/pe2.conf
@@ -37,7 +37,9 @@
  address-family ipv4 unicast
   neighbor 10.0.3.1 next-hop-self
   neighbor 10.0.3.1 send-community
-  neighbor 10.0.4.2 route-map FROM-PEER in
+  neighbor 10.0.4.2 route-map ALLOW-ALL in
   neighbor 10.0.4.2 route-map TO-PEER out
  exit-address-family
 !
+route-map ALLOW-ALL permit 10
+!
```

## What each strategy said

The expected verdict was committed to git before any run. All three strategies tested the same running lab ([method](../corpus.md#method)).

| Strategy | Verdict | Result | Checks that failed |
|---|---|---|---|
| Ping only | safe | ❌ approved a bad change | none |
| All BGP sessions up | safe | ❌ approved a bad change | none |
| Netdryrun intent checks | safe | ❌ approved a bad change | none |

## What Netdryrun flagged

Nothing: every check in the [intent spec](https://github.com/netdryrun/Netdryrun/blob/main/corpus/specs/intent.yml) passed, so Netdryrun called the change safe.

Against the pre-registered verdict this counts as one of Netdryrun's losses (false pass).

## Finding after the run

The pre-registered verdict above is unchanged. From [AMENDMENTS.md](https://github.com/netdryrun/Netdryrun/blob/main/corpus/AMENDMENTS.md):

**Cases 18, 23, 21 and 30 are real misses.** 18 and 23 are gaps in the intent spec (no check for unexpected routes reaching the customer or the upstream). 21 and 30 are latent risks that no steady-state check can see; they need a failure-injection scenario where the customer or peer actually misbehaves. These stay as losses.

## Reproduce it

On Linux or WSL2 with Docker and containerlab, from a checkout of the repository:

```bash
python corpus/run.py --case 30
```

Case file: [`corpus/cases/30-peer-import-filter-removed.yml`](https://github.com/netdryrun/Netdryrun/blob/main/corpus/cases/30-peer-import-filter-removed.yml). Published result: netdryrun 0.3.1, containerlab 0.81.1, FRR `quay.io/frrouting/frr:10.4.1`, commit `08059de`, run on 2026-10-27.
