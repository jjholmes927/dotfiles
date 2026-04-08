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
| `/save-permissions` | Scan recent sessions and save missing Bash permission patterns to `.claude/settings.local.json` |
| `/second-brain` | Process second brain inbox and run vault commands |
| `/ship` | End-to-end ship workflow: format, commit, push, PR, CI watch, code review |
| `/skill-reviewer` | Review a Claude Code skill for structural and domain quality |
| `/verify-ui` | Verify a UI flow using agent-browser against the live dev server |

## Setup on a new machine

Run the bootstrap script from the dotfiles repo root (or from inside `claude/`):

```bash
./claude/install.sh
```

The script is idempotent — safe to re-run. It symlinks `CLAUDE.md`, `settings.json`, `commands/`, `scripts/statusline.sh`, and `hooks/tmux-alert.sh` into `~/.claude/`, and backs up anything it would overwrite to `~/.claude/backups/install-<timestamp>/`.

## Unified memory across parallel clones (GigMe only)

Claude Code keys its memory dir by absolute CWD, so working on the same repo from multiple clones (`GigMe/`, `gigme2/`, `gigme3/`) would normally fragment memory across three isolated dirs. To fix this, each clone's memory dir is symlinked at a canonical shared location:

```
~/.claude/shared-memory/gigme/                            ← real dir, single source of truth
~/.claude/projects/<encoded-GigMe>/memory   → shared-memory/gigme
~/.claude/projects/<encoded-gigme2>/memory  → shared-memory/gigme
~/.claude/projects/<encoded-gigme3>/memory  → shared-memory/gigme
```

This unification is **per-machine and GigMe-only**. It isn't managed by `install.sh` and isn't synced across machines (intentional — personal and work laptops stay independent). To add a new GigMe clone, symlink its memory dir after the first Claude Code session creates the project folder:

```bash
ln -sfn ~/.claude/shared-memory/gigme \
  ~/.claude/projects/<encoded-path-of-new-clone>/memory
```

## Notes

- `settings.json` contains plugin references that may need adjusting per machine (e.g. if plugins aren't installed yet)
- `settings.local.json` (permissions) is intentionally excluded — it's machine-specific
- Project-level `CLAUDE.md` files live in each repo, not here
- `~/.claude/projects/` (session history and memory) is not touched by `install.sh` — too machine-specific and paths-based to sync via dotfiles
- The tmux notification hook requires `monitor-bell on` and `bell-action any` in tmux (enabled by default in gpakosz/.tmux)
