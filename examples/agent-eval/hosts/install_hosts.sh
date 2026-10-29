#!/bin/bash
# Pinned installs of the three agent hosts, from their official packages, under /opt/agent-hosts (as root):
#   wsl -d Ubuntu-ndr -u root -- bash hosts/install_hosts.sh
# Node 26.13.0 (nodejs.org, checksum checked) for Cline 3.0.74 (npm), Goose 1.57.0 (its GitHub release binary),
# OpenHands CLI 1.16.0 (PyPI, with uv's Python 3.12). Nothing goes into labagent's home.
set -e
mkdir -p /opt/agent-hosts
cd /opt/agent-hosts
if [ ! -d node-v26.13.0-linux-x64 ]; then
  curl -sSLO https://nodejs.org/dist/v26.13.0/node-v26.13.0-linux-x64.tar.xz
  curl -sSL https://nodejs.org/dist/v26.13.0/SHASUMS256.txt | grep "node-v26.13.0-linux-x64.tar.xz$" | sha256sum -c -
  tar xf node-v26.13.0-linux-x64.tar.xz && rm node-v26.13.0-linux-x64.tar.xz
fi
ln -sfn node-v26.13.0-linux-x64 node
mkdir -p cline bin
PATH=/opt/agent-hosts/node/bin:$PATH npm install --prefix /opt/agent-hosts/cline cline@3.0.74 --no-fund --no-audit 2>&1 | tail -2
curl -sSL https://github.com/aaif-goose/goose/releases/download/v1.57.0/goose-x86_64-unknown-linux-gnu.tar.bz2 -o goose.tar.bz2
mkdir -p goose && tar xjf goose.tar.bz2 -C goose && rm goose.tar.bz2
ls goose
[ -d uvenv ] || python3 -m venv uvenv
uvenv/bin/pip -q install uv
export UV_PYTHON_INSTALL_DIR=/opt/agent-hosts/python UV_TOOL_DIR=/opt/agent-hosts/uvtools UV_TOOL_BIN_DIR=/opt/agent-hosts/bin
uvenv/bin/uv tool install --python 3.12 openhands==1.16.0 2>&1 | tail -2
ln -sfn /opt/agent-hosts/goose/goose bin/goose
cat > bin/cline <<'W'
#!/bin/sh
exec /opt/agent-hosts/node/bin/node /opt/agent-hosts/cline/node_modules/cline/bin/cline "$@"
W
chmod 755 bin/cline
chmod -R a+rX /opt/agent-hosts
bin/goose --version; bin/cline --version; bin/openhands --version 2>/dev/null | tail -1
ls /opt/agent-hosts /opt/agent-hosts/bin
