# Codex Configuration

Personal configuration for Codex CLI (`~/.codex/`).

See the [setup map](../docs/agent-setup.md) for source ownership and the complete
cross-harness inventory, and the [operator contract](../docs/operator-workflow.md#shared-lifecycle-contract)
for the requirements these adapters preserve.

## What's here

| File | Purpose |
|------|---------|
| `AGENTS.md` | Global Codex instructions loaded from `$CODEX_HOME/AGENTS.md` |
| `install.sh` | Idempotent bootstrap for Codex dotfiles |
| `sync-mcps.sh` | Adds user-level Codex MCP server configs from the shared MCP source of truth |
| `skills/` | Global Codex skills ported from the Claude command set |
| `sync-workflow.py` | Builds ship, verify, verify-ui and PR-writing skills from the installed personal workflow release |

## MCP source of truth

Codex reuses the MCP definitions in `../claude/mcp-servers.json`.

This keeps one shared server list for both tools while allowing auth to stay machine-local.

## Setup on a new machine

Install the personal workflow parity release first, following the
[package setup order](../docs/agent-setup.md#install-update-and-remove). Then run
the bootstrap script from the dotfiles repo root or from inside `codex/`:

```bash
./codex/install.sh
```

The script:

1. Symlinks `AGENTS.md` into `~/.codex/AGENTS.md`
2. Symlinks the remaining dotfiles skill directories into `~/.codex/skills/`
3. Generates ship, verify, verify-ui and PR-writing adapters from the installed personal release
4. Adds any missing MCP server definitions to Codex

After that, log in to the MCPs you want to use:

```bash
codex mcp login linear-server
codex mcp login sentry
codex mcp login honeycomb
```

## Shared delivery workflow

Install or update the personal `joel-workflow` parity release first, then run
`python3 codex/sync-workflow.py`. It reads the installed user plugin directory,
builds the four delivery skills with full source instructions and Codex tool
mapping, and records source paths, version and hashes in
`~/.codex/workflow-migration.json`. Existing skill links/files are backed up;
provider configuration, credentials, rules and unrelated skills are preserved.
Restart the Codex session to refresh its skill catalog.

For a committed local release before publishing to GitHub:

```bash
python3 codex/install-workflow-release.py --source /path/to/personal-workflow --install
python3 codex/sync-workflow.py
python3 opencode/install.py --workflow-only
```

This pins the existing Claude marketplace name to a committed snapshot under
`~/.local/share/joel-workflow/releases/`, using Claude's supported local-marketplace
CLI. It backs up the prior registration/settings, preserves the old cache, and
records file hashes and source commit. Subsequent upstream updates are deliberately
paused while this local source is selected. To return to published releases,
run `claude plugin marketplace add jjholmes927/jjholmes927-claude-skills`, update
the plugin, then refresh the Codex and OpenCode adapters. The OpenCode
`--workflow-only` refresh preserves other adapters, MCP settings and model choices.

The generated skills retain verification evidence, tree fingerprints, the
500-line total-diff cap and bounded CI/review repairs. Edit the personal workflow
source and rebuild the adapters rather than editing generated references.
The previous short ship/verify-ui definitions are retired.

For an isolated installation, use:

```bash
python3 codex/sync-workflow.py --source /path/to/joel-workflow --target /tmp/codex-workflow-preview
python3 -B -m unittest discover -s codex -p 'test_*.py'
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
