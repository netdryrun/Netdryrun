---
title: How Netdryrun is built and verified
description: How Netdryrun is engineered, tested and released, with a link to the evidence for every claim, so you can verify it rather than take our word for it.
---

# How Netdryrun is built and verified

A tool that approves network changes has to earn trust with evidence, not claims. Most of this page links to something you can inspect or rerun yourself: the test corpus, the CI runs, the commit history and the release pipeline. Where a claim can't be checked yet, the page says so.

## At a glance

| | Evidence |
|---|---|
| Accuracy on realistic BGP changes | Verdict Corpus v1: **24/30** (ping only 20/30, sessions up 15/30). v2: **17/18** (ping only 9/18, sessions up 7/18). Both ran on the released 0.3.1 (the release gate reruns them for every release). [Results](corpus.md) |
| Expected verdicts fixed before any run | Committed first, never edited: [`b4df0b0`](https://github.com/netdryrun/netdryrun/commit/b4df0b0) (v1), [`322cc4e`](https://github.com/netdryrun/netdryrun/commit/322cc4e) (v2) |
| Results you can rerun | One command locally (`python corpus/run.py`, `--corpus v2` for v2). The [Reproduce corpus](https://github.com/netdryrun/netdryrun/blob/main/.github/workflows/reproduce-corpus.yml) workflow reruns v1 from your own fork; it has not been run on GitHub yet |
| Real labs on every change | FRR and Nokia SR Linux labs boot in CI on every push and pull request ([runs](https://github.com/netdryrun/netdryrun/actions/workflows/ci.yml)) |
| What users install is tested too | The released Action and the PyPI package, on every push and weekly ([`published-action.yml`](https://github.com/netdryrun/netdryrun/blob/main/.github/workflows/published-action.yml)) |
| Supply chain | PyPI Trusted Publishing, CodeQL, OpenSSF Scorecard, every Action pinned to a commit |
| Losses | Published next to the wins, never removed |

## Engineering process

Every change goes through the same CI tests and lab runs, and every release through the release gate described below. The [commit history](https://github.com/netdryrun/netdryrun/commits/main) records every change.

## Pre-registered accuracy testing

The [Verdict Corpus](corpus.md) measures Netdryrun on realistic BGP changes, each labelled harmful or safe in advance, and compares it with two common checks: "ping still works" and "all BGP sessions are up".

- **Verdicts are committed before anything runs.** v1: all 30 cases with their expected verdicts in [`b4df0b0`](https://github.com/netdryrun/netdryrun/commit/b4df0b0), results later in [`7576298`](https://github.com/netdryrun/netdryrun/commit/7576298). v2: 18 new cases in [`322cc4e`](https://github.com/netdryrun/netdryrun/commit/322cc4e), results later in [`669b30f`](https://github.com/netdryrun/netdryrun/commit/669b30f). No case was edited after a run ([history of `corpus/cases/`](https://github.com/netdryrun/netdryrun/commits/main/corpus/cases)).
- **The tool was run on the corpus during development, and changed before the published runs.** During 0.2.0 development, runs against the v1 cases found a bug (a change that broke a baseline check ended a scenario run as `error`) and showed that the new polling made the corpus 2 to 3 times faster; both are in the [changelog](https://github.com/netdryrun/netdryrun/blob/main/CHANGELOG.md). The expected verdicts were not changed; the v1 intent spec changed by one comment line.
- **Both published runs were rerun on the released 0.3.1** by the release gate (commit `08059de`, code identical to the v0.3.1 tag). The first runs used pre-release builds: v1 on commit `ec23379` (it called itself 0.2.0, before the tagged 0.2.0), v2 on a development build that recorded no commit. On 0.3.1 every v1 verdict is the same; v2 changed on case 18 (now rejected, as expected), recorded in [AMENDMENTS.md](https://github.com/netdryrun/netdryrun/blob/main/corpus/v2/AMENDMENTS.md).
- **v2 is a harder test, not a friendlier one.** Its cases target the kinds of change v1 missed. It was written after seeing v1's results, which is a limitation to keep in mind.
- **Everything reruns.** The runner ([`corpus/run.py`](https://github.com/netdryrun/netdryrun/blob/main/corpus/run.py)), every case and the raw output ([`results.json`](https://github.com/netdryrun/netdryrun/blob/main/corpus/results/results.json)) are public. `python corpus/run.py` reruns v1 and `--corpus v2` reruns v2, with the code you have checked out (so a different verdict can come from a code change, not only from noise). The GitHub workflow reruns v1 the same way on a hosted runner and lists any verdict that differs; it has not been run on GitHub yet, and it does not cover v2.
- **Limit of this evidence:** git commit dates come from the author's machine. The history proves the order of the commits and that the cases were not changed; it is not an independent timestamp.

## Every miss, and what it changed

A test you always pass tells you nothing. Netdryrun's misses stay in the published results, at the same size as its catches, and each one has driven a specific improvement.

<!-- facts:built_losses -->
**Verdict Corpus v1: wrong on 6 of 30 cases.** It approved 5 harmful changes and blocked 1 safe one ([RESULTS.md](https://github.com/netdryrun/netdryrun/blob/main/corpus/RESULTS.md)).
<!-- /facts:built_losses -->

**Verdict Corpus v2: wrong on 1 of 18 cases on 0.3.1**, a harmful change approved. The first run, on a development build, was wrong on 2 ([v2 results](https://github.com/netdryrun/netdryrun/blob/main/corpus/v2/RESULTS.md)).

| Case | Outcome | Root cause | What changed | Status |
|---|---|---|---|---|
| v1 [06](corpus/06-customer-adds-prefix.md): customer announces a second allowed /24 | Blocked a safe change | The intent spec pinned exactly 2 prefixes towards the upstream and peer, so normal customer growth looked like a leak | v2 checks a range (2 to 51 prefixes); the growth cases 07 and 08 pass | Fixed |
| v1 [12](corpus/12-ibgp-send-community-dropped.md): send-community removed on iBGP | Approved | **Our label was wrong.** On FRR, communities are sent by default, so the change is a no-op ([AMENDMENTS.md](https://github.com/netdryrun/netdryrun/blob/main/corpus/AMENDMENTS.md), with a reproduction script) | Scored as a loss anyway, never corrected in our favour. v2 case 09 tests the corrected expectation and case 10 the truly harmful variant; both judged correctly | Label error |
| v1 [18](corpus/18-redistribute-connected.md): redistribute connected on pe1 | Approved | Spec gap: nothing checked for infrastructure routes leaving the AS | New intent I6: no link or loopback routes at the customer, upstream or peer. v2 case 02 (the same mistake on pe2) caught | Fixed |
| v1 [23](corpus/23-fat-finger-third-party-origin.md): pe1 originates 8.8.8.0/24 | Approved | Spec gap: nothing checked for third-party space | New intent I7, a sentinel list of well-known prefixes. v2 case 03 caught | Partly fixed (see v2 04) |
| v1 [21](corpus/21-customer-max-prefix-removed.md): customer max-prefix removed | Approved | Latent risk, invisible until the customer misbehaves | New `inject_routes` failure scenario: the customer floods 200 prefixes. v2 cases 05 and 11 caught | Fixed (the scenario ships in 0.3.1) |
| v1 [30](corpus/30-peer-import-filter-removed.md): peer inbound filter replaced with permit-all | Approved | Latent risk, invisible until the peer misbehaves | The same scenario type, with the peer announcing routes it does not own. v2 case 06 caught | Fixed (the scenario ships in 0.3.1) |
| v2 04: redundant aggregate mistyped as 192.0.12.0/24 | Approved | I7 checks only a few well-known prefixes; nothing bounds what the customer receives | Predicted as a likely miss in the case file before the run | Open |
| v2 18: discard route for the aggregate deleted | Approved on the development build; **rejected on 0.3.1** | Causes a routing loop for unused addresses inside the aggregate; no check sends traffic there | 0.3.1 reads received paths and never reads an error as "no routes": the upstream and the peer no longer receive the aggregate, so checks I2 and I5 fail. The loop itself is still not probed; a path or traceroute check would show it | Caught on 0.3.1 (not by probing the loop) |

Two caveats apply. v2 was written after seeing v1's misses, so its improvements are measured on cases designed by the same team. And the corpus runs on FRR only, with one topology.

## Continuous integration with live labs

Every push to `main` and every pull request runs [`ci.yml`](https://github.com/netdryrun/netdryrun/blob/main/.github/workflows/ci.yml) ([runs](https://github.com/netdryrun/netdryrun/actions/workflows/ci.yml)): unit tests on Python 3.10, 3.12 and 3.13, plus three jobs that boot real containerlab labs.

- **`e2e`** runs the GitHub Action on [`examples/frr-bgp`](https://github.com/netdryrun/netdryrun/tree/main/examples/frr-bgp) and [`examples/srl-frr`](https://github.com/netdryrun/netdryrun/tree/main/examples/srl-frr) (FRR and Nokia SR Linux). Both must pass.
- **`catches-bad-change`** runs [`examples/frr-bgp-broken`](https://github.com/netdryrun/netdryrun/tree/main/examples/frr-bgp-broken), a change that leaks a default route. The job succeeds only if Netdryrun rejects it.
- **`agent-demo`** replays [`examples/agent-demo`](https://github.com/netdryrun/netdryrun/tree/main/examples/agent-demo): a route-leaking change must fail on exactly the leak guards, and the proper fix must pass.

A second workflow, [`published-action.yml`](https://github.com/netdryrun/netdryrun/blob/main/.github/workflows/published-action.yml), tests what users install rather than the code on `main`: the released Action by its tag (it must pass a good change and reject a bad one), and `pip install` and `uvx` from PyPI on every supported Python version, including an MCP handshake.

SONiC and Arista EOS are not in CI yet (cEOS is an image each user downloads from Arista). Their unit tests parse output captured from real lab runs ([`tests/fixtures`](https://github.com/netdryrun/netdryrun/tree/main/tests/fixtures)).

Every release also goes through a seven-layer release gate, from linting and mutation testing of the verdict logic to chaos runs on the built package, described in [RELEASING.md](https://github.com/netdryrun/netdryrun/blob/main/RELEASING.md); from the next release on, each release's results are committed in `releases/<version>/GATE.md`.

## Performance on a 20-node fabric

On a 20-node leaf-spine fabric (4 spines, 16 leaves, FRR, 64 links), `netdryrun record` produced 560 checks in 11 seconds, and a full `netdryrun run` (deploy, convergence, all checks, destroy) took 65 seconds. A deliberately broken change failed exactly the 83 checks it should have. Full numbers, memory use and limits are in the [FAQ](faq.md#a-20-node-lab). These come from one-off runs on the maintainer's machine; the topology and the reports are not published yet, so you can't check them the way you can check the corpus.

## Cross-model review (not a human audit)

Before releases 0.1.0 and 0.2.0, the code was also reviewed by AI models from other vendors (OpenAI GPT and xAI Grok); 0.3.0 was not. Separate agent sessions that start without the author's context also review changes. These review outputs are not published. Fixes from these reviews: [`ec23379`](https://github.com/netdryrun/netdryrun/commit/ec23379) (v0.2.0), [`6495759`](https://github.com/netdryrun/netdryrun/commit/6495759) (agent demo) and [`90fe0ae`](https://github.com/netdryrun/netdryrun/commit/90fe0ae): a security review of the MCP server, the GitHub Action and every path where lab output reaches a shell, a device CLI or a PR comment, with 7 findings, each fixed with a regression test.

These reviewers are AI models, not human auditors. No independent human security audit has been done yet. Report vulnerabilities through the [security policy](https://github.com/netdryrun/netdryrun/security/policy).

## Defects found by our own testing

Each was found by running Netdryrun against live labs or the corpus, and is recorded in the [changelog](https://github.com/netdryrun/netdryrun/blob/main/CHANGELOG.md).

- **False passes on SR Linux and Arista (fixed):** a leaked route that was received but not installed was invisible, so a `present: false` check passed when it should have failed. Fixed in [`77f43d6`](https://github.com/netdryrun/netdryrun/commit/77f43d6), with regression tests on captured output ([`test_drivers.py`](https://github.com/netdryrun/netdryrun/blob/main/tests/test_drivers.py)).
- **Wrong status after a failure scenario (fixed):** a change that broke a baseline check ended as `error` instead of `failed`. Found with [`scripts/pack_verify.sh`](https://github.com/netdryrun/netdryrun/blob/main/scripts/pack_verify.sh); fixed in [`f6ea560`](https://github.com/netdryrun/netdryrun/commit/f6ea560).
- **PR comments over GitHub's size limit on large labs (fixed):** found by the 20-node scale test. From 0.3.1, the comment is cut to fit GitHub's limit, failures first, and says how many checks it left out; the JSON and JUnit reports keep every check.
- **A mislabeled corpus case:** [case 12](corpus/12-ibgp-send-community-dropped.md), above.

## Supply-chain security

- **Releases** are published to PyPI with Trusted Publishing, so no tokens are stored ([`release.yml`](https://github.com/netdryrun/netdryrun/blob/main/.github/workflows/release.yml)). A release fails if the tag and the package version differ.
- **OpenSSF Scorecard** rates the repository's practices weekly and on every push ([current score](https://scorecard.dev/viewer/?uri=github.com/netdryrun/netdryrun)), including the checks where it scores low today; the viewer lists each one.
- **CodeQL** scans the Python code and the workflows ([`codeql.yml`](https://github.com/netdryrun/netdryrun/blob/main/.github/workflows/codeql.yml)).
- **Every third-party GitHub Action is pinned to a commit**, in the workflows and in [`action.yml`](https://github.com/netdryrun/netdryrun/blob/main/action.yml). Dependabot keeps the pins current.

## What we do not claim

- **Not production safety.** A pass means the change behaved correctly in a lab running open-source or lab images of network operating systems. It does not prove the change is safe on your network ([what a lab cannot prove](trust.md#what-a-lab-cannot-prove)).
- **Not Internet scale.** The largest measured lab has 20 nodes and small routing tables. Nothing here is tested with full Internet tables or hundreds of peers.
- **Not vendor parity.** FRR, SR Linux, SONiC and cEOS behave differently from each other and from hardware routers. The corpus runs only on FRR, with one topology and one intent spec per version, all written by the Netdryrun maintainers.
