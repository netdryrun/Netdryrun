#!/usr/bin/env bash
# Regenerate the hash-locked requirements (requirements/README.md). Needs uv.
set -euo pipefail
cd "$(dirname "$0")/.."
# lock FILE PYTHON INPUT...: PYTHON is the oldest Python the lock must serve (the package supports 3.10 and later;
# mkdocs-material needs 3.11, and the site builds on 3.12)
lock() {
  local out=$1 py=$2
  shift 2
  uv pip compile --quiet --universal --python-version "$py" --generate-hashes --no-header \
    --output-file "requirements/$out" "$@"
}
lock runtime.txt 3.10 pyproject.toml requirements/build.in
lock ci.txt 3.10 pyproject.toml --extra dev requirements/build.in
lock release.txt 3.10 requirements/release.in
lock docs.txt 3.11 requirements/docs.in
lock tools.txt 3.10 requirements/tools.in
echo "locked:" requirements/*.txt
