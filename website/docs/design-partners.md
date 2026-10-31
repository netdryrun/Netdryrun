---
title: Design partners
description: Free help testing one of your real network changes with Netdryrun, in exchange for honest feedback. What you get, what we ask, how your configs are handled, and how to apply.
---

# Design partners

Netdryrun was first released in October 2026, and we're looking for the first outside engineers to try it on a real change. We want it shaped by real changes, not guesses. If you have a routing change coming up, we'll help you test it in a lab, for free, in exchange for honest feedback.

## What you get

- A runnable containerlab lab of the relevant part of your network, built with you on your own machine or CI runner, so your configs stay on your side.
- A `netdryrun.yml` with checks for what your change must do and what must never happen (leaks, lost reachability).
- The verdict with evidence, before your change goes anywhere real. You keep everything.
- Help wiring it into your CI, if you want it there.

Run Cisco IOS XE or IOS XR under your own Cisco licence? Help us verify the upcoming Cisco drivers on your image, and get the verdicts first.

## What we ask

- One real upcoming change. You run the lab on your side and share only what you choose: the results, a check file, the error you got stuck on. If you'd rather we build the lab for you, send sanitized configs instead (public addresses and AS numbers replaced with documentation ranges, secrets removed); we'll help you check.
- Honest feedback: what was useful, what got in the way, how you test changes today.
- Optional: permission to publish an anonymized write-up. Nothing is published without your written OK.

## Fair warning

- A lab is not production. A pass covers the checks in the lab, on the network OSes we support ([FRR, Nokia SR Linux, SONiC, Arista EOS](reference/config.md#drivers)). See [what a lab cannot prove](trust.md#what-a-lab-cannot-prove).
- We never touch your production network and never need access to it.
- We take a few partners at a time, so each change gets proper attention.

## How your configs are handled

**By default, your configs stay on your side.** The lab runs on your machine or your CI runner with your images, and nothing in Netdryrun sends your configs anywhere.

Sending us configs is opt-in. If you want us to build the lab for you, send sanitized configs only. They're used for your lab and nothing else and kept private. We build labs with the help of Anthropic's Claude, so configs you send are processed by it, under terms that don't allow training on them; no other AI service sees them. They're deleted within 30 days after delivery unless you ask us to keep them. An NDA is available on request. See the [privacy notice](privacy.md#configs-you-send-us).

A Test my change issue is public: post only what you're happy to publish.

## After the free test

If it was useful and you want it on more of your network, we offer a fixed-scope paid pilot: two weeks on your runner with your images, a written check suite for your changes, and an evidence report. Your configs stay on your side. We take one pilot at a time. Ask at [hello@netdryrun.com](mailto:hello@netdryrun.com).

## Apply

**Quickest:** open a [Test my change](https://github.com/netdryrun/Netdryrun/issues/new?template=test-my-change.yml) issue with a sanitized change. We reply there with the verdict and evidence, usually within two working days, and you tell us whether it was right.

Or run `netdryrun feedback` and tick "Design partner", or email [hello@netdryrun.com](mailto:hello@netdryrun.com) with one line about the change you want to test.
