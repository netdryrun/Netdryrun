# Layer 5b: the two agent jobs

`scripts/acceptance.py` runs angles 1 to 4 of Layer 5b ([RELEASING.md](../RELEASING.md)) on the lab machine and writes
`releases/<version>/acceptance.json` and `acceptance.md`. Two jobs need judgement and stay with agents. Run them the
same way on every release, so the hunt costs the same and is comparable. The gate's `acceptance` layer reads
`releases/<version>/acceptance-adversary.md` (job 1) and doesn't clear without it.

## Job 1: the adversary (angle 5)

Two attackers and one verifier, each a fresh agent with no context from this session or earlier runs.

**Isolation, by what the agents get.** Export the candidate commit's code and user docs only, with no tests other
than the red-team harness, and no advisories, changelog, reviews or audits. Make one copy per attacker:

```bash
for n in A B; do
  D=~/ndr-redteam-<version>-$n; rm -rf "$D"; mkdir -p "$D/candidates"
  git archive <sha> src examples website/docs/reference website/docs/getting-started.md README.md \
    tests/test_redteam.py tests/fixtures tests/redteam/README.md | tar -x -C "$D"
done
```

The harness: `cd $D && NDR_REDTEAM_DIR=$PWD/candidates PYTHONPATH=src:tests python -m pytest -q tests/test_redteam.py -k "is_refused or does_not_pass"`.
A candidate whose test fails made Netdryrun report a pass, or accept a config. That makes it a candidate, not yet a finding.

**Attacker A: the drivers.** Paste this:

> You are testing a network change verifier whose one unforgivable bug is reporting passed when the check didn't
> test what the file says. Work only in `$D`, offline: no labs or containers. Focus on the drivers, the parsers of
> raw device output, for every driver in `src/netdryrun/drivers/`. Look at longest-match answers, VRFs, IPv6, named,
> large and extended communities, route subtypes, routes received but not installed, not best or not programmed,
> graceful restart and stale routes, truncated or paginated output, an empty answer that isn't an error, per-AFI
> tables, and address formats. Craft device output that the real NOS release in `tests/fixtures/` would print. These
> are already known: <the title of every file in tests/redteam/, one per line>. Find new ones. For each success,
> write a case file and say: the check as the user meant it, the output, why it violates that meaning, why the NOS
> prints it (cite the fixture or format), and how to reproduce it in containerlab. Count the attempts that were
> correctly refused. About 90 minutes.

**Attacker B: checks, config, record and verify.** Use the same prompt as A, with a different focus:

> Focus on the checks, config loading, `record`, `verify_change`, failure scenarios and the JSON and MCP verdicts:
> YAML parsing (duplicate keys, coercion, anchors), prefix and address normalisation, defaults, convergence gates,
> negative checks, a scenario that doesn't take effect, intent lines that explain more than they declare, and what
> `record` leaves out of a baseline. You may also show a wrong pass with a short script that calls the library on
> fake state.

**The verifier.** Start it fresh, and give it only the candidates and the same export:

> For each candidate, decide whether it is a REAL false pass, documented behaviour (quote the reference docs'
> sentence), or a state or output the pinned NOS release can't produce. Be skeptical in both directions. For each
> one, give the verdict, the severity, and the exact lab state or CLI that would confirm it live.

**Confirm it live** before calling a candidate real, on the lab machine under the lab lock, in the smallest
example lab that shows it. File each confirmed case as the next `tests/redteam/RT-NNNN-*.yml`, written to fail
before the fix, on the acceptance branch. A confirmed false pass is a BLOCKER: report it to the coordinator at once.

**Record** the outcome in `releases/<version>/acceptance-adversary.md`:

```markdown
# Angle 5: adversary, Netdryrun <version>

Commit <full sha of the candidate>

Result: no open false pass        (or: Result: open false pass)

| Candidate | Attacker | Verdict | Live | Case | Fixed in |
|---|---|---|---|---|---|

Attempts refused: A <n>, B <n>.
```

The gate reads the `Commit` line and the `Result:` line. A file for another commit doesn't count.

## Job 2: reading the mismatches

`acceptance.py` exits 1 on any mismatch, leftover lab, traceback or item it couldn't cover. Give one agent
`acceptance.md` and the work folder (`~/ndr-acceptance/<version>`; `reports/` holds every JSON report, `state.json`
every result), and paste this:

> For each item that is not `pass`, say which it is: (a) a false pass, where a change that must fail passed or a
> trap check passed (a BLOCKER: say so first); (b) a product bug, such as a wrong exit code, a broken documented
> command, a traceback, or a lab left behind; (c) a lab or image problem, such as a node that didn't boot or a
> missing image (rerun that item once with `--only <id>`); or (d) a stale expectation in the matrix or the docs'
> examples table. Quote the evidence for each one. Don't change an expectation to make an item pass: a
> documented outcome changes only with the docs, in a reviewed change.

A rerun keeps the results of every other item: the script resumes per commit. Use `--fresh` only for a new candidate.
