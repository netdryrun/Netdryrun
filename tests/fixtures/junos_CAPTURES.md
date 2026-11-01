# cJunosEvolved captures

Captured live on 2026-10-28 from `cjunosevolved:26.2R1.7-EVO` (containerlab 0.81.1, kind `juniper_cjunosevolved`, default BT flavour) in the lab `ndr-junos-cap`: j1 (AS 65001) peering eBGP with two FRR 10.4.1 routers, one session in routing-instance RED, one IPv6 session and one peer that never comes up. Each command ran as `docker exec <node> ssh ... root@176.1.1.1 "cli -c '<command>'"` (the container's own `cli -c` ignores its argument). Every command, errors included, exited 0. The image itself is never committed or redistributed.

| File | Command |
|---|---|
| `junos_bgp_neighbor.txt` | `show bgp neighbor instance master \| display json \| no-more` |
| `junos_bgp_neighbor_all_idle.txt` | `show bgp neighbor \| display json \| no-more` |
| `junos_bgp_neighbor_none.txt` | `show bgp neighbor instance NOPE \| display json \| no-more` |
| `junos_bgp_neighbor_red.txt` | `show bgp neighbor instance RED \| display json \| no-more` |
| `junos_error_syntax.txt` | `show bgp nonsense \| display json \| no-more` |
| `junos_instance_master.txt` | `show route instance master \| display json \| no-more` |
| `junos_instance_none.txt` | `show route instance NOPE \| display json \| no-more` |
| `junos_instance_red.txt` | `show route instance RED \| display json \| no-more` |
| `junos_ping.txt` | `ping 10.20.0.1 source 10.255.0.1 count 3 rapid \| display json \| no-more` |
| `junos_ping6.txt` | `ping 2001:db8:20::1 source 2001:db8:255::1 count 3 rapid \| display json \| no-more` |
| `junos_ping_badsource.txt` | `ping 10.20.0.1 source 10.123.0.1 count 3 rapid \| display json \| no-more` |
| `junos_ping_no_instance.txt` | `ping 10.40.0.1 count 3 rapid routing-instance NOPE \| display json \| no-more` |
| `junos_ping_noreply.txt` | `ping 10.0.1.3 count 3 rapid wait 1 \| display json \| no-more` |
| `junos_ping_unreachable.txt` | `ping 10.88.0.1 count 3 rapid \| display json \| no-more` |
| `junos_ping_vrf.txt` | `ping 10.40.0.1 source 10.255.1.1 count 3 rapid routing-instance RED \| display json \| no-more` |
| `junos_route_connected.txt` | `show route 10.0.1.0/30 exact table inet.0 all extensive \| display json \| no-more` |
| `junos_route_empty.txt` | `show route 10.88.0.0/24 exact table inet.0 all extensive \| display json \| no-more` |
| `junos_route_hidden_nexthop.txt` | `show route 10.31.0.0/24 exact table inet.0 all extensive \| display json \| no-more` |
| `junos_route_hidden_only_summary.txt` | `show route 10.30.0.0/24 exact table inet.0 extensive \| display json \| no-more` |
| `junos_route_hidden_policy.txt` | `show route 10.30.0.0/24 exact table inet.0 all extensive \| display json \| no-more` |
| `junos_route_leak.txt` | `show route 0.0.0.0/0 exact table inet.0 all extensive \| display json \| no-more` |
| `junos_route_local.txt` | `show route 10.0.1.1/32 exact table inet.0 all extensive \| display json \| no-more` |
| `junos_route_no_table.txt` | `show route 10.88.0.0/24 exact table NOPE.inet.0 all extensive \| display json \| no-more` |
| `junos_route_paths.txt` | `show route 10.20.0.0/24 exact table inet.0 all extensive \| display json \| no-more` |
| `junos_route_red.txt` | `show route 10.40.0.0/24 exact table RED.inet.0 all extensive \| display json \| no-more` |
| `junos_route_static.txt` | `show route 10.99.0.0/24 exact table inet.0 extensive \| display json \| no-more` |
| `junos_route_table.txt` | `show route table inet.0 \| display json \| no-more` |
| `junos_route_table_idle.txt` | `show route table inet.0 \| display json \| no-more` |
| `junos_route_table_red.txt` | `show route table RED.inet.0 \| display json \| no-more` |
| `junos_route_table_v6.txt` | `show route table inet6.0 \| display json \| no-more` |
| `junos_route_v6.txt` | `show route 2001:db8:20::/48 exact table inet6.0 all extensive \| display json \| no-more` |
| `junos_version.txt` | `show version \| display json \| no-more` |
| `junos_error_not_ready.txt` | `show bgp neighbor instance master \| display json \| no-more` (lab `ndr-junos-frr`, while rpd was starting) |
| `junos_error_not_ready_route.txt` | `show route 0.0.0.0/0 exact table inet.0 all extensive \| display json \| no-more` (same moment) |
| `junos_error_not_ready_ping.txt` | `ping 10.0.100.2 count 2 rapid wait 1 \| display json \| no-more` (same moment) |
| `junos_route_ibgp.txt` | `show route 10.50.0.0/24 exact table inet.0 all extensive \| display json \| no-more` (lab `ndr-junos-ibgp`: iBGP from FRR, next hop set to 10.60.0.1, reached by a static via 10.0.1.2) |
| `junos_route_ibgp_noexport.txt` | `show route 10.51.0.0/24 exact table inet.0 all extensive \| display json \| no-more` (same lab: community no-export, local-pref 200 set by the peer) |
| `junos_bgp_neighbor_ibgp.txt` | `show bgp neighbor instance master \| display json \| no-more` (same lab) |
| `junos_bgp_neighbor_outdelay.txt` | `show bgp neighbor instance master \| display json \| no-more` (2026-10-29, lab `ndr-cap-junos` = examples/junos-frr, with `set protocols bgp group frr1 out-delay 10`: the IPv4 peer shows `outbound-timer` 10) |
| `junos_instances.txt` | `show route instance \| display json \| no-more` (same lab, with routing-instance CUST added: master, CUST, mgmt_junos and two private instances) |
| `junos_bgp_neighbor_vrf_idle.txt` | `show bgp neighbor instance CUST \| display json \| no-more` (same lab: a CUST peer with no link, idle) |
| `junos_ping_vrf_local.txt` | `ping 10.77.0.1 source 10.77.0.1 count 3 rapid wait 1 routing-instance CUST \| display json \| no-more` (same lab) |
| `junos_route_no_med.txt` | `show route 192.168.3.1/32 exact table inet.0 all extensive \| display json \| no-more` (2026-10-31, interop lab `ndr-interop-l1`: an eBGP path FRR sent with no MED; no `metric` element) |
| `junos_route_med0.txt` | `show route 192.168.5.1/32 exact table inet.0 all extensive \| display json \| no-more` (same lab: FRR's own network route, sent with MED 0; `metric` "0") |
| `junos_bgp_neighbor_hidden_nexthop.txt` | `show bgp neighbor instance master \| display json \| no-more` (2026-10-31, interop lab `ndr-interop-l1`, overlay M09: one received route hidden for "Protocol nexthop is not on the interface"; received 206, accepted 205) |
| `junos_bgp_neighbor_policy_and_nexthop.txt` | `show bgp neighbor instance master \| display json \| no-more` (2026-10-31, lab `ndr-cap-junos`: cJunosEvolved 26.2R1.7-EVO and FRR 10.4.1; FRR sends 192.168.20.0/24, 192.168.21.0/24, which j1's import policy rejects, and 192.168.22.0/24 with next hop 10.99.99.99, which j1 can't use; received 3, accepted 1) |
| `junos_rp_hidden.txt` | `show route receive-protocol bgp 10.0.100.2 table inet.0 hidden extensive \| display json \| no-more` (same lab and time: one hidden route per reason, "Rejected by import policy" and "Protocol nexthop is not on the interface") |
| `junos_rp_hidden_lab1.txt` | Derived from `junos_rp_hidden.txt` for the lab of `junos_bgp_neighbor.txt` (peer 10.0.1.2: 10.30.0.0/24 rejected by import policy, 10.31.0.0/24 with an unusable next hop): prefixes, next hops and AS replaced, the structure unchanged |
| `junos_rp_hidden_iop7.txt` | Derived from `junos_rp_hidden.txt` for `junos_bgp_neighbor_hidden_nexthop.txt` (interop M09: one route hidden for its next hop, none rejected): only the next-hop entry kept, prefix and AS replaced |
