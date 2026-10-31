---
title: "Customer maximum-prefix safety limit removed: BGP change test (case 21)"
description: "Customer maximum-prefix safety limit removed. Expected unsafe: Nothing changes today, but a customer leaking a full table would now be accepted. Reviewers..."
---

# Customer maximum-prefix safety limit removed

Case 21 of the [Network Change Verdict Corpus](../corpus.md). Category: **latent-risk**. Expected verdict: **unsafe** (an experienced operator would reject it).

## Why it is expected unsafe

Nothing changes today, but a customer leaking a full table would now be accepted. Reviewers reject removing safety limits.

Note: Latent risk: no steady-state check can see it until the customer actually leaks. Catching it needs a failure-injection scenario (the customer sends many prefixes), planned for a later release.

## The config change

Against the FRR configs of the [base lab](https://github.com/netdryrun/Netdryrun/tree/main/corpus/base/configs):

```diff
--- a/pe1.conf
+++ b/pe1.conf
@@ -53,7 +53,6 @@
   network 192.0.2.0/24
   neighbor 10.0.1.2 route-map FROM-CUSTOMER in
   neighbor 10.0.1.2 route-map TO-CUSTOMER out
-  neighbor 10.0.1.2 maximum-prefix 100
   neighbor 10.0.2.2 route-map FROM-UPSTREAM in
   neighbor 10.0.2.2 route-map TO-UPSTREAM out
   neighbor 10.0.3.2 next-hop-self
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
python corpus/run.py --case 21
```

Case file: [`corpus/cases/21-customer-max-prefix-removed.yml`](https://github.com/netdryrun/Netdryrun/blob/main/corpus/cases/21-customer-max-prefix-removed.yml). Published result: netdryrun 0.3.1, containerlab 0.81.1, FRR `quay.io/frrouting/frr:10.4.1`, commit `08059de`, run on 2026-10-27.
