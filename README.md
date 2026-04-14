# DotFiles for Joel

Personal configuration files, symlinked into `~/`. Each top-level directory holds config for one tool.

## Contents

| Directory | Purpose |
|-----------|---------|
| `alacritty/` | Alacritty terminal config |
| `bash/` | Bash shell config |
| `claude/` | Claude Code global config — `CLAUDE.md`, settings, commands, hooks, scripts |
| `codex/` | Codex global config — `AGENTS.md`, skills, installer, MCP bootstrap |
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

## Codex

The `codex/` directory is managed by a dedicated bootstrap script — see [`codex/README.md`](codex/README.md) for details. On a new machine:

```bash
./codex/install.sh
```

It symlinks `AGENTS.md` and the global skills into `~/.codex/`, then adds the shared MCP server definitions at the user level so you can authenticate the MCPs you want on that machine.
