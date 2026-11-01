---
title: "Lower customer local-preference from 300 to 250: BGP change test (case 9)"
description: "Lower customer local-preference from 300 to 250. Expected safe: Customer routes stay the most preferred (peer 200, upstream 100)."
---

# Lower customer local-preference from 300 to 250

Case 9 of the [Network Change Verdict Corpus](../corpus.md). Category: **traffic-engineering**. Expected verdict: **safe** (an experienced operator would approve it).

## Why it is expected safe

Customer routes stay the most preferred (peer 200, upstream 100).

## The config change

Against the FRR configs of the [base lab](https://github.com/netdryrun/Netdryrun/tree/main/corpus/base/configs):

```diff
--- a/pe1.conf
+++ b/pe1.conf
@@ -27,7 +27,7 @@
 route-map FROM-CUSTOMER permit 10
  match ip address prefix-list CUSTOMER-IN
  set community 65000:100
- set local-preference 300
+ set local-preference 250
 !
 route-map FROM-UPSTREAM permit 10
  set community 65000:200
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
python corpus/run.py --case 09
```

Case file: [`corpus/cases/09-customer-localpref.yml`](https://github.com/netdryrun/Netdryrun/blob/main/corpus/cases/09-customer-localpref.yml). Published result: netdryrun 0.3.1, containerlab 0.81.1, FRR `quay.io/frrouting/frr:10.4.1`, commit `08059de`, run on 2026-10-27.
