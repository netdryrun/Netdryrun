# Oracle spec FP-042-ADDRLOAD: the address parsers read JSON from after any leading text

Status: **spec only**. A session that is not the fixer writes the oracle. No lab is needed: the evidence is the
fuzzer's crash input and the parser's own fixtures.

## The finding (ClusterFuzzLite on PR #6, 2026-11-09)
- **Where:** the `fuzz` job on 4747d42, run of PR #6, `fuzz_parsers`, target `addresses.parse_eos_interfaces`
  (selector byte 10). The crash is reproducible: ClusterFuzzLite re-ran it and saved it as
  `crash-64187dc6186124ff3f0c0508128ec4d9c7acfc2d` (artifact `crashes-fuzz_parsers`).
- **The fuzzer's rule:** a parser in `CASES` may read empty only from a real empty answer. Any other output must
  raise DriverError (tests/test_driver_fuzz.py `outcome`).
- **The input:** 938 characters. It is the `eos_` interfaces fixture with `FFFFFFFFF` in front of the `{` and one
  `vrf` value mangled (`"defa�lt"`). The text as a whole is not JSON.
- **What happens:** `parse_eos_interfaces(text, "default", "x")` returns `[]`. It should raise DriverError
  (unexpected output).
- **The cause:** `addresses._load` (src/netdryrun/drivers/addresses.py:32) starts reading at the first `{` or `[`
  and silently drops everything before it. `base.load_json`, which the rest of the drivers use, refuses that.
- **Introduced:** 6d66267 (2026-11-06), shipped in v0.4.1. It was not introduced by the main merge or by
  surfaces_agree. The fuzzer found it now by chance: the same target was green on earlier runs.
- **Who reads through `_load`:**
  - `parse_ip_j_addr` (FRR, SONiC);
  - `parse_eos_interfaces`;
  - the NX-OS parsers (`parse_nxos_ip_brief`, and the detail parsers through `_nxos_rows`);
  - RouterOS, whose fuzz target calls `_load` itself before `parse_routeros_addresses`;
  - `parse_srl_addresses`;
  - `parse_junos_terse`.

## Minimal repros (checked on this tree, Windows Python, 2026-11-10)
```text
parse_eos_interfaces('% Invalid input\n{"interfaces":{}}', "default", "x")   -> []          (want DriverError)
parse_eos_interfaces('FFFF{"interfaces":{"Ethernet1":{"vrf":"default","interfaceAddress":
    {"primaryIp":{"address":"10.0.0.1","maskLen":31}}}}}', "default", "x")    -> [10.0.0.1/31] (want DriverError)
parse_eos_interfaces('<valid json>FFFF', ...)                                    -> DriverError  (already right)
```

## Why it matters (severity: low, a fail-closed rule broken)
- `local_addresses` feeds the ping guards in checks.py `_ping`:
  - **refuse_own_target:** a ping to the node's own address never leaves the node;
  - **the source check:** the source must be one of the node's lab addresses.
- If a device prints text before its JSON and the JSON lists fewer addresses than the node owns, the own-target guard
  sees too few addresses. A ping to the node's own address would then run and pass, a false pass (red team B-9006).
- With a `source`, the source check sees an empty list and refuses, so that case fails closed.
- No real capture has been seen with text before the JSON. Every address fixture that `_load` reads starts with `{`
  or `[`; the `frr1021u_*_ip_o_addr_*` text fixtures go through `lab.interface_addresses`, not `_load`. So no case
  should need the leniency, and the rule is: unexpected output is an error, never a quieter reading.

## The oracle
- **Folder:** `tests/oracles/FP-042-ADDRLOAD/`, with the crash input committed as evidence under `tests/`, for example
  `tests/fixtures/fuzz/crash-64187dc6186124ff3f0c0508128ec4d9c7acfc2d`, listed in `evidence:`.
- **The tests:**
  1. The crash input (without its selector byte) through `parse_eos_interfaces(text, "default", "x")` raises
     DriverError.
  2. Text before a valid document raises DriverError for every `_load` reader: `% Invalid input\n` and `FFFF` in front
     of each one's committed fixture.
  3. **Guard:** each reader's committed fixture, with only leading and trailing whitespace added, still parses to the
     same result as before.
- **On the parent commit:** tests 1 and 2 must fail with an assertion (use `pytest.raises(DriverError)`, which
  reports DID NOT RAISE), and test 3 passes there too.

## The fix (for the fixing session, after the oracle)
- `_load` reads the whole text: strip whitespace, then `json.loads`. Prefer `base.load_json`, which also refuses
  empty output and repeated keys; check that no address fixture repeats a key first.
- Add the crash input to `fuzz/seeds/parsers` so the fuzzer keeps it.
- CHANGELOG Unreleased: under Fixed.
