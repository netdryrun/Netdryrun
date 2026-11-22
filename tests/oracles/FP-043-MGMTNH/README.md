# Oracle FP-043-MGMTNH: a route over Docker's default ends the run before the default is deleted

## The bug

Corpus v1 case 19 (next-hop-self removed on pe2 toward pe1, expected unsafe) ends in a run error for every strategy
since the corpus harness clears FRR's stuck import check, which lets peer1 announce 198.51.100.0/24 on every boot:

    pe1 has a route out over the management network (before the checks): 198.51.100.0/24 nhid 7 via 172.20.20.1 dev
    eth0 proto bgp metric 20

pe1 resolves next hops over a default (`Resolve via default: on`), and while Docker's default is there zebra prefers it
(kernel, distance 0) to up1's BGP default (distance 20). `mgmt.prepare_linux` reads the routes before it deletes
Docker's default and stops on a route that exists only because of that default. The release gate stops on any corpus
error.

## What the lab does (FRR 10.4.1, tests/fixtures/frr_mgmtnh, six fresh deploys; SOURCES.yml)

| Trial | Lab | After Docker's defaults are deleted |
|---|---|---|
| t1, t2, t3 | as case 19 | First read after `mgmt._delete_linux` returned (0.21-0.26 s after it began): route via 10.0.2.2 dev eth2 (up1's default), and so for all 60 s |
| t4 | as case 19, read inside the node every ~1 ms | On eth0 until 0.07 s (up1's default in the kernel at 0.01 s), then on eth2 for good |
| t5, t6 | up1 stops originating its default first | **Stays on eth0 for all 60 s.** zebra has no default left, but `show ip nht` keeps `10.0.4.2 resolved via kernel, prefix 0.0.0.0/0, via 172.20.20.1, eth0` |
| t1, t3 extras | kernel static and FRR static via 172.20.20.1 | Both stay on eth0 (15 s) |
| t1, t3 extras | Docker's IPv4 default put back by hand | The BGP route is back on eth0 at the first read (0.5 s) and up1's default leaves the kernel; deleting the default again moves it back to eth2 |

So the hypothesis holds only in part. A route over Docker's default re-resolves inside the lab once the default is
deleted, when the lab has a path for it (case 19: up1's default). When the lab has none, FRR 10.4.1 does not take the
route away: it keeps it on eth0 with a stale next-hop resolution. That stays a run error (a residual false fail, never a
false pass). SONiC VS was not run.

## The tests

- `test_oracle_fp_043_mgmtnh.py` (red until the fix): `mgmt.prepare` on the replayed case 19 state (t1-t4) ends
  without a run error, with Docker's two defaults recorded as removed and nothing left over management; on t4 read with
  no exec delay (inside zebra's 0.07 s), prepare waits with its `sleep` instead of judging the first read, and sleeps at
  most 30 s; `mgmt.describe` (the environment's `management_default`) names the route that left.
- `tests/test_oracle_guards_fp_043_mgmtnh.py` (green before and after): the statics stay a run error within the bound;
  t5/t6's BGP route still on eth0 is a run error within the bound; a route back on eth0 before a ping ends the run
  before the ping; Docker's default back before a ping is deleted again, recorded, and the ping runs.

## Fix design

1. **Order.** In `prepare_linux`, classify as now. If any route over management other than Docker's defaults can't
   have come from the default (proto static, kernel, boot or 196, a multipath leg, no via, no device, or no Docker
   default to delete), end the run at once and delete nothing, as today (tests/test_mgmt_exact.py pins that).
   Otherwise (only routing-protocol routes such as bgp, ospf or isis, via a management gateway, and Docker's default
   present) delete Docker's defaults first, then judge.
2. **Settle.** Re-read the table every 0.5 s through prepare's `sleep` (count the time slept, as `prepare_eos` does)
   until nothing but the connected management subnet is on the management device, for at most 10 s. Measured: 0.07 s
   in t4, and settled at the first read in t1-t3. 10 s is over 100 times that and equals the corpus settle. The stale
   case (t5, t6) never cleared in 60 s, so a longer bound only delays the same run error. Docker's default back during
   the wait is a run error (`repair=False`, as now).
3. **Record.** Add the routes that left after the delete to the node's `management_default`
   (`mgmt.describe`: "removed: <Docker's defaults>; left the management network once it was removed: <route lines>")
   and log the same line, so the run says why it went on.
4. **Still run errors.** Any static or kernel route via the management gateway or device. A routing-protocol route
   still on the management device after the bound (t5, t6). Its message should say that the route resolved only
   through Docker's default and the node kept it after the default was deleted. An unreadable table. Any route over
   management before a ping, around the hold or around a scenario. The rechecks (`check_linux` with repair) keep
   today's rule: Docker's default back together with another route is never repaired. Live, a re-added default pulls
   the BGP route back onto eth0 at once (t1, t3). Extending the repair there is allowed only with this same bounded
   rule, recorded in `readded`.
5. **After the fix.** Rerun every corpus case, not only 19, and read each changed verdict. Case 19 should come out
   unsafe from its checks (customer reaches peer fails), not from a run error.
