---
title: "pe2 configured with the wrong local ASN: BGP change test (case 27)"
description: "pe2 configured with the wrong local ASN. Expected unsafe: All of pe2's sessions fail and the peer is cut off."
---

# pe2 configured with the wrong local ASN

Case 27 of the [Network Change Verdict Corpus](../corpus.md). Category: **fat-finger**. Expected verdict: **unsafe** (an experienced operator would reject it).

## Why it is expected unsafe

All of pe2's sessions fail and the peer is cut off.

## The config change

Against the FRR configs of the [base lab](https://github.com/netdryrun/Netdryrun/tree/main/corpus/base/configs):

```diff
--- a/pe2.conf
+++ b/pe2.conf
@@ -28,7 +28,7 @@
 route-map TO-PEER permit 20
  match ip address prefix-list OWN
 !
-router bgp 65000
+router bgp 65001
  bgp router-id 10.255.0.2
  neighbor 10.0.3.1 remote-as 65000
  neighbor 10.0.3.1 description pe1
```

## What each strategy said

The expected verdict was committed to git before any run. All three strategies tested the same running lab ([method](../corpus.md#method)).

| Strategy | Verdict | Result | Checks that failed |
|---|---|---|---|
| Ping only | unsafe | ✅ | customer reaches peer |
| All BGP sessions up | unsafe | ✅ | pe1-pe2 up, pe2-peer1 up |
| Netdryrun intent checks | unsafe | ✅ | I1 pe1-pe2 iBGP up, I1 pe2-peer1 session up, I2 peer has customer route, I2 peer has our aggregate, I3 customer has peer route, I3 customer reaches peer, I4 no upstream route leaked to peer, I4 no default leaked to peer, I5 peer receives exactly our 2 prefixes |

## What Netdryrun flagged

These checks from the [intent spec](https://github.com/netdryrun/Netdryrun/blob/main/corpus/specs/intent.yml) failed:

- **I1 pe1-pe2 iBGP up**: the BGP session from pe1 to 10.0.3.2 is established
- **I1 pe2-peer1 session up**: the BGP session from pe2 to 10.0.4.2 is established
- **I2 peer has customer route**: 10.100.0.0/24 must be in peer1's routing table as a bgp route
- **I2 peer has our aggregate**: 192.0.2.0/24 must be in peer1's routing table as a bgp route
- **I3 customer has peer route**: 198.51.100.0/24 must be in ce1's routing table as a bgp route
- **I3 customer reaches peer**: ce1 can ping 198.51.100.1 from 10.100.0.1
- **I4 no upstream route leaked to peer**: 203.0.113.0/24 must not be in peer1's routing table as a bgp route
- **I4 no default leaked to peer**: 0.0.0.0/0 must not be in peer1's routing table as a bgp route
- **I5 peer receives exactly our 2 prefixes**: peer1 receives exactly 2 prefixes from 10.0.4.1

## Reproduce it

On Linux or WSL2 with Docker and containerlab, from a checkout of the repository:

```bash
python corpus/run.py --case 27
```

Case file: [`corpus/cases/27-local-asn-typo.yml`](https://github.com/netdryrun/Netdryrun/blob/main/corpus/cases/27-local-asn-typo.yml). Published result: netdryrun 0.3.1, containerlab 0.81.1, FRR `quay.io/frrouting/frr:10.4.1`, commit `08059de`, run on 2026-10-27.
