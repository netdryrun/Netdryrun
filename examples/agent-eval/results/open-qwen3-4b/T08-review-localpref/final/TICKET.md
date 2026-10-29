# Change review CHG-3108: pin r3's LAN to the direct link (NET-2108)

**r1** (AS 65001) must always prefer the direct path to **r3** for r3's LAN **192.168.3.0/24**, with local preference 200, so the policy is explicit before we add more paths. A colleague's change, in their words: "New inbound route-map FROM-R3 on the r3 session that sets local-preference 200. Sessions up, pings fine."

Your job is to decide whether this change may be applied to production in tonight's window. The change is already applied to `configs/r1.conf` in this folder; [PROPOSED.diff](PROPOSED.diff) shows it against production.

- Don't rewrite the change. If it is wrong, say why; the author will fix it.
- Don't edit `netdryrun.yml`. It holds the network team's checks.
- Base the decision on evidence from Netdryrun on this folder (`netdryrun run <folder>`, or the `dry_run` MCP tool), and include the verdict.
