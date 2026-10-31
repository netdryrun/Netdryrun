---
title: "Peer export filter replaced with permit-all: BGP change test (case 11)"
description: "Peer export filter replaced with permit-all. Expected unsafe: pe2 announces upstream routes and the default to the peer: a route leak toward the peer."
---

# Peer export filter replaced with permit-all

Case 11 of the [Network Change Verdict Corpus](../corpus.md). Category: **route-leak**. Expected verdict: **unsafe** (an experienced operator would reject it).

## Why it is expected unsafe

pe2 announces upstream routes and the default to the peer: a route leak toward the peer.

Note: Route leak as defined in RFC 7908.

## The config change

Against the FRR configs of the [base lab](https://github.com/netdryrun/Netdryrun/tree/main/corpus/base/configs):

```diff
--- a/pe2.conf
+++ b/pe2.conf
@@ -38,6 +38,8 @@
   neighbor 10.0.3.1 next-hop-self
   neighbor 10.0.3.1 send-community
   neighbor 10.0.4.2 route-map FROM-PEER in
-  neighbor 10.0.4.2 route-map TO-PEER out
+  neighbor 10.0.4.2 route-map ALLOW-ALL out
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
| Netdryrun intent checks | unsafe | ✅ | I4 no upstream route leaked to peer, I4 no default leaked to peer, I5 peer receives exactly our 2 prefixes |

## What Netdryrun flagged

These checks from the [intent spec](https://github.com/netdryrun/Netdryrun/blob/main/corpus/specs/intent.yml) failed:

- **I4 no upstream route leaked to peer**: 203.0.113.0/24 must not be in peer1's routing table as a bgp route
- **I4 no default leaked to peer**: 0.0.0.0/0 must not be in peer1's routing table as a bgp route
- **I5 peer receives exactly our 2 prefixes**: peer1 receives exactly 2 prefixes from 10.0.4.1

## Reproduce it

On Linux or WSL2 with Docker and containerlab, from a checkout of the repository:

```bash
python corpus/run.py --case 11
```

Case file: [`corpus/cases/11-peer-export-filter-removed.yml`](https://github.com/netdryrun/Netdryrun/blob/main/corpus/cases/11-peer-export-filter-removed.yml). Published result: netdryrun 0.3.1, containerlab 0.81.1, FRR `quay.io/frrouting/frr:10.4.1`, commit `08059de`, run on 2026-10-27.
