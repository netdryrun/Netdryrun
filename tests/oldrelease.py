"""Export an old release's src for the red-team procedure (tests/redteam/README.md).

Under mutmut the tests run in mutants/, an untracked folder of the repository: git refuses to run there ("current working
directory is untracked"), so the repository's top level is tried too. The mutation layer runs this through real mutmut
(tests/test_import_guard.py), so a git call that only works from the checkout's root fails that layer."""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path


def export_src(tag: str, dest: Path, root: Path) -> bool:
    """Extract `tag`'s src/ into dest. False when git or tar is missing or the tag cannot be found (a clone without tags);
    any other failure raises. git runs in the checkout's root, and in its parent when that is where the repository is (the
    root is mutmut's untracked mutants/ folder: the tag resolves there, but `git archive` refuses to run)."""
    if shutil.which("git") is None or shutil.which("tar") is None:
        return False
    seen, errors = False, []
    for d in (root, root.parent):
        if subprocess.run(["git", "rev-parse", "--verify", "-q", f"{tag}^{{commit}}"], cwd=d,
                          capture_output=True).returncode != 0:
            continue
        seen = True
        arc = subprocess.run(["git", "archive", tag, "src"], cwd=d, capture_output=True)
        if arc.returncode == 0:
            dest.mkdir(parents=True, exist_ok=True)
            subprocess.run(["tar", "-x", "-C", str(dest)], input=arc.stdout, check=True)
            return True
        errors.append(f"{d}: {arc.stderr.decode(errors='replace')[:200]}")
    if seen:
        raise RuntimeError(f"git archive {tag} failed: {'; '.join(errors)}")
    return False
