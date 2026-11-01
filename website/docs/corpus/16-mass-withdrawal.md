---
title: "Upstream export policy denies everything: BGP change test (case 16)"
description: "Upstream export policy denies everything. Expected unsafe: Every route we announce to the upstream is withdrawn: our aggregate and the customer vanish from..."
---

# Upstream export policy denies everything

Case 16 of the [Network Change Verdict Corpus](../corpus.md). Category: **withdrawal**. Expected verdict: **unsafe** (an experienced operator would reject it).

## Why it is expected unsafe

Every route we announce to the upstream is withdrawn: our aggregate and the customer vanish from the upstream.

Note: Mass-withdrawal outage class (the 2021 Facebook outage began with withdrawn routes).

## The config change

Against the FRR configs of the [base lab](https://github.com/netdryrun/Netdryrun/tree/main/corpus/base/configs):

```diff
--- a/pe1.conf
+++ b/pe1.conf
@@ -33,11 +33,7 @@
  set community 65000:200
  set local-preference 100
 !
-route-map TO-UPSTREAM permit 10
- match community CUSTOMER
-!
-route-map TO-UPSTREAM permit 20
- match ip address prefix-list OWN
+route-map TO-UPSTREAM deny 10
 !
 route-map TO-CUSTOMER permit 10
 !
```

## What each strategy said

The expected verdict was committed to git before any run. All three strategies tested the same running lab ([method](../corpus.md#method)).

| Strategy | Verdict | Result | Checks that failed |
|---|---|---|---|
| Ping only | unsafe | ✅ | customer reaches upstream |
| All BGP sessions up | safe | ❌ approved a bad change | none |
| Netdryrun intent checks | unsafe | ✅ | I2 upstream has customer route, I2 upstream has our aggregate, I3 customer reaches upstream, I5 upstream receives exactly our 2 prefixes |

## What Netdryrun flagged

These checks from the [intent spec](https://github.com/netdryrun/Netdryrun/blob/main/corpus/specs/intent.yml) failed:

- **I2 upstream has customer route**: 10.100.0.0/24 must be in up1's routing table as a bgp route
- **I2 upstream has our aggregate**: 192.0.2.0/24 must be in up1's routing table as a bgp route
- **I3 customer reaches upstream**: ce1 can ping 203.0.113.1 from 10.100.0.1
- **I5 upstream receives exactly our 2 prefixes**: up1 receives exactly 2 prefixes from 10.0.2.1

## Reproduce it

On Linux or WSL2 with Docker and containerlab, from a checkout of the repository:

```bash
python corpus/run.py --case 16
```

Case file: [`corpus/cases/16-mass-withdrawal.yml`](https://github.com/netdryrun/Netdryrun/blob/main/corpus/cases/16-mass-withdrawal.yml). Published result: netdryrun 0.3.1, containerlab 0.81.1, FRR `quay.io/frrouting/frr:10.4.1`, commit `08059de`, run on 2026-10-27.
