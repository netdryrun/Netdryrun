"""`netdryrun verify`: deploy the lab with the before configs, snapshot it, destroy it; the same with the
after configs (and the standing guards on the after lab); then match the diff against the intent.

`--before` and `--after` each name one side: a git ref (the repository's whole tree at that ref) or a
directory (standing for the folder of the working tree that holds the topology and every file it binds;
with --config-dir, for that folder only). A directory wins over a ref of the same name. Each side is
built in its own temporary folder, and every bind of the topology is resolved inside that side's tree:
a bind that resolves outside it (an absolute path, `~`, a variable, `..` or a symlink leading out) would
be the same file on both sides, and is exit 2. The topology file must be identical on both sides: verify
compares configs on one topology (exit 2 otherwise).
"""
from __future__ import annotations

import hashlib
import io
import os
import posixpath
import re
import shutil
import subprocess
import tarfile
import tempfile
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Callable

from ..config import ConfigError, load_yaml
from ..drivers import DRIVERS, DriverError, detect
from ..lab import Lab, LabError
from .converge import Inconclusive, stable_snapshot
from .engine import VerifyError, baseline_problems, diff, match
from .frr import FrrCollector, link_local_names, parse_link_local
from .intent import IntentError, check_nodes, load_intent, parse_intent_text
from .report import ALLOW_WARNING, INTENT_EDITED_WARNING, NO_GUARDS_WARNING, VerifyResult
from .snapshot import Snapshot, SnapshotError

BRIDGE_KINDS = ("bridge", "ovs-bridge")          # never observed: no routing stack
HOST_KINDS = ("host", "ext-container", "k8s-kind")  # refused unless named in --unobserved


class VerifyInputError(RuntimeError):
    """Bad arguments: an unreadable side, a different topology, a config directory that can't be found."""


class MissingBind(VerifyInputError):
    def __init__(self, msg: str, path: Path):
        super().__init__(msg)
        self.path = path


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ---------------------------------------------------------------------------------------------------------
# The topology's file references
# ---------------------------------------------------------------------------------------------------------

def bind_sources(topology: Path) -> list[str]:
    """Host paths the topology references (binds and startup-config), as written."""
    try:
        data = load_yaml(topology.read_text(encoding="utf-8"), str(topology)) or {}
    except (ConfigError, OSError, UnicodeDecodeError) as e:
        raise VerifyInputError(f"{topology}: cannot read the topology: {e}") from None
    t = data.get("topology") if isinstance(data, dict) else None
    if not isinstance(t, dict):
        raise VerifyInputError(f"{topology}: not a containerlab topology (no `topology:` mapping)")
    blocks = [t.get("defaults") or {}]
    for section in ("kinds", "groups", "nodes"):
        sec = t.get(section) or {}
        if isinstance(sec, dict):
            blocks += [v or {} for v in sec.values()]
    out = []
    for b in blocks:
        if not isinstance(b, dict):
            continue
        for bind in b.get("binds") or []:
            if isinstance(bind, str) and ":" in bind:
                out.append(bind.split(":", 1)[0])
        sc = b.get("startup-config")
        if isinstance(sc, str) and "\n" not in sc:
            out.append(sc)
    return list(dict.fromkeys(out))


def bind_reach(topology: Path) -> dict[str, list[tuple[str, str]]]:
    """Each host path the topology references -> the (node, path in the container) it reaches: a `nodes` bind its
    node, a `kinds` bind the nodes of that kind, a `groups` bind the nodes of that group, a `defaults` bind every
    node (containerlab's inheritance; cold review 5). Bridges have no container and are left out."""
    data = load_yaml(topology.read_text(encoding="utf-8"), str(topology)) or {}
    t = data.get("topology") or {}
    defaults = t.get("defaults") if isinstance(t.get("defaults"), dict) else {}
    kinds = t.get("kinds") if isinstance(t.get("kinds"), dict) else {}
    groups = t.get("groups") if isinstance(t.get("groups"), dict) else {}
    nodes = t.get("nodes") if isinstance(t.get("nodes"), dict) else {}
    out: dict[str, list[tuple[str, str]]] = {}
    for name, nd in nodes.items():
        nd = nd if isinstance(nd, dict) else {}
        grp = groups.get(nd.get("group")) if isinstance(groups.get(nd.get("group")), dict) else {}
        kind = nd.get("kind") or grp.get("kind") or defaults.get("kind")
        if kind in BRIDGE_KINDS:
            continue
        knd = kinds.get(kind) if isinstance(kinds.get(kind), dict) else {}
        for block in (defaults, knd, grp, nd):
            for bind in block.get("binds") or []:
                if isinstance(bind, str) and ":" in bind:
                    src, dest = bind.split(":", 2)[:2]
                    out.setdefault(src, []).append((str(name), dest))
            sc = block.get("startup-config")
            if isinstance(sc, str):   # inline (several lines): no file, but config all the same (audit F6)
                out.setdefault(sc if "\n" not in sc else "(inline startup-config)", []).append(
                    (str(name), "startup-config"))
    return {k: list(dict.fromkeys(v)) for k, v in out.items()}


def is_router_config(dest: str) -> bool:
    """An FRR config file that verify's snapshot judges: /etc/frr/<name>.conf, except vtysh.conf (vtysh's own
    settings). FRR's `daemons` is shell its init script sources, so it is not one."""
    d = posixpath.normpath(dest)
    return posixpath.dirname(d) == "/etc/frr" and d.endswith(".conf") and posixpath.basename(d) != "vtysh.conf"


_VAR = re.compile(r"\$(?:\{([A-Za-z_][A-Za-z0-9_]*)(?:(:?[-=])([^}]*))?\}|([A-Za-z_][A-Za-z0-9_]*))")


def expand_bind(src: str) -> str:
    """A bind source as containerlab reads it: `${VAR}`, `${VAR:=default}`, `$VAR` and a leading `~`
    expanded. An unset variable without a default is an error (the path can't be known)."""
    def sub(m: re.Match) -> str:
        name, op, default = m.group(1) or m.group(4), m.group(2), m.group(3)
        val = os.environ.get(name)
        if op is not None and (val is None or (op.startswith(":") and val == "")):
            return default or ""
        if val is None:
            raise VerifyInputError(f"the topology binds {src!r}, but ${name} is not set")
        return val
    out = _VAR.sub(sub, src)
    if out == "~" or out.startswith("~/"):
        out = os.path.expanduser(out)
    return out


def _real(p: Path) -> Path:
    return Path(os.path.realpath(p))


def _within(p: Path, root: Path) -> bool:
    return p == root or p.is_relative_to(root)


def resolve_bind(src: str, topo_dir: Path, root: Path, where: str) -> Path:
    """The file or folder a bind source points at, resolved like containerlab does (relative to the
    topology's folder, variables and `~` expanded, `..` and symlinks followed). It must lie inside `root`,
    the side's own tree: anything outside would be the same file on both sides (exit 2)."""
    p = Path(expand_bind(src))
    real = _real(p if p.is_absolute() else topo_dir / p)
    if not _within(real, _real(root)):
        raise VerifyInputError(f"{where}: the topology binds {src}, which resolves outside the side's tree (to {real}); "
                               "both sides would share it. Bind files by a relative path inside the lab's tree")
    if not real.exists():
        raise MissingBind(f"{where}: {src} is missing (the topology binds it)", real)
    return real


def bind_anchor(topology: Path) -> Path:
    """The smallest folder of the working tree that holds the topology and every file it binds by
    relative path: a directory given as a side mirrors this folder."""
    topo_dir = topology.resolve().parent
    parts = [topo_dir]
    for src in bind_sources(topology):
        p = Path(expand_bind(src))
        if not p.is_absolute():
            parts.append(Path(os.path.normpath(topo_dir / p)))
    return Path(os.path.commonpath([str(x) for x in parts]))


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _files(real: Path) -> list[Path]:
    return [real] if real.is_file() else sorted(f for f in real.rglob("*") if f.is_file())


# ---------------------------------------------------------------------------------------------------------
# Sides
# ---------------------------------------------------------------------------------------------------------

def _git(args: list[str], cwd: Path, binary: bool = False, stdin: bytes | None = None):
    try:
        p = subprocess.run(["git", *args], cwd=cwd, capture_output=True, timeout=120, text=not binary, input=stdin)
    except (OSError, subprocess.TimeoutExpired) as e:
        raise VerifyInputError(f"git {' '.join(args)}: {e}") from None
    if p.returncode != 0:
        err = p.stderr if not binary else p.stderr.decode("utf-8", "replace")
        raise VerifyInputError(f"git {' '.join(args)}: {' '.join(err.split())[:300] or f'exit {p.returncode}'}")
    return p.stdout


def _extract(tar_bytes: bytes, dest: Path) -> None:
    """A `git archive` tar into dest: regular files and folders first, then symlinks as they are (never
    followed while extracting; a bind through one is resolved later and must stay inside the tree)."""
    with tarfile.open(fileobj=io.BytesIO(tar_bytes)) as tf:
        members = tf.getmembers()
        for m in members:
            p = PurePosixPath(m.name)
            if p.is_absolute() or ".." in p.parts or m.isdev() or m.islnk():
                raise VerifyInputError(f"git archive: refusing member {m.name!r}")
        tf.extractall(dest, members=[m for m in members if not m.issym()])
        for m in members:
            if m.issym():
                link = dest / Path(*PurePosixPath(m.name).parts)
                if not link.exists() and not link.is_symlink():
                    link.parent.mkdir(parents=True, exist_ok=True)
                    os.symlink(m.linkname, link)


def _cat_files(repo: Path, commit: str, paths: list[str]) -> dict[str, bytes | None]:
    """The blobs at commit:path (None for a path that is not a file there), in one `git cat-file --batch`."""
    if not paths:
        return {}
    data = _git(["cat-file", "--batch"], repo, binary=True, stdin="".join(f"{commit}:{p}\n" for p in paths).encode())
    out: dict[str, bytes | None] = {}
    pos = 0
    for p in paths:
        nl = data.index(b"\n", pos)
        header = data[pos:nl].decode("utf-8", "replace").split()
        pos = nl + 1
        if len(header) == 3:
            size = int(header[2])
            out[p] = data[pos:pos + size] if header[1] == "blob" else None
            pos += size + 1
        else:
            out[p] = None    # "<object> missing"
    return out


@dataclass
class Side:
    """One side's lab tree, materialized in its own folder. Every bind of `topology` resolves inside `root`."""
    label: str
    topology: Path                      # the side's copy of the topology file
    desc: str
    root: Path                          # the side's own tree
    bound: dict[str, str] = field(default_factory=dict)     # bound file (as the topology names it) -> sha256 booted
    sources: dict[str, str] = field(default_factory=dict)   # ... -> sha256 of that file in the side's source
    repo: Path | None = None            # a git ref: the repository's working tree
    commit: str = ""
    given_dir: Path | None = None       # a directory: the directory given
    mount: Path | None = None           # a directory: the working-tree folder it stands for

    @property
    def is_ref(self) -> bool:
        return bool(self.commit)

    def locate(self, path: Path) -> Path | None:
        """Where a working-tree path (or a path inside the directory given) is in this side's tree."""
        p = _real(Path(path))
        bases = [self.repo] if self.is_ref else [self.given_dir, self.mount]
        for base_dir in bases:
            if base_dir is not None and _within(p, _real(base_dir)):
                return self.root / p.relative_to(_real(base_dir))
        return None


def _hint(topology: Path, config_hint: str | None) -> Path | None:
    if config_hint is None:
        return None
    rel = Path(config_hint.replace("\\", "/"))
    if rel.is_absolute():
        raise VerifyInputError(f"--config-dir must be relative to the topology's folder, got {config_hint!r}")
    return Path(os.path.normpath(topology.parent / rel))


def _is_ref(spec: str, topology: Path) -> bool:
    """Whether `spec` names a commit in the repository that holds the topology (False outside a repository)."""
    try:
        repo = Path(str(_git(["rev-parse", "--show-toplevel"], topology.parent)).strip())
        str(_git(["rev-parse", "--verify", "--quiet", f"{spec}^{{commit}}"], repo))
    except VerifyInputError:
        return False
    return True


def materialize(spec: str, label: str, topology: Path, work: Path, config_hint: str | None = None) -> Side:
    """Build one side's lab tree in work/<label>, isolated from the other side and from the working tree.

    A git ref: the repository's whole tree at that ref (`git archive`); the topology in it must be
    byte-identical to the one given. A directory: that directory, standing for the folder of the working
    tree that holds the topology and everything it binds (or, with --config-dir, for that folder only).
    Every bind is then resolved in the side's own tree, and must stay inside it."""
    topology = topology.resolve()
    out = work / label
    side_dir = Path(spec)
    if side_dir.is_dir():
        if _is_ref(spec, topology):
            raise VerifyInputError(f"--{label} {spec!r} is both a directory and a git ref; verify won't guess which is "
                                   "meant (a change could add a folder named like the base commit). Rename the "
                                   "directory, or pass the ref in another form (a full commit hash or a branch name)")
        given = side_dir.resolve()
        mount = _hint(topology, config_hint) or bind_anchor(topology)
        anchor = Path(os.path.commonpath([str(mount), str(topology.parent)]))
        root = out / mount.relative_to(anchor)
        shutil.copytree(given, root, symlinks=True, ignore=shutil.ignore_patterns(".git"))
        topo = out / topology.relative_to(anchor)
        if topo.exists() and topo.read_bytes() != topology.read_bytes():
            raise VerifyInputError(f"{label} (directory {spec}): its {topo.name} differs from {topology}; verify "
                                   "compares configs on one topology")
        topo.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(topology, topo)
        side = Side(label, topo, f"directory {spec}", root, given_dir=given, mount=mount)
    else:
        repo = _real(Path(str(_git(["rev-parse", "--show-toplevel"], topology.parent)).strip()))
        try:
            commit = str(_git(["rev-parse", "--verify", "--quiet", f"{spec}^{{commit}}"], repo)).strip()
        except VerifyInputError:
            raise VerifyInputError(f"--{label} {spec!r} is neither a directory nor a git ref in {repo}") from None
        try:
            rel = _real(topology).relative_to(repo)
        except ValueError:
            raise VerifyInputError(f"{topology} is not inside the git repository {repo}") from None
        out.mkdir(parents=True)
        _extract(_git(["archive", "--format=tar", commit], repo, binary=True), out)
        topo = out / rel
        if not topo.is_file():
            raise VerifyInputError(f"{label} ({spec}): the topology {rel.as_posix()} doesn't exist in that ref; verify "
                                   "compares configs on one topology")
        if topo.read_bytes() != topology.read_bytes():
            raise VerifyInputError(f"{label} ({spec}): the topology {rel.as_posix()} differs from {topology}; verify "
                                   "compares configs on one topology")
        if config_hint is not None:
            in_tree = Path(os.path.normpath(topo.parent / config_hint.replace("\\", "/")))
            if not _within(in_tree, out) or not in_tree.is_dir():
                raise VerifyInputError(f"{label} ({spec}): the config folder {config_hint} doesn't exist in that ref")
        side = Side(label, topo, f"git ref {spec} ({commit[:12]})", out, repo=repo, commit=commit)
    _hash_binds(side)
    return side


def _hash_binds(side: Side) -> None:
    """Record what each bind points at in the side's tree (sha256 of every file), and the same file in the
    side's source (the ref's blob, or the directory given). They must agree: the lab boots the side's own
    bytes, never a file the other side or the working tree put there."""
    where = f"{side.label} ({side.desc})"
    root = _real(side.root)
    files: dict[str, Path] = {}
    for src in bind_sources(side.topology):
        try:
            real = resolve_bind(src, side.topology.parent, side.root, where)
        except MissingBind as e:
            if side.is_ref:
                rel = e.path.relative_to(root).as_posix()
                if _cat_files(side.repo, side.commit, [rel])[rel] is not None:
                    raise VerifyInputError(f"{where}: {src} ({rel}) is in that ref but not in its `git archive`: "
                                           "excluded by export-ignore in .gitattributes. verify builds the side from "
                                           "the archive; remove the export-ignore for bound files") from None
            raise
        for f in _files(real):
            files[src if f == real else f"{src}/{f.relative_to(real).as_posix()}"] = _real(f)
    side.bound = {k: _sha256(f.read_bytes()) for k, f in files.items()}
    rels = {k: f.relative_to(root).as_posix() for k, f in files.items()}
    if side.is_ref:
        blobs = _cat_files(side.repo, side.commit, sorted(set(rels.values())))
        side.sources = {k: _sha256(blobs[r]) for k, r in rels.items() if blobs.get(r) is not None}
    else:
        side.sources = {k: _sha256((side.given_dir / r).read_bytes()) for k, r in rels.items()
                        if (side.given_dir / r).is_file()}
    wrong = sorted(k for k in side.bound if side.sources.get(k) != side.bound[k])
    if wrong:
        raise VerifyInputError(f"{where}: the lab folder doesn't hold the side's own bytes for {', '.join(wrong)}; "
                               "refusing to compare")


def intent_edited(intent: Path, before: Side, after: Side) -> bool:
    """Whether the intent file is part of the change: it lies in a side's tree and differs (or exists on one
    side only) between the two."""
    def read(p: Path | None) -> bytes | None:
        return p.read_bytes() if p is not None and p.is_file() else None
    b, a = before.locate(intent), after.locate(intent)
    return (b is not None or a is not None) and read(b) != read(a)


def check_sides(before: Side, after: Side, log: Callable[[str], None]) -> list[str]:
    """The self-check before booting: print which bound files differ between the sides. If the sources
    differ but every bound file hashes the same, the two sides collapsed into one (exit 2)."""
    keys = sorted(set(before.bound) | set(after.bound))
    differ = [k for k in keys if before.bound.get(k) != after.bound.get(k)]
    src_differ = [k for k in keys if before.sources.get(k) != after.sources.get(k)]
    if src_differ and not differ:
        raise VerifyInputError(f"both sides resolved to the same configs: {', '.join(src_differ)} differ between "
                               f"{before.desc} and {after.desc}, but every bound file hashes the same in the two lab "
                               "folders; refusing to compare")
    if not differ:
        raise VerifyInputError(f"nothing to verify: no file the lab boots differs between {before.desc} and "
                               f"{after.desc} (a change to a file the topology doesn't bind isn't in the lab)")
    log(f"bound files that differ between the sides: {', '.join(differ)}")
    return differ


def check_changed_binds(topology: Path, differ: list[str], nodes: dict[str, str]) -> None:
    """Every bound file that differs must be the FRR config of a node verify snapshots: anything else (FRR's
    `daemons`, a script, vtysh.conf, a startup-config of a node not observed) can change what runs without
    the snapshot judging it, so it is an error (gauntlet 0.4, R2)."""
    targets = bind_reach(topology)
    bad = []
    for key in differ:
        src = next((s for s in sorted(targets, key=len, reverse=True) if key == s or key.startswith(s + "/")), None)
        suffix = key[len(src):] if src else ""
        for node, dest in targets.get(src, [("?", "?")]):
            full = dest + suffix if dest != "startup-config" else dest
            if not (is_router_config(full) and nodes.get(node) == "frr"):
                bad.append(f"{key} ({full} on {node})")
    if bad:
        raise VerifyInputError(f"changed bound file(s) that are not a router config of a node verify observes: "
                               f"{'; '.join(dict.fromkeys(bad))}. verify judges a change by what the observed FRR "
                               "nodes do, and can't tell what this file changes; change it in a separate PR, "
                               "tested with checks")

# ---------------------------------------------------------------------------------------------------------
# Nodes
# ---------------------------------------------------------------------------------------------------------

def classify_nodes(lab: Lab, overrides: dict[str, str], unobserved: list[str]) -> dict[str, str]:
    """node -> driver ("frr"), or "" for a node verify doesn't snapshot. Every other node is an error:
    verify 0.4 is FRR only, and a node it can't classify could hide a change."""
    unknown = sorted(set(unobserved) - set(lab.nodes))
    if unknown:
        raise VerifyInputError(f"--unobserved names node(s) not in the topology: {', '.join(unknown)}")
    out = {}
    for name, node in lab.nodes.items():
        if node.kind in BRIDGE_KINDS:
            out[name] = ""
            continue
        if name in unobserved:
            try:
                runs = overrides.get(name) or detect(node)
            except DriverError:
                runs = None
            if runs == "frr":
                raise VerifyInputError(f"--unobserved {name}: {name} runs FRR, which verify observes; a change on "
                                       "it would go uncompared")
            out[name] = ""
            continue
        if node.kind in HOST_KINDS and name not in overrides:
            raise VerifyInputError(f"node {name} is of kind {node.kind}: verify can't observe it, and an unobserved "
                                   f"node could hide a change. Pass --unobserved {name} if it has no routing stack")
        drv = overrides.get(name)
        if drv is None:
            try:
                drv = detect(node)
            except DriverError:
                raise VerifyInputError(f"cannot tell what runs on node {name} (kind {node.kind!r}, image {node.image!r}); "
                                       f"set nodes.{name}.driver: frr in the guards file, or pass --unobserved {name} "
                                       "if it is a host without a routing stack") from None
        if drv not in DRIVERS:
            raise VerifyInputError(f"node {name}: unknown driver {drv!r}")
        if drv != "frr":
            raise VerifyInputError(f"node {name} runs {drv}; verify 0.4 snapshots FRR nodes only (other platforms follow). "
                                   f"Pass --unobserved {name} to run without it: changes on {name} are then not "
                                   "compared, and the report says so")
        out[name] = drv
    return out


def unobserved_reasons(lab: Lab, nodes: dict[str, str]) -> dict[str, str]:
    """Why each node verify doesn't snapshot is left out, for every output (an unobserved node is never silent)."""
    out = {}
    for name in sorted(n for n, drv in nodes.items() if not drv):
        node = lab.nodes[name]
        if node.kind in BRIDGE_KINDS:
            out[name] = f"a {node.kind} (no routing stack)"
            continue
        try:
            drv = detect(node)
        except DriverError:
            drv = None
        if drv and drv != "frr":
            out[name] = f"runs {drv}: verify 0.4 snapshots FRR only; changes on {name} are not compared"
        else:
            out[name] = f"named --unobserved (kind {node.kind}): changes on {name} are not compared"
    return out


def collect(lab: Lab, nodes: dict[str, str], cmd_timeout: float = 60) -> Snapshot:
    """`cmd_timeout`: each command's time limit; one that hits it was cut (CommandTimedOut), never "nothing"."""
    def exec_fn(node, argv):
        r = lab.exec(node, argv, timeout=cmd_timeout)
        return r.rc, r.stdout, r.stderr
    # every lab interface's link-local addresses, so a link-local next hop is named by its owner (gauntlet R1);
    # a node whose addresses can't be read leaves its addresses as written
    per_node = {}
    for n, nd in sorted(lab.nodes.items()):
        if nd.kind in BRIDGE_KINDS:
            continue
        rc, out, _err = exec_fn(n, ["ip", "-6", "addr", "show", "scope", "link"])
        if rc == 0:
            per_node[n] = parse_link_local(out, n)
    owners = link_local_names(per_node)
    snaps = {n: FrrCollector(n, exec_fn, owners).collect() for n, drv in sorted(nodes.items()) if drv == "frr"}
    return Snapshot(snaps, unobserved_reasons(lab, nodes))


@contextmanager
def deployed(topology: Path, setup: dict[str, list[str]], keep: bool, log: Callable[[str], None]):
    from ..runner import _ACTIVE, _signals_deferred

    lab = Lab(topology)
    lab.check_tools()
    lab.acquire_lock()
    started = False
    try:
        existing = lab.existing_containers()
        if existing:
            raise LabError(f"a lab named '{lab.name}' is already running ({len(existing)} container(s)); verify won't "
                           f"redeploy or destroy it. Remove it with: containerlab destroy -t <topology> --cleanup")
        started = True
        if not keep:
            _ACTIVE.add(lab)
        log(f"Deploying lab {lab.name} ({len(lab.nodes)} nodes)...")
        lab.deploy()
        missing = {n.container for n in lab.nodes.values()} - lab.running_containers()
        if missing:
            raise LabError(f"lab containers not running: {', '.join(sorted(missing))}")
        for node, cmds in setup.items():
            lab.run_setup(node, cmds, log=log)
        yield lab
    finally:
        with _signals_deferred():
            if started and not keep:
                log("Destroying lab...")
                try:
                    lab.destroy()
                except Exception as e:   # cleanup trouble must never hide the result
                    log(f"warning: lab cleanup failed: {e}")
            elif started:
                log(f"Lab {lab.name} left running (--keep); destroy with: containerlab destroy -t {topology} --cleanup")
            _ACTIVE.discard(lab)
            lab.release_lock()


FRR_CONFIGS = ("/etc/frr/frr.conf", "/etc/frr/bgpd.conf")


def check_config_loaded(lab, nodes: dict[str, str], label: str) -> None:
    """Every node loaded its config as written, or LabError (exit 2). FRR skips a line it rejects and loads the
    rest: a changed line it rejected on the after side would read as no change at all. The same reading as a run's
    (runner.config_load_by_node); a node not snapshotted counts when its log shows rejected lines."""
    from ..runner import config_load_by_node, rejected_config_message

    def driver_of(name: str, node) -> str | None:
        # a node verify doesn't snapshot (--unobserved, a host) is read the way `run` reads it: by the driver it
        # can be detected as, else by its log (multi-vendor audit F4)
        if nodes.get(name):
            return nodes[name]
        try:
            return detect(node)
        except DriverError:
            return None
    rejected = rejected_config_message(config_load_by_node(lab, driver_of))
    if rejected:
        raise LabError(f"[{label}] {rejected} No verdict.")

def expects_bgp(exec_fn, node: str) -> bool:
    """Whether an FRR node is configured to run BGP: `router bgp` in its config file, read inside the
    container (the bound file is there before FRR has loaded it). Unreadable: assume it does."""
    seen = False
    for path in FRR_CONFIGS:
        rc, out, _err = exec_fn(node, ["cat", path])
        if rc == 0:
            seen = True
            if re.search(r"(?m)^\s*router bgp(\s|$)", out):
                return True
    return not seen


def real_side(*, nodes: dict[str, str], setup: dict, settle: float, timeout: float, keep_after: bool,
              log: Callable[[str], None]):
    """The default way to get one side's snapshot: deploy, wait for a stable snapshot, run `on_up` (the
    guards, on the after lab), destroy."""
    def side(label: str, topology: Path, on_up=None):
        t0 = time.monotonic()
        with deployed(topology, setup, keep_after and label == "after", log) as lab:
            def exec_fn(node, argv):
                r = lab.exec(node, argv, timeout=60)
                return r.rc, r.stdout, r.stderr
            bgp_nodes = {n for n, drv in nodes.items() if drv == "frr" and expects_bgp(exec_fn, n)}
            log(f"[{label}] waiting for a stable snapshot (settle {settle:g}s, timeout {timeout:g}s)...")
            snap = stable_snapshot(lambda: collect(lab, nodes, max(60.0, timeout)), settle=settle, timeout=timeout, log=log,
                                   bgp_nodes=bgp_nodes)
            if isinstance(snap, Snapshot):
                check_config_loaded(lab, nodes, label)
            extra = on_up(lab, topology) if on_up is not None and isinstance(snap, Snapshot) else None
        return snap, round(time.monotonic() - t0, 1), extra
    return side


# ---------------------------------------------------------------------------------------------------------
# Guards
# ---------------------------------------------------------------------------------------------------------

def run_guards(cfg, topology: Path, settle: float, hold: float, log) -> dict:
    from ..runner import run

    rep = run(replace(cfg, lab=topology), deploy=False, keep=True, settle=settle, hold=hold, log=log)
    return {"status": rep.status, "passed": rep.passed, "failed": rep.failed, "error": rep.error or None,
            "failures": [{"check": r.check.name, "node": r.check.params.get("node"), "reason": str(r.detail)}
                         for r in rep.results if not r.passed]}


def load_guards(path: str | None, before_spec: str, before: Side):
    """The standing guards: (config or None, where it was read from, guards_source).

    With a git ref as --before, they are read from that ref (the base branch), never from the working tree
    or the change: the --guards path in that ref, or without --guards the netdryrun.yml next to the
    topology there, when one exists. With a directory as --before, only from an explicit --guards path."""
    from ..runner import load_config

    if before.is_ref:
        if path is None:
            p = before.topology.parent / "netdryrun.yml"
            if not p.is_file():
                return None, None, "none"
        else:
            p = before.locate(Path(path))
            if p is None:
                raise VerifyInputError(f"--guards {path} is outside the git repository {before.repo}")
            if p.is_dir():
                p = p / "netdryrun.yml"
            if not p.is_file():
                raise VerifyInputError(f"--guards {path}: not in the before ref ({before_spec}); the standing guards "
                                       "are read from the base, never from the change")
        return load_config(p), f"{p.relative_to(before.root).as_posix()} at {before_spec}", "before-ref"
    if path is None:
        return None, None, "none"
    return load_config(path), str(path), "explicit"


# ---------------------------------------------------------------------------------------------------------
# The determinism rule
# ---------------------------------------------------------------------------------------------------------

APPROVING = ("matched", "no_change")
NOT_DETERMINISTIC = ("a second boot of one side, with the same configs, gave a different snapshot: the lab is not "
                     "deterministic, so this run approves nothing")


def confirm_by_rerun(res: VerifyResult, side, before_topo: Path, snap_b: Snapshot, after_topo: Path,
                     snap_a: Snapshot) -> None:
    """No approval from a single boot: boot each side again and require the same snapshot (a before boot that
    stably missed an item would hide a change that removes it; an after boot, one that adds it). The first
    difference (or a rerun that never settles) is INCONCLUSIVE, naming every item that differed."""
    differing: list[str] = []
    for label, topo, first in (("rerun-before", before_topo, snap_b), ("rerun-after", after_topo, snap_a)):
        snap_r, tr, _ = side(label, topo)
        res.timings[f"{label.replace('-', '_')}_s"] = tr
        if isinstance(snap_r, Inconclusive):
            res.status, res.inconclusive, res.inconclusive_side = "inconclusive", snap_r, "rerun"
            return
        differing = [f"{label.split('-')[1]}: {d.key.where()} {d.change}" for d in diff(first, snap_r)]
        if differing:
            break
    res.determinism = {"reruns": ["before", "after"], "identical": not differing, "differing": differing}
    if differing:
        res.status, res.inconclusive, res.inconclusive_side = "inconclusive", Inconclusive(NOT_DETERMINISTIC, differing), "rerun"


# ---------------------------------------------------------------------------------------------------------
# verify
# ---------------------------------------------------------------------------------------------------------

def verify(topology: str, before: str, after: str, intent_path: str, *, guards: str | None = None,
           config_dir_name: str | None = None, unobserved: list[str] = (), settle: float = 15.0,
           timeout: float = 300.0, hold: float = 10.0, allow_unhealthy_baseline: bool = False, keep: bool = False,
           log: Callable[[str], None] = lambda _: None, side_fn=None, intent_source: str = "cli",
           intent_text: str | None = None) -> VerifyResult:
    """`intent_source` says who supplied the intent (the CLI user, an MCP caller, the Action); the report
    echoes it next to the intent. `intent_text`, when given, is the intent itself (YAML or JSON) instead of
    the file at `intent_path`: an MCP caller passes the ticket's intent inline. Inline text is in neither
    side's tree, so it can't be flagged as edited by the change."""
    res = VerifyResult(status="error", topology=str(topology), before_spec=before, after_spec=after,
                       run_id=uuid.uuid4().hex[:12], started=_now(), intent_supplied_by=intent_source)
    work = Path(tempfile.mkdtemp(prefix="netdryrun-verify-"))
    try:
        res.intent = (parse_intent_text(intent_text, "inline intent") if intent_text is not None
                      else load_intent(intent_path))
        if res.intent.allow:
            res.warnings.append(ALLOW_WARNING)
        topo = Path(topology)
        if not topo.is_file():
            raise VerifyInputError(f"{topology}: topology not found")
        lab = Lab(topo)
        res.containers = {n: nd.container for n, nd in lab.nodes.items()}
        bside = materialize(before, "before", topo, work, config_dir_name)
        aside = materialize(after, "after", topo, work, config_dir_name)
        res.before_spec, res.after_spec = f"{before}: {bside.desc}", f"{after}: {aside.desc}"
        differ = check_sides(bside, aside, log)
        if intent_text is None and intent_edited(Path(intent_path), bside, aside):
            res.warnings.append(INTENT_EDITED_WARNING)
        before_topo, after_topo = bside.topology, aside.topology
        gcfg, gsource, res.guards_source = load_guards(guards, before, bside)
        if gcfg is None:
            res.warnings.append(NO_GUARDS_WARNING)
        nodes = classify_nodes(lab, gcfg.drivers if gcfg else {}, list(unobserved))
        check_changed_binds(bside.topology, differ, nodes)
        for name, why in unobserved_reasons(lab, nodes).items():
            if lab.nodes[name].kind not in BRIDGE_KINDS:
                res.warnings.append(f"node {name} is not observed ({why})")
        check_nodes(res.intent, nodes)
        side = side_fn or real_side(nodes=nodes, setup=gcfg.setup if gcfg else {}, settle=settle, timeout=timeout,
                                    keep_after=keep, log=log)

        snap_b, tb, _ = side("before", before_topo)
        res.timings["before_s"] = tb
        if isinstance(snap_b, Inconclusive):
            res.status, res.inconclusive, res.inconclusive_side = "inconclusive", snap_b, "before"
            return res
        res.before = snap_b
        res.baseline_problems = baseline_problems(snap_b)
        if res.baseline_problems and not allow_unhealthy_baseline:
            res.status = "unhealthy_baseline"
            return res
        res.baseline_overridden = bool(res.baseline_problems)

        on_up = (lambda _lab, t: {**run_guards(gcfg, t, settle, hold, log), "source": gsource}) if gcfg else None
        snap_a, ta, gres = side("after", after_topo, on_up)
        res.timings["after_s"] = ta
        if isinstance(snap_a, Inconclusive):
            res.status, res.inconclusive, res.inconclusive_side = "inconclusive", snap_a, "after"
            return res
        res.after = snap_a
        res.guards = gres

        m = match(snap_b, snap_a, res.intent)
        res.match = m
        res.status = m.status
        if m.undeclared:
            res.failed_because.append("undeclared")
        if m.not_happened:
            res.failed_because.append("not_happened")
        if gres is not None:
            if gres["status"] == "failed":
                res.failed_because.append("guards")
                res.status = "failed"
            elif gres["status"] != "passed" and res.status != "failed":
                res.status = "inconclusive" if gres["status"] == "inconclusive" else "error"
                res.error = f"the standing guards ended with {gres['status']}: {gres.get('error') or 'no verdict'}"
        if res.status in APPROVING:
            confirm_by_rerun(res, side, before_topo, snap_b, after_topo, snap_a)
        return res
    except SnapshotError as e:
        res.status, res.error = "error", f"unreadable snapshot: {e}"
        return res
    except IntentError as e:
        res.status, res.error = "error", f"intent error: {e}"
        return res
    except ConfigError as e:
        res.status, res.error = "error", f"guards config error: {e}"
        return res
    except (VerifyInputError, VerifyError, LabError, DriverError) as e:
        res.status, res.error = "error", str(e)
        return res
    except OSError as e:
        res.status, res.error = "error", f"cannot prepare the labs: {e}"
        return res
    finally:
        res.finished = _now()
        shutil.rmtree(work, ignore_errors=True)
