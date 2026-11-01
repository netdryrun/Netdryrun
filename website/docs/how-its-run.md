---
title: How this project is run
description: Netdryrun is built by AI agents under one human owner who approves every merge and release. What every change must carry, how outside contributions are handled, and what our agents may and may not do.
---

# How this project is run

!!! note "Draft, with the next release"
    This page and the contribution rules it describes are new on the main branch after 0.4.0. The capture kit it mentions ships in the next release.

Netdryrun is built by AI agents, and one human owns it. We say so up front because you should know who you are dealing with before you open an issue or a pull request, and because a tool that approves network changes should show how its own changes are approved.

## Who does what

- **Agents do the work.** AI agents write the code, the tests, the docs and this site, run the labs, review each other's changes, and prepare releases.
- **A human owner approves every merge and every release.** The owner is the GitHub account [@VictorKhen](https://github.com/VictorKhen). Nothing reaches the main branch, PyPI or a release tag without that approval. [CODEOWNERS](https://github.com/netdryrun/Netdryrun/blob/main/.github/CODEOWNERS) names the owner for the code a verdict depends on, the corpus, the known-false-pass list and CI.
- **No AI inside the tool.** The CLI, the GitHub Action and the MCP server contain no model and call no AI service. Verdicts come from checks run against your lab ([trust page](trust.md#privacy)).

## What every change carries

- **A test that fails when the change is reverted.** For a change to a driver, a check, the runner, the config validator or `verify`, the contributor CI runs the new tests against the base branch's code and expects them to fail there. A test that passes either way doesn't test the change.
- **Must-fail results.** CI proves the tool still catches a real mistake on every change ([`catches-bad-change`](how-its-built.md)), and every false pass we have had stays a test: [`tests/known_false_passes.yml`](https://github.com/netdryrun/Netdryrun/blob/main/tests/known_false_passes.yml). Those tests run as the base branch has them, so a pull request can't make an old false pass come back by editing the test that guards it.
- **Real output only.** Every parser fixture has a recorded source ([`tests/fixtures/SOURCES.yml`](https://github.com/netdryrun/Netdryrun/blob/main/tests/fixtures/SOURCES.yml)); a fixture without one fails CI.
- **Pre-registered verdicts stay put.** A corpus case, its expected verdict or its committed result changes only with a new, public [AMENDMENTS.md](https://github.com/netdryrun/Netdryrun/blob/main/corpus/AMENDMENTS.md) entry.
- **Misses are published.** Every false pass we find becomes an advisory on the [trust page](trust.md), with the version it affects and the fix.

## Outside contributions

The same rules apply to everyone, with three more for the agents:

- **Replies from an agent say so.** Any comment an agent posts on your issue or pull request starts with "Automated triage" and states facts only: which gates ran, what a reproduction showed, which file a schema error is in.
- **Agents never judge, close or argue with your work.** Deciding whether to accept, closing, labelling something "won't fix" and blocking are the human owner's. An agent may draft a review comment; the owner edits and posts it, or approves it as written.
- **Good first issues are for people.** Issues labelled `good first issue` are reserved for human newcomers; our agents don't pick them up.

You may use AI tools too. Say so in the pull request (the template has a box), and make sure you understand every line you submit: see [CONTRIBUTING](https://github.com/netdryrun/Netdryrun/blob/main/CONTRIBUTING.md#ai-use). Large unreviewed changes are closed by the owner, whoever wrote them.

## The contributor gates

Every pull request, including one from a fork, runs [`contrib.yml`](https://github.com/netdryrun/Netdryrun/blob/main/.github/workflows/contrib.yml) with a read-only token and no secrets:

| Gate | Fails when |
|---|---|
| Sign-off (DCO) | a commit has no `Signed-off-by` line for its author |
| AI-use disclosure | the pull request doesn't tick exactly one of the two boxes |
| Known false passes | any of them passes again |
| Fails on revert | verdict code changed with no new test, or the new tests pass on the old code too |
| Fixture provenance | a fixture has no recorded source; a capture bundle fails its manifest, hash, sanitiser or replay check |
| Corpus | a pre-registered case, its committed result or the nondeterministic list changed without an amendment |
| Lab templates | a template has no broken variant, or an image isn't pinned |

With the `run-labs` label, which the owner adds, lab templates run live (the good lab must pass, the broken one must fail) and both corpora rerun; any changed verdict fails.

## Why this way

Reviewers and list curators now filter out projects that look machine-made and unaccountable, and they are right to. We would rather show the evidence than hide how the work is done: a named human who answers for every merge, tests that prove each change, and every miss in public. If something here doesn't match what you see in the repository, that is a bug: [open an issue](https://github.com/netdryrun/Netdryrun/issues).
