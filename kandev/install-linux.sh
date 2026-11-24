#!/usr/bin/env bash
set -euo pipefail

here=$(cd "$(dirname "$0")" && pwd)
repo=$(dirname "$here")
conf="${KANDEV_FLEET_CONF:-$HOME/.config/kandev-fleet.json}"
base="http://127.0.0.1:38429"

say() { printf '%s\n' "$*"; }
fail() { printf 'kandev/install-linux: %s\n' "$*" >&2; exit 1; }

[ -f "$conf" ] || fail "$conf is missing; copy coder/kandev-fleet.json there first"
version=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1])).get("kandev_version", ""))' "$conf")
[ -n "$version" ] || fail "$conf has no kandev_version"
bundle="$HOME/.local/share/kandev/$version/kandev"

render_units() {
  local out="$1" user unit
  user=$(id -un)
  mkdir -p "$out"
  for unit in kandev kandev-observer; do
    sed -e "s|@HOME@|$HOME|g" -e "s|@PATH@|$PATH|g" -e "s|@REPO@|$repo|g" -e "s|@BUNDLE@|$bundle|g" \
      -e "s|@VERSION@|$version|g" -e "s|@USER@|$user|g" "$here/systemd/$unit.service" > "$out/$unit.service"
  done
}

if [ "${1:-}" = --render-units ]; then
  render_units "${2:?usage: install-linux.sh --render-units <dir>}"
  exit 0
fi

command -v claude >/dev/null || [ -x "$HOME/.local/bin/claude" ] || fail "claude CLI must be on PATH or at ~/.local/bin/claude (the Kandev Claude profile runs it)"

tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT

if [ ! -x "$bundle/bin/kandev" ]; then
  case "$(uname -m)" in
    x86_64) arch=x64 ;;
    aarch64) arch=arm64 ;;
    *) fail "no Kandev Linux build for $(uname -m)" ;;
  esac
  url="https://github.com/kdlbs/kandev/releases/download/v$version/kandev-linux-$arch.tar.gz"
  say "installing kandev $version from $url"
  curl -fsSL -o "$tmp/kandev.tgz" "$url"
  curl -fsSL -o "$tmp/kandev.tgz.sha256" "$url.sha256"
  [ "$(cut -d' ' -f1 "$tmp/kandev.tgz.sha256")" = "$(sha256sum "$tmp/kandev.tgz" | cut -d' ' -f1)" ] \
    || fail "checksum mismatch for $url"
  mkdir -p "$(dirname "$bundle")"
  tar -C "$(dirname "$bundle")" -xzf "$tmp/kandev.tgz"
  [ -x "$bundle/bin/kandev" ] || fail "release archive has no kandev/bin/kandev"
else
  say "kandev $version already installed"
fi

mkdir -p "$HOME/.local/bin"
printf '#!/bin/sh\nKANDEV_BUNDLE_DIR=%s KANDEV_VERSION=%s exec %s/bin/kandev "$@"\n' "$bundle" "$version" "$bundle" \
  > "$tmp/kandev-wrapper"
chmod +x "$tmp/kandev-wrapper"
mv "$tmp/kandev-wrapper" "$HOME/.local/bin/kandev"

mkdir -p "$HOME/.kandev/logs"
if [ ! -f "$HOME/.kandev/config.yaml" ]; then
  printf 'server:\n  host: 127.0.0.1\n' > "$HOME/.kandev/config.yaml"
  say "wrote ~/.kandev/config.yaml (loopback only)"
fi
grep -q '127\.0\.0\.1' "$HOME/.kandev/config.yaml" || fail "~/.kandev/config.yaml does not bind to 127.0.0.1; refusing to expose the unauthenticated API"

acp_version=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1])).get("claude_acp_version","0.70.0"))' "$conf")
say "warming npm cache for @agentclientprotocol/claude-agent-acp@$acp_version"
printf '%s\n' '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":1,"clientCapabilities":{}}}' \
  | npx --yes --prefer-online "@agentclientprotocol/claude-agent-acp@$acp_version" 2>/dev/null | head -c 200 | grep -q protocolVersion \
  || say "warning: adapter did not answer initialize; Kandev's Claude probe may fail until npm metadata refreshes"

render_units "$tmp/units"
changed=0
for unit in kandev kandev-observer; do
  if ! cmp -s "$tmp/units/$unit.service" "/etc/systemd/system/$unit.service"; then
    sudo install -m 644 "$tmp/units/$unit.service" "/etc/systemd/system/$unit.service"
    changed=1
  fi
done
sudo systemctl daemon-reload
if systemctl is-active --quiet kandev; then
  if [ "$changed" = 1 ] || [ "${KANDEV_RESTART:-0}" = 1 ]; then
    say "restarting kandev (units changed or KANDEV_RESTART=1; pending plan-gate questions will be lost)"
    sudo systemctl restart kandev
  else
    say "kandev service already running; not restarting (set KANDEV_RESTART=1 to force)"
  fi
  sudo systemctl restart kandev-observer
else
  say "starting kandev and the observer as systemd services"
  sudo systemctl enable --now kandev kandev-observer
fi

for _ in $(seq 1 60); do
  curl -sf -o /dev/null "$base/api/v1/workspaces" 2>/dev/null && break
  sleep 2
done
curl -sf -o /dev/null "$base/api/v1/workspaces" || fail "kandev did not become ready on $base (see ~/.kandev/logs/service.err)"
say "kandev ready on $base"

python3 "$here/configure.py" --conf "$conf" --base "$base"

if command -v go >/dev/null; then
  "$here/plugins/install-plugin.sh" adhd-theme
else
  say "warning: go not installed; skipping the ADHD reading theme plugin"
fi
