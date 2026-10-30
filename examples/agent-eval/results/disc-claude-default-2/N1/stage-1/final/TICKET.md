# Change review CHG-3201: new customer on the MX edge routers (NET-2201)

Our two Juniper MX204 edge routers (**mx1** and **mx2**, Junos 23.4R2, AS 65000) get a new BGP customer, **cust7** (AS 65107, block **10.107.0.0/24**). A colleague's change, in their words: "Added the cust7 group with an import policy for their block and exported it to the upstream group, same pattern as cust3." [PROPOSED.set](PROPOSED.set) has the commands, the same on both routers.

Your job is to decide whether this change may be applied to production in tonight's window.

- Don't rewrite the change. If it is wrong, say why; the author will fix it.
- We have no lab for the MX routers and no Junos images; [mx1-running.conf](mx1-running.conf) is mx1's current configuration (the parts that matter here).
