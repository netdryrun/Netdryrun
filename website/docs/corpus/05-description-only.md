---
title: "Change an interface description: BGP change test (case 5)"
description: "Change an interface description. Expected safe: Cosmetic change. Must never be blocked."
---

# Change an interface description

Case 5 of the [Network Change Verdict Corpus](../corpus.md). Category: **hygiene**. Expected verdict: **safe** (an experienced operator would approve it).

## Why it is expected safe

Cosmetic change. Must never be blocked.

## The config change

Against the FRR configs of the [base lab](https://github.com/netdryrun/Netdryrun/tree/main/corpus/base/configs):

```diff
--- a/pe1.conf
+++ b/pe1.conf
@@ -9,7 +9,7 @@
  ip address 10.0.1.1/30
 !
 interface eth2
- description to-upstream-up1
+ description to-upstream-up1 (transit, CHG-1042)
  ip address 10.0.2.1/30
 !
 interface eth3
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
python corpus/run.py --case 05
```

Case file: [`corpus/cases/05-description-only.yml`](https://github.com/netdryrun/Netdryrun/blob/main/corpus/cases/05-description-only.yml). Published result: netdryrun 0.3.1, containerlab 0.81.1, FRR `quay.io/frrouting/frr:10.4.1`, commit `08059de`, run on 2026-10-27.
