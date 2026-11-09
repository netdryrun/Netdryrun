# Oracle spec RT-S01: `record --attributes` on SR Linux drops an AS path it can't read, without a warning

Status: **spec only**. The oracle itself is written after the live capture, by a session that is not the fixer
(`tests/oracles/README.md`). The capture waits for a night window and the IPI hub's ok, requested through the
coordinator.

## The bug
- **Where published:** case 4 of `advisories/0.4.1-known-false-passes/README.md` (GHSA-ggcf-664f-c9ff), and the
  CHANGELOG 0.4.1 known limits.
- **What happens:** `netdryrun record --attributes` on SR Linux writes a `bgp_route` check per BGP route, with the best
  path's AS path and local preference.
- **Since 0.4.1** (45f63df), a best path whose AS path SR Linux prints with no segment reads as unknown (`None`). The
  usual case is a route the iBGP peer originates. In 0.4.0 it was pinned as the empty AS path `""`.
- `record._attribute_check` then leaves `as_path` out of the check, and no warning is printed, while the CLI reference
  says the AS path is pinned.
- A later change of that path then passes the recorded baseline, for example a hijacked origin relayed by the same
  peer.
- **Offline reproduction:** red team B on 26380cb, `wt/redteam-26380cb/V/candidates_scripts/RT-S01-*.py`, shows
  `warnings: []` and then `PASS` after the AS path becomes `64666`.

## Evidence to capture (live, one SR Linux lab, about 10 min)
- **Lab:** `examples/srl-frr`, or two SR Linux nodes in one AS, with the image pinned by digest.
- **Setup:** srl2 originates `10.50.0.0/24` into iBGP, so srl1 learns it with an empty AS path.
- **On srl1, save the raw output, byte for byte, of the exact commands the driver sends:**
  - the `bgp-rib ipv4-unicast local-rib route 10.50.0.0/24` read;
  - the `attr-set <index>` read for its best path.
- **Save to:** `tests/fixtures/srl_rt_s01_bgp_rib.txt` and `tests/fixtures/srl_rt_s01_attr_set.txt`, plus a
  `capture.txt` with the image digest, the command lines and the date.
- **Also capture the same two reads after srl2 relays the route with a foreign AS path** (an `as-path prepend 64666`
  policy, or a third AS behind srl2). This lets the oracle show the recorded check passing on the changed path.

## The oracle (to write after the capture)
- **Folder:** `tests/oracles/RT-S01/`.
- **`ORACLE.yml`:**
  - `id: RT-S01`;
  - `bug:` the one line above;
  - `evidence:` the fixture files, which are the only files it reads that the base lacks.
- **`test_oracle_rt_s01.py`**, through the real code only (SrlDriver, `record._attribute_check`, `run_check`, all
  fed the captured replies):
  1. **Recording a route whose best path has an empty AS path is never silent.** Either the check pins the empty AS
     path (`as_path: ""`), or `record` prints a warning that names the route and the attribute it couldn't pin and
     marks the baseline incomplete.
  2. **The recorded check fails, or is not proven, when the AS path changes** (the second capture). It never passes.
  3. **Every other attribute the driver can't read** (local preference None on the captured shape) also gets a
     warning, not a silent drop.
- **Every test in the oracle folder must fail with an assertion on the commit before the fix** (0.4.1 behaviour: no
  `as_path`, no warning, PASS after the change). A test that passes there too is a guard: it goes in
  `tests/test_oracle_guards_rt_s01.py`, listed in `evidence:` (fastfix/oracle-specs/TEMPLATE.md).
- **Commit:** the oracle commit carries `Oracle: RT-S01` and its own `Session:` marker. It changes `tests/` only.

## The fix (another session, after the oracle exists)
- **Commit:** it carries `Fixes-Oracle: RT-S01` and a different `Session:`, and edits nothing under
  `tests/oracles/RT-S01/` or its evidence.
- **Rule:** a record attribute the driver can't read produces a named warning, or fails the recording. It is never
  silently dropped.
- **Also check** local_pref None noise per driver, and the `cli.md` `--attributes` row.
- **Registry:**
  - the `rt-s01-record-as-path` entry in `tests/known_false_passes.yml` then names the oracle test and moves to
    `fixed`;
  - the advisory and CHANGELOG say "fixed in 0.4.2".

## Decision for 0.4.2 (coordinator, 2026-11-10)
- **The oracle as written:** it is `tests/oracles/FP-042-RTS01/`, renamed so the gate accepts its ID. It accepts
  either outcome: `as_path: ""` pinned, or an INCOMPLETE BASELINE line naming the route and its AS path.
- **The fix in 0.4.2 is the gap (91703e7).** The live capture (SR Linux 26.7.2, iBGP) shows the route's attr-set with
  no as-path container while SR Linux's own report prints `Path : i`.
  - Pinning `""` would mean reading a missing container as the empty path at run time too.
  - A container missing for any other reason (a partial answer, a schema change) would then match the pinned `""`
    and pass: a false pass.
  - The gap exits 1 and names the route: a safe usability cost.
- **Follow-up for 0.4.3, as its own oracle:** the exact read. A missing container reads as the empty path only where
  a cross-check confirms it (for example SR Linux's report printing `Path : i`). On a route learned over eBGP, a
  missing container is an error, never the empty path.
