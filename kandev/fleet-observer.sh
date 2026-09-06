#!/usr/bin/env bash
set -uo pipefail

here=$(cd "$(dirname "$0")" && pwd)
B="${KANDEV_BASE:-http://127.0.0.1:38429}"
LOG="${KANDEV_OBSERVER_LOG:-$HOME/.kandev/logs/fleet-observer.log}"
INTERVAL="${KANDEV_OBSERVER_INTERVAL:-60}"
mkdir -p "$(dirname "$LOG")"

while true; do
  python3 "$here/fleet-observer.py" "$B" "$(date -u +%FT%TZ)" >> "$LOG" 2>&1
  sleep "$INTERVAL"
done
