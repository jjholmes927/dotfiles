#!/usr/bin/env bash
#
# Idempotent bootstrap for Claude Code config on a new machine.
# Symlinks files from this dotfiles repo into ~/.claude/.
# Safe to run multiple times. Backs up anything it would overwrite.
#
# Usage:  ./claude/install.sh      (from dotfiles repo root)
#         ./install.sh             (from inside dotfiles/claude/)

set -euo pipefail

# Resolve repo paths regardless of where the script is invoked from.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CLAUDE_HOME="${HOME}/.claude"
BACKUP_DIR="${CLAUDE_HOME}/backups/install-$(date +%Y-%m-%d-%H%M%S)"

# Output helpers
already() { printf '  ✓ %s\n' "$1"; }
linking() { printf '  → %s\n' "$1"; }
backing() { printf '  ⚠ %s\n' "$1"; }
header()  { printf '\n%s\n' "$1"; }

ensure_dir() {
  [[ -d "$1" ]] || mkdir -p "$1"
}

# Symlink $1 -> $2, backing up anything already at $2 that isn't already the right symlink.
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

header "Claude Code dotfiles install"
echo "  Source: $SCRIPT_DIR"
echo "  Target: $CLAUDE_HOME"

ensure_dir "$CLAUDE_HOME"

header "Global instructions and settings"
link "$SCRIPT_DIR/CLAUDE.md"        "$CLAUDE_HOME/CLAUDE.md"
link "$SCRIPT_DIR/settings.json"    "$CLAUDE_HOME/settings.json"
link "$SCRIPT_DIR/skill-feedback.md" "$CLAUDE_HOME/skill-feedback.md"

header "Commands (directory-level symlink)"
link "$SCRIPT_DIR/commands" "$CLAUDE_HOME/commands"

header "Scripts"
link "$SCRIPT_DIR/scripts/statusline.sh" "$CLAUDE_HOME/scripts/statusline.sh"
chmod +x "$SCRIPT_DIR/scripts/statusline.sh"

header "Hooks"
link "$SCRIPT_DIR/hooks/tmux-alert.sh" "$CLAUDE_HOME/hooks/tmux-alert.sh"
chmod +x "$SCRIPT_DIR/hooks/tmux-alert.sh"

header "MCP servers"
link "$SCRIPT_DIR/mcp-servers.json" "$CLAUDE_HOME/mcp-servers.json"
chmod +x "$SCRIPT_DIR/sync-mcps.sh"
"$SCRIPT_DIR/sync-mcps.sh"

header "Done"
if [[ -d "$BACKUP_DIR" ]]; then
  echo "  Backups: $BACKUP_DIR"
else
  echo "  No backups needed (clean install or already linked)."
fi
echo
echo "Note: settings.local.json (machine-specific permissions) is intentionally NOT symlinked."
echo "Note: ~/.claude/projects/ (sessions + memory) is intentionally NOT touched."
echo "Note: MCP auth remains machine-local. Only the server definitions are synced here."
