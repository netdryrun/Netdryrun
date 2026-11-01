---
title: "Customer announces a second allowed /24: BGP change test (case 6)"
description: "Customer announces a second allowed /24. Expected safe: The customer adds 10.100.1.0/24, inside its registered 10.100.0.0/22. Announcing it upstream is the..."
---

# Customer announces a second allowed /24

Case 6 of the [Network Change Verdict Corpus](../corpus.md). Category: **customer-growth**. Expected verdict: **safe** (an experienced operator would approve it).

## Why it is expected safe

The customer adds 10.100.1.0/24, inside its registered 10.100.0.0/22. Announcing it upstream is the desired outcome.

Note: Normal customer growth inside the registered range.

## The config change

Against the FRR configs of the [base lab](https://github.com/netdryrun/Netdryrun/tree/main/corpus/base/configs):

```diff
--- a/ce1.conf
+++ b/ce1.conf
@@ -18,3 +18,9 @@
   neighbor 10.0.1.1 route-map ALLOW-ALL out
  exit-address-family
 !
+ip route 10.100.1.0/24 blackhole
+router bgp 65100
+ address-family ipv4 unicast
+  network 10.100.1.0/24
+ exit-address-family
+!
```

## What each strategy said

The expected verdict was committed to git before any run. All three strategies tested the same running lab ([method](../corpus.md#method)).

| Strategy | Verdict | Result | Checks that failed |
|---|---|---|---|
| Ping only | safe | ✅ | none |
| All BGP sessions up | safe | ✅ | none |
| Netdryrun intent checks | unsafe | ⚠️ blocked a good change | I5 upstream receives exactly our 2 prefixes, I5 peer receives exactly our 2 prefixes |

## What Netdryrun flagged

These checks from the [intent spec](https://github.com/netdryrun/Netdryrun/blob/main/corpus/specs/intent.yml) failed:

- **I5 upstream receives exactly our 2 prefixes**: up1 receives exactly 2 prefixes from 10.0.2.1
- **I5 peer receives exactly our 2 prefixes**: peer1 receives exactly 2 prefixes from 10.0.4.1

Against the pre-registered verdict this counts as one of Netdryrun's losses (false block).

## Reproduce it

On Linux or WSL2 with Docker and containerlab, from a checkout of the repository:

```bash
python corpus/run.py --case 06
```

Case file: [`corpus/cases/06-customer-adds-prefix.yml`](https://github.com/netdryrun/Netdryrun/blob/main/corpus/cases/06-customer-adds-prefix.yml). Published result: netdryrun 0.3.1, containerlab 0.81.1, FRR `quay.io/frrouting/frr:10.4.1`, commit `08059de`, run on 2026-10-27.
