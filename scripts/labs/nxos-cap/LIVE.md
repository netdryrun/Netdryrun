# NX-OS live runs (beta gate)

The lab in this folder, on `vrnetlab/cisco_n9kv:9300-10.4.8.M` (NX-OS 10.4(8), built locally with vrnetlab, never redistributed), WSL2 Ubuntu 22.04, under the vendor-VM lab lock.

## Live runs, 2026-10-31 (Netdryrun 0.4.0 + branch ndr/nxos, WSL with 24 GB)

- **Fixture capture** (`scripts/capture_fixtures.sh nxos`, 330 s): this lab now has f3, a peer that sends nothing. Shape drift from 2026-10-30 is benign: an `advertisedto` table now that a third peer exists; VRF `EMPTY` answered `null` again (both shapes are kept and tested). New: `show vrf` lists NX-OS's own `egress-loadbalance-resolution-` VRF (left out of `record`); `show running-config bgp all` shows no advertisement interval (30 s assumed); vrnetlab's boot log (`Startup complete in: 0:04:23`).
- **Rejected startup lines** (`scripts/nxos_probe_rejected.sh`, 307 s): two bad lines in examples/nxos-frr's config. vrnetlab logged `RESULT:` with a caret line, then `% Invalid command at '^' marker.` for each; the driver now refuses such a run.
- **Live must-fail gate: met** (1,027 s): 16 must-fail on usable state and 14 controls, every check type, including **session up with zero prefixes** (f3: `min: 1` fails on `0 ipv4-unicast prefixes accepted`). Negative checks held 42 s: the 30 s advertisement interval stretched the windows.
- **examples/nxos-frr**: good configs passed 10/10 (358 s, first pass at 257 s); the leak failed exactly its two guards (377 s). Startup-config check clean on both.
- **Mutation** (mutmut on netdryrun.drivers.nxos.*, under the lock): 892 killed, 40 survived, all accepted with reasons in releases/0.4.1/accepted.json (20 message text only, 20 equivalent).

## Live must-fail gate, 2026-10-30 (Netdryrun 0.3.3 + branch ndr/nxos)

`PYTHONPATH=src python3 scripts/nxos_live_mustfail.py` on [`mustfail.yml`](mustfail.yml): **met**. 27 checks, 985 s including the boot.

| Check type | MUST FAIL (failed, on usable device state) | MUST PASS (passed) |
|---|---|---|
| `bgp_session` | idle neighbor expected established (`state is idle`); up session expected down (`state is established`) | session to f1; session in VRF RED; configured neighbor 10.0.9.9 down |
| `bgp_prefixes` | over max, under min (`3 ipv4-unicast prefixes accepted`); IPv6 over max (`1 ipv6-unicast`) | exactly 3 accepted; exactly 1 IPv6 |
| `route` | leaked default received but not installed (`unexpectedly present via bgp (not selected)`); denied prefix expected present; wrong protocol | 192.168.20.0/24 via bgp; default via static; denied prefix absent |
| `bgp_route` | leaked default in the BGP table; wrong local-pref (200 seen); missing community; forbidden large community; wrong AS path in VRF RED | best-path attributes (AS path, local-pref 200, MED 50, next hop, communities); prepended path in VRF RED |
| `ping` | unreachable target (0/2); expected to fail but replies (3/3) | from the loopback; in VRF RED |

## Fixture re-capture, 2026-10-30

`scripts/capture_fixtures.sh nxos` (407 s): 48 outputs. 46 have the committed shape. Two differ: in this boot, VRF `EMPTY` (it exists, no routes) answered `show ip route ... vrf EMPTY` with `"result": null`, where the 2026-10-28 boot answered an empty table. Both are kept (`nxos_*_emptyvrf.txt`, `nxos_*_emptyvrf_null.txt`); the driver confirms the VRF with `show vrf` before it trusts "nothing", so both read as a real absence, and the same "nothing" for a VRF that doesn't exist raises.

## Earlier

- 2026-10-28: the first capture (this lab, 48 outputs, `tests/fixtures/nxos_captures.tsv`); `examples/nxos-frr` good configs 10/10 passed, the leak variant failed exactly its two leak guards.
