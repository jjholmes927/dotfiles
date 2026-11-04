#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WARP_HOME="${HOME}/.warp"
BACKUP_DIR="${WARP_HOME}/backups/install-$(date +%Y-%m-%d-%H%M%S)"

already() { printf '  ✓ %s\n' "$1"; }
linking() { printf '  → %s\n' "$1"; }
backing() { printf '  ⚠ %s\n' "$1"; }

ensure_dir() {
  [[ -d "$1" ]] || mkdir -p "$1"
}

link() {
  local src="$1" dest="$2"
  ensure_dir "$(dirname "$dest")"

  if [[ -L "$dest" ]]; then
    local current
    current="$(readlink "$dest")"
    if [[ "$current" == "$src" ]]; then
      already "$dest"
      return 0
    fi
    backing "$dest (existing symlink -> $current, backing up)"
    ensure_dir "$BACKUP_DIR"
    mv "$dest" "$BACKUP_DIR/$(basename "$dest").symlink"
  elif [[ -e "$dest" ]]; then
    backing "$dest (existing file/dir, backing up)"
    ensure_dir "$BACKUP_DIR"
    mv "$dest" "$BACKUP_DIR/$(basename "$dest")"
  fi

  ln -s "$src" "$dest"
  linking "$dest -> $src"
}

for theme in "$SCRIPT_DIR"/themes/*.yaml; do
  link "$theme" "$WARP_HOME/themes/$(basename "$theme")"
done

if [[ -e "$WARP_HOME/settings.toml" ]]; then
  already "$WARP_HOME/settings.toml exists, left alone (compare with $SCRIPT_DIR/settings.toml)"
else
  ensure_dir "$WARP_HOME"
  cp "$SCRIPT_DIR/settings.toml" "$WARP_HOME/settings.toml"
  linking "$WARP_HOME/settings.toml copied from dotfiles"
fi
