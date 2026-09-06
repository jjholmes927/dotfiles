#!/usr/bin/env bash
set -uo pipefail

wt=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
db_suffix=$(grep -E '^DB_SUFFIX=' "$wt/.env" 2>/dev/null | cut -d= -f2)

case "$db_suffix" in
  kandev_*) ;;
  *) echo "kandev-worktree-cleanup: DB_SUFFIX '$db_suffix' is not a kandev_* suffix, leaving databases alone"; exit 0 ;;
esac

for db in $(psql -lqt 2>/dev/null | cut -d'|' -f1 | tr -d ' ' | grep -E "^gigme_(development|test)(_queue)?_${db_suffix}$"); do
  dropdb "$db" && echo "kandev-worktree-cleanup: dropped $db"
done
