#!/usr/bin/env bash
set -euo pipefail

here=$(cd "$(dirname "$0")" && pwd)
plugin_dir="$here/${1:-adhd-theme}"
base="${KANDEV_BASE:-http://127.0.0.1:38429}"
kandev_src="${KANDEV_SRC:-$HOME/engineering/kandev-src}"

id=$(sed -n 's/^id: *"\{0,1\}\([^"]*\)"\{0,1\}$/\1/p' "$plugin_dir/manifest.yaml")
version=$(sed -n 's/^version: *"\{0,1\}\([^"]*\)"\{0,1\}$/\1/p' "$plugin_dir/manifest.yaml")
[ -n "$id" ] && [ -n "$version" ] || { echo "install-plugin: id/version missing in $plugin_dir/manifest.yaml" >&2; exit 1; }

command -v go >/dev/null || { echo "install-plugin: go is required (brew install go)" >&2; exit 1; }
if [ ! -d "$kandev_src/apps/backend/pkg/pluginsdk" ]; then
  tag="v$(kandev --version 2>/dev/null | grep -o '[0-9]\+\.[0-9]\+\.[0-9]\+' | head -1)"
  echo "install-plugin: cloning kandev $tag into $kandev_src for the plugin SDK"
  git clone -q --depth 1 --branch "$tag" https://github.com/kdlbs/kandev "$kandev_src"
fi

goos=$(uname -s | tr '[:upper:]' '[:lower:]'); goarch=$(uname -m); [ "$goarch" = "x86_64" ] && goarch=amd64; [ "$goarch" = "aarch64" ] && goarch=arm64
bin="$plugin_dir/.build/server/plugin-$goos-$goarch"
rel=$(python3 -c 'import os,sys; print(os.path.relpath(sys.argv[1], sys.argv[2]))' "$kandev_src/apps/backend" "$plugin_dir")
(cd "$plugin_dir" && grep -q "=> $rel\$" go.mod || go mod edit -replace "github.com/kandev/kandev=$rel"
  go mod tidy >/dev/null 2>&1 && GOOS="$goos" GOARCH="$goarch" go build -trimpath -ldflags="-s -w" -o "$bin" ./server)

registered=$(curl -sf "$base/api/plugins" | python3 -c 'import json,sys; d=json.load(sys.stdin); ps=d if isinstance(d,list) else d.get("plugins",d); print(next((p.get("version","") for p in ps if p.get("id")==sys.argv[1]),""))' "$id" 2>/dev/null || true)
if [ -n "$registered" ] && [ "$registered" != "$version" ]; then
  echo "install-plugin: $id $registered registered; replacing with $version"
  curl -sf -X DELETE "$base/api/plugins/$id" >/dev/null || echo "install-plugin: warning: uninstall of $id $registered failed"
  rm -rf "$HOME/.kandev/plugins/$id/$registered"
fi
target="$HOME/.kandev/plugins/$id/$version"
mkdir -p "$target/server" "$target/ui"
cp "$plugin_dir/manifest.yaml" "$target/manifest.yaml"
cp "$plugin_dir"/ui/* "$target/ui/"
cp "$bin" "$target/server/"
echo "install-plugin: staged $id@$version at $target"

curl -sf -X POST "$base/api/plugins/sync" -H 'Content-Type: application/json' -d '{}' | head -c 600; echo
curl -sf -X POST "$base/api/plugins/$id/enable" >/dev/null && echo "install-plugin: $id enabled (sideloads register disabled; this is our own plugin, so enable it)"
echo "install-plugin: reload the Kandev UI to pick up the styles"
