#!/usr/bin/env bash
set -euo pipefail
repo="$1"
commit="$2"
base="${KANDEV_BASE:-http://127.0.0.1:38429}"
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT

fetch() {
  git init -q "$1"
  git -C "$1" fetch -q --depth 1 "https://github.com/$2" "$3"
  git -C "$1" checkout -q FETCH_HEAD
}

fetch "$work/plugin" "$repo" "$commit"
fetch "$work/kandev-sdk" kdlbs/kandev "$(tr -d '[:space:]' < "$work/plugin/.kandev-sdk-ref")"
(cd "$work/plugin" && npm ci --no-audit --no-fund --ignore-scripts >/dev/null && make package-host >/dev/null)
package="$work/plugin/$(make -s -C "$work/plugin" package-file)"
curl -sf -X POST "$base/api/plugins/install" -F "package=@$package" >/dev/null
echo "install-source-plugin: installed $repo@${commit:0:7}"
