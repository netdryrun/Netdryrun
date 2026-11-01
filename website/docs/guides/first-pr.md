---
title: Your first pull request, in a browser (Codespaces)
description: Make a first contribution to Netdryrun from GitHub Codespaces, with no local Docker or containerlab, using a lab template as the worked example.
---

# Your first pull request, in a browser

You don't need Docker, containerlab or Linux on your machine. A GitHub Codespace has all three, runs the FRR examples, and costs nothing within GitHub's free monthly allowance (see [getting started](../getting-started.md) for the numbers). This guide walks through one real contribution end to end: packaging an example as a **lab template**, a lab with its expected verdict and a broken variant that must fail. The same steps work for a corpus case, a docs fix or a [good first issue](https://github.com/netdryrun/Netdryrun/labels/good%20first%20issue).

!!! note "Next release"
    The lab-template format and the contributor gates are new on the main branch after 0.4.0. Everything below runs from a clone of main, which is what a Codespace is.

## 1. Open a codespace

[Open Netdryrun in GitHub Codespaces](https://codespaces.new/netdryrun/Netdryrun?quickstart=1) and click **Create codespace**. It takes a few minutes the first time: it installs Netdryrun from the checkout and pulls the FRR image. Then, in the terminal:

```bash
pip install -e ".[dev]"      # adds pytest and the test tools
pytest -q                    # the unit tests, no lab: a few minutes
```

## 2. Make the change

A template lives in `community/labs/<name>/`: the lab, its `netdryrun.yml`, a `template.yml` that says what it is, and `bad/`, the files that the broken variant replaces ([format](https://github.com/netdryrun/Netdryrun/blob/main/community/labs/README.md)). Here, the FRR triangle from `examples/frr-bgp`, broken by the leaking `r2` config from `examples/frr-bgp-broken`:

```bash
mkdir -p community/labs/frr-triangle/bad/configs
cp -r examples/frr-bgp/. community/labs/frr-triangle/
cp examples/frr-bgp-broken/r2-bad.conf community/labs/frr-triangle/bad/configs/r2.conf
```

Then write `community/labs/frr-triangle/template.yml`:

```yaml
name: frr-triangle
description: Three FRR routers in an eBGP triangle; the checks guard each LAN route and that no default route leaks.
nos: [frr]
images: [quay.io/frrouting/frr:10.4.1]
licence: free
expected: {good: passed, bad: failed}
bad_change: r2 originates a default route and leaks it to its peers
author: your-github-handle
source: examples/frr-bgp and examples/frr-bgp-broken
```

## 3. Check it the way CI will

```bash
python scripts/contrib_gate.py labs            # the format
netdryrun run community/labs/frr-triangle      # the good lab must pass (exit 0)
```

For the broken variant, copy the lab, lay `bad/` over it, and run it: it must fail (exit 1).

```bash
rm -rf /tmp/bad && cp -r community/labs/frr-triangle /tmp/bad && cp -r /tmp/bad/bad/. /tmp/bad/ && rm -rf /tmp/bad/bad
netdryrun run /tmp/bad; echo "exit $?"
```

## 4. Commit and open the pull request

Sign off your commit: it certifies the [Developer Certificate of Origin](https://developercertificate.org/), that you have the right to contribute it. CI checks every commit for it.

```bash
git checkout -b lab-frr-triangle
git add community/labs/frr-triangle
git commit -s -m "Lab template: FRR triangle with a leaking r2"
git push -u origin lab-frr-triangle
```

You can't push to netdryrun/Netdryrun itself, so GitHub offers to create a fork and push there. Then open the pull request from your fork. The template asks four things: what changed, the test that fails without it (here: n/a, it's a template), the evidence (the two runs' last lines), and whether you used AI tools. Tick one box; either is fine.

## 5. What happens next

The [contributor gates](../how-its-run.md#the-contributor-gates) run within minutes, with no secrets, on your fork's pull request. If one fails, its message says what to fix. Any comment from one of our agents starts with "Automated triage" and states facts only; the decision to merge is the owner's. The owner may add the `run-labs` label, which runs your good and bad labs live in CI.

When you're done, stop or delete the codespace at [github.com/codespaces](https://github.com/codespaces) so it doesn't use your allowance.
