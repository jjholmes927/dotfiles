#!/usr/bin/env bash
set -uo pipefail

wt=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
offset=$(grep -E '^WORKTREE_OFFSET=' "$wt/.env" 2>/dev/null | cut -d= -f2)

case "$offset" in
  kandev-*) ;;
  *) echo "kandev-worktree-cleanup: offset '$offset' is not a kandev-* offset, leaving databases alone"; exit 0 ;;
esac

pids_in_worktree() {
  for pid in $(pgrep -f "$1" 2>/dev/null); do
    cwd=$(lsof -a -p "$pid" -d cwd -Fn 2>/dev/null | grep '^n' | cut -c2-)
    case "$cwd" in
      "$wt"|"$wt"/*) echo "$pid" ;;
    esac
  done
}

masters=$(pids_in_worktree 'overmind start|foreman start')
if [ -n "$masters" ]; then
  kill -TERM $masters 2>/dev/null
  for _ in $(seq 1 20); do
    ps -p "$(echo $masters | tr ' ' ',')" >/dev/null 2>&1 || break
    sleep 1
  done
  echo "kandev-worktree-cleanup: stopped dev stack ($(echo $masters))"
fi

stragglers=$(pids_in_worktree 'puma|vite|redis-server|tailwindcss|good_job')
if [ -n "$stragglers" ]; then
  kill -TERM $stragglers 2>/dev/null
  echo "kandev-worktree-cleanup: stopped leftover processes ($(echo $stragglers))"
fi
rm -f "$wt/.overmind.sock"

suffix=$(printf '%s' "$offset" | tr -c 'a-zA-Z0-9\n' '_')
existing=$(psql -lqt 2>/dev/null | cut -d'|' -f1 | tr -d ' ')
for name in development test development_good_job test_good_job; do
  db=$(printf 'beamai_%s_%s' "$name" "$suffix" | cut -c1-63)
  if echo "$existing" | grep -qx "$db"; then
    dropdb "$db" && echo "kandev-worktree-cleanup: dropped $db"
  fi
done
