<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/netdryrun/netdryrun/main/.github/assets/netdryrun-wordmark-white-tm.svg">
    <img alt="Netdryrun" src="https://raw.githubusercontent.com/netdryrun/netdryrun/main/.github/assets/netdryrun-wordmark-navy-tm.svg" width="360">
  </picture>
</p>

[![CI](https://github.com/netdryrun/netdryrun/actions/workflows/ci.yml/badge.svg)](https://github.com/netdryrun/netdryrun/actions/workflows/ci.yml) [![OpenSSF Scorecard](https://api.scorecard.dev/projects/github.com/netdryrun/netdryrun/badge)](https://scorecard.dev/viewer/?uri=github.com/netdryrun/netdryrun)

**Test network changes before they touch production.**

Netdryrun is an open-source (Apache-2.0) tool that dry-runs network changes in a real containerlab lab and returns a pass/fail verdict with evidence. It runs as a CLI, a GitHub Action, and an MCP server for AI agents.

Software teams don't ship code without running its tests. Network changes deserve the same step: run the change in a real lab, check how the network behaves, and ship only on a pass. Netdryrun makes that one command, one CI step, or one tool call for an AI agent.

**Already have a containerlab lab? [Add Netdryrun to it in 10 minutes](https://netdryrun.com/guides/your-lab/)**: record its steady state, add one guard, run it on every pull request.

Netdryrun™ boots your topology as a real virtual network ([containerlab](https://containerlab.dev)), applies your configs, and checks how the network actually *behaves*: BGP sessions, prefix counts, routes, reachability. It catches the mistakes your checks describe, such as a route leak, before the change reaches production, and leaves the commands and raw output for a reviewer to inspect.

<p align="center"><img alt="Netdryrun catching a leaked default route that ping and session checks miss" src="https://raw.githubusercontent.com/netdryrun/netdryrun/main/.github/assets/netdryrun-demo.gif" width="820"></p>

```text
$ netdryrun run examples/frr-bgp-broken
Deploying lab ndr-frr-broken (3 nodes)...
  [PASS] r1: BGP session to 10.0.12.2 is established -- state is established (6.3s)
  [PASS] r1: ping 192.168.3.1 from 192.168.1.1 expects success -- 3/3 replies (2.3s)
  ... (3 more passing checks trimmed)
  [FAIL] r1: route 0.0.0.0/0 via bgp is absent -- unexpectedly present via bgp (not selected) (0.1s)
FAILED: 5 passed, 1 failed (6 checks)
```

That run caught a leaked default route that was *received but not selected*. Ping and session checks alone would miss this example: every session is up and every address answers. (A static analyzer such as Batfish also catches this particular leak; the [Batfish page](https://netdryrun.com/batfish/) shows one that it misses and a lab catches.)

<!-- facts:readme_status -->
> Status: **v0.3.2.** Runs on Linux and WSL2, with drivers for FRR, Nokia SR Linux, SONiC (docker-sonic-vs) and Arista EOS (cEOS, bring your own image). On the [verdict corpus](https://netdryrun.com/corpus/) v1 (30 realistic BGP changes: 19 harmful, 11 safe), Netdryrun judged 24/30 correctly, ping-only checks 20/30 and all-sessions-up checks 15/30. Netdryrun approved 5 of the 19 harmful changes (ping-only checks: 10 of 19) and blocked 1 of the 11 safe ones. On v2 (18 cases written after v1 to target v1's misses): Netdryrun 17/18, ping-only 9/18, all-sessions-up 7/18. Expected verdicts were committed before any run, on one FRR topology: a comparison of testing methods, not a production reliability estimate. Method, every miss and a one-command rerun are on the corpus page. Provenance: both ran on Netdryrun 0.3.1.
<!-- /facts:readme_status -->

## Why

- **It tests behavior, not syntax.** A config diff shows what changed, not whether BGP comes up or which routes each router ends up with. A real control plane shows what the routing software actually does.
- **It's built for CI.** One GitHub Action, a pass/fail exit code, a Markdown summary in the job, JUnit XML, and a JSON evidence file with every command and raw output.
- **It waits for convergence, with stated rules.** A positive check passes after 2 passing samples taken 3 s apart, within its timeout. Negative checks ("this route must be absent") and best-path attribute checks wait until every configured BGP session on their node is up with stable prefix counts (sessions a check expects down don't count), then a 10 s settle, then must hold for 10 s (settle and hold are configurable). If a node still reports no BGP neighbors at the timeout, its checks run anyway and the result says BGP convergence was not seen. In a failure scenario, checks start only once the fault is visible in BGP (or the run ends with exit 2), and positive checks must hold too. Exit 0 passed, 1 checks failed, 2 not tested (config or lab problem), 3 inconclusive. The rules are sample-based; see [convergence semantics](https://netdryrun.com/reference/config/#convergence-semantics).

## Quick start

### Try it in your browser (no install)

[![Open in GitHub Codespaces](https://github.com/codespaces/badge.svg)](https://codespaces.new/netdryrun/netdryrun?quickstart=1)

The codespace comes with Docker, containerlab and Netdryrun already installed. When the terminal shows `Ready`, run:

```bash
bash examples/agent-demo/demo.sh
```

A route-leaking change is rejected, then the fix passes every check. It uses your GitHub account's free Codespaces hours (2-core machine). [Details](https://netdryrun.com/getting-started/#try-it-in-your-browser).

### On your own machine

Requirements: Linux or WSL2, Docker, [containerlab](https://containerlab.dev/install/), Python 3.10+. On Ubuntu 24.04 and Debian 12 a plain `pip install` outside a virtualenv is refused ("externally managed environment"), so use pipx: `sudo apt install pipx && pipx ensurepath`, then open a new terminal. `uv tool install netdryrun`, or `pip install netdryrun` inside an activated virtualenv, work too.

```bash
pipx install netdryrun
git clone https://github.com/netdryrun/netdryrun && cd netdryrun
netdryrun run examples/frr-bgp          # 3 FRR routers, should pass
netdryrun run examples/srl-frr          # SR Linux + FRR, should pass
netdryrun run examples/frr-bgp-broken   # a bad change, should fail
```

### On your own containerlab topology (3 commands)

```bash
netdryrun record my-lab/topology.clab.yml --deploy   # snapshot today's behavior into my-lab/netdryrun.yml
# ...edit your configs (the change you want to test)...
netdryrun run my-lab                                   # re-run the checks in my-lab/netdryrun.yml
```

`record` writes checks for every established BGP session, its exact prefix count and up to 50 BGP routes per node. It has no leak guards until you add them, and a session that is down today isn't recorded. Review it (remove what is allowed to change, add negative checks such as `present: false`), commit it, and every future change runs against it, locally or in CI. A pass means those checks passed, nothing more.

## netdryrun.yml

```yaml
lab: topology.clab.yml      # your containerlab topology
timeout: 90                 # seconds a positive check may wait for convergence

checks:
  - type: bgp_session       # session reaches a state (default: established)
    node: r1
    neighbor: 10.0.12.2
  - type: bgp_prefixes      # accepted prefix count within a range
    node: r1
    neighbor: 10.0.12.2
    min: 1
    max: 10
  - type: route             # route present (or absent), optionally via a protocol
    node: r1
    prefix: 192.168.3.0/24
    protocol: bgp
  - type: ping              # reachability, optionally from a source address
    node: r1
    source: 192.168.1.1
    target: 192.168.3.1
  - type: route             # negative check: must stay absent after convergence
    node: r1
    prefix: 0.0.0.0/0
    protocol: bgp
    present: false
```

Failure scenarios break something, check the network still behaves, then restore it. They can take links down, or (from 0.3.1) make an FRR neighbor announce routes it shouldn't, to prove a max-prefix limit or an import filter actually holds:

```yaml
scenarios:
  - name: r1-r2 link fails
    link_down: {node: r1, interface: eth1}
    checks:
      - {type: ping, node: r1, source: 192.168.1.1, target: 192.168.2.1}   # rerouted via r3
      - {type: bgp_session, node: r1, neighbor: 10.0.12.2, state: down}
  - name: customer floods 200 prefixes
    inject_routes: {node: ce1, count: 200, from: 10.100.16.0/24}
    checks:
      - {type: bgp_prefixes, node: up1, neighbor: 10.0.2.1, max: 51}   # the limit stops the flood
```

Every check also accepts `name`, `timeout` and `vrf`. Ping accepts `expect: failure` and `count`. Drivers are detected from the topology; override them with `nodes: {r1: {driver: frr}}`. Nodes that are configured after boot (SONiC) take `setup` commands: `nodes: {sonic1: {setup: [...]}}`.

| Check | FRR | SR Linux | Arista EOS (cEOS) | SONiC (VS) |
|---|---|---|---|---|
| `bgp_session` | ✅ | ✅ | ✅ | ✅ |
| `bgp_prefixes` (accepted = received minus rejected by policy) | ✅ | ✅ | ✅ | ✅ |
| `route` present / absent | ✅ | ✅ | ✅ | ✅ |
| `bgp_route` best-path attributes: communities (standard, large, well-known), AS path (exact or regex), local preference, MED, next hop | ✅ | ✅ | ✅ | ✅ |
| `ping` success / failure | ✅ | ✅ | ✅ | ✅ |
| **How it is tested** | Live lab in CI on every push | Live lab in CI on every push | Parsers tested against output captured from live labs; no live lab in CI | Parsers tested against output captured from live labs; no live lab in CI |

## Commands

| Command | What it does |
|---|---|
| `netdryrun run [path]` | Deploy the lab, run the checks, destroy the lab. Add `--keep` to leave it up for debugging |
| `netdryrun check [path]` | Run the checks against a lab that is already running |
| `netdryrun validate [path]` | Validate `netdryrun.yml` and its topology without running anything |
| `netdryrun record topology.clab.yml` | Snapshot a known-good lab into a `netdryrun.yml` baseline, so you don't write checks by hand |

Reports: `--json FILE` (full evidence), `--markdown FILE`, `--junit FILE`. Under GitHub Actions, a summary is appended to the job page automatically. Exit codes: `0` passed, `1` a check failed, `2` no verdict (config or lab error, a fault that did not take effect, or an internal error; add `--debug` for the traceback), `3` inconclusive (the lab never reached a testable state, so the run says nothing about the change), `130`/`143`/`129` interrupted by SIGINT/SIGTERM/SIGHUP after cleaning up the lab.

## GitHub Action

```yaml
name: Network dry run
on: pull_request
jobs:
  dryrun:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: netdryrun/netdryrun@v0.3.2
        with:
          path: network/        # folder containing netdryrun.yml
```

The action installs containerlab, runs the checks, uploads the JSON and JUnit reports as an artifact, and fails the job if any check fails. Outputs: `status`, `passed`, `failed`, `inconclusive-reason`.

## For AI agents (MCP)

Listed in the [official MCP Registry](https://registry.modelcontextprotocol.io/v0/servers?search=io.github.netdryrun) (`io.github.netdryrun/netdryrun`); the agent skill is also on [Smithery](https://smithery.ai/skills/netdryrun/netdryrun).

**AI can propose network changes. Netdryrun verifies the outcome.** Agents: read [AGENTS.md](https://github.com/netdryrun/netdryrun/blob/main/AGENTS.md).

AI agents are starting to change networks. Netdryrun gives them a safety gate: an [MCP](https://modelcontextprotocol.io) server that lets an agent dry-run its change in a real lab and proceed only if every check passes.

```bash
pipx install netdryrun   # or uv tool install netdryrun
```

Add it to your MCP client (for example Claude Code):

```bash
claude mcp add netdryrun -- netdryrun mcp
```

Tools: `dry_run` (deploy, check, destroy, verdict), `run_checks` (against a running lab), `record_baseline` (snapshot a known-good lab into checks), `validate`, `check_types`. Each result carries a separate `verdict` field: `CHECKS PASSED (only what the checks cover)`, `DO NOT APPLY THIS CHANGE`, or `INCONCLUSIVE: the lab did not reach a testable state; ...` when the lab never came up. `CHECKS PASSED (only what the checks cover)` means only that every check in the file passed in the lab, so a pass never says "safe". A change can break something no check looks at and still get it: in our [agent evaluation](https://netdryrun.com/ai-agents/), an agent's "pure refactor" added `redistribute connected` and passed, because no check covered the extra routes. For a change that must not change behavior, record a baseline first. From 0.3.2 the verdict strings are frozen (0.3.1 said `SAFE TO PROCEED` for a pass; decide on `status`, not the text), a failed result lists each failed check with its reason, an evidence excerpt and one read-only next diagnostic command, and the result format is a published JSON Schema: [mcp-result-v1.json](https://netdryrun.com/schemas/mcp-result-v1.json).

**Demo** ([examples/agent-demo](https://github.com/netdryrun/netdryrun/tree/main/examples/agent-demo)): the ticket says the customer's new block must reach the upstream and the peer. The tempting change passes every ticket check, session and ping, but leaks routes; Netdryrun rejects it. The two-line fix passes the same checks. (A scripted replay of the two attempts; CI runs it.)

<p align="center"><img alt="Attempt 1 passes the ticket checks but fails five leak guards; attempt 2 passes all 14 checks" src="https://raw.githubusercontent.com/netdryrun/netdryrun/main/.github/assets/netdryrun-agent-demo.gif" width="820"></p>

### The agent skill

[`skills/netdryrun/SKILL.md`](https://github.com/netdryrun/netdryrun/blob/main/skills/netdryrun/SKILL.md) teaches a coding agent the rules: dry-run a routing change before applying it, paste the verdict, stop on inconclusive, never write or weaken checks to make a change pass, and use `record_baseline` when there are no checks. Install it from this repository's git URL (from 0.3.2):

```bash
git clone --depth 1 https://github.com/netdryrun/netdryrun /tmp/netdryrun
mkdir -p ~/.claude/skills && cp -r /tmp/netdryrun/skills/netdryrun ~/.claude/skills/   # Claude Code, every project
```

To give it to everyone working in one repository, copy the folder to `.claude/skills/netdryrun/` there and commit it. Other clients that read Agent Skills (a folder with a `SKILL.md`) take the same folder. The skill expects the MCP server above; without it, the agent falls back to the CLI.

Safety model:
- The server **never touches production**. It has no tool that pushes config anywhere; it only builds and tests labs.
- Tool results contain normalized check results, not full device output. A check's `detail` can still quote a fragment of lab text (a banner, a route description), and from 0.3.2 each failed check carries a short evidence excerpt; each is kept to one line and capped in length, and none of them changes `status` or `verdict`. Raw evidence goes to the JSON report file.
- A lab is code: containerlab runs privileged containers. Only point the server at topologies you trust, on a machine you'd let run Docker.

## How it compares

Netdryrun complements these tools; it doesn't replace them.

| Tool | What it does best | Where Netdryrun fits |
|---|---|---|
| [Batfish](https://batfish.org) | Static analysis of configs, without booting anything; fast and broad | Netdryrun runs the real control plane, so it sees runtime behavior: convergence, sessions that really come up, what actually lands in the RIB |
| [pyATS / Genie](https://developer.cisco.com/pyats/) | A full test framework with deep Cisco parsers | Netdryrun is a small declarative YAML file plus one GitHub Action, with no test code to write |
| [containerlab](https://containerlab.dev) | Runs the lab | Netdryrun drives containerlab; it doesn't replace it |

What Netdryrun adds: positive checks wait for convergence, negative checks run only after convergence and must hold, received-but-not-selected routes count as present, and every run produces one pass/fail plus an evidence file.

## Limits

- Lab routers are not your production routers. A pass on FRR, SR Linux, SONiC VS or Arista cEOS is strong evidence for protocol logic and policy intent, but not proof of hardware, scale or version-specific behavior. For Arista, bring your own licensed cEOS image to test real vendor code.
- Checks cover IPv4/IPv6 unicast BGP (sessions, prefix counts, best-path attributes), routes and ping, with link-down, node-isolation and route-injection (FRR only) failure scenarios. Route checks work for routes from any protocol today (`protocol: ospf`, `isis`, `static`, `connected`, ...); OSPF/IS-IS *adjacency* checks and path/traceroute are coming.
- No Cisco or Juniper driver in a release yet. Their lab images need a vendor account and can't be redistributed, so their drivers will be bring-your-own-image, like cEOS; Juniper and Cisco NX-OS are next on the [roadmap](https://netdryrun.com/faq/#why-not-cisco-or-juniper).

How results are checked and released, with evidence for each claim: [How it's built](https://netdryrun.com/how-its-built/).

## Roadmap

- **Outage replays:** famous real-world outages (route leaks, mass withdrawals) rebuilt as runnable labs and check packs. Would your change have caused one?
- More failure scenarios, more check types (OSPF/IS-IS, traceroute) and drivers
- PR comments with diffs, and signed evidence for change tickets

## License

Apache-2.0. "Netdryrun" and the Netdryrun logo are trademarks; see [TRADEMARKS.md](https://github.com/netdryrun/netdryrun/blob/main/TRADEMARKS.md).

<!-- mcp-name: io.github.netdryrun/netdryrun -->
