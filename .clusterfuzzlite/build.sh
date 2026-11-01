#!/bin/bash -eu
# Builds each fuzz/fuzz_*.py into a fuzzer with its seed corpus (ClusterFuzzLite runs this in the base-builder image).
# Dependencies come from the hash lock, Netdryrun from this checkout as a wheel.
python3 -m pip install --require-hashes -r requirements/ci.txt
python3 -m pip wheel --no-deps --no-build-isolation -w "$WORK/wheel" .
python3 -m pip install --no-deps "$WORK"/wheel/netdryrun-*.whl
python3 fuzz/seeds.py "$WORK/seeds"
for fuzzer in fuzz/fuzz_*.py; do
  name=$(basename -s .py "$fuzzer")
  # the targets and oracles live in tests/test_driver_fuzz.py, which reads the captured fixtures next to itself
  compile_python_fuzzer "$fuzzer" --paths tests --add-data "tests/fixtures:fixtures"
  (cd "$WORK/seeds/${name#fuzz_}" && zip -q -r "$OUT/${name}_seed_corpus.zip" .)
done
