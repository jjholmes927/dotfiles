#!/usr/bin/env bash

set -uo pipefail

REPO_DIR="$(python3 -c 'from pathlib import Path; import sys; print(Path(sys.argv[1]).resolve().parents[2])' "${BASH_SOURCE[0]}")"
LOG="${HOME}/.claude/plugins/jjholmes927-update.log"
mkdir -p "$(dirname "$LOG")"

status=0
message=""
if output="$(python3 "$REPO_DIR/workflow/sync.py" --daily 2>&1)"; then
  if [[ -n "$output" ]]; then
    printf '%s\n' "$output" >> "$LOG"
    message="Workflow skills refreshed. Restart sessions to load updates."
  fi
else
  printf '%s\n' "$output" >> "$LOG"
  message="Workflow sync failed. See ~/.claude/plugins/jjholmes927-update.log."
  status=1
fi

updates="$(python3 "$REPO_DIR/workflow/plugin-updates.py" --daily 2>>"$LOG")"
message="$(printf '%s\n%s\n' "$message" "$updates" | sed '/^$/d')"
if [[ -n "$message" ]]; then
  python3 -c 'import json, sys; print(json.dumps({"systemMessage": sys.argv[1]}))' "$message"
fi
exit "$status"
