# Independent check (step 5)

A fresh reviewer that had not seen the oracle was given only the configs, the checks (names reduced to ID and node,
comments stripped), the overlay edits and the netdryrun.yml reference, and predicted the verdicts for the baselines
and 10 mutants drawn with `random.Random(20261030).sample(...)`: M02 M05 M08 M09 M11 M14 N03 N04 N05 N08.
Its answer is `predictions.txt`.

| Item | Oracle flips | Agreement |
|---|---|---|
| Baseline L1 (expected failures) | T01-T09, R01-R03 | identical |
| Baseline L2 (expected failures) | U01-U05 | identical |
| M02 | 10 | identical |
| M05 | 3 | identical |
| M08 | 6 | identical |
| M09 | 11 | identical |
| M11 | 40 | identical |
| M14 | 6 | identical |
| N03 | 14 | identical |
| N04 | 27 | identical |
| N05 | 22 | identical |
| N08 | 4 | identical |

10/10 mutants and both baselines agree check for check. The reviewer flagged as ambiguous exactly the lines the live
run then contradicted or confirmed: T02/U02 (cEOS may print "med": 0 for a missing MED: confirmed live, finding
IOP-2), C77/T06 (cEOS ECMP tie-break: live, cEOS kept the first-received path as ECMP head, "Not best: ECMP-Fast
configured", so the oracle's NOS assumption was wrong), EOS send-community and large communities (live: sent), and
M09's next-hop resolution through a static default (not run).

Agreement between two readers of the same reference does not prove the oracle right (both read the same
assumptions); the live run is what found the two MED false passes.
