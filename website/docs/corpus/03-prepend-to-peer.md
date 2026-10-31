---
title: "Prepend our AS twice toward the peer: BGP change test (case 3)"
description: "Prepend our AS twice toward the peer. Expected safe: Routine inbound traffic engineering. The same prefixes are still announced."
---

# Prepend our AS twice toward the peer

Case 3 of the [Network Change Verdict Corpus](../corpus.md). Category: **traffic-engineering**. Expected verdict: **safe** (an experienced operator would approve it).

## Why it is expected safe

Routine inbound traffic engineering. The same prefixes are still announced.

## The config change

Against the FRR configs of the [base lab](https://github.com/netdryrun/Netdryrun/tree/main/corpus/base/configs):

```diff
--- a/pe2.conf
+++ b/pe2.conf
@@ -41,3 +41,6 @@
   neighbor 10.0.4.2 route-map TO-PEER out
  exit-address-family
 !
+route-map TO-PEER permit 10
+ set as-path prepend 65000 65000
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
python corpus/run.py --case 03
```

Case file: [`corpus/cases/03-prepend-to-peer.yml`](https://github.com/netdryrun/Netdryrun/blob/main/corpus/cases/03-prepend-to-peer.yml). Published result: netdryrun 0.3.1, containerlab 0.81.1, FRR `quay.io/frrouting/frr:10.4.1`, commit `08059de`, run on 2026-10-27.
