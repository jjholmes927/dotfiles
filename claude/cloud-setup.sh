#!/usr/bin/env bash
set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CLAUDE_HOME="${HOME}/.claude"

mkdir -p "$CLAUDE_HOME/commands"
cp "$SCRIPT_DIR/CLAUDE.md" "$CLAUDE_HOME/CLAUDE.md" 2>/dev/null || true
cp "$SCRIPT_DIR"/commands/*.md "$CLAUDE_HOME/commands/" 2>/dev/null || true

if [ ! -L "$CLAUDE_HOME/commands" ]; then
  rm -rf /tmp/jj-skills
  git clone --depth 1 https://github.com/jjholmes927/jjholmes927-claude-skills /tmp/jj-skills 2>/dev/null || true
  cp /tmp/jj-skills/commands/*.md "$CLAUDE_HOME/commands/" 2>/dev/null || true
fi

echo "cloud-setup: installed CLAUDE.md and $(ls "$CLAUDE_HOME/commands" | wc -l | tr -d ' ') commands into $CLAUDE_HOME"
exit 0
