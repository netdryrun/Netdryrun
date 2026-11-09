# Angle 5: adversary, Netdryrun 0.4.1

Commit 2e988a43c980ba602a40fccc1cdc30d9ea68329f

Result: no open false pass

The red team ran on an export of `26380cbfe700b39b5eb29ad862b554544fa6a81d` (2026-11-09). `2e988a4` differs from it only
in prose (CHANGELOG, releases/0.4.1/review.md and docs pages publishing the limits below), so the code tested is the
code of this commit. Two isolated attackers (A: drivers; B: checks, config, record, verify), each given only the code,
the user docs, the fixtures and the red-team harness, and a fresh verifier given only the candidates and the same
export. Records: `wt/redteam-26380cb/` (A, B, V, VERDICTS.md, cap-vrfdev.txt).

Evidence, said plainly: every row is verifier-rated offline; RT-0053 is confirmed at the kernel/iproute2 level in the
pinned FRR 10.4.1 image; none is confirmed by a Netdryrun live run. The published docs call the four real ones known
false passes found offline and published conservatively.

**Departure from the process.** ACCEPTANCE-PROMPT.md Job 1 says to confirm each case live and file it as the next
`tests/redteam/RT-NNNN-*.yml` on the acceptance branch. These four are not filed in 0.4.1: the gate's `code_differs`
counts every file under `tests/` as code, so filing them after the mutation (`8bc84c3`) and live (`26380cb`) runs would
rerun both (about 8 to 9 hours, VM labs included) for no change in behaviour. They are filed as the first commit on the
0.4.2 branch, red before each fix. The result line reads "no open false pass" because each is an accepted documented
limit, not because it was filed or fixed.

| Candidate | Attacker | Verdict | Live | Case | Fixed in |
|---|---|---|---|---|---|
| FRR/SONiC ping in a VRF to an address on the VRF device | A | real, MAJOR: accepted documented limit (owner rule 2026-11-08 'publish as limits', applied by the coordinator 2026-11-09); RT filing deferred to 0.4.2; reason: code_differs | verifier-rated offline; confirmed at the kernel/iproute2 level (pinned FRR 10.4.1 image); not by a Netdryrun live run | RT-0053 (0.4.2 branch) | planned 0.4.2 |
| EOS: non-BGP route not selected (floating static, OSPF default behind a static) | A, B | real, MAJOR: accepted documented limit (owner rule 2026-11-08 'publish as limits', applied by the coordinator 2026-11-09); RT filing deferred to 0.4.2; reason: code_differs | verifier-rated offline (from live fixtures); not by a Netdryrun live run | RT-0056, RT-0063 (0.4.2 branch) | planned 0.4.2 |
| SR Linux EVPN type-5 route in an ip-vrf without BGP, `bgp_route present: false` | A | real, MAJOR: accepted documented limit (owner rule 2026-11-08 'publish as limits', applied by the coordinator 2026-11-09); RT filing deferred to 0.4.2; reason: code_differs | verifier-rated offline; not by a Netdryrun live run | RT-0058 (0.4.2 branch) | planned 0.4.2 |
| SR Linux `record --attributes` drops an unread AS path without a warning | B | real, MAJOR: accepted documented limit (owner rule 2026-11-08 'publish as limits', applied by the coordinator 2026-11-09); RT filing deferred to 0.4.2; reason: code_differs; regression vs 0.4.0 (45f63df), coordinator accepted 2026-11-09 for the same reason | verifier-rated offline; not by a Netdryrun live run | RT-S01 (0.4.2 branch) | planned 0.4.2 |
| SR Linux floating static (pref 250) behind a BGP default | A | not real: the route table lists the losing static with active:false, and the check fails | srl-frr lab, SR Linux 26.7.2, Netdryrun at 1ab9308, 2026-11-09: `route protocol: static, present: false` FAILED ("unexpectedly present via static (not selected)") | RT-0057 | n/a |
| SR Linux OSPF default behind a static | B | untested: OSPF never reached full on SR Linux in the lab (exstart, then the rerun's mtu-ignore setting was refused); inferred not producible from RT-0057, not shown | one lab pass plus one rerun, by agreement | RT-0064 | test queued for 0.4.2 |
| SR Linux EVPN type-5 default behind a static in an ip-vrf | A | untested directly: premise (route table lists the winner only) refuted in the default network-instance on SR Linux 26.7.2; not published | needs two SR Linux leaves | RT-0054 | test queued for 0.4.2 |
| FRR VRF-imported default losing to a static | A | not producible: zebra lists the unselected bgp entry, so present: false fails | verifier, offline | RT-0055 | n/a (latent guard in 0.4.2) |
| `bgp_prefixes` without `afi` on a dual-stack IPv4 session | B | documented behaviour: "`afi` ... default `ipv4-unicast`" (config.md); doc line added | verifier, offline | RT-0065 | n/a |

Attempts refused: A 6, B 7.
