---
title: "redistribute connected added on pe1: BGP change test (case 18)"
description: "redistribute connected added on pe1. Expected unsafe: Infrastructure /30s and loopbacks go to the customer and into iBGP. Export filters keep them from the..."
---

# redistribute connected added on pe1

Case 18 of the [Network Change Verdict Corpus](../corpus.md). Category: **hygiene**. Expected verdict: **unsafe** (an experienced operator would reject it).

## Why it is expected unsafe

Infrastructure /30s and loopbacks go to the customer and into iBGP. Export filters keep them from the upstream and the peer, but leaking infrastructure to customers is rejected in review.

Note: Not covered by the intent spec, which has no check for infrastructure routes at the customer.

## The config change

Against the FRR configs of the [base lab](https://github.com/netdryrun/Netdryrun/tree/main/corpus/base/configs):

```diff
--- a/pe1.conf
+++ b/pe1.conf
@@ -60,3 +60,8 @@
   neighbor 10.0.3.2 send-community
  exit-address-family
 !
+router bgp 65000
+ address-family ipv4 unicast
+  redistribute connected
+ exit-address-family
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
python corpus/run.py --case 18
```

Case file: [`corpus/cases/18-redistribute-connected.yml`](https://github.com/netdryrun/Netdryrun/blob/main/corpus/cases/18-redistribute-connected.yml). Published result: netdryrun 0.3.1, containerlab 0.81.1, FRR `quay.io/frrouting/frr:10.4.1`, commit `08059de`, run on 2026-10-27.
