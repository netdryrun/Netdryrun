"""A capture bundle on disk, and the checks a contributed one must pass.

  BUNDLE/manifest.json        netdryrun.capture/v1: what was captured, from what, how, and the hash of every file
  BUNDLE/outputs/NN-*.txt     each command's output exactly as the device printed it (sanitised: as rewritten)

A bundle proves itself by replay: the driver is run again against the bundle's outputs, and it must ask for exactly
the bundle's commands, in order, and read exactly what the manifest says it read.
"""
from __future__ import annotations

import datetime
import hashlib
import json
import re
from pathlib import Path

from .. import __version__
from ..drivers import DRIVERS
from ..lab import Node
from . import SCHEMA, CaptureError
from . import sanitize as san
from .collect import SCENARIOS, ReplayLab, read, shows

MANIFEST = "manifest.json"
REQUIRED = ("schema", "netdryrun_version", "captured", "nos", "nos_version", "nos_version_reported", "kind", "image",
            "image_digest", "node", "scenario", "params", "vrf", "commands", "command_list_sha256", "reading",
            "shows_scenario", "sanitizer")


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _command_list_sha(commands: list[dict]) -> str:
    return _sha("\n".join(json.dumps(c["argv"]) for c in commands))


def _slug(argv: list[str]) -> str:
    return re.sub(r"[^a-z0-9]+", "-", " ".join(argv).lower()).strip("-")[:60] or "command"


def build(node: Node, nos: str, scenario: str, params: dict, vrf: str, recorded: list[dict], reading: dict,
          version: str | None, reported: str | None, digest: str | None) -> tuple[dict, dict[str, str]]:
    """(manifest, {relative path: output text}) for a fresh capture, not yet sanitised."""
    files: dict[str, str] = {}
    commands = []
    for i, r in enumerate(recorded, 1):
        rel = f"outputs/{i:02d}-{_slug(r['argv'])}.txt"
        files[rel] = r["stdout"]
        commands.append({"argv": r["argv"], "rc": r["rc"], "stderr": r["stderr"][-2000:], "file": rel,
                         "sha256": _sha(r["stdout"])})
    manifest = {
        "schema": SCHEMA, "netdryrun_version": __version__,
        "captured": datetime.datetime.now(datetime.timezone.utc).date().isoformat(),
        "nos": nos, "nos_version": version, "nos_version_reported": reported,
        "kind": node.kind, "image": node.image, "image_digest": digest, "node": node.name,
        "scenario": scenario, "params": params, "vrf": vrf,
        "commands": commands, "command_list_sha256": _command_list_sha(commands),
        "reading": reading, "shows_scenario": shows(scenario, reading), "sanitizer": None,
    }
    return manifest, files


def write(out: Path, manifest: dict, files: dict[str, str]) -> None:
    out = Path(out)
    if out.exists() and any(out.iterdir()):
        raise CaptureError(f"{out} is not empty; give a new folder")
    (out / "outputs").mkdir(parents=True, exist_ok=True)
    for rel, text in files.items():
        (out / rel).write_text(text, encoding="utf-8", newline="")
    (out / MANIFEST).write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


def load(bundle: Path) -> tuple[dict, dict[str, str]]:
    """(manifest, outputs) of a bundle whose files match their hashes; CaptureError otherwise."""
    bundle = Path(bundle)
    try:
        manifest = json.loads((bundle / MANIFEST).read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise CaptureError(f"{bundle / MANIFEST}: cannot read it: {e}") from None
    if not isinstance(manifest, dict) or manifest.get("schema") != SCHEMA:
        raise CaptureError(f"{bundle / MANIFEST}: not a {SCHEMA} manifest")
    missing = [k for k in REQUIRED if k not in manifest]
    if missing:
        raise CaptureError(f"{bundle / MANIFEST}: missing {', '.join(missing)}")
    files: dict[str, str] = {}
    for c in manifest["commands"]:
        rel = c.get("file", "")
        p = (bundle / rel).resolve()
        if not rel.startswith("outputs/") or bundle.resolve() not in p.parents:
            raise CaptureError(f"{bundle / MANIFEST}: file {rel!r} is outside the bundle's outputs/")
        try:
            text = p.read_bytes().decode("utf-8")
        except (OSError, UnicodeDecodeError) as e:
            raise CaptureError(f"{rel}: cannot read it: {e}") from None
        if _sha(text) != c.get("sha256"):
            raise CaptureError(f"{rel}: its sha256 doesn't match the manifest (edited after the capture?)")
        files[rel] = text
    listed = set(files)
    present = {p.relative_to(bundle).as_posix() for p in bundle.rglob("*") if p.is_file()} - {MANIFEST}
    if present - listed:
        raise CaptureError(f"files the manifest doesn't list: {', '.join(sorted(present - listed))}")
    if _command_list_sha(manifest["commands"]) != manifest["command_list_sha256"]:
        raise CaptureError("command_list_sha256 doesn't match the commands")
    return manifest, files


def replay(manifest: dict, files: dict[str, str]) -> tuple[dict, str | None]:
    """The driver's reading and version, run against the bundle's outputs. CaptureError when the driver asks for
    anything the bundle doesn't hold, in that order, or leaves part of it unread."""
    nos = manifest["nos"]
    if nos not in DRIVERS:
        raise CaptureError(f"nos {nos!r} has no driver; one of {sorted(DRIVERS)}")
    if manifest["scenario"] not in SCENARIOS:
        raise CaptureError(f"unknown scenario {manifest['scenario']!r}")
    node = Node(manifest["node"], manifest["node"], manifest["kind"], manifest["image"])
    recorded = [{"argv": c["argv"], "rc": c["rc"], "stdout": files[c["file"]], "stderr": c["stderr"]}
                for c in manifest["commands"]]
    lab = ReplayLab(node, recorded)
    driver = DRIVERS[nos](lab, node.name)
    version = driver.nos_version()
    reading = json.loads(json.dumps(read(driver, manifest["scenario"], manifest["params"], manifest["vrf"])))
    if lab.leftover():
        raise CaptureError(f"{len(lab.leftover())} command(s) in the bundle the driver never ran: "
                           f"`{' '.join(lab.leftover()[0]['argv'])}` first")
    return reading, version


def _image(image: str, s: san.Sanitizer) -> str:
    """An image name without a private registry host (a registry name says whose lab it is)."""
    first, sep, rest = image.partition("/")
    if sep and ("." in first or ":" in first or first == "localhost") and first not in ("docker.io", "ghcr.io", "quay.io"):
        image = "registry.invalid/" + rest
    return s.names_only(image)


def sanitize(manifest: dict, files: dict[str, str], hostnames=()) -> tuple[dict, dict[str, str], dict, list[str]]:
    """(sanitised manifest, sanitised outputs, the mapping, problems). Nothing is written. Any problem means the
    result must not be shared: the self-check below runs on the output and doesn't trust the rewrite."""
    s = san.Sanitizer([*hostnames, manifest["node"]])
    body = {k: v for k, v in manifest.items() if k not in ("sanitizer", "image")}
    body_text = json.dumps(body, indent=2)
    for text in [*files.values(), body_text]:
        s.collect(text)
    s.build()
    rewritten = {rel: s.text(text) for rel, text in files.items()}
    new = json.loads(s.text(body_text))
    new["image"] = _image(manifest["image"], s)
    new_files: dict[str, str] = {}
    originals: dict[str, str] = {}
    for i, (c, old) in enumerate(zip(new["commands"], manifest["commands"]), 1):
        c["file"] = f"outputs/{i:02d}-{_slug(c['argv'])}.txt"     # an old name can spell a prefix: name it again
        new_files[c["file"]] = rewritten[old["file"]]
        originals[c["file"]] = files[old["file"]]
        c["sha256"] = _sha(new_files[c["file"]])
    new["command_list_sha256"] = _command_list_sha(new["commands"])
    problems = list(s.problems)
    mapping = s.mapping()

    for rel, text in new_files.items():
        problems += [f"{rel}: {x} remains" for x in san.leaks(text, mapping)]
        if san.shape(s.names_only(originals[rel])) != san.shape(text):
            problems.append(f"{rel}: the structure changed")
    problems += [f"{MANIFEST}: {x} remains" for x in san.leaks(json.dumps(new), mapping)]
    try:
        reading, version = replay(new, new_files)
        if reading != new["reading"]:
            problems.append("the driver reads the sanitised outputs differently from the originals")
        if version != new["nos_version"]:
            problems.append(f"the driver reads NOS version {version!r} from the sanitised outputs, "
                            f"{new['nos_version']!r} from the originals")
    except CaptureError as e:
        problems.append(f"replay of the sanitised bundle failed: {e}")
    new["sanitizer"] = {"version": san.VERSION, "self_check": "failed" if problems else "passed",
                        "replaced": dict(s.counts)}
    return new, new_files, mapping, sorted(set(problems))


def validate(bundle: Path) -> tuple[list[str], list[str]]:
    """(problems, notes) for a contributed bundle. Any problem rejects it. Notes need a human's eyes."""
    try:
        manifest, files = load(bundle)
    except CaptureError as e:
        return [str(e)], []
    problems, notes = [], []
    sc = manifest.get("sanitizer") or {}
    if sc.get("self_check") != "passed" or sc.get("version") != san.VERSION:
        problems.append("not sanitised by this version's `netdryrun sanitize`, or its self-check failed")
    for rel, text in files.items():
        problems += [f"{rel}: {x}" for x in san.leaks(text)]
    problems += [f"{MANIFEST}: {x}" for x in san.leaks(json.dumps(manifest))]
    try:
        reading, version = replay(manifest, files)
        if reading != manifest["reading"]:
            problems.append("replay: the driver reads the outputs differently from what the manifest records")
        if version != manifest["nos_version"]:
            problems.append(f"replay: NOS version {version!r}, the manifest says {manifest['nos_version']!r}")
    except CaptureError as e:
        problems.append(f"replay: {e}")
        reading = manifest.get("reading", {})
    shown = shows(manifest["scenario"], reading) if not problems else None
    if shown is False or manifest["shows_scenario"] is False:
        problems.append(f"the outputs don't show scenario {manifest['scenario']} ({SCENARIOS[manifest['scenario']].shows})"
                        if manifest["scenario"] in SCENARIOS else "unknown scenario")
    elif shown is None and not problems:
        notes.append("the driver can't read these outputs yet: a human compares them with the scenario")
    if not manifest.get("image_digest"):
        notes.append("no image digest recorded (Docker had none for the image)")
    return sorted(set(problems)), notes
