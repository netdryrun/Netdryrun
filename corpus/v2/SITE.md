## Corpus v2

The v1 results above are frozen. Corpus v2 is a separate, second run with its own pre-registered cases. It turns v1's misses into things a test can see:

- **Unexpected routes** (v1 cases 18 and 23): the v2 intent spec says infrastructure prefixes and a sentinel list of well-known third-party prefixes must never be BGP routes at the customer, the upstream or the peer. These are `route` checks with `present: false`; no new check type is needed.
- **Latent risks** (v1 cases 21 and 30): two failure scenarios use the [`inject_routes`](reference/config.md#injecting-routes) fault, which ships in Netdryrun 0.3.1, to make a neighbor misbehave. The customer floods 200 more-specifics from its own /16, and the peer announces a more-specific of our customer's space and a third-party /24. The checks then verify that the max-prefix limit and the import filter actually hold.
- **Rigid counts** (v1 case 06): announced-prefix counts are a range (2 to 51), so customer growth inside its block is not blocked.
- **Vendor defaults** (v1 case 12): the FRR no-op is labeled safe, and the genuinely harmful variant is a separate case.

v2 changes two lines in the base lab so the customer's max-prefix limit can actually trip: in v1 the customer filter allowed at most 7 prefixes, so a limit of 100 could never be reached. The differences, the written intent (I1 to I9) and the disclosures are in [v2/INTENT.md](https://github.com/netdryrun/Netdryrun/blob/main/corpus/v2/INTENT.md). The spec is [v2/specs/intent.yml](https://github.com/netdryrun/Netdryrun/blob/main/corpus/v2/specs/intent.yml).

**Pre-registration:** all 18 cases and their expected verdicts were committed and pushed in [`322cc4e`](https://github.com/netdryrun/Netdryrun/commit/322cc4ede21492c3914a0a53b67268bea7abf7d6) (2026-10-27 04:02 UTC), before any v2 case was deployed. Rerun it with `python corpus/run.py --corpus v2`.
