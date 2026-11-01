---
title: "Upstream export filter replaced with permit-all: BGP change test (case 10)"
description: "Upstream export filter replaced with permit-all. Expected unsafe: pe1 now announces everything to the upstream, including the peer's route: free transit for..."
---

# Upstream export filter replaced with permit-all

Case 10 of the [Network Change Verdict Corpus](../corpus.md). Category: **route-leak**. Expected verdict: **unsafe** (an experienced operator would reject it).

## Why it is expected unsafe

pe1 now announces everything to the upstream, including the peer's route: free transit for the peer, a classic route leak.

Note: Route leak as defined in RFC 7908.

## The config change

Against the FRR configs of the [base lab](https://github.com/netdryrun/Netdryrun/tree/main/corpus/base/configs):

```diff
--- a/pe1.conf
+++ b/pe1.conf
@@ -55,7 +55,7 @@
   neighbor 10.0.1.2 route-map TO-CUSTOMER out
   neighbor 10.0.1.2 maximum-prefix 100
   neighbor 10.0.2.2 route-map FROM-UPSTREAM in
-  neighbor 10.0.2.2 route-map TO-UPSTREAM out
+  neighbor 10.0.2.2 route-map TO-CUSTOMER out
   neighbor 10.0.3.2 next-hop-self
   neighbor 10.0.3.2 send-community
  exit-address-family
```

## What each strategy said

The expected verdict was committed to git before any run. All three strategies tested the same running lab ([method](../corpus.md#method)).

| Strategy | Verdict | Result | Checks that failed |
|---|---|---|---|
| Ping only | safe | ❌ approved a bad change | none |
| All BGP sessions up | safe | ❌ approved a bad change | none |
| Netdryrun intent checks | unsafe | ✅ | I4 no peer route leaked to upstream, I5 upstream receives exactly our 2 prefixes |

## What Netdryrun flagged

These checks from the [intent spec](https://github.com/netdryrun/Netdryrun/blob/main/corpus/specs/intent.yml) failed:

- **I4 no peer route leaked to upstream**: 198.51.100.0/24 must not be in up1's routing table as a bgp route
- **I5 upstream receives exactly our 2 prefixes**: up1 receives exactly 2 prefixes from 10.0.2.1

## Reproduce it

On Linux or WSL2 with Docker and containerlab, from a checkout of the repository:

```bash
python corpus/run.py --case 10
```

Case file: [`corpus/cases/10-transit-export-filter-removed.yml`](https://github.com/netdryrun/Netdryrun/blob/main/corpus/cases/10-transit-export-filter-removed.yml). Published result: netdryrun 0.3.1, containerlab 0.81.1, FRR `quay.io/frrouting/frr:10.4.1`, commit `08059de`, run on 2026-10-27.
