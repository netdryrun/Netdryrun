---
title: "default-originate configured toward the peer: BGP change test (case 17)"
description: "default-originate configured toward the peer. Expected unsafe: We offer the peer a default route, so the peer can send all its traffic through us for free."
---

# default-originate configured toward the peer

Case 17 of the [Network Change Verdict Corpus](../corpus.md). Category: **route-leak**. Expected verdict: **unsafe** (an experienced operator would reject it).

## Why it is expected unsafe

We offer the peer a default route, so the peer can send all its traffic through us for free.

## The config change

Against the FRR configs of the [base lab](https://github.com/netdryrun/Netdryrun/tree/main/corpus/base/configs):

```diff
--- a/pe2.conf
+++ b/pe2.conf
@@ -41,3 +41,8 @@
   neighbor 10.0.4.2 route-map TO-PEER out
  exit-address-family
 !
+router bgp 65000
+ address-family ipv4 unicast
+  neighbor 10.0.4.2 default-originate
+ exit-address-family
+!
```

## What each strategy said

The expected verdict was committed to git before any run. All three strategies tested the same running lab ([method](../corpus.md#method)).

| Strategy | Verdict | Result | Checks that failed |
|---|---|---|---|
| Ping only | safe | ❌ approved a bad change | none |
| All BGP sessions up | safe | ❌ approved a bad change | none |
| Netdryrun intent checks | unsafe | ✅ | I4 no default leaked to peer, I5 peer receives exactly our 2 prefixes |

## What Netdryrun flagged

These checks from the [intent spec](https://github.com/netdryrun/Netdryrun/blob/main/corpus/specs/intent.yml) failed:

- **I4 no default leaked to peer**: 0.0.0.0/0 must not be in peer1's routing table as a bgp route
- **I5 peer receives exactly our 2 prefixes**: peer1 receives exactly 2 prefixes from 10.0.4.1

## Reproduce it

On Linux or WSL2 with Docker and containerlab, from a checkout of the repository:

```bash
python corpus/run.py --case 17
```

Case file: [`corpus/cases/17-default-leaked-to-peer.yml`](https://github.com/netdryrun/Netdryrun/blob/main/corpus/cases/17-default-leaked-to-peer.yml). Published result: netdryrun 0.3.1, containerlab 0.81.1, FRR `quay.io/frrouting/frr:10.4.1`, commit `08059de`, run on 2026-10-27.
