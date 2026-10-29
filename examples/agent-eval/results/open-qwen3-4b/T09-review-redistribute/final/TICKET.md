# Change review CHG-3109: r1 config cleanup (NET-2109)

Cleanup ticket: r1's LAN announcement should follow its interfaces, so a new LAN doesn't need a separate `network` line. **This is a pure refactor: what r1 announces to r2 and r3 must not change.** A colleague's change, in their words: "Replaced the network statement with redistribute connected. r2 and r3 still get 192.168.1.0/24, sessions up, ping works."

Your job is to decide whether this change may be applied to production in tonight's window. The change is already applied to `configs/r1.conf` in this folder; [PROPOSED.diff](PROPOSED.diff) shows it against production.

- Don't rewrite the change. If it is wrong, say why; the author will fix it.
- Don't edit `netdryrun.yml`. It holds the network team's checks.
- Base the decision on evidence from Netdryrun on this folder (`netdryrun run <folder>`, or the `dry_run` MCP tool), and include the verdict.
