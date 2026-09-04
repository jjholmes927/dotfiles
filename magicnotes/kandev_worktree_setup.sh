#!/usr/bin/env bash
set -euo pipefail

wt=$(git rev-parse --show-toplevel)
main=$(cd "$(dirname "$(git rev-parse --git-common-dir)")" && pwd)
offset="kandev-$(basename "$(dirname "$wt")" | tr -c 'a-zA-Z0-9\n' '-' | cut -c1-30)"

echo "kandev-worktree-setup: worktree=$wt main=$main offset=$offset"

cd "$wt"
bin/create_worktree

sed -i '' "s/^WORKTREE_OFFSET=.*/WORKTREE_OFFSET=$offset/" .env
grep -q '^WORKTREE_OFFSET=' .env || echo "WORKTREE_OFFSET=$offset" >> .env

set -a
while IFS='=' read -r key value; do
  case "$key" in
    WORKTREE_OFFSET|PORT|DEV_WEB_PORT|VITE_PORT|WSS_PORT|REDIS_PORT|REDIS_URL|SERVICE_URL) export "$key=$value" ;;
  esac
done < .env
set +a

SKIP_SERVER_RESTART=1 bin/setup
echo "kandev-worktree-setup: done (WORKTREE_OFFSET=$WORKTREE_OFFSET PORT=$PORT)"
