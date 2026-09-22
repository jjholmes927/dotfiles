# DotFiles for Joel

Personal configuration files, symlinked into `~/`. Each top-level directory holds config for one tool.

## Agent workflow

Start with the [agent setup map](docs/agent-setup.md) for package sources,
versions, the full Beam/personal skill inventory, ownership and portability.
The [operator workflow](docs/operator-workflow.md#shared-lifecycle-contract)
defines the stages from ticket intake through ship, deployment and closure.
[Kandev setup](docs/kandev-setup.md) describes the current launcher and its gaps.

Skills stay in their owning repositories; dotfiles links them and installs the
harness adapters. The map records provenance and personal counterparts so useful
skills can be traced when the setup changes. Installed caches are not edit targets.

## Contents

| Directory | Purpose |
|-----------|---------|
| `alacritty/` | Alacritty terminal config |
| `bash/` | Bash shell config — aliases, exports, history and completion |
| `bin/` | Legacy Fleet/operator helpers, symlinked into `~/.local/bin` by `claude/install.sh`; [historical reference](docs/operator-workflow.md#legacy-fleet-reference) |
| `claude/` | Claude Code global config — `CLAUDE.md`, settings, commands, hooks, scripts |
| `codex/` | Codex global config — `AGENTS.md`, skills, installer, MCP bootstrap |
| `cursor/` | Cursor CLI — shared personal/Beam skill adapters, compatibility and drift checks |
| `opencode/` | OpenCode migration — workflow adapters, skills, MCPs, notifications, installer |
| `kandev/` | Task intake, worktree/profile setup and local Kandev configuration |
| `docs/` | Agent package map, shared workflow contract and setup guides |
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

The `codex/` directory is managed by a dedicated bootstrap script — see [`codex/README.md`](codex/README.md) for details. Install the personal workflow parity release first, following the [package setup order](docs/agent-setup.md#install-update-and-remove). Then, on a new machine:

```bash
npm install -g @openai/codex
./codex/install.sh
```

The `npm install` gives you the `codex` CLI (required for the MCP sync step). The bootstrap links global instructions and the remaining local skills, generates four shared delivery skills plus Socratic interview when Beam is enabled, and adds the shared MCP definitions so you can authenticate them on this machine.

## OpenCode

After installing OpenCode and connecting a model provider:

```bash
bash opencode/install.sh
python3 opencode/doctor.py
```

Restart OpenCode to load the migrated commands and skills. See
[`opencode/README.md`](opencode/README.md) for MCP login, source precedence,
backups, and compatibility boundaries.

## Cursor CLI

After installing/authenticating Cursor CLI and its desired source packages:

```bash
python3 cursor/install.py
python3 cursor/install.py --package beam --if-installed
workflow-doctor
```

Start a fresh standalone or Kandev Cursor session. See [Cursor setup](cursor/README.md)
for imported skills, discovery, backups and configuration boundaries.
