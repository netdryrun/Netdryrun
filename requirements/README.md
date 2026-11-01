# Hash-locked requirements for CI and the GitHub Action

Every `pip install` in `.github/workflows/` and `action.yml` installs from one of these files with
`--require-hashes`, then installs Netdryrun itself from the checkout with `--no-deps` (and the build backend from the
lock, `--no-build-isolation`). So nothing CI or the Action runs comes from PyPI without a hash checked.

| Lock | From | Used by |
|---|---|---|
| `runtime.txt` | `pyproject.toml` dependencies + `build.in` | `action.yml`, live-lab jobs |
| `ci.txt` | `pyproject.toml` with `[dev]` + `build.in` | unit tests, the release gate, contributor gates |
| `release.txt` | `release.in` | building and checking the release artifacts |
| `docs.txt` | `docs.in` | the website build |
| `tools.txt` | `tools.in` | uv and pipx where a workflow needs them |

The locks are universal (every Python from 3.10, every platform), written by `uv pip compile --universal
--generate-hashes`. Regenerate them all with `bash scripts/lock_requirements.sh` after changing `pyproject.toml` or an
`.in` file; Dependabot (`pip`, `/requirements`) proposes version bumps with new hashes.

`published-action.yml` is the exception on purpose: it installs Netdryrun from PyPI exactly as the docs tell users to
(`pip install netdryrun`), because what users type is what it tests.
