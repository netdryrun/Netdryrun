# Scale test

`scripts/scale_test.sh LEAVES` runs a generated FRR leaf-spine fabric (`scripts/scale_topology.py`): LEAVES leaves + 2 spines, eBGP, each leaf announcing one /24 over two /30 links. `48` = 50 nodes, `98` = 100 nodes. Every leaf gets five guard checks (two sessions, an exact prefix count from spine1, a route to the next leaf's LAN, no BGP default route) plus one ping across the fabric: `5 * LEAVES + 1` checks.

Each size runs twice: **pass** (clean fabric, `netdryrun` must exit 0) and **leak** (one leaf also originates `0.0.0.0/0`, it must exit 1). Output in `OUT/scale-<LEAVES>.json`: per variant the exit code, seconds for deploy+wait, convergence gate, checks and destroy, and the peak memory of the lab's containers (sampled every 5 s with `docker stats`).

```bash
scripts/scale_test.sh 4                  # smoke, 6 nodes, no lock
scripts/scale_test.sh 48 --out ~/scale   # 50 nodes: takes /home/ndr/vendor-vm-lab.lock
scripts/scale_test.sh 98 --out ~/scale   # 100 nodes
```

Runs above 8 leaves take the lab lock (`NDR_LAB_LOCK`, default `/home/ndr/vendor-vm-lab.lock`) and refuse to start if it is held. The release gate runs `scale_test.sh --no-lock` itself (`live/scale`, a BLOCKER, 50 nodes by default; `--scale-leaves 48,98` adds the 100-node lab; `--skip-scale` records a SKIP).

## Memory

Measured on the lab machine (WSL, 15.8 GB, 20 CPUs), 6 nodes: peak 149-178 MiB for the lab's containers, 25-30 MiB per node (`docker stats`, includes page cache). Estimates beyond that are extrapolations until the 50 and 100 node runs are recorded:

| Nodes | Containers (est.) | With Docker / kernel overhead (est.) |
|---|---|---|
| 50 | about 1.5 GiB | 2-2.5 GiB |
| 100 | about 3 GiB (leaf 28 MiB, spines grow with their peer count) | 4-4.5 GiB |
| 250 | about 7.5 GiB | 10-11 GiB, at the limit |

The machine runs about 2.2 GB of its own plus any other lab, so roughly 10-11 GB is free for a lab. **RAM allows about 200 nodes; practical ceiling is 100-150** because the default `172.20.20.0/24` management network holds 254 nodes, `fs.inotify.max_user_instances` should be at least 1024, and the checks run one after another (about 1.3 s each in the 6-node smoke, so about 10 minutes for the 491 checks of the 100-node lab). The generator refuses more than 250 leaves.
