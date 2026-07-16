#!/usr/bin/env bash
set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CLAUDE_HOME="${HOME}/.claude"

mkdir -p "$CLAUDE_HOME/commands"
cp "$SCRIPT_DIR/CLAUDE.md" "$CLAUDE_HOME/CLAUDE.md" 2>/dev/null || true
cp "$SCRIPT_DIR"/commands/*.md "$CLAUDE_HOME/commands/" 2>/dev/null || true

echo "cloud-setup: installed CLAUDE.md and $(ls "$CLAUDE_HOME/commands" | wc -l | tr -d ' ') commands into $CLAUDE_HOME"
exit 0
