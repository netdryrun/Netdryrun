# Contributed captures

Sanitised command output from contributors' own lab nodes, made with `netdryrun capture` and `netdryrun sanitize`
(next release; see the [capture kit](https://netdryrun.com/reference/capture/)). We never hold the images: only
the output contributors chose to share.

Layout: `captures/<nos>/<version>/<scenario>/` holds one bundle (`manifest.json` and `outputs/`). Nothing else goes
in this folder.

On every pull request, `python scripts/contrib_gate.py provenance` validates every bundle here: the manifest, each
file's sha256, the sanitiser's version and self-check, a fresh scan for public addresses and AS numbers, and a replay
through the driver (it must ask for exactly the bundle's commands and read what the manifest records). A bundle that
fails any of them can't merge. CODEOWNERS review applies as for `tests/fixtures`.

What captures unlock, and what they don't, is in [docs/captured-only.md](../docs/captured-only.md).
