# Contributing to Netdryrun

Thanks for helping. The most valuable contributions, in order:

1. **A corpus case.** A realistic network change and its expected verdict, written *before* you run it. See [corpus/](corpus/). Cases where Netdryrun gets it wrong are especially welcome: published losses are what make the corpus trustworthy.
2. **A wrong verdict you can reproduce** ("make it lie"). Use the [wrong-verdict form](https://github.com/netdryrun/Netdryrun/issues/new?template=wrong-verdict.yml) and attach the JSON report (`--json report.json`); it contains every command Netdryrun ran and the raw output. Once we reproduce it, it becomes an advisory and you go in the [hall of fame](https://netdryrun.com/trust/#make-it-lie-the-hall-of-fame).
3. **A capture from your own lab** (next release). Output from a NOS version we can't get, made with `netdryrun capture` and `netdryrun sanitize`: no image needed. See the [capture kit](https://netdryrun.com/reference/capture/).
4. **A lab template**: a lab, its checks, and a broken variant that must fail. See [community/labs/](community/labs/README.md).
5. **A driver** for another network OS that runs in containerlab.
6. **Docs and examples** for real-world designs.

New here? Start with an issue labelled `good first issue` (they are kept for people, not for our agents), and [your first pull request, in a browser](https://netdryrun.com/guides/first-pr/) walks through one on Codespaces. How the project itself is run, by AI agents under a human owner, is on [How this project is run](https://netdryrun.com/how-its-run/).

## Development setup (Linux or WSL2, Docker, containerlab)

```bash
git clone https://github.com/netdryrun/Netdryrun && cd netdryrun
python -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"
pytest -q                     # unit tests, no lab needed
bash scripts/e2e.sh           # every example lab end to end (needs containerlab)
python corpus/run.py --case 10   # one corpus case
```

No Linux machine: a GitHub Codespace has Docker and containerlab ready.

## Rules of the road

- **No false passes.** Any change to check semantics needs a test showing the case it gets right, and ideally the case it used to get wrong. For a change to a driver, a check, the runner, the config validator or `verify`, CI runs your new tests against the base branch's code and expects them to fail there. A pure refactor can't have such a test: say so in the pull request, and the maintainer decides.
- **Real device output only.** Parser tests use output captured from live labs (`tests/fixtures/`), never hand-written JSON. Record where a new fixture came from in [`tests/fixtures/SOURCES.yml`](tests/fixtures/SOURCES.yml); CI fails on a fixture without a source.
- **Known false passes stay fixed.** Every false pass we have had is listed in [`tests/known_false_passes.yml`](tests/known_false_passes.yml) with the tests that guard it, and CI runs those tests as the base branch has them.
- **Pre-registered verdicts stay put.** Changing a corpus case, its expected verdict or a committed result needs a new entry in the corpus's `AMENDMENTS.md` saying why.
- **Keep the config format small.** New keys need a reason a network engineer would recognize.
- Be kind in reviews.

## Sign-off (DCO)

Sign off every commit (`git commit -s`). The `Signed-off-by: Your Name <you@example.org>` line certifies the [Developer Certificate of Origin](https://developercertificate.org/): that you wrote the change, or otherwise have the right to submit it under the project's license. CI checks that every commit in a pull request has a sign-off for its author. Forgot one? `git commit --amend -s` (or `git rebase --signoff main`), then push again.

## AI use

You may use AI tools to help with a contribution. We do: Netdryrun itself is built by AI agents, and a human owner approves every merge ([how this project is run](https://netdryrun.com/how-its-run/)). The same rules apply to you:

- **Say so.** The pull request template has two boxes, "No AI tools were used" and "AI tools were used". Tick exactly one; CI checks that one is ticked. It's a disclosure, not a ban, and it doesn't change how your pull request is reviewed.
- **Understand what you submit.** You must have read every line, and be able to explain it and answer review questions without the tool. Your sign-off is yours, whoever typed the code.
- **Bring evidence.** A test that fails without your change, the gate output, a report from a real lab. Generated text that claims a result without one will be asked for it.
- **Keep it small.** Large changes nobody has reviewed are closed by the maintainer, whoever wrote them.
- **Good first issues are for people.** If you use an agent, leave issues labelled `good first issue` to someone learning the project.

Comments on your issue or pull request from our own agents start with "Automated triage" and state facts only. Accepting, closing and other decisions are made by the human owner.

## Licensing of contributions

Netdryrun is licensed under Apache-2.0, and so are contributions: by opening a pull request you agree that your contribution is licensed under the Apache License 2.0 (section 5 of the license), and you confirm you have the right to submit it. There is no separate CLA. Please don't submit code you copied from somewhere with an incompatible license, or vendor material (images, configs, documentation) you aren't allowed to redistribute. Captures are command output you choose to share from your own lab, sanitised first; never send an image or a licence file.

## Releasing (maintainers)

Bump `__version__` in `src/netdryrun/__init__.py` and `server.json`, update CHANGELOG.md, then tag `vX.Y.Z`. GitHub Actions publishes to PyPI with Trusted Publishing.
