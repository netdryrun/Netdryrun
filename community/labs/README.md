# Community lab templates

A lab template is a containerlab lab that someone can copy to test their own change, shipped with its expected verdict
and a broken variant that must fail. Templates are inputs, not verdict logic: they can't make a check pass that
should fail, which makes them the safest first contribution. The format is new after 0.4.0 (next release).

Labs you'd rather keep in your own repository: give that repository the GitHub topic `netdryrun-lab`.

## The format

```text
community/labs/<name>/
  template.yml          what the template is (below)
  topology.clab.yml     the lab, with every image pinned
  configs/...           the configs the topology binds
  netdryrun.yml         the checks; the good lab must pass them
  bad/...               the broken variant: files that replace files of the good lab, at the same paths
  reports/good.json     bring-your-own-image templates only: your run's JSON reports (--json)
  reports/bad.json
  README.md             optional: the design, and what each check guards
```

`template.yml`:

| Key | Meaning |
|---|---|
| `name` | The folder name |
| `description` | One or two sentences: the design and what the checks guard |
| `nos` | Drivers the lab uses (`frr`, `srlinux`, `eos`, `sonic`, `junos`) |
| `images` | Every image, pinned to a version tag or a digest (never `latest`) |
| `licence` | `free` (CI can pull every image) or `bring-your-own-image` |
| `expected` | Always `{good: passed, bad: failed}` |
| `bad_change` | One line: what the broken variant does wrong |
| `author` | Your GitHub handle |
| `source` | Where the lab comes from (written for this template, adapted from ..., with its licence) |

The broken variant is the good lab with `bad/` laid over it: every file in `bad/` must replace a file the good lab
has. Keep it to one realistic mistake that one of the checks catches.

## What CI checks

On every pull request (`python scripts/contrib_gate.py labs`): `template.yml` has every key, the expected verdicts,
known drivers, pinned images, a non-empty `bad/` that only replaces existing files, a topology containerlab can read
and a `netdryrun.yml` that validates. A `bring-your-own-image` template needs both reports, with `passed` and `failed`.

With the `run-labs` label, which a maintainer adds: `free` templates run live; the good lab must exit 0 and the bad
variant must exit 1. `bring-your-own-image` templates are verified only by your attached reports, and the site says so.

Try it in a codespace first: [your first pull request](https://netdryrun.com/guides/first-pr/).
