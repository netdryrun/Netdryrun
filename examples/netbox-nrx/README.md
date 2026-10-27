# NetBox → nrx → Netdryrun

Test a change on a replica of your network built from NetBox: NetBox holds the devices, cables, addresses and a config template; [nrx](https://github.com/netreplica/nrx) exports them as a containerlab topology with one rendered config per device; Netdryrun boots the replica and checks it against a recorded baseline.

The demo network is four FRR routers in a ring (r1–r4, AS 65001–65004), each announcing one LAN over eBGP. It's made-up data, loaded by [`netbox/seed.py`](netbox/seed.py).

```text
examples/netbox-nrx/
  netbox/seed.py        loads the demo network into an empty NetBox
  netbox/frr.conf.j2    the NetBox config template that renders each router's FRR config
  netbox/bad_change.py  the bad change: a typo in r3's address on the r2-r3 link
  nrx/                  nrx settings, platform map and node template for FRR
  lab/                  what nrx exported (topology + r1..r4.config), plus netdryrun.yml
```

You don't need NetBox to try the result: the exported lab is committed.

```bash
netdryrun run examples/netbox-nrx/lab
```

## What nrx gives you, and what it doesn't

- **Wiring:** one containerlab node per NetBox device (filtered by site and role) and one link per cable.
- **Node kinds and images:** from the device's NetBox platform, through a platform map. [`nrx/platform_map.yaml`](nrx/platform_map.yaml) maps the platform `frr` to a `linux` node running `quay.io/frrouting/frr:10.4.1`.
- **Configs, if NetBox has them:** nrx asks NetBox to render each device's config template and writes it to `<device>.config`. With no config template, you get wiring only, and the configs (or `setup` lines in `netdryrun.yml`) are yours to write. Here the template [`netbox/frr.conf.j2`](netbox/frr.conf.j2) builds the whole FRR config from NetBox data: interface addresses, the ASN from the device's config context, and a BGP neighbor for the far end of each cable.
- **Interface names:** nrx names each device's cabled interfaces `eth1`, `eth2`, ... in the order of their NetBox names, sorted as text. Configs must use those names. This demo names the NetBox interfaces `eth1` and `eth2`, so they match. If your NetBox says `Ethernet1/1`, make the config template emit the emulated name (or use a NOS kind that nrx can give an interface map, such as cEOS).
- **FRR's own files:** nrx's stock node template for `linux` nodes drops the rendered config. [`nrx/clab/nodes/frr.j2`](nrx/clab/nodes/frr.j2) binds it to `/etc/frr/frr.conf` instead, next to the `daemons` and `vtysh.conf` files in `lab/`.

nrx is Apache-2.0, like Netdryrun.

## Steps

Tested on 2026-10-27 in WSL2 Ubuntu 22.04 (20 cores, 16 GB) with NetBox 4.7 (netbox-docker 5.1.1), nrx 0.9.0 (templates 0.4.0), containerlab 0.81.1, FRR 10.4.1 and Netdryrun™ 0.3.0.

### 1. Run NetBox

Use [netbox-docker](https://github.com/netbox-community/netbox-docker). This override publishes NetBox on port 8000 and creates an `admin` user. Use it for a local demo only.

```bash
git clone --depth 1 https://github.com/netbox-community/netbox-docker.git && cd netbox-docker
cat > docker-compose.override.yml <<'EOF'
services:
  netbox:
    ports:
      - "127.0.0.1:8000:8080"
    environment:
      SKIP_SUPERUSER: "false"
      SUPERUSER_NAME: admin
      SUPERUSER_EMAIL: admin@example.com
      SUPERUSER_PASSWORD: admin
EOF
docker compose up -d
```

The first start runs database migrations and takes a few minutes. Compose may report `netbox is unhealthy` the first time while they run; when the NetBox page loads, run `docker compose up -d` again to start the worker.

Get an API token for `admin`:

```bash
curl -s -X POST -H 'Content-Type: application/json' http://127.0.0.1:8000/api/users/tokens/provision/ \
  -d '{"username":"admin","password":"admin"}' \
  | python3 -c 'import json,sys; t=json.load(sys.stdin); print("nbt_%s.%s" % (t["key"], t["token"]))'
```

```bash
export NB_API_URL=http://127.0.0.1:8000
export NB_API_TOKEN=nbt_...   # the token printed above
```

### 2. Load the demo network

From a clone of this repository:

```bash
pip install nrx    # also installs pynetbox, which seed.py uses
nrx --init         # puts nrx's stock templates in ~/.nr
cd examples/netbox-nrx
python netbox/seed.py
```

This creates the site `demo-dc1`, the role `router`, the platform `frr` (with the `frr-bgp` config template attached), four devices, their interfaces and addresses, and four cables.

### 3. Export the replica

```bash
nrx -c nrx/nrx.conf -o clab -s demo-dc1 -n ndr-netbox-demo -T nrx -M nrx/platform_map.yaml -D lab
```

This writes `lab/ndr-netbox-demo.clab.yaml` and `lab/r1.config` to `lab/r4.config`. `-T nrx` puts this folder's templates ahead of the stock ones. [`nrx/nrx.conf`](nrx/nrx.conf) limits the export to the `router` role: nrx's default role list names roles this NetBox doesn't have, and NetBox 4.7 rejects that filter with `400 Bad Request`.

### 4. Record a baseline and review it

```bash
netdryrun record lab/ndr-netbox-demo.clab.yaml --deploy
```

It recorded 28 checks: 8 BGP sessions, 8 exact prefix counts and 12 routes. Running it straight away failed 2 of them. In a ring, two neighbors offer equal-length paths to the far LAN, so which one each router picks, and so how many prefixes each neighbor sends, changes from boot to boot. The committed [`lab/netdryrun.yml`](lab/netdryrun.yml) is the reviewed version: sessions and routes as recorded, prefix counts as 1 to 10, plus a ping, the best path to r2's LAN, no default route, and an r1-r2 link failure.

```bash
netdryrun run lab
```

```text
PASSED: 33 passed, 0 failed (33 checks)
```

### 5. Make a bad change in NetBox and test it

Someone mistypes r3's address on the r2-r3 link in NetBox: `10.0.23.2/30` becomes `10.0.23.6/30`. Make that change, export again, and run:

```bash
python netbox/bad_change.py
nrx -c nrx/nrx.conf -o clab -s demo-dc1 -n ndr-netbox-demo -T nrx -M nrx/platform_map.yaml -D lab
netdryrun run lab
```

```text
  [FAIL] r2: BGP session to 10.0.23.2 is established -- neighbor 10.0.23.2 not configured (seen: 10.0.12.1, 10.0.23.6) (60.2s)
  [FAIL] r3: BGP session to 10.0.23.1 is established -- state is active (60.2s)
  [FAIL] r2: prefixes from 10.0.23.2 >= 1 and <= 10 -- neighbor 10.0.23.2 not configured (seen: 10.0.12.1, 10.0.23.6) (30.1s)
  [FAIL] r3: prefixes from 10.0.23.1 >= 1 and <= 10 -- session is active; prefix counts are only meaningful when established (30.1s)
  [FAIL] [r1-r2 link fails] r1: BGP best path for 192.168.2.0/24 has as-path '65004 65003 65002', next hop 10.0.14.2 -- no BGP path (63.1s)
  [FAIL] [r1-r2 link fails] r1: ping 192.168.2.1 from 192.168.1.1 expects success -- 0/3 replies (need 2) (63.1s)
FAILED: 27 passed, 6 failed (33 checks)
```

Exit code `1`. Every LAN route and the ping still pass, because traffic goes the other way round the ring. What broke is the redundancy: the r2-r3 session is down, and once the r1-r2 link fails too, r2's LAN can't be reached from r1. A ping test alone would have passed this change.

Undo it and export again:

```bash
python netbox/bad_change.py --revert
nrx -c nrx/nrx.conf -o clab -s demo-dc1 -n ndr-netbox-demo -T nrx -M nrx/platform_map.yaml -D lab
```

Without NetBox, you can reproduce the same change by editing the exported configs: in `lab/r3.config` change `10.0.23.2/30` to `10.0.23.6/30`, and in `lab/r2.config` change neighbor `10.0.23.2` to `10.0.23.6`.

## Measured times

Wall-clock, images already pulled except where noted.

| Step | Time |
|---|---|
| Pull the NetBox images (first time) | 65 s |
| `seed.py` | 6 s (3 s when rerun) |
| `nrx` export | 1.4 s |
| `netdryrun record --deploy` | 51 s |
| `netdryrun run lab`, good change | 73 s and 71 s (two runs) |
| `netdryrun run lab`, bad change | 205 s (the failing checks wait out their 60 s timeout) |

## In CI

Commit the nrx export (`lab/`) and `netdryrun.yml` to a repository, and have the pipeline that changes NetBox run nrx and then the [GitHub Action](https://netdryrun.com/github-action/) on the result. Every NetBox change is then tested on a replica before anything is pushed to the network.
