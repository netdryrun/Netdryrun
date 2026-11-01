---
title: "Customer inbound route-map removed: BGP change test (case 28)"
description: "Customer inbound route-map removed. Expected unsafe: Without the import policy the customer's routes lose their community (or are rejected outright), so..."
---

# Customer inbound route-map removed

Case 28 of the [Network Change Verdict Corpus](../corpus.md). Category: **policy-bug**. Expected verdict: **unsafe** (an experienced operator would reject it).

## Why it is expected unsafe

Without the import policy the customer's routes lose their community (or are rejected outright), so they are no longer exported upstream.

## The config change

Against the FRR configs of the [base lab](https://github.com/netdryrun/Netdryrun/tree/main/corpus/base/configs):

```diff
--- a/pe1.conf
+++ b/pe1.conf
@@ -51,7 +51,6 @@
  neighbor 10.0.3.2 description pe2
  address-family ipv4 unicast
   network 192.0.2.0/24
-  neighbor 10.0.1.2 route-map FROM-CUSTOMER in
   neighbor 10.0.1.2 route-map TO-CUSTOMER out
   neighbor 10.0.1.2 maximum-prefix 100
   neighbor 10.0.2.2 route-map FROM-UPSTREAM in
```

## What each strategy said

The expected verdict was committed to git before any run. All three strategies tested the same running lab ([method](../corpus.md#method)).

| Strategy | Verdict | Result | Checks that failed |
|---|---|---|---|
| Ping only | unsafe | ✅ | customer reaches upstream, customer reaches peer |
| All BGP sessions up | safe | ❌ approved a bad change | none |
| Netdryrun intent checks | unsafe | ✅ | I2 upstream has customer route, I2 peer has customer route, I3 customer reaches upstream, I3 customer reaches peer, I5 upstream receives exactly our 2 prefixes, I5 peer receives exactly our 2 prefixes |

## What Netdryrun flagged

These checks from the [intent spec](https://github.com/netdryrun/Netdryrun/blob/main/corpus/specs/intent.yml) failed:

- **I2 upstream has customer route**: 10.100.0.0/24 must be in up1's routing table as a bgp route
- **I2 peer has customer route**: 10.100.0.0/24 must be in peer1's routing table as a bgp route
- **I3 customer reaches upstream**: ce1 can ping 203.0.113.1 from 10.100.0.1
- **I3 customer reaches peer**: ce1 can ping 198.51.100.1 from 10.100.0.1
- **I5 upstream receives exactly our 2 prefixes**: up1 receives exactly 2 prefixes from 10.0.2.1
- **I5 peer receives exactly our 2 prefixes**: peer1 receives exactly 2 prefixes from 10.0.4.1

## Reproduce it

On Linux or WSL2 with Docker and containerlab, from a checkout of the repository:

```bash
python corpus/run.py --case 28
```

Case file: [`corpus/cases/28-customer-import-policy-removed.yml`](https://github.com/netdryrun/Netdryrun/blob/main/corpus/cases/28-customer-import-policy-removed.yml). Published result: netdryrun 0.3.1, containerlab 0.81.1, FRR `quay.io/frrouting/frr:10.4.1`, commit `08059de`, run on 2026-10-27.
