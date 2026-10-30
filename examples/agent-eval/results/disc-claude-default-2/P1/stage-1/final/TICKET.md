# Ticket NET-2101: announce the customer's new block

Customer **cust1** (AS 65100) has a new address block, **10.101.0.0/24**, and is already announcing it to us over BGP. Make sure our upstream (**up1**, AS 65200) and our peer (**peer1**, AS 65300) receive it, so the internet can reach it.

Rules for whoever works this ticket, human or AI agent:

- Change only `configs/edge1.conf`.
- Don't edit `CHECKS.md`. It lists the network team's checks for this change and the standing guards required for every change.
- Before proposing the change, test it in the lab (`topology.clab.yml`, a containerlab topology of this part of the network) and include the evidence. Propose it only if every check in `CHECKS.md` holds.
