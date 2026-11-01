# Advisory: Netdryrun 0.3.2 could pass on an FRR lab that skipped a config line

**Affected:** netdryrun 0.3.2 and earlier, and the `netdryrun/netdryrun@v0.3.2` Action, on labs with FRR nodes. **Fixed in:** 0.3.3. **Found by:** our own 0.4 work, which reproduced it on a live lab, before any outside user reported it.

## What happened

FRR loads its configuration line by line when the container boots. A line it rejects is skipped, and the router keeps running without it. Examples are a typo such as `neighbor 10.0.12.2 default-orignate`, an incomplete command, or a command this FRR release doesn't have. The only trace is a line in the container's log.

Netdryrun 0.3.2 didn't read that log. The checks ran on a lab without the changed line, so they tested a network the change never reached, and a run could pass. A check that the change must not break something passes trivially when the change isn't there.

## What 0.3.3 does

After the checks, Netdryrun reads the boot log of every FRR node in the lab, including nodes no check names. If FRR rejected any line, the run is an **error (exit 2)**, never a pass. The message names the node, the line number, the line and the reason:

```text
FRR rejected configuration lines at boot, so the lab ran without them and the checks did not test the change as
written: r1: line 21: neighbor 10.0.12.2 default-orignate (Unknown command); line 22: neighbor 10.0.12.2
maximum-prefix (Command incomplete); line 23: neighbor 10.9.9.9 route-map ALLOW-ALL in (rejected by bgpd). Fix the
config and run again.
```

A daemon can complain about a line and still apply it (bgpd answers `bgp graceful-restart` with "Failure to communicate" on FRR 10.4.1). So such a line doesn't count when line N of the node's `frr.conf` is that line and that daemon's own running config (`vtysh -d <daemon>`) has it under the same headers at every depth (`router bgp`, VRF, address family, `vni`), at least as many times as the file does, and has the line's whole block as written. A refused header line (`vni 10`, `address-family ...`) always counts. Every other kind of rejection always counts, and so does any line when the running config or `frr.conf` can't be read. (Without that, 0.3.3's own release gate saw a false error on Verdict Corpus case 29.) A boot log that can't be read is an error too. Config applied with `setup:` commands already failed the run in 0.3.2, because `vtysh -c` exits 1 on a rejected line.

## Proof

The tests run on every commit. They are built from real `docker logs` output of `quay.io/frrouting/frr:10.4.1`, started as containerlab starts it, with the three bad lines above:

- `tests/test_frr_config_load.py`: the rejected lines are read from the real boot log; a clean boot still passes; a rejected line on any FRR node makes the run an error, with or without `--deploy`; an unreadable log is an error; a rejected `setup:` command stops the run.
- Fixtures: `tests/fixtures/frr_boot_log_rejected.txt`, `frr_boot_log_rejected.conf`, `frr_boot_log_clean.txt`.

To reproduce, add a misspelled line to a router's `frr.conf` in any FRR lab, for example `examples/frr-bgp`, and run the same checks. 0.3.2 reports what the checks saw. 0.3.3 stops with exit 2 and names the line.

## Limits that remain in 0.3.3

- **Startup config on Arista cEOS, Nokia SR Linux and SONiC** (fixed in 0.4): a line the NOS rejected at boot makes the run an error (exit 2). cEOS skips such a line and loads the rest, like FRR: Netdryrun reads `show startup-config errors` after the checks, and any listed line, or output it can't read, is an error naming the line. SR Linux: a CLI startup config is one commit containerlab applies at deploy, and a line that doesn't parse or a commit that fails fails the deploy; a JSON one SR Linux loads itself and, when it rejects it, runs without it while the deploy succeeds, so Netdryrun reads its log ("Load of startup configuration failed"; a log it can't read is an error). SONiC (docker-sonic-vs) has no startup config: it is configured with `setup:` commands, which stop the run when they exit non-zero; a config file bound into a SONiC node's `/etc`, `/usr` or `/var/lib`, or an inline startup config, is an error. A `setup:` command is checked by its exit code only: SONiC's `config ...` commands and CONFIG_DB writes can exit 0 and fail later, so configure SONiC's routing with `vtysh -c` lines, which fail at once. On a lab Netdryrun didn't deploy (`netdryrun check`), SR Linux and SONiC say `not verified`. **A topology `exec:` command that fails** is an error on every platform: containerlab only logs it and exits 0, and the node runs without what it configured. **Juniper cJunosEvolved (beta): the config load is not verified yet**; the report says `not verified on junos`: add a positive check for what each changed line creates.
- The other limits are listed in the [0.3.0 advisory](../0.3.0-false-pass/README.md#limits-that-remain-in-031).

## Found another way it can pass without looking?

[Open a corpus case](https://github.com/netdryrun/netdryrun/issues/new?template=corpus-case.yml): it becomes a permanent must-fail test, credited to you.
