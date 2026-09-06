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
db_suffix=$(printf '%s' "$offset" | tr -c 'a-zA-Z0-9\n' '_' | tr 'A-Z' 'a-z')

echo "kandev-worktree-setup: worktree=$wt main=$main offset=$offset db_suffix=$db_suffix"

cd "$wt"
grep -q 'DB_SUFFIX' config/database.yml || { echo "kandev-worktree-setup: config/database.yml does not read DB_SUFFIX; refusing to run on the shared databases" >&2; exit 1; }

[ -f config/master.key ] || { [ -f "$main/config/master.key" ] && cp "$main/config/master.key" config/master.key; }
touch .env
sed -i '' '/^DB_SUFFIX=/d' .env
echo "DB_SUFFIX=$db_suffix" >> .env

tasks_root=$(dirname "$(dirname "$wt")")
used_ports=$(grep -hs '^PORT=' "$tasks_root"/*/*/.env "$main"/.worktrees/*/.env 2>/dev/null | grep -v -x -F "$(grep '^PORT=' .env || echo PORT=none)" | cut -d= -f2 | sort -u || true)
slot=20
while echo "$used_ports" | grep -qx "$((3000 + slot))"; do slot=$((slot + 1)); done
sed -i '' -e '/^PORT=/d' -e '/^VITE_RUBY_PORT=/d' .env
printf 'PORT=%s\nVITE_RUBY_PORT=%s\n' "$((3000 + slot))" "$((3000 + slot + 36))" >> .env

set -a
while IFS='=' read -r key value; do
  case "$key" in
    DB_SUFFIX|PORT|VITE_RUBY_PORT) export "$key=$value" ;;
  esac
done < .env
set +a

bin/setup --skip-server
if command -v pnpm >/dev/null 2>&1 && [ -f pnpm-lock.yaml ]; then
  pnpm install --frozen-lockfile --silent
fi
echo "kandev-worktree-setup: done (DB_SUFFIX=$DB_SUFFIX PORT=$PORT)"
