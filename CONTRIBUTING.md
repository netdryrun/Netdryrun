# Contributing to Netdryrun

Thanks for helping. The most valuable contributions, in order:

1. **A corpus case.** A realistic network change and its expected verdict, written *before* you run it. See [corpus/](corpus/). Cases where Netdryrun gets it wrong are especially welcome: published losses are what make the corpus trustworthy.
2. **A bug report with evidence.** Attach the JSON report (`--json report.json`); it contains every command Netdryrun ran and the raw output.
3. **A driver** for another network OS that runs in containerlab (Arista cEOS, SONiC, Juniper cRPD, and others).
4. **Docs and examples** for real-world designs.

## Development setup (Linux or WSL2, Docker, containerlab)

```bash
git clone https://github.com/netdryrun/Netdryrun && cd netdryrun
python -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"
pytest -q                     # unit tests, no lab needed
bash scripts/e2e.sh           # every example lab end to end (needs containerlab)
python corpus/run.py --case 10   # one corpus case
```

## Rules of the road

- **No false passes.** Any change to check semantics needs a test showing the case it gets right, and ideally the case it used to get wrong.
- **Real device output only.** Parser tests use output captured from live labs (`tests/fixtures/`), never hand-written JSON.
- **Keep the config format small.** New keys need a reason a network engineer would recognize.
- Commits are signed off by real people; be kind in reviews.

## Licensing of contributions

Netdryrun is licensed under Apache-2.0, and so are contributions: by opening a pull request you agree that your contribution is licensed under the Apache License 2.0 (section 5 of the license), and you confirm you have the right to submit it. There is no separate CLA. Please don't submit code you copied from somewhere with an incompatible license, or vendor material (images, configs, documentation) you aren't allowed to redistribute.

## Releasing (maintainers)

Bump `__version__` in `src/netdryrun/__init__.py` and `server.json`, update CHANGELOG.md, then tag `vX.Y.Z`. GitHub Actions publishes to PyPI with Trusted Publishing.
