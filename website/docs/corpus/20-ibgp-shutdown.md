---
title: "iBGP session between pe1 and pe2 shut down: BGP change test (case 20)"
description: "iBGP session between pe1 and pe2 shut down. Expected unsafe: The two halves of the network stop exchanging routes."
---

# iBGP session between pe1 and pe2 shut down

Case 20 of the [Network Change Verdict Corpus](../corpus.md). Category: **fat-finger**. Expected verdict: **unsafe** (an experienced operator would reject it).

## Why it is expected unsafe

The two halves of the network stop exchanging routes.

## The config change

Against the FRR configs of the [base lab](https://github.com/netdryrun/Netdryrun/tree/main/corpus/base/configs):

```diff
--- a/pe1.conf
+++ b/pe1.conf
@@ -60,3 +60,6 @@
   neighbor 10.0.3.2 send-community
  exit-address-family
 !
+router bgp 65000
+ neighbor 10.0.3.2 shutdown
+!
```

## What each strategy said

The expected verdict was committed to git before any run. All three strategies tested the same running lab ([method](../corpus.md#method)).

| Strategy | Verdict | Result | Checks that failed |
|---|---|---|---|
| Ping only | unsafe | ✅ | customer reaches peer |
| All BGP sessions up | unsafe | ✅ | pe1-pe2 up |
| Netdryrun intent checks | unsafe | ✅ | I1 pe1-pe2 iBGP up, I2 peer has customer route, I2 peer has our aggregate, I3 customer has peer route, I3 customer reaches peer, I5 peer receives exactly our 2 prefixes |

## What Netdryrun flagged

These checks from the [intent spec](https://github.com/netdryrun/Netdryrun/blob/main/corpus/specs/intent.yml) failed:

- **I1 pe1-pe2 iBGP up**: the BGP session from pe1 to 10.0.3.2 is established
- **I2 peer has customer route**: 10.100.0.0/24 must be in peer1's routing table as a bgp route
- **I2 peer has our aggregate**: 192.0.2.0/24 must be in peer1's routing table as a bgp route
- **I3 customer has peer route**: 198.51.100.0/24 must be in ce1's routing table as a bgp route
- **I3 customer reaches peer**: ce1 can ping 198.51.100.1 from 10.100.0.1
- **I5 peer receives exactly our 2 prefixes**: peer1 receives exactly 2 prefixes from 10.0.4.1

## Reproduce it

On Linux or WSL2 with Docker and containerlab, from a checkout of the repository:

```bash
python corpus/run.py --case 20
```

Case file: [`corpus/cases/20-ibgp-shutdown.yml`](https://github.com/netdryrun/Netdryrun/blob/main/corpus/cases/20-ibgp-shutdown.yml). Published result: netdryrun 0.3.1, containerlab 0.81.1, FRR `quay.io/frrouting/frr:10.4.1`, commit `08059de`, run on 2026-10-27.
