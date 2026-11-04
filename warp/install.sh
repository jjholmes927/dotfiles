#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WARP_HOME="${HOME}/.warp"

mkdir -p "$WARP_HOME/themes"

for theme in "$SCRIPT_DIR"/themes/*.yaml; do
  dest="$WARP_HOME/themes/$(basename "$theme")"
  if [[ -L "$dest" && "$(readlink "$dest")" == "$theme" ]]; then
    printf '  ✓ %s\n' "$dest"
    continue
  fi
  if [[ -e "$dest" || -L "$dest" ]]; then
    mv "$dest" "$dest.backup-$(date +%Y-%m-%d-%H%M%S)"
    printf '  ⚠ %s (backed up)\n' "$dest"
  fi
  ln -s "$theme" "$dest"
  printf '  → %s -> %s\n' "$dest" "$theme"
done

if [[ -e "$WARP_HOME/settings.toml" ]]; then
  printf '  ✓ %s exists, left alone (diff it against %s/settings.toml)\n' "$WARP_HOME/settings.toml" "$SCRIPT_DIR"
else
  cp "$SCRIPT_DIR/settings.toml" "$WARP_HOME/settings.toml"
  printf '  → %s copied from dotfiles\n' "$WARP_HOME/settings.toml"
fi
