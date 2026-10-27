# WIP notes: NetBox → nrx → Netdryrun (branch ndr/netbox-nrx, paused)

Status: paused on 2026-10-27. The end-to-end test was done; the example and docs are on this branch, not merged.

## What is on the branch

- `examples/netbox-nrx/`: `netbox/seed.py` (loads 4 FRR routers in a ring into an empty NetBox), `netbox/frr.conf.j2` (NetBox config template), `netbox/bad_change.py` (the bad change), `nrx/` (nrx.conf, platform map, FRR node template, topology template), `lab/` (nrx's export plus `netdryrun.yml`), README with every command.
- `website/docs/netbox.md`, a nav entry, a row and section in `website/docs/examples.md`, a CHANGELOG line. Review before merging.

## Versions

NetBox 4.7 (netbox-docker 5.1.1), nrx 0.9.0 from PyPI (templates 0.4.0), containerlab 0.81.1, FRR 10.4.1, Netdryrun 0.3.0, WSL2 Ubuntu 22.04 (20 cores, 16 GB).

## What nrx produced

- License: Apache-2.0.
- Wiring: one containerlab node per device (site + role filter), one link per cable.
- Kind and image: from the NetBox platform via a platform map (`frr` → `linux` node, `quay.io/frrouting/frr:10.4.1`).
- Configs: only if NetBox has a config template; nrx calls NetBox's render-config and writes `<device>.config`. Our template renders the full FRR config from NetBox data (addresses, ASN from config context, a neighbor per cable), so no hand-written configs.
- Interface names: cabled interfaces renamed `eth1..N` in text-sorted order of the NetBox names; configs must use those names.

## What didn't work out of the box

- NetBox 4.7 returns `400 Bad Request` for nrx's default role filter (it names roles that don't exist). Fix: `nrx.conf` with `EXPORT_DEVICE_ROLES = ['router']`.
- nrx's stock `linux` node template drops the rendered config. Fix: custom `nrx/clab/nodes/frr.j2` binding it to `/etc/frr/frr.conf`.
- nrx's stock `topology.j2` adds a "graphite" visualization node on port 8080; we use a basic topology template instead.
- netbox-docker's first start: compose reported the netbox container unhealthy while migrations ran; a second `docker compose up -d` started the worker.
- The raw recording is flaky: exact prefix counts in a ring change from boot to boot (equal-length paths). The committed baseline uses 1..10.
- NetBox v2 tokens (`nbt_<key>.<token>`) work with nrx's `Token` header.

## Measured times

| Step | Result | Time |
|---|---|---|
| Pull NetBox images (first time) | | 65 s |
| `seed.py` | 4 routers, 4 cables, config template | 6 s (3 s rerun) |
| nrx export | 4 nodes, 4 links, 4 configs | 1.4 s (1.1 s re-export) |
| `netdryrun record --deploy` | 28 checks | 51 s |
| run, raw recording | 26 passed, 2 failed | 67 s |
| run, reviewed baseline | 33 passed, 0 failed | 73 s, 71 s |
| run, bad change | 27 passed, 6 failed, exit 1 | 205 s |

Bad change: r3's r2-r3 address `10.0.23.2/30` → `10.0.23.6/30` in NetBox, then re-export. Routes and the ping still pass (traffic goes the other way round the ring); both r2-r3 session checks, both prefix checks on that link, and the r1-r2 link-failure scenario fail.

## Checks run

`PYTHONPATH=src pytest` (158 passed), `scripts/sync_facts.py --check` (in sync), `netdryrun validate examples/netbox-nrx/lab` (OK), strict mkdocs build (OK).

## To resume

- NetBox containers were removed; volumes kept (compose project `ndrnetbox` in WSL `~/ndr-netbox/netbox-docker`, port 8765, admin/admin). `docker compose -p ndrnetbox up -d` brings it back; `seed.py` is idempotent.
- Open: not in the CI matrix; decide whether the website page ships.
