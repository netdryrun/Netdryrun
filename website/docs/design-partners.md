---
title: Design partners
description: Free help testing one of your real network changes with Netdryrun, in exchange for honest feedback. What you get, what we ask, how your configs are handled, and how to apply.
---

# Design partners

We want Netdryrun shaped by real changes, not guesses. If you have a routing change coming up, we'll help you test it in a lab, for free, in exchange for honest feedback.

## What you get

- A runnable containerlab lab of the relevant part of your network, built with you from your sanitized configs.
- A `netdryrun.yml` with checks for what your change must do and what must never happen (leaks, lost reachability).
- The verdict with evidence, before your change goes anywhere real. You keep everything.
- Help wiring it into your CI, if you want it there.

## What we ask

- One real upcoming change, and sanitized configs for the routers involved: replace public addresses and AS numbers with documentation ranges and remove secrets. We'll help you check.
- Honest feedback: what was useful, what got in the way, how you test changes today.
- Optional: permission to publish an anonymized write-up. Nothing is published without your written OK.

## Fair warning

- A lab is not production. A pass covers the checks in the lab, on the network OSes we support ([FRR, Nokia SR Linux, SONiC, Arista EOS](reference/config.md#drivers)). See [what a lab cannot prove](trust.md#what-a-lab-cannot-prove).
- We never touch your production network and never need access to it.
- We take a few partners at a time, so each change gets proper attention.

## How your configs are handled

You send sanitized configs only. They're used for your lab and nothing else and kept private. We build labs with the help of Anthropic's Claude, so your configs are processed by it, under terms that don't allow training on them; no other AI service sees them. They're deleted within 30 days after delivery unless you ask us to keep them. An NDA is available on request. See the [privacy notice](privacy.md#configs-you-send-us).

## Apply

**Quickest:** open a [Test my change](https://github.com/netdryrun/netdryrun/issues/new?template=test-my-change.yml) issue with a sanitized change. We reply there with the verdict and evidence, usually within two working days, and you tell us whether it was right.

Or run `netdryrun feedback` and tick "Design partner", or email [hello@netdryrun.com](mailto:hello@netdryrun.com) with one line about the change you want to test.
