# Claude Code Configuration

Personal configuration for [Claude Code](https://docs.anthropic.com/en/docs/claude-code) (`~/.claude/`).

## What's here

| File | Purpose |
|------|---------|
| `CLAUDE.md` | Global instructions loaded into every Claude Code session (coding style, commit conventions, PR format, etc.) |
| `settings.json` | Model preference, enabled plugins, status line config, notification hooks |
| `commands/` | Custom slash commands available in all projects |
| `hooks/tmux-alert.sh` | Sends a tmux bell when Claude needs attention (permission prompts, idle, input dialogs) |
| `scripts/statusline.sh` | Status line script that shows git branch, context usage, and model info |

### Slash commands

| Command | Description |
|---------|-------------|
| `/brag-doc` | Generate weekly brag doc entries from GitHub activity |
| `/context-check` | Assess context health and recommend action (continue, compact, handoff, clear) |
| `/handoff` | Create a handoff summary for continuing work in a fresh session |
| `/log-error` | Interview-style error logging to identify prompting/context mistakes |
| `/second-brain` | Process second brain inbox and run vault commands |

## Setup on a new machine

Claude Code stores its config at `~/.claude/`. Symlink the files from this repo:

```bash
# Symlink the global instructions
ln -sf "$(pwd)/claude/CLAUDE.md" ~/.claude/CLAUDE.md

# Symlink settings
ln -sf "$(pwd)/claude/settings.json" ~/.claude/settings.json

# Symlink custom commands
mkdir -p ~/.claude/commands
for f in claude/commands/*.md; do
  ln -sf "$(pwd)/$f" ~/.claude/commands/$(basename "$f")
done

# Symlink scripts
mkdir -p ~/.claude/scripts
ln -sf "$(pwd)/claude/scripts/statusline.sh" ~/.claude/scripts/statusline.sh
chmod +x ~/.claude/scripts/statusline.sh

# Symlink hooks
mkdir -p ~/.claude/hooks
ln -sf "$(pwd)/claude/hooks/tmux-alert.sh" ~/.claude/hooks/tmux-alert.sh
chmod +x ~/.claude/hooks/tmux-alert.sh
```

Or as a one-liner from the dotfiles repo root:

```bash
ln -sf "$(pwd)/claude/CLAUDE.md" ~/.claude/CLAUDE.md && \
ln -sf "$(pwd)/claude/settings.json" ~/.claude/settings.json && \
mkdir -p ~/.claude/commands ~/.claude/scripts ~/.claude/hooks && \
for f in claude/commands/*.md; do ln -sf "$(pwd)/$f" ~/.claude/commands/$(basename "$f"); done && \
ln -sf "$(pwd)/claude/scripts/statusline.sh" ~/.claude/scripts/statusline.sh && \
chmod +x ~/.claude/scripts/statusline.sh && \
ln -sf "$(pwd)/claude/hooks/tmux-alert.sh" ~/.claude/hooks/tmux-alert.sh && \
chmod +x ~/.claude/hooks/tmux-alert.sh
```

## Notes

- `settings.json` contains plugin references that may need adjusting per machine (e.g. if plugins aren't installed yet)
- `settings.local.json` (permissions) is intentionally excluded - it's machine-specific
- Project-level `CLAUDE.md` files live in each repo, not here
- The `projects/` directory (per-project memory) uses absolute paths and doesn't sync
- The tmux notification hook requires `monitor-bell on` and `bell-action any` in tmux (enabled by default in gpakosz/.tmux)
