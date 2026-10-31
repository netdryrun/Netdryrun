# Juniper and FRR: the route leak ping can't see (beta driver)

The [hidden-leak lab](../srl-hidden-leak/) on **Juniper cJunosEvolved** instead of SR Linux. A peer starts sending a default route it shouldn't. The session stays up, ping works, and the default route in use is still your own static, so nothing alerts. The leaked route sits in Junos's routing table as an inactive BGP route, one failure away from carrying all traffic with no more specific route.

The `junos` driver is **beta**: it is tested against output captured from a live cJunosEvolved 26.2R1.7-EVO lab, and this example runs on it live, but it isn't in a release yet and hasn't run on a hosted CI runner. See the [driver reference](../../website/docs/reference/junos.md).

## The lab

```text
   j1  (cJunosEvolved, AS 65010)                 frr1  (FRR, AS 65020)
   lo0 192.168.10.1/32, 2001:db8:10::1/128       lo 192.168.20.1/24, 2001:db8:20::1/48
   static 0.0.0.0/0 discard                      static 0.0.0.0/0 blackhole
        et-0/0/0 10.0.100.1/30 ------ eBGP ------ eth1 10.0.100.2/30
                 2001:db8:100::1/64               2001:db8:100::2/64
```

- Each router exports only its own LAN (Junos: an `EXPORT-OWN` policy with route filters; FRR: an `EXPORT-OWN` route-map that also sets community `65020:100`, large community `65020:1:1` and MED 50).
- Each router accepts whatever the peer sends (`ACCEPT-ALL`).
- Each router has its own static default, standing in for "the upstream".

You need containerlab, a host with KVM and about 10 GB of free memory, and the images `cjunosevolved:26.2R1.7-EVO` (free from Juniper for non-production labs; download it yourself and `docker load` it, it can't be redistributed) and `quay.io/frrouting/frr:10.4.1`.

```bash
cd examples/junos-frr
containerlab deploy -t topology.clab.yml     # with sudo, unless your user is in clab_admins
docker exec -it clab-ndr-junos-frr-j1 cli    # Junos answers after a few minutes
docker exec -it clab-ndr-junos-frr-frr1 vtysh
containerlab destroy -t topology.clab.yml --cleanup
```

cJunosEvolved boots a VM, which installs Junos and reboots on every deploy. On a quiet host Junos answered about 4 minutes after deploy and BGP was up after about 6; with a CPU-heavy job running next to it, 18 and 21 minutes. `CPTX_NUM_IF: "1"` in the topology tells the container how many data links to expect; without it, it waits 5 minutes for 36.

## Two one-line leaks

[`leaks/`](leaks/) holds the same two configs, each with one change.

**FRR: `default-originate` toward the wrong neighbor** ([`leaks/frr1.conf`](leaks/frr1.conf)):

```diff
   neighbor 10.0.100.1 route-map EXPORT-OWN out
+  neighbor 10.0.100.1 default-originate
```

FRR generates the default outside the outbound route-map, so the filter doesn't stop it.

**Junos: export statics without a prefix match** ([`leaks/j1.cfg`](leaks/j1.cfg)):

```text
j1# show | compare
[edit policy-options policy-statement EXPORT-OWN]
     term lan { ... }
+    term statics {
+        from protocol static;
+        then accept;
+    }
     term rest { ... }
```

Meant to export one customer's static route, it exports every static, the default included.

## Why nothing looks wrong

The static default has preference 5 on Junos, BGP 170. So the leaked default is received, accepted, and inactive. Junos's routing table lists both; the forwarding table keeps the static:

```text
j1> show route 0.0.0.0/0 exact

inet.0: 5 destinations, 6 routes (5 active, 0 holddown, 0 hidden)
+ = Active Route, - = Last Active, * = Both

0.0.0.0/0          *[Static/5] 00:04:15
                       Discard
                    [BGP/170] 00:01:31, MED 0, localpref 100
                      AS path: 65020 I, validation-state: unverified
                    >  to 10.0.100.2 via et-0/0/0.0
```

`detail` says why the BGP route waits (output trimmed):

```text
j1> show route 0.0.0.0/0 exact detail
0.0.0.0/0 (2 entries, 1 announced)
        *Static Preference: 5
                State: <Active Int Ext>
         BGP    Preference: 170/-101
                Source: 10.0.100.2
                State: <Ext Changed>
                Inactive reason: Route Preference
                AS path: 65020 I
                Accepted
```

The forwarding table only has the static's discard route, and the neighbor summary shows 2 routes received, 1 active, well under any max-prefix limit (headers trimmed):

```text
j1> show bgp summary
Peer                     AS      InPkt     OutPkt    OutQ   Flaps Last Up/Dwn State|#Active/Received/Accepted/Damped...
10.0.100.2            65020         34         37       0       0        1:35 Establ
  inet.0: 1/2/2/0
2001:db8:100::2       65020         31         34       0       0        1:29 Establ
  inet6.0: 1/1/1/0
```

| What you watch | With the leak |
|---|---|
| BGP session state | `Establ` |
| Ping between the LANs | works |
| "A default route exists" | yes, the static, as before |
| Routes in the forwarding table | unchanged |
| Prefixes received from the peer | 2 instead of 1 |

## Catch it before it ships

[`netdryrun.yml`](netdryrun.yml) has the checks monitoring usually runs (sessions, prefix counts, routes, the BGP attributes of frr1's LAN, ping) plus one leak guard per router: no BGP path for `0.0.0.0/0` at all, selected or not.

```yaml
  - type: bgp_route    # no BGP path for 0.0.0.0/0, selected or not
    node: j1
    prefix: 0.0.0.0/0
    present: false
```

On Junos the guard reads `show route 0.0.0.0/0 exact table inet.0 all extensive | display json`: active, inactive and hidden routes. A route that Junos hides because its next hop is unusable still counts (it was received); one that an import policy rejected doesn't (it can never be used), so filtering the leak on the way in makes the guard pass.

```bash
netdryrun run examples/junos-frr   # from the repository root
```

The good configs pass all 13 checks (exit code `0`):

```text
Netdryrun 0.3.1: 13 checks from netdryrun.yml
Deploying lab ndr-junos-frr (2 nodes); this usually takes 30-90 s, longer the first time images are pulled...
  [PASS] frr1: route 0.0.0.0/0 via static is present -- active via static (66.3s)
  [PASS] j1: route 0.0.0.0/0 via static is present -- active via static (250.9s)
  [PASS] j1: BGP session to 10.0.100.2 is established -- state is established (340.8s)
  [PASS] frr1: BGP session to 10.0.100.1 is established -- state is established (340.8s)
  [PASS] j1: route 192.168.20.0/24 via bgp is present -- active via bgp (340.8s)
  [PASS] frr1: route 192.168.10.1/32 via bgp is present -- active via bgp (340.8s)
  [PASS] j1: ping 192.168.20.1 from 192.168.10.1 expects success -- 3/3 replies (need 2) (340.8s)
  [PASS] j1: BGP session to 2001:db8:100::2 is established -- state is established (348.6s)
  [PASS] j1: route 2001:db8:20::/48 via bgp is present -- active via bgp (348.6s)
Convergence checks done; settling 10s before post-convergence checks...
  [PASS] j1: prefixes from 2001:db8:100::2 <= 10 -- 1 ipv6-unicast prefixes accepted (held 11s, 3 samples) (11.1s)
  [PASS] j1: BGP best path for 192.168.20.0/24 has communities 65020:100 65020:1:1, as-path '65020', local-pref 100, MED 50, next hop 10.0.100.2 -- best path: as-path '65020', next hop 10.0.100.2, local-pref 100, MED 50, communities 65020:100 65020:1:1 (held 11s, 3 samples) (11.1s)
  [PASS] j1: no BGP path for 0.0.0.0/0 -- no BGP path (held 11s, 3 samples) (11.1s)
  [PASS] frr1: no BGP path for 0.0.0.0/0 -- no BGP path (held 11s, 3 samples) (11.1s)
Destroying lab...
PASSED: 13 passed, 0 failed (13 checks)
```

To run a leak, copy its file over the good config, run, and put the good config back:

```bash
cp examples/junos-frr/leaks/frr1.conf examples/junos-frr/configs/frr1.conf
netdryrun run examples/junos-frr
git checkout examples/junos-frr/configs/
```

With the FRR leak, everything monitoring would watch still passes, and the guard on j1 fails (exit code `1`; passing lines trimmed):

```text
  [PASS] j1: BGP best path for 192.168.20.0/24 has communities 65020:100 65020:1:1, as-path '65020', local-pref 100, MED 50, next hop 10.0.100.2 -- best path: as-path '65020', next hop 10.0.100.2, local-pref 100, MED 50, communities 65020:100 65020:1:1 (held 14s, 2 samples) (13.5s)
  [FAIL] j1: no BGP path for 0.0.0.0/0 -- unexpectedly in the BGP table (1 path(s); as-path '65020', next hop 10.0.100.2, local-pref 100, MED 0, communities none) (9.1s)
  [PASS] frr1: no BGP path for 0.0.0.0/0 -- no BGP path (held 14s, 2 samples) (13.5s)
FAILED: 12 passed, 1 failed (13 checks)
```

With the Junos leak, it's the guard on frr1:

```text
  [PASS] j1: no BGP path for 0.0.0.0/0 -- no BGP path (held 12s, 3 samples) (12.3s)
  [FAIL] frr1: no BGP path for 0.0.0.0/0 -- unexpectedly in the BGP table (1 path(s); as-path '65010', next hop 10.0.100.1, local-pref 100, MED 0, communities none) (4.2s)
FAILED: 12 passed, 1 failed (13 checks)
```

Measured on 2026-10-28 on WSL2 (20 threads, 16 GB), containerlab 0.81.1, cJunosEvolved 26.2R1.7-EVO, FRR 10.4.1, Netdryrun 0.3.1 plus the unreleased `junos` driver (branch `ndr/junos`). Wall-clock includes deploying and destroying the lab:

| Run | Result | Exit | Time |
|---|---|---|---|
| Good configs | `PASSED: 13 passed, 0 failed` | `0` | 398 s |
| FRR leak (`leaks/frr1.conf`) | `FAILED: 12 passed, 1 failed` | `1` | 1385 s (a CPU-heavy job was running on the host; j1 took 1114 s to answer) |
| Junos leak (`leaks/j1.cfg`) | `FAILED: 12 passed, 1 failed` | `1` | 985 s (j1 took 756 s to answer); also 56 s with `netdryrun check` on the lab kept from the FRR-leak run, reconfigured through the CLI |

Boot time varies most: the same lab had Junos answering after 251 s on a quiet host and after 756 s and 1114 s on a busier one.
