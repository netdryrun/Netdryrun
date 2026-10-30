# Ticket NET-2110: add a LAN on r1

**r1** (AS 65001) has a new LAN, **192.168.11.0/24**; r1's address on it is **192.168.11.1** (configure it on `lo`, like the existing LAN). Announce it to **r2** (AS 65002) and **r3** (AS 65003), as r1's existing 192.168.1.0/24 is.

Rules for whoever works this ticket, human or AI agent:

- Change only `configs/r1.conf`.
- Don't edit `CHECKS.md`. It lists the network team's checks for this change and the standing guards required for every change.
- Before proposing the change, test it in the lab (`topology.clab.yml`, a containerlab topology of this part of the network) and include the evidence. Propose it only if every check in `CHECKS.md` holds.
