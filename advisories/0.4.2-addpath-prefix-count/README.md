# Advisory: Netdryrun 0.4.1 and earlier, `bgp_prefixes` counted add-path paths as prefixes (FRR, SONiC, SR Linux, Arista EOS)

**Affected:** netdryrun 0.4.1 and earlier: FRR since 0.1.0, SONiC since 0.2.0, Nokia SR Linux since 0.1.0 and Arista
EOS since 0.2.0, and the `netdryrun/Netdryrun@v0.4.1` and earlier Actions. **Severity:** Moderate, as
[GHSA-g4f6-4624-2pjv](https://github.com/netdryrun/Netdryrun/security/advisories/GHSA-g4f6-4624-2pjv): it needs a
peer that sends add-path and a count-only check; an `only:` list catches it today on FRR and SONiC.
**Patched versions:** 0.4.2. **Found by:** our own release gate (an isolated red-team agent and a fresh verifier on the
0.4.2 candidate, 12 and 13 November 2026), before any outside user reported it. **Evidence:** reproduced in containerlab
labs with FRR 10.4.1 (RT-0067), SR Linux 26.7.2 (RT-0068) and cEOS 4.36.3M (RT-0069).

## What happened

`bgp_prefixes` read a neighbor's prefix count from a counter the device keeps per neighbor. When the neighbor uses BGP
add-path and sends more than one path per prefix, that counter counts each path. A neighbor sending 2 prefixes with 2
paths each read as 4, so `bgp_prefixes min: 4` passed though only 2 prefixes arrived.

- **FRR and SONiC:** `acceptedPrefixCounter`. FRR 10.4.1 accepts add-path on every session by default, so only the
  sender needs `addpath-tx-all-paths`.
- **SR Linux:** `received-routes` minus `rejected-routes` (and, since 0.4.1, minus the paths that failed AS-loop
  detection), with `add-paths receive true` on the neighbor's family.
- **Arista EOS:** the summary's `prefixAccepted`. cEOS advertises additional-paths receive by default, so here too only
  the sender needs to send add-path.

**Fixed in 0.4.2:** when the neighbor may send add-path (its add-path state says so, or doesn't say):

- FRR and SONiC count the distinct prefixes in `show bgp ... neighbors N routes json`, and a listing that doesn't add
  up to FRR's counter gives no verdict. A family without such a listing (EVPN) is a range, judged only where the whole
  range agrees.
- SR Linux counts the distinct prefixes of the neighbor's paths in the local RIB (`bgp-rib`), which it already read for
  the AS-loop paths; a RIB whose usable paths don't add up to the counter gives no verdict.
- Arista EOS reads the peer's add-path receive state (`show ip bgp neighbors N vrf V | json`,
  `receivingAddPaths.enabled`). Where it isn't clearly off, `prefixAccepted` P becomes the range 1 to P prefixes, judged
  only where the whole range agrees: `max` passes when P is within it, `max: 0` and `exact: 0` fail, and `min` above P
  fails, but P above `max`, or a `min` from 2 to P, gets no verdict (not ready), not a fail. Counting EOS prefixes from
  a route listing is planned.

**Workaround before you upgrade:** add an `only:` list to the check (FRR and SONiC); check the count on a neighbor that
doesn't receive add-path; or turn add-path receive off on that session if your design allows it (FRR, under
`address-family ipv4 unicast`: `neighbor X disable-addpath-rx`, checked on FRR 10.4.1; SR Linux:
`afi-safi ipv4-unicast add-paths receive false` on the neighbor or group; EOS: `no neighbor X additional-paths
receive`). On SR Linux and EOS, `only:` is refused (those drivers read no per-neighbor prefix list); a `route`
check with `present: true` on each prefix you expect catches it there.

The cases are `tests/redteam/RT-0067-frr-addpath-paths-counted-as-prefixes.yml`,
`tests/redteam/RT-0068-srl-addpath-paths-counted-as-prefixes.yml` and
`tests/redteam/RT-0069-eos-addpath-paths-counted-as-prefixes.yml`; the oracles are `tests/oracles/FP-042-ADDPATH`,
`tests/oracles/FP-042-SRLADDPATH` and `tests/oracles/FP-042-EOSADDPATH`, built from the live captures. GitHub advisory:
to be linked when published.

## Also fixed in 0.4.2: FRR, SONiC and Cisco NX-OS read a dampening history entry as a received route

**Affected:** FRR and SONiC, netdryrun 0.3.1 to 0.4.1 (0.4.1 only for the default route `0.0.0.0/0`). With
`bgp dampening`, bgpd keeps a route the neighbor withdrew listed as a dampening history entry until its penalty decays
(also a path it is still removing). The driver read that path as a received BGP route that wasn't selected, so
`route ... protocol: bgp active: false` passed ("present via bgp (not selected)") after the route was withdrawn, and a
`present: false` guard failed though the route was gone. From 0.4.2 such a path is no path; a route dampening
suppressed (the neighbor still announces it) is still present and not selected. **Workaround:** check the withdrawn
route with `present: false`, which fails on it (a false alarm, never a false pass), or clear dampening first
(`clear bgp ipv4 unicast dampening`). Case `tests/redteam/RT-0070-frr-dampening-history-entry-read-as-route.yml`, oracle
`tests/oracles/FP-042-FRRDAMP`, from a live FRR 10.4.1 capture.

The same history entry stays in the neighbor's received-routes listing, which `bgp_prefixes only:` and `record`'s
closed-world list read (FRR and SONiC 0.4.1, where both came in; RT-0071): `record` wrote the withdrawn prefix into
`only`, so the prefix coming back passed the recorded check. From 0.4.2 a prefix whose paths are all withdrawn is not
listed; re-record a baseline taken while dampening held a withdrawn prefix, or remove it from `only` by hand. Case
`tests/redteam/RT-0071-frr-history-entry-listed-as-received-prefix.yml`, oracle `tests/oracles/FP-042-FRRRECVHIST`.

Cisco NX-OS (beta driver, netdryrun 0.4.1, its first release) had the same hole (RT-0075): NX-OS lists a withdrawn path
with `pathhistory: "true"` (a dampening history entry) or `pathdeleted: "true"` (a path being deleted), and the driver
read it as a received route that wasn't selected, so `route ... protocol: bgp active: false` passed after the
withdrawal. From 0.4.2 such a path is no path in `route`, `bgp_route` and `record`. The case was derived from live
NX-OS 10.4(8) captures, not captured in this state; the workaround is the FRR one above (`present: false`, or
`clear bgp ip unicast dampening`). Case `tests/redteam/RT-0075-nxos-history-path-read-as-route.yml`, oracle
`tests/oracles/FP-042-NXOSHIST`.

## Also fixed in 0.4.2: FRR and SONiC counted graceful-restart stale paths as accepted prefixes

**Affected:** FRR since 0.1.0 and SONiC since 0.2.0, netdryrun 0.4.1 and earlier. When a BGP neighbor restarts with
graceful restart and preserves its forwarding state (it sets the F-bit for the family, for example FRR's
`bgp graceful-restart preserve-fw-state`), bgpd keeps the neighbor's old paths marked stale until the neighbor sends
End-of-RIB, and counts them in `acceptedPrefixCounter`. The window a check can read lasts from the session coming
back until End-of-RIB (or until the stale-path timer ends); while the session is down the check fails as not
established. `bgp_prefixes min` is a positive check, judged before any
End-of-RIB wait, so `min: 4` passed ("4 ipv4-unicast prefixes accepted") while the restarted neighbor sent only 3 and
its End-of-RIB was still pending (FRR 10.4.1, captured live). Without the F-bit bgpd drops the stale paths when the
session comes back, and the count is the neighbor's: no false pass then.

From 0.4.2 a family whose neighbor set the F-bit and whose End-of-RIB isn't read as received
(`gracefulRestartInfo.<afi>.endOfRibStatus.endOfRibRecv` true and the family listed in `gracefulRestartInfo.endOfRibRecv`)
has no settled count: no bound is judged on it, the check samples again until End-of-RIB arrives, and `record` leaves
the count out. A per-family graceful-restart block whose F-bit or End-of-RIB fields have an unexpected type is treated
the same way, and so is a neighbor routes listing (read for add-path) that shows stale paths. A neighbor with no
graceful-restart block is read as before. **Workaround before you upgrade:** add a `max` to the
`min` check, which makes it a post-convergence check: from 0.4.1 the convergence gate waits for an End-of-RIB the node reports pending.
Or leave graceful restart (or `preserve-fw-state` on the restarting neighbor) off in the lab.

**Limits.** The guard trusts FRR's per-family F-bit. Not yet checked in a lab: a neighbor that comes back without a
family it had before, and long-lived graceful restart; in both the F-bit can read false while stale paths remain. Until
they are, pair a `min` with `route` checks on the prefixes that matter. The workaround above doesn't cover a peer
declared `eor: not_sent`, which the gate doesn't wait for. And a neighbor that sets the F-bit but never sends End-of-RIB
(`bgp graceful-restart disable-eor`), or whose stale timer runs out first, leaves the count not ready: the check ends
as not evaluated, never as a pass. Case
`tests/redteam/RT-0072-frr-gr-stale-paths-counted-as-accepted.yml`, oracle `tests/oracles/FP-042-FRRGRSTALE`, from a live
FRR 10.4.1 capture.

## Also fixed in 0.4.2: FRR and SONiC read a labeled-unicast session as not carrying unicast

**Affected:** FRR since 0.1.0 and SONiC since 0.2.0, netdryrun 0.4.1 and earlier. A session activated only for
`address-family ipv4 labeled-unicast` carries IPv4 routes that the node installs as BGP IPv4 unicast routes, but
`show bgp neighbors json` lists its family as `ipv4LabeledUnicast` alone, with an `acceptedPrefixCounter` of 0 (FRR
10.4.1, captured live: the peer's 3 prefixes installed via the session). The driver kept that name as it was, so
`bgp_prefixes afi: ipv4-unicast exact: 0` passed with "0 ipv4-unicast prefixes (the session doesn't carry
ipv4-unicast)" in 0.4.1, and in 0.4.0 and earlier, where a family the session didn't list counted 0, every `max` on
it passed too. `record` 0.4.1 wrote that `exact: 0` for every such eBGP session. Every version with `record` also wrote a check with
`afi: ipv4LabeledUnicast`: from 0.2.0 to 0.3.0 one on bgpd's labeled-unicast counter, which read 0 with the peer's
3 routes installed (live), so it caught no change; from 0.3.1 one that `run` refuses (exit 2: no false pass, but no baseline).
The same holds for IPv6 labeled-unicast. Live, the End-of-RIB gate failed the check closed unless the peer was declared
`eor: not_sent`; a peer with graceful restart negotiated, or an `eor: not_sent` declaration, let it pass.

From 0.4.2 a labeled-unicast family of the check's IP version makes the unicast count unread: every bound fails with
"the ipv4-unicast prefix count of the session to X can't be read", also when the session lists the unicast family
beside it (nothing says whether that counter includes the labeled-unicast routes). Any other family a check can't name
(`ipv4Vpn`, `ipv4Multicast`, link-state) does the same when the session doesn't list the unicast family, unless its
name says it is only of the other IP version. `record` writes neither the `exact: 0` nor a check on the unnamed family:
INCOMPLETE BASELINE lines name both, and `record` exits 1. The SR Linux driver keeps such a family under its own name
(`ipv4-labeled-unicast`), so the rule covers it too (not seen live on SR Linux). Unchanged: a session that carries no
family of that version (IPv6 only, EVPN only) still passes `exact: 0` with "doesn't carry". **Workaround before you
upgrade:** on a session that carries labeled-unicast, use `max: 0` (it fails there in 0.4.1) or `route ... present:
false` checks instead of `exact: 0`, and remove the `exact: 0` lines `record` wrote for such sessions. Case
`tests/redteam/RT-0080-frr-labeled-unicast-read-as-no-unicast.yml`, oracle `tests/oracles/FP-042-FRRLU`, from a live FRR
10.4.1 capture.

## Also fixed in 0.4.2: a duplicate key inside a YAML merge source was accepted

**Affected:** every driver, netdryrun 0.3.1 to 0.4.1 (before 0.3.1 no duplicate key was refused; see the
[0.3.0 advisory](../0.3.0-false-pass/README.md)). Duplicate keys in `netdryrun.yml` are errors at any depth, but a
mapping used only as a `<<` merge source was never checked, and YAML kept its last value without a word. A no-leak
guard template written `prefix: 0.0.0.0/0` with a pasted second `prefix: 192.0.2.0/24`, then merged into each node's
check, loaded as a guard on 192.0.2.0/24: a leaked default route passed every run. The same held for one mapping of a
`<<: [..]` list and for the containerlab topology file. From 0.4.2 every mapping a file merges is checked, at any merge
depth, and the file is refused naming the duplicate. **Workaround before you upgrade:** check each anchored mapping (`&name`) and each
mapping in a `<<: [..]` list for a key written twice. Case
`tests/redteam/RT-0073-duplicate-key-in-merge-source.yml`, oracle `tests/oracles/FP-042-YAMLMERGEDUP`.

## Also fixed in 0.4.2: a scenario's restore brought up a link the lab keeps shut

**Affected:** every node kind whose links a scenario can fail (FRR, SONiC, Arista cEOS and plain Linux containers),
netdryrun 0.2.0 to 0.4.1.
After a scenario, restore ran `ip link set up` on every interface the scenario had taken down, without reading its
state first. `node_isolated` takes down every lab link of the node, so a backup link the lab keeps administratively down
(a containerlab `exec: [ip link set eth2 down]`, or on FRR a `shutdown` under the interface, which zebra applies to
the kernel link) came back up after the scenario,
and so did a link a `link_down` named while it was already down. Every later scenario, and the network the run left
behind, had an extra link: a failover check could pass over a path the real network doesn't have. From 0.4.2 each
link's admin state is read before anything changes: a link already down is left down by `node_isolated` and never
brought up, and a `link_down` on it, or a `node_isolated` whose links are all down, stops the run with an error
(exit 2) once the lab is up, since the fault would change nothing. **Workaround before
you upgrade:** keep a scenario that fails a node with a shut link last in the file (or in its own run), or replace
`node_isolated` with a `link_down` list of the links that are up. Case
`tests/redteam/RT-0074-scenario-restore-brings-up-a-shut-link.yml`, oracle `tests/oracles/FP-042-SCENRESTORE`.

## Also fixed in 0.4.2: `record` wrote no guard in a non-default VRF

**Affected:** netdryrun 0.4.0 to 0.4.1, on every driver that lists VRFs (FRR and SONiC; Junos from 0.4.0; the NX-OS and
RouterOS beta drivers in 0.4.1). `record` records every VRF the node lists, each check with its `vrf:`, but wrote its
guards (no default route via BGP, no link subnet of the topology via BGP) in the default VRF only, and said nothing
about the others. A change that leaked the default route into a customer VRF (FRR `import vrf default` under the VRF's
`router bgp`) passed every check recorded for that VRF. From 0.4.2 every VRF with a BGP instance gets the same guards
with its `vrf:`, whether it has BGP sessions or not: a VRF fed only by `import vrf` (a shared-services VRF) is guarded
too, and so is the default VRF of a node whose sessions are all in VRFs (unguarded since 0.3.3). Each guard is first run
on the recording lab like the default VRF's: one the VRF fails today (a default it learns as its service) is left out
with a comment. **Workaround before you upgrade:** add to a recorded baseline, for each VRF,
`{type: route, node: <node>, vrf: <vrf>, prefix: 0.0.0.0/0, protocol: bgp, present: false}` (and `::/0` with IPv6), or
re-record with 0.4.2. Case `tests/redteam/RT-0076-record-no-guard-in-a-vrf.yml`, oracles `tests/oracles/FP-042-RECORDVRF`
and `tests/oracles/FP-042-RECORDVRFNOSESS`.

Four neighbours of this hole, found by adversary review of its fix, are fixed in 0.4.2 too:

- **A VRF list that couldn't be read.** **Affected:** netdryrun 0.4.0 to 0.4.1, on the same drivers (FRR, SONiC and
  Junos from 0.4.0; the NX-OS and RouterOS beta drivers from 0.4.1). When the read of the node's VRFs failed (a vtysh,
  NETCONF/CLI, NX-API or REST timeout), `record` recorded the default VRF alone with a plain `# warning:` comment, wrote
  no gap line and exited 0, so a default route leaked into any other VRF passed. From 0.4.2 it writes an
  `INCOMPLETE BASELINE` line naming the node and its VRF list, first in the file, and exits 1. SR Linux and EOS, which
  can't list VRFs, keep the documented warning. **Workaround before you upgrade:** look for `only the default VRF is
  recorded` in a baseline recorded on FRR, SONiC, Junos, NX-OS or RouterOS, and record again. Oracle
  `tests/oracles/FP-042-RECORDVRFLISTFAIL`.
- **No `::/0` guard without IPv6 BGP or an eBGP session.** **Affected:** netdryrun 0.3.3 to 0.4.1, every driver that
  reads IPv6 routes. `record` wrote the `::/0` guard only where the node (from 0.4.2 the VRF) had IPv6 BGP today or
  (from 0.4.1) an established eBGP session, so with IPv4 iBGP sessions only, or none, a change that brought IPv6 in
  (`address-family ipv6`, `import vrf`) and leaked `::/0` passed. From 0.4.2 every VRF with a BGP instance whose IPv6
  routes can be read gets `{type: route, node: <node>, prefix: ::/0, protocol: bgp, present: false}` with its `vrf:`,
  judged on the recording lab first. Where the driver answers that it can't read IPv6 routes there (RouterOS's "not
  supported", cEOS with IPv6 routing off) no `::/0` guard is written, as before; a read that fails is the next item.
  **Workaround before you upgrade:** add that check by hand. Oracle `tests/oracles/FP-042-RECORDV6DEFAULT`.
- **A failed IPv6 route read under `record --no-routes`.** **Affected:** netdryrun 0.3.3 to 0.4.1, every driver that
  reads IPv6 routes (FRR, SONiC, SR Linux and EOS with IPv6 routing on from 0.3.3; Junos from 0.4.0; NX-OS in 0.4.1). When the IPv6 route read of a node
  or VRF without IPv6 BGP today failed (a vtysh, NX-API or NETCONF timeout), `record` wrote a plain `# warning:`
  comment and left out the IPv6 link-subnet guards (from 0.3.3) and the eBGP `::/0` guard (from 0.4.1) without a gap
  line, and exited 0, so a `::/0` or link subnet leaked there later passed. 0.3.3 and 0.4.0 did this with routes
  recorded too; 0.4.1 exited 1 there, but not under `--no-routes`. From 0.4.2 the failed read is an
  `INCOMPLETE BASELINE` line ("IPv6 routes could not be read, so no IPv6 guards ...") naming the node and VRF, and
  `record` exits 1. **Workaround before you upgrade:** look for `could not read IPv6 routes` in a recorded baseline of
  a driver that reads IPv6, and record again (or add the `::/0` and IPv6 link-subnet `present: false` checks by
  hand). Oracle `tests/oracles/FP-042-RECORDV6READFAIL`.
- **An FRR or SONiC VRF list read from text that isn't one.** **Affected:** netdryrun 0.4.0 to 0.4.1, FRR and SONiC.
  The VRF list kept the lines shaped `vrf NAME ...` of `vtysh -c "show vrf"` and skipped the rest, so an answer that
  exits 0 but isn't zebra's VRF list (a daemon-connection message, an unknown command, a banner, JSON) read as no
  VRFs: `record` recorded the default VRF alone, with no warning, and exited 0. From 0.4.2 any line that isn't zebra's
  `show vrf` format is an error, and `record` writes the `INCOMPLETE BASELINE` VRF-list line and exits 1; an empty
  answer (a node without VRFs) is still no VRFs. **Workaround before you upgrade:** on a node with VRFs, check that
  the recorded baseline has checks with its `vrf:`; if not, record again. Oracle `tests/oracles/FP-042-FRRVRFPARSE`.

## Also fixed in 0.4.2: `verify` approved a static route under BGP pins

**Affected:** `netdryrun verify` (FRR only), MCP `verify_change` and the Action's `mode: verify`, netdryrun 0.4.0 to
0.4.1. An `appears_on` line with BGP attributes in `with:` (`from: 10.0.1.2`, `as_path: "65100"`) was checked against
bgpd's best path only, and every RIB entry for the prefix was explained. A change that also added
`ip route 10.101.0.0/24 10.0.3.2` (distance 1) made zebra select and install the static while bgpd kept its best path
from 10.0.1.2, and the verdict was INTENT MATCHED although the node forwarded the prefix to another next hop. The report
showed it (`protocol: static` and the static's next hop in the line's details, the `ip route` line under untested
config), but the verdict approved. From 0.4.2 the pins describe the route the node selects: `protocol`, `distance` and
`metric` must hold for every selected RIB entry, BGP attributes need the selected route to be BGP's, and with pins a
RIB entry they don't describe is an undeclared difference. **Workaround before you upgrade:** add `protocol: bgp` to
the line's `with:`, and read the `protocol` and `next_hops` of each `appears_on` line in the report. Case
`tests/redteam/RT-0077-verify-bgp-pins-explain-a-static-that-wins.yml`, oracle `tests/oracles/FP-042-VERIFYPINSTATIC`
(output derived from the live FRR 10.4.1 captures; the state is not yet captured live).

## Also fixed in 0.4.2: a `link_down` over a VLAN subinterface or a bridge was judged before the fault took effect

**Affected:** netdryrun 0.3.1 to 0.4.1 (0.2.0 and 0.3.0 waited for no session at all), on FRR and plain Linux
containers and on SONiC VS (its VLAN SVIs sit on the kernel bridge `Bridge`). Before taking a link down, a scenario
notes the BGP sessions over it and waits until they are down on both ends. Those sessions were found from the downed
interface's own addresses, so a session on a VLAN subinterface of it (`eth1.100@eth1`, eth1 holding only its
link-local), or on a bridge it is a port of (`br0` with eth1 and eth2; SONiC's `Vlan100@Bridge` over `Ethernet0`), was
not found: the run logged "no BGP session runs over the downed links" and judged after the settle and hold windows. A
far end behind a containerlab bridge gets no carrier event and keeps the session and its routes for its hold time (180
s by default), so `route ... protocol: bgp` passed on the far end in a lab with no backup path.

From 0.4.2 the node's devices are read with their kinds before any link goes down (one `ip -d -j link show`):

- VLAN subinterfaces and macvlans on a downed interface (and what is stacked on those) count as that interface, with
  their addresses and names, and so does a bond or bridge once every member is down.
- A bridge that keeps another port stays up, so the sessions between it (and the VLAN devices on it) and the far end
  of the downed link are watched. Where the far end is not a plain Linux container (cEOS, SONiC, SR Linux, VM kinds,
  any kind other than `linux`) or is a bridge port too, the run stops with exit code 2.
- A bond that keeps a member, a VRF device and a tunnel bound to the interface keep their carrier and are not waited
  for. A listing that can't be read stops the run with exit code 2.

**Not covered in 0.4.2** (the run then judges after the settle and hold windows, as before): an Arista cEOS SVI or
subinterface over a downed `ethN` (EOS's kernel devices carry no link to `ethN`; not confirmed on a live cEOS), a bond
that goes down with one member lost (`min_links`, LACP), a tunnel whose only underlay was the downed link, and a
bridge on a node whose `ip` shows no masters (busybox, unverified), and, on the far end of a plain downed interface,
an unnumbered session named after a bridge (`br0`) or a SONiC `VlanN` the port reached. **Workaround before you upgrade, and for those:**
look for "no BGP session runs over the downed links" in the output, and give the scenario a `--settle` above the BGP
hold time (or lower the hold timers in the lab). Cases `tests/redteam/RT-0078-link-down-on-a-vlan-trunk-parent.yml`,
oracles `tests/oracles/FP-042-LINKDOWNSTACKED` and `tests/oracles/FP-042-LINKDOWNBRIDGE`.

## Also fixed in 0.4.2: a `link_down` on a SONiC port watched only the SONiC end

**Affected:** SONiC VS, netdryrun 0.3.1 to 0.4.1. The topology's links name the container interface a SONiC port
sits on (`eth1` for `Ethernet0`), so for `link_down {node: s1, interface: Ethernet0}` the far end was never looked up.
The SONiC end's own session dropped at once, but a far end behind a containerlab bridge kept the session and its
routes for its hold time, and a route check on it passed on the state from before the fault. From 0.4.2 the port is
mapped to its container interface from the node (its CONFIG_DB lanes in `lanemap.ini`) before the far end is looked
up, a map that can't be read stops the run with exit code 2, and an unnumbered session on a SONiC or cEOS far end,
keyed by its port name, counts too. **Workaround before you upgrade:** take the link down on the far end's side, or
give the scenario a `--settle` above the BGP hold time. Case `tests/redteam/RT-0079-link-down-on-a-sonic-port-watched-one-end.yml`,
oracle `tests/oracles/FP-042-LINKDOWNBRIDGE`.
