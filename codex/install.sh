#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CODEX_HOME="${HOME}/.codex"
SKILLS_HOME="${CODEX_HOME}/skills"
BACKUP_DIR="${CODEX_HOME}/backups/install-$(date +%Y-%m-%d-%H%M%S)"

already() { printf '  ✓ %s\n' "$1"; }
linking() { printf '  -> %s\n' "$1"; }
backing() { printf '  ! %s\n' "$1"; }
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
    ensure_dir "$BACKUP_DIR"
    backing "$dest (existing symlink -> $current, backing up)"
    mv "$dest" "$BACKUP_DIR/$(basename "$dest").symlink"
  elif [[ -e "$dest" ]]; then
    ensure_dir "$BACKUP_DIR"
    backing "$dest (existing file/dir, backing up)"
    mv "$dest" "$BACKUP_DIR/$(basename "$dest")"
  fi

  ln -s "$src" "$dest"
  linking "$dest -> $src"
}

header "Codex dotfiles install"
echo "  Source: $SCRIPT_DIR"
echo "  Target: $CODEX_HOME"

ensure_dir "$CODEX_HOME"
ensure_dir "$SKILLS_HOME"

header "Global instructions"
link "$SCRIPT_DIR/AGENTS.md" "$CODEX_HOME/AGENTS.md"

header "Skills"
for skill_dir in "$SCRIPT_DIR"/skills/*; do
  [[ -d "$skill_dir" ]] || continue
  skill_name="$(basename "$skill_dir")"
  link "$skill_dir" "$SKILLS_HOME/$skill_name"
done

header "MCP servers"
chmod +x "$SCRIPT_DIR/sync-mcps.sh"
"$SCRIPT_DIR/sync-mcps.sh"

header "Done"
if [[ -d "$BACKUP_DIR" ]]; then
  echo "  Backups: $BACKUP_DIR"
else
  echo "  No backups needed."
fi
echo
echo "Next step: run 'codex mcp login <server>' for the MCPs you want to auth on this machine."
