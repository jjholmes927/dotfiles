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

## Prerequisites

On a fresh Mac, install Homebrew, then install every CLI the dotfiles depend on from the `Brewfile` (jq is load-bearing: the Claude statusline tmux sync and settings.json hooks silently no-op without it):

```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
brew bundle install
```

Codex CLI is npm-managed, not brew: `npm i -g @openai/codex`.

Then authenticate with GitHub:

```bash
gh auth login
```

## Claude Code

The `claude/` directory is managed by a dedicated bootstrap script — see [`claude/README.md`](claude/README.md) for details. On a new machine:

```bash
npm install -g @anthropic-ai/claude-code
./claude/install.sh
```

The `npm install` gives you the `claude` CLI. The install script symlinks `CLAUDE.md`, `settings.json`, `commands/`, `scripts/statusline.sh`, and `hooks/tmux-alert.sh` into `~/.claude/`. Idempotent and safe to re-run.

Note: project-level `CLAUDE.md` files live in each project repo, not here.

## Codex

The `codex/` directory is managed by a dedicated bootstrap script — see [`codex/README.md`](codex/README.md) for details. On a new machine:

```bash
npm install -g @openai/codex
./codex/install.sh
```

The `npm install` gives you the `codex` CLI (required for the MCP sync step). The install script symlinks `AGENTS.md` and the global skills into `~/.codex/`, then adds the shared MCP server definitions at the user level so you can authenticate the MCPs you want on that machine.
