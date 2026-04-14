# Codex Configuration

Personal configuration for Codex CLI (`~/.codex/`).

## What's here

| File | Purpose |
|------|---------|
| `AGENTS.md` | Global Codex instructions loaded from `$CODEX_HOME/AGENTS.md` |
| `install.sh` | Idempotent bootstrap for Codex dotfiles |
| `sync-mcps.sh` | Adds user-level Codex MCP server configs from the shared MCP source of truth |
| `skills/` | Global Codex skills ported from the Claude command set |

## MCP source of truth

Codex reuses the MCP definitions in `../claude/mcp-servers.json`.

This keeps one shared server list for both tools while allowing auth to stay machine-local.

## Setup on a new machine

Run the bootstrap script from the dotfiles repo root or from inside `codex/`:

```bash
./codex/install.sh
```

The script:

1. Symlinks `AGENTS.md` into `~/.codex/AGENTS.md`
2. Symlinks each skill directory into `~/.codex/skills/`
3. Adds any missing MCP server definitions to Codex

After that, log in to the MCPs you want to use:

```bash
codex mcp login linear-server
codex mcp login sentry
codex mcp login honeycomb
```

`gws` is a stdio server, so it uses whatever local auth the `gws` CLI already has.

## Notes

- `~/.codex/config.toml` remains machine-local and is not overwritten here.
- `~/.codex/rules/` remains machine-local.
- `~/.codex/sessions/`, `history.jsonl`, and auth state remain machine-local.
