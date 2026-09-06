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
offset="kandev-$(basename "$(dirname "$wt")" | tr -c 'a-zA-Z0-9\n' '-' | cut -c1-30)"

echo "kandev-worktree-setup: worktree=$wt offset=$offset"
cd "$wt"
[ -x bin/create_worktree ] || { echo "kandev-worktree-setup: bin/create_worktree missing in this checkout (branch predates GigMe PR #353); refusing to run on the shared databases" >&2; exit 1; }
WORKTREE_NAME="$offset" bin/create_worktree
echo "kandev-worktree-setup: done ($(grep -E '^(DB_SUFFIX|PORT)=' .env | tr '\n' ' '))"
