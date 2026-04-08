# DotFiles for Joel

Personal configuration files, symlinked into `~/`. Each top-level directory holds config for one tool.

## Contents

| Directory | Purpose |
|-----------|---------|
| `alacritty/` | Alacritty terminal config |
| `bash/` | Bash shell config |
| `claude/` | Claude Code global config — `CLAUDE.md`, settings, commands, hooks, scripts |
| `git/` | Git config |
| `tmux/` | tmux config |
| `vim/` | Vim config |
| `vscode/` | VS Code settings and keybindings |

## Claude Code

The `claude/` directory is managed by a dedicated bootstrap script — see [`claude/README.md`](claude/README.md) for details. On a new machine:

```bash
./claude/install.sh
```

It symlinks `CLAUDE.md`, `settings.json`, `commands/`, `scripts/statusline.sh`, and `hooks/tmux-alert.sh` into `~/.claude/`. Idempotent and safe to re-run.

Note: project-level `CLAUDE.md` files live in each project repo, not here.
