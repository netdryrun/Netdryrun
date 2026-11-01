#!/usr/bin/env bash
# Install containerlab from its GitHub release, checksum verified, the way get.containerlab.dev installs it (the
# binary with the SUID bit, the clab_admins group, the current user in it), without piping a script from the web
# into a shell.
#
#   scripts/install_containerlab.sh [VERSION]     VERSION defaults to the pinned one; "latest" resolves the newest
#
# The pinned version's archive hashes are in this file. Any other version is checked against that release's
# checksums.txt, which only proves the download matches what the release lists (said in a warning).
set -euo pipefail

PINNED=0.81.1
declare -A PINNED_SHA256=(
  [amd64]=3a257dc329774dff598c7f1277bb7c2723f76ff620cdab33f83a9f381f4e64ae
  [arm64]=3a4c0188583d9a72b96a4eb0903a49d4bfa9e23e7d5b3f37355da815364ad334
)
REPO=https://github.com/srl-labs/containerlab/releases

version=${1:-$PINNED}
if [ "$version" = latest ]; then
  version=$(curl -fsSLI -o /dev/null -w '%{url_effective}' "$REPO/latest")
  version=${version##*/v}
fi
case "$(uname -m)" in
  x86_64) arch=amd64 ;;
  aarch64 | arm64) arch=arm64 ;;
  *) echo "containerlab: no release for $(uname -m)" >&2; exit 1 ;;
esac

file="containerlab_${version}_linux_${arch}.tar.gz"
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
curl -fsSL -o "$tmp/$file" "$REPO/download/v${version}/${file}"
if [ "$version" = "$PINNED" ]; then
  sum=${PINNED_SHA256[$arch]}
else
  curl -fsSL -o "$tmp/checksums.txt" "$REPO/download/v${version}/checksums.txt"
  sum=$(awk -v f="$file" '$2 == f {print $1}' "$tmp/checksums.txt")
  [ -n "$sum" ] || { echo "containerlab: $file is not in the release's checksums.txt" >&2; exit 1; }
  echo "::warning title=containerlab::$version is not the pinned $PINNED; checked against its release's checksums.txt only"
fi
echo "$sum  $tmp/$file" | sha256sum -c -

tar -xzf "$tmp/$file" -C "$tmp" containerlab
sudo install -m 4755 "$tmp/containerlab" /usr/bin/containerlab
getent group clab_admins >/dev/null || sudo groupadd -r clab_admins
sudo usermod -aG clab_admins "$(id -un)"
containerlab version | grep -i version
