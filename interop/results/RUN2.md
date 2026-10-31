# Interop run 2 on 3ca6145: report

Status: **in progress** (L1 and L1s8 done; L2 running). Updated at the end of the run.

## Answer to the coordinator: false-pass paths for IOP-6 and IOP-7 (both are BLOCKER)

Shown on the live-captured shapes with `interop/tools/false_pass_probe.py` (evaluators on 3ca6145):

**IOP-6 (SR Linux keeps an import-rejected route in its local RIB): BLOCKER.**
- `route 192.168.6.0/24 protocol: bgp active: false` on s1 **passes**: "present via bgp (not selected)". The route
  was rejected by s1's import policy. FRR and EOS keep no path, so the same check fails there, and the reference says
  a route an import policy rejected is not received.
- These checks behave correctly and fail: `route` (default `active: true`), `bgp_route` best-path exists, and any
  `bgp_route` attribute (no best path: SR Linux marks the route `best-route: false`, `invalid-reason: rejected-route`).
- Prefix counts are not overcounted: live M07, C26 read 206 = 207 received − 1 rejected (SR Linux summary
  `[207/206/1]`), so a `min:` can't be pushed over by rejected routes.
- Regression test: `test_srl_route_rejected_by_import_policy_does_not_satisfy_active_false` (fails on 3ca6145).

**IOP-7 (Junos count leaves out a received route with an unusable next hop): BLOCKER.**
- Live M09: Junos received 206, accepted 205 ("Hidden reason: Protocol nexthop is not on the interface"). The
  reference count (received minus rejected by import policy) is 206.
- So `bgp_prefixes max: 205` and `exact: 205` on j1 **pass** where the reference count fails them: a count guard misses
  an extra received route whose next hop Junos can't use. SR Linux, EOS and FRR count it.
- A `present: false` guard on the prefix itself still catches it (R01 failed in M09: hidden routes count as present).
- Regression test: `test_junos_undercount_does_not_pass_an_upper_bound_the_reference_count_breaks` (fails on 3ca6145).

Per the coordinator ("state the answer in RUN2.md with the evidence, then keep going"), the run continues.
