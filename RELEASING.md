# Releasing Netdryrun

Netdryrun gives one thing: a pass/fail verdict on a network change. A verdict is only worth
something if a pass can be trusted, so every release goes through a gate. The gate looks for bugs
by construction rather than by eye, and above all for **false passes**: reporting "passed" when
the change should have failed.

The gate is one script, [`scripts/release_gate.py`](scripts/release_gate.py). Its results for each
release are committed in `releases/<version>/GATE.md`, so anyone can see what cleared a release
and what didn't.

## Severities

Every check in the gate has a severity:

- **BLOCKER**: a failure stops the release. No exceptions and no waivers.
- **MAJOR**: must be fixed, or accepted with a written reason in `releases/<version>/accepted.json`.
  The reason appears in `GATE.md`.
- **INFO**: recorded, never blocks.

A check that cannot run (a tool is missing, or there is no lab machine) is reported as **SKIP**,
never as a pass. A skipped BLOCKER leaves the release incomplete. With `--strict`, which CI always
uses, a skipped BLOCKER counts as a failure.

## The layers

```bash
pip install -e ".[dev]"                          # ruff, pytest-cov, hypothesis, mutmut
python scripts/release_gate.py static            # seconds
python scripts/release_gate.py unit              # minutes
python scripts/release_gate.py mutation          # minutes to an hour
python scripts/release_gate.py live              # 1 to 2 hours, on the lab machine
python scripts/release_gate.py acceptance        # Layer 5b, about 3 to 5 hours, on the lab machine
python scripts/release_gate.py after-publish 0.4.0
python scripts/release_gate.py consistency      # seconds: every public place names the release (nightly)
python scripts/release_gate.py all               # static, unit, mutation, live, acceptance
python scripts/release_gate.py report --stranger-status STATUS.json   # rebuild GATE.md (needs the stranger's status)
```

`report` never says CLEARED (or READY TO PUBLISH) without the synthetic stranger's status: the maintainers'
nightly run that follows this README on a clean machine, including `record` on a lab that is not one of the
examples and a change that must fail. A status that is missing, unreadable, older than 36 hours, not green, without a must-fail change that
failed as it must, without the netdryrun version it tested or with another one, or reporting a false pass is
a BLOCKER. 0.3.3 and 0.4.0 shipped while it
reported one ([advisory](advisories/)); this rule is why that can't happen again.

Each layer records its results in `releases/<version>/gate/<layer>.json` along with the commit,
the time, the host and the tool versions. `GATE.md` is then rebuilt from every recorded layer,
because the layers run on different machines and at different times. The script exits non-zero
when a BLOCKER fails.

A fix late in a release that touches some verdict modules reruns mutation on those modules only:
`mutation --modules drivers --carry-mutation <earlier gate/mutation.json>`. Every other module keeps
its earlier record only if its source file is byte-identical at the new commit; GATE.md says
"carried over from <commit>" on each one. A module whose source changed, or one neither mutated nor
carried, fails the layer. The other layers run in full on the new commit.

### 1. Static

- **ruff**, set up in `pyproject.toml` to look for bugs rather than style (pyflakes, pycodestyle
  errors, bugbear, pylint errors).
- **actionlint** on every workflow, with shellcheck on their `run:` scripts, and **shellcheck**
  on every shell script. Shellcheck errors are BLOCKERs and warnings are MAJOR.
- **No empty `${{ }}`** in `action.yml` or the workflows: GitHub rejects the whole file.
- **`scripts/sync_facts.py --check`**: the public numbers and versions match the source.
- **Version consistency**: `pyproject.toml`, `src/netdryrun/__init__.py`, both versions in
  `server.json`, the newest CHANGELOG release heading, and every `netdryrun/Netdryrun@vX.Y.Z`
  in the docs, examples and workflows must give the same version.
- **Python range**: `requires-python` and the classifiers match the versions the unit layer tests.
- **Every example is documented**: each folder in `examples/` has an expected result and exit
  code in the docs' examples table. The live layer then holds each example to that table.
- With `--candidate` (the release candidate itself): the CHANGELOG's Unreleased section is empty,
  and neither the git tag nor the PyPI version exists yet.

### 2. Unit tests, everywhere users run them

- The full suite on **every supported Python, 3.10 to 3.14**, each in a fresh virtual environment
  (`uv` creates the interpreters when they are missing).
- The suite again in a plain **`python:3.12-slim` container with no containerlab and no Docker**,
  as on CI runners, installed as a normal package rather than from the source folder.
- **Coverage** of the modules that decide a verdict: `checks.py`, `config.py`, `runner.py` and
  `drivers/`, lines and branches. Each has a floor in the script. The floors only ever go up, and
  a module that falls below its floor fails a MAJOR check.

### 3. Verdict invariants

A dedicated test suite in `tests/` states what must always be true and then attacks it:

- a must-fail matrix for every check type and driver;
- property-based tests (Hypothesis) that feed wrong types, typos and unknown keys into the config,
  where each must give a config error rather than a check that can't fail;
- driver parser fuzzing, where a parser must raise or return real data and never turn a failed
  command into "no routes";
- metamorphic tests: adding a leaked route, or removing a session, must flip a pass to a fail;
- timing properties with a fake clock.

These tests run as part of layer 2.

### 4. Mutation testing

`mutmut` changes the verdict modules on purpose, for example by flipping a comparison or
dropping a condition, then checks that a test fails. Each change is called a mutant. A mutant
that no test catches (a **survivor**) shows a place where a real bug could slip through
unnoticed.

- Every run starts from a fresh `mutants/` folder, so a cached result can never hide a survivor.
- **A surviving mutant in verdict logic is a BLOCKER** until a test kills it or it is shown to be
  harmless. A harmless mutant is accepted by name, with the reason, in `accepted.json`
  (`"mutants": {"<name>": "<why it cannot change a verdict>"}`).
- Survivors are listed by function in `GATE.md`, and every diff is in `releases/<version>/mutants.md`.

Use `--modules checks` to attack a single module while you write tests for it.

### 5. Live matrix on the built package

This layer runs on the lab machine (Linux with containerlab and Docker). It starts only when no
lab is running, so that anything left over afterwards is known to come from the gate.

- The **wheel is built and installed in a fresh environment**. Everything after that runs the
  installed package, never the source tree, and the gate checks this.
- **Every example** runs and must give the result and exit code documented in the docs'
  examples table. Each variant is included, such as each leak in `srl-hidden-leak`, and so is the
  agent demo (`demo.sh` must end "Demo OK"). The measured times are compared with the documented
  ones.
- **Both Verdict Corpus versions** are rerun from a scratch copy, and every verdict must match the
  committed `results.json`. A changed verdict blocks the release, even when it looks like an
  improvement, until it is understood and the results are republished.
- The **MCP handshake** against the installed package.
- **Chaos**: SIGINT and SIGTERM during the deploy and during the checks, an image that does not
  exist, a node that cannot be created, and two runs of the same lab at once. Restarting Docker
  mid-run is optional (`--chaos-docker-restart`), because it affects every container on the
  machine. Each case must end with its exit code (130 for SIGINT, 143 for SIGTERM, 2 for a lab
  that can't deploy) and a clear message with no traceback.
- After every example, corpus run and chaos case, **no `clab-` container may be left running**.

**Starting a long run** (live, acceptance, a corpus refresh) in the background: use `scripts/labrun.py`, never a
shell `&` (which leaves SIGINT ignored, so G2 refuses the run):

```bash
python scripts/labrun.py start --id live-<sha> -- python scripts/release_gate.py live --strict
python scripts/labrun.py status live-<sha>     # phase, heartbeat age, pause, result
python scripts/labrun.py pause live-<sha>      # hold at the next example or corpus; resume with `resume`
python scripts/labrun.py stop live-<sha>       # the whole process group, checked gone
```

- `start` returns 0 only once the gate has written its receipt (after G2), and 1 if the launch failed, within 90 s.
- A watcher outside the run marks it:
  - `stalled`, and stops it, when its heartbeat is older than 90 s;
  - `exited-without-result` when it ends without finishing.
- A wall-clock gap of over 60 s, from host sleep or a frozen WSL VM, is recorded in `result.json` as a taint. No
  case that overlaps a taint counts as a verdict.

### 5b. Acceptance from five angles

Added for 0.4.1, after each extra round of testing on it found another false-pass path. It runs
[`scripts/acceptance.py`](scripts/acceptance.py) on the lab machine, against the wheel of the candidate commit
built in a clean clone, from the matrix in [`releases/acceptance-matrix.yml`](releases/acceptance-matrix.yml):

1. **Each network OS:** for every driver, its examples (good and every leak), the synthetic stranger's must-fail
   change ported to that NOS (a customer filter loses its `match`) against a `record` baseline, and the vendor
   output traps (longest-match answers, a missing VRF, IPv6, communities, protocol, an unknown neighbor) on the
   kept good lab. A driver the release claims and the run can't cover live fails the layer; it is never "passing".
2. **The end user:** the README's commands word for word in a fresh container, with only the package source
   substituted, and the common mistakes (a missing image, no Docker permission, a typo in `netdryrun.yml`, a wrong
   path, no KVM). Each mistake must end in exit `2` with a clear message and no lab left.
3. **The system integrator:** a 30-node lab of four NOSes (which is also angle 1's mixed lab), two runs at once, a
   brownfield-sized FRR policy, every JSON report read against the published schema, and every CI template in
   the docs (YAML and actionlint).
4. **The AI agent:** the MCP server on a fresh lab. `dry_run` must reject a leaky change; then `start_run` and
   `get_result`, `record_baseline` and `verify_change` run, and the size of each result is recorded.
5. **The adversary:** two isolated red-teamers and a verifier, all agents, following
   [`releases/ACCEPTANCE-PROMPT.md`](releases/ACCEPTANCE-PROMPT.md). They record their outcome in
   `releases/<version>/acceptance-adversary.md`.

The script takes the lab lock for each lab and yields to a running `live` layer or stranger. It cleans up after
every lab and resumes after an interruption. It writes `acceptance.json` and `acceptance.md`. Every item that
doesn't pass is a BLOCKER: an expectation mismatch, a lab left behind, a traceback, an item that couldn't be
covered (a SKIP, which `--strict` counts as a FAIL), a partial run, or a missing or open adversary record.
An agent reads the mismatches (job 2 of the prompt file).

### 6. Independent review

Before each release, every change since the last release gets a cold review from a fresh agent
session with none of the author's context. The focus is false passes, security and wrong exit
codes. Models from other vendors also review the diff and the README. Every public claim is
checked against the release candidate, and a fresh user (an agent that has only the public docs)
installs the candidate and follows the getting-started guide and the tutorial word for word. The
findings and the decision on each go into `releases/<version>/review.md`, which `GATE.md` includes.

### 7. Release and after-publish proof

The release workflow builds the package, checks that the tag matches the version, and publishes
it to PyPI through Trusted Publishing, so no token is stored anywhere. Afterwards:

```bash
python scripts/release_gate.py after-publish 0.4.0
```

- `pip install netdryrun==0.4.0` from PyPI in a fresh environment on every supported Python, then
  `--version`, `validate` and the MCP handshake;
- `uvx netdryrun@0.4.0` on every supported Python, then `--version` and the MCP handshake;
- one live example (`frr-bgp`) run with the package from PyPI;
- the Action by its new tag passes a good change and rejects a bad one (the
  [`published-action.yml`](.github/workflows/published-action.yml) workflow);
- release consistency (BLOCKER): every public place names the new version, and each one that doesn't
  is listed: PyPI's latest version, the GitHub release marked latest, `main`'s README status line,
  every `uses: netdryrun/Netdryrun@vX` on `main` (outside the CHANGELOG, advisories and release
  records), `RELEASE` in `published-action.yml` on `main`, the netdryrun.com home page and
  `llms.txt`, and the MCP Registry's latest version. One request per source, no retries: a source
  that can't be reached is SKIP, never a pass.

The nightly gate on `main` runs the same checks between releases (`release_gate.py consistency
--strict`), outside the release record: a failure there pages the owner and blocks promotion.

## What blocks a release

`GATE.md` says **CLEARED** only when all of these hold:

- every automatic layer (static, unit, mutation, live, after-publish) has been recorded;
- every layer ran on the same commit, with no uncommitted changes;
- no BLOCKER check failed or was skipped;
- every MAJOR check passed or was accepted with a reason;
- the independent review is recorded.

Otherwise it says **NOT CLEARED** (a BLOCKER failed), **READY TO PUBLISH** (everything holds except
the after-publish proof, which can only run once the release is out: this is the state to tag in), or
**INCOMPLETE** (something else is missing). A MAJOR check that was skipped, not failed, is accepted the
same way as a failed one.
A release is never "probably fine".

## Cutting a release

1. **Branch.** Create `release/X.Y.Z` from `main`.
2. **Bump the version** in `pyproject.toml` and `src/netdryrun/__init__.py`, then run
   `python scripts/sync_facts.py` to update `server.json` and the version in the docs.
3. **Write the CHANGELOG.** Move the Unreleased entries under `## X.Y.Z (YYYY-MM-DD)`. Add a
   **Security** section when the release fixes anything security-relevant.
4. **Run the gate on the candidate:**
   `python scripts/release_gate.py static --candidate --strict --fastfix-base <previous release tag>`, then
   `unit`, `mutation` and, on the lab machine, `live`. The static layer's `loosening` and `reproduce-first` checks
   cover every commit since that base (`tests/oracles/README.md`, `fastfix/README.md`); for the first release after
   they landed, pass the commit that brought them to main, since older commits carry no trailers. Fix every BLOCKER, then fix or accept every MAJOR. Record the
   independent review in `releases/X.Y.Z/review.md`. `report` must say READY TO PUBLISH.
5. **Commit `releases/X.Y.Z/`** (the layer records, `GATE.md`, `mutants.md`, `accepted.json`
   and `review.md`) together with the release changes.
6. **Tag and push:** `git tag vX.Y.Z && git push origin vX.Y.Z`. The release workflow publishes
   to PyPI and creates the GitHub release. The MCP Registry workflow publishes `server.json`.
7. **Merge** the release branch into `main` (a merge commit), then bump `RELEASE` and the `uses:`
   pins in `published-action.yml` on `main` (the commit `git ls-remote origin 'refs/tags/vX.Y.Z^{}'` prints, with a
   `# vX.Y.Z` comment; the workflow fails if the tag and the pin differ). The website deploys from `main`. The
   release on GitHub carries the wheel, the sdist, the Sigstore bundle (`netdryrun-vX.Y.Z.sigstore.json`) and the
   same SLSA provenance as in-toto JSON Lines (`netdryrun-vX.Y.Z.intoto.jsonl`).
8. **Paste the release notes** into the GitHub release and mark it **latest**, before CLEARED: the
   after-publish consistency check fails until the GitHub latest release is `vX.Y.Z`.
9. **Prove it:** run `python scripts/release_gate.py after-publish X.Y.Z` and commit the updated
   `releases/X.Y.Z/`. Then `report` must say CLEARED; merge that record into `main`.

## Running it in CI

[`.github/workflows/release-gate.yml`](.github/workflows/release-gate.yml) runs the static and
unit layers with `--strict` on every pull request. Mutation testing runs when the workflow is
started by hand. The reports are uploaded as artifacts and shown on the job page. The live
layer needs the lab machine and does not run in CI.
