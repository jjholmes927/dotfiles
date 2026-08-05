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

## Using skills

Codex skills are usually triggered automatically from the skill `description` when your request matches the wording.

You can also invoke them intentionally by naming them in your prompt, for example:

```text
use verify-ui to check the login page
use handoff for this session
use pick-up-linear-ticket for INT-156
```

## Telemetry (OTel → Honeycomb)

Codex exports natively to Honeycomb (dataset `codex_exec` in the Agent Traces team). Because `config.toml` is machine-local, add this block manually on each machine, substituting the ingest key from the Keychain (`security find-generic-password -s honeycomb-agent-traces -w`):

```toml
[otel]
environment = "prod"
log_user_prompt = false
exporter = { otlp-http = { endpoint = "https://api.eu1.honeycomb.io/v1/logs", protocol = "binary", headers = { "x-honeycomb-team" = "<INGEST_KEY>" } } }
```

The matching Claude Code exporter is wired via `claude/settings.json` (non-secret env vars) + `bash/.profile.d/otel` (reads the key from the Keychain). One-time Keychain setup per machine:

```bash
security add-generic-password -a "$USER" -s honeycomb-agent-traces -w '<INGEST_KEY>' -U
```

## Notes

- `~/.codex/config.toml` remains machine-local and is not overwritten here.
- `~/.codex/rules/` remains machine-local.
- `~/.codex/sessions/`, `history.jsonl`, and auth state remain machine-local.
