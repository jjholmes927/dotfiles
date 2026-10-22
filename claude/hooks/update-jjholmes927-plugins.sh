#!/usr/bin/env bash

set -uo pipefail

REPO_DIR="$(python3 -c 'from pathlib import Path; import sys; print(Path(sys.argv[1]).resolve().parents[2])' "${BASH_SOURCE[0]}")"
LOG="${HOME}/.claude/plugins/jjholmes927-update.log"
mkdir -p "$(dirname "$LOG")"

if output="$(python3 "$REPO_DIR/workflow/sync.py" --daily 2>&1)"; then
  [[ -n "$output" ]] || exit 0
  printf '%s\n' "$output" >> "$LOG"
  printf '%s\n' '{"systemMessage":"Workflow skills refreshed. Restart sessions to load updates."}'
else
  printf '%s\n' "$output" >> "$LOG"
  printf '%s\n' '{"systemMessage":"Workflow sync failed. See ~/.claude/plugins/jjholmes927-update.log."}'
  exit 1
fi
