---
title: "send-community removed on the pe1 to pe2 iBGP session: BGP change test (case 12)"
description: "send-community removed on the pe1 to pe2 iBGP session. Expected unsafe: pe2 no longer sees the customer community, so it stops announcing the customer route..."
---

# send-community removed on the pe1 to pe2 iBGP session

Case 12 of the [Network Change Verdict Corpus](../corpus.md). Category: **policy-bug**. Expected verdict: **unsafe** (an experienced operator would reject it).

## Why it is expected unsafe

pe2 no longer sees the customer community, so it stops announcing the customer route to the peer.

Note: A common mistake when rebuilding iBGP sessions.

## The config change

Against the FRR configs of the [base lab](https://github.com/netdryrun/Netdryrun/tree/main/corpus/base/configs):

```diff
--- a/pe1.conf
+++ b/pe1.conf
@@ -57,6 +57,5 @@
   neighbor 10.0.2.2 route-map FROM-UPSTREAM in
   neighbor 10.0.2.2 route-map TO-UPSTREAM out
   neighbor 10.0.3.2 next-hop-self
-  neighbor 10.0.3.2 send-community
  exit-address-family
 !
```

## What each strategy said

The expected verdict was committed to git before any run. All three strategies tested the same running lab ([method](../corpus.md#method)).

| Strategy | Verdict | Result | Checks that failed |
|---|---|---|---|
| Ping only | safe | ❌ approved a bad change | none |
| All BGP sessions up | safe | ❌ approved a bad change | none |
| Netdryrun intent checks | safe | ❌ approved a bad change | none |

## What Netdryrun flagged

Nothing: every check in the [intent spec](https://github.com/netdryrun/Netdryrun/blob/main/corpus/specs/intent.yml) passed, so Netdryrun called the change safe.

Against the pre-registered verdict this counts as one of Netdryrun's losses (false pass).

## Finding after the run

The pre-registered verdict above is unchanged. From [AMENDMENTS.md](https://github.com/netdryrun/Netdryrun/blob/main/corpus/AMENDMENTS.md):

**Case 12 was labeled wrong.** The case expected that removing `neighbor 10.0.3.2 send-community` on pe1 stops pe2 from seeing the customer community. In FRR (verified on 10.4.1) communities are sent to every neighbor by default, so deleting the explicit line is a no-op: `show running-config` no longer shows it, but pe1 still advertises `10.100.0.0/24` to pe2 with community `65000:100`, and pe2 still matches it (`show bgp ipv4 unicast community 65000:100` lists the route). Reproduce with [`scripts/corpus_case12_verify.sh`](https://github.com/netdryrun/Netdryrun/blob/main/scripts/corpus_case12_verify.sh). The change is actually safe, so all three strategies answered case 12 correctly. With that one label corrected the scores would be: ping only 21/30, sessions up 16/30, Netdryrun 25/30. The headline numbers stay at the pre-registered values. The mistake would have been real on platforms that do not send communities by default (Cisco IOS, for example); a vendor-specific version of this case belongs in a future corpus.

## Reproduce it

On Linux or WSL2 with Docker and containerlab, from a checkout of the repository:

```bash
python corpus/run.py --case 12
```

Case file: [`corpus/cases/12-ibgp-send-community-dropped.yml`](https://github.com/netdryrun/Netdryrun/blob/main/corpus/cases/12-ibgp-send-community-dropped.yml). Published result: netdryrun 0.3.1, containerlab 0.81.1, FRR `quay.io/frrouting/frr:10.4.1`, commit `08059de`, run on 2026-10-27.
