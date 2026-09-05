#!/usr/bin/env bash
set -euo pipefail

here=$(cd "$(dirname "$0")" && pwd)
conf="${KANDEV_FLEET_CONF:-$HOME/.config/kandev-fleet.json}"
base="http://127.0.0.1:38429"

say() { printf '%s\n' "$*"; }
fail() { printf 'kandev/install: %s\n' "$*" >&2; exit 1; }

command -v brew >/dev/null || fail "Homebrew is required"
command -v python3 >/dev/null || fail "python3 is required"
command -v claude >/dev/null || fail "claude CLI must be on PATH (the Kandev Claude profile runs it)"

if ! brew list kandev >/dev/null 2>&1; then
  say "installing kandev"
  brew install kdlbs/kandev/kandev
else
  say "kandev $(kandev --version) already installed"
fi

mkdir -p "$HOME/.kandev"
if [ ! -f "$HOME/.kandev/config.yaml" ]; then
  printf 'server:\n  host: 127.0.0.1\n' > "$HOME/.kandev/config.yaml"
  say "wrote ~/.kandev/config.yaml (loopback only)"
fi
grep -q '127\.0\.0\.1' "$HOME/.kandev/config.yaml" || fail "~/.kandev/config.yaml does not bind to 127.0.0.1; refusing to expose the unauthenticated API"

if [ ! -f "$conf" ]; then
  mkdir -p "$(dirname "$conf")"
  cp "$here/kandev-fleet.example.json" "$conf"
  say "wrote $conf from the example; edit it (lanes, Linear team, watches) and re-run"
  exit 0
fi

acp_version=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1])).get("claude_acp_version","0.70.0"))' "$conf")
say "warming npm cache for @agentclientprotocol/claude-agent-acp@$acp_version"
printf '%s\n' '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":1,"clientCapabilities":{}}}' \
  | npx --yes --prefer-online "@agentclientprotocol/claude-agent-acp@$acp_version" 2>/dev/null | head -c 200 | grep -q protocolVersion \
  || say "warning: adapter did not answer initialize; Kandev's Claude probe may fail until npm metadata refreshes"

if kandev service status >/dev/null 2>&1; then
  say "restarting kandev service"
  kandev service restart >/dev/null
else
  say "installing kandev as a launchd service"
  kandev service install >/dev/null
fi

for _ in $(seq 1 60); do
  curl -sf -o /dev/null "$base/api/v1/workspaces" 2>/dev/null && break
  sleep 2
done
curl -sf -o /dev/null "$base/api/v1/workspaces" || fail "kandev did not become ready on $base"
say "kandev ready on $base"

python3 "$here/configure.py" --conf "$conf" --base "$base"
