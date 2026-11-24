#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROFILE_D="${HOME}/.profile.d"
BACKUP_DIR="${HOME}/.dotfiles-backups/bash-install-$(date +%Y-%m-%d-%H%M%S)"
BASHRC_START="# >>> dotfiles profile.d >>>"
BASHRC_END="# <<< dotfiles profile.d <<<"

already() { printf '  ✓ %s\n' "$1"; }
linking() { printf '  → %s\n' "$1"; }
backing() { printf '  ⚠ %s\n' "$1"; }
header()  { printf '\n%s\n' "$1"; }

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

header "Bash dotfiles install"
echo "  Source: $SCRIPT_DIR"

if [[ "$(uname -s)" == Linux ]]; then
  header "profile.d (Linux)"
  for name in alias bash-colours bash-completion bash-history otel; do
    link "$SCRIPT_DIR/.profile.d/$name" "$PROFILE_D/$name"
  done
  link "$SCRIPT_DIR/linux/exports" "$PROFILE_D/linux-exports"

  header ".bashrc"
  if grep -qF "$BASHRC_START" "$HOME/.bashrc" 2>/dev/null; then
    already "$HOME/.bashrc"
  else
    printf '\n%s\nfor f in "$HOME"/.profile.d/*; do [ -r "$f" ] && . "$f"; done\nunset f\n%s\n' \
      "$BASHRC_START" "$BASHRC_END" >> "$HOME/.bashrc"
    linking "$HOME/.bashrc (sources ~/.profile.d)"
  fi
else
  link "$SCRIPT_DIR/.bash_profile" "$HOME/.bash_profile"

  header "profile.d"
  for src in "$SCRIPT_DIR"/.profile.d/*; do
    [[ -f "$src" ]] || continue
    link "$src" "$PROFILE_D/$(basename "$src")"
  done
fi

header "Done"
if [[ -d "$BACKUP_DIR" ]]; then
  echo "  Backups: $BACKUP_DIR"
else
  echo "  No backups needed (clean install or already linked)."
fi
