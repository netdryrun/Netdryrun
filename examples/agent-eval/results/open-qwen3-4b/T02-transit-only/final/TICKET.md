# Ticket NET-2102: transit-only announcement for a customer block

Customer **cust1** (AS 65100) has a new address block, **10.101.0.0/24**, and is already announcing it to us over BGP. They bought **transit only** for this block: our upstream (**up1**, AS 65200) must receive it, our peer (**peer1**, AS 65300) must not. Their existing block 10.100.0.0/24 keeps going to both, as today.

Rules for whoever works this ticket, human or AI agent:

- Change only `configs/edge1.conf`.
- Don't edit `netdryrun.yml`. It holds the network team's checks for this change and the standing guards required for every change.
- Before proposing the change, run Netdryrun on this folder (`netdryrun run <folder>`, or the `dry_run` MCP tool) and include the verdict. Propose it only if the status is `passed`.
