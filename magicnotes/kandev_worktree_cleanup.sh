#!/usr/bin/env bash
set -uo pipefail

wt=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
offset=$(grep -E '^WORKTREE_OFFSET=' "$wt/.env" 2>/dev/null | cut -d= -f2)

case "$offset" in
  kandev-*) ;;
  *) echo "kandev-worktree-cleanup: offset '$offset' is not a kandev-* offset, leaving databases alone"; exit 0 ;;
esac

suffix=$(printf '%s' "$offset" | tr -c 'a-zA-Z0-9\n' '_')
for db in $(psql -lqt 2>/dev/null | cut -d'|' -f1 | tr -d ' ' | grep -E "^beamai_(development|test)(_good_job)?_${suffix}$"); do
  dropdb "$db" && echo "kandev-worktree-cleanup: dropped $db"
done
