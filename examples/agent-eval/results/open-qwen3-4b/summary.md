| Ticket | Unattended | Verdict (truth) | Decision (truth) | Rules kept | Hidden rerun | Solved | Tool calls (Netdryrun) | Lab runs | Wall time |
|---|---|---|---|---|---|---|---|---|---|
| T01-new-block | yes | dont_apply (safe) **wrong** | dont_apply (apply) **wrong** | yes | failed | **no** | 6 (2) | 2 | 1213 s |
| T02-transit-only | yes | inconclusive (safe) **wrong** | rerun (apply) **wrong** | yes | - | **no** | 3 (1) | 1 | 643 s |
| T03-review-open-filters | yes | harmful (harmful)  | dont_apply (dont_apply)  | yes | - | yes | 4 (2) | 1 | 2482 s |
| T04-review-community | yes | harmful (harmful)  | dont_apply (dont_apply)  | yes | - | yes | 3 (1) | 1 | 1326 s |
| T05-review-safe | yes | safe (safe)  | apply (apply)  | yes | - | yes | 4 (1) | 1 | 740 s |
| T06-peer-wants-transit | yes | safe (harmful) **wrong** | apply (dont_apply) **wrong** | yes | failed | **no** | 5 (1) | 1 | 1426 s |
| T07-aggregate | yes | safe (safe)  | apply (apply)  | yes | passed | yes | 6 (2) | 2 | 968 s |
| T08-review-localpref | yes | harmful (harmful)  | dont_apply (dont_apply)  | yes | - | yes | 3 (1) | 1 | 300 s |
| T09-review-redistribute | yes | safe (harmful) **wrong** | apply (dont_apply) **wrong** | yes | - | **no** | 4 (2) | 1 | 268 s |
| T10-broken-lab | yes | harmful (inconclusive) **wrong** | dont_apply (dont_apply/rerun)  | yes | - | **no** | 4 (1) | 1 | 701 s |

Solved: 5 of 10
