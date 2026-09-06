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
  if [ "${KANDEV_RESTART:-0}" = 1 ]; then
    say "restarting kandev service (KANDEV_RESTART=1; pending plan-gate questions will be lost)"
    kandev service restart >/dev/null
  else
    say "kandev service already running; not restarting (set KANDEV_RESTART=1 to force)"
  fi
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

plist="$HOME/Library/LaunchAgents/com.jjholmes927.kandev-observer.plist"
mkdir -p "$HOME/Library/LaunchAgents" "$HOME/.kandev/logs"
cat > "$plist.tmp" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>com.jjholmes927.kandev-observer</string>
  <key>ProgramArguments</key><array><string>$here/fleet-observer.sh</string></array>
  <key>EnvironmentVariables</key><dict><key>PATH</key><string>$PATH</string></dict>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>StandardOutPath</key><string>$HOME/.kandev/logs/observer.out</string>
  <key>StandardErrorPath</key><string>$HOME/.kandev/logs/observer.err</string>
</dict></plist>
PLIST
if [ ! -f "$plist" ] || ! cmp -s "$plist.tmp" "$plist"; then
  mv "$plist.tmp" "$plist"
  launchctl bootout "gui/$(id -u)/com.jjholmes927.kandev-observer" >/dev/null 2>&1 || true
  pkill -f "kandev/fleet-observer.sh" >/dev/null 2>&1 || true
  launchctl bootstrap "gui/$(id -u)" "$plist"
  say "observer installed as launchd agent com.jjholmes927.kandev-observer"
else
  rm -f "$plist.tmp"
  if launchctl print "gui/$(id -u)/com.jjholmes927.kandev-observer" >/dev/null 2>&1; then
    launchctl kickstart -k "gui/$(id -u)/com.jjholmes927.kandev-observer"
    say "observer restarted on the current scripts"
  else
    launchctl bootstrap "gui/$(id -u)" "$plist"
    say "observer started"
  fi
fi
