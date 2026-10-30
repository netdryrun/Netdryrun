# NX-OS live runs (beta gate)

The lab in this folder, on `vrnetlab/cisco_n9kv:9300-10.4.8.M` (NX-OS 10.4(8), built locally with vrnetlab, never redistributed), WSL2 Ubuntu 22.04, under the vendor-VM lab lock.

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
