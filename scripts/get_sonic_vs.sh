#!/usr/bin/env bash
# Download the official SONiC virtual-switch container (docker-sonic-vs) from the SONiC project's CI, record
# which build it is (the image's own `Tag` label, e.g. master.1258173-c10162df4) and load it as
# docker-sonic-vs:<build id>. The build id is the pin: put it in examples/sonic-frr/topology.clab.yml and
# re-capture the SONiC fixtures (scripts/capture_fixtures.sh sonic) in the same commit.
set -euo pipefail
mkdir -p "$HOME/sonic-download" && cd "$HOME/sonic-download"
URL="https://sonic-build.azurewebsites.net/api/sonic/artifacts?branchName=master&platform=vs&target=target/docker-sonic-vs.gz"
curl -fL --retry 3 -o docker-sonic-vs.gz "$URL"
ls -la docker-sonic-vs.gz
docker load < docker-sonic-vs.gz | tail -2
BUILD=$(docker image inspect docker-sonic-vs:latest --format '{{index .Config.Labels "Tag"}}')
case $BUILD in ''|*[!A-Za-z0-9._-]*) echo "cannot read the build id from the image's Tag label: '$BUILD'" >&2; exit 1 ;; esac
docker tag docker-sonic-vs:latest "docker-sonic-vs:$BUILD"
docker rmi docker-sonic-vs:latest >/dev/null    # leaves only the pinned tag, so nothing can run "latest" by accident
echo "loaded docker-sonic-vs:$BUILD (image $(docker image inspect "docker-sonic-vs:$BUILD" --format '{{.Id}} created {{.Created}}'))"
docker images | grep -i sonic
