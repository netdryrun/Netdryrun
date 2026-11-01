# Latency benchmark

Measures where a `netdryrun run` spends its time, cold, on the example labs, with a good change and broken ones,
and prints p50/p95 per phase. The phases come from the run's own `timings` (Netdryrun 0.4.1 and later); an older
version is timed by the wall clock only, so a base release and a candidate can be compared on one host.

```bash
# on the lab machine, one job at a time
bench/latency/locked.sh "bench before" python bench/latency/bench.py run --lab frr-bgp --lab srl-frr \
    --change good --change missing -n 10 --netdryrun /path/to/base/venv/bin/netdryrun --label before \
    --out bench/latency/results/before.jsonl
bench/latency/locked.sh "bench after" python bench/latency/bench.py run --lab frr-bgp --lab srl-frr \
    --change good --change missing -n 10 --netdryrun .venv/bin/netdryrun --label after \
    --out bench/latency/results/after.jsonl
python bench/latency/bench.py report bench/latency/results/*.jsonl
```

Changes per lab (`CHANGES` in `bench.py`): `good` (the example as it is), `missing` (one announced prefix
removed, so a positive check fails) and, on `frr-bgp`, `leak` (the example's own bad change, so a negative check
fails). The report ends with a verdict-agreement list: every trial of a lab and change must end with the same
status under every label, or the exit code is 1.

Phases (`runner.PHASES`): deploy (`containerlab deploy`), boot (containers running, setup commands), converge
(the positive checks, then the BGP gate), ready (within converge: until every node with a positive check gave
usable state), settle, checks (post-convergence checks, scenarios, the config-load read), destroy.

Never publish a table that includes cEOS: Arista's licence forbids publishing benchmark results.
