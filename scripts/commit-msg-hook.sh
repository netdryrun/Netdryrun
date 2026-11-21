#!/bin/sh
# commit-msg hook: refuse a commit whose gate trailers (Fixes-Oracle, No-Oracle, Oracle, Session) git won't read,
# because they aren't in the message's last paragraph (scripts/fastfix_gate.py check-message; PR #6, 897f1e2 and
# ca9d984). Install once per clone:
#   ln -s ../../scripts/commit-msg-hook.sh .git/hooks/commit-msg      (or copy it there)
# A checkout without scripts/fastfix_gate.py (a branch from before 0.4.2) has nothing to check.
top=$(git rev-parse --show-toplevel) || exit 1
gate="$top/scripts/fastfix_gate.py"
[ -f "$gate" ] || exit 0
for py in python3 python; do
  if command -v "$py" >/dev/null 2>&1 && "$py" -c 'import sys; sys.exit(sys.version_info < (3, 10))' 2>/dev/null; then
    exec "$py" "$gate" check-message "$1"
  fi
done
echo "commit-msg: no Python 3.10+ to check the trailers with; commit refused (fail closed)" >&2
exit 1
