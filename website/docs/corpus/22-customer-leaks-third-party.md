---
title: "Customer announces someone else's prefix; our filter blocks it: BGP change test (case 22)"
description: "Customer announces someone else's prefix; our filter blocks it. Expected safe: ce1 starts announcing 8.8.8.0/24. pe1's customer filter rejects it, so..."
---

# Customer announces someone else's prefix; our filter blocks it

Case 22 of the [Network Change Verdict Corpus](../corpus.md). Category: **filter-works**. Expected verdict: **safe** (an experienced operator would approve it).

## Why it is expected safe

ce1 starts announcing 8.8.8.0/24. pe1's customer filter rejects it, so nothing leaks. The customer-side change is bad, but our network behaves correctly, so a test of our network must pass.

## The config change

Against the FRR configs of the [base lab](https://github.com/netdryrun/Netdryrun/tree/main/corpus/base/configs):

```diff
--- a/ce1.conf
+++ b/ce1.conf
@@ -18,3 +18,9 @@
   neighbor 10.0.1.1 route-map ALLOW-ALL out
  exit-address-family
 !
+ip route 8.8.8.0/24 blackhole
+router bgp 65100
+ address-family ipv4 unicast
+  network 8.8.8.0/24
+ exit-address-family
+!
```

## What each strategy said

The expected verdict was committed to git before any run. All three strategies tested the same running lab ([method](../corpus.md#method)).

| Strategy | Verdict | Result | Checks that failed |
|---|---|---|---|
| Ping only | safe | ✅ | none |
| All BGP sessions up | safe | ✅ | none |
| Netdryrun intent checks | safe | ✅ | none |

## What Netdryrun flagged

Nothing: every check in the [intent spec](https://github.com/netdryrun/Netdryrun/blob/main/corpus/specs/intent.yml) passed, so Netdryrun called the change safe.

## Reproduce it

On Linux or WSL2 with Docker and containerlab, from a checkout of the repository:

```bash
python corpus/run.py --case 22
```

Case file: [`corpus/cases/22-customer-leaks-third-party.yml`](https://github.com/netdryrun/Netdryrun/blob/main/corpus/cases/22-customer-leaks-third-party.yml). Published result: netdryrun 0.3.1, containerlab 0.81.1, FRR `quay.io/frrouting/frr:10.4.1`, commit `08059de`, run on 2026-10-27.
