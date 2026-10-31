---
title: "Aggregate network statement typo (192.0.3.0/24): BGP change test (case 25)"
description: "Aggregate network statement typo (192.0.3.0/24). Expected unsafe: Our own aggregate is no longer announced anywhere."
---

# Aggregate network statement typo (192.0.3.0/24)

Case 25 of the [Network Change Verdict Corpus](../corpus.md). Category: **fat-finger**. Expected verdict: **unsafe** (an experienced operator would reject it).

## Why it is expected unsafe

Our own aggregate is no longer announced anywhere.

## The config change

Against the FRR configs of the [base lab](https://github.com/netdryrun/Netdryrun/tree/main/corpus/base/configs):

```diff
--- a/pe1.conf
+++ b/pe1.conf
@@ -50,7 +50,7 @@
  neighbor 10.0.3.2 remote-as 65000
  neighbor 10.0.3.2 description pe2
  address-family ipv4 unicast
-  network 192.0.2.0/24
+  network 192.0.3.0/24
   neighbor 10.0.1.2 route-map FROM-CUSTOMER in
   neighbor 10.0.1.2 route-map TO-CUSTOMER out
   neighbor 10.0.1.2 maximum-prefix 100
```

## What each strategy said

The expected verdict was committed to git before any run. All three strategies tested the same running lab ([method](../corpus.md#method)).

| Strategy | Verdict | Result | Checks that failed |
|---|---|---|---|
| Ping only | safe | ❌ approved a bad change | none |
| All BGP sessions up | safe | ❌ approved a bad change | none |
| Netdryrun intent checks | unsafe | ✅ | I2 upstream has our aggregate, I2 peer has our aggregate, I5 upstream receives exactly our 2 prefixes, I5 peer receives exactly our 2 prefixes |

## What Netdryrun flagged

These checks from the [intent spec](https://github.com/netdryrun/Netdryrun/blob/main/corpus/specs/intent.yml) failed:

- **I2 upstream has our aggregate**: 192.0.2.0/24 must be in up1's routing table as a bgp route
- **I2 peer has our aggregate**: 192.0.2.0/24 must be in peer1's routing table as a bgp route
- **I5 upstream receives exactly our 2 prefixes**: up1 receives exactly 2 prefixes from 10.0.2.1
- **I5 peer receives exactly our 2 prefixes**: peer1 receives exactly 2 prefixes from 10.0.4.1

## Reproduce it

On Linux or WSL2 with Docker and containerlab, from a checkout of the repository:

```bash
python corpus/run.py --case 25
```

Case file: [`corpus/cases/25-aggregate-typo.yml`](https://github.com/netdryrun/Netdryrun/blob/main/corpus/cases/25-aggregate-typo.yml). Published result: netdryrun 0.3.1, containerlab 0.81.1, FRR `quay.io/frrouting/frr:10.4.1`, commit `08059de`, run on 2026-10-27.
