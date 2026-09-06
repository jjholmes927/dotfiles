#!/usr/bin/env bash
set -euo pipefail

export LANG="${LANG:-en_GB.UTF-8}"
export LC_ALL="${LC_ALL:-en_GB.UTF-8}"

if command -v rbenv >/dev/null 2>&1; then
  eval "$(rbenv init - --no-rehash bash)"
elif [ -d "$HOME/.rbenv/shims" ]; then
  export PATH="$HOME/.rbenv/shims:$PATH"
fi

wt=$(git rev-parse --show-toplevel)
main=$(cd "$(dirname "$(git rev-parse --git-common-dir)")" && pwd)
offset="kandev-$(basename "$(dirname "$wt")" | tr -c 'a-zA-Z0-9\n' '-' | cut -c1-30)"

echo "kandev-worktree-setup: worktree=$wt main=$main offset=$offset"

cd "$wt"
bin/create_worktree

sed -i '' "s/^WORKTREE_OFFSET=.*/WORKTREE_OFFSET=$offset/" .env
grep -q '^WORKTREE_OFFSET=' .env || echo "WORKTREE_OFFSET=$offset" >> .env

tasks_root=$(dirname "$(dirname "$wt")")
used_ports=$(grep -hs '^PORT=' "$tasks_root"/*/*/.env "$main"/.worktrees/*/.env 2>/dev/null | grep -v -F "$(grep '^PORT=' .env || true)" | cut -d= -f2 | sort -u)
slot=20
while echo "$used_ports" | grep -qx "$((3000 + slot))"; do slot=$((slot + 1)); done
sed -i '' -e "s/^PORT=.*/PORT=$((3000 + slot))/" -e "s/^DEV_WEB_PORT=.*/DEV_WEB_PORT=$((3000 + slot))/" \
  -e "s/^VITE_PORT=.*/VITE_PORT=$((3130 + slot))/" -e "s/^WSS_PORT=.*/WSS_PORT=$((28080 + slot))/" \
  -e "s/^REDIS_PORT=.*/REDIS_PORT=$((6379 + slot))/" -e "s|^REDIS_URL=.*|REDIS_URL=redis://localhost:$((6379 + slot))/1|" \
  -e "s|^SERVICE_URL=.*|SERVICE_URL=http://localhost:$((3000 + slot))|" .env

set -a
while IFS='=' read -r key value; do
  case "$key" in
    WORKTREE_OFFSET|PORT|DEV_WEB_PORT|VITE_PORT|WSS_PORT|REDIS_PORT|REDIS_URL|SERVICE_URL) export "$key=$value" ;;
  esac
done < .env
set +a

SKIP_SERVER_RESTART=1 bin/setup
echo "kandev-worktree-setup: done (WORKTREE_OFFSET=$WORKTREE_OFFSET PORT=$PORT)"
