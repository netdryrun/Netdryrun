# MikroTik RouterOS 7 and FRR: a leak RouterOS receives but never uses

**The RouterOS driver is beta, and not released yet.** It ships in the first release whose full release gate it passes; until then it is in the code on this branch only.

A MikroTik RouterOS 7.23 router (CHR) peers eBGP with FRR. FRR starts sending a default route it shouldn't. On r1 the session stays up, the ping works, and the active default route is still r1's own static: the leaked default is received and is BGP's best path, but it loses the routing table to the static (distance 1 against eBGP's 20). The day the static goes away, all traffic without a more specific route goes to the peer.

```text
   r1  (RouterOS, AS 65010)                      frr1  (FRR, AS 65020)
   lo 192.168.10.1/32                            lo 192.168.20.1/24
   static 0.0.0.0/0 -> blackhole                 static 0.0.0.0/0 -> blackhole
        ether2 10.0.100.1/30 ---- eBGP ---- eth1 10.0.100.2/30
```

## The image (bring your own)

The CHR image can't be redistributed, and MikroTik's licence allows one copy per computer: download the CHR VMDK from [mikrotik.com/download](https://mikrotik.com/download) (Cloud Hosted Router; accept MikroTik's terms yourself; this example was run with `chr-7.23.8.vmdk`, RouterOS 7.23.8 long-term) and build a containerlab image with [vrnetlab](https://github.com/srl-labs/vrnetlab):

```bash
git clone --depth 1 https://github.com/srl-labs/vrnetlab
cp chr-7.23.8.vmdk vrnetlab/mikrotik/routeros/
cd vrnetlab/mikrotik/routeros && make docker-image     # -> vrnetlab/mikrotik_routeros:7.23.8
```

The free CHR licence level limits throughput to 1 Mbps per interface, which does not matter for these checks. Use **one CHR node per lab** (the licence terms for several are not confirmed). The host needs KVM (`/dev/kvm`); the VM uses 256 MB of RAM.

## Run it

```bash
netdryrun run examples/mikrotik
```

The router's REST API answers before the startup config is imported, and RouterOS stops an import at its first error, so a router that rejected a line of its config looks healthy with no BGP. The checks wait for BGP like any other session (`timeout: 600`).

Measured on WSL2 (Ubuntu 22.04, 20 threads, 24 GB for WSL), 2026-10-30, Netdryrun from the `ndr/mikrotik` branch, RouterOS 7.23.8, one run each:

| Run | Result | First check passed after deploy | Whole run |
|---|---|---|---|
| Good configs | passed, 10 of 10 | 52 s | 96 s |
| With [`leaks/frr1.conf`](leaks/frr1.conf) | failed, 8 passed, 2 failed | 52 s | 95 s |

## The leak

[`leaks/frr1.conf`](leaks/frr1.conf) adds one line to FRR, a common shortcut:

```diff
   neighbor 10.0.100.1 route-map EXPORT-OWN out
+  neighbor 10.0.100.1 default-originate
```

The outbound route-map only permits `192.168.20.0/24`, and the default goes out anyway: FRR generates it outside the outbound route-map. To try it, copy it over `configs/frr1.conf` and run again; `git checkout configs/` puts the good one back.

## What Netdryrun saw

With the leak (real output):

```text
  [PASS] r1: BGP session to 10.0.100.2 is established -- state is established
  [PASS] r1: ping 192.168.20.1 from 192.168.10.1 expects success -- 3/3 replies (need 2)
  [FAIL] r1: route 0.0.0.0/0 via bgp is absent -- unexpectedly present via bgp (not selected)
  [FAIL] r1: no BGP path for 0.0.0.0/0 -- unexpectedly in the BGP table (1 path(s); as-path '65020', next hop 10.0.100.2, local-pref not set, MED 0, communities none)
FAILED: 8 passed, 2 failed (10 checks)
```

Every session was up and every address answered; only the two leak guards caught it.

## What this driver does not do (yet)

It refuses, with a clear message, rather than answer: IPv6 sessions and routes, ping inside a VRF, failure scenarios (`link_down`, `node_isolated`) on a RouterOS node, and any route row with a key or value it does not know (graceful-restart stale marks included). It counts accepted prefixes from the routing route table, not from the session's own `prefix-count`, which includes prefixes an input filter rejected. A path with no LOCAL_PREF attribute reports `local-pref not set`, so a `local_pref` check on it fails rather than guessing the default.
