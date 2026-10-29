# Agent evaluation

How well does an AI agent use Netdryrun with only its public docs? Ten tickets on the example labs, each with a hidden grader; a fresh headless Claude Code agent works each ticket alone. The design and the expected outcomes are in [PREREGISTRATION.md](PREREGISTRATION.md), committed before any run. The results, failures included, are in [RESULTS.md](RESULTS.md).

- `tickets/<id>/ticket/`: everything the agent gets (plus a copy of the repository's `AGENTS.md`).
- `tickets/<id>/grader.yml`: the hidden answer: right verdict, accepted decisions, which file the agent may change, and extra checks for an independent rerun of the agent's final folder.
- `validation/`: the tickets' ground truth, checked in a lab before any agent ran.
- `run_eval.py`: runs the agents and grades them. `grade_rerun.sh`: the grader's independent rerun, in WSL.
- `results/<run>/<id>/`: per ticket, the agent's full stream-json transcript (`transcript.jsonl`), its final answer, its final folder (`final/`), the last Netdryrun report it produced, and `grade.json`. `results/<run>/summary.md` is the table.

## Reproduce

The harness was written for the setup the runs used: Windows 11 with Claude Code 2.1.116 (logged in), and WSL 2 (Ubuntu 22.04) with Docker, containerlab 0.81.1 and the `quay.io/frrouting/frr:10.4.1` image. Agents call the MCP server through `wsl.exe`; the grader's reruns run in WSL too.

1. In WSL, install the Netdryrun to test into its own virtualenv:

   ```bash
   python3 -m venv ~/.venvs/ndr-eval && ~/.venvs/ndr-eval/bin/pip install netdryrun==0.3.0
   ```

2. In Git Bash on Windows, from the repository root (Python 3.10+ with PyYAML on Windows):

   ```bash
   export MSYS_NO_PATHCONV=1 NDR_EVAL_NETDRYRUN=/home/<you>/.venvs/ndr-eval/bin/netdryrun NDR_EVAL_AGENTS_REF=096bcf6
   python examples/agent-eval/run_eval.py run --run myrun --parallel 2
   ```

   `MSYS_NO_PATHCONV=1` matters: without it Git Bash rewrites `/home/...` to a Windows path and the MCP server never starts (the harness now refuses such a path). `NDR_EVAL_AGENTS_REF` is the commit whose `AGENTS.md` the agents get (`096bcf6` for the pre-registered runs). Add `--model haiku` for another model, and `--path-style windows` to give the agent the folder's Windows path instead of its WSL path (the server accepts both only from 0.3.1 on). `NDR_EVAL_DISTRO` sets the WSL distribution (default `Ubuntu-22.04`).

3. Grade again without rerunning the agents: `python examples/agent-eval/run_eval.py grade --run myrun --parallel 1`.

Each ticket takes 1 to 6 minutes; ten tickets with `--parallel 2` took about 15 minutes. Each agent runs in a new folder under `%LOCALAPPDATA%\Temp\ndr-eval`, outside any repository, with Read, Edit and Write allowed only inside that folder, WebFetch only for `netdryrun.com`, and no shell. Labs are named `ndr-eval-tNN`, so two runs of the same ticket must not overlap.

The harness also sets `NETDRYRUN_MCP_ROOT` to the ticket folder. Netdryrun 0.3.0 ignores that variable, so in the runs on 0.3.0 the MCP server was not confined to the folder (the agents had no shell). It takes effect from 0.3.1.

## Rerun the open model on the 0.3.2 candidate (prepared, not run)

Pre-registered in [PREREGISTRATION-OPEN.md](PREREGISTRATION-OPEN.md) ("Then"); the 0.3.1 baseline is in [RESULTS.md](RESULTS.md). Use `Ubuntu-ndr` only, never `Ubuntu-22.04`. Run it after the 0.3.2 release gate finishes: the gate's live layer is timing-sensitive, and a local model beside it breaks it (LESSONS 5 and 45).

1. Install the `ndr/agent-contract` head into its own virtualenv in WSL (head `fb07cccbf8167ea0f2759025fde96f56d9a277a2` when this was written; if the branch has moved, `git rev-parse origin/ndr/agent-contract` and use that). The archive URL needs no git in the distro:

   ```bash
   MSYS_NO_PATHCONV=1 wsl -d Ubuntu-ndr -- bash -c 'python3 -m venv /home/ndr/.venvs/ndr-eval-032 && /home/ndr/.venvs/ndr-eval-032/bin/pip install https://github.com/netdryrun/netdryrun/archive/fb07cccbf8167ea0f2759025fde96f56d9a277a2.zip && /home/ndr/.venvs/ndr-eval-032/bin/netdryrun --version'
   ```

   The last line must print `0.3.2`. This keeps the 0.3.1 venv (`ndr-eval-031`) untouched.

2. In Git Bash, from the repository root, with Ollama running `qwen3:4b` and nothing else heavy on the machine. Same settings as the baseline (16k context, 8,000-character results, 60-minute limit, `keep_alive` on from the start), one ticket at a time, and the `AGENTS.md` of the same commit:

   ```bash
   export MSYS_NO_PATHCONV=1 NDR_EVAL_DISTRO=Ubuntu-ndr NDR_EVAL_TIME_LIMIT=3600 NDR_EVAL_NETDRYRUN=/home/ndr/.venvs/ndr-eval-032/bin/netdryrun NDR_EVAL_AGENTS_REF=fb07cccbf8167ea0f2759025fde96f56d9a277a2
   python examples/agent-eval/run_eval.py run --run open-qwen3-4b-032 --agent open --backend ollama --model qwen3:4b --path-style windows --parallel 1
   python examples/agent-eval/stuck.py open-qwen3-4b-032
   ```

   Read every transcript by hand and fill `results/open-qwen3-4b-032/notes.json` before comparing; a changed ticket wording would break the comparison, so the tickets stay as they are. The difference from `open-qwen3-4b` is the contract plus whatever else is in the head, not a model change.

## Unprompted discovery and with/without (pre-registered, not run yet)

Two more evals, pre-registered before any run: [PREREGISTRATION-DISCOVERY.md](PREREGISTRATION-DISCOVERY.md) (the agent is never told the name: does it find Netdryrun, choose it, run it, read it right, choose it again?) and [PREREGISTRATION-WITH-WITHOUT.md](PREREGISTRATION-WITH-WITHOUT.md) (the same tickets with Netdryrun and without it: harmful changes applied, safe changes blocked, wrong reports). Both give the agent a shell and the lab, and use the tool-neutral tickets in `neutral/` (`TICKET.md` without the tool's name, and `CHECKS.md`, the checks in plain English; `python neutral/make_neutral.py --check` verifies them). `run_arms.py` runs and grades them; `open_agent.py` gained a shell, web search, open fetches, MCP servers the agent adds itself, and multi-ticket sessions for them.

**The lab host is shared.** The agents deploy labs, so hold the vendor lab lock for the whole run, and look at `docker ps -a` before and after: in `Ubuntu-ndr`, `mkdir /home/ndr/vendor-vm-lab.lock` acquires it (retry every 5 minutes if it exists), `rm -rf /home/ndr/vendor-vm-lab.lock` releases it. The release gate and Bench have priority. Use `Ubuntu-ndr` only.

One-time setup, in WSL as root: the agent's own user with an empty home (no Netdryrun, no uv), Docker and passwordless sudo for containerlab:

```bash
wsl -d Ubuntu-ndr -u root -- bash -c 'id labagent || (useradd -m -s /bin/bash -G docker,clab_admins labagent && echo "labagent ALL=(ALL) NOPASSWD:ALL" > /etc/sudoers.d/labagent && chmod 440 /etc/sudoers.d/labagent)'
```

Then, in Git Bash from the repository root (the with arm needs a Netdryrun in its own virtualenv in WSL, as for the first eval):

```bash
export MSYS_NO_PATHCONV=1 NDR_EVAL_DISTRO=Ubuntu-ndr NDR_EVAL_NETDRYRUN=/home/ndr/.venvs/ndr-arms/bin/netdryrun NDR_EVAL_AGENTS_REF=<commit>
python examples/agent-eval/run_arms.py run --arm discovery --run disc-claude-1
python examples/agent-eval/run_arms.py run --arm without --run ww-claude-without-r1 --repeat 1
python examples/agent-eval/run_arms.py run --arm with --run ww-claude-with-r1 --repeat 1
```

Add `--model haiku`, or `--agent open --model qwen3:4b` (with `NDR_EVAL_TIME_LIMIT=3600`) for the open models. `run_arms.py grade --run NAME` grades again (the grader's reruns need `NDR_EVAL_NETDRYRUN` too). Results land in `results/<run>/<trial>/` like the first eval's, with `stage-1/` and `stage-2/` for the two tickets of a pair, and `results/<run>/summary.md`. Read every transcript and fill `results/<run>/notes.json` before reporting.

**Goose, OpenHands and Cline** (discovery arm only, Amendment 2 of [PREREGISTRATION-DISCOVERY.md](PREREGISTRATION-DISCOVERY.md)) run on the lab host itself, as `labagent`, through `hosts/run_host.py`, on the workstation's Ollama. One-time setup: install the pinned hosts into `/opt/agent-hosts`, and create the 32k-context model:

```bash
wsl -d Ubuntu-ndr -u root -- bash examples/agent-eval/hosts/install_hosts.sh
printf 'FROM gpt-oss:20b\nPARAMETER num_ctx 32768\n' > Modelfile && ollama create ctx32k-gpt-oss-20b -f Modelfile
```

Ollama listens on `127.0.0.1` only, so keep the relay running while they run: `python examples/agent-eval/hosts/ollama_relay.py 172.25.208.1 11434`, using the Windows address on the WSL network (`ipconfig`, "vEthernet (WSL)"; `NDR_EVAL_OLLAMA_WSL` if it differs). Then:

```bash
NDR_EVAL_TIME_LIMIT=3600 python examples/agent-eval/run_arms.py run --arm discovery --lock --agent goose --model ctx32k-gpt-oss-20b --run disc-goose-gpt-oss-20b-1
```

`--agent openhands` and `--agent cline` work the same way. Each trial gets a fresh `HOME` at `/tmp/agenthome/<run>-<trial>`, and the host's raw output lands in `results/<run>/<trial>/host-raw.txt`.
