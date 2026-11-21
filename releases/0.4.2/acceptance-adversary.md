# Angle 5: adversary, Netdryrun 0.4.2

Commit 79de75984253ec3727bb35fc2aec14bc957ea103

Result: no open false pass

Four red-team rounds ran offline on exports of the 0.4.2 candidates: F on `82fb052`, G on `8bf00df`, H on `83d4de0`
and I on `3d71d5a`. Each export's `src/` was matched to its commit file by file. Each round had two isolated
attackers (A: drivers; B: checks, config, record, verify, scenarios), each given only the code, the user docs, the
fixtures and the red-team harness, and a fresh verifier given only the candidates and the same export. Records:
`wt/redteam-042-{F,G,H,I}{A,B,V}/`, with the verdicts in each V folder's `VERDICT.md`.

After `82fb052`, `src/` changed only through the fixes in the table: `d413c86`, `20d9d2a`, `fe4ba70`, `0b40056`,
`61893c9`, `606d238`, `57eb8ca`, `d59479b`, `5f0b7d7`, `f9a1585`, `be7ac46` and `83478f2`. A fresh read-only adversary
reviewed each fix: n4c (`82fb052..cf460d6`, BLOCK, fixed in `606d238`), n4f (`606d238`, BLOCK, fixed in `57eb8ca`),
n4i (`57eb8ca`, BLOCK, fixed in `d59479b`), n4l (`d59479b`, HOLD), n5d (`5f0b7d7`, BLOCK, fixed in `f9a1585`), n5g
(`f9a1585`, HOLD), n6c (`be7ac46`, HOLD) and n7c (`83478f2`, HOLD). Every chain ends in a HOLD. The last code fix is
`83478f2`. n7c found no remaining false pass and no regression, and the full suite passed (7850 passed). Its notes are
hardening and doc nits. `4c62c51` is the corpus refresh on `83478f2` (docs and results only).
`git diff --stat 83478f2 4c62c51 -- src tests` is empty, so `src/` and `tests/` are byte-identical to the reviewed
`83478f2`. `3aa4c7f` adds only the release date and the roadmap row (CHANGELOG, roadmap.md, llms-full.txt) on top of `4c62c51`. `014ab58`, the commit the final gate ran on, adds only tests that kill 83 mutation survivors and the reviewed accepts in releases/0.4.2/accepted.json; `src/` is still byte-identical to `83478f2`. Reports: `wt/adv-n4c-REPORT.md` to `wt/adv-n7c-REPORT.md`. `9b304ad` came after the first acceptance run on `014ab58`: cEOS waits out its starting `kernel` default over
Management0 (up to 60 s, then judged as before), and RouterOS reads its BGP sessions again after the route table. A
fresh read-only adversary, n8a, reviewed `014ab58..ce79e10` and returned HOLD: no false pass and no regression (full suite 7915
passed). Its one question outside the commit was whether a settled cEOS ping can leave by the Linux default via eth0
that EOS doesn't list. A live run already answers it: `wt/cap-mgmt/live-out2/new.log` pinged the Docker host from
cEOS with no lab route, and the ping failed with "Network is unreachable". `8943dec` changes only the acceptance
matrix (M-10 named as a known record gap). `ce79e10` changes only the release date. `2632573` is the corpus refresh on
`ce79e10`, with docs and results only. `7f9cf25` fixes one test fixture
(`tests/test_case18_exemption.py`). `src/` is byte-identical to `9b304ad`. Report: `wt/adv-n8a-REPORT.md`.
Those three commits carried an invalid Session marker (a space), so they were committed again on `8943dec` with
`Session: ndr-main-042-regate`: `ab08f27`, `043e20c` and `7a82e4d`. Its tree is
`835bb15`, the same as `7f9cf25`'s. `11dabd2` adds tests only (26 mutants of the
9b304ad code killed, 5 equivalent ones accepted with a reviewed argument): `src/` is unchanged. `0816220` changes the acceptance harness, its matrix and its test only (the RouterOS OSPF trap is a refusal by design, exit 2), `ecf627e` likewise (record once more when RouterOS refuses a prefix-count still at 0), and `79de759`, the commit the final gate runs on, likewise (when the refusal persists after the second record, route checks by hand stand in its place, and the limit is disclosed; docs and harness only): `src/` is still unchanged.

Evidence, said plainly: most rows are verifier-rated offline. RT-0080 is confirmed by a Netdryrun live run (FRR
10.4.1, lab ndr-rplu, `wt/repro-042d/capture/`): before the fix, `exact: 0` passed "the session doesn't carry
ipv4-unicast" while the peer's routes were installed. RT-0081 and RT-0082 are confirmed at the tool level only
(busybox and iputils ping on loopback). The config, record, scenario and verify rows were reproduced offline on the
real code path. They are deterministic and did not need a lab. None of the disclosed limits is confirmed live.

The owner rule in force: a live-confirmed false pass, or an offline-deterministic one in released code, blocks the
release and was fixed. A candidate not confirmed live is a disclosed limit (owner, 2026-11-13, adoption-first plan),
published in CHANGELOG "Not fixed in 0.4.2", on the compatibility page and in config.md, each with a workaround. Some
candidates that were not live-confirmed were fixed anyway (NX-OS history paths, EOS asdot) because the fix was safe
either way. The result line reads "no open false pass" because every real one is fixed or is an accepted, published
limit, not because none was found. Disclosed limits are not filed as `tests/redteam/` cases. Cases 1 and 2 of the
0.4.1 advisory are still open as accepted 0.4.1 limits and are listed in the same CHANGELOG section.

| Candidate | Attacker | Verdict | Live | Case | Fixed in |
|---|---|---|---|---|---|
| Duplicate key inside a `<<` merge source accepted, so a guard loads for another prefix | F-B (B-RT-0073) | real, Medium | offline-deterministic (verifier, real CLI `validate`) | RT-0073 | d413c86 |
| Scenario restore brings up a link the lab keeps shut | F-B (B-RT-0076) | real, Medium | offline-deterministic (verifier, fake kernel) | RT-0074 | 20d9d2a |
| NX-OS dampening history or `pathdeleted` path read as received | F-A (A-RT-0073, A-RT-0077) | history path real (FRR twin RT-0070 confirmed live); `pathdeleted` not proven (transient); fixed together | verifier-rated offline; parser path deterministic; not run on live NX-OS | RT-0075 | fe4ba70 |
| `record` writes guards in the default VRF only, silently | F-B (B-RT-0074) | real, Medium (silent baseline gap) | offline-deterministic (verifier, real `_record_vrf`) | RT-0076 | 0b40056 |
| MCP `record_baseline` names one gap marker of two | F-B (B-RT-0075) | real contract defect, Low to Medium; no check passes falsely | offline-deterministic | none (oracle FP-042-MCPMISSNODE) | 61893c9 |
| Junos (beta) add-path: accepted-prefix-count counts paths | F-A (A-RT-0074) | real code gap, needs live | verifier-rated offline; not live | none | not fixed: disclosed limit (cf460d6) |
| SR Linux graceful-restart stale paths counted in `bgp_prefixes` | F-A (A-RT-0075) | not proven as written (peer F-bit clear, RFC 4724 flush); code gap real with the F-bit set | verifier-rated offline; not live | none | not fixed: disclosed limit (cf460d6) |
| Junos (beta) graceful-restart stale routes counted as accepted | F-A (A-RT-0076) | not proven as written (inconsistent fixture); code gap real | verifier-rated offline; not live | none | not fixed: disclosed limit (cf460d6) |
| A VRF with BGP routes but no session gets no guard and no gap line | adversary n4c on cf460d6 | real, RT-0076 class; reproduced on the oracle's fake PE | offline-deterministic | oracle FP-042-RECORDVRFNOSESS | 606d238 |
| A failed VRF-list read records the default VRF only, exit 0 | adversary n4f on 606d238 | real, since 0.4.0 | offline-deterministic | oracle FP-042-RECORDVRFLISTFAIL | 57eb8ca |
| No `::/0` guard in a VRF without IPv6 BGP | adversary n4f on 606d238 (C1) | real, since 0.4.1 (documented rule then) | offline-deterministic | oracle FP-042-RECORDV6DEFAULT | 57eb8ca |
| A failed IPv6 route read under `record --no-routes` drops `::/0` and the IPv6 link guards, exit 0 | adversary n4i on 57eb8ca (B1, D1) | real, since 0.3.3 | offline-deterministic | oracle FP-042-RECORDV6READFAIL | d59479b |
| FRR VRF list read any text as no VRFs | adversary n4i on 57eb8ca (D2) | real fail-open parse | offline-deterministic | oracle FP-042-FRRVRFPARSE | d59479b |
| `verify` `appears_on` with BGP pins approves when a static route wins | G-B (B-RT-0077) | real, Medium | verifier-rated offline; engine deterministic; FRR output shape not captured live | RT-0077 | 5f0b7d7 |
| `link_down` on a VLAN-trunk parent judged on the state from before the fault | G-B (B-RT-0078) | real, Medium to High | verifier-rated offline; code path deterministic | RT-0078 | 5f0b7d7 |
| `link_down` on a port of a bridge that keeps another port (SONiC `Vlan@Bridge` too) watches nothing | adversary n5d on 5f0b7d7 | real, RT-0078 left open; reproduced on the oracle's fake kernel | offline-deterministic | oracle FP-042-LINKDOWNBRIDGE | f9a1585 |
| `link_down` on a SONiC port never looks up the far end | found writing oracle FP-042-LINKDOWNBRIDGE | real, 0.3.1 to 0.4.1 | offline-deterministic | RT-0079 | f9a1585 |
| `link_down` sessions still not waited for: far-end unnumbered session on a bridge, cEOS SVIs and subinterfaces, `min_links` bonds, tunnels, busybox masters | adversary n5g on f9a1585 (G1), n5d | G1 real offline, not a regression; the others not proven | offline (G1); not live | none | not fixed: disclosed limit (CHANGELOG, config.md) |
| Arista EOS BGP aggregate read as protocol `aggregate`, so `route protocol: bgp present: false` passes | G-A (A-RT-0077) | real, Low to Medium; the cEOS routeType string is unconfirmed | verifier-rated offline; no cEOS aggregate capture | none | not fixed: disclosed limit (5f0b7d7) |
| Ping to the node's own HSRP VIP (NX-OS) or VARP address (EOS) | G-A (A-RT-0078, A-RT-0079) | documented behaviour (config.md ping section) | verifier, offline | none | n/a |
| FRR/SONiC labeled-unicast-only session: `exact: 0` on ipv4-unicast passes | H-A, H-B (both RT-0080) | real, High class, low prevalence | confirmed live: FRR 10.4.1, Netdryrun 0.4.2 before the fix, `wt/repro-042d` | RT-0080 | be7ac46 |
| Arista EOS graceful-restart stale paths in `prefixAccepted` | H-A (local RT-0081) | real code gap, needs live | verifier-rated offline; not live | none | not fixed: disclosed limit (a645605) |
| Cisco NX-OS (beta) graceful-restart stale paths in `prefixreceived` | H-A (local RT-0082) | plausible, needs live | verifier-rated offline; not live | none | not fixed: disclosed limit (a645605) |
| Cisco NX-OS (beta) add-path paths counted as prefixes | H-A (local RT-0083) | unconfirmed | verifier-rated offline; not live | none | not fixed: disclosed limit (a645605) |
| SR Linux labeled-unicast family without counters dropped; VPN import, EVPN type-5 in the default VRF, EOS labeled-unicast-only unchecked | adversary n6c on be7ac46 (R1, R4) | R1 reproduced on synthetic input, not a regression; R4 theoretical | offline; not live | none | not fixed: disclosed limit (61ae778) |
| Ping with a source of the other address family (IPv4 source and IPv6 target, and the reverse) | I-B (RT-0081; reverse from attempt RT-0112, raised by the verifier) | real, Medium | confirmed at tool level (busybox 1.30.1, iputils 20211215, loopback); not by a Netdryrun live run | RT-0081, RT-0082 | 83478f2 |
| Arista EOS asdot AS path passes a private-ASN `as_path_regex` guard | I-A (RT-0002) | real if cEOS JSON prints asdot (about 70%); driver side deterministic | verifier-rated offline; not live | RT-0083 | 83478f2 |
| Ping with no `source` leaves from the management address | I-B (RT-0082) | real by kernel logic; whether it passes depends on `rp_filter` | not live | none | not fixed: disclosed limit (83478f2) |
| FRR `route protocol: bgp` passes on an LLGR_STALE path | I-A (RT-0001) | documented behaviour (config.md route section) | verifier, offline | none | n/a |

Attempts refused: F: A 15, B 18; G: A 8, B 8; H: A 6, B 3; I: A 4, B 11 (73 in all). Only F-B states its count in
its own report (14 run through the harness, 4 by reading the code). The other counts are the attempt files in each
attacker folder. H-B's three are the two cases it filed as attempts and its verify script, all refused by the
verifier. I-B's count leaves out RT-0112, which became a candidate.
