# Ticket NET-2107: announce the 192.168.0.0/16 aggregate from r1

For the summarization plan, **r1** (AS 65001) must announce the aggregate **192.168.0.0/16** to both its neighbors, **r2** (AS 65002) and **r3** (AS 65003). Keep announcing r1's own 192.168.1.0/24 as today: this is an additional route, not a replacement.

Rules for whoever works this ticket, human or AI agent:

- Change only `configs/r1.conf`.
- Don't edit `netdryrun.yml`. It holds the network team's checks for this change and the standing guards required for every change.
- Before proposing the change, run Netdryrun on this folder (`netdryrun run <folder>`, or the `dry_run` MCP tool) and include the verdict. Propose it only if the status is `passed`.
