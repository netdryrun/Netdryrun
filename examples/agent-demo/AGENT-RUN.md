# A real agent run on this ticket

This is a record of one real run, not the scripted replay in `demo.sh`. On 2026-10-27, a fresh Claude Code agent was given this ticket and this lab, and nothing else.

## Setup

- **Agent:** Claude Code 2.1.116 in headless mode (`claude -p`). The run reported its model as `claude-opus-4-7`.
- **What it could see:** only `TICKET.md`, `netdryrun.yml`, `topology.clab.yml` and `configs/`. Not this folder's README, `changes/` or `demo.sh`, which contain the answer.
- **Tools:** Read, Edit, Glob and Grep on files, plus the Netdryrun MCP server (`netdryrun mcp`, version 0.2.0). No shell, no Write, no web access. It could not run containerlab or vtysh directly; its only way to test was Netdryrun.
- **Prompt:** "Work the ticket in TICKET.md in the current folder, following its rules." It also said which path the MCP tools use for the folder, and asked for the proposed diff and the Netdryrun verdict at the end. Nothing about the solution.

## What it did

7 turns, 69 seconds. The CLI reported an API-equivalent cost of $0.38.

1. Read `TICKET.md`, `configs/edge1.conf` and `netdryrun.yml`.
2. Loaded the Netdryrun MCP tools.
3. Edited `configs/edge1.conf`: added the new block to both prefix lists.
4. Called `dry_run` on the folder. Result: `status: passed`, 14 of 14 checks, verdict `SAFE TO PROCEED` (the pass verdict before 0.3.2, which renamed it `CHECKS PASSED (only what the checks cover)`).
5. Proposed the change, with the verdict.

Its change:

```diff
 ! Prefixes the customer may announce to us
 ip prefix-list CUSTOMER-IN seq 10 permit 10.100.0.0/24
+ip prefix-list CUSTOMER-IN seq 20 permit 10.101.0.0/24
 !
 ! Prefixes we announce to the upstream and the peer: our block and our customer's
 ip prefix-list OUR-ROUTES seq 10 permit 192.0.2.0/24
 ip prefix-list OUR-ROUTES seq 20 permit 10.100.0.0/24
+ip prefix-list OUR-ROUTES seq 30 permit 10.101.0.0/24
```

It explained both lines correctly, including that the customer filter still drops 8.8.8.0/24, which the customer doesn't own.

## Checked afterwards, independently of the agent's report

- The agent changed only `configs/edge1.conf`. `netdryrun.yml`, the ticket, the topology and the other routers' configs are byte-for-byte unchanged.
- Rerunning `netdryrun run` on its folder gave `PASSED: 14 passed, 0 failed`.

## What this shows, and what it doesn't

The agent got it right on the first try, and didn't make the tempting change in `changes/attempt-1-open-filters.diff`. So this run didn't show Netdryrun catching a mistake. `demo.sh` shows that, by replaying a leaky change. What this run does show is the workflow working end to end. A real agent found the tool and ran the network team's checks through MCP. Its proposal came with a verdict from a real lab, not from its own reasoning about the config. A human approving the change can read the verdict and the 14 named checks, rather than trusting the agent.

This is one run of one model on one ticket. Another run, another model or a harder ticket may go differently, which is exactly why the verdict comes from the lab.
