# Good first issues: drafts for the owner to post

Status: drafts, not posted. The owner reviews each one, edits it if needed and opens it on GitHub. Agents don't post
these and don't pick them up once posted: they are reserved for people new to the project.

Every issue gets the labels `good first issue` and `reserved-for-humans`, plus the area label shown. Each one names
the files, the check that must fail first, and an expected size under 100 lines. Items marked *(next release)* use
the capture kit or the lab-template format, which are on main but not in 0.4.0: contributors install from a clone.

Keep at least 5 open. When fewer are left, an agent drafts the next batch here from known limits, TODOs and the drift
report, and the owner approves the batch.

---

## 1. Lab template: the FRR triangle and its leaking r2 *(next release)*

Labels: `lab-template`

Package `examples/frr-bgp` (good) and `examples/frr-bgp-broken` (r2 leaks a default route) as the first template in
`community/labs/frr-triangle/`, in the format of `community/labs/README.md`.

- Files: `community/labs/frr-triangle/` (copy of the example, `template.yml`, `bad/configs/r2.conf`).
- Must fail first: `python scripts/contrib_gate.py labs` reports the missing pieces until the template is complete;
  the bad variant must exit 1 with `netdryrun run`.
- Size: a `template.yml` of about 10 lines plus copied files.
- Walkthrough: https://netdryrun.com/guides/first-pr/ does exactly this one, step by step.

## 2. Lab template: SR Linux and FRR with a hidden leak *(next release)*

Labels: `lab-template`

`examples/srl-hidden-leak` is already shaped like a template: a good lab, and `leaks/` with the same configs, each
with one change. Package it with `bad/configs/frr1.conf` taken from `leaks/frr1.conf` (one mistake per template;
the SR Linux leak in `leaks/srl1.cli` can be a second template).

- Files: `community/labs/srl-frr-hidden-leak/`.
- Must fail first: the bad variant must exit 1; say in `bad_change` which check catches it.
- Size: under 30 lines of new files besides the copied lab.

## 3. Lab template: SONiC and FRR, a port that stays down *(next release)*

Labels: `lab-template`

Build a template from `examples/sonic-frr` whose broken variant leaves the uplink administratively down in the SONiC
`setup:` commands. Note the SONiC VS image size in the template's README.

- Files: `community/labs/sonic-frr-port-down/`.
- Must fail first: the bad variant must exit 1 on a `bgp_session` check.
- Size: about 40 lines.

## 4. Capture bundle: FRR 10.4.1, `no-neighbor` *(next release)*

Labels: `capture`

Deploy `examples/frr-bgp`, shut one session on r1 (`neighbor 10.0.12.2 shutdown` in vtysh), then run
`netdryrun capture ... --node r1 --scenario no-neighbor` and `netdryrun sanitize --confirm`. Add the bundle under
`captures/frr/10.4.1/no-neighbor/`.

- Must fail first: `python scripts/contrib_gate.py provenance` must pass with your bundle in place (it fails on an
  unsanitised one).
- Size: the bundle only; no code.

## 5. Capture bundle: SR Linux, `med` *(next release)*

Labels: `capture`

From `examples/srl-frr`, set a MED on the FRR side's announcement to SR Linux and capture `--scenario med --prefix
<the prefix>` on the SR Linux node. Add it under `captures/srlinux/<version>/med/`.

- Must fail first: the bundle's `shows_scenario` must be `true`; `capture` exits 1 if the lab doesn't show a MED.
- Size: the bundle and a two-line config change you describe in the pull request.

## 6. Capture scenario: `rejected-config` *(next release)*

Labels: `capture`, `code`

The capture menu has no scenario for a config line the NOS rejected at boot, which the 0.3.2 advisory is about. Add
`rejected-config` for FRR: record the container's boot log the way the runner reads it (`Lab.boot_log`), and show
the scenario when `frr.parse_config_load_errors` finds at least one line.

- Files: `src/netdryrun/capture/collect.py`, `tests/test_capture.py`.
- Must fail first: a test that captures from a fake lab whose boot log is `tests/fixtures/frr_boot_log_rejected.txt`
  and expects `shows_scenario: true`.
- Size: under 60 lines.

## 7. Sanitiser: AS numbers in asdot form

Labels: `capture`, `code`

`netdryrun sanitize` rewrites `65001` but not the asdot form `1.10` (= 65546) that some NOSes print. Map asdot
numbers in AS contexts to the same private 4-byte range, printed in asdot again.

- Files: `src/netdryrun/capture/sanitize.py`, `tests/test_capture_sanitize.py`.
- Must fail first: `run('{"peer-as": "1.10"}')` still contains `1.10`.
- Size: under 50 lines.

## 8. Gate: two lab templates with the same lab name

Labels: `ci`, `code`

containerlab names containers after the topology's `name:`. Two templates with the same name would collide in the
live CI job. Make `python scripts/contrib_gate.py labs` report a name used twice.

- Files: `scripts/contrib_gate.py`, `tests/test_contrib_gate.py`.
- Must fail first: a test with two templates whose topologies share `name:` expects a problem.
- Size: under 30 lines.

## 9. Recipe: VRF isolation with today's checks

Labels: `docs`

Write a guard recipe for "VRF A never sees VRF B's routes": a `route` check with `present: false` per VRF, plus a
`ping` that must fail from A to B. Use only check types that exist today, and say what it doesn't prove.

- Files: `website/docs/recipes.md`.
- Must fail first: the recipe's YAML must pass `netdryrun validate` (paste it into a lab's `netdryrun.yml`).
- Size: about 40 lines.

## 10. Troubleshooting: "capture refused" *(next release)*

Labels: `docs`

Add a troubleshooting entry for `capture`'s refusals (not in the topology, not a lab node, the labels name another
lab), with the `docker inspect` command that shows a container's containerlab labels.

- Files: `website/docs/troubleshooting.md`.
- Must fail first: n/a (docs); run `python scripts/sync_facts.py` so `llms-full.txt` is regenerated.
- Size: about 25 lines.

## 11. FAQ: how do I report a wrong verdict?

Labels: `docs`

Add an FAQ entry pointing to the wrong-verdict form and the hall of fame on the trust page: what to attach, and that
a report counts once it is reproduced.

- Files: `website/docs/faq.md`.
- Must fail first: n/a (docs); `python scripts/sync_facts.py --check` must pass.
- Size: about 15 lines.

## 12. Corpus case proposal: an IPv6 leak

Labels: `corpus`

Every corpus case so far is IPv4. Propose an IPv6 route-leak case with the corpus-case form: the change, the expected
verdict decided before anything runs, and why an operator would reject it.

- Files: none (an issue with the corpus-case form).
- Must fail first: n/a; the expected verdict is written before any run.
- Size: one issue.

## 13. `capture`: list the scenarios with what each needs *(next release)*

Labels: `cli`, `code`

`netdryrun capture --help` lists scenario names only. Add `--list-scenarios`, printing each scenario, what the lab
must show and the options it needs (from `collect.SCENARIOS`), and document it on the capture kit page.

- Files: `src/netdryrun/cli.py`, `website/docs/reference/capture.md`, `tests/test_capture.py`.
- Must fail first: a test calling `cli.main(["capture", "--list-scenarios"])` expects every scenario name in the
  output (the docs test fails until the option is documented).
- Size: under 40 lines.

## 14. Fixture sources: name the NOS versions of the v0.1 fixtures

Labels: `tests`

`tests/fixtures/SOURCES.yml` says the v0.1 FRR and SR Linux fixtures don't record their versions. Re-capture them
with `scripts/capture_fixtures.sh frr` and `... srlinux`, compare with `scripts/fixture_shape.py`, and record the
versions (or the shape drift you found).

- Files: `tests/fixtures/SOURCES.yml` and the re-captured fixtures, if their scenario matches.
- Must fail first: `python scripts/fixture_shape.py` on your captures; report its output in the pull request.
- Size: depends on drift; under 100 lines of YAML and fixture changes.
