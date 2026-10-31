---
title: "Typo in the upstream's ASN (65020 instead of 65200): BGP change test (case 13)"
description: "Typo in the upstream's ASN (65020 instead of 65200). Expected unsafe: The upstream session never comes up; the customer loses internet access."
---

# Typo in the upstream's ASN (65020 instead of 65200)

Case 13 of the [Network Change Verdict Corpus](../corpus.md). Category: **fat-finger**. Expected verdict: **unsafe** (an experienced operator would reject it).

## Why it is expected unsafe

The upstream session never comes up; the customer loses internet access.

## The config change

Against the FRR configs of the [base lab](https://github.com/netdryrun/Netdryrun/tree/main/corpus/base/configs):

```diff
--- a/pe1.conf
+++ b/pe1.conf
@@ -45,7 +45,7 @@
  bgp router-id 10.255.0.1
  neighbor 10.0.1.2 remote-as 65100
  neighbor 10.0.1.2 description ce1
- neighbor 10.0.2.2 remote-as 65200
+ neighbor 10.0.2.2 remote-as 65020
  neighbor 10.0.2.2 description up1
  neighbor 10.0.3.2 remote-as 65000
  neighbor 10.0.3.2 description pe2
```

## What each strategy said

The expected verdict was committed to git before any run. All three strategies tested the same running lab ([method](../corpus.md#method)).

| Strategy | Verdict | Result | Checks that failed |
|---|---|---|---|
| Ping only | unsafe | ✅ | customer reaches upstream |
| All BGP sessions up | unsafe | ✅ | pe1-up1 up |
| Netdryrun intent checks | unsafe | ✅ | I1 pe1-up1 session up, I2 upstream has customer route, I2 upstream has our aggregate, I3 customer has upstream route, I3 customer has default, I3 customer reaches upstream, I4 no peer route leaked to upstream, I5 upstream receives exactly our 2 prefixes |

## What Netdryrun flagged

These checks from the [intent spec](https://github.com/netdryrun/Netdryrun/blob/main/corpus/specs/intent.yml) failed:

- **I1 pe1-up1 session up**: the BGP session from pe1 to 10.0.2.2 is established
- **I2 upstream has customer route**: 10.100.0.0/24 must be in up1's routing table as a bgp route
- **I2 upstream has our aggregate**: 192.0.2.0/24 must be in up1's routing table as a bgp route
- **I3 customer has upstream route**: 203.0.113.0/24 must be in ce1's routing table as a bgp route
- **I3 customer has default**: 0.0.0.0/0 must be in ce1's routing table as a bgp route
- **I3 customer reaches upstream**: ce1 can ping 203.0.113.1 from 10.100.0.1
- **I4 no peer route leaked to upstream**: 198.51.100.0/24 must not be in up1's routing table as a bgp route
- **I5 upstream receives exactly our 2 prefixes**: up1 receives exactly 2 prefixes from 10.0.2.1

## Reproduce it

On Linux or WSL2 with Docker and containerlab, from a checkout of the repository:

```bash
python corpus/run.py --case 13
```

Case file: [`corpus/cases/13-upstream-asn-typo.yml`](https://github.com/netdryrun/Netdryrun/blob/main/corpus/cases/13-upstream-asn-typo.yml). Published result: netdryrun 0.3.1, containerlab 0.81.1, FRR `quay.io/frrouting/frr:10.4.1`, commit `08059de`, run on 2026-10-27.
