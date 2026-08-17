#!/usr/bin/env bash

set -uo pipefail

PLUGINS_DIR="${HOME}/.claude/plugins"
MARKER="${PLUGINS_DIR}/.jjholmes927-update-check"
LOG="${PLUGINS_DIR}/jjholmes927-update.log"

today="$(date +%Y-%m-%d)"
if [[ -f "$MARKER" ]] && [[ "$(cat "$MARKER" 2>/dev/null)" == "$today" ]]; then
  exit 0
fi
echo "$today" > "$MARKER"

command -v claude >/dev/null 2>&1 || exit 0
command -v jq >/dev/null 2>&1 || exit 0

marketplaces="$(jq -r 'to_entries[] | select(.value.source.repo // "" | startswith("jjholmes927/")) | .key' \
  "${PLUGINS_DIR}/known_marketplaces.json" 2>/dev/null)"
[[ -n "$marketplaces" ]] || exit 0

bumps=""
{
  echo "=== $(date '+%Y-%m-%d %H:%M:%S') update check ==="
  for mkt in $marketplaces; do
    claude plugin marketplace update "$mkt" 2>&1
    plugins="$(jq -r --arg mkt "@${mkt}" '.plugins | keys[] | select(endswith($mkt))' \
      "${PLUGINS_DIR}/installed_plugins.json" 2>/dev/null)"
    for plugin in $plugins; do
      out="$(claude plugin update "$plugin" 2>&1)"
      echo "$out"
      bump="$(echo "$out" | grep -o 'updated from [0-9.]* to [0-9.]*' | head -1)"
      [[ -n "$bump" ]] && bumps="${bumps}${plugin} ${bump}; "
    done
  done
} >> "$LOG" 2>&1

if [[ -n "$bumps" ]]; then
  jq -cn --arg msg "Plugin auto-update: ${bumps}restart Claude Code to apply." '{systemMessage: $msg}'
fi
exit 0
