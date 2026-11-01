---
title: "next-hop-self removed on pe2 toward pe1: BGP change test (case 19)"
description: "next-hop-self removed on pe2 toward pe1. Expected unsafe: pe1 learns the peer route with an unreachable next hop, so the customer loses the peer route."
---

# next-hop-self removed on pe2 toward pe1

Case 19 of the [Network Change Verdict Corpus](../corpus.md). Category: **policy-bug**. Expected verdict: **unsafe** (an experienced operator would reject it).

## Why it is expected unsafe

pe1 learns the peer route with an unreachable next hop, so the customer loses the peer route.

## The config change

Against the FRR configs of the [base lab](https://github.com/netdryrun/Netdryrun/tree/main/corpus/base/configs):

```diff
--- a/pe2.conf
+++ b/pe2.conf
@@ -35,7 +35,6 @@
  neighbor 10.0.4.2 remote-as 65300
  neighbor 10.0.4.2 description peer1
  address-family ipv4 unicast
-  neighbor 10.0.3.1 next-hop-self
   neighbor 10.0.3.1 send-community
   neighbor 10.0.4.2 route-map FROM-PEER in
   neighbor 10.0.4.2 route-map TO-PEER out
```

## What each strategy said

The expected verdict was committed to git before any run. All three strategies tested the same running lab ([method](../corpus.md#method)).

| Strategy | Verdict | Result | Checks that failed |
|---|---|---|---|
| Ping only | unsafe | ✅ | customer reaches peer |
| All BGP sessions up | safe | ❌ approved a bad change | none |
| Netdryrun intent checks | unsafe | ✅ | I3 customer reaches peer |

## What Netdryrun flagged

These checks from the [intent spec](https://github.com/netdryrun/Netdryrun/blob/main/corpus/specs/intent.yml) failed:

- **I3 customer reaches peer**: ce1 can ping 198.51.100.1 from 10.100.0.1

## Reproduce it

On Linux or WSL2 with Docker and containerlab, from a checkout of the repository:

```bash
python corpus/run.py --case 19
```

Case file: [`corpus/cases/19-nexthop-self-removed.yml`](https://github.com/netdryrun/Netdryrun/blob/main/corpus/cases/19-nexthop-self-removed.yml). Published result: netdryrun 0.3.1, containerlab 0.81.1, FRR `quay.io/frrouting/frr:10.4.1`, commit `08059de`, run on 2026-10-27.
