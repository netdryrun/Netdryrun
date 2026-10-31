---
title: "Static discard route for the customer prefix on pe1: BGP change test (case 24)"
description: "Static discard route for the customer prefix on pe1. Expected unsafe: The static route beats BGP, so traffic to the customer is dropped while the route is..."
---

# Static discard route for the customer prefix on pe1

Case 24 of the [Network Change Verdict Corpus](../corpus.md). Category: **fat-finger**. Expected verdict: **unsafe** (an experienced operator would reject it).

## Why it is expected unsafe

The static route beats BGP, so traffic to the customer is dropped while the route is still announced.

## The config change

Against the FRR configs of the [base lab](https://github.com/netdryrun/Netdryrun/tree/main/corpus/base/configs):

```diff
--- a/pe1.conf
+++ b/pe1.conf
@@ -18,6 +18,7 @@
 !
 ! Our own aggregate, originated from a discard route
 ip route 192.0.2.0/24 blackhole
+ip route 10.100.0.0/24 blackhole
 !
 ip prefix-list OWN seq 10 permit 192.0.2.0/24
 ip prefix-list CUSTOMER-IN seq 10 permit 10.100.0.0/22 le 24
```

## What each strategy said

The expected verdict was committed to git before any run. All three strategies tested the same running lab ([method](../corpus.md#method)).

| Strategy | Verdict | Result | Checks that failed |
|---|---|---|---|
| Ping only | unsafe | ✅ | customer reaches upstream, customer reaches peer |
| All BGP sessions up | safe | ❌ approved a bad change | none |
| Netdryrun intent checks | unsafe | ✅ | I3 customer reaches upstream, I3 customer reaches peer |

## What Netdryrun flagged

These checks from the [intent spec](https://github.com/netdryrun/Netdryrun/blob/main/corpus/specs/intent.yml) failed:

- **I3 customer reaches upstream**: ce1 can ping 203.0.113.1 from 10.100.0.1
- **I3 customer reaches peer**: ce1 can ping 198.51.100.1 from 10.100.0.1

## Reproduce it

On Linux or WSL2 with Docker and containerlab, from a checkout of the repository:

```bash
python corpus/run.py --case 24
```

Case file: [`corpus/cases/24-customer-blackholed.yml`](https://github.com/netdryrun/Netdryrun/blob/main/corpus/cases/24-customer-blackholed.yml). Published result: netdryrun 0.3.1, containerlab 0.81.1, FRR `quay.io/frrouting/frr:10.4.1`, commit `08059de`, run on 2026-10-27.
