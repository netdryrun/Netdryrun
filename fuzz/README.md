# Fuzzing

Coverage-guided fuzzers ([Atheris](https://github.com/google/atheris)) for the code where a false pass hides:

| Fuzzer | Target | A finding is |
|---|---|---|
| `fuzz_parsers.py` | every device-output parser in `tests/test_driver_fuzz.py` (FRR, SONiC, SR Linux, EOS, Junos, NX-OS, RouterOS) | any exception but `DriverError`; an empty reading from output that isn't a real empty answer; a fail-safe parser outside its safe range |
| `fuzz_config.py` | `runner.load_config` (the `netdryrun.yml` loader every entry point uses) | an accepted check that dropped a key the file gave it, or a `present` that isn't a boolean; anything but `ConfigError` escaping |

The parser targets and oracles are the property tests' own, so a parser added to `tests/test_driver_fuzz.py` is
fuzzed too. Seeds are the captured fixtures and the shipped `netdryrun.yml` files (`python fuzz/seeds.py DIR`).

ClusterFuzzLite builds them (`.clusterfuzzlite/`) and runs them on pull requests that touch the code (5 minutes) and
weekly (30 minutes each): `.github/workflows/cflite.yml`. Locally (Linux, Python 3.10 or 3.11 for Atheris's wheels):

```bash
pip install --only-binary :all: atheris
python fuzz/seeds.py /tmp/seeds
python fuzz/fuzz_parsers.py /tmp/corpus /tmp/seeds/parsers -max_total_time=300
```

A finding is a possible false pass or crash. Report it; never silence an oracle to make a run green. Open findings
are in `findings/`, each pinned by a strict xfail in `tests/test_fuzz_harness.py` until it is fixed.
