# Cisco NX-OS and FRR: a leak NX-OS receives but never uses

**The NX-OS driver is beta.** It ships in the first release whose full release gate it passes; until then it is in the code on this branch only.

A Cisco Nexus 9000v (NX-OS 10.4(8)) peers eBGP with FRR. FRR starts sending a default route it shouldn't. On n1 the session stays up, the ping works, and the default route in the routing table is still n1's own static: the leaked default is received, it is BGP's best path, and it loses the routing table to the static (distance 1 against eBGP's 20). The day the static goes away, all traffic without a more specific route goes to the peer.

```text
   n1  (NX-OS, AS 65010)                         frr1  (FRR, AS 65020)
   loopback0 192.168.10.1/32                     lo 192.168.20.1/24
   static 0.0.0.0/0 -> Null0                     static 0.0.0.0/0 -> blackhole
        Ethernet1/1 10.0.100.1/30 ---- eBGP ---- eth1 10.0.100.2/30
```

## The image (bring your own)

The Nexus 9000v can't be redistributed: download it from Cisco (software.cisco.com, "Nexus 9000v", file `nexus9300v64.10.4.8.M.qcow2`; a free Cisco account was enough for this version) and build a containerlab image with [vrnetlab](https://github.com/srl-labs/vrnetlab):

```bash
git clone --depth 1 https://github.com/srl-labs/vrnetlab
cp nexus9300v64.10.4.8.M.qcow2 vrnetlab/cisco/n9kv/n9kv-9300-10.4.8.M.qcow2
cd vrnetlab/cisco/n9kv && make docker-image        # -> vrnetlab/cisco_n9kv:9300-10.4.8.M (about 3 GB)
```

The host needs KVM (`/dev/kvm`) and about 10 GB of free RAM for the VM (vrnetlab's default; `QEMU_MEMORY: 8192` in the node's `env` also booted in our capture lab), plus 4 vCPUs.

## Run it

```bash
netdryrun run examples/nxos-frr
```

`timeout: 900` in [`netdryrun.yml`](netdryrun.yml) covers the boot: the VM boots for about 4 to 7 minutes, then vrnetlab types the startup config into it. The driver asks nothing until vrnetlab reports that config applied (`/health` reads `0 running`): before that every check sample says `NX-OS is not ready` and counts as "no usable state yet", never as "no sessions" or "no routes", and no check can pass on a half-configured switch. A startup-config line NX-OS rejects (vrnetlab logs `% Invalid command`) stops the run with an error naming the line: the lab would run without it.

Measured on WSL2 (Ubuntu 22.04, 20 threads, 24 GB for WSL), 2026-10-31, Netdryrun 0.4.0 plus the `ndr/nxos` branch:

| Run | Result | First check passed after deploy | Whole run |
|---|---|---|---|
| Good configs | passed, 10 of 10 | 257 s | 358 s |
| With [`leaks/frr1.conf`](leaks/frr1.conf) | failed, 8 passed, 2 failed | 281 s | 377 s |

NX-OS doesn't show the advertisement interval it applies, so the driver assumes 30 s (the usual Cisco eBGP default) and the settle and hold windows stretch to 32 s. The capture lab (`QEMU_MEMORY: 8192`, three FRR peers) logged `Startup complete in: 0:04:23` on 2026-10-31 (0:07:04 on 2026-10-28, with 16 GB for WSL); the container used 9.1 GiB.

## The leak

[`leaks/frr1.conf`](leaks/frr1.conf) adds one line to FRR, a common shortcut:

```diff
   neighbor 10.0.100.1 route-map EXPORT-OWN out
+  neighbor 10.0.100.1 default-originate
```

The outbound route-map only permits `192.168.20.0/24`, and the default goes out anyway: FRR generates it outside the outbound route-map.

To try it, copy it over the good config and run again; `git checkout configs/` puts the good one back.

## What Netdryrun saw

With the leak (real output):

```text
  [PASS] n1: BGP session to 10.0.100.2 is established -- state is established (281.4s)
  [PASS] n1: prefixes from 10.0.100.2 >= 1 -- 2 ipv4-unicast prefixes accepted (281.4s)
  [PASS] n1: route 192.168.20.0/24 via bgp is present -- active via bgp (281.4s)
  [PASS] n1: ping 192.168.20.1 from 192.168.10.1 expects success -- 3/3 replies (need 2) (281.4s)
  [PASS] n1: route 0.0.0.0/0 via static is present -- active via static (281.4s)
  [PASS] frr1: BGP session to 10.0.100.1 is established -- state is established (284.7s)
  [PASS] frr1: route 192.168.10.1/32 via bgp is present -- active via bgp (284.7s)
n1 (to 10.0.100.2) has an advertisement interval of 30s, so a route can arrive that late: settle and hold extended to at least 32s
Convergence checks done; settling 32s before post-convergence checks...
  [PASS] n1: BGP best path for 192.168.20.0/24 has as-path '65020', next hop 10.0.100.2 -- best path: as-path '65020', next hop 10.0.100.2, local-pref 100, MED not set, communities none (held 32s, 11 samples) (32.3s)
  [FAIL] n1: route 0.0.0.0/0 via bgp is absent -- unexpectedly present via bgp (not selected) (0.7s)
  [FAIL] n1: no BGP path for 0.0.0.0/0 -- unexpectedly in the BGP table (1 path(s); as-path '65020', next hop 10.0.100.2, local-pref 100, MED not set, communities none) (0.7s)
Destroying lab...
FAILED: 8 passed, 2 failed (10 checks)
```

Everything monitoring usually watches is green: the sessions, the ping, n1's own default route. Only the two leak guards fail. (The prefix count went from 1 to 2, so a `max: 1` on `bgp_prefixes` would catch it too; the `min: 1` check here doesn't.)

The good configs pass all ten, including both guards (`route 0.0.0.0/0 via bgp is absent -- absent (held 33s, 10 samples)` and `no BGP path for 0.0.0.0/0 -- no BGP path (held 33s, 10 samples)`).

## How the driver sees it

NX-OS runs in a VM inside the container, so the driver asks NX-API from inside the container (`show ... ` as JSON). For `0.0.0.0/0`, NX-OS lists both paths in the routing table; the BGP one has no `ubest` flag, so it isn't installed:

```text
"ipprefix": "0.0.0.0/0", ...
"ROW_path": [{"ifname": "Null0", "pref": 1, "clientname": "static", "ubest": "true"},
             {"ipnexthop": "10.0.100.2", "pref": 20, "clientname": "bgp-65010", "type": "external"}]
```

(trimmed). The BGP table marks the leaked path `"pathbest": "true"`. The driver reads the BGP table as well as the routing table, so a received path counts as present for `present: false` whether or not it was installed.

## Limits (beta)

- Checks read IPv4 and IPv6 unicast. EVPN prefix counts are refused before deploying (they would read 0).
- Link-failure scenarios on the NX-OS node are refused: the container's `eth1` only carries frames to the VM. Take the link down on the FRR side instead.
- `inject_routes` needs an FRR node, as on every other platform.
- NX-OS keeps no route rejected by inbound policy (without soft-reconfiguration), so a denied route is simply absent, and `bgp_prefixes` counts accepted routes (live: four sent, one denied, `prefixreceived` 3).
- `med: 0` is refused before deploying: NX-OS prints MED 0 for a path received with no MED, so the two can't be told apart. Check a non-zero MED.
- The advertisement interval is assumed to be 30 s (NX-OS doesn't show it); a larger configured `advertisement-interval` is not read, so raise `--settle` and `--hold` above it.
- Graceful restart: a stale path counts as present and best (NX-OS marks it `pathstaled`, which isn't read yet).
