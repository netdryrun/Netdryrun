## What changes

<!-- One or two sentences. Link the issue if there is one. -->

## The test that fails without this change

<!-- For a change to a driver, a check, the runner, the config validator or verify: name the test. CI runs it on the
     base branch's code and expects it to fail there ("fails on revert"). Docs, examples and lab templates: write n/a. -->

## Evidence

<!-- Output of `pytest -q`, and for behaviour changes the netdryrun report (--json report.json) or the gate output.
     A capture bundle or lab template: say which lab and NOS version it ran on. -->

## AI use

Tick exactly one. This is a disclosure, not a ban: see [CONTRIBUTING.md](../CONTRIBUTING.md#ai-use).

- [ ] No AI tools were used for this change.
- [ ] AI tools were used. I have read every line, I understand it, and I can explain it without them.

## Checklist

- [ ] Every commit is signed off (`git commit -s`): I certify the [Developer Certificate of Origin](https://developercertificate.org/).
- [ ] No vendor images, licensed files or production data are included; captures went through `netdryrun sanitize`.
- [ ] Nothing here makes a check pass that failed before, unless the description says why and a must-fail test covers it.
