"""Thin wrapper around the containerlab CLI and docker exec."""
from __future__ import annotations

import ipaddress
import json
import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path


class LabError(RuntimeError):
    pass


# containerlab kinds for the Cisco Nexus 9000v (a VM inside the container, vrnetlab)
NXOS_KINDS = ("cisco_n9kv", "vr-n9kv", "vr-cisco_n9kv")


@dataclass
class Node:
    name: str        # short name from the topology, e.g. r1
    container: str   # docker container name, e.g. clab-mylab-r1
    kind: str
    image: str


@dataclass
class ExecResult:
    cmd: list[str]
    rc: int
    stdout: str
    stderr: str


def _run(cmd: list[str], timeout: float = 600, env: dict | None = None, input: str | None = None,
         errors: str | None = None) -> ExecResult:
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, env=env, input=input, errors=errors)
    except subprocess.TimeoutExpired:
        return ExecResult(cmd, 124, "", f"timed out after {timeout}s")
    return ExecResult(cmd, p.returncode, p.stdout, p.stderr)


def _parse_links(raw) -> list[tuple[tuple[str, str], tuple[str, str]]]:
    """Point-to-point links from the topology, in either containerlab syntax
    (endpoints: ["r1:eth1", "r2:eth1"], or endpoints: [{node: r1, interface: eth1}, ...])."""
    links = []
    for link in raw if isinstance(raw, list) else []:
        eps = link.get("endpoints") if isinstance(link, dict) else None
        if not isinstance(eps, list) or len(eps) != 2:
            continue
        ends = []
        for ep in eps:
            if isinstance(ep, str) and ":" in ep:
                n, i = ep.split(":", 1)
                ends.append((n, i))
            elif isinstance(ep, dict) and ep.get("node") and ep.get("interface"):
                ends.append((str(ep["node"]), str(ep["interface"])))
        if len(ends) == 2:
            links.append((ends[0], ends[1]))
    return links


class Lab:
    def __init__(self, topology: Path, containerlab: str = "containerlab"):
        self.topology = topology
        self.clab = containerlab
        self._lock_file = None
        from .config import ConfigError, load_yaml   # imported here: config -> faults -> lab

        try:
            # strict like netdryrun.yml: a duplicate key (two `nodes:` blocks) is an error, not a silent overwrite
            topo = load_yaml(topology.read_text(encoding="utf-8"), str(topology)) or {}
        except ConfigError as e:
            detail = str(e).removeprefix(f"{topology}: ")   # "not valid YAML at line L, column C: ..."
            raise LabError(f"{topology}: topology is {detail}") from None
        except (OSError, UnicodeDecodeError) as e:
            raise LabError(f"{topology}: cannot read the topology: {e}") from None
        if not isinstance(topo, dict):
            raise LabError(f"{topology}: a containerlab topology must be a mapping with 'name' and 'topology'")
        self.name = topo.get("name")
        if not self.name:
            raise LabError(f"{topology}: topology has no 'name'")
        if not isinstance(self.name, str):
            raise LabError(f"{topology}: topology 'name' must be a string, got {self.name!r}")
        t = topo.get("topology") or {}
        if not isinstance(t, dict):
            raise LabError(f"{topology}: 'topology' must be a mapping (with nodes:, links:)")
        defaults = t.get("defaults") or {}
        kinds = t.get("kinds") or {}
        nodes = t.get("nodes") or {}
        if not isinstance(nodes, dict):
            raise LabError(f"{topology}: topology.nodes must be a mapping of node name to definition, "
                           f"not a {type(nodes).__name__}")
        if not isinstance(defaults, dict) or not isinstance(kinds, dict):
            raise LabError(f"{topology}: topology.defaults and topology.kinds must be mappings")
        prefix = topo.get("prefix", "clab")
        self.nodes: dict[str, Node] = {}
        for nname, ndef in nodes.items():
            ndef = ndef or {}
            if not isinstance(ndef, dict):
                raise LabError(f"{topology}: node {nname!r} must be a mapping (kind:, image:, ...)")
            nname = str(nname)
            kind = ndef.get("kind", defaults.get("kind", ""))
            image = ndef.get("image") or (kinds.get(kind) or {}).get("image") or defaults.get("image", "")
            if prefix == "":
                container = nname
            elif prefix == "__lab-name":
                container = f"{self.name}-{nname}"
            else:
                container = f"{prefix}-{self.name}-{nname}"
            self.nodes[nname] = Node(nname, container, str(kind or ""), str(image or ""))
        self.links: list[tuple[tuple[str, str], tuple[str, str]]] = _parse_links(t.get("links"))

    def check_tools(self) -> None:
        for tool in (self.clab, "docker"):
            if not shutil.which(tool):
                raise LabError(f"'{tool}' not found on PATH")

    def _env(self) -> dict:
        """Keep containerlab's lab directory on a Linux filesystem.

        On WSL, a topology under /mnt/c lives on a Windows drive without Linux permissions,
        and SR Linux fails to save its config there.
        """
        env = dict(os.environ)
        if "CLAB_LABDIR_BASE" not in env and str(self.topology).startswith("/mnt/"):
            base = Path.home() / ".cache" / "netdryrun" / "labs"
            base.mkdir(parents=True, exist_ok=True)
            env["CLAB_LABDIR_BASE"] = str(base)
        return env

    def deploy(self) -> ExecResult:
        r = _run([self.clab, "deploy", "-t", str(self.topology), "--reconfigure"], env=self._env())
        if r.rc != 0:
            raise LabError(f"containerlab deploy failed:\n{(r.stderr or r.stdout)[-3000:]}")
        return r

    def destroy(self) -> ExecResult:
        return _run([self.clab, "destroy", "-t", str(self.topology), "--cleanup"], env=self._env())

    def version(self) -> str:
        r = _run([self.clab, "version"], timeout=30)
        for line in r.stdout.splitlines():
            if line.strip().startswith("version:"):
                return line.split(":", 1)[1].strip()
        return "unknown"

    def running_containers(self) -> set[str]:
        r = _run([self.clab, "inspect", "-t", str(self.topology), "--format", "json"], timeout=60, env=self._env())
        if r.rc != 0:
            return set()
        try:
            data = json.loads(r.stdout or "{}")
        except json.JSONDecodeError:
            return set()
        rows = data.get(self.name, []) if isinstance(data, dict) else []
        return {row["name"] for row in rows if row.get("state") == "running"}

    def existing_containers(self) -> set[str]:
        """Containers of a lab with this name that already exist, in any state (containerlab labels every
        container it creates with containerlab=<lab name>). Used to refuse a second run of the same lab."""
        r = _run(["docker", "ps", "-a", "--filter", f"label=containerlab={self.name}", "--format", "{{.Names}}"],
                 timeout=60)
        if r.rc != 0:
            raise LabError(f"could not list Docker containers: {(r.stderr or r.stdout).strip()[-300:]}")
        return {line.strip() for line in r.stdout.splitlines() if line.strip()}

    def acquire_lock(self) -> None:
        """Hold a host-wide lock on this lab name for the whole run, so two runs started at the same moment
        can't both deploy (and then destroy) the same lab. Released by release_lock() or on process exit."""
        if os.name != "posix" or self._lock_file is not None:
            return
        import fcntl

        safe = re.sub(r"[^A-Za-z0-9_.-]", "_", self.name)
        path = Path(tempfile.gettempdir()) / f"netdryrun-lab-{safe}.lock"
        f = open(path, "a+")
        try:
            fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            f.close()
            raise LabError(f"another Netdryrun run is already using lab '{self.name}' on this host; "
                           "wait for it to finish (two runs of the same lab would collide)") from None
        self._lock_file = f

    def release_lock(self) -> None:
        if self._lock_file is not None:
            try:
                self._lock_file.close()   # closing the file releases the flock
            finally:
                self._lock_file = None

    def interface_addresses(self, node: str, interface: str) -> list:
        """IP interfaces (address/prefix) configured on a node's interface ([] for an interface without
        addresses, e.g. unnumbered BGP). Used to find the BGP sessions a link fault should bring down, so
        addresses that can't be read are an error, never "no addresses"."""
        r = self.exec(node, ["ip", "-o", "addr", "show", "dev", interface], timeout=15)
        if r.rc != 0:
            raise LabError(f"could not read the addresses of {interface} on {node}: "
                           f"{' '.join((r.stderr or r.stdout).split())[:200] or f'exit code {r.rc}'}")
        out = []
        for m in re.finditer(r"\binet6?\s+([0-9A-Fa-f:.]+/\d+)", r.stdout):
            try:
                out.append(ipaddress.ip_interface(m.group(1)))
            except ValueError:
                pass
        return out

    def peers_of(self, node: str, interface: str) -> list[tuple[str, str]]:
        """The (node, interface) endpoints at the other end of a link, looking through bridge nodes
        (a clab bridge or OVS bridge in the middle is invisible to the routers on it)."""
        bridges = {n for n, nd in self.nodes.items() if nd.kind in ("bridge", "ovs-bridge")}
        start = (node, interface)
        far: list[tuple[str, str]] = []
        seen = {start}
        todo = [start]
        while todo:
            end = todo.pop()
            for a, b in self.links:
                other = b if a == end else a if b == end else None
                if other is None or other in seen:
                    continue
                seen.add(other)
                if other[0] in bridges:
                    # every other port of the bridge leads to a peer (or to another bridge)
                    for a2, b2 in self.links:
                        for x, _y in ((a2, b2), (b2, a2)):
                            if x[0] == other[0] and x != other and x not in seen:
                                seen.add(x)
                                todo.append(x)
                elif other[0] != node:
                    far.append(other)
        return far

    def data_interfaces(self, node: str) -> list[str]:
        """Interfaces a node uses for the lab's links (everything except loopback and management)."""
        self._require_linux_links(node)
        r = self.exec(node, ["ls", "/sys/class/net"], timeout=15)
        if r.rc != 0:
            raise LabError(f"could not list interfaces on {node}: {(r.stderr or r.stdout).strip()}")
        skip = {"lo", "eth0", "mgmt0", "docker0"}
        ifaces = sorted(i for i in r.stdout.split() if i not in skip and not i.startswith(("mgmt0", "gway", "monit")))
        if not ifaces:
            raise LabError(f"{node} has no lab links to take down")
        return ifaces

    def _require_linux_links(self, node: str) -> None:
        if self.nodes[node].kind in ("nokia_srlinux", "srl"):
            raise LabError(f"failure scenarios on SR Linux nodes ({node}) are not supported yet; "
                           "take the link down on the FRR/Linux side of the link instead")
        if self.nodes[node].kind in NXOS_KINDS:
            # the container's eth1.. only carry frames to the VM: taking one down is not an NX-OS link event
            raise LabError(f"failure scenarios on NX-OS nodes ({node}) are not supported yet; "
                           "take the link down on the FRR/Linux side of the link instead")

    def set_link(self, node: str, interface: str, up: bool) -> ExecResult:
        self._require_linux_links(node)
        r = self.exec(node, ["ip", "link", "set", "dev", interface, "up" if up else "down"], timeout=15)
        if r.rc != 0:
            raise LabError(f"could not set {node} {interface} {'up' if up else 'down'}: {(r.stderr or r.stdout).strip()}")
        return r

    def run_setup(self, node: str, commands: list[str], budget: float = 300, log=lambda _: None) -> None:
        """Run post-boot setup commands on a node, retrying each until it succeeds (the NOS may still be
        starting) or the shared time budget runs out."""
        import time
        deadline = time.monotonic() + budget
        for cmd in commands:
            while True:
                r = self.exec(node, ["bash", "-lc", cmd], timeout=120)
                if r.rc == 0:
                    break
                if time.monotonic() > deadline:
                    raise LabError(f"setup on {node} failed: `{cmd}`: {(r.stderr or r.stdout).strip()[-300:]}")
                time.sleep(5)
        log(f"setup done on {node} ({len(commands)} commands)")

    def boot_log(self, node: str) -> ExecResult:
        """The container's log since it last started (stdout and stderr), where the NOS reports config it rejected.
        Only the current boot: a line rejected before a restart, and fixed since, doesn't count."""
        c = self.nodes[node].container
        s = _run(["docker", "inspect", "-f", "{{.State.StartedAt}}", c], timeout=60, errors="replace")
        if s.rc != 0 or not s.stdout.strip():
            return ExecResult(s.cmd, s.rc or 1, "", s.stderr or "no start time")
        r = _run(["docker", "logs", "--since", s.stdout.strip(), c], timeout=120, errors="replace")
        return ExecResult(r.cmd, r.rc, f"{r.stdout}\n{r.stderr}", r.stderr)

    def exec(self, node: str, cmd: list[str], timeout: float = 60, input: str | None = None) -> ExecResult:
        flags = ["-i"] if input is not None else []
        return _run(["docker", "exec", *flags, self.nodes[node].container, *cmd], timeout=timeout, input=input)
