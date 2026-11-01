---
title: "No change (control): BGP change test (case 1)"
description: "No change (control). Expected safe: The base network with no edits. Every strategy must pass it, or the corpus itself is broken."
---

# No change (control)

Case 1 of the [Network Change Verdict Corpus](../corpus.md). Category: **control**. Expected verdict: **safe** (an experienced operator would approve it).

## Why it is expected safe

The base network with no edits. Every strategy must pass it, or the corpus itself is broken.

## The config change

None: the base lab runs unchanged.

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
python corpus/run.py --case 01
```

Case file: [`corpus/cases/01-no-change.yml`](https://github.com/netdryrun/Netdryrun/blob/main/corpus/cases/01-no-change.yml). Published result: netdryrun 0.3.1, containerlab 0.81.1, FRR `quay.io/frrouting/frr:10.4.1`, commit `08059de`, run on 2026-10-27.
