---
title: "Lower the customer maximum-prefix from 100 to 50: BGP change test (case 7)"
description: "Lower the customer maximum-prefix from 100 to 50. Expected safe: Tightening a safety limit that is still far above the customer's real count."
---

# Lower the customer maximum-prefix from 100 to 50

Case 7 of the [Network Change Verdict Corpus](../corpus.md). Category: **hygiene**. Expected verdict: **safe** (an experienced operator would approve it).

## Why it is expected safe

Tightening a safety limit that is still far above the customer's real count.

## The config change

Against the FRR configs of the [base lab](https://github.com/netdryrun/Netdryrun/tree/main/corpus/base/configs):

```diff
--- a/pe1.conf
+++ b/pe1.conf
@@ -53,7 +53,7 @@
   network 192.0.2.0/24
   neighbor 10.0.1.2 route-map FROM-CUSTOMER in
   neighbor 10.0.1.2 route-map TO-CUSTOMER out
-  neighbor 10.0.1.2 maximum-prefix 100
+  neighbor 10.0.1.2 maximum-prefix 50
   neighbor 10.0.2.2 route-map FROM-UPSTREAM in
   neighbor 10.0.2.2 route-map TO-UPSTREAM out
   neighbor 10.0.3.2 next-hop-self
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
python corpus/run.py --case 07
```

Case file: [`corpus/cases/07-tighten-max-prefix.yml`](https://github.com/netdryrun/Netdryrun/blob/main/corpus/cases/07-tighten-max-prefix.yml). Published result: netdryrun 0.3.1, containerlab 0.81.1, FRR `quay.io/frrouting/frr:10.4.1`, commit `08059de`, run on 2026-10-27.
