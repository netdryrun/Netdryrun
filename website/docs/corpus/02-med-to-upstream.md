---
title: "Set MED on routes sent to the upstream: BGP change test (case 2)"
description: "Set MED on routes sent to the upstream. Expected safe: Adds a metric to the upstream export clause. Changes path attributes only; nothing leaks or disappears."
---

# Set MED on routes sent to the upstream

Case 2 of the [Network Change Verdict Corpus](../corpus.md). Category: **traffic-engineering**. Expected verdict: **safe** (an experienced operator would approve it).

## Why it is expected safe

Adds a metric to the upstream export clause. Changes path attributes only; nothing leaks or disappears.

## The config change

Against the FRR configs of the [base lab](https://github.com/netdryrun/Netdryrun/tree/main/corpus/base/configs):

```diff
--- a/pe1.conf
+++ b/pe1.conf
@@ -60,3 +60,6 @@
   neighbor 10.0.3.2 send-community
  exit-address-family
 !
+route-map TO-UPSTREAM permit 10
+ set metric 50
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
python corpus/run.py --case 02
```

Case file: [`corpus/cases/02-med-to-upstream.yml`](https://github.com/netdryrun/Netdryrun/blob/main/corpus/cases/02-med-to-upstream.yml). Published result: netdryrun 0.3.1, containerlab 0.81.1, FRR `quay.io/frrouting/frr:10.4.1`, commit `08059de`, run on 2026-10-27.
