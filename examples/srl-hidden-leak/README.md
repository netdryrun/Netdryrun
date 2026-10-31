# The route leak ping can't see

A peer starts sending you a default route it shouldn't. The BGP session stays up, every ping works, and the default route in your routing table is still your own. Nothing breaks, so nothing alerts.

The leaked route hasn't gone anywhere, though. It sits in the BGP table, valid, one step from being used. The day your own default goes away (a link fails, someone cleans up a static), all traffic with no more specific route goes to that peer.

This lab shows that on **Nokia SR Linux** and **FRR**: how the leak happens, how to see it by hand on each, why the usual checks miss it, and a check that catches it before the change ships.

## The lab

```text
   srl1  (SR Linux, AS 65010)                    frr1  (FRR, AS 65020)
   lo0 192.168.10.1/32                           lo 192.168.20.1/24
   static 0.0.0.0/0 -> discard                   static 0.0.0.0/0 -> blackhole
        e1-1 10.0.100.1/30 ------- eBGP ------- eth1 10.0.100.2/30
```

- Each router exports only its own LAN: on SR Linux an `export-own` policy that matches a prefix set, on FRR an `EXPORT-OWN` route-map that matches a prefix list.
- Each router accepts whatever the peer sends (`accept-all` / `ACCEPT-ALL`), like many configs that rely on the other side's export policy.
- Each router has its own static default. In this lab it points at a discard route, standing in for "the upstream", so the lab stays at two nodes.

You need containerlab, and the images `ghcr.io/nokia/srlinux:26.7.2` (about 3.2 GB) and `quay.io/frrouting/frr:10.4.1`.

```bash
cd examples/srl-hidden-leak
containerlab deploy -t topology.clab.yml     # with sudo, unless your user is in clab_admins
docker exec -it clab-ndr-hidden-leak-srl1 sr_cli
docker exec -it clab-ndr-hidden-leak-frr1 vtysh
containerlab destroy -t topology.clab.yml --cleanup
```

On WSL2, deploy from the Linux filesystem (`~/...`), not `/mnt/c`: SR Linux can't save its startup config on a Windows drive.

## Two one-line leaks

[`leaks/`](leaks/) holds the same two configs, each with one change. Both are common shortcuts.

**FRR: `default-originate` toward the wrong neighbor** ([`leaks/frr1.conf`](leaks/frr1.conf)):

```diff
   neighbor 10.0.100.1 route-map EXPORT-OWN out
+  neighbor 10.0.100.1 default-originate
```

The outbound route-map only permits `192.168.20.0/24`, and the default goes out anyway: FRR generates it outside the outbound route-map. If you need a conditional default, that's what `default-originate route-map NAME` is for.

**SR Linux: export statics without a prefix match** ([`leaks/srl1.cli`](leaks/srl1.cli)):

```diff
 set / routing-policy policy export-own statement lan action policy-result accept
+set / routing-policy policy export-own statement statics match protocol static
+set / routing-policy policy export-own statement statics action policy-result accept
```

Meant to export one customer's static route, it exports every static, the default included.

To try one, copy it over the good config and redeploy, from `examples/srl-hidden-leak`. `git checkout configs/` puts the good ones back.

```bash
cp leaks/frr1.conf configs/frr1.conf
containerlab deploy -t topology.clab.yml --reconfigure
```

## Why nothing looks wrong

Each router already has a default route with a better preference than BGP: on SR Linux a static has preference 5 and BGP 170; on FRR a static has distance 1 and eBGP 20. So the leaked default is received, it is valid, and it loses. The routing table, and so the forwarding table, keeps the static.

| What you watch | With the leak |
|---|---|
| BGP session state | `established` |
| Ping between the LANs | works |
| "A default route exists" | yes, the static, as before |
| Routes in the forwarding table | unchanged |
| Prefixes received from the peer | 2 instead of 1: well under any max-prefix limit |

Every row is green. To see the leak you have to look at the BGP table, or at the routing table's losing entries.

## See it on FRR (the SR Linux leak)

The quickest tell is a BGP route without `>*` (not selected, not in the FIB):

```text
frr1# show ip route bgp
...
       > - selected route, * - FIB route, q - queued, r - rejected, b - backup

IPv4 unicast VRF default:
B   0.0.0.0/0 [20/0] via 10.0.100.1, eth1, weight 1, 00:01:32
B>* 192.168.10.1/32 [20/0] via 10.0.100.1, eth1, weight 1, 00:01:32
```

`show ip route 0.0.0.0/0` lists every candidate. The static is `best`; the BGP one waits:

```text
frr1# show ip route 0.0.0.0/0
Routing entry for 0.0.0.0/0
  Known via "bgp", distance 20, metric 0
  Last update 00:01:32 ago
    10.0.100.1, via eth1, weight 1

Routing entry for 0.0.0.0/0
  Known via "static", distance 1, metric 0, best
  Last update 00:02:17 ago
  * unreachable (blackhole), weight 1
```

Careful with the BGP table itself: there the leaked default is `*>`, BGP's best path, because the static it loses to isn't a BGP path. `show bgp ipv4 unicast` looks perfectly normal (header trimmed):

```text
frr1# show bgp ipv4 unicast
     Network          Next Hop            Metric LocPrf Weight Path
 *>  0.0.0.0/0        10.0.100.1                             0 65010 ?
 *>  192.168.10.1/32  10.0.100.1                             0 65010 i
 *>  192.168.20.0/24  0.0.0.0(frr1)            0         32768 i
```

## See it on SR Linux (the FRR leak)

The neighbor summary already hints at it: 2 routes received, 1 active.

```text
srl1# show network-instance default protocols bgp neighbor
| Net-Inst | Peer       | Group | Flags | Peer-AS | State       | Uptime       | AFI/SAFI [Rx/Active/Tx] |
| default  | 10.0.100.2 | ebgp  | S     | 65020   | established | 0d:0h:1m:56s | ipv4-unicast [2/1/1]    |
```

(Spacing trimmed.) The route table shows no trace of the leak: on SR Linux it only holds the route that won.

```text
srl1# show network-instance default ipv4 route 0.0.0.0/0
Prefix               Route Type   Metric   Pref    Flags    Next-Hop(s)
0.0.0.0/0            static       1        5       >        discard
```

The BGP RIB has it, valid (`*`) but not used (`u`) and not best (`>`):

```text
srl1# show network-instance default protocols bgp routes ipv4 summary
Status codes: u=used, *=valid, >=best, x=stale, b=backup, w=unused-weight-only
|  Status   |   Network          |   Next Hop    |  MED  | LocPref | Path Val  |
| u*>       | 0.0.0.0/0          | 0.0.0.0       |       |         |  ?        |
| *         | 0.0.0.0/0          | 10.0.100.2    | -     |         |  i[65020] |
| u*>       | 10.0.100.0/30      | 0.0.0.0       |       |         |  i        |
| u*>       | 192.168.10.1/32    | 0.0.0.0       |       |         |  i        |
| u*>       | 192.168.20.0/24    | 10.0.100.2    | -     |         |  i[65020] |
```

(Spacing trimmed.) The rows with next hop `0.0.0.0` are not leaks: SR Linux lists its own static and local routes in the BGP RIB as locally originated paths, whether or not the export policy advertises them (`10.0.100.0/30` is listed and never sent). The leak is the row whose next hop is the peer.

For one prefix, with both paths spelled out (output trimmed):

```text
srl1# show network-instance default protocols bgp routes ipv4 prefix 0.0.0.0/0
Network: 0.0.0.0/0
Received Paths: 2
  Path 1: <Best,Valid,Used,>
    Route source    : neighbor 0.0.0.0
    BGP next-hop    : 0.0.0.0
    Path            :  ?
  Path 2: <Valid,>
    Route source    : neighbor 10.0.100.2
    BGP next-hop    : 10.0.100.2
    Path            :  i [65020]
```

## One failure away

Take away the static default and the leak takes over, with no BGP update and no log line. On SR Linux, with `leaks/frr1.conf` applied:

```text
srl1# enter candidate
srl1# delete / network-instance default static-routes route 0.0.0.0/0
srl1# commit now
srl1# show network-instance default ipv4 route 0.0.0.0/0
Prefix               Route Type   Metric   Pref    Flags    Next-Hop(s)
0.0.0.0/0            bgp          0        170     >        10.0.100.2(route:local)
```

On FRR, with `leaks/srl1.cli` applied: `conf t`, then `no ip route 0.0.0.0/0 blackhole`:

```text
frr1# show ip route 0.0.0.0/0
Routing entry for 0.0.0.0/0
  Known via "bgp", distance 20, metric 0, best
  Last update 00:01:34 ago
  * 10.0.100.1, via eth1, weight 1
```

In this lab the peer just drops the traffic. In a real network, every packet without a more specific route now goes to a peer that never agreed to carry it.

## Catch it before it ships

The check that catches this asks the BGP table, not the routing table: **there is no BGP path for `0.0.0.0/0` at all, best or not, used or not.** By hand that's the commands above. In CI, this lab uses [Netdryrun](https://github.com/netdryrun/Netdryrun), an open-source tool that deploys a containerlab topology, runs checks like these and destroys it. [`netdryrun.yml`](netdryrun.yml) has the checks monitoring would usually run, plus one leak guard per router:

```yaml
  - type: bgp_route    # no BGP path for 0.0.0.0/0, selected or not
    node: srl1
    prefix: 0.0.0.0/0
    present: false
```

`bgp_route` reads the BGP table (FRR: `show bgp ... json`; SR Linux: the BGP RIB, counting only paths learned over BGP, so the router's own static isn't mistaken for a leak). A `present: false` check runs after the network has converged and must hold for 10 seconds.

```bash
pip install "netdryrun>=0.3.1"   # see "Version" below
netdryrun run examples/srl-hidden-leak   # from the repository root
```

The good configs pass all 9 checks:

```text
  [PASS] srl1: route 0.0.0.0/0 via static is present -- active via static (10.1s)
  [PASS] frr1: route 0.0.0.0/0 via static is present -- active via static (10.1s)
  [PASS] srl1: BGP session to 10.0.100.2 is established -- state is established (28.3s)
  [PASS] frr1: BGP session to 10.0.100.1 is established -- state is established (28.3s)
  [PASS] srl1: route 192.168.20.0/24 via bgp is present -- active via bgp (28.3s)
  [PASS] frr1: route 192.168.10.1/32 via bgp is present -- active via bgp (33.6s)
  [PASS] srl1: ping 192.168.20.1 from 192.168.10.1 expects success -- 3/3 replies (need 2) (33.6s)
Convergence checks done; settling 10s before post-convergence checks...
  [PASS] srl1: no BGP path for 0.0.0.0/0 -- no BGP path (held 11s, 4 samples) (10.8s)
  [PASS] frr1: no BGP path for 0.0.0.0/0 -- no BGP path (held 11s, 4 samples) (10.8s)
PASSED: 9 passed, 0 failed (9 checks)
```

To run a leak, copy its file over the good config, run, and put the good config back:

```bash
cp examples/srl-hidden-leak/leaks/frr1.conf examples/srl-hidden-leak/configs/frr1.conf
netdryrun run examples/srl-hidden-leak
git checkout examples/srl-hidden-leak/configs/
```

With the FRR leak, everything monitoring would watch still passes, and the guard on srl1 fails:

```text
  [FAIL] srl1: no BGP path for 0.0.0.0/0 -- unexpectedly in the BGP table (1 path(s); as-path '65020', next hop 10.0.100.2, local-pref 100, MED 0, communities none) (2.4s)
  [PASS] frr1: no BGP path for 0.0.0.0/0 -- no BGP path (held 10s, 4 samples) (10.2s)
FAILED: 8 passed, 1 failed (9 checks)
```

With the SR Linux leak (`leaks/srl1.cli` over `configs/srl1.cli`), it's the guard on frr1:

```text
  [PASS] srl1: no BGP path for 0.0.0.0/0 -- no BGP path (held 11s, 4 samples) (10.8s)
  [FAIL] frr1: no BGP path for 0.0.0.0/0 -- unexpectedly in the BGP table (1 path(s); as-path '65010', next hop 10.0.100.1, local-pref 100, MED 0, communities none) (0.8s)
FAILED: 8 passed, 1 failed (9 checks)
```

Exit code `0` for the pass, `1` for each fail, so a CI job fails on the leak. Wall-clock for `netdryrun run`, including deploying and destroying the lab, with images already pulled. Measured on 2026-10-27 on WSL2 (20 cores, 16 GB), containerlab 0.81.1, SR Linux 26.7.2, FRR 10.4.1, Netdryrun 0.3.0 plus the SR Linux fix (released in 0.3.1). Three rounds: the first from the development worktree, then two from a fresh clone following this README (the last on commit `1cbef33`):

| Run | Result | Exit | Times |
|---|---|---|---|
| Good configs | `PASSED: 9 passed, 0 failed` | `0` | 84 s; 60 s and 58 s; 61 s |
| FRR leak (`leaks/frr1.conf`) | `FAILED: 8 passed, 1 failed` | `1` | 80 s; 57 s; 52 s |
| SR Linux leak (`leaks/srl1.cli`) | `FAILED: 8 passed, 1 failed` | `1` | 55 s; 59 s; 60 s |

Most of the difference between runs is how long SR Linux takes to bring BGP up (14 to 34 s in these runs).

**Version:** on SR Linux this lab needs Netdryrun 0.3.1 or later. SR Linux lists the router's own static default in its BGP RIB, and Netdryrun 0.3.0 counts it as a BGP path, so the good configs fail the srl1 guard. The times above were measured with 0.3.0 plus that fix, before 0.3.1 was released.

Other ways to guard this: a `bgp_prefixes` check with `exact: 1` also fails here, but it breaks on every legitimate new prefix. And the config-side fix belongs on both ends: export only what you mean to (the sender), and reject a default from peers that should never send one (an import policy at the receiver).

## Gotchas found while building this lab

- **containerlab gives `linux` nodes a default route via the management network.** FRR sees it as a kernel route with distance 0, which beats any static or BGP default. In a lab that means a leaked default can never become active, and your own static default never wins either. [`topology.clab.yml`](topology.clab.yml) removes it on frr1 with `exec: ip route del default`. SR Linux keeps management in its own `mgmt` network-instance, so it doesn't have this problem.
- **SR Linux has no `blackhole` keyword on a static route.** A discard route is a next-hop group with `blackhole`, as in [`configs/srl1.cli`](configs/srl1.cli).
- **SR Linux 26.7's route-table report** is `show network-instance default ipv4 route <prefix>`.
- **The SR Linux BGP RIB lists local and static routes** as locally originated paths (next hop `0.0.0.0`) even when they aren't exported. Don't count those rows as received routes.

## Files

| File | What it is |
|---|---|
| [`topology.clab.yml`](topology.clab.yml) | containerlab topology: srl1 and frr1, one link |
| [`configs/`](configs/) | The good configs |
| [`leaks/`](leaks/) | The same configs, each with one leak |
| [`netdryrun.yml`](netdryrun.yml) | The checks: 7 that pass with or without a leak, and 2 leak guards |
